from datetime import date

import pytest

from app.scrapers.stooq import PriceDataError, daily_csv_url, parse_prices_csv
from tests.conftest import load_fixture


def test_parse_polish_header_fixture():
    bars = parse_prices_csv(load_fixture("stooq_daily.csv"))
    assert len(bars) == 2
    assert bars[-1].day == date(2025, 7, 1)
    assert bars[-1].close == 24.50
    assert bars[-1].volume == 12345


def test_parse_english_header():
    bars = parse_prices_csv("Date,Open,High,Low,Close,Volume\n2025-07-01,1,2,0.5,1.5,100\n")
    assert bars[0].close == 1.5


def test_no_data_and_malformed_rows():
    assert parse_prices_csv("") == []
    assert parse_prices_csv("Brak danych") == []
    bars = parse_prices_csv(
        "Data,Otwarcie,Najwyzszy,Najnizszy,Zamkniecie,Wolumen\n"
        "not-a-date,1,2,3,4,5\n"
        "2025-07-01,24.15,24.55,24.05,24.50,12345\n"
    )
    assert len(bars) == 1  # malformed row skipped, good row kept


def test_unknown_header_raises():
    with pytest.raises(PriceDataError):
        parse_prices_csv("foo,bar\n1,2\n")


def test_daily_csv_url():
    assert daily_csv_url("DEC") == "https://stooq.pl/q/d/l/?s=dec&i=d"
    assert daily_csv_url("DEC", start=date(2025, 1, 2)).endswith("&d1=20250102")
    assert daily_csv_url("DEC", host="https://stooq.com").startswith("https://stooq.com/")


def test_quote_fallback_when_history_404s(monkeypatch, no_sleep):
    """Production case (SNT): history endpoint 404s on both hosts — the quote
    endpoint still supplies today's close so kurs/mcap/C-Z stay alive."""
    from tests.conftest import FakeResponse

    quote_csv = (
        "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
        "SNT,2026-07-07,17:00:04,88.4,89.2,87.8,88.6,10250\n"
    )

    def fake_fetch(url, *, session=None, timeout=None):
        if "/q/d/l/" in url:
            return FakeResponse("", 404)
        if "/q/l/" in url and url.startswith("https://stooq.pl"):
            return FakeResponse(quote_csv, 200)
        return FakeResponse("", 404)

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    from app.scrapers.stooq import fetch_daily_prices

    bars = fetch_daily_prices("SNT")
    assert len(bars) == 1
    assert bars[0].close == 88.6
    assert str(bars[0].day) == "2026-07-07"


def test_limit_body_stops_immediately(monkeypatch, no_sleep):
    """'Access denied' / daily-limit bodies must stop after ONE request —
    hammering three more stooq URLs would be impolite and pointless."""
    from tests.conftest import FakeResponse
    from app.scrapers.stooq import StooqLimitError, fetch_daily_prices

    calls = []

    def fake_fetch(url, *, session=None, timeout=None):
        calls.append(url)
        return FakeResponse("Access Denied", 200)

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    with pytest.raises(StooqLimitError):
        fetch_daily_prices("SNT")
    assert len(calls) == 1


def test_error_lists_all_attempted_urls(monkeypatch, no_sleep):
    from tests.conftest import FakeResponse

    monkeypatch.setattr(
        "app.scrapers.http.fetch",
        lambda url, *, session=None, timeout=None: FakeResponse("", 404),
    )
    from app.scrapers.stooq import fetch_daily_prices

    with pytest.raises(PriceDataError) as excinfo:
        fetch_daily_prices("SNT")
    message = str(excinfo.value)
    assert "stooq.pl/q/d/l/" in message
    assert "stooq.com/q/d/l/" in message
    assert "q/l/" in message  # quote fallback attempted too
