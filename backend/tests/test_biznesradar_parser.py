"""Parser tests against committed synthetic fixtures (exact values) and,
when present, real recorded pages (structure only — see scripts/record_fixtures.py)."""

import pytest

from app.scrapers.biznesradar import (
    normalize_period,
    parse_dividends,
    parse_number,
    parse_profile,
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
    and annual pages can repeat a period column (CBF crash) — first wins."""
    html = """
    <table class="report-table">
      <tr><td>filtry</td><td>Roczne</td><td>Kwartalne</td></tr>
      <tr><td></td><th>2024-09-30</th><th>2024-12-31</th><th>2025/Q1</th><th>2025/Q1</th></tr>
      <tr data-field="IncomeRevenues"><td>Przychody ze sprzedaży</td>
        <td><span class="value">10</span></td><td><span class="value">20</span></td>
        <td><span class="value">30</span></td><td><span class="value">99</span></td></tr>
    </table>"""
    table = parse_report_table(html, freq="Q")
    assert table.periods == ["2024Q3", "2024Q4", "2025Q1"]  # dup 2025Q1 dropped
    assert table.rows[0].values == [10.0, 20.0, 30.0]  # first 2025Q1 column kept


def test_profile_price_extraction():
    meta_html = (
        '<html><head><title>X (DEC)</title>'
        '<meta itemprop="price" content="24.50"></head><body></body></html>'
    )
    assert parse_profile(meta_html, "DEC").price == 24.5

    text_html = "<html><body><h2>DECORA (DEC)</h2>Kurs: 12,30 zł</body></html>"
    assert parse_profile(text_html, "DEC").price == 12.3

    assert parse_profile(load_fixture("br_profile.html"), "DEC").price is None


# ----------------------------------------------------- synthetic fixtures

def test_income_quarterly_table():
    table = parse_report_table(load_fixture("br_income_q.html"), freq="Q")

    assert table.periods == [
        "2023Q1", "2023Q2", "2023Q3", "2023Q4",
        "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1",
    ]
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


# ------------------------------------------------- real recorded fixtures

REAL_REPORT_FIXTURES = [
    ("real_br_income_q.html", "Q"),
    ("real_br_income_y.html", "Y"),
    ("real_br_balance_q.html", "Q"),
    ("real_br_cashflow_q.html", "Q"),
    ("real_br_indicators_value.html", "Q"),
]


@pytest.mark.parametrize(("fixture_name", "freq"), REAL_REPORT_FIXTURES)
def test_real_report_pages_structure(fixture_name, freq):
    """Structural assertions over real pages recorded by scripts/record_fixtures.py."""
    path = FIXTURES_DIR / fixture_name
    if not path.exists():
        pytest.skip("real fixture not recorded yet (run scripts/record_fixtures.py)")
    table = parse_report_table(path.read_text(encoding="utf-8"), freq=freq)
    assert table.periods, "expected at least one period column"
    assert table.rows, "expected at least one data row"
    assert any(
        any(v is not None for v in row.values) for row in table.rows
    ), "expected at least one numeric value"


def test_real_income_maps_core_fields():
    path = FIXTURES_DIR / "real_br_income_q.html"
    if not path.exists():
        pytest.skip("real fixture not recorded yet (run scripts/record_fixtures.py)")
    table = parse_report_table(path.read_text(encoding="utf-8"), freq="Q")
    matched = {
        fields.match_income_field(row.label, row.field_code) for row in table.rows
    }
    # The strategy cannot work without these three lines — fail loudly if the
    # alias list needs extending for real-world labels.
    assert {"revenue", "gross_profit", "net_profit"} <= matched
