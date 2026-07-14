"""Ingest one or all bounded RT2.3 issuer-IR pilot indexes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.scrapers.issuer_ir import ISSUER_IR_SOURCES, ingest_issuer_ir_indexes
from scripts.codex_common import add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest issuer-IR index evidence.")
    parser.add_argument("--ticker", action="append")
    parser.add_argument("--force", action="store_true")
    add_json_flags(parser)
    args = parser.parse_args()
    tickers = [value.upper() for value in (args.ticker or ISSUER_IR_SOURCES)]
    db = SessionLocal()
    try:
        results = [
            ingest_issuer_ir_indexes(db, ticker, force=args.force) for ticker in tickers
        ]
    finally:
        db.close()
    write_json(
        {"ok": all(result["ok"] for result in results), "results": results},
        pretty=args.pretty,
    )
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    run_main(main)
