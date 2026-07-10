"""Company dossier: one aggregation consumed by BOTH the frontend and the AI
analysis layer (PLAN §2). Maps stored rows to canonical fields, then delegates
all math to the pure functions in metrics.py / forecast.py."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AssumptionSet,
    AnalysisRun,
    Company,
    Dividend,
    ForumIntelligence,
    Forecast,
    ForumPost,
    ForumTopic,
    IndicatorValue,
    Price,
    ReportValue,
    ResearchCase,
    VerificationRun,
)
from app.services import (
    fields,
    insights,
    metrics,
    operating_scenarios,
    scenarios,
    thesis,
    valuation_ai,
    market_data,
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
    series = load_balance_series(db, company_id)
    if not series:
        return {}
    try:
        latest_period = metrics.sort_periods(series)[-1]
    except ValueError:
        return {}
    return series[latest_period]


def load_balance_series(db: Session, company_id: int) -> dict[str, dict[str, float]]:
    rows = db.scalars(
        select(ReportValue).where(
            ReportValue.company_id == company_id,
            ReportValue.statement == "balance",
            ReportValue.freq == "Q",
        )
    ).all()
    series: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.value is None:
            continue
        canonical = fields.match_balance_field(row.field_label, row.field_code)
        if canonical is not None:
            series.setdefault(row.period, {}).setdefault(canonical, float(row.value))
    return series


def load_cashflow_latest(db: Session, company_id: int) -> dict[str, tuple[str, float]]:
    """Latest canonical cash-flow rows, preserving their reporting period."""
    rows = db.scalars(
        select(ReportValue).where(
            ReportValue.company_id == company_id,
            ReportValue.statement == "cashflow",
            ReportValue.freq == "Q",
            ReportValue.value.is_not(None),
        )
    ).all()
    latest: dict[str, tuple[str, float]] = {}
    for row in rows:
        canonical = fields.match_cashflow_field(row.field_label, row.field_code)
        if canonical is None:
            continue
        current = latest.get(canonical)
        if current is None or row.period > current[0]:
            latest[canonical] = (row.period, float(row.value))
    return latest


def load_latest_priced_outcome_verification(db: Session, company_id: int) -> dict | None:
    """Read only the latest strict verifier result for this company's analyses."""
    row = db.scalar(
        select(VerificationRun)
        .join(AnalysisRun, AnalysisRun.id == VerificationRun.analysis_run_id)
        .where(
            AnalysisRun.company_id == company_id,
            VerificationRun.model_role == "verifier_strict",
        )
        .order_by(VerificationRun.created_at.desc(), VerificationRun.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    return {
        "model_role": row.model_role,
        "verifier_model": row.verifier_model,
        "verdict": row.verdict,
        "checks": row.checks or {},
        "summary": row.summary,
        "created_at": row.created_at,
    }


def load_approved_assumption_sets(db: Session, company_id: int) -> list[dict]:
    """Expose only approved case inputs as scenario context.

    This is deliberately a dossier composition concern: the deterministic
    scenario engine stays pure and its current valuation equations remain
    unchanged. Drafts and rejected inputs must never leak into UI-visible
    scenario context, while each approved item keeps its provenance fields.
    """
    rows = db.scalars(
        select(AssumptionSet)
        .join(ResearchCase, ResearchCase.id == AssumptionSet.research_case_id)
        .where(
            ResearchCase.company_id == company_id,
            ResearchCase.purpose == "investment-research",
            AssumptionSet.status == "approved",
        )
        .order_by(AssumptionSet.scenario_kind, AssumptionSet.id)
    ).all()
    return [
        {
            "id": row.id,
            "research_case_id": row.research_case_id,
            "scenario_kind": row.scenario_kind,
            "label": row.label,
            "status": row.status,
            "as_of": row.as_of,
            "assumptions": row.assumptions,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def latest_price(db: Session, company_id: int) -> tuple[float | None, object | None]:
    row = db.execute(
        select(Price.close, Price.date)
        .where(Price.company_id == company_id)
        .order_by(Price.date.desc())
        .limit(1)
    ).first()
    return (float(row.close), row.date) if row else (None, None)


def _analysis_context_status(market_snapshot: dict, forum_snapshot: dict | None) -> dict:
    advanced = market_snapshot.get("advanced_metrics") or {}
    forecast = market_snapshot.get("forecast_consensus") or {}
    dividend = market_snapshot.get("dividend_coverage") or {}
    missing: list[str] = []
    if not forecast:
        missing.append("BiznesRadar forecast_consensus")
    for key in ("roic", "fcf"):
        item = advanced.get(key)
        if not isinstance(item, dict) or item.get("value") is None:
            missing.append(key.upper())
    if not forum_snapshot:
        missing.append("PortalAnaliz forum_intelligence")

    return {
        "ready_for_ai": not missing,
        "missing": missing,
        "industry_type": market_snapshot.get("industry_type"),
        "premium": {
            "forecast_years": sorted(forecast.keys()),
            "has_roic": isinstance(advanced.get("roic"), dict) and advanced["roic"].get("value") is not None,
            "has_fcf": isinstance(advanced.get("fcf"), dict) and advanced["fcf"].get("value") is not None,
            "has_enterprise_value": isinstance(advanced.get("enterprise_value"), dict)
            and advanced["enterprise_value"].get("value") is not None,
            "dividend_coverage_status": dividend.get("status"),
        },
        "forum": {
            "has_intelligence": bool(forum_snapshot),
            "distilled_facts_count": len((forum_snapshot or {}).get("distilled_facts") or []),
            "last_30d_post_count": (forum_snapshot or {}).get("last_30d_post_count", 0),
            "last_30d_active_user_count": (forum_snapshot or {}).get("last_30d_active_user_count", 0),
        },
    }


def _metric_cell_value(metrics_for_year: dict, metric: str) -> float | None:
    item = metrics_for_year.get(metric)
    if isinstance(item, dict):
        item = item.get("value")
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        return None
    return float(item)


def _consensus_eps_basis(
    market_snapshot: dict,
    *,
    shares_outstanding: int | None,
    current_price: float | None,
) -> dict | None:
    """Forward EPS from BiznesRadar analyst consensus, when internally usable.

    `forecast_consensus` stores net income in tys. PLN. For C/Z scenarios the
    driver must be PLN/share, so the conversion is:
    net_income_tys * 1000 / shares_outstanding.

    If BiznesRadar also provides a consensus C/Z row, use it as a consistency
    check. A wildly inconsistent C/Z means the page snapshot, share count, or
    fixture data does not describe the same company; in that case we keep the
    trailing EPS instead of feeding a nonsense forward driver into scenarios.
    """
    if not shares_outstanding:
        return None
    forecast = market_snapshot.get("forecast_consensus") or {}
    if not isinstance(forecast, dict):
        return None

    for year_key in sorted(forecast, key=lambda item: str(item)):
        year = str(year_key)
        if not year.isdigit():
            continue
        metrics_for_year = forecast.get(year_key) or {}
        if not isinstance(metrics_for_year, dict):
            continue
        net_income = _metric_cell_value(metrics_for_year, "net_income")
        if net_income is None or net_income <= 0:
            continue
        eps = net_income * 1000.0 / shares_outstanding
        if eps <= 0:
            continue

        consensus_pe = _metric_cell_value(metrics_for_year, "pe")
        if current_price is not None and current_price > 0 and consensus_pe:
            implied_pe = current_price / eps
            # Tolerate normal timing/noise differences; reject DEC-fixture-style
            # contradictions where net income and C/Z plainly cannot both be true.
            if abs(implied_pe / consensus_pe - 1.0) > 0.35:
                continue

        net_income_item = metrics_for_year.get("net_income")
        source = (
            net_income_item.get("source")
            if isinstance(net_income_item, dict) and net_income_item.get("source")
            else "biznesradar_forecasts"
        )
        return {
            "source": "biznesradar_forecasts",
            "source_field": f"market_data.forecast_consensus.{year}.net_income",
            "source_detail": source,
            "year": year,
            "net_income_tys_pln": net_income,
            "eps": round(eps, 4),
        }
    return None


def _result_quality_block(
    quarters: list[metrics.QuarterMetrics],
    ttm: metrics.TtmAggregates,
) -> dict:
    """Concise bridge between reported and repeatable earnings.

    The stored statement proves the amount classified as discontinued, but it
    does not by itself prove the economic event behind that classification.
    Keep that cause unresolved until a primary event/report source is stored.
    """
    latest = quarters[-1] if quarters else None
    discontinued = latest.discontinued_profit if latest is not None else None
    is_material = discontinued not in (None, 0)
    if latest is None:
        summary = "Brak kwartalnych danych do oceny jakości wyniku."
    elif is_material and latest.continuing_net_profit is not None:
        summary = (
            "Raportowany wynik netto zawiera istotny wynik działalności "
            "zaniechanej. Wynik działalności kontynuowanej pokazujemy osobno "
            "i na nim opieramy kroczącą wycenę, gdy most TTM jest kompletny."
        )
    else:
        summary = (
            "W najnowszym kwartale nie wykryto niezerowej, jawnie oznaczonej "
            "pozycji działalności zaniechanej."
        )

    return {
        "period": latest.period if latest is not None else None,
        "is_material": is_material,
        "cause_status": (
            "unresolved_from_stored_evidence" if is_material else "not_applicable"
        ),
        "reported_net_profit": latest.net_profit if latest is not None else None,
        "discontinued_profit": discontinued,
        "continuing_net_profit": (
            latest.continuing_net_profit if latest is not None else None
        ),
        "discontinued_share_of_net_pct": (
            latest.discontinued_share_of_net_pct if latest is not None else None
        ),
        "one_off_share_pct": latest.one_off_share_pct if latest is not None else None,
        "reported_ttm_net_profit": ttm.net_profit,
        "continuing_ttm_net_profit": ttm.continuing_net_profit,
        "reported_eps": ttm.eps,
        "continuing_eps": ttm.continuing_eps,
        "reported_pe": ttm.pe,
        "continuing_pe": ttm.continuing_pe,
        "valuation_basis": ttm.valuation_basis,
        "summary": summary,
        "valuation_warning": (
            "Raportowane C/Z jest zniekształcone przez działalność zaniechaną; "
            "wycena używa wyniku kontynuowanego."
            if is_material and ttm.valuation_basis == "continuing"
            else "Brak kompletnego mostu TTM do wyniku kontynuowanego; wycena pozostaje raportowana."
            if is_material
            else None
        ),
        "source_fields": [
            f"quarters.{latest.period}.net_profit" if latest is not None else "quarters",
            (
                f"quarters.{latest.period}.discontinued_profit"
                if latest is not None
                else "quarters"
            ),
            "ttm.continuing_net_profit",
            "ttm.continuing_pe",
        ],
    }


def build_dossier(db: Session, company: Company, *, use_ai_refiners: bool = False) -> dict:
    # Compatibility argument only: dossier reads stay deterministic and
    # provider work belongs to explicit, audited analysis runs.
    _ = use_ai_refiners
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
    pe_history = metrics.compute_pe_history(cz_values, ttm.valuation_pe)

    balance_latest = load_balance_latest(db, company.id)
    balance_series = load_balance_series(db, company.id)
    cashflow_latest = load_cashflow_latest(db, company.id)
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
    market_row = market_data.upsert_company_market_data(
        db, company, sector_group=company_insights.sector_group
    )
    db.flush()
    market_snapshot = {
        "industry_type": market_row.industry_type,
        "priority_values": market_row.priority_values,
        "forecast_consensus": market_row.forecast_consensus,
        # Caveat for both the AI prompt (market_data flows verbatim into the
        # prompt, see services/prompts.py) and the frontend — kept as its own
        # sibling key, NOT inside forecast_consensus itself, because that dict
        # is keyed purely by year (_analysis_context_status does
        # `sorted(forecast_consensus.keys())` to build `forecast_years`; a
        # "note" key there would masquerade as a bogus year).
        "forecast_consensus_note": market_data.FORECAST_CONSENSUS_NOTE,
        "advanced_metrics": market_row.advanced_metrics,
        "dividend_coverage": market_row.dividend_coverage,
    }

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
    # Read paths are deterministic and network-free. Optional model refinement
    # belongs to an explicit analysis run with quota/provenance, never a GET.
    thesis_block = {
        **company_thesis.to_dict(),
        "engine": "deterministic",
        "ai_notes": None,
    }

    # Scenario-simulation layer (stage SC / WP3): a coherent negative/base/
    # positive trio reverting the SECTOR-relevant multiple toward the company's
    # own-history quartiles. Pure composition on top of the pieces above;
    # recomputes no indicator. Load the own-history series for the
    # sector-appropriate multiple (C/Z generally, C/WK finance/realestate,
    # EV/EBITDA energy) — parametrised by indicator code, same query shape as cz.
    selected_multiple = scenarios.select_valuation_multiple(
        company_insights.sector_group, malik.MALIK
    )
    if selected_multiple == "cz":
        multiple_series, multiple_current = cz_values, ttm.valuation_pe
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

    # O4K (trailing-4-quarters) EBITDA from BiznesRadar /prognozy, tys. PLN —
    # see app.scrapers.biznesradar.parse_forecasts + refresh._upsert_forecasts.
    # Previously always None (labelled gap): energy names fell back to their
    # own C/Z history instead of a real EV/EBITDA scenario. Still None (same
    # fallback) whenever the page had no O4K column or the row was empty.
    ebitda_ttm_item = (market_snapshot.get("advanced_metrics") or {}).get("ebitda_ttm")
    ebitda_ttm = (
        float(ebitda_ttm_item["value"])
        if isinstance(ebitda_ttm_item, dict) and ebitda_ttm_item.get("value") is not None
        else None
    )
    consensus_eps_basis = _consensus_eps_basis(
        market_snapshot,
        shares_outstanding=company.shares_outstanding,
        current_price=ttm.price,
    )
    scenario_eps = (
        consensus_eps_basis["eps"]
        if consensus_eps_basis is not None
        else ttm.valuation_eps
    )

    scenario_inputs = scenarios.ScenarioInputs(
        thesis_inputs=thesis_inputs,
        multiple_history=multiple_history.to_dict(),
        eps=scenario_eps,
        book_value=balance_latest.get("equity"),  # equity, tys. PLN (C/WK driver)
        ebitda_ttm=ebitda_ttm,
        shares_outstanding=company.shares_outstanding,
        current_price=ttm.price,
        net_cash=net_cash_value,
        market_data=market_snapshot,
        earnings_basis=consensus_eps_basis or {
            "source": "ttm_continuing" if ttm.valuation_basis == "continuing" else "ttm",
            "source_field": (
                "ttm.continuing_eps"
                if ttm.valuation_basis == "continuing"
                else "ttm.eps"
            ),
            "eps": ttm.valuation_eps,
        },
    )
    scenario_set = scenarios.build_scenario_set(scenario_inputs, malik.MALIK)
    approved_assumption_sets = load_approved_assumption_sets(db, company.id)
    operating_bridge = operating_scenarios.build_operating_bridge(
        scenario_inputs,
        income,
        malik.MALIK,
        approved_assumption_sets,
        cashflow_latest=cashflow_latest,
        balance_series=balance_series,
    )
    operating_bridge_fingerprint = operating_scenarios.operating_bridge_fingerprint(
        operating_bridge
    )
    priced_verification = load_latest_priced_outcome_verification(db, company.id)
    priced_gate = operating_scenarios.evaluate_priced_outcome_gate(
        operating_bridge, priced_verification, operating_bridge_fingerprint
    )
    scenarios_block = {
        **scenario_set.to_dict(),
        "approved_assumption_sets": approved_assumption_sets,
        "driver_sensitivity": scenarios.build_driver_sensitivity(
            scenario_inputs, malik.MALIK, approved_assumption_sets
        ),
        "operating_bridge": operating_bridge,
        "priced_operating_outcomes": priced_gate,
        "engine": "deterministic",
        "ai_notes": None,
    }
    if priced_gate["status"] == "approved":
        scenarios_block["scenarios"] = operating_scenarios.attach_priced_company_outcomes(
            scenarios_block["scenarios"], operating_bridge["fcf_lens"]
        )

    # AI valuation layer (stage SC / WP4): a stock-potential read on TOP of the
    # scenario set — how much potential (anchored to the weighted EV), at what
    # confidence (a deterministic coverage heuristic), and what would change the
    # assessment. This public deterministic entry point does not resolve model
    # settings; explicit analysis jobs own every provider call.
    valuation_block = {
        **valuation_ai.build_potential(scenario_inputs, scenarios_block, malik.MALIK),
        "engine": "deterministic",
        "ai_notes": None,
    }

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
    forum_intelligence = db.scalar(
        select(ForumIntelligence).where(
            ForumIntelligence.company_id == company.id,
            ForumIntelligence.source == "portal_analiz",
        )
    )
    forum_snapshot = (
        {
            "industry_type": forum_intelligence.industry_type,
            "last_30d_post_count": forum_intelligence.last_30d_post_count,
            "last_30d_active_user_count": forum_intelligence.last_30d_active_user_count,
            "activity_spikes": forum_intelligence.activity_spikes,
            "community_sentiment": forum_intelligence.community_sentiment,
            "distilled_facts": forum_intelligence.distilled_facts,
            # AI-distilled investment expectations (services/
            # forum_expectations.py) — None until a refresh with an
            # ANTHROPIC_API_KEY has run at least once for this company.
            # Frontend contract: dossier.forum.intelligence.expectations =
            # {claims:[{claim, confidence, type, source_post_ids}], model,
            # updated_at, source_post_count}.
            "expectations": forum_intelligence.expectations,
        }
        if forum_intelligence is not None
        else None
    )

    financials_scraped_at = db.scalar(
        select(func.max(ReportValue.scraped_at)).where(ReportValue.company_id == company.id)
    )
    forum_synced_at = db.scalar(
        select(func.max(ForumTopic.last_synced_at)).where(
            ForumTopic.company_id == company.id
        )
    )

    insights_block = {
        **company_insights.to_dict(),
        "engine": "deterministic",
        "ai_notes": None,
    }

    return {
        "company": company,
        "freshness": {
            "financials_scraped_at": financials_scraped_at,
            "last_price_date": price_date,
            "forum_last_synced_at": forum_synced_at,
        },
        "quarters": quarters_dicts,
        "ttm": {**ttm_dict, "price_date": price_date},
        "result_quality": _result_quality_block(quarters, ttm),
        "pe_history": pe_history_dict,
        "net_cash": {"value": net_cash_value, "note": net_cash_note},
        "market_data": market_snapshot,
        "analysis_context_status": _analysis_context_status(market_snapshot, forum_snapshot),
        "dividends": dividends,
        "prescore": prescore.to_dict(),
        "insights": insights_block,
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
            "intelligence": forum_snapshot,
        },
    }
