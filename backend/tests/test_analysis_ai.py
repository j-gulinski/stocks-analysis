"""Phase-5 AI analysis: `services/claude_client.py` (P5.4) + `services/prompts.py`
(P5.5) — pure tests, plus client-gated endpoint tests for `api/analyses.py`
(P5.6).

Same style as `test_thesis_ai.py`: hand-built inputs, plain asserts, a tiny
`__main__` runner so the PURE tests run BOTH under `pytest` (user's machine)
and under a bare system Python (this sandbox — no PyPI, no `import pytest`,
no `sqlalchemy`/`fastapi`/`anthropic`).

Two groups, clearly marked:
  * PURE (no fixtures) — claude_client + prompts. Exercised here AND by the
    `__main__` runner below.
  * CLIENT-GATED (`client`/`db` pytest fixtures from tests/conftest.py) — the
    `/analyses` endpoints. These need sqlalchemy/fastapi/pydantic-settings
    installed, which this sandbox does not have; the `__main__` runner detects
    their signature and SKIPS them (reported separately, not counted as
    failures). They run normally under `pytest` on the user's machine.
"""
from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.services import claude_client, prompts as prompts_service

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ============================================================ pure: prompts.py


def _dossier():
    """A small hand-built dossier slice covering every key `_dossier_snapshot`
    pulls, plus a couple of keys it must DROP (company/quarters/dividends)."""
    return {
        "company": {"ticker": "SNT", "name": "SYNEKTIK"},  # must be dropped
        "quarters": [{"period": "2025Q1"}],  # must be dropped
        "dividends": [{"year": 2024}],  # must be dropped
        "prescore": {"passed": 6, "total": 8, "checks": []},
        "ttm": {"pe": 9.5, "net_profit": 4800.0},
        "pe_history": {"median": 14.0, "current": 9.5},
        "net_cash": {"value": 12000.0, "note": "Gotówka minus dług."},
        "insights": {"summary": "Tania spółka z rosnącą marżą.", "key_indicators": []},
        "thesis": {"entry_quality": {"code": "attractive"}, "engine": "deterministic"},
        "scenarios": {"scenarios": [], "engine": "deterministic"},
        "valuation": {"potential": {"value_pct": 12.0}, "engine": "deterministic"},
        "latest_forecast": {"result": {"forward": {"pe": 8.7}}},
    }


def _forum_post(post_id, posted_at, text="Ciekawy wątek o wynikach.", upvotes=0, author="user1"):
    return {
        "post_id": post_id,
        "author": author,
        "posted_at": posted_at,
        "upvotes": upvotes,
        "content_text": text,
    }


def test_module_imports_without_pypi():
    """Acceptance: importing claude_client/prompts pulls neither `anthropic`
    nor `pydantic_settings` (nor even `sqlalchemy` — they touch no ORM code).
    Checked in a FRESH subprocess so sibling tests that already imported
    app.config/app.db.models don't pollute this process's sys.modules."""
    probe = (
        "import sys\n"
        "import app.services.claude_client\n"
        "import app.services.prompts\n"
        "assert 'anthropic' not in sys.modules, 'anthropic imported eagerly'\n"
        "assert 'pydantic_settings' not in sys.modules, "
        "'pydantic_settings imported eagerly'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert callable(claude_client.default_transport)
    assert callable(prompts_service.build_analysis_prompt)


def test_prompt_assembly_is_deterministic():
    """Same dossier + forum posts twice → byte-identical system/user prompts."""
    dossier = _dossier()
    posts = [_forum_post(1, "2026-07-01T10:00:00"), _forum_post(2, "2026-07-02T10:00:00")]
    first = prompts_service.build_analysis_prompt(dossier, posts)
    second = prompts_service.build_analysis_prompt(dossier, posts)
    assert first["system"] == second["system"]
    assert first["user"] == second["user"]
    assert first["snapshot"] == second["snapshot"]


def test_prompt_system_is_skill_plus_rubric():
    """system == SKILL.md + separator + rubric.md, read from the real repo-root
    `skill/` dir (verifies the parents[3] path resolution)."""
    skill_dir = BACKEND_DIR.parent / "skill"
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    rubric_md = (skill_dir / "rubric.md").read_text(encoding="utf-8")

    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    assert bundle["system"] == skill_md + "\n\n---\n\n" + rubric_md
    # sanity: a distinctive phrase from each source doc actually landed
    assert "Malik" in bundle["system"]
    assert "alignment_score" in bundle["system"]


def test_prompt_drops_non_decision_dossier_keys_and_keeps_the_rest():
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    snapshot_dossier = bundle["snapshot"]["dossier"]
    assert "company" not in snapshot_dossier
    assert "quarters" not in snapshot_dossier
    assert "dividends" not in snapshot_dossier
    for key in (
        "prescore", "ttm", "pe_history", "net_cash", "insights",
        "thesis", "scenarios", "valuation", "latest_forecast",
    ):
        assert key in snapshot_dossier
    # and it actually reached the rendered user text too
    assert "12000.0" in bundle["user"] or "12000" in bundle["user"]


def test_prompt_forum_posts_newest_first_and_labelled_as_opinions():
    posts = [
        _forum_post(1, "2026-01-01T00:00:00", text="stary post"),
        _forum_post(2, "2026-06-01T00:00:00", text="najnowszy post"),
        _forum_post(3, "2026-03-01T00:00:00", text="środkowy post"),
    ]
    bundle = prompts_service.build_analysis_prompt(_dossier(), posts)
    user = bundle["user"]
    assert user.index("najnowszy post") < user.index("środkowy post") < user.index("stary post")
    assert "NIEZWERYFIKOWANE OPINIE" in user
    assert bundle["snapshot"]["forum_posts"][0]["post_id"] == 2  # newest first in snapshot too


def test_prompt_forum_section_handles_no_posts():
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    assert "Brak postów forum" in bundle["user"]
    assert bundle["snapshot"]["forum_posts"] == []
    assert bundle["snapshot"]["forum_truncated"] is False


def test_prompt_caps_forum_posts_to_char_budget():
    """A huge number of posts must be truncated with a marker — the char
    budget (~30k) must not be exceeded, and the snapshot must reflect only the
    posts actually included (not the full input list)."""
    huge_text = "x" * 2000
    posts = [_forum_post(i, f"2026-01-{(i % 28) + 1:02d}T00:00:00", text=huge_text) for i in range(50)]
    bundle = prompts_service.build_analysis_prompt(_dossier(), posts)
    assert "obcięto" in bundle["user"]
    assert bundle["snapshot"]["forum_truncated"] is True
    assert len(bundle["snapshot"]["forum_posts"]) < len(posts)


# ======================================================= pure: claude_client.py


class StubTransport:
    """Scripted `(messages, model, tools, tool_choice) -> dict` delegate.
    Counts calls; raises/returns per a scripted list of "actions" so tests can
    exercise the bounded retry. Mirrors `test_thesis_ai.StubTransport`'s shape
    (records every call so a test can assert on what was actually SENT)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.requests = []

    def __call__(self, messages, model, tools, tool_choice):
        self.calls += 1
        self.requests.append((messages, model, tools, tool_choice))
        action = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(action, Exception):
            raise action
        return action


def _tool_use_resp(verdict: dict, *, input_tokens=1234, output_tokens=567) -> dict:
    return {
        "content": [
            {"type": "text", "text": "Oto analiza:"},
            {"type": "tool_use", "name": "zapisz_analize", "input": verdict},
        ],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def _text_resp(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _verdict(**overrides) -> dict:
    base = {
        "thesis": "Spółka tania na tle własnej historii, z rosnącą marżą.",
        "catalysts": [
            {"type": "operational", "description": "poprawa marży", "horizon": "2 kwartały", "priced_in": "nie"}
        ],
        "checklist": [
            {"item": "Wzrost przychodów", "verdict": "spełnia", "evidence": "przychody +12% r/r"}
        ],
        "red_flags": [],
        "one_off_risk": "Niski udział zdarzeń jednorazowych.",
        "forum_insights": [
            {"claim": "Użytkownicy oczekują poprawy wyników w Q3", "confidence": "low", "post_ids": [1, 2]}
        ],
        "alignment_score": 72,
        "potential": {"upside": "C/Z poniżej mediany", "downside": "ryzyko spowolnienia"},
        "verify_next": [{"id": "catalyst", "text": "potwierdź katalizator", "why": "brak w danych"}],
        "summary_pl": "Ciekawa okazja, wymaga potwierdzenia katalizatora.",
    }
    base.update(overrides)
    return base


def _settings(**overrides):
    import types

    base = dict(
        anthropic_api_key="test-key",
        anthropic_model="claude-test",
        ai_cache_enabled=False,
        ai_cache_dir=None,
        ai_daily_limit=20,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_happy_path_parses_verdict_and_tokens():
    verdict = _verdict()
    stub = StubTransport([_tool_use_resp(verdict, input_tokens=1000, output_tokens=250)])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])

    result = claude_client.run_analysis(bundle, settings=_settings(), transport=stub, ticker="SNT")

    assert result.verdict == verdict
    assert result.input_tokens == 1000
    assert result.output_tokens == 250
    assert result.model == "claude-test"
    assert result.engine == "ai"
    assert stub.calls == 1


def test_request_carries_forced_tool_use():
    """The call must force tool use with the `zapisz_analize` tool — a
    refactor that silently dropped `tools`/`tool_choice` (and reverted to free
    text) would not be caught by output-shape assertions alone."""
    stub = StubTransport([_tool_use_resp(_verdict())])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    claude_client.run_analysis(bundle, settings=_settings(), transport=stub, ticker="SNT")

    messages, model, tools, tool_choice = stub.requests[0]
    assert tool_choice == {"type": "tool", "name": "zapisz_analize"}
    assert tools[0]["name"] == "zapisz_analize"
    assert "alignment_score" in tools[0]["input_schema"]["properties"]
    assert model == "claude-test"
    # system prompt (SKILL.md+rubric) reached the request as its own turn
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert system_messages and "Malik" in system_messages[0]["content"]


def test_alignment_score_extracted_correctly():
    stub = StubTransport([_tool_use_resp(_verdict(alignment_score=41))])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    result = claude_client.run_analysis(bundle, settings=_settings(), transport=stub)
    assert result.verdict["alignment_score"] == 41


def test_text_fallback_parse_for_stub_simplicity():
    """A transport that returns plain-text JSON (no tool_use block) must still
    parse — the fallback path documented for stub simplicity."""
    verdict = _verdict(summary_pl="Tekstowa odpowiedź zamiast tool_use.")
    stub = StubTransport([_text_resp(json.dumps(verdict, ensure_ascii=False))])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    result = claude_client.run_analysis(bundle, settings=_settings(), transport=stub)
    assert result.verdict["summary_pl"] == "Tekstowa odpowiedź zamiast tool_use."


def test_no_key_raises_analysis_unavailable_never_fabricates():
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    try:
        claude_client.run_analysis(bundle, settings=_settings(anthropic_api_key=None))
        assert False, "expected AnalysisUnavailable"
    except claude_client.AnalysisUnavailable:
        pass


def test_malformed_response_raises_unavailable_not_fabricated():
    stub = StubTransport([_text_resp("Przepraszam, nie mogę zwrócić JSON.")])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    try:
        claude_client.run_analysis(bundle, settings=_settings(), transport=stub)
        assert False, "expected AnalysisUnavailable"
    except claude_client.AnalysisUnavailable:
        pass


def test_retry_on_transient_transport_error():
    """First attempt raises, second succeeds → result still comes back
    (bounded retry), and the transport was retried (called more than once)."""
    stub = StubTransport([RuntimeError("network blip"), _tool_use_resp(_verdict())])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    result = claude_client.run_analysis(bundle, settings=_settings(), transport=stub)
    assert result.verdict["alignment_score"] == 72
    assert stub.calls == 2


def test_transport_fails_every_attempt_raises_unavailable():
    stub = StubTransport([RuntimeError("down"), RuntimeError("down"), RuntimeError("down")])
    bundle = prompts_service.build_analysis_prompt(_dossier(), [])
    try:
        claude_client.run_analysis(bundle, settings=_settings(), transport=stub)
        assert False, "expected AnalysisUnavailable"
    except claude_client.AnalysisUnavailable:
        pass
    assert stub.calls >= 2  # bounded retry actually happened, not a single try


def test_cache_hit_skips_transport():
    tmp = Path(tempfile.mkdtemp(prefix="analysis_ai_cache_"))
    try:
        stub = StubTransport([_tool_use_resp(_verdict())])
        bundle = prompts_service.build_analysis_prompt(_dossier(), [])
        cfg = _settings(ai_cache_enabled=True, ai_cache_dir=str(tmp))

        first = claude_client.run_analysis(bundle, settings=cfg, transport=stub, ticker="SNT")
        second = claude_client.run_analysis(bundle, settings=cfg, transport=stub, ticker="SNT")

        assert stub.calls == 1  # second served from cache
        assert first.verdict == second.verdict
        assert list(tmp.glob("*.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cache_disabled_bypasses_cache():
    tmp = Path(tempfile.mkdtemp(prefix="analysis_ai_nocache_"))
    try:
        stub = StubTransport([_tool_use_resp(_verdict()), _tool_use_resp(_verdict())])
        bundle = prompts_service.build_analysis_prompt(_dossier(), [])
        cfg = _settings(ai_cache_enabled=False, ai_cache_dir=str(tmp))

        claude_client.run_analysis(bundle, settings=cfg, transport=stub, ticker="SNT")
        claude_client.run_analysis(bundle, settings=cfg, transport=stub, ticker="SNT")

        assert stub.calls == 2
        assert not list(tmp.glob("*.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================ client-gated: api/analyses.py
# These need the `client`/`db` pytest fixtures (tests/conftest.py) — a running
# sqlalchemy/fastapi/pydantic-settings stack this sandbox does not have. They
# are skipped by the `__main__` runner below (signature has parameters) and
# run normally under `pytest` on the user's machine.


def test_run_analysis_endpoint_persists_and_returns_verdict(client, db, monkeypatch):
    from app.db.models import Company

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()

    verdict = _verdict(alignment_score=63)
    stub = StubTransport([_tool_use_resp(verdict, input_tokens=111, output_tokens=222)])
    monkeypatch.setattr(
        "app.services.claude_client.default_transport", lambda settings: stub
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Settings is cached via lru_cache; force a fresh read that sees the key.
    from app.config import get_settings

    get_settings.cache_clear()

    response = client.post("/api/companies/SNT/analyses")
    assert response.status_code == 200
    body = response.json()
    assert body["alignment_score"] == 63
    assert body["input_tokens"] == 111
    assert body["output_tokens"] == 222
    assert body["output"]["summary_pl"] == verdict["summary_pl"]

    history = client.get("/api/companies/SNT/analyses").json()
    assert len(history) == 1
    assert history[0]["id"] == body["id"]

    get_settings.cache_clear()


def test_run_analysis_endpoint_503_without_key(client, db, monkeypatch):
    from app.db.models import Company

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    response = client.post("/api/companies/SNT/analyses")
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]
    get_settings.cache_clear()


def test_run_analysis_endpoint_daily_cap(client, db, monkeypatch):
    from app.db.models import Analysis, Company

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()

    for _ in range(2):
        db.add(Analysis(company_id=company.id, model="claude-test", output={"alignment_score": 50}))
    db.commit()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AI_DAILY_LIMIT", "2")
    from app.config import get_settings

    get_settings.cache_clear()

    response = client.post("/api/companies/SNT/analyses")
    assert response.status_code == 429
    assert "limit" in response.json()["detail"].lower()
    get_settings.cache_clear()


def test_run_analysis_endpoint_404_unknown_ticker(client, db):
    response = client.post("/api/companies/NOPE/analyses")
    assert response.status_code == 404


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
