"""Forum discovery via PortalAnaliz search: parser, guest-block, filtering/cap,
and the refresh freshness gate. No network, no login — fixtures + monkeypatch.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import FetchLog, ForumTopic
from app.scrapers import portalanaliz
from app.scrapers.portalanaliz import (
    NeedsLoginError,
    _parse_forum_datetime,
    parse_search_results,
    search_recent_posts,
    search_url,
)
from app.services import forum_sync, refresh
from app.services.refresh import get_or_create_company
from tests.conftest import load_fixture

BASE = "https://portalanaliz.pl/forum/"


# --------------------------------------------------------------- date parsing

def test_parse_forum_datetime_en_and_pl():
    # English (the user's forum locale) and Polish month names both parse to UTC.
    assert _parse_forum_datetime("22 May 2026 14:41") == datetime(
        2026, 5, 22, 14, 41, tzinfo=timezone.utc
    )
    assert _parse_forum_datetime("10 maj 2024, 14:00") == datetime(
        2024, 5, 10, 14, 0, tzinfo=timezone.utc
    )
    assert _parse_forum_datetime("22 paź 2026, 09:05") == datetime(
        2026, 10, 22, 9, 5, tzinfo=timezone.utc
    )
    assert _parse_forum_datetime("nonsense") is None


# ------------------------------------------------------------------- parsing

def test_parse_search_results_fixture():
    rows = parse_search_results(load_fixture("pa_search_results.html"), BASE)

    # three posts, two distinct topics
    assert len(rows) == 3
    assert {r["topic_phpbb_id"] for r in rows} == {12, 77}

    first = rows[0]
    assert first["topic_phpbb_id"] == 12
    assert first["topic_title"] == "(DCR) DECORA"
    assert first["post_phpbb_id"] == 113346
    assert first["author"] == "tommy_vp"
    assert first["forum_id"] == 3
    assert first["replies"] == 209
    assert first["views"] == 29512
    assert first["posted_at"] == datetime(2026, 5, 22, 14, 41, tzinfo=timezone.utc)
    # canonical topic URL: absolutized, hilit/sid dropped, f + t kept
    assert first["topic_url"] == "https://portalanaliz.pl/forum/viewtopic.php?f=3&t=12"

    other = rows[1]
    assert other["topic_phpbb_id"] == 77
    assert other["topic_title"] == "(SNT) SYNEKTIK"
    assert other["author"] == "value_hunter"


class _FakeClient:
    """Serves a fixed HTML for any URL; records the last fetched URL."""

    def __init__(self, html: str):
        self._html = html
        self.base_url = BASE
        self.url: str | None = None

    def fetch_page(self, url: str) -> str:
        self.url = url
        return self._html


def test_search_recent_posts_returns_dicts():
    client = _FakeClient(load_fixture("pa_search_results.html"))
    rows = search_recent_posts(client, "DCR")
    assert len(rows) == 3
    assert client.url == "https://portalanaliz.pl/forum/search.php?keywords=DCR"


def test_search_guest_blocked_raises_needs_login():
    client = _FakeClient(load_fixture("pa_search_guest_blocked.html"))
    with pytest.raises(NeedsLoginError):
        search_recent_posts(client, "DCR")


# --------------------------------------------------------------- discovery

def test_discover_filters_by_ticker_and_caps(db, monkeypatch):
    company = get_or_create_company(db, "DCR")
    company.name = "DECORA"
    db.commit()

    def mk(tid: int, title: str) -> dict:
        return {
            "topic_phpbb_id": tid,
            "topic_title": title,
            "topic_url": f"{BASE}viewtopic.php?f=3&t={tid}",
            "post_phpbb_id": 1000 + tid,
            "posted_at": None,
            "author": "x",
            "forum_id": 3,
            "replies": 1,
            "views": 1,
        }

    fake_rows = [
        mk(12, "(DCR) DECORA"),
        mk(12, "(DCR) DECORA"),          # duplicate topic → deduped
        mk(77, "(SNT) SYNEKTIK"),        # other company → filtered out
        mk(20, "(DCR) DECORA — wątek 2"),
        mk(21, "Coś nowego o DECORA"),   # matched by full company name
        mk(22, "(DCR) DECORA analiza"),
        mk(23, "(DCR) DECORA c.d."),     # 5th match → over the cap of 3
    ]
    monkeypatch.setattr(portalanaliz, "search_recent_posts", lambda client, query: fake_rows)

    def fake_link(db_, url, ticker, client=None):
        topic = ForumTopic(
            company_id=company.id,
            url=url,
            phpbb_topic_id=portalanaliz.extract_topic_id(url),
            title=url,
        )
        db_.add(topic)
        db_.flush()
        return topic

    monkeypatch.setattr(forum_sync, "link_topic", fake_link)

    result = forum_sync.discover_and_link_topics(db, object(), company, max_new=3)

    assert result.searches == 1                       # ticker hit, no fallback
    assert result.candidates == 5                     # distinct title-matches
    assert len(result.linked) == 3                    # capped at max_new
    linked_ids = {t.phpbb_topic_id for t in result.linked}
    assert linked_ids == {12, 20, 21}                 # newest-first, first three
    assert 77 not in linked_ids                       # other company excluded


def test_discover_falls_back_to_name_word(db, monkeypatch):
    company = get_or_create_company(db, "DCR")
    company.name = "DECORA"
    db.commit()

    queries: list[str] = []

    def fake_search(client, query):
        queries.append(query)
        if query == "DCR":
            return []  # ticker search finds nothing topic-matching
        return [
            {
                "topic_phpbb_id": 12,
                "topic_title": "(DCR) DECORA",
                "topic_url": f"{BASE}viewtopic.php?f=3&t=12",
                "post_phpbb_id": 1,
                "posted_at": None,
                "author": "x",
                "forum_id": 3,
                "replies": 1,
                "views": 1,
            }
        ]

    monkeypatch.setattr(portalanaliz, "search_recent_posts", fake_search)
    monkeypatch.setattr(
        forum_sync,
        "link_topic",
        lambda db_, url, ticker, client=None: ForumTopic(
            company_id=company.id, url=url, phpbb_topic_id=12, title=url
        ),
    )

    result = forum_sync.discover_and_link_topics(db, object(), company, max_new=3)

    assert queries == ["DCR", "DECORA"]  # fallback used the first name word
    assert result.searches == 2          # hard cap respected
    assert len(result.linked) == 1


# ------------------------------------------------------- refresh freshness gate

def test_discovery_freshness_gate(db, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(
        refresh, "get_settings", lambda: Settings(pa_username="u", pa_password="p")
    )

    company = get_or_create_company(db, "DCR")
    db.commit()

    calls: list[str] = []

    def fake_discover(db_, client, comp, *, max_new=3):
        calls.append(comp.ticker)
        return forum_sync.DiscoveryResult(linked=[], searches=1, candidates=0)

    monkeypatch.setattr(forum_sync, "discover_and_link_topics", fake_discover)
    monkeypatch.setattr(forum_sync, "_make_client", lambda: object())

    note1 = refresh._sync_linked_forum_topics(db, company)
    assert calls == ["DCR"]                # discovery ran on the first refresh
    assert "wyszukiwarka" in note1

    note2 = refresh._sync_linked_forum_topics(db, company)
    assert calls == ["DCR"]                # 24 h gate blocked the second search
    assert "cache" in note2

    marker = search_url("DCR", BASE)
    assert db.scalar(select(FetchLog).where(FetchLog.url == marker)) is not None
