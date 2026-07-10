"""Provider-neutral Codex workflow read endpoints (stage CX).

These endpoints intentionally do not execute Codex. They expose the durable rows
that Codex skills/scripts/MCP tools will create, so the UI can read queued,
draft, verified and rejected work without depending on chat state.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AgentRunCreateIn,
    AgentRunOut,
    AnalysisRunOut,
    EventReportOut,
    PreSessionBriefIn,
    PreSessionBriefOut,
)
from app.db.base import get_db
from app.db.models import AgentRun, AnalysisRun, Company, EventReport
from app.scrapers import espi

router = APIRouter(tags=["agent-runs"])

ALLOWED_WORKFLOWS = {
    "stock-pre-session-brief",
    "stock-quick-analysis",
    "stock-deep-analysis",
    "stock-candidate-scout",
    "stock-backtest-review",
    "stock-verifier",
}


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
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    if status_filter:
        stmt = stmt.where(AgentRun.status == status_filter)
    if workflow:
        stmt = stmt.where(AgentRun.workflow == workflow)
    if ticker:
        company = _get_company_or_404(db, ticker)
        stmt = stmt.where(AgentRun.company_id == company.id)
    return list(db.scalars(stmt.limit(_bounded_limit(limit))))


@router.post(
    "/agent-runs",
    response_model=AgentRunOut,
    status_code=status.HTTP_201_CREATED,
)
def queue_agent_run(payload: AgentRunCreateIn, db: Session = Depends(get_db)) -> AgentRun:
    workflow = payload.workflow.strip()
    if workflow not in ALLOWED_WORKFLOWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported Codex workflow '{workflow}'.",
        )

    inputs = dict(payload.inputs)
    company_id = None
    if payload.ticker:
        company = _get_company_or_404(db, payload.ticker)
        company_id = company.id
        inputs = {**inputs, "ticker": company.ticker}

    agent = AgentRun(
        workflow=workflow,
        trigger=payload.trigger,
        status="queued",
        company_id=company_id,
        model_role=payload.model_role,
        model=payload.model,
        orchestrator_model=payload.orchestrator_model,
        inputs=inputs,
        outputs={},
    )
    db.add(agent)
    db.commit()
    return agent


@router.post(
    "/agent-runs/pre-session",
    response_model=PreSessionBriefOut,
    status_code=status.HTTP_201_CREATED,
)
def prepare_pre_session_brief(
    payload: PreSessionBriefIn,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    company = _get_company_or_404(db, payload.ticker) if payload.ticker else None
    poll_result = espi.poll_watchlist_reports(
        db,
        ticker=company.ticker if company else None,
        fetch_details=payload.fetch_details,
    )
    if not payload.queue:
        response.status_code = status.HTTP_200_OK
        return {
            "ok": bool(poll_result.get("ok") and poll_result.get("complete")),
            "espi_poll": poll_result,
            "agent_run": None,
        }
    if not poll_result.get("complete"):
        response.status_code = status.HTTP_200_OK
        return {"ok": False, "espi_poll": poll_result, "agent_run": None}

    agent = AgentRun(
        workflow="stock-pre-session-brief",
        trigger=payload.trigger,
        status="queued",
        company_id=company.id if company else None,
        model_role="orchestrator",
        orchestrator_model=payload.orchestrator_model,
        inputs={
            "espi_poll": poll_result,
            "task": {
                "skill": "stock-pre-session-brief",
                "objective": (
                    "Triage newly ingested ESPI/EBI reports and prepare a "
                    "verified pre-session agenda for watched companies."
                ),
                "required_verification": "verifier_strict for material UI-visible items",
            },
        },
        outputs={},
    )
    db.add(agent)
    db.commit()
    return {"ok": True, "espi_poll": poll_result, "agent_run": agent}


@router.get("/companies/{ticker}/analysis-runs", response_model=list[AnalysisRunOut])
def list_company_analysis_runs(
    ticker: str,
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    verification_status: str | None = None,
    limit: int = 50,
) -> list[AnalysisRun]:
    company = _get_company_or_404(db, ticker)
    stmt = (
        select(AnalysisRun)
        .where(AnalysisRun.company_id == company.id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    )
    if status_filter:
        stmt = stmt.where(AnalysisRun.status == status_filter)
    if verification_status:
        stmt = stmt.where(AnalysisRun.verification_status == verification_status)
    return list(db.scalars(stmt.limit(_bounded_limit(limit))))


@router.get("/companies/{ticker}/event-reports", response_model=list[EventReportOut])
def list_company_event_reports(
    ticker: str,
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[EventReport]:
    company = _get_company_or_404(db, ticker)
    stmt = (
        select(EventReport)
        .where(EventReport.company_id == company.id)
        .order_by(EventReport.published_at.desc(), EventReport.id.desc())
        .limit(_bounded_limit(limit))
    )
    return list(db.scalars(stmt))
