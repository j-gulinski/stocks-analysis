"""Forum endpoints: topic linking, sync, post reading, credentials check."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ForumPageOut,
    ForumPostOut,
    ForumSyncOut,
    ForumTopicOut,
    TopicLinkIn,
)
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Company, ForumPost, ForumTopic
from app.scrapers import portalanaliz
from app.scrapers.http import FetchError
from app.services import forum_sync

router = APIRouter(tags=["forum"])


@router.post(
    "/forum/topics", response_model=ForumTopicOut, status_code=status.HTTP_201_CREATED
)
def link_topic(payload: TopicLinkIn, db: Session = Depends(get_db)) -> ForumTopic:
    try:
        return forum_sync.link_topic(db, payload.url, payload.ticker)
    except forum_sync.TopicAlreadyLinkedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except (portalanaliz.ForumError, FetchError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/forum/topics/{topic_id}/sync", response_model=ForumSyncOut)
def sync_topic(
    topic_id: int,
    mode: Literal["recent", "full"] = "recent",
    db: Session = Depends(get_db),
) -> ForumSyncOut:
    topic = db.get(ForumTopic, topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No topic with id {topic_id}."
        )
    try:
        if mode == "full":
            new_posts, total = forum_sync.sync_topic(db, topic)
        else:
            new_posts, total = forum_sync.sync_topic_recent(db, topic)
    except (portalanaliz.ForumError, FetchError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return ForumSyncOut(topic_id=topic.id, new_posts=new_posts, total_posts=total)


@router.get("/forum/login-status")
def login_status() -> dict:
    """Report configuration only; a GET never attempts a remote login."""
    settings = get_settings()
    configured = bool(settings.pa_username and settings.pa_password)
    return {
        "ok": configured,
        "status": "configured" if configured else "not_configured",
        "detail": (
            "PortalAnaliz credentials are configured; login is attempted only "
            "by an explicit forum command."
            if configured
            else "PA_USERNAME / PA_PASSWORD not configured."
        ),
    }


@router.post("/forum/login-status/check")
def check_login_status() -> dict:
    """Explicitly verify PortalAnaliz credentials with one polite login."""
    return forum_sync.check_login()


@router.get("/companies/{ticker}/forum", response_model=ForumPageOut)
def get_company_posts(
    ticker: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    author: str | None = None,
    sort: str = Query(default="new", pattern="^(new|top)$"),
    db: Session = Depends(get_db),
) -> ForumPageOut:
    """Posts across all topics linked to the company.

    sort=new → newest first; sort=top → most upvoted first (posts without a
    vote count go last) — the ordering the AI layer will use to budget tokens.
    """
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown company '{ticker}'."
        )

    conditions = [ForumTopic.company_id == company.id]
    if author:
        conditions.append(ForumPost.author == author)

    base_query = (
        select(ForumPost)
        .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
        .where(*conditions)
    )
    total = db.scalar(
        select(func.count()).select_from(base_query.subquery())
    )
    if sort == "top":
        ordering = (ForumPost.upvotes.desc().nulls_last(), ForumPost.posted_at.desc())
    else:
        ordering = (ForumPost.posted_at.desc(),)
    posts = db.scalars(
        base_query.order_by(*ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ForumPageOut(
        total=int(total or 0),
        page=page,
        page_size=page_size,
        posts=[ForumPostOut.model_validate(p) for p in posts],
    )


@router.get("/companies/{ticker}/forum/topics", response_model=list[ForumTopicOut])
def get_company_topics(ticker: str, db: Session = Depends(get_db)) -> list[ForumTopic]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown company '{ticker}'."
        )
    return db.scalars(
        select(ForumTopic).where(ForumTopic.company_id == company.id)
    ).all()
