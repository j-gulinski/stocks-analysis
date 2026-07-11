"use client";

/** Settings — connection status checks only; secrets never leave the backend. */
import { IconCheck, IconPlayerPlay, IconRefresh, IconX } from "@tabler/icons-react";
import {
  getAiUsage,
  getBrLoginStatus,
  getForumLoginStatus,
  getHealth,
  getScrapersHealth,
  getWorkflowStatus,
  preparePreSessionBrief,
  processOneAgentRun,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { relativeDate } from "@/lib/format";
import { friendlySourceStatus } from "@/lib/source-status";
import { DEFAULT_ORCHESTRATOR_MODEL, modelPolicyDescription, ORCHESTRATOR_MODELS } from "@/lib/model-policy";
import { useState } from "react";

function StatusCard({
  title,
  status,
  detail,
  loading,
}: {
  title: string;
  status: "ok" | "error" | "not_configured" | null;
  detail: string;
  loading: boolean;
}) {
  return (
    <div className="card spread">
      <div>
        <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>{title}</p>
        <p className="small muted" style={{ margin: "4px 0 0" }}>
          {loading ? "Sprawdzanie…" : detail}
        </p>
      </div>
      {!loading && status != null && (
        <span
          className={`badge ${
            status === "ok" ? "success" : status === "error" ? "danger" : "warning"
          }`}
        >
          {status === "ok" && <IconCheck size={13} />}
          {status === "error" && <IconX size={13} />}
          {status === "ok" ? "OK" : status === "error" ? "błąd" : "Nie skonfigurowano"}
        </span>
      )}
      {loading && <IconRefresh size={15} className="spin" aria-label="Sprawdzanie" />}
    </div>
  );
}

export default function SettingsPage() {
  const health = useApi(getHealth, []);
  const forum = useApi(getForumLoginStatus, []);
  const biznesradar = useApi(getBrLoginStatus, []);
  const scrapers = useApi(getScrapersHealth, []);
  const aiUsage = useApi(getAiUsage, []);
  const workflows = useApi(getWorkflowStatus, []);
  const [sessionAction, setSessionAction] = useState<string | null>(null);
  const [orchestratorModel, setOrchestratorModel] = useState<string>(DEFAULT_ORCHESTRATOR_MODEL);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionInfo, setSessionInfo] = useState<string | null>(null);

  const recheckEspi = async () => {
    setSessionAction("espi");
    setSessionError(null);
    setSessionInfo(null);
    try {
      const result = await preparePreSessionBrief({
        trigger: "settings-ui",
        orchestrator_model: orchestratorModel,
        fetch_details: true,
        queue: true,
      });
      if (!result.ok) {
        setSessionError(`ESPI wymaga uwagi: ${friendlySourceStatus(String(result.espi_poll.incomplete_reason ?? "Niepełne pobranie ESPI."))}`);
      } else {
        setSessionInfo(result.agent_run ? `ESPI sprawdzone; utworzono zlecenie #${result.agent_run.id}.` : "ESPI sprawdzone; nie utworzono nowego zlecenia.");
      }
    } catch (err) {
      setSessionError(err instanceof Error ? err.message : String(err));
    } finally {
      setSessionAction(null);
    }
  };

  const processOne = async () => {
    setSessionAction("queue");
    setSessionError(null);
    setSessionInfo(null);
    try {
      const result = await processOneAgentRun();
      setSessionInfo(result.message);
    } catch (err) {
      setSessionError(err instanceof Error ? err.message : String(err));
    } finally {
      setSessionAction(null);
    }
  };

  return (
    <main className="settings-page">
      <section className="settings-intro">
        <div>
          <p className="eyebrow">System</p>
          <h1>Sprawdź sesję, potem diagnozuj źródła</h1>
          <p>Codzienna ścieżka jest krótka: sprawdź ESPI, odbierz najwyżej jedno zlecenie, a dopiero potem analizuj stan usług.</p>
        </div>
        <ol className="settings-steps" aria-label="Typowa sesja">
          <li className="active"><span>1</span><strong>Sesja</strong><small>ESPI + model</small></li>
          <li><span>2</span><strong>Kolejka</strong><small>jedna próba</small></li>
          <li><span>3</span><strong>Diagnoza</strong><small>źródła i budżet</small></li>
        </ol>
      </section>
      <div style={{ display: "grid", gap: 10 }}>
        <p className="settings-section-label">Stan usług</p>
        <StatusCard
          title="Backend + baza danych"
          status={health.error ? "error" : health.data ? "ok" : null}
          detail={health.error ?? "API odpowiada, połączenie z bazą działa."}
          loading={health.loading}
        />
        <StatusCard
          title="Logowanie BiznesRadar"
          status={biznesradar.data?.status ?? (biznesradar.error ? "error" : null)}
          detail={biznesradar.data?.detail ?? biznesradar.error ?? ""}
          loading={biznesradar.loading}
        />
        <StatusCard
          title="Logowanie PortalAnaliz"
          status={forum.data?.status ?? (forum.error ? "error" : null)}
          detail={forum.data?.detail ?? forum.error ?? ""}
          loading={forum.loading}
        />
        <StatusCard
          title="Codex workflow queue"
          status={workflows.error ? "error" : workflows.data ? "ok" : null}
          detail={
            workflows.error ??
            (workflows.data
              ? `${workflows.data.queued} queued · ${workflows.data.running} running · ${workflows.data.verified_24h} verified / 24 h`
              : "")
          }
          loading={workflows.loading}
        />

        <div className="card session-actions-card">
          <div>
            <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>Operacje sesyjne</p>
            <p className="small muted" style={{ margin: "4px 0 12px" }}>
              Jednorazowe sprawdzenie ESPI i przejęcie najwyżej jednego zlecenia. Dalszy workflow wykonuje Codex.
            </p>
          </div>
          <div className="command-row">
            <label className="session-model-select">
              Model orchestratora
              <select value={orchestratorModel} onChange={(event) => setOrchestratorModel(event.target.value)} disabled={sessionAction != null}>
                {ORCHESTRATOR_MODELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <button className="btn" onClick={() => void recheckEspi()} disabled={sessionAction != null}>
              <IconRefresh size={14} className={sessionAction === "espi" ? "spin" : ""} />
              {sessionAction === "espi" ? "Sprawdzam ESPI…" : "Sprawdź ESPI"}
            </button>
            <button className="btn accent" onClick={() => void processOne()} disabled={sessionAction != null}>
              <IconPlayerPlay size={14} className={sessionAction === "queue" ? "spin" : ""} />
              {sessionAction === "queue" ? "Odbieram zlecenie…" : "Wykonaj jedną próbę kolejki"}
            </button>
          </div>
          <p className="small muted" style={{ margin: "8px 0 0" }}>{modelPolicyDescription(orchestratorModel)} Wybór dotyczy żądanego orchestratora Codex; host nie ujawnia dokładnego deploymentu.</p>
          <div aria-live="polite">
            {sessionError && <p className="small neg" style={{ margin: "10px 0 0" }}>Błąd: {sessionError}</p>}
            {sessionInfo && <p className="small pos" style={{ margin: "10px 0 0" }}>{sessionInfo}</p>}
          </div>
        </div>

        <p className="settings-section-label">Diagnostyka i limity</p>
        <div className="card">
          <p style={{ fontWeight: 500, fontSize: 13, margin: "0 0 10px" }}>
            Źródła danych (ostatnie 24 h)
          </p>
          {scrapers.loading && <p className="small muted">Sprawdzanie…</p>}
          {scrapers.error && <p className="small neg">{scrapers.error}</p>}
          {scrapers.data &&
            Object.entries(scrapers.data).map(([source, info]) => (
              <div className="spread" key={source} style={{ padding: "5px 0", fontSize: 13 }}>
                <span>
                  <span style={{ fontWeight: 500 }}>{source}</span>
                  <span className="small muted" style={{ marginLeft: 8 }}>
                    ostatni sukces: {relativeDate(info.last_ok_at)}
                    {info.last_error &&
                      ` · ostatni błąd: HTTP ${info.last_error.status ?? "—"} (${relativeDate(info.last_error.at)})`}
                  </span>
                </span>
                <span
                  className={`badge ${
                    info.status === "healthy" || info.status === "recovered"
                      ? "success"
                      : info.status === "degraded"
                        ? "danger"
                        : "warning"
                  }`}
                >
                  {info.status === "healthy"
                    ? "OK"
                    : info.status === "recovered"
                      ? `Przywrócono · ${info.errors_24h} bł.`
                      : info.status === "degraded"
                        ? `Błąd · ${info.errors_24h}`
                        : "Brak danych"}
                </span>
              </div>
            ))}
          <p className="small muted" style={{ margin: "8px 0 0" }}>
            Gdy po odświeżeniu metryki pokazują „b/d”, sprawdź:{" "}
            <code>GET /api/companies/&#123;ticker&#125;/mapping-report</code> — pokaże,
            których pozycji sprawozdań aplikacja nie rozpoznaje.
            PortalAnaliz jest synchronizowany tylko dla powiązanych wątków i tylko w
            najnowszym zakresie, żeby nie odpytywać starych stron bez potrzeby.
          </p>
        </div>
        <div className="card">
          <div className="spread" style={{ marginBottom: 10 }}>
            <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>
              Budżet AI (UTC)
            </p>
            {aiUsage.data && <span className="small muted">{aiUsage.data.day}</span>}
          </div>
          {aiUsage.loading && <p className="small muted">Sprawdzanie…</p>}
          {aiUsage.error && <p className="small neg">{aiUsage.error}</p>}
          {aiUsage.data && (
            <div style={{ display: "grid", gap: 7, fontSize: 13 }}>
              <div className="spread">
                <span>Analizy</span>
                <strong>{aiUsage.data.usage.runs} / {aiUsage.data.limits.runs}</strong>
              </div>
              <div className="spread">
                <span>Wywołania dostawców (retry wliczone)</span>
                <strong>
                  {aiUsage.data.usage.provider_attempts} / {aiUsage.data.limits.provider_attempts}
                </strong>
              </div>
              <div className="spread">
                <span>Zmierzony ruch tokenów</span>
                <strong>
                  {aiUsage.data.usage.input_tokens + aiUsage.data.usage.output_tokens}
                  {" / "}{aiUsage.data.limits.tokens}
                </strong>
              </div>
              <div className="spread small muted">
                <span>
                  cache: {aiUsage.data.usage.cache_hits} · billable: {aiUsage.data.usage.billable_calls}
                </span>
                <span>billing nieznany: {aiUsage.data.usage.unknown_billing_calls}</span>
              </div>
              <p className="small muted" style={{ margin: "3px 0 0" }}>
                Koszt pieniężny pojawi się dopiero z wersjonowaną tabelą cen modelu;
                aplikacja nie przelicza tokenów według zgadywanej stawki.
              </p>
            </div>
          )}
        </div>
        <div className="card">
          <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>Konfiguracja</p>
          <p className="small muted" style={{ margin: "6px 0 0", lineHeight: 1.6 }}>
            Sekrety trzymane są wyłącznie w <code>backend/.env</code> (PA_USERNAME,
            PA_PASSWORD, BR_USERNAME, BR_PASSWORD, ANTHROPIC_API_KEY) oraz{" "}
            <code>frontend/.env.local</code> (BACKEND_URL).
          </p>
        </div>
      </div>
    </main>
  );
}
