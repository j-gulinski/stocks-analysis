/**
 * pl-PL formatting helpers. Backend sends raw numbers (statements in tys. PLN,
 * prices in PLN, market cap in PLN) — every display conversion lives here.
 */

const plNumber = (digits: number) =>
  new Intl.NumberFormat("pl-PL", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export function fmtNumber(value: number | null | undefined, digits = 1): string {
  return value == null ? "—" : plNumber(digits).format(value);
}

/** Price in PLN: 24.5 → "24,50 zł". */
export function fmtPln(value: number | null | undefined): string {
  return value == null ? "—" : `${plNumber(2).format(value)} zł`;
}

/** Thousands of PLN (statement units): 26892 → "26 892 tys. zł". */
export function fmtTys(value: number | null | undefined): string {
  return value == null ? "—" : `${plNumber(0).format(value)} tys. zł`;
}

/** Thousands of PLN shown in millions: 26892 → "26,9 mln zł". */
export function fmtTysAsMln(value: number | null | undefined): string {
  return value == null ? "—" : `${plNumber(1).format(value / 1000)} mln zł`;
}

/** Full PLN (market cap): 505e6 → "505 mln zł", 1.17e9 → "1,17 mld zł". */
export function fmtMcap(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e9) return `${plNumber(2).format(value / 1e9)} mld zł`;
  return `${plNumber(0).format(value / 1e6)} mln zł`;
}

export function fmtPct(
  value: number | null | undefined,
  { signed = false, digits = 1 }: { signed?: boolean; digits?: number } = {},
): string {
  if (value == null) return "—";
  const formatted = `${plNumber(digits).format(value)}%`;
  return signed && value > 0 ? `+${formatted}` : formatted;
}

export function signClass(value: number | null | undefined): string {
  if (value == null) return "muted";
  return value > 0 ? "pos" : value < 0 ? "neg" : "secondary";
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pl-PL");
}

/** Freshness: "dziś 08:12" / "wczoraj" / "5 dni" / "—". */
export function relativeDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso);
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round(
    (startOfDay(now).getTime() - startOfDay(then).getTime()) / 86_400_000,
  );
  if (days <= 0)
    return `dziś ${then.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}`;
  if (days === 1) return "wczoraj";
  return `${days} dni`;
}

export function staleDays(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

/** Parse user input with Polish decimal comma: "12 345,6" → 12345.6. */
export function parseNum(raw: string): number | null {
  const cleaned = raw.replace(/[\s ]/g, "").replace(",", ".");
  if (cleaned === "" || cleaned === "-") return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}
