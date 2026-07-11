"""Refresh the lease for a long-running Codex workflow."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.services.agent_queue import AgentQueueError, heartbeat_agent_run
from scripts.codex_common import ScriptError, add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Heartbeat a running Codex agent run.")
    parser.add_argument("--agent-run-id", type=int, required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--lease-minutes", type=int, default=45)
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        try:
            agent = heartbeat_agent_run(
                db,
                args.agent_run_id,
                worker_id=args.worker_id,
                lease_minutes=args.lease_minutes,
            )
        except AgentQueueError as exc:
            raise ScriptError(str(exc), code=2) from exc
        write_json(
            {
                "ok": True,
                "agent_run_id": agent.id,
                "status": agent.status,
                "heartbeat_at": agent.heartbeat_at,
                "lease_expires_at": agent.lease_expires_at,
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
