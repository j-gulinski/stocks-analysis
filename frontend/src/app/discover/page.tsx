"use client";

/** One exclusion-first Workbench sieve. Reads never refresh or enqueue. */
import { useCallback, useEffect, useState } from "react";
import { IconAlertTriangle, IconBan, IconDatabaseSearch, IconRefresh } from "@tabler/icons-react";
import { getDiscovery, refreshDiscovery } from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { fmtDate, fmtNumber } from "@/lib/format";
import type { DiscoveryCandidate, DiscoveryFactor, DiscoveryResult } from "@/lib/types";

const PAGE_SIZE = 12;

function factorValue(factor: DiscoveryFactor) {
  if (factor.id === "piotroski_f_score" && factor.value != null) return `${factor.value}/9`;
  return fmtNumber(factor.value, 1);
}

function ruleText(operator: string, threshold: number | null) {
  if (operator === "composite" || threshold == null) return "warunek łączny";
  const symbol = { lt: "<", lte: "≤", gt: ">", gte: "≥", eq: "=" }[operator] ?? operator;
  return `${symbol} ${fmtNumber(threshold, threshold % 1 === 0 ? 0 : 1)}`;
}

export default function DiscoverPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await getDiscovery());
      setVisibleCount(PAGE_SIZE);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    setSuccess(null);
    try {
      setResult(await refreshDiscovery());
      setVisibleCount(PAGE_SIZE);
      setSuccess("Źródła Discover zostały odświeżone.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  };

  const renderCandidate = (candidate: DiscoveryCandidate) => {
    return (
      <article className="candidate-row" key={candidate.ticker}>
        <div className="candidate-company">
          <span className="ticker-mark">{candidate.ticker}</span>
          <div>
            <strong>{candidate.name ?? "Nazwa do uzupełnienia"}</strong>
            <small>{candidate.improvement_signals.join(" · ") || "Brak opisanych sygnałów poprawy"}</small>
          </div>
        </div>
        <div className="candidate-factor-list" aria-label={`Czynniki ${candidate.ticker}`}>
          {candidate.factors.map((factor) => (
            <div className="candidate-factor" key={factor.id}>
              <span>{factor.label}</span>
              <strong>{factorValue(factor)}</strong>
              <small>{factor.delta == null ? factor.note : `${factor.note ?? "Zmiana"}: ${fmtNumber(factor.delta, 1)}`}</small>
            </div>
          ))}
        </div>
        <div className="candidate-source-meta">
          <span className="badge muted">{candidate.rank == null ? "Bez rankingu" : `Kolejność #${candidate.rank}`}</span>
          <small>{candidate.rank_basis[0] ?? "Członkostwo wynika z reguł sita, nie z rekomendacji."}</small>
        </div>
        <span className="badge warning">Przekazanie do Research wymaga zamrożonego wyniku sita</span>
        <details className="candidate-ranking-details">
          <summary>Dlaczego spółka przeszła?</summary>
          <ul>{candidate.rank_basis.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          {candidate.factor_gaps.length > 0 && <p>Braki danych: {candidate.factor_gaps.join(" ")}</p>}
        </details>
      </article>
    );
  };

  const sieve = result?.sieve;
  const refreshFailed = result?.freshness.last_failed_refresh_at
    && new Date(result.freshness.last_failed_refresh_at) >= new Date(result.freshness.last_successful_source_check_at);

  return (
    <main className="page-stack discover-page">
      <section className="page-header discovery-header">
        <div><p className="eyebrow">Discover</p><h1>Odrzuć najsłabsze spółki</h1><p>Jedno sito Workbench najpierw zapisuje powody wykluczenia, a potem wymaga realnych sygnałów poprawy.</p></div>
        <button className="btn" onClick={() => void refresh()} disabled={refreshing}><IconRefresh size={15} className={refreshing ? "spin" : ""} />{refreshing ? "Odświeżam…" : "Odśwież źródła"}</button>
      </section>

      {sieve && (
        <section className="discover-sieve-summary" aria-label="Sito Workbench">
          <div>
            <p className="section-label">{sieve.id} · {sieve.version}</p>
            <h2>{sieve.title}</h2>
            <p>{sieve.question}</p>
          </div>
          <div className="discover-sieve-metadata">
            <span className={`badge ${sieve.status === "available" ? "success" : "warning"}`}>{sieve.status === "available" ? "Sito gotowe" : "Sito zablokowane"}</span>
            <span className="badge neutral">Pokrycie {sieve.coverage_count}/{sieve.universe_count} · {sieve.coverage_pct.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}%</span>
            {sieve.source && <small><IconDatabaseSearch size={13} /> {sieve.source.name} · dokument #{sieve.source.document_version_id} · {fmtDate(sieve.source.as_of)}</small>}
          </div>
          <div className="discover-sieve-rules">
            <span>Reguły wykluczenia i poprawy</span>
            {sieve.rules.map((rule) => <span className={`badge ${rule.layer === "hard_kill" ? "warning" : "muted"}`} key={`${rule.layer}-${rule.factor_id}`}>{rule.label} · {ruleText(rule.operator, rule.threshold)}</span>)}
          </div>
          {sieve.gaps.length > 0 && <div className="discover-blocked-reason"><IconAlertTriangle size={16} /><div><strong>Brakuje danych do wykonania sita</strong><ul>{sieve.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></div></div>}
        </section>
      )}

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {refreshFailed && <div className="error-box" role="status">Ostatnie odświeżenie nie powiodło się: {result?.freshness.last_failed_refresh_reason ?? "nieznany błąd"}. Pokazuję ostatni poprawny zapis.</div>}
      {loading && <LoadingMessages messages={["Otwieram zapisane sito Workbench…"]} />}

      <section className="candidate-section" aria-labelledby="candidate-title">
        <div className="section-heading compact-heading"><div><p className="section-label">Przeszły sito</p><h2 id="candidate-title">Spółki warte dalszego Research</h2></div><p>Kolejność pokazuje siłę poprawy; członkostwo i powody są ważniejsze niż numer.</p></div>
        {loading ? <SkeletonRows rows={6} height={82} /> : !result?.candidates.length ? <div className="empty-state">{sieve?.status === "blocked" ? "Sito nie ruszy, dopóki batch czynników rynkowych nie będzie kompletny. Braki są widoczne powyżej." : "Żadna spółka nie przeszła bieżących reguł."}</div> : (
          <div className="candidate-list" aria-live="polite">
            {result.candidates.slice(0, visibleCount).map(renderCandidate)}
            {visibleCount < result.candidates.length && <button className="btn candidate-more" type="button" onClick={() => setVisibleCount((current) => current + PAGE_SIZE)}>Pokaż kolejne · {result.candidates.length - visibleCount} pozostało</button>}
          </div>
        )}
      </section>

      {result && (
        <details className="discover-excluded">
          <summary><IconBan size={15} /> Odrzucone ({result.excluded.length})</summary>
          {result.excluded.length === 0 ? <p>Brak policzonych wykluczeń w tym zapisie.</p> : result.excluded.map((company) => (
            <article key={company.ticker}><strong>{company.ticker} · {company.name ?? "nazwa do uzupełnienia"}</strong><ul>{company.kill_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>{company.factor_gaps.length > 0 && <small>Braki: {company.factor_gaps.join(" · ")}</small>}</article>
          ))}
        </details>
      )}
    </main>
  );
}
