"use client";

/** Research is the durable list of company cases, not a separate watchlist. */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  IconArrowRight,
  IconDatabaseOff,
  IconPlus,
} from "@tabler/icons-react";
import { addResearchCase, getResearchCases } from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { relativeDate } from "@/lib/format";
import type {
  ResearchCaseState,
  ResearchCaseStep,
  ResearchCaseSummary,
} from "@/lib/types";

const CASE_STATE_LABELS: Record<ResearchCaseState, string> = {
  new: "Nowy",
  ingesting: "Zbieranie danych",
  data_review: "Przegląd danych",
  business_model: "Model biznesowy",
  thesis: "Teza",
  scenarios: "Scenariusze",
  review: "Weryfikacja",
  monitoring: "Monitoring",
  blocked: "Zablokowany",
  closed: "Zamknięty",
};

const CASE_STEP_LABELS: Record<ResearchCaseStep, string> = {
  ingest: "zbieranie danych",
  data_review: "przegląd danych",
  business_model: "model biznesowy",
  thesis: "teza",
  scenarios: "scenariusze",
  review: "weryfikacja",
  monitoring: "monitoring",
};

function collectionStatus(status: string | null): { label: string; tone: string } {
  if (status === "queued") return { label: "Research zaplanowany", tone: "accent" };
  if (status === "running") return { label: "Research w toku", tone: "accent" };
  if (status === "completed") return { label: "Szkic Research gotowy", tone: "neutral" };
  if (status === "provisional") return { label: "Research prowizoryczny", tone: "neutral" };
  if (status === "verified") return { label: "Research zweryfikowany", tone: "success" };
  if (status === "needs-human") {
    return { label: "Wymaga przeglądu", tone: "warning" };
  }
  if (status === "failed" || status === "rejected") {
    return { label: "Research nieudany", tone: "danger" };
  }
  return { label: "Research jeszcze niezaplanowany", tone: "muted" };
}

export default function ResearchPage() {
  const [cases, setCases] = useState<ResearchCaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCases(await getResearchCases());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCases();
  }, [loadCases]);

  const addTicker = async (event: React.FormEvent) => {
    event.preventDefault();
    const ticker = newTicker.trim().toUpperCase();
    if (!ticker) return;

    setAdding(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await addResearchCase({ ticker });
      setNewTicker("");
      setSuccess(
        result.created_case
          ? `${ticker} dodano do Research. Zbieranie danych zostało zaplanowane.`
          : result.reactivated_case
            ? `${ticker} ponownie aktywowano w Research.`
          : `${ticker} jest już w Research. Pokazuję istniejący przypadek.`,
      );
      await loadCases();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const activeCount = cases.filter((item) => item.state !== "closed").length;
  const collectingCount = cases.filter((item) =>
    item.initial_research_status === "queued" || item.initial_research_status === "running"
  ).length;

  return (
    <main className="page-stack research-page">
      <section className="page-header research-header">
        <div>
          <p className="eyebrow">Research</p>
          <h1>Przypadki badawcze</h1>
          <p>Spółki, dla których zbierasz dowody, poznajesz biznes i budujesz własną tezę.</p>
        </div>
        <form className="command-row" onSubmit={addTicker}>
          <input
            value={newTicker}
            onChange={(event) => setNewTicker(event.target.value)}
            placeholder="Ticker, np. SNT"
            aria-label="Ticker spółki"
            className="ticker-input"
            maxLength={12}
          />
          <button className="btn accent" type="submit" disabled={adding}>
            <IconPlus size={14} /> {adding ? "Dodaję…" : "Dodaj do Research"}
          </button>
        </form>
      </section>

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}

      {loading ? (
        <>
          <SkeletonRows rows={4} height={72} />
          <LoadingMessages messages={["Otwieram przypadki badawcze…", "Sprawdzam stan zbierania danych…"]} />
        </>
      ) : cases.length === 0 ? (
        <section className="empty-research">
          <IconDatabaseOff size={24} />
          <h2>Brak przypadków badawczych</h2>
          <p>Dodaj znany ticker lub wybierz spółkę z jednego z sit w Discover.</p>
          <Link className="btn accent" href="/discover">
            Przejdź do Discover <IconArrowRight size={14} />
          </Link>
        </section>
      ) : (
        <>
          <section className="research-summary" aria-label="Podsumowanie Research">
            <span><strong>{activeCount}</strong> aktywnych przypadków</span>
            {collectingCount > 0 && <span><strong>{collectingCount}</strong> oczekuje lub jest w toku</span>}
          </section>

          <section className="research-case-list" aria-label="Przypadki badawcze">
            {cases.map((item) => {
              const job = collectionStatus(item.initial_research_status);
              return (
                <article className="research-case-row" key={item.id}>
                  <div className="research-case-company">
                    <span className="ticker-mark">{item.ticker}</span>
                    <div>
                      <strong>{item.name ?? "Nazwa do uzupełnienia"}</strong>
                      <small>Aktualizacja {relativeDate(item.updated_at)}</small>
                    </div>
                  </div>

                  <div className="research-case-state">
                    <span className={`badge ${item.state === "blocked" ? "warning" : "neutral"}`}>
                      {CASE_STATE_LABELS[item.state]}
                    </span>
                    <small>Etap: {CASE_STEP_LABELS[item.current_step]}</small>
                  </div>

                  <div className="research-case-job">
                    <span className={`badge ${job.tone}`}>{job.label}</span>
                    {item.blocked_reason && <small className="warn">{item.blocked_reason}</small>}
                  </div>

                  <Link className="btn research-case-open" href={`/stock/${item.ticker}`}>
                    Otwórz research <IconArrowRight size={14} />
                  </Link>
                </article>
              );
            })}
          </section>
        </>
      )}
    </main>
  );
}
