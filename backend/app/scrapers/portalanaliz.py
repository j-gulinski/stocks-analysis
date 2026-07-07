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
from datetime import datetime
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
