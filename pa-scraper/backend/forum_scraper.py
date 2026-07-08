"""
Scraper forum phpBB (PortalAnaliz.pl).

Loguje się z podanymi credentialami (sesja requests) i pobiera posty
z wątku, obsługując paginację. Parser oparty o realną strukturę HTML
forum PortalAnaliz (phpBB 3.x, styl prosilver).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE = "https://portalanaliz.pl/forum/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
# Kultura scrapowania: przerwa między requestami, żeby nie obciążać forum.
REQUEST_DELAY_S = 1.5


@dataclass
class ForumPost:
    post_id: str
    author: str
    datetime_iso: str
    content_text: str
    content_html: str


@dataclass
class TopicResult:
    title: str
    url: str
    pages_scraped: int
    posts: list[ForumPost] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "pages_scraped": self.pages_scraped,
            "post_count": len(self.posts),
            "posts": [asdict(p) for p in self.posts],
        }


class ForumScraperError(Exception):
    pass


class PhpBBScraper:
    def __init__(self, base_url: str = DEFAULT_BASE):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.logged_in = False

    # ------------------------------------------------------------------ login

    def login(self, username: str, password: str) -> None:
        """Logowanie do phpBB: pobiera formularz, wyciąga tokeny, wysyła POST."""
        login_url = urljoin(self.base_url, "ucp.php?mode=login")
        resp = self.session.get(login_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        form = soup.find("form", id="login") or soup.find(
            "form", action=re.compile(r"ucp\.php\?mode=login")
        )
        if form is None:
            raise ForumScraperError("Nie znaleziono formularza logowania (ucp.php).")

        payload = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                payload[name] = inp.get("value", "")

        payload.update(
            {
                "username": username,
                "password": password,
                "login": "Login",
                "autologin": "on",
            }
        )

        action = form.get("action") or "ucp.php?mode=login"
        post_url = urljoin(self.base_url, action)

        time.sleep(REQUEST_DELAY_S)
        resp = self.session.post(post_url, data=payload, timeout=30)
        resp.raise_for_status()

        # Po udanym logowaniu phpBB przekierowuje; sprawdzamy sesję.
        if self._is_logged_in(resp.text):
            self.logged_in = True
            return

        # Druga próba weryfikacji: pobierz stronę główną forum.
        check = self.session.get(self.base_url, timeout=30)
        if self._is_logged_in(check.text):
            self.logged_in = True
            return

        # Wyciągnij komunikat błędu z phpBB, jeśli jest.
        err_soup = BeautifulSoup(resp.text, "html.parser")
        err = err_soup.find(class_="error")
        msg = err.get_text(strip=True) if err else "Nieznany błąd logowania."
        raise ForumScraperError(f"Logowanie nieudane: {msg}")

    @staticmethod
    def _is_logged_in(html: str) -> bool:
        return ("ucp.php?mode=logout" in html) or ("mode=logout" in html)

    # ------------------------------------------------------------- pagination

    @staticmethod
    def _normalize_topic_url(url: str) -> tuple[str, dict]:
        """Zwraca URL bez fragmentu (#pXXX) oraz parametry query jako dict."""
        parsed = urlparse(url)
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        clean = urlunparse(parsed._replace(fragment="", query=""))
        return clean, qs

    def _page_url(self, base: str, qs: dict, start: int) -> str:
        params = {k: v for k, v in qs.items() if k in ("f", "t")}
        if start:
            params["start"] = str(start)
        return f"{base}?{urlencode(params)}"

    # --------------------------------------------------------------- scraping

    def scrape_topic(
        self, topic_url: str, all_pages: bool = True, max_pages: int = 50
    ) -> TopicResult:
        """
        Pobiera posty z wątku. Przy all_pages=True iteruje po paginacji
        (parametr `start`, phpBB pokazuje zwykle 25 postów/stronę).
        """
        clean_url, qs = self._normalize_topic_url(topic_url)
        if "t" not in qs:
            # URL mógł być postem typu viewtopic.php?p=NNN — pobierz i odczytaj t z canonical.
            resp = self._get(topic_url)
            soup = BeautifulSoup(resp.text, "html.parser")
            canonical = soup.find("link", rel="canonical")
            if canonical and canonical.get("href"):
                clean_url, qs = self._normalize_topic_url(canonical["href"])
            first_html = resp.text
        else:
            first_html = None

        result = TopicResult(title="", url=topic_url, pages_scraped=0)
        seen_ids: set[str] = set()
        start = int(qs.get("start", 0)) if not all_pages else 0

        for page_idx in range(max_pages):
            url = self._page_url(clean_url, qs, start)
            if page_idx == 0 and first_html is not None:
                html = first_html
            else:
                html = self._get(url).text

            soup = BeautifulSoup(html, "html.parser")
            if not result.title:
                title_el = soup.find("h2", class_="topic-title") or soup.find("title")
                result.title = title_el.get_text(strip=True) if title_el else ""

            posts = self._parse_posts(soup)
            new_posts = [p for p in posts if p.post_id not in seen_ids]
            for p in new_posts:
                seen_ids.add(p.post_id)
            result.posts.extend(new_posts)
            result.pages_scraped += 1

            per_page = len(posts)
            if not all_pages or per_page == 0 or not new_posts:
                break
            # Jest następna strona, jeśli paginacja zawiera wyższy `start`.
            if not self._has_next_page(soup, start, per_page):
                break
            start += per_page
            time.sleep(REQUEST_DELAY_S)

        return result

    def _get(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        if "mode=login" in resp.url and "ucp.php" in resp.url:
            raise ForumScraperError(
                "Forum przekierowało do logowania — sesja wygasła lub wątek wymaga zalogowania."
            )
        return resp

    @staticmethod
    def _has_next_page(soup: BeautifulSoup, current_start: int, per_page: int) -> bool:
        pagination = soup.find("div", class_="pagination")
        if not pagination:
            return False
        next_start = current_start + per_page
        for a in pagination.find_all("a", href=True):
            qs = parse_qs(urlparse(a["href"]).query)
            if "start" in qs:
                try:
                    if int(qs["start"][0]) >= next_start:
                        return True
                except ValueError:
                    continue
        return False

    @staticmethod
    def _parse_posts(soup: BeautifulSoup) -> list[ForumPost]:
        posts: list[ForumPost] = []
        containers = soup.find_all(
            "div", class_=lambda c: c and "post" in c.split() and "has-profile" in c
        )
        for div in containers:
            post_id = (div.get("id") or "").lstrip("p") or "?"
            author_tag = div.find("a", class_="username-coloured") or div.find(
                "a", class_="username"
            )
            author = author_tag.get_text(strip=True) if author_tag else "?"
            time_tag = div.find("time")
            dt = time_tag.get("datetime", "") if time_tag else ""
            content = div.find("div", class_="content")
            if content is None:
                continue
            posts.append(
                ForumPost(
                    post_id=post_id,
                    author=author,
                    datetime_iso=dt,
                    content_text=content.get_text("\n", strip=True),
                    content_html=str(content),
                )
            )
        return posts


def topic_to_markdown(result: TopicResult) -> str:
    lines = [f"# {result.title}", f"\nŹródło: {result.url}", f"Postów: {len(result.posts)}\n"]
    for p in result.posts:
        lines.append(f"\n---\n\n**{p.author}** — {p.datetime_iso}\n")
        lines.append(p.content_text)
    return "\n".join(lines)
