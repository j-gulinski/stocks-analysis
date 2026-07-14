"""Read-only observability for the canonical durable job queue.

Jobs are created only by their stage-specific commands and declared automatic
producers. A generic queue mutation would bypass those frozen-input contracts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import AgentRunOut
from app.db.base import get_db
from app.db.models import AgentRun, Company
from app.services.model_policy import CANONICAL_WORKFLOWS

router = APIRouter(tags=["agent-runs"])

ALLOWED_WORKFLOWS = CANONICAL_WORKFLOWS

def _get_company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


def _bounded_limit(limit: int) -> int:
    return min(max(limit, 1), 200)


@router.get("/agent-runs", response_model=list[AgentRunOut])
def list_agent_runs(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    workflow: str | None = None,
    ticker: str | None = None,
    limit: int = 50,
) -> list[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.workflow.in_(ALLOWED_WORKFLOWS))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    )
    if status_filter:
        stmt = stmt.where(AgentRun.status == status_filter)
    if workflow:
        if workflow not in ALLOWED_WORKFLOWS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported Codex workflow '{workflow}'.",
            )
        stmt = stmt.where(AgentRun.workflow == workflow)
    if ticker:
        company = _get_company_or_404(db, ticker)
        stmt = stmt.where(AgentRun.company_id == company.id)
    return list(db.scalars(stmt.limit(_bounded_limit(limit))))
