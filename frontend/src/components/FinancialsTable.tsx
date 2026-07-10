"use client";

/** Finanse tab: statement tables Q/Y, BiznesRadar-like layout (period columns,
 * original row order, sticky label column). */
import { useState } from "react";
import { getFinancials } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LoadingMessages } from "@/components/Loading";
import { fmtNumber } from "@/lib/format";
import type { Financials } from "@/lib/types";

const STATEMENTS: { value: Financials["statement"]; label: string }[] = [
  { value: "income", label: "Rachunek zysków i strat" },
  { value: "balance", label: "Bilans" },
  { value: "cashflow", label: "Przepływy pieniężne" },
];

export default function FinancialsTable({ ticker }: { ticker: string }) {
  const [statement, setStatement] = useState<Financials["statement"]>("income");
  const [freq, setFreq] = useState<Financials["freq"]>("Q");
  const [showFullHistory, setShowFullHistory] = useState(false);

  const { data, error, loading } = useApi(
    () => getFinancials(ticker, statement, freq),
    [ticker, statement, freq],
  );
  const startIndex = data && !showFullHistory ? Math.max(0, data.periods.length - 8) : 0;
  const visiblePeriods = data?.periods.slice(startIndex) ?? [];

  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <select
          aria-label="Rodzaj sprawozdania"
          value={statement}
          onChange={(e) => {
            setStatement(e.target.value as Financials["statement"]);
            setShowFullHistory(false);
          }}
        >
          {STATEMENTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Częstotliwość sprawozdania"
          value={freq}
          onChange={(e) => {
            setFreq(e.target.value as Financials["freq"]);
            setShowFullHistory(false);
          }}
          disabled={statement !== "income"} // only income is scraped annually (v1)
        >
          <option value="Q">Kwartalnie</option>
          <option value="Y">Rocznie</option>
        </select>
        <span className="small muted">wartości w tys. zł</span>
        {data && data.periods.length > 8 && (
          <button className="btn compact" onClick={() => setShowFullHistory((value) => !value)}>
            {showFullHistory ? "Pokaż 8 ostatnich" : `Pełna historia (${data.periods.length})`}
          </button>
        )}
      </div>

      {loading && (
        <LoadingMessages
          messages={["Otwieram sprawozdanie…", "Układam kwartały w kolumny…"]}
        />
      )}
      {error && <div className="error-box">{error}</div>}
      {data && data.periods.length === 0 && (
        <p className="empty-state">Brak danych — odśwież spółkę.</p>
      )}

      {data && data.periods.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Pozycja</th>
                {visiblePeriods.map((period) => (
                  <th key={period}>{period}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.field_code}>
                  <td className="secondary">{row.label}</td>
                  {row.values.slice(startIndex).map((value, index) => (
                    <td key={visiblePeriods[index]}>{fmtNumber(value, 0)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
