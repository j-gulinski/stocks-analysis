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
import type { DiscoveryCandidate, DiscoveryResult } from "@/lib/types";

const FINANCIAL_CONDITION_MIN_SCORE = 8;
const PIOTROSKI_MIN_SCORE = 7;
const CANDIDATE_PAGE_SIZE = 12;

const SIEVES = [
  {
    id: "financial-condition",
    title: "Kondycja finansowa",
    description: "Wstępna selekcja według odporności finansowej oraz dziewięciu testów rentowności, płynności i efektywności.",
    factors: "Odporność bilansu · rentowność · płynność · efektywność",
    available: true,
  },
  {
    id: "obs-growth",
    title: "Wzrost wyników · OBS",
    description: "Ma szukać poprawy wyników, jakości zysku i katalizatora przy rozsądnej wycenie względem historii spółki.",
    factors: "Wymaga normalizacji wyników, marż, prognoz i katalizatorów",
    available: false,
  },
  {
    id: "portal-opportunities",
    title: "Jakość i asymetria · Portal Analiz",
    description: "Ma łączyć jakość bilansu i przepływów z wyceną oraz policzalnym scenariuszem zdarzeń.",
    factors: "Wymaga pełniejszych danych o gotówce, przepływach, wycenie i zdarzeniach",
    available: false,
  },
] as const;

function financialFactors(candidate: DiscoveryCandidate) {
  return [
    {
      label: "Odporność finansowa",
      value: fmtNumber(candidate.br_rating_value, 1),
      note: `model Altmana${candidate.br_rating ? ` · klasa ${candidate.br_rating}` : ""}`,
    },
    {
      label: "Jakość zmian w wynikach",
      value: candidate.piotroski_f_score == null ? "brak" : `${candidate.piotroski_f_score}/9`,
      note: "pozytywne sygnały Piotroskiego",
    },
  ];
}

export default function DiscoverPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [addedTickers, setAddedTickers] = useState<Set<string>>(new Set());
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [visibleCount, setVisibleCount] = useState(CANDIDATE_PAGE_SIZE);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [discovery, cases] = await Promise.all([
        getDiscovery(FINANCIAL_CONDITION_MIN_SCORE, PIOTROSKI_MIN_SCORE),
        getResearchCases(),
      ]);
      setResult(discovery);
      setAddedTickers(new Set(cases.map((item) => item.ticker)));
      setVisibleCount(CANDIDATE_PAGE_SIZE);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    setSuccess(null);
    try {
      const refreshed = await refreshDiscovery(
        FINANCIAL_CONDITION_MIN_SCORE,
        PIOTROSKI_MIN_SCORE,
      );
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
        {SIEVES.map((sieve) => (
          <article className={`sieve-card ${sieve.available ? "available" : "unavailable"}`} key={sieve.id}>
            <header>
              <h2>{sieve.title}</h2>
              <span className={`badge ${sieve.available ? "success" : "muted"}`}>
                {sieve.available ? <IconCircleCheck size={13} /> : <IconLock size={13} />}
                {sieve.available ? "Dostępne" : "Jeszcze niedostępne"}
              </span>
            </header>
            <p>{sieve.description}</p>
            <small>{sieve.factors}</small>
          </article>
        ))}
      </section>

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}

      {result && (
        <section className="discovery-source-strip" aria-label="Stan aktywnego sita">
          <div>
            <IconDatabaseSearch size={17} />
            <span>
              Kondycja finansowa · {result.result_count} kandydatów · dane {fmtDate(result.as_of)}
            </span>
          </div>
          <span className="badge neutral">BiznesRadar · raporty spółek</span>
        </section>
      )}

      <section className="candidate-section" aria-labelledby="candidate-title">
        <div className="section-heading compact-heading">
          <div>
            <p className="section-label">Aktywne sito</p>
            <h2 id="candidate-title">Kondycja finansowa</h2>
          </div>
          <p>To wstępna lista do dalszego poznania spółki, nie ocena inwestycyjna.</p>
        </div>

        {loading ? (
          <>
            <SkeletonRows rows={6} height={82} />
            <LoadingMessages messages={["Otwieram zapisaną listę kandydatów…", "Sprawdzam, które spółki są już w Research…"]} />
          </>
        ) : !result?.candidates.length ? (
          <div className="empty-state">
            Brak zapisanej listy kandydatów. Użyj „Odśwież źródło”, aby pobrać aktualny zapis źródłowy.
          </div>
        ) : (
          <div className="candidate-list" aria-live="polite">
            {result.candidates.slice(0, visibleCount).map((candidate) => {
              const added = addedTickers.has(candidate.ticker);
              const adding = addingTickers.has(candidate.ticker);
              return (
                <article className="candidate-row" key={candidate.ticker}>
                  <div className="candidate-company">
                    <span className="ticker-mark">{candidate.ticker}</span>
                    <div>
                      <strong>{candidate.name ?? "Nazwa do uzupełnienia"}</strong>
                      <small>Raport {candidate.report_period}</small>
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
                    <span className="badge muted">#{candidate.rank} w tym sicie</span>
                  </div>

                  <button
                    className={`btn ${added ? "" : "accent"}`}
                    type="button"
                    onClick={() => void addCandidate(candidate.ticker)}
                    disabled={added || adding}
                    aria-label={
                      added
                        ? `${candidate.ticker} jest w Research`
                        : `Dodaj ${candidate.ticker} do Research`
                    }
                  >
                    {added ? <IconCircleCheck size={14} /> : <IconPlus size={14} />}
                    {added ? "Dodano" : adding ? "Dodaję…" : "Dodaj do Research"}
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
