"use client";

import { useState } from "react";
import {
  IconAlertTriangle,
  IconCheck,
  IconChevronRight,
  IconLock,
  IconPlayerPlay,
} from "@tabler/icons-react";
import { queueValuation } from "@/lib/api";
import { fmtDate, fmtNumber, fmtPct, fmtPln, fmtTysAsMln, signClass } from "@/lib/format";
import type {
  CanonicalValuationSnapshot,
  ResearchWorkspace,
  ValuationDeterministicOutputs,
  ValuationMethod,
  ValuationMethodOutput,
  ValuationScenarioKind,
  ValuationWorkspace,
} from "@/lib/types";

const STATUS = {
  provisional: { label: "Prowizoryczna", tone: "warning" },
  verified: { label: "Zweryfikowana", tone: "success" },
  rejected: { label: "Odrzucona", tone: "danger" },
  "needs-human": { label: "Wymaga decyzji", tone: "warning" },
} as const;

const SCENARIO = {
  negative: { label: "Spadkowy", tone: "warning" },
  base: { label: "Bazowy", tone: "neutral" },
  positive: { label: "Wzrostowy", tone: "success" },
  event: { label: "Zdarzeniowy", tone: "accent" },
} as const;

const METHOD_LABEL: Record<ValuationMethod, string> = {
  pe: "P/E · zysk powtarzalny",
  ev_ebitda: "EV/EBITDA",
  ev_ebit: "EV/EBIT",
  fcff_dcf: "DCF · FCFF",
};

const BRIDGE_LABEL: Record<string, string> = {
  revenue: "Przychody",
  ebitda: "EBITDA",
  ebit: "EBIT",
  recurring_net_result: "Zysk netto powtarzalny",
  capex: "Capex",
};

function probabilityFor(outputs: ValuationDeterministicOutputs, kind: ValuationScenarioKind) {
  return outputs.final_probabilities?.find((item) => item.kind === kind) ?? null;
}

function fmtPp(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${fmtNumber(value, 1)} pp`;
}

function readableGap(gap: string) {
  const translations: Record<string, string> = {
    "Upstream research snapshot is provisional.": "Bazowy snapshot Research ma status prowizoryczny.",
    "Reference price row is not bound to an immutable source document version.": "Kurs odniesienia nie ma powiązania z niezmienną wersją dokumentu.",
  };
  return translations[gap] ?? gap;
}

function methodBasis(method: ValuationMethod, result: ValuationMethodOutput) {
  if (result.status !== "calculated") return null;
  const valueDate = result.value_date === "present"
    ? "wartość bieżąca"
    : result.valuation_period ? `cena FY${result.valuation_period}` : null;
  const distress = result.distress_floor_applied ? "wartość rezydualna 0" : null;
  if (method === "fcff_dcf" && result.wacc_pct != null && result.terminal_growth_pct != null) {
    return [`WACC ${fmtPct(result.wacc_pct)} · g ${fmtPct(result.terminal_growth_pct)}`, valueDate, distress].filter(Boolean).join(" · ");
  }
  if (result.target_multiple != null) return [`${fmtNumber(result.target_multiple, 2)}×`, valueDate, distress].filter(Boolean).join(" · ");
  return valueDate;
}

function ForecastAndSensitivity({ outputs }: { outputs: ValuationDeterministicOutputs }) {
  return (
    <section className="valuation-model-evidence" aria-labelledby="valuation-model-evidence-heading">
      <div className="valuation-section-heading">
        <div>
          <p className="eyebrow">Ścieżka modelu</p>
          <h2 id="valuation-model-evidence-heading">Pięć lat przepływów i wrażliwość DCF</h2>
        </div>
        <p>Pierwszy okres pokazuje jawny udział i czas dyskonta; brak Street poza zachowanym horyzontem nie jest traktowany jako spadek.</p>
      </div>
      <div className="valuation-model-scenarios">
        {outputs.scenarios.map((scenario) => {
          const config = SCENARIO[scenario.kind];
          const dcf = scenario.methods.fcff_dcf;
          return (
            <details key={scenario.kind}>
              <summary><span className={`badge ${config.tone}`}>{config.label}</span><strong>{scenario.forecast_path.length} okresów</strong></summary>
              <div className="valuation-forecast-scroll">
                <table>
                  <thead><tr><th>FY</th><th>Przychody</th><th>EBITDA</th><th>EBIT</th><th>Zysk powt.</th><th>FCFF roczny</th><th>Udział okresu</th><th>Czas dyskonta</th></tr></thead>
                  <tbody>{scenario.forecast_path.map((year) => <tr key={year.period}>
                    <th>{year.period}</th>
                    <td>{fmtTysAsMln(year.revenue_pln_thousands)}</td>
                    <td>{fmtTysAsMln(year.ebitda_pln_thousands)}</td>
                    <td>{fmtTysAsMln(year.ebit_pln_thousands)}</td>
                    <td>{fmtTysAsMln(year.recurring_net_result_pln_thousands)}</td>
                    <td>{fmtTysAsMln(year.fcff_pln_thousands)}</td>
                    <td>{fmtPct(year.fcff_period_fraction * 100)}</td>
                    <td>{fmtNumber(year.fcff_discount_years, 3)} roku</td>
                  </tr>)}</tbody>
                </table>
              </div>
              {dcf.status === "calculated" && <div className="valuation-dcf-detail">
                <div className="valuation-dcf-parameters">
                  <span>WACC <strong>{fmtPct(dcf.wacc_pct)}</strong></span>
                  <span>Wzrost terminalny <strong>{fmtPct(dcf.terminal_growth_pct)}</strong></span>
                  <span>Reinwestycja terminalna <strong>{fmtPct(dcf.terminal_reinvestment_rate_pct)}</strong></span>
                  <span>ROIC przyrostowy <strong>{fmtPct(dcf.terminal_incremental_roic_pct)}</strong></span>
                  <span>FCFF terminalny <strong>{fmtTysAsMln(dcf.terminal_fcff_pln_thousands)}</strong></span>
                  <span>Udział terminala <strong>{fmtPct(dcf.terminal_value_share_pct)}</strong></span>
                  <span>Wartość kapitału <strong>{fmtTysAsMln(dcf.equity_value_pln_thousands)}</strong></span>
                </div>
                {dcf.sensitivity?.length ? <div className="valuation-dcf-sensitivity">
                  <strong>Wrażliwość ceny na WACC / wzrost terminalny</strong>
                  <div>{dcf.sensitivity.map((cell) => <span key={`${cell.wacc_pct}-${cell.terminal_growth_pct}`}>
                    <small>{fmtPct(cell.wacc_pct)} / {fmtPct(cell.terminal_growth_pct)}</small>
                    <strong>{fmtPln(cell.price_pln)}</strong>
                  </span>)}</div>
                </div> : null}
              </div>}
            </details>
          );
        })}
      </div>
    </section>
  );
}

function PricedInExpectations({ outputs }: { outputs: ValuationDeterministicOutputs }) {
  const priced = outputs.priced_in_expectations;
  const reverse = priced.reverse_dcf;
  const pe = priced.methods.pe;
  const evEbitda = priced.methods.ev_ebitda;
  return (
    <section className="valuation-priced-in" aria-labelledby="valuation-priced-in-heading">
      <div>
        <p className="eyebrow">Reverse valuation</p>
        <h2 id="valuation-priced-in-heading">Co musi dowieźć spółka, żeby uzasadnić obecny kurs</h2>
        <p>To diagnostyka oczekiwań w cenie, nie dodatkowy cel ani rekomendacja. Reverse DCF skaluje całą ścieżkę przy niezmienionych marżach, reinwestycji, WACC i g.</p>
      </div>
      <div className="valuation-priced-in-grid">
        <article>
          <span>Reverse DCF · FY{reverse?.valuation_period ?? priced.valuation_period}</span>
          {reverse?.status === "calculated" ? <>
            <strong>{fmtTysAsMln(reverse.implied_revenue_pln_thousands)}</strong>
            <small>przychodów implikowanych przez kurs</small>
            <p>BiznesRadar {fmtTysAsMln(reverse.street_revenue_pln_thousands)} · różnica <b>{fmtPct(reverse.variance_to_street_revenue_pct, { signed: true })}</b></p>
            <p>Skala ścieżki bazowej {fmtPct(reverse.implied_revenue_path_scale_pct)} · błąd repricingu {fmtNumber(reverse.repricing_residual_bps, 6)} pb</p>
          </> : <><strong>Niedostępny</strong><small>{reverse?.gap ?? "Brak rozwiązania reverse DCF."}</small></>}
        </article>
        <article>
          <span>Reverse P/E</span>
          {pe ? <><strong>{fmtTysAsMln(pe.implied_net_income_pln_thousands)}</strong><small>implikowanego zysku netto przy {fmtNumber(pe.target_multiple, 2)}×</small></> : <strong>Niedostępny</strong>}
        </article>
        <article>
          <span>Reverse EV/EBITDA</span>
          {evEbitda ? <><strong>{fmtTysAsMln(evEbitda.implied_ebitda_pln_thousands)}</strong><small>implikowanej EBITDA przy {fmtNumber(evEbitda.target_multiple, 2)}×</small></> : <strong>Niedostępny</strong>}
        </article>
      </div>
    </section>
  );
}

function DriverToValuePotential({
  outputs,
  saved,
}: {
  outputs: ValuationDeterministicOutputs;
  saved: CanonicalValuationSnapshot;
}) {
  const orderedKinds: ValuationScenarioKind[] = ["negative", "base", "positive", "event"];
  const assumptions = saved.assumptions.scenarios;
  const scenarioRows = orderedKinds.map((kind) => ({
    kind,
    assumptions: assumptions.find((scenario) => scenario.kind === kind),
    output: outputs.scenarios.find((scenario) => scenario.kind === kind),
  })).filter((row) => row.assumptions && row.output);
  const drivers = Array.from(new Map(
    scenarioRows.flatMap((row) => row.assumptions!.potential_drivers)
      .map((driver) => [driver.driver_id, driver]),
  ).values());

  if (!drivers.length || !scenarioRows.length) return null;

  return <section className="valuation-potential" aria-labelledby="valuation-potential-heading">
    <div className="valuation-section-heading">
      <div>
        <p className="eyebrow">Most potencjału</p>
        <h2 id="valuation-potential-heading">Dowód → driver → wynik → wartość</h2>
      </div>
      <p>Zmiany driverów muszą dokładnie sumować się do całej ścieżki operacyjnej. Dodatnia alokacja kapitału oznacza wypływ gotówki podnoszący dług netto; ujemna — wpływ finansowania. Potencjał bez tego mostu nie przechodzi bramki.</p>
    </div>

    <div className="valuation-driver-list">
      {drivers.map((driver) => <article key={driver.driver_id}>
        <header><strong>{driver.label}</strong><span>{driver.driver_id}</span></header>
        <div className="valuation-driver-scenario-reads">
          {scenarioRows.map(({ kind, assumptions: scenario }) => {
            const scenarioDriver = scenario!.potential_drivers.find((item) => item.driver_id === driver.driver_id);
            if (!scenarioDriver) return null;
            return <div key={kind}>
              <span className={`badge ${SCENARIO[kind].tone}`}>{SCENARIO[kind].label}</span>
              <p>{scenarioDriver.mechanism}</p>
              <small><b>Runway:</b> {scenarioDriver.runway_evidence}</small>
              <small><b>Kapitał:</b> {scenarioDriver.capital_requirements}</small>
            </div>;
          })}
        </div>
        <div className="valuation-driver-table-wrap"><table>
          <thead><tr><th>Wariant</th><th>Δ przychodu</th><th>Δ marży EBITDA</th><th>Δ amort. / sprzedaż</th><th>Δ capex / sprzedaż</th><th>Δ NWC / sprzedaż</th><th>Δ podatku</th><th>Δ wyniku fin. / sprzedaż</th><th>Runway do</th></tr></thead>
          <tbody>{scenarioRows.map(({ kind, output }) => {
            const bridge = output!.driver_to_value_bridge.drivers.find((item) => item.driver_id === driver.driver_id);
            return <tr key={kind}>
              <th>{SCENARIO[kind].label}</th>
              <td>{fmtTysAsMln(bridge?.cumulative_revenue_delta_pln_thousands)}</td>
              <td>{fmtPp(bridge?.cumulative_ebitda_margin_delta_pp)}</td>
              <td>{fmtPp(bridge?.cumulative_depreciation_ratio_delta_pp)}</td>
              <td>{fmtPp(bridge?.cumulative_capex_ratio_delta_pp)}</td>
              <td>{fmtPp(bridge?.cumulative_nwc_ratio_delta_pp)}</td>
              <td>{fmtPp(bridge?.cumulative_cash_tax_rate_delta_pp)}</td>
              <td>{fmtPp(bridge?.cumulative_net_financial_result_ratio_delta_pp)}</td>
              <td>FY{bridge?.runway_end_period ?? "—"}</td>
            </tr>;
          })}</tbody>
        </table></div>
        <details className="valuation-driver-annual">
          <summary>Pięć rocznych wierszy drivera</summary>
          <div className="valuation-driver-table-wrap"><table>
            <thead><tr><th>Wariant</th><th>FY</th><th>Δ przychodu</th><th>Δ marży EBITDA</th><th>Δ amort. / sprzedaż</th><th>Δ capex / sprzedaż</th><th>Δ NWC / sprzedaż</th><th>Δ podatku</th><th>Δ wyniku fin. / sprzedaż</th></tr></thead>
            <tbody>{scenarioRows.flatMap(({ kind, assumptions: scenario }) => {
              const scenarioDriver = scenario!.potential_drivers.find((item) => item.driver_id === driver.driver_id);
              return (scenarioDriver?.impacts ?? []).map((impact) => <tr key={`${kind}-${impact.period}`}>
                <th>{SCENARIO[kind].label}</th>
                <td>FY{impact.period}</td>
                <td>{fmtTysAsMln(impact.revenue_delta_pln_thousands?.value)}</td>
                <td>{fmtPp(impact.ebitda_margin_delta_pp?.value)}</td>
                <td>{fmtPp(impact.depreciation_pct_revenue_delta_pp?.value)}</td>
                <td>{fmtPp(impact.capex_pct_revenue_delta_pp?.value)}</td>
                <td>{fmtPp(impact.delta_nwc_pct_revenue_delta_pp?.value)}</td>
                <td>{fmtPp(impact.cash_tax_rate_delta_pp?.value)}</td>
                <td>{fmtPp(impact.net_financial_result_pct_revenue_delta_pp?.value)}</td>
              </tr>);
            })}</tbody>
          </table></div>
        </details>
      </article>)}
    </div>

    <div className="valuation-potential-scenarios">
      {scenarioRows.map(({ kind, assumptions: scenario, output }) => {
        const bridge = output!.driver_to_value_bridge;
        const primary = outputs.methodology.primary_method;
        const hurdle = bridge.market_hurdles[primary];
        return <article key={kind}>
          <header><span className={`badge ${SCENARIO[kind].tone}`}>{SCENARIO[kind].label}</span><strong>FY{bridge.anchor_period}–FY{bridge.end_period}</strong></header>
          <dl>
            <div><dt>CAGR przychodów</dt><dd>{fmtPct(bridge.trajectory.revenue.cagr_pct)}</dd></div>
            <div><dt>Δ marży EBITDA</dt><dd>{fmtPp(bridge.trajectory.ebitda_margin.change_pp)}</dd></div>
            <div><dt>FCFF horyzontu</dt><dd>{fmtTysAsMln(bridge.reinvestment.cumulative_fcff_pln_thousands)}</dd></div>
            <div><dt>Reinwestycja / przychody</dt><dd>{fmtPct(bridge.reinvestment.net_reinvestment_to_revenue_pct)}</dd></div>
            <div><dt>Dług netto dziś</dt><dd>{fmtTysAsMln(bridge.net_debt_bridge.current_net_debt_pln_thousands)}</dd></div>
            <div><dt>Gotówka po finansowaniu do FY{bridge.valuation_period}</dt><dd>{fmtTysAsMln(bridge.net_debt_bridge.cumulative_cash_after_financing_to_valuation_pln_thousands)}</dd></div>
            <div><dt>Gotówka zdarzenia do FY{bridge.valuation_period}</dt><dd>{fmtTysAsMln(bridge.net_debt_bridge.event_cash_to_valuation_pln_thousands)}</dd></div>
            <div><dt>Dług netto FY{bridge.valuation_period}</dt><dd>{fmtTysAsMln(bridge.net_debt_bridge.target_net_debt_pln_thousands)}</dd></div>
            <div><dt>Alokacja kapitału do FY{bridge.valuation_period}</dt><dd>{fmtTysAsMln(bridge.net_debt_bridge.cumulative_capital_allocation_pln_thousands)}</dd></div>
            <div><dt>Reszta uzgodnienia długu</dt><dd>{fmtTysAsMln(bridge.net_debt_bridge.reconciliation_residual_pln_thousands)}</dd></div>
            <div><dt>g = reinwestycja × ROIC</dt><dd>{fmtPct(bridge.terminal_economics.growth_pct)} = {fmtPct(bridge.terminal_economics.reinvestment_rate_pct)} × {fmtPct(bridge.terminal_economics.incremental_roic_pct)}</dd></div>
            {bridge.price_change_basis === "present_value_gap"
              ? <div><dt>Luka wartości bieżącej</dt><dd className={signClass(bridge.current_value_gap_pct)}>{fmtPct(bridge.current_value_gap_pct, { signed: true })}</dd></div>
              : <div><dt>Roczny repricing do FY{bridge.valuation_period}</dt><dd className={signClass(bridge.annualized_price_repricing_pct)}>{fmtPct(bridge.annualized_price_repricing_pct, { signed: true })}</dd></div>}
          </dl>
          {scenario!.event_impact && <p>Zdarzenie FY{scenario!.event_impact.period}: gotówka {fmtTysAsMln(scenario!.event_impact.cash_pln_thousands.value)} (PV {fmtTysAsMln(bridge.event_cash_present_value_pln_thousands)}); wynik jednorazowy {fmtTysAsMln(scenario!.event_impact.pnl_net_pln_thousands.value)}. Wycena tylko przez terminowy DCF.</p>}
          <p>Kurs przy metodzie {METHOD_LABEL[primary]} wymaga pokrycia <strong>{fmtPct(hurdle.coverage_pct)}</strong>; bufor / brak <b className={signClass(hurdle.headroom_pct)}>{fmtPct(hurdle.headroom_pct, { signed: true })}</b>.</p>
        </article>;
      })}
    </div>
  </section>;
}

function ResultComparison({
  outputs,
  saved,
}: {
  outputs: ValuationDeterministicOutputs;
  saved: CanonicalValuationSnapshot;
}) {
  const comparabilityFinding = saved.verifier_result.findings?.find((finding) => {
    const text = `${finding.area} ${finding.detail}`.toLowerCase();
    return text.includes("comparability") || text.includes("porównywalno") || text.includes("demerger");
  });
  return (
    <section className="valuation-results" aria-labelledby="valuation-results-heading">
      <div className="valuation-section-heading">
        <div>
          <p className="eyebrow">Wariant wobec konsensusu</p>
          <h2 id="valuation-results-heading">Co Workbench potwierdza, a gdzie widzi przewagę</h2>
        </div>
        <span className="valuation-current-price">Kurs odniesienia <strong>{fmtPln(outputs.current_price_pln)}</strong></span>
      </div>

      <div className="valuation-methodology">
        <div><span>Metoda główna</span><strong>{METHOD_LABEL[outputs.methodology.primary_method]}</strong></div>
        <div><span>Cross-checki</span><strong>{outputs.methodology.cross_checks.map((method) => METHOD_LABEL[method]).join(" · ")}</strong></div>
        <div><span>Rok wyceny</span><strong>FY{outputs.methodology.valuation_period}</strong></div>
        <p>{outputs.methodology.rationale}</p>
      </div>

      {comparabilityFinding && <aside className="valuation-method-caveat" role="note">
        <IconAlertTriangle size={15} />
        <div><strong>Ograniczona porównywalność mnożników historycznych</strong><p>{comparabilityFinding.detail}</p></div>
      </aside>}

      <DriverToValuePotential outputs={outputs} saved={saved} />

      <div className="valuation-scenario-results">
        {outputs.scenarios.map((row) => {
          const config = SCENARIO[row.kind];
          const probability = probabilityFor(outputs, row.kind);
          const judgment = saved.codex_judgment.scenarios?.find((item) => item.kind === row.kind);
          const year = row.forecast_path.find((item) => item.period === outputs.methodology.valuation_period) ?? row.forecast_path.at(-1);
          const bridge = row.expectation_bridge.find((item) => item.period === outputs.methodology.valuation_period);
          return (
            <article className="valuation-result-card" key={row.kind}>
              <header>
                <span className={`badge ${config.tone}`}>{config.label}</span>
                {probability && <strong>{fmtNumber(probability.probability_pct, 1)}%</strong>}
                {!probability && <span className="badge muted">bez kalibracji %</span>}
              </header>
              {judgment?.mechanism && <p className="valuation-mechanism">{judgment.mechanism}</p>}
              {year && <dl className="valuation-result-metrics">
                <div><dt>Przychody FY{year.period}</dt><dd>{fmtTysAsMln(year.revenue_pln_thousands)}</dd></div>
                <div><dt>EBITDA</dt><dd>{fmtTysAsMln(year.ebitda_pln_thousands)}</dd></div>
                <div><dt>EBIT</dt><dd>{fmtTysAsMln(year.ebit_pln_thousands)}</dd></div>
                <div><dt>Zysk powtarzalny</dt><dd>{fmtTysAsMln(year.recurring_net_result_pln_thousands)}</dd></div>
                <div><dt>EPS powtarzalny</dt><dd>{fmtPln(year.recurring_eps_pln)}</dd></div>
                <div><dt>FCFF</dt><dd>{fmtTysAsMln(year.fcff_pln_thousands)}</dd></div>
              </dl>}

              {bridge && <div className="valuation-expectation-bridge">
                <strong>Odchylenie od BiznesRadar</strong>
                {bridge.metrics.map((metric) => <p key={metric.metric}>
                  <span>{BRIDGE_LABEL[metric.metric] ?? metric.metric}</span>
                  <span>{metric.street_pln_thousands == null ? "konsensus nieznany" : `${fmtPct(metric.variance_pct, { signed: true })} · BR ${fmtTysAsMln(metric.street_pln_thousands)}`}</span>
                </p>)}
              </div>}

              <div className="valuation-method-grid">
                {(Object.keys(METHOD_LABEL) as ValuationMethod[]).map((method) => {
                  const result = row.methods[method];
                  return <div key={method} className={method === row.primary_method ? "primary" : ""}>
                    <span>{METHOD_LABEL[method]}</span>
                    <strong>{result.status === "calculated" ? fmtPln(result.price_pln) : "niedostępna"}</strong>
                    {methodBasis(method, result) && <small>{methodBasis(method, result)}</small>}
                  </div>;
                })}
              </div>

              <div className="valuation-price-result">
                <span>Cena z metody głównej</span>
                {row.target_price_pln == null ? (
                  <><strong>Metoda niedostępna</strong><small>{row.valuation_gap}</small></>
                ) : (
                  <><strong>{fmtPln(row.target_price_pln)}</strong><span className={signClass(row.return_pct)}>{fmtPct(row.return_pct, { signed: true })}</span><small>{row.target_price_basis === "present" ? "bieżąca luka wartości" : `łączny repricing do FY${row.target_price_period}`}</small></>
                )}
                {row.cross_check_range_pln && <small>Porównywalny zakres metod {fmtPln(row.cross_check_range_pln.low)}–{fmtPln(row.cross_check_range_pln.high)} · rozbieżność {fmtPct(row.method_dispersion_pct)}</small>}
              </div>

              {judgment && <div className="valuation-judgment">
                <p><span>Katalizator / przeciwwaga</span>{judgment.catalyst_or_counter_driver}</p>
                <p><span>Falsyfikator</span>{judgment.falsifier}</p>
                {judgment.gaps.length > 0 && <details className="valuation-scenario-gaps">
                  <summary>Luki wariantu ({judgment.gaps.length})</summary>
                  <ul>{judgment.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
                </details>}
              </div>}
            </article>
          );
        })}
      </div>

      {outputs.probability_weighted?.status === "calculated" && <aside className="valuation-weighted">
        <div><span>Wynik ważony audytowalnym drzewem</span><strong>{fmtPln(outputs.probability_weighted.price_pln)}</strong></div>
        <span className={signClass(outputs.probability_weighted.return_pct)}>{fmtPct(outputs.probability_weighted.return_pct, { signed: true })}</span>
        <small>Postawa: {outputs.final_probabilities?.[0]?.posture ?? "nieznana"}. Procenty są przeliczone z warunkowych gałęzi, nie wpisane jako gotowa odpowiedź.</small>
      </aside>}
      {outputs.probability_weighted?.status === "unavailable" && <aside className="valuation-weighted unavailable">
        <div><span>Wynik ważony</span><strong>Celowo niepublikowany</strong></div>
        <small>{outputs.probability_weighted.gap}</small>
      </aside>}
      <PricedInExpectations outputs={outputs} />
      <ForecastAndSensitivity outputs={outputs} />
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
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const queue = async () => {
    if (!snapshot) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await queueValuation(workspace.research_case_id, {
        research_snapshot_id: snapshot.id,
        as_of: new Date().toISOString(),
      });
      setMessage(result.created
        ? "Zlecono pięcioletnią wycenę: badacz buduje wariant wobec konsensusu, silnik liczy metody, a osobny weryfikator próbuje ją odrzucić."
        : "Wycena dla tego zamrożonego Research już oczekuje lub została opracowana.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (!snapshot || !research.profile || !workspace.template) {
    return <section className="valuation-empty"><IconAlertTriangle size={22} /><h2>Wycena nie jest jeszcze dostępna</h2><p>Potrzebny jest użyteczny snapshot Research i obsługiwany profil spółki.</p></section>;
  }

  const savedStatus = boundValuation ? STATUS[boundValuation.status] : null;
  const auditManifest = boundValuation?.input_manifest ?? null;
  const auditPrice = auditManifest?.price && typeof auditManifest.price === "object" ? auditManifest.price as Record<string, unknown> : null;
  const auditFactIds = Array.isArray(auditManifest?.fact_ids) ? auditManifest.fact_ids : [];

  return <main className="page-stack valuation-workspace">
    <header className="valuation-heading">
      <div>
        <p className="eyebrow">Valuation</p>
        <div className="valuation-title"><h1>{research.research_case.ticker}</h1><span>{research.research_case.name}</span></div>
        <p>Konsensus analityków jest punktem startu. Workbench zbiera dowody, buduje własną ścieżkę i pokazuje dokładnie, gdzie ją potwierdza lub podważa.</p>
      </div>
      <div className="valuation-boundary">
        <span className={`badge ${snapshot.status === "verified" ? "success" : "warning"}`}>Research {snapshot.status === "verified" ? "zweryfikowany" : "prowizoryczny"}</span>
        <strong>snapshot v{snapshot.version} · #{snapshot.id}</strong>
        <small>Stan wiedzy {fmtDate(snapshot.as_of)}</small>
      </div>
    </header>

    <section className="valuation-engine">
      <div><span className="snapshot-label">Silnik</span><strong>Workbench v4</strong><small>pięć lat · P/E · EV/EBITDA · EV/EBIT · FCFF DCF</small></div>
      <div><span className="snapshot-label">Szablon</span><strong>{workspace.template.label}</strong><small>{workspace.template.version}</small></div>
      {savedStatus && <div><span className="snapshot-label">Aktualna użyteczna wycena</span><span className={`badge ${savedStatus.tone}`}>{savedStatus.label}</span><small>wersja {boundValuation!.version}</small></div>}
    </section>

    {staleValuation && <aside className="valuation-stale" role="status">
      <IconLock size={15} /><div><strong>Poprzednia wycena pozostaje wyłącznie w historii</strong><p>Jest związana z Research #{staleValuation.research_snapshot_id}; bieżący Research to #{snapshot.id}.</p></div>
    </aside>}

    <div className="valuation-driver-copy">
      {workspace.template.driver_copy.map((line) => <p key={line}><IconChevronRight size={14} />{line}</p>)}
    </div>

    {boundValuation && <ResultComparison outputs={boundValuation.deterministic_outputs} saved={boundValuation} />}

    <section className="valuation-actions valuation-run-action">
      <button className="btn accent" onClick={() => void queue()} disabled={busy}><IconPlayerPlay size={15} />{busy ? "Zlecam…" : boundValuation ? "Przelicz po nowym Research" : "Zleć pełną wycenę"}</button>
      <span>Nie ma już szybkiego formularza z jednym C/Z. Zlecenie zamraża źródła, wymaga pięcioletniej ścieżki, niezależnych metod i oddzielnego werdyktu.</span>
    </section>
    {error && <div className="error-box" role="alert">{error}</div>}
    {message && <div className="success-box" role="status">{message}</div>}

    {!boundValuation && <section className="valuation-awaiting"><IconPlayerPlay size={20} /><p>Brak użytecznej wyceny dla bieżącego Research. Uruchom pełny przebieg zamiast wpisywać arbitralne scenariusze.</p></section>}

    {boundValuation?.gaps.length ? <section className="valuation-gaps"><IconAlertTriangle size={17} /><div><strong>Luki pokrycia — bez wpływu kierunkowego</strong><ul>{boundValuation.gaps.map((gap) => <li key={gap}>{readableGap(gap)}</li>)}</ul></div></section> : null}

    <details className="valuation-audit">
      <summary><IconLock size={14} /> Równanie i audyt</summary>
      <div className="valuation-audit-content">
        <div><span>Równanie</span><p>{workspace.template.equation}</p></div>
        <div><span>Powiązanie</span><p>Research #{snapshot.id} · profil #{snapshot.company_profile_id} · szablon {workspace.template.id}</p></div>
        {auditManifest && <div><span>Zamrożone wejścia</span><p>Kurs: {typeof auditPrice?.date === "string" ? fmtDate(auditPrice.date) : "—"} · źródło {String(auditPrice?.source_name ?? "brak")} · dokument #{String(auditPrice?.source_document_version_id ?? "brak")}</p><p>Fakty: {auditFactIds.length ? auditFactIds.join(", ") : "brak identyfikatorów"}</p></div>}
        {boundValuation && <div className="valuation-fingerprints"><span>Fingerprinty</span><p>wejście: {boundValuation.input_fingerprint}</p><p>obliczenia: {boundValuation.calculation_fingerprint}</p><p>artefakt: {boundValuation.artifact_fingerprint}</p></div>}
        {boundValuation && <div><span>Weryfikacja</span><p>{boundValuation.verifier_result.summary ?? "Brak podsumowania."}</p><div className="valuation-checks"><span className={boundValuation.verifier_result.verdict === "pass" ? "passed" : "failed"}>{boundValuation.verifier_result.verdict === "pass" ? <IconCheck size={12} /> : <IconAlertTriangle size={12} />}{boundValuation.verifier_result.verdict === "pass" ? "Ocena zaliczona" : "Wymaga korekty"}</span></div>{boundValuation.verifier_result.findings?.map((finding) => <p key={`${finding.area}-${finding.detail}`}><strong>{finding.area}:</strong> {finding.detail}</p>)}</div>}
      </div>
    </details>
  </main>;
}
