"""Deterministic prompt assembly for the Phase-5 AI verdict (PLAN §8, P5.5).

`build_analysis_prompt` turns a computed dossier (services/dossier.py) + the
forum signal into the exact `{"system", "user"}` turn sent to Claude by
`services/claude_client.run_analysis`, plus a `snapshot` of what was actually
used — so a run is reproducible and two runs (e.g. before and after a
quarterly report) can be diffed (the "thesis re-verification" loop from the
strategy).

Forum signal (P5.9, PLAN §8 "Forum distillation")
--------------------------------------------------
Preferred path: pass `forum_claims` — a list of `forum_distiller.
DistilledClaim` (or plain dicts with the same shape) produced by
`services/forum_distiller.distill_company_posts` over posts already synced
into the DB. Each claim is rendered labelled with its confidence and source
post ids, explicitly marked as opinion, never fact. `app/api/analyses.py`
distils the fetched posts before calling this function.

`forum_posts` (raw posts) is kept as the LEGACY/fallback path for backward
compatibility — used only when `forum_claims` is not supplied (`None`).
Passing raw, undistilled posts straight into the verdict prompt is what
P5.9 replaces; new callers should always distil first.

No PyPI at import time
-----------------------
Only stdlib (`json`, `pathlib`) at module level — verified by
`test_analysis_ai.py::test_module_imports_without_pypi`, same discipline as
`thesis_ai.py`/`claude_client.py`. No network calls here either: this module
is pure assembly.
"""
from __future__ import annotations

import json
from pathlib import Path

# backend/app/services/prompts.py -> parents[0]=services, [1]=app, [2]=backend,
# [3]=repo root. (Verified empirically — do NOT assume parents[2] here; that
# is the backend/ root, as in thesis_ai._DEFAULT_CACHE_DIR, one level short of
# the repo-root `skill/` directory.)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SKILL_DIR = _REPO_ROOT / "skill"
_ANALYSIS_SYSTEM = """You are the Stock Analysis Workbench AI verdict reviewer.

Strategy frame:
- Use the Pawel Malik / OBS style as an analysis discipline, not as a buy/sell signal.
- First understand the company from the deterministic dossier, BiznesRadar premium expectations, ROIC/FCF/EV/dividend coverage, and PortalAnaliz forum_intelligence.
- Do not base the answer only on generic C/Z. C/Z can support valuation, but scenarios must be company-specific.
- Treat PortalAnaliz claims as unverified leads. Never quote raw forum text; use only the distilled claim summaries and source post ids provided.
- Do not invent numbers. If a number is missing, label the gap and put it in verify_next.

Required reasoning flow:
1. Identify the business/industry context and key drivers.
2. Compare recent fundamentals with BiznesRadar forecast_consensus for the next years.
3. Use premium metrics (ROIC, FCF, EV, dividend coverage) as priority context.
4. Use forum_intelligence only to add hypotheses, risks, catalysts and verification items.
5. Produce negative, base and positive scenarios based on those inputs.

Return a single forced tool call named `zapisz_analize` matching the provided schema.
Do not put XML markup or serialized tool-call text inside any string field.
"""

# ~30k chars of forum text (rough token proxy — good enough for a hard budget
# without pulling in a tokenizer dependency).
_FORUM_CHAR_BUDGET = 30_000
_TRUNCATION_MARKER = "…[obcięto — przekroczono budżet znaków na posty forum]"

# The decision-relevant slice of the dossier (PLAN §8 step 1). Deliberately
# excludes `company` (an ORM row), `dividends` (ORM rows), `quarters` (already
# folded into ttm/prescore/insights) and `freshness`/`forum` (bookkeeping, not
# analysis input) — kept lean and JSON-safe.
_DOSSIER_KEYS = (
    "prescore",
    "ttm",
    "pe_history",
    "net_cash",
    "market_data",
    "analysis_context_status",
    "insights",
    "thesis",
    "scenarios",
    "valuation",
    "latest_forecast",
    "forum",
)
_MAX_FORUM_FACTS_IN_DOSSIER = 0


def _dumps(obj) -> str:
    """Deterministic, pretty JSON — sorted keys so byte-identical inputs
    always produce a byte-identical prompt (snapshot diffing depends on this).
    `default=str` handles datetimes/Decimals without extra plumbing."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _load_skill_text(skill_dir: Path) -> str:
    # The full skill files remain the maintained reference. Runtime calls use a
    # compact system prompt so a real company dossier plus BR/PA context stays
    # inside a predictable latency and token envelope.
    return _ANALYSIS_SYSTEM


def _compact_forum_for_prompt(forum: dict) -> dict:
    if not isinstance(forum, dict):
        return forum
    compact = dict(forum)
    intelligence = compact.get("intelligence")
    if isinstance(intelligence, dict):
        compact_intelligence = dict(intelligence)
        facts = list(compact_intelligence.get("distilled_facts") or [])
        compact_intelligence["distilled_facts"] = facts[:_MAX_FORUM_FACTS_IN_DOSSIER]
        compact_intelligence["distilled_facts_total"] = len(facts)
        expectations = compact_intelligence.get("expectations")
        if isinstance(expectations, dict):
            # P5.9b: `expectations.claims` is the SAME list `analyses.py`
            # already distilled and passed via `forum_claims` — rendered
            # verbatim by `_claims_section` below. Echoing it again here
            # would duplicate every claim's text inside the dossier JSON
            # block, wasting the char budget twice over for no new signal.
            compact_expectations = dict(expectations)
            claims = list(compact_expectations.get("claims") or [])
            compact_expectations["claims"] = []
            compact_expectations["claims_total"] = len(claims)
            compact_intelligence["expectations"] = compact_expectations
        compact["intelligence"] = compact_intelligence
    return compact


def _dossier_snapshot(dossier: dict) -> dict:
    """Only the decision-relevant parts of the dossier, in a fixed key order."""
    snapshot = {key: dossier[key] for key in _DOSSIER_KEYS if key in dossier}
    if "forum" in snapshot:
        snapshot["forum"] = _compact_forum_for_prompt(snapshot["forum"])
    return snapshot


def _post_entry(post: dict) -> dict:
    """Normalise one forum post to the fields the skill needs, whatever the
    caller's dict shape (ORM-row-derived dict from app/api/analyses.py, or a
    hand-built test fixture using `text` instead of `content_text`)."""
    posted_at = post.get("posted_at")
    return {
        "post_id": post.get("post_id") if post.get("post_id") is not None else post.get("phpbb_post_id"),
        "author": post.get("author"),
        "posted_at": str(posted_at) if posted_at is not None else None,
        "upvotes": post.get("upvotes"),
        "text": post.get("content_text", post.get("text", "")),
    }


def _sort_key(entry: dict):
    # Newest first; posts with an unknown timestamp sort last (never crash on
    # a None vs None comparison).
    return entry["posted_at"] or ""


def _forum_section(forum_posts: list[dict]) -> tuple[list[dict], str, bool]:
    """Build the forum block: (posts actually included, rendered text,
    truncated?). Posts are newest-first and each is labelled as an opinion,
    never fed to the model as fact — the skill's "forum claims are opinions"
    rule is reinforced here too, not left to the system prompt alone."""
    entries = sorted((_post_entry(p) for p in forum_posts), key=_sort_key, reverse=True)

    header = (
        "UWAGA: poniższe posty forumowe to NIEZWERYFIKOWANE OPINIE "
        "użytkowników PortalAnaliz, nie fakty. Traktuj je wyłącznie jako "
        "kandydatów do weryfikacji (forum_insights), nigdy jako dowód liczby "
        "czy zdarzenia."
    )
    if not entries:
        return [], header + "\nBrak postów forum dla tej spółki.", False

    included: list[dict] = []
    rendered_lines: list[str] = [header, ""]
    used = sum(len(line) + 1 for line in rendered_lines)
    truncated = False

    for entry in entries:
        block = _dumps(entry)
        if used + len(block) + 1 > _FORUM_CHAR_BUDGET:
            truncated = True
            break
        rendered_lines.append(block)
        used += len(block) + 1
        included.append(entry)

    if truncated:
        rendered_lines.append(_TRUNCATION_MARKER)

    return included, "\n".join(rendered_lines), truncated


def _claim_entry(claim) -> dict:
    """Normalise one distilled claim, whatever the caller's shape (a
    `forum_distiller.DistilledClaim`, or a hand-built test dict)."""
    if hasattr(claim, "to_dict"):
        return claim.to_dict()
    if isinstance(claim, dict):
        return dict(claim)
    raise TypeError("forum_claims items must be DistilledClaim or dict")


def _claims_section(forum_claims: list) -> tuple[list[dict], str]:
    """Build the forum block from DISTILLED CLAIMS (P5.9), not raw posts.
    Each claim is labelled with its confidence and source post ids and
    explicitly marked as opinion, never fact — reinforcing the same rule
    `_forum_section` enforces for the legacy raw-post path."""
    header = (
        "UWAGA: poniższe to ustrukturyzowane TWIERDZENIA z PortalAnaliz "
        "(zapisane w forum_intelligence, bez raw tekstu postów) — "
        "nadal NIEZWERYFIKOWANE OPINIE użytkowników, NIE fakty. Każde ma "
        "etykietę pewności (confidence) i listę id postów źródłowych "
        "(source_post_ids). Traktuj je wyłącznie jako kandydatów do "
        "weryfikacji (forum_insights), nigdy jako dowód liczby czy zdarzenia."
    )
    entries = [_claim_entry(c) for c in forum_claims]
    if not entries:
        return [], header + "\nBrak wydestylowanych twierdzeń z forum dla tej spółki."

    lines = [header, ""]
    for entry in entries:
        lines.append(
            _dumps(
                {
                    "claim": entry.get("claim"),
                    "confidence": entry.get("confidence"),
                    "type": entry.get("type"),
                    "source_post_ids": entry.get("source_post_ids"),
                }
            )
        )
    return entries, "\n".join(lines)


def build_analysis_prompt(
    dossier: dict,
    forum_posts: list[dict] | None = None,
    *,
    forum_claims: list | None = None,
    skill_dir: Path | None = None,
) -> dict:
    """Assemble the `{"system", "user", "snapshot"}` prompt bundle.

    Deterministic and side-effect-free: same inputs always produce the same
    bundle. No network access.

    Forum section: pass `forum_claims` (preferred, P5.9 — distilled claims,
    each labelled with confidence + source post ids) to use the new path; it
    takes precedence when supplied (even an empty list is valid — a company
    with no forum signal yet). `forum_posts` (legacy raw posts, newest-first)
    is used only as a fallback when `forum_claims` is `None`, preserving the
    P5.5 behaviour for callers that have not been updated yet.
    """
    skill_dir = skill_dir or _DEFAULT_SKILL_DIR
    system = _load_skill_text(skill_dir)

    dossier_snapshot = _dossier_snapshot(dossier)

    if forum_claims is not None:
        claim_entries, forum_text = _claims_section(forum_claims)
        forum_label = "TWIERDZENIA Z FORUM (wydestylowane; opinie, nie fakty):"
        forum_posts_included: list[dict] = []
        forum_truncated = False
    else:
        forum_posts_included, forum_text, forum_truncated = _forum_section(forum_posts or [])
        forum_label = "POSTY Z FORUM (od najnowszych; opinie, nie fakty):"
        claim_entries = []

    user = "\n".join(
        [
            "WYMAGANY PRZEPŁYW ANALIZY: najpierw przeanalizuj spółkę na podstawie "
            "dossier, `market_data.forecast_consensus`, metryk premium BiznesRadar "
            "(ROIC/FCF/EV/dividend_coverage) oraz `forum.intelligence`; dopiero potem "
            "wypełnij tezę, potencjał i scenariusze. Nie opieraj scenariuszy wyłącznie "
            "na generycznych wskaźnikach typu C/Z. Jeżeli `analysis_context_status` "
            "wskazuje braki, nazwij je w verify_next zamiast zgadywać.",
            "",
            "DANE SPÓŁKI (dossier obliczony deterministycznie — nie zmyślaj "
            "liczb spoza podanych; braki danych są oznaczone wprost):",
            _dumps(dossier_snapshot),
            "",
            forum_label,
            forum_text,
        ]
    )

    snapshot = {
        "dossier": dossier_snapshot,
        "forum_posts": forum_posts_included,
        "forum_claims": claim_entries,
        "forum_truncated": forum_truncated,
    }

    return {"system": system, "user": user, "snapshot": snapshot}
