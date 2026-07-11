"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconArrowRight, IconCalculator, IconLock } from "@tabler/icons-react";
import { getResearchCases, getValuationWorkspace } from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { fmtDate } from "@/lib/format";
import type { ResearchCaseSummary, ValuationWorkspace } from "@/lib/types";

type Row = {
  research: ResearchCaseSummary;
  valuation: ValuationWorkspace | null;
  loadFailed: boolean;
};

function valuationStatus(workspace: ValuationWorkspace | null) {
  const valuation = workspace?.latest_valuation;
  if (valuation && valuation.research_snapshot_id !== workspace?.latest_research_snapshot_id) {
    return { label: `Historia · Research #${valuation.research_snapshot_id}`, tone: "muted", current: false };
  }
  const status = valuation?.status;
  if (status === "verified") return { label: "Wycena zweryfikowana", tone: "success", current: true };
  if (status === "provisional") return { label: "Wycena prowizoryczna", tone: "warning", current: true };
  if (status === "rejected") return { label: "Wycena odrzucona", tone: "danger", current: true };
  if (status === "needs-human") return { label: "Wymaga decyzji", tone: "warning", current: true };
  return { label: "Brak wyceny", tone: "muted", current: false };
}

export default function ValuationPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getResearchCases()
      .then(async (cases) => {
        const eligible = cases.filter((item) => ["provisional", "verified"].includes(item.latest_snapshot_status ?? ""));
        const loaded = await Promise.all(eligible.map(async (research) => {
          try {
            return {
              research,
              valuation: await getValuationWorkspace(research.id),
              loadFailed: false,
            };
          } catch {
            return { research, valuation: null, loadFailed: true };
          }
        }));
        if (!cancelled) setRows(loaded);
      })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="page-stack valuation-list-page">
      <section className="page-header valuation-list-header">
        <div><p className="eyebrow">Valuation</p><h1>Scenariusze spółek</h1><p>Porównaj, jak jawne założenia zmieniają wyniki i możliwy zakres ceny.</p></div>
      </section>
      {error && <div className="error-box" role="alert">{error}</div>}
      {loading ? <><SkeletonRows rows={3} height={78} /><LoadingMessages messages={["Otwieram spółki z gotowym Research…", "Sprawdzam ostatnie wyceny…"]} /></> : rows.length === 0 ? (
        <section className="valuation-empty"><IconCalculator size={24} /><h2>Brak spółek gotowych do wyceny</h2><p>Najpierw doprowadź Research do użytecznego snapshotu.</p><Link href="/" className="btn accent">Przejdź do Research <IconArrowRight size={14} /></Link></section>
      ) : (
        <section className="valuation-company-list" aria-label="Spółki gotowe do wyceny">
          {rows.map(({ research, valuation, loadFailed }) => {
            const status = valuationStatus(valuation);
            const supported = Boolean(valuation?.template);
            return <article className="valuation-company-row" key={research.id}>
              <div className="valuation-company-name"><span className="ticker-mark">{research.ticker}</span><div><strong>{research.name}</strong><small>Research {research.latest_snapshot_status === "verified" ? "zweryfikowany" : "prowizoryczny"} · {fmtDate(research.latest_snapshot_as_of)}</small></div></div>
              <div><span className={`badge ${status.tone}`}>{status.label}</span>{status.current && valuation?.latest_valuation && <small>wersja {valuation.latest_valuation.version} · {fmtDate(valuation.latest_valuation.as_of)}</small>}</div>
              <div className="valuation-company-template">{supported ? <><strong>{valuation!.template!.label}</strong><small>{valuation!.template!.version}</small></> : <><IconLock size={14} /><span>{loadFailed ? "Nie udało się odczytać wyceny" : "Brak obsługiwanego szablonu"}</span></>}</div>
              {supported ? <Link className="btn valuation-company-open" href={`/valuation/${research.ticker}`}>Otwórz wycenę <IconArrowRight size={14} /></Link> : <span />}
            </article>;
          })}
        </section>
      )}
    </main>
  );
}
