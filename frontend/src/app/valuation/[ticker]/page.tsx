"use client";

import Link from "next/link";
import { use } from "react";
import { IconArrowLeft } from "@tabler/icons-react";
import ValuationWorkspaceView from "@/components/ValuationWorkspaceView";
import { getResearchWorkspace, getValuationWorkspace } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LoadingMessages, SkeletonCards } from "@/components/Loading";

export default function ValuationDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker: rawTicker } = use(params);
  const ticker = rawTicker.toUpperCase();
  const { data, error, loading } = useApi(async () => {
    const research = await getResearchWorkspace(ticker);
    const valuation = await getValuationWorkspace(research.research_case.id);
    return { research, valuation };
  }, [ticker]);

  if (loading) return <><SkeletonCards cards={3} /><LoadingMessages messages={[`Otwieram zamrożony Research ${ticker}…`, "Przygotowuję szablon wyceny…"]} /></>;
  if (error || !data) return <main className="page-stack"><div className="error-box">{error ?? "Nie można otworzyć wyceny."}</div><Link className="btn" href="/valuation"><IconArrowLeft size={14} /> Wróć do Valuation</Link></main>;

  const snapshot = data.research.latest_snapshot;
  if (!snapshot || !["provisional", "verified"].includes(snapshot.status)) {
    return <main className="page-stack"><section className="valuation-empty"><h2>Research nie jest gotowy do wyceny</h2><p>Do wyceny można użyć wyłącznie prowizorycznego lub zweryfikowanego snapshotu.</p><Link className="btn" href={`/stock/${ticker}`}>Otwórz Research</Link></section></main>;
  }
  return <ValuationWorkspaceView research={data.research} workspace={data.valuation} />;
}
