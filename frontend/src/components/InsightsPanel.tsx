import type { Insights, KeyIndicator } from "@/lib/types";

/** Verdict → Polish badge label + badge tone (tones defined in globals.scss). */
const VERDICTS: Record<KeyIndicator["verdict"], { label: string; tone: string }> = {
  good: { label: "plus", tone: "success" },
  neutral: { label: "neutralnie", tone: "neutral" },
  bad: { label: "minus", tone: "danger" },
  unknown: { label: "b/d", tone: "muted" },
};

/**
 * Dynamic (sector/size-aware) analysis from the backend `insights` block —
 * the entry point of the Przegląd tab, rendered above the static prescore.
 * All values arrive preformatted (pl-PL) from the backend; render as-is.
 */
export default function InsightsPanel({ insights }: { insights: Insights }) {
  // sort() is stable, so backend order is kept within each importance tier
  const indicators = [...insights.key_indicators].sort(
    (a, b) => b.importance - a.importance,
  );

  return (
    <div className="card insights">
      <div className="row" style={{ flexWrap: "wrap" }}>
        {insights.size_label && (
          <span className="badge accent">{insights.size_label}</span>
        )}
        <span className="badge neutral">{insights.sector_group_label}</span>
        {insights.sector && <span className="small muted">{insights.sector}</span>}
      </div>
      <p className="summary">{insights.summary}</p>

      {indicators.length > 0 && (
        <div className="insights-section">
          <p className="insights-title">Kluczowe wskaźniki dla tej spółki</p>
          <div className="indicator-grid">
            {indicators.map((ind) => (
              <div className="indicator" key={ind.id}>
                <div className="top">
                  <span className="name">{ind.name}</span>
                  {ind.importance === 3 && (
                    <span className="key-tag">kluczowy</span>
                  )}
                  <span className="value">{ind.value}</span>
                  <span className={`badge ${VERDICTS[ind.verdict].tone}`}>
                    {VERDICTS[ind.verdict].label}
                  </span>
                </div>
                {ind.comment && <p className="comment">{ind.comment}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {(insights.strengths.length > 0 || insights.concerns.length > 0) && (
        <div className="insights-section grid-2">
          {insights.strengths.length > 0 && (
            <div>
              <p className="insights-title">Mocne strony</p>
              <ul className="points good">
                {insights.strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {insights.concerns.length > 0 && (
            <div>
              <p className="insights-title">Ryzyka / minusy</p>
              <ul className="points bad">
                {insights.concerns.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {insights.missing.length > 0 && (
        <div className="insights-section">
          <p className="insights-title">Czego brakuje w danych</p>
          {insights.coverage && (
            <p className="small muted" style={{ margin: "0 0 6px" }}>
              {insights.coverage.note}
            </p>
          )}
          {insights.missing.map((item) => (
            <p className="missing-item" key={item.id}>
              <span className="name">{item.name}</span> — {item.why}
            </p>
          ))}
        </div>
      )}

      {insights.data_notes.length > 0 && (
        <div className="insights-section">
          {insights.data_notes.map((note) => (
            <p className="data-note" key={note}>
              {note}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
