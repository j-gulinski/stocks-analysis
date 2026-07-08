"""Iterative Claude-API thesis refiner (services/thesis_ai.py) — pure tests.

Same style as test_thesis.py: hand-built inputs, plain asserts, a tiny
`__main__` runner so it runs BOTH under `pytest` (on the user's machine) and
under a bare system Python (in the sandbox — no PyPI, no `import pytest`).

Every path is exercised with an injected `StubTransport` (scripted Anthropic
responses); the real network transport is never touched here. Covered:
happy-path merge, malformed fallback, iteration limit, convergence, the
fabrication guard, the no-key deterministic fallback, cache hit/skip, and that
the not-advice framing survives the AI path.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from app.services import insights as I
from app.services import thesis, thesis_ai
from app.services.strategies import cases, malik


# ------------------------------------------------------------------ builders

def _ins(id, name, value, verdict, comment, importance, brief):
    return I.Insight(id, name, value, verdict, comment, importance, brief=brief)


def _company():
    """Small profitable industrial — the deterministic read is `attractive`,
    with a rich pro set whose ids the refinements reuse."""
    indicators = [
        _ins("gross_margin", "Marża brutto na sprzedaży", "35,5%", "good",
             "Marża brutto rośnie (+0,8 p.p.) — u Malika to główny motor tezy.",
             3, "marża brutto 35,5% (+0,8 p.p.)"),
        _ins("revenue_growth", "Dynamika przychodów r/r", "12,0%", "good",
             "Przychody rosną śr. 12,0% r/r — zdrowa dynamika.", 3,
             "przychody +12,0% r/r"),
        _ins("pe_vs_history", "C/Z na tle własnej historii", "9,5", "good",
             "C/Z 9,5 poniżej własnej mediany 14,0 — historycznie tanio.", 3,
             "C/Z 9,5 vs własna mediana 14,0"),
        _ins("one_offs", "Udział zdarzeń jednorazowych", "8,0%", "good",
             "One-offy to tylko 8,0% zysku operacyjnego — wynik powtarzalny.", 2,
             "one-offy 8,0% zysku oper."),
        _ins("debt_load", "Zadłużenie", "gotówka netto", "good",
             "Więcej gotówki niż długu (12 mln zł) — bilans bezpieczny.", 2,
             "gotówka netto 12 mln zł"),
    ]
    return cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="industrial",
        sector="Przemysł", indicators=indicators, missing=[])


def _inputs():
    return thesis.ThesisInputs(
        insights=_company(),
        ttm={"pe": 9.5, "net_profit": 4800.0, "market_cap": 450e6},
        pe_history={"median": 14.0, "current": 9.5},
        net_cash={"value": 12000.0, "note": "Gotówka minus dług finansowy."},
        latest_forecast={"result": {"forward": {"pe": 8.7}}})


def _det(inputs=None):
    return thesis.build_thesis(inputs or _inputs(), malik.MALIK).to_dict()


# --------------------------------------------------------------- stub transport

class StubTransport:
    """Scripted `(messages, model) -> dict` delegate. Counts calls; returns the
    next scripted response, clamping to the last one so a short script can be
    replayed (e.g. an unchanged round for convergence). Records every call's
    `(messages, model)` in `self.requests` so tests can assert on what a round
    actually SENT (verifier finding: call *count* was checked, never the
    payload — a refactor could silently drop the profile/corpus and no test
    would notice)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.requests = []  # [(messages, model), ...] — one entry per call

    def __call__(self, messages, model):
        self.calls += 1
        self.requests.append((messages, model))
        idx = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[idx]


def _request_payload(stub: StubTransport, call: int = 0) -> dict:
    """Parse the DATA JSON blob out of one recorded request's prompt text, so
    tests can assert on the actual structured payload a round sent (dossier
    inputs, strategy profile, worked-case corpus) rather than only on how many
    calls were made."""
    messages, _model = stub.requests[call]
    content = messages[0]["content"]
    _, _, data = content.partition("\n\nDATA:\n")
    return json.loads(data)


def _resp(payload: dict) -> dict:
    """Wrap a model JSON payload in the Anthropic Messages-API envelope."""
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _text_resp(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _payload(det: dict, thesis_read: str, *, code=None, tag="v") -> dict:
    """Build a model-style refinement that reuses the deterministic pros/cons
    (so ids + numbers are valid) and swaps in a custom `thesis_read`."""
    return {
        "entry_quality": {"code": code or det["entry_quality"]["code"],
                          "rationale": det["entry_quality"]["rationale"]},
        "pros": [{"id": p["id"], "text": p["text"]} for p in det["pros"]],
        "cons": [{"id": c["id"], "text": c["text"]} for c in det["cons"]],
        "verify_next": [{"id": v["id"], "text": v["text"], "why": v["why"]}
                        for v in det["verify_next"]],
        "thesis_read": thesis_read,
        "valuation_basis": det["valuation_basis"],
        "changes": [{"field": "thesis_read", "rationale": f"iteracja {tag}"}],
        "case_similarity": [{"ticker": "SNT", "note": "zbliżony profil marż"}],
    }


# Reads that use ONLY numbers present in the inputs (9,5 = C/Z, 35,5 = marża).
_GOOD_READ = "Teza po rewizji: tania wycena (C/Z 9,5) i rosnąca marża 35,5%."


def _settings(**overrides):
    base = dict(anthropic_api_key="test-key", anthropic_model="claude-test",
                anthropic_max_iterations=1, ai_cache_enabled=False,
                ai_cache_dir=None)
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ------------------------------------------------------------------- tests

def test_module_imports_without_pypi():
    """Acceptance 1: only stdlib + insights/thesis/strategies at import time;
    the SDK and pydantic settings are lazy (never pulled in by importing us).

    Checked in a FRESH subprocess: a sibling test (or the API-suite conftest)
    may already have imported app.config — which *does* import
    pydantic_settings — polluting this process's sys.modules, so an in-process
    assertion would be order-dependent. The subprocess isolates the property
    we actually care about: importing *us* pulls neither dependency."""
    probe = (
        "import sys, app.services.thesis_ai\n"
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
    assert callable(thesis_ai.default_transport)


def test_no_key_fallback_is_deterministic():
    """Acceptance 3: no key → exactly the deterministic body + marker, no raise,
    no ai_notes."""
    inputs = _inputs()
    det = _det(inputs)
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, settings=_settings(anthropic_api_key=None))
    assert out == {**det, "engine": "deterministic"}
    assert "ai_notes" not in out


def test_no_key_fallback_accepts_prebuilt_thesis():
    """The dossier passes the already-built deterministic thesis; pass-through
    must return its body verbatim + marker."""
    inputs = _inputs()
    det_obj = thesis.build_thesis(inputs, malik.MALIK)
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det_obj,
                                  settings=_settings(anthropic_api_key=None))
    assert out == {**det_obj.to_dict(), "engine": "deterministic"}


def test_happy_path_merges_and_marks_ai():
    """Acceptance 2a: a valid refinement merges, engine == 'ai', ai_notes set."""
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings())
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 1
    assert out["ai_notes"]["model"] == "claude-test"
    assert out["ai_notes"]["case_similarity"]  # notes carried through
    # the refined read replaced the deterministic one
    assert "Teza po rewizji" in out["thesis_read"]
    # strategy provenance preserved (not taken from the model)
    assert out["strategy"] == {"id": "malik", "label": "Paweł Malik (OBS)"}


def test_ai_request_payload_carries_inputs_and_profile():
    """Verifier fix (WP2b): a round's *actual* request must carry the
    serialized ThesisInputs and StrategyProfile — not just fire a call.
    Distinctive fixture values/ids are asserted so a refactor that silently
    drops the dossier or the profile from the prompt would fail this test."""
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
    # Pass an explicit empty corpus: WP4 populated `cases.CORPUS` (DGN + SNT), so
    # the default is no longer empty; `corpus=()` keeps this test asserting the
    # empty-corpus serialization path (empty → `[]`, never omitted).
    thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                            settings=_settings(), corpus=())
    payload = _request_payload(stub)

    # (a) dossier inputs: distinctive numbers/fields from the test fixtures.
    dossier = payload["dossier_inputs"]
    assert dossier["ttm"]["net_profit"] == 4800.0
    assert dossier["net_cash"] == {
        "value": 12000.0, "note": "Gotówka minus dług finansowy."}
    gross = next(i for i in dossier["key_indicators"] if i["id"] == "gross_margin")
    assert gross["value"] == "35,5%"

    # (b) strategy profile: a distinctive criterion id/weight/principle + an
    # entry-rule threshold, straight from strategies/malik.py.
    profile = payload["strategy_profile"]
    assert profile["id"] == "malik"
    criteria_by_id = {c["id"]: c for c in profile["criteria"]}
    assert criteria_by_id["pe_vs_history"]["weight"] == 3.0
    assert criteria_by_id["pe_vs_history"]["principle"] == "C/Z na tle własnej historii"
    assert profile["entry_rule"]["min_key_indicators"] == 3
    assert profile["entry_rule"]["weak_bad_count"] == 2

    # explicit empty corpus (see above) → serialized as an empty list, never
    # omitted. (The non-empty default `cases.CORPUS` is covered by
    # test_ai_request_payload_includes_injected_corpus via an injected case.)
    assert payload["worked_cases"] == []


def test_ai_request_payload_includes_injected_corpus():
    """Verifier fix (WP2b): a non-empty WorkedCase corpus injected via
    `corpus=` must reach the actual request — distinctive ticker/citation from
    a synthetic case, not just "some non-empty list"."""
    inputs = _inputs()
    det = _det(inputs)
    case = cases.WorkedCase(
        ticker="ZZZ9",
        as_of="2026-01-01",
        inputs=_inputs(),
        sources={"pe_vs_history": "test fixture"},
        expected_read={"entry_quality": "attractive"},
        citation="synthetic fixture for WP2b payload test",
        gaps=["brak katalizatora"],
    )
    stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
    thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                            settings=_settings(), corpus=[case])
    payload = _request_payload(stub)

    assert len(payload["worked_cases"]) == 1
    sent = payload["worked_cases"][0]
    assert sent["ticker"] == "ZZZ9"
    assert sent["citation"] == "synthetic fixture for WP2b payload test"
    assert sent["expected_read"] == {"entry_quality": "attractive"}


def test_malformed_response_falls_back_cleanly():
    """Acceptance 2b: a non-JSON answer → fall back, engine deterministic, no
    exception raised."""
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_text_resp("Przepraszam, nie mogę teraz zwrócić JSON.")])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings())
    assert out == {**det, "engine": "deterministic"}
    assert stub.calls == 1  # tried once, then gave up


def test_iteration_limit_caps_transport_calls():
    """Acceptance 2c: with max_iterations=2 the transport is called at most
    twice even though the model keeps returning fresh (changed) refinements."""
    inputs = _inputs()
    det = _det(inputs)
    # three DISTINCT changed reads (roman-numeral tags carry no digits) so the
    # loop never converges — only the hard limit can stop it.
    responses = [
        _resp(_payload(det, _GOOD_READ + " (analiza pierwsza).", tag="I")),
        _resp(_payload(det, _GOOD_READ + " (analiza druga).", tag="II")),
        _resp(_payload(det, _GOOD_READ + " (analiza trzecia).", tag="III")),
    ]
    stub = StubTransport(responses)
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings(anthropic_max_iterations=2))
    assert stub.calls == 2  # never the third
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 2


def test_convergence_stops_early():
    """Acceptance 2e: an unchanged round stops the loop before the limit."""
    inputs = _inputs()
    det = _det(inputs)
    # same changed payload twice → round 2 makes no change → converge at 2,
    # well under the max of 5.
    same = _resp(_payload(det, _GOOD_READ + " (stabilna).", tag="A"))
    stub = StubTransport([same, same, same, same, same])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings(anthropic_max_iterations=5))
    assert stub.calls == 2  # first change, second no-change → stop
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 1


def test_fabrication_guard_rejects_out_of_input_number():
    """Acceptance 2d: a number absent from the inputs is rejected; the final
    read contains NO number that is not in the inputs (same guard as
    test_thesis.py)."""
    inputs = _inputs()
    det = _det(inputs)
    fabricated = _payload(det, "Ukryty potencjał: wzrost 99,9% w przyszłym roku.")
    stub = StubTransport([_resp(fabricated)])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings())
    # invented number never survives → clean fall back to the deterministic read
    invented = thesis_ai.collect_read_numbers(out) - thesis_ai.collect_input_numbers(inputs)
    assert not invented, f"fabricated numbers leaked: {invented}"
    assert 99.9 not in thesis_ai.collect_read_numbers(out)
    assert out == {**det, "engine": "deterministic"}


def test_fabrication_guard_keeps_earlier_valid_round():
    """A first valid round then a fabricating round → fall back to the LAST
    valid refinement (not all the way to deterministic), still clean."""
    inputs = _inputs()
    det = _det(inputs)
    good = _resp(_payload(det, _GOOD_READ + " (runda pierwsza).", tag="I"))
    bad = _resp(_payload(det, "Zmyślona liczba 77,7 w tekście.", tag="II"))
    stub = StubTransport([good, bad])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings(anthropic_max_iterations=3))
    assert out["engine"] == "ai"  # kept the valid first round
    assert "runda pierwsza" in out["thesis_read"]
    assert 77.7 not in thesis_ai.collect_read_numbers(out)
    assert not thesis_ai.collect_read_numbers(out) - thesis_ai.collect_input_numbers(inputs)


def test_invented_pro_id_rejected_falls_back():
    """Nit (WP2b review): a stub response that invents a brand-new pro id (not
    one of the deterministic thesis's existing pro/con ids) must be rejected —
    this schema guard (`_validate_and_merge`/`_factors`) was only
    code-reviewed, never exercised by a test."""
    inputs = _inputs()
    det = _det(inputs)
    payload = _payload(det, _GOOD_READ)
    payload["pros"] = payload["pros"] + [
        {"id": "totally_invented_pro_id", "text": "Nowy plus spoza tezy."}
    ]
    stub = StubTransport([_resp(payload)])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings())
    assert out == {**det, "engine": "deterministic"}  # whole round rejected
    assert stub.calls == 1  # tried once, gave up
    assert "ai_notes" not in out


def test_disclaimer_and_framing_preserved_on_ai_path():
    """Acceptance 5: the fixed not-advice DISCLAIMER + strategy survive on the
    AI path (re-imposed every round)."""
    inputs = _inputs()
    det = _det(inputs)
    stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                  settings=_settings())
    assert out["disclaimer"] == thesis.DISCLAIMER
    assert out["thesis_read"].rstrip().endswith(thesis.DISCLAIMER)
    assert out["strategy"] == {"id": "malik", "label": "Paweł Malik (OBS)"}
    assert out["entry_quality"]["code"] in ("attractive", "neutral", "weak",
                                            "insufficient_data")


def test_engine_marker_present_on_both_paths():
    """Acceptance 5: deterministic path → engine deterministic (no ai_notes);
    ai path → engine ai (with ai_notes)."""
    inputs = _inputs()
    det = _det(inputs)
    off = thesis_ai.refine_thesis(inputs, malik.MALIK, det,
                                  settings=_settings(anthropic_api_key=None))
    assert off["engine"] == "deterministic" and "ai_notes" not in off
    stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
    on = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=stub,
                                 settings=_settings())
    assert on["engine"] == "ai" and "ai_notes" in on


def test_cache_hit_skips_transport():
    """Acceptance 4: two identical calls with cache on → transport once, one
    JSON file written under the (gitignored) cache dir."""
    tmp = Path(tempfile.mkdtemp(prefix="thesis_ai_cache_"))
    try:
        inputs = _inputs()
        det = _det(inputs)
        stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
        cfg = _settings(ai_cache_enabled=True, ai_cache_dir=str(tmp))
        first = thesis_ai.refine_thesis(inputs, malik.MALIK, det, ticker="TST",
                                        transport=stub, settings=cfg)
        second = thesis_ai.refine_thesis(inputs, malik.MALIK, det, ticker="TST",
                                         transport=stub, settings=cfg)
        assert stub.calls == 1  # second call served from cache
        assert first == second
        assert first["engine"] == "ai"
        files = list(tmp.glob("*.json"))
        assert len(files) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cache_disabled_bypasses_cache():
    """Acceptance 4: ai_cache_enabled=False → the transport runs every call."""
    tmp = Path(tempfile.mkdtemp(prefix="thesis_ai_nocache_"))
    try:
        inputs = _inputs()
        det = _det(inputs)
        stub = StubTransport([_resp(_payload(det, _GOOD_READ))])
        cfg = _settings(ai_cache_enabled=False, ai_cache_dir=str(tmp))
        thesis_ai.refine_thesis(inputs, malik.MALIK, det, ticker="TST",
                                transport=stub, settings=cfg)
        thesis_ai.refine_thesis(inputs, malik.MALIK, det, ticker="TST",
                                transport=stub, settings=cfg)
        assert stub.calls == 2
        assert not list(tmp.glob("*.json"))  # nothing cached
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_transport_error_falls_back_without_raising():
    """A transport that raises must not propagate — fall back to deterministic."""
    inputs = _inputs()
    det = _det(inputs)

    def _boom(messages, model):
        raise RuntimeError("network down")

    out = thesis_ai.refine_thesis(inputs, malik.MALIK, det, transport=_boom,
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
