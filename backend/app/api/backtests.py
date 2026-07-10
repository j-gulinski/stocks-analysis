"""Deterministic backtest run API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BacktestRunCreateIn,
    BacktestRunDetailOut,
    BacktestRunOut,
)
from app.db.base import get_db
from app.db.models import BacktestObservation, BacktestRun
from app.services import backtest

router = APIRouter(prefix="/backtest-runs", tags=["backtests"])


def _bounded_limit(limit: int) -> int:
    return min(max(limit, 1), 100)


def _detail_payload(db: Session, run: BacktestRun) -> dict:
    observations = list(
        db.scalars(
            select(BacktestObservation)
            .where(BacktestObservation.backtest_run_id == run.id)
            .order_by(BacktestObservation.as_of_date.asc(), BacktestObservation.id.asc())
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


@router.get("", response_model=list[BacktestRunOut])
def list_backtest_runs(
    db: Session = Depends(get_db),
    strategy: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 20,
) -> list[BacktestRun]:
    stmt = select(BacktestRun).order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
    if strategy:
        stmt = stmt.where(BacktestRun.strategy == strategy)
    if status_filter:
        stmt = stmt.where(BacktestRun.status == status_filter)
    return list(db.scalars(stmt.limit(_bounded_limit(limit))))


@router.post(
    "",
    response_model=BacktestRunDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_backtest_run(
    payload: BacktestRunCreateIn,
    db: Session = Depends(get_db),
) -> dict:
    tickers = [payload.ticker.upper()] if payload.ticker else None
    try:
        result = backtest.run_strategy_backtest(
            db,
            strategy=payload.strategy,
            from_date=payload.from_date,
            to_date=payload.to_date,
            tickers=tickers,
            outcome_windows=payload.outcome_windows,
            financial_availability_policy=payload.financial_availability_policy,
            report_lag_days=payload.report_lag_days,
        )
    except backtest.BacktestInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    run = db.get(BacktestRun, result["backtest_run_id"])
    if run is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return _detail_payload(db, run)


@router.get("/{run_id}", response_model=BacktestRunDetailOut)
def get_backtest_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown backtest run {run_id}.",
        )
    return _detail_payload(db, run)
