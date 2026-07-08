"use client";

/** Stock page (`/stock/[ticker]`) — tabs per docs/design/mockups.html screen 2. */
import { use, useEffect, useState } from "react";
import {
  IconBrain,
  IconCalendarStats,
  IconChartBar,
  IconDatabase,
  IconFileAnalytics,
  IconRefresh,
  IconScale,
  IconShieldCheck,
  IconSparkles,
  IconX,
} from "@tabler/icons-react";
import { getDossier, refreshCompany } from "@/lib/api";
import { hasDossierData } from "@/lib/dossier";
import { useApi } from "@/lib/hooks";
import { fmtMcap, fmtPln, fmtDate, fmtNumber, relativeDate, staleDays } from "@/lib/format";
import { LoadingMessages, SkeletonCards } from "@/components/Loading";
import InsightsPanel from "@/components/InsightsPanel";
import ThesisPanel from "@/components/ThesisPanel";
import ScenariosPanel from "@/components/ScenariosPanel";
import MetricCards from "@/components/MetricCards";
import PrescoreChecklist from "@/components/PrescoreChecklist";
import PriceChart from "@/components/PriceChart";
import FinancialsTable from "@/components/FinancialsTable";
import QuarterlyCharts from "@/components/QuarterlyCharts";
import ForecastPanel from "@/components/ForecastPanel";
import ForumPanel from "@/components/ForumPanel";
import AnalysisPanel from "@/components/AnalysisPanel";
import type { Dossier } from "@/lib/types";

const TABS = [
  { id: "Brief", label: "Brief", icon: IconFileAnalytics },
  { id: "AI", label: "Interpretacja AI", icon: IconBrain },
  { id: "Fundamentals", label: "Fundamenty", icon: IconChartBar },
  { id: "Valuation", label: "Wycena", icon: IconScale },
  { id: "Data", label: "Dane", icon: IconDatabase },
] as const;
type Tab = (typeof TABS)[number]["id"];

function badgeToneForScore(passed: number, total: number) {
  if (total <= 0) return "muted";
  const ratio = passed / total;
  if (ratio >= 0.75) return "success";
  if (ratio >= 0.5) return "warning";
  return "danger";
}

function DecisionCockpit({
  dossier,
  onAnalyze,
}: {
  dossier: Dossier;
  onAnalyze: () => void;
}) {
  const { insights, latest_forecast: latestForecast, pe_history: peHistory, prescore, ttm } = dossier;
  const topIndicators = [...insights.key_indicators]
    .sort((a, b) => b.importance - a.importance)
    .slice(0, 4);
  const scoreTone = badgeToneForScore(prescore.passed, prescore.total);
  const freshness = dossier.freshness;
  const hasFinancials = dossier.quarters.length > 0;
  const hasPrice = ttm.price != null;

  return (
    <section className="decision-cockpit">
      <div className="decision-main card">
        <div className="section-kicker">
          <IconShieldCheck size={14} /> Aktualny odczyt
        </div>
        <h2>{dossier.thesis?.entry_quality.label ?? insights.summary}</h2>
        {dossier.thesis?.entry_quality.rationale ? (
          <p>{dossier.thesis.entry_quality.rationale}</p>
        ) : (
          <p>{insights.summary}</p>
        )}
        <div className="decision-actions">
          <span className={`badge ${scoreTone}`}>
            strategia {prescore.passed}/{prescore.total}
          </span>
          <span className="badge neutral">
            {insights.size_label ?? "rozmiar b/d"}
          </span>
          <span className="badge neutral">{insights.sector_group_label}</span>
          <button className="btn compact accent" onClick={onAnalyze}>
            <IconSparkles size={13} /> Analiza AI
          </button>
        </div>
      </div>

      <div className="decision-side">
        <div className="card decision-card">
          <div className="section-kicker">
            <IconScale size={14} /> Wycena
          </div>
          <div className="decision-metrics">
            <div>
              <span className="k">C/Z TTM</span>
              <span className="v">{fmtNumber(ttm.pe)}</span>
            </div>
            <div>
              <span className="k">C/Z fwd</span>
              <span className="v">{fmtNumber(latestForecast?.result.forward.pe)}</span>
            </div>
            <div>
              <span className="k">Mediana hist.</span>
              <span className="v">{fmtNumber(peHistory.median)}</span>
            </div>
          </div>
        </div>

        <div className="card decision-card">
          <div className="section-kicker">
            <IconDatabase size={14} /> Dane
          </div>
          <div className="freshness-grid">
            <span>Sprawozdania</span>
            <strong className={hasFinancials ? "secondary" : "warn"}>
              {hasFinancials ? relativeDate(freshness.financials_scraped_at) : "brak danych"}
            </strong>
            <span>Kurs</span>
            <strong className={hasPrice ? "secondary" : "warn"}>
              {hasPrice ? relativeDate(freshness.last_price_date ?? ttm.price_date) : "brak kursu"}
            </strong>
            <span>Forum</span>
            <strong className="secondary">{relativeDate(freshness.forum_last_synced_at)}</strong>
          </div>
        </div>
      </div>

      {topIndicators.length > 0 && (
        <div className="card decision-indicators">
          <div className="section-kicker">
            <IconCalendarStats size={14} /> Najważniejsze sygnały
          </div>
          <div className="signal-grid">
            {topIndicators.map((indicator) => (
              <div className="signal" key={indicator.id}>
                <span className="name">{indicator.name}</span>
                <strong>{indicator.value}</strong>
                {indicator.comment && <p>{indicator.comment}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker: rawTicker } = use(params);
  const ticker = rawTicker.toUpperCase();

  const [tab, setTab] = useState<Tab>("Brief");
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefreshStarted, setAutoRefreshStarted] = useState(false);
  const [refreshSummary, setRefreshSummary] = useState<Record<string, string> | null>(
    null,
  );
  const { data: dossier, error, loading, reload } = useApi(
    () => getDossier(ticker),
    [ticker],
  );

  useEffect(() => {
    if (loading || !dossier || hasDossierData(dossier) || refreshing || autoRefreshStarted) {
      return;
    }
    setAutoRefreshStarted(true);
    setRefreshing(true);
    refreshCompany(ticker, true)
      .then((result) => {
        setRefreshSummary(result.summary);
        reload();
      })
      .catch((err) => {
        setRefreshSummary({
          refresh: `error: ${err instanceof Error ? err.message : String(err)}`,
        });
      })
      .finally(() => setRefreshing(false));
  }, [autoRefreshStarted, dossier, loading, refreshing, reload, ticker]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      // Manual refresh on the stock page = intentional → bypass the 24 h
      // cache. Watchlist bulk refresh keeps using the cache.
      const result = await refreshCompany(ticker, true);
      setRefreshSummary(result.summary);
      reload();
    } catch (err) {
      setRefreshSummary({
        refresh: `error: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setRefreshing(false);
    }
  };

  if (loading)
    return (
      <div>
        <SkeletonCards cards={6} />
        <LoadingMessages
          messages={[
            `Otwieram dossier ${ticker}…`,
            "Liczę marże i C/Z…",
            "Sprawdzam checklistę strategii…",
          ]}
        />
      </div>
    );
  if (error) return <div className="error-box">{error}</div>;
  if (!dossier) return null;

  const summaryEntries = refreshSummary ? Object.entries(refreshSummary) : [];
  const summaryHasErrors = summaryEntries.some(
    ([, s]) => !s.startsWith("ok") && s !== "cached" && !s.startsWith("pominięto"),
  );

  const { company, ttm } = dossier;
  // A weekend + a couple of trading days is normal; flag only clearly-stale
  // quotes so the scenario valuation is read with the right caveat.
  const priceAge = staleDays(ttm.price_date);
  const priceStale = priceAge != null && priceAge > 5;

  return (
    <main className="page-stack">
      <section className="stock-header">
        <div className="stock-title">
          <div className="row wrap">
            <h1>{ticker}</h1>
            {company.name && <span className="company-title">{company.name}</span>}
          </div>
          <div className="meta-row">
            {company.market && <span className="badge neutral">{company.market}</span>}
            {company.sector && <span>{company.sector}</span>}
          </div>
        </div>
        <div className="quote-panel">
          <span className="quote-price">{fmtPln(ttm.price)}</span>
          <span className="small muted">
            {ttm.price_date ? `kurs z ${fmtDate(ttm.price_date)}` : "brak kursu"}
          </span>
          <span className="quote-divider" />
          <span className="small secondary">mcap {fmtMcap(ttm.market_cap)}</span>
          {priceStale && (
            <span className="badge warning">kurs sprzed {priceAge} dni</span>
          )}
        </div>
        <div className="command-row header-actions">
          <button
            className="btn"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Pełne odświeżenie — pomija cache 24 h"
          >
            <IconRefresh size={14} className={refreshing ? "spin" : ""} /> Odśwież
          </button>
          <button
            className="btn accent"
            onClick={() => setTab("AI")}
            title="Przejdź do interpretacji AI"
          >
            <IconSparkles size={14} /> Analizuj
          </button>
        </div>
      </section>

      {refreshing && (
        <LoadingMessages
          messages={[
            "Pobieram raporty z BiznesRadar…",
            "Grzeczne opóźnienia między zapytaniami (2–4 s)…",
            "Czytam bilans i przepływy…",
            "Aktualizuję kurs z BiznesRadar…",
            "Synchronizuję najnowsze powiązane wątki PortalAnaliz…",
            "Zapisuję dane do bazy…",
          ]}
          intervalMs={3200}
        />
      )}

      {refreshSummary && !refreshing && (
        <section className="card source-status">
          <div className="spread">
            <span className="source-status-title">
              Status źródeł po odświeżeniu{" "}
              {summaryHasErrors ? (
                <span className="badge warning">problemy</span>
              ) : (
                <span className="badge success">OK</span>
              )}
            </span>
            <button
              className="btn icon"
              aria-label="Ukryj status źródeł"
              onClick={() => setRefreshSummary(null)}
            >
              <IconX size={13} />
            </button>
          </div>
          <div className="source-list">
            {summaryEntries.map(([source, status]) => {
              const ok = status.startsWith("ok") || status === "cached";
              const warn = ok && status.includes("uwaga");
              return (
                <div key={source} className="source-row">
                  <span className={warn ? "warn" : ok ? "pos" : "neg"}>●</span>
                  <span className="secondary source-name">{source}</span>
                  <span className={ok && !warn ? "secondary" : warn ? "warn" : "neg"}>
                    {status}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <div className="tabs app-tabs" role="tablist" aria-label="Sekcje dossier">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
            role="tab"
            aria-selected={tab === id}
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {tab === "Brief" && (
        <>
          {!hasDossierData(dossier) ? (
            <section className="card empty-panel">
              <IconRefresh size={18} className={refreshing ? "spin" : ""} />
              <strong>{refreshing ? "Pobieram pierwsze dane" : "Brak zbudowanego dossier"}</strong>
              <span>
                {refreshing
                  ? "Ticker został dodany, trwa pobieranie danych źródłowych."
                  : "Uruchom odświeżenie, żeby zbudować analizę z BiznesRadar i powiązanych wątków forum."}
              </span>
              {!refreshing && (
                <button className="btn accent" onClick={handleRefresh}>
                  <IconRefresh size={14} /> Pobierz dane
                </button>
              )}
            </section>
          ) : (
            <>
              <DecisionCockpit dossier={dossier} onAnalyze={() => setTab("AI")} />

              <section className="overview-section">
                <div className="section-heading">
                  <p className="section-label">Teza i decyzja robocza</p>
                  <p>Najpierw wniosek, potem dowody. Szczegóły są w kolejnych zakładkach.</p>
                </div>
                <div className="overview-grid primary">
                  {dossier.thesis ? (
                    <ThesisPanel thesis={dossier.thesis} />
                  ) : (
                    <div className="card muted-panel">
                      Brak tezy inwestycyjnej — odśwież dane, aby zbudować syntezę.
                    </div>
                  )}
                  <MetricCards dossier={dossier} />
                </div>
              </section>

              {dossier.scenarios && (
                <section className="overview-section">
                  <div className="section-heading">
                    <p className="section-label">Scenariusz bazowy</p>
                    <p>Pełna symulacja i prognozy są w zakładce Wycena.</p>
                  </div>
                  <ScenariosPanel scenarios={dossier.scenarios} valuation={dossier.valuation} />
                </section>
              )}
            </>
          )}
        </>
      )}
      {tab === "AI" && <AnalysisPanel ticker={ticker} dossier={dossier} />}
      {tab === "Fundamentals" && (
        <>
          <section className="overview-section">
            <div className="section-heading">
              <p className="section-label">Jakość operacyjna</p>
              <p>Najważniejsze wskaźniki, ryzyka i luki danych z dossier.</p>
            </div>
            <div className="overview-grid">
              <InsightsPanel insights={dossier.insights} />
              <PrescoreChecklist prescore={dossier.prescore} />
            </div>
          </section>
          <QuarterlyCharts quarters={dossier.quarters} />
        </>
      )}
      {tab === "Valuation" && (
        <>
          <section className="overview-section">
            <div className="section-heading">
              <p className="section-label">Wycena i scenariusze</p>
              <p>Prognozy, potencjał i historia C/Z w jednym miejscu.</p>
            </div>
            <div className="overview-grid">
              <MetricCards dossier={dossier} />
              <PriceChart ticker={ticker} />
            </div>
            {dossier.scenarios && (
              <div className="section-block">
                <ScenariosPanel scenarios={dossier.scenarios} valuation={dossier.valuation} />
              </div>
            )}
          </section>
          <ForecastPanel ticker={ticker} dossier={dossier} onSaved={reload} />
        </>
      )}
      {tab === "Data" && (
        <>
          <section className="overview-section">
            <div className="section-heading">
              <p className="section-label">Sprawozdania</p>
              <p>Surowe tabele zostają dostępne, ale nie dominują decyzji.</p>
            </div>
            <FinancialsTable ticker={ticker} />
          </section>
          <section className="overview-section">
            <div className="section-heading">
              <p className="section-label">Forum PortalAnaliz</p>
              <p>Powiąż wątki ręcznie; odświeżanie pobiera tylko najnowszy zakres.</p>
            </div>
            <ForumPanel ticker={ticker} />
          </section>
        </>
      )}
    </main>
  );
}
