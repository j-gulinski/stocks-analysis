"""Prepare one explicit pre-session brief without claiming its queue item.

The legacy script remains as a manual compatibility entry point. ``workbench
start`` no longer invokes it, and only an executing picker/worker may acquire a
lease for the queued workflow.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.mcp import stock_tools
from scripts.codex_common import add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the session preflight; an executing worker claims it later."
    )
    parser.add_argument("--trigger", default="session-start")
    parser.add_argument("--orchestrator-model", default="gpt-5.6-terra")
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
    result = {"ok": bool(prepared.get("ok")), **prepared}
    result["queue_attempt"] = None
    result["message"] = (
        "Pre-session row prepared; no lease was claimed. Use an executing Codex "
        "picker/worker to process it."
    )
    write_json(result, pretty=args.pretty)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    run_main(main)
