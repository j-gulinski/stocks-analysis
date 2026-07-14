/**
 * Typed API client. Every call goes to same-origin `/api/...` — the route
 * handler proxies it to FastAPI (never call the backend directly).
 */
import type {
  AiUsageHealth,
  AgentRun,
  Dividend,
  DiscoveryResult,
  Dossier,
  EvidenceDocument,
  Financials,
  Falsifier,
  IndicatorPoint,
  LoginStatus,
  PricePoint,
  PortfolioSyncResult,
  PortfolioReviewQueueResult,
  PortfolioWorkspace,
  ResearchCaseCreateResult,
  ResearchReviewQueueResult,
  ResearchCaseSummary,
  CompanyProfile,
  ResearchArchetype,
  CompanyOverlay,
  ResearchDriver,
  ResearchKpi,
  ResearchWorkspace,
  RefreshSummary,
  ScraperHealth,
  WorkflowStatus,
  ValuationPreview,
  ValuationQueueRequest,
  ValuationQueueResult,
  ValuationRequest,
  ValuationWorkspace,
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
export const getDiscovery = () => request<DiscoveryResult>("/discovery");

export const refreshDiscovery = () =>
  request<DiscoveryResult>("/discovery/refresh", { method: "POST" });

// ---------------------------------------------------------- research cases
export const getResearchCases = () => request<ResearchCaseSummary[]>("/research-cases");

export const getResearchWorkspace = (ticker: string) =>
  request<ResearchWorkspace>(
    `/research-cases/by-ticker/${encodeURIComponent(ticker)}`,
  );

export const addResearchCase = (payload: { ticker: string }) => request<ResearchCaseCreateResult>("/research-cases", {
  method: "POST",
  body: JSON.stringify(payload),
});

export const queueResearchReview = (researchCaseId: number) =>
  request<ResearchReviewQueueResult>(`/research-cases/${researchCaseId}/review-runs`, {
    method: "POST",
  });

export const confirmResearchProfile = (
  researchCaseId: number,
  payload: {
    base_profile_id: number;
    reason: string;
    archetype: ResearchArchetype;
    company_overlay: CompanyOverlay;
    drivers: ResearchDriver[];
    kpis: ResearchKpi[];
  },
) => request<CompanyProfile>(`/research-cases/${researchCaseId}/profiles`, {
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

// ------------------------------------------------------ canonical valuation
export const getValuationWorkspace = (researchCaseId: number) =>
  request<ValuationWorkspace>(`/research-cases/${researchCaseId}/valuation-workspace`);

export const previewValuation = (researchCaseId: number, payload: ValuationRequest) =>
  request<ValuationPreview>(`/research-cases/${researchCaseId}/valuation-preview`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const queueValuation = (researchCaseId: number, payload: ValuationQueueRequest) =>
  request<ValuationQueueResult>(`/research-cases/${researchCaseId}/valuation-runs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

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

// ---------------------------------------------------------- agent-run audit
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

// --------------------------------------------------------------- portfolio
// Opening Portfolio is a stored-data read. Only the explicit sync command may
// contact myfund and persist a new dated snapshot.
export const getPortfolioWorkspace = () =>
  request<PortfolioWorkspace>("/portfolios/workspace");

export const syncMyfundPortfolio = () =>
  request<PortfolioSyncResult>("/portfolios/sync/myfund", { method: "POST" });

export const queuePortfolioReview = () =>
  request<PortfolioReviewQueueResult>("/portfolios/review-runs", { method: "POST" });

// ----------------------------------------------------------------- settings
export const getHealth = () => request<{ status: string }>("/health");
export const getBrLoginStatus = () => request<LoginStatus>("/diagnostics/br-login-status");
export const getScrapersHealth = () =>
  request<Record<string, ScraperHealth>>("/health/scrapers");
export const getWorkflowStatus = () =>
  request<WorkflowStatus>("/diagnostics/workflow-status");
export const getAiUsage = () => request<AiUsageHealth>("/health/ai-usage");
