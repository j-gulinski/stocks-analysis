"use client";

/** Prognoza tab — the Excel next-quarter workflow: prefilled assumptions,
 * live recompute (computed server-side, save=false), scenario saving. */
import { useCallback, useEffect, useRef, useState } from "react";
import { IconDeviceFloppy, IconRestore } from "@tabler/icons-react";
import {
  computeForecast,
  getForecastDefaults,
  listForecasts,
  saveForecast,
} from "@/lib/api";
import { fmtDate, fmtNumber, fmtPct, fmtTysAsMln, parseNum, signClass } from "@/lib/format";
import type { Dossier, Forecast, ForecastAssumptions } from "@/lib/types";

type FieldKey = keyof Omit<ForecastAssumptions, "period" | "tax_rate">;

const FIELDS: { key: FieldKey; label: string; hint: string }[] = [
  { key: "revenue", label: "Przychody (tys. zł)", hint: "domyślnie: ostatni kwartał" },
  { key: "gross_margin_pct", label: "Marża brutto %", hint: "domyślnie: ostatni kwartał" },
  { key: "selling_costs_pct", label: "Koszty sprzedaży % przych.", hint: "śr. 4 kw." },
  { key: "admin_costs", label: "Koszty zarządu (tys. zł)", hint: "uwaga: rezerwy w Q4" },
  { key: "other_operating", label: "Pozost. dział. oper. (tys. zł)", hint: "śr. 4 kw." },
  { key: "financial_net", label: "Dział. finansowa (tys. zł)", hint: "śr. 4 kw. — uwaga FX" },
  { key: "depreciation", label: "Amortyzacja (tys. zł)", hint: "dla EBITDA" },
];

function toStrings(a: ForecastAssumptions): Record<FieldKey, string> {
  const out = {} as Record<FieldKey, string>;
  for (const { key } of FIELDS) {
    const value = a[key];
    out[key] = value == null ? "" : String(value).replace(".", ",");
  }
  return out;
}

export default function ForecastPanel({
  ticker,
  dossier,
  onSaved,
}: {
  ticker: string;
  dossier: Dossier;
  onSaved: () => void;
}) {
  const [defaults, setDefaults] = useState<ForecastAssumptions | null>(null);
  const [inputs, setInputs] = useState<Record<FieldKey, string> | null>(null);
  const [period, setPeriod] = useState("");
  const [preview, setPreview] = useState<Forecast | null>(null);
  const [saved, setSaved] = useState<Forecast[]>([]);
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadDefaults = useCallback(async () => {
    setError(null);
    try {
      const d = await getForecastDefaults(ticker);
      setDefaults(d);
      setInputs(toStrings(d));
      setPeriod(d.period);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [ticker]);

  useEffect(() => {
    void loadDefaults();
    listForecasts(ticker).then(setSaved).catch(() => setSaved([]));
  }, [ticker, loadDefaults]);

  const buildAssumptions = useCallback((): ForecastAssumptions | null => {
    if (!inputs || !/^\d{4}Q[1-4]$/.test(period)) return null;
    const parsed: Partial<ForecastAssumptions> = { period, tax_rate: 0.19 };
    for (const { key } of FIELDS) {
      const value = parseNum(inputs[key]);
      if (key === "depreciation") {
        parsed.depreciation = value;
      } else if (value == null) {
        return null; // incomplete input — keep last preview, no request spam
      } else {
        (parsed as Record<string, unknown>)[key] = value;
      }
    }
    return parsed as ForecastAssumptions;
  }, [inputs, period]);

  // Live recompute, debounced — the backend does the math (one source of truth).
  useEffect(() => {
    const assumptions = buildAssumptions();
    if (!assumptions) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      computeForecast(ticker, assumptions)
        .then((result) => {
          setPreview(result);
          setError(null);
        })
        .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    }, 400);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [buildAssumptions, ticker]);

  const handleSave = async () => {
    const assumptions = buildAssumptions();
    if (!assumptions) return;
    setSaving(true);
    try {
      await saveForecast(ticker, assumptions, label.trim() || null);
      setLabel("");
      setSaved(await listForecasts(ticker));
      onSaved(); // dossier picks up the new forward C/Z
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  if (error && !inputs) return <div className="error-box">{error}</div>;
  if (!inputs) return <p className="empty-state">Ładowanie założeń…</p>;

  const forward = preview?.result.forward;
  const pnl = preview?.result.pnl;
  const yoy = preview?.result.yoy;
  const median = dossier.pe_history.median;
  const discount =
    forward?.pe != null && median != null && median > 0
      ? Math.round((1 - forward.pe / median) * 100)
      : null;

  return (
    <div>
      {error && <div className="error-box">{error}</div>}
      <div className="forecast-grid">
        <div className="card">
          <div className="spread" style={{ marginBottom: 10 }}>
            <span style={{ fontWeight: 500, fontSize: 13 }}>Założenia</span>
            <span className="row">
              <label className="small muted">Kwartał</label>
              <input
                value={period}
                onChange={(e) => setPeriod(e.target.value.toUpperCase())}
                style={{ width: 90, textAlign: "right" }}
              />
            </span>
          </div>
          {FIELDS.map(({ key, label: fieldLabel, hint }) => (
            <div
              className="spread"
              key={key}
              style={{ padding: "4px 0", fontSize: 13 }}
            >
              <label className="secondary">
                {fieldLabel} <span className="small muted">· {hint}</span>
              </label>
              <input
                value={inputs[key]}
                inputMode="decimal"
                onChange={(e) =>
                  setInputs((current) =>
                    current ? { ...current, [key]: e.target.value } : current,
                  )
                }
                style={{ width: 110, textAlign: "right" }}
              />
            </div>
          ))}
          <div className="command-row forecast-actions">
            <button
              className="btn"
              onClick={() => {
                if (defaults) {
                  setInputs(toStrings(defaults));
                  setPeriod(defaults.period);
                }
              }}
            >
              <IconRestore size={13} /> Przywróć domyślne
            </button>
            <input
              placeholder="nazwa scenariusza"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              style={{ width: 150 }}
            />
            <button className="btn accent" onClick={handleSave} disabled={saving}>
              <IconDeviceFloppy size={13} /> Zapisz
            </button>
          </div>
        </div>

        <div className="metric-card" style={{ padding: "12px 16px" }}>
          <p className="label">Wynik prognozy {preview ? `· ${preview.result.period}` : ""}</p>
          {!preview ? (
            <p className="small muted" style={{ marginTop: 8 }}>
              Uzupełnij założenia, wynik przeliczy się automatycznie.
            </p>
          ) : (
            <table style={{ width: "100%", fontSize: 13, marginTop: 6 }}>
              <tbody>
                <tr>
                  <td className="secondary" style={{ padding: "3px 0" }}>Zysk netto</td>
                  <td style={{ textAlign: "right", fontWeight: 500 }}>
                    {fmtTysAsMln(pnl?.net_profit)}
                  </td>
                </tr>
                <tr>
                  <td className="secondary" style={{ padding: "3px 0" }}>
                    vs {yoy?.period ?? "rok wcześniej"}
                  </td>
                  <td
                    className={signClass(yoy?.net_profit_change_pct)}
                    style={{ textAlign: "right" }}
                  >
                    {fmtPct(yoy?.net_profit_change_pct, { signed: true })}
                  </td>
                </tr>
                <tr>
                  <td className="secondary" style={{ padding: "3px 0" }}>EBITDA</td>
                  <td style={{ textAlign: "right" }}>{fmtTysAsMln(pnl?.ebitda)}</td>
                </tr>
                <tr>
                  <td className="secondary" style={{ padding: "3px 0" }}>EPS (TTM + prognoza)</td>
                  <td style={{ textAlign: "right" }}>
                    {forward?.eps != null ? `${fmtNumber(forward.eps, 2)} zł` : "—"}
                  </td>
                </tr>
                <tr>
                  <td className="secondary" style={{ padding: "3px 0" }}>C/Z forward</td>
                  <td style={{ textAlign: "right", fontWeight: 500 }} className="pos">
                    {fmtNumber(forward?.pe)}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
          {discount != null && (
            <p className={`small ${discount > 0 ? "pos" : "warn"}`} style={{ marginTop: 8 }}>
              {discount > 0
                ? `${discount}% poniżej własnej mediany C/Z (${fmtNumber(median)})`
                : `powyżej własnej mediany C/Z (${fmtNumber(median)})`}
            </p>
          )}
        </div>
      </div>

      {saved.length > 0 && (
        <>
          <p className="section-label">Zapisane scenariusze</p>
          <div className="table-scroll">
            <table className="table saved-forecasts">
              <thead>
                <tr>
                  <th>Nazwa</th>
                  <th>Kwartał</th>
                  <th>Zysk netto</th>
                  <th>C/Z fwd</th>
                  <th>Zapisano</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {saved.map((scenario) => (
                  <tr key={scenario.id}>
                    <td>{scenario.label ?? "bez nazwy"}</td>
                    <td>{scenario.result.period}</td>
                    <td>{fmtTysAsMln(scenario.result.pnl.net_profit)}</td>
                    <td>{fmtNumber(scenario.result.forward.pe)}</td>
                    <td className="secondary">{fmtDate(scenario.created_at)}</td>
                    <td>
                      <button
                        className="btn compact"
                        onClick={() => {
                          setInputs(toStrings(scenario.assumptions));
                          setPeriod(scenario.assumptions.period);
                        }}
                      >
                        Wczytaj
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
