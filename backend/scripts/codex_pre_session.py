"""Scheduled pre-session workflow entrypoint.

Run this before an investing session (for example from Codex automation, cron,
launchd, or a manual Codex command). It fetches GPW ESPI/EBI reports for the
watchlist and queues a `stock-pre-session-brief` agent run for Codex/GPT to
triage and verify.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.codex_common import add_json_flags, run_main, write_json

from app.mcp import stock_tools


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch ESPI/EBI and queue a Codex brief.")
    parser.add_argument("--ticker", help="Optional single ticker scope.")
    parser.add_argument("--trigger", default="scheduled")
    parser.add_argument("--orchestrator-model", default="gpt-5.5")
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Only ingest GPW list metadata; skip per-report detail fetches.",
    )
    parser.add_argument(
        "--no-queue",
        action="store_true",
        help="Fetch ESPI/EBI only; do not queue a Codex brief.",
    )
    add_json_flags(parser)
    args = parser.parse_args()

    result = stock_tools.prepare_pre_session_brief(
        {
            "ticker": args.ticker,
            "trigger": args.trigger,
            "orchestrator_model": args.orchestrator_model,
            "fetch_details": not args.no_details,
            "queue": not args.no_queue,
        }
    )
    write_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
