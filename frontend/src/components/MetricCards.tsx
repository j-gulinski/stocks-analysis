import { fmtMcap, fmtNumber, fmtPct, fmtTysAsMln } from "@/lib/format";
import type { Dossier } from "@/lib/types";

/** Key numbers strip on the Przegląd tab (design: metric cards row). */
export default function MetricCards({ dossier }: { dossier: Dossier }) {
  const forwardPe = dossier.latest_forecast?.result.forward.pe ?? null;
  // newest year can be declared-but-unpaid (yield null) — show the latest real one
  const lastDividend = dossier.dividends.find((d) => d.yield_pct != null) ?? null;

  // mcap caveats: "derived" = kurs × akcje (estimate); >20% gap between the
  // reported and derived values means the sources disagree — flag it
  const mcapNotes: { text: string; tone: string }[] = [];
  if (dossier.ttm.market_cap_source === "derived")
    mcapNotes.push({ text: "szacunkowa (kurs × liczba akcji)", tone: "muted" });
  if (dossier.ttm.market_cap_check_pct != null && dossier.ttm.market_cap_check_pct > 20)
    mcapNotes.push({
      text: `rozbieżność źródeł ${fmtPct(dossier.ttm.market_cap_check_pct, { digits: 0 })}`,
      tone: "warn",
    });

  const cards: { label: string; value: string; tone?: string; notes?: typeof mcapNotes }[] = [
    { label: "C/Z TTM", value: fmtNumber(dossier.ttm.pe) },
    { label: "C/Z forward", value: fmtNumber(forwardPe), tone: forwardPe != null ? "pos" : "" },
    { label: "Mediana C/Z (hist.)", value: fmtNumber(dossier.pe_history.median) },
    {
      label: "Gotówka netto",
      value: fmtTysAsMln(dossier.net_cash.value),
      tone:
        dossier.net_cash.value == null ? "" : dossier.net_cash.value > 0 ? "pos" : "neg",
    },
    {
      label: "Stopa dywidendy",
      value: lastDividend ? fmtPct(lastDividend.yield_pct) : "—",
    },
    { label: "Kapitalizacja", value: fmtMcap(dossier.ttm.market_cap), notes: mcapNotes },
  ];

  return (
    <div className="grid-cards">
      {cards.map((card) => (
        <div className="metric-card" key={card.label}>
          <p className="label">{card.label}</p>
          <p className={`value ${card.tone ?? ""}`}>{card.value}</p>
          {card.notes?.map((note) => (
            <p key={note.text} className={note.tone} style={{ fontSize: 11, margin: "2px 0 0" }}>
              {note.text}
            </p>
          ))}
        </div>
      ))}
    </div>
  );
}
