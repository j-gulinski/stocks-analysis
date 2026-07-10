"""AI valuation agent (services/valuation_ai.py) + WorkedCase corpus enrichment
(services/strategies/cases.py) — pure tests (stage SC / WP4).

Same style as test_scenarios_ai.py: hand-built inputs, plain asserts, a `__main__`
runner so it runs under `pytest` AND a bare system Python (no PyPI). Every AI path
uses an injected `StubTransport`; the real network transport is never touched.

Covered:
  * deterministic no-key fallback (== the deterministic valuation + marker,
    `potential == weighted_expected_upside_pct`, never raises);
  * the confidence heuristic at ALL THREE threshold levels (low/medium/high);
  * happy-path merge (engine == "ai"); malformed → clean fallback; iteration
    limit; convergence; cache hit/skip;
  * the fabrication guard (stray number rejected; scenario + corpus numbers
    allowed); framing + DISCLAIMER preserved on the AI path;
  * corpus integrity: lazy + import-pure `CORPUS`, ≥1 documented miss, every
    number is a sourced label (no bare fundamental), `evaluate_case` still runs.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from app.services import scenarios, thesis, thesis_ai, valuation_ai
from app.services import insights as I
from app.services.strategies import cases, malik


# ------------------------------------------------------------------ builders

def _ins(id, name, value, verdict, importance):
    return I.Insight(id, name, value, verdict, f"komentarz {name}", importance,
                     brief=f"{name} {value}")


# The Malik-applicable indicator ids, in a fixed order, so a test can ask for the
# first N to be computable (each a resolved verdict → counts toward `computable`).
_INDICATOR_SPECS = [
    ("gross_margin", "Marża brutto", "35,5%", 3),
    ("revenue_growth", "Dynamika przychodów", "12,0%", 3),
    ("pe_vs_history", "C/Z na tle historii", "9,5", 3),
    ("one_offs", "Zdarzenia jednorazowe", "8,0%", 2),
    ("net_cash", "Gotówka netto", "gotówka netto", 2),
    ("net_margin", "Marża netto", "10,0%", 2),
]


def _company(n_indicators):
    inds = [_ins(i, n, v, "good", imp) for i, n, v, imp in _INDICATOR_SPECS[:n_indicators]]
    return cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="industrial",
        sector="Przemysł", indicators=inds, missing=[])


def _hist(n):
    return {"median": 14.0, "q1": 11.0, "q3": 17.0, "current": 9.5,
            "percentile": 40.0, "n": n}


def _inputs(n_indicators=3, n_hist=8):
    """Industrial → C/Z, eps 2,5, current 25; own history 11/14/17.
    Deterministic scenarios: neg 27,5 (+10%), base 35 (+40%), pos 42,5 (+70%);
    weighted price 35,0 → weighted upside +40%."""
    ti = thesis.ThesisInputs(
        insights=_company(n_indicators),
        ttm={"pe": 9.5, "eps": 2.5, "price": 25.0, "net_profit": 4800.0},
        pe_history=_hist(n_hist),
        net_cash={"value": 12000.0, "note": ""})
    return scenarios.ScenarioInputs(
        thesis_inputs=ti,
        multiple_history=_hist(n_hist),
        eps=2.5,
        shares_outstanding=10_000_000,
        current_price=25.0,
        net_cash=12000.0,
        market_data={
            "industry_type": "Industrial",
            "advanced_metrics": {
                "roic": {"value": 12.0, "period": "2025Q1"},
                "fcf": {"value": 11000.0, "period": "2025Q1"},
                "enterprise_value": {"value": 238000000.0, "unit": "PLN"},
            },
            "forecast_consensus": {"2026": {"net_income": {"value": 5200.0}}},
            "dividend_coverage": {"status": "covered", "fcf_coverage_ratio": 1.4},
        },
    )


def _scenario_set(inputs=None):
    return scenarios.build_scenario_set(inputs or _inputs(), malik.MALIK).to_dict()


def _det_valuation(inputs, ss):
    return valuation_ai._build_deterministic_valuation(inputs, ss, malik.MALIK)[0]


# --------------------------------------------------------------- stub transport

class StubTransport:
    """Scripted `(messages, model) -> dict` delegate; counts calls and clamps to
    the last scripted response so a short script can be replayed."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.requests = []

    def __call__(self, messages, model):
        self.calls += 1
        self.requests.append((messages, model))
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


def _resp(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _text_resp(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _payload(det: dict, *, narrative="Rewizja oceny potencjału.", basis=None,
             rationale=None, wwc=None) -> dict:
    """A model-style refinement reusing the deterministic what_would_change ids
    (so the merge keeps a valid gap set); prose fields overridable per test."""
    return {
        "potential_basis_label": basis or det["potential"]["basis_label"],
        "confidence_rationale": rationale or det["confidence"]["rationale"],
        "what_would_change": wwc if wwc is not None else [
            {"id": w["id"], "text": w["text"], "why": w["why"]}
            for w in det["what_would_change"]
        ],
        "narrative": narrative,
        "changes": [{"field": "narrative", "rationale": "iteracja"}],
        "case_similarity": [{"ticker": "DGN", "note": "podobny wzorzec"}],
    }


def _settings(**overrides):
    base = dict(anthropic_api_key="test-key", anthropic_model="claude-test",
                anthropic_max_iterations=1, ai_cache_enabled=False, ai_cache_dir=None)
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ---------------------------------------------------------- valuation_ai tests

def test_module_imports_without_pypi():
    """Acceptance 1: SDK + pydantic settings are lazy — importing us pulls
    neither. Checked in a FRESH subprocess so a sibling test that already
    imported app.config (which imports pydantic_settings) can't pollute this
    process's sys.modules and make the assertion order-dependent."""
    probe = (
        "import sys, app.services.valuation_ai\n"
        "assert 'anthropic' not in sys.modules, 'anthropic imported eagerly'\n"
        "assert 'pydantic_settings' not in sys.modules, "
        "'pydantic_settings imported eagerly'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parent.parent,  # backend/ so `app` imports
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert callable(valuation_ai.assess_potential)


def test_no_key_fallback_is_deterministic():
    """Acceptance 2: no key → exactly the deterministic valuation + marker;
    potential == the scenario set's weighted upside; never raises, no ai_notes."""
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out == {**det, "engine": "deterministic"}
    assert "ai_notes" not in out
    assert out["potential"]["value_pct"] == ss["weighted_expected_upside_pct"] == 40.0


def test_anthropic_path_requires_premium_context():
    inputs = _inputs()
    inputs.market_data = {}
    ss = _scenario_set(inputs)
    try:
        valuation_ai.assess_potential(
            inputs, ss, malik.MALIK, transport=StubTransport([]), settings=_settings()
        )
    except valuation_ai.ValuationContextError as exc:
        assert "ROIC" in str(exc)
        assert "FCF" in str(exc)
    else:
        raise AssertionError("expected ValuationContextError")


def test_confidence_low_below_min_key_indicators():
    """Acceptance 4: < 3 computable key indicators → low."""
    inputs = _inputs(n_indicators=2, n_hist=8)
    ss = _scenario_set(inputs)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out["confidence"]["level"] == "low"


def test_confidence_low_when_history_empty():
    """Acceptance 4: n == 0 (empty own history) → low even with full coverage."""
    inputs = _inputs(n_indicators=6, n_hist=0)
    ss = _scenario_set(inputs)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out["confidence"]["level"] == "low"


def test_confidence_medium_mid_coverage():
    """Acceptance 4: 3–4 key indicators → medium (the boundary case)."""
    inputs = _inputs(n_indicators=3, n_hist=8)
    ss = _scenario_set(inputs)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out["confidence"]["level"] == "medium"


def test_confidence_medium_high_coverage_thin_history():
    """Acceptance 4: ≥ 5 key indicators but n < 4 → still medium."""
    inputs = _inputs(n_indicators=6, n_hist=3)
    ss = _scenario_set(inputs)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out["confidence"]["level"] == "medium"


def test_confidence_high_full_coverage_deep_history():
    """Acceptance 4: ≥ 5 key indicators AND n ≥ 4 → high."""
    inputs = _inputs(n_indicators=6, n_hist=8)
    ss = _scenario_set(inputs)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out["confidence"]["level"] == "high"


def test_what_would_change_never_empty_and_carries_thesis_gaps():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    out = valuation_ai.assess_potential(
        inputs, ss, malik.MALIK, settings=_settings(anthropic_api_key=None))
    ids = [w["id"] for w in out["what_would_change"]]
    assert ids  # never empty while the strategy carries verify-gaps
    assert "catalyst" in ids and "backlog" in ids  # thesis verify_next gaps
    assert "scenario_reversion" in ids  # the scenario assumption itself


def test_happy_path_merges_and_marks_ai():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    stub = StubTransport([_resp(_payload(det, narrative="Potencjał po rewizji."))])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings())
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 1
    assert out["ai_notes"]["model"] == "claude-test"
    assert out["narrative"] == "Potencjał po rewizji."
    # structured facts are re-imposed (never taken from the model)
    assert out["potential"]["value_pct"] == 40.0
    assert out["confidence"]["level"] == det["confidence"]["level"]


def test_malformed_response_falls_back_cleanly():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    stub = StubTransport([_text_resp("Nie mogę teraz zwrócić JSON.")])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings())
    assert out == {**det, "engine": "deterministic"}
    assert stub.calls == 1


def test_iteration_limit_caps_transport_calls():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    responses = [
        _resp(_payload(det, narrative="Analiza pierwsza.")),
        _resp(_payload(det, narrative="Analiza druga.")),
        _resp(_payload(det, narrative="Analiza trzecia.")),
    ]
    stub = StubTransport(responses)
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings(anthropic_max_iterations=2))
    assert stub.calls == 2  # never the third
    assert out["ai_notes"]["iterations"] == 2


def test_convergence_stops_early():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    same = _resp(_payload(det, narrative="Stabilna rewizja."))
    stub = StubTransport([same])  # clamps → same response every call
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings(anthropic_max_iterations=5))
    assert stub.calls == 2  # first change, second no-change → converge
    assert out["ai_notes"]["iterations"] == 1


def test_fabrication_guard_rejects_out_of_allowed_number():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    bad = _payload(det, narrative="Ukryty potencjał 888,8% w tym roku.")
    stub = StubTransport([_resp(bad)])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings())
    assert out == {**det, "engine": "deterministic"}  # whole round rejected
    assert 888.8 not in valuation_ai._prose_numbers(out)


def test_scenario_number_allowed():
    """A deterministic scenario target quoted by the model survives the guard."""
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    # 35 = the base scenario target price (in scenario_numbers)
    good = _payload(det, narrative="Cena docelowa bazowa 35 zł wspiera potencjał.")
    stub = StubTransport([_resp(good)])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings())
    assert out["engine"] == "ai"
    assert "35" in out["narrative"]


def test_corpus_number_allowed():
    """A figure CITED from the injected worked-case corpus survives the guard."""
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    case = cases.WorkedCase(
        ticker="XYZ9", as_of="2024-01",
        inputs=thesis.ThesisInputs(insights=_company(0)),
        gaps=["repricing trwał 18 miesięcy przy mnożniku 7,3 [XYZ]"],
        citation="synthetic corpus", outcome="hit")
    good = _payload(det, narrative="Porównywalny repricing przy mnożniku 7,3.")
    stub = StubTransport([_resp(good)])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings(), corpus=[case])
    assert out["engine"] == "ai"
    assert "7,3" in out["narrative"]


def test_cache_hit_skips_transport():
    tmp = Path(tempfile.mkdtemp(prefix="valuation_ai_cache_"))
    try:
        inputs = _inputs()
        ss = _scenario_set(inputs)
        det = _det_valuation(inputs, ss)
        stub = StubTransport([_resp(_payload(det, narrative="Baza."))])
        cfg = _settings(ai_cache_enabled=True, ai_cache_dir=str(tmp))
        first = valuation_ai.assess_potential(inputs, ss, malik.MALIK, ticker="TST",
                                              transport=stub, settings=cfg)
        second = valuation_ai.assess_potential(inputs, ss, malik.MALIK, ticker="TST",
                                               transport=stub, settings=cfg)
        assert stub.calls == 1  # second served from cache
        assert first == second and first["engine"] == "ai"
        assert len(list(tmp.glob("*.json"))) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cache_disabled_bypasses_cache():
    tmp = Path(tempfile.mkdtemp(prefix="valuation_ai_nocache_"))
    try:
        inputs = _inputs()
        ss = _scenario_set(inputs)
        det = _det_valuation(inputs, ss)
        stub = StubTransport([_resp(_payload(det, narrative="Baza."))])
        cfg = _settings(ai_cache_enabled=False, ai_cache_dir=str(tmp))
        valuation_ai.assess_potential(inputs, ss, malik.MALIK, ticker="TST",
                                      transport=stub, settings=cfg)
        valuation_ai.assess_potential(inputs, ss, malik.MALIK, ticker="TST",
                                      transport=stub, settings=cfg)
        assert stub.calls == 2
        assert not list(tmp.glob("*.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_framing_and_disclaimer_preserved_on_ai_path():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    stub = StubTransport([_resp(_payload(det, narrative="Baza po rewizji."))])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings())
    assert out["framing"] == valuation_ai.FRAMING
    assert out["disclaimer"] == thesis.DISCLAIMER


def test_transport_error_falls_back_without_raising():
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)

    def _boom(messages, model):
        raise RuntimeError("network down")

    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=_boom,
                                        settings=_settings())
    assert out == {**det, "engine": "deterministic"}


def test_invented_wwc_id_is_ignored_not_merged():
    """A model response inventing a brand-new what_would_change id must not add a
    gap; the deterministic gap set is preserved."""
    inputs = _inputs()
    ss = _scenario_set(inputs)
    det = _det_valuation(inputs, ss)
    payload = _payload(det, narrative="Rewizja.", wwc=[
        {"id": "totally_invented_gap", "text": "Nowa luka spoza tezy.", "why": "x"}])
    stub = StubTransport([_resp(payload)])
    out = valuation_ai.assess_potential(inputs, ss, malik.MALIK, transport=stub,
                                        settings=_settings())
    out_ids = {w["id"] for w in out["what_would_change"]}
    assert "totally_invented_gap" not in out_ids
    assert {w["id"] for w in det["what_would_change"]} <= out_ids  # none lost


# ------------------------------------------------------ corpus integrity tests

def test_corpus_is_lazy_and_import_pure():
    """Acceptance 3: `CORPUS` is served by PEP 562 `__getattr__` (no eager
    module-level build), returns a plain tuple, and importing cases pulls no
    PyPI (the circular-import fix survives)."""
    assert "anthropic" not in sys.modules
    assert hasattr(cases, "__getattr__")
    assert "CORPUS" not in cases.__dict__  # not an eager module attribute
    corpus = cases.CORPUS
    assert isinstance(corpus, tuple) and len(corpus) >= 3
    # unknown attribute still raises (the guard is a real __getattr__)
    try:
        cases.DOES_NOT_EXIST  # noqa: B018
        raised = False
    except AttributeError:
        raised = True
    assert raised


def test_corpus_has_documented_miss():
    """Acceptance 3 / plan §"No survivorship bias": ≥ 1 case tagged as a miss."""
    misses = [c for c in cases.CORPUS if c.outcome == "miss"]
    assert misses, "corpus is survivorship-biased — no documented miss"
    miss = misses[0]
    assert miss.citation and miss.sources  # the miss is sourced, not a bare claim


def test_corpus_numbers_are_all_sourced_no_bare_fundamentals():
    """Acceptance 3: every numeric field carries a `sources` label — i.e. NO
    reconstructed fundamental (a bare number) exists; all numbers live in the
    sourced text (sources/citation/as_of/gaps). Proven by: each case has zero
    reconstructed indicators, and each case that carries numbers has a non-empty
    citation."""
    for case in cases.CORPUS:
        # no reconstructed fundamentals → no bare (unsourced) numeric field
        assert case.inputs.insights.key_indicators == [], case.ticker
        # every case carries a citation anchoring its sourced material
        assert case.citation, case.ticker


def test_corpus_enriched_multiples_and_durations_are_citable():
    """Acceptance 3 + plan §WP4b: the real sourced multiples / repricing
    durations land in the fabrication allowed-set via
    `scenarios_ai.collect_corpus_numbers` (so a scenario/valuation may CITE
    them)."""
    from app.services import scenarios_ai
    citable = scenarios_ai.collect_corpus_numbers(cases.CORPUS)
    # DGN "+2500% w 5 lat (≈60 mies.)"; OPTEX "C/Z ~12, prognoza <10";
    # Suntech entry "~2,40 zł" — each sourced, each now citable.
    for figure in (2500.0, 60.0, 12.0, 10.0, 2.4):
        assert figure in citable, figure


def test_evaluate_case_runs_on_enriched_cases():
    """Acceptance 3: `evaluate_case` runs on the enriched DGN / comparable / miss
    cases and returns the honest `insufficient_data` read (0 computable
    indicators by construction — the data gaps, not an engine failure)."""
    for case in cases.CORPUS:
        result = cases.evaluate_case(malik.MALIK, case)
        assert result["thesis"]["entry_quality"]["code"] == "insufficient_data", case.ticker
        assert result["ticker"] == case.ticker


# ------------------------------------------------------------- in-session runner

if __name__ == "__main__":  # pragma: no cover — pytest ignores this block
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
