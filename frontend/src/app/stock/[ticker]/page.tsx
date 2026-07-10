"use client";

/** Progressive company research workspace: one canonical brief, then evidence. */
import { use, useEffect, useState } from "react";
import {
  IconAlertTriangle,
  IconBrain,
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
import { fmtDate, fmtMcap, fmtNumber, fmtPct, fmtPln, relativeDate, staleDays } from "@/lib/format";
import { LoadingMessages, SkeletonCards } from "@/components/Loading";
import InsightsPanel from "@/components/InsightsPanel";
import PrescoreChecklist from "@/components/PrescoreChecklist";
import PriceChart from "@/components/PriceChart";
import FinancialsTable from "@/components/FinancialsTable";
import QuarterlyCharts from "@/components/QuarterlyCharts";
import ForecastPanel from "@/components/ForecastPanel";
import ForumPanel from "@/components/ForumPanel";
import AnalysisPanel from "@/components/AnalysisPanel";
import ScenariosPanel from "@/components/ScenariosPanel";
import type { Dossier } from "@/lib/types";

const TABS = [
  { id: "Brief", label: "Brief", icon: IconFileAnalytics },
  { id: "Evidence", label: "Evidence", icon: IconDatabase },
  { id: "Financials", label: "Financials", icon: IconChartBar },
  { id: "Scenarios", label: "Scenarios", icon: IconScale },
  { id: "Review", label: "Review", icon: IconBrain },
] as const;
type Tab = (typeof TABS)[number]["id"];

function Brief({ dossier, onContinue }: { dossier: Dossier; onContinue: () => void }) {
  const latest = dossier.quarters.at(-1);
  const strengths = dossier.thesis?.pros.slice(0, 2).map((item) => item.text) ?? dossier.insights.strengths.slice(0, 2);
  const risks = dossier.thesis?.cons.slice(0, 2).map((item) => item.text) ?? dossier.insights.concerns.slice(0, 2);
  const checks = dossier.thesis?.verify_next.slice(0, 2) ?? dossier.insights.missing.slice(0, 2).map((item) => ({ id: item.id, text: item.name, why: item.why }));
  const signals = dossier.insights.key_indicators.slice(0, 4);
  const coverage = dossier.insights.coverage;
  const evidenceComplete = dossier.insights.missing.length === 0;

  return (
    <div className="brief-workspace">
      <section className="decision-brief">
        <div className="decision-summary">
          <p className="eyebrow">Stan analizy</p>
          <h2>{dossier.thesis?.entry_quality.label ?? "Teza robocza"}</h2>
          <p>{dossier.thesis?.entry_quality.rationale ?? dossier.insights.summary}</p>
          <div className="decision-meta">
            <span className="badge neutral">Malik / OBS: {dossier.prescore.passed}/{dossier.prescore.total} warunków</span>
            <span className={`badge ${evidenceComplete ? "success" : "warning"}`}>
              {evidenceComplete ? <IconShieldCheck size={13} /> : <IconAlertTriangle size={13} />}
              {evidenceComplete ? "dowody kompletne" : `${dossier.insights.missing.length} luk danych`}
            </span>
            {coverage && <span className="badge neutral">pokrycie {coverage.available}/{coverage.selected}</span>}
          </div>
        </div>
        <aside className="next-action-panel">
          <span className="candidate-label">Najważniejszy następny krok</span>
          <strong>{checks[0]?.text ?? "Przejrzyj tezę po kolejnym raporcie"}</strong>
          <p>{checks[0]?.why ?? "Utrzymaj jawne założenia i warunki obalenia."}</p>
          <button className="btn accent" onClick={onContinue}>Przejdź do dowodów</button>
        </aside>
      </section>

      <section className="key-number-strip" aria-label="Kluczowe liczby">
        <div><span>Przychody r/r</span><strong>{fmtPct(latest?.revenue_yoy_pct, { signed: true })}</strong><small>{latest?.period ?? "brak okresu"}</small></div>
        <div><span>Marża brutto</span><strong>{fmtPct(latest?.gross_margin_pct)}</strong><small>{latest?.period ?? "brak okresu"}</small></div>
        <div><span>C/Z TTM</span><strong>{fmtNumber(dossier.ttm.pe)}</strong><small>własna mediana {fmtNumber(dossier.pe_history.median)}</small></div>
        <div><span>Wynik TTM</span><strong>{fmtNumber(dossier.ttm.net_profit)} tys.</strong><small>deterministyczne wyliczenie</small></div>
      </section>

      {signals.length > 0 && (
        <section className="brief-signals">
          <div className="section-heading"><div><p className="section-label">Sygnały</p><h2>Co naprawdę się wyróżnia</h2></div><p>Maksymalnie cztery wskaźniki dobrane do profilu spółki.</p></div>
          <div className="signal-grid compact-signals">
            {signals.map((signal) => <div className="signal" key={signal.id}><span className="name">{signal.name}</span><strong>{signal.value}</strong><p>{signal.comment}</p></div>)}
          </div>
        </section>
      )}

      <section className="thesis-balance">
        <div>
          <h3>Co przemawia za</h3>
          {strengths.length > 0 ? <ul>{strengths.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p className="muted">Brak wystarczająco mocnego argumentu.</p>}
        </div>
        <div>
          <h3>Co przemawia przeciw</h3>
          {risks.length > 0 ? <ul>{risks.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p className="muted">Brak nazwanej kontrtezy — wymaga uzupełnienia.</p>}
        </div>
        <div className="next-checks">
          <h3>Sprawdź następnie</h3>
          {checks.length > 0 ? <ol>{checks.map((item) => <li key={item.id}><strong>{item.text}</strong><span>{item.why}</span></li>)}</ol> : <p className="muted">Brak otwartych punktów.</p>}
        </div>
      </section>

      <p className="product-disclosure">Materiał wspiera proces badawczy. Nie jest rekomendacją kupna ani sprzedaży.</p>
    </div>
  );
}

export default function StockPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker: rawTicker } = use(params);
  const ticker = rawTicker.toUpperCase();
  const [tab, setTab] = useState<Tab>("Brief");
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefreshStarted, setAutoRefreshStarted] = useState(false);
  const [refreshSummary, setRefreshSummary] = useState<Record<string, string> | null>(null);
  const { data: dossier, error, loading, reload } = useApi(() => getDossier(ticker), [ticker]);

  useEffect(() => {
    if (loading || !dossier || hasDossierData(dossier) || refreshing || autoRefreshStarted) return;
    setAutoRefreshStarted(true);
    setRefreshing(true);
    refreshCompany(ticker, true)
      .then((result) => { setRefreshSummary(result.summary); reload(); })
      .catch((err) => setRefreshSummary({ refresh: `error: ${err instanceof Error ? err.message : String(err)}` }))
      .finally(() => setRefreshing(false));
  }, [autoRefreshStarted, dossier, loading, refreshing, reload, ticker]);

  const handleRefresh = async () => {
    setRefreshing(true);
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

  if (loading) return <div><SkeletonCards cards={4} /><LoadingMessages messages={[`Otwieram przypadek ${ticker}…`, "Porządkuję dowody i tezę…"]} /></div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!dossier) return null;

  const entries = refreshSummary ? Object.entries(refreshSummary) : [];
  const hasErrors = entries.some(([, status]) => !status.startsWith("ok") && status !== "cached" && !status.startsWith("pominięto"));
  const { company, ttm } = dossier;
  const priceAge = staleDays(ttm.price_date);

  return (
    <main className="page-stack stock-workspace">
      <section className="stock-header workspace-header">
        <div className="stock-title">
          <div className="row wrap"><h1>{ticker}</h1>{company.name && <span className="company-title">{company.name}</span>}</div>
          <div className="meta-row"><span className="badge accent">Researching</span>{company.market && <span>{company.market}</span>}{company.sector && <span>{company.sector}</span>}<span>as of {relativeDate(dossier.freshness.financials_scraped_at)}</span></div>
        </div>
        <div className="quote-panel"><span className="quote-price">{fmtPln(ttm.price)}</span><span className="small muted">{ttm.price_date ? fmtDate(ttm.price_date) : "brak kursu"}</span><span className="quote-divider" /><span className="small secondary">mcap {fmtMcap(ttm.market_cap)}</span>{priceAge != null && priceAge > 5 && <span className="badge warning">kurs sprzed {priceAge} dni</span>}</div>
        <div className="command-row header-actions"><button className="btn" onClick={() => void handleRefresh()} disabled={refreshing}><IconRefresh size={14} className={refreshing ? "spin" : ""} /> Odśwież</button><button className="btn accent" onClick={() => setTab("Review")}><IconSparkles size={14} /> Poproś o recenzję</button></div>
      </section>

      {refreshing && <LoadingMessages messages={["Pobieram źródła BiznesRadar…", "Zachowuję wersje i pochodzenie faktów…", "Aktualizuję dossier…"]} intervalMs={2600} />}

      {refreshSummary && !refreshing && (
        <details className="source-status source-status-collapsed" open={hasErrors}>
          <summary>Status źródeł <span className={`badge ${hasErrors ? "warning" : "success"}`}>{hasErrors ? "wymaga uwagi" : "OK"}</span></summary>
          <button className="btn icon source-close" aria-label="Ukryj status" onClick={() => setRefreshSummary(null)}><IconX size={13} /></button>
          <div className="source-list">{entries.map(([source, status]) => { const ok = status.startsWith("ok") || status === "cached"; return <div className="source-row" key={source}><span className={ok ? "pos" : "neg"}>●</span><span className="secondary source-name">{source}</span><span className={ok ? "secondary" : "neg"}>{status}</span></div>; })}</div>
        </details>
      )}

      <div className="tabs app-tabs workflow-tabs" role="tablist" aria-label="Etapy analizy">
        {TABS.map(({ id, label, icon: Icon }, index) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)} role="tab" aria-selected={tab === id}><span className="tab-step">{index + 1}</span><Icon size={13} /> {label}</button>)}
      </div>

      {tab === "Brief" && (!hasDossierData(dossier) ? <section className="card empty-panel"><IconRefresh size={18} className={refreshing ? "spin" : ""} /><strong>{refreshing ? "Zbieram pierwsze dane" : "Brak zbudowanego dossier"}</strong><span>Uruchom odświeżenie, aby rozpocząć analizę.</span>{!refreshing && <button className="btn accent" onClick={() => void handleRefresh()}><IconRefresh size={14} /> Pobierz dane</button>}</section> : <Brief dossier={dossier} onContinue={() => setTab("Evidence")} />)}

      {tab === "Evidence" && <><section className="overview-section"><div className="section-heading"><div><p className="section-label">Dowody i luki</p><h2>Co wiemy, a czego jeszcze nie</h2></div><p>Wskaźniki są obliczeniami; forum pozostaje źródłem niezweryfikowanych tropów.</p></div><div className="overview-grid"><InsightsPanel insights={dossier.insights} /><PrescoreChecklist prescore={dossier.prescore} /></div></section><section className="overview-section"><div className="section-heading"><div><p className="section-label">Tropy z forum</p><h2>Niezweryfikowane źródła jakościowe</h2></div><p>Powiązuj i oceniaj jako leads, nie jako fakty.</p></div><ForumPanel ticker={ticker} /></section></>}

      {tab === "Financials" && <><section className="overview-section"><div className="section-heading"><div><p className="section-label">Wyniki</p><h2>Trend operacyjny</h2></div><p>Najnowsze okresy najpierw; surowa tabela pozostaje do audytu.</p></div><QuarterlyCharts quarters={dossier.quarters} /></section><section className="overview-section"><div className="section-heading"><div><p className="section-label">Sprawozdania</p><h2>Dane źródłowe</h2></div><p>Wartości są śledzone do wersji dokumentu BiznesRadar.</p></div><FinancialsTable ticker={ticker} /></section></>}

      {tab === "Scenarios" && <><section className="scenario-warning"><IconAlertTriangle size={17} /><div><strong>Ograniczenie obecnej wersji</strong><p>Bear/base/bull zmienia dziś głównie mnożnik. Traktuj wynik jako wrażliwość wyceny, dopóki scenariusze operacyjne v2 nie połączą driverów z rachunkiem wyników i cash flow.</p></div></section><section className="overview-section"><div className="section-heading"><div><p className="section-label">Scenariusze</p><h2>Założenia i wycena</h2></div><p>Pełny widok pojawia się tylko tutaj.</p></div>{dossier.scenarios && <ScenariosPanel scenarios={dossier.scenarios} valuation={dossier.valuation} />}<div className="overview-grid scenario-context"><ForecastPanel ticker={ticker} dossier={dossier} onSaved={reload} /><PriceChart ticker={ticker} /></div></section></>}

      {tab === "Review" && <section className="overview-section"><div className="section-heading"><div><p className="section-label">Recenzja modelu</p><h2>Krytyka, nie drugi raport</h2></div><p>Obecny panel jest etapem przejściowym; docelowo pokaże tylko różnice, konflikty i brakujące dowody.</p></div><AnalysisPanel ticker={ticker} dossier={dossier} /></section>}
    </main>
  );
}
