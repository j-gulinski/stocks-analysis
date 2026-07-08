"""ORM models — the full schema from PLAN §4.

Conventions:
- Scraped series use a long/narrow format (one row per value) so new fields
  appearing on BiznesRadar never require a migration.
- Money values are stored in thousands of PLN (tys. PLN), exactly as reported.
- Timestamps are timezone-aware UTC, set client-side for portability
  (tests run on SQLite, production on PostgreSQL).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in tests).
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    # BiznesRadar canonical slug (SNT → SYNEKTIK). Report URLs MUST use it:
    # ticker URLs redirect and lose the ,Q/,Y suffix (production finding).
    br_slug: Mapped[str | None] = mapped_column(String(80))
    market: Mapped[str | None] = mapped_column(String(20))  # e.g. GPW / NewConnect
    sector: Mapped[str | None] = mapped_column(String(100))
    shares_outstanding: Mapped[int | None] = mapped_column(BigInteger)
    # Reported by the BiznesRadar profile info box, in PLN (NOT tys.).
    # Authoritative for size classification — price×shares is only a fallback
    # (a stale price / misparsed share count silently understates it).
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 0))
    enterprise_value: Mapped[float | None] = mapped_column(Numeric(20, 0))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    report_values: Mapped[list[ReportValue]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class ReportValue(Base):
    """One cell of a financial statement: (statement, freq, period, field) → value."""

    __tablename__ = "report_values"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "statement", "freq", "period", "field_code",
            name="uq_report_value_key",
        ),
        Index("ix_report_values_lookup", "company_id", "statement", "freq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    statement: Mapped[str] = mapped_column(String(10))  # income | balance | cashflow
    freq: Mapped[str] = mapped_column(String(1))  # Q | Y
    period: Mapped[str] = mapped_column(String(8))  # 2025Q1 or 2024
    field_code: Mapped[str] = mapped_column(String(80))  # BR data-field or label slug
    field_label: Mapped[str] = mapped_column(String(200))
    position: Mapped[int | None] = mapped_column(Integer)  # row order in source table
    value: Mapped[float | None] = mapped_column(Numeric(20, 2))  # tys. PLN
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship(back_populates="report_values")


class IndicatorValue(Base):
    """Historical market-value / profitability indicators (C/Z, C/WK, ROE, …)."""

    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint("company_id", "indicator", "period", name="uq_indicator_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    indicator: Mapped[str] = mapped_column(String(40))  # cz, cwk, ev_ebitda, roe, …
    period: Mapped[str] = mapped_column(String(8))
    value: Mapped[float | None] = mapped_column(Numeric(14, 4))
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Dividend(Base):
    __tablename__ = "dividends"
    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_dividend_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    dps: Mapped[float | None] = mapped_column(Numeric(10, 4))  # dividend per share, PLN
    yield_pct: Mapped[float | None] = mapped_column(Numeric(6, 2))


class Price(Base):
    """Daily close from BiznesRadar history/profile quote."""

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_price_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)


class ForumTopic(Base):
    __tablename__ = "forum_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    url: Mapped[str] = mapped_column(String(500), unique=True)
    phpbb_topic_id: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    posts: Mapped[list[ForumPost]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class ForumPost(Base):
    __tablename__ = "forum_posts"
    __table_args__ = (
        UniqueConstraint("topic_id", "phpbb_post_id", name="uq_forum_post"),
        Index("ix_forum_posts_topic_time", "topic_id", "posted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("forum_topics.id", ondelete="CASCADE"))
    phpbb_post_id: Mapped[int] = mapped_column(Integer)  # stable id from div#p{id}
    author: Mapped[str] = mapped_column(String(100))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_text: Mapped[str] = mapped_column(Text)
    content_html: Mapped[str | None] = mapped_column(Text)
    upvotes: Mapped[int | None] = mapped_column(Integer)  # forum likes/thanks, if shown

    topic: Mapped[ForumTopic] = relationship(back_populates="posts")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True
    )
    note: Mapped[str | None] = mapped_column(String(500))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship()


class Forecast(Base):
    """A saved next-quarter forecast scenario (assumptions + computed result)."""

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    label: Mapped[str | None] = mapped_column(String(120))
    assumptions: Mapped[dict] = mapped_column(JSONVariant)
    result: Mapped[dict] = mapped_column(JSONVariant)
    created_by: Mapped[str | None] = mapped_column(String(200))  # user email (Phase 6)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Analysis(Base):
    """AI analysis run (Phase 5) — schema prepared now so migrations stay linear."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(60))
    prescore: Mapped[dict | None] = mapped_column(JSONVariant)
    output: Mapped[dict | None] = mapped_column(JSONVariant)
    alignment_score: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FetchLog(Base):
    """Every outbound scraper request — powers the 24 h cache and UI freshness."""

    __tablename__ = "fetch_log"
    __table_args__ = (Index("ix_fetch_log_url_at", "url", "fetched_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    status: Mapped[int | None] = mapped_column(Integer)  # None = network error
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
