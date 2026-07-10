"""Investment-expectations refresh (services/forum_expectations.py, P5.9b).

DB-backed tests (ForumPost/ForumIntelligence rows), so — unlike
`test_forum_distiller.py`'s pure per-post classification tests — this module
needs the `db` fixture from `tests/conftest.py` and only runs under pytest,
same as `test_forum.py`/`test_refresh_prices.py`. `StubTransport`/`_text_resp`
mirror `test_forum_distiller.py`'s helpers (same scripted-response shape).
"""
from __future__ import annotations

import json
import types

from sqlalchemy import select

from app.db.models import Company, ForumIntelligence, ForumPost, ForumTopic
from app.services import forum_expectations


class StubTransport:
    """Scripted `(messages, model) -> dict` delegate — same shape as
    `test_forum_distiller.StubTransport`."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def __call__(self, messages, model):
        self.calls += 1
        action = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(action, Exception):
            raise action
        return action


def _text_resp(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


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


def _company_with_posts(db, *, texts: list[str]) -> Company:
    company = Company(ticker="DEC", name="DECORA")
    db.add(company)
    db.flush()
    topic = ForumTopic(
        company_id=company.id, url="https://portalanaliz.pl/forum/viewtopic.php?t=1"
    )
    db.add(topic)
    db.flush()
    for i, text in enumerate(texts):
        db.add(
            ForumPost(
                topic_id=topic.id,
                phpbb_post_id=100 + i,
                author=f"user{i}",
                content_text=text,
            )
        )
    db.commit()
    return company


def _expectations(db, company: Company):
    return db.scalar(
        select(ForumIntelligence).where(
            ForumIntelligence.company_id == company.id,
            ForumIntelligence.source == "portal_analiz",
        )
    )


# --------------------------------------------------------------- happy path


def test_refresh_expectations_happy_path_upserts_claims(db):
    """Posts with content are distilled and merged onto a fresh
    ForumIntelligence row (none exists yet for this company)."""
    company = _company_with_posts(
        db,
        texts=[
            "Zarząd zapowiedział skup akcji.",
            "Fajna spółka na dłuższą metę.",
        ],
    )
    stub = StubTransport(
        [
            _text_resp(
                {
                    "type": "fact-claim",
                    "claims": [
                        {"claim": "Zarząd zapowiedział skup akcji.", "confidence": "medium"}
                    ],
                }
            ),
            _text_resp({"type": "opinion", "claims": []}),
        ]
    )

    result = forum_expectations.refresh_expectations(
        db, company, settings=_settings(), transport=stub
    )

    assert result.status == "ok"
    assert result.claim_count == 1

    record = _expectations(db, company)
    assert record is not None
    assert record.expectations["claims"] == [
        {
            "claim": "Zarząd zapowiedział skup akcji.",
            "confidence": "medium",
            "type": "fact-claim",
            "source_post_ids": [100],
        }
    ]
    assert record.expectations["model"] == "claude-distill-test"
    assert record.expectations["source_post_count"] == 2
    assert "updated_at" in record.expectations


def test_refresh_expectations_updates_existing_intelligence_row(db):
    """An already-existing ForumIntelligence row (written by the keyword
    heuristic at sync time) gets its `expectations` field set in place —
    `distilled_facts` etc. are left untouched."""
    company = _company_with_posts(db, texts=["Backlog rośnie kwartał do kwartału."])
    db.add(
        ForumIntelligence(
            company_id=company.id,
            source="portal_analiz",
            distilled_facts=[{"fact": "Forum wskazuje temat: portfel zamówień"}],
            community_sentiment="positive",
        )
    )
    db.commit()

    stub = StubTransport(
        [
            _text_resp(
                {
                    "type": "fact-claim",
                    "claims": [{"claim": "Backlog rośnie.", "confidence": "high"}],
                }
            )
        ]
    )
    result = forum_expectations.refresh_expectations(
        db, company, settings=_settings(), transport=stub
    )

    assert result.status == "ok"
    record = _expectations(db, company)
    assert record.expectations["claims"][0]["claim"] == "Backlog rośnie."
    # untouched keyword-heuristic fields
    assert record.community_sentiment == "positive"
    assert record.distilled_facts == [{"fact": "Forum wskazuje temat: portfel zamówień"}]


# ------------------------------------------------------------ no-key path


def test_refresh_expectations_no_key_does_not_overwrite(db):
    """No ANTHROPIC_API_KEY configured -> skip, leaving a prior run's
    expectations exactly as they were (never clobber good data with empty)."""
    company = _company_with_posts(db, texts=["Zarząd zapowiedział skup akcji."])
    existing_payload = {
        "claims": [
            {
                "claim": "stara teza",
                "confidence": "high",
                "type": "fact-claim",
                "source_post_ids": [1],
            }
        ],
        "model": "claude-old",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "source_post_count": 5,
    }
    db.add(
        ForumIntelligence(
            company_id=company.id, source="portal_analiz", expectations=existing_payload
        )
    )
    db.commit()

    result = forum_expectations.refresh_expectations(
        db, company, settings=_settings(anthropic_api_key=None)
    )

    assert result.status == "skipped"
    record = _expectations(db, company)
    assert record.expectations == existing_payload


# ------------------------------------------------------------ error path


def test_refresh_expectations_degrades_on_unexpected_error(db, monkeypatch):
    """Any unexpected failure (here: the distiller call itself blowing up)
    must degrade to status="error" rather than raise into the caller — a bad
    distillation run must never fail `refresh_company`."""
    company = _company_with_posts(db, texts=["Zarząd zapowiedział skup akcji."])

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(forum_expectations.forum_distiller, "distill_company_posts", boom)

    result = forum_expectations.refresh_expectations(db, company, settings=_settings())

    assert result.status == "error"
    assert "boom" in (result.detail or "")
    # nothing half-written: no ForumIntelligence row was created
    assert _expectations(db, company) is None


def test_refresh_expectations_no_posts_still_ok_with_empty_claims(db):
    """Zero posts with content_text is a legitimate (not erroneous) result —
    the distiller degrades to an empty list, and that IS the honest answer
    (nothing to distil yet), so it is stored rather than skipped."""
    company = Company(ticker="NEW", name="NOWA")
    db.add(company)
    db.commit()

    result = forum_expectations.refresh_expectations(
        db, company, settings=_settings(), transport=StubTransport([])
    )

    assert result.status == "ok"
    assert result.claim_count == 0
    record = _expectations(db, company)
    assert record.expectations["claims"] == []
    assert record.expectations["source_post_count"] == 0
