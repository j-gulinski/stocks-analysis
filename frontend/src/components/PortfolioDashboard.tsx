"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconBriefcase,
  IconDatabaseOff,
  IconFileUpload,
  IconRefresh,
  IconShieldCheck,
  IconSparkles,
} from "@tabler/icons-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getPortfolioWorkspace, importPortfolioOperations, previewPortfolioOperations, queuePortfolioReview, syncMyfundPortfolio } from "@/lib/api";
import { fmtDate, fmtPct, fmtPln, signClass } from "@/lib/format";
import type {
  PortfolioLiquidity,
  PortfolioPosition,
  PortfolioReviewSnapshot,
  PortfolioReviewStatus,
  PortfolioOperationsPreview,
  PortfolioWorkspace,
} from "@/lib/types";

function ageInDays(value: string): number {
  return Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000);
}

function exactTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function signedPln(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${fmtPln(value)}`;
}

function profitPct(profit: number | null, cost: number | null): number | null {
  if (profit == null || cost == null || cost <= 0) return null;
  return profit / cost * 100;
}

function providerLabel(provider: string): string {
  return provider.toLowerCase() === "myfund" ? "myfund" : provider;
}

function modelProvenanceLabel(requested: string, actual: string, substitution: string | null): string {
  if (substitution?.trim()) return substitution.trim();
  if (actual.trim() === requested.trim()) return "zgodne z żądaniem";
  const normalized = actual.trim().toLowerCase();
  if ([
    "not exposed",
    "not-exposed",
    "unavailable",
    "not available",
    "model unavailable",
    "deployment unavailable",
    "does not expose",
    "nieujawn",
    "niedostęp",
  ].some((marker) => normalized.includes(marker))) {
    return "konkretne wdrożenie nieujawnione";
  }
  return "uwaga: brak wyjaśnienia różnicy";
}

function hasCurrentSyncFailure(workspace: PortfolioWorkspace): boolean {
  const failure = workspace.last_sync_failure;
  if (!failure) return false;
  if (!workspace.latest_sync) return true;
  return new Date(failure.requested_at).getTime() >= new Date(workspace.latest_sync.requested_at).getTime();
}

function mappingLabel(position: PortfolioPosition): { text: string; tone: string } | null {
  if (position.mapping_status === "unmatched") return { text: "nierozpoznany", tone: "warning" };
  if (position.mapping_status === "ignored" || position.mapping_kind === "ignored") return { text: "pominięty świadomie", tone: "muted" };
  if (position.mapping_kind === "cash") return { text: "gotówka", tone: "neutral" };
  if (position.mapping_kind === "other") return { text: "poza analizą spółek", tone: "muted" };
  return null;
}

function liquidityLabel(item: PortfolioLiquidity | undefined): React.ReactNode {
  if (!item || item.status === "unavailable" || item.estimated_exit_days == null) {
    return <span className="muted">brak danych</span>;
  }
  return <><strong>{item.estimated_exit_days < 1 ? "< 1" : item.estimated_exit_days.toLocaleString("pl-PL", { maximumFractionDigits: 1 })} dni</strong><small>przy {item.participation_pct}% obrotu</small></>;
}

export default function PortfolioDashboard({ initial }: { initial: PortfolioWorkspace }) {
  const [workspace, setWorkspace] = useState(initial);
  const [syncing, setSyncing] = useState(false);
  const [commandError, setCommandError] = useState<string | null>(null);
  const [reviewQueueing, setReviewQueueing] = useState(false);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [operationsPayload, setOperationsPayload] = useState<{ filename: string; content: string } | null>(null);
  const [operationsPreview, setOperationsPreview] = useState<PortfolioOperationsPreview | null>(null);
  const [operationsBusy, setOperationsBusy] = useState(false);
  const [operationsNotice, setOperationsNotice] = useState<string | null>(null);
  const [operationsError, setOperationsError] = useState<string | null>(null);
  const snapshot = workspace.snapshot;
  const provider = providerLabel(workspace.provider);

  const liquidityByPosition = useMemo(
    () => new Map(workspace.liquidity.map((item) => [item.position_id, item])),
    [workspace.liquidity],
  );
  const coveredPositions = useMemo(
    () => new Set(workspace.scenario_sensitivity?.covered.map((item) => item.position_id) ?? []),
    [workspace.scenario_sensitivity],
  );
  const exclusions = useMemo(
    () => new Map(workspace.scenario_sensitivity?.exclusions.map((item) => [item.position_id, item]) ?? []),
    [workspace.scenario_sensitivity],
  );

  async function synchronize() {
    setSyncing(true);
    setCommandError(null);
    try {
      const result = await syncMyfundPortfolio();
      setWorkspace(result);
    } catch {
      setCommandError("Synchronizacja nie powiodła się. Pokazuję ostatni poprawny stan.");
      try {
        // The failed attempt is durable. Re-read it without retrying the
        // provider so the notice updates while the good snapshot remains.
        setWorkspace(await getPortfolioWorkspace());
      } catch {
        // Keep the already rendered snapshot if even the local read fails.
      }
    } finally {
      setSyncing(false);
    }
  }

  async function queueReview() {
    setReviewQueueing(true);
    setReviewNotice(null);
    let queued: Awaited<ReturnType<typeof queuePortfolioReview>>;
    try {
      queued = await queuePortfolioReview();
    } catch {
      setReviewNotice("Nie udało się zaplanować analizy. Zapisany portfel pozostał bez zmian.");
      setReviewQueueing(false);
      return;
    }
    setReviewNotice(queued.created ? "Analiza została zaplanowana." : "Analiza dla tego samego stanu już istnieje.");
    try {
      setWorkspace(await getPortfolioWorkspace());
    } catch {
      // The durable command succeeded. Keep its accurate confirmation even if
      // refreshing the local read model failed.
    } finally {
      setReviewQueueing(false);
    }
  }

  async function previewOperations(file: File) {
    setOperationsBusy(true);
    setOperationsNotice(null);
    setOperationsError(null);
    setOperationsPreview(null);
    setOperationsPayload(null);
    try {
      if (file.size > 5_000_000) throw new Error("Plik przekracza limit 5 MB.");
      const payload = { filename: file.name, content: await file.text() };
      const preview = await previewPortfolioOperations(payload);
      setOperationsPayload(payload);
      setOperationsPreview(preview);
      setOperationsNotice("Podgląd jest gotowy. Żadna operacja nie została jeszcze zapisana.");
    } catch (error) {
      setOperationsError(error instanceof Error ? error.message : "Nie udało się odczytać pliku CSV.");
    } finally {
      setOperationsBusy(false);
    }
  }

  async function confirmOperationsImport() {
    if (!operationsPayload || !operationsPreview) return;
    setOperationsBusy(true);
    setOperationsError(null);
    try {
      const result = await importPortfolioOperations({
        ...operationsPayload,
        expected_fingerprint: operationsPreview.fingerprint,
        confirm_full_export: true,
      });
      setWorkspace(result.workspace);
      setOperationsPayload(null);
      setOperationsPreview(null);
      setOperationsNotice(result.import.changed
        ? `Zapisano pełną historię: ${result.import.imported_count} operacji.`
        : "Ten sam pełny eksport jest już zapisany.");
    } catch (error) {
      setOperationsError(error instanceof Error ? error.message : "Import historii operacji nie powiódł się.");
    } finally {
      setOperationsBusy(false);
    }
  }

  if (!workspace.configured) {
    return (
      <main className="page-stack portfolio-page">
        <PortfolioHeader workspace={workspace} syncing={false} onSync={synchronize} />
        <section className="portfolio-empty">
          <IconDatabaseOff size={25} />
          <h2>Portfolio nie jest jeszcze połączone</h2>
          <p>Dodaj klucz API i nazwę jednego portfela myfund w konfiguracji środowiska. Workbench nie przechowuje loginu ani hasła.</p>
          <Link className="btn" href="/settings">Otwórz System <IconArrowRight size={14} /></Link>
        </section>
      </main>
    );
  }

  if (!snapshot) {
    return (
      <main className="page-stack portfolio-page">
        <PortfolioHeader workspace={workspace} syncing={syncing} onSync={synchronize} />
        {commandError && <div className="error-box" role="alert">{commandError}</div>}
        {hasCurrentSyncFailure(workspace) && <SyncFailure workspace={workspace} />}
        <section className="portfolio-empty">
          <IconBriefcase size={25} />
          <h2>Brak pierwszego snapshotu</h2>
          <p>Synchronizacja uruchomi się dopiero po użyciu przycisku. Odczyt tej strony nie kontaktuje się z myfund.</p>
          <button className="btn accent" onClick={() => void synchronize()} disabled={syncing}>
            <IconRefresh size={14} className={syncing ? "spin" : ""} /> {syncing ? "Synchronizuję…" : `Synchronizuj ${provider}`}
          </button>
        </section>
      </main>
    );
  }

  const resultPct = profitPct(snapshot.profit, snapshot.cost_basis);
  const analyticsAvailable = workspace.coverage?.analytics_available === true;
  const partialAnalytics = workspace.coverage?.analytics_status === "partial";
  const analyticsBasis = workspace.concentration?.basis_value ?? snapshot.total_value;
  const scenario = workspace.scenario_sensitivity;
  const scenarioCoverage = scenario?.coverage_value_pct ?? 0;
  const historyGaps = new Set(workspace.history_quality?.gaps ?? []);
  const attention: string[] = [];
  if (ageInDays(snapshot.as_of) > 3) attention.push(`Stan portfela ma ${ageInDays(snapshot.as_of)} dni — zsynchronizuj aktualne wartości.`);
  if ((workspace.coverage?.unmapped_positions ?? 0) > 0) attention.push(`${workspace.coverage!.unmapped_positions} pozycji nie ma pewnego mapowania i nie wchodzi do analizy spółek.`);
  if (analyticsAvailable && scenarioCoverage === 0 && workspace.positions.some((item) => item.mapping_kind === "company")) attention.push("Żadna pozycja nie ma aktualnej zweryfikowanej wyceny; wrażliwość scenariuszowa jest niedostępna.");
  else if (scenario && scenario.exclusions.length > 0) attention.push(`${scenario.exclusions.length} pozycji nie wchodzi do wrażliwości scenariuszowej.`);
  if (workspace.history.length === 0) attention.push("myfund nie zwrócił historii wartości i stóp zwrotu dla tego snapshotu.");
  if (workspace.operations.status === "missing") attention.push("Brak historii operacji; zaimportuj pełny eksport CSV z myfund, aby uzgodnić przepływy.");
  else if (workspace.operations.flow_reconciliation.status === "mismatch") attention.push("Historia operacji nie uzgadnia się ze zmianami wkładu myfund.");
  snapshot.gaps.filter((gap) => !historyGaps.has(gap)).forEach((gap) => attention.push(gap));

  return (
    <main className="page-stack portfolio-page">
      <PortfolioHeader workspace={workspace} syncing={syncing} onSync={synchronize} />
      {commandError && <div className="error-box" role="alert">{commandError}</div>}
      {hasCurrentSyncFailure(workspace) && <SyncFailure workspace={workspace} />}
      {workspace.reconciliation?.status === "unreconciled" && <ReconciliationWarning reconciliation={workspace.reconciliation} />}

      <section className="portfolio-summary" aria-label="Podsumowanie portfela">
        <SummaryMetric label="Wartość" value={fmtPln(snapshot.total_value)} note={`wg ${provider}`} />
        <SummaryMetric label="Koszt" value={fmtPln(snapshot.cost_basis)} note={snapshot.cost_basis == null ? "niepełne dane pozycji" : `suma bieżących pozycji · ${provider}`} />
        <SummaryMetric label="Wynik" value={signedPln(snapshot.profit)} tone={signClass(snapshot.profit)} note={resultPct == null ? "niepełne dane pozycji" : `${fmtPct(resultPct, { signed: true })} · bieżące pozycje`} />
        <SummaryMetric label="Gotówka" value={fmtPln(snapshot.cash_value)} note={snapshot.cash_value == null ? "brak rozpoznanej pozycji gotówkowej" : partialAnalytics ? "wartość zachowanego wiersza; suma dostawcy nieuzgodniona" : `${fmtPct(snapshot.total_value > 0 ? snapshot.cash_value / snapshot.total_value * 100 : 0)} portfela`} />
        <SummaryMetric label="Pokrycie scenariuszami" value={analyticsAvailable ? fmtPct(scenarioCoverage) : "niedostępne"} note={analyticsAvailable ? partialAnalytics ? "częściowe; tylko zachowane pozycje ze zweryfikowaną wyceną" : "tylko zweryfikowane wyceny" : "brak zachowanych pozycji"} />
      </section>

      {attention.length > 0 && (
        <section className="portfolio-attention" aria-labelledby="portfolio-attention-title">
          <div><IconAlertTriangle size={17} /><h2 id="portfolio-attention-title">Wymaga uwagi</h2></div>
          <ul>{attention.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
        </section>
      )}

      {workspace.risk_context && <PortfolioRiskAttention workspace={workspace} />}

      <PositionsSection
        positions={workspace.positions}
        total={analyticsBasis}
        liquidity={liquidityByPosition}
        covered={coveredPositions}
        exclusions={exclusions}
        analyticsAvailable={analyticsAvailable}
      />

      {workspace.positions.length > 0 && workspace.concentration && (
        <section className="portfolio-two-column">
          <ConcentrationPanel title="Koncentracja sektorowa" groups={workspace.concentration.sectors} top1={workspace.concentration.top1_pct} top3={workspace.concentration.top3_pct} />
          <ConcentrationPanel title="Klasy aktywów wg myfund" groups={workspace.concentration.asset_types} />
        </section>
      )}

      <HistorySection workspace={workspace} />
      <OperationsSection
        workspace={workspace}
        preview={operationsPreview}
        busy={operationsBusy}
        notice={operationsNotice}
        error={operationsError}
        onFile={previewOperations}
        onImport={confirmOperationsImport}
      />
      <ScenarioSection workspace={workspace} analyticsAvailable={analyticsAvailable} />
      <PortfolioReviewSection workspace={workspace} queueing={reviewQueueing} notice={reviewNotice} onQueue={queueReview} analyticsAvailable={analyticsAvailable} />
      <LiquidityAudit workspace={workspace} />
    </main>
  );
}

function PortfolioHeader({ workspace, syncing, onSync }: { workspace: PortfolioWorkspace; syncing: boolean; onSync: () => void }) {
  return (
    <section className="page-header portfolio-header">
      <div>
        <p className="eyebrow">Portfolio</p>
        <h1>{workspace.portfolio_label || "Mój portfel"}</h1>
        <p>{workspace.snapshot ? `Stan dokładnie na ${exactTimestamp(workspace.snapshot.as_of)} · ${ageInDays(workspace.snapshot.as_of) <= 1 ? "aktualny snapshot" : `${ageInDays(workspace.snapshot.as_of)} dni od snapshotu`}` : "Rzeczywiste aktywa, historia i ekspozycja na scenariusze spółek."}</p>
      </div>
      {workspace.configured && (
        <button className="btn accent" onClick={onSync} disabled={syncing}>
          <IconRefresh size={14} className={syncing ? "spin" : ""} /> {syncing ? "Synchronizuję…" : `Synchronizuj ${providerLabel(workspace.provider)}`}
        </button>
      )}
    </section>
  );
}

function SyncFailure({ workspace }: { workspace: PortfolioWorkspace }) {
  const failure = workspace.last_sync_failure!;
  return (
    <div className="portfolio-sync-failure" role="status">
      <IconAlertTriangle size={16} />
      <div><strong>Ostatnia synchronizacja nie powiodła się</strong><span>{fmtDate(failure.requested_at)}{failure.error ? ` · ${failure.error.replace(/[.\s]+$/, "")}` : ""}. {workspace.snapshot ? "Pokazuję ostatni poprawny snapshot." : "Dane nie zostały zapisane."}</span></div>
    </div>
  );
}

function ReconciliationWarning({ reconciliation }: { reconciliation: NonNullable<PortfolioWorkspace["reconciliation"]> }) {
  return (
    <section className="portfolio-reconciliation-warning" role="alert">
      <IconAlertTriangle size={19} />
      <div>
        <strong>Wiersze portfela nie uzgadniają się z sumą myfund</strong>
        <p>Wiersze: {fmtPln(reconciliation.retained_value)} · suma dostawcy: {fmtPln(reconciliation.provider_total)} · różnica: {signedPln(reconciliation.delta)} · tolerancja: {fmtPln(reconciliation.tolerance)}.</p>
        <span>Analityka pozostaje widoczna jako częściowa i opiera się na zachowanych pozycjach; suma dostawcy pozostaje punktem odniesienia.</span>
        {reconciliation.affected_figures.length > 0 && <ul>{reconciliation.affected_figures.map((item) => <li key={item}>{item}</li>)}</ul>}
      </div>
    </section>
  );
}

function PortfolioRiskAttention({ workspace }: { workspace: PortfolioWorkspace }) {
  const context = workspace.risk_context!;
  const stale = context.companies.filter((item) => item.research.stale);
  const snapshotFired = context.companies.filter((item) => item.snapshot_known_fired_count > 0);
  const currentOnlyFired = context.companies.filter((item) => item.current_only_fired_count > 0);
  const groups = context.shared_groups;
  if (stale.length === 0 && snapshotFired.length === 0 && currentOnlyFired.length === 0 && groups.length === 0) return null;
  const tickerByCompany = new Map(context.companies.map((item) => [item.company_id, item.ticker || `spółka ${item.company_id}`]));
  return (
    <section className="portfolio-risk-attention" aria-labelledby="portfolio-risk-title">
      <div className="portfolio-risk-heading"><div><p className="section-label">Kontekst ryzyk</p><h2 id="portfolio-risk-title">Sygnały wymagające sprawdzenia</h2></div><span>Snapshot {exactTimestamp(context.snapshot_as_of)} · kontekst {exactTimestamp(context.context_generated_at)}</span></div>
      <div className="portfolio-risk-counts">
        {stale.length > 0 && <span><strong>{stale.length}</strong> brakujący lub nieaktualny Research</span>}
        {snapshotFired.length > 0 && <span className="danger"><strong>{snapshotFired.reduce((sum, item) => sum + item.snapshot_known_fired_count, 0)}</strong> naruszone na moment snapshotu</span>}
        {currentOnlyFired.length > 0 && <span className="current"><strong>{currentOnlyFired.reduce((sum, item) => sum + item.current_only_fired_count, 0)}</strong> naruszone tylko w bieżącym kontekście</span>}
        {groups.length > 0 && <span><strong>{groups.length}</strong> wspólnych ekspozycji</span>}
      </div>
      <details>
        <summary>Spółki i wspólne ekspozycje</summary>
        <div className="portfolio-risk-details">
          {stale.length > 0 && <section><h3>Brakujący lub nieaktualny Research</h3><ul>{stale.map((item) => <li key={item.company_id}><strong>{item.ticker || item.company_id}</strong><span>{item.research.as_of ? `${item.research.age_days} dni · ${item.research.status}` : "brak snapshotu Research"}</span></li>)}</ul></section>}
          {snapshotFired.length > 0 && <section><h3>Naruszone do {exactTimestamp(context.snapshot_as_of)}</h3><ul>{snapshotFired.flatMap((item) => item.snapshot_known_fired_falsifiers.map((row) => <li key={`${item.company_id}-${row.id}`}><strong>{item.ticker || item.company_id}</strong><span>{row.statement} · aktualizacja {exactTimestamp(row.updated_at)}</span></li>))}</ul><small>Te wiersze istniały i nie zmieniły się po momencie snapshotu.</small></section>}
          {currentOnlyFired.length > 0 && <section><h3>Naruszone tylko w kontekście z {exactTimestamp(context.context_generated_at)}</h3><ul>{currentOnlyFired.flatMap((item) => item.current_only_fired_falsifiers.map((row) => <li key={`${item.company_id}-${row.id}`}><strong>{item.ticker || item.company_id}</strong><span>{row.statement} · aktualizacja {exactTimestamp(row.updated_at)}</span></li>))}</ul><small>Tych statusów nie przypisujemy do wcześniejszego snapshotu portfela.</small></section>}
          {groups.length > 0 && <section><h3>Współekspozycja</h3><ul>{groups.map((group) => { const groupType = group.type ?? group.group_type; const currentMetadata = group.time_basis === "includes-current-only"; const metadataTimes = group.evidence_basis.map((item) => item.company_metadata_updated_at).filter((item): item is string => Boolean(item)); return <li key={`${groupType}-${group.label}`}><strong>{groupType === "sector" ? "Sektor" : "Archetyp"}: {group.label}</strong><span>{group.company_ids.map((id) => tickerByCompany.get(id)).join(", ")} · {fmtPln(group.value)} · {currentMetadata ? `zawiera bieżące metadane${metadataTimes.length ? ` (${exactTimestamp(metadataTimes.sort().at(-1))})` : ""}` : "podstawa znana na moment snapshotu"}</span></li>; })}</ul><small>To wspólna ekspozycja według etykiet sektora lub archetypu. Nie oznacza korelacji, kowariancji ani wspólnego prawdopodobieństwa wyniku.</small></section>}
        </div>
      </details>
    </section>
  );
}

function SummaryMetric({ label, value, note, tone = "" }: { label: string; value: string; note: string; tone?: string }) {
  return <div><span>{label}</span><strong className={tone}>{value}</strong><small>{note}</small></div>;
}

function PositionsSection({ positions, total, liquidity, covered, exclusions, analyticsAvailable }: {
  positions: PortfolioPosition[];
  total: number;
  liquidity: Map<number, PortfolioLiquidity>;
  covered: Set<number>;
  exclusions: Map<number, { reason: string; latest_status?: string | null }>;
  analyticsAvailable: boolean;
}) {
  return (
    <section className="portfolio-section" aria-labelledby="portfolio-positions-title">
      <div className="portfolio-section-heading"><div><p className="section-label">Skład</p><h2 id="portfolio-positions-title">Pozycje</h2></div><span>{positions.length} instrumentów</span></div>
      {positions.length === 0 ? (
        <div className="portfolio-valid-empty"><strong>Portfel jest pusty</strong><span>Synchronizacja zakończyła się poprawnie i nie zwróciła pozycji.</span></div>
      ) : (
        <div className="portfolio-position-table" role="table" aria-label="Pozycje portfela">
          <div className="portfolio-position-head" role="row">
            <span>Instrument</span><span>{analyticsAvailable ? "Wartość / udział" : "Wartość"}</span><span>Koszt / wynik</span><span>Płynność</span><span>Scenariusze</span>
          </div>
          {positions.map((position) => {
            const badge = mappingLabel(position);
            const allocation = analyticsAvailable ? (total > 0 ? position.value / total * 100 : 0) : null;
            const excluded = exclusions.get(position.id);
            const displayTicker = position.company_ticker || position.ticker || position.name;
            const providerLabel = position.name !== displayTicker ? position.name : null;
            const name = <><strong>{displayTicker}</strong>{providerLabel && <span>{providerLabel}</span>}</>;
            return (
              <div className="portfolio-position-row" role="row" key={position.id}>
                <div className="portfolio-position-name" role="cell">
                  {position.company_id && position.company_ticker ? <Link href={`/stock/${position.company_ticker}`}>{name}</Link> : <div>{name}</div>}
                  <small>{position.sector || position.asset_type || "Brak klasyfikacji"}</small>
                  {badge && <span className={`badge ${badge.tone}`}>{badge.text}</span>}
                  {badge && <small className="portfolio-mapping-reason">{position.mapping_reason}</small>}
                </div>
                <div role="cell"><strong>{fmtPln(position.value)}</strong>{allocation != null && <span>{fmtPct(allocation)}</span>}{position.quantity != null && <small>{position.quantity.toLocaleString("pl-PL", { maximumFractionDigits: 4 })} szt.</small>}</div>
                <div role="cell"><strong>{fmtPln(position.cost_basis)}</strong><span className={signClass(position.profit)}>{signedPln(position.profit)}</span><small>wg dostawcy</small>{position.operation_cost_basis_status === "reconciled" && <small>z operacji: koszt {fmtPln(position.operation_cost_basis)} · wynik {signedPln(position.operation_profit)}</small>}{position.operation_cost_basis_status === "mismatch" && <small title={position.operation_cost_basis_gaps.join(" ")}>operacje: ilość nieuzgodniona</small>}</div>
                <div role="cell" className="portfolio-liquidity-cell">{analyticsAvailable ? liquidityLabel(liquidity.get(position.id)) : <span className="muted">brak zachowanych danych</span>}</div>
                <div role="cell">
                  {!analyticsAvailable ? <span className="muted">brak zachowanych danych</span> : covered.has(position.id) ? <><span className="badge success">pokryta</span><small>zweryfikowana wycena</small></> : position.mapping_kind === "company" ? <><span className="badge muted">bez pokrycia</span><small title={excluded?.reason}>{excluded?.latest_status ? `ostatnia: ${excluded.latest_status}` : "brak aktualnej zweryfikowanej wyceny"}</small></> : <span className="muted">nie dotyczy</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ConcentrationPanel({ title, groups, top1, top3 }: { title: string; groups: Array<{ label: string; value: number; allocation_pct: number }>; top1?: number; top3?: number }) {
  return (
    <section className="portfolio-section portfolio-concentration">
      <div className="portfolio-section-heading"><h2>{title}</h2>{top1 != null && <span>Największa pozycja {fmtPct(top1)} · 3 największe pozycje {fmtPct(top3)}</span>}</div>
      {groups.length === 0 ? <p className="muted">Brak sklasyfikowanych pozycji.</p> : <div className="portfolio-bars">{groups.slice(0, 6).map((group) => <div key={group.label}><div><span>{group.label}</span><strong>{fmtPct(group.allocation_pct)}</strong></div><span className="portfolio-bar"><i style={{ width: `${Math.min(100, group.allocation_pct)}%` }} /></span></div>)}</div>}
    </section>
  );
}

function HistorySection({ workspace }: { workspace: PortfolioWorkspace }) {
  const methods = workspace.performance_methods;
  const benchmark = workspace.snapshot?.benchmark_name;
  const historyQuality = workspace.history_quality;
  const performanceWindow = methods?.window_start && methods.window_end
    ? `${fmtDate(methods.window_start)}–${fmtDate(methods.window_end)}`
    : "brak pełnego okna";
  return (
    <section className="portfolio-section" aria-labelledby="portfolio-history-title">
      <div className="portfolio-section-heading"><div><p className="section-label">Historia</p><h2 id="portfolio-history-title">Wartość i wyniki wg myfund</h2></div><span>{benchmark ? `Benchmark dostawcy: ${benchmark}` : "Brak benchmarku dostawcy"}</span></div>
      {historyQuality?.status === "partial" && <div className="portfolio-history-partial"><IconAlertTriangle size={15} /><div><strong>Historia jest częściowa</strong><span>{historyQuality.gaps.join(" ")}</span></div></div>}
      {methods && <div className="portfolio-performance-grid" aria-label="Niezależnie obliczone wyniki portfela">
        <div>
          <span>TWR · wynik w oknie</span>
          <strong className={signClass(methods.twr_pct)}>{methods.twr_pct == null ? "niedostępny" : fmtPct(methods.twr_pct, { signed: true, digits: 2 })}</strong>
          <small>{methods.twr_status === "complete" ? "pełna seria" : methods.twr_status === "partial" ? "częściowa seria" : "brak podstawy"} · {performanceWindow}</small>
        </div>
        <div>
          <span>XIRR · rocznie</span>
          <strong className={signClass(methods.xirr_pct)}>{methods.xirr_pct == null ? "niedostępny" : fmtPct(methods.xirr_pct, { signed: true, digits: 2 })}</strong>
          <small>{methods.xirr_status === "complete" ? "pełna seria" : methods.xirr_status === "partial" ? "częściowa seria" : "brak podstawy"} · ACT/365</small>
        </div>
        <div>
          <span>Podstawa</span>
          <strong>{methods.observation_count.toLocaleString("pl-PL")} dni</strong>
          <small>{methods.external_flow_count} zmian wkładu · przepływ na koniec dnia</small>
        </div>
      </div>}
      {workspace.history.length === 0 ? <div className="portfolio-valid-empty"><strong>Brak historii od dostawcy</strong><span>Bieżący skład pozostaje użyteczny; nie wyliczamy stopy zwrotu z przybliżeń.</span></div> : <div className="portfolio-chart-grid">
        <div><h3>Wartość i wkład</h3><div className="portfolio-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={workspace.history}><CartesianGrid stroke="#2a3440" vertical={false} /><XAxis dataKey="date" tickFormatter={(value) => fmtDate(String(value))} tick={{ fill: "#8797a8", fontSize: 10 }} /><YAxis tick={{ fill: "#8797a8", fontSize: 10 }} width={68} /><Tooltip labelFormatter={(value) => fmtDate(String(value))} formatter={(value) => fmtPln(typeof value === "number" ? value : null)} /><Legend /><Line type="monotone" dataKey="value" name="Wartość" stroke="#58a6ff" dot={false} /><Line type="monotone" dataKey="contributed" name="Wpłacony kapitał wg myfund" stroke="#9fb0bf" dot={false} /></LineChart></ResponsiveContainer></div></div>
        <div><h3>Stopy zwrotu dostawcy</h3><div className="portfolio-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={workspace.history}><CartesianGrid stroke="#2a3440" vertical={false} /><XAxis dataKey="date" tickFormatter={(value) => fmtDate(String(value))} tick={{ fill: "#8797a8", fontSize: 10 }} /><YAxis tickFormatter={(value) => `${value}%`} tick={{ fill: "#8797a8", fontSize: 10 }} width={46} /><Tooltip labelFormatter={(value) => fmtDate(String(value))} formatter={(value) => typeof value === "number" ? fmtPct(value) : "—"} /><Legend /><Line type="monotone" dataKey="provider_return_pct" name="Portfel wg myfund" stroke="#3fd0a4" dot={false} /><Line type="monotone" dataKey="benchmark_return_pct" name={benchmark ? `${benchmark} wg myfund` : "Benchmark wg myfund"} stroke="#efb454" dot={false} /></LineChart></ResponsiveContainer></div></div>
      </div>}
      <div className="portfolio-method-note"><strong>Metoda</strong><span>Stopa portfela i benchmark na wykresie: raportowane przez myfund.</span><span>TWR: dzienne wartości i zmiany wkładu, przepływ na koniec dnia. XIRR: wartość otwarcia okna, datowane zmiany wkładu i wartość końcowa, ACT/365.</span><span>Workbench nie potwierdził, że benchmark jest indeksem dochodowym.</span></div>
    </section>
  );
}

function OperationsSection({ workspace, preview, busy, notice, error, onFile, onImport }: {
  workspace: PortfolioWorkspace;
  preview: PortfolioOperationsPreview | null;
  busy: boolean;
  notice: string | null;
  error: string | null;
  onFile: (file: File) => Promise<void>;
  onImport: () => Promise<void>;
}) {
  const operations = workspace.operations;
  const flowLabels: Record<typeof operations.flow_reconciliation.status, string> = {
    reconciled: "Uzgodnione ze zmianami wkładu",
    mismatch: "Niezgodne ze zmianami wkładu",
    partial: "Uzgodnienie częściowe",
    unavailable: "Brak podstawy do uzgodnienia",
  };
  return (
    <section className="portfolio-section portfolio-operations" aria-labelledby="portfolio-operations-title">
      <div className="portfolio-section-heading">
        <div><p className="section-label">Przepływy</p><h2 id="portfolio-operations-title">Historia operacji</h2></div>
        <span>{operations.count > 0 ? `${operations.count} operacji · ${fmtDate(operations.date_from)}–${fmtDate(operations.date_to)}` : "Pełny eksport CSV z myfund"}</span>
      </div>

      {operations.status === "imported" ? <>
        <div className="portfolio-operation-metrics">
          <div><span>Wpłaty</span><strong>{fmtPln(operations.deposit_total_pln)}</strong></div>
          <div><span>Wypłaty</span><strong>{fmtPln(operations.withdrawal_total_pln)}</strong></div>
          <div><span>Uzgodnienie przepływów</span><strong>{flowLabels[operations.flow_reconciliation.status]}</strong><small>{operations.flow_reconciliation.matched_days} zgodnych dni</small></div>
        </div>
        {operations.gaps.length > 0 && <div className="portfolio-history-partial"><IconAlertTriangle size={15} /><div><strong>Historia wymaga uwagi</strong><span>{operations.gaps.join(" ")}</span></div></div>}
        {operations.recent.length > 0 && <details className="portfolio-operation-history">
          <summary>Ostatnie operacje ({Math.min(20, operations.recent.length)})</summary>
          <div className="portfolio-operation-table" role="table" aria-label="Ostatnie operacje portfela">
            <div className="portfolio-operation-row head" role="row"><span>Data i typ</span><span>Walor</span><span>Ilość / cena</span><span>Wartość</span></div>
            {operations.recent.map((row) => <div className="portfolio-operation-row" role="row" key={row.id}>
              <div role="cell"><strong>{fmtDate(row.occurred_on)}{row.occurred_at ? ` · ${row.occurred_at.slice(11, 16)}` : ""}</strong><span>{row.kind_label}</span></div>
              <div role="cell"><strong>{row.ticker || row.instrument_name || "Gotówka"}</strong><span>{row.instrument_name}</span></div>
              <div role="cell"><strong>{row.quantity == null ? "—" : row.quantity.toLocaleString("pl-PL", { maximumFractionDigits: 6 })}</strong><span>{row.price == null ? "bez ceny" : fmtPln(row.price)}{row.commission ? ` · prowizja ${fmtPln(row.commission)}` : ""}{row.tax ? ` · podatek ${fmtPln(row.tax)}` : ""}</span></div>
              <div role="cell"><strong className={signClass(row.amount_pln)}>{signedPln(row.amount_pln)}</strong><span>{row.currency}</span></div>
            </div>)}
          </div>
        </details>}
      </> : <div className="portfolio-valid-empty"><strong>Brak historii operacji</strong><span>Bieżący skład i obliczenia z dziennej serii pozostają widoczne. Pełny eksport pozwoli niezależnie uzgodnić wpłaty i wypłaty.</span></div>}

      <div className="portfolio-operation-import">
        <div><strong>Import pełnego eksportu</strong><span>W myfund otwórz Operacje → Historia i modyfikacja, usuń filtry, ustaw wartości w walucie portfela i wybierz eksport CSV. Podgląd nie zapisuje danych.</span></div>
        <label className="btn" htmlFor="portfolio-operations-file"><IconFileUpload size={14} /> {busy ? "Sprawdzam…" : "Wybierz CSV"}</label>
        <input id="portfolio-operations-file" type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) void onFile(file); }} />
      </div>
      {notice && <div className="portfolio-review-notice" role="status">{notice}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {preview && <div className="portfolio-operation-preview">
        <div><strong>Podgląd: {preview.summary.row_count} operacji</strong><span>{fmtDate(preview.summary.date_from)}–{fmtDate(preview.summary.date_to)} · wpłaty {fmtPln(preview.summary.deposit_total_pln)} · wypłaty {fmtPln(preview.summary.withdrawal_total_pln)}</span><small>{preview.summary.unclassified_count > 0 ? `${preview.summary.unclassified_count} nierozpoznanych typów pozostanie jawnie oznaczone.` : "Wszystkie typy użyte do przepływów są rozpoznane."}</small></div>
        <button className="btn accent" disabled={busy} onClick={() => void onImport()}>{busy ? "Zapisuję…" : "Potwierdź pełny eksport i zastąp historię"}</button>
      </div>}
    </section>
  );
}

function ScenarioSection({ workspace, analyticsAvailable }: { workspace: PortfolioWorkspace; analyticsAvailable: boolean }) {
  const scenario = workspace.scenario_sensitivity;
  const current = workspace.snapshot!.total_value;
  return (
    <section className="portfolio-section" aria-labelledby="portfolio-scenarios-title">
      <div className="portfolio-section-heading"><div><p className="section-label">Perspektywy</p><h2 id="portfolio-scenarios-title">Wrażliwość na scenariusze spółek</h2></div><span>Gotówka i pozycje bez pokrycia pozostają bez zmian</span></div>
      {!analyticsAvailable ? <div className="portfolio-valid-empty"><strong>Brak zachowanych pozycji do scenariuszy</strong><span>Nie ma podstawy do agregacji zweryfikowanych wycen.</span></div> : !scenario || scenario.coverage_value_pct === 0 ? <div className="portfolio-valid-empty"><strong>Brak zweryfikowanych scenariuszy</strong><span>Wyceny prowizoryczne, odrzucone lub niepowiązane z najnowszym Research nie są agregowane.</span></div> : <>
        <div className="portfolio-scenario-grid">
          {[{ key: "negative", label: "Spadkowy" }, { key: "base", label: "Bazowy" }, { key: "positive", label: "Wzrostowy" }, { key: "weighted", label: "Ważony w spółkach" }].map(({ key, label }) => {
            const value = scenario.portfolio_values[key as keyof typeof scenario.portfolio_values];
            const change = value != null && current > 0 ? (value / current - 1) * 100 : null;
            return <div key={key}><span>{label}</span><strong>{value == null ? "Celowo niepublikowany" : fmtPln(value)}</strong><small className={signClass(change)}>{value == null ? "Brak skalibrowanych wag dla całego pokrycia" : `${fmtPct(change, { signed: true })} wobec obecnej wartości`}</small></div>;
          })}
        </div>
        <p className="portfolio-scenario-note">Pokrycie {fmtPct(scenario.coverage_value_pct)}. To równoległa wrażliwość, a nie wspólny rozkład prawdopodobieństwa ani rekomendacja.</p>
      </>}
      {scenario && scenario.exclusions.length > 0 && <details className="portfolio-exclusions"><summary>Pozycje wyłączone ({scenario.exclusions.length})</summary><ul>{scenario.exclusions.map((item) => { const position = workspace.positions.find((row) => row.id === item.position_id); return <li key={item.position_id}><strong>{position?.ticker || position?.name || `Pozycja ${item.position_id}`}</strong><span>{item.latest_status ? `ostatnia wycena: ${item.latest_status}` : "brak kwalifikującej się wyceny"}</span></li>; })}</ul></details>}
    </section>
  );
}

const REVIEW_STATUS: Record<PortfolioReviewStatus, { label: string; tone: string }> = {
  verified: { label: "zweryfikowana", tone: "success" },
  provisional: { label: "prowizoryczna", tone: "warning" },
  rejected: { label: "odrzucona", tone: "danger" },
  "needs-human": { label: "wymaga interwencji", tone: "warning" },
};

function PortfolioReviewSection({ workspace, queueing, notice, onQueue, analyticsAvailable }: {
  workspace: PortfolioWorkspace;
  queueing: boolean;
  notice: string | null;
  onQueue: () => void;
  analyticsAvailable: boolean;
}) {
  const reviewState = workspace.portfolio_review;
  const latest = reviewState.latest;
  const active = reviewState.active_run;
  const status = latest ? REVIEW_STATUS[latest.status] : null;
  const currentSnapshot = Boolean(latest && latest.portfolio_snapshot_id === workspace.snapshot?.id);
  const activeLabel = active?.status === "running" ? "Analiza jest wykonywana" : "Analiza oczekuje";

  return (
    <section className="portfolio-section portfolio-review" aria-labelledby="portfolio-review-title">
      <div className="portfolio-section-heading portfolio-review-heading">
        <div><p className="section-label">Codex</p><h2 id="portfolio-review-title">Perspektywa całego portfela</h2></div>
        <button className="btn" onClick={onQueue} disabled={!analyticsAvailable || queueing || Boolean(active)}>
          <IconSparkles size={14} /> {!analyticsAvailable ? "Brak danych do analizy" : queueing ? "Planuję…" : active ? activeLabel : "Przeanalizuj z Codex"}
        </button>
      </div>

      {notice && <div className="portfolio-review-notice" role="status">{notice}</div>}
      {!analyticsAvailable && <div className="portfolio-valid-empty"><strong>Nowa analiza Codex jest niedostępna</strong><span>Brakuje zachowanych pozycji, na których można oprzeć analizę. Poprzednie analizy pozostają poniżej jako historia.</span></div>}
      {active && (
        <div className="portfolio-review-queued" role="status">
          <IconSparkles size={16} />
          <div><strong>{activeLabel}</strong><span>Utworzono {exactTimestamp(active.created_at)} dla snapshotu portfela {active.snapshot_id ?? "—"}.</span><small>Uruchom jawnie <code>$workbench-run-queue</code>, aby opróżnić kolejkę z zachowaniem limitów bezpieczeństwa. Ta strona nie przejmuje ani nie wykonuje zadań.</small></div>
        </div>
      )}

      {!latest ? (
        analyticsAvailable ? <div className="portfolio-valid-empty"><strong>Brak analizy Codex</strong><span>Możesz jawnie zaplanować interpretację zapisanych obliczeń, ryzyk i luk. Nie zmieni ona wycen spółek ani portfela.</span></div> : null
      ) : (
        <article className={`portfolio-review-result ${latest.status}`}>
          <header>
            <div><span className={`badge ${status!.tone}`}>{status!.label}</span><strong>Analiza v{latest.version}</strong></div>
            <span>{currentSnapshot ? "Bieżący snapshot" : `Starszy snapshot ${latest.portfolio_snapshot_id}`} · {exactTimestamp(latest.as_of)}</span>
          </header>

          {!currentSnapshot && <div className="portfolio-review-stale">Od tej analizy zapisano nowszy snapshot portfela. Wniosek pozostaje historią, nie opisem bieżącego składu.</div>}
          {latest.status === "rejected" && <div className="portfolio-review-rejected">Niezależna weryfikacja odrzuciła tę wersję. Treść jest widoczna wyłącznie jako zapis audytowy.</div>}
          {latest.status === "needs-human" && <div className="portfolio-review-rejected">Integralność lub tożsamość danych wymaga ręcznego rozstrzygnięcia przed użyciem tej analizy.</div>}
          {latest.status === "rejected" || latest.status === "needs-human" ? (
            <details className="portfolio-review-details portfolio-review-audit-only">
              <summary>Treść szkicu i wynik weryfikacji</summary>
              <ReviewNarrative latest={latest} history={reviewState.history} auditOnly />
            </details>
          ) : <ReviewNarrative latest={latest} history={reviewState.history} />}
        </article>
      )}
    </section>
  );
}

function ReviewNarrative({ latest, history, auditOnly = false }: {
  latest: PortfolioReviewSnapshot;
  history: PortfolioWorkspace["portfolio_review"]["history"];
  auditOnly?: boolean;
}) {
  const detailSections = [
    ["Koncentracja", latest.sections.concentration],
    ["Płynność", latest.sections.liquidity],
    ["Historia i metoda", latest.sections.history],
    ["Ekspozycja scenariuszowa", latest.sections.scenario_exposure],
  ] as const;
  const details = <>
    <div className="portfolio-review-detail-grid">
      {detailSections.map(([label, items]) => <section key={label}><h3>{label}</h3><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></section>)}
    </div>
    {latest.gaps.length > 0 && <div className="portfolio-review-gaps"><strong>Luki ({latest.gaps.length})</strong><ul>{latest.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></div>}
    <div className="portfolio-review-verifier"><IconShieldCheck size={15} /><div>
      <strong>Weryfikacja: {latest.verifier_result.verdict}</strong>
      <span>{latest.verifier_result.summary}</span>
      <span>Szkic — żądano: {latest.draft_requested_model_role} · {latest.draft_requested_model} · {latest.draft_reasoning_effort}; host: {latest.draft_actual_host_model} · pochodzenie: {modelProvenanceLabel(latest.draft_requested_model, latest.draft_actual_host_model, latest.draft_substitution_or_escalation)}.</span>
      <span>Weryfikacja — żądano: {latest.verifier_result.requested_model_role} · {latest.verifier_result.requested_model} · {latest.verifier_result.reasoning_effort}; host: {latest.verifier_result.actual_host_model} · pochodzenie: {modelProvenanceLabel(latest.verifier_result.requested_model, latest.verifier_result.actual_host_model, latest.verifier_result.substitution_or_escalation)}.</span>
    </div></div>
    {history.length > 1 && <details className="portfolio-review-history"><summary>Historia analiz ({history.length})</summary><ol>{history.map((item) => <li key={item.id}><span>v{item.version} · {REVIEW_STATUS[item.status].label}</span><small>snapshot {item.portfolio_snapshot_id} · {exactTimestamp(item.as_of)}</small></li>)}</ol></details>}
  </>;
  return <>
    <p className="portfolio-review-summary">{latest.sections.summary}</p>
    <p className="portfolio-review-boundary">Interpretacja ryzyk i perspektyw — nie rekomendacja kupna, sprzedaży ani zmiany pozycji.</p>
    <div className="portfolio-review-primary">
      <div><h3>Najważniejsze ryzyka</h3><ul>{latest.sections.risks.map((item) => <li key={item}>{item}</li>)}</ul></div>
      <div><h3>Następne sprawdzenia</h3><ol>{latest.sections.next_checks.map((item) => <li key={item}>{item}</li>)}</ol></div>
    </div>
    {auditOnly ? details : <details className="portfolio-review-details"><summary>Pozostałe wnioski i weryfikacja</summary>{details}</details>}
  </>;
}

function LiquidityAudit({ workspace }: { workspace: PortfolioWorkspace }) {
  const available = workspace.liquidity.filter((item) => item.status === "provisional").length;
  const analyticsAvailable = workspace.coverage?.analytics_available === true;
  return (
    <details className="portfolio-audit">
      <summary>Dane, płynność i metoda</summary>
      <div>
        <p><strong>Źródło</strong><span>{providerLabel(workspace.provider)} · ostatni zapisany stan i udana synchronizacja {exactTimestamp(workspace.snapshot?.as_of)}</span></p>
        <p><strong>Mapowanie</strong><span>{analyticsAvailable ? `${fmtPct(workspace.coverage?.mapped_company_value_pct)} wartości dostawcy powiązane ze spółkami${workspace.coverage?.analytics_status === "partial" ? "; analityka udziałów używa zachowanych pozycji" : ""}` : "brak zachowanych pozycji do wyliczenia udziałów"} · {workspace.coverage?.unmapped_positions ?? 0} nierozpoznanych pozycji</span></p>
        <p><strong>Płynność</strong><span>{analyticsAvailable ? `${available} pozycji z prowizorycznym szacunkiem. Liczba dni zakłada 10% mediany wartości obrotu z 20 sesji; surowa seria nie jest prognozą wykonania.` : "Brak zachowanych pozycji do oszacowania."}</span></p>
        <p><strong>Scenariusze</strong><span>{analyticsAvailable ? `Wyłącznie zweryfikowane wyceny powiązane z najnowszym Research; dane spółek nie zmieniają się przez obecność w portfelu.${workspace.coverage?.analytics_status === "partial" ? " Wynik obejmuje wyłącznie zachowane pozycje." : ""}` : "Brak zachowanych pozycji do agregacji."}</span></p>
      </div>
    </details>
  );
}
