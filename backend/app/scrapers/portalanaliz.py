"""PortalAnaliz forum scraper (phpBB 3.x, prosilver theme).

Markup knowledge comes from the reference pa-scraper, which was verified
against real thread pages: posts are `div.post` with id `p{post_id}`, author in
`a.username-coloured` / `a.username`, timestamp in `time[datetime]`, body in
`div.content`.

Credentials are used only to hold a logged-in requests.Session in memory —
they are never persisted anywhere (see CLAUDE.md security rules).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from app.scrapers import http as polite_http

DEFAULT_BASE_URL = "https://portalanaliz.pl/forum/"
POSTS_PER_PAGE = 50  # phpBB default on PortalAnaliz (verified by reference scraper)

_POST_ID_RE = re.compile(r"^p(\d+)$")


class ForumError(Exception):
    pass


class LoginError(ForumError):
    pass


class NeedsLoginError(ForumError):
    """The forum search returned the guest-block page (HTTP 200 body).

    PortalAnaliz forbids anonymous search: the page renders fine but carries
    "Nie masz uprawnień do używania wyszukiwarki." instead of results. The
    caller is expected to (re)login the shared session and retry ONCE.
    """


@dataclass
class ParsedPost:
    phpbb_post_id: int
    author: str
    posted_at: datetime | None
    content_text: str
    content_html: str
    upvotes: int | None = None


@dataclass
class TopicPage:
    title: str | None = None
    topic_id: int | None = None
    latest_start: int = 0
    posts: list[ParsedPost] = field(default_factory=list)


# ------------------------------------------------------------------- urls

def extract_topic_id(url: str) -> int | None:
    """viewtopic.php?f=7&t=1234 → 1234."""
    query = parse_qs(urlparse(url).query)
    values = query.get("t")
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def canonical_topic_url(url: str, base_url: str = DEFAULT_BASE_URL) -> str:
    """Stable per-topic URL: strips paging/highlight params, keeps f and t.

    phpBB accepts `viewtopic.php?t={id}` alone, so post-permalinks
    (?p=115348#p115348) normalize once the topic id is known.
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    kept = {k: v[0] for k, v in query.items() if k in ("f", "t")}
    if not kept.get("t"):
        return url  # cannot canonicalize yet — resolve via page's canonical link
    return urlunparse(parsed._replace(query=urlencode(kept), fragment=""))


def topic_page_url(topic_url: str, start: int) -> str:
    """Return the topic URL for a given pagination offset."""
    parsed = urlparse(topic_url)
    query = parse_qs(parsed.query)
    query["start"] = [str(start)] if start else []
    flat = {k: v[0] for k, v in query.items() if v}
    return urlunparse(parsed._replace(query=urlencode(flat)))


# ----------------------------------------------------------------- parsing

# Vote/like markup differs between phpBB mods; try known selectors first, then
# a text pattern. If PortalAnaliz uses yet another markup, record a real page
# (scripts/record_topic_fixture.py) and extend THIS list — nothing else.
_UPVOTE_SELECTORS = (
    "span.post-rating",
    ".post_rating",
    ".post-likes",
    ".like-count",
    ".thanks-counter",
    ".post_thanks_count",
)
_UPVOTE_TEXT_RE = re.compile(
    r"(?:polubi\w*|podziękowa\w*|thanks?|liked)\D{0,20}?(\d+)", re.IGNORECASE
)
_INT_RE = re.compile(r"[+-]?\d+")


def _extract_upvotes(post_div) -> int | None:
    for selector in _UPVOTE_SELECTORS:
        element = post_div.select_one(selector)
        if element is not None:
            match = _INT_RE.search(element.get_text(" ", strip=True))
            if match:
                return abs(int(match.group(0)))
    match = _UPVOTE_TEXT_RE.search(post_div.get_text(" ", strip=True))
    return int(match.group(1)) if match else None


def parse_topic_page(html: str) -> TopicPage:
    soup = BeautifulSoup(html, "html.parser")
    page = TopicPage()

    title_link = soup.select_one("h2.topic-title a") or soup.select_one("h2 a")
    if title_link:
        page.title = title_link.get_text(" ", strip=True)
    elif soup.title:
        page.title = soup.title.get_text(strip=True)

    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        page.topic_id = extract_topic_id(canonical["href"])

    starts: list[int] = []
    for link in soup.find_all("a", href=True):
        values = parse_qs(urlparse(link["href"]).query).get("start")
        if not values:
            continue
        try:
            starts.append(int(values[0]))
        except ValueError:
            continue
    page.latest_start = max(starts) if starts else 0

    for post_div in soup.find_all("div", class_="post"):
        match = _POST_ID_RE.match(post_div.get("id") or "")
        if not match:
            continue

        author_el = post_div.select_one(
            "a.username-coloured, a.username, span.username-coloured, span.username"
        )
        author = author_el.get_text(" ", strip=True) if author_el else "unknown"

        posted_at: datetime | None = None
        time_el = post_div.find("time", attrs={"datetime": True})
        if time_el:
            try:
                posted_at = datetime.fromisoformat(time_el["datetime"])
            except ValueError:
                posted_at = None

        content_el = post_div.select_one("div.content")
        content_text = content_el.get_text("\n", strip=True) if content_el else ""
        content_html = str(content_el) if content_el else ""

        page.posts.append(
            ParsedPost(
                phpbb_post_id=int(match.group(1)),
                author=author,
                posted_at=posted_at,
                content_text=content_text,
                content_html=content_html,
                upvotes=_extract_upvotes(post_div),
            )
        )

    return page


# ------------------------------------------------------------------ search

# Guest search is blocked on PortalAnaliz: the page is HTTP 200 but carries
# this exact phrase instead of results (verified live 2026-07-08).
SEARCH_GUEST_BLOCKED = "Nie masz uprawnień do używania wyszukiwarki"

# Month names as rendered in phpBB search-result dates. The user's forum locale
# emits English ("22 May 2026 14:41"), but a Polish locale ("22 paź 2026,
# 14:41") is equally valid — map both. Values collide harmlessly where the two
# languages share a stem (maj/May → 5, mar/March/marca → 3).
_MONTHS: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    "styczeń": 1, "stycznia": 1, "sty": 1, "luty": 2, "lutego": 2, "lut": 2,
    "marzec": 3, "marca": 3, "kwiecień": 4, "kwietnia": 4, "kwi": 4,
    "maj": 5, "maja": 5, "czerwiec": 6, "czerwca": 6, "cze": 6,
    "lipiec": 7, "lipca": 7, "lip": 7, "sierpień": 8, "sierpnia": 8, "sie": 8,
    "wrzesień": 9, "września": 9, "wrz": 9, "październik": 10, "października": 10,
    "paź": 10, "paz": 10, "listopad": 11, "listopada": 11, "lis": 11,
    "grudzień": 12, "grudnia": 12, "gru": 12,
}
# "22 May 2026 14:41" and "10 maj 2024, 14:00" — day, month-word, year, HH:MM.
_SEARCH_DATE_RE = re.compile(
    r"(\d{1,2})\s+([^\s,.]+)\.?\s+(\d{4})[,\s]+(\d{1,2}):(\d{2})"
)


def _parse_forum_datetime(text: str) -> datetime | None:
    """Parse a phpBB search-result date (EN or PL month names) → UTC datetime.

    Search rows carry no ISO `datetime` attribute (unlike topic posts), only the
    displayed wall-clock string. We attach UTC for a tz-aware value consistent
    with the topic parser; the exact forum offset is unknown and not worth a
    guess for discovery metadata. Returns None on any surprise, never raises.
    """
    if not text:
        return None
    match = _SEARCH_DATE_RE.search(text)
    if not match:
        return None
    day, month_word, year, hour, minute = match.groups()
    month = _MONTHS.get(month_word.lower())
    if month is None:
        return None
    try:
        return datetime(
            int(year), month, int(day), int(hour), int(minute), tzinfo=timezone.utc
        )
    except ValueError:
        return None


def search_url(query: str, base_url: str = DEFAULT_BASE_URL) -> str:
    """Stable search URL for a keyword query (also the 24 h freshness-gate key)."""
    return urljoin(base_url, "search.php?" + urlencode({"keywords": query}))


def _absolutize(href: str, base_url: str) -> str:
    """Resolve a phpBB relative href ("./viewtopic.php?…") to an absolute URL.

    BeautifulSoup already decodes HTML entities, so `&amp;` arrives as `&`.
    """
    return urljoin(base_url, href)


def parse_search_results(html: str, base_url: str = DEFAULT_BASE_URL) -> list[dict]:
    """Parse one page of phpBB search results (posts mode) → list of dicts.

    Each result is a `div.search.post` with a `dl.postprofile` (author, date,
    forum, topic, replies, views) and a `div.postbody h3 a` post permalink.
    Locale-agnostic: topic/forum ids come from href query params, not label
    text, so EN and PL renderings parse identically.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    for block in soup.select("div.search.post"):
        profile = block.find("dl", class_="postprofile")

        author = "unknown"
        if profile is not None:
            author_link = profile.select_one("dt.author a")
            if author_link is not None:
                author = author_link.get_text(" ", strip=True)
            else:
                author_dt = profile.find("dt", class_="author")
                if author_dt is not None:
                    author = re.sub(
                        r"^\s*(by|przez)\s+", "", author_dt.get_text(" ", strip=True),
                        flags=re.IGNORECASE,
                    )

        date_el = block.find("dd", class_="search-result-date")
        posted_at = _parse_forum_datetime(date_el.get_text(" ", strip=True)) if date_el else None

        # Topic link: the postprofile <a> pointing at a viewtopic with a `t=`.
        topic_link = None
        for anchor in (profile.find_all("a", href=True) if profile else []):
            if "viewtopic.php" not in anchor["href"]:
                continue
            if parse_qs(urlparse(anchor["href"]).query).get("t"):
                topic_link = anchor
                break
        if topic_link is None:
            continue  # not a usable topic result

        topic_href = _absolutize(topic_link["href"], base_url)
        topic_id = extract_topic_id(topic_href)
        topic_title = topic_link.get_text(" ", strip=True)
        topic_url = canonical_topic_url(topic_href, base_url)  # drops hilit/sid

        forum_id = None
        forum_values = parse_qs(urlparse(topic_href).query).get("f")
        if forum_values:
            try:
                forum_id = int(forum_values[0])
            except ValueError:
                forum_id = None

        post_id = None
        post_anchor = block.select_one("div.postbody h3 a[href]")
        if post_anchor is not None:
            post_values = parse_qs(urlparse(post_anchor["href"]).query).get("p")
            if post_values:
                try:
                    post_id = int(post_values[0])
                except ValueError:
                    post_id = None

        replies = views = None
        for dd in (profile.find_all("dd") if profile else []):
            strong = dd.find("strong")
            if strong is None:
                continue
            digits = re.sub(r"\D", "", strong.get_text())
            if not digits:
                continue
            label = dd.get_text(" ", strip=True).lower()
            if label.startswith(("replies", "odpowied")):
                replies = int(digits)
            elif label.startswith(("views", "wyświetl", "wyswietl", "odsłon", "odslon")):
                views = int(digits)

        results.append(
            {
                "topic_phpbb_id": topic_id,
                "topic_title": topic_title,
                "topic_url": topic_url,
                "post_phpbb_id": post_id,
                "posted_at": posted_at,
                "author": author,
                "forum_id": forum_id,
                "replies": replies,
                "views": views,
            }
        )

    return results


def search_recent_posts(
    client: "ForumClient", query: str, base_url: str | None = None
) -> list[dict]:
    """Fetch + parse the FIRST page of forum search results for `query`.

    Politeness: exactly one GET through the shared (logged-in) session. Raises
    NeedsLoginError when the guest-block page comes back so the caller can
    (re)login and retry once. Never paginates — discovery is recent-only.
    """
    base = base_url or getattr(client, "base_url", DEFAULT_BASE_URL)
    html = client.fetch_page(search_url(query, base))
    if SEARCH_GUEST_BLOCKED in html:
        raise NeedsLoginError(
            "PortalAnaliz search requires a logged-in session (guest search blocked)."
        )
    return parse_search_results(html, base)


def extract_login_fields(html: str) -> dict[str, str]:
    """Hidden inputs of the phpBB login form (creation_time, form_token, sid…)."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="login") or soup.find(
        "form", action=re.compile(r"ucp\.php\?mode=login")
    )
    if form is None:
        raise LoginError("Login form not found on ucp.php page.")
    fields_out: dict[str, str] = {}
    for hidden in form.find_all("input", type="hidden"):
        name = hidden.get("name")
        if name:
            fields_out[name] = hidden.get("value", "")
    return fields_out


# ------------------------------------------------------------------ client

class ForumClient:
    """Thin session wrapper; all GETs go through the polite fetcher."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = polite_http.USER_AGENT
        self.logged_in = False

    def fetch_page(self, url: str) -> str:
        response = polite_http.fetch(url, session=self.session)
        if response.status_code != 200:
            raise ForumError(f"HTTP {response.status_code} for {url}")
        return response.text

    def login(self, username: str, password: str) -> None:
        login_url = urljoin(self.base_url, "ucp.php?mode=login")
        page_html = self.fetch_page(login_url)
        payload = extract_login_fields(page_html)
        payload.update(
            {"username": username, "password": password, "login": "Zaloguj", "redirect": "index.php"}
        )
        # phpBB validates form_token age — submitting faster than a human can
        # type gets rejected as "form invalid". Two seconds keeps it happy.
        time.sleep(2.0)
        try:
            response = self.session.post(login_url, data=payload, timeout=30)
        except requests.RequestException as exc:
            raise LoginError(f"Login request failed (network): {exc}") from exc

        if response.status_code == 200 and "mode=logout" in response.text:
            self.logged_in = True
            return

        # Surface phpBB's own error message — far more useful than a guess.
        soup = BeautifulSoup(response.text, "html.parser")
        error_el = soup.select_one("div.error, p.error, .errorbox")
        forum_says = (
            f" Forum message: {error_el.get_text(' ', strip=True)[:200]}"
            if error_el
            else ""
        )
        raise LoginError(
            f"Login failed (HTTP {response.status_code}) — check PA_USERNAME/"
            f"PA_PASSWORD in backend/.env.{forum_says}"
        )
