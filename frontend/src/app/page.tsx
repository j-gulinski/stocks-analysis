"use client";

/** Watchlist dashboard (`/`) — layout per docs/design/mockups.html screen 1. */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  IconArrowRight,
  IconAlertTriangle,
  IconBrain,
  IconChartDots,
  IconCircleCheck,
  IconClockExclamation,
  IconDatabase,
  IconPlus,
  IconRefresh,
  IconShieldCheck,
  IconTrash,
  IconTrendingDown,
  IconTrendingUp,
} from "@tabler/icons-react";
import {
  addToWatchlist,
  getAgentEvaluationRun,
  getDossier,
  getBacktestRun,
  listAgentEvaluationRuns,
  listAgentRuns,
  listBacktestRuns,
  preparePreSessionBrief,
  queueAgentRun,
  getWatchlist,
  refreshCompany,
  removeFromWatchlist,
  runAgentEvaluation,
  runBacktest,
} from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { hasDossierData } from "@/lib/dossier";
import { fmtMcap, fmtNumber, fmtPct, fmtPln, relativeDate, signClass, staleDays } from "@/lib/format";
import type {
  AgentEvaluationObservation,
  AgentEvaluationRun,
  AgentEvaluationRunDetail,
  AgentRun,
  BacktestObservation,
  BacktestRun,
  BacktestRunDetail,
  Dossier,
} from "@/lib/types";

interface Row {
  ticker: string;
  name: string | null;
  dossier: Dossier | null;
  refreshing: boolean;
}

function MarginTrend({ dossier }: { dossier: Dossier | null }) {
  const quarters = dossier?.quarters ?? [];
  const current = quarters.at(-1)?.gross_margin_pct ?? null;
  const previous = quarters.at(-2)?.gross_margin_pct ?? null;
  if (current == null) return <span className="muted">—</span>;
  if (previous == null || Math.abs(current - previous) < 0.05)
    return (
      <span className="secondary">
        {fmtPct(current)} <IconArrowRight size={13} />
      </span>
    );
  const up = current > previous;
  return (
    <span className={up ? "pos" : "neg"}>
      {fmtPct(current)} {up ? <IconTrendingUp size={14} /> : <IconTrendingDown size={14} />}
    </span>
  );
}

function entryTone(code: string | undefined): string {
  if (code === "attractive") return "success";
  if (code === "neutral") return "warning";
  if (code === "weak") return "danger";
  return "muted";
}

function scoreTone(dossier: Dossier | null): string {
  if (!dossier || dossier.prescore.total <= 0) return "muted";
  const ratio = dossier.prescore.passed / dossier.prescore.total;
  if (ratio >= 0.75) return "success";
  if (ratio >= 0.5) return "warning";
  return "danger";
}

function stockRead(dossier: Dossier | null): { label: string; detail: string } {
  if (!dossier) {
    return { label: "Dossier w budowie", detail: "Trwa pobieranie danych źródłowych." };
  }
  if (dossier.thesis?.entry_quality) {
    return {
      label: dossier.thesis.entry_quality.label,
      detail: dossier.thesis.entry_quality.rationale,
    };
  }
  const signal = dossier.insights.strengths[0] ?? dossier.insights.summary;
  return { label: dossier.insights.summary, detail: signal };
}

function topRisk(dossier: Dossier | null): string {
  if (!dossier) return "brak danych";
  return dossier.insights.concerns[0] ?? dossier.insights.missing[0]?.why ?? "brak dużej flagi";
}

const CLAIM_TRUNCATE_LEN = 90;
const DISCOVERY_FILTERS = [
  {
    title: "1. Skala przychodów",
    text: "Przychody r/r > 25% w ostatnim kwartale albo dwa kolejne kwartały dodatnie.",
  },
  {
    title: "2. Jakość marży",
    text: "Marża brutto stabilna lub rosnąca; unikaj wzrostu kupionego spadkiem rentowności.",
  },
  {
    title: "3. Czysty wynik",
    text: "One-offy niskie, zysk ze sprzedaży rośnie razem z przychodami, spółka jest rentowna TTM.",
  },
  {
    title: "4. Cena jeszcze nie krzyczy",
    text: "C/Z poniżej własnej historii albo scenariusze nie pokazują, że rynek już wycenił poprawę.",
  },
  {
    title: "5. Rozmiar daje przewagę",
    text: "Preferuj małe i średnie spółki; duże firmy wymagają mocniejszego katalizatora.",
  },
];

/** The single most useful line about forum sentiment for this row: the top
 * AI-distilled expectation claim when available, else the old raw counts. */
function forumHeadline(dossier: Dossier | null): string | null {
  if (!dossier) return null;
  const topClaim = dossier.forum.intelligence?.expectations?.claims?.[0]?.claim;
  if (topClaim) {
    return topClaim.length > CLAIM_TRUNCATE_LEN
      ? `${topClaim.slice(0, CLAIM_TRUNCATE_LEN).trimEnd()}…`
      : topClaim;
  }
  if (dossier.forum.posts > 0) {
    return `${dossier.forum.posts} postów, ${dossier.forum.topics} wątków`;
  }
  return null;
}

function valuationText(dossier: Dossier | null): {
  upside: number | null;
  label: string;
} {
  if (!dossier) return { upside: null, label: "brak scenariuszy" };
  const upside =
    dossier.scenarios?.weighted_expected_upside_pct ??
    dossier.valuation?.potential.value_pct ??
    null;
  const label = dossier.scenarios
    ? "EV scenariuszy"
    : dossier.valuation
      ? dossier.valuation.potential.basis_label
      : "brak scenariuszy";
  return { upside, label };
}

function scalingRead(dossier: Dossier | null): {
  score: number;
  label: string;
  tone: string;
  reasons: string[];
} {
  if (!dossier || !hasDossierData(dossier)) {
    return { score: 0, label: "brak danych", tone: "muted", reasons: ["odśwież dossier"] };
  }

  const quarters = dossier.quarters;
  const last = quarters.at(-1);
  const previous = quarters.at(-2);
  const revenueYoy = last?.revenue_yoy_pct ?? null;
  const grossMargin = last?.gross_margin_pct ?? null;
  const previousGrossMargin = previous?.gross_margin_pct ?? null;
  const oneOff = last?.one_off_share_pct ?? null;
  const upside =
    dossier.scenarios?.weighted_expected_upside_pct ??
    dossier.valuation?.potential.value_pct ??
    null;
  const pe = dossier.ttm.pe;
  const peMedian = dossier.pe_history.median;
  const mcap = dossier.ttm.market_cap;

  let score = 0;
  const reasons: string[] = [];

  if (revenueYoy != null && revenueYoy >= 30) {
    score += 30;
    reasons.push(`przychody ${fmtPct(revenueYoy, { signed: true })} r/r`);
  } else if (revenueYoy != null && revenueYoy >= 15) {
    score += 20;
    reasons.push(`przychody ${fmtPct(revenueYoy, { signed: true })} r/r`);
  } else if (revenueYoy != null && revenueYoy > 0) {
    score += 8;
    reasons.push(`wzrost przychodów ${fmtPct(revenueYoy, { signed: true })}`);
  }

  if (grossMargin != null && previousGrossMargin != null && grossMargin > previousGrossMargin) {
    score += 15;
    reasons.push(`marża br. rośnie do ${fmtPct(grossMargin)}`);
  } else if (grossMargin != null && grossMargin >= 25) {
    score += 10;
    reasons.push(`marża br. ${fmtPct(grossMargin)}`);
  }

  if (oneOff != null && oneOff <= 5) {
    score += 15;
    reasons.push("wynik bez dużych one-offów");
  } else if (oneOff != null && oneOff <= 15) {
    score += 8;
    reasons.push("one-offy pod kontrolą");
  }

  if (pe != null && peMedian != null && peMedian > 0 && pe < peMedian * 0.85) {
    score += 15;
    reasons.push(`C/Z ${fmtNumber(pe)} poniżej historii`);
  } else if (upside != null && upside > 20) {
    score += 10;
    reasons.push(`scenariusze ${fmtPct(upside, { signed: true })}`);
  }

  if (mcap != null && mcap < 1_000_000_000) {
    score += 10;
    reasons.push("mała spółka");
  } else if (mcap != null && mcap < 5_000_000_000) {
    score += 5;
    reasons.push("jeszcze nie moloch");
  }

  if (dossier.analysis_context_status?.ready_for_ai) score += 10;
  if ((dossier.forum.intelligence?.expectations?.claims.length ?? 0) > 0) score += 5;

  const capped = Math.min(100, score);
  if (capped >= 70 && upside != null && upside < 0) {
    return { score: capped, label: "Skaluje, drogo", tone: "warning", reasons };
  }
  if (capped >= 70) return { score: capped, label: "Kandydat skali", tone: "success", reasons };
  if (capped >= 45) return { score: capped, label: "Obserwuj wzrost", tone: "warning", reasons };
  return { score: capped, label: "Za wcześnie", tone: "muted", reasons };
}

function runStatusTone(status: string): string {
  if (status === "verified") return "success";
  if (status === "completed") return "success";
  if (status === "rejected" || status === "failed") return "danger";
  if (status === "running") return "accent";
  if (status === "needs-human" || status === "draft" || status === "pending") {
    return "warning";
  }
  return "neutral";
}

function verificationTone(status: string): string {
  if (status === "pass") return "success";
  if (status === "fail") return "danger";
  if (status === "needs-human") return "warning";
  return runStatusTone(status);
}

function workflowLabel(workflow: string): string {
  const labels: Record<string, string> = {
    "stock-pre-session-brief": "Pre-session brief",
    "stock-quick-analysis": "Quick analysis",
    "stock-deep-analysis": "Deep analysis",
    "stock-candidate-scout": "Candidate scout",
    "stock-backtest-review": "Backtest review",
    "stock-verifier": "Verifier",
  };
  return labels[workflow] ?? workflow;
}

function agentModelLine(run: AgentRun): string {
  const role = run.model_role ?? "role pending";
  const model = run.model ?? run.orchestrator_model ?? "model chosen by Codex";
  return `${role} · ${model}`;
}

function avgReturnText(run: BacktestRun): string {
  const averages = run.summary.average_return_pct_by_window ?? {};
  const entries = Object.entries(averages).filter(([, value]) => value != null);
  if (entries.length === 0) return "brak pełnych okien wyniku";
  return entries
    .slice(0, 3)
    .map(([days, value]) => `${days}d ${fmtPct(value, { signed: true })}`)
    .join(" · ");
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function agentRunOutputId(run: AgentRun): string | null {
  const value = run.outputs?.analysis_run_id;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return textValue(value);
}

function agentRunLifecycleText(run: AgentRun): string {
  if (run.status === "queued") return "waiting for Codex/MCP worker";
  if (run.status === "running") return "worker claimed";
  if (run.status === "completed" || run.status === "verified") return "worker closed";
  if (run.status === "needs-human") return "needs verifier/human review";
  if (run.status === "rejected" || run.status === "failed") return run.error ?? "failed/rejected";
  return "recorded";
}

function backtestWarnings(run: BacktestRun): string[] {
  const dataQuality = asRecord(run.summary.data_quality);
  const warnings = dataQuality.warnings;
  return Array.isArray(warnings)
    ? warnings.filter((warning): warning is string => typeof warning === "string")
    : [];
}

function backtestResearchOnly(run: BacktestRun): boolean {
  return asRecord(run.summary.data_quality).research_only === true;
}

function signalTone(label: string | null): string {
  if (label === "candidate") return "success";
  if (label === "watch") return "warning";
  if (label === "reject") return "danger";
  return "muted";
}

function observationTicker(observation: BacktestObservation): string {
  const company = asRecord(observation.known_inputs.company);
  return textValue(company.ticker) ?? "—";
}

function observationFinancials(observation: BacktestObservation): Record<string, unknown> {
  return asRecord(observation.known_inputs.financials);
}

function observationPrice(observation: BacktestObservation): Record<string, unknown> {
  return asRecord(observation.known_inputs.price);
}

function observationSignal(observation: BacktestObservation): Record<string, unknown> {
  return asRecord(observation.signal);
}

function observationOutcomes(observation: BacktestObservation): [string, Record<string, unknown>][] {
  const windows = asRecord(asRecord(observation.outcome).windows);
  return Object.entries(windows).map(([window, value]) => [window, asRecord(value)]);
}

function agentEvaluationWarnings(run: AgentEvaluationRun): string[] {
  const dataQuality = asRecord(run.summary.data_quality);
  const warnings = dataQuality.warnings;
  return Array.isArray(warnings)
    ? warnings.filter((warning): warning is string => typeof warning === "string")
    : [];
}

function evaluationHitRateText(run: AgentEvaluationRun): string {
  const observations = numberValue(run.summary.observation_count) ?? 0;
  const hitRate = numberValue(run.summary.hit_rate_pct);
  if (hitRate == null) return `${observations} obs · brak okien do oceny`;
  return `${observations} obs · hit ${fmtPct(hitRate)}`;
}

function predictionTone(direction: string | null): string {
  if (direction === "positive") return "success";
  if (direction === "negative") return "danger";
  if (direction === "neutral") return "warning";
  return "muted";
}

function evaluationScoreTone(status: string | null, hit: unknown): string {
  if (status === "missing_outcome") return "muted";
  if (status === "not_scored") return "warning";
  if (hit === true) return "success";
  if (hit === false) return "danger";
  return "muted";
}

function evaluationTicker(observation: AgentEvaluationObservation): string {
  return textValue(observation.known_inputs.ticker) ?? `company #${observation.company_id}`;
}

function evaluationPrediction(
  observation: AgentEvaluationObservation,
): Record<string, unknown> {
  return asRecord(observation.prediction);
}

function evaluationOutcomeWindows(
  observation: AgentEvaluationObservation,
): [string, Record<string, unknown>][] {
  const windows = asRecord(asRecord(observation.outcome).windows);
  return Object.entries(windows).map(([window, value]) => [window, asRecord(value)]);
}

function evaluationScoreWindows(
  observation: AgentEvaluationObservation,
): Record<string, Record<string, unknown>> {
  const windows = asRecord(asRecord(observation.score).windows);
  return Object.fromEntries(
    Object.entries(windows).map(([window, value]) => [window, asRecord(value)]),
  );
}

function BacktestDetailPanel({ run }: { run: BacktestRunDetail }) {
  const parameters = asRecord(run.parameters);
  const policy = textValue(parameters.financial_availability_policy) ?? "scraped_at";
  const lagDays = numberValue(parameters.report_lag_days);
  const warnings = backtestWarnings(run);
  const researchOnly = backtestResearchOnly(run);

  return (
    <div className="backtest-detail">
      <div className="spread wrap">
        <div>
          <p className="analysis-title">Run #{run.id} detail</p>
          <p className="small muted">
            {run.strategy} · {run.from_date} - {run.to_date} · {run.observations.length} observations
          </p>
        </div>
        <div className="row wrap">
          <span className={`badge ${verificationTone(run.verification_status)}`}>
            verifier: {run.verification_status}
          </span>
          <span className={`badge ${researchOnly ? "warning" : "success"}`}>
            {policy}{lagDays != null ? ` · ${lagDays}d` : ""}
          </span>
        </div>
      </div>

      <p className="small muted" style={{ margin: "8px 0 0", lineHeight: 1.5 }}>
        {run.summary.known_inputs_policy ?? "No policy note saved."}
      </p>

      {warnings.length > 0 && (
        <div className="backtest-warnings">
          {warnings.map((warning) => (
            <p key={warning}>
              <IconAlertTriangle size={14} /> {warning}
            </p>
          ))}
        </div>
      )}

      <div className="backtest-observation-list">
        {run.observations.map((observation) => {
          const signal = observationSignal(observation);
          const label = textValue(signal.label) ?? "unknown";
          const score = numberValue(signal.score);
          const total = numberValue(signal.total);
          const financials = observationFinancials(observation);
          const price = observationPrice(observation);
          const checks = Array.isArray(signal.checks) ? signal.checks : [];
          const outcomes = observationOutcomes(observation);
          return (
            <div className="backtest-observation" key={observation.id}>
              <div className="spread wrap">
                <div>
                  <strong>{observationTicker(observation)}</strong>
                  <span className="cell-note">
                    {observation.as_of_date} · period{" "}
                    {textValue(financials.latest_income_period) ?? "unknown"} · price{" "}
                    {fmtNumber(numberValue(price.close))}
                  </span>
                </div>
                <span className={`badge ${signalTone(label)}`}>
                  {label}{score != null ? ` ${score}${total != null ? `/${total}` : ""}` : ""}
                </span>
              </div>

              {checks.length > 0 && (
                <div className="backtest-checks">
                  {checks.slice(0, 4).map((check, index) => {
                    const row = asRecord(check);
                    const verdict = textValue(row.verdict) ?? "unknown";
                    return (
                      <p key={`${observation.id}-${index}`}>
                        <span className={`badge ${verdict === "pass" ? "success" : verdict === "fail" ? "danger" : "muted"}`}>
                          {textValue(row.id) ?? "check"}: {verdict}
                        </span>
                        <span>{textValue(row.evidence) ?? "No evidence text."}</span>
                      </p>
                    );
                  })}
                </div>
              )}

              {outcomes.length > 0 && (
                <div className="outcome-strip">
                  {outcomes.map(([window, outcome]) => {
                    const returnPct = numberValue(outcome.return_pct);
                    return (
                      <span key={`${observation.id}-${window}`}>
                        {window}d:{" "}
                        {returnPct == null ? "b/d" : fmtPct(returnPct, { signed: true })}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AgentEvaluationDetailPanel({ run }: { run: AgentEvaluationRunDetail }) {
  const parameters = asRecord(run.parameters);
  const policy = textValue(parameters.prediction_policy) ?? "Structured predictions only.";
  const warnings = agentEvaluationWarnings(run);

  return (
    <div className="backtest-detail">
      <div className="spread wrap">
        <div>
          <p className="analysis-title">Evaluation #{run.id} detail</p>
          <p className="small muted">
            {run.strategy} · {run.observations.length} saved analyses ·{" "}
            {textValue(parameters.workflow) ?? "all workflows"}
          </p>
        </div>
        <div className="row wrap">
          <span className={`badge ${verificationTone(run.verification_status)}`}>
            verifier: {run.verification_status}
          </span>
          <span className={`badge ${runStatusTone(run.status)}`}>{run.status}</span>
        </div>
      </div>

      <p className="small muted" style={{ margin: "8px 0 0", lineHeight: 1.5 }}>
        {policy}
      </p>

      {warnings.length > 0 && (
        <div className="backtest-warnings">
          {warnings.map((warning) => (
            <p key={warning}>
              <IconAlertTriangle size={14} /> {warning}
            </p>
          ))}
        </div>
      )}

      <div className="backtest-observation-list">
        {run.observations.map((observation) => {
          const prediction = evaluationPrediction(observation);
          const direction = textValue(prediction.direction) ?? "unknown";
          const source = textValue(prediction.source) ?? "unknown";
          const confidence = textValue(prediction.confidence) ?? "unknown";
          const potential = numberValue(prediction.potential_pct);
          const outcomes = evaluationOutcomeWindows(observation);
          const scores = evaluationScoreWindows(observation);
          const hitRate = numberValue(observation.score.hit_rate_pct);
          return (
            <div className="backtest-observation" key={observation.id}>
              <div className="spread wrap">
                <div>
                  <strong>{evaluationTicker(observation)}</strong>
                  <span className="cell-note">
                    {observation.as_of_date} · analysis #{observation.analysis_run_id} ·{" "}
                    {textValue(observation.known_inputs.model_role) ?? "role?"} /{" "}
                    {textValue(observation.known_inputs.model) ?? "model?"}
                  </span>
                </div>
                <span className={`badge ${predictionTone(direction)}`}>
                  {direction}
                  {potential != null ? ` ${fmtPct(potential, { signed: true })}` : ""}
                </span>
              </div>

              <div className="backtest-checks">
                <p>
                  <span className="badge neutral">source</span>
                  <span>
                    {source} · confidence {confidence}
                  </span>
                </p>
                <p>
                  <span className="badge neutral">score</span>
                  <span>
                    {hitRate == null ? "not scored" : `hit ${fmtPct(hitRate)}`}
                  </span>
                </p>
              </div>

              {outcomes.length > 0 && (
                <div className="outcome-strip">
                  {outcomes.map(([window, outcome]) => {
                    const returnPct = numberValue(outcome.return_pct);
                    const score = scores[window] ?? {};
                    const status = textValue(score.status);
                    return (
                      <span
                        className={evaluationScoreTone(status, score.hit)}
                        key={`${observation.id}-${window}`}
                      >
                        {window}d:{" "}
                        {returnPct == null ? "b/d" : fmtPct(returnPct, { signed: true })} ·{" "}
                        {status ?? "unknown"}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function WatchlistPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newTicker, setNewTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentLoading, setAgentLoading] = useState(true);
  const [agentAction, setAgentAction] = useState<"pre-session" | "candidate" | null>(
    null,
  );
  const [agentError, setAgentError] = useState<string | null>(null);
  const [backtestRuns, setBacktestRuns] = useState<BacktestRun[]>([]);
  const [backtestLoading, setBacktestLoading] = useState(true);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [backtestTicker, setBacktestTicker] = useState("");
  const [backtestFrom, setBacktestFrom] = useState("2024-01-01");
  const [backtestTo, setBacktestTo] = useState("2026-07-09");
  const [backtestPolicy, setBacktestPolicy] = useState<"scraped_at" | "estimated_period_lag">(
    "scraped_at",
  );
  const [backtestLagDays, setBacktestLagDays] = useState(120);
  const [selectedBacktestRunId, setSelectedBacktestRunId] = useState<number | null>(null);
  const [backtestDetailById, setBacktestDetailById] = useState<
    Record<number, BacktestRunDetail>
  >({});
  const [backtestDetailLoadingId, setBacktestDetailLoadingId] = useState<number | null>(
    null,
  );
  const [agentEvaluationRuns, setAgentEvaluationRuns] = useState<AgentEvaluationRun[]>(
    [],
  );
  const [agentEvaluationLoading, setAgentEvaluationLoading] = useState(true);
  const [agentEvaluationRunning, setAgentEvaluationRunning] = useState(false);
  const [agentEvaluationError, setAgentEvaluationError] = useState<string | null>(null);
  const [agentEvaluationTicker, setAgentEvaluationTicker] = useState("");
  const [agentEvaluationWorkflow, setAgentEvaluationWorkflow] = useState("");
  const [agentEvaluationFrom, setAgentEvaluationFrom] = useState("");
  const [agentEvaluationTo, setAgentEvaluationTo] = useState("");
  const [selectedAgentEvaluationRunId, setSelectedAgentEvaluationRunId] = useState<
    number | null
  >(null);
  const [agentEvaluationDetailById, setAgentEvaluationDetailById] = useState<
    Record<number, AgentEvaluationRunDetail>
  >({});
  const [agentEvaluationDetailLoadingId, setAgentEvaluationDetailLoadingId] = useState<
    number | null
  >(null);

  const loadDossier = useCallback(async (ticker: string) => {
    try {
      return await getDossier(ticker);
    } catch {
      return null;
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await getWatchlist();
      const dossiers = await Promise.all(items.map((i) => loadDossier(i.ticker)));
      setRows(
        items.map((item, index) => ({
          ticker: item.ticker,
          name: item.name,
          dossier: dossiers[index],
          refreshing: false,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [loadDossier]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const loadAgentRuns = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    if (!silent) setAgentLoading(true);
    try {
      setAgentRuns(await listAgentRuns({ limit: 8 }));
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!silent) setAgentLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAgentRuns();
    const pollId = window.setInterval(() => {
      void loadAgentRuns({ silent: true });
    }, 30_000);
    return () => window.clearInterval(pollId);
  }, [loadAgentRuns]);

  const loadBacktestRuns = useCallback(async () => {
    setBacktestLoading(true);
    try {
      setBacktestRuns(await listBacktestRuns({ limit: 5 }));
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : String(err));
    } finally {
      setBacktestLoading(false);
    }
  }, []);

  const handleSelectBacktest = async (runId: number) => {
    setSelectedBacktestRunId((current) => (current === runId ? null : runId));
    if (selectedBacktestRunId === runId || backtestDetailById[runId]) return;
    setBacktestDetailLoadingId(runId);
    setBacktestError(null);
    try {
      const detail = await getBacktestRun(runId);
      setBacktestDetailById((current) => ({ ...current, [runId]: detail }));
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : String(err));
    } finally {
      setBacktestDetailLoadingId(null);
    }
  };

  useEffect(() => {
    void loadBacktestRuns();
  }, [loadBacktestRuns]);

  const loadAgentEvaluationRuns = useCallback(async () => {
    setAgentEvaluationLoading(true);
    try {
      setAgentEvaluationRuns(await listAgentEvaluationRuns({ limit: 5 }));
    } catch (err) {
      setAgentEvaluationError(err instanceof Error ? err.message : String(err));
    } finally {
      setAgentEvaluationLoading(false);
    }
  }, []);

  const handleSelectAgentEvaluation = async (runId: number) => {
    setSelectedAgentEvaluationRunId((current) => (current === runId ? null : runId));
    if (selectedAgentEvaluationRunId === runId || agentEvaluationDetailById[runId]) return;
    setAgentEvaluationDetailLoadingId(runId);
    setAgentEvaluationError(null);
    try {
      const detail = await getAgentEvaluationRun(runId);
      setAgentEvaluationDetailById((current) => ({ ...current, [runId]: detail }));
    } catch (err) {
      setAgentEvaluationError(err instanceof Error ? err.message : String(err));
    } finally {
      setAgentEvaluationDetailLoadingId(null);
    }
  };

  useEffect(() => {
    void loadAgentEvaluationRuns();
  }, [loadAgentEvaluationRuns]);

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    const ticker = newTicker.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    setError(null);
    let createdTicker: string | null = null;
    try {
      const created = await addToWatchlist(ticker);
      createdTicker = created.ticker;
      setNewTicker("");
      setRows((current) => [
        ...current.filter((row) => row.ticker !== created.ticker),
        {
          ticker: created.ticker,
          name: created.name,
          dossier: null,
          refreshing: true,
        },
      ]);
      setAdding(false);

      const result = await refreshCompany(created.ticker, true);
      const failed = Object.entries(result.summary).filter(
        ([, s]) => !s.startsWith("ok") && s !== "cached" && !s.startsWith("pominięto"),
      );
      if (failed.length > 0) {
        setError(
          `${created.ticker}: dane dodane, ale część źródeł wymaga uwagi (${failed
            .map(([k]) => k)
            .join(", ")}).`,
        );
      }
      const dossier = await loadDossier(created.ticker);
      setRows((current) =>
        current.map((row) =>
          row.ticker === created.ticker
            ? {
                ...row,
                dossier,
                name: dossier?.company.name ?? row.name,
                refreshing: false,
              }
            : row,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if (createdTicker) setRefreshing(createdTicker, false);
    } finally {
      setAdding(false);
    }
  };

  const setRefreshing = (ticker: string, refreshing: boolean) =>
    setRows((current) =>
      current.map((r) => (r.ticker === ticker ? { ...r, refreshing } : r)),
    );

  const handleRefresh = async (ticker: string, force = false) => {
    setRefreshing(ticker, true);
    setError(null);
    try {
      const result = await refreshCompany(ticker, force);
      const failed = Object.entries(result.summary).filter(
        ([, s]) => !s.startsWith("ok") && s !== "cached" && !s.startsWith("pominięto"),
      );
      if (failed.length > 0) {
        setError(
          `${ticker}: część źródeł z problemami (${failed
            .map(([k]) => k)
            .join(", ")}) — szczegóły na stronie spółki po odświeżeniu.`,
        );
      }
      const dossier = await loadDossier(ticker);
      setRows((current) =>
        current.map((r) =>
          r.ticker === ticker
            ? { ...r, dossier, name: dossier?.company.name ?? r.name, refreshing: false }
            : r,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRefreshing(ticker, false);
    }
  };

  const handleRefreshAll = async () => {
    // Sequential on purpose — one polite scrape pipeline at a time.
    for (const row of rows) {
      // eslint-disable-next-line no-await-in-loop
      await handleRefresh(row.ticker);
    }
  };

  const handleRemove = async (ticker: string) => {
    if (!window.confirm(`Usunąć ${ticker} z watchlisty?`)) return;
    await removeFromWatchlist(ticker);
    setRows((current) => current.filter((r) => r.ticker !== ticker));
  };

  const handlePreSession = async () => {
    setAgentAction("pre-session");
    setAgentError(null);
    try {
      await preparePreSessionBrief({
        trigger: "ui-request",
        orchestrator_model: "gpt-5.5",
      });
      await loadAgentRuns();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err));
    } finally {
      setAgentAction(null);
    }
  };

  const handleCandidateScout = async () => {
    setAgentAction("candidate");
    setAgentError(null);
    try {
      await queueAgentRun({
        workflow: "stock-candidate-scout",
        trigger: "ui-request",
        model_role: "worker_standard",
        orchestrator_model: "gpt-5.5",
        inputs: {
          objective: "Rank stored companies and watched tickers for the next manual review.",
          required_verification: "stock-verifier before any promotion to watchlist",
        },
      });
      await loadAgentRuns();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err));
    } finally {
      setAgentAction(null);
    }
  };

  const handleRunBacktest = async (event: React.FormEvent) => {
    event.preventDefault();
    setBacktestRunning(true);
    setBacktestError(null);
    try {
      const created = await runBacktest({
        strategy: "malik_v1",
        from_date: backtestFrom,
        to_date: backtestTo,
        ticker: backtestTicker.trim() ? backtestTicker.trim().toUpperCase() : undefined,
        outcome_windows: [30, 90, 180, 365],
        financial_availability_policy: backtestPolicy,
        report_lag_days: backtestLagDays,
      });
      setBacktestRuns((current) =>
        [created, ...current.filter((run) => run.id !== created.id)].slice(0, 5),
      );
      setBacktestDetailById((current) => ({ ...current, [created.id]: created }));
      setSelectedBacktestRunId(created.id);
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : String(err));
    } finally {
      setBacktestRunning(false);
    }
  };

  const handleRunAgentEvaluation = async (event: React.FormEvent) => {
    event.preventDefault();
    setAgentEvaluationRunning(true);
    setAgentEvaluationError(null);
    try {
      const created = await runAgentEvaluation({
        strategy: "valuation_direction_v1",
        ticker: agentEvaluationTicker.trim()
          ? agentEvaluationTicker.trim().toUpperCase()
          : undefined,
        workflow: agentEvaluationWorkflow.trim() || undefined,
        from_date: agentEvaluationFrom || undefined,
        to_date: agentEvaluationTo || undefined,
        outcome_windows: [30, 90, 180, 365],
      });
      setAgentEvaluationRuns((current) =>
        [created, ...current.filter((run) => run.id !== created.id)].slice(0, 5),
      );
      setAgentEvaluationDetailById((current) => ({ ...current, [created.id]: created }));
      setSelectedAgentEvaluationRunId(created.id);
    } catch (err) {
      setAgentEvaluationError(err instanceof Error ? err.message : String(err));
    } finally {
      setAgentEvaluationRunning(false);
    }
  };

  const anyRefreshing = rows.some((r) => r.refreshing);
  const readyRows = rows.filter((r) => hasDossierData(r.dossier)).length;
  const scoredRows = rows
    .filter((row) => hasDossierData(row.dossier))
    .sort((a, b) => {
      const ar =
        (a.dossier?.prescore.passed ?? 0) / Math.max(1, a.dossier?.prescore.total ?? 1);
      const br =
        (b.dossier?.prescore.passed ?? 0) / Math.max(1, b.dossier?.prescore.total ?? 1);
      return br - ar;
    });
  const bestRow = scoredRows[0] ?? null;
  // Prefer a row with a distilled AI expectation (the real signal); fall
  // back to the old "most posts" pick when no company has one yet.
  const forumRow =
    rows
      .filter((row) => (row.dossier?.forum.intelligence?.expectations?.claims.length ?? 0) > 0)
      .sort(
        (a, b) =>
          (b.dossier?.forum.intelligence?.expectations?.claims.length ?? 0) -
          (a.dossier?.forum.intelligence?.expectations?.claims.length ?? 0),
      )[0] ??
    rows
      .filter((row) => (row.dossier?.forum.posts ?? 0) > 0)
      .sort((a, b) => (b.dossier?.forum.posts ?? 0) - (a.dossier?.forum.posts ?? 0))[0] ??
    null;
  const staleRows = rows.filter((r) => {
    if (!hasDossierData(r.dossier)) return false;
    const scraped = r.dossier?.freshness.financials_scraped_at ?? null;
    const days = staleDays(scraped);
    return days != null && days > 3;
  }).length;
  const scalingRows = rows
    .filter((row) => hasDossierData(row.dossier))
    .map((row) => ({ ...row, scaling: scalingRead(row.dossier) }))
    .sort((a, b) => b.scaling.score - a.scaling.score)
    .slice(0, 3);

  return (
    <main className="page-stack">
      <section className="page-header">
        <div>
          <h1>Watchlist</h1>
          <p>
            Szybki pulpit spółek GPW: wyceny, świeżość danych i pierwsze sygnały
            jakości w jednym widoku.
          </p>
        </div>
        <form className="command-row" onSubmit={handleAdd}>
          <input
            placeholder="Ticker, np. DEC"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            className="ticker-input"
            aria-label="Ticker spółki"
          />
          <button className="btn" type="submit" disabled={adding}>
            <IconPlus size={14} /> Dodaj
          </button>
        </form>
      </section>

      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <>
          <SkeletonRows rows={4} height={52} />
          <LoadingMessages
            messages={[
              "Wczytuję watchlistę…",
              "Zbieram dossier każdej spółki…",
              "Liczę wskaźniki…",
            ]}
          />
        </>
      ) : rows.length === 0 ? (
        <section className="empty-state empty-panel">
          <IconPlus size={18} />
          <strong>Pusta watchlista</strong>
          <span>Dodaj pierwszy ticker, a aplikacja od razu pobierze dane.</span>
        </section>
      ) : (
        <>
          <section className="watchlist-brief">
            <div className="brief-card">
              <span className="brief-icon">
                <IconDatabase size={15} />
              </span>
              <div>
                <p className="k">Dane gotowe</p>
                <p className="v">{readyRows}/{rows.length}</p>
                <p className="note">{staleRows > 0 ? `${staleRows} wymaga odświeżenia` : "źródła aktualne"}</p>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">
                <IconShieldCheck size={15} />
              </span>
              <div>
                <p className="k">Najlepsze dopasowanie</p>
                <p className="v">{bestRow?.ticker ?? "—"}</p>
                <p className="note">
                  {bestRow?.dossier
                    ? `${bestRow.dossier.prescore.passed}/${bestRow.dossier.prescore.total} strategii`
                    : "brak gotowego dossier"}
                </p>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">
                <IconBrain size={15} />
              </span>
              <div>
                <p className="k">Forum / AI kontekst</p>
                <p className="v">{forumRow?.ticker ?? "—"}</p>
                <p className="note">
                  {(forumRow?.dossier && forumHeadline(forumRow.dossier)) ??
                    "powiąż wątki PortalAnaliz"}
                </p>
              </div>
            </div>
          </section>

          <section className="codex-console">
            <div className="codex-console-head">
              <div>
                <p className="section-label">Codex workflow queue</p>
                <p>
                  Recent Codex jobs. Queued rows are waiting for a Codex/MCP worker;
                  completed rows show saved output ids when available.
                </p>
              </div>
              <div className="command-row">
                <button
                  className="btn accent"
                  onClick={handlePreSession}
                  disabled={agentAction != null}
                >
                  <IconBrain
                    size={14}
                    className={agentAction === "pre-session" ? "spin" : ""}
                  />{" "}
                  Pre-session
                </button>
                <button
                  className="btn"
                  onClick={handleCandidateScout}
                  disabled={agentAction != null}
                >
                  <IconShieldCheck
                    size={14}
                    className={agentAction === "candidate" ? "spin" : ""}
                  />{" "}
                  Scout
                </button>
                <button
                  className="btn icon"
                  onClick={() => {
                    void loadAgentRuns();
                  }}
                  title="Odśwież workflows"
                >
                  <IconRefresh size={14} className={agentLoading ? "spin" : ""} />
                </button>
              </div>
            </div>
            {agentError && <div className="error-box compact">{agentError}</div>}
            <div className="agent-run-list">
              {agentLoading ? (
                <p className="empty-state">Ładowanie workflow…</p>
              ) : agentRuns.length === 0 ? (
                <p className="empty-state">Brak ostatnich zadań Codex.</p>
              ) : (
                agentRuns.map((run) => {
                  const outputId = agentRunOutputId(run);
                  return (
                    <div className="agent-run-row" key={run.id}>
                      <div>
                        <strong>{workflowLabel(run.workflow)}</strong>
                        <span className="cell-note">
                          #{run.id} · {run.trigger} · {agentRunLifecycleText(run)} ·{" "}
                          {agentModelLine(run)}
                        </span>
                      </div>
                      <span className={`badge ${runStatusTone(run.status)}`}>
                        {run.status}
                      </span>
                      <span className="row" style={{ gap: 6, justifyContent: "flex-end", flexWrap: "wrap" }}>
                        {outputId && <span className="badge success">analysis #{outputId}</span>}
                        <span className="small muted">{relativeDate(run.updated_at)}</span>
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </section>

          <section className="backtest-lab">
            <div className="codex-console-head">
              <div>
                <p className="section-label">Backtest Lab</p>
                <p>
                  Deterministic replay: known inputs stop at each as-of date;
                  future prices are outcome-only.
                </p>
              </div>
              <form className="backtest-form" onSubmit={handleRunBacktest}>
                <input
                  value={backtestTicker}
                  onChange={(event) => setBacktestTicker(event.target.value.toUpperCase())}
                  placeholder="Ticker opcj."
                  aria-label="Ticker backtestu"
                />
                <input
                  type="date"
                  value={backtestFrom}
                  onChange={(event) => setBacktestFrom(event.target.value)}
                  aria-label="Data od"
                />
                <input
                  type="date"
                  value={backtestTo}
                  onChange={(event) => setBacktestTo(event.target.value)}
                  aria-label="Data do"
                />
                <select
                  value={backtestPolicy}
                  onChange={(event) =>
                    setBacktestPolicy(
                      event.target.value as "scraped_at" | "estimated_period_lag",
                    )
                  }
                  aria-label="Polityka dostępności danych finansowych"
                >
                  <option value="scraped_at">scraped_at</option>
                  <option value="estimated_period_lag">estimated lag</option>
                </select>
                <input
                  type="number"
                  min={0}
                  max={730}
                  value={backtestLagDays}
                  disabled={backtestPolicy !== "estimated_period_lag"}
                  onChange={(event) => setBacktestLagDays(Number(event.target.value))}
                  aria-label="Liczba dni opóźnienia raportu"
                />
                <button className="btn accent" disabled={backtestRunning}>
                  <IconChartDots size={14} className={backtestRunning ? "spin" : ""} /> Run
                </button>
              </form>
            </div>
            {backtestError && <div className="error-box compact">{backtestError}</div>}
            <div className="agent-run-list">
              {backtestLoading ? (
                <p className="empty-state">Ładowanie backtestów…</p>
              ) : backtestRuns.length === 0 ? (
                <p className="empty-state">Brak zapisanych backtestów.</p>
              ) : (
                backtestRuns.map((run) => {
                  const selected = selectedBacktestRunId === run.id;
                  const detail = backtestDetailById[run.id];
                  return (
                    <div className="backtest-run-shell" key={run.id}>
                      <button
                        className={`agent-run-row backtest-run-row ${selected ? "selected" : ""}`}
                        type="button"
                        onClick={() => void handleSelectBacktest(run.id)}
                      >
                        <div>
                          <strong>{run.strategy}</strong>
                          <span className="cell-note">
                            #{run.id} · {run.from_date} - {run.to_date} ·{" "}
                            {run.summary.observation_count ?? 0} obserwacji
                          </span>
                        </div>
                        <span className={`badge ${runStatusTone(run.status)}`}>
                          {run.status}
                        </span>
                        <span className={`badge ${verificationTone(run.verification_status)}`}>
                          {run.verification_status}
                        </span>
                        <span className="small muted">{avgReturnText(run)}</span>
                      </button>
                      {selected && (
                        backtestDetailLoadingId === run.id ? (
                          <p className="empty-state compact">Ładowanie szczegółów…</p>
                        ) : detail ? (
                          <BacktestDetailPanel run={detail} />
                        ) : null
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </section>

          <section className="backtest-lab agent-evaluation-lab">
            <div className="codex-console-head">
              <div>
                <p className="section-label">Agent Evaluation</p>
                <p>
                  Saved Codex analyses replayed against later prices. Prose-only
                  predictions stay unscored.
                </p>
              </div>
              <form className="agent-evaluation-form" onSubmit={handleRunAgentEvaluation}>
                <input
                  value={agentEvaluationTicker}
                  onChange={(event) =>
                    setAgentEvaluationTicker(event.target.value.toUpperCase())
                  }
                  placeholder="Ticker opcj."
                  aria-label="Ticker ewaluacji agenta"
                />
                <select
                  value={agentEvaluationWorkflow}
                  onChange={(event) => setAgentEvaluationWorkflow(event.target.value)}
                  aria-label="Workflow ewaluacji agenta"
                >
                  <option value="">all workflows</option>
                  <option value="stock-quick-analysis">quick</option>
                  <option value="stock-deep-analysis">deep</option>
                  <option value="stock-candidate-scout">candidate</option>
                </select>
                <input
                  type="date"
                  value={agentEvaluationFrom}
                  onChange={(event) => setAgentEvaluationFrom(event.target.value)}
                  aria-label="Data ewaluacji od"
                />
                <input
                  type="date"
                  value={agentEvaluationTo}
                  onChange={(event) => setAgentEvaluationTo(event.target.value)}
                  aria-label="Data ewaluacji do"
                />
                <button className="btn accent" disabled={agentEvaluationRunning}>
                  <IconChartDots
                    size={14}
                    className={agentEvaluationRunning ? "spin" : ""}
                  />{" "}
                  Evaluate
                </button>
                <button
                  className="btn icon"
                  type="button"
                  onClick={loadAgentEvaluationRuns}
                  title="Odśwież ewaluacje"
                >
                  <IconRefresh
                    size={14}
                    className={agentEvaluationLoading ? "spin" : ""}
                  />
                </button>
              </form>
            </div>
            {agentEvaluationError && (
              <div className="error-box compact">{agentEvaluationError}</div>
            )}
            <div className="agent-run-list">
              {agentEvaluationLoading ? (
                <p className="empty-state">Ładowanie ewaluacji…</p>
              ) : agentEvaluationRuns.length === 0 ? (
                <p className="empty-state">Brak zapisanych ewaluacji agentów.</p>
              ) : (
                agentEvaluationRuns.map((run) => {
                  const selected = selectedAgentEvaluationRunId === run.id;
                  const detail = agentEvaluationDetailById[run.id];
                  return (
                    <div className="backtest-run-shell" key={run.id}>
                      <button
                        className={`agent-run-row agent-evaluation-row ${selected ? "selected" : ""}`}
                        type="button"
                        onClick={() => void handleSelectAgentEvaluation(run.id)}
                      >
                        <div>
                          <strong>{run.strategy}</strong>
                          <span className="cell-note">
                            #{run.id} · {run.model_role ?? "role?"} /{" "}
                            {run.model ?? "model?"} ·{" "}
                            {textValue(run.parameters.workflow) ?? "all workflows"}
                          </span>
                        </div>
                        <span className={`badge ${runStatusTone(run.status)}`}>
                          {run.status}
                        </span>
                        <span className={`badge ${verificationTone(run.verification_status)}`}>
                          {run.verification_status}
                        </span>
                        <span className="small muted">{evaluationHitRateText(run)}</span>
                      </button>
                      {selected &&
                        (agentEvaluationDetailLoadingId === run.id ? (
                          <p className="empty-state compact">Ładowanie szczegółów…</p>
                        ) : detail ? (
                          <AgentEvaluationDetailPanel run={detail} />
                        ) : null)}
                    </div>
                  );
                })
              )}
            </div>
          </section>

          {scalingRows.length > 0 && (
            <section className="scaling-radar">
              <div className="section-heading">
                <p className="section-label">Scaling radar</p>
                <p>
                  Szuka wzorca z udanych inwestycji: szybki wzrost, jakość marży,
                  czysty wynik, miejsce na re-rating i wystarczające dane.
                </p>
              </div>
              <div className="scaling-grid">
                {scalingRows.map((row) => {
                  const scaling = row.scaling;
                  const d = row.dossier;
                  const valuation = valuationText(d);
                  const lastQ = d?.quarters.at(-1);
                  return (
                    <button
                      className="scaling-card"
                      key={row.ticker}
                      onClick={() => router.push(`/stock/${row.ticker}`)}
                    >
                      <div className="spread" style={{ gap: 8 }}>
                        <span className="ticker-mark">{row.ticker}</span>
                        <span className={`badge ${scaling.tone}`}>{scaling.label}</span>
                      </div>
                      <div className="scaling-score">
                        <strong>{scaling.score}</strong>
                        <span>scaling score</span>
                      </div>
                      <div className="scaling-metrics">
                        <span>
                          <IconTrendingUp size={13} />{" "}
                          {fmtPct(lastQ?.revenue_yoy_pct, { signed: true })} r/r
                        </span>
                        <span>
                          <IconChartDots size={13} /> marża br.{" "}
                          {fmtPct(lastQ?.gross_margin_pct)}
                        </span>
                        <span className={signClass(valuation.upside)}>
                          {fmtPct(valuation.upside, { signed: true })} EV
                        </span>
                      </div>
                      <p>{scaling.reasons.slice(0, 3).join(" · ") || "brak mocnych sygnałów skali"}</p>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          <section className="discovery-brief">
            <div className="section-heading">
              <p className="section-label">BiznesRadar discovery</p>
              <p>
                Filtry do ręcznego przesiania BR zanim ticker trafi na watchlistę.
                To wzorzec z udanych inwestycji, nie automatyczny sygnał.
              </p>
            </div>
            <div className="discovery-grid">
              {DISCOVERY_FILTERS.map((filter) => (
                <div className="discovery-filter" key={filter.title}>
                  <strong>{filter.title}</strong>
                  <p>{filter.text}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="table-panel">
            <div className="table-toolbar">
              <div className="status-strip">
                <span className="status-pill">
                  <IconCircleCheck size={13} /> {readyRows}/{rows.length} z dossier
                </span>
                <span className={`status-pill ${staleRows > 0 ? "warn" : ""}`}>
                  <IconClockExclamation size={13} /> {staleRows} po terminie
                </span>
              </div>
              <button className="btn" onClick={handleRefreshAll} disabled={anyRefreshing}>
                <IconRefresh size={13} className={anyRefreshing ? "spin" : ""} /> Odśwież
                wszystkie
              </button>
            </div>
            <div className="table-scroll watchlist-table">
              <table className="table decision-table">
                <thead>
                  <tr>
                    <th>Spółka</th>
                    <th>Odczyt</th>
                    <th>Strategia</th>
                    <th>Wycena</th>
                    <th>Operacje</th>
                    <th>Dane</th>
                    <th style={{ width: 70 }} />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const d = row.dossier;
                    const hasData = hasDossierData(d);
                    const lastQ = d?.quarters.at(-1);
                    const scraped = d?.freshness.financials_scraped_at ?? null;
                    const days = staleDays(scraped);
                    const read = stockRead(d);
                    const valuation = valuationText(d);
                    const thesisCode = d?.thesis?.entry_quality.code;
                    const forumNote = forumHeadline(d);
                    return (
                      <tr
                        key={row.ticker}
                        className="clickable"
                        onClick={() => router.push(`/stock/${row.ticker}`)}
                      >
                        <td data-label="Spółka">
                          <span className="ticker-mark">{row.ticker}</span>
                          <span className="company-name">
                            {row.refreshing ? "ładowanie danych…" : row.name ?? (hasData ? "—" : "brak danych")}
                          </span>
                          <span className="stock-meta">
                            {fmtPln(d?.ttm.price)} · {fmtMcap(d?.ttm.market_cap)}
                          </span>
                        </td>
                        <td className="watch-read-cell" data-label="Odczyt">
                          <span className={`badge ${entryTone(thesisCode)}`}>
                            {read.label}
                          </span>
                          <span className="watch-read">{read.detail}</span>
                        </td>
                        <td data-label="Strategia">
                          <span className={`badge ${scoreTone(d)}`}>
                            {d ? `${d.prescore.passed}/${d.prescore.total}` : "—"}
                          </span>
                          <span className="cell-note">
                            <IconAlertTriangle size={12} /> {topRisk(d)}
                          </span>
                        </td>
                        <td data-label="Wycena">
                          <span className={signClass(valuation.upside)}>
                            {fmtPct(valuation.upside, { signed: true })}
                          </span>
                          <span className="cell-note">
                            C/Z {fmtNumber(d?.ttm.pe)} · fwd {fmtNumber(d?.latest_forecast?.result.forward.pe)}
                          </span>
                          <span className="cell-note">{valuation.label}</span>
                        </td>
                        <td data-label="Operacje">
                          <span className={signClass(lastQ?.revenue_yoy_pct)}>
                            <IconChartDots size={13} /> {fmtPct(lastQ?.revenue_yoy_pct, { signed: true })} r/r
                          </span>
                          <span className="cell-note">marża br. <MarginTrend dossier={d} /></span>
                        </td>
                        <td data-label="Dane">
                          {row.refreshing ? (
                            <span className="badge accent">pobieranie</span>
                          ) : hasData ? (
                            <span className={`badge ${days != null && days > 3 ? "warning" : "neutral"}`}>
                              {relativeDate(scraped)}
                            </span>
                          ) : (
                            <span className="badge warning">brak</span>
                          )}
                          <span className="cell-note">
                            {forumNote ?? `forum ${d?.forum.posts ?? 0}`} · kurs{" "}
                            {relativeDate(d?.freshness.last_price_date)}
                          </span>
                        </td>
                        <td data-label="Akcje" onClick={(e) => e.stopPropagation()}>
                          <span className="row row-actions">
                            <button
                              className="btn icon"
                              title="Odśwież dane"
                              aria-label={`Odśwież dane ${row.ticker}`}
                              disabled={row.refreshing}
                              onClick={() => handleRefresh(row.ticker, true)}
                            >
                              <IconRefresh size={15} className={row.refreshing ? "spin" : ""} />
                            </button>
                            <button
                              className="btn icon"
                              title="Usuń z watchlisty"
                              aria-label={`Usuń ${row.ticker} z watchlisty`}
                              onClick={() => handleRemove(row.ticker)}
                            >
                              <IconTrash size={15} />
                            </button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {rows.length > 0 && (
        <p className="small muted page-note">
          {rows.length} {rows.length === 1 ? "spółka" : "spółki"} · odświeżanie działa
          sekwencyjnie ze względu na limity źródeł.
        </p>
      )}
    </main>
  );
}
