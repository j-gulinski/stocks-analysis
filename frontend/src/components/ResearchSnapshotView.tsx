"use client";

/** Fixed renderer for versioned canonical research-snapshot artifacts. */
import Link from "next/link";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconChevronRight,
  IconDatabase,
  IconHistory,
} from "@tabler/icons-react";
import { fmtDate, fmtPct, fmtPln } from "@/lib/format";
import type {
  CompanyProfile,
  ResearchCaseSummary,
  ResearchClaim,
  ResearchClaimKind,
  ResearchArchetypePack,
  ResearchOutlookDirection,
  ResearchSnapshot,
  ResearchSnapshotHistory,
  ResearchSnapshotStatus,
  ResearchSourceChannel,
} from "@/lib/types";

const ARCHETYPE_LABELS: Record<CompanyProfile["archetype"], string> = {
  "industrial-consumer": "Przemysł / konsument",
  "bank-financial": "Bank / finanse",
  "developer-real-estate": "Deweloper / nieruchomości",
  "software-services": "Software / usługi",
  "gaming-event": "Gaming / wydarzenie",
  "energy-resources": "Energia / surowce",
  "holding-biotech": "Holding / biotech",
};

const STATUS: Record<ResearchSnapshotStatus, { label: string; tone: string }> = {
  provisional: { label: "Prowizoryczny", tone: "warning" },
  verified: { label: "Zweryfikowany", tone: "success" },
  rejected: { label: "Odrzucony", tone: "danger" },
  "needs-human": { label: "Wymaga decyzji", tone: "warning" },
};

const CLAIM_KIND: Record<ResearchClaimKind, string> = {
  fact: "fakt",
  calculation: "obliczenie",
  assumption: "założenie",
  lead: "trop",
  unknown: "niewiadoma",
};

const VERIFIER_JUSTIFICATIONS = [
  ["evidence_and_claim_fit", "Dopasowanie dowodów do twierdzeń"],
  ["company_specificity", "Specyfika spółki"],
  ["outlook_and_thesis_plausibility", "Wiarygodność perspektywy i tezy"],
] as const;

const SCENARIO_LABELS: Record<string, string> = {
  negative: "spadkowy",
  base: "bazowy",
  positive: "wzrostowy",
  event: "zdarzeniowy",
};

const OUTLOOK_DIRECTION: Record<ResearchOutlookDirection, string> = {
  positive: "sprzyjający",
  neutral: "neutralny",
  negative: "niekorzystny",
  mixed: "mieszany",
  unknown: "nieustalony",
};

const RESOLUTION_STATUS = {
  confirmed: { label: "Potwierdzona", tone: "success" },
  partial: { label: "Częściowa", tone: "warning" },
  not_found: { label: "Nie znaleziono", tone: "warning" },
  not_applicable: { label: "Nie dotyczy", tone: "neutral" },
} as const;

const RESOLUTION_SCOPE = {
  profile: "Pytanie profilu",
  catalyst: "Katalizator",
  visibility: "Widoczność wyniku",
  governance: "Zarządzanie i ład",
} as const;

const SOURCE_CHANNEL: Record<ResearchSourceChannel, string> = {
  "issuer-primary": "Emitent",
  "regulatory-primary": "ESPI / EBI / GPW",
  biznesradar: "BiznesRadar",
  portalanaliz: "PortalAnaliz",
  "other-web": "Pozostały web",
};

function EmptyLine({ children }: { children: string }) {
  return <p className="snapshot-empty">{children}</p>;
}

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <EmptyLine>{empty}</EmptyLine>;
  return <ul className="snapshot-list">{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>;
}

function ClaimList({ claims }: { claims: ResearchClaim[] }) {
  if (claims.length === 0) return <EmptyLine>Brak dodatkowych twierdzeń w tej sekcji.</EmptyLine>;
  return (
    <div className="snapshot-claims">
      {claims.map((claim, index) => (
        <article className="snapshot-claim" key={`${claim.kind}-${index}-${claim.text}`}>
          <span className={`claim-kind ${claim.kind}`}>{CLAIM_KIND[claim.kind]}</span>
          <p>{claim.text}</p>
          {(claim.source_document_version_ids.length > 0 || claim.basis) && (
            <details>
              <summary>Podstawa</summary>
              {claim.source_document_version_ids.length > 0 && (
                <span>Wersje dokumentów: {claim.source_document_version_ids.join(", ")}</span>
              )}
              {claim.basis && <span>{claim.basis}</span>}
            </details>
          )}
        </article>
      ))}
    </div>
  );
}

function ClaimBasis({ claim }: { claim: ResearchClaim }) {
  if (claim.source_document_version_ids.length === 0 && !claim.basis) return null;
  return (
    <small className="snapshot-claim-basis">
      <span className={`claim-kind ${claim.kind}`}>{CLAIM_KIND[claim.kind]}</span>{" "}
      {claim.source_document_version_ids.length > 0 && `Dokumenty v${claim.source_document_version_ids.join(", v")}`}
      {claim.source_document_version_ids.length > 0 && claim.basis && " · "}
      {claim.basis}
    </small>
  );
}

function ValuationDecision({
  ticker,
  valuationStrip,
}: {
  ticker: string;
  valuationStrip: ResearchCaseSummary["valuation_strip"];
}) {
  if (!valuationStrip) {
    return (
      <section className="snapshot-decision snapshot-valuation-empty" aria-labelledby="snapshot-decision">
        <div>
          <span className="snapshot-label">Decyzja / Valuation</span>
          <h2 id="snapshot-decision">Brak bieżącej wyceny</h2>
          <p>Research jest gotowy do przełożenia na scenariusze właściwe dla spółki.</p>
        </div>
        <Link className="btn accent" href={`/valuation/${ticker}`}>Przejdź do Valuation <IconArrowRight size={14} /></Link>
      </section>
    );
  }

  const hasWeightedValue = valuationStrip.weighted_value_pln != null;

  return (
    <section className="snapshot-decision" aria-labelledby="snapshot-decision">
      <header><span className="snapshot-label">Decyzja / Valuation</span><h2 id="snapshot-decision">{hasWeightedValue ? "Scenariusze i wartość ważona" : "Scenariusze bez arbitralnych wag"}</h2></header>
      <div className="snapshot-valuation-summary">
        <div className="research-valuation-prices">
          {Object.entries(valuationStrip.scenario_prices_pln).map(([kind, price]) => (
            <span key={kind}>
              {SCENARIO_LABELS[kind] ?? kind}
              <strong>{fmtPln(price)}</strong>
              {valuationStrip.scenario_probabilities_pct[kind] != null && <small>{fmtPct(valuationStrip.scenario_probabilities_pct[kind])}</small>}
            </span>
          ))}
        </div>
        <dl>
          <div><dt>Wynik ważony</dt><dd>{hasWeightedValue ? fmtPln(valuationStrip.weighted_value_pln) : "Celowo niepublikowany"}</dd></div>
          <div><dt>Kurs odniesienia</dt><dd>{fmtPln(valuationStrip.current_price_pln)}</dd></div>
          <div><dt>Potencjał ważony</dt><dd className={valuationStrip.upside_pct != null && valuationStrip.upside_pct >= 0 ? "pos" : valuationStrip.upside_pct != null ? "neg" : ""}>{valuationStrip.upside_pct == null ? "Nie dotyczy" : fmtPct(valuationStrip.upside_pct, { signed: true })}</dd></div>
        </dl>
        <div className="snapshot-valuation-action">
          <span className={`badge ${valuationStrip.verification_status === "verified" ? "success" : valuationStrip.verification_status === "rejected" ? "danger" : "warning"}`}>Wycena {valuationStrip.verification_status}</span>
          {valuationStrip.catalyst && <small>Katalizator: {valuationStrip.catalyst}</small>}
          <small>Stan na {fmtDate(valuationStrip.as_of)}</small>
          <Link className="btn" href={`/valuation/${ticker}`}>Otwórz pełną wycenę <IconArrowRight size={14} /></Link>
        </div>
      </div>
    </section>
  );
}

export default function ResearchSnapshotView({
  ticker,
  companyName,
  profile,
  snapshot,
  history,
  archetypePack,
  valuationStrip,
}: {
  ticker: string;
  companyName: string | null;
  profile: CompanyProfile;
  snapshot: ResearchSnapshot;
  history: ResearchSnapshotHistory[];
  archetypePack: ResearchArchetypePack | null;
  valuationStrip: ResearchCaseSummary["valuation_strip"];
}) {
  const sections = snapshot.sections;
  const outlook = sections.outlook;
  const drivers = profile.drivers.filter((item) =>
    sections.business_and_drivers.driver_keys.includes(item.key),
  );
  const kpis = profile.kpis.filter((item) =>
    sections.performance.kpi_keys.includes(item.key),
  );
  const riskItems = Array.from(new Set([
    ...sections.thesis.risks,
    ...profile.company_overlay.unusual_risks,
  ]));
  const unresolvedQuestions = outlook
    ? outlook.question_resolutions
      .filter((item) => item.status === "partial" || item.status === "not_found")
      .map((item) => `${item.question} — ${item.remaining_gap}`)
    : profile.company_overlay.source_questions;
  const sourcedCheckQuestions = new Set(
    snapshot.next_checks.map((item) => item.question.trim()),
  );
  const checkItems = Array.from(new Set([
    ...sections.thesis.next_checks.filter(
      (question) => !sourcedCheckQuestions.has(question.trim()),
    ),
    ...unresolvedQuestions,
    ...snapshot.next_checks.map((item) => `${item.question} — ${item.suggested_source}`),
  ]));
  const status = STATUS[snapshot.status];
  const sectionNumbers = outlook
    ? { thesis: "06", history: "07" }
    : { thesis: "05", history: "06" };

  return (
    <article className="research-snapshot">
      <header className="snapshot-heading">
        <div>
          <p className="eyebrow">Research snapshot · wersja {snapshot.version}</p>
          <div className="snapshot-title-row"><h1>{ticker}</h1>{companyName && <span>{companyName}</span>}</div>
          <p>{sections.brief.current_understanding}</p>
        </div>
        <div className="snapshot-heading-status">
          <span className={`badge ${status.tone}`}>{status.label}</span>
          <span>Stan wiedzy na {fmtDate(snapshot.as_of)}</span>
        </div>
      </header>

      <ValuationDecision ticker={ticker} valuationStrip={valuationStrip} />

      <section className="snapshot-section snapshot-brief" aria-labelledby="snapshot-brief">
        <header><span>01</span><h2 id="snapshot-brief">Brief</h2></header>
        <div className="snapshot-brief-grid">
          <div><span className="snapshot-label">Aktualność</span><p>{sections.brief.freshness}</p></div>
          <div><span className="snapshot-label">Najważniejsza luka</span><p>{sections.brief.main_gap}</p></div>
          <div className="snapshot-next-action"><IconArrowRight size={17} /><div><span className="snapshot-label">Następny użyteczny krok</span><p>{sections.brief.next_action}</p></div></div>
        </div>
      </section>

      <details className="snapshot-detail">
        <summary>Profil badawczy spółki</summary>
        <aside className="snapshot-profile" aria-label="Profil badawczy spółki">
          <div>
            <span className="snapshot-label">Profil</span>
            <strong>{archetypePack?.label ?? ARCHETYPE_LABELS[profile.archetype]}</strong>
            <small>
              pakiet {archetypePack?.version ?? profile.archetype_version} · profil v{profile.version}
              {archetypePack && ` · Zakres pakietu ${archetypePack.coverage_count}/${archetypePack.required_markers.length}`}
            </small>
          </div>
          <div>
            <span className="snapshot-label">Segmenty</span>
            <strong>{profile.company_overlay.segments.join(" · ") || "Do ustalenia"}</strong>
          </div>
          <div>
            <span className="snapshot-label">Konkurenci</span>
            <strong>{profile.company_overlay.competitors.join(" · ") || "Do ustalenia"}</strong>
          </div>
        </aside>
      </details>

      <details className="snapshot-detail">
        <summary>Biznes i czynniki wyniku</summary>
      <section className="snapshot-section" aria-labelledby="snapshot-business">
        <header><span>02</span><h2 id="snapshot-business">Biznes i czynniki wyniku</h2></header>
        <div className="snapshot-two-column">
          <div><h3>Jak spółka zarabia</h3><p>{sections.business_and_drivers.business_model}</p></div>
          <div><h3>Model przychodów</h3><p>{sections.business_and_drivers.revenue_model}</p></div>
        </div>
        <div className="snapshot-definition-grid">
          {drivers.map((driver) => (
            <article key={driver.key}>
              <span className="snapshot-label">{driver.unit ?? "czynnik"}</span>
              <h3>{driver.label}</h3>
              <p>{driver.mechanism}</p>
            </article>
          ))}
        </div>
        <ClaimList claims={sections.business_and_drivers.claims} />
      </section>
      </details>

      <details className="snapshot-detail">
        <summary>Wyniki</summary>
      <section className="snapshot-section" aria-labelledby="snapshot-performance">
        <header><span>03</span><h2 id="snapshot-performance">Wyniki</h2></header>
        <p className="snapshot-lead">{sections.performance.summary}</p>
        <div className="snapshot-two-column">
          <div><h3>Most wyniku</h3><TextList items={sections.performance.result_bridge} empty="Brak wiarygodnego mostu wyniku w zebranych danych." /></div>
          <div>
            <h3>Wskaźniki właściwe dla spółki</h3>
            {kpis.length === 0 ? <EmptyLine>Brak zdefiniowanych KPI.</EmptyLine> : (
              <dl className="snapshot-kpis">{kpis.map((kpi) => <div key={kpi.key}><dt>{kpi.label}{kpi.unit ? ` (${kpi.unit})` : ""}</dt><dd>{kpi.rationale}</dd></div>)}</dl>
            )}
          </div>
        </div>
        <ClaimList claims={sections.performance.claims} />
      </section>
      </details>

      <details className="snapshot-detail snapshot-evidence-workspace">
        <summary>Dowody i źródła</summary>
      <section className="snapshot-section" aria-labelledby="snapshot-evidence">
        <header><span>04</span><h2 id="snapshot-evidence">Dowody</h2></header>
        <p className="snapshot-lead">{sections.evidence.summary}</p>
        <div className="snapshot-evidence-meta">
          <span className="badge neutral">{snapshot.source_manifest.length} źródeł</span>
          <span className="badge neutral">{sections.evidence.primary_document_version_ids.length} dokumentów pierwotnych</span>
          {snapshot.conflicts.length > 0 && <span className="badge warning">{snapshot.conflicts.length} sprzeczności</span>}
          {snapshot.gaps.length > 0 && <span className="badge warning">{snapshot.gaps.length} luk</span>}
        </div>
        <ClaimList claims={sections.evidence.claims} />
        {(snapshot.conflicts.length > 0 || snapshot.gaps.length > 0) && (
          <div className="snapshot-two-column snapshot-integrity-grid">
            <div>
              <h3>Sprzeczności</h3>
              {snapshot.conflicts.length === 0 ? <EmptyLine>Nie wykryto sprzeczności.</EmptyLine> : snapshot.conflicts.map((item) => <article key={item.topic}><IconAlertTriangle size={15} /><div><strong>{item.topic}</strong><p>{item.description}</p></div></article>)}
            </div>
            <div>
              <h3>Luki</h3>
              {snapshot.gaps.length === 0 ? <EmptyLine>Brak nazwanych luk.</EmptyLine> : snapshot.gaps.map((item) => <article key={item.topic}><IconChevronRight size={15} /><div><strong>{item.topic}</strong><p>{item.description}</p><small>Wpływ: {item.impact}</small></div></article>)}
            </div>
          </div>
        )}
        <section className="snapshot-source-workspace">
          <h3>Źródła użyte w snapshotcie</h3>
          {snapshot.source_manifest.length === 0 ? <EmptyLine>Snapshot nie zawiera manifestu źródeł.</EmptyLine> : snapshot.source_manifest.map((source) => (
            <div className="snapshot-source-row" key={`${source.document_version_id}-${source.role}`}>
              <span className="badge neutral">{source.role}</span>
              <strong>Dokument v{source.document_version_id}</strong>
              <p>{source.purpose}</p>
            </div>
          ))}
        </section>
      </section>
      </details>

      {outlook && (
        <details className="snapshot-detail">
          <summary>Perspektywa</summary>
        <section className="snapshot-section snapshot-outlook" aria-labelledby="snapshot-outlook">
          <header><span>05</span><h2 id="snapshot-outlook">Perspektywa</h2></header>
          <p className="snapshot-lead">{outlook.summary}</p>
          <div className="snapshot-outlook-drivers">
            {outlook.driver_outlooks.map((item) => {
              const driver = profile.drivers.find((candidate) => candidate.key === item.driver_key);
              return (
                <article key={item.driver_key}>
                  <header>
                    <div><span className="snapshot-label">Czynnik spółki</span><h3>{driver?.label ?? item.driver_key}</h3></div>
                  </header>
                  {([
                    ["Następny kwartał", item.next_quarter],
                    ["Następne 12 miesięcy", item.next_12_months],
                  ] as const).map(([horizon, assessment]) => (
                    <div className="snapshot-outlook-horizon" key={horizon}>
                      <div>
                        <span>{horizon}</span>
                        <span className={`outlook-direction ${assessment.direction}`}>
                          {OUTLOOK_DIRECTION[assessment.direction]}
                        </span>
                      </div>
                      <p>{assessment.assessment.text}</p>
                      <ClaimBasis claim={assessment.assessment} />
                      <small>Sprawdzono: {assessment.source_channels.map((channel) => SOURCE_CHANNEL[channel]).join(" · ")}</small>
                      <small>Obserwuj: {assessment.watch_items.join(" · ")}</small>
                    </div>
                  ))}
                </article>
              );
            })}
          </div>
          <div className="snapshot-resolutions">
            <h3>Odpowiedzi z pełnego przepływu</h3>
            {outlook.question_resolutions.map((item, index) => {
              const resolution = RESOLUTION_STATUS[item.status];
              return (
                <article key={`${item.scope}-${index}-${item.question}`}>
                  <header>
                    <span className="snapshot-label">{RESOLUTION_SCOPE[item.scope]}</span>
                    <span className={`badge ${resolution.tone}`}>{resolution.label}</span>
                  </header>
                  <h3>{item.question}</h3>
                  <p>{item.answer.text}</p>
                  <ClaimBasis claim={item.answer} />
                  <small>Sprawdzono: {item.source_channels.map((channel) => SOURCE_CHANNEL[channel]).join(" · ")}</small>
                  {item.remaining_gap && <small className="snapshot-resolution-gap">Pozostała luka: {item.remaining_gap}</small>}
                </article>
              );
            })}
          </div>
          <details className="snapshot-source-searches">
            <summary>Zakres wyszukiwania źródeł</summary>
            {outlook.source_searches.map((item) => (
              <div key={item.channel}>
                <strong>{SOURCE_CHANNEL[item.channel]}</strong>
                <span className={`badge ${item.status === "found" ? "success" : "warning"}`}>
                  {item.status === "found" ? "znaleziono" : item.status === "not_found" ? "brak wyniku" : "niedostępne"}
                </span>
                <p>{item.summary}</p>
                {item.document_version_ids.length > 0 && <small>Dokumenty v{item.document_version_ids.join(", v")}</small>}
              </div>
            ))}
          </details>
          <ClaimList claims={outlook.claims} />
        </section>
        </details>
      )}

      <details className="snapshot-detail">
        <summary>Teza</summary>
      <section className="snapshot-section" aria-labelledby="snapshot-thesis">
        <header><span>{sectionNumbers.thesis}</span><h2 id="snapshot-thesis">Teza</h2></header>
        <div className="snapshot-thesis-core">
          <div><span className="snapshot-label">Dlaczego teraz</span><p>{sections.thesis.why_now}</p></div>
          <div><span className="snapshot-label">Kontrteza</span><p>{sections.thesis.counter_thesis}</p></div>
        </div>
        <div className="snapshot-three-column">
          <div><h3>Katalizatory</h3><TextList items={sections.thesis.catalysts} empty="Brak potwierdzonych katalizatorów." /></div>
          <div><h3>Ryzyka</h3><TextList items={riskItems} empty="Brak nazwanych ryzyk." /></div>
          <div><h3>Falsyfikatory</h3><TextList items={sections.thesis.falsifiers} empty="Falsyfikatory wymagają uzupełnienia." /></div>
        </div>
        <div className="snapshot-governance"><h3>Ład i zarządzanie</h3><p>{sections.thesis.governance}</p></div>
        <ClaimList claims={sections.thesis.claims} />
        <div className="snapshot-next-checks">
          <h3>Następne kontrole</h3>
          <TextList items={checkItems} empty="Brak kolejnych kontroli." />
        </div>
      </section>
      </details>

      <details className="snapshot-detail">
        <summary>Historia</summary>
      <section className="snapshot-section" aria-labelledby="snapshot-history">
        <header><span>{sectionNumbers.history}</span><h2 id="snapshot-history">Historia</h2></header>
        <TextList items={sections.history.changes_since_previous} empty="To pierwszy zapisany snapshot — nie ma jeszcze zmian do porównania." />
        <ClaimList claims={sections.history.claims} />
        <div className="snapshot-timeline">
          {history.map((item) => {
            const itemStatus = STATUS[item.status];
            return <div key={item.id}><IconHistory size={14} /><strong>v{item.version}</strong><span>{fmtDate(item.as_of)}</span><span className={`badge ${itemStatus.tone}`}>{itemStatus.label}</span></div>;
          })}
        </div>
      </section>
      </details>

      <details className="snapshot-audit">
        <summary><IconDatabase size={15} /> Audyt źródeł i weryfikacji</summary>
        <div className="snapshot-audit-content">
          {archetypePack && (
            <section>
              <h3>Zakres pakietu {archetypePack.label}</h3>
              <div className="snapshot-pack-summary">
                <strong>{archetypePack.coverage_count}/{archetypePack.required_markers.length}</strong>
                <span>zakresu adresowane · {archetypePack.coverage_pct.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}%</span>
              </div>
              <div className="snapshot-pack-groups">
                <div>
                  <span>Oparte na źródłach ({archetypePack.sourced_count})</span>
                  <p>{archetypePack.required_markers.filter((marker) => marker.state === "sourced").map((marker) => marker.label).join(" · ") || "Brak"}</p>
                </div>
                <div>
                  <span>Jawne założenia ({archetypePack.assumption_count})</span>
                  <p>{archetypePack.required_markers.filter((marker) => marker.state === "assumption").map((marker) => marker.label).join(" · ") || "Brak"}</p>
                </div>
                <div>
                  <span>Nazwane luki ({archetypePack.gap_count})</span>
                  <p>{archetypePack.required_markers.filter((marker) => marker.state === "gap").map((marker) => marker.label).join(" · ") || "Brak"}</p>
                </div>
              </div>
              {archetypePack.missing_markers.length > 0 && (
                <details className="snapshot-pack-missing">
                  <summary>Brakujące markery ({archetypePack.missing_markers.length})</summary>
                  <ul>
                    {archetypePack.required_markers.filter((marker) => marker.state === "missing").map((marker) => <li key={marker.id}>{marker.label}</li>)}
                  </ul>
                </details>
              )}
              <details className="snapshot-pack-missing">
                <summary>Podstawa czynników i KPI</summary>
                <ul>
                  {[...profile.drivers, ...profile.kpis].filter((item) => item.focus_tags.length > 0).map((item) => (
                    <li key={`${item.key}-${item.focus_tags[0]}`}>
                      <strong>{item.label}:</strong>{" "}
                      {item.source_document_version_ids.length > 0
                        ? `dokumenty ${item.source_document_version_ids.join(", ")}`
                        : `założenie — ${item.basis}`}
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          )}
          <section>
            <h3>Manifest źródeł</h3>
            {snapshot.source_manifest.length === 0 ? <EmptyLine>Snapshot nie zawiera manifestu źródeł.</EmptyLine> : snapshot.source_manifest.map((source) => (
              <div className="snapshot-source-row" key={`${source.document_version_id}-${source.role}`}>
                <span className="badge neutral">{source.role}</span>
                <strong>Dokument v{source.document_version_id}</strong>
                <p>{source.purpose}</p>
              </div>
            ))}
          </section>
          <section>
            <h3>Pochodzenie wyświetlanych twierdzeń</h3>
            {snapshot.statement_provenance.map((item) => (
              <details className="snapshot-provenance-row" key={item.path}>
                <summary>{item.claim.text}</summary>
                <span>{item.path}</span>
                {item.claim.source_document_version_ids.length > 0 && (
                  <span>Wersje dokumentów: {item.claim.source_document_version_ids.join(", ")}</span>
                )}
                {item.claim.basis && <span>Podstawa: {item.claim.basis}</span>}
              </details>
            ))}
          </section>
          <section>
            <h3>Wynik verifiera</h3>
            <p>{snapshot.verifier_result.summary}</p>
            {snapshot.verifier_result.justifications && (
              <dl className="snapshot-verifier-justifications">
                {VERIFIER_JUSTIFICATIONS.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{snapshot.verifier_result.justifications?.[key]}</dd></div>)}
              </dl>
            )}
            {snapshot.verifier_result.findings.length > 0 && (
              <div className="snapshot-verifier-findings">
                {snapshot.verifier_result.findings.map((finding, index) => <article key={`${finding.area}-${index}`}><span className={`badge ${finding.severity === "minor" ? "warning" : "danger"}`}>{finding.severity}</span><div><strong>{finding.area}</strong><p>{finding.detail}</p></div></article>)}
              </div>
            )}
          </section>
          <section className="snapshot-run-meta">
            <h3>Metadane artefaktu</h3>
            <dl>
              <div><dt>Kontrakt</dt><dd>{snapshot.contract_version}</dd></div>
              <div><dt>Agent run</dt><dd>{snapshot.agent_run_id}</dd></div>
              <div><dt>Verification run</dt><dd>{snapshot.verification_run_id}</dd></div>
              <div><dt>Profil</dt><dd>{snapshot.company_profile_id}</dd></div>
              <div><dt>Verifier</dt><dd>{snapshot.verifier_result.verifier_model}</dd></div>
              <div><dt>Pokrycie twierdzeń</dt><dd>{snapshot.statement_provenance.length}</dd></div>
              <div><dt>Input fingerprint</dt><dd>{snapshot.input_fingerprint}</dd></div>
              <div><dt>Artifact fingerprint</dt><dd>{snapshot.artifact_fingerprint}</dd></div>
            </dl>
          </section>
        </div>
      </details>
    </article>
  );
}
