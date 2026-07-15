/**
 * API contracts — mirror of backend/app/api/schemas.py (snake_case preserved
 * on purpose: one shape end to end, no mapping layer to maintain).
 */

export interface DiscoveryCandidate {
  ticker: string;
  name: string | null;
  rank: number | null;
  rank_basis: string[];
  factors: DiscoveryFactor[];
  factor_gaps: string[];
  improvement_signals: string[];
  potential_score: number | null;
  score_components: DiscoveryScoreComponent[];
  score_normalizations: DiscoveryScoreNormalization[];
  analyst_expectations: DiscoveryAnalystExpectations;
}

export interface DiscoveryExpectationMetric {
  metric: "revenue" | "ebitda" | "operating_profit" | "net_income";
  label: string;
  value: number;
  unit: string;
  growth_pct: number | null;
  growth_base_period: string | null;
  forecast_count: number | null;
  range_min: number | null;
  range_max: number | null;
  dispersion_pct: number | null;
}

export interface DiscoveryExpectationPeriod {
  period: string;
  period_kind: "fiscal_year";
  metrics: DiscoveryExpectationMetric[];
}

export interface DiscoveryAnalystExpectations {
  provider: "biznesradar";
  status: "available" | "unavailable";
  periods: DiscoveryExpectationPeriod[];
  source_document_version_id: number | null;
  source_as_of: string | null;
  note: string;
}

export interface DiscoveryScoreComponent {
  id: string;
  label: string;
  raw_value: number;
  ranking_value: number;
  percentile: number;
  weight: number;
}

export interface DiscoveryScoreNormalization {
  component_id: "net_income_growth" | "current_pe";
  label: string;
  reported_value: number | null;
  normalized_value: number | null;
  discontinued_share_pct: number;
  period: string;
  reason: string;
  source_fact_ids: number[];
  source_document_version_ids: number[];
}

export interface DiscoveryExcluded {
  ticker: string;
  name: string | null;
  kill_reasons: string[];
  factors: DiscoveryFactor[];
  factor_gaps: string[];
  score_normalizations: DiscoveryScoreNormalization[];
}

export interface DiscoveryFactor {
  id: string;
  label: string;
  note: string | null;
  value: number | null;
  delta: number | null;
  period: string | null;
  source_document_version_id: number | null;
  source_as_of: string | null;
  source_freshness: "current" | "stale" | null;
  history_median: number | null;
  history_batch_ids: number[];
  history_document_version_ids: number[];
}

export interface DiscoveryResult {
  as_of: string;
  universe_count: number;
  result_count: number;
  source_note: string;
  freshness: DiscoveryFreshness;
  sieve: DiscoverySieve;
  candidates: DiscoveryCandidate[];
  excluded: DiscoveryExcluded[];
}

export interface DiscoverySieve {
  id: string;
  version: string;
  title: string;
  question: string;
  status: "available" | "blocked";
  universe_count: number;
  survivor_count: number;
  excluded_count: number;
  coverage_count: number;
  coverage_pct: number;
  coverage_label: string;
  rules: Array<{
    layer: "hard_kill" | "improvement";
    factor_id: string;
    label: string;
    operator: "lt" | "lte" | "gt" | "gte" | "eq" | "composite";
    threshold: number | null;
  }>;
  factor_coverage: Array<{
    id: string;
    label: string;
    covered_count: number;
    total_count: number;
  }>;
  batch_id: number | null;
  sources: DiscoverySieveSource[];
  freshness: DiscoveryFreshness | null;
  gaps: string[];
}

export interface DiscoverySieveSource {
  id: string;
  label: string;
  name: string;
  url: string;
  document_version_id: number;
  parser_version: string;
  as_of: string;
  fields: string[];
}

export interface DiscoveryFreshness {
  status: "current" | "stale";
  content_version_at: string;
  last_successful_source_check_at: string;
  last_failed_refresh_at: string | null;
  last_failed_refresh_reason: string | null;
  stale_after_hours: number;
}

export interface Company {
  ticker: string;
  name: string | null;
  market: string | null;
  sector: string | null;
  shares_outstanding: number | null;
  market_cap: number | null;
  enterprise_value: number | null;
  updated_at: string;
}

export type ResearchCaseState =
  | "new"
  | "ingesting"
  | "data_review"
  | "business_model"
  | "thesis"
  | "scenarios"
  | "review"
  | "monitoring"
  | "blocked"
  | "closed";

export type ResearchCaseStep =
  | "ingest"
  | "data_review"
  | "business_model"
  | "thesis"
  | "scenarios"
  | "review"
  | "monitoring";

export interface ResearchCase {
  id: number;
  company_id: number;
  purpose: string;
  state: ResearchCaseState;
  current_step: ResearchCaseStep;
  as_of: string | null;
  blocked_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchCaseSummary {
  id: number;
  company_id: number;
  ticker: string;
  name: string | null;
  purpose: string;
  state: ResearchCaseState;
  current_step: ResearchCaseStep;
  as_of: string | null;
  blocked_reason: string | null;
  created_at: string;
  updated_at: string;
  phase: "collecting" | "researched" | "valued";
  phase_label: string;
  phase_summary: string;
  main_gap: string | null;
  agenda_reasons: string[];
  latest_snapshot_status: ResearchSnapshotStatus | null;
  latest_snapshot_as_of: string | null;
  collection_progress: {
    state: "waiting" | "collecting" | "attention";
    summary: string;
    completed_sources: string[];
    remaining_sources: string[];
    percent: number | null;
  } | null;
  valuation_strip: {
    scenario_prices_pln: Record<string, number | null>;
    scenario_probabilities_pct: Record<string, number>;
    price_range_pln: [number, number] | null;
    weighted_value_pln: number | null;
    current_price_pln: number | null;
    upside_pct: number | null;
    catalyst: string | null;
    verification_status: ValuationSnapshotStatus;
    as_of: string;
  } | null;
}

export type ResearchArchetype =
  | "industrial-consumer"
  | "bank-financial"
  | "developer-real-estate"
  | "software-services"
  | "gaming-event"
  | "energy-resources"
  | "holding-biotech";

export type ResearchSnapshotStatus =
  | "provisional"
  | "verified"
  | "rejected"
  | "needs-human";

export interface ResearchDriver {
  key: string;
  label: string;
  mechanism: string;
  unit: string | null;
  source_document_version_ids: number[];
  basis: string | null;
  focus_tags: string[];
}

export interface ResearchKpi {
  key: string;
  label: string;
  unit: string | null;
  rationale: string;
  source_document_version_ids: number[];
  basis: string | null;
  focus_tags: string[];
}

export interface CompanyOverlay {
  segments: string[];
  competitors: string[];
  source_questions: string[];
  unusual_risks: string[];
}

export interface CompanyProfile {
  id: number;
  research_case_id: number;
  schema_version: "company-profile-v2";
  version: number;
  archetype: ResearchArchetype;
  archetype_version: string;
  company_overlay: CompanyOverlay;
  drivers: ResearchDriver[];
  kpis: ResearchKpi[];
  provenance: "codex-proposed" | "human-confirmed" | "human-corrected";
  reason: string | null;
  based_on_profile_id: number | null;
  created_at: string;
}

export type ResearchClaimKind =
  | "fact"
  | "calculation"
  | "assumption"
  | "lead"
  | "unknown";

export interface ResearchClaim {
  text: string;
  kind: ResearchClaimKind;
  source_document_version_ids: number[];
  basis: string | null;
}

export type ResearchSourceChannel =
  | "issuer-primary"
  | "regulatory-primary"
  | "biznesradar"
  | "portalanaliz"
  | "other-web";

export type ResearchOutlookDirection =
  | "positive"
  | "neutral"
  | "negative"
  | "mixed"
  | "unknown";

export interface ResearchOutlookAssessment {
  direction: ResearchOutlookDirection;
  assessment: ResearchClaim;
  source_channels: ResearchSourceChannel[];
  watch_items: string[];
  gap_topic: string | null;
}

export interface ResearchOutlookSection {
  summary: string;
  driver_outlooks: Array<{
    driver_key: string;
    next_quarter: ResearchOutlookAssessment;
    next_12_months: ResearchOutlookAssessment;
  }>;
  question_resolutions: Array<{
    scope: "profile" | "catalyst" | "visibility" | "governance";
    question: string;
    status: "confirmed" | "partial" | "not_found" | "not_applicable";
    answer: ResearchClaim;
    source_channels: ResearchSourceChannel[];
    remaining_gap: string | null;
    gap_topic: string | null;
  }>;
  source_searches: Array<{
    channel: ResearchSourceChannel;
    status: "found" | "not_found" | "unavailable";
    summary: string;
    document_version_ids: number[];
  }>;
  claims: ResearchClaim[];
}

export interface ResearchSections {
  brief: {
    current_understanding: string;
    freshness: string;
    main_gap: string;
    next_action: string;
  };
  business_and_drivers: {
    business_model: string;
    revenue_model: string;
    driver_keys: string[];
    claims: ResearchClaim[];
  };
  performance: {
    summary: string;
    result_bridge: string[];
    kpi_keys: string[];
    claims: ResearchClaim[];
  };
  evidence: {
    summary: string;
    primary_document_version_ids: number[];
    claims: ResearchClaim[];
  };
  outlook: ResearchOutlookSection | null;
  thesis: {
    why_now: string;
    counter_thesis: string;
    catalysts: string[];
    risks: string[];
    governance: string;
    falsifiers: string[];
    next_checks: string[];
    claims: ResearchClaim[];
  };
  history: {
    changes_since_previous: string[];
    prior_snapshot_id: number | null;
    claims: ResearchClaim[];
  };
}

export interface ResearchSourceManifestItem {
  document_version_id: number;
  role: "primary" | "normalized" | "context" | "lead";
  purpose: string;
}

export interface ResearchConflict {
  topic: string;
  description: string;
  document_version_ids: number[];
}

export interface ResearchGap {
  topic: string;
  description: string;
  impact: string;
  focus_tags: string[];
}

export interface ResearchNextCheck {
  question: string;
  suggested_source: string;
}

export interface ResearchVerifierResult {
  model_role: "verifier_strict";
  verifier_model: string;
  verdict: "pass" | "fail" | "needs-human";
  findings: Array<{
    severity: "minor" | "major" | "blocking";
    area: string;
    detail: string;
  }>;
  justifications: {
    evidence_and_claim_fit: string;
    company_specificity: string;
    outlook_and_thesis_plausibility: string;
  } | null;
  summary: string;
  verification_standard: "adversarial-v1";
}

export interface ResearchStatementProvenance {
  path: string;
  claim: ResearchClaim;
}

export interface ResearchSnapshot {
  id: number;
  research_case_id: number;
  company_profile_id: number;
  agent_run_id: number;
  verification_run_id: number;
  version: number;
  contract_version: "research-snapshot-v3";
  status: ResearchSnapshotStatus;
  as_of: string;
  input_fingerprint: string;
  artifact_fingerprint: string;
  sections: ResearchSections;
  source_manifest: ResearchSourceManifestItem[];
  conflicts: ResearchConflict[];
  gaps: ResearchGap[];
  next_checks: ResearchNextCheck[];
  statement_provenance: ResearchStatementProvenance[];
  verifier_result: ResearchVerifierResult;
  created_at: string;
}

export interface ResearchSnapshotHistory {
  id: number;
  version: number;
  status: ResearchSnapshotStatus;
  as_of: string;
  profile_version: number;
  created_at: string;
}

export interface ResearchWorkspace {
  research_case: ResearchCaseSummary;
  profile: CompanyProfile | null;
  current_profile: CompanyProfile | null;
  profile_history: CompanyProfile[];
  latest_snapshot: ResearchSnapshot | null;
  history: ResearchSnapshotHistory[];
  archetype_pack: ResearchArchetypePack | null;
}

export interface ResearchArchetypePack {
  id: string;
  version: string;
  label: string;
  required_markers: Array<{
    id: string;
    label: string;
    covered: boolean;
    state: "sourced" | "assumption" | "gap" | "missing";
  }>;
  sourced_markers: string[];
  assumption_markers: string[];
  covered_markers: string[];
  gap_markers: string[];
  missing_markers: string[];
  sourced_count: number;
  assumption_count: number;
  gap_count: number;
  missing_count: number;
  coverage_count: number;
  coverage_pct: number;
}

export interface ResearchCaseCreateResult {
  research_case: ResearchCaseSummary;
  agent_run: AgentRun;
  created_company: boolean;
  created_case: boolean;
  reactivated_case: boolean;
  created_job: boolean;
}

export interface ResearchReviewQueueResult {
  agent_run_id: number;
  status: string;
  created: boolean;
  prior_snapshot_id: number;
  source_fingerprint: string;
  profile_id: number;
  profile_version: number;
  profile_fingerprint: string;
}

export interface ResearchCaseStepHistory {
  id: number;
  research_case_id: number;
  from_state: ResearchCaseState | null;
  from_step: ResearchCaseStep | null;
  to_state: ResearchCaseState;
  to_step: ResearchCaseStep;
  reason: string;
  changed_by: string | null;
  created_at: string;
}

// --- canonical valuation (P3) ---------------------------------------------

export type ValuationScenarioKind = "negative" | "base" | "positive" | "event";
export type ValuationSnapshotStatus = "provisional" | "verified" | "rejected" | "needs-human";

export interface ValuationTemplate {
  id: string;
  version: string;
  archetype: ResearchArchetype;
  label: string;
  driver_copy: string[];
  equation: string;
}

export interface ValuationAssumptionValue {
  value: number;
  basis: "reported_fact" | "street_estimate" | "codex_judgment" | "human_override";
  rationale: string;
  source_fact_ids: number[];
  research_claim_paths: string[];
}

export interface ValuationForecastYear {
  period: string;
  revenue_pln_thousands: ValuationAssumptionValue;
  ebitda_margin_pct: ValuationAssumptionValue;
  depreciation_pct_revenue: ValuationAssumptionValue;
  capex_pct_revenue: ValuationAssumptionValue;
  delta_nwc_pct_revenue: ValuationAssumptionValue;
  cash_tax_rate_pct: ValuationAssumptionValue;
  net_financial_result_pct_revenue: ValuationAssumptionValue;
  fcff_period_fraction: ValuationAssumptionValue;
  fcff_discount_years: ValuationAssumptionValue;
}

export interface ValuationScenarioAssumptions {
  kind: ValuationScenarioKind;
  label: string;
  forecast_years: ValuationForecastYear[];
  target_pe: ValuationAssumptionValue | null;
  target_ev_ebitda: ValuationAssumptionValue | null;
  target_ev_ebit: ValuationAssumptionValue | null;
  wacc_pct: ValuationAssumptionValue | null;
  terminal_growth_pct: ValuationAssumptionValue | null;
  event_impact: {
    period: string;
    recurring: false;
    pnl_net_pln_thousands: ValuationAssumptionValue;
    cash_pln_thousands: ValuationAssumptionValue;
  } | null;
}

export type ValuationMethod = "pe" | "ev_ebitda" | "ev_ebit" | "fcff_dcf";

export interface ValuationMethodology {
  primary_method: ValuationMethod;
  cross_checks: ValuationMethod[];
  valuation_period: string;
  rationale: string;
}

export interface ValuationRequest {
  research_snapshot_id: number;
  assumptions: ValuationScenarioAssumptions[];
  methodology: ValuationMethodology;
  as_of: string;
}

export interface ValuationQueueRequest {
  research_snapshot_id?: number;
  as_of?: string;
}

export interface ValuationForecastOutput {
  period: string;
  revenue_pln_thousands: number;
  ebitda_pln_thousands: number;
  depreciation_pln_thousands: number;
  ebit_pln_thousands: number;
  financial_result_pln_thousands: number;
  pretax_result_pln_thousands: number;
  cash_tax_pln_thousands: number;
  recurring_net_result_pln_thousands: number;
  reported_net_result_pln_thousands: number;
  recurring_eps_pln: number;
  capex_pln_thousands: number;
  delta_nwc_pln_thousands: number;
  fcff_pln_thousands: number;
  fcff_period_fraction: number;
  fcff_discount_years: number;
  event_cash_pln_thousands: number;
}

export interface ValuationMethodOutput {
  status: "calculated" | "unavailable";
  price_pln: number | null;
  target_multiple?: number;
  enterprise_value_pln_thousands?: number;
  equity_value_pln_thousands?: number;
  terminal_value_share_pct?: number;
  wacc_pct?: number;
  terminal_growth_pct?: number;
  net_debt_pln_thousands?: number;
  sensitivity?: Array<{
    wacc_pct: number;
    terminal_growth_pct: number;
    price_pln: number;
  }>;
}

export interface ValuationExpectationBridgePeriod {
  period: string;
  metrics: Array<{
    metric: string;
    workbench_pln_thousands: number;
    street_pln_thousands: number | null;
    street_range: { low: number | null; high: number | null; forecast_count: number | null } | null;
    variance_pct: number | null;
    status: "compared" | "street_unknown";
  }>;
}

export interface ValuationScenarioOutput {
  kind: ValuationScenarioKind;
  label: string;
  forecast_path: ValuationForecastOutput[];
  expectation_bridge: ValuationExpectationBridgePeriod[];
  methods: Record<ValuationMethod, ValuationMethodOutput>;
  primary_method: ValuationMethod;
  cross_check_methods: ValuationMethod[];
  target_price_pln: number | null;
  return_pct: number | null;
  valuation_status: "calculated" | "unavailable";
  valuation_gap: string | null;
  cross_check_range_pln: { low: number; high: number } | null;
  method_dispersion_pct: number | null;
}

export interface ValuationDeterministicOutputs {
  engine_version: string;
  current_price_pln: number;
  methodology: ValuationMethodology;
  street_expectations: Record<string, unknown>;
  priced_in_expectations: {
    valuation_period: string;
    market_cap_pln: number;
    enterprise_value_pln: number | null;
    methods: {
      pe?: { target_multiple: number; implied_net_income_pln_thousands: number };
      ev_ebitda?: { target_multiple: number; implied_ebitda_pln_thousands: number };
      [key: string]: Record<string, number> | undefined;
    };
    reverse_dcf?: {
      status: "calculated" | "unavailable";
      valuation_period: string;
      implied_revenue_pln_thousands: number | null;
      street_revenue_pln_thousands: number | null;
      variance_to_street_revenue_pct: number | null;
      implied_revenue_path_scale_pct: number | null;
      repricing_residual_bps: number | null;
      gap?: string | null;
    };
  };
  scenarios: ValuationScenarioOutput[];
  probability_weighted: {
    status: "calculated" | "unavailable";
    price_pln: number | null;
    return_pct: number | null;
    gap: string | null;
  } | null;
  final_probabilities?: Array<{ kind: ValuationScenarioKind; probability_pct: number; rationale: string; posture: string }>;
}

export interface ValuationPreview {
  research_snapshot_id: number;
  template: ValuationTemplate;
  base_values: Record<string, unknown>;
  deterministic_outputs: ValuationDeterministicOutputs;
  input_manifest: Record<string, unknown>;
  gaps: string[];
  input_fingerprint: string;
  calculation_fingerprint: string;
}

export interface CanonicalValuationSnapshot {
  id: number;
  research_case_id: number;
  research_snapshot_id: number;
  agent_run_id: number | null;
  verification_run_id: number | null;
  version: number;
  contract_version: "valuation-snapshot-v2";
  status: ValuationSnapshotStatus;
  origin: "codex" | "human-override";
  as_of: string;
  template_id: string;
  template_version: string;
  calculation_engine_version: string;
  assumptions: { scenarios: ValuationScenarioAssumptions[]; methodology: ValuationMethodology };
  base_values: Record<string, unknown>;
  deterministic_outputs: ValuationDeterministicOutputs;
  codex_judgment: {
    strategy_read?: string;
    scenarios?: Array<{
      kind: ValuationScenarioKind;
      mechanism: string;
      probability_pct: number | null;
      catalyst_or_counter_driver: string;
      falsifier: string;
      gaps: string[];
    }>;
    probability_model?: { posture: "uncalibrated" | "judgmental_unvalidated" | "empirical_calibrated" };
    catalysts?: string[];
    falsifiers?: string[];
  };
  input_manifest: Record<string, unknown>;
  gaps: string[];
  input_fingerprint: string;
  calculation_fingerprint: string;
  artifact_fingerprint: string;
  verifier_result: {
    origin?: "human-override";
    note?: string;
    model_role?: "verifier_strict";
    verifier_model?: string;
    verdict?: "pass" | "fail" | "needs-human";
    findings?: Array<{
      severity: "minor" | "major" | "blocking";
      area: string;
      detail: string;
    }>;
    judgment_review?: {
      evidence_fit: string;
      mechanism_plausibility: string;
      probability_reasonableness: string;
    };
    summary?: string;
  };
  created_at: string;
}

export interface ValuationHistoryItem {
  id: number;
  version: number;
  status: ValuationSnapshotStatus;
  origin: string;
  as_of: string;
  template_id: string;
  created_at: string;
}

export interface ValuationWorkspace {
  research_case_id: number;
  latest_research_snapshot_id: number | null;
  template: ValuationTemplate | null;
  latest_valuation: CanonicalValuationSnapshot | null;
  history: ValuationHistoryItem[];
}

export interface ValuationQueueResult {
  agent_run_id: number;
  status: string;
  created: boolean;
  input_fingerprint: string;
}

export type AssumptionScenarioKind = "negative" | "base" | "positive" | "event";
export type AssumptionStatus = "draft" | "approved" | "rejected";
export type AssumptionProvenance = "evidence" | "human_assumption" | "model_suggestion";

export interface AssumptionItem {
  key: string;
  value: unknown;
  unit: string | null;
  provenance: AssumptionProvenance;
  source_ref: string | null;
  rationale: string;
}

export interface AssumptionSet {
  id: number;
  research_case_id: number;
  scenario_kind: AssumptionScenarioKind;
  label: string;
  status: AssumptionStatus;
  as_of: string | null;
  assumptions: AssumptionItem[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DriverAssumption extends AssumptionItem {
  applied: boolean;
  note: string;
}

export interface ScenarioSensitivityRow {
  scenario_kind: AssumptionScenarioKind;
  label: string;
  baseline_target_price: number | null;
  sensitivity_target_price: number | null;
  target_price_delta: number | null;
  baseline_upside_pct: number | null;
  sensitivity_upside_pct: number | null;
  upside_delta_pct: number | null;
  applied: DriverAssumption[];
  ignored: DriverAssumption[];
}

export interface ScenarioDriverSensitivity {
  status: "none" | "applied" | "human_review_required";
  note: string;
  rows: ScenarioSensitivityRow[];
}

export interface OperatingBridgeRow {
  scenario_kind: AssumptionScenarioKind;
  label: string;
  baseline_target_price: number | null;
  operating_target_price: number | null;
  target_price_delta: number | null;
  operating_upside_pct: number | null;
  projected_revenue: number | null;
  projected_gross_margin_pct: number | null;
  projected_net_profit: number | null;
  projected_eps: number | null;
  projected_ebitda: number | null;
  projected_depreciation: number | null;
  projected_fcf: number | null;
  fcf_gap: string | null;
  applied: DriverAssumption[];
  ignored: DriverAssumption[];
  missing: string[];
}

export interface OperatingBridge {
  status: "none" | "applied" | "needs_human" | "unsupported_template";
  template: { id: string; label: string; sector_group: string; equation: string } | null;
  note: string;
  rows: OperatingBridgeRow[];
  cash_conversion: {
    status: "none" | "partial" | "needs_human";
    period: string | null;
    operating_cashflow: number | null;
    net_profit: number | null;
    conversion_ratio: number | null;
    capex: number | null;
    capex_intensity_pct: number | null;
    observed_fcf: number | null;
    working_capital_change: number | null;
    working_capital_cash_effect: number | null;
    gaps: string[];
  };
  fcf_lens: {
    status: "none" | "applied" | "needs_human";
    method: string;
    note: string;
    rows: Array<{
      scenario_kind: AssumptionScenarioKind;
      label: string;
      baseline_target_price: number | null;
      projected_fcf: number | null;
      fcf_multiple: number | null;
      fcf_target_price: number | null;
      target_price_delta: number | null;
      applied: DriverAssumption[];
      ignored: DriverAssumption[];
      missing: string[];
      gap: string | null;
    }>;
  };
}

export interface RefreshSummary {
  ticker: string;
  summary: Record<string, string>;
}

export interface FinancialsRow {
  field_code: string;
  label: string;
  values: (number | null)[];
}

export interface Financials {
  statement: "income" | "balance" | "cashflow";
  freq: "Q" | "Y";
  periods: string[];
  rows: FinancialsRow[];
}

export interface IndicatorPoint {
  period: string;
  value: number | null;
}

export interface Dividend {
  year: number;
  dps: number | null;
  yield_pct: number | null;
}

export interface PricePoint {
  source_version_id: number | null;
  date: string;
  close: number;
  volume: number | null;
}

export interface Check {
  id: string;
  name: string;
  verdict: "pass" | "fail" | "unknown";
  evidence: string;
}

export interface Prescore {
  passed: number;
  total: number;
  checks: Check[];
}

export interface QuarterMetrics {
  period: string;
  revenue: number | null;
  revenue_yoy_pct: number | null;
  gross_margin_pct: number | null;
  sales_margin_pct: number | null;
  net_margin_pct: number | null;
  profit_on_sales: number | null;
  operating_profit: number | null;
  net_profit: number | null;
  one_off_share_pct: number | null;
  discontinued_profit: number | null;
  continuing_net_profit: number | null;
  discontinued_share_of_net_pct: number | null;
}

export interface Ttm {
  net_profit: number | null;
  eps: number | null;
  pe: number | null;
  discontinued_profit: number | null;
  continuing_net_profit: number | null;
  continuing_eps: number | null;
  continuing_pe: number | null;
  valuation_eps: number | null;
  valuation_pe: number | null;
  valuation_basis: "continuing" | "reported";
  market_cap: number | null;
  // "reported" = scraped as-is, "derived" = price × shares (estimate)
  market_cap_source: "reported" | "derived" | null;
  // |reported − derived| discrepancy between the two sources, in %
  market_cap_check_pct: number | null;
  price: number | null;
  price_date: string | null;
}

export interface PeHistory {
  median: number | null;
  q1: number | null;
  q3: number | null;
  current: number | null;
  percentile: number | null;
}

export interface ResultQuality {
  period: string | null;
  is_material: boolean;
  cause_status: "unresolved_from_stored_evidence" | "not_applicable" | string;
  reported_net_profit: number | null;
  discontinued_profit: number | null;
  continuing_net_profit: number | null;
  discontinued_share_of_net_pct: number | null;
  one_off_share_pct: number | null;
  reported_ttm_net_profit: number | null;
  continuing_ttm_net_profit: number | null;
  reported_eps: number | null;
  continuing_eps: number | null;
  reported_pe: number | null;
  continuing_pe: number | null;
  valuation_basis: "continuing" | "reported" | string;
  summary: string;
  valuation_warning: string | null;
  source_fields: string[];
}

export interface ForecastAssumptions {
  period: string;
  revenue: number;
  gross_margin_pct: number;
  selling_costs_pct: number;
  admin_costs: number;
  other_operating: number;
  financial_net: number;
  tax_rate: number;
  depreciation: number | null;
}

export interface ForecastResult {
  period: string;
  pnl: {
    revenue: number;
    gross_profit: number;
    selling_costs: number;
    admin_costs: number;
    profit_on_sales: number;
    other_operating: number;
    operating_profit: number;
    financial_net: number;
    pretax_profit: number;
    tax: number;
    net_profit: number;
    ebitda: number | null;
  };
  yoy: {
    period: string;
    revenue: number | null;
    revenue_change_pct: number | null;
    net_profit: number | null;
    net_profit_change_pct: number | null;
  };
  forward: {
    ttm_net_profit: number | null;
    eps: number | null;
    pe: number | null;
  };
}

export interface Forecast {
  id: number | null;
  label: string | null;
  assumptions: ForecastAssumptions;
  result: ForecastResult;
  created_at: string | null;
}

export interface KeyIndicator {
  id: string;
  name: string;
  value: string; // preformatted by the backend — render as-is
  verdict: "good" | "neutral" | "bad" | "unknown";
  comment: string;
  importance: 1 | 2 | 3;
}

export interface MissingIndicator {
  id: string;
  name: string;
  why: string;
}

export interface Insights {
  size_code: "micro" | "small" | "mid" | "large" | null;
  size_label: string | null;
  // "finance" | "biotech_med" | "tech" | "energy" | "realestate" | "consumer" | "industrial" | "other"
  sector_group: string;
  sector_group_label: string;
  sector: string | null;
  key_indicators: KeyIndicator[];
  strengths: string[];
  concerns: string[];
  missing: MissingIndicator[];
  data_notes: string[];
  coverage: { available: number; selected: number; note: string } | null;
  summary: string;
  // Optional on purpose: a parallel backend task is adding an AI-refined path
  // for insights (mirrors thesis/scenarios `engine`); older/undecorated
  // dossiers won't have it — render the provenance chip only when present.
  engine?: "deterministic" | "ai";
}

export interface EntryQuality {
  // Framed as an analysis entrance, never a buy signal; Polish `label` + `rationale`
  code: "attractive" | "neutral" | "weak" | "insufficient_data";
  label: string;
  rationale: string;
}

export interface ThesisFactor {
  id: string;
  text: string; // mirrors the source Insight comment verbatim — render as-is
  weight: number;
  principle: string; // investor-principle tag (Polish)
}

export interface VerifyNextItem {
  id: string;
  text: string;
  why: string;
}

export interface StrategyRef {
  id: string;
  label: string;
}

// WP2b AI-path provenance. Loosely-typed `dict` on the backend, so we mirror it
// as an open record but surface the two fields the panel renders.
export interface AiNotes {
  model?: string;
  iterations?: number;
  [key: string]: unknown;
}

export interface Thesis {
  entry_quality: EntryQuality;
  pros: ThesisFactor[]; // backend sorts by weight desc — render in delivered order
  cons: ThesisFactor[];
  verify_next: VerifyNextItem[];
  thesis_read: string;
  disclaimer: string;
  valuation_basis: string; // forward vs trailing C/Z, honest about which
  strategy: StrategyRef; // which profile produced the read
  // WP2b provenance: "deterministic" (no key / AI fallback) or "ai"
  engine: "deterministic" | "ai";
  ai_notes: AiNotes | null;
}

// --- scenario simulation (stage SC) — mirrors schemas.ScenarioSetOut ----------

export interface ScenarioTargetMultiple {
  type: "cz" | "cwk" | "ev_ebitda"; // the effective multiple the target uses
  value: number | null; // the own-history quartile reverted to
  basis_label: string; // Polish; names the quartile + observation count (n)
}

export interface ScenarioHorizon {
  low_months: number;
  high_months: number;
  basis_label: string;
}

export interface ScenarioCompanyOutcome {
  direction: "negative" | "neutral" | "positive" | "unknown";
  label: string;
  description: string;
  mode?: "qualitative" | "priced";
}

export interface Scenario {
  id: string;
  kind: "negative" | "base" | "positive" | "event";
  label: string;
  probability: number; // 0–1; the set sums to 1
  narrative: string; // Polish, sourced (or a labelled data gap)
  target_multiple: ScenarioTargetMultiple;
  target_price: number | null; // PLN; null = missing driver (labelled gap)
  implied_upside_pct: number | null;
  horizon: ScenarioHorizon;
  drivers: string[];
  assumptions: string[];
  company_outcome?: ScenarioCompanyOutcome | null;
}

export interface ScenarioSet {
  scenarios: Scenario[];
  valuation_multiple: string; // cz | cwk | ev_ebitda
  current_price: number | null;
  weighted_expected_price: number | null; // PLN, Σ pᵢ·target_priceᵢ
  weighted_expected_upside_pct: number | null;
  priced_probability_mass?: number | null;
  framing: string; // "punkt wejścia w analizę, nie sygnał"
  disclaimer: string;
  quality_warnings?: string[];
  approved_assumption_sets?: AssumptionSet[];
  driver_sensitivity?: ScenarioDriverSensitivity;
  operating_bridge?: OperatingBridge;
  simulation_verification?: SimulationVerification;
  priced_operating_outcomes?: PricedOutcomeGate;
  engine: "deterministic" | "ai";
  ai_notes: AiNotes | null;
}

export interface PricedOutcomeGate {
  status: "blocked" | "approved";
  reason: string;
  required_checks: string[];
  verification: Record<string, unknown> | null;
  input_fingerprint?: string | null;
}

export interface SimulationVerificationCheck {
  id: string;
  verdict: "pass" | "fail" | "needs-human";
  evidence: string;
}

export interface SimulationVerification {
  status: "failed" | "math_passed" | "needs-human";
  checks: SimulationVerificationCheck[];
  summary: string;
  strict_verification_required: boolean;
}

// --- AI valuation (stage SC / WP4) — mirrors schemas.ValuationOut -------------

export interface ValuationPotential {
  value_pct: number | null; // anchored to the scenario set's weighted-EV upside
  range_pct: [number, number] | null; // [min, max] scenario upside band
  basis_label: string; // Polish; names the number (or the gap)
}

export interface ValuationConfidence {
  level: "low" | "medium" | "high"; // deterministic coverage heuristic
  rationale: string; // Polish; the counts + level (AI may reword)
}

export interface WhatWouldChange {
  id: string;
  text: string;
  why: string;
}

export interface Valuation {
  potential: ValuationPotential;
  confidence: ValuationConfidence;
  what_would_change: WhatWouldChange[];
  narrative: string;
  framing: string;
  disclaimer: string;
  engine: "deterministic" | "ai";
  ai_notes: AiNotes | null;
}

export interface ForumDistilledFact {
  topic?: string;
  type?: string;
  polarity?: string;
  fact: string;
  confidence?: string;
  source_post_ids?: number[];
}

// AI-distilled forum investment expectations (services/forum_expectations.py,
// wraps services/forum_distiller.py::distill_company_posts). `type` mirrors
// the backend classifier verbatim (currently the post-level "fact-claim" /
// "opinion" / "question" / "noise" tag — only "fact-claim" posts ever
// produce claims); the UI groups by a curated set of investment-argument
// labels when present and falls back to a catch-all bucket otherwise, so a
// taxonomy change on the backend degrades gracefully instead of breaking.
export interface ForumExpectationClaim {
  claim: string;
  confidence: "low" | "medium" | "high" | string;
  type: string;
  source_post_ids: number[];
}

export interface ForumExpectations {
  claims: ForumExpectationClaim[];
  model: string;
  updated_at: string;
  source_post_count: number;
}

export interface ForumIntelligence {
  industry_type: string | null;
  last_30d_post_count: number;
  last_30d_active_user_count: number;
  activity_spikes: unknown[];
  community_sentiment: string | null;
  distilled_facts: ForumDistilledFact[];
  // Optional: null/absent until a model-assisted forum expectation pass has
  // run at least once for this company.
  expectations?: ForumExpectations | null;
}

export interface ScraperHealth {
  status: "healthy" | "recovered" | "degraded" | "unknown";
  last_ok_at: string | null;
  last_error: { url: string; status: number | null; at: string } | null;
  errors_24h: number;
}

export interface EvidenceDocument {
  id: number;
  source_name: string;
  source_type: string;
  scope_key: string;
  canonical_url: string;
  first_seen_at: string;
  last_fetched_at: string;
  latest_content_hash: string;
  parser_version: string;
  last_fetch_status: number | null;
  version_count: number;
  first_version_at: string | null;
  latest_version_at: string | null;
  latest_parse_status: string;
  latest_parse_error: string | null;
  quality: {
    priority: number | null;
    label: string;
    allowed_use: string;
    limitation: string;
    terms_status: "review_required";
    terms_note: string;
    rate_policy: string;
  };
}

export interface AiUsageHealth {
  day: string;
  limits: { runs: number; provider_attempts: number; tokens: number };
  usage: {
    runs: number;
    logical_operations: number;
    provider_attempts: number;
    cache_hits: number;
    billable_calls: number;
    unknown_billing_calls: number;
    input_tokens: number;
    output_tokens: number;
  };
  providers: Array<{
    provider: string;
    logical_operations: number;
    provider_attempts: number;
    cache_hits: number;
    billable_calls: number;
    unknown_billing_calls: number;
    input_tokens: number;
    output_tokens: number;
  }>;
  pricing_status: "not_configured";
}

export interface LoginStatus {
  ok: boolean;
  status: "ok" | "configured" | "error" | "not_configured";
  detail: string;
}

// GET /api/diagnostics/workflow-status — provider-neutral Codex workflow health.
export interface WorkflowStatus {
  ok: boolean;
  queued: number;
  running: number;
  completed_24h: number;
  verified_24h: number;
  latest_run_at: string | null;
}

export interface AgentRun {
  id: number;
  workflow: string;
  trigger: string;
  status: string;
  company_id: number | null;
  model_role: string | null;
  model: string | null;
  orchestrator_model: string | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  available_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Falsifier {
  id: number;
  ticker: string;
  key: string;
  statement: string;
  status: "holding" | "warning" | "fired";
  reason: string;
  review_date: string | null;
  thesis_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface PortfolioSyncSummary {
  id: number;
  status: string;
  requested_at: string;
  fetched_at: string | null;
  snapshot_id: number | null;
  reused_snapshot: boolean;
  error: string | null;
}

export interface PortfolioSnapshotSummary {
  id: number;
  version: number;
  as_of: string;
  currency: string;
  total_value: number;
  cost_basis: number | null;
  profit: number | null;
  cash_value: number | null;
  benchmark_name: string | null;
  gaps: string[];
}

export interface PortfolioPosition {
  id: number;
  mapping_id: number;
  mapping_kind: "company" | "cash" | "other" | "ignored";
  mapping_status: "exact" | "confirmed" | "unmatched" | "ignored";
  company_id: number | null;
  company_ticker: string | null;
  ticker: string | null;
  name: string;
  asset_type: string | null;
  sector: string | null;
  currency: string;
  quote_date: string | null;
  quote: number | null;
  quantity: number | null;
  value: number;
  cost_basis: number | null;
  profit: number | null;
  allocation_pct: number | null;
}

export interface PortfolioHistoryPoint {
  date: string;
  value: number | null;
  contributed: number | null;
  profit: number | null;
  provider_return_pct: number | null;
  benchmark_return_pct: number | null;
  daily_change: number | null;
}

export interface PortfolioLiquidity {
  position_id: number;
  status: "provisional" | "unavailable";
  median_20d_traded_value_pln?: number;
  participation_pct?: number;
  estimated_exit_days?: number | null;
  series_status?: string;
  gap: string;
}

export interface PortfolioScenarioSensitivity {
  label: string;
  coverage_value_pct: number;
  portfolio_values: {
    negative: number;
    base: number;
    positive: number;
    weighted: number;
  };
  covered: Array<{
    position_id: number;
    valuation_snapshot_id: number;
    valuation_fingerprint: string;
    current_value: number;
    negative_value: number;
    base_value: number;
    positive_value: number;
    weighted_value: number;
  }>;
  exclusions: Array<{
    position_id: number;
    reason: string;
    latest_status?: string | null;
  }>;
}

export interface PortfolioReconciliation {
  status: "reconciled" | "unreconciled";
  retained_value: number;
  provider_total: number;
  delta: number;
  tolerance: number;
  affected_figures: string[];
}

export interface PortfolioHistoryQuality {
  status: "complete" | "partial";
  gaps: string[];
}

export interface PortfolioRiskFalsifier {
  id: number;
  key: string;
  statement: string;
  status: "holding" | "warning" | "fired";
  reason: string;
  review_date: string | null;
  thesis_hash: string | null;
  status_basis: string;
  created_at?: string;
  updated_at?: string;
  known_by_snapshot?: boolean;
  changed_after_snapshot?: boolean;
}

export interface PortfolioRiskCompany {
  position_id: number;
  company_id: number;
  ticker: string | null;
  value: number;
  sector: string | null;
  sector_basis: string;
  sector_known_by_snapshot: boolean;
  company_metadata_updated_at: string | null;
  asset_type: string | null;
  research: {
    id: number | null;
    status: string;
    as_of: string | null;
    gaps: unknown[];
    age_days: number | null;
    stale: boolean;
    stale_threshold_days: number;
    freshness_version: string;
  };
  profile: {
    id: number | null;
    archetype: string | null;
    archetype_version: string | null;
    driver_keys: string[];
  };
  falsifiers: PortfolioRiskFalsifier[];
  snapshot_known_falsifiers: PortfolioRiskFalsifier[];
  current_only_falsifiers: PortfolioRiskFalsifier[];
  snapshot_known_fired_count: number;
  snapshot_known_fired_falsifiers: PortfolioRiskFalsifier[];
  current_only_fired_count: number;
  current_only_fired_falsifiers: PortfolioRiskFalsifier[];
}

export interface PortfolioRiskContext {
  version: string;
  snapshot_as_of: string;
  context_generated_at: string;
  research_stale_threshold_days: number;
  companies: PortfolioRiskCompany[];
  shared_groups: Array<{
    type?: "sector" | "archetype";
    group_type?: "sector" | "archetype";
    label: string;
    company_ids: number[];
    position_ids: number[];
    value: number;
    time_basis: "snapshot-known" | "includes-current-only";
    evidence_basis: Array<{
      company_id: number;
      sector_basis: string;
      company_metadata_updated_at: string | null;
      research_snapshot_id: number | null;
      profile_id: number | null;
    }>;
    interpretation: string;
  }>;
  falsifier_status_basis: string;
}

export type PortfolioReviewStatus = "provisional" | "verified" | "rejected" | "needs-human";

export interface PortfolioReviewSections {
  summary: string;
  concentration: string[];
  liquidity: string[];
  history: string[];
  scenario_exposure: string[];
  risks: string[];
  next_checks: string[];
}

export interface PortfolioReviewSnapshot {
  id: number;
  portfolio_id: number;
  portfolio_snapshot_id: number;
  agent_run_id: number;
  verification_run_id: number;
  version: number;
  contract_version: string;
  status: PortfolioReviewStatus;
  draft_requested_model_role: string;
  draft_requested_model: string;
  draft_reasoning_effort: string;
  draft_actual_host_model: string;
  draft_substitution_or_escalation: string | null;
  as_of: string;
  sections: PortfolioReviewSections;
  input_manifest: Record<string, unknown>;
  gaps: string[];
  input_fingerprint: string;
  analytics_fingerprint: string;
  draft_fingerprint: string;
  artifact_fingerprint: string;
  verifier_result: {
    requested_model_role: "verifier_strict";
    requested_model: string;
    reasoning_effort: string;
    actual_host_model: string;
    substitution_or_escalation: string | null;
    verdict: "pass" | "fail" | "needs-human";
    checks: Record<string, boolean>;
    summary: string;
  };
  created_at: string;
}

export interface PortfolioReviewHistoryItem {
  id: number;
  version: number;
  status: PortfolioReviewStatus;
  draft_requested_model_role: string;
  draft_requested_model: string;
  draft_reasoning_effort: string;
  draft_actual_host_model: string;
  draft_substitution_or_escalation: string | null;
  portfolio_snapshot_id: number;
  as_of: string;
  gaps: string[];
  created_at: string;
}

export interface PortfolioReviewRun {
  id: number;
  status: "queued" | "running";
  created_at: string;
  snapshot_id: number | null;
  input_fingerprint: string | null;
  risk_context_fingerprint: string | null;
}

export interface PortfolioReviewQueueResult {
  agent_run_id: number;
  status: string;
  created: boolean;
  portfolio_id: number;
  portfolio_snapshot_id: number;
  input_fingerprint: string;
  analytics_fingerprint: string;
  risk_context_fingerprint: string;
}

export interface PortfolioWorkspace {
  configured: boolean;
  provider: string;
  portfolio_label: string | null;
  latest_sync: PortfolioSyncSummary | null;
  last_sync_failure: PortfolioSyncSummary | null;
  snapshot: PortfolioSnapshotSummary | null;
  positions: PortfolioPosition[];
  reconciliation: PortfolioReconciliation | null;
  concentration: {
    status: "complete" | "partial";
    basis: "provider_total" | "retained_positions_total";
    basis_value: number;
    top1_pct: number;
    top3_pct: number;
    hhi: number;
    sectors: Array<{ label: string; value: number; allocation_pct: number }>;
    asset_types: Array<{ label: string; value: number; allocation_pct: number }>;
  } | null;
  history: PortfolioHistoryPoint[];
  history_quality: PortfolioHistoryQuality | null;
  liquidity: PortfolioLiquidity[];
  scenario_sensitivity: PortfolioScenarioSensitivity | null;
  risk_context: PortfolioRiskContext | null;
  performance_methods: {
    provider_return: string;
    benchmark: string;
    twr: string;
    xirr: string;
    gap: string;
  } | null;
  coverage: {
    mapped_company_value_pct: number | null;
    unmapped_positions: number;
    retained_position_value_pct?: number | null;
    analytics_available: boolean;
    analytics_status: "complete" | "partial";
  } | null;
  portfolio_review: {
    latest: PortfolioReviewSnapshot | null;
    history: PortfolioReviewHistoryItem[];
    active_run: PortfolioReviewRun | null;
  };
}

export type PortfolioSyncResult = PortfolioWorkspace & { sync: PortfolioSyncSummary };
