"""
Scraper rachunku zysków i strat z biznesradar.pl.

Strona: https://www.biznesradar.pl/raporty-finansowe-rachunek-zyskow-i-strat/{TICKER}
Nie wymaga logowania. Parser napisany defensywnie — struktura tabeli
(class "report-table") może się zmieniać, więc kod szuka po kilku
wariantach i zwraca surowe nagłówki + wiersze.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.biznesradar.pl/raporty-finansowe-rachunek-zyskow-i-strat/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


class BiznesRadarError(Exception):
    pass


def _clean_number(text: str) -> float | None:
    """'12 345' / '1,23' / '-5 000' -> float; zwraca None gdy brak liczby."""
    t = text.strip().replace("\xa0", " ")
    t = re.sub(r"\s+", "", t).replace(",", ".")
    # usuń dopiski typu r/r, %, strzałki
    m = re.match(r"^(-?\d+(?:\.\d+)?)", t)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def fetch_income_statement(ticker: str, quarterly: bool = True) -> dict:
    """
    Pobiera rachunek zysków i strat dla tickera (np. 'MBR', 'MOBRUK').
    quarterly=True -> dane kwartalne (domyślny widok), False -> ?type=Y (roczne).
    """
    ticker = ticker.strip().upper()
    url = BASE_URL + ticker
    if not quarterly:
        url += ",Y"

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    if resp.status_code == 404:
        raise BiznesRadarError(f"Nie znaleziono spółki '{ticker}' na BiznesRadar.")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table", class_="report-table")
    if table is None:
        # fallback: pierwsza duża tabela na stronie
        table = max(soup.find_all("table"), key=lambda t: len(t.find_all("tr")), default=None)
    if table is None:
        raise BiznesRadarError("Nie znaleziono tabeli z raportem na stronie.")

    # --- nagłówki okresów -------------------------------------------------
    periods: list[str] = []
    header_row = table.find("tr")
    if header_row:
        for th in header_row.find_all(["th", "td"])[1:]:
            label = th.get_text(" ", strip=True)
            if label:
                periods.append(label)

    # --- wiersze pozycji ---------------------------------------------------
    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        name = cells[0].get_text(" ", strip=True)
        if not name:
            continue
        field = tr.get("data-field") or ""
        values = []
        for td in cells[1 : len(periods) + 1]:
            # BiznesRadar trzyma wartość w <span class="value"> (a zmiany r/r w osobnych spanach)
            value_span = td.find("span", class_="value")
            raw = (
                value_span.get_text(" ", strip=True)
                if value_span
                else td.get_text(" ", strip=True)
            )
            values.append({"raw": raw, "number": _clean_number(raw)})
        rows.append({"name": name, "field": field, "values": values})

    # --- nazwa spółki ------------------------------------------------------
    name_el = soup.find("h1") or soup.find("h2")
    company = name_el.get_text(" ", strip=True) if name_el else ticker

    return {
        "ticker": ticker,
        "company": company,
        "source_url": url,
        "periods": periods,
        "rows": rows,
    }
