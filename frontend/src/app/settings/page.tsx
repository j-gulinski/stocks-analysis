"use client";

/** Settings — connection status checks only; secrets never leave the backend. */
import { IconCheck, IconX } from "@tabler/icons-react";
import {
  getAiUsage,
  getBrLoginStatus,
  getForumLoginStatus,
  getHealth,
  getScrapersHealth,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { relativeDate } from "@/lib/format";

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
    </div>
  );
}

export default function SettingsPage() {
  const health = useApi(getHealth, []);
  const forum = useApi(getForumLoginStatus, []);
  const biznesradar = useApi(getBrLoginStatus, []);
  const scrapers = useApi(getScrapersHealth, []);
  const aiUsage = useApi(getAiUsage, []);

  return (
    <main>
      <h1 style={{ fontSize: 19, marginBottom: 16 }}>Settings</h1>
      <div style={{ display: "grid", gap: 10 }}>
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
