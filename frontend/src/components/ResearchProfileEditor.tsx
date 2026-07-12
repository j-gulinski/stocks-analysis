"use client";

/** Explicit, user-owned successor profiles; snapshots remain immutable. */
import { useEffect, useState } from "react";
import { IconCheck, IconChevronRight, IconPlus, IconTrash } from "@tabler/icons-react";
import { ApiError, confirmResearchProfile } from "@/lib/api";
import type {
  CompanyOverlay,
  CompanyProfile,
  ResearchArchetype,
  ResearchDriver,
  ResearchKpi,
} from "@/lib/types";

const ARCHETYPES: Array<{ value: ResearchArchetype; label: string }> = [
  { value: "industrial-consumer", label: "Przemysł / konsument" },
  { value: "bank-financial", label: "Bank / finanse" },
  { value: "developer-real-estate", label: "Deweloper / nieruchomości" },
  { value: "software-services", label: "Software / usługi" },
  { value: "gaming-event", label: "Gaming / wydarzenie" },
  { value: "energy-resources", label: "Energia / surowce" },
  { value: "holding-biotech", label: "Holding / biotech" },
];

type Draft = {
  archetype: ResearchArchetype;
  company_overlay: CompanyOverlay;
  drivers: ResearchDriver[];
  kpis: ResearchKpi[];
  reason: string;
};

const newDriver = (): ResearchDriver => ({
  key: "",
  label: "",
  mechanism: "",
  unit: null,
  source_document_version_ids: [],
  basis: null,
  focus_tags: [],
});

const newKpi = (): ResearchKpi => ({
  key: "",
  label: "",
  unit: null,
  rationale: "",
  source_document_version_ids: [],
  basis: null,
  focus_tags: [],
});

function lines(items: string[]) {
  return items.join("\n");
}

function toLines(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function ids(value: string) {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item > 0);
}

function draftFrom(profile: CompanyProfile): Draft {
  return {
    archetype: profile.archetype,
    company_overlay: {
      segments: [...profile.company_overlay.segments],
      competitors: [...profile.company_overlay.competitors],
      source_questions: [...profile.company_overlay.source_questions],
      unusual_risks: [...profile.company_overlay.unusual_risks],
    },
    drivers: profile.drivers.map((item) => ({ ...item, source_document_version_ids: [...item.source_document_version_ids], focus_tags: [...item.focus_tags] })),
    kpis: profile.kpis.map((item) => ({ ...item, source_document_version_ids: [...item.source_document_version_ids], focus_tags: [...item.focus_tags] })),
    reason: "",
  };
}

function ProfileListField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <label>
      {label}
      <textarea value={lines(value)} onChange={(event) => onChange(toLines(event.target.value))} rows={3} />
      <small>Jedna pozycja w wierszu.</small>
    </label>
  );
}

export default function ResearchProfileEditor({
  researchCaseId,
  profile,
  profileHistory,
  onSaved,
}: {
  researchCaseId: number;
  profile: CompanyProfile;
  profileHistory: CompanyProfile[];
  onSaved: () => Promise<unknown> | void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(profile));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(draftFrom(profile));
    setError(null);
  }, [profile.id]);

  const updateDriver = (index: number, patch: Partial<ResearchDriver>) => {
    setDraft((current) => ({
      ...current,
      drivers: current.drivers.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }));
  };
  const updateKpi = (index: number, patch: Partial<ResearchKpi>) => {
    setDraft((current) => ({
      ...current,
      kpis: current.kpis.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }));
  };

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await confirmResearchProfile(researchCaseId, {
        base_profile_id: profile.id,
        reason: draft.reason.trim(),
        archetype: draft.archetype,
        company_overlay: draft.company_overlay,
        drivers: draft.drivers,
        kpis: draft.kpis,
      });
      setMessage(
        saved.provenance === "human-confirmed"
          ? `Potwierdzono profil v${saved.version}.`
          : `Zapisano Twoją korektę jako profil v${saved.version}.`,
      );
      await onSaved();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="research-profile-editor" aria-label="Profil badawczy użytkownika">
      <header>
        <div>
          <span className="snapshot-label">Pamięć Research</span>
          <h2>Potwierdź lub skoryguj profil</h2>
          <p>To utworzy nową, niezmienną wersję profilu. Obecny snapshot i jego dowody pozostaną bez zmian, aż jawnie zlecisz Research.</p>
        </div>
        <span className={`badge ${profile.provenance === "codex-proposed" ? "warning" : "success"}`}>
          {profile.provenance === "codex-proposed" ? "propozycja Codex" : "potwierdzone przez Ciebie"}
        </span>
      </header>
      <details>
        <summary><IconChevronRight size={15} /> Edytuj profil v{profile.version}</summary>
        <div className="research-profile-form">
          <label>
            Archetyp
            <select value={draft.archetype} onChange={(event) => setDraft((current) => ({ ...current, archetype: event.target.value as ResearchArchetype }))}>
              {ARCHETYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <div className="research-profile-overlay">
            <ProfileListField label="Segmenty" value={draft.company_overlay.segments} onChange={(segments) => setDraft((current) => ({ ...current, company_overlay: { ...current.company_overlay, segments } }))} />
            <ProfileListField label="Konkurenci / porównania" value={draft.company_overlay.competitors} onChange={(competitors) => setDraft((current) => ({ ...current, company_overlay: { ...current.company_overlay, competitors } }))} />
            <ProfileListField label="Pytania do źródeł" value={draft.company_overlay.source_questions} onChange={(source_questions) => setDraft((current) => ({ ...current, company_overlay: { ...current.company_overlay, source_questions } }))} />
            <ProfileListField label="Nietypowe ryzyka" value={draft.company_overlay.unusual_risks} onChange={(unusual_risks) => setDraft((current) => ({ ...current, company_overlay: { ...current.company_overlay, unusual_risks } }))} />
          </div>

          <div className="research-profile-items">
            <div className="research-profile-items-heading"><h3>Czynniki wyniku</h3><button className="btn compact" type="button" onClick={() => setDraft((current) => ({ ...current, drivers: [...current.drivers, newDriver()] }))}><IconPlus size={14} /> Dodaj czynnik</button></div>
            {draft.drivers.map((item, index) => (
              <details className="research-profile-item" key={`${index}-${item.key}`} open>
                <summary>{item.label || `Czynnik ${index + 1}`}</summary>
                <div className="research-profile-item-fields">
                  <label>Klucz<input value={item.key} onChange={(event) => updateDriver(index, { key: event.target.value })} /></label>
                  <label>Etykieta<input value={item.label} onChange={(event) => updateDriver(index, { label: event.target.value })} /></label>
                  <label>Jednostka<input value={item.unit ?? ""} onChange={(event) => updateDriver(index, { unit: event.target.value || null })} /></label>
                  <label>Tag pakietu<input value={lines(item.focus_tags)} onChange={(event) => updateDriver(index, { focus_tags: toLines(event.target.value) })} placeholder="opcjonalnie, jeden" /></label>
                  <label className="wide">Mechanizm<textarea value={item.mechanism} onChange={(event) => updateDriver(index, { mechanism: event.target.value })} rows={2} /></label>
                  <label>Wersje dokumentów<input value={item.source_document_version_ids.join(", ")} onChange={(event) => updateDriver(index, { source_document_version_ids: ids(event.target.value) })} placeholder="np. 12, 18" /></label>
                  <label className="wide">Podstawa przy braku dokumentu<textarea value={item.basis ?? ""} onChange={(event) => updateDriver(index, { basis: event.target.value || null })} rows={2} /></label>
                  <button className="btn danger compact" type="button" onClick={() => setDraft((current) => ({ ...current, drivers: current.drivers.filter((_, itemIndex) => itemIndex !== index) }))}><IconTrash size={14} /> Usuń</button>
                </div>
              </details>
            ))}
          </div>

          <div className="research-profile-items">
            <div className="research-profile-items-heading"><h3>KPI</h3><button className="btn compact" type="button" onClick={() => setDraft((current) => ({ ...current, kpis: [...current.kpis, newKpi()] }))}><IconPlus size={14} /> Dodaj KPI</button></div>
            {draft.kpis.map((item, index) => (
              <details className="research-profile-item" key={`${index}-${item.key}`} open>
                <summary>{item.label || `KPI ${index + 1}`}</summary>
                <div className="research-profile-item-fields">
                  <label>Klucz<input value={item.key} onChange={(event) => updateKpi(index, { key: event.target.value })} /></label>
                  <label>Etykieta<input value={item.label} onChange={(event) => updateKpi(index, { label: event.target.value })} /></label>
                  <label>Jednostka<input value={item.unit ?? ""} onChange={(event) => updateKpi(index, { unit: event.target.value || null })} /></label>
                  <label>Tag pakietu<input value={lines(item.focus_tags)} onChange={(event) => updateKpi(index, { focus_tags: toLines(event.target.value) })} placeholder="opcjonalnie, jeden" /></label>
                  <label className="wide">Uzasadnienie<textarea value={item.rationale} onChange={(event) => updateKpi(index, { rationale: event.target.value })} rows={2} /></label>
                  <label>Wersje dokumentów<input value={item.source_document_version_ids.join(", ")} onChange={(event) => updateKpi(index, { source_document_version_ids: ids(event.target.value) })} placeholder="np. 12, 18" /></label>
                  <label className="wide">Podstawa przy braku dokumentu<textarea value={item.basis ?? ""} onChange={(event) => updateKpi(index, { basis: event.target.value || null })} rows={2} /></label>
                  <button className="btn danger compact" type="button" onClick={() => setDraft((current) => ({ ...current, kpis: current.kpis.filter((_, itemIndex) => itemIndex !== index) }))}><IconTrash size={14} /> Usuń</button>
                </div>
              </details>
            ))}
          </div>

          <label className="research-profile-reason">Powód potwierdzenia lub korekty<textarea value={draft.reason} onChange={(event) => setDraft((current) => ({ ...current, reason: event.target.value }))} rows={2} placeholder="Np. po rozmowie z zarządem zmieniam znaczenie backlogu." /></label>
          <div className="research-profile-actions"><button className="btn accent" type="button" onClick={() => void save()} disabled={saving || draft.reason.trim().length < 3}><IconCheck size={14} /> {saving ? "Zapisuję…" : "Potwierdź profil"}</button>{message && <span className="success-box" role="status">{message}</span>}{error && <span className="error-box" role="alert">{error}</span>}</div>
        </div>
      </details>
      <details className="research-profile-history">
        <summary>Historia profili ({profileHistory.length})</summary>
        <ol>{profileHistory.map((item) => <li key={item.id}><strong>v{item.version} · {item.provenance === "codex-proposed" ? "propozycja Codex" : "Twoja wersja"}</strong><span>{item.reason ?? "Profil zaproponowany przez job Research."}</span><small>{new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}</small></li>)}</ol>
      </details>
    </section>
  );
}
