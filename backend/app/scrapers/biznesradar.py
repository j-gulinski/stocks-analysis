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
        heading = soup.find("h1")
        if heading:
            heading_text = heading.get_text(" ", strip=True)
            # A generic listing header is worse than no name at all.
            if not heading_text.lower().startswith("notowania"):
                profile.name = re.sub(r"\s*\([^)]*\)\s*$", "", heading_text) or None

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
# report/price history than the anonymous pages parsed above. This section
# mirrors app/scrapers/portalanaliz.py's ForumClient/extract_login_fields
# shape 1:1 (LoginError -> BrLoginError, ForumClient -> BrClient).
#
# UNVERIFIED ASSUMPTION: unlike the phpBB login form (verified against a real
# PortalAnaliz page), BiznesRadar's real login page markup has never been
# fetched in this environment (egress to biznesradar.pl is proxy-blocked in
# the sandbox this was written in). Everything below — the login path, field
# names, and "did it work" check — is a best-effort guess based on common PHP
# login-form conventions, backed only by the SYNTHETIC fixture in
# tests/fixtures/br_login.html. Before trusting this in production:
#   1. run `python scripts/record_fixtures.py --login` (or equivalent) on a
#      machine that can reach biznesradar.pl while logged out, to capture the
#      real login page HTML;
#   2. replace tests/fixtures/br_login.html with the real recording (or add
#      it alongside) and fix extract_login_fields()/BrClient.LOGIN_PATH/the
#      payload field names/the success check below to match reality;
#   3. do one real login by hand (BR_USERNAME/BR_PASSWORD in backend/.env)
#      and confirm BrClient.login() succeeds and a premium page actually
#      differs from the anonymous one.
# This module only implements the plumbing; it does NOT claim the parser is
# correct against the real site yet.


class BrLoginError(Exception):
    pass


def _find_login_form(html: str):
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"log(?:owanie|in)", re.IGNORECASE))
    if form is None:
        for candidate in soup.find_all("form"):
            if candidate.find("input", attrs={"type": "password"}):
                form = candidate
                break
    if form is None:
        raise BrLoginError("Login form not found on BiznesRadar login page.")
    return form


def extract_login_fields(html: str) -> dict[str, str]:
    """Hidden inputs of the BiznesRadar login form.

    ASSUMPTION (see module banner above, UNVERIFIED against a real page):
    looks for a `<form>` whose `action` mentions "login"/"logowanie"; falls
    back to the first form containing a password input (works even if the
    action attribute is relative/absent). Collects every hidden input as a
    name -> value pair, exactly like portalanaliz.extract_login_fields does
    for phpBB's creation_time/form_token/sid triplet — BiznesRadar likely has
    an analogous CSRF-style token that must be echoed back unchanged.
    """
    form = _find_login_form(html)
    fields_out: dict[str, str] = {}
    for hidden in form.find_all("input", attrs={"type": "hidden"}):
        name = hidden.get("name")
        if name:
            fields_out[name] = hidden.get("value", "")
    return fields_out


def _login_payload_and_action(
    html: str, username: str, password: str
) -> tuple[dict[str, str], str | None]:
    """Build a payload from the real form names instead of hard-coding them."""
    form = _find_login_form(html)
    payload = extract_login_fields(html)

    user_input = form.find(
        "input",
        attrs={"type": re.compile(r"^(text|email)$", re.IGNORECASE)},
    )
    if user_input is None:
        user_input = form.find(
            "input",
            attrs={"name": re.compile(r"(login|user|email)", re.IGNORECASE)},
        )
    password_input = form.find("input", attrs={"type": "password"})

    user_name = user_input.get("name") if user_input else None
    password_name = password_input.get("name") if password_input else None
    payload[user_name or "login"] = username
    payload[password_name or "password"] = password
    return payload, form.get("action")


def _looks_logged_in(html: str) -> bool:
    """Best-effort post-login success check — ASSUMPTION, see module banner.

    Real markup unknown, so this checks for either signal: a logout
    link/control, or simply the login form no longer being present.
    """
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("a", href=re.compile(r"(logout|wyloguj|logoff)", re.IGNORECASE)):
        return True
    if soup.find(string=re.compile(r"(wyloguj|logout)", re.IGNORECASE)):
        return True
    return soup.find("input", attrs={"type": "password"}) is None


class BrClient:
    """Thin session wrapper for a logged-in (premium) BiznesRadar session.

    Mirrors portalanaliz.ForumClient's shape. All HTTP goes through
    app.scrapers.http.fetch so the same per-domain politeness/backoff policy
    applies to the login page as to every other BiznesRadar request.
    """

    # Try the Polish path first (current app expectation), then common fallbacks.
    LOGIN_PATHS = ("logowanie", "login")

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = polite_http.USER_AGENT
        self.logged_in = False

    def login(self, username: str, password: str) -> None:
        response = None
        login_url = ""
        failures: list[str] = []
        for path in self.LOGIN_PATHS:
            candidate = urljoin(self.base_url, path)
            candidate_response = polite_http.fetch(candidate, session=self.session)
            if candidate_response.status_code != 200:
                failures.append(f"{path}: HTTP {candidate_response.status_code}")
                continue
            try:
                _find_login_form(candidate_response.text)
            except BrLoginError as exc:
                failures.append(f"{path}: {exc}")
                continue
            response = candidate_response
            login_url = candidate
            break
        if response is None:
            raise BrLoginError(
                "Could not load BiznesRadar login page (" + "; ".join(failures) + ")."
            )

        try:
            payload, form_action = _login_payload_and_action(response.text, username, password)
        except BrLoginError:
            # No hidden fields found is not necessarily fatal — some login
            # forms carry none. Try the bare credentials before giving up.
            payload, form_action = {"login": username, "password": password}, None
        post_url = urljoin(login_url, form_action) if form_action else login_url

        try:
            post_response = self.session.post(
                post_url, data=payload, timeout=polite_http.DEFAULT_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise BrLoginError(f"Login request failed (network): {exc}") from exc

        if post_response.status_code == 200 and _looks_logged_in(post_response.text):
            self.logged_in = True
            return

        raise BrLoginError(
            f"Login failed (HTTP {post_response.status_code}) — check BR_USERNAME/"
            "BR_PASSWORD in backend/.env. Note: BiznesRadar's real login markup "
            "has not been verified in this codebase yet (see BrClient's module "
            "docstring) — if the credentials are correct, extract_login_fields/"
            "LOGIN_PATH/the success check likely need updating against a real "
            "recorded login page."
        )
