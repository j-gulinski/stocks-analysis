"use client";

import {
  IconAlertTriangle,
  IconChartDots,
  IconShieldCheck,
  IconSparkles,
} from "@tabler/icons-react";
import { fmtNumber, fmtPct, fmtTysAsMln, signClass } from "@/lib/format";
import type { Dossier } from "@/lib/types";

type Props = {
  dossier: Dossier;
  onRequestAnalysis: () => void;
};

function ReportList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="company-report-list">
      <h3>{title}</h3>
      {items.length > 0 ? (
        <ul>{items.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul>
      ) : (
        <p className="muted">Brak wystarczających danych.</p>
      )}
    </section>
  );
}

function duplicatesResultQuality(item: string): boolean {
  const normalized = item.toLocaleLowerCase("pl-PL");
  return [
    "zdarzeń jednorazowych",
    "działalność zaniechana",
    "powtarzalność zysku",
  ].some((phrase) => normalized.includes(phrase));
}

export default function CompanyReport({ dossier, onRequestAnalysis }: Props) {
  const latest = dossier.quarters.at(-1);
  const quality = dossier.result_quality;
  const thesis = dossier.thesis;
  const scenarios = dossier.scenarios;
  const valuation = dossier.valuation;
  const unresolved = quality.cause_status === "unresolved_from_stored_evidence";
  const valuationBasis = dossier.ttm.valuation_basis === "continuing"
    ? "działalność kontynuowana"
    : "wynik raportowany";

  const pros = thesis?.pros.map((item) => item.text) ?? dossier.insights.strengths;
  const cons = (thesis?.cons.map((item) => item.text) ?? dossier.insights.concerns)
    .filter((item) => !duplicatesResultQuality(item));
  const checks = (thesis?.verify_next.map((item) => item.text)
    ?? dossier.insights.missing.map((item) => item.name))
    .filter((item) => !duplicatesResultQuality(item));

  return (
    <article className="company-report" aria-label="Przygotowany raport spółki">
      <header className="company-report-header">
        <div>
          <p className="eyebrow">Raport spółki</p>
          <h2>{thesis?.entry_quality.label ?? "Teza robocza"}</h2>
          <p>{thesis?.entry_quality.rationale ?? dossier.insights.summary}</p>
        </div>
        <div className="company-report-status">
          <span className="badge neutral"><IconChartDots size={14} /> szkic deterministyczny</span>
          {unresolved && (
            <span className="badge warning"><IconAlertTriangle size={14} /> wymaga źródła pierwotnego</span>
          )}
        </div>
      </header>

      <section className="key-number-strip company-report-numbers" aria-label="Kluczowe liczby raportu">
        <div>
          <span>Przychody r/r</span>
          <strong className={signClass(latest?.revenue_yoy_pct)}>
            {fmtPct(latest?.revenue_yoy_pct, { signed: true })}
          </strong>
          <small>{latest?.period ?? "brak okresu"}</small>
        </div>
        <div>
          <span>Marża brutto</span>
          <strong>{fmtPct(latest?.gross_margin_pct)}</strong>
          <small>{latest?.period ?? "brak okresu"}</small>
        </div>
        <div>
          <span>C/Z do wyceny</span>
          <strong>{fmtNumber(dossier.ttm.valuation_pe)}</strong>
          <small>{valuationBasis}</small>
        </div>
        <div>
          <span>Potencjał scenariuszowy</span>
          <strong className={signClass(scenarios?.weighted_expected_upside_pct)}>
            {fmtPct(scenarios?.weighted_expected_upside_pct, { signed: true })}
          </strong>
          <small>ważony, nie sygnał</small>
        </div>
      </section>

      {quality.is_material && (
        <section className="company-report-quality">
          <div className="company-report-section-title">
            <IconAlertTriangle size={20} />
            <div>
              <p className="section-label">Jakość wyniku</p>
              <h3>Raportowany zysk nie jest dobrym skrótem wyniku powtarzalnego</h3>
            </div>
          </div>
          <p>{quality.summary}</p>
          <div className="company-report-quality-bridge">
            <div><span>Wynik netto raportowany</span><strong>{fmtTysAsMln(quality.reported_net_profit)}</strong></div>
            <div><span>Działalność zaniechana</span><strong>{fmtTysAsMln(quality.discontinued_profit)}</strong></div>
            <div><span>Wynik kontynuowany</span><strong>{fmtTysAsMln(quality.continuing_net_profit)}</strong></div>
          </div>
          {unresolved && (
            <p className="company-report-source-gap">
              Zapisane sprawozdanie potwierdza klasyfikację i kwoty, ale przyczyna ekonomiczna
              wymaga utrwalonego raportu pierwotnego spółki. Do tego czasu raport pozostaje szkicem.
            </p>
          )}
          {quality.valuation_warning && <p className="company-report-valuation-warning">{quality.valuation_warning}</p>}
        </section>
      )}

      <section className="company-report-lists" aria-label="Najważniejsze czynniki">
        <ReportList title="Najważniejsze argumenty za" items={pros} />
        <ReportList title="Najważniejsze ryzyka" items={cons} />
        <ReportList title="Co sprawdzić następnie" items={checks} />
      </section>

      <section className="company-report-valuation">
        <div className="company-report-section-title">
          <IconShieldCheck size={20} />
          <div><p className="section-label">Wycena i pewność</p><h3>Zakres zamiast jednej obietnicy</h3></div>
        </div>
        {valuation ? (
          <>
            <p>{valuation.narrative}</p>
            <div className="company-report-valuation-line">
              <strong className={signClass(valuation.potential.value_pct)}>
                {fmtPct(valuation.potential.value_pct, { signed: true })}
              </strong>
              {valuation.potential.range_pct && (
                <span>
                  zakres {fmtPct(valuation.potential.range_pct[0], { signed: true })} …{" "}
                  {fmtPct(valuation.potential.range_pct[1], { signed: true })}
                </span>
              )}
              <span className={`badge ${valuation.confidence.level === "low" ? "warning" : "neutral"}`}>
                pewność: {valuation.confidence.level}
              </span>
            </div>
            <p className="small muted">{valuation.confidence.rationale}</p>
          </>
        ) : (
          <p className="muted">Brak wystarczających danych do zakresu wyceny.</p>
        )}
      </section>

      <footer className="company-report-footer">
        <button className="btn accent" type="button" onClick={onRequestAnalysis}>
          <IconSparkles size={15} /> Zleć pełną analizę Codex
        </button>
        <p className="product-disclosure">
          Raport porządkuje zapisane dowody i wspiera research. Nie jest rekomendacją kupna ani sprzedaży.
        </p>
      </footer>
    </article>
  );
}
