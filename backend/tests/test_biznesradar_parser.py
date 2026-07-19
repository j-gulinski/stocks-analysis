"""Parser tests against committed synthetic fixtures (exact values) and,
when present, real recorded pages (structure only — see scripts/record_fixtures.py)."""

from datetime import date

import pytest

from app.scrapers.biznesradar import (
    normalize_period,
    parse_dividends,
    parse_forecasts,
    parse_number,
    parse_profile,
    parse_price_history,
    parse_report_table,
)
from app.services import fields
from tests.conftest import FIXTURES_DIR, load_fixture


# ------------------------------------------------------------- primitives

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12 345", 12345.0),
        ("12 345", 12345.0),
        ("-5 000", -5000.0),
        ("1,23", 1.23),
        ("4,9%", 4.9),
        ("—", None),
        ("", None),
        (None, None),
        ("b/d", None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "freq", "expected"),
    [
        ("2025/Q1", "Q", "2025Q1"),
        ("2025 Q1", "Q", "2025Q1"),
        ("2024", "Y", "2024"),
        ("r/r", "Q", None),
        ("", "Q", None),
        ("2024", "Q", None),  # a bare year is not a quarter column
        # report as-of dates — production header format on some pages
        ("2025-03-31", "Q", "2025Q1"),
        ("2025-09-30", "Q", "2025Q3"),
        ("2025-06", "Q", "2025Q2"),
        ("2024-12-31", "Y", "2024"),
    ],
)
def test_normalize_period(raw, freq, expected):
    assert normalize_period(raw, freq) == expected


def test_header_row_scan_and_duplicate_columns():
    """Production findings: the period header is not always the first <tr>,
    and annual pages can repeat a period column (CBF crash) — first wins.
    Publication metadata must follow those exact selected column indexes."""
    html = """
    <table class="report-table">
      <tr><td>filtry</td><td>Roczne</td><td>Kwartalne</td></tr>
      <tr><td></td><th>2024-09-30</th><th>O4K (mar 26)*</th><th>2024-12-31</th><th>2025/Q1</th><th>2025/Q1</th></tr>
      <tr data-field="PrimaryReport"><td>Data publikacji</td>
        <td>2024-11-14</td><td>2026-05-15</td><td>2025-02-30</td>
        <td>2025-05-15</td><td>2099-01-01</td></tr>
      <tr data-field="IncomeRevenues"><td>Przychody ze sprzedaży</td>
        <td><span class="value">10</span></td><td><span class="value">999</span></td>
        <td><span class="value">20</span></td><td><span class="value">30</span></td>
        <td><span class="value">99</span></td></tr>
    </table>"""
    table = parse_report_table(html, freq="Q")
    assert table.periods == ["2024Q3", "2024Q4", "2025Q1"]  # dup 2025Q1 dropped
    assert table.publication_dates == [date(2024, 11, 14), None, date(2025, 5, 15)]
    assert table.rows[0].values == [10.0, 20.0, 30.0]  # first 2025Q1 column kept
    assert [row.label for row in table.rows] == ["Przychody ze sprzedaży"]


def test_profile_price_extraction():
    meta_html = (
        '<html><head><title>X (DEC)</title>'
        '<meta itemprop="price" content="24.50"></head><body></body></html>'
    )
    assert parse_profile(meta_html, "DEC").price == 24.5

    text_html = "<html><body><h2>DECORA (DEC)</h2>Kurs: 12,30 zł</body></html>"
    assert parse_profile(text_html, "DEC").price == 12.3

    assert parse_profile(load_fixture("br_profile.html"), "DEC").price is None


def test_profile_report_calendar_uses_source_date_and_surfaces_bad_markup():
    html = (FIXTURES_DIR / "real/br/ABS/profile.html").read_text(encoding="utf-8")

    profile = parse_profile(html, "ABS")

    assert profile.next_report_date == date(2026, 8, 6)
    assert profile.next_report_label == "raport półroczny"
    assert profile.next_report_parse_error is None

    malformed = parse_profile(
        '<html><div class="report-date"><label>raport kwartalny</label>'
        '<span class="countdown">wkrótce</span></div></html>',
        "ABS",
    )
    assert malformed.next_report_date is None
    assert "RRRR-MM-DD" in malformed.next_report_parse_error


# ----------------------------------------------------- synthetic fixtures

def test_income_quarterly_table():
    table = parse_report_table(load_fixture("br_income_q.html"), freq="Q")

    assert table.periods == [
        "2023Q1", "2023Q2", "2023Q3", "2023Q4",
        "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1",
    ]
    assert table.publication_dates == [None] * len(table.periods)
    assert len(table.rows) == 11

    revenue = next(r for r in table.rows if r.field_code == "IncomeRevenues")
    assert revenue.values[0] == 50000.0
    assert revenue.values[-1] == 62700.0

    # Row without data-field falls back to a slug code; junk r/r column skipped.
    other = next(r for r in table.rows if "pozostalej" in r.field_code)
    assert len(other.values) == len(table.periods)
    assert other.values[-1] == 106.0


def test_income_annual_table():
    table = parse_report_table(load_fixture("br_income_y.html"), freq="Y")
    assert table.periods == ["2023", "2024"]
    net = next(r for r in table.rows if r.field_code == "IncomeNetProfit")
    assert net.values == [18832.0, 24454.0]


def test_profile():
    profile = parse_profile(load_fixture("br_profile.html"), "DEC")
    assert profile.name == "DECORA"
    # the free-float row sits ABOVE "Liczba akcji" in the fixture — the strict
    # `label :? digits` matching must not bridge across "w wolnym obrocie"
    # (the old permissive regex captured the float count → false "small cap")
    assert profile.shares_outstanding == 10_566_435
    assert profile.sector.startswith("Materiały")
    assert profile.market is None  # no explicit "Rynek:" label in the fixture
    # reported figures from the info box (PLN, full-integer form)
    assert profile.market_cap == 258_877_658.0
    assert profile.enterprise_value == 236_877_658.0


def test_profile_scaled_market_cap_and_free_float_trap():
    """Info boxes also serve the scaled form ('2,82 mld') — a naive parse
    would store 2.82 PLN and re-create the small-cap bug from the other side.
    A page with ONLY the free-float count must yield no share count at all."""
    html = (
        "<html><head><title>BIGCO (BIG) - notowania</title></head><body>"
        "<h1>Notowania BIG</h1>"
        "<table><tr><td>Liczba akcji w wolnym obrocie:</td><td>6 400 000</td></tr>"
        "<tr><td>Kapitalizacja:</td><td>2,82 mld</td></tr></table></body></html>"
    )
    profile = parse_profile(html, "BIG")
    assert profile.market_cap == 2_820_000_000.0
    assert profile.shares_outstanding is None


def test_profile_production_shape():
    """Generic 'Notowania X' h1 (seen in production) — name must come from
    the title's 'NAME (TICKER)' pattern, market only from an explicit label."""
    html = (
        "<html><head><title>SYNEKTIK (SNT) - notowania akcji - BiznesRadar.pl"
        "</title></head><body><h1>Notowania SNT</h1>"
        "<table><tr><td>Rynek:</td><td>GPW</td></tr>"
        "<tr><td>Liczba akcji:</td><td>8 526 089</td></tr></table></body></html>"
    )
    profile = parse_profile(html, "SNT")
    assert profile.name == "SYNEKTIK"
    assert profile.shares_outstanding == 8_526_089
    assert profile.market == "GPW"

    nameless = parse_profile("<html><h1>Notowania XYZ</h1></html>", "XYZ")
    assert nameless.name is None  # never store the generic listing header


def test_profile_uses_legal_name_h2_when_h1_contains_exchange_alias():
    """ABS live shape: ticker and BR alias are in h1, legal name is in h2."""
    html = (
        "<html><head><title>Notowania ABS ASSECO BUSINESS SOLUTIONS SA"
        "- BiznesRadar.pl</title></head><body>"
        "<h1>Notowania ABS (ASSECOBS)</h1>"
        "<h2>ASSECO BUSINESS SOLUTIONS SPÓŁKA AKCYJNA</h2>"
        "</body></html>"
    )

    profile = parse_profile(html, "ABS")

    assert profile.name == "ASSECO BUSINESS SOLUTIONS SPÓŁKA AKCYJNA"


def test_profile_snt_regressions():
    """Second production round: 'Notowania SYNEKTIK SA (SNT)' in the title
    leaked the prefix into the name, and menu text 'Rynek NewConnect'
    (no colon) mislabeled a main-market company."""
    html = (
        "<html><head><title>Notowania SYNEKTIK SA (SNT) - BiznesRadar.pl</title>"
        "</head><body><h1>Notowania SNT</h1>"
        "<nav>Rynek NewConnect Rynek GPW</nav></body></html>"
    )
    profile = parse_profile(html, "SNT")
    assert profile.name == "SYNEKTIK SA"
    assert profile.market is None  # menu links prove nothing

    labeled = parse_profile(html.replace("<nav>", "<p>Rynek: GPW</p><nav>"), "SNT")
    assert labeled.market == "GPW"


def test_live_page_findings_2026_07():
    """Verified against the live SNT page fetched during debugging."""
    # annual headers carry month annotations; O4K is a TTM aggregate to skip
    assert normalize_period("2018  (paź 18)", "Y") == "2018"
    assert normalize_period("O4K  (mar 26)*", "Y") is None
    assert normalize_period("O4K  (mar 26)*", "Q") is None

    # 'Data publikacji' dates row must never win header detection
    html = (
        '<table class="report-table">'
        "<tr><td>Data publikacji</td><td>2010-02-14</td><td>2019-11-08</td><td>2024-12-20</td></tr>"
        "<tr><td></td><th>2025/Q1</th><th>2025/Q2</th><th>2025/Q3</th></tr>"
        '<tr data-field="IncomeRevenues"><td>Przychody ze sprzedaży</td>'
        '<td><span class="value">1</span></td><td><span class="value">2</span></td>'
        '<td><span class="value">3</span></td></tr></table>'
    )
    table = parse_report_table(html, "Q")
    assert table.periods == ["2025Q1", "2025Q2", "2025Q3"]
    assert table.publication_dates == [
        date(2010, 2, 14),
        date(2019, 11, 8),
        date(2024, 12, 20),
    ]
    assert all(row.label != "Data publikacji" for row in table.rows)

    # profile: slug link, 'Branża:' label, market banner, name not crossing ':'
    live = (
        "<html><head><title>SYNEKTIK SA (SNT) - notowania akcji - BiznesRadar.pl"
        '</title></head><body><a href="/notowania/SYNEKTIK">Profil</a>'
        "<h1>Notowania SNT</h1>GPW - Akcje - Notowania ciągłe"
        "<table><tr><td>Branża:</td><td>Biotechnologia</td></tr>"
        "<tr><td>Liczba akcji:</td><td>8 529 129</td></tr></table></body></html>"
    )
    profile = parse_profile(live, "SNT")
    assert profile.name == "SYNEKTIK SA"
    assert profile.slug == "SYNEKTIK"
    assert profile.market == "GPW"
    assert profile.sector == "Biotechnologia"
    assert profile.shares_outstanding == 8_529_129


def test_income_codes_real_semantics():
    """BR codes 'Zysk ze sprzedaży' as IncomeGrossProfit — it is profit AFTER
    SG&A (profit_on_sales), never true gross. Verified on the live page."""
    assert fields.match_income_field("Zysk ze sprzedaży", "IncomeGrossProfit") == "profit_on_sales"
    assert fields.match_income_field("Zysk brutto ze sprzedaży") == "gross_profit"
    assert fields.match_income_field("Techniczny koszt wytworzenia produkcji sprzedanej", "IncomeCostOfSales") == "cogs"
    assert fields.match_income_field("Koszty sprzedaży", "IncomeDistributionExpenses") == "selling_costs"
    assert fields.match_income_field("Zysk operacyjny (EBIT)", "IncomeEBIT") == "operating_profit"
    assert fields.match_income_field("Zysk przed opodatkowaniem", "IncomeBeforeTaxProfit") == "pretax_profit"
    assert fields.match_income_field("Wynik zdarzeń nadzwyczajnych", "IncomeExtraordinarProfit") == "extraordinary_profit"
    assert fields.match_income_field("Zysk (strata) netto z działalności zaniechanej", "IncomeDiscontinuedProfit") == "discontinued_profit"
    assert fields.match_income_field("EBITDA", "BanIncomeEBITDA") == "ebitda"


def test_balance_field_codes_snt():
    """Real data-field codes from the SNT mapping-report: duplicate labels
    ('Kredyty i pożyczki' in both sections) are resolved by code."""
    assert fields.match_balance_field("Kredyty i pożyczki", "BalanceNoncurrentBorrowings") == "debt_borrowings_long"
    assert fields.match_balance_field("Kredyty i pożyczki", "BalanceCurrentBorrowings") == "debt_borrowings_short"
    assert fields.match_balance_field("Zobowiązania z tytułu leasingu finansowego", "BalanceCurrentLeasing") == "debt_leasing_short"
    assert fields.match_balance_field("Z tytułu emisji dłużnych papierów wartościowych", "BalanceNoncurrentObligations") == "debt_bonds_long"
    assert fields.match_balance_field("Środki pieniężne i inne aktywa pieniężne", "BalanceCash") == "cash"
    assert fields.match_balance_field("Kapitał własny akcjonariuszy jednostki dominującej", "BalanceCapital") == "equity"
    # bare ambiguous label without a code → honestly unmapped
    assert fields.match_balance_field("Kredyty i pożyczki") is None


def test_dividends():
    entries = parse_dividends(load_fixture("br_dividend.html"))
    assert [(e.year, e.dps, e.yield_pct) for e in entries] == [
        (2025, 1.2, 4.9),
        (2024, 1.0, 3.2),
        (2023, 0.8, 2.7),
    ]


# ------------------------------------------------------------- forecasts

def test_forecasts_columns_and_money_conversion():
    """Live-verified /prognozy shape (2026-07-09): columns carry a raw label,
    a kind (raport/raport_ttm/konsensus) and BiznesRadar's own note text; O4K
    is recognised as the TTM column by label alone, regardless of its note."""
    table = parse_forecasts(load_fixture("br_forecasts.html"))

    assert [(c.label, c.kind, c.note) for c in table.columns] == [
        ("2025", "raport", "raport"),
        ("O4K", "raport_ttm", "raport (mar 26)*"),
        ("2026", "konsensus", "konsensus"),
        ("2027", "konsensus", "konsensus"),
        ("2028", "konsensus", "konsensus"),
    ]

    revenue = next(r for r in table.rows if r.metric == "revenue")
    # "267 827.0" mln zł (dot decimal, 2025 column) -> tys. PLN (×1000) — the
    # DB convention; loudly commented at the conversion site in the parser.
    assert revenue.values[0] == 267_827_000.0
    # "275 000,0" mln zł (comma decimal, 2026 consensus column) -> tys. PLN.
    assert revenue.values[2] == 275_000_000.0

    ebitda = next(r for r in table.rows if r.metric == "ebitda")
    assert ebitda.values == [
        32_500_000.0, 33_100_000.0, 34_000_000.0, 35_500_000.0, 37_000_000.0,
    ]


def test_forecasts_percent_and_ratio_rows_are_not_scaled():
    """Marża/Rentowność (%) and Cena / Zysk (C/Z) rows are plain numbers —
    only the money rows go through the mln->tys conversion."""
    table = parse_forecasts(load_fixture("br_forecasts.html"))

    margin = next(r for r in table.rows if r.metric == "ebitda_margin_pct")
    assert margin.values == [12.14, 12.19, 12.36, 12.68, 12.98]  # "12.14%" / "12,36%"

    pe = next(r for r in table.rows if r.metric == "pe")
    assert pe.values == [44.08, 41.5, 40.1, 37.8, 36.0]  # "44.08" / "40,10"


def test_forecasts_preserve_consensus_count_and_range():
    html = load_fixture("br_forecasts.html").replace(
        "<td>275 000,0</td>",
        "<td>275 000,0 6 (270 000,0 - 280 000,0)</td>",
        1,
    )
    table = parse_forecasts(html)
    revenue = next(r for r in table.rows if r.metric == "revenue")

    assert revenue.estimate_ranges[:2] == [None, None]
    estimate = revenue.estimate_ranges[2]
    assert estimate is not None
    assert estimate.forecast_count == 6
    assert estimate.minimum == 270_000_000.0
    assert estimate.maximum == 280_000_000.0


def test_forecasts_unmapped_label_is_reported_not_dropped():
    """A row BiznesRadar doesn't actually show (added to the fixture on
    purpose) must surface in unmapped_labels, same discipline as the
    indicator-page parser's 'pominięte' reporting — never silently dropped."""
    table = parse_forecasts(load_fixture("br_forecasts.html"))

    assert "Dług netto / kapitał własny" in table.unmapped_labels
    unmapped_row = next(r for r in table.rows if r.label == "Dług netto / kapitał własny")
    assert unmapped_row.metric is None
    assert unmapped_row.values == [1.2, 1.1, 1.05, 0.95, 0.9]  # kept, just unmapped


def test_forecasts_values_by_metric_helper():
    table = parse_forecasts(load_fixture("br_forecasts.html"))
    by_metric = table.values_by_metric()
    assert by_metric["revenue"]["2025"] == 267_827_000.0
    assert by_metric["revenue"]["O4K"] == 271_500_000.0
    assert by_metric["revenue"]["2028"] == 285_000_000.0
    assert "Dług netto / kapitał własny" not in by_metric  # unmapped rows excluded


def test_forecasts_empty_consensus_becomes_none():
    """Production finding: BiznesRadar only counts analyst forecasts younger
    than 6 months, so consensus columns are frequently entirely empty/'-' —
    the parser must degrade to None per cell, never raise or drop the row."""
    table = parse_forecasts(load_fixture("br_forecasts_empty_consensus.html"))

    assert [c.kind for c in table.columns] == [
        "raport", "raport_ttm", "konsensus", "konsensus", "konsensus",
    ]
    for row in table.rows:
        assert row.values[2:] == [None, None, None]  # both "" and "-" -> None
        assert row.values[0] is not None and row.values[1] is not None

    revenue = next(r for r in table.rows if r.metric == "revenue")
    assert revenue.values[0] == 267_800.0  # "267.8" mln zł -> tys. PLN
    assert revenue.values[1] == 271_500.0  # "271.5" mln zł (O4K) -> tys. PLN


def test_indicator_table_and_mapping():
    table = parse_report_table(load_fixture("br_indicators_value.html"), freq="Q")
    cz = next(r for r in table.rows if r.label == "C/Z")
    assert cz.values == [12.5, 11.8, 12.0, 11.5, 10.9, 11.2, 10.4, 9.8]
    assert fields.match_indicator("C/Z") == "cz"
    assert fields.match_indicator("EV/EBITDA") == "ev_ebitda"
    assert fields.match_indicator("Jakiś inny wskaźnik") is None


def test_income_field_matching_disambiguates_gross_lines():
    # 'Zysk brutto' (pretax) must never match 'Zysk brutto ze sprzedaży' (gross).
    assert fields.match_income_field("Zysk brutto ze sprzedaży") == "gross_profit"
    assert fields.match_income_field("Zysk brutto") == "pretax_profit"
    assert fields.match_income_field("anything", "IncomeNetProfit") == "net_profit"
    assert fields.match_balance_field("Środki pieniężne i inne aktywa pieniężne") == "cash"
    assert fields.match_cashflow_field("anything", "CashflowOperatingCashflow") == "operating_cashflow"
    assert fields.match_cashflow_field("Wydatki inwestycyjne") == "capex"
    assert fields.match_balance_field("anything", "BalanceCurrentReceivables") == "receivables_current"


# ------------------------------------------------- real recorded fixtures

REAL_BR_ROOT = FIXTURES_DIR / "real" / "br"
REAL_COMPANY_DIRS = sorted(path for path in REAL_BR_ROOT.glob("*") if path.is_dir())
REAL_REPORT_FIXTURES = [
    ("income_q.html", "Q"),
    ("income_y.html", "Y"),
    ("balance_q.html", "Q"),
    ("cashflow_q.html", "Q"),
    ("indicators_value.html", "Q"),
    ("indicators_profitability.html", "Q"),
]


@pytest.mark.parametrize("company_dir", REAL_COMPANY_DIRS)
@pytest.mark.parametrize(("fixture_name", "freq"), REAL_REPORT_FIXTURES)
def test_real_report_pages_structure(company_dir, fixture_name, freq):
    """Structural assertions over every ticker-specific real capture."""
    path = company_dir / fixture_name
    assert path.exists(), f"incomplete real fixture set: missing {path}"
    table = parse_report_table(path.read_text(encoding="utf-8"), freq=freq)
    assert table.periods, "expected at least one period column"
    assert len(table.publication_dates) == len(table.periods)
    assert table.rows, "expected at least one data row"
    assert all(row.label != "Data publikacji" for row in table.rows)
    assert any(
        any(v is not None for v in row.values) for row in table.rows
    ), "expected at least one numeric value"


@pytest.mark.parametrize("company_dir", REAL_COMPANY_DIRS)
def test_real_income_maps_core_fields(company_dir):
    path = company_dir / "income_q.html"
    table = parse_report_table(path.read_text(encoding="utf-8"), freq="Q")
    matched = {
        fields.match_income_field(row.label, row.field_code) for row in table.rows
    }
    # The strategy cannot work without these three lines — fail loudly if the
    # alias list needs extending for real-world labels.
    assert {"revenue", "net_profit"} <= matched
    assert {"gross_profit", "cogs", "profit_on_sales"} & matched


@pytest.mark.parametrize("company_dir", REAL_COMPANY_DIRS)
def test_real_profile_dividend_and_price_pages(company_dir):
    ticker = company_dir.name
    profile_path = company_dir / "profile.html"
    dividend_path = company_dir / "dividends.html"
    price_path = company_dir / "price_history.html"
    for path in (profile_path, dividend_path, price_path, company_dir / "metadata.json"):
        assert path.exists(), f"incomplete real fixture set: missing {path}"

    profile = parse_profile(profile_path.read_text(encoding="utf-8"), ticker)
    assert profile.slug
    assert profile.name
    # A company may legitimately pay no dividend; parsing must still be safe.
    assert isinstance(parse_dividends(dividend_path.read_text(encoding="utf-8")), list)
    bars = parse_price_history(price_path.read_text(encoding="utf-8"))
    assert bars, "expected at least one real price-history bar"


def test_real_fixture_matrix_has_two_companies_when_rt03_is_closed():
    if not REAL_COMPANY_DIRS:
        pytest.skip("RT0.3 open: record one GPW and one verified NewConnect company")
    assert len(REAL_COMPANY_DIRS) >= 2
