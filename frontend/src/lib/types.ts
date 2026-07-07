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
