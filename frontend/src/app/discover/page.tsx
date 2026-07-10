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
import { addToWatchlist, getDiscovery } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { DiscoveryResult } from "@/lib/types";

const PRESETS = [
  { id: "broad", label: "Szeroki radar", minRating: 5, minFScore: null },
  { id: "selective", label: "Selekcja jakościowa", minRating: 7, minFScore: 5 },
  { id: "strict", label: "Wysoka jakość", minRating: 8, minFScore: 7 },
] as const;

export default function DiscoverPage() {
  const router = useRouter();
  const [presetId, setPresetId] = useState<(typeof PRESETS)[number]["id"]>("broad");
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(15);

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

        <div className="candidate-list" aria-live="polite">
          {result?.candidates.slice(0, visibleCount).map((candidate) => (
            <article className="candidate-row" key={candidate.ticker}>
              <div className="candidate-company">
                <span className="ticker-mark">{candidate.ticker}</span>
                <strong>{candidate.name ?? "Nazwa do potwierdzenia"}</strong>
                <span>raport {candidate.report_period}</span>
              </div>
              <div className="candidate-reasons">
                <span className="candidate-label">Dlaczego na liście</span>
                <div>
                  {candidate.reasons.slice(0, 2).map((reason) => (
                    <span className="evidence-chip" key={reason}>
                      <IconShieldCheck size={13} /> {reason}
                    </span>
                  ))}
                </div>
              </div>
              <div className="candidate-caveat">
                <IconAlertTriangle size={15} />
                <span>{candidate.caveat}</span>
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
          ))}
        </div>
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
              Ocena Codex #{result.evaluation_job.id}: {result.evaluation_job.status}
              {result.evaluation_job.status === "queued"
                ? " — czeka na uruchomienie workera"
                : ""}
              . Szeroki snapshot zachował {result.evaluation_job.candidate_count}
              {" "}pomysłów; pierwsza partia oceny obejmuje maksymalnie{" "}
              {result.evaluation_job.evaluation_budget} spółek.
            </p>
          )}
        </div>
      )}
    </main>
  );
}
