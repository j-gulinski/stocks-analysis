"use client";

import { useEffect, useState } from "react";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { createAssumptionSet, getAssumptionSets } from "@/lib/api";
import type {
  AssumptionItem,
  AssumptionProvenance,
  AssumptionScenarioKind,
  AssumptionSet,
  ResearchCase,
} from "@/lib/types";

type DraftItem = Omit<AssumptionItem, "value" | "unit" | "source_ref"> & {
  value: string;
  unit: string;
  source_ref: string;
};

const SCENARIO_LABELS: Record<AssumptionScenarioKind, string> = {
  negative: "Negatywny",
  base: "Bazowy",
  positive: "Pozytywny",
  event: "Event",
};

const PROVENANCE_LABELS: Record<AssumptionProvenance, string> = {
  evidence: "Dowód / fakt",
  human_assumption: "Założenie człowieka",
  model_suggestion: "Sugestia modelu",
};

const EMPTY_ITEM: DraftItem = {
  key: "",
  value: "",
  unit: "",
  provenance: "human_assumption",
  source_ref: "",
  rationale: "",
};

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "—";
  return String(value);
}

function toValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const numeric = Number(trimmed.replace(",", "."));
  return Number.isFinite(numeric) ? numeric : trimmed;
}

export default function AssumptionSetsPanel({
  ticker,
  researchCase,
}: {
  ticker: string;
  researchCase: ResearchCase | null;
}) {
  const [sets, setSets] = useState<AssumptionSet[]>([]);
  const [scenarioKind, setScenarioKind] = useState<AssumptionScenarioKind>("base");
  const [label, setLabel] = useState("Bazowy");
  const [draftItem, setDraftItem] = useState<DraftItem>(EMPTY_ITEM);
  const [draftItems, setDraftItems] = useState<DraftItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!researchCase) {
      setSets([]);
      return;
    }
    setLoading(true);
    getAssumptionSets(ticker)
      .then(setSets)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [researchCase, ticker]);

  const addItem = () => {
    if (!draftItem.key.trim() || !draftItem.value.trim() || !draftItem.rationale.trim()) {
      setError("Uzupełnij klucz, wartość i uzasadnienie założenia.");
      return;
    }
    setError(null);
    setDraftItems((items) => [...items, { ...draftItem }]);
    setDraftItem({ ...EMPTY_ITEM });
  };

  const removeItem = (index: number) => {
    setDraftItems((items) => items.filter((_, itemIndex) => itemIndex !== index));
  };

  const saveSet = async () => {
    if (!researchCase) return;
    if (!label.trim() || draftItems.length === 0) {
      setError("Podaj nazwę zestawu i dodaj co najmniej jedno założenie.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await createAssumptionSet(ticker, {
        scenario_kind: scenarioKind,
        label: label.trim(),
        assumptions: draftItems.map((item) => ({
          ...item,
          key: item.key.trim(),
          value: toValue(item.value),
          unit: item.unit.trim() || null,
          source_ref: item.source_ref.trim() || null,
          rationale: item.rationale.trim(),
        })),
      });
      setSets((current) => [...current, created]);
      setDraftItems([]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="assumption-sets-panel" aria-label="Założenia scenariuszy">
      <div className="section-heading">
        <div>
          <p className="section-label">Scenariusze v2</p>
          <h2>Założenia z pochodzeniem</h2>
        </div>
        <p>Każde wejście mówi, czy pochodzi z dowodu, decyzji człowieka czy sugestii modelu.</p>
      </div>
      {!researchCase ? (
        <p className="muted">Najpierw utwórz przypadek badawczy w nagłówku spółki.</p>
      ) : (
        <>
          <div className="assumption-set-list">
            {loading && <p className="muted">Wczytuję zapisane założenia…</p>}
            {!loading && sets.length === 0 && <p className="muted">Brak zapisanych zestawów. Dodaj pierwszy poniżej.</p>}
            {sets.map((set) => (
              <article className="assumption-set-card" key={set.id}>
                <header>
                  <div><span className="badge neutral">{SCENARIO_LABELS[set.scenario_kind]}</span><strong>{set.label}</strong></div>
                  <span className="small muted">{set.status === "draft" ? "szkic" : set.status}</span>
                </header>
                <ul>
                  {set.assumptions.map((item) => (
                    <li key={`${set.id}-${item.key}`}>
                      <strong>{item.key}</strong>: {displayValue(item.value)}{item.unit ? ` ${item.unit}` : ""}
                      <span className="assumption-provenance">{PROVENANCE_LABELS[item.provenance]}</span>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
          <div className="assumption-set-editor">
            <div className="assumption-set-editor-heading">
              <strong>Nowy zestaw</strong>
              <span className="small muted">Zapisany zestaw jest szkicem do dalszej weryfikacji.</span>
            </div>
            <div className="assumption-set-fields">
              <label>Scenariusz<select value={scenarioKind} onChange={(event) => setScenarioKind(event.target.value as AssumptionScenarioKind)}><option value="negative">Negatywny</option><option value="base">Bazowy</option><option value="positive">Pozytywny</option><option value="event">Event</option></select></label>
              <label>Nazwa<input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="np. Mediana" /></label>
            </div>
            {draftItems.length > 0 && <ul className="assumption-draft-list">{draftItems.map((item, index) => <li key={`${item.key}-${index}`}><span><strong>{item.key}</strong> = {item.value} <em>{PROVENANCE_LABELS[item.provenance]}</em></span><button className="btn icon" aria-label={`Usuń ${item.key}`} onClick={() => removeItem(index)}><IconTrash size={14} /></button></li>)}</ul>}
            <div className="assumption-item-fields">
              <label>Klucz<input value={draftItem.key} onChange={(event) => setDraftItem({ ...draftItem, key: event.target.value })} placeholder="np. revenue_growth" /></label>
              <label>Wartość<input value={draftItem.value} onChange={(event) => setDraftItem({ ...draftItem, value: event.target.value })} placeholder="np. 0,12" /></label>
              <label>Jednostka<input value={draftItem.unit} onChange={(event) => setDraftItem({ ...draftItem, unit: event.target.value })} placeholder="ratio / PLN / %" /></label>
              <label>Pochodzenie<select value={draftItem.provenance} onChange={(event) => setDraftItem({ ...draftItem, provenance: event.target.value as AssumptionProvenance })}><option value="evidence">Dowód / fakt</option><option value="human_assumption">Założenie człowieka</option><option value="model_suggestion">Sugestia modelu</option></select></label>
              <label className="assumption-rationale">Uzasadnienie<input value={draftItem.rationale} onChange={(event) => setDraftItem({ ...draftItem, rationale: event.target.value })} placeholder="Dlaczego to założenie?" /></label>
              <label>Źródło<input value={draftItem.source_ref} onChange={(event) => setDraftItem({ ...draftItem, source_ref: event.target.value })} placeholder="np. fact:123" /></label>
              <button className="btn" onClick={addItem}><IconPlus size={14} /> Dodaj wejście</button>
            </div>
            <div className="assumption-editor-actions"><button className="btn accent" onClick={() => void saveSet()} disabled={saving}>{saving ? "Zapisuję…" : "Zapisz zestaw"}</button>{error && <span className="case-update-error">{error}</span>}</div>
          </div>
        </>
      )}
    </section>
  );
}
