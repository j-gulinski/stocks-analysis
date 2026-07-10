"""Poll GPW ESPI/EBI reports for watched companies."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.codex_common import add_json_flags, run_main, write_json

from app.db.base import SessionLocal
from app.scrapers import espi


def main() -> int:
    parser = argparse.ArgumentParser(description="Report ESPI/EBI polling status.")
    parser.add_argument("--ticker")
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Only ingest list-page metadata; skip per-report detail fetches.",
    )
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = espi.poll_watchlist_reports(
            db, ticker=args.ticker, fetch_details=not args.no_details
        )
    finally:
        db.close()

    write_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
