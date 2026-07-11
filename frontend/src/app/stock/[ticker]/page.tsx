"use client";

/** Progressive company research workspace: one canonical brief, then evidence. */
import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  IconAlertTriangle,
  IconBrain,
  IconChartBar,
  IconDatabase,
  IconFileAnalytics,
  IconRefresh,
  IconSparkles,
  IconX,
} from "@tabler/icons-react";
import {
  createResearchCase,
  getDossier,
  getResearchCase,
  getResearchCaseHistory,
  getResearchWorkspace,
  listAgentRuns,
  listAnalysisRuns,
  refreshCompany,
  updateResearchCase,
} from "@/lib/api";
import { findCurrentVerifiedRun } from "@/lib/analysis";
import { ApiError } from "@/lib/api";
import { hasDossierData } from "@/lib/dossier";
import { useApi } from "@/lib/hooks";
import { fmtDate, fmtMcap, fmtPln, relativeDate, staleDays } from "@/lib/format";
import { friendlySourceStatus } from "@/lib/source-status";
import { LoadingMessages, SkeletonCards } from "@/components/Loading";
import InsightsPanel from "@/components/InsightsPanel";
import InvestorMemo from "@/components/InvestorMemo";
import PrescoreChecklist from "@/components/PrescoreChecklist";
import PriceChart from "@/components/PriceChart";
import FinancialsTable from "@/components/FinancialsTable";
import QuarterlyCharts from "@/components/QuarterlyCharts";
import ForecastPanel from "@/components/ForecastPanel";
import ForumPanel from "@/components/ForumPanel";
import AnalysisPanel from "@/components/AnalysisPanel";
import ScenariosPanel from "@/components/ScenariosPanel";
import CompanyReport from "@/components/CompanyReport";
import AssumptionSetsPanel from "@/components/AssumptionSetsPanel";
import DecisionJournalPanel from "@/components/DecisionJournalPanel";
import FalsifiersPanel from "@/components/FalsifiersPanel";
import PositionPanel from "@/components/PositionPanel";
import EvidenceSourcesPanel from "@/components/EvidenceSourcesPanel";
import ResearchSnapshotView from "@/components/ResearchSnapshotView";
import type { AgentRun, AnalysisRun, ResearchCase, ResearchCaseStepHistory } from "@/lib/types";

const TABS = [
  { id: "Report", label: "Raport", icon: IconFileAnalytics },
  { id: "Charts", label: "Wykresy", icon: IconChartBar },
  { id: "Audit", label: "Źródła", icon: IconDatabase },
  { id: "History", label: "Codex", icon: IconBrain },
] as const;
type Tab = (typeof TABS)[number]["id"];

const CASE_STATE_LABELS: Record<ResearchCase["state"], string> = {
  new: "nowy",
  ingesting: "zbieranie danych",
  data_review: "przegląd danych",
  business_model: "model biznesowy",
  thesis: "teza",
  scenarios: "scenariusze",
  review: "weryfikacja",
  monitoring: "monitoring",
  blocked: "zablokowany",
  closed: "zamknięty",
};

const CASE_STEP_LABELS: Record<ResearchCase["current_step"], string> = {
  ingest: "ingest",
  data_review: "przegląd danych",
  business_model: "model biznesowy",
  thesis: "teza",
  scenarios: "scenariusze",
  review: "weryfikacja",
  monitoring: "monitoring",
};

export default function StockPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker: rawTicker } = use(params);
  const ticker = rawTicker.toUpperCase();
  const [tab, setTab] = useState<Tab>("Report");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshSummary, setRefreshSummary] = useState<Record<string, string> | null>(null);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[] | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRun[] | null>(null);
  const [researchCase, setResearchCase] = useState<ResearchCase | null>(null);
  const [creatingCase, setCreatingCase] = useState(false);
  const [caseStateDraft, setCaseStateDraft] = useState<ResearchCase["state"]>("new");
  const [caseStepDraft, setCaseStepDraft] = useState<ResearchCase["current_step"]>("ingest");
  const [caseReasonDraft, setCaseReasonDraft] = useState("");
  const [caseChangeReason, setCaseChangeReason] = useState("");
  const [savingCase, setSavingCase] = useState(false);
  const [caseUpdateError, setCaseUpdateError] = useState<string | null>(null);
  const [caseHistory, setCaseHistory] = useState<ResearchCaseStepHistory[]>([]);
  const [showLegacyDossier, setShowLegacyDossier] = useState(false);
  const { data: dossier, error, loading, reload } = useApi(() => getDossier(ticker), [ticker]);
  const { data: researchWorkspace, error: workspaceError, loading: workspaceLoading } = useApi(async () => {
    try {
      return await getResearchWorkspace(ticker);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }, [ticker]);

  useEffect(() => {
    let cancelled = false;
    setResearchCase(null);
    setCaseHistory([]);
    getResearchCase(ticker)
      .then((caseRow) => {
        if (!cancelled) {
          setResearchCase(caseRow);
          setCaseStateDraft(caseRow.state);
          setCaseStepDraft(caseRow.current_step);
          setCaseReasonDraft(caseRow.blocked_reason ?? "");
          getResearchCaseHistory(ticker)
            .then((history) => { if (!cancelled) setCaseHistory(history); })
            .catch(() => { if (!cancelled) setCaseHistory([]); });
        }
      })
      .catch((err: unknown) => {
        // A missing case is an honest empty state, not a page failure.
        if (!cancelled && (!(err instanceof ApiError) || err.status !== 404)) setResearchCase(null);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  const createCase = async () => {
    setCreatingCase(true);
    setCaseUpdateError(null);
    try {
      const created = await createResearchCase(ticker);
      setResearchCase(created);
      setCaseStateDraft(created.state);
      setCaseStepDraft(created.current_step);
      setCaseReasonDraft(created.blocked_reason ?? "");
      setCaseHistory(await getResearchCaseHistory(ticker));
    } catch (err) {
      setCaseUpdateError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingCase(false);
    }
  };

  const saveCase = async () => {
    setSavingCase(true);
    setCaseUpdateError(null);
    try {
      const updated = await updateResearchCase(ticker, {
        state: caseStateDraft,
        current_step: caseStepDraft,
        blocked_reason: caseStateDraft === "blocked" ? caseReasonDraft : null,
        change_reason: caseChangeReason.trim() || null,
      });
      setResearchCase(updated);
      setCaseReasonDraft(updated.blocked_reason ?? "");
      setCaseChangeReason("");
      setCaseHistory(await getResearchCaseHistory(ticker));
    } catch (err) {
      setCaseUpdateError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingCase(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadReviewState = async () => {
      const [analyses, jobs] = await Promise.all([
        listAnalysisRuns(ticker),
        listAgentRuns({ ticker, limit: 8 }),
      ]);
      if (!cancelled) {
        setAnalysisRuns(analyses);
        setAgentRuns(jobs);
      }
    };
    const refreshReviewState = () => {
      loadReviewState().catch(() => {
        // The report remains useful from the deterministic dossier. Queue/API
        // diagnostics stay available in the Codex tab when this side read fails.
      });
    };
    refreshReviewState();
    const pollId = window.setInterval(refreshReviewState, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(pollId);
    };
  }, [ticker]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshSummary(null);
    try {
      const result = await refreshCompany(ticker, true);
      setRefreshSummary(result.summary);
      reload();
    } catch (err) {
      setRefreshSummary({ refresh: `error: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setRefreshing(false);
    }
  };

  if (workspaceLoading || (loading && !researchWorkspace?.latest_snapshot)) return <div><SkeletonCards cards={4} /><LoadingMessages messages={[`Wczytuję zapisane dane ${ticker}…`, "Otwieram ostatni zapisany stan researchu…"]} /></div>;

  if (workspaceError) return <div className="error-box">Nie można otworzyć workspace Research: {workspaceError}</div>;
  if (researchWorkspace?.latest_snapshot && !researchWorkspace.profile) return <div className="error-box">Snapshot Research nie ma powiązanego profilu spółki. Wymagany jest przegląd integralności danych.</div>;

  if (
    researchWorkspace?.latest_snapshot &&
    researchWorkspace.profile &&
    ["rejected", "needs-human"].includes(researchWorkspace.latest_snapshot.status)
  ) {
    const blockedSnapshot = researchWorkspace.latest_snapshot;
    return (
      <main className="page-stack stock-workspace snapshot-workspace">
        <section className="snapshot-blocked" role="alert">
          <p className="eyebrow">Research snapshot · wersja {blockedSnapshot.version}</p>
          <h1>{ticker}: wynik nie jest źródłem decyzji</h1>
          <p>{blockedSnapshot.verifier_result.summary}</p>
          {blockedSnapshot.gaps.length > 0 && (
            <ul className="snapshot-list">
              {blockedSnapshot.gaps.map((gap) => <li key={gap.topic}><strong>{gap.topic}:</strong> {gap.description}</li>)}
            </ul>
          )}
        </section>
        <details className="snapshot-rejected-audit">
          <summary>Pokaż odrzucony artefakt wyłącznie do audytu</summary>
          <ResearchSnapshotView
            ticker={ticker}
            companyName={researchWorkspace.research_case.name}
            profile={researchWorkspace.profile}
            snapshot={blockedSnapshot}
            history={researchWorkspace.history}
            archetypePack={researchWorkspace.archetype_pack}
          />
        </details>
      </main>
    );
  }

  if (researchWorkspace?.latest_snapshot && researchWorkspace.profile && !showLegacyDossier) {
    return (
      <main className="page-stack stock-workspace snapshot-workspace">
        <ResearchSnapshotView
          ticker={ticker}
          companyName={researchWorkspace.research_case.name}
          profile={researchWorkspace.profile}
          snapshot={researchWorkspace.latest_snapshot}
          history={researchWorkspace.history}
          archetypePack={researchWorkspace.archetype_pack}
        />
        <section className="research-to-valuation">
          <div><span className="snapshot-label">Następny etap</span><strong>Przetestuj jawne scenariusze wyniku i ceny</strong></div>
          <Link className="btn accent" href={`/valuation/${ticker}`}>Przejdź do Valuation</Link>
        </section>
        {dossier && hasDossierData(dossier) && (
          <details className="snapshot-legacy-entry">
            <summary>Starszy raport i narzędzia audytowe</summary>
            <p>Ten widok korzysta z wcześniejszego dossier. Snapshot powyżej jest kanonicznym wynikiem Research.</p>
            <button className="btn compact" onClick={() => setShowLegacyDossier(true)}>Otwórz starszy widok</button>
          </details>
        )}
      </main>
    );
  }

  if (error) return <div className="error-box">{error}</div>;
  if (!dossier) return null;

  const entries = refreshSummary ? Object.entries(refreshSummary) : [];
  const hasErrors = entries.some(([, status]) => !status.startsWith("ok") && status !== "cached" && !status.startsWith("pominięto"));
  const { company, ttm } = dossier;
  const priceAge = staleDays(ttm.price_date);
  const hasData = hasDossierData(dossier);
  const currentAnalysis = findCurrentVerifiedRun(analysisRuns, dossier);
  const reviewAnalysis = analysisRuns?.find(
    (run) => run.workflow === "stock-deep-analysis" && run.verification_status === "needs-human",
  ) ?? null;
  const latestDeepJob = agentRuns?.find((run) => run.workflow === "stock-deep-analysis") ?? null;

  if (!hasData) {
    const preparing = refreshing;
    return (
      <main className="page-stack stock-workspace initial-refresh-workspace">
        <section className="stock-header workspace-header initial-refresh-header">
          <div className="stock-title">
            <div className="row wrap"><h1>{ticker}</h1></div>
            <div className="meta-row">
              <span className={`badge ${preparing ? "accent" : "warning"}`}>
                {preparing ? "Zbieranie danych" : "Brak dossier"}
              </span>
            </div>
          </div>
        </section>
        <section className="initial-refresh-panel" aria-live="polite">
          <IconRefresh size={24} className={preparing ? "spin" : ""} />
          <div>
            <p className="eyebrow">Zapisany stan researchu</p>
            <h2>{preparing ? "Pobieram dane na Twoje polecenie" : "Brak zapisanego dossier"}</h2>
            <p>
              {preparing
                ? "Pobieram źródła, zapisuję pochodzenie faktów i buduję dossier. To jawna operacja, która może potrwać kilkadziesiąt sekund."
                : "Otwarcie tej strony tylko odczytuje zapisane dane. Uruchom pobranie, gdy chcesz świadomie odświeżyć źródła i zbudować dossier."}
            </p>
          </div>
          <ol className="initial-refresh-steps">
            <li className={preparing ? "active" : ""}>Źródła BiznesRadar i PortalAnaliz</li>
            <li>Normalizacja faktów i jakości wyniku</li>
            <li>Scenariusze i gotowy raport</li>
          </ol>
          {!preparing && (
            <button className="btn accent" onClick={() => void handleRefresh()}>
              <IconRefresh size={14} /> {refreshSummary ? "Spróbuj ponownie" : "Pobierz dane"}
            </button>
          )}
          {refreshSummary && !preparing && (
            <div className="source-list">
              {entries.map(([source, status]) => (
                <div className="source-row" key={source}>
                  <span className={status.startsWith("ok") || status === "cached" ? "pos" : "neg"}>●</span>
                  <span className="secondary source-name">{source}</span>
                  <span>{friendlySourceStatus(status)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="page-stack stock-workspace">
      {researchWorkspace?.latest_snapshot && researchWorkspace.profile && (
        <section className="legacy-dossier-notice">
          <div><strong>Widok starszego dossier</strong><span>Kanoniczny snapshot Research pozostaje bez zmian.</span></div>
          <button className="btn compact" onClick={() => setShowLegacyDossier(false)}>Wróć do snapshotu</button>
        </section>
      )}
      <section className="stock-header workspace-header">
        <div className="stock-title">
          <div className="row wrap"><h1>{ticker}</h1>{company.name && <span className="company-title">{company.name}</span>}</div>
          <div className="meta-row"><span className="badge accent">Researching</span>{company.market && <span>{company.market}</span>}{company.sector && <span>{company.sector}</span>}<span>as of {relativeDate(dossier.freshness.financials_scraped_at)}</span>{researchCase && <span className={`badge ${researchCase.state === "blocked" ? "warning" : "muted"}`}>Przypadek: {CASE_STATE_LABELS[researchCase.state]}</span>}</div>
        </div>
        <div className="quote-panel"><span className="quote-price">{fmtPln(ttm.price)}</span><span className="small muted">{ttm.price_date ? fmtDate(ttm.price_date) : "brak kursu"}</span><span className="quote-divider" /><span className="small secondary">mcap {fmtMcap(ttm.market_cap)}</span>{priceAge != null && priceAge > 5 && <span className="badge warning">kurs sprzed {priceAge} dni</span>}</div>
        <div className="command-row header-actions"><button className="btn" onClick={() => void handleRefresh()} disabled={refreshing}><IconRefresh size={14} className={refreshing ? "spin" : ""} /> {refreshing ? "Odświeżanie…" : "Odśwież"}</button>{!researchCase && <button className="btn" onClick={() => void createCase()} disabled={creatingCase}>{creatingCase ? "Tworzę przypadek…" : "Utwórz przypadek"}</button>}<button className="btn accent" onClick={() => setTab("History")}><IconSparkles size={14} /> Analiza Codex</button></div>
      </section>

      {researchCase && (
        <section className="case-editor" aria-label="Edytor przypadku badawczego">
          <div>
            <span className="case-label">Przypadek badawczy</span>
            <p>Stan i etap są ręcznym kontekstem workflow; system nie przesuwa ich automatycznie.</p>
            {researchCase.quarterly_review_due_on && <p className="small muted">Review kwartalny zaplanowany na {fmtDate(researchCase.quarterly_review_due_on)}. Codex wykona go tylko po ręcznym uruchomieniu kolejki; zdarzenie materialne wymaga osobnego, świadomego review.</p>}
          </div>
          <label>Stan<select value={caseStateDraft} onChange={(event) => setCaseStateDraft(event.target.value as ResearchCase["state"])}><option value="new">Nowy</option><option value="ingesting">Zbieranie danych</option><option value="data_review">Przegląd danych</option><option value="business_model">Model biznesowy</option><option value="thesis">Teza</option><option value="scenarios">Scenariusze</option><option value="review">Weryfikacja</option><option value="monitoring">Monitoring</option><option value="blocked">Zablokowany</option><option value="closed">Zamknięty</option></select></label>
          <label>Etap<select value={caseStepDraft} onChange={(event) => setCaseStepDraft(event.target.value as ResearchCase["current_step"])}><option value="ingest">Ingest</option><option value="data_review">Przegląd danych</option><option value="business_model">Model biznesowy</option><option value="thesis">Teza</option><option value="scenarios">Scenariusze</option><option value="review">Weryfikacja</option><option value="monitoring">Monitoring</option></select></label>
          {caseStateDraft === "blocked" && <label>Powód blokady<input value={caseReasonDraft} onChange={(event) => setCaseReasonDraft(event.target.value)} placeholder="Brakujący dowód lub decyzja" /></label>}
          <label>Powód zmiany<input value={caseChangeReason} onChange={(event) => setCaseChangeReason(event.target.value)} placeholder="Dlaczego zmieniasz etap lub stan?" /></label>
          <button className="btn accent" onClick={() => void saveCase()} disabled={savingCase}>{savingCase ? "Zapisuję…" : "Zapisz stan"}</button>
          {caseUpdateError && <span className="case-update-error">{caseUpdateError}</span>}
          {caseHistory.length > 0 && <details className="case-history"><summary>Historia etapów ({caseHistory.length})</summary><ol>{caseHistory.slice(0, 8).map((entry) => <li key={entry.id}><strong>{entry.from_state ? `${CASE_STATE_LABELS[entry.from_state]} / ${CASE_STEP_LABELS[entry.from_step ?? "ingest"]}` : "start"} → {CASE_STATE_LABELS[entry.to_state]} / {CASE_STEP_LABELS[entry.to_step]}</strong><span>{entry.reason}</span><small>{fmtDate(entry.created_at)}{entry.changed_by ? ` · ${entry.changed_by}` : ""}</small></li>)}</ol></details>}
        </section>
      )}

      {refreshing && (
        <section className="refresh-activity" aria-live="polite">
          <IconRefresh size={15} className="spin" />
          <div><strong>Odświeżam raport w tle</strong><span>Źródła → fakty → dossier → scenariusze</span></div>
        </section>
      )}

      {refreshSummary && !refreshing && (
        <details className="source-status source-status-collapsed" open={hasErrors}>
          <summary>Status źródeł <span className={`badge ${hasErrors ? "warning" : "success"}`}>{hasErrors ? "wymaga uwagi" : "OK"}</span></summary>
          <button className="btn icon source-close" aria-label="Ukryj status" onClick={() => setRefreshSummary(null)}><IconX size={13} /></button>
          <div className="source-list">{entries.map(([source, status]) => { const ok = status.startsWith("ok") || status === "cached"; return <div className="source-row" key={source}><span className={ok ? "pos" : "neg"}>●</span><span className="secondary source-name">{source}</span><span className={ok ? "secondary" : "neg"}>{friendlySourceStatus(status)}</span></div>; })}</div>
        </details>
      )}

      <div className="tabs app-tabs workflow-tabs" role="tablist" aria-label="Etapy analizy">
        {TABS.map(({ id, label, icon: Icon }, index) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)} role="tab" aria-selected={tab === id}><span className="tab-step">{index + 1}</span><Icon size={13} /> {label}</button>)}
      </div>

      {tab === "Report" && <><CompanyReport dossier={dossier} analysis={currentAnalysis} reviewAnalysis={reviewAnalysis} analysisJob={latestDeepJob} researchCase={researchCase} onRequestAnalysis={() => setTab("History")} /><PositionPanel ticker={ticker} /><FalsifiersPanel ticker={ticker} /><DecisionJournalPanel ticker={ticker} thesis={dossier.thesis} /><section className="overview-section report-chart"><div className="section-heading"><div><p className="section-label">Trend operacyjny</p><h2>Najważniejsze wykresy wyników</h2></div><p>W raporcie pozostaje tylko trend potrzebny do oceny tezy.</p></div><QuarterlyCharts quarters={dossier.quarters} preferContinuingNet /></section></>}

      {tab === "Charts" && <><section className="scenario-warning"><IconAlertTriangle size={17} /><div><strong>Ograniczenie scenariuszy</strong><p>Warunek wyniku spółki jest pokazany jakościowo, ale cena nadal wynika głównie ze zmiany mnożnika. Traktuj to jako wrażliwość wyceny do czasu scenariuszy operacyjnych v2.</p></div></section><AssumptionSetsPanel ticker={ticker} researchCase={researchCase} /><section className="overview-section"><div className="section-heading"><div><p className="section-label">Wycena</p><h2>Scenariusze i kurs</h2></div><p>Widoki wspierające raport, bez surowych tabel.</p></div>{dossier.scenarios && <ScenariosPanel scenarios={dossier.scenarios} valuation={dossier.valuation} />}<div className="overview-grid scenario-context"><ForecastPanel ticker={ticker} dossier={dossier} onSaved={reload} /><PriceChart ticker={ticker} /></div></section></>}

      {tab === "Audit" && <section className="overview-section"><div className="section-heading"><div><p className="section-label">Warstwa audytowa</p><h2>Źródła i obliczenia na żądanie</h2></div><p>Te materiały zasilają raport, lecz nie są domyślnym ekranem.</p></div><details className="review-history" open><summary>Rejestr źródeł i ograniczenia</summary><EvidenceSourcesPanel ticker={ticker} /></details><details className="review-history"><summary>Kluczowe wskaźniki i checklista</summary><div className="overview-grid audit-detail"><InsightsPanel insights={dossier.insights} /><PrescoreChecklist prescore={dossier.prescore} /></div></details><details className="review-history"><summary>Sprawozdania finansowe</summary><FinancialsTable ticker={ticker} /></details><details className="review-history"><summary>Tropy z forum — niezweryfikowane</summary><ForumPanel ticker={ticker} /></details></section>}

      {tab === "History" && <section className="overview-section"><div className="section-heading"><div><p className="section-label">Codex</p><h2>Pełna analiza i historia weryfikacji</h2></div><p>Tylko wynik z aktualnych danych i po verifierze może zastąpić szkic raportu.</p></div><AnalysisPanel ticker={ticker} dossier={dossier} /><details className="review-history"><summary>Deterministyczne memo audytowe</summary><InvestorMemo dossier={dossier} /></details></section>}
    </main>
  );
}
