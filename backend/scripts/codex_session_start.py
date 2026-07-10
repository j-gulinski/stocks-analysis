"""Run one session-triggered pre-session brief and claim one queue item.

This is the detached hook used by ``./workbench start``. It deliberately stops
at the durable queue boundary: Codex still performs the claimed workflow and
must save a verifier-gated result through the normal scripts/MCP tools.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.db.models import AgentRun, utcnow
from app.mcp import stock_tools
from scripts.codex_common import add_json_flags, run_main, write_json


def _claim_agent_run(agent_run_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        agent = db.get(AgentRun, agent_run_id)
        if agent is None:
            return {"ok": False, "reason": f"unknown_agent_run:{agent_run_id}"}
        if agent.status != "queued":
            return {
                "ok": False,
                "reason": f"agent_run_not_queued:{agent.id}:{agent.status}",
            }
        agent.status = "running"
        agent.started_at = utcnow()
        db.commit()
        return {
            "ok": True,
            "agent_run_id": agent.id,
            "workflow": agent.workflow,
            "status": agent.status,
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the session preflight and claim one Codex queue item."
    )
    parser.add_argument("--trigger", default="session-start")
    parser.add_argument("--orchestrator-model", default="gpt-5.6-luna")
    add_json_flags(parser)
    args = parser.parse_args()

    prepared = stock_tools.prepare_pre_session_brief(
        {
            "trigger": args.trigger,
            "orchestrator_model": args.orchestrator_model,
            "fetch_details": True,
            "queue": True,
        }
    )
    agent_run = prepared.get("agent_run")
    claim = _claim_agent_run(agent_run["id"]) if agent_run else None
    result = {"ok": bool(prepared.get("ok") and claim and claim.get("ok")), **prepared}
    result["queue_attempt"] = claim
    write_json(result, pretty=args.pretty)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    run_main(main)
