"use client";

/** Stock page (`/stock/[ticker]`) — tabs per docs/design/mockups.html screen 2. */
import { use, useState } from "react";
import { IconRefresh, IconSparkles, IconX } from "@tabler/icons-react";
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

const TABS = ["Overview", "Financials", "Charts", "Forecast", "Forum", "AI analysis"] as const;
type Tab = (typeof TABS)[number];

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
  // quotes so the scenario valuation (computed off this price) is read with the
  // right caveat instead of silently trusting an old number.
  const priceAge = staleDays(ttm.price_date);
  const priceStale = priceAge != null && priceAge > 5;

  return (
    <main>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <div>
          <span style={{ fontSize: 19, fontWeight: 500 }}>
            {ticker}
            {company.name ? ` · ${company.name}` : ""}
          </span>
          <span className="small muted" style={{ marginLeft: 10 }}>
            {company.market ?? ""}
            {company.sector ? ` · ${company.sector}` : ""}
          </span>
          <br />
          <span style={{ fontSize: 15 }}>{fmtPln(ttm.price)}</span>
          <span className="small muted" style={{ marginLeft: 8 }}>
            {ttm.price_date ? `kurs z ${fmtDate(ttm.price_date)}` : "brak kursu"}
            {" · mcap "}
            {fmtMcap(ttm.market_cap)}
          </span>
          {priceStale && (
            <span className="badge warning" style={{ marginLeft: 8, fontSize: 11 }}>
              kurs sprzed {priceAge} dni
            </span>
          )}
        </div>
        <div className="row">
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
      </div>

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
        <div
          className="card"
          style={{ margin: "10px 0", fontSize: 12, padding: "10px 14px" }}
        >
          <div className="spread">
            <span style={{ fontWeight: 500 }}>
              Status źródeł po odświeżeniu{" "}
              {summaryHasErrors ? (
                <span className="badge warning">problemy</span>
              ) : (
                <span className="badge success">OK</span>
              )}
            </span>
            <button className="btn icon" onClick={() => setRefreshSummary(null)}>
              <IconX size={13} />
            </button>
          </div>
          <div style={{ marginTop: 8, fontFamily: "ui-monospace, monospace", fontSize: 11.5 }}>
            {summaryEntries.map(([source, status]) => {
              const ok = status.startsWith("ok") || status === "cached";
              const warn = ok && status.includes("uwaga");
              return (
                <div key={source} style={{ padding: "2px 0", display: "flex", gap: 8 }}>
                  <span className={warn ? "warn" : ok ? "pos" : "neg"}>●</span>
                  <span style={{ minWidth: 170 }} className="secondary">
                    {source}
                  </span>
                  <span className={ok && !warn ? "secondary" : warn ? "warn" : "neg"}>
                    {status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="tabs">
        {TABS.map((name) => (
          <button
            key={name}
            className={tab === name ? "active" : ""}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <>
          <MetricCards dossier={dossier} />
          {/* Thesis is the synthesis; insights below are the evidence it is
              built from (plan WP3 order). Guard the label too so an older
              dossier without a thesis block shows nothing, not an orphan. */}
          {dossier.thesis && (
            <>
              <p className="section-label">Teza inwestycyjna</p>
              <ThesisPanel thesis={dossier.thesis} />
            </>
          )}
          {/* Scenarios = the projections off the thesis read (plan WP3 order:
              MetricCards → Teza → Scenariusze → Analiza → Prescore → Kurs).
              Guard the label too so an older dossier without the block shows
              nothing, not an orphan heading. */}
          {dossier.scenarios && (
            <>
              <p className="section-label">Scenariusze</p>
              {/* The AI valuation (WP4) rides inside the scenarios card, below
                  the weighted-EV strip; passed through here (optional). */}
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
