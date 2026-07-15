"""Pydantic DTOs — request/response contracts for the API.

Kept in one module on purpose (small app); split by domain if it outgrows ~300
lines. `from_attributes=True` lets a schema be built straight from an ORM
object, like AutoMapper-lite.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CaseState = Literal[
    "new",
    "ingesting",
    "data_review",
    "business_model",
    "thesis",
    "scenarios",
    "review",
    "monitoring",
    "blocked",
    "closed",
]
CaseStep = Literal[
    "ingest",
    "data_review",
    "business_model",
    "thesis",
    "scenarios",
    "review",
    "monitoring",
]


class PortfolioPerformanceOut(BaseModel):
    """One enforced deterministic provider-history performance contract."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    version: Literal["portfolio-performance-v1"]
    provider_return_basis: Literal["provider-reported"]
    benchmark_basis: Literal[
        "provider-reported; total-return basis unverified"
    ]
    twr_status: Literal["complete", "partial", "unavailable"]
    twr_pct: float | None
    twr_method: Literal["flow-adjusted daily compound"]
    xirr_status: Literal["complete", "partial", "unavailable"]
    xirr_pct: float | None
    xirr_method: Literal[
        "dated opening value + contribution changes + terminal value"
    ]
    flow_timing: Literal["end-of-day"]
    day_count: Literal["actual/365"]
    window_start: date | None
    window_end: date | None
    terminal_date: date
    terminal_value: float = Field(ge=0)
    observation_count: int = Field(ge=0)
    external_flow_count: int = Field(ge=0)
    gaps: list[str]


class PortfolioWorkspaceOut(BaseModel):
    """Top-level Portfolio read model with enforced performance semantics."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    provider: str
    portfolio_label: str | None
    latest_sync: dict[str, Any] | None
    last_sync_failure: dict[str, Any] | None
    snapshot: dict[str, Any] | None
    positions: list[dict[str, Any]]
    reconciliation: dict[str, Any] | None
    concentration: dict[str, Any] | None
    history: list[dict[str, Any]]
    history_quality: dict[str, Any] | None
    liquidity: list[dict[str, Any]]
    scenario_sensitivity: dict[str, Any] | None
    risk_context: dict[str, Any] | None
    performance_methods: PortfolioPerformanceOut | None
    coverage: dict[str, Any]
    portfolio_review: dict[str, Any]


class PortfolioSyncWorkspaceOut(PortfolioWorkspaceOut):
    sync: dict[str, Any]


class PortfolioMappingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    provider_key: str
    mapping_kind: str
    mapping_status: str
    company_id: int | None
    reason: str


class DiscoveryResearchOriginIn(BaseModel):
    """A typed, server-recomputed handoff from the one Discover sieve."""

    model_config = ConfigDict(extra="forbid")

    batch_id: int = Field(gt=0)
    sieve_id: Literal["workbench_sieve_v1"]
    sieve_version: Literal["workbench-sieve-v1"]


class ResearchLabCreateIn(BaseModel):
    """Create or reopen the durable research identity for one ticker."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=12)
    discovery: DiscoveryResearchOriginIn | None = None


class ResearchCollectionProgressOut(BaseModel):
    state: Literal["waiting", "collecting", "attention"]
    summary: str
    completed_sources: list[str] = Field(default_factory=list)
    remaining_sources: list[str] = Field(default_factory=list)
    percent: int | None = Field(default=None, ge=0, le=100)


class ResearchValuationStripOut(BaseModel):
    scenario_prices_pln: dict[str, float | None]
    scenario_probabilities_pct: dict[str, float]
    price_range_pln: list[float] | None
    weighted_value_pln: float | None
    current_price_pln: float | None
    upside_pct: float | None
    catalyst: str | None
    verification_status: str
    as_of: datetime


class ResearchCaseSummaryOut(BaseModel):
    """Phase-aware Research row; queue metadata belongs in the audit path."""

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
    phase: Literal["collecting", "researched", "valued"]
    phase_label: str
    phase_summary: str
    main_gap: str | None
    agenda_reasons: list[str] = Field(default_factory=list)
    collection_progress: ResearchCollectionProgressOut | None
    valuation_strip: ResearchValuationStripOut | None
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
    schema_version: Literal["company-profile-v2"] = "company-profile-v2"
    version: int = Field(ge=1)
    archetype: ResearchArchetype
    archetype_version: str = Field(min_length=1, max_length=40)
    company_overlay: CompanyOverlay
    drivers: list[ResearchDriver] = Field(min_length=1)
    kpis: list[ResearchKpi] = Field(min_length=1)


class CompanyProfileCorrectionIn(StrictResearchModel):
    """Human-owned successor to the current immutable company profile."""

    base_profile_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)
    archetype: ResearchArchetype
    company_overlay: CompanyOverlay
    drivers: list[ResearchDriver] = Field(min_length=1)
    kpis: list[ResearchKpi] = Field(min_length=1)


class CompanyProfileOut(CompanyProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    provenance: Literal["codex-proposed", "human-confirmed", "human-corrected"]
    reason: str | None
    based_on_profile_id: int | None
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
            raise ValueError(
                "calculation, assumption and unknown claims require a named basis"
            )
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


ResearchSourceChannel = Literal[
    "issuer-primary",
    "regulatory-primary",
    "biznesradar",
    "portalanaliz",
    "other-web",
]
ResearchResolutionStatus = Literal[
    "confirmed",
    "partial",
    "not_found",
    "not_applicable",
]
ResearchOutlookDirection = Literal[
    "positive",
    "neutral",
    "negative",
    "mixed",
    "unknown",
]


class ResearchSourceSearch(StrictResearchModel):
    """One required source-channel attempt in the bounded completion loop."""

    channel: ResearchSourceChannel
    status: Literal["found", "not_found", "unavailable"]
    summary: str = Field(min_length=1, max_length=2000)
    document_version_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_found_source(self):
        if len(self.document_version_ids) != len(set(self.document_version_ids)):
            raise ValueError("source-search document versions must be unique")
        if self.status == "found" and not self.document_version_ids:
            raise ValueError("a found source search requires a document version")
        if self.status != "found" and self.document_version_ids:
            raise ValueError(
                "a not-found or unavailable source search cannot cite document versions"
            )
        return self


class ResearchOutlookAssessment(StrictResearchModel):
    direction: ResearchOutlookDirection
    assessment: ResearchClaim
    source_channels: list[ResearchSourceChannel] = Field(min_length=1)
    watch_items: list[str] = Field(min_length=1)
    gap_topic: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def keep_unknown_direction_explicit(self):
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("outlook-assessment source channels must be unique")
        if self.direction == "unknown" and self.assessment.kind != "unknown":
            raise ValueError("an unknown outlook direction requires an unknown claim")
        if self.direction == "unknown" and not self.gap_topic:
            raise ValueError("an unknown outlook direction requires a named gap")
        if self.direction != "unknown" and self.assessment.kind == "unknown":
            raise ValueError("a known outlook direction cannot use an unknown claim")
        if self.direction != "unknown" and self.gap_topic is not None:
            raise ValueError("a known outlook direction cannot point to an unknown gap")
        if self.assessment.kind == "lead":
            raise ValueError("a lead cannot become a directional outlook conclusion")
        return self


class ResearchDriverOutlook(StrictResearchModel):
    driver_key: str = Field(min_length=1, max_length=80)
    next_quarter: ResearchOutlookAssessment
    next_12_months: ResearchOutlookAssessment


class ResearchQuestionResolution(StrictResearchModel):
    scope: Literal["profile", "catalyst", "visibility", "governance"]
    question: str = Field(min_length=1, max_length=1000)
    status: ResearchResolutionStatus
    answer: ResearchClaim
    source_channels: list[ResearchSourceChannel] = Field(min_length=1)
    remaining_gap: str | None = Field(default=None, max_length=2000)
    gap_topic: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def preserve_resolution_certainty(self):
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("question-resolution source channels must be unique")
        if self.status == "confirmed":
            if self.answer.kind not in {"fact", "calculation"}:
                raise ValueError("a confirmed answer must be a fact or calculation")
            if self.remaining_gap is not None:
                raise ValueError("a confirmed answer cannot retain a remaining gap")
            if self.gap_topic is not None:
                raise ValueError("a confirmed answer cannot point to a gap")
        elif self.status == "partial":
            if self.answer.kind not in {"fact", "calculation"}:
                raise ValueError("a partial answer requires a fact or calculation")
            if not self.remaining_gap:
                raise ValueError("a partial answer requires a remaining gap")
            if not self.gap_topic:
                raise ValueError("a partial answer requires a named gap")
        elif self.status == "not_found":
            if self.answer.kind != "unknown":
                raise ValueError("a not-found answer requires an unknown claim")
            if not self.remaining_gap:
                raise ValueError("a not-found answer requires a remaining gap")
            if not self.gap_topic:
                raise ValueError("a not-found answer requires a named gap")
        elif self.status == "not_applicable":
            if self.answer.kind not in {"fact", "calculation"}:
                raise ValueError(
                    "a not-applicable answer requires a sourced fact or calculation"
                )
            if self.remaining_gap is not None:
                raise ValueError("a not-applicable answer cannot retain a gap")
            if self.gap_topic is not None:
                raise ValueError("a not-applicable answer cannot point to a gap")
        return self


class ResearchOutlookSection(StrictResearchModel):
    summary: str = Field(min_length=1, max_length=6000)
    driver_outlooks: list[ResearchDriverOutlook] = Field(min_length=1)
    question_resolutions: list[ResearchQuestionResolution] = Field(min_length=3)
    source_searches: list[ResearchSourceSearch] = Field(min_length=5)
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
    outlook: ResearchOutlookSection | None = None
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


class ResearchVerifierFinding(StrictResearchModel):
    severity: Literal["minor", "major", "blocking"]
    area: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=20, max_length=2000)


class ResearchVerifierJustifications(StrictResearchModel):
    evidence_and_claim_fit: str = Field(min_length=60, max_length=3000)
    company_specificity: str = Field(min_length=60, max_length=3000)
    outlook_and_thesis_plausibility: str = Field(min_length=60, max_length=3000)


class ResearchVerifierResult(StrictResearchModel):
    model_role: Literal["verifier_strict"] = "verifier_strict"
    verifier_model: str = Field(min_length=1, max_length=80)
    verdict: Literal["pass", "fail", "needs-human"]
    findings: list[ResearchVerifierFinding] = Field(default_factory=list, max_length=20)
    justifications: ResearchVerifierJustifications
    summary: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_adversarial_contract(self):
        blocking = [item for item in self.findings if item.severity in {"major", "blocking"}]
        if self.verdict == "pass" and blocking:
            raise ValueError("a passing verdict cannot carry major/blocking findings")
        if self.verdict == "fail" and not self.findings:
            raise ValueError("a failing verdict must name concrete findings")
        return self


class ResearchVerifierResultOut(ResearchVerifierResult):
    """Canonical V5 verifier evidence attached to a readable snapshot."""

    verification_standard: Literal["adversarial-v1"] = "adversarial-v1"


class ResearchSnapshotDraftIn(StrictResearchModel):
    contract_version: Literal["research-snapshot-v3"] = "research-snapshot-v3"
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
        if self.sections.outlook is None:
            raise ValueError("research-snapshot-v3 requires an outlook section")
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
    contract_version: Literal["research-snapshot-v3"]
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
    verifier_result: ResearchVerifierResultOut
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
    # Profile bound to latest_snapshot (or the only profile before first save).
    profile: CompanyProfileOut | None
    # Latest human/model understanding; it can intentionally be newer than the
    # profile bound to latest_snapshot while an explicit review is pending.
    current_profile: CompanyProfileOut | None
    profile_history: list[CompanyProfileOut]
    latest_snapshot: ResearchSnapshotOut | None
    history: list[ResearchSnapshotHistoryOut]
    archetype_pack: ArchetypePackOut | None = None


# -------------------------------------------------------------- valuation

ValuationScenarioKind = Literal["negative", "base", "positive", "event"]
ValuationStatus = Literal["provisional", "verified", "rejected", "needs-human"]


class ValuationAssumptionValue(StrictResearchModel):
    value: float
    basis: Literal[
        "reported_fact",
        "street_estimate",
        "codex_judgment",
        "human_override",
    ]
    rationale: str = Field(min_length=1, max_length=1000)
    source_fact_ids: list[int] = Field(default_factory=list)
    research_claim_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provenance(self):
        from math import isfinite

        if not isfinite(self.value):
            raise ValueError("assumption values must be finite")
        if self.basis in {"reported_fact", "street_estimate"} and not self.source_fact_ids:
            raise ValueError("reported/street assumptions require source_fact_ids")
        if self.basis == "human_override" and self.source_fact_ids:
            raise ValueError("human overrides cannot claim source_fact_ids")
        return self


class ValuationForecastYear(StrictResearchModel):
    period: str = Field(pattern=r"^\d{4}$")
    revenue_pln_thousands: ValuationAssumptionValue
    ebitda_margin_pct: ValuationAssumptionValue
    depreciation_pct_revenue: ValuationAssumptionValue
    capex_pct_revenue: ValuationAssumptionValue
    delta_nwc_pct_revenue: ValuationAssumptionValue
    cash_tax_rate_pct: ValuationAssumptionValue
    net_financial_result_pct_revenue: ValuationAssumptionValue
    # DCF timing is explicit because a fiscal-year forecast may be partly elapsed
    # at the valuation cutoff.  The first value scales annual FCFF to the
    # remaining stub; the second is the year-end discount exponent from as_of.
    fcff_period_fraction: ValuationAssumptionValue
    fcff_discount_years: ValuationAssumptionValue

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.revenue_pln_thousands.value <= 0:
            raise ValueError("forecast revenue must be positive")
        if not -100 <= self.ebitda_margin_pct.value <= 100:
            raise ValueError("EBITDA margin must be bounded to -100..100%")
        if not 0 <= self.depreciation_pct_revenue.value <= 100:
            raise ValueError("depreciation ratio must be 0..100%")
        if not 0 <= self.capex_pct_revenue.value <= 100:
            raise ValueError("capex ratio must be 0..100%")
        if not -100 <= self.delta_nwc_pct_revenue.value <= 100:
            raise ValueError("delta NWC ratio must be bounded to -100..100%")
        if not 0 <= self.cash_tax_rate_pct.value <= 100:
            raise ValueError("cash tax rate must be 0..100%")
        if not -100 <= self.net_financial_result_pct_revenue.value <= 100:
            raise ValueError("net financial result ratio must be bounded to -100..100%")
        if not 0 < self.fcff_period_fraction.value <= 1:
            raise ValueError("FCFF period fraction must be in (0, 1]")
        if not 0 < self.fcff_discount_years.value <= 10:
            raise ValueError("FCFF discount timing must be in (0, 10] years")
        return self


class ValuationEventImpact(StrictResearchModel):
    period: str = Field(pattern=r"^\d{4}$")
    recurring: Literal[False] = False
    pnl_net_pln_thousands: ValuationAssumptionValue
    cash_pln_thousands: ValuationAssumptionValue


class ValuationPotentialDriverImpact(StrictResearchModel):
    """One driver's explicit contribution to a year-on-year forecast change.

    Nullable fields are still required in the JSON contract. ``None`` means
    that the driver does not affect that line in the period; it is not a
    hidden zero or a template seed (VISION V4).
    """

    period: str = Field(pattern=r"^\d{4}$")
    revenue_delta_pln_thousands: ValuationAssumptionValue | None
    ebitda_margin_delta_pp: ValuationAssumptionValue | None
    depreciation_pct_revenue_delta_pp: ValuationAssumptionValue | None
    capex_pct_revenue_delta_pp: ValuationAssumptionValue | None
    delta_nwc_pct_revenue_delta_pp: ValuationAssumptionValue | None
    cash_tax_rate_delta_pp: ValuationAssumptionValue | None
    net_financial_result_pct_revenue_delta_pp: ValuationAssumptionValue | None


class ValuationPotentialDriver(StrictResearchModel):
    """Company-specific operating driver that reconciles to the forecast path."""

    driver_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    # This is an immutable foreign key into Research, not a new valuation slug.
    # It must accept every key allowed by ResearchDriver.key.
    research_driver_key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=3, max_length=120)
    mechanism: str = Field(min_length=30, max_length=2000)
    runway_evidence: str = Field(min_length=30, max_length=2000)
    capital_requirements: str = Field(min_length=30, max_length=2000)
    impacts: list[ValuationPotentialDriverImpact] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_material_impact(self):
        values = [
            value
            for impact in self.impacts
            for value in (
                impact.revenue_delta_pln_thousands,
                impact.ebitda_margin_delta_pp,
                impact.depreciation_pct_revenue_delta_pp,
                impact.capex_pct_revenue_delta_pp,
                impact.delta_nwc_pct_revenue_delta_pp,
                impact.cash_tax_rate_delta_pp,
                impact.net_financial_result_pct_revenue_delta_pp,
            )
            if value is not None
        ]
        if not values:
            raise ValueError(
                "a potential driver must declare at least one explicit impact, including an evidenced zero when dormant"
            )
        return self


class ValuationScenarioAssumptions(StrictResearchModel):
    kind: ValuationScenarioKind
    label: str = Field(min_length=1, max_length=120)
    forecast_years: list[ValuationForecastYear] = Field(min_length=5, max_length=5)
    potential_drivers: list[ValuationPotentialDriver] = Field(min_length=1, max_length=4)
    # Optional methods are still explicit inputs.  ``None`` means "method not
    # available for this scenario"; omitting a field must never seed a hidden
    # default (VISION V4).
    target_pe: ValuationAssumptionValue | None
    target_ev_ebitda: ValuationAssumptionValue | None
    target_ev_ebit: ValuationAssumptionValue | None
    target_net_debt_pln_thousands: ValuationAssumptionValue | None
    cumulative_capital_allocation_pln_thousands: ValuationAssumptionValue | None
    wacc_pct: ValuationAssumptionValue | None
    terminal_growth_pct: ValuationAssumptionValue | None
    terminal_reinvestment_rate_pct: ValuationAssumptionValue | None
    terminal_incremental_roic_pct: ValuationAssumptionValue | None
    event_impact: ValuationEventImpact | None

    @model_validator(mode="after")
    def validate_ranges(self):
        years = [int(row.period) for row in self.forecast_years]
        if years != list(range(years[0], years[0] + 5)):
            raise ValueError("forecast years must be five sequential fiscal periods")
        fractions = [row.fcff_period_fraction.value for row in self.forecast_years]
        if any(abs(value - 1.0) > 1e-6 for value in fractions[1:]):
            raise ValueError("only the first DCF forecast period may be a stub")
        timings = [row.fcff_discount_years.value for row in self.forecast_years]
        if timings[0] > 1.25 or any(
            not 0.75 <= later - earlier <= 1.25
            for earlier, later in zip(timings, timings[1:])
        ):
            raise ValueError(
                "DCF timings must start within 1.25 years and advance by about one year"
            )
        driver_ids = [row.driver_id for row in self.potential_drivers]
        if len(driver_ids) != len(set(driver_ids)):
            raise ValueError("potential driver IDs must be unique within a scenario")
        research_driver_keys = [
            row.research_driver_key for row in self.potential_drivers
        ]
        if len(research_driver_keys) != len(set(research_driver_keys)):
            raise ValueError(
                "a frozen Research driver may underwrite only one potential driver per scenario"
            )
        expected_impact_periods = [row.period for row in self.forecast_years]
        for driver in self.potential_drivers:
            impact_periods = [row.period for row in driver.impacts]
            if impact_periods != expected_impact_periods:
                raise ValueError(
                    "potential driver impacts must cover all five forecast periods in order"
                )
        reconciliations = (
            ("revenue_pln_thousands", "revenue_delta_pln_thousands", 0.02),
            ("ebitda_margin_pct", "ebitda_margin_delta_pp", 0.0001),
            (
                "depreciation_pct_revenue",
                "depreciation_pct_revenue_delta_pp",
                0.0001,
            ),
            ("capex_pct_revenue", "capex_pct_revenue_delta_pp", 0.0001),
            ("delta_nwc_pct_revenue", "delta_nwc_pct_revenue_delta_pp", 0.0001),
            ("cash_tax_rate_pct", "cash_tax_rate_delta_pp", 0.0001),
            (
                "net_financial_result_pct_revenue",
                "net_financial_result_pct_revenue_delta_pp",
                0.0001,
            ),
        )
        for index, current in enumerate(self.forecast_years[1:], start=1):
            previous = self.forecast_years[index - 1]
            for forecast_field, impact_field, tolerance in reconciliations:
                forecast_change = (
                    getattr(current, forecast_field).value
                    - getattr(previous, forecast_field).value
                )
                driver_change = sum(
                    value.value
                    for driver in self.potential_drivers
                    for impact in driver.impacts
                    if impact.period == current.period
                    and (value := getattr(impact, impact_field)) is not None
                )
                if abs(forecast_change - driver_change) > tolerance:
                    raise ValueError(
                        f"potential drivers do not reconcile {forecast_field} for {current.period}: "
                        f"forecast change {forecast_change} vs driver sum {driver_change}"
                    )
        for name in ("target_pe", "target_ev_ebitda", "target_ev_ebit", "wacc_pct"):
            value = getattr(self, name)
            if value is not None and value.value <= 0:
                raise ValueError(f"{name} must be positive")
        net_debt_bridge = (
            self.target_net_debt_pln_thousands,
            self.cumulative_capital_allocation_pln_thousands,
        )
        if any(value is not None for value in net_debt_bridge) and not all(
            value is not None for value in net_debt_bridge
        ):
            raise ValueError(
                "target net debt and cumulative capital allocation must be explicit together"
            )
        if (
            self.target_ev_ebitda is not None or self.target_ev_ebit is not None
        ) and not all(value is not None for value in net_debt_bridge):
            raise ValueError(
                "future EV methods require an explicit target-net-debt rollforward"
            )
        dcf_values = (
            self.wacc_pct,
            self.terminal_growth_pct,
            self.terminal_reinvestment_rate_pct,
            self.terminal_incremental_roic_pct,
        )
        if any(value is not None for value in dcf_values) and not all(
            value is not None for value in dcf_values
        ):
            raise ValueError(
                "DCF requires WACC, terminal growth, terminal reinvestment and incremental ROIC together"
            )
        if all(value is not None for value in dcf_values):
            assert self.wacc_pct is not None
            assert self.terminal_growth_pct is not None
            assert self.terminal_reinvestment_rate_pct is not None
            assert self.terminal_incremental_roic_pct is not None
            if self.wacc_pct.value <= self.terminal_growth_pct.value:
                raise ValueError("WACC must be above terminal growth")
            if not -100 <= self.terminal_reinvestment_rate_pct.value <= 100:
                raise ValueError("terminal reinvestment rate must be bounded to -100..100%")
            if self.terminal_incremental_roic_pct.value <= 0:
                raise ValueError("terminal incremental ROIC must be positive")
            sustainable_growth = (
                self.terminal_reinvestment_rate_pct.value
                * self.terminal_incremental_roic_pct.value
                / 100.0
            )
            if abs(sustainable_growth - self.terminal_growth_pct.value) > 0.05:
                raise ValueError(
                    "terminal growth must reconcile to reinvestment rate x incremental ROIC"
                )
        if self.kind != "event" and self.event_impact is not None:
            raise ValueError("event impact is allowed only in the event scenario")
        if self.kind == "event" and self.event_impact is None:
            raise ValueError("event scenario requires an explicit non-recurring impact")
        if self.event_impact is not None and self.event_impact.period not in {
            row.period for row in self.forecast_years
        }:
            raise ValueError("event impact period must exist in the forecast horizon")
        return self


ValuationMethod = Literal["pe", "ev_ebitda", "ev_ebit", "fcff_dcf"]


class ValuationMethodology(StrictResearchModel):
    primary_method: ValuationMethod
    cross_checks: list[ValuationMethod] = Field(min_length=1, max_length=3)
    valuation_period: str = Field(pattern=r"^\d{4}$")
    rationale: str = Field(min_length=30, max_length=2000)

    @model_validator(mode="after")
    def validate_methods(self):
        if self.primary_method in self.cross_checks:
            raise ValueError("primary method cannot also be a cross-check")
        if len(set(self.cross_checks)) != len(self.cross_checks):
            raise ValueError("cross-check methods must be unique")
        families = {
            "pe": "relative",
            "ev_ebitda": "relative",
            "ev_ebit": "relative",
            "fcff_dcf": "intrinsic",
        }
        selected = [self.primary_method, *self.cross_checks]
        if len({families[item] for item in selected}) < 2:
            raise ValueError("methodology requires relative and intrinsic method families")
        return self


def _validate_shared_valuation_horizon(
    assumptions: list[ValuationScenarioAssumptions],
    methodology: ValuationMethodology,
    as_of: datetime,
) -> None:
    """Keep scenario prices and runway comparisons on one explicit clock."""

    kinds = [scenario.kind for scenario in assumptions]
    if len(kinds) != len(set(kinds)) or not {
        "negative",
        "base",
        "positive",
    }.issubset(kinds):
        raise ValueError(
            "valuation requires unique negative, base and positive scenarios"
        )
    grids = {
        (
            tuple(year.period for year in scenario.forecast_years),
            tuple(
                round(year.fcff_period_fraction.value, 6)
                for year in scenario.forecast_years
            ),
            tuple(
                round(year.fcff_discount_years.value, 6)
                for year in scenario.forecast_years
            ),
        )
        for scenario in assumptions
    }
    if len(grids) != 1:
        raise ValueError(
            "all scenarios must share forecast periods, FCFF fractions and discount timings"
        )
    periods = next(iter(grids))[0]
    if methodology.valuation_period not in periods:
        raise ValueError("valuation period must exist in the shared forecast horizon")
    if any(scenario.kind == "event" for scenario in assumptions) and (
        methodology.primary_method != "fcff_dcf"
    ):
        raise ValueError(
            "an optional non-recurring event scenario requires FCFF DCF as the primary method"
        )
    driver_sets = [
        {driver.driver_id for driver in scenario.potential_drivers}
        for scenario in assumptions
    ]
    if len({tuple(sorted(driver_ids)) for driver_ids in driver_sets}) != 1:
        raise ValueError("all scenarios must use the same potential driver IDs")
    for driver_id in driver_sets[0]:
        labels = {
            driver.label.strip().casefold()
            for scenario in assumptions
            for driver in scenario.potential_drivers
            if driver.driver_id == driver_id
        }
        research_keys = {
            driver.research_driver_key
            for scenario in assumptions
            for driver in scenario.potential_drivers
            if driver.driver_id == driver_id
        }
        if len(labels) != 1 or len(research_keys) != 1:
            raise ValueError(
                f"potential driver {driver_id} must keep one label and Research key across scenarios"
            )
    base = assumptions[kinds.index("base")]
    anchor_fields = (
        ("revenue_pln_thousands", "revenue_delta_pln_thousands", 0.02),
        ("ebitda_margin_pct", "ebitda_margin_delta_pp", 0.0001),
        (
            "depreciation_pct_revenue",
            "depreciation_pct_revenue_delta_pp",
            0.0001,
        ),
        ("capex_pct_revenue", "capex_pct_revenue_delta_pp", 0.0001),
        ("delta_nwc_pct_revenue", "delta_nwc_pct_revenue_delta_pp", 0.0001),
        ("cash_tax_rate_pct", "cash_tax_rate_delta_pp", 0.0001),
        (
            "net_financial_result_pct_revenue",
            "net_financial_result_pct_revenue_delta_pp",
            0.0001,
        ),
    )
    base_anchor = base.forecast_years[0]
    for scenario in assumptions:
        values = [
            value
            for driver in scenario.potential_drivers
            for impact in driver.impacts
            for value in (
                impact.revenue_delta_pln_thousands,
                impact.ebitda_margin_delta_pp,
                impact.depreciation_pct_revenue_delta_pp,
                impact.capex_pct_revenue_delta_pp,
                impact.delta_nwc_pct_revenue_delta_pp,
                impact.cash_tax_rate_delta_pp,
                impact.net_financial_result_pct_revenue_delta_pp,
            )
            if value is not None
        ]
        if scenario.kind in {"negative", "base", "positive"} and not any(
            abs(value.value) > 0.0001 for value in values
        ):
            raise ValueError(
                f"core scenario {scenario.kind} requires a non-zero operating-driver contribution"
            )
        anchor = scenario.forecast_years[0]
        for forecast_field, impact_field, tolerance in anchor_fields:
            expected = (
                getattr(anchor, forecast_field).value
                - getattr(base_anchor, forecast_field).value
            )
            bridged = sum(
                value.value
                for driver in scenario.potential_drivers
                for impact in driver.impacts
                if impact.period == anchor.period
                and (value := getattr(impact, impact_field)) is not None
            )
            if abs(expected - bridged) > tolerance:
                raise ValueError(
                    f"scenario {scenario.kind} anchor {forecast_field} does not reconcile to potential drivers"
                )
    anchor_year = int(periods[0])
    if not as_of.year <= anchor_year <= as_of.year + 1:
        raise ValueError(
            "forecast anchor must be the as-of fiscal year or the immediately following year"
        )


class ValuationRequestIn(StrictResearchModel):
    """Deterministic preview/override input: explicit assumption grid."""

    research_snapshot_id: int = Field(ge=1)
    assumptions: list[ValuationScenarioAssumptions] = Field(min_length=3, max_length=4)
    methodology: ValuationMethodology
    as_of: datetime

    @model_validator(mode="after")
    def validate_scenarios(self):
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        kinds = [row.kind for row in self.assumptions]
        if len(kinds) != len(set(kinds)):
            raise ValueError("scenario kinds must be unique")
        if set(kinds) - {"negative", "base", "positive", "event"}:
            raise ValueError("unsupported scenario kind")
        if not {"negative", "base", "positive"}.issubset(kinds):
            raise ValueError("negative, base and positive scenarios are required")
        _validate_shared_valuation_horizon(
            self.assumptions, self.methodology, self.as_of
        )
        return self


class ValuationScenarioJudgment(StrictResearchModel):
    """Drafter-owned, company-specific scenario judgment (VISION V4)."""

    kind: ValuationScenarioKind
    # Required even when unavailable: ``None`` is the explicit uncalibrated
    # posture, while a number must reconcile to the probability tree.
    probability_pct: float | None
    mechanism: str = Field(min_length=30, max_length=2000)
    catalyst_or_counter_driver: str = Field(min_length=1, max_length=1000)
    falsifier: str = Field(min_length=1, max_length=1000)
    gaps: list[str] = Field(default_factory=list)


class ValuationProbabilityNode(StrictResearchModel):
    node_id: str = Field(min_length=1, max_length=80)
    parent_id: str | None = Field(default=None, max_length=80)
    condition: str = Field(min_length=10, max_length=1000)
    conditional_probability_pct: float = Field(gt=0, lt=100)
    basis: Literal[
        "empirical_frequency",
        "forecast_distribution",
        "company_history",
        "judgment",
    ]
    numerator: int | None = Field(default=None, ge=0)
    denominator: int | None = Field(default=None, gt=0)
    source_fact_ids: list[int] = Field(default_factory=list)
    research_claim_paths: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=30, max_length=1000)
    scenario_kind: ValuationScenarioKind | None = None

    @model_validator(mode="after")
    def validate_empirical_basis(self):
        if self.basis == "empirical_frequency":
            if self.numerator is None or self.denominator is None:
                raise ValueError("empirical probability requires numerator/denominator")
            expected = self.numerator / self.denominator * 100.0
            if abs(expected - self.conditional_probability_pct) > 0.05:
                raise ValueError("empirical probability does not reconcile to its sample")
        return self


class ValuationReliabilityBin(StrictResearchModel):
    lower_probability_pct: float = Field(ge=0, le=100)
    upper_probability_pct: float = Field(ge=0, le=100)
    sample_count: int = Field(ge=1)
    predicted_mean_pct: float = Field(ge=0, le=100)
    observed_frequency_pct: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_bin(self):
        if self.lower_probability_pct >= self.upper_probability_pct:
            raise ValueError("reliability-bin lower bound must be below upper bound")
        if not self.lower_probability_pct <= self.predicted_mean_pct <= self.upper_probability_pct:
            raise ValueError("predicted mean must fall inside its reliability bin")
        return self


class ValuationProbabilityModel(StrictResearchModel):
    posture: Literal[
        "uncalibrated",
        "judgmental_unvalidated",
        "empirical_calibrated",
    ]
    nodes: list[ValuationProbabilityNode] = Field(default_factory=list)
    dataset_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    brier_score: float | None = Field(default=None, ge=0)
    calibration_engine_version: Literal["probability-calibration-v1"] | None = None
    calibration_cutoff: datetime | None = None
    sample_size: int | None = Field(default=None, ge=30)
    reliability_bins: list[ValuationReliabilityBin] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_posture(self):
        if self.posture == "uncalibrated" and self.nodes:
            raise ValueError("uncalibrated probability model cannot publish percentages")
        if self.posture != "uncalibrated" and not self.nodes:
            raise ValueError("probability posture requires an auditable tree")
        if self.posture == "empirical_calibrated" and (
            not self.dataset_fingerprint
            or self.brier_score is None
            or self.calibration_engine_version is None
            or self.calibration_cutoff is None
            or self.sample_size is None
            or not self.reliability_bins
        ):
            raise ValueError(
                "calibrated posture requires dataset fingerprint, engine, cutoff, sample, Brier score and reliability bins"
            )
        if self.calibration_cutoff is not None and self.calibration_cutoff.tzinfo is None:
            raise ValueError("calibration cutoff must include timezone")
        return self


class ValuationDraftJudgment(StrictResearchModel):
    strategy_read: str = Field(min_length=1, max_length=4000)
    scenarios: list[ValuationScenarioJudgment] = Field(min_length=3, max_length=4)
    probability_model: ValuationProbabilityModel
    catalysts: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scenario_kinds(self):
        kinds = [row.kind for row in self.scenarios]
        if len(kinds) != len(set(kinds)):
            raise ValueError("judgment scenario kinds must be unique")
        probabilities = [row.probability_pct for row in self.scenarios]
        if self.probability_model.posture == "uncalibrated":
            if any(value is not None for value in probabilities):
                raise ValueError("uncalibrated posture cannot publish scenario percentages")
        else:
            if any(value is None for value in probabilities):
                raise ValueError("auditable probability trees require scenario percentages")
            if abs(sum(value for value in probabilities if value is not None) - 100.0) > 0.05:
                raise ValueError("scenario probabilities must sum to 100%")
        return self


class ValuationSnapshotDraftIn(StrictResearchModel):
    contract_version: Literal["valuation-snapshot-v3"] = "valuation-snapshot-v3"
    engine_version: Literal["valuation-engine-v4"] = "valuation-engine-v4"
    template_contract_version: Literal["valuation-templates-v3"] = (
        "valuation-templates-v3"
    )
    agent_run_id: int = Field(ge=1)
    lease_owner: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    research_snapshot_id: int = Field(ge=1)
    as_of: datetime
    template_id: str
    template_version: str
    assumptions: list[ValuationScenarioAssumptions]
    methodology: ValuationMethodology
    base_values: dict
    deterministic_outputs: dict
    input_manifest: dict
    gaps: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=64, max_length=64)
    calculation_fingerprint: str = Field(min_length=64, max_length=64)
    codex_judgment: ValuationDraftJudgment

    @model_validator(mode="after")
    def require_aware_as_of(self):
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        _validate_shared_valuation_horizon(
            self.assumptions, self.methodology, self.as_of
        )
        return self


class ValuationVerifierFinding(StrictResearchModel):
    severity: Literal["minor", "major", "blocking"]
    area: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=20, max_length=2000)


class ValuationJudgmentReview(StrictResearchModel):
    """Adversarial review of what cannot be computed (VISION V5).

    Each field must reference the evidence examined; empty confirmations are
    rejected by the artifact boundary.
    """

    evidence_fit: str = Field(min_length=60, max_length=3000)
    mechanism_plausibility: str = Field(min_length=60, max_length=3000)
    potential_underwrite: str = Field(min_length=60, max_length=3000)
    probability_reasonableness: str = Field(min_length=60, max_length=3000)


class ValuationVerifierResult(StrictResearchModel):
    model_role: Literal["verifier_strict"] = "verifier_strict"
    verifier_model: str = Field(min_length=1, max_length=80)
    verdict: Literal["pass", "fail", "needs-human"]
    findings: list[ValuationVerifierFinding] = Field(default_factory=list, max_length=20)
    judgment_review: ValuationJudgmentReview
    summary: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_adversarial_contract(self):
        blocking = [f for f in self.findings if f.severity in {"major", "blocking"}]
        if self.verdict == "pass" and blocking:
            raise ValueError(
                "a passing verdict cannot carry major/blocking findings"
            )
        if self.verdict == "fail" and not self.findings:
            raise ValueError("a failing verdict must name concrete findings")
        return self


class ValuationSnapshotVerificationIn(StrictResearchModel):
    verifier_worker_id: str = Field(min_length=1, max_length=200)
    draft: ValuationSnapshotDraftIn
    verifier_result: ValuationVerifierResult


class ValuationSnapshotSaveIn(ValuationSnapshotDraftIn):
    verification_run_id: int = Field(ge=1)


class ValuationQueueIn(StrictResearchModel):
    """Queue a Codex-drafted valuation: the drafter owns the assumptions."""

    research_snapshot_id: int | None = Field(default=None, ge=1)
    as_of: datetime | None = None

    @model_validator(mode="after")
    def require_aware_as_of(self):
        if self.as_of is not None and self.as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return self


class ValuationOverrideIn(ValuationRequestIn):
    """Human correction: explicit grid saved as a provisional override version."""

    note: str = Field(min_length=1, max_length=2000)


class ValuationSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    research_snapshot_id: int
    agent_run_id: int | None
    verification_run_id: int | None
    version: int
    contract_version: Literal["valuation-snapshot-v3"]
    status: ValuationStatus
    origin: Literal["codex", "human-override"]
    as_of: datetime
    template_id: str
    template_version: str
    calculation_engine_version: str
    assumptions: dict
    base_values: dict
    deterministic_outputs: dict
    codex_judgment: dict
    input_manifest: dict
    gaps: list[str]
    input_fingerprint: str
    calculation_fingerprint: str
    artifact_fingerprint: str
    verifier_result: dict
    created_at: datetime


class ValuationHistoryOut(BaseModel):
    id: int
    version: int
    status: ValuationStatus
    origin: str
    as_of: datetime
    template_id: str
    created_at: datetime


class ValuationWorkspaceOut(BaseModel):
    research_case_id: int
    latest_research_snapshot_id: int | None
    template: dict | None
    latest_valuation: ValuationSnapshotOut | None
    history: list[ValuationHistoryOut]


class PortfolioReviewSections(StrictResearchModel):
    summary: str = Field(min_length=1, max_length=2000)
    concentration: list[str] = Field(min_length=1, max_length=5)
    liquidity: list[str] = Field(min_length=1, max_length=5)
    history: list[str] = Field(min_length=1, max_length=5)
    scenario_exposure: list[str] = Field(min_length=1, max_length=5)
    risks: list[str] = Field(min_length=1, max_length=6)
    next_checks: list[str] = Field(min_length=1, max_length=3)


_UNAVAILABLE_HOST_MODELS = {
    "host deployment not exposed",
    "host model not exposed",
    "actual host model not exposed",
    "host deployment unavailable",
}


def _validate_model_provenance(
    requested_model: str,
    actual_host_model: str,
    substitution_or_escalation: str | None,
) -> None:
    requested = requested_model.strip().casefold()
    actual = actual_host_model.strip().casefold()
    substitution = (substitution_or_escalation or "").strip()
    if not requested:
        raise ValueError("requested_model cannot be blank")
    if not actual:
        raise ValueError("actual_host_model cannot be blank")
    if substitution_or_escalation is not None and not substitution:
        raise ValueError("substitution_or_escalation cannot be blank")
    if (
        actual != requested
        and actual not in _UNAVAILABLE_HOST_MODELS
        and not substitution
    ):
        raise ValueError(
            "a disclosed host model differing from requested_model requires substitution_or_escalation"
        )


class PortfolioReviewDraftIn(StrictResearchModel):
    contract_version: Literal["portfolio-review-v1"] = "portfolio-review-v1"
    agent_run_id: int = Field(ge=1)
    lease_owner: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    portfolio_id: int = Field(ge=1)
    portfolio_snapshot_id: int = Field(ge=1)
    as_of: datetime
    input_manifest: dict
    gaps: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=64, max_length=64)
    analytics_fingerprint: str = Field(min_length=64, max_length=64)
    sections: PortfolioReviewSections
    requested_model_role: Literal["worker_standard"] = "worker_standard"
    requested_model: str = Field(min_length=1, max_length=80)
    reasoning_effort: Literal["medium"] = "medium"
    actual_host_model: str = Field(min_length=1, max_length=160)
    substitution_or_escalation: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_aware_as_of(self):
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        _validate_model_provenance(
            self.requested_model,
            self.actual_host_model,
            self.substitution_or_escalation,
        )
        return self


class PortfolioReviewVerifierFinding(StrictResearchModel):
    severity: Literal["minor", "major", "blocking"]
    area: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=20, max_length=2000)


class PortfolioReviewVerifierJustifications(StrictResearchModel):
    concentration_and_liquidity: str = Field(min_length=60, max_length=3000)
    history_and_scenario_exposure: str = Field(min_length=60, max_length=3000)
    risks_and_decision_support_boundary: str = Field(min_length=60, max_length=3000)


class PortfolioReviewVerifierResult(StrictResearchModel):
    requested_model_role: Literal["verifier_strict"] = "verifier_strict"
    requested_model: str = Field(min_length=1, max_length=80)
    reasoning_effort: Literal["high"] = "high"
    actual_host_model: str = Field(min_length=1, max_length=160)
    substitution_or_escalation: str | None = Field(default=None, max_length=1000)
    verdict: Literal["pass", "fail", "needs-human"]
    findings: list[PortfolioReviewVerifierFinding] = Field(
        default_factory=list, max_length=20
    )
    justifications: PortfolioReviewVerifierJustifications
    summary: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def validate_model_provenance(self):
        _validate_model_provenance(
            self.requested_model,
            self.actual_host_model,
            self.substitution_or_escalation,
        )
        blocking = [item for item in self.findings if item.severity in {"major", "blocking"}]
        if self.verdict == "pass" and blocking:
            raise ValueError("a passing verdict cannot carry major/blocking findings")
        if self.verdict == "fail" and not self.findings:
            raise ValueError("a failing verdict must name concrete findings")
        return self


class PortfolioReviewVerificationIn(StrictResearchModel):
    verifier_worker_id: str = Field(min_length=1, max_length=200)
    draft: PortfolioReviewDraftIn
    verifier_result: PortfolioReviewVerifierResult


class PortfolioReviewSaveIn(PortfolioReviewDraftIn):
    verification_run_id: int = Field(ge=1)


class PortfolioReviewSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    portfolio_snapshot_id: int
    agent_run_id: int
    verification_run_id: int
    version: int
    contract_version: str
    status: Literal["provisional", "verified", "rejected", "needs-human"]
    draft_requested_model_role: str
    draft_requested_model: str
    draft_reasoning_effort: str
    draft_actual_host_model: str
    draft_substitution_or_escalation: str | None
    as_of: datetime
    sections: dict
    input_manifest: dict
    gaps: list[str]
    input_fingerprint: str
    analytics_fingerprint: str
    draft_fingerprint: str
    artifact_fingerprint: str
    verifier_result: dict
    created_at: datetime


class ValuationPreviewOut(BaseModel):
    research_snapshot_id: int
    template: dict
    base_values: dict
    deterministic_outputs: dict
    input_manifest: dict
    gaps: list[str]
    input_fingerprint: str
    calculation_fingerprint: str


class ValuationQueueOut(BaseModel):
    agent_run_id: int
    status: str
    created: bool
    input_fingerprint: str


AssumptionScenarioKind = Literal["negative", "base", "positive", "event"]
AssumptionProvenance = Literal["evidence", "human_assumption", "model_suggestion"]


class AssumptionItemIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: Any
    unit: str | None = Field(default=None, max_length=40)
    provenance: AssumptionProvenance
    source_ref: str | None = Field(default=None, max_length=240)
    rationale: str = Field(min_length=1, max_length=1000)


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


class DiscoveryFactorOut(BaseModel):
    id: str
    label: str
    note: str | None = None
    value: float | int | None
    delta: float | None = None
    period: str | None = None
    source_document_version_id: int | None = None
    source_as_of: datetime | None = None
    source_freshness: Literal["current", "stale"] | None = None
    history_median: float | None = None
    history_batch_ids: list[int] = Field(default_factory=list)
    history_document_version_ids: list[int] = Field(default_factory=list)


class DiscoveryScoreComponentOut(BaseModel):
    id: str
    label: str
    raw_value: float
    ranking_value: float
    percentile: float = Field(ge=0.0, le=100.0)
    weight: float = Field(gt=0.0, le=1.0)


class DiscoveryExpectationMetricOut(BaseModel):
    metric: Literal["revenue", "ebitda", "operating_profit", "net_income"]
    label: str
    value: float
    unit: str
    growth_pct: float | None = None
    growth_base_period: str | None = None
    forecast_count: int | None = Field(default=None, ge=1)
    range_min: float | None = None
    range_max: float | None = None
    dispersion_pct: float | None = Field(default=None, ge=0)


class DiscoveryExpectationPeriodOut(BaseModel):
    period: str
    period_kind: Literal["fiscal_year"] = "fiscal_year"
    metrics: list[DiscoveryExpectationMetricOut]


class DiscoveryAnalystExpectationsOut(BaseModel):
    provider: Literal["biznesradar"] = "biznesradar"
    status: Literal["available", "unavailable"]
    periods: list[DiscoveryExpectationPeriodOut] = Field(default_factory=list)
    source_document_version_id: int | None = None
    source_as_of: datetime | None = None
    note: str


class DiscoveryScoreNormalizationOut(BaseModel):
    component_id: Literal["net_income_growth", "current_pe"]
    label: str
    reported_value: float | None = None
    normalized_value: float | None = None
    discontinued_share_pct: float = Field(ge=0.0)
    period: str
    reason: str
    source_fact_ids: list[int] = Field(default_factory=list)
    source_document_version_ids: list[int] = Field(default_factory=list)


class DiscoveryCandidateOut(BaseModel):
    ticker: str
    name: str | None
    rank: int | None
    rank_basis: list[str]
    factors: list[DiscoveryFactorOut]
    factor_gaps: list[str]
    improvement_signals: list[str]
    potential_score: float | None = Field(default=None, ge=0.0, le=100.0)
    score_components: list[DiscoveryScoreComponentOut] = Field(default_factory=list)
    score_normalizations: list[DiscoveryScoreNormalizationOut] = Field(
        default_factory=list
    )
    analyst_expectations: DiscoveryAnalystExpectationsOut


class DiscoveryExcludedOut(BaseModel):
    ticker: str
    name: str | None
    kill_reasons: list[str] = Field(min_length=1)
    factors: list[DiscoveryFactorOut]
    factor_gaps: list[str]
    score_normalizations: list[DiscoveryScoreNormalizationOut] = Field(
        default_factory=list
    )


class DiscoverySieveFactorCoverageOut(BaseModel):
    id: str
    label: str
    covered_count: int
    total_count: int


class DiscoverySieveRuleOut(BaseModel):
    layer: Literal["hard_kill", "improvement"]
    factor_id: str
    label: str
    operator: Literal["lt", "lte", "gt", "gte", "eq", "composite"]
    threshold: float | None = None


class DiscoverySieveSourceOut(BaseModel):
    id: str
    label: str
    name: str
    url: str
    document_version_id: int
    parser_version: str
    as_of: datetime
    fields: list[str]


class DiscoveryFreshnessOut(BaseModel):
    status: Literal["current", "stale"]
    content_version_at: datetime
    last_successful_source_check_at: datetime
    last_failed_refresh_at: datetime | None = None
    last_failed_refresh_reason: str | None = None
    stale_after_hours: int


class DiscoverySieveOut(BaseModel):
    id: str
    version: str
    title: str
    question: str
    status: Literal["available", "blocked"]
    universe_count: int
    survivor_count: int
    excluded_count: int
    coverage_count: int
    coverage_pct: float
    coverage_label: str
    rules: list[DiscoverySieveRuleOut]
    factor_coverage: list[DiscoverySieveFactorCoverageOut]
    batch_id: int | None = None
    sources: list[DiscoverySieveSourceOut] = Field(default_factory=list)
    freshness: DiscoveryFreshnessOut | None = None
    gaps: list[str]


class DiscoveryOut(BaseModel):
    as_of: datetime
    universe_count: int
    result_count: int
    source_note: str
    freshness: DiscoveryFreshnessOut
    sieve: DiscoverySieveOut
    candidates: list[DiscoveryCandidateOut]
    excluded: list[DiscoveryExcludedOut]


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

    source_version_id: int | None
    date: date
    close: float
    volume: int | None
    source_name: str | None
    series_key: str | None
    basis_version: str | None
    adjustment_status: str
    scraped_at: datetime | None


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


class ResearchLabCreateOut(BaseModel):
    research_case: ResearchCaseSummaryOut
    agent_run: AgentRunOut
    created_company: bool
    created_case: bool
    reactivated_case: bool
    created_job: bool


class ResearchReviewQueueOut(BaseModel):
    agent_run_id: int
    status: str
    created: bool
    prior_snapshot_id: int
    source_fingerprint: str
    profile_id: int
    profile_version: int
    profile_fingerprint: str


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
