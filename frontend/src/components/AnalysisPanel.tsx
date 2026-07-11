"use client";

/** Analysis tab: queue Codex workflows and show provider-neutral verified results. */
import { useEffect, useState } from "react";
import { IconSparkles } from "@tabler/icons-react";
import {
  ApiError,
  listAgentRuns,
  listAnalysisRuns,
  queueAgentRun,
} from "@/lib/api";
import { isCurrentVerifiedRun } from "@/lib/analysis";
import { fmtDate, fmtPct, relativeDate, signClass } from "@/lib/format";
import { DEFAULT_ORCHESTRATOR_MODEL, modelPolicyDescription, ORCHESTRATOR_MODELS } from "@/lib/model-policy";
import { LoadingMessages } from "@/components/Loading";
import type {
  AgentRun,
  AnalysisRun,
  Dossier,
} from "@/lib/types";

function scoreTone(score: number | null): string {
  if (score == null) return "muted";
  if (score >= 70) return "success";
  if (score >= 40) return "warning";
  return "danger";
}

function textField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberField(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordField(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function rangeField(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const low = numberField(value[0]);
  const high = numberField(value[1]);
  return low == null || high == null ? null : [low, high];
}

function analysisRunSummary(run: AnalysisRun): string {
  return (
    textField(run.output.summary_pl) ||
    textField(run.output.executive_read) ||
    textField(run.output.thesis) ||
    "Brak krótkiego opisu w zapisanym wyniku."
  );
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

function predictionTone(direction: string | null): string {
  if (direction === "positive") return "success";
  if (direction === "negative") return "danger";
  if (direction === "neutral") return "warning";
  return "muted";
}

function scenarioValidityTone(validity: string | null): string {
  if (validity === "valid") return "success";
  if (validity === "limited") return "warning";
  if (validity === "invalid") return "danger";
  return "muted";
}

function agentModelLine(run: AgentRun): string {
  const role = run.model_role ?? "role pending";
  const model = run.model ?? run.orchestrator_model ?? "model chosen by Codex";
  return `${role} · ${model}`;
}

function agentRunOutputId(run: AgentRun): string | null {
  const value = run.outputs?.analysis_run_id;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return textField(value);
}

function agentRunLifecycleText(run: AgentRun): string {
  if (run.status === "queued") {
    return "oczekuje w FIFO na cykliczny worker Codex";
  }
  if (run.status === "running") return "worker odebrał zlecenie";
  if (run.status === "completed" || run.status === "verified") return "worker zakończył zlecenie";
  if (run.status === "needs-human") return "verifier wymaga decyzji człowieka";
  if (run.status === "rejected" || run.status === "failed") return run.error ?? "zlecenie odrzucone lub zakończone błędem";
  return "stan workflow zapisany";
}

function textList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const row = item as Record<string, unknown>;
        return (
          textField(row.text) ||
          textField(row.description) ||
          textField(row.claim) ||
          textField(row.reason) ||
          textField(row.why) ||
          null
        );
      }
      return null;
    })
    .filter((item): item is string => item != null);
}

function confidenceFields(value: unknown): { label: string | null; rationale: string | null } {
  const text = textField(value);
  if (text) return { label: text, rationale: null };
  const row = recordField(value);
  if (!row) return { label: null, rationale: null };
  const score = numberField(row.score);
  return {
    label:
      textField(row.level) ||
      textField(row.value) ||
      textField(row.confidence) ||
      (score == null ? null : String(score)),
    rationale: textField(row.rationale) || textField(row.reason) || textField(row.why),
  };
}

function nestedPotential(output: Record<string, unknown>): Record<string, unknown> | null {
  return recordField(output.potential) ?? recordField(recordField(output.valuation)?.potential);
}

function analysisRunSignal(run: AnalysisRun): { direction: string; label: string } | null {
  const prediction = recordField(run.output.prediction);
  const potential = nestedPotential(run.output);
  const direction = textField(prediction?.direction);
  const potentialValue =
    numberField(potential?.value_pct) ??
    numberField(prediction?.potential_pct) ??
    numberField(run.output.expected_upside_pct) ??
    numberField(run.output.upside_pct);
  if (!direction && potentialValue == null) return null;
  return {
    direction: direction ?? "unknown",
    label: `${direction ?? "unknown"}${
      potentialValue != null ? ` ${fmtPct(potentialValue, { signed: true })}` : ""
    }`,
  };
}

function extractSourceLinks(value: unknown, limit = 8): string[] {
  const links = new Set<string>();
  const visit = (item: unknown, depth: number) => {
    if (links.size >= limit || depth > 4 || item == null) return;
    if (typeof item === "string") {
      if (item.startsWith("http://") || item.startsWith("https://")) links.add(item);
      return;
    }
    if (Array.isArray(item)) {
      for (const child of item) visit(child, depth + 1);
      return;
    }
    if (typeof item === "object") {
      for (const [key, child] of Object.entries(item as Record<string, unknown>)) {
        if (
          typeof child === "string" &&
          (key === "url" || key.endsWith("_url") || key === "raw_url")
        ) {
          links.add(child);
        } else {
          visit(child, depth + 1);
        }
      }
    }
  };
  visit(value, 0);
  return [...links].slice(0, limit);
}

function ProviderNeutralAnalysisCard({ run }: { run: AnalysisRun }) {
  const output = run.output ?? {};
  const verification = run.verification ?? {};
  const prediction = recordField(output.prediction);
  const potential = nestedPotential(output);
  const resultQuality = recordField(output.result_quality);
  const direction = textField(prediction?.direction);
  const horizonDays = numberField(prediction?.horizon_days);
  const sourceFields = textList(prediction?.source_fields).slice(0, 10);
  const missingSourceFields = prediction != null && sourceFields.length === 0;
  const potentialValue =
    numberField(potential?.value_pct) ??
    numberField(prediction?.potential_pct) ??
    numberField(output.expected_upside_pct) ??
    numberField(output.upside_pct);
  const potentialRange = rangeField(potential?.range_pct);
  const potentialBasis = textField(potential?.basis_label) || textField(potential?.basis);
  const confidence = confidenceFields(output.confidence ?? prediction?.confidence);
  const resultCause = textField(resultQuality?.result_cause);
  const oneOffRisk = textField(resultQuality?.one_off_risk);
  const scenarioValidity = textField(resultQuality?.scenario_validity);
  const scenarioWarnings = textList(resultQuality?.scenario_warnings);
  const missingResultQualityNotes =
    resultQuality != null &&
    !resultCause &&
    !oneOffRisk &&
    scenarioWarnings.length === 0;
  const hasContractFields =
    prediction != null ||
    potential != null ||
    resultQuality != null ||
    confidence.label != null ||
    confidence.rationale != null;
  const summary =
    textField(output.executive_read) ||
    textField(output.summary_pl) ||
    textField(output.thesis) ||
    textField(output.next_action) ||
    "Codex zapisał wynik bez krótkiego pola podsumowania.";
  const redFlags = textList(output.red_flags ?? output.risks);
  const watchItems = textList(output.watch_items ?? output.action_plan);
  const dataGaps = textList(output.data_gaps ?? output.missing_data);
  const verifyNext = textList(output.verify_next);
  const nextAction = textField(output.next_action);
  const verifierSummary = textField(verification.summary) || textField(verification.verdict);
  const links = extractSourceLinks(output);

  return (
    <div className="card analysis">
      <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
        <div>
          <p className="analysis-title">{run.workflow}</p>
          <p className="small muted">
            {fmtDate(run.created_at)} · {run.model_role} · {run.model}
          </p>
        </div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          <span className="badge muted">analysis #{run.id}</span>
          <span className={`badge ${runStatusTone(run.status)}`}>{run.status}</span>
          <span className={`badge ${verificationTone(run.verification_status)}`}>
            verifier: {run.verification_status}
          </span>
          <span className="badge muted">{run.source}</span>
        </div>
      </div>

      {run.alignment_score != null && (
        <div className={`score ${scoreTone(run.alignment_score)}`} style={{ marginTop: 12 }}>
          <span className="score-value">{run.alignment_score}</span>
          <span className="score-label">alignment score</span>
        </div>
      )}

      <p style={{ marginTop: 12, fontWeight: 500, lineHeight: 1.5 }}>{summary}</p>

      {hasContractFields && (
        <div className="analysis-contract" aria-label="Structured Codex analysis fields">
          <div className="analysis-contract-grid">
            <div className="analysis-contract-cell">
              <span className="contract-label">Prediction</span>
              <span className="contract-value">
                <span className={`badge ${predictionTone(direction)}`}>{direction ?? "unknown"}</span>
                {horizonDays != null && <span>{horizonDays}d</span>}
              </span>
            </div>
            <div className="analysis-contract-cell">
              <span className="contract-label">Potential</span>
              <span className={`contract-value ${signClass(potentialValue)}`}>
                {fmtPct(potentialValue, { signed: true })}
              </span>
              {potentialRange && (
                <span className="contract-note">
                  {fmtPct(potentialRange[0], { signed: true })} …{" "}
                  {fmtPct(potentialRange[1], { signed: true })}
                </span>
              )}
            </div>
            <div className="analysis-contract-cell">
              <span className="contract-label">Scenario validity</span>
              <span className="contract-value">
                <span className={`badge ${scenarioValidityTone(scenarioValidity)}`}>
                  {scenarioValidity ?? "unknown"}
                </span>
              </span>
            </div>
            <div className="analysis-contract-cell">
              <span className="contract-label">Confidence</span>
              <span className="contract-value">{confidence.label ?? "unknown"}</span>
            </div>
          </div>

          {(sourceFields.length > 0 || missingSourceFields || potentialBasis) && (
            <div className="source-field-row">
              {missingSourceFields && (
                <span className="source-field-chip warning">source_fields: missing</span>
              )}
              {sourceFields.map((field) => (
                <span className="source-field-chip" key={field}>{field}</span>
              ))}
              {potentialBasis && <span className="source-field-chip">{potentialBasis}</span>}
            </div>
          )}
        </div>
      )}

      {nextAction && (
        <div className="analysis-section">
          <p className="analysis-title">Next action</p>
          <p className="secondary" style={{ lineHeight: 1.5 }}>{nextAction}</p>
        </div>
      )}

      {confidence.rationale && (
        <div className="analysis-section">
          <p className="analysis-title">Confidence</p>
          <p className="secondary" style={{ lineHeight: 1.5 }}>{confidence.rationale}</p>
        </div>
      )}

      {(resultCause || oneOffRisk || scenarioWarnings.length > 0 || missingResultQualityNotes) && (
        <div className="analysis-section">
          <p className="analysis-title">Result quality</p>
          <div className="quality-grid">
            {missingResultQualityNotes && (
              <p className="quality-note">
                <span>Result quality</span>
                structured notes missing
              </p>
            )}
            {resultCause && (
              <p className="quality-note">
                <span>Result cause</span>
                {resultCause}
              </p>
            )}
            {oneOffRisk && (
              <p className="quality-note">
                <span>One-off risk</span>
                {oneOffRisk}
              </p>
            )}
            {scenarioWarnings.length > 0 && (
              <div className="quality-note">
                <span>Scenario warnings</span>
                {scenarioWarnings.map((warning, index) => (
                  <p key={`${warning}-${index}`}>{warning}</p>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {watchItems.length > 0 && (
        <div className="analysis-section">
          <p className="analysis-title">Watch items</p>
          {watchItems.map((item, index) => (
            <p className="verify-item" key={`${item}-${index}`}>{item}</p>
          ))}
        </div>
      )}

      {redFlags.length > 0 && (
        <div className="analysis-section">
          <p className="analysis-title">Risks / red flags</p>
          <ul className="points bad">
            {redFlags.map((flag, index) => (
              <li key={`${flag}-${index}`}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {dataGaps.length > 0 && (
        <div className="analysis-section">
          <p className="analysis-title">Data gaps</p>
          {dataGaps.map((gap, index) => (
            <p className="verify-item" key={`${gap}-${index}`}>{gap}</p>
          ))}
        </div>
      )}

      {verifyNext.length > 0 && (
        <div className="analysis-section">
          <p className="analysis-title">Verify next</p>
          {verifyNext.map((item, index) => (
            <p className="verify-item" key={`${item}-${index}`}>{item}</p>
          ))}
        </div>
      )}

      {links.length > 0 && (
        <div className="analysis-section">
          <p className="analysis-title">Source links</p>
          <div className="source-link-list">
            {links.map((link) => (
              <a href={link} target="_blank" rel="noreferrer" key={link}>
                {link}
              </a>
            ))}
          </div>
        </div>
      )}

      {verifierSummary && (
        <div className="analysis-section">
          <p className="analysis-title">Verifier notes</p>
          <p className="secondary" style={{ lineHeight: 1.5 }}>{verifierSummary}</p>
        </div>
      )}

      <p className="disclaimer">Provider-neutral Codex analysis, not investment advice.</p>
    </div>
  );
}

export default function AnalysisPanel({
  ticker,
  dossier,
}: {
  ticker: string;
  // Accepted for call-site parity with the other tab panels (ForecastPanel
  // etc., which all get the loaded dossier) — the backend re-derives its own
  // dossier server-side for the analysis run, so this component doesn't need
  // to read it today. Kept typed rather than `unknown` so it starts useful
  // the moment a caller wants to show dossier-derived context here.
  dossier: Dossier;
}) {
  const [agentHistory, setAgentHistory] = useState<AnalysisRun[] | null>(null);
  const [agentWorkflowRows, setAgentWorkflowRows] = useState<AgentRun[] | null>(null);
  const [selectedAgentRunId, setSelectedAgentRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [queueing, setQueueing] = useState(false);
  const [orchestratorModel, setOrchestratorModel] = useState<string>(DEFAULT_ORCHESTRATOR_MODEL);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const loadRows = async () => {
      const [agentRows, workflowRows] = await Promise.all([
        listAnalysisRuns(ticker),
        listAgentRuns({ ticker, limit: 6 }),
      ]);
      if (cancelled) return;
      setAgentHistory(agentRows);
      setAgentWorkflowRows(workflowRows);
      const currentVerified = agentRows.find((run) => isCurrentVerifiedRun(run, dossier));
      if (currentVerified) setSelectedAgentRunId(currentVerified.id);
    };
    loadRows()
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    const pollId = window.setInterval(() => {
      loadRows().catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    }, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(pollId);
    };
  }, [dossier, ticker]);

  const handleQueueCodex = async () => {
    setQueueing(true);
    setError(null);
    try {
      const run = await queueAgentRun({
        workflow: "stock-deep-analysis",
        ticker,
        trigger: "ui-request",
        model_role: "orchestrator",
        model: orchestratorModel,
        orchestrator_model: orchestratorModel,
        inputs: {
          objective: "Create a complete, concise company report from stored evidence and primary-source research.",
          required_verification: "Strongest configured verifier independently owns prediction, confidence, result quality and approval.",
          ui_contract: "Prepared report only; keep raw evidence in audit storage.",
          model_selection: {
            requested: orchestratorModel,
            provider_mode: "codex-host",
            exact_deployment_exposed: false,
          },
        },
      });
      setAgentWorkflowRows((current) => [run, ...(current ?? [])]);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error ? err.message : String(err),
      );
    } finally {
      setQueueing(false);
    }
  };

  if (loading) return <LoadingMessages messages={["Ładuję historię analiz…", "Sprawdzam najnowszy verifier…"]} />;

  const agentRows = agentHistory ?? [];
  const workflowRows = agentWorkflowRows ?? [];
  const activeDeepJob = workflowRows.find(
    (run) =>
      run.workflow === "stock-deep-analysis" &&
      (run.status === "queued" || run.status === "running"),
  );
  const selectedAgentRun =
    selectedAgentRunId == null
      ? null
      : agentRows.find((run) => run.id === selectedAgentRunId) ?? null;
  const currentVerifiedRows = agentRows.filter((run) => isCurrentVerifiedRun(run, dossier));
  const context = dossier.analysis_context_status;
  const selectedOutput = selectedAgentRun?.output ?? {};
  const selectedRedFlags = textList(selectedOutput.red_flags ?? selectedOutput.risks).slice(0, 4);
  const selectedDataGaps = textList(selectedOutput.data_gaps ?? selectedOutput.missing_data).slice(0, 4);
  const selectedVerifierNote = selectedAgentRun
    ? textField(selectedAgentRun.verification?.summary) || textField(selectedAgentRun.verification?.verdict)
    : null;

  return (
    <div>
      <section className="codex-next-action" aria-label="Następny krok analizy Codex">
        <div>
          <p className="eyebrow">Następny krok</p>
          <h3>{activeDeepJob ? "Raport jest już prowadzony przez Codex" : "Zleć pełny raport po zebraniu danych"}</h3>
          <p>
            Codex pracuje na zapisanym dossier, a wynik dopiero po niezależnej
            weryfikacji może zastąpić raport roboczy. Nie jest wymagany klucz API.
          </p>
        </div>
        <div className="codex-next-controls">
          <label>
            Model orchestratora
            <select
              value={orchestratorModel}
              onChange={(event) => setOrchestratorModel(event.target.value)}
              disabled={queueing || Boolean(activeDeepJob)}
              aria-describedby="model-policy-note"
            >
              {ORCHESTRATOR_MODELS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <button className="btn accent" onClick={handleQueueCodex} disabled={queueing || Boolean(activeDeepJob)}>
            <IconSparkles size={14} className={queueing ? "spin" : ""} />
            {activeDeepJob ? "W toku / w kolejce" : "Zleć pełny raport"}
          </button>
        </div>
        <p id="model-policy-note" className="small muted">
          {modelPolicyDescription(orchestratorModel)} Host Codex nie ujawnia dokładnego deploymentu; wybór jest zapisany w historii runu.
        </p>
      </section>
      <div className="row wrap" style={{ marginBottom: 14 }}>
        {context && (
          <span className={`badge ${context.ready_for_ai ? "success" : "warning"}`}>
            dane analizy: {context.ready_for_ai ? "gotowe" : `braki: ${context.missing.join(", ")}`}
          </span>
        )}
        {agentRows.length > 0 && (
          <span className="small muted">
            {currentVerifiedRows.length} aktualnych i zweryfikowanych · {agentRows.length} w historii
          </span>
        )}
      </div>

      {error && <div className="error-box">{error}</div>}

      {selectedAgentRun && (
        <div className="card analysis" style={{ marginBottom: 14 }}>
          <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <div>
              <p className="analysis-title">Najważniejsze wyjątki</p>
              <p className="small muted">{analysisRunSummary(selectedAgentRun)}</p>
            </div>
            <span className={`badge ${verificationTone(selectedAgentRun.verification_status)}`}>
              verifier: {selectedAgentRun.verification_status}
            </span>
          </div>
          {(selectedRedFlags.length > 0 || selectedDataGaps.length > 0 || selectedVerifierNote) ? (
            <div className="analysis-section" style={{ marginTop: 10 }}>
              {selectedRedFlags.map((flag, index) => (
                <p className="verify-item" key={`flag-${index}`}>Ryzyko: {flag}</p>
              ))}
              {selectedDataGaps.map((gap, index) => (
                <p className="verify-item" key={`gap-${index}`}>Brak danych: {gap}</p>
              ))}
              {selectedVerifierNote && <p className="verify-item">Verifier: {selectedVerifierNote}</p>}
            </div>
          ) : (
            <p className="small muted" style={{ margin: "10px 0 0" }}>
              Model nie nazwał wyjątków. Nadal sprawdź źródła przed decyzją.
            </p>
          )}
        </div>
      )}

      {workflowRows.length > 0 && (
        <details className="review-history">
          <summary>Stan kolejki Codex ({workflowRows.length})</summary>
          <div className="analysis-section" style={{ marginTop: 10 }}>
            {workflowRows.map((run) => {
              const outputId = agentRunOutputId(run);
              return (
                <div className="verify-item" key={run.id}>
                  <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
                    <strong>{run.workflow}</strong>
                    <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                      {outputId && <span className="badge success">analysis #{outputId}</span>}
                      <span className={`badge ${runStatusTone(run.status)}`}>
                        {run.status}
                      </span>
                    </span>
                  </div>
                  <p className="small muted">
                    #{run.id} · {relativeDate(run.updated_at)} · {agentRunLifecycleText(run)} ·{" "}
                    {agentModelLine(run)}
                  </p>
                </div>
              );
            })}
          </div>
        </details>
      )}

      {agentRows.length > 0 && (
        <details className="review-history">
          <summary>Historia recenzji Codex ({agentRows.length})</summary>
          <div className="analysis-section" style={{ marginTop: 10 }}>
            {agentRows.slice(0, 5).map((run) => {
              const signal = analysisRunSignal(run);
              const currentVerified = isCurrentVerifiedRun(run, dossier);
              return (
                <button
                  className={`verify-item analysis-run-select${
                    selectedAgentRunId === run.id ? " selected" : ""
                  }`}
                  aria-pressed={selectedAgentRunId === run.id}
                  key={run.id}
                  onClick={() => {
                    setSelectedAgentRunId(run.id);
                  }}
                >
                  <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
                    <strong>{run.workflow}</strong>
                    <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                      {signal && (
                        <span className={`badge ${predictionTone(signal.direction)}`}>
                          {signal.label}
                        </span>
                      )}
                      <span className={`badge ${verificationTone(run.verification_status)}`}>
                        {run.status} / {run.verification_status}
                      </span>
                      {!currentVerified && <span className="badge muted">historyczny / audyt</span>}
                    </span>
                  </div>
                  <p className="secondary" style={{ lineHeight: 1.5, marginTop: 6 }}>
                    {analysisRunSummary(run)}
                  </p>
                  <p className="small muted">
                    #{run.id} · {fmtDate(run.created_at)} · {run.model_role} · {run.model}
                  </p>
                </button>
              );
            })}
          </div>
        </details>
      )}

      {!selectedAgentRun && !error && (
        <p className="empty-state">
          Brak aktualnego raportu po pełnej weryfikacji. Historyczne wyniki pozostają poniżej wyłącznie do audytu.
        </p>
      )}

      {selectedAgentRun && (
        <details className="review-history">
          <summary>Pełny zapis wybranej recenzji</summary>
          <ProviderNeutralAnalysisCard run={selectedAgentRun} />
        </details>
      )}
    </div>
  );
}
