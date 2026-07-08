"""Deferred real-API smoke test for the WP3 scenario refiner + WP4 valuation
agent (run on YOUR machine).

Not runnable in the sandbox (no PyPI, no egress, no DB) — byte-compile checked
only there. On a machine with the deps + a database + a key:

    cd backend
    ANTHROPIC_API_KEY=sk-ant-... python scripts/scenarios_smoke.py SNT

It builds the ticker's dossier — which runs BOTH the scenario refiner and the
valuation agent because a key is set — and prints, for each: the `engine` marker,
the iteration count, the whole scenario set (probability, target, upside, horizon
per scenario) with the probability-weighted expected value, and then the
valuation block (potential %/range, confidence level + rationale, "co zmieniłoby
ocenę"). With the key unset it prints `engine: deterministic` for both (the
fallback) — a useful check that the pass-through never breaks the dossier.
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
        full = dossier.build_dossier(db, company)
        block = full["scenarios"]
        valuation = full["valuation"]
    finally:
        db.close()

    notes = block.get("ai_notes") or {}
    print(f"ticker            : {ticker.upper()}")
    print(f"engine            : {block.get('engine')}")
    print(f"iterations        : {notes.get('iterations', 0)}")
    print(f"model             : {notes.get('model', '-')}")
    print(f"valuation_multiple: {block.get('valuation_multiple')}")
    print(f"current_price     : {block.get('current_price')}")
    print(
        f"weighted EV       : {block.get('weighted_expected_price')} "
        f"({block.get('weighted_expected_upside_pct')}%)"
    )
    print("scenarios:")
    for s in block.get("scenarios", []):
        tm = s.get("target_multiple") or {}
        hz = s.get("horizon") or {}
        print(
            f"  - [{s.get('kind')}] {s.get('label')} · p={s.get('probability')} · "
            f"{tm.get('type')} {tm.get('value')} → cena {s.get('target_price')} "
            f"({s.get('implied_upside_pct')}%) · "
            f"horyzont {hz.get('low_months')}–{hz.get('high_months')} mies."
        )
        print(f"      {s.get('narrative')}")
    if notes.get("changes"):
        print("\nai_notes.changes:")
        for change in notes["changes"]:
            print(f"  - {change}")

    # WP4 valuation agent (rides on top of the scenario set above).
    vnotes = valuation.get("ai_notes") or {}
    potential = valuation.get("potential") or {}
    confidence = valuation.get("confidence") or {}
    print("\n--- wycena (potencjał) ---")
    print(f"engine            : {valuation.get('engine')}")
    print(f"iterations        : {vnotes.get('iterations', 0)}")
    print(f"model             : {vnotes.get('model', '-')}")
    print(
        f"potential         : {potential.get('value_pct')}% "
        f"(pasmo {potential.get('range_pct')})"
    )
    print(f"  basis           : {potential.get('basis_label')}")
    print(f"confidence        : {confidence.get('level')}")
    print(f"  rationale       : {confidence.get('rationale')}")
    print("co zmieniłoby ocenę:")
    for item in valuation.get("what_would_change", []):
        print(f"  - [{item.get('id')}] {item.get('text')}")
    print(f"narrative         : {valuation.get('narrative')}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/scenarios_smoke.py <TICKER>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
