"use client";

import { getEvidenceDocuments } from "@/lib/api";
import { relativeDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";

const STATUS_LABELS: Record<string, string> = {
  parsed: "odczytane",
  failed: "wymaga uwagi",
  needs_ocr: "potrzebny OCR",
  partial: "odczyt częściowy",
  pending: "oczekuje na parser",
  missing: "brak wersji",
};

function parseErrorLabel(error: string | null): string {
  if (!error) return "Nieznany błąd parsera.";
  if (error.toLowerCase().includes("no extractable text")) {
    return "Skan bez warstwy tekstowej — potrzebny OCR.";
  }
  return error;
}

export default function EvidenceSourcesPanel({ ticker }: { ticker: string }) {
  const { data, error, loading } = useApi(
    () => getEvidenceDocuments(ticker),
    [ticker],
  );

  if (loading) return <p className="secondary">Ładuję rejestr źródeł…</p>;
  if (error) return <p className="neg">Nie udało się odczytać rejestru źródeł: {error}</p>;
  if (!data?.length) {
    return <p className="secondary">Brak zapisanych dokumentów. Najpierw odśwież dane spółki.</p>;
  }
  const groups = Object.values(
    data.reduce<Record<string, { quality: (typeof data)[number]["quality"]; documents: typeof data }>>(
      (result, document) => {
        const group = result[document.source_type] ?? {
          quality: document.quality,
          documents: [],
        };
        group.documents.push(document);
        result[document.source_type] = group;
        return result;
      },
      {},
    ),
  );

  return (
    <div className="evidence-source-grid">
      {groups.map(({ quality, documents }) => {
        const failedDocuments = documents.filter(
          (document) => document.latest_parse_status !== "parsed",
        );
        const newest = [...documents].sort((left, right) =>
          (right.latest_version_at ?? "").localeCompare(left.latest_version_at ?? ""),
        )[0];
        return (
          <article className="evidence-source-card" key={newest.source_type}>
            <div className="spread">
              <div>
                <span className="badge muted">priorytet {quality.priority ?? "?"}</span>
                <span className="badge warning">warunki: do weryfikacji</span>
                <h3>{quality.label}</h3>
              </div>
              <span className={failedDocuments.length ? "badge warning" : "badge success"}>
                {failedDocuments.length
                  ? `${failedDocuments.length} wymaga uwagi`
                  : STATUS_LABELS[newest.latest_parse_status] ?? newest.latest_parse_status}
              </span>
            </div>
            <p><strong>Możesz użyć do:</strong> {quality.allowed_use}</p>
            <p className="secondary"><strong>Nie wnioskuj:</strong> {quality.limitation}</p>
            {failedDocuments.map((document) => (
              <p className="neg" key={document.id}>Parser: {parseErrorLabel(document.latest_parse_error)}</p>
            ))}
            <div className="evidence-source-meta">
              <span>{newest.source_type}</span>
              <span>{documents.length} dokumentów</span>
              <span>{documents.reduce((sum, document) => sum + document.version_count, 0)} wersji</span>
              <span>ostatnio {relativeDate(newest.latest_version_at)}</span>
            </div>
            <details>
              <summary>Dokumenty, warunki i polityka pobierania</summary>
              <div className="evidence-document-links">
                {documents.map((document) => (
                  <a href={document.canonical_url} target="_blank" rel="noreferrer" key={document.id}>
                    {document.scope_key} · {STATUS_LABELS[document.latest_parse_status] ?? document.latest_parse_status} ↗
                  </a>
                ))}
              </div>
              <p>{quality.terms_note}</p>
              <p className="secondary">{quality.rate_policy}</p>
            </details>
          </article>
        );
      })}
    </div>
  );
}
