"""Durable ORM model for evidence, research and portfolio state.

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
    Float,
    CheckConstraint,
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


class CompanyReportSchedule(Base):
    """One source-linked observation of the company's next periodic report."""

    __tablename__ = "company_report_schedules"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_version_id",
            name="uq_company_report_schedule_source_version",
        ),
        CheckConstraint(
            "source_status IN ('scheduled', 'unavailable')",
            name="ck_company_report_schedule_source_status",
        ),
        CheckConstraint(
            "automation_status IN ('not-eligible', 'scheduled', 'blocked', 'already-covered')",
            name="ck_company_report_schedule_automation_status",
        ),
        Index(
            "ix_company_report_schedules_company_observed",
            "company_id",
            "observed_at",
        ),
        Index("ix_company_report_schedules_report_date", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"), index=True
    )
    report_date: Mapped[date | None] = mapped_column(Date)
    report_label: Mapped[str | None] = mapped_column(String(160))
    source_status: Mapped[str] = mapped_column(String(30))
    automation_status: Mapped[str] = mapped_column(
        String(30), default="not-eligible"
    )
    automation_reason: Mapped[str | None] = mapped_column(String(500))
    research_agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True
    )
    valuation_agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchCase(Base):
    """Durable workflow root for one company and research purpose."""

    __tablename__ = "research_cases"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "purpose", name="uq_research_case_company_purpose"
        ),
        CheckConstraint(
            "origin IN ('manual', 'discover', 'portfolio')",
            name="ck_research_case_origin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(80), default="investment-research")
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    state: Mapped[str] = mapped_column(String(40), default="new", index=True)
    current_step: Mapped[str] = mapped_column(String(40), default="ingest")
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CompanyProfile(Base):
    """Immutable, versioned research tailoring for one case."""

    __tablename__ = "company_profiles"
    __table_args__ = (
        UniqueConstraint(
            "research_case_id", "version", name="uq_company_profile_case_version"
        ),
        CheckConstraint("version > 0", name="ck_company_profile_positive_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    research_case_id: Mapped[int] = mapped_column(
        ForeignKey("research_cases.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(40))
    archetype: Mapped[str] = mapped_column(String(40), index=True)
    archetype_version: Mapped[str] = mapped_column(String(40))
    company_overlay: Mapped[dict] = mapped_column(JSONVariant)
    drivers: Mapped[list] = mapped_column(JSONVariant)
    kpis: Mapped[list] = mapped_column(JSONVariant)
    provenance: Mapped[str] = mapped_column(String(40), default="codex-proposed")
    reason: Mapped[str | None] = mapped_column(String(1000))
    based_on_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ResearchSnapshot(Base):
    """Canonical immutable UI artifact produced by one leased research run."""

    __tablename__ = "research_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "research_case_id", "version", name="uq_research_snapshot_case_version"
        ),
        UniqueConstraint("agent_run_id", name="uq_research_snapshot_agent_run"),
        UniqueConstraint(
            "verification_run_id", name="uq_research_snapshot_verification_run"
        ),
        CheckConstraint("version > 0", name="ck_research_snapshot_positive_version"),
        CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_research_snapshot_status",
        ),
        Index("ix_research_snapshots_case_created", "research_case_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    research_case_id: Mapped[int] = mapped_column(
        ForeignKey("research_cases.id", ondelete="CASCADE"), index=True
    )
    company_profile_id: Mapped[int] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True
    )
    verification_run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_runs.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    contract_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(128))
    artifact_fingerprint: Mapped[str] = mapped_column(String(64))
    sections: Mapped[dict] = mapped_column(JSONVariant)
    source_manifest: Mapped[list] = mapped_column(JSONVariant)
    conflicts: Mapped[list] = mapped_column(JSONVariant)
    gaps: Mapped[list] = mapped_column(JSONVariant)
    next_checks: Mapped[list] = mapped_column(JSONVariant)
    statement_provenance: Mapped[list] = mapped_column(JSONVariant)
    verifier_result: Mapped[dict] = mapped_column(JSONVariant)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ValuationSnapshot(Base):
    """Canonical immutable valuation produced from one research snapshot."""

    __tablename__ = "valuation_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "research_case_id", "version", name="uq_valuation_snapshot_case_version"
        ),
        UniqueConstraint("agent_run_id", name="uq_valuation_snapshot_agent_run"),
        UniqueConstraint(
            "verification_run_id", name="uq_valuation_snapshot_verification_run"
        ),
        CheckConstraint("version > 0", name="ck_valuation_snapshot_positive_version"),
        CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_valuation_snapshot_status",
        ),
        Index("ix_valuation_snapshots_case_created", "research_case_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    research_case_id: Mapped[int] = mapped_column(
        ForeignKey("research_cases.id", ondelete="CASCADE"), index=True
    )
    research_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("research_snapshots.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    verification_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("verification_runs.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer)
    contract_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), index=True)
    origin: Mapped[str] = mapped_column(String(20), default="codex")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    template_id: Mapped[str] = mapped_column(String(80))
    template_version: Mapped[str] = mapped_column(String(60))
    calculation_engine_version: Mapped[str] = mapped_column(String(60))
    assumptions: Mapped[dict] = mapped_column(JSONVariant)
    base_values: Mapped[dict] = mapped_column(JSONVariant)
    deterministic_outputs: Mapped[dict] = mapped_column(JSONVariant)
    codex_judgment: Mapped[dict] = mapped_column(JSONVariant)
    input_manifest: Mapped[dict] = mapped_column(JSONVariant)
    gaps: Mapped[list] = mapped_column(JSONVariant)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    calculation_fingerprint: Mapped[str] = mapped_column(String(64))
    artifact_fingerprint: Mapped[str] = mapped_column(String(64))
    verifier_result: Mapped[dict] = mapped_column(JSONVariant)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ResearchCaseStepHistory(Base):
    """Append-only human-recorded workflow transition for a research case."""

    __tablename__ = "research_case_step_history"
    __table_args__ = (
        Index("ix_case_step_history_case_created", "research_case_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    research_case_id: Mapped[int] = mapped_column(
        ForeignKey("research_cases.id", ondelete="CASCADE"), index=True
    )
    from_state: Mapped[str | None] = mapped_column(String(40))
    from_step: Mapped[str | None] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    to_step: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ReportValue(Base):
    """One cell of a financial statement: (statement, freq, period, field) → value."""

    __tablename__ = "report_values"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "statement",
            "freq",
            "period",
            "field_code",
            name="uq_report_value_key",
        ),
        Index("ix_report_values_lookup", "company_id", "statement", "freq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
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
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    company: Mapped[Company] = relationship(back_populates="report_values")


class IndicatorValue(Base):
    """Historical market-value / profitability indicators (C/Z, C/WK, ROE, …)."""

    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint("company_id", "indicator", "period", name="uq_indicator_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    indicator: Mapped[str] = mapped_column(String(40))  # cz, cwk, ev_ebitda, roe, …
    period: Mapped[str] = mapped_column(String(8))
    value: Mapped[float | None] = mapped_column(Numeric(14, 4))
    source_fact_id: Mapped[int | None] = mapped_column(Integer, index=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Dividend(Base):
    __tablename__ = "dividends"
    __table_args__ = (UniqueConstraint("company_id", "year", name="uq_dividend_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    year: Mapped[int] = mapped_column(Integer)
    dps: Mapped[float | None] = mapped_column(Numeric(10, 4))  # dividend per share, PLN
    yield_pct: Mapped[float | None] = mapped_column(Numeric(6, 2))


class Price(Base):
    """Daily close plus when the workbench learned the source row.

    Older rows may have no availability timestamp; strict historical replay
    excludes them rather than pretending their original publication time is
    known.
    """

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_price_day"),
        CheckConstraint(
            "adjustment_status IN ('unknown', 'raw_unverified', 'split_adjusted', 'total_return')",
            name="ck_prices_adjustment_status",
        ),
        CheckConstraint(
            "adjustment_status NOT IN ('split_adjusted', 'total_return') OR "
            "(source_name IS NOT NULL AND length(trim(source_name)) > 0 AND "
            "series_key IS NOT NULL AND length(trim(series_key)) > 0 AND "
            "basis_version IS NOT NULL AND length(trim(basis_version)) > 0)",
            name="ck_prices_eligible_provenance",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    # Serving rows may be replaced as providers correct history, but every
    # lineage-complete row points back to the immutable raw document version
    # from which it can be rebuilt.
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    source_name: Mapped[str | None] = mapped_column(String(80))
    series_key: Mapped[str | None] = mapped_column(String(160), index=True)
    basis_version: Mapped[str | None] = mapped_column(String(80))
    adjustment_status: Mapped[str] = mapped_column(
        String(40), default="unknown", server_default="unknown", index=True
    )
    scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, default=utcnow
    )


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


class ForumIntelligence(Base):
    """Structured PortalAnaliz intelligence, without raw forum message bodies."""

    __tablename__ = "forum_intelligence"
    __table_args__ = (
        UniqueConstraint("company_id", "source", name="uq_forum_intelligence_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
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
    # Research drafting prefers the classified read when present. Nullable:
    # no ANTHROPIC_API_KEY configured means this column simply stays empty.
    expectations: Mapped[dict | None] = mapped_column(JSONVariant)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DecisionJournalEntry(Base):
    """Append-only investor decision context for one company.

    This is the user's historical record, not an AI recommendation. The
    thesis snapshot is copied at entry time so later dossier changes cannot
    rewrite what the decision was based on.
    """

    __tablename__ = "decision_journal_entries"
    __table_args__ = (
        Index(
            "ix_decision_journal_company_created",
            "company_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[int] = mapped_column(Integer)
    thesis: Mapped[str] = mapped_column(Text)
    invalidation: Mapped[str] = mapped_column(Text)
    next_check: Mapped[str] = mapped_column(Text)
    review_date: Mapped[date] = mapped_column(Date)
    thesis_snapshot: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    thesis_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ThesisFalsifier(Base):
    """Explicit user-managed condition that can put a thesis at risk.

    Status is never inferred from a metric or model. Every state change carries
    a human/evidence reason so a fired falsifier remains auditable.
    """

    __tablename__ = "thesis_falsifiers"
    __table_args__ = (
        UniqueConstraint("company_id", "key", name="uq_thesis_falsifier_company_key"),
        Index("ix_thesis_falsifiers_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="holding", index=True)
    reason: Mapped[str] = mapped_column(Text)
    review_date: Mapped[date | None] = mapped_column(Date)
    thesis_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Portfolio(Base):
    """One explicitly configured provider portfolio; credentials remain in env."""

    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("provider", "provider_ref", name="uq_portfolio_provider_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), default="myfund")
    provider_ref: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(160))
    base_currency: Mapped[str] = mapped_column(String(8), default="PLN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PortfolioSync(Base):
    __tablename__ = "portfolio_syncs"
    __table_args__ = (
        Index("ix_portfolio_syncs_portfolio_requested", "portfolio_id", "requested_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    provider_status_code: Mapped[str | None] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(String(500))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(
        String(40), default="myfund-portfolio-v1"
    )
    reused_snapshot: Mapped[bool] = mapped_column(default=False)
    coverage_version: Mapped[str | None] = mapped_column(String(40))
    coverage_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    coverage_decisions: Mapped[list] = mapped_column(JSONVariant, default=list)


class InstrumentMapping(Base):
    __tablename__ = "instrument_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_key", name="uq_instrument_mapping_provider_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_key: Mapped[str] = mapped_column(String(200))
    provider_ticker: Mapped[str | None] = mapped_column(String(80))
    provider_name: Mapped[str] = mapped_column(String(300))
    provider_type: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str | None] = mapped_column(String(8))
    mapping_kind: Mapped[str] = mapped_column(String(20))
    mapping_status: Mapped[str] = mapped_column(String(20))
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "version", name="uq_portfolio_snapshot_version"
        ),
        CheckConstraint("version > 0", name="ck_portfolio_snapshot_positive_version"),
        Index("ix_portfolio_snapshots_portfolio_as_of", "portfolio_id", "as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    currency: Mapped[str] = mapped_column(String(8))
    total_value: Mapped[float] = mapped_column(Numeric(20, 2))
    cost_basis: Mapped[float | None] = mapped_column(Numeric(20, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(20, 2))
    cash_value: Mapped[float | None] = mapped_column(Numeric(20, 2))
    benchmark_name: Mapped[str | None] = mapped_column(String(160))
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    gaps: Mapped[list] = mapped_column(JSONVariant, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class PortfolioPositionSnapshot(Base):
    __tablename__ = "portfolio_position_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "provider_row_key", name="uq_portfolio_position_row"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), index=True
    )
    mapping_id: Mapped[int] = mapped_column(
        ForeignKey("instrument_mappings.id", ondelete="RESTRICT"), index=True
    )
    mapping_kind: Mapped[str] = mapped_column(String(20))
    mapping_status: Mapped[str] = mapped_column(String(20))
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    provider_row_key: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str | None] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(300))
    asset_type: Mapped[str | None] = mapped_column(String(100))
    sector: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(8))
    quote_date: Mapped[date | None] = mapped_column(Date)
    quote: Mapped[float | None] = mapped_column(Numeric(20, 6))
    quantity: Mapped[float | None] = mapped_column(Numeric(24, 8))
    value: Mapped[float] = mapped_column(Numeric(20, 2))
    cost_basis: Mapped[float | None] = mapped_column(Numeric(20, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(20, 2))
    allocation_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))


class PortfolioValuePoint(Base):
    __tablename__ = "portfolio_value_points"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "date", name="uq_portfolio_value_point_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[float | None] = mapped_column(Numeric(20, 2))
    contributed: Mapped[float | None] = mapped_column(Numeric(20, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(20, 2))
    provider_return_pct: Mapped[float | None] = mapped_column(Numeric(14, 6))
    benchmark_return_pct: Mapped[float | None] = mapped_column(Numeric(14, 6))
    daily_change: Mapped[float | None] = mapped_column(Numeric(20, 6))


class PortfolioReviewSnapshot(Base):
    """Canonical immutable Codex interpretation of one frozen portfolio snapshot."""

    __tablename__ = "portfolio_review_snapshots"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "version", name="uq_portfolio_review_version"),
        UniqueConstraint("agent_run_id", name="uq_portfolio_review_agent_run"),
        UniqueConstraint(
            "verification_run_id", name="uq_portfolio_review_verification_run"
        ),
        CheckConstraint("version > 0", name="ck_portfolio_review_positive_version"),
        CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_portfolio_review_status",
        ),
        Index("ix_portfolio_review_portfolio_created", "portfolio_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    portfolio_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True
    )
    verification_run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_runs.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    contract_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), index=True)
    draft_requested_model_role: Mapped[str] = mapped_column(String(40))
    draft_requested_model: Mapped[str] = mapped_column(String(80))
    draft_reasoning_effort: Mapped[str] = mapped_column(String(20))
    draft_actual_host_model: Mapped[str] = mapped_column(String(160))
    draft_substitution_or_escalation: Mapped[str | None] = mapped_column(String(1000))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sections: Mapped[dict] = mapped_column(JSONVariant)
    input_manifest: Mapped[dict] = mapped_column(JSONVariant)
    gaps: Mapped[list] = mapped_column(JSONVariant)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    analytics_fingerprint: Mapped[str] = mapped_column(String(64))
    draft_fingerprint: Mapped[str] = mapped_column(String(64))
    artifact_fingerprint: Mapped[str] = mapped_column(String(64))
    verifier_result: Mapped[dict] = mapped_column(JSONVariant)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


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
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
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
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AgentRun(Base):
    """One Codex-operated workflow run.

    This is the durable audit trail for canonical workflows: what was
    requested, which role/model handled it, and what changed.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_status_created", "status", "created_at"),
        Index(
            "ix_agent_runs_status_priority_created",
            "status",
            "queue_priority",
            "created_at",
        ),
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
    queue_priority: Mapped[float] = mapped_column(Numeric(20, 6), default=0)
    inputs: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    outputs: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(160), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # A future review is durable but cannot be claimed before this timestamp.
    # It never wakes Codex by itself; a user-invoked worker claims it once due.
    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VerificationRun(Base):
    """Strict verifier result for one canonical AgentRun artifact."""

    __tablename__ = "verification_runs"
    __table_args__ = (
        Index("ix_verification_runs_agent_created", "agent_run_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    model_role: Mapped[str] = mapped_column(String(40), default="verifier_strict")
    verifier_model: Mapped[str] = mapped_column(String(80))
    verdict: Mapped[str] = mapped_column(String(30))
    checks: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


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
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    title: Mapped[str | None] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    materiality: Mapped[dict] = mapped_column(JSONVariant, default=dict)


class ListPollState(Base):
    """Durable completeness watermark for one list-style source."""

    __tablename__ = "list_poll_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_target_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_next_offset: Mapped[int | None] = mapped_column()
    scan_next_limit: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FetchLog(Base):
    """Every outbound scraper request — powers the 24 h cache and UI freshness."""

    __tablename__ = "fetch_log"
    __table_args__ = (Index("ix_fetch_log_url_at", "url", "fetched_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    status: Mapped[int | None] = mapped_column(Integer)  # None = network error
    document_version_id: Mapped[int | None] = mapped_column(Integer, index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class MarketFactorBatch(Base):
    """One versioned market-wide factor snapshot feeding the single sieve (V1).

    Binds the immutable BiznesRadar market pages (DocumentVersion ids) that
    were parsed into rows, so sieve output is reproducible per batch.
    """

    __tablename__ = "market_factor_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    page_document_versions: Mapped[dict] = mapped_column(JSONVariant)
    parser_version: Mapped[str] = mapped_column(String(40))
    coverage: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketFactorRow(Base):
    """Per-company factor values parsed from one market batch."""

    __tablename__ = "market_factor_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "ticker", name="uq_market_factor_row_batch_ticker"),
        Index("ix_market_factor_rows_batch_ticker", "batch_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("market_factor_batches.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    br_slug: Mapped[str | None] = mapped_column(String(120))
    name: Mapped[str | None] = mapped_column(String(200))
    report_period: Mapped[str | None] = mapped_column(String(20))
    altman_grade: Mapped[str | None] = mapped_column(String(8))
    altman_value: Mapped[float | None] = mapped_column(Float)
    piotroski_f: Mapped[float | None] = mapped_column(Float)
    cz: Mapped[float | None] = mapped_column(Float)
    cz_delta_rr_pct: Mapped[float | None] = mapped_column(Float)
    cwk: Mapped[float | None] = mapped_column(Float)
    ev_ebitda: Mapped[float | None] = mapped_column(Float)
    roe_pct: Mapped[float | None] = mapped_column(Float)
    op_margin_pct: Mapped[float | None] = mapped_column(Float)
    op_margin_delta_pp: Mapped[float | None] = mapped_column(Float)
    net_margin_pct: Mapped[float | None] = mapped_column(Float)
    revenue_dyn_rr_pct: Mapped[float | None] = mapped_column(Float)
    net_income_dyn_rr_pct: Mapped[float | None] = mapped_column(Float)
    debt_to_equity: Mapped[float | None] = mapped_column(Float)
    net_debt_ebitda: Mapped[float | None] = mapped_column(Float)
    net_income_ttm_pln_thousands: Mapped[float | None] = mapped_column(Float)
    equity_pln_thousands: Mapped[float | None] = mapped_column(Float)
    turnover_present: Mapped[bool | None] = mapped_column()
    extras: Mapped[dict] = mapped_column(JSONVariant, default=dict)


class PortfolioOperation(Base):
    """Imported myfund operation/flow row (API or file export), deduplicated."""

    __tablename__ = "portfolio_operations"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "content_hash", name="uq_portfolio_operation_content"
        ),
        Index("ix_portfolio_operations_portfolio_date", "portfolio_id", "occurred_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    occurred_on: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    instrument_name: Mapped[str | None] = mapped_column(String(240))
    ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    quantity: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    amount_pln: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="PLN")
    source: Mapped[str] = mapped_column(String(20), default="api")
    provider_key: Mapped[str | None] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
