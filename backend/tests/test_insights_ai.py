"""Iterative Claude-API insights refiner (services/insights_ai.py) — pure
tests.

Same style as test_thesis_ai.py: hand-built inputs, plain asserts, a tiny
`__main__` runner so it runs BOTH under `pytest` (on the user's machine) and
under a bare system Python (in the sandbox — no PyPI, no `import pytest`).

Every path is exercised with an injected `StubTransport` (scripted Anthropic
responses); the real network transport is never touched here. Covered:
no-key deterministic pass-through (dict AND dataclass input), happy-path
merge, malformed fallback, iteration limit, convergence, the fabrication
guard (rejects a stray number, allows a context-only number, keeps the last
valid round), the structural guards unique to insights (can't invent an
indicator id, a dropped id falls back to the deterministic comment, a
sneaked verdict/value change is ignored, strengths/concerns can't be padded
beyond the deterministic count), cache hit/skip, and import hygiene.
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
from app.services import insights_ai
from app.services.strategies import cases


# ------------------------------------------------------------------ builders

def _ins(id, name, value, verdict, comment, importance, brief):
    return I.Insight(id, name, value, verdict, comment, importance, brief=brief)


def _company() -> I.CompanyInsights:
    """Small profitable industrial with a mixed good/bad indicator set, plus
    one missing-data gap — enough surface for strengths AND concerns."""
    indicators = [
        _ins("gross_margin", "Marża brutto na sprzedaży", "35,5%", "good",
             "Marża brutto rośnie (+0,8 p.p.) — u Malika to główny motor tezy.",
             3, "marża brutto 35,5% (+0,8 p.p.)"),
        _ins("revenue_growth", "Dynamika przychodów r/r", "12,0%", "good",
             "Przychody rosną śr. 12,0% r/r — zdrowa dynamika.", 3,
             "przychody +12,0% r/r"),
        _ins("debt_load", "Zadłużenie", "gotówka netto", "good",
             "Więcej gotówki niż długu (12 mln zł) — bilans bezpieczny.", 2,
             "gotówka netto 12 mln zł"),
        _ins("net_margin", "Marża netto", "3,0%", "bad",
             "Marża netto 3,0% — słabo jak na tę branżę.", 2,
             "marża netto 3,0%"),
    ]
    missing = [I.MissingData("cwk", "C/WK", "Brak C/WK w danych bilansowych.")]
    company = cases.build_case_insights(
        size_code="small", size_label="Mała spółka", sector_group="industrial",
        sector="Przemysł", indicators=indicators, missing=missing)
    company.strengths = [indicators[0].comment, indicators[1].comment,
                         indicators[2].comment]
    company.concerns = [indicators[3].comment]
    company.data_notes = ["Kurs sprzed 10 dni — kapitalizacja i C/Z mogą być nieaktualne."]
    company.summary = (
        "Mała spółka, przemysł (450 mln zł). Na plus: marża brutto 35,5% "
        "(+0,8 p.p.); przychody +12,0% r/r; gotówka netto 12 mln zł. "
        "Na minus: marża netto 3,0%."
    )
    return company


def _det(company=None) -> dict:
    return (company or _company()).to_dict()


def _context() -> dict:
    """Decision-relevant extras. `net_cash.value` (12345.0) is deliberately a
    number that does NOT appear anywhere in `_det()` — it exists purely so
    fabrication-guard tests can prove context numbers are allowed too."""
    return {
        "prescore": {"score": 7, "max": 10},
        "ttm": {"pe": 9.5, "net_profit": 4800.0, "market_cap": 450e6},
        "net_cash": {"value": 12345.0, "note": "Gotówka minus dług finansowy."},
        "pe_history": {"median": 14.0, "current": 9.5},
        "forum_expectations": [
            {"claim": "Rynek liczy na kontrakt eksportowy w drugiej połowie roku.",
             "confidence": "medium", "type": "catalyst",
             "source_post_ids": [101, 102]},
        ],
        "forecast_consensus": {"2026": {"revenue": 500000.0}},
        "forecast_consensus_note": "Konsensus analityków — traktować ostrożnie.",
        "entry_quality": {"code": "attractive", "label": "Atrakcyjna",
                          "rationale": "Tania wycena i rosnąca marża."},
    }


# --------------------------------------------------------------- stub transport

class StubTransport:
    """Scripted `(messages, model) -> dict` delegate. Counts calls; returns
    the next scripted response, clamping to the last one. Records every
    call's `(messages, model)` so tests can assert on what a round actually
    SENT, not just how many calls were made."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.requests = []

    def __call__(self, messages, model):
        self.calls += 1
        self.requests.append((messages, model))
        idx = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[idx]


def _request_payload(stub: StubTransport, call: int = 0) -> dict:
    messages, _model = stub.requests[call]
    content = messages[0]["content"]
    _, _, data = content.partition("\n\nDATA:\n")
    return json.loads(data)


def _resp(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _text_resp(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _payload(det: dict, summary: str, *, tag="v") -> dict:
    """A model-style refinement that reuses the deterministic indicators/
    strengths/concerns verbatim (so ids stay valid) and swaps in a custom
    `summary`."""
    return {
        "summary": summary,
        "key_indicators": [
            {"id": i["id"], "comment": i["comment"]} for i in det["key_indicators"]
        ],
        "strengths": list(det["strengths"]),
        "concerns": list(det["concerns"]),
        "changes": [{"field": "summary", "rationale": f"iteracja {tag}"}],
    }


# Summary that uses ONLY numbers already present in det/context (9,5 = C/Z,
# 14,0 = median, 35,5 = marża brutto, 3,0 = marża netto).
_GOOD_SUMMARY = (
    "Po rewizji: tania wycena (C/Z 9,5 wobec mediany 14,0) i rosnąca marża "
    "brutto 35,5%, ale marża netto 3,0% ogranicza jakość zysku."
)


def _settings(**overrides):
    base = dict(anthropic_api_key="test-key", anthropic_model="claude-test",
                anthropic_max_iterations=1, ai_cache_enabled=False,
                ai_cache_dir=None)
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ------------------------------------------------------------------- tests

def test_module_imports_without_pypi():
    """Only stdlib + insights/thesis_ai at import time; the SDK and pydantic
    settings are lazy — checked in a FRESH subprocess (a sibling test may
    already have polluted this process's sys.modules)."""
    probe = (
        "import sys, app.services.insights_ai\n"
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


def test_no_key_fallback_is_deterministic():
    det = _det()
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(),
        settings=_settings(anthropic_api_key=None))
    assert out == {**det, "engine": "deterministic"}
    assert "ai_notes" not in out


def test_no_key_fallback_accepts_dataclass_input():
    """The dossier passes the live `CompanyInsights` object, not a dict;
    pass-through must return its `.to_dict()` body verbatim + marker."""
    company = _company()
    out = insights_ai.refine_insights(
        company, ticker="TST", context=_context(),
        settings=_settings(anthropic_api_key=None))
    assert out == {**company.to_dict(), "engine": "deterministic"}


def test_happy_path_merges_and_marks_ai():
    det = _det()
    stub = StubTransport([_resp(_payload(det, _GOOD_SUMMARY))])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 1
    assert out["ai_notes"]["model"] == "claude-test"
    assert "Po rewizji" in out["summary"]
    # size/sector metadata, indicator values/verdicts/importance and
    # missing/data_notes/coverage all survive untouched.
    assert out["sector_group"] == det["sector_group"]
    assert out["missing"] == det["missing"]
    assert out["data_notes"] == det["data_notes"]
    assert out["coverage"] == det["coverage"]
    for before, after in zip(det["key_indicators"], out["key_indicators"]):
        assert after["value"] == before["value"]
        assert after["verdict"] == before["verdict"]
        assert after["importance"] == before["importance"]
        assert after["name"] == before["name"]


def test_ai_request_payload_carries_det_and_context():
    """A round's actual request must carry the deterministic insights AND the
    context — distinctive fixture values asserted so a refactor that
    silently drops either from the prompt would fail this test."""
    det = _det()
    context = _context()
    stub = StubTransport([_resp(_payload(det, _GOOD_SUMMARY))])
    insights_ai.refine_insights(
        det, ticker="TST", context=context, transport=stub, settings=_settings())
    payload = _request_payload(stub)

    sent_det = payload["deterministic_insights"]
    gross = next(i for i in sent_det["key_indicators"] if i["id"] == "gross_margin")
    assert gross["value"] == "35,5%"
    assert sent_det["missing"] == det["missing"]

    sent_ctx = payload["context"]
    assert sent_ctx["pe_history"]["median"] == 14.0
    assert sent_ctx["net_cash"]["value"] == 12345.0
    assert sent_ctx["forum_expectations"][0]["claim"].startswith("Rynek liczy")
    assert sent_ctx["entry_quality"]["code"] == "attractive"


def test_malformed_response_falls_back_cleanly():
    det = _det()
    stub = StubTransport([_text_resp("Przepraszam, nie mogę teraz zwrócić JSON.")])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert out == {**det, "engine": "deterministic"}
    assert stub.calls == 1


def test_iteration_limit_caps_transport_calls():
    det = _det()
    responses = [
        _resp(_payload(det, _GOOD_SUMMARY + " Runda pierwsza.", tag="I")),
        _resp(_payload(det, _GOOD_SUMMARY + " Runda druga.", tag="II")),
        _resp(_payload(det, _GOOD_SUMMARY + " Runda trzecia.", tag="III")),
    ]
    stub = StubTransport(responses)
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub,
        settings=_settings(anthropic_max_iterations=2))
    assert stub.calls == 2
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 2


def test_convergence_stops_early():
    det = _det()
    same = _resp(_payload(det, _GOOD_SUMMARY + " Stabilna ocena.", tag="A"))
    stub = StubTransport([same, same, same, same, same])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub,
        settings=_settings(anthropic_max_iterations=5))
    assert stub.calls == 2  # first change, second no-change → stop
    assert out["engine"] == "ai"
    assert out["ai_notes"]["iterations"] == 1


def test_fabrication_guard_rejects_out_of_input_number():
    det = _det()
    fabricated = _payload(det, "Ukryty potencjał: wzrost 99,9% w przyszłym roku.")
    stub = StubTransport([_resp(fabricated)])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    invented = insights_ai.collect_prose_numbers(out) - (
        insights_ai.collect_deterministic_numbers(det)
        | insights_ai.collect_context_numbers(_context())
    )
    assert not invented, f"fabricated numbers leaked: {invented}"
    assert out == {**det, "engine": "deterministic"}


def test_fabrication_guard_allows_context_only_number():
    """12345.0 exists ONLY in the context (net_cash.value), not in det — a
    summary quoting it must be accepted, proving context numbers widen the
    allowed set rather than the det numbers alone."""
    det = _det()
    context = _context()
    assert 12345.0 not in insights_ai.collect_deterministic_numbers(det)
    assert 12345.0 in insights_ai.collect_context_numbers(context)
    payload = _payload(det, _GOOD_SUMMARY + " Gotówka netto sięga 12345 tys. zł.")
    stub = StubTransport([_resp(payload)])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=context, transport=stub, settings=_settings())
    assert out["engine"] == "ai"
    assert "12345" in out["summary"]


def test_fabrication_guard_keeps_earlier_valid_round():
    det = _det()
    good = _resp(_payload(det, _GOOD_SUMMARY + " Runda pierwsza.", tag="I"))
    bad = _resp(_payload(det, "Zmyślona liczba 77,7 w tekście.", tag="II"))
    stub = StubTransport([good, bad])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub,
        settings=_settings(anthropic_max_iterations=3))
    assert out["engine"] == "ai"
    assert "Runda pierwsza" in out["summary"]
    assert 77.7 not in insights_ai.collect_prose_numbers(out)


def test_invented_indicator_id_rejected_falls_back():
    """A stub response that invents a brand-new indicator id (not one of the
    deterministic set's ids) must reject the whole round."""
    det = _det()
    payload = _payload(det, _GOOD_SUMMARY)
    payload["key_indicators"] = payload["key_indicators"] + [
        {"id": "totally_invented_id", "comment": "Nowy wskaźnik spoza zestawu."}
    ]
    stub = StubTransport([_resp(payload)])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert out == {**det, "engine": "deterministic"}
    assert stub.calls == 1
    assert "ai_notes" not in out


def test_dropped_indicator_falls_back_to_deterministic_comment():
    """The model may cover fewer indicators than the deterministic set (it is
    NOT required to reword all of them); a dropped id keeps its exact
    deterministic comment, and the indicator itself is never removed from
    the list."""
    det = _det()
    payload = _payload(det, _GOOD_SUMMARY)
    dropped_id = payload["key_indicators"][0]["id"]
    payload["key_indicators"] = payload["key_indicators"][1:]  # drop the first
    stub = StubTransport([_resp(payload)])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert out["engine"] == "ai"
    ids = [i["id"] for i in out["key_indicators"]]
    assert dropped_id in ids  # still present
    det_comment = next(i["comment"] for i in det["key_indicators"] if i["id"] == dropped_id)
    out_comment = next(i["comment"] for i in out["key_indicators"] if i["id"] == dropped_id)
    assert out_comment == det_comment  # untouched deterministic text


def test_sneaked_verdict_change_is_ignored():
    """Even if a rogue response tries to smuggle a different verdict/value
    for an indicator, only `comment` is ever read from the model — verdict/
    value/importance always come from the deterministic block."""
    det = _det()
    payload = _payload(det, _GOOD_SUMMARY)
    target = payload["key_indicators"][0]
    target["verdict"] = "bad"        # not a recognised field — must be ignored
    target["value"] = "0,0%"         # ditto
    target["comment"] = "Przeformułowany komentarz bez zmiany liczb."
    stub = StubTransport([_resp(payload)])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert out["engine"] == "ai"
    out_ind = next(i for i in out["key_indicators"] if i["id"] == target["id"])
    det_ind = next(i for i in det["key_indicators"] if i["id"] == target["id"])
    assert out_ind["verdict"] == det_ind["verdict"]
    assert out_ind["value"] == det_ind["value"]
    assert out_ind["comment"] == "Przeformułowany komentarz bez zmiany liczb."


def test_strengths_and_concerns_cannot_be_padded():
    """The model may reword/trim strengths/concerns, never pad beyond the
    deterministic count."""
    det = _det()
    payload = _payload(det, _GOOD_SUMMARY)
    payload["strengths"] = payload["strengths"] + [
        "Wymyślony dodatkowy plus.", "Kolejny wymyślony plus.",
    ]
    stub = StubTransport([_resp(payload)])
    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert out["engine"] == "ai"
    assert len(out["strengths"]) == len(det["strengths"])


def test_engine_marker_present_on_both_paths():
    det = _det()
    off = insights_ai.refine_insights(
        det, ticker="TST", context=_context(),
        settings=_settings(anthropic_api_key=None))
    assert off["engine"] == "deterministic" and "ai_notes" not in off
    stub = StubTransport([_resp(_payload(det, _GOOD_SUMMARY))])
    on = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=stub, settings=_settings())
    assert on["engine"] == "ai" and "ai_notes" in on


def test_cache_hit_skips_transport():
    tmp = Path(tempfile.mkdtemp(prefix="insights_ai_cache_"))
    try:
        det = _det()
        stub = StubTransport([_resp(_payload(det, _GOOD_SUMMARY))])
        cfg = _settings(ai_cache_enabled=True, ai_cache_dir=str(tmp))
        first = insights_ai.refine_insights(
            det, ticker="TST", context=_context(), transport=stub, settings=cfg)
        second = insights_ai.refine_insights(
            det, ticker="TST", context=_context(), transport=stub, settings=cfg)
        assert stub.calls == 1
        assert first == second
        assert first["engine"] == "ai"
        files = list(tmp.glob("*.json"))
        assert len(files) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cache_disabled_bypasses_cache():
    tmp = Path(tempfile.mkdtemp(prefix="insights_ai_nocache_"))
    try:
        det = _det()
        stub = StubTransport([_resp(_payload(det, _GOOD_SUMMARY))])
        cfg = _settings(ai_cache_enabled=False, ai_cache_dir=str(tmp))
        insights_ai.refine_insights(
            det, ticker="TST", context=_context(), transport=stub, settings=cfg)
        insights_ai.refine_insights(
            det, ticker="TST", context=_context(), transport=stub, settings=cfg)
        assert stub.calls == 2
        assert not list(tmp.glob("*.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_transport_error_falls_back_without_raising():
    det = _det()

    def _boom(messages, model):
        raise RuntimeError("network down")

    out = insights_ai.refine_insights(
        det, ticker="TST", context=_context(), transport=_boom, settings=_settings())
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
