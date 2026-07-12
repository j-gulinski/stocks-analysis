"use client";

/** Separate immutable method lenses over one unchanged Research snapshot. */
import { useState } from "react";
import { IconAlertTriangle, IconCheck, IconSparkles } from "@tabler/icons-react";
import { ApiError, queueResearchMethodPerspective } from "@/lib/api";
import type {
  ResearchClaim,
  ResearchMethodCatalog,
  ResearchMethodPerspective,
  ResearchMethodPerspectiveFindingStatus,
  ResearchSnapshot,
  ResearchSnapshotHistory,
  ResearchSnapshotStatus,
} from "@/lib/types";

const ARTIFACT_STATUS: Record<ResearchSnapshotStatus, { label: string; tone: string }> = {
  provisional: { label: "Prowizoryczna", tone: "warning" },
  verified: { label: "Zweryfikowana", tone: "success" },
  rejected: { label: "Odrzucona", tone: "danger" },
  "needs-human": { label: "Wymaga decyzji", tone: "warning" },
};

const FINDING_STATUS: Record<ResearchMethodPerspectiveFindingStatus, string> = {
  supports: "Wspiera",
  contradicts: "Podważa",
  unknown: "Niewiadome",
  "not-applicable": "Nie dotyczy",
};

const FINDING_ORDER: ResearchMethodPerspectiveFindingStatus[] = [
  "supports",
  "contradicts",
  "unknown",
  "not-applicable",
];

function Claim({ claim }: { claim: ResearchClaim }) {
  return (
    <div className="method-perspective-claim">
      <p>{claim.text}</p>
      {(claim.source_document_version_ids.length > 0 || claim.basis) && (
        <small>
          {claim.source_document_version_ids.length > 0 && `Dokumenty v${claim.source_document_version_ids.join(", v")}`}
          {claim.source_document_version_ids.length > 0 && claim.basis && " · "}
          {claim.basis}
        </small>
      )}
    </div>
  );
}

function TextList({ items, empty }: { items: string[]; empty: string }) {
  return items.length > 0
    ? <ul className="snapshot-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>
    : <p className="snapshot-empty">{empty}</p>;
}

function PerspectiveCard({ perspective }: { perspective: ResearchMethodPerspective }) {
  const status = ARTIFACT_STATUS[perspective.status];
  const checks = perspective.method_manifest.required_checks;
  return (
    <article className="method-perspective-card">
      <header>
        <div>
          <h3>{perspective.method_manifest.label}</h3>
          <span>{perspective.method_pack_version} · snapshot Research #{perspective.research_snapshot_id}</span>
        </div>
        <span className={`badge ${status.tone}`}>{status.label}</span>
      </header>
      <p className="method-perspective-disclaimer">{perspective.method_manifest.disclaimer}</p>
      <div className="method-perspective-applicability">
        <span className="snapshot-label">Zastosowanie</span>
        <strong>{perspective.applicability.status === "applicable" ? "Metoda ma zastosowanie" : "Metoda nie ma zastosowania"}</strong>
        <Claim claim={perspective.applicability.reason} />
      </div>
      {perspective.conclusion && <div className="method-perspective-conclusion"><span className="snapshot-label">Wniosek tej perspektywy</span><Claim claim={perspective.conclusion} /></div>}
      <div className="method-perspective-findings">
        {FINDING_ORDER.map((findingStatus) => {
          const findings = perspective.findings.filter((item) => item.status === findingStatus);
          return (
            <section key={findingStatus}>
              <h4>{FINDING_STATUS[findingStatus]} ({findings.length})</h4>
              {findings.length === 0 ? <p className="snapshot-empty">Brak pozycji w tej klasyfikacji.</p> : findings.map((finding) => {
                const check = checks.find((item) => item.id === finding.required_check_id);
                return (
                  <article key={finding.required_check_id}>
                    <strong>{check?.label ?? finding.required_check_id}</strong>
                    <Claim claim={finding.claim} />
                  </article>
                );
              })}
            </section>
          );
        })}
      </div>
      <div className="method-perspective-details">
        <section><h4>Ślepe punkty</h4><TextList items={perspective.blind_spots} empty="Brak dodatkowych ślepych punktów." /></section>
        <section><h4>Falsyfikatory</h4>{perspective.falsifiers.length === 0 ? <p className="snapshot-empty">Brak zapisanych falsyfikatorów.</p> : perspective.falsifiers.map((item, index) => <Claim key={`${index}-${item.text}`} claim={item} />)}</section>
        <section><h4>Następne kontrole</h4><TextList items={perspective.next_checks.map((item) => `${item.question} — ${item.suggested_source}`)} empty="Brak kolejnych kontroli." /></section>
        <section><h4>Nazwane luki</h4>{perspective.gaps.length === 0 ? <p className="snapshot-empty">Brak dodatkowych luk w perspektywie.</p> : <ul className="snapshot-list">{perspective.gaps.map((item) => <li key={item.topic}><strong>{item.topic}:</strong> {item.description}</li>)}</ul>}</section>
      </div>
      <details className="method-perspective-audit">
        <summary>Audyt perspektywy</summary>
        <p>Manifest {perspective.method_manifest_fingerprint} · verifier: {perspective.verifier_result.verifier_model}</p>
        <p>{perspective.verifier_result.summary}</p>
        <h4>Zamrożone źródła metody</h4>
        <ul>{perspective.method_manifest.source_manifest.map((source) => <li key={source.id}>{source.label} · {source.locator} · {source.sha256}</li>)}</ul>
        {perspective.method_manifest.gaps.length > 0 && <><h4>Granice manifestu metody</h4><TextList items={perspective.method_manifest.gaps} empty="Brak nazwanych granic." /></>}
        <ul>{Object.entries(perspective.verifier_result.checks).map(([name, passed]) => <li key={name}>{name}: {passed ? "tak" : "nie"}</li>)}</ul>
      </details>
    </article>
  );
}

export default function ResearchMethodPerspectivesView({
  researchCaseId,
  snapshot,
  methods,
  perspectives,
  snapshotHistory,
}: {
  researchCaseId: number;
  snapshot: ResearchSnapshot;
  methods: ResearchMethodCatalog[];
  perspectives: ResearchMethodPerspective[];
  snapshotHistory: ResearchSnapshotHistory[];
}) {
  const [queueing, setQueueing] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = perspectives.filter((item) => item.research_snapshot_id === snapshot.id);
  const historic = perspectives.filter((item) => item.research_snapshot_id !== snapshot.id);
  const snapshotVersion = new Map(snapshotHistory.map((item) => [item.id, item.version]));
  const canQueueForSnapshot = ["provisional", "verified"].includes(snapshot.status);

  const queue = async (method: ResearchMethodCatalog) => {
    setQueueing(method.id);
    setMessage(null);
    setError(null);
    try {
      const result = await queueResearchMethodPerspective(researchCaseId, {
        research_snapshot_id: snapshot.id,
        method_pack_id: method.id,
      });
      setMessage(result.created
        ? `Perspektywa ${method.label} dla snapshotu v${snapshot.version} oczekuje na jawne wykonanie.`
        : result.status === "queued" || result.status === "running"
          ? "Ta perspektywa już oczekuje lub jest w toku."
          : "Dla tego zamrożonego snapshotu istnieje już ten sam zapis perspektywy.");
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err));
    } finally {
      setQueueing(null);
    }
  };

  return (
    <section className="snapshot-section research-method-perspectives" aria-labelledby="snapshot-method-perspectives">
      <header><span>06</span><h2 id="snapshot-method-perspectives">Perspektywy metod</h2></header>
      <p className="snapshot-lead">Każda perspektywa jest osobnym, niezmiennym odczytem tego samego snapshotu Research. Workbench nie scala ich w ukryty konsensus ani rekomendację.</p>
      <div className="method-perspective-list">
        {methods.map((method) => {
          const saved = current.find((item) => item.method_pack_id === method.id && item.method_pack_version === method.version);
          const supported = method.stages.research.status === "supported";
          if (saved) return <PerspectiveCard key={saved.id} perspective={saved} />;
          return (
            <article className="method-perspective-empty" key={method.id}>
              <div>
                <h3>{method.label}</h3>
                <p>{supported ? `Nie ma jeszcze zapisanego odczytu dla snapshotu v${snapshot.version}.` : method.stages.research.reason ?? "Pakiet nie jest dostępny dla Research."}</p>
              </div>
              {supported && canQueueForSnapshot ? (
                <button className="btn compact" type="button" onClick={() => void queue(method)} disabled={queueing !== null}>
                  <IconSparkles size={14} /> {queueing === method.id ? "Zlecam…" : `Utwórz perspektywę v${snapshot.version}`}
                </button>
              ) : <span className="badge neutral">{supported ? "Snapshot wymaga poprawy" : `Research: ${method.stages.research.status}`}</span>}
            </article>
          );
        })}
      </div>
      {historic.length > 0 && (
        <details className="method-perspective-history">
          <summary>Perspektywy wcześniejszych snapshotów ({historic.length})</summary>
          {historic.map((item) => <PerspectiveCard key={item.id} perspective={item} />)}
          <p className="snapshot-empty">Numery snapshotów: {historic.map((item) => `#${item.research_snapshot_id} (v${snapshotVersion.get(item.research_snapshot_id) ?? "?"})`).join(" · ")}</p>
        </details>
      )}
      {message && <div className="success-box" role="status"><IconCheck size={15} /> {message}</div>}
      {error && <div className="error-box" role="alert"><IconAlertTriangle size={15} /> {error}</div>}
    </section>
  );
}
