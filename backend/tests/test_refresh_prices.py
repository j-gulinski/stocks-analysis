"""Price-chain behaviour after the 2026-07 source rework.

Production verdicts encoded here:
- stooq denies non-browser clients → it is tried ONLY during backfill (one
  chance to recover), never on the daily incremental top-up;
- BiznesRadar archiwum (page 1, robots-allowed) is the reliable incremental
  source; Yahoo is best-effort;
- future-dated price rows once froze the chain forever (the `last_day >=
  today` guard) → they are purged on every refresh and never re-stored.

All network is stubbed at app.scrapers.http.fetch; the `seen` list records
the exact request order for chain-order assertions.
"""
from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import Company, Price
from tests.conftest import FakeResponse, load_fixture

BR_HISTORY_URL = "https://www.biznesradar.pl/notowania-historyczne/DEC"
# br_price_history.html covers sessions 2026-06-26 … 2026-07-03
HISTORY_NEWEST = date(2026, 7, 3)


def _company_with_prices(db, rows: int, last_day: date) -> Company:
    company = Company(ticker="DEC", name="DECORA", br_slug="DEC")
    db.add(company)
    db.flush()
    for offset in range(rows):
        db.add(Price(
            company_id=company.id,
            date=last_day - timedelta(days=rows - 1 - offset),
            close=20.0 + offset * 0.01,
        ))
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


def test_incremental_uses_br_archiwum_first(client, db, monkeypatch):
    _company_with_prices(db, rows=35, last_day=date(2026, 6, 25))
    seen: list[str] = []
    _stub(monkeypatch, seen, {
        BR_HISTORY_URL: FakeResponse(load_fixture("br_price_history.html"), 200),
    })

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("ok (6 new days")
    assert "BR archiwum" in summary["prices"]
    assert seen[0] == BR_HISTORY_URL  # archiwum is the FIRST incremental source
    assert not any("yahoo" in url for url in seen)  # nothing else was needed
    assert not any("stooq" in url for url in seen)

    prices = client.get("/api/companies/DEC/prices", params={"days": 5000}).json()
    assert prices[-1]["date"] == HISTORY_NEWEST.isoformat()
    assert prices[-1]["close"] == 24.80


def test_incremental_never_hits_stooq(client, db, monkeypatch):
    """Even with BR archiwum AND Yahoo down, the incremental path must not
    knock on stooq's door — it told us to go away (access denied)."""
    _company_with_prices(db, rows=35, last_day=date(2026, 6, 25))
    seen: list[str] = []
    _stub(monkeypatch, seen, {})  # everything 404s

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("error")
    assert any("biznesradar" in url for url in seen)
    assert any("yahoo" in url for url in seen)
    assert not any("stooq" in url for url in seen)


def test_future_rows_are_purged(client, db, monkeypatch):
    company = _company_with_prices(db, rows=35, last_day=date(2026, 6, 25))
    db.add(Price(company_id=company.id, date=date.today() + timedelta(days=30),
                 close=999.0))
    db.commit()
    seen: list[str] = []
    _stub(monkeypatch, seen, {
        BR_HISTORY_URL: FakeResponse(load_fixture("br_price_history.html"), 200),
    })

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    # without the purge the future row makes last_day >= today and the chain
    # returns "aktualne" forever — the production freeze this test pins down
    assert "usunieto 1 przyszlych dat" in summary["prices"]
    stored = db.scalars(select(Price).where(Price.company_id == company.id)).all()
    assert all(p.date <= date.today() for p in stored)
    assert all(float(p.close) != 999.0 for p in stored)


def test_backfill_order_yahoo_stooq_archiwum(client, db, monkeypatch):
    """Backfill (thin history): deep sources first, archiwum as the safety
    net. With Yahoo and stooq both down, page 1 still yields ~50 sessions."""
    company = Company(ticker="DEC", name="DECORA", br_slug="DEC")
    db.add(company)
    db.commit()
    seen: list[str] = []
    _stub(monkeypatch, seen, {
        BR_HISTORY_URL: FakeResponse(load_fixture("br_price_history.html"), 200),
    })

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("ok (6 new days")
    assert "BR archiwum" in summary["prices"]
    yahoo_hits = [i for i, url in enumerate(seen) if "yahoo" in url]
    stooq_hits = [i for i, url in enumerate(seen) if "stooq" in url]
    archiwum_hits = [i for i, url in enumerate(seen) if url == BR_HISTORY_URL]
    assert yahoo_hits and stooq_hits and archiwum_hits
    assert max(yahoo_hits) < min(stooq_hits) < min(archiwum_hits)


def test_future_bars_are_never_stored(client, db, monkeypatch):
    from app.scrapers.biznesradar import PriceBar

    company = Company(ticker="DEC", name="DECORA", br_slug="DEC")
    db.add(company)
    db.commit()

    def fake_yahoo(ticker, start=None, session=None):
        return [
            PriceBar(day=date.today() - timedelta(days=1), close=10.0, volume=1),
            PriceBar(day=date.today() + timedelta(days=1), close=11.0, volume=1),
        ]

    monkeypatch.setattr("app.services.refresh.yahoo.fetch_daily_prices", fake_yahoo)
    monkeypatch.setattr(
        "app.services.refresh.yahoo.chart_url", lambda t, s=None, host=None: "x"
    )

    summary = client.post("/api/companies/DEC/refresh?scope=prices").json()["summary"]

    assert summary["prices"].startswith("ok (1 new days")
    stored = db.scalars(select(Price).where(Price.company_id == company.id)).all()
    assert len(stored) == 1
    assert stored[0].date <= date.today()
