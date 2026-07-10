"use client";

/** Read-only portfolio context; positions never enter dossier/AI inputs. */
import { useEffect, useState } from "react";
import { IconBriefcase } from "@tabler/icons-react";
import { getPositions } from "@/lib/api";
import { fmtDate, fmtPln } from "@/lib/format";
import type { Position } from "@/lib/types";

export default function PositionPanel({ ticker }: { ticker: string }) {
  const [rows, setRows] = useState<Position[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPositions(ticker)
      .then((loadedRows) => {
        if (!cancelled) setRows(loadedRows);
      })
      .catch(() => {
        // Portfolio context is optional; a failed read must not block research.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  if (!loaded || rows.length === 0) return null;
  return (
    <section className="card position-panel" aria-labelledby="position-title">
      <div className="spread">
        <div>
          <p className="section-label">Kontekst portfela</p>
          <h2 id="position-title"><IconBriefcase size={17} /> Pozycja</h2>
        </div>
        <span className="badge muted">read-only · nie wpływa na wynik</span>
      </div>
      <div className="position-list">
        {rows.map((row) => (
          <div className="position-row" key={row.id}>
            <strong>{row.ticker}</strong>
            <span>{row.quantity ?? "—"} szt. · wejście {fmtPln(row.entry_price)}</span>
            <span>{fmtPln(row.size_pln)} · {row.portfolio}</span>
            <span className="small muted">{row.entry_date ? fmtDate(row.entry_date) : "data wejścia —"}{row.sizing_rule_flag ? " · reguła sizingu" : ""}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
