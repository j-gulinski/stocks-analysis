"""Investment-thesis engine (services/thesis.py) — pure unit tests.

Mirrors test_insights.py: hand-built inputs, explicit honesty assertions. Four
archetypes prove the engine adapts the *read* to the company, and a second
"toy" profile over the SAME inputs proves the engine is strategy-agnostic.

Runs two ways so it works with AND without PyPI:
  * `pytest` collects the `test_*` functions on the user's machine (no pytest
    import needed here — plain asserts);
  * in the sandbox (no pytest) `python tests/test_thesis.py` runs the same
    functions via the tiny runner at the bottom.
"""
from __future__ import annotations

import re

from app.services import insights as I
from app.services import thesis
from app.services.strategies import base, cases, malik


# ------------------------------------------------------------------ builders

def _ins(id, name, value, verdict, comment, importance, brief):
    return I.Insight(id, name, value, verdict, comment, importance, brief=brief)


def _inputs(company, **kw):
    return thesis.ThesisInputs(insights=company, **kw)


def _industrial_company(*, net_margin_missing=True):
    """Small profitable industrial with the full Malik-relevant set."""
    indicators = [
        _ins("gross_margin", "Marża brutto na sprzedaży", "35,5%", "good",
             "Marża brutto rośnie (+0,8 p.p. vs 4 wcześniejsze kwartały) — u "
             "Malika to główny motor tezy inwestycyjnej.", 3,
             "marża brutto 35,5% (+0,8 p.p.)"),
        _ins("revenue_growth", "Dynamika przychodów r/r", "12,0%", "good",
             "Przychody rosną śr. 12,0% r/r w ostatnich kwartałach — zdrowa "
             "dynamika.", 3, "przychody +12,0% r/r"),
        _ins("operating_leverage", "Dźwignia operacyjna", "+18% vs +12%", "good",
             "Zysk ze sprzedaży +18% vs przychody +12% r/r — koszty rosną "
             "wolniej niż biznes.", 2,
             "zysk ze sprzedaży +18% przy przychodach +12% r/r"),
        _ins("pe_vs_history", "C/Z na tle własnej historii", "9,5", "good",
             "C/Z 9,5 wyraźnie poniżej własnej mediany 14,0 — historycznie "
             "tanio, jeśli wyniki się utrzymają.", 3,
             "C/Z 9,5 vs własna mediana 14,0"),
        _ins("one_offs", "Udział zdarzeń jednorazowych", "8,0%", "good",
             "One-offy to tylko 8,0% zysku operacyjnego — wynik wygląda na "
             "powtarzalny.", 2, "one-offy 8,0% zysku oper."),
        _ins("debt_load", "Zadłużenie", "gotówka netto", "good",
             "Więcej gotówki niż długu (12 mln zł) — bilans bezpieczny.", 2,
             "gotówka netto 12 mln zł"),
    ]
    missing = []
    if net_margin_missing:
        missing.append(I.MissingData(
            "net_margin", "Marża netto",
            "Brak zysku netto lub przychodów w danych kwartalnych — źródło: "
            "rachunek zysków i strat."))
    company = cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="industrial",
        sector="Przemysł elektromaszynowy", indicators=indicators, missing=missing)
    return company


def industrial_inputs():
    return _inputs(
        _industrial_company(),
        ttm={"pe": 9.5, "net_profit": 4800.0, "market_cap": 450e6},
        pe_history={"median": 14.0, "current": 9.5},
        net_cash={"value": 12000.0, "note": "Gotówka minus dług finansowy."},
        latest_forecast={"result": {"forward": {"pe": 8.7}}},
    )


def moloch_inputs():
    """Large cap that would be attractive on the numbers — must be demoted by
    the sweet-spot penalty (spec principle 9)."""
    indicators = [
        _ins("gross_margin", "Marża brutto na sprzedaży", "28,0%", "good",
             "Marża brutto rośnie (+0,6 p.p.) — motor tezy.", 3,
             "marża brutto 28,0% (+0,6 p.p.)"),
        _ins("revenue_growth", "Dynamika przychodów r/r", "9,0%", "good",
             "Przychody rosną śr. 9,0% r/r — zdrowa dynamika.", 2,
             "przychody +9,0% r/r"),
        _ins("pe_vs_history", "C/Z na tle własnej historii", "10,0", "good",
             "C/Z 10,0 wyraźnie poniżej własnej mediany 15,0 — historycznie "
             "tanio.", 3, "C/Z 10,0 vs własna mediana 15,0"),
        _ins("one_offs", "Udział zdarzeń jednorazowych", "6,0%", "good",
             "One-offy to tylko 6,0% zysku operacyjnego — wynik powtarzalny.", 2,
             "one-offy 6,0% zysku oper."),
        _ins("debt_load", "Zadłużenie", "gotówka netto", "good",
             "Więcej gotówki niż długu (900 mln zł) — bilans bezpieczny.", 2,
             "gotówka netto 900 mln zł"),
    ]
    company = cases.build_case_insights(
        size_code="large", size_label="Duża spółka", sector_group="industrial",
        sector="Przemysł", indicators=indicators, missing=[])
    return _inputs(
        company,
        ttm={"pe": 10.0, "net_profit": 500000.0, "market_cap": 8e9},
        pe_history={"median": 15.0, "current": 10.0},
        net_cash={"value": 900000.0, "note": ""},
        latest_forecast=None,
    )


def biotech_inputs():
    """Cash-burning biotech: net loss, no valuation, thin data → honest gap."""
    indicators = [
        _ins("cash_runway", "Zapas gotówki (runway)", "~2,5 roku", "good",
             "Gotówka netto 30 mln zł przy stracie TTM -12 mln zł — wystarczy "
             "na ~2,5 roku działalności bez emisji.", 3, "runway ~2,5 roku"),
        _ins("revenue_growth", "Dynamika przychodów r/r", "40,0%", "good",
             "Przychody rosną śr. 40,0% r/r — kluczowe dla wyceny spółki "
             "wzrostowej.", 3, "przychody +40,0% r/r"),
    ]
    missing = [
        I.MissingData("one_offs", "Udział zdarzeń jednorazowych",
                      "Brak danych o pozostałej działalności operacyjnej."),
        I.MissingData("gross_margin", "Marża brutto na sprzedaży",
                      "Nie da się policzyć marży brutto."),
        I.MissingData("pe_vs_history", "C/Z na tle własnej historii",
                      "Brak bieżącego C/Z (spółka nierentowna TTM)."),
    ]
    company = cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="biotech_med",
        sector="Biotechnologia", indicators=indicators, missing=missing)
    return _inputs(
        company,
        ttm={"pe": None, "net_profit": -12000.0, "market_cap": 300e6},
        pe_history={"median": 20.0, "current": None},
        net_cash={"value": 30000.0, "note": ""},
        latest_forecast=None,
    )


def weak_inputs():
    """Enough data, but the market already prices the improvement → weak."""
    indicators = [
        _ins("gross_margin", "Marża brutto na sprzedaży", "22,0%", "neutral",
             "Marża brutto stabilna (+0,1 p.p.) — ani motor, ani hamulec.", 3,
             "marża brutto 22,0% (+0,1 p.p.)"),
        _ins("revenue_growth", "Dynamika przychodów r/r", "3,0%", "good",
             "Przychody rosną śr. 3,0% r/r — zdrowa dynamika.", 2,
             "przychody +3,0% r/r"),
        _ins("pe_vs_history", "C/Z na tle własnej historii", "22,0", "bad",
             "C/Z 22,0 powyżej własnej mediany 12,0 — rynek już wycenia "
             "poprawę.", 3, "C/Z 22,0 vs własna mediana 12,0"),
        _ins("one_offs", "Udział zdarzeń jednorazowych", "10,0%", "good",
             "One-offy to tylko 10,0% zysku operacyjnego — wynik powtarzalny.",
             2, "one-offy 10,0% zysku oper."),
        _ins("debt_load", "Zadłużenie", "gotówka netto", "good",
             "Więcej gotówki niż długu (5 mln zł) — bilans bezpieczny.", 2,
             "gotówka netto 5 mln zł"),
    ]
    company = cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="industrial",
        sector="Przemysł", indicators=indicators, missing=[])
    return _inputs(
        company,
        ttm={"pe": 22.0, "net_profit": 3000.0, "market_cap": 400e6},
        pe_history={"median": 12.0, "current": 22.0},
        net_cash={"value": 5000.0, "note": ""},
        latest_forecast=None,
    )


# --------------------------------------------------------------- toy profile

def toy_profile():
    """A deliberately different strategy: revenue+dividend heavy, valuation is a
    CONTRARIAN signal (cheap = weakness), size preference INVERTED (favours big
    caps). Same inputs → different read ⇒ the engine holds no Malik literals."""
    criteria = (
        base.Criterion("revenue_growth", "Momentum przychodów", 3.0),
        base.Criterion("dividend", "Dywidenda (fundament)", 3.0),
        base.Criterion("gross_margin", "Marża", 1.0),
        # contrarian: a LOW multiple is a weakness, a high one a strength
        base.Criterion("pe_vs_history", "Wycena (kontra)", 1.0,
                       direction=base.BAD_IS_STRENGTH),
        base.Criterion("one_offs", "Jakość zysku", 1.0),
        base.Criterion("debt_load", "Zadłużenie", 1.0),
    )
    rule = base.EntryQualityRule(
        valuation=frozenset({"pe_vs_history"}),
        growth=frozenset({"revenue_growth", "gross_margin"}),
        veto=frozenset({"one_offs"}),
        min_key_indicators=3, weak_bad_count=2, high_importance_level=3,
        sweet_spot_sizes=frozenset({"large"}),        # inverted
        penalised_sizes=frozenset({"micro", "small"}),  # inverted
    )
    gaps = (base.VerifyGap("momentum", "Sprawdź momentum kursu.",
                           "Strategia zabawkowa skupia się na sile względnej."),)
    return base.StrategyProfile(
        id="toy", label="Profil testowy", spec_ref="(test)", criteria=criteria,
        entry_rule=rule, verify_gaps=gaps, size_weight=3.0,
        size_pro_text="Duża spółka ({size}) — preferowana przez ten profil.",
        size_con_text="Mała spółka ({size}) — poza preferencją tego profilu.",
        size_principle="Preferencja rozmiaru")


# ----------------------------------------------------------- number helpers

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def _numbers(text):
    return {round(float(tok.replace(",", ".")), 4) for tok in _NUM.findall(text)}


def _output_numbers(td):
    """Every number the read shows the user (prose only — weights are metadata,
    not claims about the company)."""
    parts = [td["entry_quality"]["label"], td["entry_quality"]["rationale"],
             td["thesis_read"], td["valuation_basis"], td["disclaimer"]]
    for f in td["pros"] + td["cons"]:
        parts.append(f["text"])
    for v in td["verify_next"]:
        parts += [v["text"], v["why"]]
    out = set()
    for p in parts:
        out |= _numbers(p)
    return out


def _input_numbers(inp):
    """Every number available in the inputs — including the Insight strings and
    the coverage note the engine is allowed to quote verbatim. If a number in
    the read is not found here, the engine invented it."""
    company = inp.insights
    parts = [str(company.coverage), str(company.data_notes), company.summary,
             company.size_label or ""]
    for ins in company.key_indicators:
        parts += [ins.name, ins.value, ins.comment, ins.brief or ""]
    for m in company.missing:
        parts += [m.name, m.why]
    parts += [str(inp.ttm), str(inp.pe_history), str(inp.net_cash),
              str(inp.latest_forecast), str(inp.prescore)]
    nums = set()
    for p in parts:
        nums |= _numbers(p)
    return nums


ALL_INPUTS = {
    "industrial": industrial_inputs,
    "moloch": moloch_inputs,
    "biotech": biotech_inputs,
    "weak": weak_inputs,
}


# ------------------------------------------------------------------- tests

def test_industrial_small_reads_attractive():
    td = thesis.build_thesis(industrial_inputs(), malik.MALIK).to_dict()
    assert td["entry_quality"]["code"] in ("attractive", "neutral")
    assert td["entry_quality"]["code"] == "attractive"  # this fixture: clean setup
    # ordered by weight desc → the two 3.0-weight pillars lead
    assert [p["id"] for p in td["pros"]][:2] == ["gross_margin", "pe_vs_history"]
    # small cap → the sweet-spot factor is a PRO here
    assert any(p["id"] == "size" for p in td["pros"])
    assert td["strategy"] == {"id": "malik", "label": "Paweł Malik (OBS)"}
    # forward C/Z preferred + quoted
    assert "forward" in td["valuation_basis"] and "8,7" in td["valuation_basis"]


def test_large_moloch_carries_sweet_spot_penalty():
    td = thesis.build_thesis(moloch_inputs(), malik.MALIK).to_dict()
    # numbers say attractive, but a moloch is demoted (spec principle 9)
    assert td["entry_quality"]["code"] == "neutral"
    assert "sweet spot" in td["entry_quality"]["rationale"].lower()
    size_con = [c for c in td["cons"] if c["id"] == "size"]
    assert size_con and "Duża spółka" in size_con[0]["text"]
    # no saved forecast → honest trailing fallback
    assert "TTM" in td["valuation_basis"] and "10,0" in td["valuation_basis"]


def test_size_factor_label_not_duplicated():
    """Regression: the sweet-spot pro/con must carry the size label exactly once,
    not 'Mała spółka (Mała spółka)' / 'Duża spółka (Duża spółka)'."""
    td = thesis.build_thesis(industrial_inputs(), malik.MALIK).to_dict()
    size_pro = next(p for p in td["pros"] if p["id"] == "size")
    assert size_pro["text"].startswith("Mała spółka —")
    assert "Mała spółka (Mała spółka)" not in size_pro["text"]

    tc = thesis.build_thesis(moloch_inputs(), malik.MALIK).to_dict()
    size_con = next(c for c in tc["cons"] if c["id"] == "size")
    assert size_con["text"].startswith("Duża spółka —")
    assert "Duża spółka (Duża spółka)" not in size_con["text"]


def test_biotech_cash_burn_reads_insufficient():
    td = thesis.build_thesis(biotech_inputs(), malik.MALIK).to_dict()
    assert td["entry_quality"]["code"] in ("weak", "insufficient_data")
    assert td["entry_quality"]["code"] == "insufficient_data"  # thin + no C/Z
    # the missing valuation indicator is a verify item, never a fabricated con
    vn_ids = [v["id"] for v in td["verify_next"]]
    assert "pe_vs_history" in vn_ids
    assert all(c["id"] != "pe_vs_history" for c in td["cons"])
    # unprofitable, no forecast → valuation cannot be assessed, said plainly
    assert "Brak C/Z" in td["valuation_basis"]


def test_weak_when_market_already_prices_it():
    td = thesis.build_thesis(weak_inputs(), malik.MALIK).to_dict()
    assert td["entry_quality"]["code"] == "weak"
    assert "mediany" in td["entry_quality"]["rationale"]
    # the expensive multiple is a weighted con
    assert any(c["id"] == "pe_vs_history" for c in td["cons"])


def test_disclaimer_present_everywhere():
    for name, factory in ALL_INPUTS.items():
        td = thesis.build_thesis(factory(), malik.MALIK).to_dict()
        assert td["disclaimer"] == thesis.DISCLAIMER
        assert td["disclaimer"].strip()
        assert td["thesis_read"].rstrip().endswith(td["disclaimer"])


def test_no_fabricated_numbers():
    """Fabrication guard: every number in the read exists in the inputs."""
    for name, factory in ALL_INPUTS.items():
        inp = factory()
        td = thesis.build_thesis(inp, malik.MALIK).to_dict()
        invented = _output_numbers(td) - _input_numbers(inp)
        assert not invented, f"{name}: invented numbers {invented}"


def test_every_factor_and_verify_is_traceable():
    """Each pro/con text is a verbatim Insight comment (proves reuse, no
    divergence); the size factor comes from the profile template. Each verify
    item traces to a missing gap, the one-off check, or a profile gap."""
    for name, factory in ALL_INPUTS.items():
        inp = factory()
        company = inp.insights
        comments = {ins.id: ins.comment for ins in company.key_indicators}
        miss = {m.id: m.why for m in company.missing}
        gaps = {g.id: g.why for g in malik.MALIK.verify_gaps}
        td = thesis.build_thesis(inp, malik.MALIK).to_dict()

        for f in td["pros"] + td["cons"]:
            if f["id"] == "size":
                assert company.size_label in f["text"]
            else:
                assert f["text"] == comments[f["id"]], f"{name}/{f['id']} not verbatim"

        for v in td["verify_next"]:
            if v["id"] in miss:
                assert v["why"] == miss[v["id"]]
            elif v["id"] == "one_off_risk":
                assert v["why"]  # fixed, non-empty
            else:
                assert v["id"] in gaps and v["why"] == gaps[v["id"]]


def test_missing_inputs_route_to_verify_next_not_pros_cons():
    inp = industrial_inputs()
    td = thesis.build_thesis(inp, malik.MALIK).to_dict()
    factor_ids = {f["id"] for f in td["pros"] + td["cons"]}
    for m in inp.insights.missing:
        assert m.id in {v["id"] for v in td["verify_next"]}
        assert m.id not in factor_ids  # never fabricated into a pro/con


def test_verify_next_always_carries_strategy_gaps():
    """The human/AI-check gaps (catalyst, backlog, …) are always present — the
    entrance to human analysis (spec §Implications)."""
    td = thesis.build_thesis(industrial_inputs(), malik.MALIK).to_dict()
    vn_ids = {v["id"] for v in td["verify_next"]}
    assert {"catalyst", "backlog", "management", "thesis_recheck"} <= vn_ids


def test_reuses_insight_numbers_no_divergence():
    """Acceptance 3: a spot-check that the thesis quotes the exact insight
    number, not a recomputed one."""
    inp = industrial_inputs()
    pe_insight = next(i for i in inp.insights.key_indicators if i.id == "pe_vs_history")
    td = thesis.build_thesis(inp, malik.MALIK).to_dict()
    pe_pro = next(p for p in td["pros"] if p["id"] == "pe_vs_history")
    assert pe_pro["text"] == pe_insight.comment
    assert "9,5" in pe_pro["text"]  # the insight's C/Z, unchanged


# --------------------------------------------------------------- genericity

def test_toy_profile_changes_the_read_on_same_inputs():
    inp = industrial_inputs()
    malik_td = thesis.build_thesis(inp, malik.MALIK).to_dict()
    toy_td = thesis.build_thesis(inp, toy_profile()).to_dict()

    assert toy_td["strategy"] == {"id": "toy", "label": "Profil testowy"}
    # inverted size preference → the small cap is now a CON, not a PRO
    assert any(c["id"] == "size" for c in toy_td["cons"])
    assert all(p["id"] != "size" for p in toy_td["pros"])
    # contrarian valuation direction → the cheap C/Z flips from pro to con
    assert any(c["id"] == "pe_vs_history" for c in toy_td["cons"])
    assert any(p["id"] == "pe_vs_history" for p in malik_td["pros"])
    # and the overall verdict differs (small cap demoted by the toy profile)
    assert toy_td["entry_quality"]["code"] != malik_td["entry_quality"]["code"]


def test_thesis_module_holds_no_strategy_literals():
    """thesis.py must contain no Malik thresholds / size-code / profile-id
    literals — those live only in malik.py (grep-style genericity guard)."""
    with open(thesis.__file__, encoding="utf-8") as fh:
        src = fh.read()
    for banned in ('0.85', '1.15', '"micro"', '"small"', '"mid"', '"large"',
                   '"malik"'):
        assert banned not in src, f"strategy literal {banned!r} leaked into thesis.py"


# ------------------------------------------------------------- worked cases

def test_evaluate_case_runs_on_partial_snapshot():
    """A synthetic WorkedCase with a partial, per-field-sourced snapshot; the
    engine must run on it and match the expected read (DGN/SNT arrive in WP4)."""
    company = cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="industrial",
        indicators=[
            _ins("pe_vs_history", "C/Z na tle własnej historii", "8,0", "good",
                 "C/Z 8,0 poniżej własnej mediany 13,0 — historycznie tanio.", 3,
                 "C/Z 8,0 vs własna mediana 13,0"),
            _ins("gross_margin", "Marża brutto na sprzedaży", "30,0%", "good",
                 "Marża brutto rośnie (+1,0 p.p.) — motor tezy.", 3,
                 "marża brutto 30,0% (+1,0 p.p.)"),
            _ins("debt_load", "Zadłużenie", "gotówka netto", "good",
                 "Więcej gotówki niż długu (10 mln zł) — bilans bezpieczny.", 2,
                 "gotówka netto 10 mln zł"),
        ],
        missing=[I.MissingData("one_offs", "Udział zdarzeń jednorazowych",
                               "Brak danych o pozostałej działalności.")])
    case = cases.WorkedCase(
        ticker="SYN", as_of="2024-01",
        inputs=thesis.ThesisInputs(
            insights=company,
            ttm={"pe": 8.0, "net_profit": 2000.0, "market_cap": 300e6},
            pe_history={"median": 13.0, "current": 8.0},
            net_cash={"value": 10000.0, "note": ""}),
        sources={"pe_vs_history": "BiznesRadar C/Z history",
                 "gross_margin": "BiznesRadar income (Q)",
                 "catalyst": "forum digest (nieodtworzone)"},
        expected_read={"entry_quality": "attractive"},
        citation="synthetic — WP2 smoke case",
        gaps=["katalizator nieznany z danych", "backlog nie scrapowany"])

    out = cases.evaluate_case(malik.MALIK, case)
    assert out["ticker"] == "SYN"
    assert out["thesis"]["entry_quality"]["code"] == "attractive"
    assert out["matches"]["entry_quality"] is True
    assert out["gaps"] and out["sources"]  # provenance + honesty preserved


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
