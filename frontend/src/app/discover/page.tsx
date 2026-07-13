"use client";

/** Compact, explainable entry to Research. Only evidence-backed sieves are active. */
import { useCallback, useEffect, useState } from "react";
import {
  IconCircleCheck,
  IconDatabaseSearch,
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
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
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

function selectedAvailableSieveId(result: DiscoveryResult) {
  return result.sieves.find((sieve) => sieve.status === "available")?.id ?? null;
}

export default function DiscoverPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [addedTickers, setAddedTickers] = useState<Set<string>>(new Set());
  const [closedTickers, setClosedTickers] = useState<Set<string>>(new Set());
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [visibleCount, setVisibleCount] = useState(CANDIDATE_PAGE_SIZE);
  const [selectedSieveId, setSelectedSieveId] = useState<string | null>(null);
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
      const nextResult = discoveryResult.value;
      setResult(nextResult);
      setSelectedSieveId((current) => (
        current && nextResult.sieves.some((sieve) => sieve.id === current && sieve.status === "available")
          ? current
          : selectedAvailableSieveId(nextResult)
      ));
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
      setSelectedSieveId((current) => (
        current && refreshed.sieves.some((sieve) => sieve.id === current && sieve.status === "available")
          ? current
          : selectedAvailableSieveId(refreshed)
      ));
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
  const selectedSieve = result?.sieves.find((sieve) => sieve.id === selectedSieveId)
    ?? result?.sieves.find((sieve) => sieve.status === "available")
    ?? null;
  const selectedCandidates = selectedSieve?.candidates
    .map((reference) => candidatesByTicker.get(reference.ticker))
    .filter((candidate): candidate is DiscoveryCandidate => candidate != null)
    .map((candidate) => ({ candidate, membership: candidate.memberships.find((item) => item.sieve_id === selectedSieve.id) }))
    .filter((item): item is { candidate: DiscoveryCandidate; membership: DiscoveryCandidateMembership } => item.membership != null)
    ?? [];

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
          <small>{membership.rank_basis[1] ?? membership.caveat}</small>
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

        <details className="candidate-ranking-details">
          <summary>Dlaczego ta pozycja?</summary>
          <ul>{membership.rank_basis.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          {membership.factor_gaps.length > 0 && <p>Braki czynników: {membership.factor_gaps.join(" ")}</p>}
          <p>
            Źródło: {membership.source?.name ?? "brak"}
            {membership.source ? ` · zapis #${membership.source.document_version_id}` : ""}
            {membership.freshness ? ` · ${membership.freshness.status === "stale" ? "dane nieaktualne" : "źródło aktualne"}` : ""}.
          </p>
        </details>
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

      <section className="discover-filter-bar" aria-label="Wybierz sito inwestycyjne">
        <span className="discover-filter-label">Sito</span>
        {loading && !result ? <span className="skeleton discover-filter-skeleton" aria-hidden="true" /> : result?.sieves.map((sieve) => {
          const selected = sieve.id === selectedSieve?.id;
          const available = sieve.status === "available";
          return (
            <button
              className={`discover-filter ${selected ? "selected" : ""}`}
              type="button"
              key={sieve.id}
              onClick={() => setSelectedSieveId(sieve.id)}
              disabled={!available}
              aria-pressed={selected}
            >
              {available ? <IconCircleCheck size={14} /> : <IconLock size={14} />}
              <span>{sieve.title}</span>
              <small>{available ? `${sieve.candidate_count} kand.` : "brak danych"}</small>
            </button>
          );
        })}
      </section>

      {selectedSieve && (
        <section className="discover-sieve-summary" aria-label={`Szczegóły sita ${selectedSieve.title}`}>
          <div>
            <p className="section-label">Aktywne sito</p>
            <h2>{selectedSieve.title}</h2>
            <p>{selectedSieve.question}</p>
          </div>
          <div className="discover-sieve-metadata">
            <span className="badge neutral">Pokrycie {selectedSieve.coverage_count}/{selectedSieve.universe_count} · {selectedSieve.coverage_pct.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}%</span>
            <span className={`badge ${selectedSieve.freshness?.status === "stale" ? "warning" : "muted"}`}>
              {selectedSieve.freshness?.status === "stale" ? "Dane nieaktualne" : "Źródło sprawdzone"}
            </span>
            {selectedSieve.source && <small><IconDatabaseSearch size={13} /> {selectedSieve.source.name} · zapis #{selectedSieve.source.document_version_id} · dane {fmtDate(selectedSieve.source.as_of)}</small>}
          </div>
          {selectedSieve.selection_rules.length > 0 && (
            <div className="discover-sieve-rules">
              <span>Warunki wejścia</span>
              {selectedSieve.selection_rules.map((rule) => <span className="badge muted" key={rule.factor_id}>{rule.label} ≥ {fmtNumber(rule.threshold, rule.threshold % 1 === 0 ? 0 : 1)}</span>)}
            </div>
          )}
          {selectedSieve.gaps.length > 0 && (
            <details className="discover-sieve-gaps">
              <summary>Braki danych ({selectedSieve.gaps.length})</summary>
              <ul>{selectedSieve.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
            </details>
          )}
        </section>
      )}

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {researchReadWarning && <div className="error-box" role="status">{researchReadWarning}</div>}

      {result?.freshness.last_failed_refresh_at && new Date(result.freshness.last_failed_refresh_at) >= new Date(result.freshness.last_successful_source_check_at) && (
        <div className="error-box" role="status">
          Ostatnia nieudana próba odświeżenia ({fmtDate(result.freshness.last_failed_refresh_at)}): {result.freshness.last_failed_refresh_reason ?? "nieznany błąd"}. Wyświetlane są ostatnie poprawne dane.
        </div>
      )}

      {loading && <LoadingMessages messages={["Otwieram zapisane sita…", "Sprawdzam, które spółki są już w Research…"]} />}

      <section className="candidate-section" aria-labelledby="candidate-title">
        <div className="section-heading compact-heading">
          <div>
            <p className="section-label">Kandydaci</p>
            <h2 id="candidate-title">{selectedSieve?.title ?? "Brak dostępnego sita"}</h2>
          </div>
          <p>Kolejność jest lokalna dla wybranego sita. Wspólna obecność w kilku sitach nie tworzy globalnego rankingu.</p>
        </div>

        {loading ? (
          <SkeletonRows rows={6} height={82} />
        ) : !selectedSieve ? (
          <div className="empty-state">Żadne sito nie ma jeszcze wystarczającego pokrycia danych, aby pokazać kandydatów.</div>
        ) : !selectedCandidates.length ? (
          <div className="empty-state">Brak kandydatów dla tego sita. Status i braki danych pozostają widoczne powyżej.</div>
        ) : (
          <div className="candidate-list" aria-live="polite">
            {selectedCandidates.slice(0, visibleCount).map(({ candidate, membership }) => renderCandidate(candidate, membership))}
            {visibleCount < selectedCandidates.length && (
              <button className="btn candidate-more" type="button" onClick={() => setVisibleCount((current) => current + CANDIDATE_PAGE_SIZE)}>
                Pokaż kolejne · {selectedCandidates.length - visibleCount} pozostało
              </button>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
