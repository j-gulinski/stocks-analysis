"""BiznesRadar page parsers: fetch-and-parse only, no DB, no business logic.

Every financial page on BiznesRadar shares one structure — a `table.report-table`
with period columns and one row per statement line — so a single generic parser
covers income statement, balance sheet, cash flow and both indicator pages.

Parsers are defensive: unknown columns are skipped, missing cells become None,
and nothing here guesses meaning (that lives in services/fields.py). If the
site's markup changes, fixtures in tests/fixtures catch it and this is the
only module to fix.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.scrapers import http as polite_http

BASE_URL = "https://www.biznesradar.pl"

# Production finding (CBF): the bare statement URL serves the ANNUAL view for
# at least some companies — quarterly must be requested explicitly with ',Q'
# (annual with ',Y'). Never rely on BiznesRadar's default view.
PAGE_PATHS: dict[str, str] = {
    "profile": "/notowania/{ticker}",
    "income_q": "/raporty-finansowe-rachunek-zyskow-i-strat/{ticker},Q",
    "income_y": "/raporty-finansowe-rachunek-zyskow-i-strat/{ticker},Y",
    "balance_q": "/raporty-finansowe-bilans/{ticker},Q",
    "cashflow_q": "/raporty-finansowe-przeplywy-pieniezne/{ticker},Q",
    "indicators_value": "/wskazniki-wartosci-rynkowej/{ticker}",
    "indicators_profitability": "/wskazniki-rentownosci/{ticker}",
    "dividends": "/dywidenda/{ticker}",
    "forecasts": "/prognozy/{ticker}",
    # Archiwum notowań — price-history source on a domain we already fetch
    # politely. robots.txt ALLOWS this first page and DISALLOWS the paginated
    # views (`Disallow: /notowania-historyczne/*,*`) — so the app only ever
    # requests page 1 (~50 most recent sessions). Never append `,2`, `,3`…
    "price_history": "/notowania-historyczne/{ticker}",
}


def page_url(kind: str, ticker: str) -> str:
    return BASE_URL + PAGE_PATHS[kind].format(ticker=ticker.upper())


class ParseError(Exception):
    """Expected markup not found — fixture tests should catch this early."""


@dataclass
class ReportRow:
    field_code: str
    label: str
    values: list[float | None]


@dataclass
class ReportTable:
    freq: str  # Q | Y
    periods: list[str] = field(default_factory=list)  # normalized, e.g. 2025Q1
    rows: list[ReportRow] = field(default_factory=list)


@dataclass
class CompanyProfile:
    name: str | None = None
    shares_outstanding: int | None = None
    sector: str | None = None
    market: str | None = None
    price: float | None = None  # current quote — price source of last resort
    slug: str | None = None  # BR canonical company slug (SNT -> SYNEKTIK)
    # Reported by BiznesRadar in the profile info box. The REPORTED market cap
    # is authoritative for size classification — deriving it as price×shares
    # silently understates it whenever the share count or stored price is
    # stale/misparsed (production: a >1 mld PLN company scored "small").
    market_cap: float | None = None  # PLN
    enterprise_value: float | None = None  # PLN


@dataclass
class PriceBar:
    """One daily close bar from BiznesRadar price history."""
    day: date
    close: float
    volume: int | None = None


@dataclass
class DividendEntry:
    year: int
    dps: float | None
    yield_pct: float | None


@dataclass
class PremiumMarketData:
    """Advanced/premium nodes exposed by authenticated BiznesRadar pages."""

    forecast_consensus: dict = field(default_factory=dict)
    advanced_metrics: dict = field(default_factory=dict)
    dividend_coverage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "forecast_consensus": self.forecast_consensus,
            "advanced_metrics": self.advanced_metrics,
            "dividend_coverage": self.dividend_coverage,
        }


@dataclass(frozen=True)
class MarketCandidate:
    """One row from BiznesRadar's market-wide financial rating table.

    This is discovery evidence, not our strategy score.  Keeping the source
    fields verbatim lets the research layer explain why a ticker surfaced
    without pretending the BR rating is a Malik/OBS recommendation.
    """

    ticker: str
    name: str | None
    report_period: str
    rating: str | None
    rating_value: float | None
    piotroski_f_score: int | None


# --------------------------------------------------------------- primitives

_SPACE_CHARS = "\u00a0\u2009\u202f "  # nbsp, thin, narrow-nbsp, regular (escaped: editor-proof)
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?")
_QUARTER_RE = re.compile(r"(\d{4})\s*/?\s*Q([1-4])")
_DATE_RE = re.compile(r"(\d{4})-(\d{2})(?:-\d{2})?")  # 2025-03-31 or 2025-03
_YEAR_RE = re.compile(r"^(\d{4})$")


def parse_number(raw: str | None) -> float | None:
    """'12 345' → 12345.0, '1,23%' → 1.23, '—'/'' → None.

    Polish formatting: spaces (incl. nbsp) group thousands, comma is the
    decimal separator. Trailing junk (%, r/r arrows) is ignored.
    """
    if raw is None:
        return None
    text = raw.strip()
    for ch in _SPACE_CHARS:
        text = text.replace(ch, "")
    text = text.replace(",", ".")
    match = _NUMBER_RE.match(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:  # pragma: no cover — regex guarantees a float
        return None


def normalize_period(raw: str, freq: str) -> str | None:
    """Normalize a period header cell; None = not a period column.

    Accepted forms (production shows BiznesRadar mixes them per page):
    - freq=Q: '2025/Q1', '2025 Q1'  → '2025Q1'
              '2025-03-31', '2025-03' (report as-of dates) → '2025Q1'
    - freq=Y: '2024' → '2024'; '2024-12-31' → '2024'
    """
    text = raw.strip()
    if not text or "r/r" in text.lower():
        return None
    if freq == "Q":
        match = _QUARTER_RE.search(text)
        if match:
            return f"{match.group(1)}Q{match.group(2)}"
        date_match = _DATE_RE.search(text)
        if date_match:
            year, month = int(date_match.group(1)), int(date_match.group(2))
            if 1 <= month <= 12:
                return f"{year}Q{(month + 2) // 3}"
        return None
    match = _YEAR_RE.match(text)
    if match:
        return match.group(1)
    # Real annual headers look like "2018 (paź 18)"; the trailing "O4K (mar 26)"
    # TTM aggregate has no leading year and is correctly skipped.
    match = re.match(r"\s*((?:19|20)\d{2})\b", text)
    if match:
        return match.group(1)
    date_match = _DATE_RE.search(text)
    return date_match.group(1) if date_match else None


def _slugify(label: str) -> str:
    """Stable ascii code for rows without a data-field attribute."""
    folded = label.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))
    return re.sub(r"[^a-z0-9]+", "_", folded).strip("_")[:80]


def _norm_label(label: str) -> str:
    folded = label.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))
    folded = re.sub(r"\s*/\s*", "/", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _year_from_header(raw: str) -> str | None:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", raw)
    return match.group(1) if match else None


def _metric_from_consensus_label(label: str) -> str | None:
    normalized = _norm_label(label)
    if "marz" in normalized or "rentownosc" in normalized:
        return None
    if "ebitda" in normalized:
        return "ebitda"
    if "zysk netto" in normalized or "net income" in normalized:
        return "net_income"
    if "przychod" in normalized or "revenue" in normalized:
        return "revenue"
    return None


def _advanced_metric_from_label(label: str) -> str | None:
    normalized = _norm_label(label)
    if "roic" in normalized or "zainwestowanego kapitalu" in normalized:
        return "roic"
    if normalized in {"fcf", "free cash flow"} or "wolne przeplywy" in normalized:
        return "fcf"
    if normalized == "ev" or "enterprise value" in normalized:
        return "enterprise_value"
    return None


def parse_premium_market_data(html: str) -> PremiumMarketData:
    """Extract premium/advanced nodes from any fetched BR page."""
    soup = BeautifulSoup(html, "html.parser")
    result = PremiumMarketData()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        table_text = _norm_label(table.get_text(" ", strip=True))
        header_cells = rows[0].find_all(["th", "td"])
        header_meta: dict[int, tuple[str | None, bool]] = {}
        scale = 1000.0 if "mln zl" in table_text else 1.0
        for idx, cell in enumerate(header_cells):
            header = cell.get_text(" ", strip=True)
            normalized_header = _norm_label(header)
            header_meta[idx] = (
                _year_from_header(header),
                "konsensus" in normalized_header or "forecast" in normalized_header,
            )
        has_consensus_year_flags = any(year and flag for year, flag in header_meta.values())
        looks_consensus = any(word in table_text for word in ("konsensus", "prognoz", "forecast"))

        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label_idx = 0
            if not cells[0].get_text(" ", strip=True) and len(cells) > 1:
                label_idx = 1
            elif len(cells) > 1 and "name" in (cells[1].get("class") or []):
                label_idx = 1
            label = cells[label_idx].get_text(" ", strip=True)
            metric = _metric_from_consensus_label(label) if looks_consensus else None
            if metric:
                for idx, cell in enumerate(cells):
                    if idx <= label_idx:
                        continue
                    year, is_consensus = header_meta.get(idx, (None, False))
                    if year is None or (has_consensus_year_flags and not is_consensus):
                        continue
                    value = parse_number(cell.get_text(" ", strip=True))
                    if value is None:
                        continue
                    result.forecast_consensus.setdefault(year, {})[metric] = {
                        "value": value * scale,
                        "unit": "tys. PLN",
                        "source": "biznesradar_premium_consensus",
                    }

            advanced = _advanced_metric_from_label(label)
            if advanced:
                raw = cells[1].get_text(" ", strip=True)
                value = _parse_money(raw) if advanced == "enterprise_value" else parse_number(raw)
                if value is not None:
                    result.advanced_metrics[advanced] = {
                        "value": value,
                        "unit": "PLN" if advanced == "enterprise_value" else None,
                        "source": "biznesradar_premium",
                    }

            normalized = _norm_label(label)
            if "pokry" in normalized and "dywid" in normalized and "fcf" in normalized:
                value = parse_number(cells[1].get_text(" ", strip=True))
                if value is not None:
                    result.dividend_coverage = {
                        "fcf_coverage_ratio": value,
                        "status": "covered" if value >= 1 else "not_covered",
                        "source": "biznesradar_premium",
                    }

    return result


# -------------------------------------------------------------- forecasts
#
# /prognozy/{slug} — VERIFIED live-DOM 2026-07-09 and live HTTP 2026-07-11.
# The table structure is public, but consensus values are blank anonymously
# and populated in an authenticated Premium session. Parsing remains the same;
# collection must label whether Premium authentication was available.
#
# Structure: <div id="profile-forecast"> containing an <h3>, a div.tools
# (JS-only view toggles, ignored) and a single
# <table class="qTableFull contentList"> with one <tbody>:
#   header tr (th): [blank][ "dane w mln zł" ][ <strong>LABEL</strong> note ]...
#     columns observed: 2025 "raport", O4K "raport (mar 26)*" (TTM aggregate
#     of the last 4 quarters), 2026/2027/2028 "konsensus"
#   data tr (td): [blank][td.name METRIC][value]...[value]
#     metric rows observed: Przychody ze sprzedaży, EBITDA, Zysk z
#     działalności operacyjnej, Zysk netto, Marża EBITDA, Rentowność
#     operacyjna, Rentowność netto, Nakłady inwestycyjne, Amortyzacja,
#     Cena / Zysk (C/Z).
# Consensus columns are frequently empty/"-" (BR only counts analyst
# forecasts younger than 6 months) — every cell here is optional.

@dataclass
class ForecastColumn:
    label: str  # raw column header, e.g. "2025", "O4K", "2026"
    kind: str  # "raport" | "raport_ttm" (O4K) | "konsensus"
    note: str | None = None  # e.g. "raport", "raport (mar 26)*", "konsensus"


@dataclass
class ForecastRow:
    metric: str | None  # canonical code (see _FORECAST_METRIC_LABELS), None = unmapped
    label: str  # raw BR row label, always kept (mirrors the indicator parser)
    values: list[float | None]  # aligned with ForecastTable.columns


@dataclass
class ForecastTable:
    columns: list[ForecastColumn] = field(default_factory=list)
    rows: list[ForecastRow] = field(default_factory=list)
    # Rows whose label didn't match _FORECAST_METRIC_LABELS — surfaced instead
    # of silently dropped, same discipline as _upsert_indicators' `unmapped`.
    unmapped_labels: list[str] = field(default_factory=list)

    def values_by_metric(self) -> dict[str, dict[str, float | None]]:
        """metric code -> {column label -> value}; unmapped rows excluded."""
        return {
            row.metric: {
                column.label: value for column, value in zip(self.columns, row.values)
            }
            for row in self.rows
            if row.metric is not None
        }


# Local label -> canonical metric code map, same pattern as
# _metric_from_consensus_label/_advanced_metric_from_label above: this page's
# rows are not income-statement lines routed through services/fields.py, they
# are a page-specific mix of money/percent/ratio rows, so the mapping lives
# here (markup-adjacent), not in fields.py.
_FORECAST_METRIC_LABELS: dict[str, str] = {
    "przychody ze sprzedazy": "revenue",
    "ebitda": "ebitda",
    "zysk z dzialalnosci operacyjnej": "operating_profit",
    "zysk netto": "net_income",
    "marza ebitda": "ebitda_margin_pct",
    "rentownosc operacyjna": "operating_margin_pct",
    "rentownosc netto": "net_margin_pct",
    "naklady inwestycyjne": "capex",
    "amortyzacja": "depreciation",
    "cena/zysk (c/z)": "pe",
}

# Rows carrying money values on this page (BiznesRadar states them in mln zł —
# see the ×1000 conversion in parse_forecasts). Percent (*_pct) and pe rows
# are plain numbers, no scale conversion.
_FORECAST_MONEY_METRICS = {
    "revenue", "ebitda", "operating_profit", "net_income", "capex", "depreciation",
}


def _forecast_metric_from_label(label: str) -> str | None:
    return _FORECAST_METRIC_LABELS.get(_norm_label(label))


def _forecast_column_kind(label: str, note: str) -> str:
    if label.strip().upper() == "O4K":
        return "raport_ttm"
    if "konsensus" in note.lower():
        return "konsensus"
    return "raport"


def _cell_label_and_note(cell) -> tuple[str, str]:
    """Split a header cell into its `<strong>` label and the remaining text.

    Walks direct children instead of slicing `full_text[len(label):]` — more
    robust to nbsp/whitespace variance between the label and its note than a
    prefix cut would be.
    """
    strong = cell.find("strong")
    if strong is None:
        return cell.get_text(" ", strip=True), ""
    label = strong.get_text(" ", strip=True)
    remainder_parts = []
    for content in cell.contents:
        if content is strong:
            continue
        text = content.get_text(" ", strip=True) if hasattr(content, "get_text") else str(content).strip()
        if text:
            remainder_parts.append(text)
    return label, " ".join(remainder_parts).strip()


def _forecast_label_cell_index(cells) -> int:
    """Row-label cell index — the layout leads with a blank `<td>`, then
    `<td class="name">`, same defensive shape as parse_premium_market_data."""
    if not cells[0].get_text(" ", strip=True) and len(cells) > 1:
        return 1
    if len(cells) > 1 and "name" in (cells[1].get("class") or []):
        return 1
    return 0


def parse_forecasts(html: str) -> ForecastTable:
    """Parse the /prognozy/{slug} analyst-forecast table (public page)."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", id="profile-forecast")
    table = None
    if container is not None:
        table = container.find(
            "table", class_=lambda c: c and "qTableFull" in c.split()
        )
    if table is None:
        # Fallback: any qTableFull table on the page, else the largest table —
        # survives the container id being renamed (mirrors parse_report_table).
        table = soup.find("table", class_=lambda c: c and "qTableFull" in c.split())
    if table is None:
        tables = soup.find_all("table")
        table = max(tables, key=lambda t: len(t.find_all("tr")), default=None)
    if table is None:
        raise ParseError("No forecast table found on page.")

    rows_container = table.find("tbody") or table
    all_rows = rows_container.find_all("tr", recursive=False) or table.find_all("tr")
    if not all_rows:
        raise ParseError("Forecast table has no rows.")

    header_cells = all_rows[0].find_all(["th", "td"])
    if len(header_cells) < 3:
        raise ParseError("Forecast header row too short.")

    columns: list[ForecastColumn] = []
    for cell in header_cells[2:]:  # skip [blank][ "dane w mln zł" ]
        label, note = _cell_label_and_note(cell)
        if not label:
            continue
        columns.append(ForecastColumn(label=label, kind=_forecast_column_kind(label, note), note=note or None))

    rows: list[ForecastRow] = []
    unmapped_labels: list[str] = []
    for tr in all_rows[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label_idx = _forecast_label_cell_index(cells)
        label = cells[label_idx].get_text(" ", strip=True)
        if not label:
            continue
        metric = _forecast_metric_from_label(label)
        value_cells = cells[label_idx + 1 :]
        values: list[float | None] = []
        for column_index in range(len(columns)):
            if column_index >= len(value_cells):
                values.append(None)
                continue
            raw = value_cells[column_index].get_text(" ", strip=True)
            value = parse_number(raw)
            if value is not None and metric in _FORECAST_MONEY_METRICS:
                # BiznesRadar states this page's money rows in mln zł; the DB
                # convention (services/fields.py, ReportValue) is tys. PLN —
                # ×1000 here converts once, at the parser boundary, so every
                # downstream consumer sees the same unit as the statement
                # tables (LOUD on purpose: this is a real unit change, not a
                # formatting tweak). round(): mln zł source has at most ~1-2
                # decimal digits, so the extra precision is pure IEEE754 noise
                # (e.g. 64.1 * 1000 == 64099.99999999999) — round it away
                # instead of writing it to the DB.
                value = round(value * 1000.0, 3)
            values.append(value)
        rows.append(ForecastRow(metric=metric, label=label, values=values))
        if metric is None:
            unmapped_labels.append(label)

    return ForecastTable(columns=columns, rows=rows, unmapped_labels=unmapped_labels)


# ---------------------------------------------------------- market discovery

_CANDIDATE_NAME_RE = re.compile(r"^([A-Z0-9]{2,12})(?:\s*\(([^)]+)\))?$")
_CANDIDATE_PERIOD_RE = re.compile(r"\b((?:19|20)\d{2})\s*/\s*Q([1-4])\b")
_CANDIDATE_RATING_RE = re.compile(
    r"\b(AAA|AA|A|BBB|BB|B|CCC|CC|C|D)([+-]?)\s*"
    r"\(\s*(-?[\d\s]+(?:[,.]\d+)?)\s*\)"
)


def parse_market_rating(html: str) -> list[MarketCandidate]:
    """Parse the single-page GPW rating universe used for candidate discovery.

    The parser identifies rows by their profile link + report period + rating
    pattern instead of table position.  That survives extra navigation tables
    and missing F-scores.  Duplicate tickers keep the first (highest) row.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[MarketCandidate] = []
    seen: set[str] = set()
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        profile_link = cells[0].find("a")
        profile_text = (
            profile_link.get_text(" ", strip=True)
            if profile_link is not None
            else cells[0].get_text(" ", strip=True)
        )
        profile_match = _CANDIDATE_NAME_RE.match(profile_text.upper())
        row_text = row.get_text(" ", strip=True)
        period_match = _CANDIDATE_PERIOD_RE.search(row_text)
        rating_match = _CANDIDATE_RATING_RE.search(row_text)
        if profile_match is None or period_match is None or rating_match is None:
            continue

        ticker = profile_match.group(1)
        if ticker in seen:
            continue
        rating_value = parse_number(rating_match.group(3))
        rating = rating_match.group(1) + rating_match.group(2)

        # BR documents this final integer as Piotroski F-Score.  It is absent
        # for some company types, which remains None rather than becoming 0.
        trailing_text = row_text[rating_match.end() :].strip()
        f_score_match = re.search(r"\b([0-9])\b", trailing_text)
        candidates.append(
            MarketCandidate(
                ticker=ticker,
                name=(profile_match.group(2) or "").strip() or None,
                report_period=f"{period_match.group(1)}Q{period_match.group(2)}",
                rating=rating,
                rating_value=rating_value,
                piotroski_f_score=(
                    int(f_score_match.group(1)) if f_score_match is not None else None
                ),
            )
        )
        seen.add(ticker)
    if not candidates:
        raise ParseError("No market-rating candidates found on page.")
    return candidates


# ------------------------------------------------------------ report tables

def parse_report_table(html: str, freq: str) -> ReportTable:
    """Generic parser for every `report-table` page (statements + indicators)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="report-table")
    if table is None:
        # Fallback: the largest table on the page — survives class renames.
        tables = soup.find_all("table")
        table = max(tables, key=lambda t: len(t.find_all("tr")), default=None)
    if table is None:
        raise ParseError("No report table found on page.")

    all_rows = table.find_all("tr")
    if not all_rows:
        raise ParseError("Report table has no rows.")

    # Header detection: the period row is NOT always the first <tr> (production
    # finding — statement pages carry controls/date rows above it). Scan the
    # first few rows and take the one with the most period-like cells.
    best_row_index = 0
    best_matches: list[tuple[int, str]] = []
    for row_index, tr in enumerate(all_rows[: min(5, len(all_rows))]):
        all_cells = tr.find_all(["th", "td"])
        first_label = all_cells[0].get_text(" ", strip=True).lower() if all_cells else ""
        if first_label.startswith("data publikacji"):
            continue  # publication dates masqueraded as periods in production
        cells = all_cells[1:]
        matches = []
        seen_periods: set[str] = set()
        for index, cell in enumerate(cells):
            period = normalize_period(cell.get_text(" ", strip=True), freq)
            # First occurrence wins: annual pages can repeat a period column
            # (e.g. '2026' + a '2026' TTM/estimate) — production crash source.
            if period is not None and period not in seen_periods:
                matches.append((index, period))
                seen_periods.add(period)
        if len(matches) > len(best_matches):
            best_row_index, best_matches = row_index, matches

    kept_column_indexes = [index for index, _ in best_matches]
    periods = [period for _, period in best_matches]

    result = ReportTable(freq=freq, periods=periods)
    for tr in all_rows[best_row_index + 1 :]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True)
        if not label:
            continue
        field_code = tr.get("data-field") or cells[0].get("data-field") or _slugify(label)

        value_cells = cells[1:]
        values: list[float | None] = []
        for column_index in kept_column_indexes:
            if column_index >= len(value_cells):
                values.append(None)
                continue
            cell = value_cells[column_index]
            # BiznesRadar wraps the actual value in <span class="value">;
            # sibling spans hold y/y changes we must not swallow.
            value_span = cell.find("span", class_="value")
            raw = (
                value_span.get_text(" ", strip=True)
                if value_span
                else cell.get_text(" ", strip=True)
            )
            values.append(parse_number(raw))
        result.rows.append(ReportRow(field_code=field_code, label=label, values=values))

    return result


# ----------------------------------------------------------------- profile

_DIGITS_GROUP = r"(\d[\d\s\u00a0\u2009]*)"
# `:?\s*` then a DIGIT immediately: "Liczba akcji: 8 529 129" matches, while
# "Liczba akcji w wolnym obrocie: \u2026" (free float \u2014 a SMALLER number) does not.
# The old permissive `[^\d]*` bridged right across such suffix words and could
# capture the free-float count \u2192 understated market cap \u2192 false "small cap".
_SHARES_PATTERNS = tuple(
    re.compile(label + r"\s*:?\s*" + _DIGITS_GROUP)
    for label in (
        r"Liczba akcji",
        r"Liczba wyemitowanych akcji",
        r"Akcje wszystkich emisji",
    )
)
_SECTOR_RE = re.compile(r"(?:Sektor|Bran\u017ca):?\s*([^\n|<>]{2,60})")
_SLUG_RE = re.compile(r"/notowania/([A-Z0-9_-]{2,40})")
_SCALE = {"tys": 1e3, "mln": 1e6, "mld": 1e9}


def _parse_money(raw: str | None) -> float | None:
    """Info-box money cell \u2192 PLN. Handles both the full-integer form and the
    scaled 'X,YZ mln/mld' form (a naive parse of '2,82 mld' would store 2.82
    PLN and re-create the small-cap bug from the other side)."""
    if raw is None:
        return None
    text = raw.strip()
    match = re.match(
        r"\s*(\d[\d\s\u00a0\u2009]*(?:[,.]\d+)?)\s*(mld|mln|tys)?", text, re.IGNORECASE
    )
    if not match:
        return None
    value = parse_number(match.group(1))
    if value is None:
        return None
    scale = _SCALE.get((match.group(2) or "").lower(), 1.0)
    return round(value * scale, 0)


def _adjacent_cell_text(soup, labels: set[str]) -> str | None:
    """Value cell next to a label cell (e.g. 'Bran\u017ca:' -> 'Biotechnologia')."""
    for cell in soup.find_all(["td", "th"]):
        label = cell.get_text(" ", strip=True).rstrip(":").lower()
        if label in labels:
            sibling = cell.find_next_sibling(["td", "th"])
            if sibling is not None:
                value = sibling.get_text(" ", strip=True)
                if value:
                    return value
    return None


def parse_profile(html: str, ticker: str) -> CompanyProfile:
    """Company header page: name, share count, sector, market. Best-effort.

    Production finding: the page <h1> can be a generic "Notowania {TICKER}",
    not the company name — so the name comes from a "NAME (TICKER)" pattern
    searched across <title>/<h1>/<h2> first.
    """
    soup = BeautifulSoup(html, "html.parser")
    profile = CompanyProfile()

    name_pattern = re.compile(
        r"([0-9A-Z\u0104\u0106\u0118\u0141\u0143\u00d3\u015a\u0179\u017b]"
        r"[^():\n]{1,60}?)\s*\(\s*" + re.escape(ticker.upper()) + r"\s*\)"
    )
    candidates: list[str] = []
    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))
    candidates.extend(
        tag.get_text(" ", strip=True) for tag in soup.find_all(["h1", "h2"], limit=8)
    )
    for candidate in candidates:
        match = name_pattern.search(candidate)
        if match:
            name = match.group(1).strip(" -\u2013\u00b7")
            # Titles read "Notowania SYNEKTIK SA (SNT)" \u2014 drop the page-type
            # prefix words, keep the company name.
            name = re.sub(
                r"^(?:(?:notowania|akcje|kurs|sp\u00f3\u0142ka|raporty finansowe|rachunek zysk\u00f3w i strat|bilans|przep\u0142ywy pieni\u0119\u017cne)\s+)+", "", name, flags=re.IGNORECASE
            )
            profile.name = name or None
            break
    else:
        # Some live profiles use the short exchange alias in h1
        # ("Notowania ABS (ASSECOBS)") and put the legal company name in h2.
        # Prefer the first non-generic heading instead of treating a generic h1
        # as proof that the page is nameless.
        for heading in soup.find_all(["h1", "h2"], limit=8):
            heading_text = heading.get_text(" ", strip=True)
            if not heading_text or heading_text.lower().startswith("notowania"):
                continue
            cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", heading_text).strip()
            if cleaned and cleaned.upper() != ticker.upper():
                profile.name = cleaned
                break

    text = soup.get_text(" ", strip=True)

    # Info-box facts, DOM-first (label cell → value cell), flat-text fallback.
    shares_cell = _adjacent_cell_text(soup, {"liczba akcji"})
    if shares_cell:
        shares = parse_number(shares_cell)
        if shares and shares >= 1000:  # a share count, not a stray percent
            profile.shares_outstanding = int(shares)
    if profile.shares_outstanding is None:
        for pattern in _SHARES_PATTERNS:
            shares_match = pattern.search(text)
            if shares_match:
                shares = parse_number(shares_match.group(1))
                if shares:
                    profile.shares_outstanding = int(shares)
                    break

    # Reported market cap / EV — authoritative for size classification.
    profile.market_cap = _parse_money(_adjacent_cell_text(soup, {"kapitalizacja"}))
    if profile.market_cap is None:
        mcap_match = re.search(
            r"Kapitalizacja\s*:?\s*([\d\s  ]+(?:[,.]\d+)?\s*(?:mld|mln|tys)?)",
            text,
            re.IGNORECASE,
        )
        if mcap_match:
            profile.market_cap = _parse_money(mcap_match.group(1))
    profile.enterprise_value = _parse_money(
        _adjacent_cell_text(soup, {"enterprise value", "ev"})
    )

    profile.sector = _adjacent_cell_text(soup, {"sektor", "bran\u017ca"})
    if profile.sector is None:
        sector_match = _SECTOR_RE.search(text)
        if sector_match:
            raw_sector = sector_match.group(1)
            # flat-text fallback bleeds into neighbouring cells — trim hard
            raw_sector = re.split(
                r"\s{2,}|Liczba|Kapitalizacja|ISIN|Enterprise", raw_sector
            )[0]
            profile.sector = raw_sector.strip().rstrip(",;") or None

    # Only trust an explicit market label: nav menus mention NewConnect on
    # Market: explicit label ("Rynek: X") or the live-page banner
    # ("GPW - Akcje - Notowania ciągłe"). Bare menu links must NOT match.
    lower = text.lower()
    if re.search(r"rynek:\s*newconnect", lower) or "newconnect - akcje" in lower:
        profile.market = "NewConnect"
    elif re.search(r"rynek:\s*(gpw|g\u0142\u00f3wny|glowny|podstawowy)", lower) or "gpw - akcje" in lower:
        profile.market = "GPW"

    # Canonical slug: BR redirects ticker URLs to /notowania/{SLUG} and DROPS
    # any ,Q/,Y suffix in the process — report URLs must use the slug.
    for link in soup.find_all("a", href=True):
        slug_match = _SLUG_RE.search(link["href"])
        if slug_match:
            profile.slug = slug_match.group(1)
            break

    # Current quote: schema.org microdata first (clean), then a text pattern.
    # Used as a last-resort price bar when history is unavailable; costs zero
    # extra requests because this page is fetched anyway.
    price_meta = soup.find("meta", attrs={"itemprop": "price"})
    if price_meta and price_meta.get("content"):
        profile.price = parse_number(price_meta["content"])
    if profile.price is None:
        price_match = re.search(r"Kurs[:\s]+([\d\s,\.]+)", text)
        if price_match:
            profile.price = parse_number(price_match.group(1))
    return profile


# --------------------------------------------------------------- dividends

def parse_dividends(html: str) -> list[DividendEntry]:
    """Dividend history table: one row per year with DPS and yield."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[DividendEntry] = []

    for table in soup.find_all("table"):
        header_text = table.find("tr").get_text(" ", strip=True).lower() if table.find("tr") else ""
        if "dywidend" not in header_text:
            continue
        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            year_match = re.search(r"\b(20\d{2}|19\d{2})\b", cells[0])
            if not year_match:
                continue
            dps = parse_number(cells[1]) if len(cells) > 1 else None
            yield_pct = next(
                (parse_number(c) for c in cells[1:] if "%" in c),
                None,
            )
            entries.append(
                DividendEntry(year=int(year_match.group(1)), dps=dps, yield_pct=yield_pct)
            )
        if entries:
            break  # first matching table is the dividend history

    return entries


# ---------------------------------------------------------- price history

_HISTORY_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")  # 12.05.2026


def parse_price_history(html: str) -> list[PriceBar]:
    """Archiwum notowań (page 1 ≈ 50 most recent sessions) → daily bars.

    Table shape (live 2026-07): Data | Otwarcie | Max | Min | Zamknięcie |
    Wolumen | Obrót, dates dd.mm.yyyy, Polish number formatting. The table is
    found by its header labels, not CSS class — resilient to skin changes.
    Returned bars are sorted oldest→newest (the page lists newest first).
    """
    soup = BeautifulSoup(html, "html.parser")

    target = None
    close_index = volume_index = None
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if header_row is None:
            continue
        headers = [
            c.get_text(" ", strip=True).lower()
            for c in header_row.find_all(["th", "td"])
        ]
        if not headers or "data" not in headers[0]:
            continue
        close_candidates = [i for i, h in enumerate(headers) if "zamkni" in h]
        if not close_candidates:
            continue
        target = table
        close_index = close_candidates[0]
        volume_index = next((i for i, h in enumerate(headers) if "wolumen" in h), None)
        break
    if target is None:
        raise ParseError("No price-history table found on page.")

    bars: list[PriceBar] = []
    for tr in target.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) <= close_index:
            continue
        date_match = _HISTORY_DATE_RE.search(cells[0])
        if not date_match:
            continue
        close = parse_number(cells[close_index])
        if close is None:
            continue
        day, month, year = (int(g) for g in date_match.groups())
        volume = None
        if volume_index is not None and volume_index < len(cells):
            raw_volume = parse_number(cells[volume_index])
            volume = int(raw_volume) if raw_volume is not None else None
        bars.append(PriceBar(day=date(year, month, day), close=close, volume=volume))

    bars.sort(key=lambda bar: bar.day)
    return bars


# ------------------------------------------------------------ premium login
#
# P1.9 (BiznesRadar premium session): a logged-in session unlocks longer
# report/price history than the anonymous pages parsed above.
#
# LOGIN MECHANICS — VERIFIED 2026-07-08 via live browser capture (see
# skills/scraper-doctor/SKILL.md "BiznesRadar — premium login"):
#   * There is NO server-rendered login page. `/logowanie` and `/login` (no
#     trailing slash) both 404. The header "Logowanie" link is
#     `<a href="javascript:void(0)" onclick="Dialogs.login()">` — the form is
#     built client-side in a JS modal, so it never appears in static HTML.
#   * The real endpoint is a fixed, documented POST to `{BASE}/login/`
#     (TRAILING SLASH), form-encoded: `email` + `password` (+ optional
#     `remember_me=1`). No CSRF token, no hidden inputs — nothing to scrape.
#   * POST /login/ answers with a redirect on BOTH success and failure, so its
#     body is not authoritative. Success is confirmed by re-fetching the
#     homepage and finding the logged-in-only marker `account-settings`
#     (Dialogs.accountSettings); the anonymous page carries `Dialogs.login`
#     instead. Secondary marker: GET /user-data/ returns a ~194 B script
#     anonymous vs ~1686 B logged in. There is NO logout href (logout is JS
#     too) — never key off logout links or password-field absence.
# BR_USERNAME is the account e-mail (email-shaped, verified).


class BrLoginError(Exception):
    pass


# Logged-in-only marker in the homepage HTML (verified 2026-07-08).
_LOGGED_IN_MARKER = "account-settings"
# Anonymous-only marker — present when BiznesRadar re-serves the logged-out
# homepage (i.e. the credentials were rejected), absent once logged in.
_ANON_MARKER = "Dialogs.login"


def _find_login_form(html: str):
    """Locate the BiznesRadar `<form action="/login/">` in a captured fragment.

    Used ONLY to validate the recorded fixture's shape (see
    extract_login_fields). login() never parses a form at runtime — the live
    site builds it client-side in a JS modal and POSTs to a fixed endpoint.
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"log(?:owanie|in)", re.IGNORECASE))
    if form is None:
        for candidate in soup.find_all("form"):
            if candidate.find("input", attrs={"type": "password"}):
                form = candidate
                break
    if form is None:
        raise BrLoginError("No BiznesRadar login form in the given HTML.")
    return form


def extract_login_fields(html: str) -> dict[str, str]:
    """Input `name -> type` map of the captured BiznesRadar login form.

    login() does NOT call this — the live login form is never in static HTML
    (JS modal) and the POST target is the fixed /login/ endpoint with a known
    {email, password} payload. This helper survives only so a test can assert
    the recorded fixture (tests/fixtures/br_login_live.html) still has the
    documented shape ({email, password, remember_me}); if BiznesRadar ever
    renames those inputs, re-record the fixture and the structural test flags
    the drift.
    """
    form = _find_login_form(html)
    fields_out: dict[str, str] = {}
    for input_tag in form.find_all("input"):
        name = input_tag.get("name")
        if name:
            fields_out[name] = input_tag.get("type", "text")
    return fields_out


def _looks_logged_in(html: str) -> bool:
    """Post-login success check (VERIFIED 2026-07-08).

    The logged-in BiznesRadar homepage embeds an `account-settings` control
    (Dialogs.accountSettings); the anonymous page does not. This single string
    is the authoritative marker — do NOT rely on logout links (logout is JS,
    no href) or on a login form being absent (there is no server-rendered form
    on either page).
    """
    return _LOGGED_IN_MARKER in html


class BrClient:
    """Thin session wrapper for a logged-in (premium) BiznesRadar session.

    All HTTP goes through app.scrapers.http.fetch so the same per-domain
    politeness/backoff policy applies to the login round-trip as to every other
    BiznesRadar request. The login recipe is fixed and documented (see the
    section banner above) — there is no login page to scrape.
    """

    # Fixed POST endpoint. The TRAILING SLASH is required — `/login` and
    # `/logowanie` both 404 (verified 2026-07-08).
    LOGIN_PATH = "login/"

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = polite_http.USER_AGENT
        self.logged_in = False

    def login(self, username: str, password: str) -> None:
        """Log in to BiznesRadar; raise BrLoginError on failure.

        `username` is the account e-mail. Flow: warm-up GET → POST credentials
        to /login/ (redirects followed) → re-fetch the homepage and confirm the
        `account-settings` marker, with GET /user-data/ payload size as a
        fallback check. Every hop goes through the polite fetcher.
        """
        # 1. Warm-up: load the homepage first (as a browser would before
        #    opening the login modal) so the session holds whatever anonymous
        #    cookies BiznesRadar hands out.
        try:
            polite_http.fetch(self.base_url, session=self.session)
        except polite_http.FetchError as exc:
            raise BrLoginError(
                f"Nie udało się otworzyć strony BiznesRadar przed logowaniem: {exc}"
            ) from exc

        # 2. POST the credentials to the fixed /login/ endpoint. BiznesRadar
        #    redirects on both success and failure; requests follows the
        #    redirect and this body is NOT authoritative (step 3 verifies).
        login_url = urljoin(self.base_url, self.LOGIN_PATH)
        try:
            polite_http.fetch(
                login_url,
                method="POST",
                data={"email": username, "password": password},
                session=self.session,
            )
        except polite_http.FetchError as exc:
            raise BrLoginError(
                f"Żądanie logowania do BiznesRadar nie powiodło się (sieć): {exc}"
            ) from exc

        # 3. Verify against the logged-in-only homepage marker.
        try:
            verify = polite_http.fetch(self.base_url, session=self.session)
        except polite_http.FetchError as exc:
            raise BrLoginError(
                f"Nie udało się zweryfikować logowania do BiznesRadar: {exc}"
            ) from exc
        if _looks_logged_in(verify.text):
            self.logged_in = True
            return

        # Fallback marker: /user-data/ grows from ~194 B (anon) to ~1686 B
        # (logged in). Guards against a stale anonymous homepage from the CDN.
        if self._user_data_confirms_login():
            self.logged_in = True
            return

        raise BrLoginError(self._login_failure_message(verify.text))

    def _user_data_confirms_login(self) -> bool:
        """Secondary logged-in check: GET /user-data/ payload > ~1 kB."""
        try:
            response = polite_http.fetch(
                urljoin(self.base_url, "user-data/"), session=self.session
            )
        except polite_http.FetchError:
            return False
        return len(response.text) > 1000

    @staticmethod
    def _login_failure_message(verify_html: str) -> str:
        """Turn a failed verification into a useful Polish diagnosis."""
        if _ANON_MARKER in verify_html or "Logowanie" in verify_html:
            # BiznesRadar re-served the anonymous homepage — creds rejected.
            return (
                "Logowanie do BiznesRadar nie powiodło się — po wysłaniu danych "
                "strona nadal jest anonimowa. Najczęstsza przyczyna: błędny "
                "BR_USERNAME (adres e-mail konta) lub BR_PASSWORD w backend/.env."
            )
        # Neither the logged-in nor the anonymous marker is present — the page
        # shape changed and the recipe needs re-verifying against the live site.
        return (
            "Logowanie do BiznesRadar zwróciło nierozpoznaną stronę — brak "
            "markera zalogowania ('account-settings') oraz markera strony "
            "anonimowej ('Dialogs.login'). Układ strony mógł się zmienić; "
            "zweryfikuj przepis (POST /login/, pola email/password, marker "
            "'account-settings') na żywej stronie."
        )
