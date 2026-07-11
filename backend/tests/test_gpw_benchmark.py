from datetime import date, datetime, timezone

from app.scrapers.gpw_benchmark import parse_index_portfolio
from tests.conftest import load_fixture


def test_parses_dated_official_portfolio_table():
    portfolio = parse_index_portfolio(load_fixture("gpw_benchmark_portfolio.html"))
    assert portfolio.as_of == date(2026, 7, 10)
    assert portfolio.instruments == {"PKOBP", "SYNEKTIK"}


def test_policy_uses_dated_membership_and_never_sector_guessing(db):
    from app.services import evidence, universe_policy
    from app.scrapers.biznesradar import MarketCandidate

    recorded = evidence.record_market_document_version(
        db, market_key="__GPW__", source_name="gpw_benchmark", source_type="index_portfolio",
        scope_key="mWIG40", requested_url="https://example.test", effective_url="https://example.test",
        content=load_fixture("gpw_benchmark_portfolio.html").encode(), text=load_fixture("gpw_benchmark_portfolio.html"),
        response_status=200, mime_type="text/html", parser_version="test", fetched_at=datetime.now(timezone.utc),
    )
    evidence.mark_parse_result(recorded.version, success=True); db.commit()
    row = universe_policy.policy_for_candidates(db, [MarketCandidate("SNT", None, "SYNEKTIK", "2026Q1", "AAA", 9, 6)])["rows"][0]
    assert row["included"] is False
    assert row["excluded_by"] == ["mWIG40"]
