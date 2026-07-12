"""Explicit myfund sync and zero-write portfolio workspace reads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db
from app.db.models import (
    AgentRun,
    Company,
    InstrumentMapping,
    Portfolio,
    PortfolioPositionSnapshot,
    PortfolioReviewSnapshot,
    PortfolioSnapshot,
    PortfolioSync,
    PortfolioValuePoint,
    utcnow,
)
from app.api.schemas import (
    PortfolioReviewSaveIn,
    PortfolioReviewSnapshotOut,
    PortfolioReviewVerificationIn,
)
from app.scrapers import http as polite_http
from app.services.portfolio import (
    PARSER_VERSION,
    classify_mapping,
    normalize_myfund,
    portfolio_workspace,
    provider_gpw_ticker,
)
from app.services.portfolio_review_artifacts import (
    PortfolioReviewArtifactError,
    queue_portfolio_review,
    save_portfolio_review,
    verify_portfolio_review,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class MappingPatchIn(BaseModel):
    company_ticker: str | None = Field(default=None, max_length=12)
    ignored: bool = False


def _portfolio(db: Session, *, create: bool = False) -> Portfolio | None:
    settings = get_settings()
    ref = (settings.myfund_portfolio or "").strip()
    if not ref:
        return None
    row = db.scalar(
        select(Portfolio).where(
            Portfolio.provider == "myfund", Portfolio.provider_ref == ref
        )
    )
    if row is None and create:
        row = Portfolio(
            provider="myfund", provider_ref=ref, name=ref, base_currency="PLN"
        )
        db.add(row)
        db.flush()
    return row


def _latest_sync(
    db: Session, portfolio_id: int, *, failed: bool = False
) -> PortfolioSync | None:
    stmt = select(PortfolioSync).where(PortfolioSync.portfolio_id == portfolio_id)
    if failed:
        stmt = stmt.where(PortfolioSync.status == "failed")
    return db.scalar(
        stmt.order_by(PortfolioSync.requested_at.desc(), PortfolioSync.id.desc()).limit(
            1
        )
    )


def _sync_out(row: PortfolioSync | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "status": row.status,
        "provider_status_code": row.provider_status_code,
        "error": row.error,
        "requested_at": row.requested_at,
        "fetched_at": row.fetched_at,
        "snapshot_id": row.snapshot_id,
        "reused_snapshot": row.reused_snapshot,
        "parser_version": row.parser_version,
    }


def _workspace(db: Session, portfolio: Portfolio | None) -> dict[str, Any]:
    configured = bool(get_settings().myfund_api_key and get_settings().myfund_portfolio)
    base: dict[str, Any] = {
        "configured": configured,
        "provider": "myfund",
        "portfolio_label": (
            portfolio.name if portfolio else (get_settings().myfund_portfolio or None)
        ),
        "latest_sync": None,
        "last_sync_failure": None,
        "snapshot": None,
        "positions": [],
        "reconciliation": None,
        "concentration": None,
        "history": [],
        "history_quality": None,
        "liquidity": [],
        "scenario_sensitivity": None,
        "risk_context": None,
        "performance_methods": None,
        "coverage": {"mapped_company_value_pct": 0, "unmapped_positions": 0},
        "portfolio_review": {"latest": None, "history": [], "active_run": None},
    }
    if portfolio is None:
        return base
    base["latest_sync"] = _sync_out(_latest_sync(db, portfolio.id))
    base["last_sync_failure"] = _sync_out(_latest_sync(db, portfolio.id, failed=True))
    snapshot = db.scalar(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(PortfolioSnapshot.version.desc())
        .limit(1)
    )
    if snapshot is not None:
        base.update(portfolio_workspace(db, snapshot))
    reviews = list(
        db.scalars(
            select(PortfolioReviewSnapshot)
            .where(PortfolioReviewSnapshot.portfolio_id == portfolio.id)
            .order_by(PortfolioReviewSnapshot.version.desc())
            .limit(20)
        )
    )
    active = next(
        (
            row
            for row in db.scalars(
                select(AgentRun)
                .where(
                    AgentRun.workflow == "stock-portfolio-review",
                    AgentRun.status.in_(("queued", "running")),
                )
                .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            )
            if ((row.inputs or {}).get("portfolio_review") or {})
            .get("portfolio", {})
            .get("id")
            == portfolio.id
        ),
        None,
    )
    base["portfolio_review"] = {
        "latest": _review_out(reviews[0]) if reviews else None,
        "history": [_review_summary(row) for row in reviews],
        "active_run": _agent_summary(active),
    }
    return base


def _review_out(row: PortfolioReviewSnapshot) -> dict[str, Any]:
    return PortfolioReviewSnapshotOut.model_validate(row).model_dump(mode="json")


def _review_summary(row: PortfolioReviewSnapshot) -> dict[str, Any]:
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "draft_requested_model_role": row.draft_requested_model_role,
        "draft_requested_model": row.draft_requested_model,
        "draft_reasoning_effort": row.draft_reasoning_effort,
        "draft_actual_host_model": row.draft_actual_host_model,
        "draft_substitution_or_escalation": row.draft_substitution_or_escalation,
        "portfolio_snapshot_id": row.portfolio_snapshot_id,
        "as_of": row.as_of,
        "gaps": row.gaps,
        "created_at": row.created_at,
    }


def _agent_summary(row: AgentRun | None) -> dict[str, Any] | None:
    if row is None:
        return None
    frozen = (row.inputs or {}).get("portfolio_review") or {}
    return {
        "id": row.id,
        "status": row.status,
        "created_at": row.created_at,
        "snapshot_id": (frozen.get("snapshot") or {}).get("id"),
        "input_fingerprint": frozen.get("input_fingerprint"),
        "risk_context_fingerprint": frozen.get("risk_context_fingerprint"),
    }


def _artifact_http_error(exc: PortfolioReviewArtifactError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if exc.kind == "not-found"
        else (
            status.HTTP_409_CONFLICT
            if exc.kind == "conflict"
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
    )
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/workspace")
def get_portfolio_workspace(db: Session = Depends(get_db)) -> dict[str, Any]:
    return _workspace(db, _portfolio(db))


@router.post("/review-runs", status_code=status.HTTP_201_CREATED)
def queue_review(response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    portfolio = _portfolio(db)
    if portfolio is None:
        raise HTTPException(
            status_code=409, detail="A configured stored portfolio is required."
        )
    snapshot = db.scalar(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(PortfolioSnapshot.version.desc())
        .limit(1)
    )
    if snapshot is None:
        raise HTTPException(
            status_code=409, detail="Synchronise a portfolio snapshot first."
        )
    try:
        agent, created = queue_portfolio_review(db, portfolio, snapshot)
    except PortfolioReviewArtifactError as exc:
        raise _artifact_http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    frozen = (agent.inputs or {}).get("portfolio_review") or {}
    return {
        "agent_run_id": agent.id,
        "status": agent.status,
        "created": created,
        "portfolio_id": portfolio.id,
        "portfolio_snapshot_id": snapshot.id,
        "input_fingerprint": frozen.get("input_fingerprint"),
        "analytics_fingerprint": frozen.get("analytics_fingerprint"),
        "risk_context_fingerprint": frozen.get("risk_context_fingerprint"),
    }


@router.post("/review-verifications")
def create_review_verification(
    payload: PortfolioReviewVerificationIn, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        row = verify_portfolio_review(db, payload)
    except PortfolioReviewArtifactError as exc:
        raise _artifact_http_error(exc) from exc
    return {
        "id": row.id,
        "agent_run_id": row.agent_run_id,
        "requested_model_role": row.model_role,
        "requested_model": (row.checks or {}).get("requested_model"),
        "reasoning_effort": (row.checks or {}).get("reasoning_effort"),
        "actual_host_model": row.verifier_model,
        "substitution_or_escalation": (row.checks or {}).get(
            "substitution_or_escalation"
        ),
        "verdict": row.verdict,
        "checks": row.checks,
        "summary": row.summary,
        "created_at": row.created_at,
    }


@router.post(
    "/review-snapshots",
    response_model=PortfolioReviewSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
def create_review_snapshot(
    payload: PortfolioReviewSaveIn, db: Session = Depends(get_db)
) -> PortfolioReviewSnapshot:
    try:
        return save_portfolio_review(db, payload)
    except PortfolioReviewArtifactError as exc:
        raise _artifact_http_error(exc) from exc


@router.post("/sync/myfund")
def sync_myfund(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    if not settings.myfund_api_key or not settings.myfund_portfolio:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="myfund API key and portfolio name are required.",
        )
    portfolio = _portfolio(db, create=True)
    assert portfolio is not None
    sync = PortfolioSync(
        portfolio_id=portfolio.id,
        status="running",
        requested_at=utcnow(),
        parser_version=PARSER_VERSION,
        reused_snapshot=False,
    )
    db.add(sync)
    db.commit()
    db.refresh(sync)
    url = settings.myfund_base_url.rstrip("/") + "/API/v1/getPortfel.php"
    try:
        response = polite_http.fetch(
            url,
            params={
                "portfel": settings.myfund_portfolio,
                "apiKey": settings.myfund_api_key,
                "format": "json",
            },
        )
        payload = response.json()
        provider_status = payload.get("status") if isinstance(payload, dict) else None
        provider_code = (
            provider_status.get("code")
            if isinstance(provider_status, dict)
            else provider_status
        )
        normalized = normalize_myfund(payload)
    except Exception as exc:
        # Commit the attempt before raising; never expose provider text, URL or credentials.
        failed = db.get(PortfolioSync, sync.id)
        assert failed is not None
        failed.status = "failed"
        failed.fetched_at = utcnow()
        failed.provider_status_code = (
            str(locals().get("provider_code"))[:30]
            if locals().get("provider_code") is not None
            else None
        )
        failed.error = "Provider request or response validation failed."
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=failed.error
        ) from exc
    try:
        return _persist_normalized(db, portfolio.id, sync.id, normalized)
    except Exception as exc:
        db.rollback()
        failed = db.get(PortfolioSync, sync.id)
        assert failed is not None
        failed.status = "failed"
        failed.fetched_at = utcnow()
        failed.provider_status_code = "0"
        failed.error = "Validated portfolio data could not be saved."
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=failed.error
        ) from exc


def _persist_normalized(
    db: Session, portfolio_id: int, sync_id: int, normalized
) -> dict[str, Any]:
    fetched_at = utcnow()
    # Serialize fingerprint/version assignment without holding a lock during HTTP.
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
    )
    assert portfolio is not None
    latest = db.scalar(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(PortfolioSnapshot.version.desc())
        .limit(1)
    )
    if latest is not None and latest.input_fingerprint == normalized.fingerprint:
        sync = db.get(PortfolioSync, sync_id)
        assert sync is not None
        sync.status = "succeeded"
        sync.fetched_at = fetched_at
        sync.provider_status_code = "0"
        sync.payload_hash = normalized.fingerprint
        sync.snapshot_id = latest.id
        sync.reused_snapshot = True
        db.commit()
        result = _workspace(db, portfolio)
        result["sync"] = _sync_out(sync)
        return result
    snapshot = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        version=(latest.version + 1 if latest else 1),
        as_of=fetched_at,
        currency=normalized.summary["currency"],
        total_value=normalized.summary["total_value"],
        cost_basis=normalized.summary["cost_basis"],
        profit=normalized.summary["profit"],
        cash_value=None,
        benchmark_name=normalized.summary["benchmark_name"],
        input_fingerprint=normalized.fingerprint,
        gaps=list(normalized.gaps),
        created_at=fetched_at,
    )
    db.add(snapshot)
    db.flush()
    cash = 0.0
    cash_recognized = False
    for row in normalized.positions:
        mapping = db.scalar(
            select(InstrumentMapping).where(
                InstrumentMapping.provider == "myfund",
                InstrumentMapping.provider_key == row["provider_key"],
            )
        )
        if mapping is None:
            kind, mapping_status, company, reason = classify_mapping(db, row)
            mapping = InstrumentMapping(
                provider="myfund",
                provider_key=row["provider_key"],
                provider_ticker=row["ticker"],
                provider_name=row["name"],
                provider_type=row["asset_type"],
                currency=row["currency"],
                mapping_kind=kind,
                mapping_status=mapping_status,
                company_id=company.id if company else None,
                reason=reason,
            )
            db.add(mapping)
            db.flush()
        elif mapping.mapping_status not in {"confirmed", "ignored"}:
            kind, mapping_status, company, reason = classify_mapping(db, row)
            mapping.provider_ticker = row["ticker"]
            mapping.provider_name = row["name"]
            mapping.provider_type = row["asset_type"]
            mapping.currency = row["currency"]
            mapping.mapping_kind = kind
            mapping.mapping_status = mapping_status
            mapping.company_id = company.id if company else None
            mapping.reason = reason
        if mapping.mapping_kind == "cash":
            cash_recognized = True
            cash += row["value"]
        db.add(
            PortfolioPositionSnapshot(
                snapshot_id=snapshot.id,
                mapping_id=mapping.id,
                mapping_kind=mapping.mapping_kind,
                mapping_status=mapping.mapping_status,
                company_id=mapping.company_id,
                provider_row_key=row["row_key"],
                ticker=row["ticker"],
                name=row["name"],
                asset_type=row["asset_type"],
                sector=row["sector"],
                currency=row["currency"],
                quote_date=row["quote_date"],
                quote=row["quote"],
                quantity=row["quantity"],
                value=row["value"],
                cost_basis=row["cost_basis"],
                profit=row["profit"],
                allocation_pct=row["allocation_pct"],
            )
        )
    snapshot.cash_value = cash if cash_recognized else None
    for point in normalized.history:
        db.add(
            PortfolioValuePoint(
                snapshot_id=snapshot.id,
                date=date_from_iso(point["date"]),
                value=point["value"],
                contributed=point["contributed"],
                profit=point["profit"],
                provider_return_pct=point["provider_return_pct"],
                benchmark_return_pct=point["benchmark_return_pct"],
                daily_change=point["daily_change"],
            )
        )
    sync = db.get(PortfolioSync, sync_id)
    assert sync is not None
    sync.status = "succeeded"
    sync.fetched_at = fetched_at
    sync.provider_status_code = "0"
    sync.payload_hash = normalized.fingerprint
    sync.snapshot_id = snapshot.id
    portfolio.base_currency = snapshot.currency
    db.commit()
    db.refresh(snapshot)
    result = _workspace(db, portfolio)
    result["sync"] = _sync_out(sync)
    return result


def date_from_iso(value: str):
    return datetime.fromisoformat(value).date()


@router.patch("/mappings/{mapping_id}")
def patch_mapping(
    mapping_id: int, payload: MappingPatchIn, db: Session = Depends(get_db)
) -> dict[str, Any]:
    mapping = db.get(InstrumentMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Instrument mapping not found.")
    if mapping.mapping_kind == "cash" or mapping.mapping_status == "exact":
        raise HTTPException(
            status_code=409, detail="Exact provider identity cannot be reinterpreted."
        )
    if payload.ignored:
        mapping.mapping_kind = "ignored"
        mapping.mapping_status = "ignored"
        mapping.company_id = None
        mapping.reason = "Ignored by user."
        mapping.confirmed_at = utcnow()
    else:
        ticker = (payload.company_ticker or "").strip().upper()
        provider_ticker = provider_gpw_ticker(
            provider_ticker=mapping.provider_ticker,
            provider_name=mapping.provider_name,
            provider_type=mapping.provider_type,
            currency=mapping.currency,
        )
        if not ticker or provider_ticker != ticker:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Confirmed ticker must exactly match one terminal GPW code "
                    "from a PLN Akcje GPW provider identity."
                ),
            )
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if company is None:
            display_name = mapping.provider_name.strip()
            suffix = f" ({ticker})"
            if display_name.upper().endswith(suffix):
                display_name = display_name[: -len(suffix)].strip()
            company = Company(
                ticker=ticker,
                name=display_name or ticker,
                market="GPW",
            )
            db.add(company)
            db.flush()
        mapping.mapping_kind = "company"
        mapping.mapping_status = "confirmed"
        mapping.company_id = company.id
        mapping.reason = "Confirmed by user."
        mapping.confirmed_at = utcnow()
    db.commit()
    db.refresh(mapping)
    return {
        "id": mapping.id,
        "provider_key": mapping.provider_key,
        "mapping_kind": mapping.mapping_kind,
        "mapping_status": mapping.mapping_status,
        "company_id": mapping.company_id,
        "reason": mapping.reason,
    }
