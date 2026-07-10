import type { AssumptionItem, Scenario, ScenarioSet, Valuation } from "@/lib/types";
import { fmtPln, fmtPct, fmtTys, signClass } from "@/lib/format";

/**
 * Scenario simulation ("Scenariusze") — sits below the thesis section on the
 * Przegląd tab (thesis = the read; scenarios = the projections off it). The set
 * is composed rule-based by the backend (services/scenarios.py) + an optional
 * model-assisted refiner; this component only lays it out.
 *
 * Numbers: the panel does no client-side number formatting of its own — every
 * display value goes through the project's pl-PL helpers in lib/format.ts
 * (fmtPln/fmtPct), which centralise the pl-PL formatting, exactly like the rest
 * of the app. Horizon months are small integers rendered as-is. These are
 * conditional if-this-then-that projections, never a buy/sell signal.
 */
const MULTIPLE_LABEL: Record<string, string> = {
  cz: "C/Z",
  cwk: "C/WK",
  ev_ebitda: "EV/EBITDA",
};

// Confidence level → badge tone + Polish label. `high` is success (not a buy
// signal — just "the coverage is decent"); `low` is a muted caution, mirroring
// the not-a-signal framing the whole card carries.
const CONFIDENCE: Record<Valuation["confidence"]["level"], { tone: string; label: string }> = {
  high: { tone: "success", label: "wysoka" },
  medium: { tone: "neutral", label: "umiarkowana" },
  low: { tone: "warning", label: "niska" },
};

function scenarioTone(scenario: Scenario): string {
  if (scenario.implied_upside_pct == null) return "muted";
  if (scenario.implied_upside_pct < 0) return "warning";
  if (scenario.implied_upside_pct > 0) return "success";
  return "neutral";
}

const PROVENANCE_LABEL: Record<AssumptionItem["provenance"], string> = {
  evidence: "źródło",
  human_assumption: "założenie człowieka",
  model_suggestion: "sugestia modelu",
};

function assumptionValue(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export default function ScenariosPanel({
  scenarios,
  valuation,
}: {
  scenarios?: ScenarioSet;
  valuation?: Valuation;
}) {
  // Older cached dossiers predate the scenario layer — render nothing rather
  // than crash (the caller guards the section label too, so there is no orphan).
  if (!scenarios) return null;

  const engineLabel = scenarios.engine === "ai" ? "AI" : "deterministyczny";
  const multipleLabel =
    MULTIPLE_LABEL[scenarios.valuation_multiple] ?? scenarios.valuation_multiple;
  const qualityWarnings = scenarios.quality_warnings ?? [];

  return (
    <div className="card scenarios">
      {/* Valuation lens on the left; engine provenance on the right (mirrors
          the thesis card's silnik chip). */}
      <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
        <span className="badge muted">wycena wg mnożnika: {multipleLabel}</span>
        <span className="badge muted">silnik: {engineLabel}</span>
      </div>

      {/* Headline — the probability-weighted potential is the card's primary
          output, so it leads (large signed number) with the current→expected
          reconciliation. The per-scenario rows below are the supporting detail. */}
      <div className="headline">
        <div>
          <span className="headline-k">Oczekiwany potencjał (ważony scenariuszami)</span>
          <span className={`potential ${signClass(scenarios.weighted_expected_upside_pct)}`}>
            {fmtPct(scenarios.weighted_expected_upside_pct, { signed: true })}
          </span>
        </div>
        {scenarios.weighted_expected_price != null ? (
          <span className="headline-sub">
            {fmtPln(scenarios.current_price)} → {fmtPln(scenarios.weighted_expected_price)}
          </span>
        ) : (
          <span className="headline-gap">
            wycena niedostępna — brak ceny docelowej w scenariuszach
          </span>
        )}
      </div>

      {/* The standing framing — an analysis entrance, never a signal. */}
      {scenarios.framing && <p className="framing">Analiza: {scenarios.framing}</p>}

      {qualityWarnings.length > 0 && (
        <div className="scenario-warnings">
          {qualityWarnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}

      <div className="scenario-list">
        {scenarios.scenarios.map((s) => (
          <div className="scenario" key={s.id}>
            <div className="spread" style={{ flexWrap: "wrap", gap: 6 }}>
              <span className={`badge ${scenarioTone(s)}`}>{s.label}</span>
              <span className="prob">
                p ≈ {fmtPct(s.probability * 100, { digits: 0 })}
              </span>
            </div>

            {s.narrative && <p className="narrative">{s.narrative}</p>}

            {s.company_outcome && (
              <div className={`scenario-outcome ${s.company_outcome.direction}`}>
                <span className="k">Wynik w spółce</span>
                <strong>{s.company_outcome.label}</strong>
                <p>{s.company_outcome.description}</p>
              </div>
            )}

            <div className="scenario-metrics">
              <div>
                <span className="k">Cena docelowa</span>
                <span className="v">{fmtPln(s.target_price)}</span>
              </div>
              <div>
                <span className="k">Potencjał</span>
                <span className={`v ${signClass(s.implied_upside_pct)}`}>
                  {fmtPct(s.implied_upside_pct, { signed: true })}
                </span>
              </div>
              <div>
                <span className="k">Horyzont</span>
                <span className="v">
                  {s.horizon.low_months}–{s.horizon.high_months} mies.
                </span>
              </div>
            </div>

            {s.target_multiple.basis_label && (
              <p className="basis">{s.target_multiple.basis_label}</p>
            )}

            {s.assumptions.length > 0 && (
              <ul className="assumptions">
                {s.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      {scenarios.approved_assumption_sets && scenarios.approved_assumption_sets.length > 0 && (
        <div className="thesis-section approved-assumptions">
          <p className="thesis-title">Zatwierdzone założenia przypadku</p>
          <p className="assumption-context-note">
            Przekazane do kontekstu scenariusza; na tym etapie nie zmieniają jeszcze ceny docelowej.
          </p>
          <div className="approved-assumption-list">
            {scenarios.approved_assumption_sets.map((set) => (
              <div className="approved-assumption-set" key={set.id}>
                <div className="spread" style={{ flexWrap: "wrap", gap: 6 }}>
                  <strong>{set.label}</strong>
                  <span className="badge muted">{set.scenario_kind}</span>
                </div>
                {set.assumptions.length > 0 ? (
                  <ul>
                    {set.assumptions.map((item) => (
                      <li key={`${set.id}-${item.key}`}>
                        <span className="assumption-key">{item.key}</span>: {assumptionValue(item.value)}
                        {item.unit ? ` ${item.unit}` : ""} · {PROVENANCE_LABEL[item.provenance]}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="small muted">Brak pozycji w zatwierdzonym zestawie.</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {scenarios.driver_sensitivity && scenarios.driver_sensitivity.status !== "none" && (
        <div className="thesis-section driver-sensitivity">
          <p className="thesis-title">Wrażliwość na zatwierdzone sterowniki</p>
          <p className="sensitivity-note">{scenarios.driver_sensitivity.note}</p>
          <div className="sensitivity-list">
            {scenarios.driver_sensitivity.rows.map((row) => (
              <div className="sensitivity-row" key={row.scenario_kind}>
                <div className="spread" style={{ flexWrap: "wrap", gap: 6 }}>
                  <strong>{row.label}</strong>
                  <span className={`badge ${row.applied.length > 0 ? "success" : "warning"}`}>
                    {row.applied.length > 0 ? "zastosowano" : "wymaga decyzji"}
                  </span>
                </div>
                <div className="scenario-metrics">
                  <div>
                    <span className="k">Cena bazowa</span>
                    <span className="v">{fmtPln(row.baseline_target_price)}</span>
                  </div>
                  <div>
                    <span className="k">Cena po założeniu</span>
                    <span className="v">{fmtPln(row.sensitivity_target_price)}</span>
                  </div>
                  <div>
                    <span className="k">Zmiana</span>
                    <span className={`v ${signClass(row.target_price_delta)}`}>
                      {row.target_price_delta != null && row.target_price_delta > 0 ? "+" : ""}
                      {fmtPln(row.target_price_delta)}
                    </span>
                  </div>
                  <div>
                    <span className="k">Zmiana potencjału</span>
                    <span className={`v ${signClass(row.upside_delta_pct)}`}>
                      {fmtPct(row.upside_delta_pct, { signed: true })}
                    </span>
                  </div>
                </div>
                {row.applied.length > 0 && (
                  <p className="sensitivity-detail">
                    Zastosowano: {row.applied.map((item) => `${item.key} (${PROVENANCE_LABEL[item.provenance]})`).join(", ")}.
                  </p>
                )}
                {row.ignored.length > 0 && (
                  <p className="sensitivity-detail muted">
                    Pominięto: {row.ignored.map((item) => `${item.key} — ${item.note}`).join("; ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {scenarios.operating_bridge && scenarios.operating_bridge.status !== "none" && (
        <div className="thesis-section operating-bridge">
          <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <p className="thesis-title">Most operacyjny</p>
            <span className={`badge ${scenarios.operating_bridge.status === "applied" ? "success" : "warning"}`}>
              {scenarios.operating_bridge.status === "applied" ? "policzony" : "wymaga danych"}
            </span>
          </div>
          {scenarios.operating_bridge.template && (
            <p className="small muted">{scenarios.operating_bridge.template.label}: {scenarios.operating_bridge.template.equation}</p>
          )}
          <p className="sensitivity-note">{scenarios.operating_bridge.note}</p>
          <div className="operating-bridge-list">
            {scenarios.operating_bridge.rows.map((row) => (
              <div className="operating-bridge-row" key={row.scenario_kind}>
                <div className="spread" style={{ flexWrap: "wrap", gap: 6 }}>
                  <strong>{row.label}</strong>
                  <span className="badge muted">{row.scenario_kind}</span>
                </div>
                <div className="scenario-metrics">
                  <div><span className="k">Przychód</span><span className="v">{fmtTys(row.projected_revenue)}</span></div>
                  <div><span className="k">Marża brutto</span><span className="v">{fmtPct(row.projected_gross_margin_pct)}</span></div>
                  <div><span className="k">Zysk netto</span><span className="v">{fmtTys(row.projected_net_profit)}</span></div>
                  <div><span className="k">Cena z mostu</span><span className={`v ${signClass(row.target_price_delta)}`}>{fmtPln(row.operating_target_price)}</span></div>
                </div>
                {row.missing.length > 0 && <p className="sensitivity-detail muted">Luki: {row.missing.join("; ")}</p>}
                {row.ignored.length > 0 && <p className="sensitivity-detail muted">Pominięto: {row.ignored.map((item) => `${item.key} — ${item.note}`).join("; ")}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI path only: a minimal secondary line (model / iteration count). */}
      {scenarios.engine === "ai" && scenarios.ai_notes && (
        <p className="ai-note">
          {[
            scenarios.ai_notes.model ? `model: ${scenarios.ai_notes.model}` : null,
            scenarios.ai_notes.iterations != null
              ? `iteracje: ${scenarios.ai_notes.iterations}`
              : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}

      {/* AI valuation (stage SC / WP4): the stock-potential read on top of the
          scenarios — potential anchored to the weighted EV, a confidence level,
          and "what would change the assessment". Optional so older cached
          dossiers (no valuation block) degrade to the scenarios alone. All
          numeric fields go through the pl-PL helpers in lib/format.ts — the
          component does no raw number-formatting of its own. */}
      {valuation && (
        <div className="thesis-section valuation">
          <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <p className="thesis-title" style={{ margin: 0 }}>
              Potencjał (ocena)
            </p>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              <span className={`badge ${CONFIDENCE[valuation.confidence.level]?.tone ?? "muted"}`}>
                pewność: {CONFIDENCE[valuation.confidence.level]?.label ?? valuation.confidence.level}
              </span>
              <span className="badge muted">
                silnik: {valuation.engine === "ai" ? "AI" : "deterministyczny"}
              </span>
            </div>
          </div>

          <div className="scenario-metrics">
            <div>
              <span className="k">Potencjał</span>
              <span className={`v ${signClass(valuation.potential.value_pct)}`}>
                {fmtPct(valuation.potential.value_pct, { signed: true })}
              </span>
            </div>
            {valuation.potential.range_pct && (
              <div>
                <span className="k">Pasmo scenariuszy</span>
                <span className="v secondary">
                  {fmtPct(valuation.potential.range_pct[0], { signed: true })} …{" "}
                  {fmtPct(valuation.potential.range_pct[1], { signed: true })}
                </span>
              </div>
            )}
          </div>

          {valuation.potential.basis_label && (
            <p className="basis">{valuation.potential.basis_label}</p>
          )}
          {valuation.confidence.rationale && (
            <p className="rationale">{valuation.confidence.rationale}</p>
          )}

          {valuation.what_would_change.length > 0 && (
            <>
              <p className="thesis-title" style={{ marginTop: 12 }}>
                Co zmieniłoby ocenę
              </p>
              {valuation.what_would_change.map((w) => (
                <p className="wwc-item" key={w.id}>
                  {w.text}
                  {w.why && (
                    <>
                      {" — "}
                      <span className="why">{w.why}</span>
                    </>
                  )}
                </p>
              ))}
            </>
          )}

          {valuation.narrative && <p className="rationale">{valuation.narrative}</p>}
          {valuation.framing && <p className="framing">Analiza: {valuation.framing}</p>}

          {valuation.engine === "ai" && valuation.ai_notes && (
            <p className="ai-note">
              {[
                valuation.ai_notes.model ? `model: ${valuation.ai_notes.model}` : null,
                valuation.ai_notes.iterations != null
                  ? `iteracje: ${valuation.ai_notes.iterations}`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
      )}

      {/* Standing not-advice line — always visible, muted (plan Non-goals). One
          disclaimer covers the whole scenarios + valuation card (both carry the
          identical thesis.DISCLAIMER). */}
      {scenarios.disclaimer && <p className="disclaimer">{scenarios.disclaimer}</p>}
    </div>
  );
}
