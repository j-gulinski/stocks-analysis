"use client";

/** Deterministic, low-request entry into the research funnel. */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconDatabaseSearch,
  IconPlus,
  IconRefresh,
  IconShieldCheck,
} from "@tabler/icons-react";
import { addToWatchlist, getDiscovery, listAgentRuns } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import type { AgentRun, DiscoveryResult } from "@/lib/types";

const PRESETS = [
  { id: "broad", label: "Szeroki radar", minRating: 5, minFScore: null },
  { id: "selective", label: "Selekcja jakościowa", minRating: 7, minFScore: 5 },
  { id: "strict", label: "Wysoka jakość", minRating: 8, minFScore: 7 },
] as const;

type CandidateEvaluation = {
  score: number | null;
  status: string | null;
  nextStep: string | null;
};

function recordField(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function textField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function candidateEvaluations(run: AgentRun | null): Map<string, CandidateEvaluation> {
  const output = recordField(run?.outputs.output);
  const rows = Array.isArray(output?.candidates) ? output.candidates : [];
  const result = new Map<string, CandidateEvaluation>();
  rows.forEach((value) => {
    const row = recordField(value);
    const ticker = textField(row?.ticker);
    if (!ticker) return;
    result.set(ticker, {
      score: typeof row?.score === "number" && Number.isFinite(row.score) ? row.score : null,
      status: textField(row?.status),
      nextStep: textField(row?.recommended_next_step),
    });
  });
  return result;
}

function evaluationStatusLabel(status: string | null): string {
  if (status?.includes("ready-for-bounded-review")) return "gotowa do przeglądu dossier";
  if (status?.includes("secondary")) return "druga partia odświeżenia";
  if (status?.includes("refresh-candidate")) return "kandydat do kontrolowanego odświeżenia";
  return "prescreen źródłowy";
}

function runStatusLabel(status: string): string {
  if (status === "completed" || status === "verified") return "zakończona";
  if (status === "running") return "w toku";
  if (status === "queued") return "w kolejce";
  if (status === "needs-human") return "wymaga decyzji";
  if (status === "failed" || status === "rejected") return "odrzucona";
  return status;
}

export default function DiscoverPage() {
  const router = useRouter();
  const [presetId, setPresetId] = useState<(typeof PRESETS)[number]["id"]>("broad");
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(15);
  const [evaluationRun, setEvaluationRun] = useState<AgentRun | null>(null);

  const load = async (force = false, nextPreset = presetId) => {
    const preset = PRESETS.find((item) => item.id === nextPreset) ?? PRESETS[0];
    setLoading(true);
    setError(null);
    try {
      setResult(await getDiscovery(preset.minRating, preset.minFScore, force));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(false, "broad");
    // Initial source load only. Preset changes are explicit button actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const evaluationJobId = result?.evaluation_job?.id ?? null;
  useEffect(() => {
    if (evaluationJobId == null) {
      setEvaluationRun(null);
      return;
    }
    let cancelled = false;
    const pollEvaluation = async () => {
      const rows = await listAgentRuns({ workflow: "stock-candidate-scout", limit: 8 });
      if (!cancelled) setEvaluationRun(rows.find((run) => run.id === evaluationJobId) ?? null);
    };
    pollEvaluation().catch(() => undefined);
    const pollId = window.setInterval(() => pollEvaluation().catch(() => undefined), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(pollId);
    };
  }, [evaluationJobId]);

  const choosePreset = (next: (typeof PRESETS)[number]["id"]) => {
    setPresetId(next);
    setVisibleCount(15);
    void load(false, next);
  };

  const startResearch = async (ticker: string) => {
    setStarting(ticker);
    setError(null);
    try {
      await addToWatchlist(ticker);
    } catch (err) {
      // A candidate already in Research should still open normally.
      if (!(err instanceof Error) || !err.message.includes("already")) {
        setError(err instanceof Error ? err.message : String(err));
        setStarting(null);
        return;
      }
    }
    router.push(`/stock/${ticker}`);
  };

  const evaluated = candidateEvaluations(evaluationRun);
  const evaluationOutput = recordField(evaluationRun?.outputs.output);
  const evaluationSummary = recordField(evaluationOutput?.summary);
  const evaluatedCount = typeof evaluationSummary?.evaluated_count === "number"
    ? evaluationSummary.evaluated_count
    : evaluated.size;
  const boundedBatch = Array.isArray(evaluationSummary?.bounded_refresh_batch)
    ? evaluationSummary.bounded_refresh_batch.filter((item): item is string => typeof item === "string")
    : [];

  return (
    <main className="page-stack discover-page">
      <section className="page-header discovery-header">
        <div>
          <p className="eyebrow">Początek procesu</p>
          <h1>Pomysły do analizy</h1>
          <p>
            Przesiej rynek GPW jednym odczytem BiznesRadar. To lista kandydatów do
            sprawdzenia, nie ranking inwestycyjny ani rekomendacja.
          </p>
        </div>
        <button className="btn" onClick={() => void load(true)} disabled={loading}>
          <IconRefresh size={15} className={loading ? "spin" : ""} /> Odśwież źródło
        </button>
      </section>

      <section className="discovery-source-strip" aria-label="Stan źródła">
        <div>
          <IconDatabaseSearch size={17} />
          <span>
            {result
              ? `${result.universe_count} spółek w źródle · stan na ${fmtDate(result.as_of)}`
              : "Ładowanie rynku GPW"}
          </span>
        </div>
        <span className="badge neutral">1 strona źródłowa · cache 24 h</span>
      </section>

      <section className="workflow-guide discovery-guide" aria-label="Typowa ścieżka odkrywania">
        <div className="workflow-guide-copy">
          <p className="eyebrow">Typowa ścieżka</p>
          <h2>Najpierw wybierz kandydatów, potem odśwież tylko wybrane dossier</h2>
          <p>Ranking jest źródłowym prescreenem. Kliknięcie „Rozpocznij analizę” jest jedyną akcją, która dodaje spółkę do Research.</p>
        </div>
        <ol className="workflow-guide-steps">
          <li className="active"><span>1</span><strong>Przesiej</strong><small>rating + F-Score</small></li>
          <li><span>2</span><strong>Sprawdź powód</strong><small>źródła i zastrzeżenia</small></li>
          <li><span>3</span><strong>Rozpocznij</strong><small>jawne dossier</small></li>
          <li><span>4</span><strong>Zweryfikuj</strong><small>raport Codex</small></li>
        </ol>
      </section>

      <section className="screening-controls" aria-label="Wybór sita">
        <div>
          <h2>Wybierz szerokość sita</h2>
          <p>
            Domyślny radar stawia na kompletność: brak F-Score pozostaje jawną
            luką, ale nie usuwa pomysłu przed oceną Codex.
          </p>
        </div>
        <div className="preset-row">
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              className={`preset-button ${presetId === preset.id ? "active" : ""}`}
              onClick={() => choosePreset(preset.id)}
              aria-pressed={presetId === preset.id}
            >
              <strong>{preset.label}</strong>
              <span>
                Rating ≥ {preset.minRating} · {preset.minFScore == null
                  ? "bez minimum F-Score"
                  : `F-Score ≥ ${preset.minFScore}`}
              </span>
            </button>
          ))}
        </div>
      </section>

      {error && <div className="error-box">{error}</div>}

      <section className="candidate-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Kandydaci</p>
            <h2>{loading ? "Aktualizuję listę…" : `${result?.result_count ?? 0} wyników`}</h2>
          </div>
          <p>Sortowanie: rating źródłowy, następnie Piotroski F-Score.</p>
        </div>

        {evaluationRun && evaluationRun.status !== "queued" && (
          <div className="candidate-evaluation-summary">
            <span className={`badge ${evaluationRun.status === "completed" ? "success" : "accent"}`}>
              Ocena Codex #{evaluationRun.id}: {runStatusLabel(evaluationRun.status)}
            </span>
            <span>{evaluatedCount} ocenionych na podstawie źródła</span>
            {boundedBatch.length > 0 && <span>Następna partia: {boundedBatch.join(", ")}</span>}
          </div>
        )}

        {loading ? (
          <><SkeletonRows rows={5} height={96} /><LoadingMessages messages={["Ładuję ranking źródłowy…", "Sprawdzam powody wysokiej pozycji…"]} /></>
        ) : (
        <div className="candidate-list" aria-live="polite">
          {result?.candidates.slice(0, visibleCount).map((candidate) => {
            const evaluation = evaluated.get(candidate.ticker);
            return (
            <article className="candidate-row" key={candidate.ticker}>
              <div className="candidate-company">
                <span className="ticker-mark">{candidate.ticker}</span>
                <strong>{candidate.name ?? "Nazwa do potwierdzenia"}</strong>
                <span>raport {candidate.report_period}</span>
                {evaluation && (
                  <span className="candidate-codex-score">
                    ocena źródeł Codex {evaluation.score == null ? "b/d" : `${Math.round(evaluation.score)}/100`}
                  </span>
                )}
              </div>
              <div className="candidate-reasons">
                <span className="candidate-label">Dlaczego wysoko · #{candidate.rank}</span>
                <div>
                  {candidate.reasons.slice(0, 2).map((reason) => (
                    <span className="evidence-chip" key={reason}>
                      <IconShieldCheck size={13} /> {reason}
                    </span>
                  ))}
                </div>
                <details className="candidate-rank-details">
                  <summary>Pełne uzasadnienie rankingu</summary>
                  <ul>
                    {candidate.rank_basis.map((reason) => <li key={reason}>{reason}</li>)}
                  </ul>
                </details>
              </div>
              <div className="candidate-caveat">
                <IconAlertTriangle size={15} />
                <span>
                  {evaluation
                    ? evaluationStatusLabel(evaluation.status)
                    : candidate.caveat}
                </span>
              </div>
              <div className="candidate-actions">
                <button className="btn accent" onClick={() => void startResearch(candidate.ticker)} disabled={starting === candidate.ticker}>
                  {starting === candidate.ticker ? (
                    "Tworzę analizę…"
                  ) : (
                    <><IconPlus size={14} /> Rozpocznij analizę</>
                  )}
                </button>
                <button className="btn icon" title="Otwórz istniejące dossier" aria-label={`Otwórz ${candidate.ticker}`} onClick={() => router.push(`/stock/${candidate.ticker}`)}>
                  <IconArrowRight size={16} />
                </button>
              </div>
            </article>
            );
          })}
        </div>
        )}
        {result && visibleCount < result.candidates.length && (
          <button className="btn show-more-candidates" onClick={() => setVisibleCount((count) => count + 15)}>
            Pokaż kolejne ({result.candidates.length - visibleCount})
          </button>
        )}
      </section>

      {result && (
        <div className="discovery-note">
          <p>{result.source_note}</p>
          {result.evaluation_job && (
            <p>
              Ocena Codex #{result.evaluation_job.id}: {runStatusLabel(evaluationRun?.status ?? result.evaluation_job.status)}
              {(evaluationRun?.status ?? result.evaluation_job.status) === "queued"
                ? " — czeka na uruchomienie workera"
                : ""}
              . Szeroki snapshot zachował {result.evaluation_job.candidate_count}
              {" "}pomysłów; pierwsza partia oceny obejmuje maksymalnie{" "}
              {result.evaluation_job.evaluation_budget} spółek.
            </p>
          )}
          {result.scheduled_analysis && (
            <p>
              Po odświeżeniu źródła: zaplanowano {result.scheduled_analysis.queued} z {result.scheduled_analysis.considered}
              {" "}najwyżej sklasyfikowanych analiz. Pominięto: {result.scheduled_analysis.skipped_recent} świeżych,
              {" "}{result.scheduled_analysis.skipped_pending} już oczekujących i
              {" "}{result.scheduled_analysis.skipped_not_stored} bez dossier w bazie.
              Analiza jest uznawana za starą po {result.scheduled_analysis.stale_after_days} dniach.
              {result.scheduled_analysis.tickers.length > 0 && (
                <> Zaplanowane tickery: {result.scheduled_analysis.tickers.join(", ")}.</>
              )}
            </p>
          )}
        </div>
      )}
    </main>
  );
}
