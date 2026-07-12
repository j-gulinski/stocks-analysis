/** Read-only source catalog; it deliberately makes no company conclusion. */
import type { ResearchMethodCatalog, ResearchMethodStageStatus } from "@/lib/types";

const STAGE_LABELS = {
  discover: "Discover",
  research: "Research",
  valuation: "Valuation",
} as const;

const STATUS: Record<ResearchMethodStageStatus, { label: string; tone: string }> = {
  supported: { label: "dostępna", tone: "success" },
  planned: { label: "planowana", tone: "warning" },
  draft: { label: "szkic", tone: "neutral" },
  retired: { label: "wycofana", tone: "danger" },
};

function TextList({ items, empty }: { items: string[]; empty: string }) {
  return items.length > 0
    ? <ul className="snapshot-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>
    : <p className="snapshot-empty">{empty}</p>;
}

export default function ResearchMethodCatalogView({ methods }: { methods: ResearchMethodCatalog[] }) {
  return (
    <section className="snapshot-section research-method-catalog" aria-labelledby="snapshot-methods">
      <header><span>06</span><h2 id="snapshot-methods">Katalog metod</h2></header>
      <p className="snapshot-lead">Katalog pokazuje źródła, gotowość i pytania metod. Nie jest jeszcze odrębną oceną tej spółki ani ukrytym konsensusem.</p>
      <div className="research-method-list">
        {methods.map((method) => {
          const research = method.stages.research;
          const researchStatus = STATUS[research.status];
          return (
            <article className="research-method-card" key={method.id}>
              <header>
                <div><h3>{method.label}</h3><span>{method.version} · dojrzałość: {method.evaluation_maturity}</span></div>
                <span className={`badge ${researchStatus.tone}`}>Research: {researchStatus.label}</span>
              </header>
              <p>{method.disclaimer}</p>
              <div className="research-method-stages">
                {(Object.keys(STAGE_LABELS) as Array<keyof typeof STAGE_LABELS>).map((stage) => {
                  const readiness = method.stages[stage];
                  const status = STATUS[readiness.status];
                  return <div key={stage}><span>{STAGE_LABELS[stage]}</span><strong className={status.tone}>{status.label}</strong>{readiness.reason && <small>{readiness.reason}</small>}</div>;
                })}
              </div>
              {method.required_questions.length > 0 && <div><h4>Pytania dla wspólnego snapshotu</h4><TextList items={method.required_questions} empty="Brak aktywnych pytań." /></div>}
              <details className="research-method-details">
                <summary>Źródła, ograniczenia i kontrakt</summary>
                <div className="research-method-detail-content">
                  <section>
                    <h4>Manifest źródeł</h4>
                    {method.source_manifest.length === 0 ? <p className="snapshot-empty">Brak zachowanego manifestu źródeł — pack nie może być aktywowany.</p> : method.source_manifest.map((source) => (
                      <article key={source.id}>
                        <strong>{source.label}</strong>
                        <span>{source.author_identity ?? "Autor nieustalony"}</span>
                        <span>{source.locator ?? "Brak dokładnego locatora"}</span>
                        <span>Repozytorium: {source.repo_path}</span>
                        <span>Retencja: {source.retention_status}</span>
                        {source.publication_at && <span>Publikacja: {source.publication_at}</span>}
                        {!source.publication_at && source.known_at && <span>Znana data: {source.known_at}</span>}
                        {source.date_note && <span>{source.date_note}</span>}
                        {source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">Otwórz źródło</a>}
                        <span>SHA-256: {source.sha256}</span>
                      </article>
                    ))}
                  </section>
                  <section><h4>Ślepe punkty</h4><TextList items={method.blind_spots} empty="Brak dodatkowych informacji." /></section>
                  <section><h4>Nazwane luki</h4><TextList items={method.gaps} empty="Brak nazwanych luk." /></section>
                  <section className="research-method-contract"><h4>Kontrakt</h4><p>Skill: {method.skill ?? "brak"} · schema Research: {method.research_output_schema_version ?? "jeszcze nieutworzony"} · schema Valuation: {method.valuation_output_schema_version ?? "brak"} · verifier: {method.required_verifier_role ?? "brak"}</p></section>
                </div>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}
