"""Forum topic linking and incremental post sync (Module A service layer)."""
from __future__ import annotations

from urllib.parse import urljoin

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ForumPost, ForumTopic, utcnow
from app.scrapers import portalanaliz
from app.services.refresh import get_or_create_company


class TopicAlreadyLinkedError(Exception):
    pass


def _make_client() -> portalanaliz.ForumClient:
    """Build a client, logged in when credentials are configured.

    Public topics are readable anonymously; login unlocks members-only ones.
    Tests monkeypatch this function to inject a fake client.
    """
    settings = get_settings()
    client = portalanaliz.ForumClient(base_url=settings.pa_base_url)
    if settings.pa_username and settings.pa_password:
        client.login(settings.pa_username, settings.pa_password)
    return client


def check_login() -> dict:
    """Used by the settings page: verifies forum credentials actually work.

    Must NEVER raise — whatever goes wrong (bad password, network, the forum
    blocking us) becomes a readable {ok: false, detail} instead of a 500.
    """
    settings = get_settings()
    if not (settings.pa_username and settings.pa_password):
        return {
            "ok": False,
            "status": "not_configured",
            "detail": "PA_USERNAME / PA_PASSWORD not configured.",
        }
    try:
        client = portalanaliz.ForumClient(base_url=settings.pa_base_url)
        client.login(settings.pa_username, settings.pa_password)
        return {
            "ok": True,
            "status": "ok",
            "detail": f"Logged in as {settings.pa_username}.",
        }
    except Exception as exc:  # noqa: BLE001 — diagnostics endpoint, see docstring
        return {
            "ok": False,
            "status": "error",
            "detail": f"{type(exc).__name__}: {exc}",
        }


def link_topic(db: Session, url: str, ticker: str) -> ForumTopic:
    """Attach a forum thread URL to a company (fetches page 1 for metadata)."""
    company = get_or_create_company(db, ticker)

    client = _make_client()
    html = client.fetch_page(url)
    page = portalanaliz.parse_topic_page(html)

    # Canonical URL: prefer the id from the page itself (works for post
    # permalinks like ?p=115348 that carry no explicit topic id).
    topic_id = page.topic_id or portalanaliz.extract_topic_id(url)
    if topic_id and portalanaliz.extract_topic_id(url):
        canonical = portalanaliz.canonical_topic_url(url)
    elif topic_id:
        canonical = urljoin(client.base_url, f"viewtopic.php?t={topic_id}")
    else:
        canonical = url

    lookup = [ForumTopic.url == canonical]
    if topic_id:
        lookup.append(ForumTopic.phpbb_topic_id == topic_id)
    existing = db.scalar(select(ForumTopic).where(or_(*lookup)))
    if existing is not None:
        raise TopicAlreadyLinkedError(
            f"Topic already linked (id={existing.id}, title={existing.title!r})."
        )

    topic = ForumTopic(
        company_id=company.id,
        url=canonical,
        phpbb_topic_id=topic_id,
        title=page.title,
    )
    db.add(topic)
    db.commit()
    return topic


def _existing_post_ids(db: Session, topic: ForumTopic) -> set[int]:
    return set(
        db.scalars(select(ForumPost.phpbb_post_id).where(ForumPost.topic_id == topic.id))
    )


def _store_posts(
    db: Session,
    topic: ForumTopic,
    page: portalanaliz.TopicPage,
    existing_ids: set[int],
) -> int:
    new_posts = 0
    for post in page.posts:
        if post.phpbb_post_id in existing_ids:
            continue
        db.add(
            ForumPost(
                topic_id=topic.id,
                phpbb_post_id=post.phpbb_post_id,
                author=post.author,
                posted_at=post.posted_at,
                content_text=post.content_text,
                content_html=post.content_html,
                upvotes=post.upvotes,
            )
        )
        existing_ids.add(post.phpbb_post_id)
        new_posts += 1

    if page.title and not topic.title:
        topic.title = page.title
    return new_posts


def _finish_sync(db: Session, topic: ForumTopic) -> int:
    topic.last_synced_at = utcnow()
    topic.last_post_at = db.scalar(
        select(func.max(ForumPost.posted_at)).where(ForumPost.topic_id == topic.id)
    )
    db.commit()

    total = db.scalar(
        select(func.count()).select_from(ForumPost).where(ForumPost.topic_id == topic.id)
    )
    return int(total or 0)


def sync_topic(db: Session, topic: ForumTopic) -> tuple[int, int]:
    """Pull all new posts; returns (new_posts, total_posts).

    Incremental strategy: re-fetch from the last partial page onward and skip
    already-stored post ids. Deleted posts can shift offsets — a rare case;
    normal stock refresh uses `sync_topic_recent` instead of this full crawler.
    """
    client = _make_client()
    existing_ids = _existing_post_ids(db, topic)

    per_page = portalanaliz.POSTS_PER_PAGE
    start = (len(existing_ids) // per_page) * per_page if existing_ids else 0
    new_posts = 0

    while True:
        page_url = portalanaliz.topic_page_url(topic.url, start)
        page = portalanaliz.parse_topic_page(client.fetch_page(page_url))
        new_posts += _store_posts(db, topic, page, existing_ids)
        if len(page.posts) < per_page:
            break  # last page reached
        start += per_page

    return new_posts, _finish_sync(db, topic)


def sync_topic_recent(
    db: Session, topic: ForumTopic, max_pages: int = 2
) -> tuple[int, int]:
    """Pull only the newest page(s) of a linked topic.

    PortalAnaliz threads can be years long. Normal stock refresh should capture
    recent/high-signal discussion without crawling historical pages. We fetch
    the topic once to read pagination, then store at most the latest
    `max_pages` pages, skipping post ids already in the DB.
    """
    client = _make_client()
    existing_ids = _existing_post_ids(db, topic)
    first_page = portalanaliz.parse_topic_page(client.fetch_page(topic.url))

    latest_start = first_page.latest_start
    starts = [
        latest_start - offset * portalanaliz.POSTS_PER_PAGE
        for offset in range(max(1, max_pages))
        if latest_start - offset * portalanaliz.POSTS_PER_PAGE >= 0
    ] or [0]

    pages = [first_page] if latest_start == 0 else []
    for start in sorted(set(starts)):
        if start == 0 and latest_start == 0:
            continue
        page_url = portalanaliz.topic_page_url(topic.url, start)
        pages.append(portalanaliz.parse_topic_page(client.fetch_page(page_url)))

    new_posts = 0
    for page in pages:
        new_posts += _store_posts(db, topic, page, existing_ids)

    return new_posts, _finish_sync(db, topic)
