"""Evaluate saved agent analyses against later price outcomes."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.services import agent_evaluation
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
    parser = argparse.ArgumentParser(
        description="Replay saved agent analyses against future outcomes."
    )
    parser.add_argument("--strategy", default=agent_evaluation.STRATEGY_VALUATION_DIRECTION)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--ticker")
    parser.add_argument("--workflow")
    parser.add_argument(
        "--outcome-window",
        action="append",
        help="Outcome window in days; repeatable. Defaults to 30/90/180/365.",
    )
    add_json_flags(parser)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = agent_evaluation.run_agent_evaluation(
            db,
            strategy=args.strategy,
            from_date=_parse_date(args.from_date),
            to_date=_parse_date(args.to_date),
            ticker=args.ticker,
            workflow=args.workflow,
            outcome_windows=_parse_windows(args.outcome_window),
        )
    except agent_evaluation.AgentEvaluationInputError as exc:
        raise ScriptError(str(exc), code=2) from exc
    finally:
        db.close()

    write_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
