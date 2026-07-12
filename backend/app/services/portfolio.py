"""Strict myfund normalization and deterministic portfolio analytics."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    CompanyProfile,
    InstrumentMapping,
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
    PortfolioValuePoint,
    Price,
    ResearchCase,
    ResearchSnapshot,
    ThesisFalsifier,
    ValuationSnapshot,
)

PARSER_VERSION = "myfund-portfolio-v1"
RISK_CONTEXT_VERSION = "portfolio-risk-context-v1"
RESEARCH_STALE_DAYS = 180


def _number(
    value: Any, *, required: bool = False, nonnegative: bool = False
) -> float | None:
    if value is None or value == "":
        if required:
            raise ValueError("missing required numeric value")
        return None
    if isinstance(value, str):
        value = (
            value.replace("\u00a0", "")
            .replace(" ", "")
            .replace(",", ".")
            .replace("%", "")
        )
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid numeric value") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError("numeric value outside accepted range")
    return result


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def _rows(value: Any) -> list[tuple[str, str, dict[str, Any]]]:
    if isinstance(value, dict):
        if any(not isinstance(row, dict) for row in value.values()):
            raise ValueError("provider instrument row is not an object")
        return [("native", str(key), row) for key, row in value.items()]
    if isinstance(value, list):
        if any(not isinstance(row, dict) for row in value):
            raise ValueError("provider instrument row is not an object")
        return [("list", "", row) for row in value]
    if value is None:
        return []
    raise ValueError("provider instrument collection is malformed")


def _identity_text(value: Any, *, upper: bool = False) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized.upper() if upper else normalized.casefold()


def _provider_key(source_kind: str, source_key: str, raw: dict[str, Any]) -> str:
    if source_kind == "native":
        native = str(source_key)
        direct = f"myfund:native:{native}"
        if len(direct) <= 190:
            return direct
        digest = hashlib.sha256(native.encode("utf-8")).hexdigest()
        return f"myfund:native-sha256:{digest}"
    identity = {
        "ticker": _identity_text(
            raw.get("tickerClear") or raw.get("ticker"), upper=True
        ),
        "name": _identity_text(raw.get("nazwa") or raw.get("name")),
        "asset_type": _identity_text(raw.get("typOrg") or raw.get("typ")),
        "currency": _identity_text(raw.get("waluta"), upper=True),
        "account": [
            _identity_text(raw.get(key))
            for key in (
                "kontoInvName",
                "portfelOrg",
                "konto",
                "account",
                "rachunek",
                "portfel",
                "accountId",
                "idKonta",
            )
        ],
    }
    canonical = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return f"myfund:canonical-sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _series(value: Any) -> tuple[dict[date, float], int, int]:
    result: dict[date, float] = {}
    if isinstance(value, dict):
        items = list(value.items())
    elif isinstance(value, list):
        items = list(enumerate(value))
    elif value is None:
        return result, 0, 0
    else:
        return result, 1, 1
    dropped = 0
    for key, raw in items:
        if isinstance(raw, dict):
            day = raw.get("data") or raw.get("date") or raw.get("dzien") or key
            number = raw.get(
                "wartosc", raw.get("value", raw.get("close", raw.get("stopaZwrotu")))
            )
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            day, number = raw[0], raw[1]
        else:
            day, number = key, raw
        try:
            parsed_day, parsed_number = _date(day), _number(number)
        except ValueError:
            dropped += 1
            continue
        if parsed_day is not None and parsed_number is not None:
            result[parsed_day] = parsed_number
        else:
            dropped += 1
    return result, dropped, len(items)


@dataclass(frozen=True)
class NormalizedPortfolio:
    summary: dict[str, Any]
    positions: list[dict[str, Any]]
    history: list[dict[str, Any]]
    gaps: list[str]
    fingerprint: str


def normalize_myfund(payload: Any) -> NormalizedPortfolio:
    if not isinstance(payload, dict):
        raise ValueError("provider response is not an object")
    status = payload.get("status")
    status_code = status.get("code") if isinstance(status, dict) else status
    if str(status_code) != "0":
        raise ValueError("provider rejected the portfolio request")
    raw_summary = payload.get("portfel")
    if not isinstance(raw_summary, dict):
        raise ValueError("provider response has no portfolio summary")
    total = _number(raw_summary.get("wartosc"), required=True, nonnegative=True)
    currency = str(raw_summary.get("waluta") or "PLN").strip().upper()
    profit = _number(raw_summary.get("zysk"))
    cost = total - profit if profit is not None else None
    summary = {
        "currency": currency,
        "total_value": total,
        "profit": profit,
        "cost_basis": cost,
        "benchmark_name": str(raw_summary.get("benchName") or "").strip() or None,
    }
    positions: list[dict[str, Any]] = []
    gaps: list[str] = []
    for source_kind, source_key, raw in _rows(payload.get("tickers")):
        ticker = str(raw.get("tickerClear") or raw.get("ticker") or "").strip()
        name = str(raw.get("nazwa") or ticker or "Nieznany instrument").strip()
        provider_key = _provider_key(source_kind, source_key, raw)
        value = _number(raw.get("wartosc"), required=True, nonnegative=True)
        row_profit = _number(raw.get("zysk"))
        row_cost = value - row_profit if row_profit is not None else None
        positions.append(
            {
                "provider_key": provider_key,
                "ticker": ticker or None,
                "name": name,
                "asset_type": str(raw.get("typOrg") or raw.get("typ") or "").strip()
                or None,
                "sector": str(raw.get("sektor") or "").strip() or None,
                "currency": str(raw.get("waluta") or currency).strip().upper(),
                "quote_date": _date(raw.get("data")),
                "quote": _number(raw.get("close")),
                "quantity": _number(raw.get("liczbaJednostek")),
                "value": value,
                "profit": row_profit,
                "cost_basis": row_cost,
                "allocation_pct": _number(raw.get("udzial")),
            }
        )
    positions.sort(
        key=lambda row: (
            row["provider_key"],
            json.dumps(row, ensure_ascii=False, sort_keys=True, default=str),
        )
    )
    seen: dict[str, int] = {}
    for row in positions:
        provider_key = row["provider_key"]
        seen[provider_key] = seen.get(provider_key, 0) + 1
        row["row_key"] = (
            provider_key
            if seen[provider_key] == 1
            else f"{provider_key}#{seen[provider_key]}"
        )
    if not positions and total > 0:
        gaps.append(
            "Dostawca zwrócił dodatnią wartość portfela bez pozycji składowych."
        )
    retained = sum(row["value"] for row in positions)
    if abs(retained - total) > max(0.02, total * 0.001):
        gaps.append(
            f"Suma pozycji różni się od wartości portfela o {round(retained-total, 2)} {currency}."
        )
    series: dict[str, dict[date, float]] = {}
    raw_series = {
        "value": payload.get("wartoscWCzasie"),
        "contributed": payload.get("wkladWCzasie"),
        "profit": payload.get("zyskWCzasie"),
        "provider_return_pct": payload.get("stopaZwrotuWCzasie"),
        "benchmark_return_pct": payload.get("benchWCzasie"),
        "daily_change": payload.get("zmianaDzienna"),
    }
    for name, raw in raw_series.items():
        parsed, dropped, point_count = _series(raw)
        series[name] = parsed
        if dropped:
            gaps.append(
                f"Historia {name}: pominięto {dropped} z {point_count} błędnych punktów."
            )
    days = sorted(set().union(*(values.keys() for values in series.values())))
    history = [
        {
            "date": day.isoformat(),
            **{key: values.get(day) for key, values in series.items()},
        }
        for day in days
    ]
    canonical = {
        "summary": summary,
        "positions": positions,
        "history": history,
        "gaps": gaps,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode()
    ).hexdigest()
    return NormalizedPortfolio(summary, positions, history, gaps, fingerprint)


def classify_mapping(
    db: Session, row: dict[str, Any]
) -> tuple[str, str, Company | None, str]:
    asset_type = _identity_text(row.get("asset_type"))
    if asset_type in {"gotówka", "gotowka", "cash"}:
        return "cash", "exact", None, "Provider identifies a cash instrument."
    ticker = str(row.get("ticker") or "").upper()
    company = (
        db.scalar(select(Company).where(Company.ticker == ticker)) if ticker else None
    )
    if company is not None and row.get("currency") == "PLN":
        return "company", "exact", company, "Exact stored GPW ticker and PLN currency."
    return "other", "unmatched", None, "No exact stored PLN company identity."


def portfolio_workspace(db: Session, snapshot: PortfolioSnapshot) -> dict[str, Any]:
    rows = db.scalars(
        select(PortfolioPositionSnapshot)
        .where(PortfolioPositionSnapshot.snapshot_id == snapshot.id)
        .order_by(PortfolioPositionSnapshot.value.desc())
    ).all()
    mappings = (
        {
            m.id: m
            for m in db.scalars(
                select(InstrumentMapping).where(
                    InstrumentMapping.id.in_([r.mapping_id for r in rows])
                )
            ).all()
        }
        if rows
        else {}
    )
    positions: list[dict[str, Any]] = []
    sectors: dict[str, float] = {}
    types: dict[str, float] = {}
    mapped_value = 0.0
    cash = 0.0
    for row in rows:
        mapping = mappings[row.mapping_id]
        value = float(row.value)
        if mapping.mapping_kind == "company":
            mapped_value += value
        if mapping.mapping_kind == "cash":
            cash += value
        sector = row.sector or "Nieokreślony"
        asset_type = row.asset_type or "Inne"
        sectors[sector] = sectors.get(sector, 0) + value
        types[asset_type] = types.get(asset_type, 0) + value
        positions.append(
            {
                "id": row.id,
                "mapping_id": mapping.id,
                "mapping_kind": mapping.mapping_kind,
                "mapping_status": mapping.mapping_status,
                "company_id": mapping.company_id,
                "ticker": row.ticker,
                "name": row.name,
                "asset_type": row.asset_type,
                "sector": row.sector,
                "currency": row.currency,
                "quote_date": row.quote_date,
                "quote": float(row.quote) if row.quote is not None else None,
                "quantity": float(row.quantity) if row.quantity is not None else None,
                "value": value,
                "cost_basis": (
                    float(row.cost_basis) if row.cost_basis is not None else None
                ),
                "profit": float(row.profit) if row.profit is not None else None,
                "allocation_pct": (
                    float(row.allocation_pct)
                    if row.allocation_pct is not None
                    else None
                ),
            }
        )
    total = float(snapshot.total_value)
    retained_value = sum(float(row.value) for row in rows)
    tolerance = max(0.02, total * 0.001)
    delta = retained_value - total
    reconciled = abs(delta) <= tolerance
    reconciliation = {
        "status": "reconciled" if reconciled else "unreconciled",
        "retained_value": round(retained_value, 2),
        "provider_total": round(total, 2),
        "delta": round(delta, 2),
        "tolerance": round(tolerance, 2),
    }
    weights = [float(r.value) / total for r in rows] if reconciled and total > 0 else []
    concentration = (
        {
            "top1_pct": round(max(weights, default=0) * 100, 2),
            "top3_pct": round(sum(sorted(weights, reverse=True)[:3]) * 100, 2),
            "hhi": round(sum(w * w for w in weights), 6),
            "sectors": _shares(sectors, total),
            "asset_types": _shares(types, total),
        }
        if reconciled
        else None
    )
    history = [
        {
            "date": p.date,
            "value": _float(p.value),
            "contributed": _float(p.contributed),
            "profit": _float(p.profit),
            "provider_return_pct": _float(p.provider_return_pct),
            "benchmark_return_pct": _float(p.benchmark_return_pct),
            "daily_change": _float(p.daily_change),
        }
        for p in db.scalars(
            select(PortfolioValuePoint)
            .where(PortfolioValuePoint.snapshot_id == snapshot.id)
            .order_by(PortfolioValuePoint.date)
        ).all()
    ]
    liquidity = _liquidity(db, snapshot, rows, mappings) if reconciled else []
    scenarios = (
        _scenario_sensitivity(db, snapshot, rows, mappings) if reconciled else None
    )
    risk_context = _risk_context(db, snapshot, rows, mappings) if reconciled else None
    history_gaps = [
        gap for gap in (snapshot.gaps or []) if str(gap).startswith("Historia ")
    ]
    return {
        "snapshot": {
            "id": snapshot.id,
            "version": snapshot.version,
            "as_of": snapshot.as_of,
            "currency": snapshot.currency,
            "total_value": total,
            "cost_basis": _float(snapshot.cost_basis),
            "profit": _float(snapshot.profit),
            "cash_value": _float(snapshot.cash_value),
            "benchmark_name": snapshot.benchmark_name,
            "gaps": snapshot.gaps,
        },
        "positions": positions,
        "reconciliation": reconciliation,
        "concentration": concentration,
        "history": history,
        "history_quality": {
            "status": "partial" if history_gaps else "complete",
            "gaps": history_gaps,
        },
        "liquidity": liquidity,
        "scenario_sensitivity": scenarios,
        "risk_context": risk_context,
        "performance_methods": {
            "provider_return": "provider-reported",
            "benchmark": "provider-reported; total-return basis unverified",
            "twr": "unavailable",
            "xirr": "unavailable",
            "gap": "Brak historii i semantyki przepływów zewnętrznych wymaganych do obliczeń.",
        },
        "coverage": {
            "mapped_company_value_pct": (
                round(mapped_value / total * 100, 2) if reconciled and total else None
            ),
            "unmapped_positions": sum(
                mappings[r.mapping_id].mapping_status == "unmatched" for r in rows
            ),
            "retained_position_value_pct": (
                round(retained_value / total * 100, 2) if reconciled and total else None
            ),
            "analytics_available": reconciled,
        },
    }


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _shares(groups: dict[str, float], total: float) -> list[dict[str, Any]]:
    return [
        {
            "label": key,
            "value": round(value, 2),
            "allocation_pct": round(value / total * 100, 2) if total else 0,
        }
        for key, value in sorted(groups.items(), key=lambda item: item[1], reverse=True)
    ]


def _liquidity(
    db: Session,
    snapshot: PortfolioSnapshot,
    rows: list,
    mappings: dict[int, InstrumentMapping],
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        mapping = mappings[row.mapping_id]
        if mapping.mapping_kind != "company" or mapping.company_id is None:
            continue
        prices = db.scalars(
            select(Price)
            .where(
                Price.company_id == mapping.company_id,
                Price.date <= snapshot.as_of.date(),
                Price.scraped_at.is_not(None),
                Price.scraped_at <= snapshot.as_of,
            )
            .order_by(Price.date.desc())
            .limit(20)
        ).all()
        traded = [
            float(p.close) * int(p.volume)
            for p in prices
            if p.volume is not None and float(p.close) > 0 and int(p.volume) >= 0
        ]
        if len(traded) < 20:
            result.append(
                {
                    "position_id": row.id,
                    "status": "unavailable",
                    "gap": "Mniej niż 20 sesji z ceną i wolumenem znanych w dacie snapshotu.",
                }
            )
            continue
        med = median(traded)
        days = float(row.value) / (med * 0.10) if med > 0 else None
        result.append(
            {
                "position_id": row.id,
                "status": "provisional",
                "median_20d_traded_value_pln": round(med, 2),
                "participation_pct": 10,
                "estimated_exit_days": round(days, 2) if days is not None else None,
                "series_status": prices[0].adjustment_status,
                "gap": "Surowa, niezweryfikowana seria ceny i wolumenu; to nie jest prognoza wykonania.",
            }
        )
    return result


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _driver_keys(profile: CompanyProfile | None) -> list[str]:
    keys: list[str] = []
    for driver in (profile.drivers if profile else []) or []:
        if isinstance(driver, dict):
            key = driver.get("key") or driver.get("id") or driver.get("name")
            if key:
                keys.append(str(key))
    return list(dict.fromkeys(keys))


def _risk_context(
    db: Session,
    snapshot: PortfolioSnapshot,
    rows: list[PortfolioPositionSnapshot],
    mappings: dict[int, InstrumentMapping],
) -> dict[str, Any]:
    companies: list[dict[str, Any]] = []
    company_rows = [
        row
        for row in rows
        if mappings[row.mapping_id].mapping_kind == "company"
        and mappings[row.mapping_id].company_id is not None
    ]
    for row in company_rows:
        mapping = mappings[row.mapping_id]
        company = db.get(Company, mapping.company_id)
        case = db.scalar(
            select(ResearchCase).where(
                ResearchCase.company_id == mapping.company_id,
                ResearchCase.purpose == "investment-research",
            )
        )
        research = (
            db.scalar(
                select(ResearchSnapshot)
                .where(
                    ResearchSnapshot.research_case_id == case.id,
                    ResearchSnapshot.as_of <= snapshot.as_of,
                )
                .order_by(
                    ResearchSnapshot.as_of.desc(), ResearchSnapshot.version.desc()
                )
                .limit(1)
            )
            if case
            else None
        )
        profile = (
            db.get(CompanyProfile, research.company_profile_id) if research else None
        )
        age_days = (
            max(0, (snapshot.as_of.date() - research.as_of.date()).days)
            if research
            else None
        )
        falsifiers = list(
            db.scalars(
                select(ThesisFalsifier)
                .where(ThesisFalsifier.company_id == mapping.company_id)
                .order_by(ThesisFalsifier.id)
            )
        )
        falsifier_rows = [
            {
                "id": item.id,
                "key": item.key,
                "statement": item.statement,
                "status": item.status,
                "reason": item.reason,
                "review_date": item.review_date,
                "thesis_hash": item.thesis_hash,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "known_by_snapshot": (
                    _aware(item.created_at) <= _aware(snapshot.as_of)
                    and _aware(item.updated_at) <= _aware(snapshot.as_of)
                ),
                "changed_after_snapshot": _aware(item.updated_at)
                > _aware(snapshot.as_of),
                "status_basis": "current-only-no-history",
            }
            for item in falsifiers
        ]
        for item in falsifier_rows:
            if item["known_by_snapshot"]:
                item["status_basis"] = "snapshot-known-current-row-no-history"
        snapshot_known_falsifiers = [
            item for item in falsifier_rows if item["known_by_snapshot"]
        ]
        current_only_falsifiers = [
            item for item in falsifier_rows if not item["known_by_snapshot"]
        ]
        snapshot_known_fired = [
            item for item in snapshot_known_falsifiers if item["status"] == "fired"
        ]
        current_only_fired = [
            item for item in current_only_falsifiers if item["status"] == "fired"
        ]
        companies.append(
            {
                "position_id": row.id,
                "company_id": mapping.company_id,
                "ticker": company.ticker if company else row.ticker,
                "value": float(row.value),
                "sector": row.sector or (company.sector if company else None),
                "sector_basis": (
                    "provider-position-at-snapshot"
                    if row.sector
                    else "current-only-company-metadata-no-history"
                ),
                "sector_known_by_snapshot": bool(row.sector),
                "company_metadata_updated_at": company.updated_at if company else None,
                "asset_type": row.asset_type,
                "research": {
                    "id": research.id if research else None,
                    "status": research.status if research else "missing",
                    "as_of": research.as_of if research else None,
                    "gaps": (
                        research.gaps
                        if research
                        else ["Brak punktowego snapshotu Research."]
                    ),
                    "age_days": age_days,
                    "stale": research is None or age_days > RESEARCH_STALE_DAYS,
                    "stale_threshold_days": RESEARCH_STALE_DAYS,
                    "freshness_version": RISK_CONTEXT_VERSION,
                },
                "profile": {
                    "id": profile.id if profile else None,
                    "archetype": profile.archetype if profile else None,
                    "archetype_version": profile.archetype_version if profile else None,
                    "driver_keys": _driver_keys(profile),
                },
                "falsifiers": falsifier_rows,
                "snapshot_known_falsifiers": snapshot_known_falsifiers,
                "current_only_falsifiers": current_only_falsifiers,
                "snapshot_known_fired_count": len(snapshot_known_fired),
                "snapshot_known_fired_falsifiers": snapshot_known_fired,
                "current_only_fired_count": len(current_only_fired),
                "current_only_fired_falsifiers": current_only_fired,
            }
        )
    groups: list[dict[str, Any]] = []
    for group_type, field in (("sector", "sector"), ("archetype", "archetype")):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for company in companies:
            label = company[field] if field == "sector" else company["profile"][field]
            if label:
                grouped.setdefault(str(label), []).append(company)
        for label, members in grouped.items():
            if len({member["company_id"] for member in members}) < 2:
                continue
            groups.append(
                {
                    "group_type": group_type,
                    "label": label,
                    "company_ids": [member["company_id"] for member in members],
                    "position_ids": [member["position_id"] for member in members],
                    "value": round(sum(member["value"] for member in members), 2),
                    "evidence_basis": [
                        {
                            "company_id": member["company_id"],
                            "sector_basis": member["sector_basis"],
                            "company_metadata_updated_at": member[
                                "company_metadata_updated_at"
                            ],
                            "research_snapshot_id": member["research"]["id"],
                            "profile_id": member["profile"]["id"],
                        }
                        for member in members
                    ],
                    "time_basis": (
                        "snapshot-known"
                        if group_type == "archetype"
                        or all(member["sector_known_by_snapshot"] for member in members)
                        else "includes-current-only"
                    ),
                    "interpretation": "evidence-labelled co-exposure only; not covariance or joint probability",
                }
            )
    context_times = [
        _aware(item["updated_at"])
        for company in companies
        for item in company["falsifiers"]
    ]
    context_times.extend(
        _aware(company["company_metadata_updated_at"])
        for company in companies
        if not company["sector_known_by_snapshot"]
        and company["company_metadata_updated_at"] is not None
    )
    return {
        "version": RISK_CONTEXT_VERSION,
        "snapshot_as_of": snapshot.as_of,
        "context_generated_at": max([_aware(snapshot.created_at), *context_times]),
        "research_stale_threshold_days": RESEARCH_STALE_DAYS,
        "companies": companies,
        "shared_groups": groups,
        "falsifier_status_basis": (
            "current rows without state history; split by whether created_at and updated_at were known by snapshot_as_of"
        ),
    }


def _scenario_sensitivity(
    db: Session,
    snapshot: PortfolioSnapshot,
    rows: list,
    mappings: dict[int, InstrumentMapping],
) -> dict[str, Any]:
    covered = []
    exclusions = []
    covered_value = 0.0
    totals = {"negative": 0.0, "base": 0.0, "positive": 0.0, "weighted": 0.0}
    unchanged = float(snapshot.total_value)
    for row in rows:
        mapping = mappings[row.mapping_id]
        if (
            mapping.mapping_kind != "company"
            or mapping.company_id is None
            or row.currency != "PLN"
            or row.quantity is None
        ):
            exclusions.append(
                {
                    "position_id": row.id,
                    "reason": "Brak dokładnego mapowania spółki, ilości lub waluty PLN.",
                }
            )
            continue
        case = db.scalar(
            select(ResearchCase).where(
                ResearchCase.company_id == mapping.company_id,
                ResearchCase.purpose == "investment-research",
            )
        )
        latest_research = (
            db.scalar(
                select(ResearchSnapshot)
                .where(
                    ResearchSnapshot.research_case_id == case.id,
                    ResearchSnapshot.as_of <= snapshot.as_of,
                )
                .order_by(ResearchSnapshot.version.desc())
                .limit(1)
            )
            if case
            else None
        )
        valuation = (
            db.scalar(
                select(ValuationSnapshot)
                .where(
                    ValuationSnapshot.research_case_id == case.id,
                    ValuationSnapshot.status == "verified",
                    ValuationSnapshot.as_of <= snapshot.as_of,
                )
                .order_by(ValuationSnapshot.version.desc())
                .limit(1)
            )
            if case
            else None
        )
        if (
            valuation is None
            or latest_research is None
            or valuation.research_snapshot_id != latest_research.id
        ):
            latest_any = (
                db.scalar(
                    select(ValuationSnapshot)
                    .where(
                        ValuationSnapshot.research_case_id == case.id,
                        ValuationSnapshot.as_of <= snapshot.as_of,
                    )
                    .order_by(ValuationSnapshot.version.desc())
                    .limit(1)
                )
                if case
                else None
            )
            exclusions.append(
                {
                    "position_id": row.id,
                    "reason": "Brak zweryfikowanej wyceny powiązanej z najnowszym Research.",
                    "latest_status": latest_any.status if latest_any else None,
                }
            )
            continue
        outputs = valuation.deterministic_outputs or {}
        by_kind = {
            s.get("kind"): s
            for s in outputs.get("scenarios", [])
            if isinstance(s, dict)
        }
        if not all(
            by_kind.get(kind, {}).get("target_price_pln") is not None
            for kind in ("negative", "base", "positive")
        ):
            exclusions.append(
                {
                    "position_id": row.id,
                    "reason": "Zweryfikowana wycena nie zawiera wszystkich cen scenariuszowych.",
                }
            )
            continue
        quantity = float(row.quantity)
        current = float(row.value)
        values = {
            kind: quantity * float(by_kind[kind]["target_price_pln"])
            for kind in ("negative", "base", "positive")
        }
        weighted = outputs.get("probability_weighted", {}).get("price_pln")
        if weighted is None:
            exclusions.append(
                {
                    "position_id": row.id,
                    "reason": "Zweryfikowana wycena nie zawiera ceny ważonej.",
                }
            )
            continue
        covered_value += current
        unchanged -= current
        for kind in values:
            totals[kind] += values[kind]
        totals["weighted"] += quantity * float(weighted)
        covered.append(
            {
                "position_id": row.id,
                "valuation_snapshot_id": valuation.id,
                "valuation_fingerprint": valuation.artifact_fingerprint,
                "current_value": current,
                **{f"{k}_value": round(v, 2) for k, v in values.items()},
                "weighted_value": round(quantity * float(weighted), 2),
            }
        )
    for key in totals:
        totals[key] = round(totals[key] + unchanged, 2)
    return {
        "label": "Aligned sensitivity, not a joint probability.",
        "coverage_value_pct": (
            round(covered_value / float(snapshot.total_value) * 100, 2)
            if snapshot.total_value
            else 0
        ),
        "portfolio_values": totals,
        "covered": covered,
        "exclusions": exclusions,
    }
