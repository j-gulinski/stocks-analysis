"""Persist a verified/rejected Codex analysis result.

The input JSON must contain at least:

    {"output": {...}, "input_snapshot": {...}, "verification": {...}}

Usage:
    cd backend
    python3 scripts/codex_save_analysis.py SNT \
      --workflow stock-quick-analysis \
      --model-role worker_standard \
      --model gpt-5.5 \
      --verification-status pass \
      --input result.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.codex_common import (
    ScriptError,
    add_json_flags,
    get_company,
    read_payload,
    require_dict,
    require_nonempty,
    run_main,
    write_json,
)

from app.db.base import SessionLocal
from app.db.models import AgentRun, AnalysisRun, utcnow
from app.services import analysis_contract


def _status_from_verification(value: str) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Save a Codex analysis run.")
    parser.add_argument("ticker")
    parser.add_argument("--input", default="-", help="JSON input file, or '-' for stdin.")
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--model-role", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--verification-status", required=True)
    parser.add_argument("--status")
    parser.add_argument("--source", default="codex_skill")
    parser.add_argument("--created-by", default="codex")
    parser.add_argument("--agent-run-id", type=int)
    parser.add_argument("--trigger", default="manual")
    add_json_flags(parser)
    args = parser.parse_args()

    workflow = require_nonempty(args.workflow, "--workflow")
    model_role = require_nonempty(args.model_role, "--model-role")
    model = require_nonempty(args.model, "--model")
    verification_status = require_nonempty(
        args.verification_status, "--verification-status"
    )
    payload = read_payload(args.input)
    output = require_dict(payload, "output")
    input_snapshot = payload.get("input_snapshot") or {}
    verification = payload.get("verification") or {}
    if not isinstance(input_snapshot, dict):
        raise ScriptError("Optional JSON field 'input_snapshot' must be an object.", code=2)
    if not isinstance(verification, dict):
        raise ScriptError("Optional JSON field 'verification' must be an object.", code=2)
    contract_errors = analysis_contract.verified_analysis_contract_errors(
        workflow=workflow,
        verification_status=verification_status,
        output=output,
    )
    contract_errors += analysis_contract.verified_scenario_simulation_contract_errors(
        workflow=workflow,
        verification_status=verification_status,
        input_snapshot=input_snapshot,
        output=output,
        verification=verification,
    )
    if contract_errors:
        raise ScriptError(" ".join(contract_errors), code=2)

    alignment_score = payload.get("alignment_score")
    if alignment_score is None and isinstance(output.get("alignment_score"), int):
        alignment_score = output["alignment_score"]

    db = SessionLocal()
    try:
        company = get_company(db, args.ticker)
        agent_run_id = args.agent_run_id
        if agent_run_id is None:
            agent = AgentRun(
                workflow=workflow,
                trigger=args.trigger,
                status="completed",
                company_id=company.id,
                model_role=model_role,
                model=model,
                inputs=input_snapshot,
                outputs=output,
            )
            db.add(agent)
            db.flush()
            agent_run_id = agent.id

        record = AnalysisRun(
            company_id=company.id,
            agent_run_id=agent_run_id,
            source=args.source,
            workflow=workflow,
            model_role=model_role,
            model=model,
            status=args.status or _status_from_verification(verification_status),
            verification_status=verification_status,
            input_snapshot=input_snapshot,
            output=output,
            verification=verification,
            alignment_score=alignment_score,
            created_by=args.created_by,
        )
        db.add(record)
        db.flush()
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
        db.commit()
        write_json(
            {
                "ok": True,
                "ticker": company.ticker,
                "agent_run_id": agent_run_id,
                "analysis_run_id": record.id,
                "status": record.status,
                "verification_status": record.verification_status,
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
