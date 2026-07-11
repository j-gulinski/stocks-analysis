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
    AnalysisRun,
    Company,
    EventReport,
    Price,
    ReportValue,
    VerificationRun,
    WatchlistItem,
    utcnow,
)
from app.scrapers import espi
from app.services import (
    agent_queue,
    agent_evaluation,
    analysis_contract,
    analysis_scoring,
    backtest,
    dossier as dossier_service,
    codex_context,
    model_policy,
)
from app.services.model_policy import default_model_for_workflow
from app.services.agent_queue import clear_agent_lease
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
from app.services.valuation_method_packs import list_method_packs


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


def _analysis_status_from_verification(value: str) -> str:
    lowered = value.lower()
    if lowered == "pass":
        return "verified"
    if lowered == "fail":
        return "rejected"
    return "draft"


def _agent_status_from_verification(value: str) -> str:
    lowered = value.lower()
    if lowered == "pass":
        return "completed"
    if lowered == "fail":
        return "rejected"
    if lowered == "needs-human":
        return "needs-human"
    return "completed"


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


def get_watchlist(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(WatchlistItem, Company)
            .join(Company, WatchlistItem.company_id == Company.id)
            .order_by(WatchlistItem.added_at)
        ).all()
        return {
            "ok": True,
            "watchlist": [
                {
                    "ticker": company.ticker,
                    "name": company.name,
                    "note": item.note,
                    "added_at": item.added_at,
                }
                for item, company in rows
            ],
        }
    finally:
        db.close()


def get_model_policy(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow = _require_text(arguments, "workflow")
    return {"ok": True, "policy": model_policy.get_model_policy(workflow)}


def get_archetype_pack(arguments: dict[str, Any]) -> dict[str, Any]:
    archetype = _require_text(arguments, "archetype")
    pack = get_pack(archetype)
    if pack is None:
        raise ToolInputError(f"Unknown archetype '{archetype}'.")
    return {"ok": True, "archetype_pack": pack_payload(pack)}


def get_valuation_method_packs(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "method_packs": list_method_packs()}


def get_company_dossier(arguments: dict[str, Any]) -> dict[str, Any]:
    ticker = _require_text(arguments, "ticker").upper()
    use_ai_refiners = bool(arguments.get("use_ai_refiners", False))
    db = SessionLocal()
    try:
        company = _get_company(db, ticker)
        dossier = dossier_service.build_dossier(
            db, company, use_ai_refiners=use_ai_refiners
        )
        ui_contract = DossierOut.model_validate(dossier).model_dump(mode="json")
        return {
            "ok": True,
            "ticker": ticker,
            "dossier": ui_contract,
            "codex_score_base": analysis_scoring.build_codex_score_base(ui_contract),
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
            .where(AgentRun.status == status)
            .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
            .limit(limit)
        )
        if workflow:
            stmt = stmt.where(AgentRun.workflow == str(workflow))
        return {
            "ok": True,
            "status": status,
            "agent_runs": [_agent_row(row) for row in db.scalars(stmt)],
        }
    finally:
        db.close()


def queue_agent_run(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow = _require_text(arguments, "workflow")
    ticker = arguments.get("ticker")
    inputs = _optional_dict(arguments, "inputs")
    db = SessionLocal()
    try:
        company_id = None
        if ticker:
            company_id = _get_company(db, str(ticker)).id
            inputs = {**inputs, "ticker": str(ticker).upper()}
        selected_model = (
            arguments.get("model")
            or arguments.get("orchestrator_model")
            or default_model_for_workflow(workflow)
        )
        agent = AgentRun(
            workflow=workflow,
            trigger=str(arguments.get("trigger") or "ui-request"),
            status="queued",
            company_id=company_id,
            model_role=arguments.get("model_role"),
            model=selected_model,
            orchestrator_model=arguments.get("orchestrator_model") or selected_model,
            inputs=inputs,
            outputs={},
        )
        db.add(agent)
        db.commit()
        return {"ok": True, "agent_run": _agent_row(agent)}
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


def save_analysis_run(arguments: dict[str, Any]) -> dict[str, Any]:
    ticker = _require_text(arguments, "ticker").upper()
    workflow = _require_text(arguments, "workflow")
    model_role = _require_text(arguments, "model_role")
    model = _require_text(arguments, "model")
    verification_status = _require_text(arguments, "verification_status")
    output = _optional_dict(arguments, "output")
    if not output:
        raise ToolInputError("Required field 'output' must be a non-empty object.")
    contract_errors = analysis_contract.verified_analysis_contract_errors(
        workflow=workflow,
        verification_status=verification_status,
        output=output,
        input_snapshot=_optional_dict(arguments, "input_snapshot"),
        verification=_optional_dict(arguments, "verification"),
    )
    contract_errors += analysis_contract.verified_scenario_simulation_contract_errors(
        workflow=workflow,
        verification_status=verification_status,
        input_snapshot=_optional_dict(arguments, "input_snapshot"),
        output=output,
        verification=_optional_dict(arguments, "verification"),
    )
    if contract_errors:
        raise ToolInputError(" ".join(contract_errors))
    input_snapshot = _optional_dict(arguments, "input_snapshot")
    verification = _optional_dict(arguments, "verification")
    source = str(arguments.get("source") or "codex_mcp")
    status = arguments.get("status") or _analysis_status_from_verification(
        verification_status
    )

    db = SessionLocal()
    try:
        company = _get_company(db, ticker)
        agent_run_id = arguments.get("agent_run_id")
        if agent_run_id is not None and not isinstance(agent_run_id, int):
            raise ToolInputError("Optional field 'agent_run_id' must be an integer.")
        if agent_run_id is None:
            agent = AgentRun(
                workflow=workflow,
                trigger=str(arguments.get("trigger") or "manual"),
                status="completed",
                company_id=company.id,
                model_role=model_role,
                model=model,
                inputs=input_snapshot,
                outputs=output,
                finished_at=utcnow(),
            )
            db.add(agent)
            db.flush()
            agent_run_id = agent.id
        alignment_score = arguments.get("alignment_score")
        if alignment_score is None and isinstance(output.get("alignment_score"), int):
            alignment_score = output["alignment_score"]

        record = AnalysisRun(
            company_id=company.id,
            agent_run_id=agent_run_id,
            source=source,
            workflow=workflow,
            model_role=model_role,
            model=model,
            status=str(status),
            verification_status=verification_status,
            input_snapshot=input_snapshot,
            output=output,
            output_contract_version=analysis_contract.output_contract_version(output),
            verification=verification,
            alignment_score=alignment_score,
            created_by=str(arguments.get("created_by") or "codex_mcp"),
        )
        db.add(record)
        db.flush()
        if (
            analysis_contract.output_contract_version(output)
            == analysis_contract.SCORED_SCENARIO_OUTPUT_CONTRACT_VERSION
            and verification_status.lower() == "pass"
        ):
            # A direct strict save still needs an auditable verifier row. Draft
            # saves use mark_verification_result later; both paths preserve the
            # same independent-verifier evidence instead of a bare status flag.
            db.add(
                VerificationRun(
                    agent_run_id=agent_run_id,
                    analysis_run_id=record.id,
                    model_role=verification["model_role"],
                    verifier_model=verification["verifier_model"],
                    verdict=verification["verdict"],
                    checks=verification["checks"],
                    summary=verification.get("summary"),
                )
            )
        agent = db.get(AgentRun, agent_run_id)
        if agent is not None:
            agent.status = _agent_status_from_verification(verification_status)
            agent.company_id = agent.company_id or company.id
            agent.model_role = agent.model_role or model_role
            agent.model = agent.model or model
            agent.outputs = {
                **(agent.outputs or {}),
                "analysis_run_id": record.id,
                "verification_status": verification_status,
                "output": output,
                "verification": verification,
            }
            agent.finished_at = utcnow()
            clear_agent_lease(agent)
        db.commit()
        return {
            "ok": True,
            "ticker": company.ticker,
            "agent_run_id": agent_run_id,
            "analysis_run_id": record.id,
            "status": record.status,
            "verification_status": record.verification_status,
        }
    finally:
        db.close()


def complete_agent_run(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_run_id = arguments.get("agent_run_id")
    if not isinstance(agent_run_id, int):
        raise ToolInputError("Required field 'agent_run_id' must be an integer.")
    verification_status = _require_text(arguments, "verification_status")
    output = _optional_dict(arguments, "output")
    if not output:
        raise ToolInputError("Required field 'output' must be a non-empty object.")
    verification = _optional_dict(arguments, "verification")

    db = SessionLocal()
    try:
        agent = db.get(AgentRun, agent_run_id)
        if agent is None:
            raise ToolInputError(f"Unknown agent_run_id {agent_run_id}.")
        if arguments.get("model_role"):
            agent.model_role = str(arguments["model_role"])
        if arguments.get("model"):
            agent.model = str(arguments["model"])
        if arguments.get("orchestrator_model"):
            agent.orchestrator_model = str(arguments["orchestrator_model"])
        status = arguments.get("status") or _agent_status_from_verification(
            verification_status
        )
        agent.status = str(status)
        agent.outputs = {
            **(agent.outputs or {}),
            "output": output,
            "verification_status": verification_status,
            "verification": verification,
        }
        agent.error = arguments.get("error")
        agent.finished_at = utcnow()
        clear_agent_lease(agent)
        db.commit()
        return {
            "ok": True,
            "agent_run": _agent_row(agent),
            "verification_status": verification_status,
        }
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


def mark_verification_result(arguments: dict[str, Any]) -> dict[str, Any]:
    verdict = _require_text(arguments, "verdict")
    verifier_model = _require_text(arguments, "verifier_model")
    checks = _optional_dict(arguments, "checks")
    model_role = str(arguments.get("model_role") or "verifier_strict")
    agent_run_id = arguments.get("agent_run_id")
    analysis_run_id = arguments.get("analysis_run_id")
    if agent_run_id is None and analysis_run_id is None:
        raise ToolInputError("Provide 'agent_run_id' or 'analysis_run_id'.")
    db = SessionLocal()
    try:
        verification = VerificationRun(
            agent_run_id=agent_run_id,
            analysis_run_id=analysis_run_id,
            model_role=model_role,
            verifier_model=verifier_model,
            verdict=verdict,
            checks=checks,
            summary=arguments.get("summary"),
        )
        db.add(verification)
        if isinstance(analysis_run_id, int):
            analysis = db.get(AnalysisRun, analysis_run_id)
            if analysis is not None:
                contract_errors = analysis_contract.verified_scenario_simulation_contract_errors(
                    workflow=analysis.workflow,
                    verification_status=verdict,
                    input_snapshot=analysis.input_snapshot or {},
                    output=analysis.output or {},
                    verification={
                        "model_role": model_role,
                        "verifier_model": verifier_model,
                        "verdict": verdict,
                        "checks": checks,
                    },
                )
                contract_errors += analysis_contract.verified_analysis_contract_errors(
                    workflow=analysis.workflow,
                    verification_status=verdict,
                    output=analysis.output or {},
                    input_snapshot=analysis.input_snapshot or {},
                    verification={
                        "model_role": model_role,
                        "verifier_model": verifier_model,
                        "verdict": verdict,
                        "checks": checks,
                    },
                )
                if contract_errors:
                    raise ToolInputError(" ".join(contract_errors))
                analysis.verification_status = verdict
                analysis.verification = {
                    "model_role": model_role,
                    "verifier_model": verifier_model,
                    "verdict": verdict,
                    "checks": checks,
                }
                analysis.status = _analysis_status_from_verification(verdict)
        if isinstance(agent_run_id, int):
            agent = db.get(AgentRun, agent_run_id)
            if agent is not None and verdict in {"pass", "fail", "needs-human"}:
                agent.outputs = {**(agent.outputs or {}), "verification": checks}
                agent.status = _agent_status_from_verification(verdict)
                agent.finished_at = utcnow()
                clear_agent_lease(agent)
        db.commit()
        return {
            "ok": True,
            "verification_run_id": verification.id,
            "verdict": verification.verdict,
        }
    finally:
        db.close()


def poll_espi_watchlist(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    ticker = arguments.get("ticker")
    db = SessionLocal()
    try:
        return espi.poll_watchlist_reports(
            db,
            ticker=str(ticker) if ticker else None,
            fetch_details=bool(arguments.get("fetch_details", True)),
        )
    finally:
        db.close()


def prepare_pre_session_brief(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    ticker = arguments.get("ticker")
    db = SessionLocal()
    try:
        poll_result = espi.poll_watchlist_reports(
            db,
            ticker=str(ticker) if ticker else None,
            fetch_details=bool(arguments.get("fetch_details", True)),
        )
        if arguments.get("queue", True) is False:
            return {
                "ok": bool(poll_result.get("ok") and poll_result.get("complete")),
                "espi_poll": poll_result,
                "agent_run": None,
            }
        if not poll_result.get("complete"):
            return {
                "ok": False,
                "espi_poll": poll_result,
                "agent_run": None,
            }

        inputs = {
            "espi_poll": poll_result,
            "task": {
                "skill": "stock-pre-session-brief",
                "objective": (
                    "Triage newly ingested ESPI/EBI reports and prepare a "
                    "verified pre-session agenda for watched companies."
                ),
                "required_verification": "verifier_strict for material UI-visible items",
            },
        }
        company_id = None
        if ticker:
            company_id = _get_company(db, str(ticker)).id
        agent = AgentRun(
            workflow="stock-pre-session-brief",
            trigger=str(arguments.get("trigger") or "scheduled"),
            status="queued",
            company_id=company_id,
            model_role="orchestrator",
            orchestrator_model=arguments.get("orchestrator_model"),
            inputs=inputs,
            outputs={},
        )
        db.add(agent)
        db.commit()
        return {"ok": True, "espi_poll": poll_result, "agent_run": _agent_row(agent)}
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
        else:
            stmt = stmt.join(WatchlistItem, WatchlistItem.company_id == Company.id)
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


def rank_candidates(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
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
        companies = list(db.scalars(stmt.limit(limit)))
        rows = sorted(
            (_score_candidate(db, company) for company in companies),
            key=lambda row: (row["score"], row["ticker"]),
            reverse=True,
        )
        return {
            "ok": True,
            "workflow": "stock-candidate-scout",
            "source": "stored-companies",
            "candidates": rows,
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


def run_backtest(arguments: dict[str, Any]) -> dict[str, Any]:
    strategy = _require_text(arguments, "strategy")
    from_date = _parse_iso_date(arguments.get("from_date"))
    to_date = _parse_iso_date(arguments.get("to_date"))
    ticker = arguments.get("ticker")
    if isinstance(ticker, str):
        tickers = [ticker.upper()]
    elif isinstance(ticker, list):
        tickers = [str(item).upper() for item in ticker]
    elif ticker is None:
        tickers = None
    else:
        raise ToolInputError("Optional field 'ticker' must be a string or list.")
    windows = arguments.get("outcome_windows")
    if windows is not None:
        if not isinstance(windows, list):
            raise ToolInputError("Optional field 'outcome_windows' must be a list.")
        outcome_windows = [int(window) for window in windows]
    else:
        outcome_windows = None
    financial_availability_policy = arguments.get(
        "financial_availability_policy", "scraped_at"
    )
    if not isinstance(financial_availability_policy, str):
        raise ToolInputError(
            "Optional field 'financial_availability_policy' must be a string."
        )
    report_lag_days_raw = arguments.get("report_lag_days", backtest.DEFAULT_REPORT_LAG_DAYS)
    try:
        report_lag_days = int(report_lag_days_raw)
    except (TypeError, ValueError) as exc:
        raise ToolInputError("Optional field 'report_lag_days' must be an integer.") from exc

    db = SessionLocal()
    try:
        return backtest.run_strategy_backtest(
            db,
            strategy=strategy,
            from_date=from_date,
            to_date=to_date,
            tickers=tickers,
            outcome_windows=outcome_windows,
            financial_availability_policy=financial_availability_policy,
            report_lag_days=report_lag_days,
        )
    except backtest.BacktestInputError as exc:
        raise ToolInputError(str(exc)) from exc
    finally:
        db.close()


def evaluate_agent_runs(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    strategy = str(
        arguments.get("strategy") or agent_evaluation.STRATEGY_VALUATION_DIRECTION
    )
    from_date = _parse_iso_date(arguments.get("from_date"))
    to_date = _parse_iso_date(arguments.get("to_date"))
    ticker = arguments.get("ticker")
    workflow = arguments.get("workflow")
    windows = arguments.get("outcome_windows")
    if windows is not None:
        if not isinstance(windows, list):
            raise ToolInputError("Optional field 'outcome_windows' must be a list.")
        outcome_windows = [int(window) for window in windows]
    else:
        outcome_windows = None

    db = SessionLocal()
    try:
        return agent_evaluation.run_agent_evaluation(
            db,
            strategy=strategy,
            from_date=from_date,
            to_date=to_date,
            ticker=str(ticker).upper() if ticker else None,
            workflow=str(workflow) if workflow else None,
            outcome_windows=outcome_windows,
        )
    except agent_evaluation.AgentEvaluationInputError as exc:
        raise ToolInputError(str(exc)) from exc
    finally:
        db.close()


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
