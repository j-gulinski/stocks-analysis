/**
 * API contracts — mirror of backend/app/api/schemas.py (snake_case preserved
 * on purpose: one shape end to end, no mapping layer to maintain).
 */

export interface WatchlistItem {
  ticker: string;
  name: string | null;
  note: string | null;
  added_at: string;
}

export interface DiscoveryCandidate {
  ticker: string;
  name: string | null;
  report_period: string;
  br_rating: string | null;
  br_rating_value: number | null;
  piotroski_f_score: number | null;
  reasons: string[];
  caveat: string;
}

export interface DiscoveryResult {
  source: string;
  source_url: string;
  as_of: string;
  universe_count: number;
  result_count: number;
  source_note: string;
  candidates: DiscoveryCandidate[];
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
}

export interface Ttm {
  net_profit: number | null;
  eps: number | null;
  pe: number | null;
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
}

export interface ScenarioSet {
  scenarios: Scenario[];
  valuation_multiple: string; // cz | cwk | ev_ebitda
  current_price: number | null;
  weighted_expected_price: number | null; // PLN, Σ pᵢ·target_priceᵢ
  weighted_expected_upside_pct: number | null;
  framing: string; // "punkt wejścia w analizę, nie sygnał"
  disclaimer: string;
  quality_warnings?: string[];
  engine: "deterministic" | "ai";
  ai_notes: AiNotes | null;
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

// Shared shape for market_data.forecast_consensus / advanced_metrics cells
// (backend: services/market_data.py, services/refresh.py). `period` shows up
// on a couple of legacy indicator-sourced entries (roic/fcf) instead of
// `unit` — keep both optional rather than modelling two variants.
export interface MarketDataMetric {
  value: number | null;
  unit?: string;
  period?: string;
  source?: string;
}

export interface Dossier {
  company: Company;
  freshness: {
    financials_scraped_at: string | null;
    last_price_date: string | null;
    forum_last_synced_at: string | null;
  };
  quarters: QuarterMetrics[];
  ttm: Ttm;
  pe_history: PeHistory;
  net_cash: { value: number | null; note: string };
  market_data: {
    industry_type: string | null;
    priority_values: Record<string, unknown>;
    // Keyed by YEAR (e.g. "2025", "2026" — raw BiznesRadar consensus column
    // labels), then by metric code (revenue/ebitda/operating_profit/
    // net_income/capex/depreciation/ebitda_margin_pct/operating_margin_pct/
    // net_margin_pct/pe) — mirrors services/refresh.py::_upsert_forecasts +
    // services/market_data.py::merge_premium_market_data. Money metrics
    // arrive in tys. PLN (unit "tys. PLN"); margins in "%"; pe in "x".
    forecast_consensus: Record<string, Record<string, MarketDataMetric>>;
    // Polish trust caveat (services/market_data.py::FORECAST_CONSENSUS_NOTE)
    // — sibling key, NOT nested inside forecast_consensus (that dict is
    // keyed purely by year). Optional: absent on dossiers built before this
    // field existed.
    forecast_consensus_note?: string;
    // roic/fcf/enterprise_value plus (new) ebitda_ttm/capex_ttm/
    // depreciation_ttm from the /prognozy O4K column — all {value, unit,
    // source} shaped, but some legacy entries carry `period` instead of
    // `unit`, so keep the value type loose.
    advanced_metrics: Record<string, MarketDataMetric>;
    dividend_coverage: Record<string, unknown>;
  };
  analysis_context_status?: {
    ready_for_ai: boolean;
    missing: string[];
    industry_type: string | null;
    premium: {
      forecast_years: string[];
      has_roic: boolean;
      has_fcf: boolean;
      has_enterprise_value: boolean;
      dividend_coverage_status: string | null;
    };
    forum: {
      has_intelligence: boolean;
      distilled_facts_count: number;
      last_30d_post_count: number;
      last_30d_active_user_count: number;
    };
  } | null;
  dividends: Dividend[];
  prescore: Prescore;
  insights: Insights;
  // Optional on purpose: older cached dossiers predate the thesis layer, so the
  // UI must render gracefully when it is absent (backend shape has it required).
  thesis?: Thesis;
  // Same graceful-degradation contract for the scenario layer (stage SC).
  scenarios?: ScenarioSet;
  // And for the AI valuation layer (stage SC / WP4); backend shape has it
  // required, older cached dossiers predate it → optional here.
  valuation?: Valuation;
  latest_forecast: Forecast | null;
  forum: {
    topics: number;
    posts: number;
    last_post_at: string | null;
    intelligence?: ForumIntelligence | null;
  };
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

export interface ForumTopic {
  id: number;
  url: string;
  title: string | null;
  last_post_at: string | null;
  last_synced_at: string | null;
}

export interface ForumPost {
  phpbb_post_id: number;
  author: string;
  posted_at: string | null;
  upvotes: number | null;
}

export interface ScraperHealth {
  status: "healthy" | "recovered" | "degraded" | "unknown";
  last_ok_at: string | null;
  last_error: { url: string; status: number | null; at: string } | null;
  errors_24h: number;
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

export interface ForumPage {
  total: number;
  page: number;
  page_size: number;
  posts: ForumPost[];
}

export interface ForumSync {
  topic_id: number;
  new_posts: number;
  total_posts: number;
}

export interface LoginStatus {
  ok: boolean;
  status: "ok" | "error" | "not_configured";
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

// --- Analysis history: old rows remain readable while provider-neutral
// `analysis_runs` become the primary CX path. -----------------------------

export interface AnalysisCatalyst {
  type: string;
  description: string;
  horizon: string;
  priced_in: "tak" | "nie" | "częściowo" | "nieznane";
}

export interface AnalysisChecklistItem {
  id: string;
  item: string;
  verdict: "spełnia" | "nie spełnia" | "nieznane";
  evidence: string;
}

export interface ForumInsight {
  claim: string;
  confidence: "low" | "medium" | "high";
  post_ids: number[];
}

export interface AnalysisPotential {
  upside: string;
  downside: string;
}

export interface AnalysisScenario {
  kind: "negative" | "base" | "positive" | "event";
  title: string;
  description: string;
  key_drivers: string[];
  watch_items: string[];
  probability: string;
}

export interface AnalysisVerdict {
  thesis: string;
  catalysts: AnalysisCatalyst[];
  checklist: AnalysisChecklistItem[];
  red_flags: string[];
  one_off_risk: string;
  forum_insights: ForumInsight[];
  alignment_score: number | null;
  potential: AnalysisPotential;
  scenarios?: AnalysisScenario[];
  verify_next: VerifyNextItem[]; // reuses the thesis type — identical shape
  summary_pl: string;
}

export interface Analysis {
  id: number;
  created_at: string;
  completed_at: string | null;
  as_of: string | null;
  provider: string | null;
  model: string;
  purpose: string;
  status: string;
  skill_version: string | null;
  skill_hash: string | null;
  validation: Record<string, unknown> | null;
  latency_ms: number | null;
  alignment_score: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  input_hash: string | null;
  created_by: string | null;
  output: AnalysisVerdict;
}

export interface AnalysisRun {
  id: number;
  company_id: number;
  agent_run_id: number | null;
  source: string;
  workflow: string;
  model_role: string;
  model: string;
  status: string;
  verification_status: string;
  input_snapshot: Record<string, unknown>;
  output: Record<string, unknown>;
  verification: Record<string, unknown>;
  alignment_score: number | null;
  created_by: string | null;
  created_at: string;
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
  created_at: string;
  updated_at: string;
}

export interface AgentRunCreate {
  workflow: string;
  ticker?: string;
  trigger?: string;
  model_role?: string;
  model?: string;
  orchestrator_model?: string;
  inputs?: Record<string, unknown>;
}

export interface PreSessionBriefResult {
  ok: boolean;
  espi_poll: Record<string, unknown>;
  agent_run: AgentRun | null;
}

export interface BacktestObservation {
  id: number;
  backtest_run_id: number;
  company_id: number;
  as_of_date: string;
  known_inputs: Record<string, unknown>;
  signal: Record<string, unknown>;
  outcome: Record<string, unknown>;
  created_at: string;
}

export interface BacktestRun {
  id: number;
  agent_run_id: number | null;
  strategy: string;
  from_date: string | null;
  to_date: string | null;
  status: string;
  model_role: string | null;
  model: string | null;
  parameters: Record<string, unknown>;
  summary: {
    observation_count?: number;
    signal_counts?: Record<string, number>;
    average_return_pct_by_window?: Record<string, number | null>;
    known_inputs_policy?: string;
    [key: string]: unknown;
  };
  verification_status: string;
  created_at: string;
}

export interface BacktestRunDetail extends BacktestRun {
  observations: BacktestObservation[];
}

export interface BacktestRunCreate {
  strategy?: string;
  from_date: string;
  to_date: string;
  ticker?: string;
  outcome_windows?: number[];
  financial_availability_policy?: "scraped_at" | "estimated_period_lag";
  report_lag_days?: number;
}

export interface AgentEvaluationObservation {
  id: number;
  evaluation_run_id: number;
  analysis_run_id: number;
  company_id: number;
  as_of_date: string;
  known_inputs: Record<string, unknown>;
  prediction: Record<string, unknown>;
  outcome: Record<string, unknown>;
  score: Record<string, unknown>;
  created_at: string;
}

export interface AgentEvaluationRun {
  id: number;
  agent_run_id: number | null;
  strategy: string;
  from_date: string | null;
  to_date: string | null;
  status: string;
  model_role: string | null;
  model: string | null;
  parameters: Record<string, unknown>;
  summary: Record<string, unknown>;
  verification_status: string;
  created_at: string;
}

export interface AgentEvaluationRunDetail extends AgentEvaluationRun {
  observations: AgentEvaluationObservation[];
}

export interface AgentEvaluationRunCreate {
  strategy?: string;
  from_date?: string | null;
  to_date?: string | null;
  ticker?: string;
  workflow?: string;
  outcome_windows?: number[];
}
