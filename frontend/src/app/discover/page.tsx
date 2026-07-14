"use client";

/** One exclusion-first Workbench sieve. Reads never refresh or enqueue. */
import { useCallback, useEffect, useState } from "react";
import { IconAlertTriangle, IconBan, IconDatabaseSearch, IconRefresh } from "@tabler/icons-react";
import { addResearchCase, getDiscovery, refreshDiscovery } from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { fmtDate, fmtNumber } from "@/lib/format";
import type { DiscoveryCandidate, DiscoveryFactor, DiscoveryResult, DiscoveryScoreComponent } from "@/lib/types";

const PAGE_SIZE = 12;

function factorValue(factor: DiscoveryFactor) {
  if (factor.id === "piotroski_f_score" && factor.value != null) return `${factor.value}/9`;
  return fmtNumber(factor.value, 1);
}

function factorSource(factor: DiscoveryFactor) {
  if (factor.source_document_version_id == null) return "Brak przypisanego źródła";
  const period = factor.period ? `okres ${factor.period}` : "okres nieznany";
  const freshness = factor.source_freshness === "stale" ? "źródło nieaktualne" : "źródło aktualne";
  return `Dok. #${factor.source_document_version_id} · ${period} · pobrano ${fmtDate(factor.source_as_of)} · ${freshness}`;
}

function scoreComponentValue(component: DiscoveryScoreComponent) {
  const raw = fmtNumber(component.raw_value, 1);
  const ranking = fmtNumber(component.ranking_value, 1);
  const unit = component.id === "current_pe"
    ? "×"
    : component.id === "operating_margin_change"
      ? " pp"
      : "%";
  return component.raw_value === component.ranking_value
    ? `${raw}${unit}`
    : `${raw}${unit} → limit ${ranking}${unit}`;
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
  const [addingTicker, setAddingTicker] = useState<string | null>(null);

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

  const addToResearch = async (candidate: DiscoveryCandidate) => {
    const currentSieve = result?.sieve;
    if (
      currentSieve?.status !== "available"
      || currentSieve.batch_id == null
      || addingTicker != null
    ) return;
    setAddingTicker(candidate.ticker);
    setError(null);
    setSuccess(null);
    try {
      const created = await addResearchCase({
        ticker: candidate.ticker,
        discovery: {
          batch_id: currentSieve.batch_id,
          sieve_id: "workbench_sieve_v1",
          sieve_version: "workbench-sieve-v1",
        },
      });
      setSuccess(
        created.created_case
          ? `${candidate.ticker} dodano do Research z zamrożonym wynikiem sita.`
          : `${candidate.ticker} ma już sprawę Research; jej zamrożone pochodzenie nie zostało zmienione.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAddingTicker(null);
    }
  };

  const renderCandidate = (candidate: DiscoveryCandidate) => {
    return (
      <article className="candidate-row" key={candidate.ticker}>
        <div className="candidate-company">
          <span className="ticker-mark">{candidate.ticker}</span>
          <div>
            <strong>{candidate.name ?? "Nazwa do uzupełnienia"}</strong>
            <small>Jeden porównywalny wynik; składniki i źródła są w szczegółach.</small>
          </div>
        </div>
        <div className="candidate-factor-list" aria-label={`Wynik potencjału ${candidate.ticker}`}>
          <div className="candidate-factor">
            <span>Wynik potencjału</span>
            <strong>{candidate.potential_score == null ? "—" : `${fmtNumber(candidate.potential_score, 1)}/100`}</strong>
            <small>{candidate.potential_score == null ? `Brak pełnych danych · ${candidate.score_components.length}/5 składników` : "Porównywalny w bieżącym batchu · 5/5 składników"}</small>
          </div>
        </div>
        <div className="candidate-source-meta">
          <span className="badge muted">{candidate.rank == null ? "Bez kolejności" : `Potencjał #${candidate.rank}`}</span>
          <small>{candidate.rank_basis[0] ?? "Członkostwo wynika z reguł sita, nie z rekomendacji."}</small>
        </div>
        <button
          className="btn"
          type="button"
          onClick={() => void addToResearch(candidate)}
          disabled={sieve?.status !== "available" || sieve.batch_id == null || addingTicker != null}
        >
          {addingTicker === candidate.ticker ? "Dodaję…" : "Dodaj do Research"}
        </button>
        <details className="candidate-ranking-details">
          <summary>Jak policzono wynik?</summary>
          <ul>{candidate.rank_basis.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          {candidate.score_components.length > 0 && <ul>{candidate.score_components.map((component) => {
            const factor = candidate.factors.find((item) => item.id === component.id);
            return <li key={component.id}>{component.label}: {scoreComponentValue(component)} → percentyl {fmtNumber(component.percentile, 1)} · waga {fmtNumber(component.weight * 100, 0)}%{factor ? ` · ${factorSource(factor)}` : ""}</li>;
          })}</ul>}
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
            <span className="badge neutral" title={sieve.coverage_label}>Dane bazowe {sieve.coverage_count}/{sieve.universe_count} · {sieve.coverage_pct.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}%</span>
            {sieve.sources.length > 0 && <small><IconDatabaseSearch size={13} /> batch #{sieve.batch_id} · {sieve.sources.length} stron źródłowych · {fmtDate(result?.as_of)}</small>}
          </div>
          <div className="discover-sieve-rules">
            <span>Reguły wykluczenia i poprawy</span>
            {sieve.rules.map((rule) => <span className={`badge ${rule.layer === "hard_kill" ? "warning" : "muted"}`} key={`${rule.layer}-${rule.factor_id}`}>{rule.label} · {ruleText(rule.operator, rule.threshold)}</span>)}
          </div>
          {sieve.gaps.length > 0 && <div className="discover-blocked-reason"><IconAlertTriangle size={16} /><div><strong>Ograniczenia pokrycia batcha</strong><ul>{sieve.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></div></div>}
          {sieve.sources.length > 0 && <details className="candidate-ranking-details"><summary>Źródła zamrożonego batcha</summary><ul>{sieve.sources.map((source) => <li key={source.id}>{source.label} · dokument #{source.document_version_id} · {fmtDate(source.as_of)} · {source.parser_version}</li>)}</ul></details>}
        </section>
      )}

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {refreshFailed && <div className="error-box" role="status">Ostatnie odświeżenie nie powiodło się: {result?.freshness.last_failed_refresh_reason ?? "nieznany błąd"}. Pokazuję ostatni poprawny zapis.</div>}
      {loading && <LoadingMessages messages={["Otwieram zapisane sito Workbench…"]} />}

      <section className="candidate-section" aria-labelledby="candidate-title">
        <div className="section-heading compact-heading"><div><p className="section-label">Przeszły sito</p><h2 id="candidate-title">Najwyższy mierzalny potencjał</h2></div><p>Jeden wynik 0–100 z pięciu równoważnych percentyli; nie jest prawdopodobieństwem. {result && sieve ? `Pokazano ${result.result_count} z ${sieve.survivor_count}, maksymalnie 100.` : ""}</p></div>
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
            <article key={company.ticker}><strong>{company.ticker} · {company.name ?? "nazwa do uzupełnienia"}</strong><ul>{company.kill_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul><p>{company.factors.filter((factor) => factor.value != null).map((factor) => `${factor.label}: ${factorValue(factor)} (${factorSource(factor)})`).join(" · ")}</p>{company.factor_gaps.length > 0 && <small>Braki: {company.factor_gaps.join(" · ")}</small>}</article>
          ))}
        </details>
      )}
    </main>
  );
}
