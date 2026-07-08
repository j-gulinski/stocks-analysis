"""BiznesRadar-only price refresh behaviour.

Yahoo/stooq are no longer part of the live refresh path. Prices come from the
robots-allowed BiznesRadar history page, with the already-fetched profile quote
as a one-row fallback when history is unavailable.
"""
from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import Company, Price
from tests.conftest import FakeResponse, load_fixture

BR_PROFILE_URL = "https://www.biznesradar.pl/notowania/DEC"
BR_HISTORY_URL = "https://www.biznesradar.pl/notowania-historyczne/DEC"
# br_price_history.html covers sessions 2026-06-26 … 2026-07-03
HISTORY_NEWEST = date(2026, 7, 3)


def _company_with_prices(db, rows: int, last_day: date) -> Company:
    company = Company(ticker="DEC", name="DECORA", br_slug="DEC")
    db.add(company)
    db.flush()
    for offset in range(rows):
        db.add(
            Price(
                company_id=company.id,
                date=last_day - timedelta(days=rows - 1 - offset),
                close=20.0 + offset * 0.01,
            )
        )
    db.commit()
    return company


def _stub(monkeypatch, seen, responses):
    """URL-prefix → FakeResponse; anything unlisted answers 404."""

    def fetch(url, *, session=None, timeout=None):
        seen.append(url)
        for prefix, response in responses.items():
            if url.startswith(prefix):
                return response
        return FakeResponse("", 404)

    monkeypatch.setattr("app.scrapers.http.fetch", fetch)


def test_incremental_uses_br_archiwum_only(client, db, monkeypatch):
    _company_with_prices(db, rows=35, last_day=date(2026, 6, 25))
    seen: list[str] = []
    _stub(
        monkeypatch,
        seen,
        {BR_PROFILE_URL: FakeResponse("", 200), BR_HISTORY_URL: FakeResponse(load_fixture("br_price_history.html"), 200)},
    )

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("ok (6 new days")
    assert "BR archiwum" in summary["prices"]
    assert any(url == BR_HISTORY_URL for url in seen)
    assert not any("yahoo" in url.lower() for url in seen)
    assert not any("stooq" in url.lower() for url in seen)

    prices = client.get("/api/companies/DEC/prices", params={"days": 5000}).json()
    assert prices[-1]["date"] == HISTORY_NEWEST.isoformat()
    assert prices[-1]["close"] == 24.80


def test_br_profile_quote_fallback_when_history_unavailable(client, db, monkeypatch):
    company = Company(ticker="DEC", name="DECORA", br_slug="DEC")
    db.add(company)
    db.commit()
    seen: list[str] = []
    _stub(
        monkeypatch,
        seen,
        {
            BR_PROFILE_URL: FakeResponse(
                '<html><head><title>DECORA (DEC)</title>'
                '<meta itemprop="price" content="24.50"></head></html>',
                200,
            ),
        },
    )

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("ok (fallback: 1 dzien")
    assert any(url == BR_HISTORY_URL for url in seen)
    stored = db.scalars(select(Price).where(Price.company_id == company.id)).all()
    assert len(stored) == 1
    assert stored[0].close == 24.5


def test_future_rows_are_purged(client, db, monkeypatch):
    company = _company_with_prices(db, rows=35, last_day=date(2026, 6, 25))
    db.add(
        Price(company_id=company.id, date=date.today() + timedelta(days=30), close=999.0)
    )
    db.commit()
    seen: list[str] = []
    _stub(
        monkeypatch,
        seen,
        {BR_PROFILE_URL: FakeResponse("", 200), BR_HISTORY_URL: FakeResponse(load_fixture("br_price_history.html"), 200)},
    )

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert "usunieto 1 przyszlych dat" in summary["prices"]
    stored = db.scalars(select(Price).where(Price.company_id == company.id)).all()
    assert all(p.date <= date.today() for p in stored)
    assert all(float(p.close) != 999.0 for p in stored)


def test_future_bars_are_never_stored(client, db, monkeypatch):
    from app.scrapers.biznesradar import PriceBar

    company = Company(ticker="DEC", name="DECORA", br_slug="DEC")
    db.add(company)
    db.commit()

    def fake_history(db, company, session=None):
        return [
            PriceBar(day=date.today() - timedelta(days=1), close=10.0, volume=1),
            PriceBar(day=date.today() + timedelta(days=1), close=11.0, volume=1),
        ]

    monkeypatch.setattr("app.services.refresh._fetch_br_history", fake_history)
    _stub(monkeypatch, [], {BR_PROFILE_URL: FakeResponse("", 200)})

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("ok (1 new days")
    stored = db.scalars(select(Price).where(Price.company_id == company.id)).all()
    assert len(stored) == 1
    assert stored[0].date <= date.today()
