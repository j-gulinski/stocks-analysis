"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getPrices } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LoadingMessages } from "@/components/Loading";
import { fmtPln } from "@/lib/format";

/** 12-month close price line on the Overview tab. */
export default function PriceChart({ ticker }: { ticker: string }) {
  const { data, error, loading } = useApi(() => getPrices(ticker, 365), [ticker]);

  if (loading)
    return <LoadingMessages messages={["Rysuję wykres kursu…", "Skaluję osie…"]} />;
  if (error) return <div className="error-box">{error}</div>;
  if (!data || data.length === 0)
    return <p className="empty-state">Brak historii kursu — odśwież dane.</p>;

  return (
    <div className="card" style={{ height: 260 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            tickFormatter={(value: string) => value.slice(0, 7)}
            minTickGap={40}
            stroke="var(--border)"
          />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            domain={["auto", "auto"]}
            width={54}
            stroke="var(--border)"
          />
          <Tooltip
            formatter={(value) => [fmtPln(Number(value)), "kurs"]}
            contentStyle={{
              background: "var(--surface-2)",
              border: "0.5px solid var(--border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--text-muted)" }}
          />
          <Line
            type="monotone"
            dataKey="close"
            stroke="var(--fill-accent)"
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
