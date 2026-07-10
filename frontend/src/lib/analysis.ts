import type { AnalysisRun, Dossier } from "@/lib/types";

function recordField(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function numberField(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * A verified memo is current only when it was built from the same normalized
 * earnings basis as the dossier now on screen. Older results remain audit
 * history and must never silently replace a refreshed report.
 */
export function isCurrentVerifiedRun(run: AnalysisRun, dossier: Dossier): boolean {
  if (run.verification_status !== "pass") return false;
  const root = recordField(run.input_snapshot.dossier) ?? run.input_snapshot;
  const snapshotTtm = recordField(root.ttm);
  const snapshotQuality = recordField(root.result_quality);
  const snapshotPe = numberField(snapshotTtm?.valuation_pe);
  const currentPe = dossier.ttm.valuation_pe;
  const peMatches =
    snapshotPe == null || currentPe == null
      ? snapshotPe === currentPe
      : Math.abs(snapshotPe - currentPe) < 0.01;
  return snapshotQuality != null && peMatches;
}

export function findCurrentVerifiedRun(
  runs: AnalysisRun[] | null,
  dossier: Dossier,
): AnalysisRun | null {
  return runs?.find((run) => isCurrentVerifiedRun(run, dossier)) ?? null;
}
