"use client";

import Link from "next/link";
import { use, useState } from "react";
import { IconAlertTriangle, IconArrowLeft, IconRefresh } from "@tabler/icons-react";
import { getResearchWorkspace, queueResearchReview } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LoadingMessages, SkeletonCards } from "@/components/Loading";
import ResearchProfileEditor from "@/components/ResearchProfileEditor";
import ResearchSnapshotView from "@/components/ResearchSnapshotView";

function collectionCopy(status: "waiting" | "collecting" | "attention" | null) {
  if (status === "collecting") return {
    title: "Zbieram i porządkuję dowody",
    body: "Trwa praca nad źródłami, profilem spółki i pierwszym zrozumieniem biznesu.",
    tone: "accent",
  };
  if (status === "waiting") return {
    title: "Research czeka na wykonanie",
    body: "Spółka jest w kolejce. Po zebraniu i niezależnej weryfikacji pojawi się tu kanoniczny snapshot.",
    tone: "accent",
  };
  if (status === "attention") return {
    title: "Potrzebna jest decyzja",
    body: "Integralność źródeł lub profilu wymaga ręcznego rozstrzygnięcia przed dalszą analizą.",
    tone: "warning",
  };
  return {
    title: "Brak gotowego snapshotu",
    body: "Research nie ma jeszcze zweryfikowanego zapisu wiedzy o tej spółce.",
    tone: "muted",
  };
}

export default function StockPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker: rawTicker } = use(params);
  const ticker = rawTicker.toUpperCase();
  const [queueing, setQueueing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const { data: workspace, error, loading, reload } = useApi(
    () => getResearchWorkspace(ticker),
    [ticker],
  );

  if (loading) return <><SkeletonCards cards={4} /><LoadingMessages messages={[`Otwieram Research ${ticker}…`, "Sprawdzam ostatni zapis wiedzy…"]} /></>;
  if (error || !workspace) {
    return (
      <main className="page-stack">
        <div className="error-box" role="alert">{error ?? "Nie można otworzyć Research."}</div>
        <Link className="btn" href="/"><IconArrowLeft size={14} /> Wróć do Research</Link>
      </main>
    );
  }

  const snapshot = workspace.latest_snapshot;
  const profile = workspace.profile;
  const currentProfile = workspace.current_profile;
  const activeResearch = ["waiting", "collecting"].includes(
    workspace.research_case.collection_progress?.state ?? "",
  );
  const reviewBlockReason = !currentProfile
    ? "Brak profilu do potwierdzenia."
    : currentProfile.provenance === "codex-proposed"
      ? "Najpierw potwierdź lub skoryguj profil spółki."
      : currentProfile.company_overlay.source_questions.length === 0
        ? "Dodaj do profilu co najmniej jedno pytanie właściwe dla tej spółki."
        : null;

  const queueReview = async () => {
    if (reviewBlockReason) {
      setActionError(reviewBlockReason);
      return;
    }
    setQueueing(true);
    setMessage(null);
    setActionError(null);
    try {
      const result = await queueResearchReview(workspace.research_case.id);
      setMessage(
        result.created
          ? `Odświeżenie Research użyje potwierdzonego profilu v${result.profile_version}. Obecny snapshot pozostaje widoczny do czasu weryfikacji następnego.`
          : ["queued", "running"].includes(result.status)
            ? "Odświeżenie Research już oczekuje lub jest w toku."
            : "Ten sam stan źródeł został już przeanalizowany.",
      );
      reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setQueueing(false);
    }
  };

  if (!snapshot) {
    const state = collectionCopy(workspace.research_case.collection_progress?.state ?? null);
    return (
      <main className="page-stack stock-workspace snapshot-workspace">
        <section className="snapshot-blocked" role="status">
          <p className="eyebrow">Research · {ticker}</p>
          <span className={`badge ${state.tone}`}>{state.title}</span>
          <h1>{workspace.research_case.name ?? ticker}</h1>
          <p>{workspace.research_case.collection_progress?.summary ?? state.body}</p>
          {workspace.research_case.collection_progress && (
            <div className="snapshot-two-column">
              <div><strong>Zebrane źródła</strong><p>{workspace.research_case.collection_progress.completed_sources.join(" · ") || "Jeszcze brak"}</p></div>
              <div><strong>Pozostało</strong><p>{workspace.research_case.collection_progress.remaining_sources.join(" · ") || "Brak nazwanych źródeł"}</p></div>
            </div>
          )}
          {workspace.research_case.blocked_reason && <p><strong>Przyczyna:</strong> {workspace.research_case.blocked_reason}</p>}
        </section>
        {currentProfile && (
          <ResearchProfileEditor
            researchCaseId={workspace.research_case.id}
            profile={currentProfile}
            profileHistory={workspace.profile_history}
            onSaved={reload}
          />
        )}
        <Link className="btn" href="/"><IconArrowLeft size={14} /> Wróć do listy</Link>
      </main>
    );
  }

  if (!profile) {
    return <main className="page-stack"><div className="error-box" role="alert">Snapshot Research nie ma powiązanego profilu spółki. Wymagany jest przegląd integralności danych.</div></main>;
  }

  const blockedSnapshot = ["rejected", "needs-human"].includes(snapshot.status);
  const legacyVerification = snapshot.verifier_result.verification_standard === "legacy-incomplete";
  return (
    <main className="page-stack stock-workspace snapshot-workspace">
      {blockedSnapshot && (
        <section className="snapshot-blocked" role="alert">
          <IconAlertTriangle size={20} />
          <h2>Ten snapshot nie jest podstawą decyzji</h2>
          <p>{snapshot.verifier_result.summary}</p>
        </section>
      )}

      {legacyVerification && (
        <section className="snapshot-blocked" role="alert">
          <IconAlertTriangle size={20} />
          <h2>Historyczna weryfikacja wymaga odświeżenia</h2>
          <p>Snapshot pozostaje czytelny, ale zapisany verifier nie zawiera adversarialnego uzasadnienia wymaganego przez V5. Nie traktuj go jako ponownie zatwierdzonego.</p>
        </section>
      )}

      <ResearchSnapshotView
        ticker={ticker}
        companyName={workspace.research_case.name}
        profile={profile}
        snapshot={snapshot}
        history={workspace.history}
        archetypePack={workspace.archetype_pack}
        valuationStrip={workspace.research_case.valuation_strip}
      />

      {currentProfile && (
        <ResearchProfileEditor
          researchCaseId={workspace.research_case.id}
          profile={currentProfile}
          profileHistory={workspace.profile_history}
          onSaved={reload}
        />
      )}

      {currentProfile && currentProfile.id !== profile.id && (
        <section className="research-profile-pending" role="status">
          <IconAlertTriangle size={16} />
          <div>
            <strong>Profil v{currentProfile.version} czeka na nowy Research.</strong>
            <span>Widoczny snapshot zachowuje profil v{profile.version}; odświeżenie zamrozi i zweryfikuje kolejną wersję.</span>
          </div>
        </section>
      )}

      <section className="research-to-valuation">
        <div>
          <span className="snapshot-label">Następny krok</span>
          <strong>{blockedSnapshot ? "Usuń przyczynę odrzucenia i odśwież Research" : "Uzupełnij dowody albo przejdź do wyceny"}</strong>
          {reviewBlockReason && <small>{reviewBlockReason}</small>}
        </div>
        <div className="command-row">
          <button className="btn" type="button" title={reviewBlockReason ?? undefined} onClick={() => void queueReview()} disabled={Boolean(reviewBlockReason) || activeResearch || queueing}>
            <IconRefresh size={14} className={queueing ? "spin" : ""} />
            {queueing ? "Zlecam…" : "Odśwież Research"}
          </button>
          {!blockedSnapshot && <Link className="btn accent" href={`/valuation/${ticker}`}>Przejdź do Valuation</Link>}
        </div>
      </section>
      {message && <div className="success-box" role="status">{message}</div>}
      {actionError && <div className="error-box" role="alert">{actionError}</div>}
    </main>
  );
}
