"""Honest 1/2/3-year cards for the frozen CX.16 historical cohort.

The cards are an availability audit, not a strategy-performance calculation.
Returns are computed only when the case has an exact anchor and the local store
contains a point-in-time-admissible base price. Documentary labels (hit/miss)
never substitute for missing market returns.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, Price
from app.services import backtest
from app.services.strategies import cases

DEFAULT_WINDOWS = (365, 730, 1095)


def build_frozen_cohort_review(
    db: Session,
    *,
    outcome_windows: tuple[int, ...] = DEFAULT_WINDOWS,
) -> dict[str, Any]:
    windows = tuple(sorted(set(int(value) for value in outcome_windows)))
    cards = [_case_card(db, case, windows) for case in cases.CORPUS]
    included = [card for card in cards if card["admission_status"] != "excluded"]
    complete = bool(included) and all(
        all(item["return_pct"] is not None for item in card["horizons"])
        for card in included
    )
    return {
        "workflow": "stock-backtest-review",
        "strategy": "malik_v1",
        "period": {
            "frozen_at": "2026-07-10",
            "outcome_windows_days": list(windows),
        },
        "known_inputs_policy": (
            "Exact case anchor plus a base Price row whose scraped_at is on or "
            "before the price date; later prices are outcome-only."
        ),
        "signals": [],
        "outcomes": cards,
        "false_positives": [],
        "false_negatives": [],
        "learning_notes": [
            "Identity resolution is not outcome reconstruction.",
            "Documentary hit/miss labels remain qualitative until total-return "
            "prices and point-in-time fundamentals are reconstructed.",
            "No aggregate return or strategy-performance claim is permitted from "
            "this hand-authored cohort.",
        ],
        "verification_status": "pending" if complete else "needs-human",
        "verification": {
            "lookahead_boundary": "pass",
            "complete_numeric_outcomes": "pass" if complete else "fail",
            "excluded_placeholders": [
                card["case_id"]
                for card in cards
                if card["admission_status"] == "excluded"
            ],
        },
    }


def _case_card(db: Session, case: cases.WorkedCase, windows: tuple[int, ...]) -> dict[str, Any]:
    excluded = case.cohort_label == "unverified_placeholder"
    anchor = _parse_anchor(case.anchor_date)
    company = None
    if case.market_ticker:
        company = db.scalar(
            select(Company).where(Company.ticker == case.market_ticker.upper())
        )
    base_price = _admissible_base_price(db, company, anchor)
    if excluded:
        admission_status = "excluded"
        blocker = "Historical attribution and anchor are unverified."
    elif anchor is None:
        admission_status = "blocked"
        blocker = "No exact historical anchor date is stored."
    elif company is None:
        admission_status = "blocked"
        blocker = f"No local company/price history for {case.market_ticker}."
    elif base_price is None:
        admission_status = "blocked"
        blocker = "No point-in-time-admissible base price near the exact anchor."
    else:
        admission_status = "measurable"
        blocker = None

    computed = (
        backtest._outcomes(db, company.id, base_price, list(windows))
        if base_price is not None and company is not None and not excluded
        else None
    )
    horizons = []
    for window in windows:
        outcome = (computed or {}).get("windows", {}).get(str(window), {})
        horizons.append(
            {
                "days": window,
                "target_date": outcome.get("target_date"),
                "price_date": outcome.get("price_date"),
                "return_pct": outcome.get("return_pct"),
                "status": "measured" if outcome.get("return_pct") is not None else "unavailable",
                "reason": None if outcome.get("return_pct") is not None else blocker,
            }
        )
    return {
        "case_id": case.ticker,
        "cohort_label": case.cohort_label,
        "documented_outcome": case.outcome or "unquantified",
        "admission_status": admission_status,
        "market_identity": {
            "ticker": case.market_ticker,
            "isin": case.isin,
            "market": case.market,
            "source": case.identity_source,
        },
        "anchor": {
            "description": case.as_of,
            "exact_date": anchor,
        },
        "base_price": (
            {
                "date": base_price.date,
                "close": float(base_price.close),
                "scraped_at": base_price.scraped_at,
            }
            if base_price is not None
            else None
        ),
        "horizons": horizons,
        "blocker": blocker,
        "sources": dict(case.sources),
        "gaps": list(case.gaps),
    }


def _parse_anchor(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _admissible_base_price(
    db: Session,
    company: Company | None,
    anchor: date | None,
) -> Price | None:
    if company is None or anchor is None:
        return None
    candidate = db.scalar(
        select(Price)
        .where(
            Price.company_id == company.id,
            Price.date <= anchor,
            Price.date >= anchor - timedelta(days=7),
        )
        .order_by(Price.date.desc())
        .limit(1)
    )
    if candidate is None or not backtest._price_known_on(candidate):
        return None
    return candidate
