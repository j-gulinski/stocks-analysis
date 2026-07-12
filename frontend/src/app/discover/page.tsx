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
import type { DiscoveryCandidate, DiscoveryResult, ResearchCaseSummary } from "@/lib/types";

const CANDIDATE_PAGE_SIZE = 12;

function financialFactors(candidate: DiscoveryCandidate) {
  return [
    {
      label: "Altman EM-Score",
      value: fmtNumber(candidate.br_rating_value, 1),
      note: `ryzyko problemów finansowych${candidate.br_rating ? ` · klasa ${candidate.br_rating}` : ""}`,
    },
    {
      label: "Piotroski F-Score",
      value: candidate.piotroski_f_score == null ? "brak" : `${candidate.piotroski_f_score}/9`,
      note: "zmiany rentowności, płynności i efektywności",
    },
  ];
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

  const activeSieve = result?.sieves.find(
    (sieve) => sieve.id === "financial_health_br_v1" && sieve.status === "available",
  ) ?? null;

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
            {sieve.source && <small>{sieve.source.name} · dane {fmtDate(sieve.source.as_of)}</small>}
          </article>
        ); })}
      </section>

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {researchReadWarning && <div className="error-box" role="status">{researchReadWarning}</div>}

      {result && activeSieve && (
        <section className="discovery-source-strip" aria-label="Stan aktywnego sita">
          <div>
            <IconDatabaseSearch size={17} />
            <span>
              {activeSieve.title} · {activeSieve.candidate_count} kandydatów · {activeSieve.source?.name ?? result.source} · zapis #{activeSieve.source?.document_version_id ?? result.source_version_id} · dane {fmtDate(activeSieve.source?.as_of ?? result.as_of)}
            </span>
          </div>
          <div>
            <span className={`badge ${result.freshness.status === "stale" ? "warning" : "neutral"}`}>
              {result.freshness.status === "stale" ? "Dane nieaktualne" : "Źródło sprawdzone"}
            </span>
            <small> treść: {fmtDate(result.freshness.content_version_at)} · sprawdzono: {fmtDate(result.freshness.last_successful_source_check_at)}</small>
          </div>
        </section>
      )}

      {result?.freshness.last_failed_refresh_at && new Date(result.freshness.last_failed_refresh_at) >= new Date(result.freshness.last_successful_source_check_at) && (
        <div className="error-box" role="status">
          Ostatnia nieudana próba odświeżenia ({fmtDate(result.freshness.last_failed_refresh_at)}): {result.freshness.last_failed_refresh_reason ?? "nieznany błąd"}. Wyświetlane są ostatnie poprawne dane.
        </div>
      )}

      <section className="candidate-section" aria-labelledby="candidate-title">
        <div className="section-heading compact-heading">
          <div>
            <p className="section-label">Aktywne sito</p>
            <h2 id="candidate-title">{activeSieve?.title ?? "Brak aktywnego sita"}</h2>
          </div>
          <p>To wstępna lista do dalszego poznania spółki, nie ocena inwestycyjna.</p>
        </div>

        <p className="discovery-method-note">
          Altman EM-Score szacuje kondycję finansową i ryzyko problemów; klasa AAA oznacza mocną klasyfikację w tym modelu. Piotroski F-Score to dziewięć testów zmian rentowności, płynności i efektywności. Żaden z nich nie jest werdyktem inwestycyjnym.
        </p>

        {loading ? (
          <>
            <SkeletonRows rows={6} height={82} />
            <LoadingMessages messages={["Otwieram zapisaną listę kandydatów…", "Sprawdzam, które spółki są już w Research…"]} />
          </>
        ) : !activeSieve ? (
          <div className="empty-state">
            Żadne sito nie ma jeszcze wystarczającego pokrycia danych, aby pokazać kandydatów.
          </div>
        ) : !result?.candidates.length ? (
          <div className="empty-state">
            Brak zapisanej listy kandydatów. Użyj „Odśwież źródło”, aby pobrać aktualny zapis źródłowy.
          </div>
        ) : (
          <div className="candidate-list" aria-live="polite">
            {result.candidates.slice(0, visibleCount).map((candidate) => {
              const added = addedTickers.has(candidate.ticker);
              const closed = closedTickers.has(candidate.ticker);
              const adding = addingTickers.has(candidate.ticker);
              return (
                <article className="candidate-row" key={candidate.ticker}>
                  <div className="candidate-company">
                    <span className="ticker-mark">{candidate.ticker}</span>
                    <div>
                      <strong>{candidate.name ?? "Nazwa do uzupełnienia"}</strong>
                      <small>Raport {candidate.report_period}</small>
                      <small>{candidate.neutral_context.map((item) => `${item.label}: ${item.value ?? "brak"}`).join(" · ")}</small>
                      <small>Do sprawdzenia: {candidate.strategy_questions[0]}</small>
                      {candidate.factor_status === "stale" && <small className="warning">{candidate.caveat}</small>}
                    </div>
                  </div>

                  <div className="candidate-factor-list" aria-label={`Czynniki ${candidate.ticker}`}>
                    {financialFactors(candidate).map((factor) => (
                      <div className="candidate-factor" key={factor.label}>
                        <span>{factor.label}</span>
                        <strong>{factor.value}</strong>
                        <small>{factor.note}</small>
                      </div>
                    ))}
                  </div>

                  <div className="candidate-source-meta">
                    <span className="badge muted">{candidate.rank == null ? "Ranking nieaktualny" : `#${candidate.rank} w tym sicie`}</span>
                  </div>

                  <button
                    className={`btn ${added ? "" : "accent"}`}
                    type="button"
                    onClick={() => void addCandidate(candidate.ticker)}
                    disabled={added || adding}
                    aria-label={
                      added
                        ? `${candidate.ticker} jest w Research`
                        : closed
                          ? `Wznów ${candidate.ticker} w Research`
                          : `Dodaj ${candidate.ticker} do Research`
                    }
                  >
                    {added ? <IconCircleCheck size={14} /> : <IconPlus size={14} />}
                    {added ? "Dodano" : adding ? "Dodaję…" : closed ? "Wznów Research" : "Dodaj do Research"}
                  </button>
                </article>
              );
            })}
            {visibleCount < result.candidates.length && (
              <button
                className="btn candidate-more"
                type="button"
                onClick={() => setVisibleCount((current) => current + CANDIDATE_PAGE_SIZE)}
              >
                Pokaż kolejne · {result.candidates.length - visibleCount} pozostało
              </button>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
