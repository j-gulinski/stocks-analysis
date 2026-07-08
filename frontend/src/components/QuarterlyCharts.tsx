"use client";

/** Wykresy tab — the Excel "Wykresy" sheet: four quarterly charts with two
 * views (sequence and year-over-year quarter grouping). */
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtNumber } from "@/lib/format";
import type { QuarterMetrics } from "@/lib/types";

type Mode = "seq" | "yoy";
type Field = keyof Pick<
  QuarterMetrics,
  "revenue" | "gross_margin_pct" | "profit_on_sales" | "net_profit"
>;

const CHARTS: { field: Field; title: string; unit: string; color: string; toMln?: boolean }[] = [
  { field: "revenue", title: "Przychody", unit: "mln zł", color: "var(--fill-accent)", toMln: true },
  { field: "gross_margin_pct", title: "Marża brutto na sprzedaży", unit: "%", color: "var(--fill-success)" },
  { field: "profit_on_sales", title: "Zysk ze sprzedaży", unit: "mln zł", color: "var(--fill-accent)", toMln: true },
  { field: "net_profit", title: "Zysk netto", unit: "mln zł", color: "var(--fill-success)", toMln: true },
];

const YEAR_OPACITIES = [0.35, 0.65, 1.0]; // older → newer

const tooltipStyle = {
  background: "var(--surface-2)",
  border: "0.5px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
} as const;

function scaled(value: number | null, toMln?: boolean): number | null {
  if (value == null) return null;
  return toMln ? Math.round((value / 1000) * 10) / 10 : value;
}

export default function QuarterlyCharts({ quarters }: { quarters: QuarterMetrics[] }) {
  const [mode, setMode] = useState<Mode>("seq");

  const years = useMemo(() => {
    const all = [...new Set(quarters.map((q) => q.period.slice(0, 4)))].sort();
    return all.slice(-3); // last 3 years keep the y/y view readable
  }, [quarters]);

  if (quarters.length === 0)
    return <p className="empty-state">Brak danych kwartalnych — odśwież spółkę.</p>;

  const buildSequence = (field: Field, toMln?: boolean) =>
    quarters.map((q) => ({ period: q.period, value: scaled(q[field], toMln) }));

  const buildYoy = (field: Field, toMln?: boolean) =>
    ["Q1", "Q2", "Q3", "Q4"].map((label) => {
      const row: Record<string, string | number | null> = { quarter: label };
      for (const year of years) {
        const match = quarters.find((q) => q.period === `${year}${label}`);
        row[year] = match ? scaled(match[field], toMln) : null;
      }
      return row;
    });

  return (
    <div>
      <div className="tabs" style={{ margin: "0 0 12px" }}>
        <button className={mode === "seq" ? "active" : ""} onClick={() => setMode("seq")}>
          Kwartalnie
        </button>
        <button className={mode === "yoy" ? "active" : ""} onClick={() => setMode("yoy")}>
          Rok do roku
        </button>
      </div>

      <div className="grid-2">
        {CHARTS.map((chart) => (
          <div className="card" key={chart.field}>
            <p style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>
              {chart.title} <span className="muted">({chart.unit})</span>
            </p>
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                {mode === "seq" ? (
                  <BarChart data={buildSequence(chart.field, chart.toMln)}>
                    <XAxis
                      dataKey="period"
                      tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                      stroke="var(--border)"
                      minTickGap={18}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                      width={44}
                      stroke="var(--border)"
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      formatter={(v) => [fmtNumber(Number(v)), chart.title]}
                    />
                    <Bar dataKey="value" fill={chart.color} radius={[3, 3, 0, 0]} />
                  </BarChart>
                ) : (
                  <BarChart data={buildYoy(chart.field, chart.toMln)}>
                    <XAxis
                      dataKey="quarter"
                      tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                      stroke="var(--border)"
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                      width={44}
                      stroke="var(--border)"
                      domain={["auto", "auto"]}
                    />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {years.map((year, index) => (
                      <Bar
                        key={year}
                        dataKey={year}
                        fill={chart.color}
                        fillOpacity={YEAR_OPACITIES[index] ?? 1}
                        radius={[3, 3, 0, 0]}
                      />
                    ))}
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
