/**
 * Typed API client. Every call goes to same-origin `/api/...` — the route
 * handler proxies it to FastAPI (never call the backend directly).
 */
import type {
  AiUsageHealth,
  Analysis,
  Dividend,
  Dossier,
  DiscoveryResult,
  Financials,
  Forecast,
  ForecastAssumptions,
  ForumPage,
  ForumSync,
  ForumTopic,
  IndicatorPoint,
  LoginStatus,
  PricePoint,
  RefreshSummary,
  ScraperHealth,
  WatchlistItem,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body — keep the status text */
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ---------------------------------------------------------------- watchlist
export const getWatchlist = () => request<WatchlistItem[]>("/watchlist");

export const addToWatchlist = (ticker: string, note?: string) =>
  request<WatchlistItem>("/watchlist", {
    method: "POST",
    body: JSON.stringify({ ticker, note }),
  });

export const removeFromWatchlist = (ticker: string) =>
  request<void>(`/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });

// --------------------------------------------------------------- discovery
export const getDiscovery = (
  minRating = 7,
  minFScore: number | null = 5,
  force = false,
) => {
  const params = new URLSearchParams({
    min_rating: String(minRating),
    force: String(force),
  });
  if (minFScore != null) params.set("min_f_score", String(minFScore));
  return request<DiscoveryResult>(`/discovery?${params}`);
};

// ---------------------------------------------------------------- companies
export const getDossier = (ticker: string) =>
  request<Dossier>(`/companies/${encodeURIComponent(ticker)}`);

export const refreshCompany = (ticker: string, force = false) =>
  request<RefreshSummary>(
    `/companies/${encodeURIComponent(ticker)}/refresh?force=${force}`,
    { method: "POST" },
  );

export const getFinancials = (
  ticker: string,
  statement: Financials["statement"],
  freq: Financials["freq"],
) =>
  request<Financials>(
    `/companies/${encodeURIComponent(ticker)}/financials?statement=${statement}&freq=${freq}`,
  );

export const getIndicators = (ticker: string) =>
  request<Record<string, IndicatorPoint[]>>(
    `/companies/${encodeURIComponent(ticker)}/indicators`,
  );

export const getDividends = (ticker: string) =>
  request<Dividend[]>(`/companies/${encodeURIComponent(ticker)}/dividends`);

export const getPrices = (ticker: string, days = 365) =>
  request<PricePoint[]>(`/companies/${encodeURIComponent(ticker)}/prices?days=${days}`);

// ---------------------------------------------------------------- forecasts
export const getForecastDefaults = (ticker: string) =>
  request<ForecastAssumptions>(
    `/companies/${encodeURIComponent(ticker)}/forecast-defaults`,
  );

export const computeForecast = (ticker: string, assumptions: ForecastAssumptions) =>
  request<Forecast>(`/companies/${encodeURIComponent(ticker)}/forecasts`, {
    method: "POST",
    body: JSON.stringify({ assumptions, save: false }),
  });

export const saveForecast = (
  ticker: string,
  assumptions: ForecastAssumptions,
  label: string | null,
) =>
  request<Forecast>(`/companies/${encodeURIComponent(ticker)}/forecasts`, {
    method: "POST",
    body: JSON.stringify({ assumptions, label, save: true }),
  });

export const listForecasts = (ticker: string) =>
  request<Forecast[]>(`/companies/${encodeURIComponent(ticker)}/forecasts`);

// -------------------------------------------------------------------- forum
export const linkForumTopic = (url: string, ticker: string) =>
  request<ForumTopic>("/forum/topics", {
    method: "POST",
    body: JSON.stringify({ url, ticker }),
  });

export const syncForumTopic = (topicId: number) =>
  request<ForumSync>(`/forum/topics/${topicId}/sync`, { method: "POST" });

export const getForumTopics = (ticker: string) =>
  request<ForumTopic[]>(`/companies/${encodeURIComponent(ticker)}/forum/topics`);

export const getForumPosts = (
  ticker: string,
  page = 1,
  author?: string,
  sort: "new" | "top" = "new",
) => {
  const params = new URLSearchParams({ page: String(page), page_size: "25", sort });
  if (author) params.set("author", author);
  return request<ForumPage>(
    `/companies/${encodeURIComponent(ticker)}/forum?${params}`,
  );
};

// -------------------------------------------------------------- analyses
// 429 (daily cap) / 503 (no ANTHROPIC_API_KEY) surface as ApiError with the
// backend's Polish `detail` — the panel renders that message as-is.
export const runAnalysis = (ticker: string) =>
  request<Analysis>(`/companies/${encodeURIComponent(ticker)}/analyses`, {
    method: "POST",
  });

export const listAnalyses = (ticker: string) =>
  request<Analysis[]>(`/companies/${encodeURIComponent(ticker)}/analyses`);

// ----------------------------------------------------------------- settings
export const getHealth = () => request<{ status: string }>("/health");
export const getForumLoginStatus = () => request<LoginStatus>("/forum/login-status");
export const getBrLoginStatus = () => request<LoginStatus>("/diagnostics/br-login-status");
export const getScrapersHealth = () =>
  request<Record<string, ScraperHealth>>("/health/scrapers");
export const getAiUsage = () => request<AiUsageHealth>("/health/ai-usage");
