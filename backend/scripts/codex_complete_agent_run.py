"""Complete a queued Codex workflow that stores output on `agent_runs`.

Use this for watchlist-level or candidate-scout jobs that do not naturally
produce a single company `analysis_run`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.db.models import AgentRun, utcnow
from app.services.agent_queue import clear_agent_lease
from scripts.codex_common import (
    ScriptError,
    add_json_flags,
    read_payload,
    require_dict,
    require_nonempty,
    run_main,
    write_json,
)


def _status_from_verification(value: str) -> str:
    lowered = value.lower()
    if lowered == "pass":
        return "completed"
    if lowered == "fail":
        return "rejected"
    if lowered == "needs-human":
        return "needs-human"
    return "completed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete a Codex agent run.")
    parser.add_argument("--agent-run-id", type=int, required=True)
    parser.add_argument("--input", default="-", help="JSON input file, or '-' for stdin.")
    parser.add_argument("--verification-status", required=True)
    parser.add_argument("--status")
    parser.add_argument("--model-role")
    parser.add_argument("--model")
    parser.add_argument("--orchestrator-model")
    parser.add_argument("--error")
    add_json_flags(parser)
    args = parser.parse_args()

    verification_status = require_nonempty(
        args.verification_status,
        "--verification-status",
    )
    payload = read_payload(args.input)
    output = require_dict(payload, "output")
    verification = payload.get("verification") or {}
    if not isinstance(verification, dict):
        raise ScriptError("Optional JSON field 'verification' must be an object.", code=2)

    db = SessionLocal()
    try:
        agent = db.get(AgentRun, args.agent_run_id)
        if agent is None:
            raise ScriptError(f"Unknown agent_run_id {args.agent_run_id}.", code=1)
        if args.model_role:
            agent.model_role = args.model_role
        if args.model:
            agent.model = args.model
        if args.orchestrator_model:
            agent.orchestrator_model = args.orchestrator_model
        agent.status = args.status or _status_from_verification(verification_status)
        agent.outputs = {
            **(agent.outputs or {}),
            "output": output,
            "verification_status": verification_status,
            "verification": verification,
        }
        agent.error = args.error
        agent.finished_at = utcnow()
        clear_agent_lease(agent)
        db.commit()
        write_json(
            {
                "ok": True,
                "agent_run_id": agent.id,
                "workflow": agent.workflow,
                "status": agent.status,
                "verification_status": verification_status,
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
