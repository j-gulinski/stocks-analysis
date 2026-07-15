"""Point-in-time valuation inputs and pure scenario equations for P3."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ResearchVerifierResult, ValuationRequestIn
from app.db.models import (
    AgentRun,
    Company,
    CompanyProfile,
    DocumentVersion,
    Fact,
    Price,
    ResearchCase,
    ResearchSnapshot,
    SourceDocument,
)
from app.services.artifact_contracts import (
    RESEARCH_PROFILE_SCHEMA,
    RESEARCH_SNAPSHOT_CONTRACT,
)
from app.services import fields, metrics
from app.services.valuation_templates import get_template

ENGINE_VERSION = "valuation-engine-v4"
TEMPLATE_CONTRACT_VERSION = "valuation-templates-v3"
REVENUE_KEY = "income.IncomeRevenues"
COST_OF_SALES_KEY = "income.IncomeCostOfSales"
NET_PROFIT_KEYS = ("income.IncomeShareholderNetProfit", "income.IncomeNetProfit")
DISCONTINUED_KEY = "income.IncomeDiscontinuedProfit"
BASE_FINANCIAL_KEYS = {
    REVENUE_KEY,
    COST_OF_SALES_KEY,
    *NET_PROFIT_KEYS,
    DISCONTINUED_KEY,
}
CONSENSUS_METRICS = (
    "revenue",
    "ebitda",
    "operating_profit",
    "net_income",
    "capex",
    "depreciation",
)
CONSENSUS_FACT_KEYS = {
    f"consensus.{metric}.{statistic}"
    for metric in CONSENSUS_METRICS
    for statistic in ("value", "low", "high", "forecast_count", "growth_pct")
}
MARKET_IMPLIED_FORWARD_PE_KEY = "market_implied.forward_pe"
class ValuationInputError(ValueError):
    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def classify_forward_pe_identity(
    expectations: dict[str, dict[str, float | int | None]],
    *,
    market_cap_pln: float,
    shares_outstanding: int,
    tolerance_pct: float = 0.25,
) -> dict:
    """Prove whether a forecast P/E row merely recreates today's equity value.

    BiznesRadar publishes forecast earnings beside a forward trading P/E.  The
    multiple is current market capitalisation divided by those earnings, not an
    analyst target multiple.  This classification is deterministic so no model
    may relabel the row as valuation evidence.
    """
    rows: list[dict] = []
    for period in sorted(expectations):
        values = expectations[period]
        net_income = values.get("net_income_pln_thousands")
        forward_pe = values.get("forward_pe")
        if net_income is None or forward_pe is None:
            continue
        implied_market_cap = float(net_income) * 1000.0 * float(forward_pe)
        difference_pct = abs(implied_market_cap / market_cap_pln - 1.0) * 100.0
        rows.append(
            {
                "period": period,
                "net_income_pln_thousands": float(net_income),
                "forward_pe": float(forward_pe),
                "implied_market_cap_pln": round(implied_market_cap, 2),
                "implied_price_pln": round(implied_market_cap / shares_outstanding, 4),
                "market_cap_difference_pct": round(difference_pct, 4),
            }
        )
    is_identity = bool(rows) and all(
        row["market_cap_difference_pct"] <= tolerance_pct for row in rows
    )
    return {
        "classification": (
            "current_trading_multiple_identity" if is_identity else "not_proven_identity"
        ),
        "not_a_target_multiple": is_identity,
        "tolerance_pct": tolerance_pct,
        "rows": rows,
    }


def calculate_fcff_dcf(
    forecast_years: list[dict],
    *,
    wacc_pct: float,
    terminal_growth_pct: float,
    terminal_reinvestment_rate_pct: float,
    terminal_incremental_roic_pct: float,
    net_debt_pln_thousands: float,
    shares_outstanding: int,
) -> dict:
    """Deterministic FCFF DCF in the Workbench's statement unit (tys. PLN)."""
    if not forecast_years:
        raise ValuationInputError("FCFF DCF requires at least one forecast year.")
    if wacc_pct <= terminal_growth_pct:
        raise ValuationInputError("DCF requires WACC above terminal growth.")
    if not -100 <= terminal_reinvestment_rate_pct <= 100:
        raise ValuationInputError(
            "DCF terminal reinvestment rate must be bounded to -100..100%."
        )
    if terminal_incremental_roic_pct <= 0:
        raise ValuationInputError("DCF terminal incremental ROIC must be positive.")
    sustainable_growth = (
        terminal_reinvestment_rate_pct * terminal_incremental_roic_pct / 100.0
    )
    if abs(sustainable_growth - terminal_growth_pct) > 0.05:
        raise ValuationInputError(
            "DCF terminal growth must equal reinvestment rate x incremental ROIC."
        )
    if shares_outstanding <= 0:
        raise ValuationInputError("DCF requires a positive share count.")
    wacc = wacc_pct / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    projected: list[dict] = []
    present_value_fcff = 0.0
    present_value_event_cash = 0.0
    last_ebit = 0.0
    last_tax_rate = 0.0
    last_discount_years = 0.0
    for row in forecast_years:
        ebit = float(row["ebit_pln_thousands"])
        tax_rate = float(row["tax_rate_pct"]) / 100.0
        depreciation = float(row["depreciation_pln_thousands"])
        capex = float(row["capex_pln_thousands"])
        delta_nwc = float(row["delta_nwc_pln_thousands"])
        period_fraction = float(row["fcff_period_fraction"])
        discount_years = float(row["fcff_discount_years"])
        if not 0 < period_fraction <= 1 or discount_years <= last_discount_years:
            raise ValuationInputError(
                "DCF requires a positive period fraction and strictly increasing timing."
            )
        annual_fcff = ebit * (1.0 - tax_rate) + depreciation - capex - delta_nwc
        fcff = annual_fcff * period_fraction
        discount_factor = (1.0 + wacc) ** discount_years
        pv_fcff = fcff / discount_factor
        event_cash = float(row.get("event_cash_pln_thousands") or 0.0)
        pv_event_cash = event_cash / discount_factor
        present_value_fcff += pv_fcff
        present_value_event_cash += pv_event_cash
        last_ebit = ebit
        last_tax_rate = tax_rate
        last_discount_years = discount_years
        projected.append(
            {
                "period": row.get("period") or str(len(projected) + 1),
                "annual_fcff_pln_thousands": round(annual_fcff, 2),
                "fcff_period_fraction": round(period_fraction, 6),
                "fcff_discount_years": round(discount_years, 6),
                "fcff_pln_thousands": round(fcff, 2),
                "present_value_pln_thousands": round(pv_fcff, 2),
                "event_cash_pln_thousands": round(event_cash, 2),
                "event_cash_present_value_pln_thousands": round(
                    pv_event_cash, 2
                ),
            }
        )
    terminal_nopat = last_ebit * (1.0 - last_tax_rate) * (1.0 + terminal_growth)
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate_pct / 100.0)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    terminal_present_value = terminal_value / ((1.0 + wacc) ** last_discount_years)
    enterprise_value = present_value_fcff + terminal_present_value
    raw_equity_value = (
        enterprise_value - net_debt_pln_thousands + present_value_event_cash
    )
    equity_value = max(raw_equity_value, 0.0)
    price = equity_value * 1000.0 / shares_outstanding
    return {
        "status": "calculated",
        "forecast_years": projected,
        "wacc_pct": wacc_pct,
        "terminal_growth_pct": terminal_growth_pct,
        "terminal_reinvestment_rate_pct": terminal_reinvestment_rate_pct,
        "terminal_incremental_roic_pct": terminal_incremental_roic_pct,
        "terminal_nopat_pln_thousands": round(terminal_nopat, 2),
        "terminal_fcff_pln_thousands": round(terminal_fcff, 2),
        "terminal_value_pln_thousands": round(terminal_value, 2),
        "terminal_present_value_pln_thousands": round(terminal_present_value, 2),
        "terminal_value_share_pct": (
            round(terminal_present_value / enterprise_value * 100.0, 2)
            if enterprise_value != 0
            else None
        ),
        "enterprise_value_pln_thousands": round(enterprise_value, 2),
        "event_cash_present_value_pln_thousands": round(
            present_value_event_cash, 2
        ),
        "net_debt_pln_thousands": round(net_debt_pln_thousands, 2),
        "raw_equity_value_pln_thousands": round(raw_equity_value, 2),
        "distress_floor_applied": raw_equity_value < 0,
        "equity_value_pln_thousands": round(equity_value, 2),
        "price_pln": round(price, 2),
    }


def solve_reverse_dcf_revenue_scale(
    forecast_years: list[dict],
    *,
    wacc_pct: float,
    terminal_growth_pct: float,
    terminal_reinvestment_rate_pct: float,
    terminal_incremental_roic_pct: float,
    market_enterprise_value_pln_thousands: float,
    lower_scale: float = 0.05,
    upper_scale: float = 5.0,
) -> dict:
    """Solve the uniform operating-path scale already embedded in market EV.

    This is a diagnostic, not another fair-value method.  It holds margins,
    reinvestment ratios, WACC and terminal growth fixed and asks how large the
    full revenue/FCFF path must be to reproduce the observed enterprise value.
    """
    if market_enterprise_value_pln_thousands <= 0:
        raise ValuationInputError("Reverse DCF requires positive market enterprise value.")

    def enterprise_value(scale: float) -> float:
        scaled: list[dict] = []
        for row in forecast_years:
            clone = dict(row)
            for key in (
                "ebit_pln_thousands",
                "depreciation_pln_thousands",
                "capex_pln_thousands",
                "delta_nwc_pln_thousands",
            ):
                clone[key] = float(row[key]) * scale
            scaled.append(clone)
        result = calculate_fcff_dcf(
            scaled,
            wacc_pct=wacc_pct,
            terminal_growth_pct=terminal_growth_pct,
            terminal_reinvestment_rate_pct=terminal_reinvestment_rate_pct,
            terminal_incremental_roic_pct=terminal_incremental_roic_pct,
            net_debt_pln_thousands=0.0,
            shares_outstanding=1,
        )
        return float(result["enterprise_value_pln_thousands"])

    low_value = enterprise_value(lower_scale)
    high_value = enterprise_value(upper_scale)
    target = float(market_enterprise_value_pln_thousands)
    if not low_value <= target <= high_value:
        return {
            "status": "outside_bracket",
            "implied_revenue_path_scale_pct": None,
            "bracket_pct": [lower_scale * 100.0, upper_scale * 100.0],
            "market_enterprise_value_pln_thousands": round(target, 2),
            "bracket_enterprise_values_pln_thousands": [
                round(low_value, 2),
                round(high_value, 2),
            ],
        }
    low, high = lower_scale, upper_scale
    for _ in range(80):
        mid = (low + high) / 2.0
        if enterprise_value(mid) < target:
            low = mid
        else:
            high = mid
    scale = (low + high) / 2.0
    repriced = enterprise_value(scale)
    return {
        "status": "calculated",
        "implied_revenue_path_scale_pct": round(scale * 100.0, 4),
        "variance_vs_workbench_path_pct": round((scale - 1.0) * 100.0, 4),
        "market_enterprise_value_pln_thousands": round(target, 2),
        "repriced_enterprise_value_pln_thousands": round(repriced, 2),
        "repricing_residual_bps": round(abs(repriced / target - 1.0) * 10_000.0, 6),
        "bracket_pct": [lower_scale * 100.0, upper_scale * 100.0],
    }


def calculate_dcf_sensitivity(
    forecast_years: list[dict],
    *,
    wacc_pct: float,
    terminal_growth_pct: float,
    terminal_reinvestment_rate_pct: float,
    terminal_incremental_roic_pct: float,
    net_debt_pln_thousands: float,
    shares_outstanding: int,
) -> list[dict]:
    """Small deterministic WACC/g grid around the drafted DCF assumptions."""
    expected_growth = (
        terminal_reinvestment_rate_pct * terminal_incremental_roic_pct / 100.0
    )
    if abs(expected_growth - terminal_growth_pct) > 0.05:
        raise ValuationInputError(
            "DCF sensitivity requires reconciled terminal growth economics."
        )
    rows: list[dict] = []
    for wacc in (wacc_pct - 1.0, wacc_pct, wacc_pct + 1.0):
        for growth in (
            terminal_growth_pct - 0.5,
            terminal_growth_pct,
            terminal_growth_pct + 0.5,
        ):
            if wacc <= growth:
                continue
            implied_reinvestment_rate_pct = (
                growth / terminal_incremental_roic_pct * 100.0
            )
            # The drafted DCF is valid independently of this auxiliary grid.
            # Do not let an intentionally small +/-0.5 pp growth stress create
            # an economically impossible reinvestment rate and fail the whole
            # canonical artifact at an otherwise valid boundary input.
            if not -100.0 <= implied_reinvestment_rate_pct <= 100.0:
                continue
            result = calculate_fcff_dcf(
                forecast_years,
                wacc_pct=wacc,
                terminal_growth_pct=growth,
                terminal_reinvestment_rate_pct=implied_reinvestment_rate_pct,
                terminal_incremental_roic_pct=terminal_incremental_roic_pct,
                net_debt_pln_thousands=net_debt_pln_thousands,
                shares_outstanding=shares_outstanding,
            )
            rows.append(
                {
                    "wacc_pct": round(wacc, 2),
                    "terminal_growth_pct": round(growth, 2),
                    "terminal_reinvestment_rate_pct": round(
                        implied_reinvestment_rate_pct, 4
                    ),
                    "price_pln": result["price_pln"],
                }
            )
    return rows


def ev_to_equity_price(
    operating_metric_pln_thousands: float,
    *,
    target_multiple: float,
    net_debt_pln_thousands: float,
    shares_outstanding: int,
) -> dict:
    if target_multiple <= 0 or shares_outstanding <= 0:
        raise ValuationInputError("EV bridge requires a positive multiple and share count.")
    enterprise_value = operating_metric_pln_thousands * target_multiple
    raw_equity_value = enterprise_value - net_debt_pln_thousands
    equity_value = max(raw_equity_value, 0.0)
    return {
        "enterprise_value_pln_thousands": round(enterprise_value, 2),
        "net_debt_pln_thousands": round(net_debt_pln_thousands, 2),
        "raw_equity_value_pln_thousands": round(raw_equity_value, 2),
        "distress_floor_applied": raw_equity_value < 0,
        "equity_value_pln_thousands": round(equity_value, 2),
        "price_pln": round(equity_value * 1000.0 / shares_outstanding, 2),
    }


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _quarter_key(period: str | None) -> tuple[int, int] | None:
    if not isinstance(period, str) or len(period) != 6 or period[4] != "Q":
        return None
    try:
        year, quarter = int(period[:4]), int(period[5])
    except ValueError:
        return None
    return (year, quarter) if quarter in {1, 2, 3, 4} else None


def _fact_value(rows: list[Fact], key: str, period: str) -> Fact | None:
    return next((row for row in rows if row.fact_key == key and row.period == period), None)


def _resolve_manifest_facts(
    rows: list[Fact], version_times: dict[int, datetime]
) -> list[Fact]:
    """Select one coherent immutable fact per key/period or reject conflict.

    A manifest may contain successive immutable document versions. Repeating an
    identical value is harmless; silently choosing between different values or
    units would make the valuation depend on query order.
    """
    groups: dict[tuple[str, str | None], list[Fact]] = {}
    for row in rows:
        groups.setdefault((row.fact_key, row.period), []).append(row)
    resolved: list[Fact] = []
    for (fact_key, period), candidates in groups.items():
        signatures = {(row.numeric_value, row.unit) for row in candidates}
        if len(signatures) > 1:
            raise ValuationInputError(
                "Conflicting immutable facts in research manifest for "
                f"{fact_key}/{period}: numeric value or unit differs.",
                kind="conflict",
            )
        resolved.append(
            max(
                candidates,
                key=lambda row: (
                    _aware(version_times[row.source_version_id]),
                    row.source_version_id,
                    row.id,
                ),
            )
        )
    return resolved


def _previous_quarter(period: str) -> str:
    year, quarter = _quarter_key(period) or (0, 0)
    return f"{year - 1}Q4" if quarter == 1 else f"{year}Q{quarter - 1}"


def _financial_base(rows: list[Fact]) -> tuple[dict, list[int], list[str]]:
    revenue_rows = [row for row in rows if row.fact_key == REVENUE_KEY and _quarter_key(row.period)]
    by_period: dict[str, Fact] = {}
    for row in sorted(revenue_rows, key=lambda item: (item.source_version_id, item.id)):
        by_period[row.period] = row
    periods = sorted(by_period, key=lambda value: _quarter_key(value) or (0, 0))
    if not periods:
        raise ValuationInputError(
            "Research manifest has no immutable quarterly revenue fact.", kind="conflict"
        )
    latest_period = periods[-1]
    selected_financial_facts = [by_period[period] for period in periods[-4:]]
    if any(row.unit not in {"tys_pln", "tys. PLN"} for row in selected_financial_facts):
        raise ValuationInputError("Revenue facts must use thousands of PLN.", kind="conflict")
    latest_revenue = float(by_period[latest_period].numeric_value)
    ttm_periods = periods[-4:]
    gaps: list[str] = []
    consecutive = len(ttm_periods) == 4 and all(
        ttm_periods[index - 1] == _previous_quarter(ttm_periods[index])
        for index in range(1, len(ttm_periods))
    )
    if not consecutive:
        raise ValuationInputError(
            "Forward-12m base requires four consecutive immutable quarterly revenue facts.",
            kind="conflict",
        )
    ttm_revenue = sum(float(by_period[period].numeric_value) for period in ttm_periods)
    used = [by_period[period].id for period in ttm_periods]

    cost = _fact_value(rows, COST_OF_SALES_KEY, latest_period)
    if cost is not None:
        if cost.unit not in {"tys_pln", "tys. PLN"}:
            raise ValuationInputError("Cost-of-sales fact must use thousands of PLN.", kind="conflict")
        used.append(cost.id)
        base_margin = round(
            (latest_revenue - float(cost.numeric_value)) / latest_revenue * 100.0,
            4,
        )
    else:
        base_margin = None
        gaps.append("No immutable cost-of-sales fact for the latest quarter gross-margin base.")

    net = next(
        (
            _fact_value(rows, key, latest_period)
            for key in NET_PROFIT_KEYS
            if _fact_value(rows, key, latest_period) is not None
        ),
        None,
    )
    discontinued = _fact_value(rows, DISCONTINUED_KEY, latest_period)
    continuing_net = None
    if net is not None:
        used.append(net.id)
        continuing_net = float(net.numeric_value)
        if discontinued is not None:
            used.append(discontinued.id)
            continuing_net -= float(discontinued.numeric_value)
    return (
        {
            "latest_quarter": latest_period,
            "latest_quarter_revenue_pln_thousands": round(latest_revenue, 2),
            "forward_12m_revenue_base_pln_thousands": round(ttm_revenue, 2),
            "latest_gross_margin_pct": base_margin,
            "latest_continuing_net_result_pln_thousands": (
                round(continuing_net, 2) if continuing_net is not None else None
            ),
            "continuing_result_policy": "reported net result minus disclosed discontinued result",
        },
        sorted(set(used)),
        gaps,
    )


def _mutable_company_scalar_base(
    company: Company, as_of: datetime
) -> tuple[dict, dict, list[str]]:
    if company.updated_at is None or _aware(company.updated_at) > _aware(as_of):
        raise ValuationInputError(
            "Company shares/market-cap state was updated after valuation as_of.",
            kind="conflict",
        )
    values = {
        "shares_outstanding": company.shares_outstanding,
        "market_cap_pln": float(company.market_cap) if company.market_cap else None,
        "enterprise_value_pln": (
            float(company.enterprise_value) if company.enterprise_value else None
        ),
    }
    provenance = {
        "kind": "company_scalar_freeze",
        "updated_at": company.updated_at.isoformat(),
        "fields": ["shares_outstanding", "market_cap", "enterprise_value"],
        "fact_ids": [],
        "source_document_version_id": None,
        "immutable_fact_bound": False,
    }
    return values, provenance, [
        "Shares and reported market cap are mutable Company scalars frozen at company.updated_at, not immutable Fact IDs."
    ]


def _company_scalar_base(
    db: Session, company: Company, as_of: datetime
) -> tuple[dict, dict, list[str]]:
    """Resolve one same-version profile identity or retain the legacy gap."""
    source_row = db.execute(
        select(DocumentVersion, SourceDocument)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            SourceDocument.company_ticker == company.ticker,
            SourceDocument.source_name == "biznesradar",
            SourceDocument.source_type == "company_profile",
            SourceDocument.scope_key == "current",
            DocumentVersion.parse_status == "parsed",
            DocumentVersion.fetched_at <= as_of,
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    ).first()
    if source_row is None:
        return _mutable_company_scalar_base(company, as_of)

    version, document = source_row
    if document.company_id != company.id:
        raise ValuationInputError(
            "Company-profile source version does not match canonical company identity.",
            kind="conflict",
        )
    expected = {
        fields.COMPANY_SCALAR_FACT_KEYS["shares_outstanding"],
        fields.COMPANY_SCALAR_FACT_KEYS["market_cap"],
        fields.COMPANY_SCALAR_FACT_KEYS["enterprise_value"],
    }
    facts = list(
        db.scalars(
            select(Fact)
            .where(
                Fact.source_version_id == version.id,
                Fact.fact_type == "company_scalar",
                Fact.fact_key.in_(expected),
                Fact.numeric_value.is_not(None),
                Fact.known_at <= as_of,
                Fact.verification_state == "parsed",
            )
            .order_by(Fact.fact_key, Fact.id)
        ).all()
    )
    if any(
        fact.company_id != company.id or fact.company_ticker != company.ticker
        for fact in facts
    ):
        raise ValuationInputError(
            "Immutable company scalar facts do not match canonical company identity.",
            kind="conflict",
        )
    by_key: dict[str, list[Fact]] = {}
    for fact in facts:
        by_key.setdefault(fact.fact_key, []).append(fact)
    if set(by_key) != expected:
        return _mutable_company_scalar_base(company, as_of)

    resolved: dict[str, Fact] = {}
    for key, candidates in by_key.items():
        signatures = {(row.numeric_value, row.unit) for row in candidates}
        if len(signatures) != 1:
            raise ValuationInputError(
                f"Conflicting immutable company scalar facts for {key}.",
                kind="conflict",
            )
        resolved[key] = max(candidates, key=lambda row: row.id)

    shares_fact = resolved[fields.COMPANY_SCALAR_FACT_KEYS["shares_outstanding"]]
    market_cap_fact = resolved[fields.COMPANY_SCALAR_FACT_KEYS["market_cap"]]
    enterprise_value_fact = resolved[fields.COMPANY_SCALAR_FACT_KEYS["enterprise_value"]]
    shares_value = float(shares_fact.numeric_value)
    market_cap_value = float(market_cap_fact.numeric_value)
    enterprise_value = float(enterprise_value_fact.numeric_value)
    if shares_fact.unit != "shares" or not shares_value.is_integer() or shares_value <= 0:
        raise ValuationInputError(
            "Immutable share-count fact must be a positive whole number of shares.",
            kind="conflict",
        )
    if market_cap_fact.unit != "PLN" or market_cap_value <= 0:
        raise ValuationInputError(
            "Immutable market-cap fact must be positive PLN.", kind="conflict"
        )
    if enterprise_value_fact.unit != "PLN" or enterprise_value <= 0:
        raise ValuationInputError(
            "Immutable enterprise-value fact must be positive PLN.", kind="conflict"
        )
    values = {
        "shares_outstanding": int(shares_value),
        "market_cap_pln": market_cap_value,
        "enterprise_value_pln": enterprise_value,
    }
    provenance = {
        "kind": "immutable_company_profile_facts",
        "fields": ["shares_outstanding", "market_cap"],
        "fact_ids": sorted(row.id for row in resolved.values()),
        "source_document_id": document.id,
        "source_document_version_id": version.id,
        "source_content_hash": version.content_hash,
        "known_at": version.fetched_at.isoformat(),
        "immutable_fact_bound": True,
    }
    return values, provenance, []


def _price_base(
    db: Session,
    company: Company,
    as_of: datetime,
    *,
    shares_outstanding: int | None,
    market_cap_pln: float | None,
    scalar_fact_bound: bool,
) -> tuple[dict, list[str]]:
    row = db.scalar(
        select(Price)
        .where(
            Price.company_id == company.id,
            Price.adjustment_status == "raw_unverified",
            Price.date <= as_of.date(),
            Price.scraped_at.is_not(None),
            Price.scraped_at <= as_of,
        )
        .order_by(Price.date.desc(), Price.id.desc())
        .limit(1)
    )
    if row is None:
        raise ValuationInputError(
            "No raw_unverified price known by valuation as_of.", kind="conflict"
        )
    close = float(row.close)
    if not isfinite(close) or close <= 0:
        raise ValuationInputError(
            "Raw valuation price must be finite and positive.", kind="conflict"
        )
    gaps: list[str] = []
    implied_market_cap = None
    difference_pct = None
    if shares_outstanding and market_cap_pln:
        implied_market_cap = close * shares_outstanding
        difference_pct = round(
            abs(implied_market_cap / market_cap_pln - 1.0) * 100.0, 2
        )
        if difference_pct > 2:
            raise ValuationInputError(
                "Raw price differs from reported market cap / shares by more than 2%; "
                "the valuation reference price is blocked until the identity reconciles.",
                kind="conflict",
            )
    else:
        gaps.append("Price cannot be corroborated with reported market cap and shares.")
    if not row.source_name or not row.series_key or not row.basis_version:
        gaps.append("Raw price series has incomplete source/series/basis identity.")
    source_version = db.get(DocumentVersion, row.source_version_id) if row.source_version_id else None
    source_document = (
        db.get(SourceDocument, source_version.source_document_id)
        if source_version is not None
        else None
    )
    if source_version is None or source_document is None:
        gaps.append("Reference price row is not bound to an immutable source document version.")
    elif (
        source_document.company_id != company.id
        or source_document.company_ticker != company.ticker
        or source_document.source_name != "biznesradar"
        or source_document.source_type not in {"price_history", "company_profile"}
        or source_version.parse_status != "parsed"
        or _aware(source_version.fetched_at) > _aware(as_of)
    ):
        raise ValuationInputError(
            "Reference price source version does not match company/cutoff identity.",
            kind="conflict",
        )
    if difference_pct is None:
        reference_price_status = "not_corroborated"
    elif source_version is None:
        reference_price_status = "source_unbound"
    elif not scalar_fact_bound:
        reference_price_status = "mutable_scalar_corroboration_only"
    else:
        reference_price_status = "market_cap_corroborated"
    return {
        "price_row_id": row.id,
        "date": row.date.isoformat(),
        "close_pln": close,
        "adjustment_status": row.adjustment_status,
        "source_name": row.source_name,
        "series_key": row.series_key,
        "basis_version": row.basis_version,
        "scraped_at": row.scraped_at.isoformat() if row.scraped_at else None,
        "source_document_id": source_document.id if source_document else None,
        "source_document_version_id": source_version.id if source_version else None,
        "source_content_hash": source_version.content_hash if source_version else None,
        "reference_price_status": reference_price_status,
        "return_series_eligible": row.adjustment_status in {"split_adjusted", "total_return"},
        "implied_market_cap_pln": implied_market_cap,
        "reported_market_cap_pln": market_cap_pln,
        "corroboration_difference_pct": difference_pct,
    }, gaps


def _expectations_base(
    rows: list[Fact],
    *,
    market_cap_pln: float,
    shares_outstanding: int,
) -> tuple[dict, list[int], list[str]]:
    """Build a typed Street expectation bridge from immutable forecast facts."""
    periods: dict[str, dict] = {}
    used: list[int] = []
    gaps: list[str] = []
    for fact in rows:
        if not fact.period or not fact.period.isdigit():
            continue
        if fact.fact_key == MARKET_IMPLIED_FORWARD_PE_KEY:
            periods.setdefault(fact.period, {})["forward_pe"] = float(
                fact.numeric_value
            )
            periods[fact.period]["forward_pe_fact_id"] = fact.id
            used.append(fact.id)
            continue
        if fact.fact_key not in CONSENSUS_FACT_KEYS:
            continue
        _, metric, statistic = fact.fact_key.split(".", 2)
        key = (
            f"{metric}_pln_thousands"
            if metric in {
                "revenue",
                "ebitda",
                "operating_profit",
                "net_income",
                "capex",
                "depreciation",
            }
            else metric
        )
        target = periods.setdefault(fact.period, {}).setdefault(key, {})
        target[statistic] = float(fact.numeric_value)
        target[f"{statistic}_fact_id"] = fact.id
        used.append(fact.id)

    normalized: dict[str, dict] = {}
    for period, payload in sorted(periods.items()):
        row: dict = {"period": period, "period_kind": "fiscal_year"}
        for metric, value in payload.items():
            if metric in {"forward_pe", "forward_pe_fact_id"}:
                row[metric] = value
                continue
            if isinstance(value, dict):
                row[metric] = value.get("value")
                row[f"{metric}_growth_pct"] = value.get("growth_pct")
                row[f"{metric}_range"] = {
                    "low": value.get("low"),
                    "high": value.get("high"),
                    "forecast_count": (
                        int(value["forecast_count"])
                        if value.get("forecast_count") is not None
                        else None
                    ),
                    "fact_ids": sorted(
                        item
                        for name, item in value.items()
                        if name.endswith("_fact_id")
                    ),
                }
        normalized[period] = row
    if len(normalized) < 2:
        gaps.append(
            "Street expectation bridge has fewer than two retained fiscal periods; "
            "this reduces comparison coverage but has no directional effect."
        )
    identity_input = {
        period: {
            "net_income_pln_thousands": row.get("net_income_pln_thousands"),
            "forward_pe": row.get("forward_pe"),
        }
        for period, row in normalized.items()
    }
    identity = classify_forward_pe_identity(
        identity_input,
        market_cap_pln=market_cap_pln,
        shares_outstanding=shares_outstanding,
    )
    return (
        {
            "provider": "biznesradar",
            "periods": normalized,
            "forward_pe_semantics": identity,
            "missingness_direction": "none",
        },
        sorted(set(used)),
        gaps,
    )


def load_immutable_base(
    db: Session, *, case: ResearchCase, research_snapshot_id: int, as_of: datetime
) -> dict:
    snapshot = db.get(ResearchSnapshot, research_snapshot_id)
    if snapshot is None or snapshot.research_case_id != case.id:
        raise ValuationInputError("Research snapshot does not belong to the case.", kind="not-found")
    if snapshot.contract_version != RESEARCH_SNAPSHOT_CONTRACT:
        raise ValuationInputError("Valuation requires a canonical Research v3 snapshot.", kind="conflict")
    try:
        ResearchVerifierResult.model_validate(snapshot.verifier_result)
    except ValueError as exc:
        raise ValuationInputError(
            "Valuation requires complete adversarial Research verification evidence.",
            kind="conflict",
        ) from exc
    if snapshot.status not in {"provisional", "verified"}:
        raise ValuationInputError("Valuation requires a usable research snapshot.", kind="conflict")
    if _aware(as_of) < _aware(snapshot.as_of):
        raise ValuationInputError("Valuation as_of cannot precede research as_of.", kind="conflict")
    company = db.get(Company, case.company_id)
    profile = db.get(CompanyProfile, snapshot.company_profile_id)
    if company is None or profile is None or profile.schema_version != RESEARCH_PROFILE_SCHEMA:
        raise ValuationInputError("Research company/profile is missing.", kind="conflict")
    template = get_template(profile.archetype)
    if template is None:
        raise ValuationInputError(
            f"No valuation template for research archetype {profile.archetype}.",
            kind="conflict",
        )
    version_ids = sorted({item["document_version_id"] for item in snapshot.source_manifest})
    facts = list(
        db.scalars(
            select(Fact)
            .join(DocumentVersion, Fact.source_version_id == DocumentVersion.id)
            .where(
                Fact.source_version_id.in_(version_ids),
                Fact.company_ticker == company.ticker,
                Fact.numeric_value.is_not(None),
                Fact.known_at <= as_of,
                DocumentVersion.fetched_at <= snapshot.as_of,
            )
            .order_by(Fact.period, Fact.id)
        ).all()
    )
    available_fact_ids = {row.id for row in facts}
    valuation_facts = [row for row in facts if row.fact_key in BASE_FINANCIAL_KEYS]
    expectation_facts = [
        row
        for row in facts
        if row.fact_key in CONSENSUS_FACT_KEYS
        or row.fact_key == MARKET_IMPLIED_FORWARD_PE_KEY
    ]
    version_times = dict(
        db.execute(
            select(DocumentVersion.id, DocumentVersion.fetched_at).where(
                DocumentVersion.id.in_(version_ids)
            )
        ).all()
    )
    resolved_facts = _resolve_manifest_facts(valuation_facts, version_times)
    resolved_expectations = _resolve_manifest_facts(expectation_facts, version_times)
    base_financials, used_fact_ids, gaps = _financial_base(resolved_facts)
    used_fact_ids = sorted(set(used_fact_ids))
    scalar_values, scalar_provenance, scalar_gaps = _company_scalar_base(
        db, company, as_of
    )
    gaps.extend(scalar_gaps)
    expectations, expectation_fact_ids, expectation_gaps = _expectations_base(
        resolved_expectations,
        market_cap_pln=float(scalar_values["market_cap_pln"]),
        shares_outstanding=int(scalar_values["shares_outstanding"]),
    )
    used_fact_ids = sorted(set(used_fact_ids + expectation_fact_ids))
    gaps.extend(expectation_gaps)
    price, price_gaps = _price_base(
        db,
        company,
        as_of,
        shares_outstanding=scalar_values["shares_outstanding"],
        market_cap_pln=scalar_values["market_cap_pln"],
        scalar_fact_bound=scalar_provenance["immutable_fact_bound"],
    )
    gaps.extend(price_gaps)
    if snapshot.status == "provisional":
        gaps.append("Upstream research snapshot is provisional.")
    if snapshot.gaps:
        gaps.append(f"Upstream research contains {len(snapshot.gaps)} explicit gap(s).")
    base_values = {
        **base_financials,
        "company": {
            "id": company.id,
            "ticker": company.ticker,
            "name": company.name,
            "shares_outstanding": scalar_values["shares_outstanding"],
            "market_cap_pln": scalar_values["market_cap_pln"],
            "enterprise_value_pln": scalar_values["enterprise_value_pln"],
            "net_debt_pln": (
                scalar_values["enterprise_value_pln"]
                - scalar_values["market_cap_pln"]
                if scalar_values["enterprise_value_pln"] is not None
                and scalar_values["market_cap_pln"] is not None
                else None
            ),
            "updated_at": company.updated_at.isoformat(),
            "scalar_known_at": scalar_provenance.get("known_at"),
        },
        "price": price,
        "street_expectations": expectations,
    }
    if not scalar_values["shares_outstanding"] or scalar_values["shares_outstanding"] <= 0:
        raise ValuationInputError("A positive share count is required.", kind="conflict")
    outlook_driver_claim_paths: dict[str, list[str]] = {}
    outlook = ((snapshot.sections or {}).get("outlook") or {})
    for index, row in enumerate(outlook.get("driver_outlooks") or []):
        key = row.get("driver_key") if isinstance(row, dict) else None
        if not key:
            continue
        outlook_driver_claim_paths[str(key)] = [
            f"/sections/outlook/driver_outlooks/{index}/next_quarter/assessment",
            f"/sections/outlook/driver_outlooks/{index}/next_12_months/assessment",
        ]

    manifest = {
        "research_snapshot_id": snapshot.id,
        "research_snapshot_status": snapshot.status,
        "research_artifact_fingerprint": snapshot.artifact_fingerprint,
        "document_version_ids": version_ids,
        "fact_ids": used_fact_ids,
        "bindable_fact_ids": sorted(available_fact_ids),
        "fact_catalog": {
            str(row.id): {
                "fact_key": row.fact_key,
                "fact_type": row.fact_type,
                "unit": row.unit,
                "period": row.period,
                "source_version_id": row.source_version_id,
            }
            for row in facts
        },
        "research_claim_catalog": {
            str(item.get("path")): {
                "kind": (item.get("claim") or {}).get("kind"),
                "text": (item.get("claim") or {}).get("text"),
                "basis": (item.get("claim") or {}).get("basis"),
                "source_version_ids": (
                    (item.get("claim") or {}).get("source_document_version_ids")
                    or []
                ),
            }
            for item in (snapshot.statement_provenance or [])
            if item.get("path") and isinstance(item.get("claim"), dict)
        },
        "research_driver_catalog": {
            str(item.get("key")): {
                "label": item.get("label"),
                "mechanism": item.get("mechanism"),
                "unit": item.get("unit"),
                "source_document_version_ids": (
                    item.get("source_document_version_ids") or []
                ),
                "claim_paths": outlook_driver_claim_paths.get(
                    str(item.get("key")), []
                ),
            }
            for item in (profile.drivers or [])
            if isinstance(item, dict) and item.get("key")
        },
        "research_profile": {
            "id": profile.id,
            "version": profile.version,
            "schema_version": profile.schema_version,
        },
        "price": price,
        "company_identity": base_values["company"],
        "company_scalar_provenance": scalar_provenance,
    }
    return {
        "snapshot": snapshot,
        "template": template,
        "base_values": base_values,
        "input_manifest": manifest,
        "gaps": sorted(set(gaps)),
    }


def _forecast_path(scenario, *, shares: int) -> list[dict]:
    path: list[dict] = []
    for year in scenario.forecast_years:
        revenue = year.revenue_pln_thousands.value
        ebitda = revenue * year.ebitda_margin_pct.value / 100.0
        depreciation = revenue * year.depreciation_pct_revenue.value / 100.0
        ebit = ebitda - depreciation
        financial_result = (
            revenue * year.net_financial_result_pct_revenue.value / 100.0
        )
        pretax = ebit + financial_result
        cash_tax = max(pretax, 0.0) * year.cash_tax_rate_pct.value / 100.0
        recurring_net = pretax - cash_tax
        capex = revenue * year.capex_pct_revenue.value / 100.0
        delta_nwc = revenue * year.delta_nwc_pct_revenue.value / 100.0
        fcff = ebit * (1.0 - year.cash_tax_rate_pct.value / 100.0) + depreciation - capex - delta_nwc
        cash_after_financing = recurring_net + depreciation - capex - delta_nwc
        reported_net = recurring_net
        event_cash = 0.0
        if scenario.event_impact and scenario.event_impact.period == year.period:
            reported_net += scenario.event_impact.pnl_net_pln_thousands.value
            event_cash = scenario.event_impact.cash_pln_thousands.value
        path.append(
            {
                "period": year.period,
                "revenue_pln_thousands": round(revenue, 2),
                "ebitda_pln_thousands": round(ebitda, 2),
                "depreciation_pln_thousands": round(depreciation, 2),
                "ebit_pln_thousands": round(ebit, 2),
                "financial_result_pln_thousands": round(financial_result, 2),
                "pretax_result_pln_thousands": round(pretax, 2),
                "cash_tax_pln_thousands": round(cash_tax, 2),
                "recurring_net_result_pln_thousands": round(recurring_net, 2),
                "reported_net_result_pln_thousands": round(reported_net, 2),
                "recurring_eps_pln": round(recurring_net * 1000.0 / shares, 4),
                "capex_pln_thousands": round(capex, 2),
                "delta_nwc_pln_thousands": round(delta_nwc, 2),
                "fcff_pln_thousands": round(fcff, 2),
                "cash_after_financing_pln_thousands": round(
                    cash_after_financing, 2
                ),
                "fcff_period_fraction": round(year.fcff_period_fraction.value, 6),
                "fcff_discount_years": round(year.fcff_discount_years.value, 6),
                "event_cash_pln_thousands": round(event_cash, 2),
            }
        )
    return path


def _expectation_bridge(path: list[dict], street: dict) -> list[dict]:
    metric_pairs = (
        ("revenue_pln_thousands", "revenue_pln_thousands"),
        ("ebitda_pln_thousands", "ebitda_pln_thousands"),
        ("ebit_pln_thousands", "operating_profit_pln_thousands"),
        ("recurring_net_result_pln_thousands", "net_income_pln_thousands"),
        ("capex_pln_thousands", "capex_pln_thousands"),
    )
    result: list[dict] = []
    for model_year in path:
        street_year = (street.get("periods") or {}).get(model_year["period"], {})
        metrics = []
        for model_key, street_key in metric_pairs:
            model_value = model_year[model_key]
            street_value = street_year.get(street_key)
            variance = (
                round((model_value / street_value - 1.0) * 100.0, 2)
                if street_value not in {None, 0}
                else None
            )
            metrics.append(
                {
                    "metric": model_key.removesuffix("_pln_thousands"),
                    "workbench_pln_thousands": model_value,
                    "street_pln_thousands": street_value,
                    "street_range": street_year.get(f"{street_key}_range"),
                    "variance_pct": variance,
                    "status": "compared" if street_value is not None else "street_unknown",
                }
            )
        result.append({"period": model_year["period"], "metrics": metrics})
    return result


def _dcf_forecast_input(scenario, path: list[dict]) -> list[dict]:
    tax_by_period = {
        item.period: item.cash_tax_rate_pct.value for item in scenario.forecast_years
    }
    return [
        {
            "period": row["period"],
            "ebit_pln_thousands": row["ebit_pln_thousands"],
            "tax_rate_pct": tax_by_period[row["period"]],
            "depreciation_pln_thousands": row["depreciation_pln_thousands"],
            "capex_pln_thousands": row["capex_pln_thousands"],
            "delta_nwc_pln_thousands": row["delta_nwc_pln_thousands"],
            "fcff_period_fraction": row["fcff_period_fraction"],
            "fcff_discount_years": row["fcff_discount_years"],
            "event_cash_pln_thousands": row["event_cash_pln_thousands"],
        }
        for row in path
    ]


def _target_net_debt_bridge(
    scenario,
    path: list[dict],
    *,
    valuation_period: str,
    current_net_debt_pln_thousands: float | None,
) -> dict:
    """Reconcile the future EV equity bridge without assuming today's debt."""

    target = scenario.target_net_debt_pln_thousands
    allocation = scenario.cumulative_capital_allocation_pln_thousands
    if (
        target is None
        or allocation is None
        or current_net_debt_pln_thousands is None
    ):
        return {
            "status": "unavailable",
            "current_net_debt_pln_thousands": current_net_debt_pln_thousands,
            "cumulative_cash_after_financing_to_valuation_pln_thousands": None,
            "event_cash_to_valuation_pln_thousands": None,
            "cumulative_capital_allocation_pln_thousands": (
                allocation.value if allocation is not None else None
            ),
            "target_net_debt_pln_thousands": target.value if target is not None else None,
            "reconciliation_residual_pln_thousands": None,
        }
    included = [row for row in path if row["period"] <= valuation_period]
    cumulative_cash_after_financing = sum(
        float(row["cash_after_financing_pln_thousands"])
        * float(row["fcff_period_fraction"])
        for row in included
    )
    event_cash = sum(float(row["event_cash_pln_thousands"]) for row in included)
    expected_target = (
        current_net_debt_pln_thousands
        - cumulative_cash_after_financing
        - event_cash
        + allocation.value
    )
    residual = target.value - expected_target
    if abs(residual) > 0.02:
        raise ValuationInputError(
            "Target net debt does not reconcile current net debt, cash after financing, "
            "event cash and explicit capital allocation."
        )
    return {
        "status": "calculated",
        "current_net_debt_pln_thousands": round(
            current_net_debt_pln_thousands, 2
        ),
        "cumulative_cash_after_financing_to_valuation_pln_thousands": round(
            cumulative_cash_after_financing, 2
        ),
        "event_cash_to_valuation_pln_thousands": round(event_cash, 2),
        "cumulative_capital_allocation_pln_thousands": round(
            allocation.value, 2
        ),
        "target_net_debt_pln_thousands": round(target.value, 2),
        "reconciliation_residual_pln_thousands": round(residual, 6),
    }


def _method_outputs(
    scenario,
    path: list[dict],
    *,
    methodology,
    shares: int,
    net_debt_pln_thousands: float | None,
) -> dict[str, dict]:
    by_period = {row["period"]: row for row in path}
    selected = by_period.get(methodology.valuation_period)
    if selected is None:
        raise ValuationInputError("Valuation period is absent from scenario forecast path.")
    methods: dict[str, dict] = {}
    event_branch = scenario.kind == "event"
    net_debt_bridge = _target_net_debt_bridge(
        scenario,
        path,
        valuation_period=methodology.valuation_period,
        current_net_debt_pln_thousands=net_debt_pln_thousands,
    )
    if event_branch:
        methods["pe"] = {
            "status": "unavailable",
            "price_pln": None,
            "gap": "A non-recurring event is valued only through its timed DCF cash impact.",
        }
    elif scenario.target_pe is None or selected["recurring_eps_pln"] <= 0:
        methods["pe"] = {"status": "unavailable", "price_pln": None}
    else:
        methods["pe"] = {
            "status": "calculated",
            "value_date": "future_fiscal_period",
            "valuation_period": methodology.valuation_period,
            "target_multiple": scenario.target_pe.value,
            "recurring_eps_pln": selected["recurring_eps_pln"],
            "price_pln": round(selected["recurring_eps_pln"] * scenario.target_pe.value, 2),
        }
    target_net_debt = (
        net_debt_bridge["target_net_debt_pln_thousands"]
        if net_debt_bridge["status"] == "calculated"
        else None
    )
    for method, assumption_name, metric_name in (
        ("ev_ebitda", "target_ev_ebitda", "ebitda_pln_thousands"),
        ("ev_ebit", "target_ev_ebit", "ebit_pln_thousands"),
    ):
        assumption = getattr(scenario, assumption_name)
        if event_branch:
            methods[method] = {
                "status": "unavailable",
                "price_pln": None,
                "gap": "A non-recurring event is valued only through its timed DCF cash impact.",
            }
        elif (
            assumption is None
            or target_net_debt is None
            or selected[metric_name] <= 0
        ):
            methods[method] = {"status": "unavailable", "price_pln": None}
            if assumption is not None and selected[metric_name] <= 0:
                methods[method]["gap"] = (
                    f"{method} requires a positive operating denominator."
                )
        else:
            methods[method] = {
                "status": "calculated",
                "value_date": "future_fiscal_period",
                "valuation_period": methodology.valuation_period,
                "target_multiple": assumption.value,
                **ev_to_equity_price(
                    selected[metric_name],
                    target_multiple=assumption.value,
                    net_debt_pln_thousands=target_net_debt,
                    shares_outstanding=shares,
                ),
            }
    if (
        scenario.wacc_pct is None
        or scenario.terminal_growth_pct is None
        or net_debt_pln_thousands is None
    ):
        methods["fcff_dcf"] = {"status": "unavailable", "price_pln": None}
    else:
        dcf_input = _dcf_forecast_input(scenario, path)
        methods["fcff_dcf"] = calculate_fcff_dcf(
            dcf_input,
            wacc_pct=scenario.wacc_pct.value,
            terminal_growth_pct=scenario.terminal_growth_pct.value,
            terminal_reinvestment_rate_pct=scenario.terminal_reinvestment_rate_pct.value,
            terminal_incremental_roic_pct=scenario.terminal_incremental_roic_pct.value,
            net_debt_pln_thousands=net_debt_pln_thousands,
            shares_outstanding=shares,
        )
        methods["fcff_dcf"]["value_date"] = "present"
        methods["fcff_dcf"]["valuation_period"] = None
        methods["fcff_dcf"]["sensitivity"] = calculate_dcf_sensitivity(
            dcf_input,
            wacc_pct=scenario.wacc_pct.value,
            terminal_growth_pct=scenario.terminal_growth_pct.value,
            terminal_reinvestment_rate_pct=scenario.terminal_reinvestment_rate_pct.value,
            terminal_incremental_roic_pct=scenario.terminal_incremental_roic_pct.value,
            net_debt_pln_thousands=net_debt_pln_thousands,
            shares_outstanding=shares,
        )
    return methods


def _growth_rate(start: float, end: float, years: float) -> float | None:
    if start <= 0 or end < 0 or years <= 0:
        return None
    return round(((end / start) ** (1.0 / years) - 1.0) * 100.0, 2)


def _numeric_values(value):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _numeric_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _numeric_values(child)


def _market_hurdle(
    *,
    metric: str,
    required_value: float | None,
    forecast_value: float,
    target_multiple: float | None = None,
) -> dict:
    if required_value is None or required_value <= 0:
        return {
            "status": "unavailable",
            "metric": metric,
            "required_pln_thousands": None,
            "forecast_pln_thousands": round(forecast_value, 2),
            "coverage_pct": None,
            "headroom_pct": None,
        }
    coverage = forecast_value / required_value * 100.0
    result = {
        "status": "calculated",
        "metric": metric,
        "required_pln_thousands": round(required_value, 2),
        "forecast_pln_thousands": round(forecast_value, 2),
        "coverage_pct": round(coverage, 2),
        "headroom_pct": round(coverage - 100.0, 2),
    }
    if target_multiple is not None:
        result["target_multiple"] = round(target_multiple, 4)
    return result


def _driver_to_value_bridge(
    scenario,
    path: list[dict],
    *,
    methodology,
    current_price: float,
    market_cap: float,
    enterprise_value: float | None,
    net_debt_pln_thousands: float | None,
    target_price: float | None,
    methods: dict[str, dict],
) -> dict:
    """Compute the auditable operating-potential bridge for one scenario.

    Driver inputs reconcile to the aggregate forecast in the Pydantic
    contract.  This function exposes what those inputs imply for runway,
    reinvestment, cash conversion and today's price hurdle; it never invents
    an extra fair-value estimate.
    """

    by_period = {row["period"]: row for row in path}
    first = path[0]
    last = path[-1]
    selected = by_period[methodology.valuation_period]
    horizon_years = float(selected["fcff_discount_years"])
    full_path_years = float(int(last["period"]) - int(first["period"]))

    driver_rows = []
    for driver in scenario.potential_drivers:
        impacts = []
        for impact in driver.impacts:
            impacts.append(
                {
                    "period": impact.period,
                    "revenue_delta_pln_thousands": (
                        round(impact.revenue_delta_pln_thousands.value, 2)
                        if impact.revenue_delta_pln_thousands is not None
                        else None
                    ),
                    "ebitda_margin_delta_pp": (
                        round(impact.ebitda_margin_delta_pp.value, 4)
                        if impact.ebitda_margin_delta_pp is not None
                        else None
                    ),
                    "depreciation_pct_revenue_delta_pp": (
                        round(impact.depreciation_pct_revenue_delta_pp.value, 4)
                        if impact.depreciation_pct_revenue_delta_pp is not None
                        else None
                    ),
                    "capex_pct_revenue_delta_pp": (
                        round(impact.capex_pct_revenue_delta_pp.value, 4)
                        if impact.capex_pct_revenue_delta_pp is not None
                        else None
                    ),
                    "delta_nwc_pct_revenue_delta_pp": (
                        round(impact.delta_nwc_pct_revenue_delta_pp.value, 4)
                        if impact.delta_nwc_pct_revenue_delta_pp is not None
                        else None
                    ),
                    "cash_tax_rate_delta_pp": (
                        round(impact.cash_tax_rate_delta_pp.value, 4)
                        if impact.cash_tax_rate_delta_pp is not None
                        else None
                    ),
                    "net_financial_result_pct_revenue_delta_pp": (
                        round(
                            impact.net_financial_result_pct_revenue_delta_pp.value,
                            4,
                        )
                        if impact.net_financial_result_pct_revenue_delta_pp
                        is not None
                        else None
                    ),
                }
            )
        material_periods = [
            row["period"]
            for row in impacts
            if any(
                value not in {None, 0}
                for key, value in row.items()
                if key != "period"
            )
        ]
        driver_rows.append(
            {
                "driver_id": driver.driver_id,
                "research_driver_key": driver.research_driver_key,
                "impacts": impacts,
                "cumulative_revenue_delta_pln_thousands": round(
                    sum(row["revenue_delta_pln_thousands"] or 0.0 for row in impacts),
                    2,
                ),
                "cumulative_ebitda_margin_delta_pp": round(
                    sum(row["ebitda_margin_delta_pp"] or 0.0 for row in impacts),
                    4,
                ),
                "cumulative_depreciation_ratio_delta_pp": round(
                    sum(
                        row["depreciation_pct_revenue_delta_pp"] or 0.0
                        for row in impacts
                    ),
                    4,
                ),
                "cumulative_capex_ratio_delta_pp": round(
                    sum(row["capex_pct_revenue_delta_pp"] or 0.0 for row in impacts),
                    4,
                ),
                "cumulative_nwc_ratio_delta_pp": round(
                    sum(row["delta_nwc_pct_revenue_delta_pp"] or 0.0 for row in impacts),
                    4,
                ),
                "cumulative_cash_tax_rate_delta_pp": round(
                    sum(row["cash_tax_rate_delta_pp"] or 0.0 for row in impacts),
                    4,
                ),
                "cumulative_net_financial_result_ratio_delta_pp": round(
                    sum(
                        row["net_financial_result_pct_revenue_delta_pp"] or 0.0
                        for row in impacts
                    ),
                    4,
                ),
                "runway_end_period": material_periods[-1] if material_periods else None,
            }
        )

    weighted = [
        (row, float(row["fcff_period_fraction"]))
        for row in path
    ]
    cumulative_revenue = sum(
        row["revenue_pln_thousands"] * fraction for row, fraction in weighted
    )
    cumulative_ebitda = sum(
        row["ebitda_pln_thousands"] * fraction for row, fraction in weighted
    )
    cumulative_depreciation = sum(
        row["depreciation_pln_thousands"] * fraction for row, fraction in weighted
    )
    cumulative_capex = sum(
        row["capex_pln_thousands"] * fraction for row, fraction in weighted
    )
    cumulative_nwc = sum(
        row["delta_nwc_pln_thousands"] * fraction for row, fraction in weighted
    )
    cumulative_fcff = sum(
        row["fcff_pln_thousands"] * fraction for row, fraction in weighted
    )
    cumulative_net_reinvestment = (
        cumulative_capex - cumulative_depreciation + cumulative_nwc
    )

    event_cash_present_value = (
        sum(
            float(row["event_cash_pln_thousands"])
            / ((1.0 + scenario.wacc_pct.value / 100.0) ** float(row["fcff_discount_years"]))
            for row in path
        )
        if scenario.wacc_pct is not None
        else 0.0
    )
    market_ev_thousands = (
        float(enterprise_value) / 1000.0
        if enterprise_value is not None
        else (
            market_cap / 1000.0 + net_debt_pln_thousands
            if net_debt_pln_thousands is not None
            else None
        )
    )
    effective_market_ev = (
        market_ev_thousands - event_cash_present_value
        if market_ev_thousands is not None
        else None
    )
    net_debt_bridge = _target_net_debt_bridge(
        scenario,
        path,
        valuation_period=methodology.valuation_period,
        current_net_debt_pln_thousands=net_debt_pln_thousands,
    )
    target_net_debt = (
        net_debt_bridge["target_net_debt_pln_thousands"]
        if net_debt_bridge["status"] == "calculated"
        else None
    )
    future_ev_at_current_equity = (
        market_cap / 1000.0 + target_net_debt
        if target_net_debt is not None and scenario.kind != "event"
        else None
    )
    pe_required = (
        market_cap / scenario.target_pe.value / 1000.0
        if scenario.target_pe is not None and scenario.kind != "event"
        else None
    )
    ev_ebitda_required = (
        future_ev_at_current_equity / scenario.target_ev_ebitda.value
        if future_ev_at_current_equity is not None
        and scenario.target_ev_ebitda is not None
        else None
    )
    ev_ebit_required = (
        future_ev_at_current_equity / scenario.target_ev_ebit.value
        if future_ev_at_current_equity is not None
        and scenario.target_ev_ebit is not None
        else None
    )
    reverse_dcf = {
        "status": "unavailable",
        "implied_path_scale_pct": None,
        "coverage_pct": None,
        "headroom_pct": None,
        "held_constant": "margin, reinvestment ratios, WACC, terminal economics and timed event cash",
    }
    if (
        effective_market_ev is not None
        and effective_market_ev > 0
        and scenario.wacc_pct is not None
        and scenario.terminal_growth_pct is not None
    ):
        solved = solve_reverse_dcf_revenue_scale(
            _dcf_forecast_input(scenario, path),
            wacc_pct=scenario.wacc_pct.value,
            terminal_growth_pct=scenario.terminal_growth_pct.value,
            terminal_reinvestment_rate_pct=scenario.terminal_reinvestment_rate_pct.value,
            terminal_incremental_roic_pct=scenario.terminal_incremental_roic_pct.value,
            market_enterprise_value_pln_thousands=effective_market_ev,
        )
        if solved.get("status") == "calculated":
            scale = float(solved["implied_revenue_path_scale_pct"])
            coverage = 10000.0 / scale if scale > 0 else None
            reverse_dcf = {
                "status": "calculated",
                "implied_path_scale_pct": round(scale, 4),
                "coverage_pct": round(coverage, 2) if coverage is not None else None,
                "headroom_pct": (
                    round(coverage - 100.0, 2) if coverage is not None else None
                ),
                "repricing_residual_bps": solved.get("repricing_residual_bps"),
                "held_constant": "margin, reinvestment ratios, WACC, terminal economics and timed event cash",
            }

    current_value_gap = (
        round((target_price / current_price - 1.0) * 100.0, 2)
        if target_price is not None and current_price > 0
        else None
    )
    annualized_repricing = (
        round(((target_price / current_price) ** (1.0 / horizon_years) - 1.0) * 100.0, 2)
        if target_price is not None
        and target_price >= 0
        and current_price > 0
        and horizon_years > 0
        and methodology.primary_method != "fcff_dcf"
        else None
    )
    dcf = methods.get("fcff_dcf") or {}
    return {
        "anchor_period": first["period"],
        "valuation_period": selected["period"],
        "end_period": last["period"],
        "drivers": driver_rows,
        "trajectory": {
            "revenue": {
                "anchor_pln_thousands": first["revenue_pln_thousands"],
                "valuation_pln_thousands": selected["revenue_pln_thousands"],
                "end_pln_thousands": last["revenue_pln_thousands"],
                "cagr_pct": _growth_rate(
                    first["revenue_pln_thousands"],
                    last["revenue_pln_thousands"],
                    full_path_years,
                ),
            },
            "ebitda_margin": {
                "anchor_pct": round(
                    first["ebitda_pln_thousands"]
                    / first["revenue_pln_thousands"]
                    * 100.0,
                    4,
                ),
                "valuation_pct": round(
                    selected["ebitda_pln_thousands"]
                    / selected["revenue_pln_thousands"]
                    * 100.0,
                    4,
                ),
                "end_pct": round(
                    last["ebitda_pln_thousands"]
                    / last["revenue_pln_thousands"]
                    * 100.0,
                    4,
                ),
                "change_pp": round(
                    last["ebitda_pln_thousands"]
                    / last["revenue_pln_thousands"]
                    * 100.0
                    - first["ebitda_pln_thousands"]
                    / first["revenue_pln_thousands"]
                    * 100.0,
                    4,
                ),
            },
            "recurring_net_result": {
                "anchor_pln_thousands": first["recurring_net_result_pln_thousands"],
                "valuation_pln_thousands": selected["recurring_net_result_pln_thousands"],
                "end_pln_thousands": last["recurring_net_result_pln_thousands"],
                "cagr_pct": _growth_rate(
                    first["recurring_net_result_pln_thousands"],
                    last["recurring_net_result_pln_thousands"],
                    full_path_years,
                ),
            },
            "fcff": {
                "anchor_pln_thousands": first["fcff_pln_thousands"],
                "valuation_pln_thousands": selected["fcff_pln_thousands"],
                "end_pln_thousands": last["fcff_pln_thousands"],
                "cagr_pct": _growth_rate(
                    first["fcff_pln_thousands"],
                    last["fcff_pln_thousands"],
                    full_path_years,
                ),
            },
        },
        "reinvestment": {
            "cumulative_capex_pln_thousands": round(cumulative_capex, 2),
            "cumulative_delta_nwc_pln_thousands": round(cumulative_nwc, 2),
            "cumulative_net_reinvestment_pln_thousands": round(
                cumulative_net_reinvestment, 2
            ),
            "cumulative_fcff_pln_thousands": round(cumulative_fcff, 2),
            "net_reinvestment_to_revenue_pct": (
                round(cumulative_net_reinvestment / cumulative_revenue * 100.0, 2)
                if cumulative_revenue != 0
                else None
            ),
            "fcff_to_ebitda_pct": (
                round(cumulative_fcff / cumulative_ebitda * 100.0, 2)
                if cumulative_ebitda != 0
                else None
            ),
            "capex_to_depreciation_pct": (
                round(cumulative_capex / cumulative_depreciation * 100.0, 2)
                if cumulative_depreciation != 0
                else None
            ),
        },
        "net_debt_bridge": net_debt_bridge,
        "event_cash_present_value_pln_thousands": round(
            event_cash_present_value, 2
        ),
        "terminal_economics": {
            "growth_pct": scenario.terminal_growth_pct.value if scenario.terminal_growth_pct else None,
            "reinvestment_rate_pct": (
                scenario.terminal_reinvestment_rate_pct.value
                if scenario.terminal_reinvestment_rate_pct
                else None
            ),
            "incremental_roic_pct": (
                scenario.terminal_incremental_roic_pct.value
                if scenario.terminal_incremental_roic_pct
                else None
            ),
            "terminal_value_share_pct": dcf.get("terminal_value_share_pct"),
        },
        "market_hurdles": {
            "pe": _market_hurdle(
                metric="recurring_net_result",
                required_value=pe_required,
                forecast_value=selected["recurring_net_result_pln_thousands"],
                target_multiple=scenario.target_pe.value if scenario.target_pe else None,
            ),
            "ev_ebitda": _market_hurdle(
                metric="ebitda",
                required_value=ev_ebitda_required,
                forecast_value=selected["ebitda_pln_thousands"],
                target_multiple=(
                    scenario.target_ev_ebitda.value if scenario.target_ev_ebitda else None
                ),
            ),
            "ev_ebit": _market_hurdle(
                metric="ebit",
                required_value=ev_ebit_required,
                forecast_value=selected["ebit_pln_thousands"],
                target_multiple=(
                    scenario.target_ev_ebit.value if scenario.target_ev_ebit else None
                ),
            ),
            "fcff_dcf": reverse_dcf,
        },
        "valuation_horizon_years": round(horizon_years, 6),
        "price_change_basis": (
            "present_value_gap"
            if methodology.primary_method == "fcff_dcf"
            else "future_period_repricing"
        ),
        "current_value_gap_pct": current_value_gap,
        "annualized_price_repricing_pct": annualized_repricing,
    }


def calculate_valuation(base_values: dict, assumptions: list, methodology) -> dict:
    shares = int(base_values["company"]["shares_outstanding"])
    current_price = float(base_values["price"]["close_pln"])
    market_cap = float(base_values["company"]["market_cap_pln"])
    enterprise_value = base_values["company"].get("enterprise_value_pln")
    net_debt = base_values["company"].get("net_debt_pln")
    net_debt_thousands = float(net_debt) / 1000.0 if net_debt is not None else None
    rows = []
    for scenario in assumptions:
        path = _forecast_path(scenario, shares=shares)
        methods = _method_outputs(
            scenario,
            path,
            methodology=methodology,
            shares=shares,
            net_debt_pln_thousands=net_debt_thousands,
        )
        primary = methods[methodology.primary_method]
        target_price = primary.get("price_pln")
        return_pct = (
            round((target_price / current_price - 1.0) * 100.0, 2)
            if target_price is not None
            else None
        )
        primary_value_date = (
            primary.get("value_date"), primary.get("valuation_period")
        )
        cross_values = [
            methods[name]["price_pln"]
            for name in methodology.cross_checks
            if methods[name].get("price_pln") is not None
            and (
                methods[name].get("value_date"),
                methods[name].get("valuation_period"),
            )
            == primary_value_date
        ]
        all_values = [target_price, *cross_values] if target_price is not None else cross_values
        all_values = [float(value) for value in all_values if value is not None]
        dispersion_scale = (
            abs(float(target_price))
            if target_price not in {None, 0}
            else max((abs(value) for value in all_values), default=0.0)
        )
        dispersion = (
            round(
                (max(all_values) - min(all_values)) / dispersion_scale * 100.0,
                2,
            )
            if len(all_values) > 1 and dispersion_scale > 0
            else (0.0 if len(all_values) > 1 else None)
        )
        potential_bridge = _driver_to_value_bridge(
            scenario,
            path,
            methodology=methodology,
            current_price=current_price,
            market_cap=market_cap,
            enterprise_value=(float(enterprise_value) if enterprise_value is not None else None),
            net_debt_pln_thousands=net_debt_thousands,
            target_price=target_price,
            methods=methods,
        )
        rows.append(
            {
                "kind": scenario.kind,
                "label": scenario.label,
                "forecast_path": path,
                "expectation_bridge": _expectation_bridge(
                    path, base_values.get("street_expectations") or {}
                ),
                "methods": methods,
                "primary_method": methodology.primary_method,
                "cross_check_methods": methodology.cross_checks,
                "target_price_pln": target_price,
                "target_price_basis": primary.get("value_date"),
                "target_price_period": primary.get("valuation_period"),
                "return_pct": return_pct,
                "valuation_status": (
                    "calculated" if target_price is not None else "unavailable"
                ),
                "valuation_gap": (
                    None
                    if target_price is not None
                    else f"Primary method {methodology.primary_method} is unavailable."
                ),
                "cross_check_range_pln": (
                    {"low": round(min(all_values), 2), "high": round(max(all_values), 2)}
                    if len(all_values) > 1
                    else None
                ),
                "method_dispersion_pct": dispersion,
                "driver_to_value_bridge": potential_bridge,
            }
        )
    base_scenario = next((row for row in assumptions if row.kind == "base"), assumptions[0])
    valuation_year = next(
        row for row in base_scenario.forecast_years if row.period == methodology.valuation_period
    )
    implied: dict[str, dict] = {}
    if base_scenario.target_pe:
        implied["pe"] = {
            "implied_net_income_pln_thousands": round(
                market_cap / base_scenario.target_pe.value / 1000.0, 2
            ),
            "target_multiple": base_scenario.target_pe.value,
        }
    if enterprise_value and base_scenario.target_ev_ebitda:
        implied["ev_ebitda"] = {
            "implied_ebitda_pln_thousands": round(
                float(enterprise_value) / base_scenario.target_ev_ebitda.value / 1000.0,
                2,
            ),
            "target_multiple": base_scenario.target_ev_ebitda.value,
        }
    if enterprise_value and base_scenario.target_ev_ebit:
        implied["ev_ebit"] = {
            "implied_ebit_pln_thousands": round(
                float(enterprise_value) / base_scenario.target_ev_ebit.value / 1000.0,
                2,
            ),
            "target_multiple": base_scenario.target_ev_ebit.value,
        }
    reverse_dcf: dict = {
        "status": "unavailable",
        "gap": "Reverse DCF needs market enterprise value plus explicit WACC and terminal growth.",
    }
    market_enterprise_value = (
        float(enterprise_value)
        if enterprise_value is not None
        else (market_cap + float(net_debt) if net_debt is not None else None)
    )
    base_output = next(row for row in rows if row["kind"] == base_scenario.kind)
    if (
        market_enterprise_value is not None
        and base_scenario.wacc_pct is not None
        and base_scenario.terminal_growth_pct is not None
    ):
        reverse_dcf = solve_reverse_dcf_revenue_scale(
            _dcf_forecast_input(base_scenario, base_output["forecast_path"]),
            wacc_pct=base_scenario.wacc_pct.value,
            terminal_growth_pct=base_scenario.terminal_growth_pct.value,
            terminal_reinvestment_rate_pct=base_scenario.terminal_reinvestment_rate_pct.value,
            terminal_incremental_roic_pct=base_scenario.terminal_incremental_roic_pct.value,
            market_enterprise_value_pln_thousands=market_enterprise_value / 1000.0,
        )
        if reverse_dcf.get("status") == "calculated":
            scale = reverse_dcf["implied_revenue_path_scale_pct"] / 100.0
            implied_revenue = valuation_year.revenue_pln_thousands.value * scale
            street_year = (
                (base_values.get("street_expectations") or {}).get("periods") or {}
            ).get(methodology.valuation_period, {})
            street_revenue = street_year.get("revenue_pln_thousands")
            reverse_dcf.update(
                {
                    "valuation_period": methodology.valuation_period,
                    "implied_revenue_pln_thousands": round(implied_revenue, 2),
                    "street_revenue_pln_thousands": street_revenue,
                    "variance_to_street_revenue_pct": (
                        round((implied_revenue / street_revenue - 1.0) * 100.0, 2)
                        if street_revenue not in {None, 0}
                        else None
                    ),
                }
            )
    result = {
        "engine_version": ENGINE_VERSION,
        "current_price_pln": current_price,
        "methodology": methodology.model_dump(mode="json"),
        "street_expectations": base_values.get("street_expectations") or {},
        "priced_in_expectations": {
            "valuation_period": valuation_year.period,
            "market_cap_pln": market_cap,
            "enterprise_value_pln": enterprise_value,
            "methods": implied,
            "reverse_dcf": reverse_dcf,
        },
        "scenarios": rows,
        "probability_weighted": None,
    }
    numeric = list(_numeric_values(result))
    if not all(isfinite(value) for value in numeric):
        raise ValuationInputError("Deterministic valuation produced a non-finite value.")
    return result


def _scenario_assumption_values(scenario) -> list[tuple[str, object]]:
    values: list[tuple[str, object]] = []
    for year in scenario.forecast_years:
        for name in (
            "revenue_pln_thousands",
            "ebitda_margin_pct",
            "depreciation_pct_revenue",
            "capex_pct_revenue",
            "delta_nwc_pct_revenue",
            "cash_tax_rate_pct",
            "net_financial_result_pct_revenue",
            "fcff_period_fraction",
            "fcff_discount_years",
        ):
            values.append((f"forecast_years.{year.period}.{name}", getattr(year, name)))
    for driver in scenario.potential_drivers:
        for impact in driver.impacts:
            for name in (
                "revenue_delta_pln_thousands",
                "ebitda_margin_delta_pp",
                "depreciation_pct_revenue_delta_pp",
                "capex_pct_revenue_delta_pp",
                "delta_nwc_pct_revenue_delta_pp",
                "cash_tax_rate_delta_pp",
                "net_financial_result_pct_revenue_delta_pp",
            ):
                value = getattr(impact, name)
                if value is not None:
                    values.append(
                        (
                            f"potential_drivers.{driver.driver_id}.{impact.period}.{name}",
                            value,
                        )
                    )
    for name in (
        "target_pe",
        "target_ev_ebitda",
        "target_ev_ebit",
        "target_net_debt_pln_thousands",
        "cumulative_capital_allocation_pln_thousands",
        "wacc_pct",
        "terminal_growth_pct",
        "terminal_reinvestment_rate_pct",
        "terminal_incremental_roic_pct",
    ):
        value = getattr(scenario, name)
        if value is not None:
            values.append((name, value))
    if scenario.event_impact:
        values.extend(
            (
                ("event_impact.pnl_net_pln_thousands", scenario.event_impact.pnl_net_pln_thousands),
                ("event_impact.cash_pln_thousands", scenario.event_impact.cash_pln_thousands),
            )
        )
    return values


def validate_assumption_bindings(assumptions: list, manifest: dict) -> None:
    """Validate both lineage membership and the economic meaning of cited facts."""
    bindable = set(manifest.get("bindable_fact_ids") or manifest.get("fact_ids") or [])
    catalog = manifest.get("fact_catalog") or {}
    claim_catalog = manifest.get("research_claim_catalog") or {}
    referenced = {
        fact_id
        for scenario in assumptions
        for _name, value in _scenario_assumption_values(scenario)
        for fact_id in value.source_fact_ids
    }
    outside = referenced - bindable
    if outside:
        raise ValuationInputError(
            f"Assumption evidence facts are outside the research manifest: {sorted(outside)}.",
            kind="conflict",
        )
    for scenario in assumptions:
        for name, value in _scenario_assumption_values(scenario):
            missing_claims = set(value.research_claim_paths) - set(claim_catalog)
            if missing_claims:
                raise ValuationInputError(
                    f"Assumption research claims are outside the frozen snapshot: {sorted(missing_claims)}.",
                    kind="conflict",
                )
            malformed_claims = [
                path
                for path in value.research_claim_paths
                if not (claim_catalog.get(path) or {}).get("text")
                or (
                    (claim_catalog.get(path) or {}).get("kind") in {"fact", "lead"}
                    and not (claim_catalog.get(path) or {}).get("source_version_ids")
                )
            ]
            if malformed_claims:
                raise ValuationInputError(
                    "Assumption research claims lost their frozen text/source lineage: "
                    f"{sorted(malformed_claims)}.",
                    kind="conflict",
                )
            fact_keys = {
                (catalog.get(str(fact_id)) or {}).get("fact_key")
                for fact_id in value.source_fact_ids
            }
            if value.basis == "street_estimate":
                semantic_metric = next(
                    (
                        metric
                        for field, metric in (
                            ("revenue_pln_thousands", "revenue"),
                            ("ebitda_margin_pct", "ebitda_margin_pct"),
                            ("depreciation_pct_revenue", "depreciation"),
                            ("capex_pct_revenue", "capex"),
                        )
                        if field in name
                    ),
                    None,
                )
                permitted_prefix = (
                    f"consensus.{semantic_metric}." if semantic_metric else None
                )
                if permitted_prefix is None or not fact_keys or not all(
                    key and key.startswith(permitted_prefix) for key in fact_keys
                ):
                    raise ValuationInputError(
                        f"Street assumption {name} is not bound to a semantically matching consensus fact.",
                        kind="conflict",
                    )
            if name == "target_pe" and MARKET_IMPLIED_FORWARD_PE_KEY in fact_keys:
                raise ValuationInputError(
                    "Market-implied forward P/E is trading context and cannot anchor target P/E.",
                    kind="conflict",
                )
            if name == "target_pe" and value.basis == "street_estimate":
                raise ValuationInputError(
                    "A Street forecast P/E is not an analyst target multiple.",
                    kind="conflict",
                )


def prepare_valuation_base(
    db: Session, *, case: ResearchCase, research_snapshot_id: int, as_of: datetime
) -> dict:
    """Frozen queue-time bundle: everything deterministic, no assumptions yet.

    `input_fingerprint` covers only this base; drafted assumptions live in the
    draft/artifact fingerprints (VISION V4 — the drafter owns them).
    """
    loaded = load_immutable_base(
        db, case=case, research_snapshot_id=research_snapshot_id, as_of=as_of
    )
    gaps = sorted(set(loaded["gaps"]))
    input_payload = {
        "research_snapshot_id": research_snapshot_id,
        "template": loaded["template"].to_dict(),
        "engine_version": ENGINE_VERSION,
        "as_of": as_of,
        "base_values": loaded["base_values"],
        "input_manifest": loaded["input_manifest"],
        "gaps": gaps,
    }
    return {
        **loaded,
        "gaps": gaps,
        "input_fingerprint": canonical_hash(input_payload),
    }


def compute_scenarios(base: dict, assumptions: list, methodology) -> dict:
    """Deterministic outputs + gaps + fingerprint for one assumption grid."""
    validate_assumption_bindings(assumptions, base["input_manifest"])
    outputs = calculate_valuation(base["base_values"], assumptions, methodology)
    calculation_gaps = [
        f"{row['kind']}: {row['valuation_gap']}"
        for row in outputs["scenarios"]
        if row.get("valuation_gap")
    ]
    return {
        "deterministic_outputs": outputs,
        "gaps": sorted(set(list(base["gaps"]) + calculation_gaps)),
        "calculation_fingerprint": canonical_hash(outputs),
    }


def prepare_valuation(db: Session, *, case: ResearchCase, request: ValuationRequestIn) -> dict:
    base = prepare_valuation_base(
        db,
        case=case,
        research_snapshot_id=request.research_snapshot_id,
        as_of=request.as_of,
    )
    computed = compute_scenarios(base, request.assumptions, request.methodology)
    return {**base, **computed}


def probability_weighted(outputs: dict, probabilities: list[dict]) -> dict:
    if not probabilities:
        return {
            "status": "unavailable",
            "price_pln": None,
            "return_pct": None,
            "gap": "Scenario probabilities are not calibrated; no weighted value is published.",
            "probability_posture": "uncalibrated",
        }
    by_kind = {row["kind"]: row for row in outputs["scenarios"]}
    if set(by_kind) != {row["kind"] for row in probabilities}:
        raise ValuationInputError("Final probabilities do not match deterministic scenarios.")
    unpriced = [
        row["kind"]
        for row in probabilities
        if row["probability_pct"] > 0
        and by_kind[row["kind"]].get("target_price_pln") is None
    ]
    if unpriced:
        return {
            "status": "unavailable",
            "price_pln": None,
            "return_pct": None,
            "gap": "Positive probability is assigned to unpriced scenario(s): " + ", ".join(unpriced) + ".",
        }
    weighted_price = round(
        sum(by_kind[row["kind"]]["target_price_pln"] * row["probability_pct"] / 100.0 for row in probabilities),
        2,
    )
    current = outputs.get("current_price_pln")
    weighted_return = (
        round((weighted_price / current - 1.0) * 100.0, 2) if current else None
    )
    return {"status": "calculated", "price_pln": weighted_price, "return_pct": weighted_return, "gap": None}


def derive_scenario_probabilities(probability_model, scenario_kinds: set[str]) -> list[dict]:
    """Compute leaf probabilities from an auditable conditional state tree."""
    if probability_model.posture == "uncalibrated":
        return []
    nodes = {row.node_id: row for row in probability_model.nodes}
    if len(nodes) != len(probability_model.nodes):
        raise ValuationInputError("Probability node IDs must be unique.")
    children: dict[str | None, list] = {}
    for row in probability_model.nodes:
        if row.parent_id is not None and row.parent_id not in nodes:
            raise ValuationInputError("Probability node parent is absent from the tree.")
        children.setdefault(row.parent_id, []).append(row)
    for parent_id, rows in children.items():
        total = sum(row.conditional_probability_pct for row in rows)
        if abs(total - 100.0) > 0.01:
            label = parent_id or "root"
            raise ValuationInputError(
                f"Conditional probabilities under {label} sum to {total}, not 100."
            )
    totals: dict[str, float] = {}
    rationales: dict[str, list[str]] = {}

    def visit(node, path_probability: float, ancestors: set[str]) -> None:
        if node.node_id in ancestors:
            raise ValuationInputError("Probability tree contains a cycle.")
        probability = path_probability * node.conditional_probability_pct / 100.0
        node_children = children.get(node.node_id, [])
        if node_children:
            if node.scenario_kind is not None:
                raise ValuationInputError("Only probability-tree leaves may map to scenarios.")
            for child in node_children:
                visit(child, probability, {*ancestors, node.node_id})
            return
        if node.scenario_kind is None:
            raise ValuationInputError("Every probability-tree leaf must map to a scenario.")
        totals[node.scenario_kind] = totals.get(node.scenario_kind, 0.0) + probability
        rationales.setdefault(node.scenario_kind, []).append(node.rationale)

    for root in children.get(None, []):
        visit(root, 100.0, set())
    if set(totals) != scenario_kinds:
        raise ValuationInputError("Probability leaves must cover every scenario exactly by kind.")
    result = [
        {
            "kind": kind,
            "probability_pct": round(totals[kind], 6),
            "rationale": " | ".join(rationales[kind]),
            "posture": probability_model.posture,
        }
        for kind in sorted(totals)
    ]
    if abs(sum(row["probability_pct"] for row in result) - 100.0) > 0.01:
        raise ValuationInputError("Derived scenario probabilities do not sum to 100.")
    return result
