"""Phase 2 tests: topic page parsing (fixture) + link/sync/read flow via API
with a fake forum client (no network, no login)."""
from datetime import datetime, timezone

import pytest

from app.scrapers.portalanaliz import (
    LoginError,
    canonical_topic_url,
    extract_login_fields,
    extract_topic_id,
    parse_topic_page,
    topic_page_url,
)
from tests.conftest import FIXTURES_DIR, load_fixture


# ----------------------------------------------------------------- parsing

def test_parse_topic_page_fixture():
    page = parse_topic_page(load_fixture("pa_topic.html"))

    assert page.title == "Decora - dyskusja o spółce"
    assert page.topic_id == 1234
    assert [p.phpbb_post_id for p in page.posts] == [101, 102]

    first = page.posts[0]
    assert first.author == "OBS"
    assert first.posted_at == datetime(2024, 5, 10, 12, 0, tzinfo=timezone.utc)
    assert "Marża brutto rośnie" in first.content_text
    assert "<div" in first.content_html
    assert first.upvotes == 4
    assert page.posts[1].upvotes is None  # no vote markup → honest None

    second = page.posts[1]
    assert second.author == "analityk77"
    assert "Backlog wygląda dobrze" in second.content_text
    # Quoted text is kept — it is part of the discussion context.
    assert "eksport UE" in second.content_text


def test_real_topic_fixture_recognizes_real_upvote_markup():
    path = FIXTURES_DIR / "real" / "pa" / "topic.html"
    if not path.exists():
        pytest.skip("RT0.3 open: record a public topic with visible vote markup")
    page = parse_topic_page(path.read_text(encoding="utf-8"))
    assert page.posts
    assert any(post.upvotes is not None for post in page.posts), (
        "real topic recorded, but no upvote value was recognized; extend only "
        "_UPVOTE_SELECTORS/_UPVOTE_TEXT_RE from this fixture"
    )


def test_url_helpers():
    url = "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234"
    assert extract_topic_id(url) == 1234
    assert extract_topic_id("https://portalanaliz.pl/forum/index.php") is None

    assert topic_page_url(url, 0) == url
    assert topic_page_url(url, 50).endswith("start=50")
    # replacing an existing offset, not appending a second one
    assert topic_page_url(topic_page_url(url, 50), 100).count("start=") == 1

    messy = "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234&start=150&hilit=x"
    assert canonical_topic_url(messy) == url


def test_extract_login_fields():
    html = """
    <form id="login" action="./ucp.php?mode=login">
      <input type="text" name="username" />
      <input type="hidden" name="creation_time" value="123" />
      <input type="hidden" name="form_token" value="abc" />
      <input type="hidden" name="sid" value="s1" />
    </form>"""
    assert extract_login_fields(html) == {
        "creation_time": "123",
        "form_token": "abc",
        "sid": "s1",
    }
    with pytest.raises(LoginError):
        extract_login_fields("<html><body>no form here</body></html>")


def test_forum_login_uses_shared_polite_fetcher(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        def __init__(self, text):
            self.text = text

    login_form = """
    <form id="login">
      <input type="hidden" name="creation_time" value="123" />
      <input type="hidden" name="form_token" value="abc" />
    </form>
    """

    def fake_fetch(url, **kwargs):
        calls.append((url, kwargs))
        if kwargs.get("method") == "POST":
            return Response('<a href="./ucp.php?mode=logout">logout</a>')
        return Response(login_form)

    monkeypatch.setattr("app.scrapers.portalanaliz.polite_http.fetch", fake_fetch)
    monkeypatch.setattr("app.scrapers.portalanaliz.time.sleep", lambda _seconds: None)

    from app.scrapers.portalanaliz import ForumClient

    client = ForumClient()
    client.login("user", "password")

    assert client.logged_in is True
    assert len(calls) == 2
    assert calls[0][1]["session"] is client.session
    assert calls[1][1]["session"] is client.session
    assert calls[1][1]["method"] == "POST"
    assert calls[1][1]["data"]["username"] == "user"


# ------------------------------------------------------------- link + sync

class FakeForumClient:
    """Serves the fixture for every page URL — a 2-post, single-page topic."""

    def __init__(self):
        self.fetched: list[str] = []

    def fetch_page(self, url: str) -> str:
        self.fetched.append(url)
        return load_fixture("pa_topic.html")


@pytest.fixture()
def fake_forum(monkeypatch):
    client = FakeForumClient()
    monkeypatch.setattr(
        "app.services.forum_sync._make_client", lambda: client
    )
    return client


def test_link_sync_and_read_flow(client, fake_forum):
    url = "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234"

    linked = client.post("/api/forum/topics", json={"url": url, "ticker": "DEC"})
    assert linked.status_code == 201
    body = linked.json()
    assert body["title"] == "Decora - dyskusja o spółce"
    topic_id = body["id"]

    # linking the same thread twice is a conflict, not a duplicate
    duplicate = client.post("/api/forum/topics", json={"url": url, "ticker": "DEC"})
    assert duplicate.status_code == 409

    synced = client.post(f"/api/forum/topics/{topic_id}/sync").json()
    assert synced == {"topic_id": topic_id, "new_posts": 2, "total_posts": 2}

    # second sync is incremental: nothing new
    resynced = client.post(f"/api/forum/topics/{topic_id}/sync").json()
    assert resynced["new_posts"] == 0
    assert resynced["total_posts"] == 2

    posts = client.get("/api/companies/DEC/forum").json()
    assert posts["total"] == 2
    assert [p["phpbb_post_id"] for p in posts["posts"]] == [102, 101]  # newest first

    filtered = client.get("/api/companies/DEC/forum", params={"author": "OBS"}).json()
    assert filtered["total"] == 1
    assert filtered["posts"][0]["author"] == "OBS"

    # top sort: the upvoted post (p101, +4) outranks the newer unvoted one
    top = client.get("/api/companies/DEC/forum", params={"sort": "top"}).json()
    assert [p["phpbb_post_id"] for p in top["posts"]] == [101, 102]
    assert top["posts"][0]["upvotes"] == 4

    topics = client.get("/api/companies/DEC/forum/topics").json()
    assert len(topics) == 1


def test_sync_unknown_topic_404(client):
    assert client.post("/api/forum/topics/999/sync").status_code == 404


def test_login_status_without_credentials(client):
    status_body = client.get("/api/forum/login-status").json()
    assert status_body["ok"] is False
    assert status_body["status"] == "not_configured"
    assert "not configured" in status_body["detail"]


# ------------------------------------------------------------- content_text

def test_content_text_stored_on_sync(client, fake_forum, db):
    """A normal sync now stores post bodies, not just author/date/upvotes —
    the gap `forum_sync._store_posts` used to have (nothing fed the
    distiller). Content is parsed straight from the fixture (see
    `test_parse_topic_page_fixture` above for the source text)."""
    from app.db.models import ForumPost
    from sqlalchemy import select

    url = "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234"
    linked = client.post("/api/forum/topics", json={"url": url, "ticker": "DEC"})
    topic_id = linked.json()["id"]

    client.post(f"/api/forum/topics/{topic_id}/sync")

    posts = db.scalars(
        select(ForumPost).where(ForumPost.topic_id == topic_id)
    ).all()
    by_id = {p.phpbb_post_id: p for p in posts}
    assert "Marża brutto rośnie" in by_id[101].content_text
    assert "Backlog wygląda dobrze" in by_id[102].content_text


def test_content_text_backfilled_on_full_resync(client, fake_forum, db):
    """A `mode=full` resync heals posts stored before this column existed
    (content_text IS NULL) instead of skipping them forever via
    `existing_ids` — see `forum_sync._store_posts`'s backfill pass."""
    from app.db.models import ForumPost, ForumTopic
    from sqlalchemy import select

    url = "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234"
    linked = client.post("/api/forum/topics", json={"url": url, "ticker": "DEC"})
    topic_id = linked.json()["id"]

    # Simulate a pre-migration row: post 101 already stored with no body
    # text at all (every row synced before this feature would look like this).
    topic = db.get(ForumTopic, topic_id)
    db.add(
        ForumPost(
            topic_id=topic.id,
            phpbb_post_id=101,
            author="OBS",
            posted_at=None,
            upvotes=None,
            content_text=None,
        )
    )
    db.commit()

    synced = client.post(
        f"/api/forum/topics/{topic_id}/sync", params={"mode": "full"}
    ).json()
    # post 101 already existed (by id) -> not counted as "new"; only 102 is.
    assert synced["new_posts"] == 1
    assert synced["total_posts"] == 2

    row = db.scalar(
        select(ForumPost).where(
            ForumPost.topic_id == topic_id, ForumPost.phpbb_post_id == 101
        )
    )
    assert row.content_text is not None
    assert "Marża brutto rośnie" in row.content_text
