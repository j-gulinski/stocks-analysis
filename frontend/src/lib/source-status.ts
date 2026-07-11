/** Keep source failures actionable without hiding the raw status in storage. */
export function friendlySourceStatus(value: string): string {
  if (value.includes("HTTP 500") || value.includes("Giving up on")) {
    return "GPW chwilowo niedostępne (HTTP 500) · watermark zachowany · spróbuj później";
  }
  if (value.includes("network error")) {
    return "GPW chwilowo niedostępne · błąd sieci · watermark zachowany · spróbuj później";
  }
  if (value.startsWith("list_page_error:")) {
    return "Lista GPW niepełna · watermark zachowany · spróbuj później";
  }
  if (value.startsWith("detail_error:")) {
    return "Lista GPW pobrana, ale szczegóły raportu wymagają ponowienia";
  }
  return value;
}
