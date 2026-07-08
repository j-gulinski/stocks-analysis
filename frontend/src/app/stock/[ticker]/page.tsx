"use client";

/** Stock page (`/stock/[ticker]`) — tabs per docs/design/mockups.html screen 2. */
import { use, useState } from "react";
import {
  IconBrain,
  IconChartBar,
  IconFileAnalytics,
  IconMessageCircle,
  IconRefresh,
  IconSparkles,
  IconTable,
  IconTrendingUp,
  IconX,
} from "@tabler/icons-react";
import { getDossier, refreshCompany } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { fmtMcap, fmtPln, fmtDate, staleDays } from "@/lib/format";
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

const TABS = [
  { id: "Overview", label: "Przegląd", icon: IconFileAnalytics },
  { id: "Financials", label: "Finanse", icon: IconTable },
  { id: "Charts", label: "Wykresy", icon: IconChartBar },
  { id: "Forecast", label: "Prognoza", icon: IconTrendingUp },
  { id: "Forum", label: "Forum", icon: IconMessageCircle },
  { id: "AI analysis", label: "Analiza AI", icon: IconBrain },
] as const;
type Tab = (typeof TABS)[number]["id"];

export default function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker: rawTicker } = use(params);
  const ticker = rawTicker.toUpperCase();

  const [tab, setTab] = useState<Tab>("Overview");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshSummary, setRefreshSummary] = useState<Record<string, string> | null>(
    null,
  );
  const { data: dossier, error, loading, reload } = useApi(
    () => getDossier(ticker),
    [ticker],
  );

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
  const summaryHasErrors = summaryEntries.some(([, s]) => !s.startsWith("ok") && s !== "cached");

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
            onClick={() => setTab("AI analysis")}
            title="Przejdź do zakładki Analiza AI"
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
            "Aktualizuję kursy ze stooq…",
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

      {tab === "Overview" && (
        <>
          <MetricCards dossier={dossier} />
          {dossier.thesis && (
            <>
              <p className="section-label">Teza inwestycyjna</p>
              <ThesisPanel thesis={dossier.thesis} />
            </>
          )}
          {dossier.scenarios && (
            <>
              <p className="section-label">Scenariusze</p>
              <ScenariosPanel scenarios={dossier.scenarios} valuation={dossier.valuation} />
            </>
          )}
          <p className="section-label">Analiza spółki</p>
          <InsightsPanel insights={dossier.insights} />
          <p className="section-label">Prescore strategii</p>
          <PrescoreChecklist prescore={dossier.prescore} />
          <p className="section-label">Kurs (12 mies.)</p>
          <PriceChart ticker={ticker} />
        </>
      )}
      {tab === "Financials" && <FinancialsTable ticker={ticker} />}
      {tab === "Charts" && <QuarterlyCharts quarters={dossier.quarters} />}
      {tab === "Forecast" && (
        <ForecastPanel ticker={ticker} dossier={dossier} onSaved={reload} />
      )}
      {tab === "Forum" && <ForumPanel ticker={ticker} />}
      {tab === "AI analysis" && <AnalysisPanel ticker={ticker} dossier={dossier} />}
    </main>
  );
}
