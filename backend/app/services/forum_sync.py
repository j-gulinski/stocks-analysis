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
        return {"ok": False, "detail": "PA_USERNAME / PA_PASSWORD not configured."}
    try:
        client = portalanaliz.ForumClient(base_url=settings.pa_base_url)
        client.login(settings.pa_username, settings.pa_password)
        return {"ok": True, "detail": f"Logged in as {settings.pa_username}."}
    except Exception as exc:  # noqa: BLE001 — diagnostics endpoint, see docstring
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


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


def sync_topic(db: Session, topic: ForumTopic) -> tuple[int, int]:
    """Pull new posts; returns (new_posts, total_posts).

    Incremental strategy: re-fetch from the last partial page onward and skip
    already-stored post ids. Deleted posts can shift offsets — a rare case;
    a full re-sync button is a documented extension, not v1.
    """
    client = _make_client()
    existing_ids: set[int] = set(
        db.scalars(
            select(ForumPost.phpbb_post_id).where(ForumPost.topic_id == topic.id)
        )
    )

    per_page = portalanaliz.POSTS_PER_PAGE
    start = (len(existing_ids) // per_page) * per_page if existing_ids else 0
    new_posts = 0

    while True:
        page_url = portalanaliz.topic_page_url(topic.url, start)
        page = portalanaliz.parse_topic_page(client.fetch_page(page_url))

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
        if len(page.posts) < per_page:
            break  # last page reached
        start += per_page

    topic.last_synced_at = utcnow()
    topic.last_post_at = db.scalar(
        select(func.max(ForumPost.posted_at)).where(ForumPost.topic_id == topic.id)
    )
    db.commit()

    total = db.scalar(
        select(func.count()).select_from(ForumPost).where(ForumPost.topic_id == topic.id)
    )
    return new_posts, int(total or 0)
