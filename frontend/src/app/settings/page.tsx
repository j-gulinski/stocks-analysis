"use client";

/** Settings — connection status checks only; secrets never leave the backend. */
import { IconCheck, IconX } from "@tabler/icons-react";
import {
  getBrLoginStatus,
  getForumLoginStatus,
  getHealth,
  getScrapersHealth,
  getWorkflowStatus,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { relativeDate } from "@/lib/format";

function StatusCard({
  title,
  ok,
  detail,
  loading,
  okLabel = "OK",
  errorLabel = "błąd",
}: {
  title: string;
  ok: boolean | null;
  detail: string;
  loading: boolean;
  okLabel?: string;
  errorLabel?: string;
}) {
  return (
    <div className="card spread">
      <div>
        <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>{title}</p>
        <p className="small muted" style={{ margin: "4px 0 0" }}>
          {loading ? "Sprawdzanie…" : detail}
        </p>
      </div>
      {!loading && ok != null && (
        <span className={`badge ${ok ? "success" : "danger"}`}>
          {ok ? <IconCheck size={13} /> : <IconX size={13} />} {ok ? okLabel : errorLabel}
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
  const workflows = useApi(getWorkflowStatus, []);

  return (
    <main>
      <h1 style={{ fontSize: 19, marginBottom: 16 }}>Settings</h1>
      <div style={{ display: "grid", gap: 10 }}>
        <StatusCard
          title="Backend + baza danych"
          ok={health.error ? false : health.data ? true : null}
          detail={health.error ?? "API odpowiada, połączenie z bazą działa."}
          loading={health.loading}
        />
        <StatusCard
          title="Logowanie BiznesRadar"
          ok={biznesradar.data?.ok ?? (biznesradar.error ? false : null)}
          detail={biznesradar.data?.detail ?? biznesradar.error ?? ""}
          loading={biznesradar.loading}
        />
        <StatusCard
          title="Logowanie PortalAnaliz"
          ok={forum.data?.ok ?? (forum.error ? false : null)}
          detail={forum.data?.detail ?? forum.error ?? ""}
          loading={forum.loading}
        />
        <StatusCard
          title="Codex workflow queue"
          ok={workflows.data ? workflows.data.ok : workflows.error ? false : null}
          detail={
            workflows.error
              ? workflows.error
              : workflows.data
                ? `${workflows.data.queued} queued · ${workflows.data.running} running · ${workflows.data.verified_24h} verified / 24 h`
                : ""
          }
          loading={workflows.loading}
          okLabel="gotowe"
          errorLabel="błąd"
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
                  className={`badge ${info.errors_24h === 0 ? "success" : info.last_ok_at ? "warning" : "danger"}`}
                >
                  {info.errors_24h === 0 ? "OK" : `${info.errors_24h} błędów`}
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
          <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>Konfiguracja</p>
          <p className="small muted" style={{ margin: "6px 0 0", lineHeight: 1.6 }}>
            Sekrety trzymane są wyłącznie w <code>backend/.env</code> (PA_USERNAME,
            PA_PASSWORD, BR_USERNAME, BR_PASSWORD) oraz{" "}
            <code>frontend/.env.local</code> (BACKEND_URL).
          </p>
        </div>
      </div>
    </main>
  );
}
