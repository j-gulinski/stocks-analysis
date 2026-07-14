"""Tool functions behind the Stock Workbench MCP server.

These functions are intentionally plain Python so they can be tested without a
running MCP client. The stdio adapter in `stock_workbench_server.py` only
translates JSON-RPC messages into calls here.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from pydantic import ValidationError

from app.api.schemas import (
    DossierOut,
    ResearchSnapshotOut,
    ResearchSnapshotSaveIn,
    ResearchSnapshotVerificationIn,
    ValuationSnapshotOut,
    ValuationSnapshotSaveIn,
    ValuationSnapshotVerificationIn,
)
from app.db.base import SessionLocal
from app.db.models import (
    AgentRun,
    Company,
    EventReport,
    Price,
    ReportValue,
)
from app.services import (
    agent_queue,
    dossier as dossier_service,
    codex_context,
    model_policy,
)
from app.services.archetype_packs import get_pack, pack_payload
from app.services.research_artifacts import (
    ResearchArtifactError,
    save_research_snapshot as persist_research_snapshot,
    verify_research_snapshot as persist_research_verification,
)
from app.services.valuation_artifacts import (
    ValuationArtifactError,
    save_valuation_snapshot as persist_valuation_snapshot,
    verify_valuation_snapshot as persist_valuation_verification,
)


class ToolInputError(ValueError):
    """User-correctable MCP tool input problem."""


def _bounded_limit(value: int | None, *, default: int = 50, maximum: int = 200) -> int:
    if value is None:
        return default
    return min(max(int(value), 1), maximum)


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"Required field '{key}' must be a non-empty string.")
    return value.strip()


def _optional_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ToolInputError(f"Optional field '{key}' must be an object.")
    return value


def _get_company(db, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise ToolInputError(f"Unknown company '{ticker.upper()}'.")
    return company


def _agent_row(agent: AgentRun) -> dict[str, Any]:
    return {
        "id": agent.id,
        "workflow": agent.workflow,
        "trigger": agent.trigger,
        "status": agent.status,
        "company_id": agent.company_id,
        "model_role": agent.model_role,
        "model": agent.model,
        "orchestrator_model": agent.orchestrator_model,
        "inputs": agent.inputs,
        "outputs": agent.outputs,
        "error": agent.error,
        "started_at": agent.started_at,
        "finished_at": agent.finished_at,
        "lease_owner": agent.lease_owner,
        "heartbeat_at": agent.heartbeat_at,
        "lease_expires_at": agent.lease_expires_at,
        "available_at": agent.available_at,
        "attempt_count": agent.attempt_count,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def get_model_policy(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow = _require_text(arguments, "workflow")
    return {"ok": True, "policy": model_policy.get_model_policy(workflow)}


def get_archetype_pack(arguments: dict[str, Any]) -> dict[str, Any]:
    archetype = _require_text(arguments, "archetype")
    pack = get_pack(archetype)
    if pack is None:
        raise ToolInputError(f"Unknown archetype '{archetype}'.")
    return {"ok": True, "archetype_pack": pack_payload(pack)}


def get_company_dossier(arguments: dict[str, Any]) -> dict[str, Any]:
    ticker = _require_text(arguments, "ticker").upper()
    db = SessionLocal()
    try:
        company = _get_company(db, ticker)
        dossier = dossier_service.build_dossier(db, company)
        ui_contract = DossierOut.model_validate(dossier).model_dump(mode="json")
        return {
            "ok": True,
            "ticker": ticker,
            "dossier": ui_contract,
            "codex_context": codex_context.source_data_context(
                "company-dossier", "issuer-data", "forum-opinions"
            ),
        }
    finally:
        db.close()


def list_queued_agent_runs(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    status = str(arguments.get("status") or "queued")
    workflow = arguments.get("workflow")
    limit = _bounded_limit(arguments.get("limit"))
    db = SessionLocal()
    try:
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.workflow.in_(model_policy.CANONICAL_WORKFLOWS),
                AgentRun.status == status,
            )
            .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
            .limit(limit)
        )
        if workflow:
            if str(workflow) not in model_policy.CANONICAL_WORKFLOWS:
                raise ToolInputError(f"Unsupported Codex workflow '{workflow}'.")
            stmt = stmt.where(AgentRun.workflow == str(workflow))
        return {
            "ok": True,
            "status": status,
            "agent_runs": [_agent_row(row) for row in db.scalars(stmt)],
        }
    finally:
        db.close()


def claim_agent_run(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_run_id = arguments.get("agent_run_id")
    if not isinstance(agent_run_id, int):
        raise ToolInputError("Required field 'agent_run_id' must be an integer.")
    db = SessionLocal()
    try:
        try:
            agent = agent_queue.claim_agent_run(
                db,
                agent_run_id=agent_run_id,
                worker_id=str(arguments["worker_id"]) if arguments.get("worker_id") else None,
                model_role=str(arguments["model_role"]) if arguments.get("model_role") else None,
                model=str(arguments["model"]) if arguments.get("model") else None,
                orchestrator_model=(
                    str(arguments["orchestrator_model"])
                    if arguments.get("orchestrator_model")
                    else None
                ),
                lease_minutes=int(arguments.get("lease_minutes") or 45),
            )
        except agent_queue.AgentQueueError as exc:
            raise ToolInputError(str(exc)) from exc
        return {"ok": True, "agent_run": _agent_row(agent)}
    finally:
        db.close()


def save_research_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    """Thin MCP adapter over the canonical research artifact save gate."""
    case_id = arguments.get("case_id")
    payload = arguments.get("payload")
    if not isinstance(case_id, int):
        raise ToolInputError("Required field 'case_id' must be an integer.")
    if not isinstance(payload, dict):
        raise ToolInputError("Required field 'payload' must be an object.")
    try:
        parsed = ResearchSnapshotSaveIn.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError(str(exc)) from exc
    db = SessionLocal()
    try:
        try:
            snapshot = persist_research_snapshot(db, case_id=case_id, payload=parsed)
        except ResearchArtifactError as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "ok": True,
            "research_snapshot": ResearchSnapshotOut.model_validate(snapshot).model_dump(
                mode="json"
            ),
        }
    finally:
        db.close()


def verify_research_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    """Record an independent verdict bound to the exact research draft."""
    case_id = arguments.get("case_id")
    payload = arguments.get("payload")
    if not isinstance(case_id, int):
        raise ToolInputError("Required field 'case_id' must be an integer.")
    if not isinstance(payload, dict):
        raise ToolInputError("Required field 'payload' must be an object.")
    try:
        parsed = ResearchSnapshotVerificationIn.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError(str(exc)) from exc
    db = SessionLocal()
    try:
        try:
            verification = persist_research_verification(
                db, case_id=case_id, payload=parsed
            )
        except ResearchArtifactError as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "ok": True,
            "verification_run": {
                "id": verification.id,
                "agent_run_id": verification.agent_run_id,
                "model_role": verification.model_role,
                "verifier_model": verification.verifier_model,
                "verdict": verification.verdict,
                "checks": verification.checks,
                "summary": verification.summary,
                "created_at": verification.created_at,
            },
        }
    finally:
        db.close()


def save_valuation_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    case_id = arguments.get("case_id")
    payload = arguments.get("payload")
    if not isinstance(case_id, int) or not isinstance(payload, dict):
        raise ToolInputError("case_id must be an integer and payload an object.")
    try:
        parsed = ValuationSnapshotSaveIn.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError(str(exc)) from exc
    db = SessionLocal()
    try:
        try:
            row = persist_valuation_snapshot(db, case_id=case_id, payload=parsed)
        except ValuationArtifactError as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "ok": True,
            "valuation_snapshot": ValuationSnapshotOut.model_validate(row).model_dump(mode="json"),
        }
    finally:
        db.close()


def verify_valuation_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    case_id = arguments.get("case_id")
    payload = arguments.get("payload")
    if not isinstance(case_id, int) or not isinstance(payload, dict):
        raise ToolInputError("case_id must be an integer and payload an object.")
    try:
        parsed = ValuationSnapshotVerificationIn.model_validate(payload)
    except ValidationError as exc:
        raise ToolInputError(str(exc)) from exc
    db = SessionLocal()
    try:
        try:
            row = persist_valuation_verification(db, case_id=case_id, payload=parsed)
        except ValuationArtifactError as exc:
            raise ToolInputError(str(exc)) from exc
        return {"ok": True, "verification_run": {
            "id": row.id, "agent_run_id": row.agent_run_id,
            "model_role": row.model_role, "verifier_model": row.verifier_model,
            "verdict": row.verdict, "checks": row.checks,
            "summary": row.summary, "created_at": row.created_at,
        }}
    finally:
        db.close()


def get_recent_source_deltas(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    ticker = arguments.get("ticker")
    since = _parse_iso_datetime(arguments.get("since"))
    limit = _bounded_limit(arguments.get("limit"), default=50)
    db = SessionLocal()
    try:
        stmt = (
            select(EventReport, Company)
            .join(Company, EventReport.company_id == Company.id)
            .order_by(EventReport.published_at.desc(), EventReport.id.desc())
            .limit(limit)
        )
        if ticker:
            stmt = stmt.where(Company.ticker == str(ticker).upper())
        if since is not None:
            stmt = stmt.where(EventReport.published_at >= since)
        rows = []
        for event, company in db.execute(stmt):
            rows.append(
                {
                    "ticker": company.ticker,
                    "event_report_id": event.id,
                    "source": event.source,
                    "external_id": event.external_id,
                    "raw_url": event.raw_url,
                    "published_at": event.published_at,
                    "title": event.title,
                    "parsed": event.parsed,
                    "materiality": event.materiality,
                }
            )
        return {
            "ok": True,
            "events": rows,
            "codex_context": codex_context.source_data_context(
                "espi", "ebi", "stored-event-report"
            ),
        }
    finally:
        db.close()


def assess_data_readiness(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Describe stored-company research inputs; this is not an opportunity rank."""
    arguments = arguments or {}
    limit = _bounded_limit(arguments.get("limit"), default=20)
    tickers = arguments.get("ticker")
    if isinstance(tickers, str):
        ticker_filter = [tickers.upper()]
    elif isinstance(tickers, list):
        ticker_filter = [str(ticker).upper() for ticker in tickers]
    elif tickers is None:
        ticker_filter = None
    else:
        raise ToolInputError("Optional field 'ticker' must be a string or list.")

    db = SessionLocal()
    try:
        stmt = select(Company).order_by(Company.ticker)
        if ticker_filter:
            stmt = stmt.where(Company.ticker.in_(ticker_filter))
        companies = list(db.scalars(stmt))
        rows = sorted(
            (_score_candidate(db, company) for company in companies),
            key=lambda row: (row["score"], row["ticker"]),
            reverse=True,
        )
        return {
            "ok": True,
            "workflow": "stored-company-data-readiness",
            "source": "stored-companies",
            "data_readiness": rows[:limit],
        }
    finally:
        db.close()


def _score_candidate(db, company: Company) -> dict[str, Any]:
    latest_price = db.scalar(
        select(Price.close)
        .where(Price.company_id == company.id)
        .order_by(Price.date.desc())
        .limit(1)
    )
    income_rows = db.scalar(
        select(ReportValue.id)
        .where(ReportValue.company_id == company.id, ReportValue.statement == "income")
        .limit(1)
    )
    score = 0
    reasons: list[str] = []
    missing: list[str] = []
    if company.market_cap is not None:
        score += 20
        reasons.append("reported market cap available")
    else:
        missing.append("market_cap")
    if latest_price is not None:
        score += 20
        reasons.append("latest price available")
    else:
        missing.append("latest_price")
    if income_rows is not None:
        score += 40
        reasons.append("income statement data available")
    else:
        missing.append("income_statement")
    if company.sector:
        score += 10
        reasons.append("sector known")
    else:
        missing.append("sector")
    if company.shares_outstanding:
        score += 10
        reasons.append("share count known")
    else:
        missing.append("shares_outstanding")
    return {
        "ticker": company.ticker,
        "name": company.name,
        "score": score,
        "reasons": reasons,
        "missing_data": missing,
        "status": "needs-refresh" if missing else "ready-for-codex-review",
    }


def _parse_iso_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ToolInputError("Date fields must be ISO date strings.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ToolInputError(f"Invalid ISO date: {value}") from exc


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ToolInputError("'since' must be an ISO datetime string.")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ToolInputError(f"Invalid ISO datetime: {value}") from exc
