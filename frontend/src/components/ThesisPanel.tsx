import type { ComponentType } from "react";
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleDot,
  IconHelpCircle,
} from "@tabler/icons-react";
import type { Thesis } from "@/lib/types";

// Minimal shape we use from a Tabler icon — avoids coupling to the library's
// exact exported type name across versions.
type IconComponent = ComponentType<{ size?: number; stroke?: number }>;

/**
 * Entry-quality code → verdict tone + icon (tones live in globals.scss). The
 * Polish LABELS come from the backend (`thesis.entry_quality.label`); here we
 * only pick the colour + icon. The icon is a non-colour cue so the verdict never
 * relies on colour alone. `weak` is amber (a caution), not red: the app reserves
 * red for hard "minus" indicators and this layer emits no buy/sell signal (plan
 * Non-goals).
 */
const ENTRY_QUALITY: Record<
  Thesis["entry_quality"]["code"],
  { tone: string; Icon: IconComponent }
> = {
  attractive: { tone: "success", Icon: IconCircleCheck },
  neutral: { tone: "neutral", Icon: IconCircleDot },
  weak: { tone: "warning", Icon: IconAlertTriangle },
  insufficient_data: { tone: "muted", Icon: IconHelpCircle },
};

/**
 * Investment-thesis synthesis ("Teza inwestycyjna") — the top card of the
 * Przegląd tab, above InsightsPanel (its per-indicator evidence). The read is
 * composed rule-based by the backend (services/thesis.py); this component only
 * lays it out. Every value arrives preformatted from the backend — render
 * as-is, no client-side number formatting (same rule as InsightsPanel).
 */
export default function ThesisPanel({ thesis }: { thesis?: Thesis }) {
  // Older cached dossiers predate the thesis layer. Render nothing rather than
  // crash — the caller also guards the section label so there is no orphan.
  if (!thesis) return null;

  const eq = ENTRY_QUALITY[thesis.entry_quality.code] ?? {
    tone: "muted",
    Icon: IconHelpCircle,
  };
  const VerdictIcon = eq.Icon;
  // WP2b provenance: the deterministic engine (default / no-key fallback) vs the
  // optional model-assisted refiner. Degraded states are identical for both.
  const engineLabel = thesis.engine === "ai" ? "AI" : "deterministyczny";

  return (
    <div className="card thesis">
      {/* Headline verdict (icon + large label) on the left — the primary output;
          strategy + engine provenance demoted to muted chips on the right. */}
      <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
        <div className={`verdict ${eq.tone}`}>
          <span className="verdict-icon">
            <VerdictIcon size={20} stroke={1.8} />
          </span>
          <span className="verdict-label">{thesis.entry_quality.label}</span>
        </div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          <span className="badge muted">wg strategii: {thesis.strategy.label}</span>
          <span className="badge muted">silnik: {engineLabel}</span>
        </div>
      </div>

      {/* Always present from the backend; for `insufficient_data` this is the
          clear Polish "why" so the card is never blank. */}
      {thesis.entry_quality.rationale && (
        <p className="rationale">{thesis.entry_quality.rationale}</p>
      )}

      {/* AI path only: a minimal secondary line (model / iteration count). */}
      {thesis.engine === "ai" && thesis.ai_notes && (
        <p className="ai-note">
          {[
            thesis.ai_notes.model ? `model: ${thesis.ai_notes.model}` : null,
            thesis.ai_notes.iterations != null
              ? `iteracje: ${thesis.ai_notes.iterations}`
              : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}

      {/* Weighted pros/cons. The backend already orders each list by weight
          desc, so we render in the delivered order (no client-side sort). A
          "brak" placeholder keeps a lop-sided thesis from showing a blank
          column. The principle tag trails each item subtly. */}
      <div className="thesis-section grid-2">
        <div>
          <p className="thesis-title">Mocne strony tezy</p>
          {thesis.pros.length > 0 ? (
            <ul className="points good">
              {thesis.pros.map((p) => (
                <li key={p.id}>
                  {p.text}
                  {p.principle && <span className="principle">{p.principle}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="points-empty">brak</p>
          )}
        </div>
        <div>
          <p className="thesis-title">Ryzyka dla tezy</p>
          {thesis.cons.length > 0 ? (
            <ul className="points bad">
              {thesis.cons.map((c) => (
                <li key={c.id}>
                  {c.text}
                  {c.principle && <span className="principle">{c.principle}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="points-empty">brak</p>
          )}
        </div>
      </div>

      {/* "Co sprawdzić dalej" — the entrance to deeper human analysis. */}
      {thesis.verify_next.length > 0 && (
        <div className="thesis-section">
          <p className="thesis-title">Co sprawdzić dalej</p>
          {thesis.verify_next.map((v) => (
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

      {/* Composed paragraph + the forward/trailing-C/Z basis note. */}
      {(thesis.thesis_read || thesis.valuation_basis) && (
        <div className="thesis-section">
          {thesis.thesis_read && <p className="thesis-read">{thesis.thesis_read}</p>}
          {thesis.valuation_basis && (
            <p className="valuation-basis">{thesis.valuation_basis}</p>
          )}
        </div>
      )}

      {/* Standing not-advice line — always visible, muted (plan Non-goals). */}
      {thesis.disclaimer && <p className="disclaimer">{thesis.disclaimer}</p>}
    </div>
  );
}
