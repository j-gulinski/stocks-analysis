"""Deferred real-API smoke test for the WP2b thesis refiner (run on YOUR machine).

Not runnable in the sandbox (no PyPI, no egress, no DB) — byte-compile checked
only there. On a machine with the deps + a database + a key:

    cd backend
    ANTHROPIC_API_KEY=sk-ant-... python scripts/thesis_ai_smoke.py SNT

It builds the ticker's dossier — which runs the refiner because a key is set —
and prints the `engine` marker, the iteration count, and the refined thesis
read. With the key unset it prints `engine: deterministic` (the fallback), which
is itself a useful check that the pass-through never breaks the dossier.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402 — after sys.path shim

from app.db.base import SessionLocal  # noqa: E402
from app.db.models import Company  # noqa: E402
from app.services import dossier  # noqa: E402


def main(ticker: str) -> int:
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if company is None:
            print(f"Nie znaleziono spółki {ticker!r} — odśwież ją najpierw.")
            return 1
        block = dossier.build_dossier(db, company)["thesis"]
    finally:
        db.close()

    engine = block.get("engine")
    notes = block.get("ai_notes") or {}
    print(f"ticker         : {ticker.upper()}")
    print(f"engine         : {engine}")
    print(f"iterations     : {notes.get('iterations', 0)}")
    print(f"model          : {notes.get('model', '-')}")
    print(f"entry_quality  : {block['entry_quality']['code']}")
    print(f"valuation_basis: {block['valuation_basis']}")
    print("thesis_read    :")
    print(block["thesis_read"])
    if notes.get("changes"):
        print("\nai_notes.changes:")
        for change in notes["changes"]:
            print(f"  - {change}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/thesis_ai_smoke.py <TICKER>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
