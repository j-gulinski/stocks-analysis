"use client";

/** Explicit thesis-risk rules; status changes always require a reason. */
import { FormEvent, useEffect, useState } from "react";
import { IconAlertTriangle, IconDeviceFloppy, IconPlus } from "@tabler/icons-react";
import { createFalsifier, getFalsifiers, updateFalsifier } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Falsifier } from "@/lib/types";

type NewFalsifier = { key: string; statement: string; reason: string; review_date: string };

const EMPTY_FORM: NewFalsifier = {
  key: "",
  statement: "",
  reason: "Reguła zdefiniowana przez użytkownika.",
  review_date: "",
};

function statusLabel(status: Falsifier["status"]): string {
  return { holding: "trzymana", warning: "ostrzeżenie", fired: "uruchomiona" }[status];
}

function futureDate(): string {
  const value = new Date();
  value.setDate(value.getDate() + 30);
  return value.toISOString().slice(0, 10);
}

export default function FalsifiersPanel({ ticker }: { ticker: string }) {
  const [rows, setRows] = useState<Falsifier[]>([]);
  const [form, setForm] = useState<NewFalsifier>({ ...EMPTY_FORM, review_date: futureDate() });
  const [drafts, setDrafts] = useState<Record<number, { status: Falsifier["status"]; reason: string; review_date: string }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    getFalsifiers(ticker)
      .then((loaded) => {
        setRows(loaded);
        setDrafts(Object.fromEntries(loaded.map((row) => [row.id, {
          status: row.status,
          reason: row.reason,
          review_date: row.review_date ?? futureDate(),
        }])));
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [ticker]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await createFalsifier(ticker, { ...form, status: "holding" });
      setRows((current) => [...current, created]);
      setDrafts((current) => ({ ...current, [created.id]: { status: created.status, reason: created.reason, review_date: created.review_date ?? futureDate() } }));
      setForm({ ...EMPTY_FORM, review_date: futureDate() });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const save = async (row: Falsifier) => {
    const draft = drafts[row.id];
    if (!draft?.reason.trim()) {
      setError("Każda zmiana stanu falsyfikatora wymaga powodu.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateFalsifier(ticker, row.id, draft);
      setRows((current) => current.map((item) => item.id === updated.id ? updated : item));
      setDrafts((current) => ({ ...current, [updated.id]: { status: updated.status, reason: updated.reason, review_date: updated.review_date ?? futureDate() } }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card falsifier-panel" aria-labelledby="falsifiers-title">
      <div className="spread falsifier-heading">
        <div>
          <p className="section-label">Teza / ryzyko</p>
          <h2 id="falsifiers-title"><IconAlertTriangle size={17} /> Falsyfikatory</h2>
          <p className="small muted">Stan jest ręczny i wymaga powodu. System nigdy nie oznacza tezy jako uruchomionej samodzielnie.</p>
        </div>
        <span className="badge muted">holding · warning · fired</span>
      </div>
      {error && <div className="error-box">{error}</div>}
      {loading ? <p className="small muted">Ładuję reguły tezy…</p> : rows.length === 0 ? <p className="small muted">Brak jawnych falsyfikatorów dla tej tezy.</p> : (
        <div className="falsifier-list">
          {rows.map((row) => {
            const draft = drafts[row.id] ?? { status: row.status, reason: row.reason, review_date: row.review_date ?? "" };
            return <article className={`falsifier-row ${draft.status}`} key={row.id}>
              <div className="spread"><strong>{row.key}</strong><span className={`badge ${draft.status === "fired" ? "danger" : draft.status === "warning" ? "warning" : "muted"}`}>{statusLabel(draft.status)}</span></div>
              <p>{row.statement}</p>
              <div className="falsifier-edit">
                <select value={draft.status} onChange={(event) => setDrafts((current) => ({ ...current, [row.id]: { ...draft, status: event.target.value as Falsifier["status"] } }))} aria-label={`Stan falsyfikatora ${row.key}`}>
                  <option value="holding">trzymana</option><option value="warning">ostrzeżenie</option><option value="fired">uruchomiona</option>
                </select>
                <input value={draft.reason} onChange={(event) => setDrafts((current) => ({ ...current, [row.id]: { ...draft, reason: event.target.value } }))} placeholder="powód / dowód" aria-label={`Powód zmiany ${row.key}`} />
                <input type="date" value={draft.review_date} onChange={(event) => setDrafts((current) => ({ ...current, [row.id]: { ...draft, review_date: event.target.value } }))} aria-label={`Data przeglądu ${row.key}`} />
                <button className="btn compact" type="button" onClick={() => void save(row)} disabled={saving}><IconDeviceFloppy size={13} /> Zapisz</button>
              </div>
              <p className="small muted">Ostatnia zmiana: {fmtDate(row.updated_at)}</p>
            </article>;
          })}
        </div>
      )}
      <form className="falsifier-form" onSubmit={add}>
        <input required value={form.key} onChange={(event) => setForm({ ...form, key: event.target.value })} placeholder="klucz, np. margin" aria-label="Klucz falsyfikatora" />
        <input required value={form.statement} onChange={(event) => setForm({ ...form, statement: event.target.value })} placeholder="Warunek, który podważa tezę" aria-label="Treść falsyfikatora" />
        <input required value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder="Dlaczego ta reguła?" aria-label="Powód falsyfikatora" />
        <input required type="date" value={form.review_date} onChange={(event) => setForm({ ...form, review_date: event.target.value })} aria-label="Data przeglądu nowego falsyfikatora" />
        <button className="btn accent" type="submit" disabled={saving}><IconPlus size={13} /> Dodaj regułę</button>
      </form>
    </section>
  );
}
