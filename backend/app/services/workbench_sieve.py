"""Pure, exclusion-first evaluator for the one Workbench market sieve."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import re
from statistics import median
from typing import Iterable, Mapping, Protocol


SIEVE_ID = "workbench_sieve_v1"
SIEVE_VERSION = "workbench-sieve-v1"


class FactorRow(Protocol):
    ticker: str
    name: str | None
    report_period: str | None
    altman_value: float | None
    piotroski_f: float | None
    cz: float | None
    cz_delta_rr_pct: float | None
    op_margin_pct: float | None
    op_margin_delta_pp: float | None
    revenue_dyn_rr_pct: float | None
    net_income_dyn_rr_pct: float | None
    net_debt_ebitda: float | None
    net_income_ttm_pln_thousands: float | None
    equity_pln_thousands: float | None
    turnover_present: bool | None


@dataclass(frozen=True)
class CzHistoryPoint:
    """One immutable C/Z input used by B4's own-history comparison."""

    batch_id: int | None
    document_version_id: int | None
    value: float
    observed_at: datetime | None = None


@dataclass(frozen=True)
class SieveFactor:
    id: str
    label: str
    note: str | None
    value: float | None
    delta: float | None
    period: str | None
    history_median: float | None = None
    history_batch_ids: tuple[int, ...] = ()
    history_document_version_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class SieveScoreComponent:
    id: str
    label: str
    raw_value: float
    ranking_value: float
    percentile: float
    weight: float


@dataclass(frozen=True)
class SieveScoreNormalization:
    """One source-bound replacement of a distorted market-page component."""

    component_id: str
    label: str
    reported_value: float | None
    normalized_value: float | None
    discontinued_share_pct: float
    period: str
    reason: str
    source_fact_ids: tuple[int, ...]
    source_document_version_ids: tuple[int, ...]


@dataclass(frozen=True)
class SieveCandidate:
    ticker: str
    name: str | None
    rank: int | None
    rank_basis: tuple[str, ...]
    factors: tuple[SieveFactor, ...]
    factor_gaps: tuple[str, ...]
    improvement_signals: tuple[str, ...]
    potential_score: float | None
    score_components: tuple[SieveScoreComponent, ...]
    score_normalizations: tuple[SieveScoreNormalization, ...] = ()

    def frozen_evidence(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "rank": self.rank,
            "rank_basis": list(self.rank_basis),
            "improvement_signals": list(self.improvement_signals),
            "factor_gaps": list(self.factor_gaps),
            "factors": [asdict(factor) for factor in self.factors],
            "potential_score": self.potential_score,
            "score_components": [asdict(component) for component in self.score_components],
            "score_normalizations": [
                asdict(normalization) for normalization in self.score_normalizations
            ],
        }


@dataclass(frozen=True)
class SieveExcluded:
    ticker: str
    name: str | None
    kill_reasons: tuple[str, ...]
    factors: tuple[SieveFactor, ...]
    factor_gaps: tuple[str, ...]
    score_normalizations: tuple[SieveScoreNormalization, ...] = ()


@dataclass(frozen=True)
class SieveResult:
    candidates: tuple[SieveCandidate, ...]
    excluded: tuple[SieveExcluded, ...]
    factor_coverage: Mapping[str, int]
    coverage_count: int


_FACTOR_LABELS = {
    "altman_em_score": "Altman EM-Score",
    "piotroski_f_score": "Piotroski F-Score",
    "equity": "Kapitał własny",
    "revenue_growth": "Dynamika przychodów r/r",
    "net_income_growth": "Dynamika zysku netto r/r",
    "operating_margin": "Marża operacyjna",
    "operating_margin_change": "Zmiana marży operacyjnej",
    "net_debt_ebitda": "Dług netto / EBITDA",
    "net_income": "Zysk netto TTM",
    "turnover": "Obrót w oknie snapshotu",
    "current_pe": "C/Z bieżące",
    "valuation_vs_own_history": "C/Z względem własnej historii",
    "net_cash_or_debt_trend": "Gotówka netto / trend długu",
}

SCORE_COMPONENT_IDS = (
    "revenue_growth",
    "net_income_growth",
    "operating_margin_change",
    "operating_margin",
    "current_pe",
)
SCORE_COMPONENT_COUNT = len(SCORE_COMPONENT_IDS)
_SCORE_LABELS = {
    "revenue_growth": "Dynamika przychodów r/r",
    "net_income_growth": "Dynamika zysku netto r/r",
    "operating_margin_change": "Zmiana marży operacyjnej",
    "operating_margin": "Rentowność operacyjna",
    "current_pe": "C/Z bieżące (niżej lepiej)",
}
_SCORE_BOUNDS = {
    # Extreme changes usually encode a tiny/negative base. Once the company
    # reaches the bound it ties with peers instead of winning for base effects.
    "revenue_growth": (-100.0, 100.0),
    "net_income_growth": (-100.0, 100.0),
    "operating_margin_change": (-20.0, 20.0),
    "operating_margin": (-20.0, 40.0),
    "current_pe": (0.0, 50.0),
}
_SCORE_DIRECTIONS = {component_id: 1.0 for component_id in SCORE_COMPONENT_IDS}
_SCORE_DIRECTIONS["current_pe"] = -1.0
_SCORE_WEIGHT = 1.0 / SCORE_COMPONENT_COUNT
_MIN_CZ_HISTORY_AGE = timedelta(days=30)
_MAX_SCORE_PERIOD_AGE_QUARTERS = 2
_MAX_SCORE_PERIOD_SPREAD_QUARTERS = 1
_SCORE_SOURCE_KEYS = ("revenue", "net_income", "operating_margin", "cz")


def rules() -> list[dict]:
    """Server-owned sieve rules.  Unsupported fallbacks stay explicit gaps."""
    return [
        {"layer": "hard_kill", "factor_id": "altman_em_score", "label": "A1 · zagrożenie wypłacalności", "operator": "lt", "threshold": 4.0},
        {"layer": "hard_kill", "factor_id": "piotroski_f_score", "label": "A2 · zapaść jakości", "operator": "lte", "threshold": 3.0},
        {"layer": "hard_kill", "factor_id": "equity", "label": "A3 · ujemny lub nieopublikowany kapitał własny", "operator": "lte", "threshold": 0.0},
        {"layer": "hard_kill", "factor_id": "revenue_growth", "label": "A4 · trwały regres przychodów i marży", "operator": "composite", "threshold": None},
        {"layer": "hard_kill", "factor_id": "net_debt_ebitda", "label": "A5 · dźwignia ekstremalna", "operator": "gt", "threshold": 6.0},
        {"layer": "hard_kill", "factor_id": "turnover", "label": "A6 · brak obrotu", "operator": "eq", "threshold": 0.0},
        {"layer": "hard_kill", "factor_id": "net_income", "label": "A7 · chroniczna strata", "operator": "composite", "threshold": None},
        {"layer": "improvement", "factor_id": "improvement_signals", "label": "B · co najmniej dwa sygnały poprawy", "operator": "gte", "threshold": 2.0},
    ]


def _factor(
    factor_id: str,
    *,
    value: float | None,
    delta: float | None,
    period: str | None,
    note: str | None = None,
    history_median: float | None = None,
    history_batch_ids: tuple[int, ...] = (),
    history_document_version_ids: tuple[int, ...] = (),
) -> SieveFactor:
    return SieveFactor(
        id=factor_id,
        label=_FACTOR_LABELS[factor_id],
        note=note,
        value=value,
        delta=delta,
        period=period,
        history_median=history_median,
        history_batch_ids=history_batch_ids,
        history_document_version_ids=history_document_version_ids,
    )


def _history_points(
    history: Mapping[str, Iterable[float | CzHistoryPoint]], ticker: str
) -> tuple[CzHistoryPoint, ...]:
    points: list[CzHistoryPoint] = []
    for item in history.get(ticker, ()):
        if isinstance(item, CzHistoryPoint):
            points.append(item)
        elif item is not None:
            points.append(CzHistoryPoint(None, None, float(item)))
    return tuple(points)


def _percentiles(values: Iterable[tuple[str, float]]) -> dict[str, float]:
    """Average-rank percentiles with deterministic ties, scoped to one batch."""
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0][0]: 50.0}
    result: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average_rank = (index + end) / 2.0
        percentile = average_rank / (len(ordered) - 1) * 100.0
        for position in range(index, end + 1):
            result[ordered[position][0]] = percentile
        index = end + 1
    return result


def _ranking_value(component_id: str, raw_value: float) -> float:
    lower, upper = _SCORE_BOUNDS[component_id]
    return max(lower, min(upper, raw_value))


def _period_index(period: str | None) -> int | None:
    match = re.fullmatch(r"((?:19|20)\d{2})Q([1-4])", period or "")
    if match is None:
        return None
    return int(match.group(1)) * 4 + int(match.group(2)) - 1


def _period_label(index: int) -> str:
    return f"{index // 4}Q{index % 4 + 1}"


def _source_period(row: FactorRow, key: str) -> str | None:
    return getattr(row, "extras", {}).get("source_periods", {}).get(
        key, row.report_period
    )


def _score_normalizations(row: FactorRow) -> tuple[SieveScoreNormalization, ...]:
    raw_items = getattr(row, "extras", {}).get("score_normalizations", [])
    result: list[SieveScoreNormalization] = []
    for raw in raw_items:
        if not isinstance(raw, dict) or raw.get("component_id") not in SCORE_COMPONENT_IDS:
            continue
        result.append(
            SieveScoreNormalization(
                component_id=str(raw["component_id"]),
                label=str(raw.get("label") or _SCORE_LABELS[str(raw["component_id"])]),
                reported_value=(
                    float(raw["reported_value"])
                    if raw.get("reported_value") is not None
                    else None
                ),
                normalized_value=(
                    float(raw["normalized_value"])
                    if raw.get("normalized_value") is not None
                    else None
                ),
                discontinued_share_pct=float(raw["discontinued_share_pct"]),
                period=str(raw.get("period") or row.report_period or "unknown"),
                reason=str(raw.get("reason") or "Material result distortion."),
                source_fact_ids=tuple(int(value) for value in raw.get("source_fact_ids", [])),
                source_document_version_ids=tuple(
                    int(value) for value in raw.get("source_document_version_ids", [])
                ),
            )
        )
    return tuple(sorted(result, key=lambda item: item.component_id))


def evaluate_workbench_sieve(
    rows: Iterable[FactorRow],
    *,
    prior_cz_by_ticker: Mapping[str, Iterable[float | CzHistoryPoint]] | None = None,
    as_of: datetime | None = None,
) -> SieveResult:
    """Evaluate stored values only — no database access, fetch or side effects.

    Only positive evidence fires a numeric rule.  Equity is the documented
    required-fundamental exception: a missing published value is an inspectable
    A3 exclusion, never silently coerced to zero.  The undefined debt-ratio
    fallback and unavailable raw net-debt series remain named gaps.
    """
    history = prior_cz_by_ticker or {}
    candidates: list[
        tuple[SieveCandidate, dict[str, float | None], tuple[str, ...]]
    ] = []
    excluded: list[SieveExcluded] = []
    coverage = {factor_id: 0 for factor_id in _FACTOR_LABELS}
    covered_rows = 0
    ordered_rows = sorted(rows, key=lambda item: item.ticker)
    market_period_indexes = [
        index
        for row in ordered_rows
        for key in _SCORE_SOURCE_KEYS
        if (index := _period_index(_source_period(row, key))) is not None
    ]
    latest_market_period = max(market_period_indexes, default=None)

    for row in ordered_rows:
        period = row.report_period
        source_periods = getattr(row, "extras", {}).get("source_periods", {})
        factor_period = lambda factor_id: source_periods.get(factor_id, period)
        normalizations = _score_normalizations(row)
        normalization_by_component = {
            item.component_id: item for item in normalizations
        }
        normalized_net_income_growth = (
            normalization_by_component["net_income_growth"].normalized_value
            if "net_income_growth" in normalization_by_component
            else row.net_income_dyn_rr_pct
        )
        normalized_current_pe = (
            normalization_by_component["current_pe"].normalized_value
            if "current_pe" in normalization_by_component
            else row.cz
        )
        current_pe_was_normalized = "current_pe" in normalization_by_component
        factors = (
            _factor("altman_em_score", value=row.altman_value, delta=None, period=period),
            _factor("piotroski_f_score", value=row.piotroski_f, delta=None, period=period),
            _factor("equity", value=row.equity_pln_thousands, delta=None, period=factor_period("equity")),
            _factor("revenue_growth", value=row.revenue_dyn_rr_pct, delta=row.revenue_dyn_rr_pct, period=factor_period("revenue")),
            _factor(
                "net_income_growth",
                value=normalized_net_income_growth,
                delta=normalized_net_income_growth,
                period=factor_period("net_income"),
                note=(
                    normalization_by_component["net_income_growth"].reason
                    if "net_income_growth" in normalization_by_component
                    else None
                ),
            ),
            _factor("operating_margin", value=row.op_margin_pct, delta=row.op_margin_delta_pp, period=factor_period("operating_margin")),
            _factor(
                "operating_margin_change",
                value=row.op_margin_delta_pp,
                delta=row.op_margin_delta_pp,
                period=factor_period("operating_margin"),
            ),
            _factor("net_debt_ebitda", value=row.net_debt_ebitda, delta=None, period=factor_period("net_debt_ebitda")),
            _factor("net_income", value=row.net_income_ttm_pln_thousands, delta=None, period=period),
            _factor(
                "turnover",
                value=(1.0 if row.turnover_present else 0.0) if row.turnover_present is not None else None,
                delta=None,
                period=factor_period("cz"),
            ),
            _factor(
                "current_pe",
                value=normalized_current_pe,
                delta=None,
                period=factor_period("cz"),
                note=(
                    normalization_by_component["current_pe"].reason
                    if "current_pe" in normalization_by_component
                    else "Do wyniku trafia wyłącznie dodatnie C/Z; niższe jest lepsze."
                ),
            ),
        )
        history_points = _history_points(history, row.ticker)
        history_cutoff = as_of - _MIN_CZ_HISTORY_AGE if as_of is not None else None
        comparable_history = tuple(
            point
            for point in history_points
            if point.value > 0.0
            and (
                history_cutoff is None
                or (
                    point.observed_at is not None
                    and point.observed_at <= history_cutoff
                )
            )
        )
        previous_cz_median = (
            float(median(point.value for point in comparable_history))
            if comparable_history
            else None
        )
        valuation_delta = (
            ((previous_cz_median - normalized_current_pe) / abs(previous_cz_median) * 100.0)
            if not current_pe_was_normalized
            and normalized_current_pe is not None
            and normalized_current_pe > 0.0
            and previous_cz_median not in (None, 0.0)
            else None
        )
        factors += (
            _factor(
                "valuation_vs_own_history",
                value=normalized_current_pe,
                delta=valuation_delta,
                period=factor_period("cz"),
                note=(
                    "Bieżące C/Z oczyszczono do działalności kontynuowanej, "
                    "a historyczne snapshoty są raportowane; nie porównano różnych semantyk."
                    if current_pe_was_normalized
                    else (
                        f"Mediana wcześniejszych snapshotów: {previous_cz_median:g}"
                        if previous_cz_median is not None
                        else "Brak snapshotu C/Z starszego o co najmniej 30 dni."
                    )
                ),
                history_median=previous_cz_median,
                history_batch_ids=tuple(
                    point.batch_id for point in comparable_history if point.batch_id is not None
                ),
                history_document_version_ids=tuple(
                    point.document_version_id
                    for point in comparable_history
                    if point.document_version_id is not None
                ),
            ),
            _factor(
                "net_cash_or_debt_trend",
                value=None,
                delta=None,
                period=period,
                note="Źródło nie dostarcza jeszcze wartości długu netto ani jego zmiany.",
            ),
        )

        values = {factor.id: factor.value for factor in factors}
        for factor_id, value in values.items():
            if factor_id == "valuation_vs_own_history":
                continue
            if value is not None:
                coverage[factor_id] += 1
        if (
            not current_pe_was_normalized
            and normalized_current_pe is not None
            and normalized_current_pe > 0.0
            and previous_cz_median is not None
        ):
            coverage["valuation_vs_own_history"] += 1
        base_inputs = (
            row.altman_value,
            row.piotroski_f,
            row.equity_pln_thousands,
            row.revenue_dyn_rr_pct,
            normalized_net_income_growth,
            row.op_margin_delta_pp,
            row.net_debt_ebitda,
        )
        if all(value is not None for value in base_inputs):
            covered_rows += 1

        gaps: list[str] = []
        if row.altman_value is None:
            gaps.append("Brak Altman EM-Score.")
        if row.piotroski_f is None:
            gaps.append("Brak Piotroski F-Score.")
        if row.equity_pln_thousands is None:
            gaps.append("Brak publikowalnego kapitału własnego (fundamental wymagany).")
        if row.revenue_dyn_rr_pct is None:
            gaps.append("Brak dynamiki przychodów r/r.")
        if normalized_net_income_growth is None:
            gaps.append("Brak dynamiki zysku netto r/r.")
        if row.op_margin_delta_pp is None:
            gaps.append("Brak trendu marży operacyjnej.")
        if row.net_debt_ebitda is None:
            gaps.append("Brak wskaźnika dług netto / EBITDA.")
        if row.net_income_ttm_pln_thousands is None:
            gaps.append("Brak punktowego zysku netto TTM do testu A7.")
        if row.turnover_present is None:
            gaps.append("Brak źródła obrotu w oknie snapshotu.")
        if normalized_current_pe is None or normalized_current_pe <= 0.0:
            gaps.append("C/Z nie jest dodatnie i nie może wejść do wyniku potencjału.")
        if current_pe_was_normalized:
            gaps.append(
                "B4 niedostępny: oczyszczone bieżące C/Z nie jest porównywalne "
                "z raportowaną historią C/Z."
            )
        elif previous_cz_median is None:
            gaps.append(
                "Brak dodatniej historii C/Z starszej o co najmniej 30 dni do testu B4."
            )
        if row.net_debt_ebitda is not None:
            gaps.append("Brak wartości długu netto do testu B5 (sam wskaźnik nie dowodzi gotówki netto).")

        kills: list[str] = []
        if row.altman_value is not None and row.altman_value < 4.0:
            kills.append("A1 · Altman EM-Score < 4,0.")
        if row.piotroski_f is not None and row.piotroski_f <= 3.0:
            kills.append("A2 · Piotroski F-Score ≤ 3.")
        if row.equity_pln_thousands is None:
            kills.append("A3 · Brak publikowalnego kapitału własnego (fundamental wymagany).")
        elif row.equity_pln_thousands <= 0.0:
            kills.append("A3 · Kapitał własny ≤ 0.")
        if (
            row.revenue_dyn_rr_pct is not None
            and row.revenue_dyn_rr_pct < 0.0
            and row.op_margin_delta_pp is not None
            and row.op_margin_delta_pp < 0.0
        ):
            kills.append("A4 · Przychody r/r i marża operacyjna spadają jednocześnie.")
        if row.net_debt_ebitda is not None and row.net_debt_ebitda > 6.0:
            kills.append("A5 · Dług netto / EBITDA > 6.")
        if row.turnover_present is False:
            kills.append("A6 · Brak obrotu w oknie snapshotu.")
        if (
            row.net_income_ttm_pln_thousands is not None
            and row.net_income_ttm_pln_thousands < 0.0
            and row.piotroski_f is not None
            and row.piotroski_f <= 5.0
        ):
            kills.append("A7 · Strata netto przy F-Score ≤ 5.")

        signals: list[str] = []
        if row.revenue_dyn_rr_pct is not None and row.revenue_dyn_rr_pct > 0.0:
            signals.append("B1 · Przychody rosną r/r")
        if row.op_margin_delta_pp is not None and row.op_margin_delta_pp > 0.0:
            signals.append("B2 · Marża operacyjna rośnie")
        if normalized_net_income_growth is not None and normalized_net_income_growth > 0.0:
            signals.append("B3 · Zysk netto rośnie r/r")
        if (
            not current_pe_was_normalized
            and normalized_current_pe is not None
            and normalized_current_pe > 0.0
            and previous_cz_median is not None
            and normalized_current_pe < previous_cz_median
        ):
            signals.append("B4 · C/Z poniżej własnej mediany snapshotów")

        if kills:
            excluded.append(
                SieveExcluded(
                    ticker=row.ticker,
                    name=row.name,
                    kill_reasons=tuple(kills),
                    factors=factors,
                    factor_gaps=tuple(gaps),
                    score_normalizations=normalizations,
                )
            )
            continue
        if len(signals) < 2:
            excluded.append(
                SieveExcluded(
                    ticker=row.ticker,
                    name=row.name,
                    kill_reasons=("stagnacja · mniej niż dwa sygnały poprawy B1–B5.",),
                    factors=factors,
                    factor_gaps=tuple(gaps),
                    score_normalizations=normalizations,
                )
            )
            continue
        score_raw_values = {
            "revenue_growth": row.revenue_dyn_rr_pct,
            "net_income_growth": normalized_net_income_growth,
            "operating_margin_change": row.op_margin_delta_pp,
            "operating_margin": row.op_margin_pct,
            "current_pe": (
                normalized_current_pe
                if normalized_current_pe is not None and normalized_current_pe > 0.0
                else None
            ),
        }
        score_periods = {
            "revenue_growth": factor_period("revenue"),
            "net_income_growth": factor_period("net_income"),
            "operating_margin_change": factor_period("operating_margin"),
            "operating_margin": factor_period("operating_margin"),
            "current_pe": factor_period("cz"),
        }
        score_blockers: list[str] = []
        present_score_components = tuple(
            component_id
            for component_id in SCORE_COMPONENT_IDS
            if score_raw_values[component_id] is not None
        )
        if present_score_components:
            score_period_indexes = {
                component_id: _period_index(score_periods[component_id])
                for component_id in present_score_components
            }
            if any(index is None for index in score_period_indexes.values()):
                score_blockers.append(
                    "Wynik potencjału niedostępny: nie rozpoznano okresu jednego "
                    "z dostępnych składników."
                )
            else:
                indexes = [int(index) for index in score_period_indexes.values()]
                spread = max(indexes) - min(indexes)
                age = (
                    latest_market_period - min(indexes)
                    if latest_market_period is not None
                    else 0
                )
                period_summary = ", ".join(
                    f"{component_id}={score_periods[component_id]}"
                    for component_id in present_score_components
                )
                if age > _MAX_SCORE_PERIOD_AGE_QUARTERS:
                    score_blockers.append(
                        "Wynik potencjału niedostępny: najstarszy składnik jest "
                        f"o {age} kw. za okresem rynku {_period_label(latest_market_period)} "
                        f"({period_summary})."
                    )
                if spread > _MAX_SCORE_PERIOD_SPREAD_QUARTERS:
                    score_blockers.append(
                        "Wynik potencjału niedostępny: okresy składników różnią się "
                        f"o {spread} kw. ({period_summary})."
                    )
        gaps.extend(score_blockers)
        candidates.append(
            (
                SieveCandidate(
                    ticker=row.ticker,
                    name=row.name,
                    rank=None,
                    rank_basis=(),
                    factors=factors,
                    factor_gaps=tuple(gaps),
                    improvement_signals=tuple(signals),
                    potential_score=None,
                    score_components=(),
                    score_normalizations=normalizations,
                ),
                score_raw_values,
                tuple(score_blockers),
            )
        )

    scoreable_tickers = {
        candidate.ticker
        for candidate, raw_values, blockers in candidates
        if not blockers
        and all(raw_values[component_id] is not None for component_id in SCORE_COMPONENT_IDS)
    }
    percentiles = {
        component_id: _percentiles(
            (
                candidate.ticker,
                _ranking_value(component_id, raw_values[component_id])
                * _SCORE_DIRECTIONS[component_id],
            )
            for candidate, raw_values, _blockers in candidates
            if candidate.ticker in scoreable_tickers
        )
        for component_id in SCORE_COMPONENT_IDS
    }
    scored: list[SieveCandidate] = []
    for candidate, raw_values, blockers in candidates:
        normalized_labels = {
            item.component_id: item.label for item in candidate.score_normalizations
        }
        components = (
            tuple(
                SieveScoreComponent(
                    id=component_id,
                    label=normalized_labels.get(
                        component_id, _SCORE_LABELS[component_id]
                    ),
                    raw_value=float(raw_values[component_id]),
                    ranking_value=_ranking_value(
                        component_id, float(raw_values[component_id])
                    ),
                    percentile=percentiles[component_id][candidate.ticker],
                    weight=_SCORE_WEIGHT,
                )
                for component_id in SCORE_COMPONENT_IDS
            )
            if candidate.ticker in scoreable_tickers
            else ()
        )
        potential_score = (
            round(sum(component.percentile * component.weight for component in components), 1)
            if len(components) == SCORE_COMPONENT_COUNT
            else None
        )
        if blockers:
            rank_basis = blockers
        elif potential_score is None:
            available_count = sum(value is not None for value in raw_values.values())
            rank_basis = (
                "Brak porównywalnego wyniku potencjału: "
                f"dostępne {available_count}/{SCORE_COMPONENT_COUNT} składników; braków nie imputowano.",
            )
        else:
            score_text = f"{potential_score:.1f}".replace(".", ",")
            rank_basis = (
                f"Wynik potencjału {score_text}/100 to średnia pięciu "
                "równoważnych percentyli poprawy, rentowności i wyceny "
                "w bieżącym batchu; nie jest prawdopodobieństwem.",
            )
        scored.append(
            SieveCandidate(
                ticker=candidate.ticker,
                name=candidate.name,
                rank=None,
                rank_basis=rank_basis,
                factors=candidate.factors,
                factor_gaps=candidate.factor_gaps,
                improvement_signals=candidate.improvement_signals,
                potential_score=potential_score,
                score_components=components,
                score_normalizations=candidate.score_normalizations,
            )
        )

    ranked = sorted(
        scored,
        key=lambda candidate: (
            candidate.potential_score is None,
            -(candidate.potential_score or 0.0),
            candidate.ticker,
        ),
    )
    ordered_candidates = tuple(
        SieveCandidate(
            ticker=candidate.ticker,
            name=candidate.name,
            rank=index,
            rank_basis=candidate.rank_basis,
            factors=candidate.factors,
            factor_gaps=candidate.factor_gaps,
            improvement_signals=candidate.improvement_signals,
            potential_score=candidate.potential_score,
            score_components=candidate.score_components,
            score_normalizations=candidate.score_normalizations,
        )
        for index, candidate in enumerate(ranked, start=1)
    )
    return SieveResult(
        candidates=ordered_candidates,
        excluded=tuple(sorted(excluded, key=lambda item: item.ticker)),
        factor_coverage=coverage,
        coverage_count=covered_rows,
    )
