"""Iterative Claude-API scenario refiner (services/scenarios_ai.py) — pure tests.

Same style as test_thesis_ai.py: hand-built inputs, plain asserts, a `__main__`
runner so it runs under `pytest` AND a bare system Python (no PyPI). Every path
uses an injected `StubTransport`; the real network transport is never touched.
Covered: happy-path merge, malformed fallback, iteration limit, convergence, the
widened fabrication guard (input / corpus / engine numbers), probability
renormalisation after an AI-added event scenario, the no-key deterministic
fallback, cache hit/skip, and that framing + DISCLAIMER survive the AI path.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from app.services import scenarios, scenarios_ai, thesis
from app.services.strategies import cases, malik


# ------------------------------------------------------------------ builders

def _company(sector_group="industrial"):
    return cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group=sector_group,
        sector="Przemysł", indicators=[], missing=[])


def _hist(median, q1, q3, *, current=None, n):
    return {"median": median, "q1": q1, "q3": q3, "current": current,
            "percentile": None, "n": n}


def _inputs():
    """Industrial → C/Z, eps 2,5, current 25; own history 11/14/17.
    Deterministic base target = 14 × 2,5 = 35,0 (+40%)."""
    ti = thesis.ThesisInputs(
        insights=_company(),
        ttm={"pe": 9.5, "eps": 2.5, "price": 25.0, "net_profit": 4800.0},
        pe_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8),
        net_cash={"value": 12000.0, "note": ""})
    return scenarios.ScenarioInputs(
        thesis_inputs=ti, multiple_history=_hist(14.0, 11.0, 17.0, current=9.5, n=8),
        eps=2.5, shares_outstanding=10_000_000, current_price=25.0, net_cash=12000.0)


def _det(inputs=None):
    return scenarios.build_scenario_set(inputs or _inputs(), malik.MALIK).to_dict()


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


def _payload(det: dict, *, narratives=None, extra=None, probs=None) -> dict:
    """Model-style refinement reusing det's scenario ids (so the merge keeps the
    deterministic structured numbers). `narratives` overrides prose per id;
    `probs` overrides [neg, base, pos] weights; `extra` appends event scenarios."""
    narratives = narratives or {}
    scs = []
    for i, s in enumerate(det["scenarios"]):
        scs.append({
            "id": s["id"], "kind": s["kind"], "label": s["label"],
            "probability": probs[i] if probs else s["probability"],
            "narrative": narratives.get(s["id"], "Rewizja: " + s["label"]),
            "drivers": s["drivers"], "assumptions": s["assumptions"],
        })
    scs.extend(extra or [])
    return {"scenarios": scs,
            "changes": [{"field": "narrative", "rationale": "iteracja"}],
            "case_similarity": [{"ticker": "XYZ", "note": "podobny profil"}]}


def _settings(**overrides):
    base = dict(anthropic_api_key="test-key", anthropic_model="claude-test",
                anthropic_max_iterations=1, ai_cache_enabled=False, ai_cache_dir=None)
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _by_kind(ss):
    return {s["kind"]: s for s in ss["scenarios"]}


# ------------------------------------------------------------------- tests

def test_module_imports_without_pypi():
    """Acceptance 1: SDK + pydantic settings are lazy — importing us pulls
    neither. Checked in a FRESH subprocess so a sibling test that already
    imported app.config (which imports pydantic_settings) can't pollute this
    process's sys.modules and make the assertion order-dependent."""
    probe = (
        "import sys, app.services.scenarios_ai\n"
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
    assert callable(scenarios_ai.simulate_scenarios)


def test_no_key_fallback_is_deterministic():
    inputs = _inputs()
    det = _det(inputs)
    out = scenarios_ai.simulate_scenarios(
        inputs, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out == {**det, "engine": "deterministic"}
    assert "ai_notes" not in out


def test_happy_path_merges_and_marks_ai():
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_resp(_payload(det, narratives={"base": "Baza po rewizji."}))])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings())
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 1
    assert out["ai_notes"]["model"] == "claude-test"
    assert _by_kind(out)["base"]["narrative"] == "Baza po rewizji."
    # deterministic structured numbers are preserved (merge keeps them)
    assert _by_kind(out)["base"]["target_price"] == 35.0


def test_malformed_response_falls_back_cleanly():
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_text_resp("Nie mogę teraz zwrócić JSON.")])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings())
    assert out == {**det, "engine": "deterministic"}
    assert stub.calls == 1


def test_iteration_limit_caps_transport_calls():
    inputs = _inputs()
    det = _det(inputs)
    responses = [
        _resp(_payload(det, narratives={"base": "Analiza pierwsza."})),
        _resp(_payload(det, narratives={"base": "Analiza druga."})),
        _resp(_payload(det, narratives={"base": "Analiza trzecia."})),
    ]
    stub = StubTransport(responses)
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings(anthropic_max_iterations=2))
    assert stub.calls == 2  # never the third
    assert out["ai_notes"]["iterations"] == 2


def test_convergence_stops_early():
    inputs = _inputs()
    det = _det(inputs)
    same = _resp(_payload(det, narratives={"base": "Stabilna rewizja."}))
    stub = StubTransport([same])  # clamps → same response every call
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings(anthropic_max_iterations=5))
    assert stub.calls == 2  # first change, second no-change → converge
    assert out["ai_notes"]["iterations"] == 1


def test_fabrication_guard_rejects_out_of_allowed_number():
    inputs = _inputs()
    det = _det(inputs)
    bad = _payload(det, narratives={"base": "Ukryty potencjał 999,9% w tym roku."})
    stub = StubTransport([_resp(bad)])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings())
    assert out == {**det, "engine": "deterministic"}  # whole round rejected
    assert 999.9 not in scenarios.scenario_numbers(out)


def test_corpus_number_allowed():
    """A figure CITED from the injected worked-case corpus survives the guard."""
    inputs = _inputs()
    det = _det(inputs)
    case = cases.WorkedCase(
        ticker="XYZ9", as_of="2024-01",
        inputs=thesis.ThesisInputs(insights=_company()),
        gaps=["repricing trwał 18 miesięcy przy mnożniku 7,3 [XYZ]"],
        citation="synthetic corpus")
    # base narrative quotes the corpus multiple 7,3 — must be allowed
    good = _payload(det, narratives={"base": "Porównywalny repricing przy mnożniku 7,3."})
    stub = StubTransport([_resp(good)])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings(), corpus=[case])
    assert out["engine"] == "ai"
    assert "7,3" in _by_kind(out)["base"]["narrative"]


def test_engine_number_allowed():
    """A deterministic-computed target quoted by the model survives the guard."""
    inputs = _inputs()
    det = _det(inputs)
    good = _payload(det, narratives={"base": "Cena docelowa 35 zł potwierdza bazę."})
    stub = StubTransport([_resp(good)])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings())
    assert out["engine"] == "ai"
    assert "35" in _by_kind(out)["base"]["narrative"]


def test_probability_renormalisation_after_event_scenario():
    """The model adds an event scenario and returns weights summing to 1,2; we
    renormalise so |Σ−1| ≤ 0,01 and the event is carried."""
    inputs = _inputs()
    det = _det(inputs)
    event = {"id": "event_catalyst", "kind": "event",
             "label": "Scenariusz zdarzeniowy — katalizator",
             "probability": 0.4,
             "narrative": "Rozstrzygnięcie przetargu (z luk analizy) — katalizator.",
             "drivers": ["Katalizator z listy „co sprawdzić dalej”"],
             "assumptions": ["Założenie: katalizator się materializuje"]}
    payload = _payload(det, probs=[0.2, 0.4, 0.2], extra=[event])  # Σ = 1,2
    stub = StubTransport([_resp(payload)])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings())
    assert out["engine"] == "ai"
    assert len(out["scenarios"]) == 4
    total = sum(s["probability"] for s in out["scenarios"])
    assert abs(total - 1.0) <= 0.01, total
    assert any(s["kind"] == "event" for s in out["scenarios"])
    # the event carries no fabricated price
    event_out = next(s for s in out["scenarios"] if s["kind"] == "event")
    assert event_out["target_price"] is None
    assert event_out["company_outcome"]["direction"] == "unknown"
    assert "do weryfikacji" in event_out["company_outcome"]["label"]


def test_cache_hit_skips_transport():
    tmp = Path(tempfile.mkdtemp(prefix="scenarios_ai_cache_"))
    try:
        inputs = _inputs()
        det = _det(inputs)
        stub = StubTransport([_resp(_payload(det, narratives={"base": "Baza."}))])
        cfg = _settings(ai_cache_enabled=True, ai_cache_dir=str(tmp))
        first = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, ticker="TST",
                                                transport=stub, settings=cfg)
        second = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, ticker="TST",
                                                 transport=stub, settings=cfg)
        assert stub.calls == 1  # second served from cache
        assert first == second and first["engine"] == "ai"
        assert len(list(tmp.glob("*.json"))) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cache_disabled_bypasses_cache():
    tmp = Path(tempfile.mkdtemp(prefix="scenarios_ai_nocache_"))
    try:
        inputs = _inputs()
        det = _det(inputs)
        stub = StubTransport([_resp(_payload(det, narratives={"base": "Baza."}))])
        cfg = _settings(ai_cache_enabled=False, ai_cache_dir=str(tmp))
        scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, ticker="TST",
                                        transport=stub, settings=cfg)
        scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, ticker="TST",
                                        transport=stub, settings=cfg)
        assert stub.calls == 2
        assert not list(tmp.glob("*.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_framing_and_disclaimer_preserved_on_ai_path():
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_resp(_payload(det, narratives={"base": "Baza po rewizji."}))])
    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=stub,
                                          settings=_settings())
    assert out["disclaimer"] == thesis.DISCLAIMER
    assert out["framing"] == scenarios.FRAMING
    assert out["valuation_multiple"] == "cz"


def test_transport_error_falls_back_without_raising():
    inputs = _inputs()
    det = _det(inputs)

    def _boom(messages, model):
        raise RuntimeError("network down")

    out = scenarios_ai.simulate_scenarios(inputs, malik.MALIK, det, transport=_boom,
                                          settings=_settings())
    assert out == {**det, "engine": "deterministic"}


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
