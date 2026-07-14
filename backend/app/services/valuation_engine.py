"""Point-in-time valuation inputs and pure scenario equations for P3."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ValuationRequestIn
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
from app.services import fields, metrics
from app.services.valuation_templates import get_template

ENGINE_VERSION = "valuation-engine-v2"
TEMPLATE_CONTRACT_VERSION = "valuation-templates-v1"
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
ASSUMPTION_VALUE_FIELDS = (
    "quarter_revenue_growth_pct", "year_revenue_growth_pct", "gross_margin_pct",
    "operating_cost_ratio_pct", "financial_result_ratio_pct", "tax_rate_pct",
    "cash_conversion_pct", "capex_spend_ratio_pct", "target_pe",
    "event_one_off_net_pln_thousands",
)


class ValuationInputError(ValueError):
    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


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
    }
    provenance = {
        "kind": "company_scalar_freeze",
        "updated_at": company.updated_at.isoformat(),
        "fields": ["shares_outstanding", "market_cap"],
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
    shares_value = float(shares_fact.numeric_value)
    market_cap_value = float(market_cap_fact.numeric_value)
    if shares_fact.unit != "shares" or not shares_value.is_integer() or shares_value <= 0:
        raise ValuationInputError(
            "Immutable share-count fact must be a positive whole number of shares.",
            kind="conflict",
        )
    if market_cap_fact.unit != "PLN" or market_cap_value <= 0:
        raise ValuationInputError(
            "Immutable market-cap fact must be positive PLN.", kind="conflict"
        )
    values = {
        "shares_outstanding": int(shares_value),
        "market_cap_pln": market_cap_value,
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
            gaps.append(
                "Raw price differs from reported market cap / shares by more than 2%."
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
    elif difference_pct > 2:
        reference_price_status = "market_cap_mismatch"
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


def load_immutable_base(
    db: Session, *, case: ResearchCase, research_snapshot_id: int, as_of: datetime
) -> dict:
    snapshot = db.get(ResearchSnapshot, research_snapshot_id)
    if snapshot is None or snapshot.research_case_id != case.id:
        raise ValuationInputError("Research snapshot does not belong to the case.", kind="not-found")
    if snapshot.status not in {"provisional", "verified"}:
        raise ValuationInputError("Valuation requires a usable research snapshot.", kind="conflict")
    if _aware(as_of) < _aware(snapshot.as_of):
        raise ValuationInputError("Valuation as_of cannot precede research as_of.", kind="conflict")
    company = db.get(Company, case.company_id)
    profile = db.get(CompanyProfile, snapshot.company_profile_id)
    if company is None or profile is None:
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
    version_times = dict(
        db.execute(
            select(DocumentVersion.id, DocumentVersion.fetched_at).where(
                DocumentVersion.id.in_(version_ids)
            )
        ).all()
    )
    resolved_facts = _resolve_manifest_facts(valuation_facts, version_times)
    base_financials, used_fact_ids, gaps = _financial_base(resolved_facts)
    used_fact_ids = sorted(set(used_fact_ids))
    scalar_values, scalar_provenance, scalar_gaps = _company_scalar_base(
        db, company, as_of
    )
    gaps.extend(scalar_gaps)
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
            "updated_at": company.updated_at.isoformat(),
            "scalar_known_at": scalar_provenance.get("known_at"),
        },
        "price": price,
    }
    if not scalar_values["shares_outstanding"] or scalar_values["shares_outstanding"] <= 0:
        raise ValuationInputError("A positive share count is required.", kind="conflict")
    manifest = {
        "research_snapshot_id": snapshot.id,
        "research_snapshot_status": snapshot.status,
        "research_artifact_fingerprint": snapshot.artifact_fingerprint,
        "document_version_ids": version_ids,
        "fact_ids": used_fact_ids,
        "bindable_fact_ids": sorted(available_fact_ids),
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


def _projection(revenue: float, scenario, *, year: bool, shares: int) -> dict:
    growth = (
        scenario.year_revenue_growth_pct.value
        if year
        else scenario.quarter_revenue_growth_pct.value
    )
    projected_revenue = revenue * (1.0 + growth / 100.0)
    gross_profit = projected_revenue * scenario.gross_margin_pct.value / 100.0
    operating_costs = projected_revenue * scenario.operating_cost_ratio_pct.value / 100.0
    ebit = gross_profit - operating_costs
    financial_result = projected_revenue * scenario.financial_result_ratio_pct.value / 100.0
    pretax = ebit + financial_result
    tax = max(pretax, 0.0) * scenario.tax_rate_pct.value / 100.0
    net = pretax - tax
    if scenario.kind == "event" and scenario.event_one_off_net_pln_thousands is not None:
        net += scenario.event_one_off_net_pln_thousands.value
    cfo = net * scenario.cash_conversion_pct.value / 100.0
    capex_spend = projected_revenue * scenario.capex_spend_ratio_pct.value / 100.0
    fcf = cfo - capex_spend
    eps = net * 1000.0 / shares
    return {
        "revenue_pln_thousands": round(projected_revenue, 2),
        "gross_profit_pln_thousands": round(gross_profit, 2),
        "ebit_pln_thousands": round(ebit, 2),
        "financial_result_pln_thousands": round(financial_result, 2),
        "pretax_result_pln_thousands": round(pretax, 2),
        "tax_pln_thousands": round(tax, 2),
        "net_result_pln_thousands": round(net, 2),
        "eps_pln": round(eps, 4),
        "cfo_pln_thousands": round(cfo, 2),
        "capex_spend_pln_thousands": round(capex_spend, 2),
        "fcf_pln_thousands": round(fcf, 2),
    }


def calculate_valuation(base_values: dict, assumptions: list) -> dict:
    shares = int(base_values["company"]["shares_outstanding"])
    current_price = float(base_values["price"]["close_pln"])
    rows = []
    for scenario in assumptions:
        quarter = _projection(
            float(base_values["latest_quarter_revenue_pln_thousands"]),
            scenario,
            year=False,
            shares=shares,
        )
        year = _projection(
            float(base_values["forward_12m_revenue_base_pln_thousands"]),
            scenario,
            year=True,
            shares=shares,
        )
        if year["eps_pln"] <= 0:
            target_price = None
            return_pct = None
            valuation_status = "unavailable"
            valuation_gap = "C/Z is undefined for non-positive forward EPS; no alternate v1 bridge is available."
        else:
            target_price = round(year["eps_pln"] * scenario.target_pe.value, 2)
            return_pct = round((target_price / current_price - 1.0) * 100.0, 2)
            valuation_status = "calculated"
            valuation_gap = None
        rows.append(
            {
                "kind": scenario.kind,
                "label": scenario.label,
                "quarter": quarter,
                "forward_12m": year,
                "target_pe": scenario.target_pe.value,
                "target_price_pln": target_price,
                "return_pct": return_pct,
                "valuation_status": valuation_status,
                "valuation_gap": valuation_gap,
            }
        )
    result = {
        "engine_version": ENGINE_VERSION,
        "current_price_pln": current_price,
        "scenarios": rows,
        "probability_weighted": None,
        "own_history_sensitivity": {
            "status": "unavailable",
            "note": "Own-history multiple reversion is a separate sensitivity and is not the operating scenario mechanism.",
        },
    }
    numeric = [
        value
        for row in rows
        for section in (row["quarter"], row["forward_12m"])
        for value in section.values()
    ] + [
        value
        for row in rows
        for value in (row["target_pe"], row["target_price_pln"], row["return_pct"])
        if value is not None
    ]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) for value in numeric):
        raise ValuationInputError("Deterministic valuation produced a non-finite value.")
    return result


def validate_assumption_bindings(assumptions: list, manifest: dict) -> None:
    """Every evidence-bound assumption must cite facts inside the frozen manifest."""
    bindable = set(manifest.get("bindable_fact_ids") or manifest.get("fact_ids") or [])
    referenced = {
        fact_id
        for scenario in assumptions
        for name in ASSUMPTION_VALUE_FIELDS
        for fact_id in (
            getattr(getattr(scenario, name), "source_fact_ids", [])
            if getattr(scenario, name, None) is not None
            else []
        )
    }
    outside = referenced - bindable
    if outside:
        raise ValuationInputError(
            f"Assumption evidence facts are outside the research manifest: {sorted(outside)}.",
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


def compute_scenarios(base: dict, assumptions: list) -> dict:
    """Deterministic outputs + gaps + fingerprint for one assumption grid."""
    validate_assumption_bindings(assumptions, base["input_manifest"])
    outputs = calculate_valuation(base["base_values"], assumptions)
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
    computed = compute_scenarios(base, request.assumptions)
    return {**base, **computed}


def probability_weighted(outputs: dict, probabilities: list[dict]) -> dict:
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
