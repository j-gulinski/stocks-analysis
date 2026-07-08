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
  forum: { topics: number; posts: number; last_post_at: string | null };
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
  content_text: string;
  upvotes: number | null;
}

export interface ScraperHealth {
  last_ok_at: string | null;
  last_error: { url: string; status: number | null; at: string } | null;
  errors_24h: number;
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
  detail: string;
}

// --- AI analysis (Phase 5, P5.6/P5.7) — mirrors schemas.AnalysisOut + the
// `zapisz_analize` tool input_schema (backend/app/services/claude_client.py,
// single source of truth for the verdict shape) ---------------------------

export interface AnalysisCatalyst {
  type: string;
  description: string;
  horizon: string;
  priced_in: "tak" | "nie" | "częściowo" | "nieznane";
}

export interface AnalysisChecklistItem {
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

export interface AnalysisVerdict {
  thesis: string;
  catalysts: AnalysisCatalyst[];
  checklist: AnalysisChecklistItem[];
  red_flags: string[];
  one_off_risk: string;
  forum_insights: ForumInsight[];
  alignment_score: number;
  potential: AnalysisPotential;
  verify_next: VerifyNextItem[]; // reuses the thesis type — identical shape
  summary_pl: string;
}

export interface Analysis {
  id: number;
  created_at: string;
  model: string;
  alignment_score: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_by: string | null;
  output: AnalysisVerdict;
}
