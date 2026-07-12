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
    latest_research_run_id: int | None = None
    latest_research_run_status: str | None = None
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
    schema_version: Literal["company-profile-v1", "company-profile-v2"] = (
        "company-profile-v2"
    )
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
    author: str
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
    contract_version: Literal["research-snapshot-v1", "research-snapshot-v2"] = (
        "research-snapshot-v2"
    )
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
    # Profile bound to latest_snapshot (or the only profile before first save).
    profile: CompanyProfileOut | None
    # Latest human/model understanding; it can intentionally be newer than the
    # profile bound to latest_snapshot while an explicit review is pending.
    current_profile: CompanyProfileOut | None
    profile_history: list[CompanyProfileOut]
    latest_snapshot: ResearchSnapshotOut | None
    history: list[ResearchSnapshotHistoryOut]
    archetype_pack: ArchetypePackOut | None = None


# --------------------------------------------------------------- valuation v1

ValuationScenarioKind = Literal["negative", "base", "positive", "event"]
ValuationStatus = Literal["provisional", "verified", "rejected", "needs-human"]


class ValuationMethodPackOut(BaseModel):
    id: str
    version: str
    label: str
    status: Literal["ready", "blocked"]
    reason: str | None = None
    skill: str | None = None


class ValuationAssumptionValue(StrictResearchModel):
    value: float
    provenance: Literal["evidence", "human_assumption"]
    rationale: str = Field(min_length=1, max_length=1000)
    source_fact_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provenance(self):
        from math import isfinite

        if not isfinite(self.value):
            raise ValueError("assumption values must be finite")
        if self.provenance == "evidence" and not self.source_fact_ids:
            raise ValueError("evidence assumptions require source_fact_ids")
        if self.provenance == "human_assumption" and self.source_fact_ids:
            raise ValueError("human assumptions cannot claim source_fact_ids")
        return self


class ValuationScenarioAssumptions(StrictResearchModel):
    kind: ValuationScenarioKind
    label: str = Field(min_length=1, max_length=120)
    quarter_revenue_growth_pct: ValuationAssumptionValue
    year_revenue_growth_pct: ValuationAssumptionValue
    gross_margin_pct: ValuationAssumptionValue
    operating_cost_ratio_pct: ValuationAssumptionValue
    financial_result_ratio_pct: ValuationAssumptionValue
    tax_rate_pct: ValuationAssumptionValue
    cash_conversion_pct: ValuationAssumptionValue
    capex_spend_ratio_pct: ValuationAssumptionValue
    target_pe: ValuationAssumptionValue
    event_one_off_net_pln_thousands: ValuationAssumptionValue | None = None

    @model_validator(mode="after")
    def validate_ranges(self):
        if (
            self.quarter_revenue_growth_pct.value <= -100
            or self.year_revenue_growth_pct.value <= -100
        ):
            raise ValueError("revenue growth must stay above -100%")
        if not -200 <= self.gross_margin_pct.value <= 200:
            raise ValueError("gross margin must be bounded to -200..200%")
        if not -100 <= self.operating_cost_ratio_pct.value <= 300:
            raise ValueError("operating cost ratio must be bounded to -100..300%")
        if not -300 <= self.financial_result_ratio_pct.value <= 300:
            raise ValueError("financial result ratio must be bounded to -300..300%")
        if not 0 <= self.tax_rate_pct.value <= 100:
            raise ValueError("tax rate must be 0..100%")
        if not -500 <= self.cash_conversion_pct.value <= 500:
            raise ValueError("cash conversion must be bounded to -500..500%")
        if not 0 <= self.capex_spend_ratio_pct.value <= 100:
            raise ValueError("capex spend ratio must be 0..100% positive magnitude")
        if self.target_pe.value <= 0:
            raise ValueError("target_pe must be positive")
        if self.capex_spend_ratio_pct.value < 0:
            raise ValueError("capex spend is a positive outlay ratio")
        if self.kind != "event" and self.event_one_off_net_pln_thousands is not None:
            raise ValueError("event one-off is allowed only in the event scenario")
        if self.kind == "event" and self.event_one_off_net_pln_thousands is None:
            raise ValueError(
                "event scenario requires an explicit net one-off assumption"
            )
        return self


class ValuationRequestIn(StrictResearchModel):
    research_snapshot_id: int = Field(ge=1)
    method_pack_id: str = "malik_obs_v1"
    assumptions: list[ValuationScenarioAssumptions] = Field(min_length=3, max_length=4)
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
        return self


class ValuationScenarioJudgment(StrictResearchModel):
    kind: ValuationScenarioKind
    mechanism: str = Field(min_length=1, max_length=2000)
    proposed_probability_pct: int = Field(ge=0, le=100)
    probability_rationale: str = Field(min_length=1, max_length=1000)
    catalyst_or_counter_driver: str = Field(min_length=1, max_length=1000)
    falsifier: str = Field(min_length=1, max_length=1000)
    gaps: list[str] = Field(default_factory=list)


class ValuationDraftJudgment(StrictResearchModel):
    method_read: str = Field(min_length=1, max_length=4000)
    scenarios: list[ValuationScenarioJudgment] = Field(min_length=3, max_length=4)
    catalysts: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scenario_kinds(self):
        kinds = [row.kind for row in self.scenarios]
        if len(kinds) != len(set(kinds)):
            raise ValueError("judgment scenario kinds must be unique")
        return self


class ValuationSnapshotDraftIn(StrictResearchModel):
    contract_version: Literal["valuation-snapshot-v1"] = "valuation-snapshot-v1"
    engine_version: Literal["valuation-engine-v2"] = "valuation-engine-v2"
    template_contract_version: Literal["valuation-templates-v1"] = (
        "valuation-templates-v1"
    )
    agent_run_id: int = Field(ge=1)
    lease_owner: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    research_snapshot_id: int = Field(ge=1)
    as_of: datetime
    method_pack_id: str
    method_pack_version: str
    template_id: str
    template_version: str
    assumptions: list[ValuationScenarioAssumptions]
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
        return self


class ValuationVerifierChecks(StrictResearchModel):
    schema_integrity: bool
    source_integrity: bool
    company_identity: bool
    look_ahead: bool
    math_integrity: bool
    probability_coherence: bool
    method_integrity: bool


class ValuationFinalProbability(StrictResearchModel):
    kind: ValuationScenarioKind
    probability_pct: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=1000)


class ValuationVerifierResult(StrictResearchModel):
    model_role: Literal["verifier_strict"] = "verifier_strict"
    verifier_model: str = Field(min_length=1, max_length=80)
    verdict: Literal["pass", "fail", "needs-human"]
    checks: ValuationVerifierChecks
    final_probabilities: list[ValuationFinalProbability] = Field(
        default_factory=list, max_length=4
    )
    summary: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_probabilities(self):
        kinds = [row.kind for row in self.final_probabilities]
        if len(kinds) != len(set(kinds)):
            raise ValueError("final probability kinds must be unique")
        if self.verdict == "pass":
            if len(self.final_probabilities) < 3:
                raise ValueError("passing verification requires final probabilities")
            if sum(row.probability_pct for row in self.final_probabilities) != 100:
                raise ValueError("final probabilities must sum exactly to 100")
        elif self.final_probabilities:
            raise ValueError("fail/needs-human verdicts do not own final probabilities")
        return self


class ValuationSnapshotVerificationIn(StrictResearchModel):
    verifier_worker_id: str = Field(min_length=1, max_length=200)
    draft: ValuationSnapshotDraftIn
    verifier_result: ValuationVerifierResult


class ValuationSnapshotSaveIn(ValuationSnapshotDraftIn):
    verification_run_id: int = Field(ge=1)


class ValuationSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_case_id: int
    research_snapshot_id: int
    agent_run_id: int
    verification_run_id: int
    version: int
    contract_version: str
    status: ValuationStatus
    as_of: datetime
    method_pack_id: str
    method_pack_version: str
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
    as_of: datetime
    method_pack_id: str
    template_id: str
    created_at: datetime


class ValuationWorkspaceOut(BaseModel):
    research_case_id: int
    latest_research_snapshot_id: int | None
    method_packs: list[ValuationMethodPackOut]
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
    reasoning_effort: Literal["high"] = "high"
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


class PortfolioReviewVerifierChecks(StrictResearchModel):
    snapshot_source_identity: bool
    reconciliation: bool
    mapping_set: bool
    method_labels: bool
    scenario_arithmetic: bool
    eligible_valuations: bool
    look_ahead: bool
    draft_fingerprint: bool
    no_recommendation: bool


class PortfolioReviewVerifierResult(StrictResearchModel):
    requested_model_role: Literal["verifier_strict"] = "verifier_strict"
    requested_model: str = Field(min_length=1, max_length=80)
    reasoning_effort: Literal["high"] = "high"
    actual_host_model: str = Field(min_length=1, max_length=160)
    substitution_or_escalation: str | None = Field(default=None, max_length=1000)
    verdict: Literal["pass", "fail", "needs-human"]
    checks: PortfolioReviewVerifierChecks
    summary: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def validate_model_provenance(self):
        _validate_model_provenance(
            self.requested_model,
            self.actual_host_model,
            self.substitution_or_escalation,
        )
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
    method_pack: ValuationMethodPackOut
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
    neutral_context: list["DiscoveryContextOut"]
    memberships: list["DiscoveryCandidateMembershipOut"]
    overlap: "DiscoveryOverlapOut"


class DiscoveryMembershipFactorOut(BaseModel):
    id: str
    label: str
    note: str | None = None
    value: float | int | None
    report_period: str
    source_document_version_id: int


class DiscoveryCandidateMembershipOut(BaseModel):
    sieve_id: str
    sieve_version: str
    rank: int | None
    rank_basis: list[str]
    factor_status: Literal["current", "stale"]
    factors: list[DiscoveryMembershipFactorOut]
    factor_gaps: list[str]
    strategy_questions: list[str]
    caveat: str
    source: "DiscoverySieveSourceOut | None" = None
    freshness: "DiscoveryFreshnessOut | None" = None


class DiscoveryOverlapOut(BaseModel):
    sieve_ids: list[str]
    count: int


class DiscoveryContextOut(BaseModel):
    id: Literal["wig_bucket", "sector", "size"]
    label: str
    value: str | None
    basis: str


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
    candidate_count: int
    coverage_count: int
    coverage_pct: float
    selection_rules: list[DiscoverySieveRuleOut]
    factor_coverage: list[DiscoverySieveFactorCoverageOut]
    source: DiscoverySieveSourceOut | None = None
    freshness: DiscoveryFreshnessOut | None = None
    candidates: list["DiscoverySieveCandidateRefOut"]
    gaps: list[str]


class DiscoverySieveCandidateRefOut(BaseModel):
    ticker: str


class DiscoveryOut(BaseModel):
    source: str
    source_url: str
    as_of: datetime
    universe_count: int
    result_count: int
    source_note: str
    source_version_id: int
    freshness: DiscoveryFreshnessOut
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


class ResearchReviewQueueOut(BaseModel):
    agent_run_id: int
    status: str
    created: bool
    prior_snapshot_id: int
    source_fingerprint: str
    profile_id: int
    profile_version: int
    profile_fingerprint: str


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
