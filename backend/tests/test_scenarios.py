"""Deterministic scenario engine (services/scenarios.py) — pure unit tests.

Same style as test_thesis.py: hand-built inputs, plain asserts, a tiny
`__main__` runner so it runs BOTH under `pytest` (user's machine) and under a
bare system Python (sandbox — no PyPI). Every target / upside / weighted-EV is
asserted against a HAND computation shown in the comments; the fabrication guard
proves no scenario number is invented.
"""
from __future__ import annotations

from app.services import metrics, scenarios, thesis
from app.services.strategies import cases, malik


# ------------------------------------------------------------------ builders

def _company(sector_group, *, size_code="small", size_label="Mała spółka"):
    return cases.build_case_insights(
        size_code=size_code, size_label=size_label, sector_group=sector_group,
        sector="Sektor testowy", indicators=[], missing=[])


def _inputs(sector_group, *, multiple_history, eps=None, book_value=None,
            ebitda_ttm=None, shares=10_000_000, current_price=None, net_cash=None,
            pe_history=None, ttm=None, earnings_basis=None):
    ti = thesis.ThesisInputs(
        insights=_company(sector_group),
        ttm=ttm or {},
        pe_history=pe_history if pe_history is not None else {},
        net_cash={"value": net_cash, "note": ""},
    )
    return scenarios.ScenarioInputs(
        thesis_inputs=ti, multiple_history=multiple_history, eps=eps,
        book_value=book_value, ebitda_ttm=ebitda_ttm, shares_outstanding=shares,
        current_price=current_price, net_cash=net_cash,
        earnings_basis=earnings_basis or {})


# Own-history stat dicts (shape == metrics.MultipleHistoryStats.to_dict()).
def _hist(median, q1, q3, *, current=None, n):
    return {"median": median, "q1": q1, "q3": q3, "current": current,
            "percentile": None, "n": n}


# --- three archetype fixtures, one per sector-multiple ----------------------

def cz_inputs():
    """Industrial → C/Z. eps 2,5; current 25; own history q1/med/q3 = 11/14/17.
    neg 11×2,5=27,5 (+10%); base 14×2,5=35,0 (+40%); pos 17×2,5=42,5 (+70%)."""
    return _inputs("industrial",
                   multiple_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8),
                   eps=2.5, current_price=25.0,
                   pe_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8))


def cwk_inputs():
    """Finance → C/WK. book 500 000 tys, shares 10 mln → bvps 50,0; current 50;
    q1/med/q3 = 0,8/1,0/1,4. neg 0,8×50=40,0 (−20%); base 1,0×50=50,0 (0%);
    pos 1,4×50=70,0 (+40%)."""
    return _inputs("finance",
                   multiple_history=_hist(1.0, 0.8, 1.4, current=0.9, n=6),
                   book_value=500_000.0, current_price=50.0)


def ev_ebitda_inputs():
    """Energy → EV/EBITDA. ebitda 100 000 tys, shares 10 mln, net DEBT 50 000 tys,
    current 50; q1/med/q3 = 4/6/8.
    base: EV=6×100 000×1000=600 mln; equity=600−50=550 mln; /10 mln=55,0 (+10%).
    neg: EV=4×100 000×1000=400 mln; equity=350 mln; /10 mln=35,0 (−30%).
    pos: EV=8×100 000×1000=800 mln; equity=750 mln; /10 mln=75,0 (+50%)."""
    return _inputs("energy",
                   multiple_history=_hist(6.0, 4.0, 8.0, current=5.0, n=5),
                   ebitda_ttm=100_000.0, net_cash=-50_000.0, current_price=50.0)


def _by_kind(scenario_set):
    return {s["kind"]: s for s in scenario_set["scenarios"]}


# ------------------------------------------------------------------- tests

def test_compute_multiple_history_has_n():
    """The generalised metric returns the observation count `n` (the P/E alias
    stays intact). Hand check: [10,12,14] → median 12, n 3."""
    stats = metrics.compute_multiple_history([10.0, 12.0, 14.0], current=11.0).to_dict()
    assert stats["median"] == 12.0 and stats["n"] == 3
    # the thin alias yields the identical object
    assert metrics.compute_pe_history([10.0, 12.0, 14.0], 11.0).to_dict() == stats


def test_multiple_selection_by_sector():
    """finance/realestate → cwk, energy → ev_ebitda, everything else → cz —
    derived from malik.py applicability, not a second hard-coded map."""
    pick = lambda sg: scenarios.select_valuation_multiple(sg, malik.MALIK)
    assert pick("finance") == "cwk"
    assert pick("realestate") == "cwk"
    assert pick("energy") == "ev_ebitda"
    for sg in ("industrial", "tech", "consumer", "biotech_med", "other"):
        assert pick(sg) == "cz", sg


def test_target_price_cz_matches_hand_check():
    ss = scenarios.build_scenario_set(cz_inputs(), malik.MALIK).to_dict()
    by = _by_kind(ss)
    assert ss["valuation_multiple"] == "cz"
    # base: 14 × 2,5 = 35,0 → upside 35/25−1 = +40,0%
    assert by["base"]["target_price"] == 35.0
    assert by["base"]["implied_upside_pct"] == 40.0
    # negative: 11 × 2,5 = 27,5 (+10%); positive: 17 × 2,5 = 42,5 (+70%)
    assert by["negative"]["target_price"] == 27.5
    assert by["negative"]["implied_upside_pct"] == 10.0
    assert by["positive"]["target_price"] == 42.5
    assert by["positive"]["implied_upside_pct"] == 70.0
    assert by["base"]["target_multiple"]["value"] == 14.0
    assert "n=8" in by["base"]["target_multiple"]["basis_label"]
    assert by["negative"]["company_outcome"]["direction"] == "negative"
    assert "EPS / zysk na akcję" in by["negative"]["company_outcome"]["description"]
    assert by["base"]["company_outcome"]["direction"] == "neutral"
    assert by["positive"]["company_outcome"]["direction"] == "positive"


def test_target_price_cwk_matches_hand_check():
    ss = scenarios.build_scenario_set(cwk_inputs(), malik.MALIK).to_dict()
    by = _by_kind(ss)
    assert ss["valuation_multiple"] == "cwk"
    # bvps = 500 000 × 1000 / 10 000 000 = 50,0; base 1,0 × 50 = 50,0 (0%)
    assert by["base"]["target_price"] == 50.0
    assert by["base"]["implied_upside_pct"] == 0.0
    # neg 0,8 × 50 = 40,0 (−20%); pos 1,4 × 50 = 70,0 (+40%)
    assert by["negative"]["target_price"] == 40.0
    assert by["negative"]["implied_upside_pct"] == -20.0
    assert by["positive"]["target_price"] == 70.0
    assert by["positive"]["implied_upside_pct"] == 40.0


def test_target_price_ev_ebitda_matches_hand_check():
    ss = scenarios.build_scenario_set(ev_ebitda_inputs(), malik.MALIK).to_dict()
    by = _by_kind(ss)
    assert ss["valuation_multiple"] == "ev_ebitda"
    # base: EV = 6 × 100 000 × 1000 = 600 mln PLN; equity = 600 − 50 = 550 mln;
    # /10 mln akcji = 55,0 zł → upside 55/50−1 = +10,0%
    assert by["base"]["target_price"] == 55.0
    assert by["base"]["implied_upside_pct"] == 10.0
    # neg 35,0 (−30%); pos 75,0 (+50%)
    assert by["negative"]["target_price"] == 35.0
    assert by["negative"]["implied_upside_pct"] == -30.0
    assert by["positive"]["target_price"] == 75.0
    assert by["positive"]["implied_upside_pct"] == 50.0


def test_company_outcome_names_the_selected_operating_driver():
    cases_by_driver = (
        (cwk_inputs(), "wartość księgowa na akcję"),
        (ev_ebitda_inputs(), "EBITDA"),
    )
    for inputs, driver in cases_by_driver:
        ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
        for row in ss["scenarios"]:
            assert driver in row["company_outcome"]["description"]
            assert "wyłącznie rewersję mnożnika" in row["company_outcome"]["description"]


def test_probabilities_sum_to_one():
    for factory in (cz_inputs, cwk_inputs, ev_ebitda_inputs):
        ss = scenarios.build_scenario_set(factory(), malik.MALIK).to_dict()
        total = sum(s["probability"] for s in ss["scenarios"])
        assert abs(total - 1.0) <= 0.01, total
        assert [s["probability"] for s in ss["scenarios"]] == [0.25, 0.50, 0.25]


def test_weighted_expected_value_matches_hand_check():
    ss = scenarios.build_scenario_set(cz_inputs(), malik.MALIK).to_dict()
    # 0,25×27,5 + 0,50×35,0 + 0,25×42,5 = 6,875 + 17,5 + 10,625 = 35,0
    assert ss["weighted_expected_price"] == 35.0
    # 35,0 / 25,0 − 1 = +40,0%
    assert ss["weighted_expected_upside_pct"] == 40.0
    # cwk set: 0,25×40 + 0,5×50 + 0,25×70 = 52,5; 52,5/50−1 = +5,0%
    cwk = scenarios.build_scenario_set(cwk_inputs(), malik.MALIK).to_dict()
    assert cwk["weighted_expected_price"] == 52.5
    assert cwk["weighted_expected_upside_pct"] == 5.0


def test_downside_only_set_warns_and_avoids_positive_label():
    """CBF-style case: even the upper-quartile own-history path is below the
    current price. The internal `positive` id remains for compatibility, but the
    user-facing copy must not imply a positive return scenario."""
    inputs = _inputs(
        "tech",
        multiple_history=_hist(27.07, 23.66, 31.53, current=39.8, n=31),
        eps=4.7438,
        current_price=188.8,
        pe_history=_hist(27.07, 23.66, 31.53, current=39.8, n=31),
    )
    ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
    by = _by_kind(ss)

    assert by["positive"]["implied_upside_pct"] < 0
    assert "pozytywn" not in by["positive"]["label"].lower()
    assert ss["quality_warnings"]
    assert "ujemny potencjał" in ss["quality_warnings"][0]


def test_cz_scenario_labels_biznesradar_consensus_eps_driver():
    inputs = _inputs(
        "industrial",
        multiple_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8),
        eps=3.0,
        current_price=30.0,
        pe_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8),
        earnings_basis={
            "source": "biznesradar_forecasts",
            "source_field": "market_data.forecast_consensus.2026.net_income",
            "year": "2026",
            "net_income_tys_pln": 30_000.0,
            "eps": 3.0,
        },
    )

    ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
    by = _by_kind(ss)

    assert by["base"]["target_price"] == 42.0
    assert any("konsensusie analityków BiznesRadar 2026" in a for a in by["base"]["assumptions"])
    assert any("EPS z konsensusu analityków BiznesRadar 2026" in d for d in by["base"]["drivers"])
    allowed = scenarios.input_numbers(inputs) | scenarios.computed_numbers(ss)
    assert not (scenarios.prose_numbers(ss) - allowed)


def test_negative_base_positive_ordering():
    """Upside is monotone: negative ≤ base ≤ positive (Q1 ≤ median ≤ Q3)."""
    for factory in (cz_inputs, cwk_inputs, ev_ebitda_inputs):
        by = _by_kind(scenarios.build_scenario_set(factory(), malik.MALIK).to_dict())
        neg, bas, pos = (by[k]["implied_upside_pct"] for k in ("negative", "base", "positive"))
        assert neg <= bas <= pos, (neg, bas, pos)


def test_missing_driver_labels_gap_no_fabrication():
    """Energy name with NO EBITDA TTM and no C/Z fallback data → every target is
    None, the gap is labelled, and NOT A SINGLE number is invented in the prose."""
    inputs = _inputs("energy",
                     multiple_history=_hist(6.0, 4.0, 8.0, current=5.0, n=5),
                     ebitda_ttm=None, eps=None, current_price=50.0,
                     pe_history={})  # no cz fallback either
    ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
    assert all(s["target_price"] is None for s in ss["scenarios"])
    assert all(s["implied_upside_pct"] is None for s in ss["scenarios"])
    assert ss["weighted_expected_price"] is None
    # the gap is surfaced honestly (a labelled assumption on every scenario)
    for s in ss["scenarios"]:
        assert any("Luka danych" in a for a in s["assumptions"])
        assert s["target_multiple"]["value"] is None
    # fabrication guard: no prose number outside the sourced/computed allowed-set
    allowed = scenarios.input_numbers(inputs) | scenarios.computed_numbers(ss)
    assert not (scenarios.prose_numbers(ss) - allowed)


def test_missing_current_price_labels_gap_no_crash():
    """WP5 regression: found by cross-checking DEC's real fixture numbers (own
    C/Z history + EPS known — docs/validation-thesis.md — but the fixture profile
    carries NO price). Target price is computable, but with no current price to
    compare against the OLD code crashed formatting a `None` upside instead of
    labelling the gap. Must degrade honestly, never raise, never fabricate."""
    inputs = _inputs("industrial",
                     multiple_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8),
                     eps=2.5, current_price=None,
                     pe_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8))
    ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
    by = _by_kind(ss)
    # target price IS computable (EPS + own history known) ...
    assert by["base"]["target_price"] == 35.0
    # ... but upside is honestly None — never a fabricated comparison.
    assert by["base"]["implied_upside_pct"] is None
    assert ss["weighted_expected_price"] == 35.0
    assert ss["weighted_expected_upside_pct"] is None
    for s in ss["scenarios"]:
        text = " ".join(s["assumptions"] + [s["narrative"]]).lower()
        assert "brak bieżącego kursu" in text or "brak aktualnej ceny" in text
    # still passes the fabrication guard — the gap label adds no stray number.
    allowed = scenarios.input_numbers(inputs) | scenarios.computed_numbers(ss)
    assert not (scenarios.prose_numbers(ss) - allowed)


def test_ev_ebitda_missing_driver_falls_back_to_cz():
    """No EBITDA but a usable C/Z history → the engine falls back to C/Z (labelled)
    instead of yielding nothing."""
    inputs = _inputs("energy",
                     multiple_history=_hist(6.0, 4.0, 8.0, current=5.0, n=5),
                     ebitda_ttm=None, eps=2.0, current_price=20.0,
                     pe_history=_hist(10.0, 8.0, 12.0, current=9.0, n=7))
    ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
    assert ss["valuation_multiple"] == "cz"  # fell back
    by = _by_kind(ss)
    assert by["base"]["target_price"] == 20.0  # 10 × 2,0
    # the fallback is stated, not silent
    assert any("fallback" in a.lower() for s in ss["scenarios"] for a in s["assumptions"])


def test_every_scenario_number_is_traceable():
    """Fabrication guard over the deterministic set: every prose number is a
    subset of the sourced inputs ∪ the engine-computed numbers."""
    for factory in (cz_inputs, cwk_inputs, ev_ebitda_inputs):
        inputs = factory()
        ss = scenarios.build_scenario_set(inputs, malik.MALIK).to_dict()
        allowed = scenarios.input_numbers(inputs) | scenarios.computed_numbers(ss)
        invented = scenarios.prose_numbers(ss) - allowed
        assert not invented, f"{factory.__name__}: invented {invented}"


def test_disclaimer_and_framing_present():
    ss = scenarios.build_scenario_set(cz_inputs(), malik.MALIK).to_dict()
    assert ss["disclaimer"] == thesis.DISCLAIMER
    assert ss["framing"] == scenarios.FRAMING
    assert "sygnał" in ss["framing"]  # "punkt wejścia w analizę, nie sygnał"
    assert ss["engine"] == "deterministic"


def test_scenario_set_shape_and_engine():
    """The to_dict() shape mirrors the API contract (schemas.ScenarioSetOut)."""
    ss = scenarios.build_scenario_set(cz_inputs(), malik.MALIK).to_dict()
    assert set(ss) == {"scenarios", "valuation_multiple", "current_price",
                       "weighted_expected_price", "weighted_expected_upside_pct",
                       "framing", "disclaimer", "quality_warnings", "engine"}
    sc = ss["scenarios"][0]
    assert set(sc) == {"id", "kind", "label", "probability", "narrative",
                       "target_multiple", "target_price", "implied_upside_pct",
                       "horizon", "drivers", "assumptions", "company_outcome"}
    assert set(sc["target_multiple"]) == {"type", "value", "basis_label"}
    assert set(sc["horizon"]) == {"low_months", "high_months", "basis_label"}
    # deterministic engine emits no event scenarios (it cannot invent catalysts)
    assert all(s["kind"] != "event" for s in ss["scenarios"])
    assert sc["horizon"]["low_months"] == 12 and sc["horizon"]["high_months"] == 24


# ------------------------------------------------------------- in-session runner

if __name__ == "__main__":  # pragma: no cover — pytest ignores this block
    import sys

    fns = [(n, o) for n, o in sorted(globals().items())
           if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — report any error, keep going
            failed += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
