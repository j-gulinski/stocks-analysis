"""Pick the next queued Codex workflow run and print an execution brief.

This script is the bridge between web-created queue rows and a Codex-operated
worker. It can be run manually, from a background Codex thread, or from a
scheduled Codex task. It does not call a model by itself; it claims durable work
and tells Codex which skill/tool contract should execute it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import AgentRun, Company, utcnow
from scripts.codex_common import ScriptError, add_json_flags, run_main, write_json


def _bounded_limit(value: int) -> int:
    return min(max(value, 1), 50)


def _company_ticker(db, company_id: int | None) -> str | None:
    if company_id is None:
        return None
    company = db.get(Company, company_id)
    return company.ticker if company is not None else None


def _agent_row(db, agent: AgentRun) -> dict[str, Any]:
    return {
        "id": agent.id,
        "workflow": agent.workflow,
        "trigger": agent.trigger,
        "status": agent.status,
        "ticker": _company_ticker(db, agent.company_id),
        "model_role": agent.model_role,
        "model": agent.model,
        "orchestrator_model": agent.orchestrator_model,
        "inputs": agent.inputs,
        "outputs": agent.outputs,
        "error": agent.error,
        "started_at": agent.started_at,
        "finished_at": agent.finished_at,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def _execution_contract(agent: AgentRun) -> dict[str, Any]:
    ticker = (agent.inputs or {}).get("ticker")
    base: dict[str, Any] = {
        "agent_run_id": agent.id,
        "workflow": agent.workflow,
        "status_after_pick": agent.status,
        "requested_model_role": agent.model_role,
        "requested_model": agent.model,
        "orchestrator_model": agent.orchestrator_model,
        "must_save_result": True,
        "verification_required": "stock-verifier before any UI-visible verified result",
    }
    if agent.workflow == "stock-quick-analysis":
        return {
            **base,
            "skill": "stock-quick-analysis",
            "steps": [
                "Read docs/project-guardrails.md.",
                f"Use get_company_dossier for {ticker or 'the queued ticker'}.",
                "Create a compact evidence-grounded analysis from stored data.",
                "Run stock-verifier on the draft.",
                "Save through save_analysis_run with this agent_run_id.",
            ],
        }
    if agent.workflow == "stock-deep-analysis":
        return {
            **base,
            "skill": "stock-deep-analysis",
            "steps": [
                "Read docs/project-guardrails.md and docs/strategy-malik.md.",
                f"Use get_company_dossier for {ticker or 'the queued ticker'}.",
                "Build a verifier-gated decision memo with thesis, scenarios, risks and gaps.",
                "Run stock-verifier before saving any verified status.",
                "Save through save_analysis_run with this agent_run_id.",
            ],
        }
    if agent.workflow == "stock-pre-session-brief":
        return {
            **base,
            "skill": "stock-pre-session-brief",
            "steps": [
                "Use get_recent_source_deltas for the watchlist or queued ticker.",
                "Triage fresh ESPI/EBI events and list material changes, gaps and follow-ups.",
                "Run stock-verifier for material claims.",
                "Save company-specific output through save_analysis_run, or complete "
                "watchlist-level output with codex_complete_agent_run.py / complete_agent_run.",
            ],
        }
    if agent.workflow == "stock-candidate-scout":
        source = (agent.inputs or {}).get("source")
        source_step = (
            "Use inputs.candidates as the immutable source shortlist; do not replace "
            "it with rank_candidates and do not broad-refresh companies."
            if source == "biznesradar-market-rating"
            else "Run rank_candidates or backend/scripts/codex_candidate_scan.py."
        )
        return {
            **base,
            "skill": "stock-candidate-scout",
            "steps": [
                source_step,
                "Interpret candidate readiness without inventing missing financial facts.",
                "Run stock-verifier before promoting any candidate.",
                "Complete the queue row with codex_complete_agent_run.py or MCP complete_agent_run.",
            ],
        }
    if agent.workflow == "stock-backtest-review":
        return {
            **base,
            "skill": "stock-backtest-review",
            "steps": [
                "Run deterministic backtest via run_backtest or codex_run_backtest.py.",
                "Treat estimated_period_lag runs as research-only needs-human evidence.",
                "Interpret false positives, false negatives and data gaps separately from math.",
                "Run stock-verifier before saving learning conclusions.",
            ],
        }
    if agent.workflow == "stock-verifier":
        return {
            **base,
            "skill": "stock-verifier",
            "steps": [
                "Load the target analysis/backtest/candidate result from inputs.",
                "Audit source grounding, schema completeness and look-ahead boundaries.",
                "Persist verifier result through mark_verification_result.",
            ],
        }
    return {
        **base,
        "skill": None,
        "steps": [
            "Unsupported workflow for automatic briefing. Inspect inputs manually.",
            "Do not mark complete until a verified structured result is saved.",
        ],
    }


def _query_agents(db, *, status: str, workflow: str | None, limit: int) -> list[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.status == status)
        .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
        .limit(_bounded_limit(limit))
    )
    if workflow:
        stmt = stmt.where(AgentRun.workflow == workflow)
    return list(db.scalars(stmt))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List or claim queued Codex workflow runs for a Codex worker."
    )
    parser.add_argument("--workflow", help="Restrict to one workflow.")
    parser.add_argument("--status", default="queued", help="Status to list; default queued.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--agent-run-id", type=int, help="Claim a specific queued run.")
    parser.add_argument("--claim", action="store_true", help="Claim the first matching run.")
    parser.add_argument("--model-role", help="Model role to record when claiming.")
    parser.add_argument("--model", help="Concrete model to record when claiming.")
    parser.add_argument("--orchestrator-model", help="Orchestrator model to record.")
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        selected: AgentRun | None = None
        if args.agent_run_id is not None:
            selected = db.get(AgentRun, args.agent_run_id)
            if selected is None:
                raise ScriptError(f"Unknown agent_run_id {args.agent_run_id}.", code=1)
        elif args.claim:
            selected = next(
                iter(
                    _query_agents(
                        db,
                        status=args.status,
                        workflow=args.workflow,
                        limit=1,
                    )
                ),
                None,
            )

        if selected is not None:
            if selected.status != "queued":
                raise ScriptError(
                    f"Agent run {selected.id} has status '{selected.status}', not 'queued'.",
                    code=2,
                )
            selected.status = "running"
            selected.started_at = utcnow()
            if args.model_role:
                selected.model_role = args.model_role
            if args.model:
                selected.model = args.model
            if args.orchestrator_model:
                selected.orchestrator_model = args.orchestrator_model
            db.commit()
            db.refresh(selected)
            write_json(
                {
                    "ok": True,
                    "action": "claimed",
                    "agent_run": _agent_row(db, selected),
                    "execution_contract": _execution_contract(selected),
                },
                pretty=args.pretty,
            )
            return 0

        rows = _query_agents(
            db,
            status=args.status,
            workflow=args.workflow,
            limit=args.limit,
        )
        write_json(
            {
                "ok": True,
                "action": "listed",
                "status": args.status,
                "workflow": args.workflow,
                "agent_runs": [_agent_row(db, row) for row in rows],
            },
            pretty=args.pretty,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    run_main(main)
