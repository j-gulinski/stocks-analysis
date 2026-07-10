"use client";

/** Research queue: one next action per company, not a portfolio data dump. */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCircleCheck,
  IconDatabaseOff,
  IconPlus,
  IconRefresh,
  IconTrash,
} from "@tabler/icons-react";
import {
  addToWatchlist,
  getDossier,
  getWatchlist,
  refreshCompany,
  removeFromWatchlist,
} from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { hasDossierData } from "@/lib/dossier";
import { fmtMcap, fmtPln, relativeDate, staleDays } from "@/lib/format";
import type { Dossier } from "@/lib/types";

interface Row {
  ticker: string;
  name: string | null;
  dossier: Dossier | null;
  refreshing: boolean;
}

function currentRead(dossier: Dossier | null): string {
  if (!dossier) return "Dane nie zostały jeszcze zebrane.";
  return dossier.thesis?.entry_quality.rationale ?? dossier.insights.summary;
}

function researchState(row: Row): { label: string; tone: string; next: string } {
  if (row.refreshing) return { label: "Zbieranie danych", tone: "accent", next: "Poczekaj na zakończenie odświeżenia" };
  if (!hasDossierData(row.dossier)) return { label: "Nowa", tone: "warning", next: "Zbierz dane źródłowe" };
  if ((row.dossier?.insights.missing.length ?? 0) > 0) return { label: "Do weryfikacji", tone: "warning", next: "Rozwiąż najważniejszą lukę" };
  return { label: "Teza robocza", tone: "neutral", next: "Przejrzyj tezę i scenariusze" };
}

export default function ResearchQueuePage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newTicker, setNewTicker] = useState("");
  const [adding, setAdding] = useState(false);

  const loadDossier = useCallback(async (ticker: string) => {
    try {
      return await getDossier(ticker);
    } catch {
      return null;
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await getWatchlist();
      const dossiers = await Promise.all(items.map((item) => loadDossier(item.ticker)));
      setRows(items.map((item, index) => ({
        ticker: item.ticker,
        name: item.name,
        dossier: dossiers[index],
        refreshing: false,
      })));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [loadDossier]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  const setRefreshing = (ticker: string, refreshing: boolean) => {
    setRows((current) => current.map((row) => row.ticker === ticker ? { ...row, refreshing } : row));
  };

  const refresh = async (ticker: string, force = false) => {
    setRefreshing(ticker, true);
    setError(null);
    try {
      const result = await refreshCompany(ticker, force);
      const failed = Object.entries(result.summary).filter(([, status]) =>
        !status.startsWith("ok") && status !== "cached" && !status.startsWith("pominięto"),
      );
      if (failed.length > 0) setError(`${ticker}: część źródeł wymaga uwagi (${failed.map(([key]) => key).join(", ")}).`);
      const dossier = await loadDossier(ticker);
      setRows((current) => current.map((row) => row.ticker === ticker ? {
        ...row,
        dossier,
        name: dossier?.company.name ?? row.name,
        refreshing: false,
      } : row));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRefreshing(ticker, false);
    }
  };

  const addTicker = async (event: React.FormEvent) => {
    event.preventDefault();
    const ticker = newTicker.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    setError(null);
    try {
      const created = await addToWatchlist(ticker);
      setNewTicker("");
      setRows((current) => [...current.filter((row) => row.ticker !== created.ticker), {
        ticker: created.ticker,
        name: created.name,
        dossier: null,
        refreshing: true,
      }]);
      setAdding(false);
      await refresh(created.ticker, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const remove = async (ticker: string) => {
    if (!window.confirm(`Usunąć ${ticker} z aktywnych analiz?`)) return;
    await removeFromWatchlist(ticker);
    setRows((current) => current.filter((row) => row.ticker !== ticker));
  };

  const refreshAll = async () => {
    for (const row of rows) {
      // Sequential by design: one polite source pipeline at a time.
      // eslint-disable-next-line no-await-in-loop
      await refresh(row.ticker);
    }
  };

  const ready = rows.filter((row) => hasDossierData(row.dossier)).length;
  const needsEvidence = rows.filter((row) => !hasDossierData(row.dossier) || (row.dossier?.insights.missing.length ?? 0) > 0).length;
  const stale = rows.filter((row) => {
    const days = staleDays(row.dossier?.freshness.financials_scraped_at ?? null);
    return days != null && days > 3;
  }).length;
  const anyRefreshing = rows.some((row) => row.refreshing);

  return (
    <main className="page-stack research-page">
      <section className="page-header research-header">
        <div>
          <p className="eyebrow">Aktywne przypadki</p>
          <h1>Research</h1>
          <p>Każda spółka ma jeden stan, główną lukę i następny krok. Pełne dane czekają w dossier.</p>
        </div>
        <form className="command-row" onSubmit={addTicker}>
          <input value={newTicker} onChange={(event) => setNewTicker(event.target.value)} placeholder="Ticker, np. DEC" aria-label="Ticker spółki" className="ticker-input" />
          <button className="btn accent" type="submit" disabled={adding}><IconPlus size={14} /> Dodaj ticker</button>
        </form>
      </section>

      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <><SkeletonRows rows={4} height={72} /><LoadingMessages messages={["Otwieram aktywne analizy…", "Sprawdzam następne kroki…"]} /></>
      ) : rows.length === 0 ? (
        <section className="empty-research">
          <IconDatabaseOff size={24} />
          <h2>Brak aktywnych analiz</h2>
          <p>Zacznij od transparentnego sita BiznesRadar albo dodaj znany ticker.</p>
          <Link className="btn accent" href="/discover">Przejdź do Discover <IconArrowRight size={14} /></Link>
        </section>
      ) : (
        <>
          <section className="queue-summary" aria-label="Stan kolejki">
            <div><span>Aktywne</span><strong>{rows.length}</strong></div>
            <div><span>Dossier gotowe</span><strong>{ready}</strong></div>
            <div className={needsEvidence > 0 ? "warn" : ""}><span>Wymaga danych</span><strong>{needsEvidence}</strong></div>
            <div className={stale > 0 ? "warn" : ""}><span>Nieaktualne</span><strong>{stale}</strong></div>
            <button className="btn" onClick={() => void refreshAll()} disabled={anyRefreshing}><IconRefresh size={14} className={anyRefreshing ? "spin" : ""} /> Odśwież kolejkę</button>
          </section>

          <section className="research-list">
            {rows.map((row) => {
              const dossier = row.dossier;
              const state = researchState(row);
              const signals = dossier?.insights.key_indicators.slice(0, 2) ?? [];
              const missingEvidence = dossier?.insights.missing[0]?.why ?? null;
              const concern = dossier?.insights.concerns[0] ?? null;
              const gap = missingEvidence ?? concern ?? "Brak krytycznej luki w obecnym odczycie";
              const scrapedAt = dossier?.freshness.financials_scraped_at ?? null;
              const days = staleDays(scrapedAt);
              return (
                <article className="research-row" key={row.ticker}>
                  <button className="research-open" onClick={() => router.push(`/stock/${row.ticker}`)} aria-label={`Kontynuuj analizę ${row.ticker}`}>
                    <div className="research-company">
                      <span className="ticker-mark">{row.ticker}</span>
                      <strong>{row.name ?? "Nazwa do uzupełnienia"}</strong>
                      <span>{fmtPln(dossier?.ttm.price)} · {fmtMcap(dossier?.ttm.market_cap)}</span>
                    </div>
                    <div className="research-state">
                      <span className={`badge ${state.tone}`}>{state.label}</span>
                      <p>{currentRead(dossier)}</p>
                    </div>
                    <div className="research-signals">
                      <span className="candidate-label">Kluczowe sygnały</span>
                      {signals.length > 0 ? signals.map((signal) => <span key={signal.id}>{signal.name}: <strong>{signal.value}</strong></span>) : <span>Po zebraniu danych</span>}
                    </div>
                    <div className={`research-gap ${!missingEvidence && !concern ? "clear" : ""}`}>
                      <span className="candidate-label">{missingEvidence ? "Główna luka" : "Główne ryzyko"}</span>
                      <span>{!missingEvidence && !concern ? <IconCircleCheck size={13} /> : <IconAlertTriangle size={13} />} {gap}</span>
                    </div>
                    <div className="research-next">
                      <span>{state.next}</span>
                      <small className={days != null && days > 3 ? "warn" : ""}><IconCircleCheck size={12} /> {relativeDate(scrapedAt)}</small>
                    </div>
                    <IconArrowRight className="research-arrow" size={17} />
                  </button>
                  <div className="research-maintenance">
                    <button className="btn icon" title="Odśwież dane" aria-label={`Odśwież ${row.ticker}`} onClick={() => void refresh(row.ticker, true)} disabled={row.refreshing}><IconRefresh size={15} className={row.refreshing ? "spin" : ""} /></button>
                    <button className="btn icon" title="Usuń analizę" aria-label={`Usuń ${row.ticker}`} onClick={() => void remove(row.ticker)}><IconTrash size={15} /></button>
                  </div>
                </article>
              );
            })}
          </section>
        </>
      )}
    </main>
  );
}
