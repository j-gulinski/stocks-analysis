"use client";

import {
  IconAlertTriangle,
  IconChartDots,
  IconShieldCheck,
  IconSparkles,
} from "@tabler/icons-react";
import { fmtNumber, fmtPct, fmtTysAsMln, signClass } from "@/lib/format";
import type { AgentRun, AnalysisRun, Dossier } from "@/lib/types";

type Props = {
  dossier: Dossier;
  analysis: AnalysisRun | null;
  analysisJob: AgentRun | null;
  onRequestAnalysis: () => void;
};

type ResearchStatus = "confirmed" | "partial" | "not_found" | "pending";

type ResearchItem = {
  id: "catalyst" | "backlog" | "management_governance";
  label: string;
  status: ResearchStatus;
  finding: string;
  sourceCount: number;
};

const RESEARCH_TOPICS: Array<Pick<ResearchItem, "id" | "label">> = [
  { id: "catalyst", label: "Katalizator" },
  { id: "backlog", label: "Portfel zamówień" },
  { id: "management_governance", label: "Zarząd i ład korporacyjny" },
];

function recordField(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function textField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberField(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function concise(value: string, max = 260): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max).trimEnd()}…`;
}

function confidenceLevel(value: unknown): "high" | "medium" | "low" | "unknown" {
  const row = recordField(value);
  const raw = (textField(row?.level) ?? textField(value) ?? "").toLowerCase();
  if (raw.startsWith("high") || raw.startsWith("wysok")) return "high";
  if (raw.startsWith("medium") || raw.startsWith("śred") || raw.startsWith("umiark")) return "medium";
  if (raw.startsWith("low") || raw.startsWith("nisk")) return "low";
  return "unknown";
}

function confidenceLabel(level: ReturnType<typeof confidenceLevel>): string {
  return { high: "wysoka", medium: "średnia", low: "niska", unknown: "nieustalona" }[level];
}

function confidenceTone(level: ReturnType<typeof confidenceLevel>): string {
  if (level === "high") return "success";
  if (level === "low" || level === "unknown") return "warning";
  return "neutral";
}

function duplicatesResultQuality(item: string): boolean {
  const normalized = item.toLocaleLowerCase("pl-PL");
  return [
    "zdarzeń jednorazowych",
    "działalność zaniechana",
    "powtarzalność zysku",
  ].some((phrase) => normalized.includes(phrase));
}

function isStrategyFitOnly(item: string): boolean {
  const normalized = item.toLocaleLowerCase("pl-PL");
  return normalized.includes("sweet spot") || normalized.includes("przewaga informacyjna");
}

function ReportList({ title, items, emptyText }: { title: string; items: string[]; emptyText?: string }) {
  return (
    <section className="company-report-list">
      <h3>{title}</h3>
      {items.length > 0 ? (
        <ul>{items.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul>
      ) : (
        <p className="muted">{emptyText ?? "Brak wyodrębnionego czynnika w obecnym odczycie."}</p>
      )}
    </section>
  );
}

function pendingResearchFinding(job: AgentRun | null): string {
  if (job?.status === "running") return "Worker Codex sprawdza źródła i raporty pierwotne.";
  if (job?.status === "queued") return "Zlecenie czeka na cykliczny worker Codex.";
  return "Pełny research Codex nie został jeszcze zakończony.";
}

function researchItems(analysis: AnalysisRun | null, job: AgentRun | null): ResearchItem[] {
  const resolution = recordField(analysis?.output.research_resolution);
  return RESEARCH_TOPICS.map(({ id, label }) => {
    const key = id === "management_governance" && !resolution?.[id] ? "management" : id;
    const row = recordField(resolution?.[key]);
    const rawStatus = textField(row?.status);
    const status: ResearchStatus =
      rawStatus === "confirmed" || rawStatus === "partial" || rawStatus === "not_found"
        ? rawStatus
        : "pending";
    const sourceIds = row?.source_ids ?? row?.sources;
    const sourceCount = Array.isArray(sourceIds) ? sourceIds.length : 0;
    return {
      id,
      label,
      status,
      finding: concise(textField(row?.finding) ?? pendingResearchFinding(job), 220),
      sourceCount,
    };
  });
}

function researchStatusLabel(status: ResearchStatus): string {
  return {
    confirmed: "potwierdzone",
    partial: "częściowe",
    not_found: "brak potwierdzenia",
    pending: "w toku",
  }[status];
}

function researchStatusTone(status: ResearchStatus): string {
  if (status === "confirmed") return "success";
  if (status === "partial" || status === "not_found") return "warning";
  return "neutral";
}

function userPrescore(dossier: Dossier): { passed: number; total: number } {
  const checks = dossier.prescore.checks.filter((check) => check.id !== "small_cap");
  return {
    passed: checks.filter((check) => check.verdict === "pass").length,
    total: checks.length,
  };
}

export default function CompanyReport({
  dossier,
  analysis,
  analysisJob,
  onRequestAnalysis,
}: Props) {
  const latest = dossier.quarters.at(-1);
  const quality = dossier.result_quality;
  const thesis = dossier.thesis;
  const scenarios = dossier.scenarios;
  const valuation = dossier.valuation;
  const unresolved = quality.cause_status === "unresolved_from_stored_evidence";
  const verified = analysis?.verification_status === "pass";
  const outputPotential = recordField(analysis?.output.potential);
  const potentialValue =
    numberField(outputPotential?.value_pct) ?? valuation?.potential.value_pct ?? null;
  const confidence = confidenceLevel(analysis?.output.confidence ?? valuation?.confidence);
  const outputScore = recordField(analysis?.output.company_score);
  const verifiedScore =
    numberField(analysis?.output.company_score) ??
    numberField(outputScore?.value) ??
    numberField(analysis?.output.alignment_score) ??
    analysis?.alignment_score ??
    null;
  const valuationBasis = dossier.ttm.valuation_basis === "continuing"
    ? "wynik kontynuowany"
    : "wynik raportowany";
  const prescore = userPrescore(dossier);

  const pros = thesis
    ? thesis.pros.filter((item) => item.id !== "size").map((item) => item.text)
    : dossier.insights.strengths.filter((item) => !isStrategyFitOnly(item));
  const cons = thesis
    ? thesis.cons
        .filter((item) => item.id !== "size")
        .map((item) => item.text)
        .filter((item) => !duplicatesResultQuality(item))
    : dossier.insights.concerns.filter(
        (item) => !isStrategyFitOnly(item) && !duplicatesResultQuality(item),
      );
  const resolvedResearch = researchItems(analysis, analysisJob);
  const executiveRead = textField(analysis?.output.executive_read);
  const reportTitle = verified ? "Zweryfikowany odczyt Codex" : "Szkic analityczny";
  const reportLead = verified && executiveRead
    ? concise(executiveRead)
    : "Skrót z zapisanych faktów i scenariuszy; pełny wniosek pojawi się dopiero po niezależnej weryfikacji.";

  return (
    <article className="company-report" aria-label="Przygotowany raport spółki">
      <header className="company-report-header">
        <div>
          <p className="eyebrow">Raport spółki</p>
          <h2>{reportTitle}</h2>
          <p>{reportLead}</p>
        </div>
        <div className="company-report-status">
          <span className={`badge ${verified ? "success" : "neutral"}`}>
            <IconChartDots size={14} /> {verified ? "zweryfikowany" : "szkic deterministyczny"}
          </span>
          {analysisJob && (analysisJob.status === "queued" || analysisJob.status === "running") && (
            <span className="badge accent">
              <IconSparkles size={14} /> {analysisJob.status === "running" ? "Codex pracuje" : "Codex w kolejce"}
            </span>
          )}
        </div>
      </header>

      <section className="company-report-summary" aria-label="Podsumowanie decyzji">
        <div>
          <span>Szacowany potencjał</span>
          <strong className={signClass(potentialValue)}>{fmtPct(potentialValue, { signed: true })}</strong>
          <small>wartość ważona scenariuszami</small>
        </div>
        <div>
          <span>Pewność scenariusza</span>
          <strong>{confidenceLabel(confidence)}</strong>
          <small>jakość danych i spójność scenariuszy</small>
        </div>
        <div>
          <span>{verifiedScore == null ? "Sito danych" : "Ocena spółki"}</span>
          <strong>{verifiedScore == null ? `${prescore.passed}/${prescore.total}` : `${Math.round(verifiedScore)}/100`}</strong>
          <small>{verifiedScore == null ? "bez kryterium rozmiaru" : "ocena po verifierze"}</small>
        </div>
        <div>
          <span>Podstawa wyceny</span>
          <strong>{fmtNumber(dossier.ttm.valuation_pe)}</strong>
          <small>C/Z · {valuationBasis}</small>
        </div>
      </section>

      <section className="company-report-operating" aria-label="Najważniejsze dane operacyjne">
        <span>Przychody r/r <strong className={signClass(latest?.revenue_yoy_pct)}>{fmtPct(latest?.revenue_yoy_pct, { signed: true })}</strong></span>
        <span>Marża brutto <strong>{fmtPct(latest?.gross_margin_pct)}</strong></span>
        <span>Okres <strong>{latest?.period ?? "b/d"}</strong></span>
      </section>

      {quality.is_material && (
        <section className="company-report-quality">
          <div className="company-report-section-title">
            <IconAlertTriangle size={20} />
            <div>
              <p className="section-label">Jakość wyniku</p>
              <h3>Wycena nie opiera się na zawyżonym wyniku raportowanym</h3>
            </div>
          </div>
          <p>{quality.summary}</p>
          <div className="company-report-quality-bridge">
            <div><span>Wynik raportowany</span><strong>{fmtTysAsMln(quality.reported_net_profit)}</strong></div>
            <div><span>Działalność zaniechana</span><strong>{fmtTysAsMln(quality.discontinued_profit)}</strong></div>
            <div><span>Wynik kontynuowany</span><strong>{fmtTysAsMln(quality.continuing_net_profit)}</strong></div>
          </div>
          {unresolved && (
            <p className="company-report-source-gap">
              Klasyfikacja i kwoty są zapisane; ekonomiczna przyczyna nadal wymaga utrwalonego raportu pierwotnego.
            </p>
          )}
          {quality.valuation_warning && <p className="company-report-valuation-warning">{quality.valuation_warning}</p>}
        </section>
      )}

      <section className="company-report-lists" aria-label="Najważniejsze czynniki">
        <ReportList title="Najważniejsze argumenty za" items={pros} />
        <ReportList
          title="Najważniejsze ryzyka"
          items={cons}
          emptyText={quality.is_material ? "Główne ryzyko opisano wyżej w sekcji jakości wyniku." : undefined}
        />
      </section>

      <section className="company-report-research" aria-label="Badania Codex">
        <div className="company-report-section-title">
          <IconSparkles size={20} />
          <div>
            <p className="section-label">Badania Codex</p>
            <h3>Katalizator, backlog i jakość zarządu</h3>
          </div>
        </div>
        <div className="company-report-research-grid">
          {resolvedResearch.map((item) => (
            <div key={item.id}>
              <span className={`badge ${researchStatusTone(item.status)}`}>{researchStatusLabel(item.status)}</span>
              <strong>{item.label}</strong>
              <p>{item.finding}</p>
              {item.sourceCount > 0 && <small>{item.sourceCount} zapisane źródła</small>}
            </div>
          ))}
        </div>
      </section>

      <section className="company-report-valuation">
        <div className="company-report-section-title">
          <IconShieldCheck size={20} />
          <div><p className="section-label">Zakres scenariuszy</p><h3>Warunki zamiast jednej obietnicy</h3></div>
        </div>
        {valuation ? (
          <>
            <div className="company-report-valuation-line">
              <strong className={signClass(potentialValue)}>{fmtPct(potentialValue, { signed: true })}</strong>
              {valuation.potential.range_pct && (
                <span>
                  zakres {fmtPct(valuation.potential.range_pct[0], { signed: true })} …{" "}
                  {fmtPct(valuation.potential.range_pct[1], { signed: true })}
                </span>
              )}
              <span className={`badge ${confidenceTone(confidence)}`}>pewność: {confidenceLabel(confidence)}</span>
            </div>
            {valuation.confidence.rationale && (
              <details className="company-report-rationale">
                <summary>Dlaczego taki poziom pewności?</summary>
                <p>{valuation.confidence.rationale}</p>
              </details>
            )}
          </>
        ) : (
          <p className="muted">Brak wystarczających danych do zakresu wyceny.</p>
        )}
      </section>

      <footer className="company-report-footer">
        <button className="btn accent" type="button" onClick={onRequestAnalysis}>
          <IconSparkles size={15} /> {analysisJob ? "Pokaż pracę Codex" : "Zleć pełną analizę Codex"}
        </button>
        <p className="product-disclosure">
          Raport porządkuje zapisane dowody i wspiera research. Nie jest rekomendacją kupna ani sprzedaży.
        </p>
      </footer>
    </article>
  );
}
