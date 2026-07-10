"use client";

/** Fast, append-only investor decision record attached to the current thesis. */
import { FormEvent, useEffect, useMemo, useState } from "react";
import { IconBook, IconDeviceFloppy, IconRefresh } from "@tabler/icons-react";
import { checkMonitor, createDecisionJournalEntry, getDecisionJournal } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { DecisionJournalEntry, MonitorCheckResult, Thesis } from "@/lib/types";

type JournalForm = {
  decision: string;
  confidence: string;
  thesis: string;
  invalidation: string;
  next_check: string;
  review_date: string;
};

function futureDate(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function initialForm(thesis: Thesis | undefined): JournalForm {
  return {
    decision: "holding",
    confidence: "50",
    thesis: thesis?.thesis_read ?? "",
    invalidation: thesis?.verify_next[0]?.text ?? "",
    next_check: thesis?.verify_next[0]?.text ?? "",
    review_date: futureDate(30),
  };
}

function decisionLabel(value: string): string {
  return {
    holding: "Utrzymuję tezę",
    watching: "Obserwuję",
    review: "Wymaga ponownej analizy",
    passed: "Odkładam przypadek",
  }[value] ?? value;
}

export default function DecisionJournalPanel({
  ticker,
  thesis,
}: {
  ticker: string;
  thesis?: Thesis;
}) {
  const [entries, setEntries] = useState<DecisionJournalEntry[]>([]);
  const [form, setForm] = useState<JournalForm>(() => initialForm(thesis));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [monitorResult, setMonitorResult] = useState<MonitorCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const snapshot = useMemo(
    () =>
      thesis
        ? {
            thesis_read: thesis.thesis_read,
            strategy: thesis.strategy,
            entry_quality: thesis.entry_quality,
          }
        : {},
    [thesis],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDecisionJournal(ticker)
      .then((loaded) => {
        if (!cancelled) setEntries(loaded);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await createDecisionJournalEntry(ticker, {
        ...form,
        confidence: Number(form.confidence),
        thesis_snapshot: snapshot,
      });
      setEntries((current) => [created, ...current]);
      setForm({ ...initialForm(thesis), decision: form.decision, confidence: form.confidence });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const monitor = async () => {
    setChecking(true);
    setError(null);
    try {
      setMonitorResult(await checkMonitor(ticker));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  };

  return (
    <section className="card journal-panel" aria-labelledby="decision-journal-title">
      <div className="spread journal-heading">
        <div>
          <p className="section-label">Monitor / Journal</p>
          <h2 id="decision-journal-title"><IconBook size={17} /> Decyzja na dziś</h2>
          <p className="small muted">Nowy wpis dopisuje historię i zapisuje tezę dokładnie w tej wersji.</p>
        </div>
        <div className="row wrap">
          <span className="badge muted">append-only</span>
          <button className="btn compact" type="button" onClick={() => void monitor()} disabled={checking}>
            <IconRefresh size={13} className={checking ? "spin" : ""} />
            {checking ? "Sprawdzam…" : "Sprawdź zmiany"}
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {monitorResult && (
        <div className={`monitor-result ${monitorResult.changed ? "changed" : "unchanged"}`} aria-live="polite">
          <strong>{monitorResult.changed ? "Znaleziono zmianę od poprzedniej sesji" : monitorResult.baseline_exists ? "Brak zmian od poprzedniej sesji" : "Utworzono pierwszy punkt odniesienia"}</strong>
          {monitorResult.change && <span>{monitorResult.change.changes.slice(0, 4).map((change) => change.summary).join(" ")}</span>}
        </div>
      )}

      <form onSubmit={submit}>
        <div className="journal-form">
          <label>
            Decyzja
            <select value={form.decision} onChange={(event) => setForm({ ...form, decision: event.target.value })}>
              <option value="holding">Utrzymuję tezę</option>
              <option value="watching">Obserwuję</option>
              <option value="review">Wymaga ponownej analizy</option>
              <option value="passed">Odkładam przypadek</option>
            </select>
          </label>
          <label>
            Pewność: <strong>{form.confidence}%</strong>
            <input type="range" min="0" max="100" step="5" value={form.confidence} onChange={(event) => setForm({ ...form, confidence: event.target.value })} />
          </label>
          <label>
            Następny przegląd
            <input type="date" required value={form.review_date} onChange={(event) => setForm({ ...form, review_date: event.target.value })} />
          </label>
          <label className="journal-wide">
            Teza
            <textarea required rows={2} value={form.thesis} onChange={(event) => setForm({ ...form, thesis: event.target.value })} />
          </label>
          <label>
            Co unieważnia tezę?
            <textarea required rows={2} value={form.invalidation} onChange={(event) => setForm({ ...form, invalidation: event.target.value })} />
          </label>
          <label>
            Co sprawdzę dalej?
            <textarea required rows={2} value={form.next_check} onChange={(event) => setForm({ ...form, next_check: event.target.value })} />
          </label>
        </div>
        <div className="command-row journal-actions">
          <button className="btn accent" type="submit" disabled={saving}><IconDeviceFloppy size={14} /> {saving ? "Zapisuję…" : "Zapisz decyzję"}</button>
          <span className="small muted">Wpisu nie można edytować — korektę dopisz jako nową decyzję.</span>
        </div>
      </form>

      <div className="journal-history">
        <p className="candidate-label">Ostatnie wpisy</p>
        {loading ? <p className="small muted">Ładuję historię…</p> : entries.length === 0 ? <p className="small muted">Brak wpisów. Pierwszy zajmuje mniej niż minutę.</p> : entries.slice(0, 5).map((entry) => (
          <article className="journal-entry" key={entry.id}>
            <div className="spread"><strong>{decisionLabel(entry.decision)}</strong><span className="small muted">{fmtDate(entry.created_at)} · pewność {entry.confidence}%</span></div>
            <p>{entry.thesis}</p>
            <div className="journal-meta"><span>Unieważnienie: {entry.invalidation}</span><span>Następnie: {entry.next_check}</span><span>Przegląd: {entry.review_date}</span></div>
          </article>
        ))}
      </div>
    </section>
  );
}
