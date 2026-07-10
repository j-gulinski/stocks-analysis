"""Deterministic point-in-time backtest engine.

The default engine is deliberately strict: it only uses rows whose `scraped_at`
timestamp is known on or before the observation date. CX.11 adds an explicit
research-only `estimated_period_lag` mode for datasets that lack historical
publication timestamps. Future price outcomes are attached after signal
creation and kept under `outcome`, never under `known_inputs` or `signal`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BacktestObservation,
    BacktestRun,
    Company,
    Price,
    ReportValue,
)
from app.services import fields
from app.services.metrics import compute_one_off_share, period_key, previous_year_period
DEFAULT_OUTCOME_WINDOWS = (30, 90, 180, 365)
DEFAULT_REPORT_LAG_DAYS = 120
FINANCIAL_AVAILABILITY_SCRAPED_AT = "scraped_at"
FINANCIAL_AVAILABILITY_ESTIMATED_LAG = "estimated_period_lag"
FINANCIAL_AVAILABILITY_POLICIES = {
    FINANCIAL_AVAILABILITY_SCRAPED_AT,
    FINANCIAL_AVAILABILITY_ESTIMATED_LAG,
}


class BacktestInputError(ValueError):
    """User-correctable backtest request problem."""


def run_strategy_backtest(
    db: Session,
    *,
    strategy: str,
    from_date: date | None,
    to_date: date | None,
    tickers: list[str] | None = None,
    outcome_windows: list[int] | None = None,
    cadence: str = "quarterly",
    financial_availability_policy: str = FINANCIAL_AVAILABILITY_SCRAPED_AT,
    report_lag_days: int = DEFAULT_REPORT_LAG_DAYS,
    persist: bool = True,
) -> dict[str, Any]:
    if strategy != "malik_v1":
        raise BacktestInputError(f"Unsupported strategy '{strategy}'.")
    if from_date is None or to_date is None:
        raise BacktestInputError("'from_date' and 'to_date' are required for replay.")
    if from_date > to_date:
        raise BacktestInputError("'from_date' must be on or before 'to_date'.")
    if cadence != "quarterly":
        raise BacktestInputError("Only quarterly cadence is implemented in CX.8.")

    windows = _normalize_windows(outcome_windows)
    policy = _normalize_financial_availability_policy(financial_availability_policy)
    lag_days = _normalize_report_lag_days(report_lag_days)
    companies = _load_companies(db, tickers)
    parameters = {
        "tickers": [company.ticker for company in companies],
        "outcome_windows_days": windows,
        "cadence": cadence,
        "financial_availability_policy": policy,
        "report_lag_days": lag_days if policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG else None,
        "known_inputs_policy": _known_inputs_policy(policy, lag_days),
    }

    observations_payload: list[dict[str, Any]] = []
    run = None
    if persist:
        run = BacktestRun(
            strategy=strategy,
            from_date=from_date,
            to_date=to_date,
            status="running",
            model_role="deterministic",
            model="python",
            parameters=parameters,
            summary={},
            verification_status="pending",
        )
        db.add(run)
        db.flush()

    for company in companies:
        for price in _quarterly_observation_prices(db, company, from_date, to_date):
            observation = _build_observation(
                db,
                company,
                price,
                windows,
                financial_availability_policy=policy,
                report_lag_days=lag_days,
            )
            observations_payload.append(observation)
            if run is not None:
                db.add(
                    BacktestObservation(
                        backtest_run_id=run.id,
                        company_id=company.id,
                        as_of_date=price.date,
                        known_inputs=_json_safe(observation["known_inputs"]),
                        signal=_json_safe(observation["signal"]),
                        outcome=_json_safe(observation["outcome"]),
                    )
                )

    summary = _summarize(observations_payload, windows, policy, lag_days)
    if run is not None:
        run.status = "completed"
        run.summary = _json_safe(summary)
        if policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG:
            run.verification_status = "needs-human"
        db.commit()

    return {
        "ok": True,
        "workflow": "stock-backtest-review",
        "status": "completed",
        "backtest_run_id": run.id if run is not None else None,
        "strategy": strategy,
        "from_date": from_date,
        "to_date": to_date,
        "parameters": parameters,
        "summary": summary,
        "observations": observations_payload,
    }


def _normalize_windows(windows: list[int] | None) -> list[int]:
    values = list(DEFAULT_OUTCOME_WINDOWS if windows is None else windows)
    if not values:
        raise BacktestInputError("At least one outcome window is required.")
    normalized = sorted({int(value) for value in values})
    if normalized[0] <= 0 or normalized[-1] > 3650:
        raise BacktestInputError("Outcome windows must be between 1 and 3650 days.")
    return normalized


def _normalize_financial_availability_policy(policy: str | None) -> str:
    value = (policy or FINANCIAL_AVAILABILITY_SCRAPED_AT).strip()
    if value not in FINANCIAL_AVAILABILITY_POLICIES:
        allowed = ", ".join(sorted(FINANCIAL_AVAILABILITY_POLICIES))
        raise BacktestInputError(
            f"Unsupported financial availability policy '{value}'. Allowed: {allowed}."
        )
    return value


def _normalize_report_lag_days(days: int | None) -> int:
    value = DEFAULT_REPORT_LAG_DAYS if days is None else int(days)
    if value < 0 or value > 730:
        raise BacktestInputError("'report_lag_days' must be between 0 and 730.")
    return value


def _known_inputs_policy(policy: str, report_lag_days: int) -> str:
    common = (
        "Company current scalar fields such as market_cap are not used as "
        "historical signal inputs. Future prices are attached only in outcome windows."
    )
    if policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG:
        return (
            "Research-only: quarterly ReportValue rows are treated as available "
            f"{report_lag_days} days after quarter end because exact publication "
            f"timestamps are not stored yet. {common}"
        )
    return f"Only ReportValue rows with scraped_at <= as_of_date are used. {common}"


def _load_companies(db: Session, tickers: list[str] | None) -> list[Company]:
    stmt = select(Company).order_by(Company.ticker)
    if tickers:
        wanted = [ticker.upper() for ticker in tickers]
        stmt = stmt.where(Company.ticker.in_(wanted))
    companies = list(db.scalars(stmt))
    if tickers and len(companies) != len(set(t.upper() for t in tickers)):
        found = {company.ticker for company in companies}
        missing = sorted({ticker.upper() for ticker in tickers} - found)
        raise BacktestInputError(f"Unknown ticker(s): {', '.join(missing)}.")
    if not companies:
        raise BacktestInputError("No companies available for backtest.")
    return companies


def _quarterly_observation_prices(
    db: Session,
    company: Company,
    from_date: date,
    to_date: date,
) -> list[Price]:
    prices = list(
        db.scalars(
            select(Price)
            .where(
                Price.company_id == company.id,
                Price.date >= from_date,
                Price.date <= to_date,
            )
            .order_by(Price.date.asc())
        )
    )
    by_quarter: dict[tuple[int, int], Price] = {}
    for price in prices:
        quarter = (price.date.year, (price.date.month - 1) // 3 + 1)
        by_quarter[quarter] = price
    return [by_quarter[key] for key in sorted(by_quarter)]


def _build_observation(
    db: Session,
    company: Company,
    price: Price,
    windows: list[int],
    *,
    financial_availability_policy: str,
    report_lag_days: int,
) -> dict[str, Any]:
    income = _income_snapshot(
        db,
        company.id,
        price.date,
        financial_availability_policy=financial_availability_policy,
        report_lag_days=report_lag_days,
    )
    latest_period = _latest_period(income)
    latest = income.get(latest_period or "", {})
    revenue_yoy = _revenue_yoy(income, latest_period)
    one_off_share = _one_off_share(latest)
    signal = _signal(
        company,
        price,
        latest_period,
        latest,
        revenue_yoy,
        one_off_share,
        _missing_financials_evidence(financial_availability_policy),
    )
    latest_available_at = (
        _estimated_period_available_at(latest_period, report_lag_days)
        if financial_availability_policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG
        and latest_period
        else None
    )
    return {
        "ticker": company.ticker,
        "as_of_date": price.date,
        "known_inputs": {
            "availability": {
                "financial_policy": financial_availability_policy,
                "report_lag_days": (
                    report_lag_days
                    if financial_availability_policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG
                    else None
                ),
                "latest_income_available_at": latest_available_at,
            },
            "price": {"date": price.date, "close": float(price.close)},
            "financials": {
                "latest_income_period": latest_period,
                "revenue": latest.get("revenue"),
                "revenue_yoy_pct": revenue_yoy,
                "net_profit": latest.get("net_profit"),
                "operating_profit": latest.get("operating_profit"),
                "profit_on_sales": latest.get("profit_on_sales"),
                "one_off_share_pct": one_off_share,
            },
            "company": {
                "ticker": company.ticker,
                "sector": company.sector,
            },
        },
        "signal": signal,
        "outcome": _outcomes(db, company.id, price, windows),
    }


def _income_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    financial_availability_policy: str,
    report_lag_days: int,
) -> dict[str, dict[str, float]]:
    as_of_end = datetime.combine(as_of, time.max, tzinfo=timezone.utc)
    stmt = select(ReportValue).where(
        ReportValue.company_id == company_id,
        ReportValue.statement == "income",
        ReportValue.freq == "Q",
        ReportValue.value.is_not(None),
    )
    if financial_availability_policy == FINANCIAL_AVAILABILITY_SCRAPED_AT:
        stmt = stmt.where(ReportValue.scraped_at <= as_of_end)
    rows = db.scalars(stmt)

    by_period: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        if financial_availability_policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG:
            available_at = _estimated_period_available_at(row.period, report_lag_days)
            if available_at is None or available_at > as_of:
                continue
        canonical = fields.match_income_field(row.field_label, row.field_code)
        if canonical is None:
            continue
        by_period[row.period][canonical] = float(row.value)
    return dict(by_period)


def _estimated_period_available_at(period: str | None, report_lag_days: int) -> date | None:
    if not period:
        return None
    try:
        year, quarter = period_key(period)
    except ValueError:
        return None
    quarter_end = {
        1: date(year, 3, 31),
        2: date(year, 6, 30),
        3: date(year, 9, 30),
        4: date(year, 12, 31),
    }[quarter]
    return quarter_end + timedelta(days=report_lag_days)


def _missing_financials_evidence(financial_availability_policy: str) -> str:
    if financial_availability_policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG:
        return (
            "No income rows were available under the estimated period-lag "
            "policy on or before as_of_date."
        )
    return "No income rows were scraped on or before as_of_date."


def _latest_period(income: dict[str, dict[str, float]]) -> str | None:
    valid = []
    for period in income:
        try:
            period_key(period)
            valid.append(period)
        except ValueError:
            continue
    if not valid:
        return None
    return sorted(valid, key=period_key)[-1]


def _revenue_yoy(income: dict[str, dict[str, float]], period: str | None) -> float | None:
    if period is None:
        return None
    current = income.get(period, {}).get("revenue")
    previous = income.get(previous_year_period(period), {}).get("revenue")
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1.0) * 100.0, 1)


def _one_off_share(latest: dict[str, float]) -> float | None:
    return compute_one_off_share(latest)


def _signal(
    company: Company,
    price: Price,
    period: str | None,
    latest: dict[str, float],
    revenue_yoy: float | None,
    one_off_share: float | None,
    missing_financials_evidence: str,
) -> dict[str, Any]:
    checks = []
    if period is None:
        return {
            "label": "insufficient_data",
            "score": 0,
            "checks": [
                {
                    "id": "financials_known",
                    "verdict": "unknown",
                    "evidence": missing_financials_evidence,
                }
            ],
        }

    checks.append(
        {
            "id": "revenue_growth",
            "verdict": _verdict(revenue_yoy is not None and revenue_yoy >= 15),
            "evidence": f"Revenue yoy {revenue_yoy}%" if revenue_yoy is not None else "Revenue yoy unavailable.",
        }
    )
    net_profit = latest.get("net_profit")
    checks.append(
        {
            "id": "profitable",
            "verdict": _verdict(net_profit is not None and net_profit > 0),
            "evidence": f"Net profit {net_profit} tys. PLN" if net_profit is not None else "Net profit unavailable.",
        }
    )
    checks.append(
        {
            "id": "clean_operating_result",
            "verdict": _verdict(one_off_share is not None and one_off_share <= 30),
            "evidence": (
                f"One-off share {one_off_share}%"
                if one_off_share is not None
                else "One-off share unavailable."
            ),
        }
    )
    checks.append(
        {
            "id": "price_known",
            "verdict": "pass",
            "evidence": f"Price {float(price.close)} PLN from {price.date.isoformat()}.",
        }
    )
    passed = sum(1 for check in checks if check["verdict"] == "pass")
    label = "candidate" if passed >= 3 else "watch" if passed == 2 else "reject"
    return {
        "label": label,
        "score": passed,
        "total": len(checks),
        "checks": checks,
        "basis": {
            "latest_income_period": period,
            "price_date": price.date,
            "price": float(price.close),
        },
    }


def _verdict(condition: bool) -> str:
    return "pass" if condition else "fail"


def _outcomes(
    db: Session,
    company_id: int,
    base_price: Price,
    windows: list[int],
) -> dict[str, Any]:
    result: dict[str, Any] = {"base_price": float(base_price.close), "windows": {}}
    for days in windows:
        target = date.fromordinal(base_price.date.toordinal() + days)
        future = db.scalar(
            select(Price)
            .where(Price.company_id == company_id, Price.date >= target)
            .order_by(Price.date.asc())
            .limit(1)
        )
        if future is None:
            result["windows"][str(days)] = {
                "target_date": target,
                "price_date": None,
                "return_pct": None,
            }
            continue
        return_pct = round((float(future.close) / float(base_price.close) - 1.0) * 100.0, 1)
        result["windows"][str(days)] = {
            "target_date": target,
            "price_date": future.date,
            "price": float(future.close),
            "return_pct": return_pct,
        }
    return result


def _summarize(
    observations: list[dict[str, Any]],
    windows: list[int],
    financial_availability_policy: str,
    report_lag_days: int,
) -> dict[str, Any]:
    by_label: dict[str, int] = defaultdict(int)
    returns: dict[str, list[float]] = {str(window): [] for window in windows}
    for observation in observations:
        label = str(observation["signal"].get("label") or "unknown")
        by_label[label] += 1
        for window in windows:
            value = observation["outcome"]["windows"][str(window)].get("return_pct")
            if value is not None:
                returns[str(window)].append(float(value))
    average_returns = {
        window: round(sum(values) / len(values), 1) if values else None
        for window, values in returns.items()
    }
    return {
        "observation_count": len(observations),
        "signal_counts": dict(sorted(by_label.items())),
        "average_return_pct_by_window": average_returns,
        "known_inputs_policy": _known_inputs_policy(
            financial_availability_policy, report_lag_days
        ),
        "data_quality": {
            "financial_availability_policy": financial_availability_policy,
            "report_lag_days": (
                report_lag_days
                if financial_availability_policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG
                else None
            ),
            "research_only": financial_availability_policy
            == FINANCIAL_AVAILABILITY_ESTIMATED_LAG,
            "warnings": _data_quality_warnings(
                financial_availability_policy, observations
            ),
        },
    }


def _data_quality_warnings(
    financial_availability_policy: str,
    observations: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if financial_availability_policy == FINANCIAL_AVAILABILITY_ESTIMATED_LAG:
        warnings.append(
            "Exact report publication timestamps are not stored; this run uses "
            "a conservative quarter-end lag and needs verifier review before "
            "strategy learning."
        )
    if all(
        observation["signal"].get("label") == "insufficient_data"
        for observation in observations
    ) and observations:
        warnings.append("All observations lack usable financial inputs.")
    return warnings


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
