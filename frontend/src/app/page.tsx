"use client";

/** Phase-aware Research list. Every row leads with stored company substance. */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { IconArrowRight, IconDatabaseOff, IconPlus } from "@tabler/icons-react";
import { addResearchCase, getResearchCases } from "@/lib/api";
import { LoadingMessages, SkeletonRows } from "@/components/Loading";
import { fmtPct, fmtPln, relativeDate } from "@/lib/format";
import type { ResearchCaseSummary } from "@/lib/types";

const SCENARIO_LABELS: Record<string, string> = {
  negative: "spadkowy",
  base: "bazowy",
  positive: "wzrostowy",
  event: "zdarzeniowy",
};

function valuationTone(status: string) {
  if (status === "verified") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}

export default function ResearchPage() {
  const [cases, setCases] = useState<ResearchCaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCases(await getResearchCases());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadCases(); }, [loadCases]);

  const addTicker = async (event: React.FormEvent) => {
    event.preventDefault();
    const ticker = newTicker.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await addResearchCase({ ticker });
      setNewTicker("");
      setSuccess(
        result.created_case
          ? `${ticker} dodano do Research. Zbieranie danych zostało zaplanowane.`
          : result.reactivated_case
            ? `${ticker} ponownie aktywowano w Research.`
            : `${ticker} jest już w Research.`,
      );
      await loadCases();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const activeCases = cases.filter((item) => item.state !== "closed");
  const agenda = activeCases.filter((item) =>
    item.collection_progress?.state === "attention"
    || item.latest_snapshot_status === "needs-human"
    || item.latest_snapshot_status === "rejected"
    || item.valuation_strip?.verification_status === "rejected"
    || item.valuation_strip?.verification_status === "needs-human",
  );

  return (
    <main className="page-stack research-page">
      <section className="page-header research-header">
        <div>
          <p className="eyebrow">Research</p>
          <h1>Spółki w analizie</h1>
          <p>Zbieraj dowody, rozumiej biznes i przechodź do wyceny na jednym, wersjonowanym przebiegu.</p>
        </div>
        <form className="command-row" onSubmit={addTicker}>
          <input value={newTicker} onChange={(event) => setNewTicker(event.target.value)} placeholder="Ticker, np. SNT" aria-label="Ticker spółki" className="ticker-input" maxLength={12} />
          <button className="btn accent" type="submit" disabled={adding}><IconPlus size={14} /> {adding ? "Dodaję…" : "Dodaj do Research"}</button>
        </form>
      </section>

      {success && <div className="success-box" role="status">{success}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}

      {loading ? (
        <><SkeletonRows rows={4} height={100} /><LoadingMessages messages={["Otwieram przypadki badawcze…", "Układam bieżące etapy i luki…"]} /></>
      ) : cases.length === 0 ? (
        <section className="empty-research">
          <IconDatabaseOff size={24} />
          <h2>Brak spółek w Research</h2>
          <p>Dodaj znany ticker lub wybierz spółkę z sita Workbench w Discover.</p>
          <Link className="btn accent" href="/discover">Przejdź do Discover <IconArrowRight size={14} /></Link>
        </section>
      ) : (
        <>
          <section className="research-agenda" aria-labelledby="research-agenda-title">
            <div><p className="section-label">Agenda</p><h2 id="research-agenda-title">Do sprawdzenia</h2></div>
            {agenda.length === 0 ? <p>Brak zapisanych stanów wymagających interwencji.</p> : (
              <ul>{agenda.map((item) => <li key={item.id}><Link href={`/stock/${item.ticker}`}><strong>{item.ticker}</strong><span>{item.main_gap ?? item.phase_summary}</span></Link></li>)}</ul>
            )}
          </section>

          <section className="research-summary" aria-label="Podsumowanie Research">
            <span><strong>{activeCases.length}</strong> aktywnych spółek</span>
            <span><strong>{activeCases.filter((item) => item.phase === "collecting").length}</strong> w zbieraniu</span>
            <span><strong>{activeCases.filter((item) => item.phase === "valued").length}</strong> wycenionych</span>
          </section>

          <section className="research-case-list" aria-label="Spółki w Research">
            {cases.map((item) => (
              <article className="research-case-row" key={item.id}>
                <div className="research-case-company">
                  <span className="ticker-mark">{item.ticker}</span>
                  <div><strong>{item.name ?? "Nazwa do uzupełnienia"}</strong><small>Aktualizacja {relativeDate(item.updated_at)}</small></div>
                </div>

                <div className="research-case-substance">
                  <span className={`badge ${item.phase === "collecting" ? "accent" : item.phase === "valued" ? "success" : "neutral"}`}>{item.phase_label}</span>
                  <strong>{item.phase_summary}</strong>
                  {item.main_gap && <small>Główna luka: {item.main_gap}</small>}
                  {item.collection_progress && (
                    <small>
                      {item.collection_progress.percent == null ? "Postęp bez wiarygodnego procentu" : `Postęp ${item.collection_progress.percent.toLocaleString("pl-PL")}%`}
                      {item.collection_progress.remaining_sources.length > 0 && ` · pozostało: ${item.collection_progress.remaining_sources.join(", ")}`}
                    </small>
                  )}
                </div>

                <div className="research-case-evidence">
                  {item.valuation_strip ? (
                    <>
                      <div className="research-valuation-prices">
                        {Object.entries(item.valuation_strip.scenario_prices_pln).map(([kind, price]) => <span key={kind}>{SCENARIO_LABELS[kind] ?? kind}<strong>{fmtPln(price)}</strong></span>)}
                      </div>
                      <small>Wartość ważona {fmtPln(item.valuation_strip.weighted_value_pln)} · <span className={item.valuation_strip.upside_pct != null && item.valuation_strip.upside_pct >= 0 ? "pos" : "neg"}>{fmtPct(item.valuation_strip.upside_pct, { signed: true })}</span></small>
                      {item.valuation_strip.catalyst && <small>Katalizator: {item.valuation_strip.catalyst}</small>}
                      <span className={`badge ${valuationTone(item.valuation_strip.verification_status)}`}>Wycena {item.valuation_strip.verification_status}</span>
                    </>
                  ) : item.latest_snapshot_as_of ? (
                    <><small>Stan wiedzy {relativeDate(item.latest_snapshot_as_of)}</small><span className={`badge ${item.latest_snapshot_status === "verified" ? "success" : "warning"}`}>Research {item.latest_snapshot_status}</span></>
                  ) : (
                    <small>{item.collection_progress?.summary ?? "Oczekiwanie na pierwszy snapshot."}</small>
                  )}
                </div>

                <Link className="btn research-case-open" href={`/stock/${item.ticker}`}>Otwórz Research <IconArrowRight size={14} /></Link>
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
