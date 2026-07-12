"use client";

/** Compact, explainable entry to Research. Only evidence-backed sieves are active. */
import { useCallback, useEffect, useState } from "react";
import {
  IconCircleCheck,
  IconLock,
  IconPlus,
  IconRefresh,
} from "@tabler/icons-react";
import {
  addResearchCase,
  getDiscovery,
  getResearchCases,
  refreshDiscovery,
} from "@/lib/api";
import { LoadingMessages } from "@/components/Loading";
import { fmtDate, fmtNumber } from "@/lib/format";
import type { DiscoveryCandidate, DiscoveryCandidateMembership, DiscoveryResult, ResearchCaseSummary } from "@/lib/types";

const CANDIDATE_PAGE_SIZE = 12;

function membershipFactors(membership: DiscoveryCandidateMembership) {
  return membership.factors.map((factor) => ({
    label: factor.label,
    value: factor.id === "piotroski_f_score" && factor.value != null
      ? `${factor.value}/9`
      : fmtNumber(factor.value, 1),
    note: factor.note ?? "Czynnik tego sita — szczegółowa interpretacja wymaga źródła.",
  }));
}

export default function DiscoverPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [addedTickers, setAddedTickers] = useState<Set<string>>(new Set());
  const [closedTickers, setClosedTickers] = useState<Set<string>>(new Set());
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [visibleCount, setVisibleCount] = useState(CANDIDATE_PAGE_SIZE);
  const [error, setError] = useState<string | null>(null);
  const [researchReadWarning, setResearchReadWarning] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResearchReadWarning(null);
    const [discoveryResult, casesResult] = await Promise.allSettled([
      getDiscovery(),
      getResearchCases(),
    ]);
    if (discoveryResult.status === "fulfilled") {
      setResult(discoveryResult.value);
      setVisibleCount(CANDIDATE_PAGE_SIZE);
    } else {
      setError(discoveryResult.reason instanceof Error ? discoveryResult.reason.message : String(discoveryResult.reason));
    }
    if (casesResult.status === "fulfilled") {
      const rows: ResearchCaseSummary[] = casesResult.value;
      setAddedTickers(new Set(rows.filter((item) => item.state !== "closed").map((item) => item.ticker)));
      setClosedTickers(new Set(rows.filter((item) => item.state === "closed").map((item) => item.ticker)));
    } else {
      setResearchReadWarning("Nie udało się odczytać listy Research. Nadal możesz dodać spółkę — zapis zweryfikuje stan po stronie serwera.");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    setSuccess(null);
    try {
      const refreshed = await refreshDiscovery();
      setResult(refreshed);
      setVisibleCount(CANDIDATE_PAGE_SIZE);
      setSuccess("Lista kandydatów została odświeżona ze źródła.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  };

  const addCandidate = async (ticker: string) => {
    if (!result || addedTickers.has(ticker) || addingTickers.has(ticker)) return;

    setAddingTickers((current) => new Set(current).add(ticker));
    setError(null);
    setSuccess(null);
    try {
      const response = await addResearchCase({
        ticker,
        source_document_version_id: result.source_version_id,
      });
      setAddedTickers((current) => new Set(current).add(ticker));
      setClosedTickers((current) => {
        const next = new Set(current);
        next.delete(ticker);
        return next;
      });
      setSuccess(
        response.created_case
          ? `${ticker} dodano do Research. Możesz dodać kolejną spółkę.`
          : response.reactivated_case
            ? `${ticker} ponownie aktywowano w Research.`
          : `${ticker} jest już w Research.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAddingTickers((current) => {
        const next = new Set(current);
        next.delete(ticker);
        return next;
      });
    }
  };

  const candidatesByTicker = new Map((result?.candidates ?? []).map((candidate) => [candidate.ticker, candidate]));
  const sieveTitles = new Map((result?.sieves ?? []).map((sieve) => [sieve.id, sieve.title]));

  const renderCandidate = (candidate: DiscoveryCandidate, membership: DiscoveryCandidateMembership) => {
    const added = addedTickers.has(candidate.ticker);
    const closed = closedTickers.has(candidate.ticker);
    const adding = addingTickers.has(candidate.ticker);
    const addIsReady = membership.sieve_id === "financial_health_br_v1" && membership.source != null;
    const reportPeriod = membership.factors[0]?.report_period ?? "brak okresu";
    return (
      <article className="candidate-row" key={`${membership.sieve_id}:${candidate.ticker}`}>
        <div className="candidate-company">
          <span className="ticker-mark">{candidate.ticker}</span>
          <div>
            <strong>{candidate.name ?? "Nazwa do uzupełnienia"}</strong>
            <small>Raport {reportPeriod}</small>
            <small>{candidate.neutral_context.map((item) => `${item.label}: ${item.value ?? "brak"}`).join(" · ")}</small>
            <small>Do sprawdzenia: {membership.strategy_questions[0]}</small>
            {membership.factor_status === "stale" && <small className="warning">{membership.caveat}</small>}
          </div>
        </div>

        <div className="candidate-factor-list" aria-label={`Czynniki ${candidate.ticker} w sicie ${membership.sieve_id}`}>
          {membershipFactors(membership).map((factor) => (
            <div className="candidate-factor" key={factor.label}>
              <span>{factor.label}</span>
              <strong>{factor.value}</strong>
              <small>{factor.note}</small>
            </div>
          ))}
        </div>

        <div className="candidate-source-meta">
          <span className="badge muted">{membership.rank == null ? "Ranking nieaktualny" : `#${membership.rank} w tym sicie`}</span>
          {candidate.overlap.count > 1 && <span className="badge neutral">{candidate.overlap.sieve_ids.map((id) => sieveTitles.get(id) ?? id).join(" + ")}</span>}
        </div>

        <button
          className={`btn ${added ? "" : "accent"}`}
          type="button"
          onClick={() => void addCandidate(candidate.ticker)}
          disabled={!addIsReady || added || adding}
          aria-label={
            added
              ? `${candidate.ticker} jest w Research`
              : !addIsReady
                ? `${membership.sieve_id} nie ma jeszcze źródła do dodania`
                : closed
                ? `Wznów ${candidate.ticker} w Research`
                : `Dodaj ${candidate.ticker} do Research`
          }
        >
          {added ? <IconCircleCheck size={14} /> : <IconPlus size={14} />}
          {added ? "Dodano" : !addIsReady ? "Brak źródła" : adding ? "Dodaję…" : closed ? "Wznów Research" : "Dodaj do Research"}
        </button>
      </article>
    );
  };

  return (
    <main className="page-stack discover-page">
      <section className="page-header discovery-header">
        <div>
          <p className="eyebrow">Discover</p>
          <h1>Porównaj sita inwestycyjne</h1>
          <p>Każde sito odpowiada na inne pytanie. Do Research trafiają wyłącznie spółki wybrane przez Ciebie.</p>
        </div>
        <button className="btn" onClick={() => void refresh()} disabled={refreshing}>
          <IconRefresh size={15} className={refreshing ? "spin" : ""} />
          {refreshing ? "Odświeżam…" : "Odśwież źródło"}
        </button>
      </section>

      <section className="sieve-grid" aria-label="Dostępne sita inwestycyjne">
        {loading && !result ? Array.from({ length: 3 }, (_, index) => (
          <article className="sieve-card sieve-card-loading" key={index} aria-hidden="true">
            <span className="skeleton" /><span className="skeleton" /><span className="skeleton" />
          </article>
        )) : result?.sieves.map((sieve) => {
          const available = sieve.status === "available";
          const sieveCandidates = sieve.candidates
            .map((reference) => candidatesByTicker.get(reference.ticker))
            .filter((candidate): candidate is DiscoveryCandidate => candidate != null)
            .map((candidate) => ({ candidate, membership: candidate.memberships.find((item) => item.sieve_id === sieve.id) }))
            .filter((item): item is { candidate: DiscoveryCandidate; membership: DiscoveryCandidateMembership } => item.membership != null);
          return (
          <article className={`sieve-card ${available ? "available" : "unavailable"}`} key={sieve.id}>
            <header>
              <h2>{sieve.title}</h2>
              <span className={`badge ${available ? "success" : "muted"}`}>
                {available ? <IconCircleCheck size={13} /> : <IconLock size={13} />}
                {available ? `Dostępne · ${sieve.candidate_count} kand.` : "Zablokowane"}
              </span>
            </header>
            <p className="sieve-question">{sieve.question}</p>
            <div className="sieve-coverage">
              <span>Pokrycie danych</span>
              <strong>{sieve.coverage_count}/{sieve.universe_count} · {sieve.coverage_pct.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}%</strong>
              <div role="progressbar" aria-label={`Pokrycie danych sita ${sieve.title}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={sieve.coverage_pct}><span style={{ width: `${Math.min(100, sieve.coverage_pct)}%` }} /></div>
            </div>
            <dl className="sieve-factors">
              {sieve.factor_coverage.slice(0, 3).map((factor) => (
                <div key={factor.id}><dt>{factor.label}</dt><dd>{factor.covered_count}/{factor.total_count}</dd></div>
              ))}
            </dl>
            {sieve.factor_coverage.length > 3 && (
              <details className="sieve-gaps">
                <summary>Pozostałe obszary ({sieve.factor_coverage.length - 3})</summary>
                <dl className="sieve-factors">
                  {sieve.factor_coverage.slice(3).map((factor) => (
                    <div key={factor.id}><dt>{factor.label}</dt><dd>{factor.covered_count}/{factor.total_count}</dd></div>
                  ))}
                </dl>
              </details>
            )}
            {sieve.gaps.length > 0 && (
              <details className="sieve-gaps">
                <summary>Braki danych ({sieve.gaps.length})</summary>
                <ul>{sieve.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
              </details>
            )}
            {sieve.source && <small>{sieve.source.name} · zapis #{sieve.source.document_version_id} · dane {fmtDate(sieve.source.as_of)}</small>}
            {sieve.freshness && <small>Sprawdzono {fmtDate(sieve.freshness.last_successful_source_check_at)} · {sieve.freshness.status === "stale" ? "dane nieaktualne" : "źródło aktualne"}</small>}
            {available && (
              <div className="candidate-list discovery-sieve-candidates" aria-live="polite">
                {sieveCandidates.slice(0, visibleCount).map(({ candidate, membership }) => renderCandidate(candidate, membership))}
                {!sieveCandidates.length && <p className="empty-state">Brak kandydatów mimo dostępnego sita.</p>}
                {visibleCount < sieveCandidates.length && (
                  <button className="btn candidate-more" type="button" onClick={() => setVisibleCount((current) => current + CANDIDATE_PAGE_SIZE)}>
                    Pokaż kolejne · {sieveCandidates.length - visibleCount} pozostało
                  </button>
                )}
              </div>
            )}
          </article>
        ); })}
      </section>

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {researchReadWarning && <div className="error-box" role="status">{researchReadWarning}</div>}

      {result?.freshness.last_failed_refresh_at && new Date(result.freshness.last_failed_refresh_at) >= new Date(result.freshness.last_successful_source_check_at) && (
        <div className="error-box" role="status">
          Ostatnia nieudana próba odświeżenia ({fmtDate(result.freshness.last_failed_refresh_at)}): {result.freshness.last_failed_refresh_reason ?? "nieznany błąd"}. Wyświetlane są ostatnie poprawne dane.
        </div>
      )}

      {loading && <LoadingMessages messages={["Otwieram zapisane sita…", "Sprawdzam, które spółki są już w Research…"]} />}
    </main>
  );
}
