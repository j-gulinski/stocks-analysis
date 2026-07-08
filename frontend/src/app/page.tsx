"use client";

/** Watchlist dashboard (`/`) — layout per docs/design/mockups.html screen 1. */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  IconArrowRight,
  IconPlus,
  IconRefresh,
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
      return null; // company added but never refreshed — row shows dashes
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
    if (!newTicker.trim()) return;
    setAdding(true);
    setError(null);
    try {
      await addToWatchlist(newTicker.trim().toUpperCase());
      setNewTicker("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const setRefreshing = (ticker: string, refreshing: boolean) =>
    setRows((current) =>
      current.map((r) => (r.ticker === ticker ? { ...r, refreshing } : r)),
    );

  const handleRefresh = async (ticker: string) => {
    setRefreshing(ticker, true);
    setError(null);
    try {
      const result = await refreshCompany(ticker);
      const failed = Object.entries(result.summary).filter(
        ([, s]) => !s.startsWith("ok") && s !== "cached",
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

  return (
    <main>
      <div className="spread">
        <h1 style={{ fontSize: 19 }}>Watchlist</h1>
        <form className="row" onSubmit={handleAdd}>
          <input
            placeholder="Ticker, np. DEC"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            style={{ width: 130 }}
          />
          <button className="btn" type="submit" disabled={adding}>
            <IconPlus size={14} /> Dodaj
          </button>
        </form>
      </div>

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
        <p className="empty-state">
          Pusta watchlista — dodaj pierwszy ticker (np. DEC), potem kliknij odśwież.
        </p>
      ) : (
        <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Spółka</th>
              <th>Kurs</th>
              <th>Mcap</th>
              <th>C/Z TTM</th>
              <th>C/Z fwd</th>
              <th>Marża br.</th>
              <th>Przych. r/r</th>
              <th style={{ textAlign: "center" }}>AI</th>
              <th style={{ textAlign: "center" }}>Dane</th>
              <th style={{ width: 70 }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const d = row.dossier;
              const lastQ = d?.quarters.at(-1);
              const scraped = d?.freshness.financials_scraped_at ?? null;
              const days = staleDays(scraped);
              return (
                <tr
                  key={row.ticker}
                  className="clickable"
                  onClick={() => router.push(`/stock/${row.ticker}`)}
                >
                  <td>
                    <span style={{ fontWeight: 500 }}>{row.ticker}</span>
                    <br />
                    <span className="small muted">{row.name ?? "—"}</span>
                  </td>
                  <td>{fmtPln(d?.ttm.price)}</td>
                  <td className="secondary">{fmtMcap(d?.ttm.market_cap)}</td>
                  <td>{fmtNumber(d?.ttm.pe)}</td>
                  <td className={d?.latest_forecast ? "pos" : "muted"}>
                    {fmtNumber(d?.latest_forecast?.result.forward.pe)}
                  </td>
                  <td>
                    <MarginTrend dossier={d} />
                  </td>
                  <td className={signClass(lastQ?.revenue_yoy_pct)}>
                    {fmtPct(lastQ?.revenue_yoy_pct, { signed: true })}
                  </td>
                  <td style={{ textAlign: "center" }} className="muted small">
                    brak
                  </td>
                  <td
                    style={{ textAlign: "center" }}
                    className={`small ${days != null && days > 3 ? "warn" : "secondary"}`}
                  >
                    {relativeDate(scraped)}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className="row" style={{ gap: 2, justifyContent: "flex-end" }}>
                      <button
                        className="btn icon"
                        title="Odśwież dane"
                        disabled={row.refreshing}
                        onClick={() => handleRefresh(row.ticker)}
                      >
                        <IconRefresh size={15} className={row.refreshing ? "spin" : ""} />
                      </button>
                      <button
                        className="btn icon"
                        title="Usuń z watchlisty"
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
      )}

      {rows.length > 0 && (
        <div className="spread" style={{ marginTop: 12 }}>
          <span className="small muted">
            {rows.length} {rows.length === 1 ? "spółka" : "spółki"} · odświeżanie działa
            sekwencyjnie (limity zapytań)
          </span>
          <button className="btn" onClick={handleRefreshAll} disabled={anyRefreshing}>
            <IconRefresh size={13} className={anyRefreshing ? "spin" : ""} /> Odśwież
            wszystkie
          </button>
        </div>
      )}
    </main>
  );
}
