import type { Dossier } from "@/lib/types";

export function hasDossierData(dossier: Dossier | null | undefined): boolean {
  if (!dossier) return false;
  return Boolean(
    dossier.quarters.length > 0 ||
      dossier.freshness.financials_scraped_at ||
      dossier.freshness.last_price_date ||
      dossier.ttm.price != null,
  );
}
