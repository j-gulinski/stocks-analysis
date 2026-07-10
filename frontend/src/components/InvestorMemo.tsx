import {
  IconBrain,
  IconCircleCheck,
  IconDatabase,
  IconEye,
  IconFlag,
  IconScale,
  IconSearch,
} from "@tabler/icons-react";
import { fmtPct, relativeDate, signClass } from "@/lib/format";
import type { Dossier, VerifyNextItem, WhatWouldChange } from "@/lib/types";

type MemoStatus = {
  label: string;
  tone: string;
  rationale: string;
};

type MemoTask = {
  id: string;
  text: string;
  why: string;
  source: string;
};

function decisionStatus(dossier: Dossier): MemoStatus {
  const quality = dossier.thesis?.entry_quality.code;
  const ev = dossier.scenarios?.weighted_expected_upside_pct;
  const confidence = dossier.valuation?.confidence.level;
  const readyForAi = dossier.analysis_context_status?.ready_for_ai ?? false;

  if (quality === "attractive" && ev != null && ev > 0 && confidence !== "low") {
    return {
      label: "Kandydat do decyzji",
      tone: "success",
      rationale:
        "Teza, wycena i pokrycie danych są spójne na tyle, żeby przejść do ręcznej weryfikacji ceny wejścia i ryzyka.",
    };
  }

  if (quality === "weak") {
    return {
      label: "Odrzuć lub czekaj",
      tone: "warning",
      rationale:
        "Aktualny odczyt nie daje przewagi wejścia. Wróć dopiero po zmianie ceny, wyników albo katalizatora.",
    };
  }

  if (quality === "insufficient_data" || !readyForAi) {
    return {
      label: "Research niepełny",
      tone: "muted",
      rationale:
        "Najpierw uzupełnij braki danych i potwierdź kluczowe założenia, bo decyzja byłaby oparta na zbyt wąskiej bazie.",
    };
  }

  return {
    label: "Obserwuj aktywnie",
    tone: "neutral",
    rationale:
      "Jest materiał do analizy, ale brakuje przewagi wystarczającej do decyzji bez dodatkowego katalizatora lub lepszej ceny.",
  };
}

function decisionReadiness(dossier: Dossier): number {
  let score = 0;
  if (dossier.quarters.length > 0) score += 20;
  if (dossier.ttm.price != null) score += 15;
  if (dossier.thesis) score += 20;
  if (dossier.scenarios) score += 15;
  if (dossier.valuation) score += 10;
  if (dossier.analysis_context_status?.ready_for_ai) score += 10;
  if ((dossier.forum.intelligence?.distilled_facts.length ?? 0) > 0) score += 5;
  if ((dossier.forum.intelligence?.expectations?.claims.length ?? 0) > 0) score += 5;
  return Math.min(100, score);
}

function topTasks(dossier: Dossier): MemoTask[] {
  const tasks: MemoTask[] = [];
  const seen = new Set<string>();

  const push = (task: MemoTask) => {
    const key = task.text.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      tasks.push(task);
    }
  };

  for (const item of dossier.thesis?.verify_next ?? []) {
    push({
      id: `thesis-${item.id}`,
      text: item.text,
      why: item.why,
      source: "teza",
    });
  }

  for (const item of dossier.valuation?.what_would_change ?? []) {
    push({
      id: `valuation-${item.id}`,
      text: item.text,
      why: item.why,
      source: "wycena",
    });
  }

  for (const claim of dossier.forum.intelligence?.expectations?.claims ?? []) {
    push({
      id: `forum-${claim.source_post_ids.join("-") || claim.claim}`,
      text: claim.claim,
      why: `Forum PortalAnaliz, pewność ${claim.confidence}; potwierdź w ESPI/raporcie przed użyciem w tezie.`,
      source: "forum",
    });
  }

  return tasks.slice(0, 6);
}

function hasCatalystTask(task: MemoTask | VerifyNextItem | WhatWouldChange) {
  const text = `${task.text} ${"why" in task ? task.why : ""}`.toLowerCase();
  return (
    text.includes("kataliz") ||
    text.includes("backlog") ||
    text.includes("certyfik") ||
    text.includes("espi") ||
    text.includes("zamów")
  );
}

function sourceRows(dossier: Dossier) {
  const facts = dossier.forum.intelligence?.distilled_facts.length ?? 0;
  const claims = dossier.forum.intelligence?.expectations?.claims.length ?? 0;
  const aiReady = dossier.analysis_context_status?.ready_for_ai ?? false;

  return [
    {
      label: "Sprawozdania",
      value: dossier.quarters.length > 0 ? relativeDate(dossier.freshness.financials_scraped_at) : "brak",
      tone: dossier.quarters.length > 0 ? "success" : "warning",
      detail: "BiznesRadar",
    },
    {
      label: "Cena i mnożniki",
      value: dossier.ttm.price != null ? relativeDate(dossier.freshness.last_price_date ?? dossier.ttm.price_date) : "brak",
      tone: dossier.ttm.price != null ? "success" : "warning",
      detail: dossier.ttm.market_cap_source === "reported" ? "mcap raportowany" : "mcap szacowany",
    },
    {
      label: "Forum",
      value: claims > 0 ? `${claims} tez` : facts > 0 ? `${facts} faktów` : "brak tropów",
      tone: claims > 0 || facts > 0 ? "neutral" : "muted",
      detail: "opinie, nie dowody",
    },
    {
      label: "AI context",
      value: aiReady ? "gotowy" : "luki",
      tone: aiReady ? "success" : "warning",
      detail: dossier.analysis_context_status?.missing.join(", ") || "pełny pakiet",
    },
  ];
}

export default function InvestorMemo({ dossier }: { dossier: Dossier }) {
  const status = decisionStatus(dossier);
  const readiness = decisionReadiness(dossier);
  const tasks = topTasks(dossier);
  const catalystOpen = tasks.some(hasCatalystTask);
  const negativeScenario = dossier.scenarios?.scenarios.find((s) => s.kind === "negative");
  const expectedUpside =
    dossier.scenarios?.weighted_expected_upside_pct ?? dossier.valuation?.potential.value_pct ?? null;
  const confidence = dossier.valuation?.confidence.level ?? "low";
  const confidenceLabel =
    confidence === "high" ? "wysoka" : confidence === "medium" ? "umiarkowana" : "niska";

  return (
    <div className="card investor-memo">
      <div className="memo-header">
        <div>
          <p className="section-kicker">
            <IconEye size={14} /> Memo inwestora
          </p>
          <h3>{status.label}</h3>
          <p className="memo-rationale">{status.rationale}</p>
        </div>
        <div className="readiness">
          <span className="readiness-value">{readiness}</span>
          <span className="readiness-label">gotowość researchu</span>
        </div>
      </div>

      <div className="memo-grid">
        <div className="memo-column">
          <p className="memo-title">
            <IconFlag size={14} /> Decyzja robocza
          </p>
          <div className="memo-facts">
            <div>
              <span className="k">Status</span>
              <span className={`badge ${status.tone}`}>{status.label}</span>
            </div>
            <div>
              <span className="k">Potencjał ważony</span>
              <strong className={signClass(expectedUpside)}>
                {fmtPct(expectedUpside, { signed: true })}
              </strong>
            </div>
            <div>
              <span className="k">Pewność</span>
              <strong>{confidenceLabel}</strong>
            </div>
            <div>
              <span className="k">Katalizator</span>
              <strong className={catalystOpen ? "warn" : "secondary"}>
                {catalystOpen ? "do potwierdzenia" : "brak jawnego tropu"}
              </strong>
            </div>
          </div>
        </div>

        <div className="memo-column">
          <p className="memo-title">
            <IconScale size={14} /> Downside first
          </p>
          {negativeScenario ? (
            <>
              <div className="downside-line">
                <span>{negativeScenario.label}</span>
                <strong className={signClass(negativeScenario.implied_upside_pct)}>
                  {fmtPct(negativeScenario.implied_upside_pct, { signed: true })}
                </strong>
              </div>
              <p className="memo-note">{negativeScenario.narrative}</p>
            </>
          ) : (
            <p className="memo-note warn">
              Brak scenariusza negatywnego — nie używaj wyceny jako decyzji.
            </p>
          )}
        </div>
      </div>

      <div className="memo-section">
        <p className="memo-title">
          <IconSearch size={14} /> Co blokuje decyzję
        </p>
        {tasks.length > 0 ? (
          <div className="task-list">
            {tasks.map((task) => (
              <div className="memo-task" key={task.id}>
                <div className="spread" style={{ gap: 8 }}>
                  <strong>{task.text}</strong>
                  <span className="badge muted">{task.source}</span>
                </div>
                {task.why && <p>{task.why}</p>}
              </div>
            ))}
          </div>
        ) : (
          <p className="memo-note">Brak jawnych blokad w dossier; ręcznie sprawdź raport i komunikaty spółki.</p>
        )}
      </div>

      <div className="memo-section">
        <p className="memo-title">
          <IconDatabase size={14} /> Źródła i zaufanie
        </p>
        <div className="source-proof-grid">
          {sourceRows(dossier).map((row) => (
            <div className="source-proof" key={row.label}>
              <span className="source-label">{row.label}</span>
              <strong className={row.tone}>{row.value}</strong>
              <span>{row.detail}</span>
            </div>
          ))}
        </div>
      </div>

      <p className="memo-disclaimer">
        <IconBrain size={13} /> To jest bramka decyzyjna dla researchu: pomaga wybrać
        następny krok, ale nie zastępuje własnej decyzji inwestycyjnej.
      </p>
    </div>
  );
}
