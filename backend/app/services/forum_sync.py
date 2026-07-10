"""Forum topic linking and incremental post sync (Module A service layer)."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ForumPost, ForumTopic, utcnow
from app.scrapers import portalanaliz
from app.services import forum_intelligence
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


def link_topic(
    db: Session,
    url: str,
    ticker: str,
    client: portalanaliz.ForumClient | None = None,
) -> ForumTopic:
    """Attach a forum thread URL to a company (fetches page 1 for metadata).

    `client` lets a caller reuse an already-logged-in session (e.g. discovery,
    which searches and links in one polite pass). The API path passes nothing,
    so a fresh client is built and logged in exactly as before.
    """
    company = get_or_create_company(db, ticker)

    if client is None:
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


# Bound row size: real investor write-ups are a few paragraphs at most; a
# rare wall-of-text post shouldn't blow up storage or the (already
# per-call-truncated) distiller prompt. Comfortably above anything the
# forum_distiller budget (_POST_TEXT_CHAR_BUDGET=4000) would ever use.
_CONTENT_CHAR_LIMIT = 10_000


def _truncate_content(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    return text[:_CONTENT_CHAR_LIMIT]


def _store_posts(
    db: Session,
    topic: ForumTopic,
    page: portalanaliz.TopicPage,
    existing_ids: set[int],
) -> int:
    """Store new posts (with body text); also BACKFILL content on posts that
    already exist but have no `content_text` yet — either written before this
    column existed, or synced by a page this run happens to re-fetch. A
    `mode=full` resync (`sync_topic`, which walks every page from start) is
    the realistic way to heal a whole topic's history; `sync_topic_recent`
    only backfills whatever falls inside its bounded recent-page window.
    """
    new_posts = 0

    backfill_candidate_ids = {
        post.phpbb_post_id
        for post in page.posts
        if post.phpbb_post_id in existing_ids and (post.content_text or "").strip()
    }
    backfill_rows: dict[int, ForumPost] = {}
    if backfill_candidate_ids:
        backfill_rows = {
            row.phpbb_post_id: row
            for row in db.scalars(
                select(ForumPost).where(
                    ForumPost.topic_id == topic.id,
                    ForumPost.phpbb_post_id.in_(backfill_candidate_ids),
                    ForumPost.content_text.is_(None),
                )
            )
        }

    for post in page.posts:
        if post.phpbb_post_id in existing_ids:
            row = backfill_rows.get(post.phpbb_post_id)
            if row is not None:
                row.content_text = _truncate_content(post.content_text)
            continue
        db.add(
            ForumPost(
                topic_id=topic.id,
                phpbb_post_id=post.phpbb_post_id,
                author=post.author,
                posted_at=post.posted_at,
                upvotes=post.upvotes,
                content_text=_truncate_content(post.content_text),
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
    pages: list[portalanaliz.TopicPage] = []

    while True:
        page_url = portalanaliz.topic_page_url(topic.url, start)
        page = portalanaliz.parse_topic_page(client.fetch_page(page_url))
        pages.append(page)
        new_posts += _store_posts(db, topic, page, existing_ids)
        if len(page.posts) < per_page:
            break  # last page reached
        start += per_page

    forum_intelligence.update_for_topic_pages(db, topic, pages)
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

    forum_intelligence.update_for_topic_pages(db, topic, pages)
    return new_posts, _finish_sync(db, topic)


# ----------------------------------------------------------- topic discovery

@dataclass
class DiscoveryResult:
    """Outcome of a forum-search discovery pass (see discover_and_link_topics)."""

    linked: list[ForumTopic] = field(default_factory=list)
    searches: int = 0  # search.php GETs made (hard cap 2)
    candidates: int = 0  # distinct title-matching topics found


def _title_matches(title: str | None, ticker: str, company_name: str | None) -> bool:
    """A PA topic title belongs to this company.

    Convention on PA is "(TICKER) NAME" (e.g. "(DCR) DECORA"), so the ticker in
    parentheses is the strong signal; the full company name is a softer fallback
    for threads that omit the ticker tag. `(dcr)` never matches `(dcrx)` — the
    closing paren makes the substring test effectively exact-in-parens.
    """
    if not title:
        return False
    low = title.lower()
    if f"({ticker.lower()})" in low:
        return True
    if company_name and company_name.strip() and company_name.strip().lower() in low:
        return True
    return False


def discover_and_link_topics(
    db: Session,
    client: portalanaliz.ForumClient,
    company: Company,
    *,
    max_new: int = 3,
) -> DiscoveryResult:
    """Find + auto-link this company's PA threads via the forum search.

    Bounded and polite: one search for the ticker; if nothing matches, ONE
    fallback search for the first word of the company name (2 GETs max). Topics
    whose title matches (TICKER)/name are linked through `link_topic` (reusing
    the passed logged-in session — no extra login), skipping already-linked
    ones, capped at `max_new`. Guest-block → relogin + retry the search once.
    """
    from app.db.models import Company as _Company  # noqa: F401 (type clarity only)

    ticker = company.ticker
    name = company.name

    # phpBB topic ids are globally unique, so a global set is the dedupe key.
    linked_ids: set[int] = {
        tid
        for tid in db.scalars(
            select(ForumTopic.phpbb_topic_id).where(ForumTopic.phpbb_topic_id.is_not(None))
        )
        if tid is not None
    }

    result = DiscoveryResult()

    def gather(query: str) -> list[dict]:
        result.searches += 1
        rows = portalanaliz.search_recent_posts(client, query)
        seen: set[int] = set()
        matched: list[dict] = []
        for row in rows:  # search results come newest-first
            tid = row.get("topic_phpbb_id")
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            if _title_matches(row.get("topic_title"), ticker, name):
                matched.append(row)
        return matched

    # 1) ticker search, with a single relogin+retry if the session got bounced.
    try:
        candidates = gather(ticker)
    except portalanaliz.NeedsLoginError:
        settings = get_settings()
        if not (settings.pa_username and settings.pa_password):
            raise
        client.login(settings.pa_username, settings.pa_password)
        candidates = gather(ticker)  # the one permitted retry (consumes budget)

    # 2) fallback to the first name word ONLY if we still have budget + no hits.
    if not candidates and name and name.strip() and result.searches < 2:
        first_word = name.strip().split()[0]
        if first_word.lower() != ticker.lower():
            candidates = gather(first_word)

    result.candidates = len(candidates)

    # 3) link up to max_new brand-new topics, reusing the logged-in session.
    for row in candidates:
        if len(result.linked) >= max_new:
            break
        tid = row.get("topic_phpbb_id")
        if tid is not None and tid in linked_ids:
            continue
        try:
            topic = link_topic(db, row["topic_url"], ticker, client=client)
        except TopicAlreadyLinkedError:
            continue
        if tid is not None:
            linked_ids.add(tid)
        result.linked.append(topic)

    return result
