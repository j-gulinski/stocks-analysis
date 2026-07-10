"""Optional iterative Claude-API refiner for the per-company insights read
(Fundamenty tab + the Brief tab's "Najważniejsze sygnały" both render
`dossier.insights`).

What this is
-----------
`insights.build_insights` (services/insights.py) produces a *deterministic*
read: a picked indicator set (sector/size aware), a good/bad verdict per
indicator with a template-composed Polish comment, strengths/concerns lists,
missing-data gaps, and a summary paragraph assembled by string-concatenating
`Insight.brief` fragments. That template-composed prose is honest but reads
mechanically ("wrongly static" per the user). This module can rewrite the
PROSE ONLY with the Claude API — the summary, each indicator's comment, and
the strengths/concerns wording — while staying inside the same two hard
guard-rails every other refiner in this codebase uses:

  * **Deterministic-first.** With no API key (the sandbox default) the
    refiner returns the deterministic block verbatim, marked
    ``engine: "deterministic"``. It never raises on the no-key path — the
    caller always gets an insights block.
  * **No fabricated numbers.** Every number the model's prose contains must
    already be present in the deterministic insights block or the supplied
    `context` (prescore, TTM, net cash, own-history C/Z, forum-distilled
    expectations, analyst forecast consensus, thesis entry-quality). A stray
    figure invalidates the whole round; the refiner falls back to the last
    valid read (or the deterministic one).

Unlike `thesis_ai`/`scenarios_ai`, the model may NOT add, remove, or reorder
`key_indicators`, and may NEVER touch `value`/`verdict`/`importance` — those
are re-imposed from the deterministic block on every round; only `comment`
(per indicator, keyed by id) and the free-form `summary`/`strengths`/
`concerns` are writable. A model that omits an indicator's comment simply
falls back to the deterministic text for that one indicator (partial
responses are fine — this is NOT the same "drop is allowed" rule
`thesis_ai` uses for pros/cons).

Design notes (for a C# dev): same shape as `thesis_ai.refine_thesis` — an
**injected `transport`** delegate makes the network call swappable (tests
inject a scripted stub); the Anthropic SDK + pydantic `Settings` stay lazy
imports so this module (and its tests) load under a bare system Python with
only the stdlib + our pure `insights` layer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.services import thesis_ai

# Gitignored cache dir, separate from the other refiners'.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "insights_ai"


# ------------------------------------------------------------- settings/dep


def _resolve_settings(settings):
    """Injected settings, or the lazily-loaded pydantic `Settings` (deferred
    so this module imports without pydantic-settings in the sandbox)."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


def _as_dict(insights_block) -> dict:
    """Accept either a `CompanyInsights` or an already-serialised dict."""
    if hasattr(insights_block, "to_dict"):
        return insights_block.to_dict()
    if isinstance(insights_block, dict):
        return dict(insights_block)
    raise TypeError("insights_block must be a CompanyInsights or dict")


# --------------------------------------------------------- number vocabulary
# Same fabrication-guard grammar as thesis_ai/scenarios_ai/valuation_ai
# (`thesis_ai.numbers` — an optional sign, digits, optional decimal comma/
# period), just walked recursively over a nested dict/list structure instead
# of a fixed field list, since both the deterministic block and the caller's
# `context` payload are open-shaped.


def _collect_numbers(value) -> set[float]:
    """Every numeric token anywhere inside a nested dict/list/scalar
    structure — recurses through dicts/lists, adds int/float leaves
    directly, and regex-scans string leaves via `thesis_ai.numbers`. Used for
    BOTH the deterministic insights block and the `context` payload, so the
    AI path's allowed-number set is the union of everything it was shown."""
    nums: set[float] = set()
    if isinstance(value, dict):
        for v in value.values():
            nums |= _collect_numbers(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            nums |= _collect_numbers(v)
    elif isinstance(value, bool):
        pass  # bool is an int subclass — exclude before the int/float branch
    elif isinstance(value, (int, float)):
        nums.add(round(float(value), 4))
    elif isinstance(value, str):
        nums |= thesis_ai.numbers(value)
    return nums


def collect_deterministic_numbers(det: dict) -> set[float]:
    """Numbers the engine is allowed to quote from the deterministic insights
    block itself (name/value/comment/summary/strengths/concerns/missing/
    data_notes/coverage — everything)."""
    return _collect_numbers(det)


def collect_context_numbers(context: dict | None) -> set[float]:
    """Numbers the engine is allowed to quote from the caller-supplied
    decision context (prescore, ttm, net_cash, pe_history, forum
    expectations, forecast_consensus, thesis entry_quality, ...)."""
    return _collect_numbers(context or {})


def collect_prose_numbers(insights_dict: dict) -> set[float]:
    """Every number in the prose the user actually reads and the model may
    have rewritten: `summary`, each indicator's `comment`, `strengths`,
    `concerns`. Deliberately excludes `value`/`missing`/`data_notes`/
    `coverage` — those are re-imposed verbatim from the deterministic block
    and never touched by the model, so guarding them again is redundant."""
    parts: list[str] = [str(insights_dict.get("summary", ""))]
    for ind in insights_dict.get("key_indicators", []) or []:
        parts.append(str(ind.get("comment", "")))
    parts += [str(s) for s in (insights_dict.get("strengths") or [])]
    parts += [str(s) for s in (insights_dict.get("concerns") or [])]
    nums: set[float] = set()
    for part in parts:
        nums |= thesis_ai.numbers(part)
    return nums


# ------------------------------------------------------------------- prompt

_INSTRUCTIONS = (
    "You rewrite the PROSE of a rule-based per-company insights read for a "
    "Warsaw-listed (GPW) stock, in the spirit of Pawel Malik's strategy plus "
    "general fundamental analysis. You are given the DETERMINISTIC insights "
    "(a picked indicator set with computed value/verdict/importance, "
    "strengths, concerns, missing data, data notes, coverage) and a compact "
    "decision-relevant CONTEXT (prescore, TTM figures, net cash, own-history "
    "C/Z, forum-distilled investor expectations, analyst forecast consensus, "
    "and — if available — the investment-thesis entry-quality read) so your "
    "rewrite weighs the WHOLE picture, not just the indicator list in "
    "isolation.\n\n"
    "IMPORTANT: `forecast_consensus` is ANALYST OPINION (BiznesRadar "
    "consensus estimates, often thin coverage for small/mid GPW names) — "
    "treat it cautiously, attribute it explicitly as analyst consensus, "
    "never present it as an achieved or certain fact.\n\n"
    "Return ONLY a single JSON object (no markdown, no prose outside it) "
    "with exactly these keys:\n"
    '  "summary": string,   // Polish paragraph reading like an analyst '
    "weighing ALL the evidence (indicators + context), not a template\n"
    '  "key_indicators": [{"id": string, "comment": string}],  // one Polish '
    "one-liner per indicator id already in the current set; ids MUST come "
    "from the current key_indicators — you may cover fewer, never invent an "
    "id\n"
    '  "strengths": [string],   // Polish, reworded/trimmed from the current '
    "strengths — no new points beyond what the current list already "
    "conveys\n"
    '  "concerns": [string],    // same rule\n'
    '  "changes": [{"field": string, "rationale": string}]   // what you '
    "changed and why\n\n"
    "HARD RULES:\n"
    "1. NEVER introduce a number (percentage, ratio, PLN amount, multiple, "
    "year, count) that is not already present in the deterministic insights "
    "or the context. Quote figures verbatim. Any invented number invalidates "
    "your whole answer.\n"
    "2. Do NOT add, remove, or reorder key indicators, and do NOT change any "
    "value/verdict/importance — only reword the comment text.\n"
    "3. Do NOT pad strengths/concerns with invented points; reword or trim "
    "only.\n"
    "4. Domain language stays Polish. This is an ENTRANCE to human analysis, "
    "never a buy/sell signal.\n"
    "5. If you cannot improve the current read, return it unchanged (a "
    "valid, converged answer)."
)


def _build_prompt(det: dict, context: dict, current: dict) -> str:
    payload = {
        "deterministic_insights": {
            "size_label": det.get("size_label"),
            "sector_group_label": det.get("sector_group_label"),
            "sector": det.get("sector"),
            "key_indicators": det.get("key_indicators"),
            "missing": det.get("missing"),
            "data_notes": det.get("data_notes"),
            "coverage": det.get("coverage"),
        },
        "context": context,
        "current": {
            "summary": current.get("summary"),
            "key_indicators": [
                {"id": i.get("id"), "comment": i.get("comment")}
                for i in current.get("key_indicators", []) or []
            ],
            "strengths": current.get("strengths"),
            "concerns": current.get("concerns"),
        },
    }
    return _INSTRUCTIONS + "\n\nDATA:\n" + json.dumps(
        payload, ensure_ascii=False, default=str
    )


# -------------------------------------------------------- validate / merge


def _sanitize_notes(raw) -> list:
    """Coerce the model's `changes` to JSON-safe, capped data (provenance
    shown in `ai_notes`, NOT company claims — outside the number guard)."""
    if not isinstance(raw, list):
        return []
    out: list = []
    for item in raw[:10]:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append(
                {
                    str(k): (v if isinstance(v, (str, int, float, bool)) else str(v))
                    for k, v in item.items()
                }
            )
    return out


def _str_list(raw, fallback: list) -> list:
    """A list of non-empty strings from the model, or the deterministic
    fallback verbatim when the shape is wrong or empty after filtering."""
    if not isinstance(raw, list):
        return list(fallback)
    out = [s for s in raw if isinstance(s, str) and s.strip()]
    return out if out else list(fallback)


def _validate_and_merge(parsed: dict, det: dict) -> dict | None:
    """Enforce the schema and merge the reworded prose onto the
    deterministic insights (structured fields re-imposed). Returns the
    merged insights dict, or None on ANY structural failure (caller falls
    back to the last valid read). The fabrication guard is checked
    separately by the caller (needs the allowed-number set)."""
    if not isinstance(parsed, dict):
        return None

    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    det_ids = {i["id"] for i in det.get("key_indicators", [])}
    proposed = parsed.get("key_indicators")
    if proposed is not None and not isinstance(proposed, list):
        return None

    overrides: dict[str, str] = {}
    if isinstance(proposed, list):
        for item in proposed:
            if not isinstance(item, dict):
                continue
            iid, comment = item.get("id"), item.get("comment")
            # An id outside the deterministic set would be an invented
            # indicator — reject the whole round rather than silently drop
            # it (same "no invented ids" contract as thesis_ai's pros/cons).
            if iid not in det_ids:
                return None
            if isinstance(comment, str) and comment.strip():
                overrides[iid] = comment

    # Re-impose value/verdict/importance/name for every indicator; only the
    # comment may change, and ONLY for ids the model actually covered — a
    # dropped id simply keeps its deterministic comment (not a rejection).
    merged_indicators = []
    for ind in det.get("key_indicators", []):
        entry = dict(ind)
        if entry["id"] in overrides:
            entry["comment"] = overrides[entry["id"]]
        merged_indicators.append(entry)

    strengths = _str_list(parsed.get("strengths"), det.get("strengths", []))
    concerns = _str_list(parsed.get("concerns"), det.get("concerns", []))
    # Cap growth at the deterministic count — reword/trim only, never pad
    # with extra invented points (rule 3 in the prompt).
    strengths = strengths[: len(det.get("strengths", []))]
    concerns = concerns[: len(det.get("concerns", []))]

    return {
        "size_code": det.get("size_code"),
        "size_label": det.get("size_label"),
        "sector_group": det.get("sector_group"),
        "sector_group_label": det.get("sector_group_label"),
        "sector": det.get("sector"),
        "key_indicators": merged_indicators,
        "strengths": strengths,
        "concerns": concerns,
        "missing": det.get("missing", []),
        "data_notes": det.get("data_notes", []),
        "coverage": det.get("coverage"),
        "summary": summary.strip(),
    }


def _refinable(insights_dict: dict) -> dict:
    """Just the fields the model may change — used for convergence
    comparison."""
    return {
        "summary": insights_dict.get("summary"),
        "key_indicators": [
            (i.get("id"), i.get("comment"))
            for i in insights_dict.get("key_indicators", []) or []
        ],
        "strengths": list(insights_dict.get("strengths", [])),
        "concerns": list(insights_dict.get("concerns", [])),
    }


# --------------------------------------------------------------------- cache


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(settings, ticker, det: dict, context: dict, model: str) -> Path:
    """One JSON file per (ticker, insights-block hash, context hash, model)."""
    base_dir = Path(getattr(settings, "ai_cache_dir", None) or _DEFAULT_CACHE_DIR)
    key = _json(
        {
            "ticker": ticker or "",
            "insights": _short_hash(_json(det)),
            "context": _short_hash(_json(context)),
            "model": model,
        }
    )
    digest = _short_hash(key)
    return base_dir / f"{ticker or 'unknown'}_{digest}.json"


def _cache_read(path: Path):
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
        pass  # cache is best-effort; a write failure must never break the read


# --------------------------------------------------------------- entry point


def refine_insights(
    insights_block,
    *,
    ticker: str | None = None,
    context: dict | None = None,
    settings=None,
    transport=None,
) -> dict:
    """Refine the deterministic insights read with the Claude API, or pass it
    through.

    Returns a `CompanyInsights`-shaped dict plus an ``engine`` provenance
    key: ``"deterministic"`` (no key, or every AI round failed → identical
    body) or ``"ai"`` (≥1 valid refinement merged; carries an ``ai_notes``
    block with the model, iteration count and per-change rationale). Never
    raises on the no-key path — the dossier always gets an insights block.

    `insights_block` may be a `CompanyInsights` or an already-serialised
    dict (as built by `insights.build_insights`). `context` is a compact
    dict of decision-relevant extras (prescore, ttm, net_cash, pe_history,
    forum expectations, forecast_consensus, thesis entry_quality, ...) so the
    rewrite can weigh the whole picture — every number in it is added to the
    fabrication-guard's allowed set. `transport`/`settings` are injectable
    for testing.
    """
    settings = _resolve_settings(settings)
    det = _as_dict(insights_block)
    context = context or {}

    # No key → deterministic pass-through (exactly the WP body + marker).
    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        return {**det, "engine": "deterministic"}

    model = getattr(settings, "anthropic_model", None) or "claude-sonnet-4-6"
    max_iterations = int(getattr(settings, "anthropic_max_iterations", 2) or 2)
    cache_enabled = bool(getattr(settings, "ai_cache_enabled", True))

    # Cache: a hit skips the transport entirely (cost control).
    cache_file = _cache_path(settings, ticker, det, context, model)
    if cache_enabled:
        cached = _cache_read(cache_file)
        if cached is not None:
            return cached

    transport = transport or thesis_ai.default_transport(settings)
    allowed = collect_deterministic_numbers(det) | collect_context_numbers(context)

    current = det
    applied = 0  # count of valid, changed refinements actually merged
    notes: dict | None = None

    for _ in range(max_iterations):
        prompt = _build_prompt(det, context, current)
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = transport(messages, model)
        except Exception:  # noqa: BLE001 — any transport error → fall back
            break
        parsed = thesis_ai.parse_response(raw)
        if parsed is None:  # malformed → fall back to last valid
            break
        merged = _validate_and_merge(parsed, det)
        if merged is None:  # schema failure → fall back
            break
        if collect_prose_numbers(merged) - allowed:  # fabrication guard
            break
        if _refinable(merged) == _refinable(current):
            # A round that changed nothing → converged, stop early.
            break
        current = merged
        applied += 1
        notes = {"changes": _sanitize_notes(parsed.get("changes"))}

    if applied == 0:
        # Nothing valid merged (all rounds failed or immediate convergence to
        # the deterministic read) → honest deterministic marker, no ai_notes.
        return {**det, "engine": "deterministic"}

    result = {
        **current,
        "engine": "ai",
        "ai_notes": {"model": model, "iterations": applied, **(notes or {})},
    }
    # Defensive belt-and-suspenders: the merged read must still be clean.
    if collect_prose_numbers(result) - allowed:
        return {**det, "engine": "deterministic"}

    if cache_enabled:
        _cache_write(cache_file, result)
    return result
