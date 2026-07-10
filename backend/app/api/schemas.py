"""Pydantic DTOs — request/response contracts for the API.

Kept in one module on purpose (small app); split by domain if it outgrows ~300
lines. `from_attributes=True` lets a schema be built straight from an ORM
object, like AutoMapper-lite.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- watchlist

class WatchlistAddIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    note: str | None = Field(default=None, max_length=500)


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str | None
    note: str | None
    added_at: datetime
    risk_level: str = "none"
    fired_falsifiers: int = 0
    warning_falsifiers: int = 0


# -------------------------------------------------------- decision journal

class DecisionJournalEntryOut(BaseModel):
    """One immutable user decision record attached to a company thesis."""

    id: int
    ticker: str
    decision: str
    confidence: int
    thesis: str
    invalidation: str
    next_check: str
    review_date: date
    thesis_snapshot: dict
    thesis_hash: str | None
    created_by: str | None
    created_at: datetime


class DecisionJournalEntryCreateIn(BaseModel):
    """Fields needed to record a decision in under a minute.

    There is intentionally no update DTO or endpoint: correcting a decision
    means adding a new entry, preserving the point-in-time history.
    """

    decision: str = Field(min_length=1, max_length=40)
    confidence: int = Field(ge=0, le=100)
    thesis: str = Field(min_length=1, max_length=4000)
    invalidation: str = Field(min_length=1, max_length=2000)
    next_check: str = Field(min_length=1, max_length=2000)
    review_date: date
    thesis_snapshot: dict = Field(default_factory=dict)


# --------------------------------------------------------------- discovery

class DiscoveryCandidateOut(BaseModel):
    ticker: str
    name: str | None
    report_period: str
    br_rating: str | None
    br_rating_value: float | None
    piotroski_f_score: int | None
    rank: int
    rank_basis: list[str]
    reasons: list[str]
    caveat: str


class DiscoveryEvaluationJobOut(BaseModel):
    id: int
    status: str
    candidate_count: int
    evaluation_budget: int
    reused: bool


class DiscoveryScheduleOut(BaseModel):
    """Bounded quick-analysis scheduling after an explicit source refetch."""

    considered: int
    queued: int
    skipped_recent: int
    skipped_pending: int
    skipped_not_stored: int
    tickers: list[str]
    stale_after_days: int


class DiscoveryOut(BaseModel):
    source: str
    source_url: str
    as_of: datetime
    universe_count: int
    result_count: int
    source_note: str
    candidates: list[DiscoveryCandidateOut]
    evaluation_job: DiscoveryEvaluationJobOut | None = None
    scheduled_analysis: DiscoveryScheduleOut | None = None


# ---------------------------------------------------------------- companies

class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str | None
    market: str | None
    sector: str | None
    shares_outstanding: int | None
    market_cap: float | None = None  # PLN, reported by BiznesRadar
    enterprise_value: float | None = None  # PLN
    updated_at: datetime


class RefreshSummaryOut(BaseModel):
    ticker: str
    summary: dict[str, str]


class ReportRowOut(BaseModel):
    field_code: str
    label: str
    values: list[float | None]


class FinancialsOut(BaseModel):
    statement: str
    freq: str
    periods: list[str]
    rows: list[ReportRowOut]


class IndicatorPointOut(BaseModel):
    period: str
    value: float | None


class DividendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    dps: float | None
    yield_pct: float | None


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    close: float
    volume: int | None
    scraped_at: datetime | None


# -------------------------------------------------------------------- forum

class TopicLinkIn(BaseModel):
    url: str = Field(max_length=500)
    ticker: str = Field(min_length=1, max_length=12)


class ForumTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str | None
    last_post_at: datetime | None
    last_synced_at: datetime | None


class ForumSyncOut(BaseModel):
    topic_id: int
    new_posts: int
    total_posts: int


class ForumPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phpbb_post_id: int
    author: str
    posted_at: datetime | None
    upvotes: int | None


class ForumPageOut(BaseModel):
    total: int
    page: int
    page_size: int
    posts: list[ForumPostOut]


# ----------------------------------------------------------------- forecast

class ForecastAssumptionsIn(BaseModel):
    """Next-quarter assumptions; every value in tys. PLN unless stated."""

    period: str = Field(pattern=r"^\d{4}Q[1-4]$")
    revenue: float
    gross_margin_pct: float = Field(ge=-100, le=100)
    selling_costs_pct: float = Field(ge=0, le=100)
    admin_costs: float
    other_operating: float = 0.0
    financial_net: float = 0.0
    tax_rate: float = Field(default=0.19, ge=0, le=1)
    depreciation: float | None = None


class ForecastCreateIn(BaseModel):
    assumptions: ForecastAssumptionsIn
    label: str | None = Field(default=None, max_length=120)
    save: bool = True


class ForecastOut(BaseModel):
    id: int | None  # None when computed without saving
    label: str | None
    assumptions: dict
    result: dict
    created_at: datetime | None


# ------------------------------------------------------------------ dossier

class CheckOut(BaseModel):
    id: str
    name: str
    verdict: str  # pass | fail | unknown
    evidence: str


class PrescoreOut(BaseModel):
    passed: int
    total: int
    checks: list[CheckOut]


class QuarterMetricsOut(BaseModel):
    period: str
    revenue: float | None
    revenue_yoy_pct: float | None
    gross_margin_pct: float | None
    sales_margin_pct: float | None
    net_margin_pct: float | None
    profit_on_sales: float | None
    operating_profit: float | None
    net_profit: float | None
    one_off_share_pct: float | None
    discontinued_profit: float | None = None
    continuing_net_profit: float | None = None
    discontinued_share_of_net_pct: float | None = None


class TtmOut(BaseModel):
    net_profit: float | None  # tys. PLN
    eps: float | None  # PLN per share
    pe: float | None
    discontinued_profit: float | None = None
    continuing_net_profit: float | None = None
    continuing_eps: float | None = None
    continuing_pe: float | None = None
    valuation_eps: float | None = None
    valuation_pe: float | None = None
    valuation_basis: str = "reported"
    market_cap: float | None  # PLN
    price: float | None
    price_date: date | None
    # "reported" (BiznesRadar profile figure) or "derived" (price × shares);
    # check_pct = deviation between the two when both are known.
    market_cap_source: str | None = None
    market_cap_check_pct: float | None = None


class ResultQualityOut(BaseModel):
    """Prepared bridge for report UI; raw evidence stays in audit views."""

    period: str | None
    is_material: bool
    cause_status: str
    reported_net_profit: float | None
    discontinued_profit: float | None
    continuing_net_profit: float | None
    discontinued_share_of_net_pct: float | None
    one_off_share_pct: float | None
    reported_ttm_net_profit: float | None
    continuing_ttm_net_profit: float | None
    reported_eps: float | None
    continuing_eps: float | None
    reported_pe: float | None
    continuing_pe: float | None
    valuation_basis: str
    summary: str
    valuation_warning: str | None
    source_fields: list[str]


class PeHistoryOut(BaseModel):
    median: float | None
    q1: float | None
    q3: float | None
    current: float | None
    percentile: float | None  # 0–100, share of history ≤ current


class NetCashOut(BaseModel):
    value: float | None  # tys. PLN
    note: str


class FreshnessOut(BaseModel):
    financials_scraped_at: datetime | None
    last_price_date: date | None
    forum_last_synced_at: datetime | None


class ForumStatsOut(BaseModel):
    topics: int
    posts: int
    last_post_at: datetime | None
    intelligence: dict | None = None


class InsightOut(BaseModel):
    id: str
    name: str
    value: str
    verdict: str  # good | neutral | bad | unknown
    comment: str
    importance: int  # 3 kluczowy · 2 ważny · 1 kontekst


class MissingDataOut(BaseModel):
    id: str
    name: str
    why: str


class InsightsOut(BaseModel):
    """Dynamic per-company analysis: indicator set picked by sector/size,
    honest about what could not be computed (see services/insights.py)."""

    size_code: str | None
    size_label: str | None
    sector_group: str
    sector_group_label: str
    sector: str | None
    key_indicators: list[InsightOut]
    strengths: list[str]
    concerns: list[str]
    missing: list[MissingDataOut]
    data_notes: list[str]
    coverage: dict | None
    summary: str
    # Provenance (services/insights_ai.py): "deterministic" (no key / AI
    # fallback) or "ai" (+ ai_notes). Optional/defaulted for backward
    # compatibility with any caller still building this dict by hand.
    engine: str | None = "deterministic"
    ai_notes: dict | None = None


class ThesisFactorOut(BaseModel):
    """A weighted pro or con; `text` mirrors the source Insight verbatim."""

    id: str
    text: str
    weight: float
    principle: str  # investor-principle tag (Polish)


class VerifyNextOut(BaseModel):
    id: str
    text: str
    why: str


class EntryQualityOut(BaseModel):
    code: str  # attractive | neutral | weak | insufficient_data
    label: str  # Polish; framed as an analysis entrance, not a buy signal
    rationale: str


class StrategyRefOut(BaseModel):
    id: str
    label: str


class ThesisOut(BaseModel):
    """Rule-based investment-thesis read composed on top of the insights
    (services/thesis.py). An entrance to human analysis, never a buy signal."""

    entry_quality: EntryQualityOut
    pros: list[ThesisFactorOut]
    cons: list[ThesisFactorOut]
    verify_next: list[VerifyNextOut]
    thesis_read: str
    disclaimer: str
    valuation_basis: str  # forward vs trailing C/Z, honest about which
    strategy: StrategyRefOut  # which profile produced the read
    # WP2b provenance: "deterministic" (no key / AI fallback) or "ai". `ai_notes`
    # (model, iterations, per-change rationale, case-similarity) is present only
    # on the AI path; the frontend renders a "silnik: deterministyczny/AI" chip.
    engine: str = "deterministic"
    ai_notes: dict | None = None


class ScenarioTargetMultipleOut(BaseModel):
    type: str  # cz | cwk | ev_ebitda (the effective multiple used)
    value: float | None  # the own-history quartile the scenario reverts to
    basis_label: str  # Polish; names the quartile + observation count (n)


class ScenarioHorizonOut(BaseModel):
    low_months: int
    high_months: int
    basis_label: str  # Polish; a labelled default until the corpus cites real ones


class ScenarioCompanyOutcomeOut(BaseModel):
    direction: Literal["negative", "neutral", "positive", "unknown"]
    label: str
    description: str


class ScenarioOut(BaseModel):
    """One simulation scenario — an if-this-then-that projection, never a signal."""

    id: str
    kind: str  # negative | base | positive | event
    label: str  # Polish
    probability: float  # 0–1; the set sums to 1 (renormalised on the AI path)
    narrative: str  # Polish, sourced (or a labelled data gap)
    target_multiple: ScenarioTargetMultipleOut
    target_price: float | None  # PLN; None when a driver is missing (labelled gap)
    implied_upside_pct: float | None
    horizon: ScenarioHorizonOut
    drivers: list[str]  # each traceable
    assumptions: list[str]  # each labelled as an assumption
    company_outcome: ScenarioCompanyOutcomeOut | None = None


class ScenarioSetOut(BaseModel):
    """The scenario set for one stock (services/scenarios.py). Framed as an
    entrance to analysis; carries a set-level probability-weighted EV."""

    scenarios: list[ScenarioOut]
    valuation_multiple: str  # cz | cwk | ev_ebitda
    current_price: float | None  # PLN
    weighted_expected_price: float | None  # PLN, Σ pᵢ·target_priceᵢ
    weighted_expected_upside_pct: float | None
    framing: str  # fixed "punkt wejścia w analizę, nie sygnał"
    disclaimer: str
    quality_warnings: list[str] = Field(default_factory=list)
    # Provenance: "deterministic" (no key / AI fallback) or "ai" (+ ai_notes).
    engine: str = "deterministic"
    ai_notes: dict | None = None


class ValuationPotentialOut(BaseModel):
    value_pct: float | None  # anchored to the scenario set's weighted-EV upside
    range_pct: list[float] | None  # [min, max] scenario upside band, or None
    basis_label: str  # Polish; names what the number is (or the gap)


class ValuationConfidenceOut(BaseModel):
    level: str  # low | medium | high (deterministic coverage heuristic)
    rationale: str  # Polish; the counts + level, AI may reword


class WhatWouldChangeOut(BaseModel):
    id: str
    text: str
    why: str


class ValuationOut(BaseModel):
    """Stock-potential valuation composed on top of the scenario set
    (services/valuation_ai.py). An entrance to analysis, never a signal."""

    potential: ValuationPotentialOut
    confidence: ValuationConfidenceOut
    what_would_change: list[WhatWouldChangeOut]
    narrative: str
    framing: str
    disclaimer: str
    # Provenance: "deterministic" (no key / AI fallback) or "ai" (+ ai_notes).
    engine: str = "deterministic"
    ai_notes: dict | None = None


# ----------------------------------------------------------------- analyses

class AnalysisOut(BaseModel):
    """One persisted AI analysis run (services/claude_client.py, Phase 5).
    `output` is the verdict object (PLAN §8 schema) kept as a permissive dict —
    it is rendered by the frontend, not re-validated field-by-field here."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    completed_at: datetime | None
    as_of: datetime | None
    provider: str | None
    model: str
    purpose: str
    status: str
    skill_version: str | None
    skill_hash: str | None
    validation: dict | None
    latency_ms: int | None
    alignment_score: int | None
    input_tokens: int | None
    output_tokens: int | None
    input_hash: str | None = None
    created_by: str | None
    output: dict | None


class AgentRunOut(BaseModel):
    """One Codex workflow run, regardless of whether it produced analysis."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow: str
    trigger: str
    status: str
    company_id: int | None
    model_role: str | None
    model: str | None
    orchestrator_model: str | None
    inputs: dict
    outputs: dict
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentRunCreateIn(BaseModel):
    """Queue a provider-neutral Codex/GPT workflow for later execution."""

    workflow: str = Field(min_length=1, max_length=80)
    ticker: str | None = Field(default=None, min_length=1, max_length=12)
    trigger: str = Field(default="ui-request", min_length=1, max_length=30)
    model_role: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=80)
    orchestrator_model: str | None = Field(default=None, max_length=80)
    inputs: dict = Field(default_factory=dict)


class PreSessionBriefIn(BaseModel):
    """HTTP/n8n-friendly trigger for the pre-session Codex workflow."""

    ticker: str | None = Field(default=None, min_length=1, max_length=12)
    trigger: str = Field(default="ui-request", min_length=1, max_length=30)
    orchestrator_model: str | None = Field(default=None, max_length=80)
    fetch_details: bool = True
    queue: bool = True


class PreSessionBriefOut(BaseModel):
    ok: bool
    espi_poll: dict
    agent_run: AgentRunOut | None


class QueueAttemptOut(BaseModel):
    """Result of one supervised queue claim; no model is executed here."""

    ok: bool
    attempted: bool
    message: str
    agent_run: AgentRunOut | None


class MonitorChangeOut(BaseModel):
    id: int
    from_snapshot_id: int
    to_snapshot_id: int
    changes: list[dict]
    created_at: datetime


class MonitorCheckOut(BaseModel):
    baseline_exists: bool
    changed: bool
    snapshot_id: int
    snapshot_hash: str
    change: MonitorChangeOut | None


class FalsifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    key: str
    statement: str
    status: str
    reason: str
    review_date: date | None
    thesis_hash: str | None
    created_at: datetime
    updated_at: datetime


class FalsifierCreateIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=2000)
    status: str = Field(default="holding", min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=2000)
    review_date: date | None = None
    thesis_hash: str | None = Field(default=None, min_length=64, max_length=64)


class FalsifierUpdateIn(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=2000)
    review_date: date | None = None


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    instrument_name: str | None
    portfolio: str
    entry_date: date | None
    entry_price: float | None
    quantity: float | None
    size_pln: float | None
    sizing_rule_flag: bool
    source: str
    imported_at: datetime


class PositionCsvImportIn(BaseModel):
    portfolio: str = Field(default="default", min_length=1, max_length=80)
    csv_text: str = Field(min_length=1, max_length=500_000)


class PositionImportOut(BaseModel):
    imported: int
    skipped_duplicates: int
    unmatched: list[str]
    positions: list[PositionOut]


class MyfundImportIn(BaseModel):
    portfolio: str | None = Field(default=None, min_length=1, max_length=80)


class AnalysisRunOut(BaseModel):
    """Provider-neutral analysis result, used by Codex/MCP workflows."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    agent_run_id: int | None
    source: str
    workflow: str
    model_role: str
    model: str
    status: str
    verification_status: str
    input_snapshot: dict
    output: dict
    verification: dict
    alignment_score: int | None
    created_by: str | None
    created_at: datetime


class EventReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    source: str
    external_id: str
    raw_url: str | None
    published_at: datetime | None
    scraped_at: datetime
    title: str | None
    parsed: dict
    materiality: dict


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_run_id: int | None
    strategy: str
    from_date: date | None
    to_date: date | None
    status: str
    model_role: str | None
    model: str | None
    parameters: dict
    summary: dict
    verification_status: str
    created_at: datetime


class BacktestObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    backtest_run_id: int
    company_id: int
    as_of_date: date
    known_inputs: dict
    signal: dict
    outcome: dict
    created_at: datetime


class BacktestRunDetailOut(BacktestRunOut):
    observations: list[BacktestObservationOut]


class BacktestRunCreateIn(BaseModel):
    strategy: str = Field(default="malik_v1", min_length=1, max_length=80)
    from_date: date
    to_date: date
    ticker: str | None = Field(default=None, min_length=1, max_length=12)
    outcome_windows: list[int] = Field(default_factory=lambda: [30, 90, 180, 365])
    financial_availability_policy: str = Field(default="scraped_at")
    report_lag_days: int = Field(default=120, ge=0, le=730)


class AgentEvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_run_id: int | None
    strategy: str
    from_date: date | None
    to_date: date | None
    status: str
    model_role: str | None
    model: str | None
    parameters: dict
    summary: dict
    verification_status: str
    created_at: datetime


class AgentEvaluationObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evaluation_run_id: int
    analysis_run_id: int
    company_id: int
    as_of_date: date
    known_inputs: dict
    prediction: dict
    outcome: dict
    score: dict
    created_at: datetime


class AgentEvaluationRunDetailOut(AgentEvaluationRunOut):
    observations: list[AgentEvaluationObservationOut]


class AgentEvaluationRunCreateIn(BaseModel):
    strategy: str = Field(default="valuation_direction_v1", min_length=1, max_length=80)
    from_date: date | None = None
    to_date: date | None = None
    ticker: str | None = Field(default=None, min_length=1, max_length=12)
    workflow: str | None = Field(default=None, min_length=1, max_length=80)
    outcome_windows: list[int] = Field(default_factory=lambda: [30, 90, 180, 365])


class DossierOut(BaseModel):
    company: CompanyOut
    freshness: FreshnessOut
    quarters: list[QuarterMetricsOut]
    ttm: TtmOut
    result_quality: ResultQualityOut
    pe_history: PeHistoryOut
    net_cash: NetCashOut
    market_data: dict
    analysis_context_status: dict | None = None
    dividends: list[DividendOut]
    prescore: PrescoreOut
    insights: InsightsOut
    thesis: ThesisOut
    scenarios: ScenarioSetOut
    valuation: ValuationOut
    latest_forecast: ForecastOut | None
    forum: ForumStatsOut
