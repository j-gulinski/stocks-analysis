"""Agent-output evaluation API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AgentEvaluationRunCreateIn,
    AgentEvaluationRunDetailOut,
    AgentEvaluationRunOut,
)
from app.db.base import get_db
from app.db.models import AgentEvaluationObservation, AgentEvaluationRun
from app.services import agent_evaluation

router = APIRouter(prefix="/agent-evaluation-runs", tags=["agent-evaluations"])


def _bounded_limit(limit: int) -> int:
    return min(max(limit, 1), 100)


def _detail_payload(db: Session, run: AgentEvaluationRun) -> dict:
    observations = list(
        db.scalars(
            select(AgentEvaluationObservation)
            .where(AgentEvaluationObservation.evaluation_run_id == run.id)
            .order_by(
                AgentEvaluationObservation.as_of_date.asc(),
                AgentEvaluationObservation.id.asc(),
            )
        )
    )
    return {
        "id": run.id,
        "agent_run_id": run.agent_run_id,
        "strategy": run.strategy,
        "from_date": run.from_date,
        "to_date": run.to_date,
        "status": run.status,
        "model_role": run.model_role,
        "model": run.model,
        "parameters": run.parameters,
        "summary": run.summary,
        "verification_status": run.verification_status,
        "created_at": run.created_at,
        "observations": observations,
    }


@router.get("", response_model=list[AgentEvaluationRunOut])
def list_agent_evaluation_runs(
    db: Session = Depends(get_db),
    strategy: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 20,
) -> list[AgentEvaluationRun]:
    stmt = select(AgentEvaluationRun).order_by(
        AgentEvaluationRun.created_at.desc(),
        AgentEvaluationRun.id.desc(),
    )
    if strategy:
        stmt = stmt.where(AgentEvaluationRun.strategy == strategy)
    if status_filter:
        stmt = stmt.where(AgentEvaluationRun.status == status_filter)
    return list(db.scalars(stmt.limit(_bounded_limit(limit))))


@router.post(
    "",
    response_model=AgentEvaluationRunDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_evaluation_run(
    payload: AgentEvaluationRunCreateIn,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = agent_evaluation.run_agent_evaluation(
            db,
            strategy=payload.strategy,
            from_date=payload.from_date,
            to_date=payload.to_date,
            ticker=payload.ticker,
            workflow=payload.workflow,
            outcome_windows=payload.outcome_windows,
        )
    except agent_evaluation.AgentEvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    run = db.get(AgentEvaluationRun, result["evaluation_run_id"])
    if run is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return _detail_payload(db, run)


@router.get("/{run_id}", response_model=AgentEvaluationRunDetailOut)
def get_agent_evaluation_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(AgentEvaluationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent evaluation run {run_id}.",
        )
    return _detail_payload(db, run)
