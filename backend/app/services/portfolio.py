"""Strict myfund normalization and deterministic portfolio analytics."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import median
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
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
from app.services.artifact_contracts import (
    RESEARCH_PROFILE_SCHEMA,
    canonical_research_snapshot_predicate,
    canonical_valuation_snapshot_predicate,
)
from app.services.portfolio_operations import (
    portfolio_operation_cost_basis,
    portfolio_operations_workspace,
)

PARSER_VERSION = "myfund-portfolio-v2"
RISK_CONTEXT_VERSION = "portfolio-risk-context-v1"
PERFORMANCE_METHOD_VERSION = "portfolio-performance-v1"
RESEARCH_STALE_DAYS = 30


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
        keys = [str(key) for key in value]
        # myfund serializes an array as an object with disposable 0..N-1 keys.
        # Those positions are not provider identities and can change on reorder.
        sequential = set(keys) == {str(index) for index in range(len(keys))}
        source_kind = "list" if sequential else "native"
        return [(source_kind, str(key), row) for key, row in value.items()]
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
        "name": _identity_text(
            raw.get("nazwa") or raw.get("name") or raw.get("ticker")
        ),
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


_GPW_ASSET_TYPE = "akcje gpw"
_TERMINAL_GPW_CODE = re.compile(r"\(([A-Z0-9]{1,12})\)\s*$")
_PARENTHETICAL_GPW_CODE = re.compile(r"\(([A-Z0-9]{1,12})\)")


def _gpw_marker_codes(
    provider_ticker: Any, provider_name: Any
) -> tuple[set[str], set[str]]:
    values = [str(provider_ticker or "").strip(), str(provider_name or "").strip()]
    all_codes = {
        match.group(1)
        for value in values
        for match in _PARENTHETICAL_GPW_CODE.finditer(value.upper())
    }
    terminal_codes = {
        match.group(1)
        for value in values
        if (match := _TERMINAL_GPW_CODE.search(value.upper())) is not None
    }
    return all_codes, terminal_codes


def provider_gpw_ticker(
    *,
    provider_ticker: Any,
    provider_name: Any,
    provider_type: Any,
    currency: Any,
) -> str | None:
    """Return one explicit terminal GPW code, never a display-name guess."""
    if _identity_text(provider_type) != _GPW_ASSET_TYPE:
        return None
    if _identity_text(currency, upper=True) != "PLN":
        return None
    all_codes, terminal = _gpw_marker_codes(provider_ticker, provider_name)
    if len(terminal) != 1 or all_codes != terminal:
        return None
    return next(iter(terminal))


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
    summary = {
        "currency": currency,
        "total_value": total,
        "profit": None,
        "cost_basis": None,
        "benchmark_name": str(raw_summary.get("benchName") or "").strip() or None,
    }
    positions: list[dict[str, Any]] = []
    gaps: list[str] = []
    for source_kind, source_key, raw in _rows(payload.get("tickers")):
        ticker = str(raw.get("tickerClear") or raw.get("ticker") or "").strip()
        name = str(
            raw.get("nazwa")
            or raw.get("name")
            or raw.get("ticker")
            or ticker
            or "Nieznany instrument"
        ).strip()
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
    if not positions and total == 0:
        summary["profit"] = 0.0
        summary["cost_basis"] = 0.0
    elif positions and all(row["profit"] is not None for row in positions):
        summary["profit"] = sum(row["profit"] for row in positions)
        summary["cost_basis"] = sum(row["cost_basis"] for row in positions)
    elif positions:
        gaps.append(
            "Bieżący koszt i wynik portfela są niedostępne: nie każda pozycja ma wynik dostawcy."
        )
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


def _company_display_name(value: Any, ticker: str | None = None) -> str:
    display = str(value or "").strip()
    if ticker:
        display = re.sub(
            rf"\s*\({re.escape(ticker)}\)\s*$", "", display, flags=re.IGNORECASE
        ).strip()
    return display or ticker or "Nieznana spółka"


def _normalized_company_name(value: Any) -> str:
    normalized = _identity_text(value).casefold()
    normalized = re.sub(r"\s*\([a-z0-9]{1,12}\)\s*$", "", normalized)
    normalized = normalized.translate(str.maketrans({"ł": "l"}))
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^0-9a-ząćęłńóśźż]+", " ", normalized).strip()
    normalized = re.sub(r"\s+(?:s\s*a|sa|spolka akcyjna)$", "", normalized)
    return normalized.strip()


def _minimal_gpw_company(db: Session, ticker: str, provider_name: Any) -> Company:
    company = db.scalar(
        select(Company).where(Company.ticker == ticker).with_for_update()
    )
    if company is None:
        try:
            with db.begin_nested():
                company = Company(
                    ticker=ticker,
                    name=_company_display_name(provider_name, ticker),
                    market="GPW",
                )
                db.add(company)
                db.flush()
        except IntegrityError:
            company = db.scalar(
                select(Company).where(Company.ticker == ticker).with_for_update()
            )
            if company is None:
                raise
    elif _identity_text(company.market, upper=True) in {"", "GPW"}:
        if company.market is None:
            company.market = "GPW"
        if not company.name:
            company.name = _company_display_name(provider_name, ticker)
    return company


def classify_mapping(
    db: Session, row: dict[str, Any]
) -> tuple[str, str, Company | None, str]:
    asset_type = _identity_text(row.get("asset_type"))
    if asset_type in {"gotówka", "gotowka", "cash", "konta gotówkowe"}:
        return "cash", "exact", None, "Dostawca oznaczył instrument jako gotówkę."
    if asset_type != _GPW_ASSET_TYPE or _identity_text(
        row.get("currency"), upper=True
    ) != "PLN":
        return "other", "unmatched", None, "To nie jest instrument Akcje GPW w PLN."
    all_codes, terminal_codes = _gpw_marker_codes(
        row.get("ticker"), row.get("name")
    )
    if len(terminal_codes) > 1 or (
        all_codes and (len(terminal_codes) != 1 or all_codes != terminal_codes)
    ):
        return "other", "unmatched", None, "Oznaczenia tickerów GPW są niejednoznaczne."
    ticker = provider_gpw_ticker(
        provider_ticker=row.get("ticker"),
        provider_name=row.get("name"),
        provider_type=row.get("asset_type"),
        currency=row.get("currency"),
    )
    if ticker:
        company = _minimal_gpw_company(db, ticker, row.get("name"))
        if _identity_text(company.market, upper=True) == "GPW":
            return (
                "company",
                "exact",
                company,
                "Jednoznaczny końcowy ticker GPW i waluta PLN.",
            )
        return (
            "other",
            "unmatched",
            None,
            "Ticker GPW koliduje z zapisanym rynkiem spółki.",
        )
    provider_name = _normalized_company_name(row.get("name"))
    candidates = [
        company
        for company in db.scalars(
            select(Company)
            .where(or_(Company.market == "GPW", Company.market.is_(None)))
            .order_by(Company.id)
            .with_for_update()
        )
        if provider_name and _normalized_company_name(company.name) == provider_name
    ]
    if len(candidates) == 1:
        if candidates[0].market is None:
            candidates[0].market = "GPW"
        return (
            "company",
            "exact",
            candidates[0],
            "Jednoznaczna znormalizowana nazwa zapisanej spółki GPW.",
        )
    if len(candidates) > 1:
        return "other", "unmatched", None, "Nazwa pasuje do więcej niż jednej spółki GPW."
    return "other", "unmatched", None, "Brak jednoznacznego tickera lub nazwy spółki GPW."


def resolve_instrument_mapping(
    db: Session, row: dict[str, Any], *, provider: str = "myfund"
) -> InstrumentMapping:
    """Create or refresh one current mapping without rewriting frozen positions."""
    mapping = db.scalar(
        select(InstrumentMapping).where(
            InstrumentMapping.provider == provider,
            InstrumentMapping.provider_key == row["provider_key"],
        ).with_for_update()
    )
    if mapping is None:
        try:
            with db.begin_nested():
                mapping = InstrumentMapping(
                    provider=provider,
                    provider_key=row["provider_key"],
                    provider_ticker=row.get("ticker"),
                    provider_name=row.get("name") or "Nieznany instrument",
                    provider_type=row.get("asset_type"),
                    currency=row.get("currency"),
                    mapping_kind="other",
                    mapping_status="unmatched",
                    company_id=None,
                    reason="Mapowanie oczekuje na rozstrzygnięcie.",
                )
                db.add(mapping)
                db.flush()
        except IntegrityError:
            mapping = db.scalar(
                select(InstrumentMapping)
                .where(
                    InstrumentMapping.provider == provider,
                    InstrumentMapping.provider_key == row["provider_key"],
                )
                .with_for_update()
            )
            if mapping is None:
                raise
    mapping.provider_ticker = row.get("ticker")
    mapping.provider_name = row.get("name") or "Nieznany instrument"
    mapping.provider_type = row.get("asset_type")
    mapping.currency = row.get("currency")
    if mapping.mapping_status == "ignored" or (
        mapping.mapping_status == "confirmed" and mapping.company_id is not None
    ):
        return mapping
    kind, status, company, reason = classify_mapping(db, row)
    mapping.mapping_kind = kind
    mapping.mapping_status = status
    mapping.company_id = company.id if company else None
    mapping.reason = reason
    mapping.confirmed_at = None
    return mapping


def apply_manual_instrument_mapping(
    db: Session,
    mapping: InstrumentMapping,
    *,
    company_ticker: str | None,
    ignored: bool,
    reason: str,
) -> InstrumentMapping:
    """Persist one explicit user override without guessing a new identity."""
    rationale = reason.strip()
    if len(rationale) < 3:
        raise ValueError("Uzasadnienie musi mieć co najmniej 3 znaki.")
    if mapping.mapping_kind == "cash":
        raise ValueError("Nie można zmienić jednoznacznej pozycji gotówkowej.")
    if ignored:
        mapping.mapping_kind = "ignored"
        mapping.mapping_status = "ignored"
        mapping.company_id = None
        mapping.reason = f"Ręcznie pominięto: {rationale}"
        mapping.confirmed_at = datetime.now(timezone.utc)
        return mapping
    if _identity_text(mapping.provider_type) != _GPW_ASSET_TYPE or _identity_text(
        mapping.currency, upper=True
    ) != "PLN":
        raise ValueError("Ręczne mapowanie spółki wymaga instrumentu Akcje GPW w PLN.")
    ticker = str(company_ticker or "").strip().upper()
    if not ticker:
        raise ValueError("Ręczne mapowanie wymaga tickera spółki.")
    company = db.scalar(
        select(Company).where(Company.ticker == ticker).with_for_update()
    )
    if company is None:
        provider_ticker = provider_gpw_ticker(
            provider_ticker=mapping.provider_ticker,
            provider_name=mapping.provider_name,
            provider_type=mapping.provider_type,
            currency=mapping.currency,
        )
        if provider_ticker != ticker:
            raise ValueError(
                "Wybrana spółka musi już istnieć albo odpowiadać jednemu "
                "końcowemu tickerowi GPW dostawcy."
            )
        company = _minimal_gpw_company(db, ticker, mapping.provider_name)
    if _identity_text(company.market, upper=True) not in {"", "GPW"}:
        raise ValueError("Wybrana spółka nie jest tożsamością GPW.")
    if company.market is None:
        company.market = "GPW"
    mapping.mapping_kind = "company"
    mapping.mapping_status = "confirmed"
    mapping.company_id = company.id
    mapping.reason = f"Ręczna korekta: {rationale}"
    mapping.confirmed_at = datetime.now(timezone.utc)
    return mapping


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
    company_ids = {
        mapping.company_id
        for mapping in mappings.values()
        if mapping.company_id is not None
    }
    company_tickers = (
        {
            company.id: company.ticker
            for company in db.scalars(
                select(Company).where(Company.id.in_(company_ids))
            ).all()
        }
        if company_ids
        else {}
    )
    positions: list[dict[str, Any]] = []
    operation_cost_basis = portfolio_operation_cost_basis(
        db, portfolio_id=snapshot.portfolio_id
    )
    sectors: dict[str, float] = {}
    types: dict[str, float] = {}
    mapped_value = 0.0
    cash = 0.0
    for row in rows:
        mapping = mappings[row.mapping_id]
        value = float(row.value)
        position_quantity = float(row.quantity) if row.quantity is not None else None
        ledger_ticker = company_tickers.get(mapping.company_id) or row.ticker
        ledger = (
            operation_cost_basis.get(ledger_ticker.strip().upper())
            if ledger_ticker
            else None
        )
        operation_basis_status = "missing"
        operation_basis_value = None
        operation_basis_gaps: list[str] = []
        if ledger is not None:
            operation_basis_gaps = list(ledger["gaps"])
            if ledger["status"] != "reconciled" or position_quantity is None:
                operation_basis_status = "unavailable"
            elif abs(float(ledger["quantity"]) - position_quantity) > 0.000001:
                operation_basis_status = "mismatch"
                operation_basis_gaps.append(
                    "Liczba jednostek z operacji nie zgadza się z bieżącą pozycją."
                )
            else:
                operation_basis_status = "reconciled"
                operation_basis_value = float(ledger["cost_basis"])
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
                "mapping_reason": mapping.reason,
                "company_id": mapping.company_id,
                "company_ticker": company_tickers.get(mapping.company_id),
                "ticker": row.ticker,
                "name": row.name,
                "asset_type": row.asset_type,
                "sector": row.sector,
                "currency": row.currency,
                "quote_date": row.quote_date,
                "quote": float(row.quote) if row.quote is not None else None,
                "quantity": position_quantity,
                "value": value,
                "cost_basis": (
                    float(row.cost_basis) if row.cost_basis is not None else None
                ),
                "profit": float(row.profit) if row.profit is not None else None,
                "operation_cost_basis": operation_basis_value,
                "operation_profit": (
                    round(value - operation_basis_value, 2)
                    if operation_basis_value is not None
                    else None
                ),
                "operation_cost_basis_status": operation_basis_status,
                "operation_cost_basis_gaps": list(dict.fromkeys(operation_basis_gaps)),
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
        "affected_figures": (
            []
            if reconciled
            else [
                "udziały liczone względem sumy zachowanych pozycji",
                "pokrycie względem sumy raportowanej przez dostawcę",
                "wartości scenariuszy obejmują tylko zachowane pozycje",
            ]
        ),
    }
    analytics_total = retained_value if retained_value > 0 else total
    weights = (
        [float(row.value) / analytics_total for row in rows]
        if analytics_total > 0
        else []
    )
    concentration = {
        "status": "complete" if reconciled else "partial",
        "basis": "provider_total" if reconciled else "retained_positions_total",
        "basis_value": round(analytics_total, 2),
        "top1_pct": round(max(weights, default=0) * 100, 2),
        "top3_pct": round(sum(sorted(weights, reverse=True)[:3]) * 100, 2),
        "hhi": round(sum(weight * weight for weight in weights), 6),
        "sectors": _shares(sectors, analytics_total),
        "asset_types": _shares(types, analytics_total),
    }
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
    liquidity = _liquidity(db, snapshot, rows, mappings)
    scenarios = _scenario_sensitivity(db, snapshot, rows, mappings)
    if scenarios is not None:
        scenarios["reconciliation_status"] = reconciliation["status"]
    risk_context = _risk_context(db, snapshot, rows, mappings)
    history_gaps = [
        gap for gap in (snapshot.gaps or []) if str(gap).startswith("Historia ")
    ]
    performance_methods = calculate_portfolio_performance(
        history,
        terminal_value=total,
        terminal_date=snapshot.as_of.date(),
    )
    operations = portfolio_operations_workspace(
        db, portfolio_id=snapshot.portfolio_id, history=history
    )
    performance_gaps = list(performance_methods["gaps"])
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
            "status": "partial" if history_gaps or performance_gaps else "complete",
            "gaps": list(dict.fromkeys(history_gaps + performance_gaps)),
        },
        "liquidity": liquidity,
        "scenario_sensitivity": scenarios,
        "risk_context": risk_context,
        "performance_methods": performance_methods,
        "operations": operations,
        "coverage": {
            "mapped_company_value_pct": (
                round(mapped_value / total * 100, 2) if total else None
            ),
            "unmapped_positions": sum(
                mappings[r.mapping_id].mapping_status == "unmatched" for r in rows
            ),
            "retained_position_value_pct": (
                round(retained_value / total * 100, 2) if total else None
            ),
            "analytics_available": bool(rows),
            "analytics_status": "complete" if reconciled else "partial",
        },
    }


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _performance_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _date(value)


def _scaled_exponential_value(
    terms: list[tuple[float, float]], log_one_plus_rate: float
) -> tuple[float, float]:
    """Return a scale-free exponential-sum value and absolute magnitude."""
    exponents = [-time * log_one_plus_rate for time, _ in terms]
    pivot = max(exponents)
    weighted = [
        amount * math.exp(exponent - pivot)
        for exponent, (_, amount) in zip(exponents, terms)
    ]
    return sum(weighted), sum(abs(item) for item in weighted)


def _exponential_sign(
    terms: list[tuple[float, float]], log_one_plus_rate: float
) -> int:
    value, magnitude = _scaled_exponential_value(terms, log_one_plus_rate)
    tolerance = max(1e-12 * magnitude, 1e-12)
    if abs(value) <= tolerance:
        return 0
    return 1 if value > 0.0 else -1


def _bisect_exponential_root(
    terms: list[tuple[float, float]], low: float, high: float
) -> float:
    low_sign = _exponential_sign(terms, low)
    for _ in range(160):
        middle = (low + high) / 2.0
        middle_sign = _exponential_sign(terms, middle)
        if middle_sign == 0 or high - low <= 1e-12:
            return middle
        if middle_sign == low_sign:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _limit_bracket(
    terms: list[tuple[float, float]],
    *,
    anchor: float,
    direction: int,
    limit_sign: int,
) -> float | None:
    step = 1.0
    for _ in range(32):
        point = anchor + direction * step
        sign = _exponential_sign(terms, point)
        if sign == limit_sign:
            return point
        if sign == 0:
            return None
        step *= 2.0
    return None


def _isolate_exponential_roots(
    terms: list[tuple[float, float]],
) -> tuple[list[float], bool]:
    """Isolate every real root using recursively proven monotonic intervals.

    Factoring the first exponential from the derivative reduces its term count
    by one. Its recursively isolated roots partition the current function into
    monotonic intervals, so every sign change identifies exactly one root.
    A stationary value numerically indistinguishable from zero is rejected as
    ambiguous instead of silently treating a repeated or clustered root as
    unique.
    """
    if len(terms) <= 1:
        return [], False
    derivative = [
        (time, -time * amount) for time, amount in terms[1:]
    ]
    first_time = derivative[0][0]
    normalized_derivative = [
        (time - first_time, amount) for time, amount in derivative
    ]
    critical_points, ambiguous = _isolate_exponential_roots(
        normalized_derivative
    )
    if ambiguous:
        return [], True
    critical_signs = [
        _exponential_sign(terms, point) for point in critical_points
    ]
    if any(sign == 0 for sign in critical_signs):
        return [], True

    left_limit_sign = 1 if terms[-1][1] > 0.0 else -1
    right_limit_sign = 1 if terms[0][1] > 0.0 else -1
    roots: list[float] = []
    if not critical_points:
        if left_limit_sign == right_limit_sign:
            return roots, False
        low = _limit_bracket(
            terms, anchor=0.0, direction=-1, limit_sign=left_limit_sign
        )
        high = _limit_bracket(
            terms, anchor=0.0, direction=1, limit_sign=right_limit_sign
        )
        if low is None or high is None:
            return [], True
        roots.append(_bisect_exponential_root(terms, low, high))
        return roots, False

    if left_limit_sign != critical_signs[0]:
        low = _limit_bracket(
            terms,
            anchor=critical_points[0],
            direction=-1,
            limit_sign=left_limit_sign,
        )
        if low is None:
            return [], True
        roots.append(
            _bisect_exponential_root(terms, low, critical_points[0])
        )
    for index in range(len(critical_points) - 1):
        if critical_signs[index] != critical_signs[index + 1]:
            roots.append(
                _bisect_exponential_root(
                    terms, critical_points[index], critical_points[index + 1]
                )
            )
    if critical_signs[-1] != right_limit_sign:
        high = _limit_bracket(
            terms,
            anchor=critical_points[-1],
            direction=1,
            limit_sign=right_limit_sign,
        )
        if high is None:
            return [], True
        roots.append(
            _bisect_exponential_root(terms, critical_points[-1], high)
        )
    return roots, False


def _solve_xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """Solve one unambiguous dated-flow IRR using actual days / 365.

    Recursive derivative roots partition log(1+r) space into proven monotonic
    intervals over the full valid domain ``r > -1``. Multiple or numerically
    ambiguous roots are rejected rather than choosing one silently.
    """
    compact = [(day, amount) for day, amount in cashflows if abs(amount) > 1e-9]
    if (
        len(compact) < 2
        or compact[0][0] == compact[-1][0]
        or not any(amount < 0 for _, amount in compact)
        or not any(amount > 0 for _, amount in compact)
    ):
        return None
    origin = compact[0][0]
    terms = [
        ((flow_date - origin).days / 365.0, amount)
        for flow_date, amount in compact
    ]
    roots, ambiguous = _isolate_exponential_roots(terms)
    if ambiguous or len(roots) != 1 or roots[0] > 700.0:
        return None
    return math.expm1(roots[0])


def calculate_portfolio_performance(
    history: list[dict[str, Any]],
    *,
    terminal_value: float,
    terminal_date: date,
) -> dict[str, Any]:
    """Compute canonical portfolio-level TWR and XIRR from retained history."""
    performance_history = [
        item
        for item in history
        if item.get("value") is not None or item.get("contributed") is not None
    ]
    result: dict[str, Any] = {
        "version": PERFORMANCE_METHOD_VERSION,
        "provider_return_basis": "provider-reported",
        "benchmark_basis": "provider-reported; total-return basis unverified",
        "twr_status": "unavailable",
        "twr_pct": None,
        "twr_method": "flow-adjusted daily compound",
        "xirr_status": "unavailable",
        "xirr_pct": None,
        "xirr_method": (
            "dated opening value + contribution changes + terminal value"
        ),
        "flow_timing": "end-of-day",
        "day_count": "actual/365",
        "window_start": None,
        "window_end": None,
        "terminal_date": terminal_date.isoformat(),
        "terminal_value": round(float(terminal_value), 2),
        "observation_count": len(performance_history),
        "external_flow_count": 0,
        "gaps": [],
    }
    if len(performance_history) < 2:
        result["gaps"].append(
            "TWR/XIRR wymagają co najmniej dwóch dziennych obserwacji wartości i wkładu."
        )
        return result

    rows: list[tuple[date, float, float]] = []
    for item in performance_history:
        try:
            day = _performance_date(item.get("date"))
        except ValueError:
            day = None
        value = item.get("value")
        contributed = item.get("contributed")
        if day is None or value is None or contributed is None:
            result["gaps"].append(
                "Historia wartości/wkładu ma brakujący dzień lub wartość; szeregu nie wygładzono."
            )
            return result
        value_number = float(value)
        contribution_number = float(contributed)
        if (
            not math.isfinite(value_number)
            or not math.isfinite(contribution_number)
            or value_number < 0.0
        ):
            result["gaps"].append(
                "Historia wartości/wkładu zawiera liczbę poza dozwolonym zakresem."
            )
            return result
        rows.append((day, value_number, contribution_number))
    if any(current[0] <= previous[0] for previous, current in zip(rows, rows[1:])):
        result["gaps"].append(
            "Daty historii wartości/wkładu nie są ściśle rosnące."
        )
        return result
    if any(
        (current[0] - previous[0]).days != 1
        for previous, current in zip(rows, rows[1:])
    ):
        result["gaps"].append(
            "Historia wartości/wkładu nie jest ciągłą serią dzienną; brakujących dni nie wygładzono."
        )
        return result

    result["window_start"] = rows[0][0].isoformat()
    result["window_end"] = rows[-1][0].isoformat()
    twr_factor = 1.0
    twr_valid = True
    external_flows: list[tuple[date, float]] = [(rows[0][0], -rows[0][1])]
    flow_count = 0
    for previous, current in zip(rows, rows[1:]):
        previous_value = previous[1]
        contribution_change = current[2] - previous[2]
        if abs(contribution_change) > 1e-9:
            external_flows.append((current[0], -contribution_change))
            flow_count += 1
        if previous_value <= 0.0:
            twr_valid = False
            continue
        period_factor = (current[1] - contribution_change) / previous_value
        if period_factor < 0.0 or not math.isfinite(period_factor):
            twr_valid = False
        elif twr_valid:
            twr_factor *= period_factor
    result["external_flow_count"] = flow_count
    if twr_valid:
        result["twr_status"] = "complete"
        result["twr_pct"] = round((twr_factor - 1.0) * 100.0, 6)
    else:
        result["gaps"].append(
            "TWR jest niedostępny: poprzednia wartość była niedodatnia albo przepływ przekroczył wartość okresu."
        )

    parsed_terminal_date = _performance_date(terminal_date)
    if parsed_terminal_date is None or rows[-1][0] != parsed_terminal_date:
        if result["twr_status"] == "complete":
            result["twr_status"] = "partial"
        result["gaps"].append(
            "XIRR jest niedostępny: dzienna historia nie dochodzi do daty bieżącej wartości portfela."
        )
    elif abs(rows[-1][1] - terminal_value) > 0.02:
        if result["twr_status"] == "complete":
            result["twr_status"] = "partial"
        result["gaps"].append(
            "XIRR jest niedostępny: końcowa wartość historii nie zgadza się z bieżącą wartością portfela."
        )
    else:
        external_flows.append((rows[-1][0], terminal_value))
        by_day: dict[date, float] = {}
        for day, amount in external_flows:
            by_day[day] = by_day.get(day, 0.0) + amount
        xirr = _solve_xirr(sorted(by_day.items()))
        if xirr is None:
            result["gaps"].append(
                "XIRR jest niedostępny: przepływy nie mają jednego rozwiązania w dozwolonej dziedzinie."
            )
        else:
            result["xirr_status"] = "complete"
            result["xirr_pct"] = round(xirr * 100.0, 6)
    return result


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
                .join(
                    CompanyProfile,
                    ResearchSnapshot.company_profile_id == CompanyProfile.id,
                )
                .where(
                    ResearchSnapshot.research_case_id == case.id,
                    *canonical_research_snapshot_predicate(),
                    CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
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
    totals = {"negative": 0.0, "base": 0.0, "positive": 0.0}
    weighted_total = 0.0
    weighted_complete = True
    weighted_covered_value = 0.0
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
                .join(
                    CompanyProfile,
                    ResearchSnapshot.company_profile_id == CompanyProfile.id,
                )
                .where(
                    ResearchSnapshot.research_case_id == case.id,
                    *canonical_research_snapshot_predicate(),
                    CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
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
                    *canonical_valuation_snapshot_predicate(),
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
            or valuation.status != "verified"
            or latest_research is None
            or valuation.research_snapshot_id != latest_research.id
        ):
            exclusions.append(
                {
                    "position_id": row.id,
                    "reason": "Brak zweryfikowanej wyceny powiązanej z najnowszym Research.",
                    "latest_status": valuation.status if valuation else None,
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
        weighted = (outputs.get("probability_weighted") or {}).get("price_pln")
        covered_value += current
        unchanged -= current
        for kind in values:
            totals[kind] += values[kind]
        weighted_value = quantity * float(weighted) if weighted is not None else None
        if weighted_value is None:
            weighted_complete = False
        else:
            weighted_total += weighted_value
            weighted_covered_value += current
        covered.append(
            {
                "position_id": row.id,
                "valuation_snapshot_id": valuation.id,
                "valuation_fingerprint": valuation.artifact_fingerprint,
                "current_value": current,
                **{f"{k}_value": round(v, 2) for k, v in values.items()},
                "weighted_value": (
                    round(weighted_value, 2) if weighted_value is not None else None
                ),
            }
        )
    for key in totals:
        totals[key] = round(totals[key] + unchanged, 2)
    portfolio_values = {
        **totals,
        "weighted": (
            round(weighted_total + unchanged, 2)
            if covered and weighted_complete
            else None
        ),
    }
    return {
        "label": "Aligned sensitivity, not a joint probability.",
        "coverage_value_pct": (
            round(covered_value / float(snapshot.total_value) * 100, 2)
            if snapshot.total_value
            else 0
        ),
        "weighted_coverage_value_pct": (
            round(weighted_covered_value / float(snapshot.total_value) * 100, 2)
            if snapshot.total_value
            else 0
        ),
        "portfolio_values": portfolio_values,
        "covered": covered,
        "exclusions": exclusions,
    }
