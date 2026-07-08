"""Forum distiller (services/forum_distiller.py, P5.9) — pure tests.

Same style as test_thesis_ai.py / test_analysis_ai.py: hand-built inputs,
plain asserts, a tiny `__main__` runner so it runs BOTH under `pytest` (on
the user's machine) and under a bare system Python (in the sandbox — no
PyPI, no `import pytest`).

Covered: classification parsing, claim extraction, per-post cache hit
avoids a second transport call, no-key graceful empty result, malformed
response degrades gracefully, dedup/merge of source_post_ids across posts,
upvote-weighted ordering, budget truncation of the final claims list, and
import hygiene (subprocess-isolated, no PyPI at module import time).
"""
from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from app.services import forum_distiller as fd
from app.services import prompts as prompts_service

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ builders


class StubTransport:
    """Scripted `(messages, model) -> dict` delegate. Counts calls; raises/
    returns per a scripted list of "actions", mirroring
    `test_thesis_ai.StubTransport` / `test_analysis_ai.StubTransport`."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.requests = []

    def __call__(self, messages, model):
        self.calls += 1
        self.requests.append((messages, model))
        action = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(action, Exception):
            raise action
        return action


def _text_resp(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _post(post_id, text, upvotes=None, posted_at=None, author="user1"):
    return {
        "post_id": post_id,
        "author": author,
        "posted_at": posted_at,
        "upvotes": upvotes,
        "content_text": text,
    }


def _settings(**overrides):
    base = dict(
        anthropic_api_key="test-key",
        anthropic_model="claude-test",
        ai_distill_model="claude-distill-test",
        ai_cache_enabled=False,
        ai_cache_dir=None,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ============================================================ pure: classify


def test_module_imports_without_pypi():
    """Importing forum_distiller must pull neither `anthropic` nor
    `pydantic_settings` — checked in a FRESH subprocess so sibling tests that
    already imported app.config/app.db.models don't pollute this process's
    sys.modules."""
    probe = (
        "import sys\n"
        "import app.services.forum_distiller\n"
        "assert 'anthropic' not in sys.modules, 'anthropic imported eagerly'\n"
        "assert 'pydantic_settings' not in sys.modules, "
        "'pydantic_settings imported eagerly'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe], cwd=BACKEND_DIR, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert callable(fd.default_transport)
    assert callable(fd.distill_company_posts)


def test_classification_and_claim_extraction():
    """A fact-bearing post gets type=fact-claim and its concrete claims
    extracted with the model's confidence label."""
    stub = StubTransport(
        [
            _text_resp(
                {
                    "type": "fact-claim",
                    "claims": [
                        {"claim": "Spółka podpisała nowy kontrakt w Q2.", "confidence": "medium"}
                    ],
                }
            )
        ]
    )
    posts = [_post(101, "Widziałem w komunikacie, że podpisali nowy kontrakt w Q2.", upvotes=5)]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)

    assert len(claims) == 1
    assert claims[0].claim == "Spółka podpisała nowy kontrakt w Q2."
    assert claims[0].confidence == "medium"
    assert claims[0].type == "fact-claim"
    assert claims[0].source_post_ids == [101]
    assert stub.calls == 1


def test_opinion_post_yields_no_claims():
    stub = StubTransport([_text_resp({"type": "opinion", "claims": []})])
    posts = [_post(102, "Uważam że to fajna spółka na dłuższą metę.", upvotes=1)]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)
    assert claims == []


def test_cache_hit_avoids_second_transport_call():
    tmp = Path(tempfile.mkdtemp(prefix="forum_claims_cache_"))
    try:
        stub = StubTransport(
            [_text_resp({"type": "fact-claim", "claims": [{"claim": "Marża rośnie.", "confidence": "high"}]})]
        )
        cfg = _settings(ai_cache_enabled=True, ai_cache_dir=str(tmp))
        posts = [_post(201, "Marża brutto wyraźnie rośnie kwartał do kwartału.", upvotes=3)]

        first = fd.distill_company_posts(posts, settings=cfg, transport=stub)
        second = fd.distill_company_posts(posts, settings=cfg, transport=stub)

        assert stub.calls == 1  # second run served from the per-post cache
        assert [c.claim for c in first] == [c.claim for c in second]
        assert list(tmp.glob("*.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_key_graceful_empty_result_never_raises():
    posts = [_post(301, "Ktoś wie kiedy raport za Q2?", upvotes=0)]
    # No transport injected AND no api key => distiller must not attempt any
    # call and must not raise.
    claims = fd.distill_company_posts(posts, settings=_settings(anthropic_api_key=None))
    assert claims == []


def test_malformed_response_degrades_to_empty_not_raised():
    stub = StubTransport([{"content": [{"type": "text", "text": "nie mogę pomóc"}]}])
    posts = [_post(401, "Ciekawa dyskusja o wynikach.", upvotes=2)]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)
    assert claims == []
    assert stub.calls == 1  # attempted once, degraded gracefully afterward


def test_transport_error_degrades_to_empty_not_raised():
    stub = StubTransport([RuntimeError("network blip")])
    posts = [_post(402, "Ciekawa dyskusja o wynikach.", upvotes=2)]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)
    assert claims == []


# ==================================================== pure: dedup/merge/order


def test_dedup_merges_source_post_ids_across_posts():
    """Two different posts producing the (near-)identical claim text must
    merge into ONE DistilledClaim carrying both source post ids."""
    stub = StubTransport(
        [
            _text_resp({"type": "fact-claim", "claims": [{"claim": "Zarząd zapowiedział skup akcji.", "confidence": "low"}]}),
            _text_resp({"type": "fact-claim", "claims": [{"claim": "zarząd zapowiedział skup akcji.", "confidence": "high"}]}),
        ]
    )
    posts = [
        _post(501, "Podobno zarząd zapowiedział skup akcji.", upvotes=10, posted_at="2026-07-01"),
        _post(502, "Potwierdzam, zarząd zapowiedział skup akcji na konferencji.", upvotes=1, posted_at="2026-07-02"),
    ]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)

    assert len(claims) == 1
    assert sorted(claims[0].source_post_ids) == [501, 502]
    # highest confidence across the merged duplicates wins
    assert claims[0].confidence == "high"
    assert stub.calls == 2


def test_upvote_weighted_ordering_processes_top_posts_first():
    """Posts must be distilled in `sort=top` order (upvotes desc, nulls
    last, then newest first) — the same ordering
    `app/api/forum.py::get_company_posts(sort="top")` documents."""
    # Responses are scripted in PROCESSING order (most upvotes -> mid ->
    # nulls-last no-upvotes), matching `_top_ordered`'s sort=top semantics.
    stub = StubTransport(
        [
            _text_resp({"type": "fact-claim", "claims": [{"claim": "claim-from-most-upvoted", "confidence": "high"}]}),
            _text_resp({"type": "fact-claim", "claims": [{"claim": "claim-from-mid-upvotes", "confidence": "low"}]}),
            _text_resp({"type": "fact-claim", "claims": [{"claim": "claim-from-no-upvotes", "confidence": "low"}]}),
        ]
    )
    posts = [
        _post(601, "post with no upvotes", upvotes=None, posted_at="2026-07-03"),
        _post(602, "post with most upvotes", upvotes=20, posted_at="2026-07-01"),
        _post(603, "post with mid upvotes", upvotes=5, posted_at="2026-07-02"),
    ]
    text_to_id = {p["content_text"]: p["post_id"] for p in posts}
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)

    # request order mirrors processing order: most upvotes, then mid, then
    # the (nulls-last) no-upvotes post. `_build_prompt` doesn't echo the post
    # id, so recover it from the (unique, per-post) text in the sent payload.
    processed_post_ids = []
    for messages, _model in stub.requests:
        payload_text = messages[0]["content"].split("POST:\n", 1)[1]
        payload = json.loads(payload_text)
        processed_post_ids.append(text_to_id[payload["text"]])
    assert processed_post_ids == [602, 603, 601]
    assert [c.claim for c in claims] == [
        "claim-from-most-upvoted", "claim-from-mid-upvotes", "claim-from-no-upvotes",
    ]


def test_max_posts_bounds_call_count():
    """`max_posts` caps how many posts ever get a model call, regardless of
    how many posts are passed in — a cost guard."""
    stub = StubTransport([_text_resp({"type": "noise", "claims": []})])
    posts = [_post(700 + i, f"post {i}", upvotes=i) for i in range(10)]
    fd.distill_company_posts(posts, settings=_settings(), transport=stub, max_posts=3)
    assert stub.calls == 3


def test_budget_truncates_final_claims_list():
    """A tiny char budget on the OUTPUT claims list truncates even though
    every post distilled successfully — the budget governs the merged
    result, not just the per-call text sent to the model."""
    stub = StubTransport(
        [
            _text_resp({"type": "fact-claim", "claims": [{"claim": "x" * 200, "confidence": "high"}]}),
            _text_resp({"type": "fact-claim", "claims": [{"claim": "y" * 200, "confidence": "high"}]}),
            _text_resp({"type": "fact-claim", "claims": [{"claim": "z" * 200, "confidence": "high"}]}),
        ]
    )
    posts = [
        _post(801, "post a", upvotes=3),
        _post(802, "post b", upvotes=2),
        _post(803, "post c", upvotes=1),
    ]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub, budget=400)
    assert 0 < len(claims) < 3


def test_empty_or_whitespace_posts_are_skipped_without_a_call():
    stub = StubTransport([_text_resp({"type": "noise", "claims": []})])
    posts = [_post(901, "   ", upvotes=1), _post(902, "", upvotes=2)]
    claims = fd.distill_company_posts(posts, settings=_settings(), transport=stub)
    assert claims == []
    assert stub.calls == 0


# =============================================== wiring: prompts.build_analysis_prompt
# P5.9 deliverable #2: the verdict prompt's forum section must be built from
# DISTILLED CLAIMS, not raw posts, whenever `forum_claims` is supplied.


def _dossier():
    return {
        "prescore": {"passed": 6, "total": 8, "checks": []},
        "ttm": {"pe": 9.5},
        "pe_history": {"median": 14.0},
        "net_cash": {"value": 12000.0},
        "insights": {"summary": "Tania spółka.", "key_indicators": []},
        "thesis": {"entry_quality": {"code": "attractive"}},
        "scenarios": {"scenarios": []},
        "valuation": {"potential": {"value_pct": 12.0}},
        "latest_forecast": {"result": {}},
    }


def test_prompt_uses_distilled_claims_when_supplied_not_raw_posts():
    claims = [
        fd.DistilledClaim(
            claim="Zarząd zapowiedział skup akcji.",
            confidence="medium",
            type="fact-claim",
            source_post_ids=[501, 502],
        )
    ]
    raw_posts = [{"post_id": 999, "content_text": "SUROWY POST NIE POWINIEN TU TRAFIĆ"}]
    bundle = prompts_service.build_analysis_prompt(_dossier(), raw_posts, forum_claims=claims)

    assert "Zarząd zapowiedział skup akcji." in bundle["user"]
    assert "SUROWY POST NIE POWINIEN TU TRAFIĆ" not in bundle["user"]
    assert "opinie, nie fakty" in bundle["user"].lower() or "OPINIE" in bundle["user"]
    assert "501" in bundle["user"] and "502" in bundle["user"]
    assert bundle["snapshot"]["forum_claims"][0]["claim"] == "Zarząd zapowiedział skup akcji."
    assert bundle["snapshot"]["forum_posts"] == []  # legacy path unused


def test_prompt_empty_claims_list_still_assembles_valid_prompt():
    """No key / no forum signal ⇒ `forum_claims=[]` (not None) must still
    produce a valid, non-crashing prompt — the no-key degrade-gracefully
    path all the way through to the verdict prompt."""
    bundle = prompts_service.build_analysis_prompt(_dossier(), [], forum_claims=[])
    assert "Brak wydestylowanych twierdzeń" in bundle["user"]
    assert bundle["snapshot"]["forum_claims"] == []


def test_prompt_falls_back_to_raw_posts_when_claims_not_supplied():
    """Backward compatibility: omitting `forum_claims` (None) preserves the
    pre-P5.9 raw-post rendering exactly — existing callers/tests must not
    break."""
    posts = [{"post_id": 1, "content_text": "post surowy", "posted_at": "2026-01-01T00:00:00"}]
    bundle = prompts_service.build_analysis_prompt(_dossier(), posts)
    assert "post surowy" in bundle["user"]
    assert bundle["snapshot"]["forum_posts"]
    assert bundle["snapshot"]["forum_claims"] == []


# ------------------------------------------------------------- in-session runner

if __name__ == "__main__":  # pragma: no cover — pytest ignores this block
    fns = [
        (n, o)
        for n, o in sorted(globals().items())
        if n.startswith("test_") and callable(o)
    ]
    failed = 0
    skipped = 0
    for name, fn in fns:
        params = inspect.signature(fn).parameters
        if params:
            skipped += 1
            print(f"SKIP  {name} (needs pytest fixtures: {', '.join(params)} — run under pytest)")
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — report any error, keep going
            failed += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    ran = len(fns) - skipped
    print(f"\n{ran - failed}/{ran} pure tests passed ({skipped} client-gated tests skipped)")
    sys.exit(1 if failed else 0)
