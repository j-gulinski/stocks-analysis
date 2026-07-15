"""Immutable multi-page GPW factor batches for the one Workbench sieve."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    DocumentVersion,
    Fact,
    FetchLog,
    MarketFactorBatch,
    MarketFactorRow,
    ReportValue,
    SourceDocument,
)
from app.scrapers import biznesradar
from app.services import evidence
from app.services.refresh import _build_br_session, _get_page
from app.services.metrics import ONE_OFF_SHARE_LIMIT_PCT
from app.services.workbench_sieve import (
    CzHistoryPoint,
    SIEVE_ID,
    SIEVE_VERSION,
    SieveCandidate,
    SieveResult,
    evaluate_workbench_sieve,
)

MARKET_KEY = "__GPW__"
BATCH_PARSER_VERSION = "workbench-market-batch@6"
DISCOVERY_RESULT_LIMIT = 100
_MIN_INITIAL_UNIVERSE = 100
_MIN_FACTOR_PAGE_COVERAGE_RATIO = 0.70
_MAX_UNIVERSE_DROP_RATIO = 0.30
_MIN_TICKER_OVERLAP_RATIO = 0.70


@dataclass(frozen=True)
class MarketPageSpec:
    id: str
    label: str
    url: str
    parser_version: str
    parse: Callable[[str], Iterable]
    fields: tuple[str, ...]


def _factor_parser(header: str) -> Callable[[str], list[biznesradar.MarketFactorEntry]]:
    return lambda html: biznesradar.parse_market_factor_page(
        html, expected_header=header
    )


MARKET_PAGE_SPECS = (
    MarketPageSpec(
        id="rating",
        label="Rating kondycji",
        url=f"{biznesradar.BASE_URL}/spolki-rating/akcje_gpw",
        parser_version="br-market-rating@4",
        parse=biznesradar.parse_market_rating,
        fields=("altman_em_score", "piotroski_f_score"),
    ),
    MarketPageSpec(
        id="cz",
        label="Cena / zysk",
        url=f"{biznesradar.BASE_URL}/spolki-wskazniki-wartosci-rynkowej/akcje_gpw,0,CZ",
        parser_version="br-market-factor@1",
        parse=_factor_parser("cena / zysk"),
        fields=("current_pe", "valuation_vs_own_history"),
    ),
    MarketPageSpec(
        id="operating_margin",
        label="Marża operacyjna",
        url=f"{biznesradar.BASE_URL}/spolki-wskazniki-rentownosci/akcje_gpw,OPM",
        parser_version="br-market-factor@1",
        parse=_factor_parser("marża zysku operacyjnego"),
        fields=("operating_margin", "operating_margin_change"),
    ),
    MarketPageSpec(
        id="net_debt_ebitda",
        label="Dług netto / EBITDA",
        url=f"{biznesradar.BASE_URL}/spolki-wskazniki-zadluzenia/akcje_gpw,NetDebtEBITDA",
        parser_version="br-market-factor@1",
        parse=_factor_parser("netto / ebitda"),
        fields=("net_debt_ebitda",),
    ),
    MarketPageSpec(
        id="revenue",
        label="Przychody ze sprzedaży",
        url=f"{biznesradar.BASE_URL}/spolki-raporty-finansowe-rachunek-zyskow-i-strat/akcje_gpw,Q,IncomeRevenues",
        parser_version="br-market-factor@1",
        parse=_factor_parser("przychody ze sprzedaży"),
        fields=("revenue_growth",),
    ),
    MarketPageSpec(
        id="net_income",
        label="Zysk netto",
        url=f"{biznesradar.BASE_URL}/spolki-raporty-finansowe-rachunek-zyskow-i-strat/akcje_gpw,Q,IncomeNetProfit",
        parser_version="br-market-factor@1",
        parse=_factor_parser("zysk netto"),
        fields=("net_income_growth",),
    ),
    MarketPageSpec(
        id="equity",
        label="Kapitał własny",
        url=f"{biznesradar.BASE_URL}/spolki-raporty-finansowe-bilans/akcje_gpw,0,BalanceCapital",
        parser_version="br-market-factor@1",
        parse=_factor_parser("kapitał własny"),
        fields=("equity",),
    ),
)

_SPECS_BY_ID = {spec.id: spec for spec in MARKET_PAGE_SPECS}
_FACTOR_SOURCE = {
    field: spec.id for spec in MARKET_PAGE_SPECS for field in spec.fields
}


@dataclass(frozen=True)
class DiscoveryAdmission:
    batch: MarketFactorBatch
    candidate: SieveCandidate
    page_document_versions: dict[str, int]
    fingerprint: str


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _batch_fingerprint(
    page_document_versions: dict[str, int],
    normalization_source_document_versions: Iterable[int] = (),
) -> str:
    raw = json.dumps(
        {
            "sieve_id": SIEVE_ID,
            "sieve_version": SIEVE_VERSION,
            "parser_version": BATCH_PARSER_VERSION,
            "page_document_versions": page_document_versions,
            "normalization_source_document_versions": sorted(
                int(value) for value in normalization_source_document_versions
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _latest_batch(db: Session) -> MarketFactorBatch | None:
    return db.scalar(
        select(MarketFactorBatch)
        .where(MarketFactorBatch.parser_version == BATCH_PARSER_VERSION)
        .order_by(MarketFactorBatch.as_of.desc(), MarketFactorBatch.id.desc())
        .limit(1)
    )


def _latest_any_batch(db: Session) -> MarketFactorBatch | None:
    return db.scalar(
        select(MarketFactorBatch)
        .order_by(MarketFactorBatch.as_of.desc(), MarketFactorBatch.id.desc())
        .limit(1)
    )


def _has_current_manifest(batch: MarketFactorBatch) -> bool:
    """A handoff may name only the complete, current source contract."""
    try:
        manifest = {str(key): int(value) for key, value in batch.page_document_versions.items()}
    except (AttributeError, TypeError, ValueError):
        return False
    return (
        batch.parser_version == BATCH_PARSER_VERSION
        and set(manifest) == set(_SPECS_BY_ID)
        and len(set(manifest.values())) == len(MARKET_PAGE_SPECS)
    )


def stored_market_factor_batch(db: Session) -> MarketFactorBatch | None:
    """Read stored evidence only.  Discover GET must never fetch or write."""
    return _latest_batch(db)


def batch_rows(db: Session, batch: MarketFactorBatch) -> list[MarketFactorRow]:
    return list(
        db.scalars(
            select(MarketFactorRow)
            .where(MarketFactorRow.batch_id == batch.id)
            .order_by(MarketFactorRow.ticker)
        )
    )


def _prior_cz_by_ticker(
    db: Session, batch: MarketFactorBatch
) -> dict[str, list[CzHistoryPoint]]:
    """Frozen earlier batches are supplied to the pure evaluator as history."""
    prior_ids = list(
        db.scalars(
            select(MarketFactorBatch.id)
            .where(
                or_(
                    MarketFactorBatch.as_of < batch.as_of,
                    (MarketFactorBatch.as_of == batch.as_of)
                    & (MarketFactorBatch.id < batch.id),
                )
            )
            .order_by(MarketFactorBatch.as_of, MarketFactorBatch.id)
        )
    )
    if not prior_ids:
        return {}
    rows = db.execute(
        select(
            MarketFactorRow.ticker,
            MarketFactorRow.cz,
            MarketFactorBatch.id,
            MarketFactorBatch.page_document_versions,
            MarketFactorBatch.as_of,
        )
        .join(MarketFactorBatch, MarketFactorRow.batch_id == MarketFactorBatch.id)
        .where(MarketFactorRow.batch_id.in_(prior_ids), MarketFactorRow.cz.is_not(None))
        .order_by(MarketFactorRow.batch_id, MarketFactorRow.id)
    ).all()
    result: dict[str, list[CzHistoryPoint]] = {}
    for ticker, cz, history_batch_id, manifest, history_as_of in rows:
        result.setdefault(ticker, []).append(
            CzHistoryPoint(
                batch_id=history_batch_id,
                document_version_id=int(manifest["cz"]),
                value=float(cz),
                observed_at=_as_utc(history_as_of),
            )
        )
    return result


def evaluate_batch(db: Session, batch: MarketFactorBatch) -> SieveResult:
    return evaluate_workbench_sieve(
        batch_rows(db, batch),
        prior_cz_by_ticker=_prior_cz_by_ticker(db, batch),
        as_of=_as_utc(batch.as_of),
    )


def _versions_for_batch(
    db: Session, batch: MarketFactorBatch
) -> dict[str, tuple[DocumentVersion, SourceDocument]]:
    manifest = {key: int(value) for key, value in batch.page_document_versions.items()}
    if set(manifest) != set(_SPECS_BY_ID):
        raise biznesradar.ParseError("Market batch has an incomplete page manifest.")
    records = db.execute(
        select(DocumentVersion, SourceDocument)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(DocumentVersion.id.in_(manifest.values()))
    ).all()
    by_id = {version.id: (version, document) for version, document in records}
    if set(by_id) != set(manifest.values()):
        raise biznesradar.ParseError("Market batch references a missing source version.")
    return {page_id: by_id[version_id] for page_id, version_id in manifest.items()}


def batch_sources(db: Session, batch: MarketFactorBatch) -> list[dict]:
    """Per-page immutable provenance used by API output and Research origin."""
    versions = _versions_for_batch(db, batch)
    result: list[dict] = []
    for spec in MARKET_PAGE_SPECS:
        version, document = versions[spec.id]
        result.append(
            {
                "id": spec.id,
                "label": spec.label,
                "name": document.source_name,
                "url": version.effective_url,
                "document_version_id": version.id,
                "parser_version": version.parser_version,
                "as_of": _as_utc(version.fetched_at),
                "fields": list(spec.fields),
            }
        )
    return result


def factor_source_versions(db: Session, batch: MarketFactorBatch) -> dict[str, dict]:
    sources = {source["id"]: source for source in batch_sources(db, batch)}
    return {
        factor_id: sources[page_id]
        for factor_id, page_id in _FACTOR_SOURCE.items()
    }


def _source_coverage(rows: list[MarketFactorRow]) -> dict:
    total = len(rows)
    return {
        "universe_count": total,
        "page_set": [spec.id for spec in MARKET_PAGE_SPECS],
        "factor_coverage": {
            "altman_em_score": sum(row.altman_value is not None for row in rows),
            "piotroski_f_score": sum(row.piotroski_f is not None for row in rows),
            "equity": sum(row.equity_pln_thousands is not None for row in rows),
            "revenue_growth": sum(row.revenue_dyn_rr_pct is not None for row in rows),
            "net_income_growth": sum(row.net_income_dyn_rr_pct is not None for row in rows),
            "operating_margin": sum(row.op_margin_pct is not None for row in rows),
            "operating_margin_change": sum(
                row.op_margin_delta_pp is not None for row in rows
            ),
            "net_debt_ebitda": sum(row.net_debt_ebitda is not None for row in rows),
            "net_income": sum(row.net_income_ttm_pln_thousands is not None for row in rows),
            "turnover": sum(row.turnover_present is not None for row in rows),
            "current_pe": sum(row.cz is not None for row in rows),
            "valuation_vs_own_history": sum(row.cz is not None for row in rows),
            "net_cash_or_debt_trend": 0,
        },
    }


def _relative_change_to_absolute_delta(
    current: float | None, relative_change_pct: float | None
) -> float | None:
    """Convert a source r/r percent into the current-minus-prior point change."""
    if current is None or relative_change_pct is None:
        return None
    denominator = 1.0 + relative_change_pct / 100.0
    if abs(denominator) < 1e-12:
        return None
    return current - current / denominator


def _merge_rows(
    parsed: dict[str, list],
) -> list[MarketFactorRow]:
    rating_rows = parsed["rating"]
    if len(rating_rows) < _MIN_INITIAL_UNIVERSE:
        raise biznesradar.ParseError(
            f"Market-rating universe has only {len(rating_rows)} rows (minimum {_MIN_INITIAL_UNIVERSE})."
        )
    fragments = {
        key: {entry.ticker: entry for entry in entries}
        for key, entries in parsed.items()
        if key != "rating"
    }
    result: list[MarketFactorRow] = []
    for rating in rating_rows:
        cz = fragments["cz"].get(rating.ticker)
        margin = fragments["operating_margin"].get(rating.ticker)
        debt = fragments["net_debt_ebitda"].get(rating.ticker)
        revenue = fragments["revenue"].get(rating.ticker)
        net_income = fragments["net_income"].get(rating.ticker)
        equity = fragments["equity"].get(rating.ticker)
        result.append(
            MarketFactorRow(
                ticker=rating.ticker,
                br_slug=rating.br_slug,
                name=rating.name,
                report_period=rating.report_period,
                altman_grade=rating.rating,
                altman_value=rating.rating_value,
                piotroski_f=rating.piotroski_f_score,
                cz=cz.value if cz else None,
                cz_delta_rr_pct=cz.delta_rr_pct if cz else None,
                op_margin_pct=margin.value if margin else None,
                op_margin_delta_pp=(
                    _relative_change_to_absolute_delta(
                        margin.value, margin.delta_rr_pct
                    )
                    if margin
                    else None
                ),
                revenue_dyn_rr_pct=revenue.delta_rr_pct if revenue else None,
                net_income_dyn_rr_pct=(
                    net_income.delta_rr_pct if net_income else None
                ),
                net_debt_ebitda=debt.value if debt else None,
                # A7 needs point-in-time trailing income.  The available
                # market page is quarterly/annual presentation, not a frozen
                # four-quarter calculation, so no single-quarter loss is
                # promoted into this field or a hard exclusion.
                net_income_ttm_pln_thousands=None,
                equity_pln_thousands=equity.value if equity else None,
                turnover_present=None,
                extras={
                    "source_periods": {
                        key: fragment.report_period
                        for key, fragment in (
                            ("cz", cz),
                            ("operating_margin", margin),
                            ("net_debt_ebitda", debt),
                            ("revenue", revenue),
                            ("net_income", net_income),
                            ("equity", equity),
                        )
                        if fragment is not None
                    }
                },
            )
        )
    return result


def _quarter_index(period: str) -> int | None:
    if len(period) != 6 or period[4] != "Q" or not period[:4].isdigit():
        return None
    try:
        quarter = int(period[5])
    except ValueError:
        return None
    if quarter not in (1, 2, 3, 4):
        return None
    return int(period[:4]) * 4 + quarter - 1


def _quarter_period(index: int) -> str:
    return f"{index // 4}Q{index % 4 + 1}"


def _derive_discontinued_score_normalizations(
    row: MarketFactorRow,
    *,
    quarterly_values: dict[str, dict[str, dict]],
    market_cap: dict | None,
) -> list[dict]:
    """Replace result components distorted by a material discontinued result.

    This is deliberately strict: the bridge must contain explicit reported
    values.  An incomplete bridge makes the affected score component unknown;
    it is never imputed and the raw, distorted market-page number is not used.
    """
    current_period = row.extras.get("source_periods", {}).get("net_income")
    current_index = _quarter_index(str(current_period or ""))
    if current_index is None:
        return []
    current = quarterly_values.get(str(current_period), {})
    current_net = current.get("IncomeNetProfit")
    current_discontinued = current.get("IncomeDiscontinuedProfit")
    if current_net is None or current_discontinued is None:
        return []
    reported_net = float(current_net["value"])
    discontinued = float(current_discontinued["value"])
    if reported_net == 0.0:
        return []
    discontinued_share_pct = abs(discontinued) / abs(reported_net) * 100.0
    if discontinued_share_pct < ONE_OFF_SHARE_LIMIT_PCT:
        return []

    prior_period = _quarter_period(current_index - 4)
    prior = quarterly_values.get(prior_period, {})
    prior_net = prior.get("IncomeNetProfit")
    prior_discontinued = prior.get("IncomeDiscontinuedProfit")
    normalized_growth: float | None = None
    growth_records = [current_net, current_discontinued]
    if prior_net is not None and prior_discontinued is not None:
        growth_records.extend((prior_net, prior_discontinued))
        current_continuing = reported_net - discontinued
        prior_continuing = float(prior_net["value"]) - float(
            prior_discontinued["value"]
        )
        if prior_continuing > 0.0:
            normalized_growth = (
                current_continuing / prior_continuing - 1.0
            ) * 100.0

    trailing_records: list[dict] = []
    continuing_ttm = 0.0
    complete_trailing_bridge = True
    for index in range(current_index - 3, current_index + 1):
        period_values = quarterly_values.get(_quarter_period(index), {})
        net = period_values.get("IncomeNetProfit")
        discontinued_result = period_values.get("IncomeDiscontinuedProfit")
        if net is None or discontinued_result is None:
            complete_trailing_bridge = False
            break
        trailing_records.extend((net, discontinued_result))
        continuing_ttm += float(net["value"]) - float(discontinued_result["value"])
    normalized_pe: float | None = None
    pe_records = list(trailing_records)
    if market_cap is not None:
        pe_records.append(market_cap)
    if (
        complete_trailing_bridge
        and continuing_ttm > 0.0
        and market_cap is not None
        and float(market_cap["value"]) > 0.0
    ):
        normalized_pe = float(market_cap["value"]) / (continuing_ttm * 1000.0)

    def lineage(records: list[dict], key: str) -> list[int]:
        return sorted({int(record[key]) for record in records if record.get(key)})

    shared_reason = (
        f"Wynik działalności zaniechanej stanowi {discontinued_share_pct:.1f}% "
        f"raportowanego zysku netto {current_period} (próg "
        f"{ONE_OFF_SHARE_LIMIT_PCT:.0f}%). Surowa wartość z rankingu rynku "
        "nie jest używana; składnik policzono z działalności kontynuowanej."
    )
    return [
        {
            "component_id": "net_income_growth",
            "label": "Dynamika zysku działalności kontynuowanej r/r",
            "reported_value": row.net_income_dyn_rr_pct,
            "normalized_value": (
                round(normalized_growth, 4) if normalized_growth is not None else None
            ),
            "discontinued_share_pct": round(discontinued_share_pct, 4),
            "period": str(current_period),
            "reason": shared_reason,
            "source_fact_ids": lineage(growth_records, "fact_id"),
            "source_document_version_ids": lineage(
                growth_records, "source_version_id"
            ),
        },
        {
            "component_id": "current_pe",
            "label": "C/Z działalności kontynuowanej (niżej lepiej)",
            "reported_value": row.cz,
            "normalized_value": round(normalized_pe, 4) if normalized_pe is not None else None,
            "discontinued_share_pct": round(discontinued_share_pct, 4),
            "period": str(current_period),
            "reason": shared_reason,
            "source_fact_ids": lineage(pe_records, "fact_id"),
            "source_document_version_ids": lineage(
                pe_records, "source_version_id"
            ),
        },
    ]


def _attach_score_normalizations(
    db: Session, rows: list[MarketFactorRow], *, as_of: datetime
) -> tuple[int, ...]:
    """Freeze detailed-fact normalizations into each immutable market row."""
    tickers = {row.ticker for row in rows}
    quarterly_by_ticker: dict[str, dict[str, dict[str, dict]]] = {}
    report_records = db.execute(
        select(
            Company.ticker,
            ReportValue.period,
            ReportValue.field_code,
            ReportValue.value,
            Fact.id,
            Fact.source_version_id,
        )
        .join(Company, ReportValue.company_id == Company.id)
        .join(Fact, Fact.id == ReportValue.source_fact_id)
        .where(
            Company.ticker.in_(tickers),
            ReportValue.statement == "income",
            ReportValue.freq == "Q",
            ReportValue.field_code.in_(
                ("IncomeNetProfit", "IncomeDiscontinuedProfit")
            ),
            ReportValue.value.is_not(None),
            Fact.known_at <= as_of,
        )
        .order_by(Company.ticker, ReportValue.period, ReportValue.field_code)
    ).all()
    for ticker, period, field_code, value, fact_id, source_version_id in report_records:
        quarterly_by_ticker.setdefault(ticker, {}).setdefault(period, {})[
            field_code
        ] = {
            "value": float(value),
            "fact_id": fact_id,
            "source_version_id": source_version_id,
        }

    market_cap_by_ticker: dict[str, dict] = {}
    market_cap_records = db.execute(
        select(
            Fact.company_ticker,
            Fact.numeric_value,
            Fact.id,
            Fact.source_version_id,
        )
        .where(
            Fact.company_ticker.in_(tickers),
            Fact.fact_key == "company.market_cap",
            Fact.numeric_value.is_not(None),
            Fact.known_at <= as_of,
        )
        .order_by(Fact.company_ticker, Fact.known_at.desc(), Fact.id.desc())
    ).all()
    for ticker, value, fact_id, source_version_id in market_cap_records:
        market_cap_by_ticker.setdefault(
            ticker,
            {
                "value": float(value),
                "fact_id": fact_id,
                "source_version_id": source_version_id,
            },
        )

    source_version_ids: set[int] = set()
    for row in rows:
        normalizations = _derive_discontinued_score_normalizations(
            row,
            quarterly_values=quarterly_by_ticker.get(row.ticker, {}),
            market_cap=market_cap_by_ticker.get(row.ticker),
        )
        if not normalizations:
            continue
        row.extras = {**row.extras, "score_normalizations": normalizations}
        source_version_ids.update(
            version_id
            for item in normalizations
            for version_id in item["source_document_version_ids"]
        )
    return tuple(sorted(source_version_ids))


def _validate_market_universe(db: Session, parsed: dict[str, list]) -> None:
    """Reject a plausible-looking partial universe before it can become a batch."""
    rating_rows = parsed["rating"]
    if len(rating_rows) < _MIN_INITIAL_UNIVERSE:
        raise biznesradar.ParseError(
            "Market-rating universe has only "
            f"{len(rating_rows)} rows (minimum {_MIN_INITIAL_UNIVERSE})."
        )
    rating_tickers = {row.ticker for row in rating_rows}
    minimum_factor_coverage = int(len(rating_tickers) * _MIN_FACTOR_PAGE_COVERAGE_RATIO)
    for spec in MARKET_PAGE_SPECS:
        if spec.id == "rating":
            continue
        tickers = {row.ticker for row in parsed[spec.id]}
        overlap = len(rating_tickers.intersection(tickers))
        if len(tickers) < _MIN_INITIAL_UNIVERSE or overlap < minimum_factor_coverage:
            raise biznesradar.ParseError(
                f"Market source {spec.id} covers only {overlap}/{len(rating_tickers)} "
                f"rating tickers (minimum {minimum_factor_coverage})."
            )

    previous = _latest_any_batch(db)
    if previous is None:
        return
    previous_rows = batch_rows(db, previous)
    previous_tickers = {row.ticker for row in previous_rows}
    if len(previous_tickers) < _MIN_INITIAL_UNIVERSE:
        return
    minimum_count = int(len(previous_tickers) * (1 - _MAX_UNIVERSE_DROP_RATIO))
    if len(rating_tickers) < minimum_count:
        raise biznesradar.ParseError(
            "Market-rating universe dropped from "
            f"{len(previous_tickers)} to {len(rating_tickers)} rows (minimum {minimum_count})."
        )
    overlap = len(previous_tickers.intersection(rating_tickers))
    minimum_overlap = int(len(previous_tickers) * _MIN_TICKER_OVERLAP_RATIO)
    if overlap < minimum_overlap:
        raise biznesradar.ParseError(
            "Market-rating universe retains only "
            f"{overlap}/{len(previous_tickers)} prior tickers (minimum {minimum_overlap})."
        )


def _matching_batch(
    db: Session,
    page_document_versions: dict[str, int],
    normalization_source_document_versions: Iterable[int],
) -> MarketFactorBatch | None:
    # JSON equality is backend-specific; compare the small immutable manifest
    # in Python so SQLite and PostgreSQL share the exact idempotence rule.
    expected = {key: int(value) for key, value in page_document_versions.items()}
    expected_normalization_versions = sorted(
        int(value) for value in normalization_source_document_versions
    )
    for batch in db.scalars(select(MarketFactorBatch).order_by(MarketFactorBatch.id.desc())):
        manifest = {key: int(value) for key, value in batch.page_document_versions.items()}
        normalization_versions = sorted(
            int(value)
            for value in batch.coverage.get(
                "score_normalization_source_document_version_ids", []
            )
        )
        if (
            manifest == expected
            and normalization_versions == expected_normalization_versions
            and batch.parser_version == BATCH_PARSER_VERSION
        ):
            return batch
    return None


def refresh_market_factor_batch(db: Session, *, force: bool = True) -> MarketFactorBatch:
    """Fetch every declared source and publish a batch only when all parse.

    Failed/partial attempts are still retained through FetchLog/DocumentVersion,
    but cannot replace the last complete immutable batch.
    """
    parsed: dict[str, list] = {}
    manifest: dict[str, int] = {}
    fetched_at: list[datetime] = []
    br_session = _build_br_session({})
    for spec in MARKET_PAGE_SPECS:
        page = _get_page(db, spec.url, force, session=br_session)
        if page is None:
            raise biznesradar.ParseError(
                f"Market source {spec.id} was skipped without stored batch evidence."
            )
        recorded = evidence.record_market_document_version(
            db,
            market_key=MARKET_KEY,
            source_name="biznesradar",
            source_type="market_factor",
            scope_key=spec.id,
            requested_url=page.requested_url,
            effective_url=page.effective_url,
            content=page.content,
            text=page.text,
            response_status=page.status_code,
            mime_type=page.mime_type,
            parser_version=spec.parser_version,
            fetched_at=page.fetched_at,
        )
        page.fetch_log.document_version_id = recorded.version.id
        try:
            entries = list(spec.parse(recorded.version.raw_content))
        except Exception as exc:
            evidence.mark_parse_result(recorded.version, success=False, error=str(exc))
            db.commit()
            raise biznesradar.ParseError(f"{spec.id}: {exc}") from exc
        evidence.mark_parse_result(recorded.version, success=True)
        parsed[spec.id] = entries
        manifest[spec.id] = recorded.version.id
        fetched_at.append(_as_utc(recorded.version.fetched_at))

    # Raw page evidence and fetch logs remain inspectable even when the
    # cross-page universe guard below rejects this attempted batch.
    db.commit()
    _validate_market_universe(db, parsed)
    rows = _merge_rows(parsed)
    batch_as_of = max(fetched_at)
    normalization_source_versions = _attach_score_normalizations(
        db, rows, as_of=batch_as_of
    )
    existing = _matching_batch(db, manifest, normalization_source_versions)
    if existing is not None:
        db.commit()
        return existing
    batch = MarketFactorBatch(
        as_of=batch_as_of,
        page_document_versions=manifest,
        parser_version=BATCH_PARSER_VERSION,
        coverage={},
    )
    db.add(batch)
    db.flush()
    for row in rows:
        row.batch_id = batch.id
        db.add(row)
    coverage = _source_coverage(rows)
    coverage["score_normalized_company_count"] = sum(
        bool(row.extras.get("score_normalizations")) for row in rows
    )
    coverage["score_normalization_source_document_version_ids"] = list(
        normalization_source_versions
    )
    batch.coverage = coverage
    db.commit()
    return batch


def batch_freshness(db: Session, batch: MarketFactorBatch) -> dict:
    """Batch freshness is the oldest successful declared-page check."""
    urls = [spec.url for spec in MARKET_PAGE_SPECS]
    last_successes: list[datetime] = []
    manifest = {key: int(value) for key, value in batch.page_document_versions.items()}
    for spec in MARKET_PAGE_SPECS:
        fetched_at = db.scalar(
            select(FetchLog.fetched_at)
            .join(DocumentVersion, FetchLog.document_version_id == DocumentVersion.id)
            .where(
                FetchLog.url == spec.url,
                FetchLog.status == 200,
                FetchLog.document_version_id == manifest[spec.id],
                DocumentVersion.parse_status == "parsed",
            )
            .order_by(FetchLog.fetched_at.desc(), FetchLog.id.desc())
            .limit(1)
        )
        if fetched_at is not None:
            last_successes.append(_as_utc(fetched_at))
    last_check = min(last_successes) if len(last_successes) == len(urls) else _as_utc(batch.as_of)
    failed_fetch = db.execute(
        select(FetchLog.fetched_at, FetchLog.status)
        .where(FetchLog.url.in_(urls), or_(FetchLog.status.is_(None), FetchLog.status != 200))
        .order_by(FetchLog.fetched_at.desc(), FetchLog.id.desc())
        .limit(1)
    ).first()
    failed_parse = db.execute(
        select(DocumentVersion.fetched_at, DocumentVersion.parse_error)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            SourceDocument.company_ticker == MARKET_KEY,
            SourceDocument.source_type == "market_factor",
            SourceDocument.scope_key.in_([spec.id for spec in MARKET_PAGE_SPECS]),
            DocumentVersion.parse_status == "failed",
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    ).first()
    options: list[tuple[datetime, str]] = []
    if failed_fetch is not None:
        fetched, status = failed_fetch
        options.append((_as_utc(fetched), "Błąd sieci" if status is None else f"HTTP {status}"))
    if failed_parse is not None:
        fetched, error = failed_parse
        options.append((_as_utc(fetched), f"Nie rozpoznano źródła: {error or 'błąd parsera'}"))
    failed_at, failed_reason = max(
        options,
        default=(None, None),
        key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc),
    )
    return {
        "content_version_at": _as_utc(batch.as_of),
        "last_successful_source_check_at": last_check,
        "last_failed_refresh_at": failed_at,
        "last_failed_refresh_reason": failed_reason,
    }


def admit_discovery_candidate(
    db: Session,
    *,
    batch_id: int,
    ticker: str,
    sieve_id: str,
    sieve_version: str,
) -> DiscoveryAdmission:
    """Recompute a claimed Discover survivor from the stored immutable batch."""
    if sieve_id != SIEVE_ID or sieve_version != SIEVE_VERSION:
        raise ValueError("Discover handoff names an unsupported sieve version.")
    batch = db.get(MarketFactorBatch, batch_id)
    if batch is None:
        raise LookupError("Discover batch no longer exists.")
    if not _has_current_manifest(batch):
        raise PermissionError(
            "Discover batch is not a complete batch for the current sieve source contract."
        )
    result = evaluate_batch(db, batch)
    candidate = next(
        (
            item
            for item in result.candidates[:DISCOVERY_RESULT_LIMIT]
            if item.ticker == ticker
        ),
        None,
    )
    if candidate is None:
        raise PermissionError(
            "Ticker is not in the surfaced top Discover results for the claimed batch."
        )
    manifest = {key: int(value) for key, value in batch.page_document_versions.items()}
    return DiscoveryAdmission(
        batch=batch,
        candidate=candidate,
        page_document_versions=manifest,
        fingerprint=_batch_fingerprint(
            manifest,
            batch.coverage.get(
                "score_normalization_source_document_version_ids", []
            ),
        ),
    )
