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
    # Logical lineage link (kept unconstrained for portable additive SQLite
    # migrations); evidence tests enforce that referenced facts exist.
    source_fact_id: Mapped[int | None] = mapped_column(Integer, index=True)
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
    source_fact_id: Mapped[int | None] = mapped_column(Integer, index=True)
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


class CompanyMarketData(Base):
    """Priority market/premium facts for the AI prompt pipeline.

    This compact row keeps the context Claude needs close at hand: industry
    type, premium consensus, ROIC/FCF/EV, and FCF dividend coverage. The normal
    statement/indicator tables remain the source of truth for raw numerics.
    """

    __tablename__ = "company_market_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True
    )
    industry_type: Mapped[str | None] = mapped_column(String(80))
    priority_values: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    forecast_consensus: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    advanced_metrics: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    dividend_coverage: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


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
    upvotes: Mapped[int | None] = mapped_column(Integer)  # forum likes/thanks, if shown
    # Raw post body (plain text, HTML stripped) — the parser has always
    # produced this (ParsedPost.content_text) but syncs used to discard it,
    # so nothing fed the AI distiller. Nullable: rows written before this
    # column existed have NULL until a resync backfills them (see
    # forum_sync._store_posts). Truncated at storage time — see
    # forum_sync._CONTENT_CHAR_LIMIT for why.
    content_text: Mapped[str | None] = mapped_column(Text)

    topic: Mapped[ForumTopic] = relationship(back_populates="posts")


class ForumIntelligence(Base):
    """Structured PortalAnaliz intelligence, without raw forum message bodies."""

    __tablename__ = "forum_intelligence"
    __table_args__ = (
        UniqueConstraint("company_id", "source", name="uq_forum_intelligence_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(60), default="portal_analiz")
    industry_type: Mapped[str | None] = mapped_column(String(80))
    last_30d_post_count: Mapped[int] = mapped_column(Integer, default=0)
    last_30d_active_user_count: Mapped[int] = mapped_column(Integer, default=0)
    activity_spikes: Mapped[list] = mapped_column(JSONVariant, default=list)
    community_sentiment: Mapped[str | None] = mapped_column(String(30))
    distilled_facts: Mapped[list] = mapped_column(JSONVariant, default=list)
    # AI-distilled investment expectations (services/forum_expectations.py,
    # P5.9b): {"claims": [DistilledClaim dicts], "model", "updated_at",
    # "source_post_count"}. Separate from `distilled_facts` (the cheap
    # keyword-heuristic pass above) — this is the Claude-classified read the
    # verdict prompt prefers when present (see api/analyses.py). Nullable:
    # no ANTHROPIC_API_KEY configured means this column simply stays empty.
    expectations: Mapped[dict | None] = mapped_column(JSONVariant)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


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
    """A reproducible AI analysis run.

    The legacy table name stays in place until the RT1.3 orchestrator migration
    consolidates every analysis producer. A row is inserted *before* provider
    work starts, so failed and interrupted attempts remain auditable instead of
    disappearing.
    """

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str | None] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(80), default="investment_verdict")
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prescore: Mapped[dict | None] = mapped_column(JSONVariant)
    input_snapshot: Mapped[dict | None] = mapped_column(JSONVariant)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    evidence_ids: Mapped[dict | None] = mapped_column(JSONVariant)
    skill_version: Mapped[str | None] = mapped_column(String(120))
    skill_hash: Mapped[str | None] = mapped_column(String(80))
    model_configuration: Mapped[dict | None] = mapped_column(JSONVariant)
    idempotency_key_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output: Mapped[dict | None] = mapped_column(JSONVariant)
    validation: Mapped[dict | None] = mapped_column(JSONVariant)
    alignment_score: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(14, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    model_calls: Mapped[list[ModelCall]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class ModelCall(Base):
    """One provider attempt made as part of an analysis run."""

    __tablename__ = "model_calls"
    __table_args__ = (
        Index("ix_model_calls_analysis_role", "analysis_id", "role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    operation_key: Mapped[str | None] = mapped_column(String(200))
    contract_name: Mapped[str | None] = mapped_column(String(100))
    contract_version: Mapped[str | None] = mapped_column(String(40))
    request_hash: Mapped[str | None] = mapped_column(String(80))
    output: Mapped[dict | None] = mapped_column(JSONVariant)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    finish_reason: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(80))
    # Logical self-reference kept unconstrained so SQLite migrations remain
    # portable; executor tests ensure it points at an existing successful call.
    cache_source_call_id: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    billed: Mapped[bool | None] = mapped_column()
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(14, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    analysis: Mapped[Analysis] = relationship(back_populates="model_calls")


class AiUsageDaily(Base):
    """Atomic daily reservations and measured model usage per provider."""

    __tablename__ = "ai_usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    logical_operations: Mapped[int] = mapped_column(Integer, default=0)
    provider_attempts: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    billable_calls: Mapped[int] = mapped_column(Integer, default=0)
    unknown_billing_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SourceDocument(Base):
    """Stable identity for one externally published/fetched document URL."""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "company_ticker",
            "source_name",
            "source_type",
            "scope_key",
            name="uq_source_document_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_ticker: Mapped[str] = mapped_column(String(12), index=True)
    source_name: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    scope_key: Mapped[str] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500))
    period: Mapped[str | None] = mapped_column(String(40))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    latest_content_hash: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(120))
    parser_version: Mapped[str] = mapped_column(String(120))
    last_fetch_status: Mapped[int | None] = mapped_column(Integer)


class DocumentVersion(Base):
    """Immutable raw content version; identical re-fetches reuse one row."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id", "content_hash", name="uq_document_version_hash"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    requested_url: Mapped[str] = mapped_column(String(1000))
    effective_url: Mapped[str] = mapped_column(String(1000))
    response_status: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(120))
    parser_version: Mapped[str] = mapped_column(String(120))
    parse_status: Mapped[str] = mapped_column(String(40), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    raw_content: Mapped[str] = mapped_column(Text)


class Fact(Base):
    """Typed, point-in-time fact extracted from an immutable document version."""

    __tablename__ = "facts"
    __table_args__ = (
        UniqueConstraint("source_version_id", "fact_hash", name="uq_fact_version_hash"),
        Index("ix_facts_company_known_key", "company_id", "known_at", "fact_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_ticker: Mapped[str] = mapped_column(String(12), index=True)
    source_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    fact_type: Mapped[str] = mapped_column(String(80))
    fact_key: Mapped[str] = mapped_column(String(200))
    fact_hash: Mapped[str] = mapped_column(String(64))
    numeric_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(80))
    period: Mapped[str | None] = mapped_column(String(40))
    effective_date: Mapped[date | None] = mapped_column(Date)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    locator: Mapped[dict] = mapped_column(JSONVariant)
    extractor_version: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    verification_state: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    """Material company event linked to the version that disclosed it."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_ticker: Mapped[str] = mapped_column(String(12), index=True)
    source_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claims: Mapped[list] = mapped_column(JSONVariant)
    verification_state: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataConflict(Base):
    """Explicit disagreement between two facts; never silently overwrite it."""

    __tablename__ = "data_conflicts"
    __table_args__ = (
        UniqueConstraint(
            "left_fact_id", "right_fact_id", name="uq_data_conflict_fact_pair"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_ticker: Mapped[str] = mapped_column(String(12), index=True)
    fact_key: Mapped[str] = mapped_column(String(200), index=True)
    period: Mapped[str | None] = mapped_column(String(40))
    left_fact_id: Mapped[int] = mapped_column(
        ForeignKey("facts.id", ondelete="CASCADE")
    )
    right_fact_id: Mapped[int] = mapped_column(
        ForeignKey("facts.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    resolution_rule: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    """One Codex-operated workflow run.

    This is the durable audit trail for CX workflows: what was requested, which
    role/model handled it, and what changed. UI-visible analysis lives in
    `analysis_runs`; this row tracks the broader orchestration.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_status_created", "status", "created_at"),
        Index("ix_agent_runs_workflow_created", "workflow", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(80))
    trigger: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    model_role: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    orchestrator_model: Mapped[str | None] = mapped_column(String(80))
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160), unique=True, index=True
    )
    inputs: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    outputs: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AnalysisRun(Base):
    """Provider-neutral analysis visible to the app after Codex/API workflows."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_runs_company_created", "company_id", "created_at"),
        Index("ix_analysis_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(40), default="codex_skill")
    workflow: Mapped[str] = mapped_column(String(80))
    model_role: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    verification_status: Mapped[str] = mapped_column(String(30), default="pending")
    input_snapshot: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    output: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    verification: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    alignment_score: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VerificationRun(Base):
    """Strict verifier result for an agent/analysis run."""

    __tablename__ = "verification_runs"
    __table_args__ = (
        Index("ix_verification_runs_agent_created", "agent_run_id", "created_at"),
        Index("ix_verification_runs_analysis_created", "analysis_run_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    model_role: Mapped[str] = mapped_column(String(40), default="verifier_strict")
    verifier_model: Mapped[str] = mapped_column(String(80))
    verdict: Mapped[str] = mapped_column(String(30))
    checks: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventReport(Base):
    """ESPI/EBI or other source event tied to a company."""

    __tablename__ = "event_reports"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_event_report_source_id"),
        Index("ix_event_reports_company_published", "company_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(120))
    raw_url: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    title: Mapped[str | None] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    materiality: Mapped[dict] = mapped_column(JSONVariant, default=dict)


class CandidateRun(Base):
    """One saved candidate-screening result for a company."""

    __tablename__ = "candidate_runs"
    __table_args__ = (
        Index("ix_candidate_runs_company_created", "company_id", "created_at"),
        Index("ix_candidate_runs_score_created", "score", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    workflow: Mapped[str] = mapped_column(String(80), default="stock-candidate-scout")
    model_role: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    verification_status: Mapped[str] = mapped_column(String(30), default="pending")
    reasons: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    missing_data: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestRun(Base):
    """A deterministic replay run, optionally interpreted by Codex."""

    __tablename__ = "backtest_runs"
    __table_args__ = (Index("ix_backtest_runs_strategy_created", "strategy", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    strategy: Mapped[str] = mapped_column(String(80))
    from_date: Mapped[date | None] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    model_role: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    parameters: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    summary: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    verification_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestObservation(Base):
    """One point-in-time company observation inside a backtest run."""

    __tablename__ = "backtest_observations"
    __table_args__ = (
        Index("ix_backtest_observations_run_date", "backtest_run_id", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE")
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date)
    known_inputs: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    signal: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    outcome: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentEvaluationRun(Base):
    """Replay saved agent outputs against future outcomes."""

    __tablename__ = "agent_evaluation_runs"
    __table_args__ = (
        Index(
            "ix_agent_evaluation_runs_strategy_created",
            "strategy",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    strategy: Mapped[str] = mapped_column(String(80))
    from_date: Mapped[date | None] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    model_role: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    parameters: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    summary: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    verification_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentEvaluationObservation(Base):
    """One saved agent prediction with future outcomes attached."""

    __tablename__ = "agent_evaluation_observations"
    __table_args__ = (
        Index(
            "ix_agent_evaluation_observations_run_created",
            "evaluation_run_id",
            "as_of_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_evaluation_runs.id", ondelete="CASCADE")
    )
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE")
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date)
    known_inputs: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    prediction: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    outcome: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    score: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FetchLog(Base):
    """Every outbound scraper request — powers the 24 h cache and UI freshness."""

    __tablename__ = "fetch_log"
    __table_args__ = (Index("ix_fetch_log_url_at", "url", "fetched_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    status: Mapped[int | None] = mapped_column(Integer)  # None = network error
    document_version_id: Mapped[int | None] = mapped_column(Integer, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
