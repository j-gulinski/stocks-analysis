"""Persist a strict Codex verifier result without requiring the MCP client.

The JSON input is intentionally small::

    {"checks": {"source_lineage": {"passed": true}}, "summary": "..."}

The script shares the same scenario approval guard as the MCP tool, so a
fallback transport cannot approve a stale or incomplete priced simulation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.db.models import AgentRun, AnalysisRun, VerificationRun, utcnow
from app.services import analysis_contract
from scripts.codex_common import (
    ScriptError,
    add_json_flags,
    read_payload,
    require_dict,
    require_nonempty,
    run_main,
    write_json,
)


def _analysis_status(verdict: str) -> str:
    lowered = verdict.lower()
    if lowered == "pass":
        return "verified"
    if lowered == "fail":
        return "rejected"
    return "draft"


def _agent_status(verdict: str) -> str:
    lowered = verdict.lower()
    if lowered == "pass":
        return "completed"
    if lowered == "fail":
        return "rejected"
    if lowered == "needs-human":
        return "needs-human"
    return "completed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Save a strict Codex verifier result.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--analysis-run-id", type=int)
    target.add_argument("--agent-run-id", type=int)
    parser.add_argument("--verifier-model", required=True)
    parser.add_argument("--model-role", default="verifier_strict")
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--input", default="-", help="JSON input file, or '-' for stdin.")
    add_json_flags(parser)
    args = parser.parse_args()

    verifier_model = require_nonempty(args.verifier_model, "--verifier-model")
    model_role = require_nonempty(args.model_role, "--model-role")
    verdict = require_nonempty(args.verdict, "--verdict")
    payload = read_payload(args.input)
    checks = require_dict(payload, "checks")
    summary = payload.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise ScriptError("Optional JSON field 'summary' must be a string.", code=2)

    db = SessionLocal()
    try:
        analysis = db.get(AnalysisRun, args.analysis_run_id) if args.analysis_run_id else None
        agent = db.get(AgentRun, args.agent_run_id) if args.agent_run_id else None
        if args.analysis_run_id and analysis is None:
            raise ScriptError(f"Unknown analysis_run_id {args.analysis_run_id}.", code=1)
        if args.agent_run_id and agent is None:
            raise ScriptError(f"Unknown agent_run_id {args.agent_run_id}.", code=1)

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
            if contract_errors:
                raise ScriptError(" ".join(contract_errors), code=2)
            analysis.verification_status = verdict
            analysis.verification = checks
            analysis.status = _analysis_status(verdict)

        verification = VerificationRun(
            agent_run_id=agent.id if agent is not None else None,
            analysis_run_id=analysis.id if analysis is not None else None,
            model_role=model_role,
            verifier_model=verifier_model,
            verdict=verdict,
            checks=checks,
            summary=summary,
        )
        db.add(verification)
        if agent is not None:
            agent.outputs = {**(agent.outputs or {}), "verification": checks}
            agent.status = _agent_status(verdict)
            agent.finished_at = utcnow()
        db.commit()
        write_json(
            {
                "ok": True,
                "verification_run_id": verification.id,
                "analysis_run_id": analysis.id if analysis is not None else None,
                "agent_run_id": agent.id if agent is not None else None,
                "verdict": verdict,
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
