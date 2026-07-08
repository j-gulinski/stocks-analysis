"""Forum distillation pass (PLAN §8 "Forum distillation", P5.9).

Forum posts are UNVERIFIED opinions and must never enter the AI verdict as
facts. This module runs a separate, cheap-model pass OVER POSTS ALREADY
SYNCED into the DB (`services/forum_sync.py`) — it triggers **zero** new
forum HTTP requests. Each post is classified (fact-claim / opinion /
question / noise) and any concrete claims are pulled out with a confidence
label. Results are cached **per post** (file cache keyed by post id +
content hash + model) so a post is ever distilled once — a second run over
an unchanged post costs zero transport calls.

`distill_company_posts` merges the per-post claims into a deduplicated,
upvote-weighted, budget-truncated list of `DistilledClaim`s. `services/
prompts.py` renders that list into the verdict prompt labelled "opinie, nie
fakty" — never as raw post text (see `build_analysis_prompt`'s
`forum_claims` parameter).

Relationship to `thesis_ai.py` / `claude_client.py`
----------------------------------------------------
Same deterministic-first discipline as the other AI services: no API key —
or any transport/parse failure on a given post — degrades that post to an
empty/neutral distillation (no claims) rather than raising, so the Phase-5
analysis run always completes, just without forum claims for that post.
`transport`/`settings` are injectable exactly like
`thesis_ai.default_transport` / `claude_client.default_transport` (a stub
replaces the network call in tests).

"Batched, cheap-model pass" (PLAN §8) here means: bounded call COUNT
(`max_posts`) and bounded call SIZE (each post's text truncated before it
reaches the model) — not one combined multi-post prompt. A combined prompt
would break the per-post cache granularity (one post's edit would bust every
other post's cache entry), so each post gets its own small, cheap call
instead.

No PyPI at import time
-----------------------
Only stdlib at module level (`json`, `hashlib`, `pathlib`, `dataclasses`) —
verified by `test_forum_distiller.py::test_module_imports_without_pypi`,
same discipline as `claude_client.py`/`prompts.py`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# Where cached per-post distillations live (gitignored). `parents[2]` ==
# the backend/ root, same convention as thesis_ai._DEFAULT_CACHE_DIR /
# claude_client._DEFAULT_CACHE_DIR.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "forum_claims"

_VALID_TYPES = frozenset({"fact-claim", "opinion", "question", "noise"})
_VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

# A neutral, no-claims result — returned whenever we cannot (or should not,
# e.g. no key) call the model for a post. Never raises the caller into a
# missing-forum-section state.
_EMPTY_DISTILLATION = {"type": "opinion", "claims": []}

# Bound cost per call: a single post's text is truncated before it ever
# reaches the model (a wall-of-text post shouldn't blow the per-call budget).
_POST_TEXT_CHAR_BUDGET = 4000

# Bound how many posts get a model call at all in one distillation run (cost
# guard — same spirit as api/analyses.py._FORUM_POST_LIMIT). Posts beyond
# this, in upvote-weighted order, are simply never distilled — not an error.
_DEFAULT_MAX_POSTS = 60

# Final claims list char budget (rough token proxy — same style as
# prompts.py._FORUM_CHAR_BUDGET) — keeps the verdict prompt's forum section
# bounded even if many posts each yield a claim.
_DEFAULT_CLAIMS_CHAR_BUDGET = 8_000

_MAX_TOKENS = 300  # small cheap-model reply: one classification + a few claims
_FALLBACK_MODEL = "claude-haiku-4-5"

# Anthropic Messages API wiring (only used by `default_transport`, never
# exercised in-session — no egress in the sandbox). No secret literal here.
_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


@dataclass
class DistilledClaim:
    """One concrete, deduplicated claim distilled from one or more posts.

    `source_post_ids` carries every `phpbb_post_id` whose distillation
    produced this (normalised-identical) claim text — the verdict prompt
    shows these ids so a human can go verify against the actual post."""

    claim: str
    confidence: str
    type: str
    source_post_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "confidence": self.confidence,
            "type": self.type,
            "source_post_ids": list(self.source_post_ids),
        }


# --------------------------------------------------------------- settings/dep


def _resolve_settings(settings):
    """Return the injected settings, or lazily load the pydantic `Settings`.

    Deferred so this module loads without pydantic-settings in the sandbox;
    tests always inject a lightweight stub."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


# ------------------------------------------------------------- post handling


def _post_entry(post) -> dict:
    """Normalise one post to a plain dict, tolerant of an ORM `ForumPost`
    row, a dict shaped like `app/api/analyses.py._recent_forum_posts`
    (`post_id`/`content_text`), or a hand-built test fixture (`text`)."""
    if isinstance(post, dict):
        getter = post.get
    else:
        getter = lambda key, default=None: getattr(post, key, default)  # noqa: E731

    post_id = getter("post_id")
    if post_id is None:
        post_id = getter("phpbb_post_id")
    return {
        "post_id": post_id,
        "author": getter("author"),
        "posted_at": getter("posted_at"),
        "upvotes": getter("upvotes"),
        "text": getter("content_text") or getter("text") or "",
    }


def _sort_key_posted(entry: dict):
    posted_at = entry.get("posted_at")
    return str(posted_at) if posted_at is not None else ""


def _sort_key_upvotes(entry: dict):
    upvotes = entry.get("upvotes")
    # None sorts last (True > False); larger upvotes sort first (ascending
    # on the negated value). Two stable sorts (posted_at desc, then this)
    # reproduce SQL's `ORDER BY upvotes DESC NULLS LAST, posted_at DESC` —
    # the same "sort=top" ordering `app/api/forum.py::get_company_posts`
    # documents as "the ordering the AI layer will use to budget tokens".
    return (upvotes is None, -(upvotes or 0))


def _top_ordered(entries: list[dict]) -> list[dict]:
    ordered = sorted(entries, key=_sort_key_posted, reverse=True)
    ordered = sorted(ordered, key=_sort_key_upvotes)
    return ordered


def _normalize_claim(text: str) -> str:
    """Case/whitespace-insensitive key for exact-claim deduplication."""
    return " ".join(text.lower().split())


# ------------------------------------------------------------------- prompt

_INSTRUCTIONS = (
    "Klasyfikujesz JEDEN post z polskiego forum inwestorskiego PortalAnaliz, "
    "dotyczący spółki notowanej na GPW. Zwróć WYŁĄCZNIE jeden obiekt JSON "
    "(bez markdown, bez tekstu poza nim) z dokładnie takimi kluczami:\n"
    '  "type": jedno z ["fact-claim", "opinion", "question", "noise"],\n'
    '  "claims": [{"claim": string (po polsku, jedno konkretne zdanie), '
    '"confidence": jedno z ["low", "medium", "high"]}]\n\n'
    "ZASADY:\n"
    '1. "claims" wypełniasz TYLKO gdy post zawiera konkretne, sprawdzalne '
    "twierdzenie o spółce (liczba, zdarzenie, fakt) — nie ogólne odczucia czy "
    "nastawienie.\n"
    '2. Czysta opinia/spekulacja bez konkretu -> type="opinion", claims=[].\n'
    '3. Pytanie bez twierdzenia -> type="question", claims=[].\n'
    '4. Spam/off-topic/brak treści -> type="noise", claims=[].\n'
    "5. Nie dodawaj faktów spoza treści posta; confidence odzwierciedla "
    "pewność AUTORA posta, nie Twoją ocenę czy to prawda.\n"
    '6. Gdy post zawiera wiele twierdzeń, zwróć każde osobno w "claims".'
)


def _build_prompt(author, text: str, upvotes) -> str:
    payload = {
        "author": author,
        "upvotes": upvotes,
        "text": (text or "")[:_POST_TEXT_CHAR_BUDGET],
    }
    return _INSTRUCTIONS + "\n\nPOST:\n" + json.dumps(payload, ensure_ascii=False)


# ------------------------------------------------------------------ transport


def default_transport(settings):
    """Build the production transport: a callable ``(messages, model) -> dict``
    returning the raw Anthropic Messages-API response shape.

    Resolution order (both lazy so import stays PyPI-free):
      1. the official `anthropic` SDK if it is importable;
      2. a stdlib `urllib` POST with the correct headers.

    Never exercised in-session — the tests inject a stub instead. Same shape
    as `thesis_ai.default_transport` (free-text JSON, no forced tool use —
    the classifier's schema is small enough not to need it)."""

    api_key = getattr(settings, "anthropic_api_key", None)

    def _call(messages: list[dict], model: str) -> dict:
        try:
            import anthropic  # lazy: optional dependency

            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model, max_tokens=_MAX_TOKENS, messages=messages
            )
            return {
                "content": [
                    {"type": "text", "text": getattr(block, "text", "")}
                    for block in resp.content
                ]
            }
        except ImportError:
            pass  # fall through to stdlib

        import urllib.request  # lazy: stdlib, but keep import local

        body = json.dumps(
            {"model": model, "max_tokens": _MAX_TOKENS, "messages": messages}
        ).encode("utf-8")
        request = urllib.request.Request(
            _API_URL,
            data=body,
            headers={
                "x-api-key": api_key or "",
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    return _call


# ----------------------------------------------------------- response parsing


def _extract_json(text: str):
    """Best-effort JSON extraction: tolerate ```json fences and surrounding
    prose. Returns the parsed object or None (malformed). Duplicated (not
    imported) from thesis_ai/claude_client's identical helper so this module
    stays free of their import chains (only stdlib at module level)."""
    trimmed = text.strip()
    if trimmed.startswith("```"):
        parts = trimmed.split("```")
        trimmed = parts[1] if len(parts) >= 2 else trimmed.strip("`")
        if trimmed.startswith("json"):
            trimmed = trimmed[4:]
        trimmed = trimmed.strip()
    try:
        return json.loads(trimmed)
    except Exception:  # noqa: BLE001 — any parse error → try to locate an object
        start, end = trimmed.find("{"), trimmed.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(trimmed[start : end + 1])
            except Exception:  # noqa: BLE001
                return None
        return None


def _extract_text(raw) -> str:
    if not isinstance(raw, dict):
        return ""
    content = raw.get("content")
    if isinstance(content, list):
        return "".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    if isinstance(content, str):
        return content
    return ""


def _validate_distillation(parsed) -> dict | None:
    if not isinstance(parsed, dict):
        return None
    ptype = parsed.get("type")
    if ptype not in _VALID_TYPES:
        return None
    claims_raw = parsed.get("claims")
    if not isinstance(claims_raw, list):
        return None
    claims: list[dict] = []
    for item in claims_raw:
        if not isinstance(item, dict):
            return None
        claim_text = item.get("claim")
        confidence = item.get("confidence")
        if not isinstance(claim_text, str) or not claim_text.strip():
            return None
        if confidence not in _VALID_CONFIDENCE:
            return None
        claims.append({"claim": claim_text.strip(), "confidence": confidence})
    return {"type": ptype, "claims": claims}


# --------------------------------------------------------------------- cache


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(settings, post_id, text: str, model: str) -> Path:
    """One JSON file per (post id, content hash, model) — content-hash keyed
    so an edited/re-synced post busts its own cache entry without touching
    any other post's."""
    base_dir = Path(getattr(settings, "ai_cache_dir", None) or _DEFAULT_CACHE_DIR)
    digest = _short_hash(
        _json({"post_id": post_id, "text": _short_hash(text or ""), "model": model})
    )
    return base_dir / f"post{post_id if post_id is not None else 'unknown'}_{digest}.json"


def _cache_read(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _cache_write(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, default=str)
    except OSError:
        pass  # cache is best-effort; a write failure must never break the run


# ---------------------------------------------------------- per-post distill


def _distill_post(
    entry: dict,
    *,
    settings,
    transport,
    model: str,
    cache_enabled: bool,
) -> dict:
    """Classify + extract claims for one post. Cached; degrades to the
    neutral no-claims result on any failure (no transport available, a
    transport error, or a malformed/unparseable response) rather than
    raising — forum distillation having a bad day must never break the
    Phase-5 analysis run."""
    post_id = entry["post_id"]
    text = entry["text"] or ""
    cache_file = _cache_path(settings, post_id, text, model)
    if cache_enabled:
        cached = _cache_read(cache_file)
        if cached is not None:
            return cached

    if transport is None:
        # No API key (or explicitly disabled) — graceful degrade, no call,
        # nothing cached (so a later run WITH a key still does the real
        # call instead of being stuck on a cached empty result).
        return dict(_EMPTY_DISTILLATION)

    prompt = _build_prompt(entry.get("author"), text, entry.get("upvotes"))
    messages = [{"role": "user", "content": prompt}]
    try:
        raw = transport(messages, model)
    except Exception:  # noqa: BLE001 — any transport error → degrade, don't raise
        return dict(_EMPTY_DISTILLATION)

    parsed = _extract_json(_extract_text(raw))
    validated = _validate_distillation(parsed)
    if validated is None:
        return dict(_EMPTY_DISTILLATION)

    if cache_enabled:
        _cache_write(cache_file, validated)
    return validated


# --------------------------------------------------------------- entry point


def distill_company_posts(
    posts,
    *,
    settings=None,
    transport=None,
    budget: int | None = None,
    max_posts: int = _DEFAULT_MAX_POSTS,
) -> list[DistilledClaim]:
    """Distil already-synced forum posts into deduplicated, upvote-weighted,
    budget-truncated claims. Triggers ZERO forum HTTP requests — `posts` are
    whatever the caller already fetched from the DB (ORM rows or dicts).

    `budget` is a char budget on the OUTPUT claims list (rough token proxy,
    same convention as `prompts.py`'s forum char budget); `max_posts` bounds
    how many posts get a model call at all, in "sort=top" order (upvotes
    desc, nulls last, then newest first) — the same ordering
    `app/api/forum.py::get_company_posts(sort="top")` uses.

    No API key configured ⇒ every post degrades to an empty distillation
    (no claims) — this function never raises on the no-key path, and the
    caller (`api/analyses.py`) always gets a valid (possibly empty) claims
    list to hand to `build_analysis_prompt`.
    """
    settings = _resolve_settings(settings)
    budget = _DEFAULT_CLAIMS_CHAR_BUDGET if budget is None else budget

    entries = [_post_entry(p) for p in posts]
    entries = [e for e in entries if (e["text"] or "").strip()]  # nothing to distil
    ordered = _top_ordered(entries)[:max_posts]

    api_key = getattr(settings, "anthropic_api_key", None)
    model = (
        getattr(settings, "ai_distill_model", None)
        or getattr(settings, "anthropic_model", None)
        or _FALLBACK_MODEL
    )
    cache_enabled = bool(getattr(settings, "ai_cache_enabled", True))

    active_transport = None
    if api_key:
        active_transport = transport or default_transport(settings)

    merged: dict[str, DistilledClaim] = {}
    first_seen_order: list[str] = []

    for entry in ordered:
        distillation = _distill_post(
            entry,
            settings=settings,
            transport=active_transport,
            model=model,
            cache_enabled=cache_enabled,
        )
        claim_type = distillation.get("type", "opinion")
        post_id = entry["post_id"]
        for claim in distillation.get("claims", []):
            key = _normalize_claim(claim["claim"])
            existing = merged.get(key)
            if existing is None:
                merged[key] = DistilledClaim(
                    claim=claim["claim"],
                    confidence=claim["confidence"],
                    type=claim_type,
                    source_post_ids=[post_id] if post_id is not None else [],
                )
                first_seen_order.append(key)
            else:
                if post_id is not None and post_id not in existing.source_post_ids:
                    existing.source_post_ids.append(post_id)
                if _CONFIDENCE_RANK[claim["confidence"]] > _CONFIDENCE_RANK[existing.confidence]:
                    existing.confidence = claim["confidence"]

    # `first_seen_order` already reflects the upvote-weighted `ordered`
    # sequence (a claim is recorded the first time it is encountered).
    claims = [merged[key] for key in first_seen_order]

    out: list[DistilledClaim] = []
    used = 0
    for claim in claims:
        size = len(_json(claim.to_dict()))
        if used + size > budget:
            break
        out.append(claim)
        used += size
    return out
