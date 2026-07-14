"use client";

import { useMemo, useState } from "react";
import {
  IconAlertTriangle,
  IconCalculator,
  IconCheck,
  IconChevronRight,
  IconLock,
  IconPlayerPlay,
} from "@tabler/icons-react";
import { previewValuation, queueValuation } from "@/lib/api";
import { fmtDate, fmtNumber, fmtPct, fmtPln, fmtTysAsMln, parseNum, signClass } from "@/lib/format";
import type {
  CanonicalValuationSnapshot,
  ResearchWorkspace,
  ValuationAssumptionValue,
  ValuationDeterministicOutputs,
  ValuationPreview,
  ValuationRequest,
  ValuationScenarioAssumptions,
  ValuationScenarioKind,
  ValuationWorkspace,
} from "@/lib/types";

type AssumptionKey = Exclude<keyof ValuationScenarioAssumptions, "kind" | "label" | "event_one_off_net_pln_thousands">;
type InputState = Record<ValuationScenarioKind, Record<AssumptionKey, string>>;

const SCENARIOS: Array<{ kind: Exclude<ValuationScenarioKind, "event">; label: string; tone: string }> = [
  { kind: "negative", label: "Spadkowy", tone: "warning" },
  { kind: "base", label: "Bazowy", tone: "neutral" },
  { kind: "positive", label: "Wzrostowy", tone: "success" },
];
const EVENT_SCENARIO = { kind: "event" as const, label: "Zdarzeniowy", tone: "accent" };

const CORE_FIELDS: Array<{ key: AssumptionKey; label: string; unit: string }> = [
  { key: "quarter_revenue_growth_pct", label: "Zmiana przychodów · kwartał", unit: "%" },
  { key: "year_revenue_growth_pct", label: "Zmiana przychodów · 12 mies.", unit: "%" },
  { key: "gross_margin_pct", label: "Marża brutto", unit: "%" },
  { key: "operating_cost_ratio_pct", label: "Koszty operacyjne / przychody", unit: "%" },
  { key: "target_pe", label: "Docelowe C/Z", unit: "×" },
];

const DETAIL_FIELDS: Array<{ key: AssumptionKey; label: string; unit: string }> = [
  { key: "financial_result_ratio_pct", label: "Wynik finansowy / przychody", unit: "%" },
  { key: "tax_rate_pct", label: "Efektywna stopa podatku", unit: "%" },
  { key: "cash_conversion_pct", label: "Konwersja zysku na CFO", unit: "%" },
  { key: "capex_spend_ratio_pct", label: "Capex / przychody", unit: "%" },
];

const STATUS = {
  provisional: { label: "Prowizoryczna", tone: "warning" },
  verified: { label: "Zweryfikowana", tone: "success" },
  rejected: { label: "Odrzucona", tone: "danger" },
  "needs-human": { label: "Wymaga decyzji", tone: "warning" },
} as const;

function humanValue(value: number, rationale: string): ValuationAssumptionValue {
  return { value, provenance: "human_assumption", rationale, source_fact_ids: [] };
}

function emptyInputs(): InputState {
  const row = () => Object.fromEntries(
    [...CORE_FIELDS, ...DETAIL_FIELDS].map(({ key }) => [key, ""]),
  ) as Record<AssumptionKey, string>;
  return {
    negative: row(),
    base: row(),
    positive: row(),
    event: row(),
  };
}

function savedInputs(snapshot: CanonicalValuationSnapshot | null): InputState {
  const next = emptyInputs();
  if (!snapshot) return next;
  const saved = snapshot.assumptions.scenarios;
  if (!Array.isArray(saved)) return next;
  for (const scenario of saved) {
    if (!scenario || !(scenario.kind in next)) continue;
    for (const { key } of [...CORE_FIELDS, ...DETAIL_FIELDS]) {
      const value = scenario[key]?.value;
      if (typeof value === "number") next[scenario.kind][key] = String(value).replace(".", ",");
    }
  }
  return next;
}

function probabilityFor(snapshot: CanonicalValuationSnapshot | null, kind: ValuationScenarioKind) {
  return snapshot?.codex_judgment.scenarios?.find((item) => item.kind === kind) ?? null;
}

function scenarioConfig(kind: ValuationScenarioKind) {
  return kind === "event" ? EVENT_SCENARIO : SCENARIOS.find((item) => item.kind === kind)!;
}

function readableGap(gap: string) {
  const upstreamCount = gap.match(/^Upstream research contains (\d+) explicit gap\(s\)\.$/);
  if (upstreamCount) return `Research zawiera ${upstreamCount[1]} jawnych luk źródłowych.`;
  const translations: Record<string, string> = {
    "Shares and reported market cap are mutable Company scalars frozen at company.updated_at, not immutable Fact IDs.": "Liczba akcji i raportowana kapitalizacja są zamrożonym stanem spółki, ale nie mają jeszcze powiązania z niezmiennym faktem źródłowym.",
    "Upstream research snapshot is provisional.": "Bazowy snapshot Research ma status prowizoryczny.",
    "Raw price differs from reported market cap / shares by more than 2%.": "Kurs różni się o ponad 2% od relacji raportowanej kapitalizacji do liczby akcji.",
    "Price cannot be corroborated with reported market cap and shares.": "Nie można potwierdzić kursu przez raportowaną kapitalizację i liczbę akcji.",
    "Raw price series has incomplete source/series/basis identity.": "Seria kursu nie ma kompletnej tożsamości źródła, serii lub podstawy.",
    "Reference price row is not bound to an immutable source document version.": "Kurs odniesienia nie ma jeszcze powiązania z niezmienną wersją dokumentu źródłowego.",
  };
  return translations[gap] ?? gap;
}

function ResultComparison({
  outputs,
  saved,
}: {
  outputs: ValuationDeterministicOutputs;
  saved: CanonicalValuationSnapshot | null;
}) {
  return (
    <section className="valuation-results" aria-labelledby="valuation-results-heading">
      <div className="valuation-section-heading">
        <div>
          <p className="eyebrow">Porównanie</p>
          <h2 id="valuation-results-heading">Co musi się wydarzyć i jaki może być wynik</h2>
        </div>
        <span className="valuation-current-price">Kurs odniesienia <strong>{fmtPln(outputs.current_price_pln)}</strong></span>
      </div>

      <div className="valuation-scenario-results">
        {outputs.scenarios.map((row) => {
          const config = scenarioConfig(row.kind);
          const probability = probabilityFor(saved, row.kind);
          const judgment = saved?.codex_judgment.scenarios?.find((item) => item.kind === row.kind);
          return (
            <article className="valuation-result-card" key={row.kind}>
              <header>
                <span className={`badge ${config.tone}`}>{config.label}</span>
                {probability && <strong>{probability.probability_pct}%</strong>}
              </header>
              {judgment?.mechanism && <p className="valuation-mechanism">{judgment.mechanism}</p>}
              <dl className="valuation-result-metrics">
                <div><dt>Przychody · kwartał</dt><dd>{fmtTysAsMln(row.quarter.revenue_pln_thousands)}</dd></div>
                <div><dt>Zysk netto · kwartał</dt><dd>{fmtTysAsMln(row.quarter.net_result_pln_thousands)}</dd></div>
                <div><dt>Przychody · 12 mies.</dt><dd>{fmtTysAsMln(row.forward_12m.revenue_pln_thousands)}</dd></div>
                <div><dt>Zysk netto · 12 mies.</dt><dd>{fmtTysAsMln(row.forward_12m.net_result_pln_thousands)}</dd></div>
                <div><dt>EPS / FCF · 12 mies.</dt><dd>{fmtPln(row.forward_12m.eps_pln)} / {fmtTysAsMln(row.forward_12m.fcf_pln_thousands)}</dd></div>
              </dl>
              <div className="valuation-price-result">
                <span>Cena przy C/Z {fmtNumber(row.target_pe)}</span>
                {row.target_price_pln == null ? (
                  <><strong>Brak sensownej wyceny C/Z</strong><small>{row.valuation_gap ?? "Prognozowany EPS nie pozwala zastosować dodatniego mnożnika."}</small></>
                ) : (
                  <><strong>{fmtPln(row.target_price_pln)}</strong><span className={signClass(row.return_pct)}>{fmtPct(row.return_pct, { signed: true })}</span></>
                )}
              </div>
              {judgment && (
                <div className="valuation-judgment">
                  <p><span>Katalizator / przeciwwaga</span>{judgment.catalyst_or_counter_driver}</p>
                  <p><span>Falsyfikator</span>{judgment.falsifier}</p>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {saved && outputs.probability_weighted?.status === "calculated" && (
        <aside className="valuation-weighted">
          <div><span>Wynik ważony prawdopodobieństwem</span><strong>{fmtPln(outputs.probability_weighted.price_pln)}</strong></div>
          <span className={signClass(outputs.probability_weighted.return_pct)}>{fmtPct(outputs.probability_weighted.return_pct, { signed: true })}</span>
          <small>Prawdopodobieństwa są częścią szkicu spółki i podlegają niezależnej weryfikacji.</small>
        </aside>
      )}
      {saved && outputs.probability_weighted?.status === "unavailable" && (
        <aside className="valuation-weighted unavailable">
          <div><span>Wynik ważony prawdopodobieństwem</span><strong>Niedostępny</strong></div>
          <small>{outputs.probability_weighted.gap ?? "Nie wszystkie zweryfikowane scenariusze mają policzalną cenę."}</small>
        </aside>
      )}

      <details className="valuation-sensitivity">
        <summary>Osobna wrażliwość: powrót mnożnika do własnej historii</summary>
        <p>{outputs.own_history_sensitivity.status === "unavailable" ? "Brak porównywalnego, zamrożonego szeregu historycznych mnożników. Ta wrażliwość nie zastępuje scenariuszy operacyjnych." : outputs.own_history_sensitivity.note}</p>
        <span className="badge muted">{outputs.own_history_sensitivity.status === "unavailable" ? "brak policzalnego szeregu" : outputs.own_history_sensitivity.status}</span>
      </details>
    </section>
  );
}

export default function ValuationWorkspaceView({
  research,
  workspace,
}: {
  research: ResearchWorkspace;
  workspace: ValuationWorkspace;
}) {
  const snapshot = research.latest_snapshot;
  const boundValuation = workspace.latest_valuation?.research_snapshot_id === snapshot?.id
    ? workspace.latest_valuation
    : null;
  const staleValuation = workspace.latest_valuation && !boundValuation ? workspace.latest_valuation : null;
  const savedScenarioRows = boundValuation
    ? boundValuation.assumptions.scenarios
    : [];
  const savedEvent = savedScenarioRows.find((row) => row.kind === "event");
  const [inputs, setInputs] = useState<InputState>(() => savedInputs(boundValuation));
  const [eventEnabled, setEventEnabled] = useState(Boolean(savedEvent));
  const [eventOneOff, setEventOneOff] = useState(() => {
    const value = savedEvent?.event_one_off_net_pln_thousands?.value;
    return typeof value === "number" ? String(value).replace(".", ",") : "";
  });
  const [preview, setPreview] = useState<ValuationPreview | null>(null);
  const [busy, setBusy] = useState<"preview" | "queue" | null>(null);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canCalculate = Boolean(snapshot && workspace.template);
  const savedStatus = boundValuation ? STATUS[boundValuation.status] : null;

  const scenarioAssumptions = useMemo(() => {
    const rows: ValuationScenarioAssumptions[] = [];
    for (const scenario of SCENARIOS) {
      const values = inputs[scenario.kind];
      const parsed = Object.fromEntries(
        [...CORE_FIELDS, ...DETAIL_FIELDS].map(({ key, label }) => {
          const value = parseNum(values[key]);
          return [key, value == null ? null : humanValue(value, `${label}: jawne założenie użytkownika dla scenariusza ${scenario.label.toLowerCase()}.`)];
        }),
      );
      if (Object.values(parsed).some((value) => value == null)) return null;
      rows.push({ kind: scenario.kind, label: scenario.label, ...parsed } as ValuationScenarioAssumptions);
    }
    if (eventEnabled) {
      const values = inputs.event;
      const parsed = Object.fromEntries(
        [...CORE_FIELDS, ...DETAIL_FIELDS].map(({ key, label }) => {
          const value = parseNum(values[key]);
          return [key, value == null ? null : humanValue(value, `${label}: jawne założenie użytkownika dla scenariusza zdarzeniowego.`)];
        }),
      );
      const oneOff = parseNum(eventOneOff);
      if (Object.values(parsed).some((value) => value == null) || oneOff == null) return null;
      rows.push({
        kind: "event",
        label: EVENT_SCENARIO.label,
        ...parsed,
        event_one_off_net_pln_thousands: humanValue(oneOff, "Jednorazowy wpływ netto jawnie przyjęty dla ścieżki zdarzeniowej."),
      } as ValuationScenarioAssumptions);
    }
    return rows;
  }, [eventEnabled, eventOneOff, inputs]);

  const buildRequest = (asOf: string): ValuationRequest | null => {
    if (!snapshot || !scenarioAssumptions) return null;
    return {
      research_snapshot_id: snapshot.id,
      assumptions: scenarioAssumptions,
      as_of: asOf,
    };
  };

  const updateInput = (kind: ValuationScenarioKind, key: AssumptionKey, value: string) => {
    setInputs((current) => ({ ...current, [kind]: { ...current[kind], [key]: value } }));
    setPreview(null);
    setDirty(true);
    setMessage(null);
  };

  const updateEventOneOff = (value: string) => {
    setEventOneOff(value);
    setPreview(null); setDirty(true); setMessage(null);
  };

  const toggleEvent = () => {
    setEventEnabled((current) => !current);
    setPreview(null); setDirty(true); setMessage(null);
  };

  const calculate = async () => {
    const asOf = new Date().toISOString();
    const request = buildRequest(asOf);
    if (!request) {
      setError("Uzupełnij wszystkie założenia liczbami, zanim przeliczysz scenariusze.");
      return;
    }
    setBusy("preview"); setError(null); setMessage(null);
    try {
      setPreview(await previewValuation(workspace.research_case_id, request));
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const queue = async () => {
    if (!snapshot) return;
    setBusy("queue"); setError(null); setMessage(null);
    try {
      const result = await queueValuation(workspace.research_case_id, {
        research_snapshot_id: snapshot.id,
        as_of: new Date().toISOString(),
      });
      setMessage(result.created ? "Wycena została przekazana do opracowania i niezależnej weryfikacji." : "Wycena dla tego stanu Research już oczekuje lub została opracowana.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  if (!snapshot || !research.profile || !workspace.template) {
    return <section className="valuation-empty"><IconAlertTriangle size={22} /><h2>Wycena nie jest jeszcze dostępna</h2><p>Potrzebny jest użyteczny snapshot Research i obsługiwany szablon spółki.</p></section>;
  }

  const displayedOutputs = preview?.deterministic_outputs ?? (!dirty ? boundValuation?.deterministic_outputs : null) ?? null;
  const displayedSaved = preview ? null : boundValuation;
  const auditManifest = preview?.input_manifest ?? boundValuation?.input_manifest ?? null;
  const auditPrice = auditManifest?.price && typeof auditManifest.price === "object"
    ? auditManifest.price as Record<string, unknown>
    : null;
  const auditScalars = auditManifest?.company_scalar_provenance && typeof auditManifest.company_scalar_provenance === "object"
    ? auditManifest.company_scalar_provenance as Record<string, unknown>
    : null;
  const auditFactIds = Array.isArray(auditManifest?.fact_ids) ? auditManifest.fact_ids : [];
  const auditScalarFactIds = Array.isArray(auditScalars?.fact_ids) ? auditScalars.fact_ids : [];

  return (
    <main className="page-stack valuation-workspace">
      <header className="valuation-heading">
        <div>
          <p className="eyebrow">Valuation</p>
          <div className="valuation-title"><h1>{research.research_case.ticker}</h1><span>{research.research_case.name}</span></div>
          <p>Jawne scenariusze wyniku i ceny, policzone z zamrożonego stanu Research.</p>
        </div>
        <div className="valuation-boundary">
          <span className={`badge ${snapshot.status === "verified" ? "success" : "warning"}`}>Research {snapshot.status === "verified" ? "zweryfikowany" : "prowizoryczny"}</span>
          <strong>snapshot v{snapshot.version} · #{snapshot.id}</strong>
          <small>Stan wiedzy {fmtDate(snapshot.as_of)}</small>
        </div>
      </header>

      <section className="valuation-engine">
        <div><span className="snapshot-label">Silnik</span><strong>Workbench</strong><small>scenariusze właściwe dla spółki</small></div>
        <div><span className="snapshot-label">Szablon obliczeń</span><strong>{workspace.template.label}</strong><small>{workspace.template.version}</small></div>
        {savedStatus && <div><span className="snapshot-label">Ostatnia wycena</span><span className={`badge ${savedStatus.tone}`}>{savedStatus.label}</span><small>wersja {boundValuation!.version}</small></div>}
      </section>

      {staleValuation && (
        <aside className="valuation-stale" role="status">
          <IconLock size={15} />
          <div><strong>Poprzednia wycena pozostaje w historii</strong><p>Wersja {staleValuation.version} jest związana z Research snapshot #{staleValuation.research_snapshot_id}, a bieżący Research to #{snapshot.id}. Jej wyniki i prawdopodobieństwa nie są pokazywane jako aktualne.</p></div>
        </aside>
      )}

      <div className="valuation-driver-copy">
        {workspace.template.driver_copy.map((line) => <p key={line}><IconChevronRight size={14} />{line}</p>)}
      </div>

      <section className="valuation-editor" aria-labelledby="valuation-inputs-heading">
        <div className="valuation-section-heading">
          <div><p className="eyebrow">Założenia</p><h2 id="valuation-inputs-heading">Spadkowy, bazowy i wzrostowy</h2></div>
          <p>Pola są puste, dopóki nie wpiszesz własnych założeń. Zapisana wycena może wypełnić je wartościami właściwymi dla tej spółki.</p>
        </div>
        <div className="valuation-input-table">
          <div className="valuation-input-header"><span>Czynnik</span>{SCENARIOS.map((item) => <strong key={item.kind}>{item.label}</strong>)}</div>
          {CORE_FIELDS.map((field) => <div className="valuation-input-row" key={field.key}><label>{field.label}<small>{field.unit}</small></label>{SCENARIOS.map((scenario) => <input key={scenario.kind} inputMode="decimal" aria-label={`${field.label}, scenariusz ${scenario.label}`} value={inputs[scenario.kind][field.key]} onChange={(event) => updateInput(scenario.kind, field.key, event.target.value)} />)}</div>)}
          <details className="valuation-extra-inputs">
            <summary>Dodatkowe założenia wyniku i gotówki</summary>
            {DETAIL_FIELDS.map((field) => <div className="valuation-input-row" key={field.key}><label>{field.label}<small>{field.unit}</small></label>{SCENARIOS.map((scenario) => <input key={scenario.kind} inputMode="decimal" aria-label={`${field.label}, scenariusz ${scenario.label}`} value={inputs[scenario.kind][field.key]} onChange={(event) => updateInput(scenario.kind, field.key, event.target.value)} />)}</div>)}
          </details>
          <div className="valuation-event-toggle">
            <button className="btn compact" type="button" onClick={toggleEvent}>{eventEnabled ? "Usuń ścieżkę zdarzeniową" : "Dodaj opcjonalną ścieżkę zdarzeniową"}</button>
            <span>Użyj tylko dla konkretnego kontraktu, premiery, regulacji lub innego rozłącznego zdarzenia.</span>
          </div>
          {eventEnabled && (
            <section className="valuation-event-editor" aria-label="Założenia scenariusza zdarzeniowego">
              <header><span className="badge accent">Zdarzeniowy</span><strong>Jawne założenia zdarzenia</strong></header>
              <div className="valuation-event-fields">
                {[...CORE_FIELDS, ...DETAIL_FIELDS].map((field) => <label key={field.key}>{field.label}<span><input inputMode="decimal" value={inputs.event[field.key]} onChange={(event) => updateInput("event", field.key, event.target.value)} /><small>{field.unit}</small></span></label>)}
                <label>Jednorazowy wpływ na wynik netto<span><input inputMode="decimal" value={eventOneOff} onChange={(event) => updateEventOneOff(event.target.value)} /><small>tys. zł</small></span></label>
              </div>
            </section>
          )}
        </div>
        <div className="valuation-actions">
          <button className="btn" onClick={() => void calculate()} disabled={!canCalculate || busy != null}><IconCalculator size={15} />{busy === "preview" ? "Przeliczam…" : "Przelicz własny szkic"}</button>
          <button className="btn accent" onClick={() => void queue()} disabled={busy != null}><IconPlayerPlay size={15} />{busy === "queue" ? "Przekazuję…" : "Zleć wycenę spółki"}</button>
          <span>Własny szkic liczy Python. Zlecona wycena powstaje osobno z zamrożonych dowodów Research, a niezależny weryfikator podważa jej założenia i prawdopodobieństwa.</span>
        </div>
        {error && <div className="error-box" role="alert">{error}</div>}
        {message && <div className="success-box" role="status">{message}</div>}
      </section>

      {displayedOutputs ? <ResultComparison outputs={displayedOutputs} saved={displayedSaved} /> : <section className="valuation-awaiting"><IconCalculator size={20} /><p>Zmień założenia i przelicz szkic, aby zobaczyć porównanie trzech scenariuszy.</p></section>}

      {(preview?.gaps.length || boundValuation?.gaps.length) ? (
        <section className="valuation-gaps"><IconAlertTriangle size={17} /><div><strong>Ograniczenia tej wyceny</strong><ul>{(preview?.gaps ?? boundValuation?.gaps ?? []).map((gap) => <li key={gap}>{readableGap(gap)}</li>)}</ul></div></section>
      ) : null}

      <details className="valuation-audit">
        <summary><IconLock size={14} /> Równanie i audyt</summary>
        <div className="valuation-audit-content">
          <div><span>Równanie</span><p>{workspace.template.equation}</p></div>
          <div><span>Powiązanie</span><p>Research snapshot #{snapshot.id} · profil #{snapshot.company_profile_id} · szablon {workspace.template.id}</p></div>
          {auditManifest && <div><span>Zamrożone wejścia rynkowe</span><p>Kurs: {typeof auditPrice?.date === "string" ? fmtDate(auditPrice.date) : "—"} · źródło {String(auditPrice?.source_name ?? "brak")} · seria {String(auditPrice?.series_key ?? "brak")} · dokument #{String(auditPrice?.source_document_version_id ?? "brak")}</p><p>Potwierdzenie kursu: {auditPrice?.reference_price_status === "market_cap_corroborated" ? "zgodny z kapitalizacją i liczbą akcji" : String(auditPrice?.reference_price_status ?? "brak")} · seria zwrotu {auditPrice?.return_series_eligible === true ? "kwalifikowana" : "niekwalifikowana"}</p><p>Profil spółki: dokument #{String(auditScalars?.source_document_version_id ?? "brak")} · fakty {auditScalarFactIds.length > 0 ? auditScalarFactIds.join(", ") : "brak identyfikatorów"}</p><p>Fakty finansowe: {auditFactIds.length > 0 ? auditFactIds.join(", ") : "brak identyfikatorów"}</p></div>}
          {(preview || boundValuation) && <div className="valuation-fingerprints"><span>Fingerprinty</span><p>wejście: {(preview?.input_fingerprint ?? boundValuation?.input_fingerprint)}</p><p>obliczenia: {(preview?.calculation_fingerprint ?? boundValuation?.calculation_fingerprint)}</p>{boundValuation && <p>artefakt: {boundValuation.artifact_fingerprint}</p>}</div>}
          {boundValuation && <div><span>Weryfikacja</span>{boundValuation.origin === "human-override" ? <><p>Korekta użytkownika bez niezależnej weryfikacji.</p>{boundValuation.verifier_result.note && <p>{boundValuation.verifier_result.note}</p>}</> : <><p>{boundValuation.verifier_result.summary ?? "Brak podsumowania weryfikacji."}</p><div className="valuation-checks"><span className={boundValuation.verifier_result.verdict === "pass" ? "passed" : "failed"}>{boundValuation.verifier_result.verdict === "pass" ? <IconCheck size={12} /> : <IconAlertTriangle size={12} />}{boundValuation.verifier_result.verdict === "pass" ? "Ocena zaliczona" : "Wymaga korekty"}</span></div>{boundValuation.verifier_result.findings?.map((finding) => <p key={`${finding.area}-${finding.detail}`}><strong>{finding.area}:</strong> {finding.detail}</p>)}</>}</div>}
        </div>
      </details>
    </main>
  );
}
