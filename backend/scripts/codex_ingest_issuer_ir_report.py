"""Ingest one issuer PDF already discovered by the RT2.3 index adapter."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.scrapers.issuer_ir import ingest_issuer_ir_report
from scripts.codex_common import add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest one discovered issuer PDF.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--force", action="store_true")
    add_json_flags(parser)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = ingest_issuer_ir_report(
            db,
            args.ticker,
            args.url,
            force=args.force,
        )
    finally:
        db.close()
    write_json(result, pretty=args.pretty)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    run_main(main)
