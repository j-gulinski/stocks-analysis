"""Pydantic DTOs — request/response contracts for the API.

Kept in one module on purpose (small app); split by domain if it outgrows ~300
lines. `from_attributes=True` lets a schema be built straight from an ORM
object, like AutoMapper-lite.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


CaseState = Literal[
    "new", "ingesting", "data_review", "business_model", "thesis",
    "scenarios", "review", "monitoring", "blocked", "closed",
]
CaseStep = Literal[
    "ingest", "data_review", "business_model", "thesis",
    "scenarios", "review", "monitoring",
]


class ResearchCaseCreateIn(BaseModel):
    purpose: str = Field(default="investment-research", min_length=1, max_length=80)
    state: CaseState = "new"
    current_step: CaseStep = "ingest"
    as_of: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=2000)


class ResearchCaseUpdateIn(BaseModel):
    state: CaseState | None = None
    current_step: CaseStep | None = None
    as_of: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=2000)
    change_reason: str | None = Field(default=None, max_length=2000)


class ResearchCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    purpose: str
    state: CaseState
    current_step: CaseStep
    as_of: datetime | None
    blocked_reason: str | None
    promotion_triage_review_id: int | None
    promotion_review_price_pln: float | None
    promotion_note: str | None
    promotion_evidence_reason: str | None
    quarterly_review_due_on: date | None
    material_event_review_policy: str | None
    created_at: datetime
    updated_at: datetime


class ResearchLabCreateIn(BaseModel):
    """Create or reopen the durable research identity for one ticker."""

    ticker: str = Field(min_length=1, max_length=12)
    source_document_version_id: int | None = Field(default=None, ge=1)


class ResearchCaseSummaryOut(BaseModel):
    """Compact Research Lab row with its one initial-research queue item."""

    id: int
    company_id: int
    ticker: str
    name: str | None
    purpose: str
    state: CaseState
    current_step: CaseStep
    as_of: datetime | None
    blocked_reason: str | None
    created_at: datetime
    updated_at: datetime
    initial_research_run_id: int | None
    initial_research_status: str | None
    latest_snapshot_status: str | None = None
    latest_snapshot_as_of: datetime | None = None


ResearchArchetype = Literal[
    "industrial-consumer",
    "bank-financial",
    "developer-real-estate",
    "software-services",
    "gaming-event",
    "energy-resources",
    "holding-biotech",
]
ResearchSnapshotStatus = Literal["provisional", "verified", "rejected", "needs-human"]


class StrictResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchDriver(StrictResearchModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    mechanism: str = Field(min_length=1, max_length=1000)
    unit: str | None = Field(default=None, max_length=40)
    source_document_version_ids: list[int] = Field(default_factory=list)
    basis: str | None = Field(default=None, max_length=2000)
    focus_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_driver_provenance(self):
        if not self.source_document_version_ids and not self.basis:
            raise ValueError("drivers require a document version or explicit basis")
        return self


class ResearchKpi(StrictResearchModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    unit: str | None = Field(default=None, max_length=40)
    rationale: str = Field(min_length=1, max_length=1000)
    source_document_version_ids: list[int] = Field(default_factory=list)
    basis: str | None = Field(default=None, max_length=2000)
    focus_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_kpi_provenance(self):
        if not self.source_document_version_ids and not self.basis:
            raise ValueError("KPIs require a document version or explicit basis")
        return self


class CompanyOverlay(StrictResearchModel):
    segments: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    source_questions: list[str] = Field(default_factory=list)
    unusual_risks: list[str] = Field(default_factory=list)


class CompanyProfileIn(StrictResearchModel):
    schema_version: Literal["company-profile-v1", "company-profile-v2"] = "company-profile-v2"
    version: int = Field(ge=1)
    archetype: ResearchArchetype
    archetype_version: str = Field(min_length=1, max_length=40)
    company_overlay: CompanyOverlay
    drivers: list[ResearchDriver] = Field(min_length=1)
    kpis: list[ResearchKpi] = Field(min_length=1)


class CompanyProfileOut(CompanyProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    created_at: datetime


class ResearchClaim(StrictResearchModel):
    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["fact", "calculation", "assumption", "lead", "unknown"]
    source_document_version_ids: list[int] = Field(default_factory=list)
    basis: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_claim_provenance(self):
        if self.kind in {"fact", "lead"} and not self.source_document_version_ids:
            raise ValueError("fact and lead claims require a document version")
        if self.kind in {"calculation", "assumption", "unknown"} and not self.basis:
            raise ValueError("calculation, assumption and unknown claims require a named basis")
        return self


class ResearchStatementProvenance(StrictResearchModel):
    """Provenance for one exact displayed statement path in the fixed renderer."""

    path: str = Field(pattern=r"^/", min_length=2, max_length=300)
    claim: ResearchClaim


class BriefSection(StrictResearchModel):
    current_understanding: str = Field(min_length=1, max_length=4000)
    freshness: str = Field(min_length=1, max_length=1000)
    main_gap: str = Field(min_length=1, max_length=2000)
    next_action: str = Field(min_length=1, max_length=2000)


class BusinessAndDriversSection(StrictResearchModel):
    business_model: str = Field(min_length=1, max_length=6000)
    revenue_model: str = Field(min_length=1, max_length=4000)
    driver_keys: list[str] = Field(min_length=1)
    claims: list[ResearchClaim] = Field(default_factory=list)


class PerformanceSection(StrictResearchModel):
    summary: str = Field(min_length=1, max_length=6000)
    result_bridge: list[str] = Field(default_factory=list)
    kpi_keys: list[str] = Field(min_length=1)
    claims: list[ResearchClaim] = Field(default_factory=list)


class EvidenceSection(StrictResearchModel):
    summary: str = Field(min_length=1, max_length=4000)
    primary_document_version_ids: list[int] = Field(default_factory=list)
    claims: list[ResearchClaim] = Field(default_factory=list)


class ThesisSection(StrictResearchModel):
    why_now: str = Field(min_length=1, max_length=4000)
    counter_thesis: str = Field(min_length=1, max_length=4000)
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    governance: str = Field(min_length=1, max_length=4000)
    falsifiers: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    claims: list[ResearchClaim] = Field(default_factory=list)


class HistorySection(StrictResearchModel):
    changes_since_previous: list[str] = Field(default_factory=list)
    prior_snapshot_id: int | None = Field(default=None, ge=1)
    claims: list[ResearchClaim] = Field(default_factory=list)


class ResearchSections(StrictResearchModel):
    brief: BriefSection
    business_and_drivers: BusinessAndDriversSection
    performance: PerformanceSection
    evidence: EvidenceSection
    thesis: ThesisSection
    history: HistorySection


class ResearchSourceManifestItem(StrictResearchModel):
    document_version_id: int = Field(ge=1)
    role: Literal["primary", "normalized", "context", "lead"]
    purpose: str = Field(min_length=1, max_length=1000)


class ResearchConflict(StrictResearchModel):
    topic: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    document_version_ids: list[int] = Field(min_length=2)


class ResearchGap(StrictResearchModel):
    topic: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    impact: str = Field(min_length=1, max_length=1000)
    focus_tags: list[str] = Field(default_factory=list)


class ResearchNextCheck(StrictResearchModel):
    question: str = Field(min_length=1, max_length=1000)
    suggested_source: str = Field(min_length=1, max_length=500)


class ResearchVerifierChecks(StrictResearchModel):
    schema_integrity: bool
    source_integrity: bool
    company_identity: bool
    look_ahead: bool
    math_integrity: bool


class ResearchVerifierResult(StrictResearchModel):
    model_role: Literal["verifier_strict"] = "verifier_strict"
    verifier_model: str = Field(min_length=1, max_length=80)
    verdict: Literal["pass", "fail", "needs-human"]
    checks: ResearchVerifierChecks
    summary: str = Field(min_length=1, max_length=4000)


class ResearchSnapshotDraftIn(StrictResearchModel):
    contract_version: Literal["research-snapshot-v1", "research-snapshot-v2"] = "research-snapshot-v2"
    agent_run_id: int = Field(ge=1)
    lease_owner: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    as_of: datetime
    profile: CompanyProfileIn
    sections: ResearchSections
    source_manifest: list[ResearchSourceManifestItem]
    conflicts: list[ResearchConflict] = Field(default_factory=list)
    gaps: list[ResearchGap] = Field(default_factory=list)
    next_checks: list[ResearchNextCheck] = Field(default_factory=list)
    statement_provenance: list[ResearchStatementProvenance]

    @model_validator(mode="after")
    def require_aware_as_of(self):
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return self


class ResearchSnapshotVerificationIn(StrictResearchModel):
    verifier_worker_id: str = Field(min_length=1, max_length=200)
    draft: ResearchSnapshotDraftIn
    verifier_result: ResearchVerifierResult


class ResearchSnapshotSaveIn(ResearchSnapshotDraftIn):
    verification_run_id: int = Field(ge=1)


class ResearchSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    company_profile_id: int
    agent_run_id: int
    verification_run_id: int
    version: int
    contract_version: Literal["research-snapshot-v1", "research-snapshot-v2"]
    status: ResearchSnapshotStatus
    as_of: datetime
    input_fingerprint: str
    artifact_fingerprint: str
    sections: ResearchSections
    source_manifest: list[ResearchSourceManifestItem]
    conflicts: list[ResearchConflict]
    gaps: list[ResearchGap]
    next_checks: list[ResearchNextCheck]
    statement_provenance: list[ResearchStatementProvenance]
    verifier_result: ResearchVerifierResult
    created_at: datetime


class ResearchSnapshotHistoryOut(BaseModel):
    id: int
    version: int
    status: ResearchSnapshotStatus
    as_of: datetime
    profile_version: int
    created_at: datetime


class ArchetypeFocusMarkerOut(BaseModel):
    id: str
    label: str
    covered: bool
    state: Literal["sourced", "assumption", "gap", "missing"]


class ArchetypePackOut(BaseModel):
    id: str
    version: str
    label: str
    required_markers: list[ArchetypeFocusMarkerOut]
    covered_markers: list[str]
    sourced_markers: list[str]
    assumption_markers: list[str]
    gap_markers: list[str]
    missing_markers: list[str]
    sourced_count: int
    assumption_count: int
    gap_count: int
    missing_count: int
    coverage_count: int
    coverage_pct: float


class ResearchCaseWorkspaceOut(BaseModel):
    research_case: ResearchCaseSummaryOut
    profile: CompanyProfileOut | None
    latest_snapshot: ResearchSnapshotOut | None
    history: list[ResearchSnapshotHistoryOut]
    archetype_pack: ArchetypePackOut | None = None


class ResearchCaseStepHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    from_state: CaseState | None
    from_step: CaseStep | None
    to_state: CaseState
    to_step: CaseStep
    reason: str
    changed_by: str | None
    created_at: datetime


AssumptionScenarioKind = Literal["negative", "base", "positive", "event"]
AssumptionStatus = Literal["draft", "approved", "rejected"]
AssumptionProvenance = Literal["evidence", "human_assumption", "model_suggestion"]


class AssumptionItemIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: Any
    unit: str | None = Field(default=None, max_length=40)
    provenance: AssumptionProvenance
    source_ref: str | None = Field(default=None, max_length=240)
    rationale: str = Field(min_length=1, max_length=1000)


class AssumptionSetCreateIn(BaseModel):
    scenario_kind: AssumptionScenarioKind
    label: str = Field(min_length=1, max_length=120)
    status: AssumptionStatus = "draft"
    as_of: datetime | None = None
    assumptions: list[AssumptionItemIn] = Field(max_length=30)


class AssumptionSetUpdateIn(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    status: AssumptionStatus | None = None
    as_of: datetime | None = None
    assumptions: list[AssumptionItemIn] | None = Field(default=None, max_length=30)


class AssumptionSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    scenario_kind: AssumptionScenarioKind
    label: str
    status: AssumptionStatus
    as_of: datetime | None
    assumptions: list[AssumptionItemIn]
    created_by: str | None
    created_at: datetime
    updated_at: datetime


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


class DiscoverySieveFactorCoverageOut(BaseModel):
    id: str
    label: str
    covered_count: int
    total_count: int


class DiscoverySieveRuleOut(BaseModel):
    factor_id: str
    label: str
    operator: Literal["gte"]
    threshold: float


class DiscoverySieveSourceOut(BaseModel):
    name: str
    version: str
    document_version_id: int
    parser_version: str
    as_of: datetime


class DiscoverySieveOut(BaseModel):
    id: str
    version: str
    title: str
    question: str
    status: Literal["available", "blocked"]
    universe_count: int
    candidate_count: int
    coverage_count: int
    coverage_pct: float
    selection_rules: list[DiscoverySieveRuleOut]
    factor_coverage: list[DiscoverySieveFactorCoverageOut]
    source: DiscoverySieveSourceOut | None = None
    gaps: list[str]


class DiscoveryOut(BaseModel):
    source: str
    source_url: str
    as_of: datetime
    universe_count: int
    result_count: int
    source_note: str
    source_version_id: int
    candidates: list[DiscoveryCandidateOut]
    sieves: list[DiscoverySieveOut]


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
    source_name: str | None
    series_key: str | None
    basis_version: str | None
    adjustment_status: str
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
    mode: Literal["qualitative", "priced"] = "qualitative"


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


class DriverAssumptionOut(AssumptionItemIn):
    """One approved input and the deterministic application decision."""

    applied: bool
    note: str


class ScenarioSensitivityRowOut(BaseModel):
    scenario_kind: AssumptionScenarioKind
    label: str
    baseline_target_price: float | None
    sensitivity_target_price: float | None
    target_price_delta: float | None
    baseline_upside_pct: float | None
    sensitivity_upside_pct: float | None
    upside_delta_pct: float | None
    applied: list[DriverAssumptionOut] = Field(default_factory=list)
    ignored: list[DriverAssumptionOut] = Field(default_factory=list)


class ScenarioDriverSensitivityOut(BaseModel):
    status: Literal["none", "applied", "human_review_required"]
    note: str
    rows: list[ScenarioSensitivityRowOut] = Field(default_factory=list)


class PricedOutcomeGateOut(BaseModel):
    status: Literal["blocked", "approved"]
    reason: str
    required_checks: list[str] = Field(default_factory=list)
    verification: dict | None = None
    input_fingerprint: str | None = None


class SimulationVerificationCheckOut(BaseModel):
    id: str
    verdict: Literal["pass", "fail", "needs-human"]
    evidence: str


class SimulationVerificationOut(BaseModel):
    status: Literal["failed", "math_passed", "needs-human"]
    checks: list[SimulationVerificationCheckOut] = Field(default_factory=list)
    summary: str
    strict_verification_required: bool = True


class OperatingBridgeRowOut(BaseModel):
    scenario_kind: AssumptionScenarioKind
    label: str
    baseline_target_price: float | None
    operating_target_price: float | None
    target_price_delta: float | None
    operating_upside_pct: float | None
    projected_revenue: float | None
    projected_gross_margin_pct: float | None
    projected_net_profit: float | None
    projected_eps: float | None
    projected_ebitda: float | None
    projected_depreciation: float | None
    projected_fcf: float | None
    fcf_gap: str | None
    applied: list[DriverAssumptionOut] = Field(default_factory=list)
    ignored: list[DriverAssumptionOut] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class OperatingBridgeOut(BaseModel):
    status: Literal["none", "applied", "needs_human", "unsupported_template"]
    template: dict | None
    note: str
    rows: list[OperatingBridgeRowOut] = Field(default_factory=list)
    cash_conversion: dict
    fcf_lens: dict


class ScenarioSetOut(BaseModel):
    """The scenario set for one stock (services/scenarios.py). Framed as an
    entrance to analysis; carries a set-level probability-weighted EV."""

    scenarios: list[ScenarioOut]
    valuation_multiple: str  # cz | cwk | ev_ebitda
    current_price: float | None  # PLN
    weighted_expected_price: float | None  # PLN, Σ pᵢ·target_priceᵢ
    weighted_expected_upside_pct: float | None
    priced_probability_mass: float | None = None
    framing: str  # fixed "punkt wejścia w analizę, nie sygnał"
    disclaimer: str
    quality_warnings: list[str] = Field(default_factory=list)
    # Approved case inputs are shown as context only until RT4.3b wires them
    # into operating equations. Keeping the full provenance-bearing contract
    # here prevents sourced facts and human/model assumptions from collapsing
    # into one unlabeled number.
    approved_assumption_sets: list[AssumptionSetOut] = Field(default_factory=list)
    driver_sensitivity: ScenarioDriverSensitivityOut = Field(
        default_factory=lambda: ScenarioDriverSensitivityOut(
            status="none",
            note="Brak zatwierdzonych zestawów sterowników do policzenia wrażliwości.",
        )
    )
    operating_bridge: OperatingBridgeOut = Field(
        default_factory=lambda: OperatingBridgeOut(
            status="none",
            template=None,
            note="Brak projekcji operacyjnej.",
            cash_conversion={"status": "needs_human", "gaps": []},
            fcf_lens={
                "status": "none",
                "method": "FCF/share × jawny mnożnik FCF",
                "note": "Brak soczewki FCF.",
                "rows": [],
            },
        )
    )
    priced_operating_outcomes: PricedOutcomeGateOut = Field(
        default_factory=lambda: PricedOutcomeGateOut(
            status="blocked",
            reason="Brak zapisanego wyniku verifier_strict dla priced outcomes.",
        )
    )
    simulation_verification: SimulationVerificationOut = Field(
        default_factory=lambda: SimulationVerificationOut(
            status="needs-human",
            summary="Brak wyniku deterministycznej kontroli symulacji.",
        )
    )
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
    lease_owner: str | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    available_at: datetime | None
    attempt_count: int
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
    available_at: datetime | None = None
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


class ResearchLabCreateOut(BaseModel):
    research_case: ResearchCaseSummaryOut
    agent_run: AgentRunOut
    created_company: bool
    created_case: bool
    reactivated_case: bool
    created_job: bool


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
    output_contract_version: str
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
