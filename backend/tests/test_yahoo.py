"""Yahoo Finance chart parsing + its place in the price-source chain."""
import json
from datetime import date

import pytest

from app.scrapers.yahoo import YahooError, chart_url, parse_chart_json, yahoo_symbol
from tests.conftest import FakeResponse

SAMPLE = json.dumps(
    {
        "chart": {
            "result": [
                {
                    "timestamp": [1751241600, 1751328000, 1751414400],
                    "indicators": {
                        "quote": [
                            {
                                "close": [88.4, None, 88.6],  # None = holiday
                                "volume": [10250, None, 11000],
                            }
                        ]
                    },
                }
            ]
        }
    }
)


def test_symbol_and_url():
    assert yahoo_symbol("snt") == "SNT.WA"
    assert chart_url("SNT").startswith(
        "https://query1.finance.yahoo.com/v8/finance/chart/SNT.WA?"
    )
    assert "range=5y" in chart_url("SNT")
    incremental = chart_url("SNT", start=date(2026, 7, 1))
    assert "period1=" in incremental and "period2=" in incremental


def test_parse_chart_json():
    bars = parse_chart_json(SAMPLE)
    assert len(bars) == 2  # the null close (holiday) is skipped
    assert bars[0].close == 88.4 and bars[0].volume == 10250
    assert bars[1].close == 88.6
    assert bars[0].day == date(2025, 6, 30)


def test_parse_rejects_unexpected_payload():
    with pytest.raises(YahooError):
        parse_chart_json("{}")
    with pytest.raises(YahooError):
        parse_chart_json("not json")


def test_price_chain_falls_back_to_yahoo(client, monkeypatch):
    """stooq fully 404s (production case) → Yahoo supplies the history."""
    from tests.test_api_phase1 import fake_fetch

    def fetch(url, *, session=None, timeout=None):
        if url.startswith("https://stooq"):
            return FakeResponse("", 404)
        if url.startswith("https://query1.finance.yahoo.com/"):
            return FakeResponse(SAMPLE, 200)
        return fake_fetch(url, session=session, timeout=timeout)

    monkeypatch.setattr("app.scrapers.http.fetch", fetch)
    summary = client.post("/api/companies/DEC/refresh").json()["summary"]
    assert summary["prices"].startswith("ok (2 new days")
    assert "Yahoo" in summary["prices"]

    prices = client.get("/api/companies/DEC/prices").json()
    assert [p["close"] for p in prices] == [88.4, 88.6]


def test_backfill_replaces_lone_fallback_row(client, monkeypatch, db):
    """Production case: a single profile-quote row must not block history —
    the next refresh with a working provider replaces it with the full range."""
    from datetime import date
    from sqlalchemy import select
    from app.db.models import Company, Price
    from tests.test_api_phase1 import fake_fetch

    client.post("/api/companies/DEC/refresh")
    company = db.scalar(select(Company).where(Company.ticker == "DEC"))
    db.query(Price).filter(Price.company_id == company.id).delete()
    db.add(Price(company_id=company.id, date=date.today(), close=999.0))
    db.commit()

    def fetch(url, *, session=None, timeout=None):
        if url.startswith("https://query1.finance.yahoo.com/"):
            return FakeResponse(SAMPLE, 200)
        if url.startswith("https://stooq"):
            return FakeResponse("", 404)
        return fake_fetch(url, session=session, timeout=timeout)

    monkeypatch.setattr("app.scrapers.http.fetch", fetch)
    summary = client.post("/api/companies/DEC/refresh").json()["summary"]
    assert summary["prices"].startswith("ok (2 new days")
    assert "Yahoo" in summary["prices"]

    prices = client.get("/api/companies/DEC/prices").json()
    assert [p["close"] for p in prices] == [88.4, 88.6]  # stub row gone
