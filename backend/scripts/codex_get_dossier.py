"""Print the app dossier JSON for a ticker.

Usage:
    cd backend
    python3 scripts/codex_get_dossier.py SNT --pretty
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.codex_common import add_json_flags, get_company, json_safe, run_main, write_json

from app.db.base import SessionLocal
from app.services import dossier as dossier_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Return one company dossier as JSON.")
    parser.add_argument("ticker")
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        company = get_company(db, args.ticker)
        dossier = dossier_service.build_dossier(db, company)
    finally:
        db.close()

    write_json(
        {
            "ok": True,
            "ticker": args.ticker.upper(),
            "dossier": json_safe(dossier),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    run_main(main)
