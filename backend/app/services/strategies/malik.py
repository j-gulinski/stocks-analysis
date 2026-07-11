"""The Paweł Malik ("OBS") strategy expressed purely as data.

Every weight, applicability and rule parameter below is cited to a section of
`docs/STRATEGY.md` and `skills/strategy-malik-obs/SKILL.md` — **except** the two
profitability-context criteria tagged `GENERAL_FUNDAMENTALS` ("analiza
fundamentalna (ogólna)"): ROE and net margin are *general fundamental analysis*,
not sourced Malik doctrine. There is **no engine
logic here** — this module only declares *what Malik weighs and how much*; the
generic engine in `services/thesis.py` does the composing. Changing Malik's mind
means editing numbers here, never touching the generic engine.

Weights are on a rough 1–3 scale mirroring the spec's evidence strength and the
"Implications for the thesis engine" priorities:
  3.0  two top pillars (growth motor + valuation vs own history) and the veto
  2.0  supporting balance-sheet / trend signals
  1.0  bonus / context
Verdicts themselves come from `insights.py` (which already encodes Malik's
numeric thresholds, e.g. C/Z < 0.85× own median); we do not restate those here,
so the two layers can never disagree.
"""
from __future__ import annotations

from app.services.strategies.base import (
    Criterion,
    EntryQualityRule,
    StrategyProfile,
    VerifyGap,
)

_SPEC = "docs/STRATEGY.md"

# Principle-tag suffix for criteria that are NOT Malik doctrine but *general
# fundamental analysis*. These entries have no source-backed Malik citation and
# must never render as
# Malik principles. Kept as a distinct, greppable namespace because the
# `principle` tag flows verbatim into the UI pros/cons — honest attribution.
GENERAL_FUNDAMENTALS = "analiza fundamentalna (ogólna)"

# --- criteria ---------------------------------------------------------------
# id / principle / weight, each mapped to an insights.Insight and cited.
_CRITERIA: tuple[Criterion, ...] = (
    # PILLAR 1 — growth from the P&L (spec §Philosophy pt2; principles 2–4;
    # §Implications "two pillars, top weight"). Marża brutto is Malik's single
    # most-watched motor (principle 3, evidence S) → the heaviest growth weight.
    Criterion(
        id="gross_margin",
        principle="Marża brutto — motor tezy",  # spec principle 3
        weight=3.0,
    ),
    Criterion(
        id="revenue_growth",
        principle="Wzrost przychodów",  # spec principle 2
        weight=2.5,
    ),
    Criterion(
        id="operating_leverage",
        principle="Dźwignia operacyjna",  # spec principle 4
        weight=2.0,
    ),
    # Growth-signal fallback for sectors where insights emits a profit trend
    # instead of margins (e.g. finance). spec §Entry-quality rule lists
    # net_profit_trend as an alternative growth signal.
    Criterion(
        id="net_profit_trend",
        principle="Trend zysku netto",  # spec principle 2 (growth read)
        weight=2.0,
    ),
    # PILLAR 2 — valuation vs the company's OWN history (spec §Valuation
    # doctrine; principle 6, evidence S). Forward C/Z preferred, honesty about
    # the basis is the engine's job (`valuation_basis`).
    Criterion(
        id="pe_vs_history",
        principle="C/Z na tle własnej historii",  # spec principle 6
        weight=3.0,
    ),
    # For finance/real estate the valuation lens is C/WK, not C/Z (insights only
    # emits `cwk` there). spec principle 6 + insights finance playbook.
    Criterion(
        id="cwk",
        principle="C/WK (spółki finansowe/deweloperzy)",
        weight=2.0,
        applies_to_sectors=frozenset({"finance", "realestate"}),
    ),
    # For energy/commodities EV/EBITDA is the better multiple (spec: insights
    # energy playbook; principle 6 generalised).
    Criterion(
        id="ev_ebitda",
        principle="EV/EBITDA (surowce/energetyka)",
        weight=2.0,
        applies_to_sectors=frozenset({"energy"}),
    ),
    # VETO — profit quality. A cheap multiple sitting on one-off profit is the
    # classic value trap; spec §Entry-quality rule makes `one_offs` a veto, not
    # a footnote (principle 5, evidence S).
    Criterion(
        id="one_offs",
        principle="Jakość zysku (one-offy) — weto",  # spec principle 5
        weight=2.5,
    ),
    # SAFETY LEG — net cash is one of the three margin-of-safety legs
    # (spec principle 8/10); debt load is its sector-heavy sibling.
    Criterion(
        id="net_cash",
        principle="Gotówka netto (margines bezpieczeństwa)",  # spec principle 8
        weight=2.0,
    ),
    Criterion(
        id="debt_load",
        principle="Zadłużenie",  # spec principle 10
        weight=1.5,
    ),
    Criterion(
        id="liquidity",
        principle="Płynność bieżąca",  # spec principle 10
        weight=1.0,
    ),
    # For an early-stage / loss-making name the #1 question is runway, not
    # margins (spec: insights biotech playbook; principle 10 balance safety).
    Criterion(
        id="cash_runway",
        principle="Zapas gotówki (runway)",
        weight=2.0,
        applies_to_sectors=frozenset({"biotech_med"}),
    ),
    # GENERAL FUNDAMENTALS (not Malik doctrine) — profitability-quality context.
    # No source-backed Malik rule makes ROE/net margin a standalone veto; these
    # are Workbench general-fundamentals context. Tagged GENERAL_FUNDAMENTALS so
    # the UI never attributes them to Malik. roe is still read for finance names
    # (insights finance playbook), just under the honest general-fundamentals tag.
    Criterion(
        id="roe",
        principle=f"ROE — {GENERAL_FUNDAMENTALS}",
        weight=1.5,
    ),
    Criterion(
        id="net_margin",
        principle=f"Marża netto — {GENERAL_FUNDAMENTALS}",
        weight=1.5,
    ),
    # BONUS — dividend is a bonus, never the foundation (spec principle 12).
    Criterion(
        id="dividend",
        principle="Dywidenda (bonus)",  # spec principle 12
        weight=1.0,
    ),
)

# --- entry-quality rule (spec §Entry-quality decision rule) ------------------
# min_key_indicators=3 and weak_bad_count=2 are the spec's stated thresholds;
# sweet_spot = micro/small and penalised = mid/large operationalise the small-
# cap edge (spec principle 9 + §Valuation doctrine "the size number is ours").
_ENTRY_RULE = EntryQualityRule(
    valuation=frozenset({"pe_vs_history", "cwk", "ev_ebitda"}),
    growth=frozenset(
        {"revenue_growth", "gross_margin", "operating_leverage", "net_profit_trend"}
    ),
    veto=frozenset({"one_offs"}),
    min_key_indicators=3,  # spec §Entry-quality: "< 3 computable key indicators"
    weak_bad_count=2,  # spec §Entry-quality: "≥2 high-importance bad factors"
    high_importance_level=3,  # insights importance 3 = "kluczowy"
    sweet_spot_sizes=frozenset({"micro", "small"}),  # spec principle 9
    penalised_sizes=frozenset({"mid", "large"}),  # spec: dislikes molochy
)

# --- gaps the app cannot compute (spec §Implications "Gaps WP2 must respect")
# Always routed to `verify_next`; NEVER fabricated into a pro/con. Text stays
# digit-free (qualitative) so it can't trip the fabrication guard.
_VERIFY_GAPS: tuple[VerifyGap, ...] = (
    VerifyGap(
        "catalyst",
        "Zidentyfikuj katalizator — co konkretnie ma poprawić wyniki i sprawić, "
        "że rynek to doceni.",
        # spec principle 7 + §Valuation doctrine: cheap alone is insufficient.
        "Malik: samo niskie C/Z nigdy nie jest wystarczającą przesłanką — "
        "potrzebna teza z katalizatorem. Tego nie da się policzyć z danych.",
    ),
    VerifyGap(
        "backlog",
        "Sprawdź portfel zamówień / backlog i jego dynamikę.",
        # spec principle 8: third leg of the margin-of-safety trio, not scraped.
        "Trzecia noga marginesu bezpieczeństwa (obok niskiej wyceny i gotówki "
        "netto); BiznesRadar tego nie raportuje.",
    ),
    VerifyGap(
        "management",
        "Oceń wiarygodność zarządu i ład korporacyjny (transakcje z podmiotami "
        "powiązanymi, wynagrodzenia, dotrzymywanie obietnic).",
        # spec principle 14: needs human/AI check.
        "Jakość i uczciwość zarządu bywa decydująca, a nie wynika ze "
        "sprawozdań — wymaga oceny człowieka.",
    ),
    VerifyGap(
        "cashflow_quality",
        "Porównaj przepływy operacyjne z zyskiem oraz obrotowość należności i "
        "zapasów.",
        # spec principle 11: cash-flow quality not fully computed.
        "Zysk księgowy bez pokrycia w gotówce to sygnał ostrzegawczy; pełnej "
        "analizy przepływów aplikacja jeszcze nie liczy.",
    ),
    VerifyGap(
        "thesis_recheck",
        "Zweryfikuj tezę po następnym raporcie — czy poprawa się potwierdza, "
        "czy była jednorazowa.",
        # spec principle 13: sell/hold discipline, re-verify each report.
        "U Malika każdy raport na nowo potwierdza (lub łamie) tezę; to nie jest "
        "sygnał sprzedaży, tylko punkt kontrolny.",
    ),
)

MALIK = StrategyProfile(
    id="malik",
    label="Paweł Malik (OBS)",
    spec_ref=_SPEC,
    criteria=_CRITERIA,
    entry_rule=_ENTRY_RULE,
    verify_gaps=_VERIFY_GAPS,
    size_weight=2.0,  # sweet spot is a top-weight lens (spec principle 9)
    # {size} carries the company's own size label (e.g. "Mała spółka") — the
    # template must NOT repeat that class word, otherwise it renders as
    # "Mała spółka (Mała spółka)" (fixed 2026-07-08). Wording stays size-agnostic
    # so every sweet-spot / penalised size reads correctly.
    size_pro_text=(
        "{size} — sweet spot strategii: przewaga informacyjna, zanim zmianę "
        "dostrzeże rynek."
    ),
    size_con_text=(
        "{size} — poza sweet spotem strategii: większe spółki są lepiej pokryte "
        "przez analityków, więc przewaga informacyjna maleje."
    ),
    size_principle="Sweet spot — małe spółki",  # spec principle 9
)
