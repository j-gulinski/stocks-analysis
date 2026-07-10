"""Produce a deterministic candidate-scan JSON draft.

This is deliberately not a broad crawler. It scores companies already present
in the database so Codex can review and save candidates later through the
provider-neutral run tables.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from scripts.codex_common import add_json_flags, run_main, write_json

from app.db.base import SessionLocal
from app.db.models import Company, Price, ReportValue


def _score_company(db, company: Company) -> dict:
    latest_price = db.scalar(
        select(Price.close)
        .where(Price.company_id == company.id)
        .order_by(Price.date.desc())
        .limit(1)
    )
    income_rows = db.scalar(
        select(ReportValue.id)
        .where(ReportValue.company_id == company.id, ReportValue.statement == "income")
        .limit(1)
    )
    score = 0
    reasons = []
    missing = []

    if company.market_cap is not None:
        score += 20
        reasons.append("reported market cap available")
    else:
        missing.append("market_cap")
    if latest_price is not None:
        score += 20
        reasons.append("latest price available")
    else:
        missing.append("latest_price")
    if income_rows is not None:
        score += 40
        reasons.append("income statement data available")
    else:
        missing.append("income_statement")
    if company.sector:
        score += 10
        reasons.append("sector known")
    else:
        missing.append("sector")
    if company.shares_outstanding:
        score += 10
        reasons.append("share count known")
    else:
        missing.append("shares_outstanding")

    return {
        "ticker": company.ticker,
        "name": company.name,
        "score": score,
        "reasons": reasons,
        "missing_data": missing,
        "status": "needs-refresh" if missing else "ready-for-codex-review",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan stored companies as candidates.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--ticker", action="append", help="Restrict to ticker; repeatable.")
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stmt = select(Company).order_by(Company.ticker)
        if args.ticker:
            stmt = stmt.where(Company.ticker.in_([t.upper() for t in args.ticker]))
        companies = list(db.scalars(stmt.limit(max(1, min(args.limit, 200)))))
        rows = sorted(
            (_score_company(db, company) for company in companies),
            key=lambda row: (row["score"], row["ticker"]),
            reverse=True,
        )
    finally:
        db.close()

    write_json(
        {
            "ok": True,
            "workflow": "stock-candidate-scout",
            "source": "stored-companies",
            "candidates": rows,
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    run_main(main)
