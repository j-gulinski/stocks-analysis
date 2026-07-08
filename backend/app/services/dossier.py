"""Company dossier: one aggregation consumed by BOTH the frontend and the AI
analysis layer (PLAN §2). Maps stored rows to canonical fields, then delegates
all math to the pure functions in metrics.py / forecast.py."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    Dividend,
    Forecast,
    ForumPost,
    ForumTopic,
    IndicatorValue,
    Price,
    ReportValue,
)
from app.services import (
    fields,
    insights,
    metrics,
    scenarios,
    scenarios_ai,
    thesis,
    thesis_ai,
    valuation_ai,
)
from app.services.strategies import malik


def load_income_series(db: Session, company_id: int, freq: str = "Q") -> metrics.IncomeSeries:
    """report_values (long rows) → {period: {canonical_field: value}}.

    When several rows map to the same canonical field (group vs
    parent-shareholders net profit, duplicate aliases), the HIGHEST-RANKED
    row wins (fields.income_match_rank) — deterministic across statement
    layouts, unlike the old first-row-wins which silently depended on page
    row order and made EPS/PE incomparable between companies.
    """
    rows = db.scalars(
        select(ReportValue)
        .where(
            ReportValue.company_id == company_id,
            ReportValue.statement == "income",
            ReportValue.freq == freq,
        )
        .order_by(ReportValue.position)
    ).all()

    series: metrics.IncomeSeries = {}
    ranks: dict[tuple[str, str], int] = {}
    for row in rows:
        canonical = fields.match_income_field(row.field_label, row.field_code)
        if canonical is None or row.value is None:
            continue
        rank = fields.income_match_rank(canonical, row.field_label, row.field_code)
        key = (row.period, canonical)
        if key in ranks and ranks[key] >= rank:
            continue
        ranks[key] = rank
        series.setdefault(row.period, {})[canonical] = float(row.value)
    # Fill statement-variant gaps (kalkulacyjny layout: derive gross profit
    # and profit-on-sales) — one place, feeds UI, forecast and AI alike.
    return metrics.derive_income_fields(series)


def load_indicators_latest(
    db: Session, company_id: int
) -> dict[str, tuple[str, float]]:
    """Latest known value per indicator code → {code: (period, value)}."""
    rows = db.scalars(
        select(IndicatorValue).where(
            IndicatorValue.company_id == company_id,
            IndicatorValue.value.is_not(None),
        )
    ).all()
    latest: dict[str, tuple[str, float]] = {}
    for row in rows:
        current = latest.get(row.indicator)
        if current is None or row.period > current[0]:
            latest[row.indicator] = (row.period, float(row.value))
    return latest


def load_balance_latest(db: Session, company_id: int) -> dict[str, float]:
    rows = db.scalars(
        select(ReportValue).where(
            ReportValue.company_id == company_id,
            ReportValue.statement == "balance",
            ReportValue.freq == "Q",
        )
    ).all()
    if not rows:
        return {}

    try:
        latest_period = metrics.sort_periods({r.period for r in rows})[-1]
    except ValueError:
        return {}

    latest: dict[str, float] = {}
    for row in rows:
        if row.period != latest_period or row.value is None:
            continue
        canonical = fields.match_balance_field(row.field_label, row.field_code)
        if canonical and canonical not in latest:
            latest[canonical] = float(row.value)
    return latest


def latest_price(db: Session, company_id: int) -> tuple[float | None, object | None]:
    row = db.execute(
        select(Price.close, Price.date)
        .where(Price.company_id == company_id)
        .order_by(Price.date.desc())
        .limit(1)
    ).first()
    return (float(row.close), row.date) if row else (None, None)


def build_dossier(db: Session, company: Company) -> dict:
    income = load_income_series(db, company.id)
    quarters = metrics.compute_quarter_metrics(income)[-12:]

    price, price_date = latest_price(db, company.id)
    reported_cap = (
        float(company.market_cap) if company.market_cap is not None else None
    )
    ttm = metrics.compute_ttm(
        income, company.shares_outstanding, price, reported_market_cap=reported_cap
    )

    cz_values = [
        float(v)
        for v in db.scalars(
            select(IndicatorValue.value).where(
                IndicatorValue.company_id == company.id,
                IndicatorValue.indicator == "cz",
                IndicatorValue.value.is_not(None),
            )
        )
    ]
    pe_history = metrics.compute_pe_history(cz_values, ttm.pe)

    balance_latest = load_balance_latest(db, company.id)
    net_cash_value, net_cash_note = metrics.compute_net_cash(balance_latest)

    dividends = db.scalars(
        select(Dividend)
        .where(Dividend.company_id == company.id)
        .order_by(Dividend.year.desc())
    ).all()

    latest_forecast = db.scalar(
        select(Forecast)
        .where(Forecast.company_id == company.id)
        .order_by(Forecast.created_at.desc(), Forecast.id.desc())
        .limit(1)
    )
    forward_pe = None
    if latest_forecast is not None:
        forward_pe = (latest_forecast.result or {}).get("forward", {}).get("pe")

    prescore = metrics.compute_prescore(
        quarters=quarters,
        ttm=ttm,
        pe_history=pe_history,
        net_cash_value=net_cash_value,
        net_cash_note=net_cash_note,
        dividend_years=[d.year for d in dividends],
        forward_pe=forward_pe,
    )

    # Dynamic per-company layer: which indicators matter for THIS stock
    # (sector/size), verdict + why per indicator, honest about missing data.
    price_age_days = None
    if price_date is not None:
        try:
            price_age_days = (date.today() - price_date).days
        except TypeError:  # pragma: no cover — defensive against str dates
            price_age_days = None
    quarters_dicts = [q.to_dict() for q in quarters]
    ttm_dict = ttm.to_dict()
    pe_history_dict = pe_history.to_dict()
    dividend_yield_latest = next(
        (float(d.yield_pct) for d in dividends if d.yield_pct is not None), None
    )
    indicators_latest = load_indicators_latest(db, company.id)
    company_insights = insights.build_insights(
        sector=company.sector,
        quarters=quarters_dicts,
        ttm=ttm_dict,
        pe_history=pe_history_dict,
        net_cash_value=net_cash_value,
        balance_latest=balance_latest,
        indicators_latest=indicators_latest,
        dividend_years=[d.year for d in dividends],
        dividend_yield_latest=dividend_yield_latest,
        price_age_days=price_age_days,
    )

    # Investment-thesis layer: synthesise the insights into an entry-point read
    # (weighted pros/cons + "what to check next") for the Malik profile — the
    # only registered strategy this stage. Pure composition ON TOP of the
    # insights above; recomputes nothing (stage TH / docs/plan-stage-thesis.md).
    thesis_inputs = thesis.ThesisInputs(
        insights=company_insights,
        ttm=ttm_dict,
        pe_history=pe_history_dict,
        net_cash={"value": net_cash_value, "note": net_cash_note},
        latest_forecast=(
            {"result": latest_forecast.result}
            if latest_forecast is not None
            else None
        ),
        prescore=prescore.to_dict(),
    )
    company_thesis = thesis.build_thesis(thesis_inputs, profile=malik.MALIK)
    # WP2b: try the optional iterative Claude-API refiner on top of the
    # deterministic read. With no ANTHROPIC_API_KEY (the default) this is a
    # transparent pass-through returning the exact deterministic body plus
    # `engine: "deterministic"`; with a key it may return `engine: "ai"`
    # (+ ai_notes). It never raises, so the dossier always has a thesis block.
    thesis_block = thesis_ai.refine_thesis(
        thesis_inputs,
        malik.MALIK,
        company_thesis,
        ticker=company.ticker,
    )

    # Scenario-simulation layer (stage SC / WP3): a coherent negative/base/
    # positive trio reverting the SECTOR-relevant multiple toward the company's
    # own-history quartiles, plus the optional Claude-API refiner (event
    # scenarios, reworded narratives). Pure composition on top of the pieces
    # above; recomputes no indicator. Load the own-history series for the
    # sector-appropriate multiple (C/Z generally, C/WK finance/realestate,
    # EV/EBITDA energy) — parametrised by indicator code, same query shape as cz.
    selected_multiple = scenarios.select_valuation_multiple(
        company_insights.sector_group, malik.MALIK
    )
    if selected_multiple == "cz":
        multiple_series, multiple_current = cz_values, ttm.pe
    else:
        multiple_series = [
            float(v)
            for v in db.scalars(
                select(IndicatorValue.value).where(
                    IndicatorValue.company_id == company.id,
                    IndicatorValue.indicator == selected_multiple,
                    IndicatorValue.value.is_not(None),
                )
            )
        ]
        latest_entry = indicators_latest.get(selected_multiple)
        multiple_current = latest_entry[1] if latest_entry else None
    multiple_history = metrics.compute_multiple_history(multiple_series, multiple_current)

    scenario_inputs = scenarios.ScenarioInputs(
        thesis_inputs=thesis_inputs,
        multiple_history=multiple_history.to_dict(),
        eps=ttm.eps,
        book_value=balance_latest.get("equity"),  # equity, tys. PLN (C/WK driver)
        # EBITDA TTM is not computed anywhere yet (labelled gap) → energy names
        # fall back to their own C/Z history rather than fabricate an EV/EBITDA.
        ebitda_ttm=None,
        shares_outstanding=company.shares_outstanding,
        current_price=ttm.price,
        net_cash=net_cash_value,
    )
    scenario_set = scenarios.build_scenario_set(scenario_inputs, malik.MALIK)
    # No ANTHROPIC_API_KEY (the default) ⇒ transparent pass-through returning the
    # deterministic body + `engine: "deterministic"`; never raises.
    scenarios_block = scenarios_ai.simulate_scenarios(
        scenario_inputs, malik.MALIK, scenario_set, ticker=company.ticker
    )

    # AI valuation layer (stage SC / WP4): a stock-potential read on TOP of the
    # scenario set — how much potential (anchored to the weighted EV), at what
    # confidence (a deterministic coverage heuristic), and what would change the
    # assessment. Same deterministic-first contract: no key ⇒ the deterministic
    # valuation + `engine: "deterministic"`; never raises, so the dossier always
    # has a valuation block.
    valuation_block = valuation_ai.assess_potential(
        scenario_inputs, scenarios_block, malik.MALIK, ticker=company.ticker
    )

    topics_count = db.scalar(
        select(func.count()).select_from(ForumTopic).where(ForumTopic.company_id == company.id)
    )
    posts_count = db.scalar(
        select(func.count())
        .select_from(ForumPost)
        .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
        .where(ForumTopic.company_id == company.id)
    )
    last_post_at = db.scalar(
        select(func.max(ForumPost.posted_at))
        .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
        .where(ForumTopic.company_id == company.id)
    )

    financials_scraped_at = db.scalar(
        select(func.max(ReportValue.scraped_at)).where(ReportValue.company_id == company.id)
    )
    forum_synced_at = db.scalar(
        select(func.max(ForumTopic.last_synced_at)).where(
            ForumTopic.company_id == company.id
        )
    )

    return {
        "company": company,
        "freshness": {
            "financials_scraped_at": financials_scraped_at,
            "last_price_date": price_date,
            "forum_last_synced_at": forum_synced_at,
        },
        "quarters": quarters_dicts,
        "ttm": {**ttm_dict, "price_date": price_date},
        "pe_history": pe_history_dict,
        "net_cash": {"value": net_cash_value, "note": net_cash_note},
        "dividends": dividends,
        "prescore": prescore.to_dict(),
        "insights": company_insights.to_dict(),
        "thesis": thesis_block,
        "scenarios": scenarios_block,
        "valuation": valuation_block,
        "latest_forecast": (
            {
                "id": latest_forecast.id,
                "label": latest_forecast.label,
                "assumptions": latest_forecast.assumptions,
                "result": latest_forecast.result,
                "created_at": latest_forecast.created_at,
            }
            if latest_forecast is not None
            else None
        ),
        "forum": {
            "topics": int(topics_count or 0),
            "posts": int(posts_count or 0),
            "last_post_at": last_post_at,
        },
    }
