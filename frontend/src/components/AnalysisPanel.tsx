"use client";

/** Analiza AI tab (Phase 5, P5.7): run a Claude verdict against the dossier +
 * recent forum posts (backend P5.6 endpoints), show the latest verdict, and
 * keep a run history with a lightweight diff vs the previous run. Mirrors
 * ForecastPanel's shape (typed client call → loading/error state → result
 * card) and reuses ThesisPanel's card conventions (verdict headline,
 * `.points`, `.verify-item`, `.disclaimer`) under a new `.analysis` scope. */
import { useEffect, useState } from "react";
import { IconCheck, IconHelp, IconSparkles, IconX } from "@tabler/icons-react";
import { ApiError, listAnalyses, runAnalysis } from "@/lib/api";
import { fmtDate, relativeDate } from "@/lib/format";
import type {
  Analysis,
  AnalysisCatalyst,
  AnalysisChecklistItem,
  Dossier,
  ForumInsight,
} from "@/lib/types";

// Same icon-per-verdict convention as PrescoreChecklist — icon + colour so
// the verdict never relies on colour alone.
const CHECK_ICONS = {
  "spełnia": <IconCheck size={15} className="pos" />,
  "nie spełnia": <IconX size={15} className="neg" />,
  "nieznane": <IconHelp size={15} className="warn" />,
} as const;

// "nie" (not yet priced in) reads as open upside → success; "tak" (already
// priced in) is the least exciting state → muted, not danger (this is not a
// pass/fail signal, just a framing cue).
const PRICED_IN_TONE: Record<AnalysisCatalyst["priced_in"], string> = {
  nie: "success",
  "częściowo": "warning",
  tak: "muted",
  nieznane: "muted",
};

const CONFIDENCE_TONE: Record<ForumInsight["confidence"], string> = {
  high: "success",
  medium: "warning",
  low: "muted",
};

function scoreTone(score: number | null): string {
  if (score == null) return "muted";
  if (score >= 70) return "success";
  if (score >= 40) return "warning";
  return "danger";
}

/** Per-item checklist verdict changes between two runs, matched by the item
 * text (the backend doesn't emit stable item ids). Kept deliberately simple —
 * a name match miss just means no diff line, not a crash. */
function checklistChanges(
  current: AnalysisChecklistItem[],
  previous: AnalysisChecklistItem[],
): { item: string; from: string; to: string }[] {
  const prevByItem = new Map(previous.map((c) => [c.item, c.verdict]));
  const changes: { item: string; from: string; to: string }[] = [];
  for (const c of current) {
    const prevVerdict = prevByItem.get(c.item);
    if (prevVerdict != null && prevVerdict !== c.verdict) {
      changes.push({ item: c.item, from: prevVerdict, to: c.verdict });
    }
  }
  return changes;
}

export default function AnalysisPanel({
  ticker,
}: {
  ticker: string;
  // Accepted for call-site parity with the other tab panels (ForecastPanel
  // etc., which all get the loaded dossier) — the backend re-derives its own
  // dossier server-side for the analysis run, so this component doesn't need
  // to read it today. Kept typed rather than `unknown` so it starts useful
  // the moment a caller wants to show dossier-derived context here.
  dossier: Dossier;
}) {
  const [history, setHistory] = useState<Analysis[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listAnalyses(ticker)
      .then((rows) => {
        if (cancelled) return;
        setHistory(rows);
        setSelectedId(rows[0]?.id ?? null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await runAnalysis(ticker);
      setHistory((current) => [result, ...(current ?? [])]);
      setSelectedId(result.id);
    } catch (err) {
      // 429 (daily cap) / 503 (no API key) both arrive as ApiError with a
      // ready-made Polish `detail` — show it as-is, not as a crash.
      setError(
        err instanceof ApiError || err instanceof Error ? err.message : String(err),
      );
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <p className="empty-state">Ładowanie historii analiz…</p>;

  const rows = history ?? [];
  const selectedIndex = rows.findIndex((r) => r.id === selectedId);
  const selected = selectedIndex >= 0 ? rows[selectedIndex] : null;
  const previous = selectedIndex >= 0 ? rows[selectedIndex + 1] : undefined;
  const verdict = selected?.output;

  const scoreDelta =
    selected?.alignment_score != null && previous?.alignment_score != null
      ? selected.alignment_score - previous.alignment_score
      : null;
  const changes =
    verdict && previous ? checklistChanges(verdict.checklist, previous.output.checklist) : [];

  return (
    <div>
      <div className="row" style={{ marginBottom: 14 }}>
        <button className="btn accent" onClick={handleRun} disabled={running}>
          <IconSparkles size={14} className={running ? "spin" : ""} /> Analizuj
        </button>
        {rows.length > 0 && (
          <span className="small muted">
            {rows.length} {rows.length === 1 ? "analiza" : "analiz"} w historii
          </span>
        )}
      </div>

      {error && <div className="error-box">{error}</div>}

      {!selected && !error && (
        <p className="empty-state">Brak analiz — uruchom pierwszą.</p>
      )}

      {selected && verdict && (
        <div className="card analysis">
          <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <div className={`score ${scoreTone(selected.alignment_score)}`}>
              <span className="score-value">
                {selected.alignment_score != null ? selected.alignment_score : "brak"}
              </span>
              <span className="score-label">zgodność ze strategią</span>
            </div>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              <span className="badge muted">model: {selected.model}</span>
              <span className="badge muted">{fmtDate(selected.created_at)}</span>
              {scoreDelta != null && (
                <span
                  className={`badge ${scoreDelta > 0 ? "success" : scoreDelta < 0 ? "danger" : "neutral"}`}
                >
                  {scoreDelta > 0 ? `+${scoreDelta}` : scoreDelta} vs poprzednia
                </span>
              )}
            </div>
          </div>

          <p style={{ marginTop: 12, fontWeight: 500, lineHeight: 1.5 }}>{verdict.thesis}</p>

          {changes.length > 0 && (
            <div className="analysis-section">
              <p className="analysis-title">Zmiany checklisty vs poprzednia analiza</p>
              {changes.map((c) => (
                <p className="verify-item" key={c.item}>
                  {c.item}: {c.from} → {c.to}
                </p>
              ))}
            </div>
          )}

          {verdict.catalysts.length > 0 && (
            <div className="analysis-section">
              <p className="analysis-title">Katalizatory</p>
              {verdict.catalysts.map((cat, i) => (
                <div className="catalyst-row" key={i}>
                  <span className="type">{cat.type}</span>
                  <span className="desc">{cat.description}</span>
                  <span className="small muted">{cat.horizon}</span>
                  <span className={`badge ${PRICED_IN_TONE[cat.priced_in] ?? "muted"}`}>
                    w cenie: {cat.priced_in}
                  </span>
                </div>
              ))}
            </div>
          )}

          {verdict.checklist.length > 0 && (
            <div className="analysis-section">
              <p className="analysis-title">Checklista strategii</p>
              <div className="checklist">
                {verdict.checklist.map((c, i) => (
                  <div className="check" key={i}>
                    {CHECK_ICONS[c.verdict] ?? <IconHelp size={15} className="warn" />}
                    <span>
                      {c.item} <span className="evidence">{c.evidence}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {verdict.red_flags.length > 0 && (
            <div className="analysis-section">
              <p className="analysis-title">Czerwone flagi</p>
              <ul className="points bad">
                {verdict.red_flags.map((flag, i) => (
                  <li key={i}>{flag}</li>
                ))}
              </ul>
            </div>
          )}

          {verdict.one_off_risk && (
            <div className="analysis-section">
              <p className="analysis-title">Ryzyko zdarzeń jednorazowych</p>
              <p className="secondary" style={{ lineHeight: 1.5 }}>{verdict.one_off_risk}</p>
            </div>
          )}

          <div className="analysis-section">
            <p className="analysis-title">Potencjał</p>
            <div className="grid-2">
              <p className="secondary" style={{ lineHeight: 1.5 }}>
                <span className="muted">wzrost: </span>
                {verdict.potential.upside}
              </p>
              <p className="secondary" style={{ lineHeight: 1.5 }}>
                <span className="muted">spadek: </span>
                {verdict.potential.downside}
              </p>
            </div>
          </div>

          {verdict.forum_insights.length > 0 && (
            <div className="analysis-section">
              <p className="analysis-title">
                Wnioski z forum <span className="small muted">(opinie, nie fakty)</span>
              </p>
              {verdict.forum_insights.map((f, i) => (
                <p className="verify-item" key={i}>
                  {f.claim}{" "}
                  <span className={`badge ${CONFIDENCE_TONE[f.confidence] ?? "muted"}`}>
                    {f.confidence}
                  </span>
                  {f.post_ids.length > 0 && (
                    <span className="why"> · posty: {f.post_ids.join(", ")}</span>
                  )}
                </p>
              ))}
            </div>
          )}

          {verdict.verify_next.length > 0 && (
            <div className="analysis-section">
              <p className="analysis-title">Co sprawdzić dalej</p>
              {verdict.verify_next.map((v) => (
                <p className="verify-item" key={v.id}>
                  {v.text}
                  {v.why && (
                    <>
                      {" — "}
                      <span className="why">{v.why}</span>
                    </>
                  )}
                </p>
              ))}
            </div>
          )}

          <div className="analysis-section">
            <p className="secondary" style={{ lineHeight: 1.55, margin: 0 }}>
              {verdict.summary_pl}
            </p>
          </div>

          <p className="disclaimer">Analiza, nie rekomendacja inwestycyjna.</p>
        </div>
      )}

      {rows.length > 0 && (
        <>
          <p className="section-label">Historia analiz</p>
          <table className="table">
            <thead>
              <tr>
                <th>Data</th>
                <th>Model</th>
                <th>Wynik</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="clickable"
                  onClick={() => setSelectedId(r.id)}
                  style={
                    r.id === selectedId ? { background: "var(--surface-1)" } : undefined
                  }
                >
                  <td className="secondary">{relativeDate(r.created_at)}</td>
                  <td>{r.model}</td>
                  <td>
                    <span className={`badge ${scoreTone(r.alignment_score)}`}>
                      {r.alignment_score ?? "brak"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
