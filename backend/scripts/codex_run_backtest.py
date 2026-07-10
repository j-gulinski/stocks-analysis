"""Run a deterministic point-in-time strategy backtest for Codex workflows."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.services import backtest
from scripts.codex_common import ScriptError, add_json_flags, run_main, write_json


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ScriptError(f"Invalid ISO date: {value}", code=2) from exc


def _parse_windows(values: list[str] | None) -> list[int] | None:
    if not values:
        return None
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise ScriptError("Outcome windows must be integers.", code=2) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic strategy backtest.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--ticker", action="append", help="Restrict to ticker; repeatable.")
    parser.add_argument(
        "--financial-availability-policy",
        choices=["scraped_at", "estimated_period_lag"],
        default="scraped_at",
        help=(
            "Financial row availability policy. Default uses only rows scraped by "
            "as-of date. estimated_period_lag is research-only."
        ),
    )
    parser.add_argument(
        "--report-lag-days",
        type=int,
        default=backtest.DEFAULT_REPORT_LAG_DAYS,
        help="Quarter-end lag for estimated_period_lag research runs.",
    )
    parser.add_argument(
        "--outcome-window",
        action="append",
        help="Outcome window in days; repeatable. Defaults to 30/90/180/365.",
    )
    add_json_flags(parser)
    args = parser.parse_args()

    from_date = _parse_date(args.from_date)
    to_date = _parse_date(args.to_date)
    db = SessionLocal()
    try:
        result = backtest.run_strategy_backtest(
            db,
            strategy=args.strategy,
            from_date=from_date,
            to_date=to_date,
            tickers=args.ticker,
            outcome_windows=_parse_windows(args.outcome_window),
            financial_availability_policy=args.financial_availability_policy,
            report_lag_days=args.report_lag_days,
        )
    except backtest.BacktestInputError as exc:
        raise ScriptError(str(exc), code=2) from exc
    finally:
        db.close()

    write_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
