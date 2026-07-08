"use client";

/** Watchlist dashboard (`/`) — layout per docs/design/mockups.html screen 1. */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  IconArrowRight,
  IconAlertTriangle,
  IconBrain,
  IconChartDots,
  IconCircleCheck,
  IconClockExclamation,
  IconDatabase,
  IconPlus,
  IconRefresh,
  IconShieldCheck,
  IconTrash,
  IconTrendingDown,
  IconTrendingUp,
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
import { fmtMcap, fmtNumber, fmtPct, fmtPln, relativeDate, signClass, staleDays } from "@/lib/format";
import type { Dossier } from "@/lib/types";

interface Row {
  ticker: string;
  name: string | null;
  dossier: Dossier | null;
  refreshing: boolean;
}

function MarginTrend({ dossier }: { dossier: Dossier | null }) {
  const quarters = dossier?.quarters ?? [];
  const current = quarters.at(-1)?.gross_margin_pct ?? null;
  const previous = quarters.at(-2)?.gross_margin_pct ?? null;
  if (current == null) return <span className="muted">—</span>;
  if (previous == null || Math.abs(current - previous) < 0.05)
    return (
      <span className="secondary">
        {fmtPct(current)} <IconArrowRight size={13} />
      </span>
    );
  const up = current > previous;
  return (
    <span className={up ? "pos" : "neg"}>
      {fmtPct(current)} {up ? <IconTrendingUp size={14} /> : <IconTrendingDown size={14} />}
    </span>
  );
}

function entryTone(code: string | undefined): string {
  if (code === "attractive") return "success";
  if (code === "neutral") return "warning";
  if (code === "weak") return "danger";
  return "muted";
}

function scoreTone(dossier: Dossier | null): string {
  if (!dossier || dossier.prescore.total <= 0) return "muted";
  const ratio = dossier.prescore.passed / dossier.prescore.total;
  if (ratio >= 0.75) return "success";
  if (ratio >= 0.5) return "warning";
  return "danger";
}

function stockRead(dossier: Dossier | null): { label: string; detail: string } {
  if (!dossier) {
    return { label: "Dossier w budowie", detail: "Trwa pobieranie danych źródłowych." };
  }
  if (dossier.thesis?.entry_quality) {
    return {
      label: dossier.thesis.entry_quality.label,
      detail: dossier.thesis.entry_quality.rationale,
    };
  }
  const signal = dossier.insights.strengths[0] ?? dossier.insights.summary;
  return { label: dossier.insights.summary, detail: signal };
}

function topRisk(dossier: Dossier | null): string {
  if (!dossier) return "brak danych";
  return dossier.insights.concerns[0] ?? dossier.insights.missing[0]?.why ?? "brak dużej flagi";
}

function valuationText(dossier: Dossier | null): {
  upside: number | null;
  label: string;
} {
  if (!dossier) return { upside: null, label: "brak scenariuszy" };
  const upside =
    dossier.scenarios?.weighted_expected_upside_pct ??
    dossier.valuation?.potential.value_pct ??
    null;
  const label = dossier.scenarios
    ? "EV scenariuszy"
    : dossier.valuation
      ? dossier.valuation.potential.basis_label
      : "brak scenariuszy";
  return { upside, label };
}

export default function WatchlistPage() {
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
      const dossiers = await Promise.all(items.map((i) => loadDossier(i.ticker)));
      setRows(
        items.map((item, index) => ({
          ticker: item.ticker,
          name: item.name,
          dossier: dossiers[index],
          refreshing: false,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [loadDossier]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    const ticker = newTicker.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    setError(null);
    let createdTicker: string | null = null;
    try {
      const created = await addToWatchlist(ticker);
      createdTicker = created.ticker;
      setNewTicker("");
      setRows((current) => [
        ...current.filter((row) => row.ticker !== created.ticker),
        {
          ticker: created.ticker,
          name: created.name,
          dossier: null,
          refreshing: true,
        },
      ]);
      setAdding(false);

      const result = await refreshCompany(created.ticker, true);
      const failed = Object.entries(result.summary).filter(
        ([, s]) => !s.startsWith("ok") && s !== "cached" && !s.startsWith("pominięto"),
      );
      if (failed.length > 0) {
        setError(
          `${created.ticker}: dane dodane, ale część źródeł wymaga uwagi (${failed
            .map(([k]) => k)
            .join(", ")}).`,
        );
      }
      const dossier = await loadDossier(created.ticker);
      setRows((current) =>
        current.map((row) =>
          row.ticker === created.ticker
            ? {
                ...row,
                dossier,
                name: dossier?.company.name ?? row.name,
                refreshing: false,
              }
            : row,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if (createdTicker) setRefreshing(createdTicker, false);
    } finally {
      setAdding(false);
    }
  };

  const setRefreshing = (ticker: string, refreshing: boolean) =>
    setRows((current) =>
      current.map((r) => (r.ticker === ticker ? { ...r, refreshing } : r)),
    );

  const handleRefresh = async (ticker: string, force = false) => {
    setRefreshing(ticker, true);
    setError(null);
    try {
      const result = await refreshCompany(ticker, force);
      const failed = Object.entries(result.summary).filter(
        ([, s]) => !s.startsWith("ok") && s !== "cached" && !s.startsWith("pominięto"),
      );
      if (failed.length > 0) {
        setError(
          `${ticker}: część źródeł z problemami (${failed
            .map(([k]) => k)
            .join(", ")}) — szczegóły na stronie spółki po odświeżeniu.`,
        );
      }
      const dossier = await loadDossier(ticker);
      setRows((current) =>
        current.map((r) =>
          r.ticker === ticker
            ? { ...r, dossier, name: dossier?.company.name ?? r.name, refreshing: false }
            : r,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRefreshing(ticker, false);
    }
  };

  const handleRefreshAll = async () => {
    // Sequential on purpose — one polite scrape pipeline at a time.
    for (const row of rows) {
      // eslint-disable-next-line no-await-in-loop
      await handleRefresh(row.ticker);
    }
  };

  const handleRemove = async (ticker: string) => {
    if (!window.confirm(`Usunąć ${ticker} z watchlisty?`)) return;
    await removeFromWatchlist(ticker);
    setRows((current) => current.filter((r) => r.ticker !== ticker));
  };

  const anyRefreshing = rows.some((r) => r.refreshing);
  const readyRows = rows.filter((r) => hasDossierData(r.dossier)).length;
  const scoredRows = rows
    .filter((row) => hasDossierData(row.dossier))
    .sort((a, b) => {
      const ar =
        (a.dossier?.prescore.passed ?? 0) / Math.max(1, a.dossier?.prescore.total ?? 1);
      const br =
        (b.dossier?.prescore.passed ?? 0) / Math.max(1, b.dossier?.prescore.total ?? 1);
      return br - ar;
    });
  const bestRow = scoredRows[0] ?? null;
  const forumRow =
    rows
      .filter((row) => (row.dossier?.forum.posts ?? 0) > 0)
      .sort((a, b) => (b.dossier?.forum.posts ?? 0) - (a.dossier?.forum.posts ?? 0))[0] ??
    null;
  const staleRows = rows.filter((r) => {
    if (!hasDossierData(r.dossier)) return false;
    const scraped = r.dossier?.freshness.financials_scraped_at ?? null;
    const days = staleDays(scraped);
    return days != null && days > 3;
  }).length;

  return (
    <main className="page-stack">
      <section className="page-header">
        <div>
          <h1>Watchlist</h1>
          <p>
            Szybki pulpit spółek GPW: wyceny, świeżość danych i pierwsze sygnały
            jakości w jednym widoku.
          </p>
        </div>
        <form className="command-row" onSubmit={handleAdd}>
          <input
            placeholder="Ticker, np. DEC"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            className="ticker-input"
            aria-label="Ticker spółki"
          />
          <button className="btn" type="submit" disabled={adding}>
            <IconPlus size={14} /> Dodaj
          </button>
        </form>
      </section>

      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <>
          <SkeletonRows rows={4} height={52} />
          <LoadingMessages
            messages={[
              "Wczytuję watchlistę…",
              "Zbieram dossier każdej spółki…",
              "Liczę wskaźniki…",
            ]}
          />
        </>
      ) : rows.length === 0 ? (
        <section className="empty-state empty-panel">
          <IconPlus size={18} />
          <strong>Pusta watchlista</strong>
          <span>Dodaj pierwszy ticker, a aplikacja od razu pobierze dane.</span>
        </section>
      ) : (
        <>
          <section className="watchlist-brief">
            <div className="brief-card">
              <span className="brief-icon">
                <IconDatabase size={15} />
              </span>
              <div>
                <p className="k">Dane gotowe</p>
                <p className="v">{readyRows}/{rows.length}</p>
                <p className="note">{staleRows > 0 ? `${staleRows} wymaga odświeżenia` : "źródła aktualne"}</p>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">
                <IconShieldCheck size={15} />
              </span>
              <div>
                <p className="k">Najlepsze dopasowanie</p>
                <p className="v">{bestRow?.ticker ?? "—"}</p>
                <p className="note">
                  {bestRow?.dossier
                    ? `${bestRow.dossier.prescore.passed}/${bestRow.dossier.prescore.total} strategii`
                    : "brak gotowego dossier"}
                </p>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">
                <IconBrain size={15} />
              </span>
              <div>
                <p className="k">Forum / AI kontekst</p>
                <p className="v">{forumRow?.ticker ?? "—"}</p>
                <p className="note">
                  {forumRow?.dossier
                    ? `${forumRow.dossier.forum.posts} postów, ${forumRow.dossier.forum.topics} wątków`
                    : "powiąż wątki PortalAnaliz"}
                </p>
              </div>
            </div>
          </section>

          <section className="table-panel">
            <div className="table-toolbar">
              <div className="status-strip">
                <span className="status-pill">
                  <IconCircleCheck size={13} /> {readyRows}/{rows.length} z dossier
                </span>
                <span className={`status-pill ${staleRows > 0 ? "warn" : ""}`}>
                  <IconClockExclamation size={13} /> {staleRows} po terminie
                </span>
              </div>
              <button className="btn" onClick={handleRefreshAll} disabled={anyRefreshing}>
                <IconRefresh size={13} className={anyRefreshing ? "spin" : ""} /> Odśwież
                wszystkie
              </button>
            </div>
            <div className="table-scroll watchlist-table">
              <table className="table decision-table">
                <thead>
                  <tr>
                    <th>Spółka</th>
                    <th>Odczyt</th>
                    <th>Strategia</th>
                    <th>Wycena</th>
                    <th>Operacje</th>
                    <th>Dane</th>
                    <th style={{ width: 70 }} />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const d = row.dossier;
                    const hasData = hasDossierData(d);
                    const lastQ = d?.quarters.at(-1);
                    const scraped = d?.freshness.financials_scraped_at ?? null;
                    const days = staleDays(scraped);
                    const read = stockRead(d);
                    const valuation = valuationText(d);
                    const thesisCode = d?.thesis?.entry_quality.code;
                    return (
                      <tr
                        key={row.ticker}
                        className="clickable"
                        onClick={() => router.push(`/stock/${row.ticker}`)}
                      >
                        <td data-label="Spółka">
                          <span className="ticker-mark">{row.ticker}</span>
                          <span className="company-name">
                            {row.refreshing ? "ładowanie danych…" : row.name ?? (hasData ? "—" : "brak danych")}
                          </span>
                          <span className="stock-meta">
                            {fmtPln(d?.ttm.price)} · {fmtMcap(d?.ttm.market_cap)}
                          </span>
                        </td>
                        <td className="watch-read-cell" data-label="Odczyt">
                          <span className={`badge ${entryTone(thesisCode)}`}>
                            {read.label}
                          </span>
                          <span className="watch-read">{read.detail}</span>
                        </td>
                        <td data-label="Strategia">
                          <span className={`badge ${scoreTone(d)}`}>
                            {d ? `${d.prescore.passed}/${d.prescore.total}` : "—"}
                          </span>
                          <span className="cell-note">
                            <IconAlertTriangle size={12} /> {topRisk(d)}
                          </span>
                        </td>
                        <td data-label="Wycena">
                          <span className={signClass(valuation.upside)}>
                            {fmtPct(valuation.upside, { signed: true })}
                          </span>
                          <span className="cell-note">
                            C/Z {fmtNumber(d?.ttm.pe)} · fwd {fmtNumber(d?.latest_forecast?.result.forward.pe)}
                          </span>
                          <span className="cell-note">{valuation.label}</span>
                        </td>
                        <td data-label="Operacje">
                          <span className={signClass(lastQ?.revenue_yoy_pct)}>
                            <IconChartDots size={13} /> {fmtPct(lastQ?.revenue_yoy_pct, { signed: true })} r/r
                          </span>
                          <span className="cell-note">marża br. <MarginTrend dossier={d} /></span>
                        </td>
                        <td data-label="Dane">
                          {row.refreshing ? (
                            <span className="badge accent">pobieranie</span>
                          ) : hasData ? (
                            <span className={`badge ${days != null && days > 3 ? "warning" : "neutral"}`}>
                              {relativeDate(scraped)}
                            </span>
                          ) : (
                            <span className="badge warning">brak</span>
                          )}
                          <span className="cell-note">
                            forum {d?.forum.posts ?? 0} · kurs {relativeDate(d?.freshness.last_price_date)}
                          </span>
                        </td>
                        <td data-label="Akcje" onClick={(e) => e.stopPropagation()}>
                          <span className="row row-actions">
                            <button
                              className="btn icon"
                              title="Odśwież dane"
                              aria-label={`Odśwież dane ${row.ticker}`}
                              disabled={row.refreshing}
                              onClick={() => handleRefresh(row.ticker, true)}
                            >
                              <IconRefresh size={15} className={row.refreshing ? "spin" : ""} />
                            </button>
                            <button
                              className="btn icon"
                              title="Usuń z watchlisty"
                              aria-label={`Usuń ${row.ticker} z watchlisty`}
                              onClick={() => handleRemove(row.ticker)}
                            >
                              <IconTrash size={15} />
                            </button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {rows.length > 0 && (
        <p className="small muted page-note">
          {rows.length} {rows.length === 1 ? "spółka" : "spółki"} · odświeżanie działa
          sekwencyjnie ze względu na limity źródeł.
        </p>
      )}
    </main>
  );
}
