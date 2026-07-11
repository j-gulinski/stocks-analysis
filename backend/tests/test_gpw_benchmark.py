from datetime import date

from app.scrapers.gpw_benchmark import parse_index_portfolio
from tests.conftest import load_fixture


def test_parses_dated_official_portfolio_table():
    portfolio = parse_index_portfolio(load_fixture("gpw_benchmark_portfolio.html"))
    assert portfolio.as_of == date(2026, 7, 10)
    assert portfolio.instruments == {"PKOBP", "SYNEKTIK"}
