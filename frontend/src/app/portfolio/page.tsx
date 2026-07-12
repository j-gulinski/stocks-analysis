"use client";

import { useEffect, useState } from "react";
import { getPortfolioWorkspace } from "@/lib/api";
import { LoadingMessages, SkeletonCards } from "@/components/Loading";
import PortfolioDashboard from "@/components/PortfolioDashboard";
import type { PortfolioWorkspace } from "@/lib/types";

export default function PortfolioPage() {
  const [workspace, setWorkspace] = useState<PortfolioWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPortfolioWorkspace()
      .then((result) => { if (!cancelled) setWorkspace(result); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { cancelled = true; };
  }, []);

  if (error) return <main className="page-stack portfolio-page"><section className="page-header"><div><p className="eyebrow">Portfolio</p><h1>Nie udało się otworzyć portfela</h1><p>Odczyt nie uruchomił synchronizacji ani nie zmienił zapisanych danych.</p></div></section><div className="error-box" role="alert">{error}</div></main>;
  if (!workspace) return <main className="page-stack portfolio-page"><SkeletonCards cards={5} /><LoadingMessages messages={["Otwieram ostatni snapshot portfela…", "Łączę pozycje ze zweryfikowanymi scenariuszami…"]} /></main>;
  return <PortfolioDashboard initial={workspace} />;
}
