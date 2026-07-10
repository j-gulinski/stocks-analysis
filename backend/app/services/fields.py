"""Canonical financial fields and their BiznesRadar label aliases.

Scrapers store rows verbatim (label + data-field code + value); THIS module is
the single place that decides "row X means revenue". Matching is by exact
normalized label (never prefix — 'Zysk brutto' and 'Zysk brutto ze sprzedaży'
are different lines!), with the raw data-field code as a secondary key.

Alias lists were written against fixtures mirroring the reference scraper's
output; after recording real pages (scripts/record_fixtures.py) extend the
tuples here — nothing else needs to change, and no re-scrape is required
because raw labels are already stored in the DB.
"""
from __future__ import annotations

import re


def normalize_label(label: str) -> str:
    text = label.lower().strip()
    text = re.sub(r"[*†]+$", "", text).strip()  # footnote markers
    text = re.sub(r"\s+", " ", text)
    # Live pages write "Cena / Zysk" — spaces around slashes broke matching.
    return re.sub(r"\s*/\s*", "/", text)


# canonical field -> exact normalized labels seen on BiznesRadar
INCOME_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": (
        "przychody netto ze sprzedaży",
        "przychody ze sprzedaży",
        "przychody netto ze sprzedaży produktów, towarów i materiałów",
    ),
    "gross_profit": (
        "zysk brutto ze sprzedaży",
        "zysk (strata) brutto ze sprzedaży",
    ),
    "cogs": (
        "techniczny koszt wytworzenia produkcji sprzedanej",
        "koszt sprzedanych produktów, towarów i materiałów",
        "koszty sprzedanych produktów, towarów i materiałów",
        "koszt własny sprzedaży",
    ),
    "selling_costs": ("koszty sprzedaży",),
    "admin_costs": ("koszty ogólnego zarządu",),
    "profit_on_sales": (
        "zysk ze sprzedaży",
        "zysk (strata) ze sprzedaży",
    ),
    "operating_profit": (
        "zysk operacyjny (ebit)",
        "zysk operacyjny",
        "zysk z działalności operacyjnej",
        "zysk (strata) z działalności operacyjnej",
        "ebit",
    ),
    "pretax_profit": (
        "zysk przed opodatkowaniem",
        "zysk (strata) brutto",
        "zysk brutto",
    ),
    "net_profit": (
        "zysk netto",
        "zysk (strata) netto",
        "zysk netto akcjonariuszy jednostki dominującej",
    ),
    "depreciation": ("amortyzacja",),
    "ebitda": ("ebitda",),
}

# data-field attribute values — verified against the LIVE SNT page (2026-07).
# TRAP: BiznesRadar codes its "Zysk ze sprzedaży" row (profit AFTER SG&A) as
# IncomeGrossProfit. It is NOT gross profit; true gross (Malik's marża brutto)
# has no row in this layout and is derived as revenue − cogs.
INCOME_FIELD_CODES: dict[str, tuple[str, ...]] = {
    "revenue": ("IncomeRevenues",),
    "cogs": ("IncomeCostOfSales",),
    "selling_costs": ("IncomeDistributionExpenses",),
    "admin_costs": ("IncomeAdministrativExpenses",),
    "profit_on_sales": ("IncomeGrossProfit", "IncomeProfitOnSales"),
    "operating_profit": ("IncomeEBIT", "IncomeOperatingProfit"),
    "pretax_profit": (
        "IncomeBeforeTaxProfit",
        "IncomeNetGrossProfit",
        "IncomeProfitBeforeTax",
    ),
    "net_profit": ("IncomeNetProfit",),
    "ebitda": ("BanIncomeEBITDA", "IncomeEBITDA"),
}

# Financial debt is split into granular components on BiznesRadar (verified
# against a real SNT mapping-report). Labels DUPLICATE between the long- and
# short-term sections ("Kredyty i pożyczki" appears twice!), so balance rows
# are matched by data-field code first; labels are only a fallback for rows
# whose label is unambiguous. Everything starting with `debt_` is summed by
# metrics.compute_net_cash.
BALANCE_FIELD_CODES: dict[str, tuple[str, ...]] = {
    "total_assets": ("BalanceTotalAssets",),
    "equity": ("BalanceCapital",),
    "current_assets": ("BalanceCurrentAssets",),
    "noncurrent_assets": ("BalanceNoncurrentAssets",),
    "current_liabilities": ("BalanceCurrentLiabilities",),
    "noncurrent_liabilities": ("BalanceNoncurrentLiabilities",),
    "inventory": ("BalanceInventory",),
    "cash": ("BalanceCash",),
    "debt_borrowings_long": ("BalanceNoncurrentBorrowings",),
    "debt_bonds_long": ("BalanceNoncurrentObligations",),
    "debt_leasing_long": ("BalanceNoncurrentLeasing",),
    "debt_borrowings_short": ("BalanceCurrentBorrowings",),
    "debt_bonds_short": ("BalanceCurrentObligations",),
    "debt_leasing_short": ("BalanceCurrentLeasing",),
}

BALANCE_ALIASES: dict[str, tuple[str, ...]] = {
    "total_assets": ("aktywa razem", "suma aktywów"),
    "equity": (
        "kapitał własny",
        "kapitał (fundusz) własny",
        "kapitał własny akcjonariuszy jednostki dominującej",
    ),
    # Section totals — unambiguous (each appears once, as its section header).
    # Feed the liquidity/leverage ratios in services/insights.py.
    "current_assets": ("aktywa obrotowe",),
    "noncurrent_assets": ("aktywa trwałe",),
    "current_liabilities": ("zobowiązania krótkoterminowe",),
    "noncurrent_liabilities": ("zobowiązania długoterminowe",),
    "inventory": ("zapasy",),
    "cash": (
        "środki pieniężne i inne aktywa pieniężne",
        "środki pieniężne",
        "środki pieniężne i ich ekwiwalenty",
    ),
    # unambiguous full labels only — bare "kredyty i pożyczki" is NOT here
    # because it appears in both the long- and short-term sections
    "debt_borrowings_long": (
        "zobowiązania finansowe długoterminowe",
        "długoterminowe kredyty i pożyczki",
        "zobowiązania długoterminowe z tytułu kredytów i pożyczek",
    ),
    "debt_borrowings_short": (
        "zobowiązania finansowe krótkoterminowe",
        "krótkoterminowe kredyty i pożyczki",
        "zobowiązania krótkoterminowe z tytułu kredytów i pożyczek",
    ),
}

# indicator label -> short code used in indicator_values.indicator
# (labels are normalized first: lowercase, "/" tightened — live pages write
# the long forms "Cena / Zysk", "Cena / Wartość księgowa", …)
INDICATOR_CODES: dict[str, str] = {
    "c/z": "cz",
    "cena/zysk": "cz",
    "c/wk": "cwk",
    "cena/wartość księgowa": "cwk",
    "c/p": "cp",
    "cena/przychody ze sprzedaży": "cp",
    "c/zo": "czo",
    "cena/zysk operacyjny": "czo",  # own code — must NEVER masquerade as cz
    "ev/ebitda": "ev_ebitda",
    "ev/ebit": "ev_ebit",
    "ev/przychody ze sprzedaży": "ev_revenue",
    "ev/przychody": "ev_revenue",
    "roe": "roe",
    "roe (zwrot z kapitału własnego)": "roe",
    "roa": "roa",
    "roa (zwrot z aktywów)": "roa",
    "stopa dywidendy": "dividend_yield",
    "marża zysku netto": "net_margin",
    "marża netto": "net_margin",
    "marża zysku operacyjnego": "operating_margin",
    "marża operacyjna": "operating_margin",
    "marża zysku brutto ze sprzedaży": "gross_margin",
    "marża brutto na sprzedaży": "gross_margin",
    "marża zysku ze sprzedaży": "sales_margin",
    # deliberately unmapped: "cena/wartość księgowa grahama" (Graham cousin of
    # cwk) and "marża zysku brutto" (PRETAX margin, not gross-sales margin) —
    # near-namesakes that must never pollute cwk/gross_margin series.
}

# BiznesRadar data-field codes on the wskaźniki pages (`<tr data-field="CZ">` —
# present in recorded pages). Codes are the stable row identity; labels above
# stay as the fallback for rows without a code. Extend from real fixtures via
# scripts/record_fixtures.py — never guess a Graham/operacyjny cousin here.
INDICATOR_FIELD_CODES: dict[str, tuple[str, ...]] = {
    "cz": ("CZ",),
    "cwk": ("CWK",),
    "cp": ("CP", "CPS"),
    "czo": ("CZO",),
    "ev_ebitda": ("EVEBITDA",),
    "ev_ebit": ("EVEBIT",),
    "ev_revenue": ("EVS", "EVREVENUES"),
    "roe": ("ROE",),
    "roa": ("ROA",),
    "dividend_yield": ("DY", "DIVIDENDYIELD"),
    "net_margin": ("NPM", "NETPROFITMARGIN"),
    "operating_margin": ("OPM", "OPERATINGPROFITMARGIN"),
    "gross_margin": ("GPM", "GROSSPROFITMARGIN"),
}

# Consolidated statements list the group ("skonsolidowany") line and sometimes
# a parent-shareholders line for the same concept. For EPS/valuation the
# strategy uses the PARENT (jednostki dominującej) net profit — when both rows
# are present the parent one wins, whatever their order on the page.
_PARENT_PREFERRED_LABELS: dict[str, tuple[str, ...]] = {
    "net_profit": (
        "zysk netto akcjonariuszy jednostki dominującej",
        "zysk (strata) netto akcjonariuszy jednostki dominującej",
        "zysk netto przypadający akcjonariuszom jednostki dominującej",
    ),
}


def _match(aliases: dict[str, tuple[str, ...]], label: str) -> str | None:
    normalized = normalize_label(label)
    for canonical, names in aliases.items():
        if normalized in names:
            return canonical
    return None


def match_income_field(label: str, field_code: str | None = None) -> str | None:
    if field_code:
        for canonical, codes in INCOME_FIELD_CODES.items():
            if field_code in codes:
                return canonical
    return _match(INCOME_ALIASES, label)


def income_match_rank(canonical: str, label: str, field_code: str | None = None) -> int:
    """How authoritative a matched row is for its canonical field.

    2 = parent-shareholders line (wins for net_profit), 1 = data-field code
    match, 0 = plain label alias. dossier.load_income_series keeps the
    highest-ranked row per (period, field) — deterministic across layouts,
    instead of the old first-row-wins which depended on page row order.
    """
    normalized = normalize_label(label)
    if normalized in _PARENT_PREFERRED_LABELS.get(canonical, ()):
        return 2
    if field_code and field_code in INCOME_FIELD_CODES.get(canonical, ()):
        return 1
    return 0


def match_balance_field(label: str, field_code: str | None = None) -> str | None:
    if field_code:
        for canonical, codes in BALANCE_FIELD_CODES.items():
            if field_code in codes:
                return canonical
    return _match(BALANCE_ALIASES, label)


def match_indicator(label: str, field_code: str | None = None) -> str | None:
    """Code-aware like the statement matchers (codes survive label drift).

    Safety valve: only CZ/CWK codes are fixture-verified; the rest of
    INDICATOR_FIELD_CODES is educated guessing. If the label maps to a
    DIFFERENT canonical than the code, the (live-verified) label wins —
    a guessed code must never mislabel a series.
    """
    label_canonical = INDICATOR_CODES.get(normalize_label(label))
    if field_code:
        for canonical, codes in INDICATOR_FIELD_CODES.items():
            if field_code in codes:
                if label_canonical is not None and label_canonical != canonical:
                    return label_canonical
                return canonical
    return label_canonical


PERCENT_INDICATORS = frozenset(
    {"roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin"}
)


def indicator_unit(indicator: str) -> str:
    """Canonical unit belongs with field meaning, never scraper markup."""
    return "percent" if indicator in PERCENT_INDICATORS else "ratio"
