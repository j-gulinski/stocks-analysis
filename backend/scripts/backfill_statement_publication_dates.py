"""Backfill statement publication-date facts from stored immutable HTML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.services.publication_dates import backfill_statement_publication_facts
from scripts.codex_common import add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", help="Limit replay to one stored company ticker.")
    add_json_flags(parser)
    args = parser.parse_args()

    with SessionLocal() as db:
        result = backfill_statement_publication_facts(db, ticker=args.ticker)
        db.commit()

    write_json(result, pretty=args.pretty)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    run_main(main)
