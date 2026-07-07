"""Pydantic DTOs — request/response contracts for the API.

Kept in one module on purpose (small app); split by domain if it outgrows ~300
lines. `from_attributes=True` lets a schema be built straight from an ORM
object, like AutoMapper-lite.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- watchlist

class WatchlistAddIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    note: str | None = Field(default=None, max_length=500)


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str | None
    note: str | None
    added_at: datetime


# ---------------------------------------------------------------- companies

class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str | None
    market: str | None
    sector: str | None
    shares_outstanding: int | None
    market_cap: float | None = None  # PLN, reported by BiznesRadar
    enterprise_value: float | None = None  # PLN
    updated_at: datetime


class RefreshSummaryOut(BaseModel):
    ticker: str
    summary: dict[str, str]


class ReportRowOut(BaseModel):
    field_code: str
    label: str
    values: list[float | None]


class FinancialsOut(BaseModel):
    statement: str
    freq: str
    periods: list[str]
    rows: list[ReportRowOut]


class IndicatorPointOut(BaseModel):
    period: str
    value: float | None


class DividendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    dps: float | None
    yield_pct: float | None


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    close: float
    volume: int | None


# -------------------------------------------------------------------- forum

class TopicLinkIn(BaseModel):
    url: str = Field(max_length=500)
    ticker: str = Field(min_length=1, max_length=12)


class ForumTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str | None
    last_post_at: datetime | None
    last_synced_at: datetime | None


class ForumSyncOut(BaseModel):
    topic_id: int
    new_posts: int
    total_posts: int


class ForumPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phpbb_post_id: int
    author: str
    posted_at: datetime | None
    content_text: str
    upvotes: int | None


class ForumPageOut(BaseModel):
    total: int
    page: int
    page_size: int
    posts: list[ForumPostOut]


# ----------------------------------------------------------------- forecast

class ForecastAssumptionsIn(BaseModel):
    """Next-quarter assumptions; every value in tys. PLN unless stated."""

    period: str = Field(pattern=r"^\d{4}Q[1-4]$")
    revenue: float
    gross_margin_pct: float = Field(ge=-100, le=100)
    selling_costs_pct: float = Field(ge=0, le=100)
    admin_costs: float
    other_operating: float = 0.0
    financial_net: float = 0.0
    tax_rate: float = Field(default=0.19, ge=0, le=1)
    depreciation: float | None = None


class ForecastCreateIn(BaseModel):
    assumptions: ForecastAssumptionsIn
    label: str | None = Field(default=None, max_length=120)
    save: bool = True


class ForecastOut(BaseModel):
    id: int | None  # None when computed without saving
    label: str | None
    assumptions: dict
    result: dict
    created_at: datetime | None


# ------------------------------------------------------------------ dossier

class CheckOut(BaseModel):
    id: str
    name: str
    verdict: str  # pass | fail | unknown
    evidence: str


class PrescoreOut(BaseModel):
    passed: int
    total: int
    checks: list[CheckOut]


class QuarterMetricsOut(BaseModel):
    period: str
    revenue: float | None
    revenue_yoy_pct: float | None
    gross_margin_pct: float | None
    sales_margin_pct: float | None
    net_margin_pct: float | None
    profit_on_sales: float | None
    operating_profit: float | None
    net_profit: float | None
    one_off_share_pct: float | None


class TtmOut(BaseModel):
    net_profit: float | None  # tys. PLN
    eps: float | None  # PLN per share
    pe: float | None
    market_cap: float | None  # PLN
    price: float | None
    price_date: date | None
    # "reported" (BiznesRadar profile figure) or "derived" (price × shares);
    # check_pct = deviation between the two when both are known.
    market_cap_source: str | None = None
    market_cap_check_pct: float | None = None


class PeHistoryOut(BaseModel):
    median: float | None
    q1: float | None
    q3: float | None
    current: float | None
    percentile: float | None  # 0–100, share of history ≤ current


class NetCashOut(BaseModel):
    value: float | None  # tys. PLN
    note: str


class FreshnessOut(BaseModel):
    financials_scraped_at: datetime | None
    last_price_date: date | None
    forum_last_synced_at: datetime | None


class ForumStatsOut(BaseModel):
    topics: int
    posts: int
    last_post_at: datetime | None


class InsightOut(BaseModel):
    id: str
    name: str
    value: str
    verdict: str  # good | neutral | bad | unknown
    comment: str
    importance: int  # 3 kluczowy · 2 ważny · 1 kontekst


class MissingDataOut(BaseModel):
    id: str
    name: str
    why: str


class InsightsOut(BaseModel):
    """Dynamic per-company analysis: indicator set picked by sector/size,
    honest about what could not be computed (see services/insights.py)."""

    size_code: str | None
    size_label: str | None
    sector_group: str
    sector_group_label: str
    sector: str | None
    key_indicators: list[InsightOut]
    strengths: list[str]
    concerns: list[str]
    missing: list[MissingDataOut]
    data_notes: list[str]
    coverage: dict | None
    summary: str


class DossierOut(BaseModel):
    company: CompanyOut
    freshness: FreshnessOut
    quarters: list[QuarterMetricsOut]
    ttm: TtmOut
    pe_history: PeHistoryOut
    net_cash: NetCashOut
    dividends: list[DividendOut]
    prescore: PrescoreOut
    insights: InsightsOut
    latest_forecast: ForecastOut | None
    forum: ForumStatsOut
