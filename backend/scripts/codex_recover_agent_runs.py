"""Recover Codex queue rows whose worker lease expired."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.services.agent_queue import DEFAULT_MAX_ATTEMPTS, recover_expired_agent_runs
from scripts.codex_common import add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Requeue expired Codex leases, stopping after a bounded attempt count."
    )
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--dry-run", action="store_true")
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.dry_run:
            # The normal path is intentionally the only mutating implementation;
            # a dry run is for the scheduled worker's observability step.
            from datetime import datetime, timezone
            from sqlalchemy import select
            from app.db.models import AgentRun
            from app.services.model_policy import CANONICAL_WORKFLOWS

            rows = list(
                db.scalars(
                    select(AgentRun)
                    .where(
                        AgentRun.workflow.in_(CANONICAL_WORKFLOWS),
                        AgentRun.status == "running",
                        AgentRun.lease_expires_at.is_not(None),
                        AgentRun.lease_expires_at < datetime.now(timezone.utc),
                    )
                    .order_by(AgentRun.lease_expires_at.asc(), AgentRun.id.asc())
                )
            )
        else:
            rows = recover_expired_agent_runs(db, max_attempts=args.max_attempts)
        write_json(
            {
                "ok": True,
                "dry_run": args.dry_run,
                "recovered": [
                    {
                        "agent_run_id": row.id,
                        "workflow": row.workflow,
                        "status": row.status,
                        "attempt_count": row.attempt_count,
                    }
                    for row in rows
                ],
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
