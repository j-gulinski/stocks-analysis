/**
 * Typed API client. Every call goes to same-origin `/api/...` — the route
 * handler proxies it to FastAPI (never call the backend directly).
 */
import type {
  AiUsageHealth,
  AssumptionItem,
  AssumptionScenarioKind,
  AssumptionSet,
  AssumptionStatus,
  AgentEvaluationRun,
  AgentEvaluationRunCreate,
  AgentEvaluationRunDetail,
  AgentRun,
  AgentRunCreate,
  Analysis,
  AnalysisRun,
  BacktestRun,
  BacktestRunCreate,
  BacktestRunDetail,
  DecisionJournalEntry,
  Dividend,
  DiscoveryResult,
  Dossier,
  EvidenceDocument,
  Financials,
  Falsifier,
  Forecast,
  ForecastAssumptions,
  ForumPage,
  ForumSync,
  ForumTopic,
  IndicatorPoint,
  LoginStatus,
  MonitorCheckResult,
  PricePoint,
  Position,
  PreSessionBriefResult,
  ResearchCase,
  ResearchCaseCreateResult,
  ResearchCaseSummary,
  ResearchCaseStepHistory,
  ResearchCaseState,
  ResearchCaseStep,
  RefreshSummary,
  ScraperHealth,
  WorkflowStatus,
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

// --------------------------------------------------------------- discovery
export const getDiscovery = (
  minRating = 5,
  minFScore: number | null = null,
) => {
  const params = new URLSearchParams({ min_rating: String(minRating) });
  if (minFScore != null) params.set("min_f_score", String(minFScore));
  return request<DiscoveryResult>(`/discovery?${params}`);
};

export const refreshDiscovery = (minRating = 8, minFScore: number | null = 7) => {
  const params = new URLSearchParams({ min_rating: String(minRating) });
  if (minFScore != null) params.set("min_f_score", String(minFScore));
  return request<DiscoveryResult>(`/discovery/refresh?${params}`, { method: "POST" });
};

// ---------------------------------------------------------- research cases
export const getResearchCases = () => request<ResearchCaseSummary[]>("/research-cases");

export const addResearchCase = (payload: {
  ticker: string;
  source_document_version_id?: number | null;
}) => request<ResearchCaseCreateResult>("/research-cases", {
  method: "POST",
  body: JSON.stringify(payload),
});

// ---------------------------------------------------------------- companies
export const getDossier = (ticker: string) =>
  request<Dossier>(`/companies/${encodeURIComponent(ticker)}`);

export const getEvidenceDocuments = (ticker: string) =>
  request<EvidenceDocument[]>(
    `/companies/${encodeURIComponent(ticker)}/evidence/documents`,
  );

export const getResearchCase = (ticker: string, purpose = "investment-research") =>
  request<ResearchCase>(
    `/companies/${encodeURIComponent(ticker)}/research-case?purpose=${encodeURIComponent(purpose)}`,
  );

export const getResearchCaseHistory = (ticker: string, purpose = "investment-research") =>
  request<ResearchCaseStepHistory[]>(
    `/companies/${encodeURIComponent(ticker)}/research-case/history?purpose=${encodeURIComponent(purpose)}`,
  );

export const createResearchCase = (ticker: string, purpose = "investment-research") =>
  request<ResearchCase>(`/companies/${encodeURIComponent(ticker)}/research-case`, {
    method: "POST",
    body: JSON.stringify({ purpose }),
  });

export const updateResearchCase = (
  ticker: string,
  patch: {
    state?: ResearchCaseState;
    current_step?: ResearchCaseStep;
    blocked_reason?: string | null;
    change_reason?: string | null;
    as_of?: string | null;
  },
) =>
  request<ResearchCase>(`/companies/${encodeURIComponent(ticker)}/research-case`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const getAssumptionSets = (ticker: string, purpose = "investment-research") =>
  request<AssumptionSet[]>(
    `/companies/${encodeURIComponent(ticker)}/research-case/assumptions?purpose=${encodeURIComponent(purpose)}`,
  );

export const createAssumptionSet = (
  ticker: string,
  payload: {
    scenario_kind: AssumptionScenarioKind;
    label: string;
    status?: AssumptionStatus;
    as_of?: string | null;
    assumptions: AssumptionItem[];
  },
) =>
  request<AssumptionSet>(`/companies/${encodeURIComponent(ticker)}/research-case/assumptions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const updateAssumptionSet = (
  ticker: string,
  id: number,
  patch: Partial<Pick<AssumptionSet, "label" | "status" | "as_of" | "assumptions">>,
) =>
  request<AssumptionSet>(
    `/companies/${encodeURIComponent(ticker)}/research-case/assumptions/${id}`,
    { method: "PATCH", body: JSON.stringify(patch) },
  );

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

// Legacy provider endpoint remains available while the Review UI moves to
// verifier-gated, provider-neutral Codex workflows.
export const runAnalysis = (ticker: string) =>
  request<Analysis>(`/companies/${encodeURIComponent(ticker)}/analyses`, {
    method: "POST",
  });

export const listAnalyses = (ticker: string) =>
  request<Analysis[]>(`/companies/${encodeURIComponent(ticker)}/analyses`);

export const listAnalysisRuns = (ticker: string) =>
  request<AnalysisRun[]>(`/companies/${encodeURIComponent(ticker)}/analysis-runs`);

export const listAgentRuns = (params: {
  status?: string;
  workflow?: string;
  ticker?: string;
  limit?: number;
} = {}) => {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.workflow) search.set("workflow", params.workflow);
  if (params.ticker) search.set("ticker", params.ticker);
  if (params.limit) search.set("limit", String(params.limit));
  const query = search.toString();
  return request<AgentRun[]>(`/agent-runs${query ? `?${query}` : ""}`);
};

export const getDecisionJournal = (ticker: string, limit = 20) =>
  request<DecisionJournalEntry[]>(
    `/companies/${encodeURIComponent(ticker)}/decision-journal?limit=${limit}`,
  );

export const createDecisionJournalEntry = (
  ticker: string,
  payload: Omit<DecisionJournalEntry, "id" | "ticker" | "thesis_hash" | "created_by" | "created_at">,
) =>
  request<DecisionJournalEntry>(
    `/companies/${encodeURIComponent(ticker)}/decision-journal`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );

export const queueAgentRun = (payload: AgentRunCreate) =>
  request<AgentRun>("/agent-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const preparePreSessionBrief = (payload: {
  ticker?: string;
  trigger?: string;
  orchestrator_model?: string;
  fetch_details?: boolean;
  queue?: boolean;
} = {}) =>
  request<PreSessionBriefResult>("/agent-runs/pre-session", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const checkMonitor = (ticker: string) =>
  request<MonitorCheckResult>(
    `/companies/${encodeURIComponent(ticker)}/monitor/check`,
    { method: "POST" },
  );

export const getFalsifiers = (ticker: string) =>
  request<Falsifier[]>(`/companies/${encodeURIComponent(ticker)}/falsifiers`);

export const createFalsifier = (
  ticker: string,
  payload: Omit<Falsifier, "id" | "ticker" | "created_at" | "updated_at" | "thesis_hash">,
) =>
  request<Falsifier>(`/companies/${encodeURIComponent(ticker)}/falsifiers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const updateFalsifier = (
  ticker: string,
  id: number,
  payload: Pick<Falsifier, "status" | "reason" | "review_date">,
) =>
  request<Falsifier>(
    `/companies/${encodeURIComponent(ticker)}/falsifiers/${id}`,
    { method: "PATCH", body: JSON.stringify(payload) },
  );

export const getPositions = (ticker?: string) => {
  const query = ticker ? `?ticker=${encodeURIComponent(ticker)}` : "";
  return request<Position[]>(`/positions${query}`);
};

export const listBacktestRuns = (params: { limit?: number; strategy?: string } = {}) => {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.strategy) search.set("strategy", params.strategy);
  const query = search.toString();
  return request<BacktestRun[]>(`/backtest-runs${query ? `?${query}` : ""}`);
};

export const getBacktestRun = (id: number) =>
  request<BacktestRunDetail>(`/backtest-runs/${id}`);

export const runBacktest = (payload: BacktestRunCreate) =>
  request<BacktestRunDetail>("/backtest-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listAgentEvaluationRuns = (
  params: { limit?: number; strategy?: string } = {},
) => {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.strategy) search.set("strategy", params.strategy);
  const query = search.toString();
  return request<AgentEvaluationRun[]>(
    `/agent-evaluation-runs${query ? `?${query}` : ""}`,
  );
};

export const getAgentEvaluationRun = (id: number) =>
  request<AgentEvaluationRunDetail>(`/agent-evaluation-runs/${id}`);

export const runAgentEvaluation = (payload: AgentEvaluationRunCreate) =>
  request<AgentEvaluationRunDetail>("/agent-evaluation-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });

// ----------------------------------------------------------------- settings
export const getHealth = () => request<{ status: string }>("/health");
export const getForumLoginStatus = () => request<LoginStatus>("/forum/login-status");
export const getBrLoginStatus = () => request<LoginStatus>("/diagnostics/br-login-status");
export const getScrapersHealth = () =>
  request<Record<string, ScraperHealth>>("/health/scrapers");
export const getWorkflowStatus = () =>
  request<WorkflowStatus>("/diagnostics/workflow-status");
export const getAiUsage = () => request<AiUsageHealth>("/health/ai-usage");
