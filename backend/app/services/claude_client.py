"""Claude API transport for the Phase-5 AI *analysis* product (PLAN §8, P5.4).

What this is
-----------
`services/prompts.py` assembles the skill system prompt + the dossier/forum
user turn (P5.5). This module makes the actual Claude call and turns the raw
response into a typed `AnalysisResult` — the parsed verdict (the schema in
PLAN §8 / `skill/SKILL.md`'s "Output contract") plus token counts for
logging/cost tracking.

Relationship to `thesis_ai.py` / `scenarios_ai.py` / `valuation_ai.py`
-----------------------------------------------------------------
Those modules are *deterministic-first refiners*: no key ⇒ silent pass-through
of a deterministic read, never raising. This module is different — the
Phase-5 "Analiza AI" run has **no deterministic fallback** to fall back to (a
verdict IS the product). So the no-key path here raises `AnalysisUnavailable`
instead of fabricating a verdict; the API layer (`app/api/analyses.py`) maps
its `.reason` ("no_key" / "transport" / "parse") to a distinct HTTP status +
Polish message rather than a single catch-all 503.

The transport also differs from `thesis_ai.default_transport`: the verdict
must come back as **forced tool use** (a single tool call, not free text), so
this module builds its own `tools`/`tool_choice` payload rather than reusing
`thesis_ai`'s (which never passes tools). Design notes (for a C# dev): think
of `default_transport(settings)` as constructing a small `HttpClient`-like
delegate — `Func<messages, model, tools, tool_choice, dict>` — that the tests
substitute with a scripted stub, exactly the same injection shape as
`thesis_ai`.

No PyPI at import time
-----------------------
The Anthropic SDK and pydantic `Settings` are imported lazily *inside*
functions only, so this module (and its tests) load under a bare system
Python with just the stdlib — verified by
`test_analysis_ai.py::test_module_imports_without_pypi`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

# --- Anthropic Messages API wiring (only used by `default_transport`, never
# exercised in-session — no egress in the sandbox). No secret literal here.
_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 8000

# Bounded retry: a transient transport error gets a couple of extra tries
# before we give up and tell the caller the run failed (never fabricate).
_MAX_ATTEMPTS = 3

# Where cached verdicts live (gitignored). `parents[2]` == the backend/ root
# (same convention as thesis_ai._DEFAULT_CACHE_DIR).
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "analysis"

_TOOL_NAME = "zapisz_analize"

# The verdict schema — single source of truth, mirrors PLAN §8 / SKILL.md's
# "Output contract" EXACTLY. Forced via tool_choice so the model cannot answer
# in free text.
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "thesis": {
            "type": "string",
            "description": (
                'Teza inwestycyjna po polsku, albo dosłownie '
                '"Brak wyraźnej tezy inwestycyjnej" gdy jej brak.'
            ),
        },
        "catalysts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                    "horizon": {"type": "string"},
                    "priced_in": {
                        "type": "string",
                        "enum": ["tak", "nie", "częściowo", "nieznane"],
                    },
                },
                "required": ["type", "description", "horizon", "priced_in"],
            },
        },
        "checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["spełnia", "nie spełnia", "nieznane"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["item", "verdict", "evidence"],
            },
        },
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "one_off_risk": {"type": "string"},
        "forum_insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "post_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["claim", "confidence", "post_ids"],
            },
        },
        "alignment_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "potential": {
            "type": "object",
            "properties": {
                "upside": {"type": "string"},
                "downside": {"type": "string"},
            },
            "required": ["upside", "downside"],
        },
        "scenarios": {
            "type": "array",
            "minItems": 3,
            "description": (
                "Qualitative AI review of the prepared deterministic scenario set, "
                "not a replacement for the calculator."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["negative", "base", "positive", "event"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "key_drivers": {
                        "type": "array",
                        "minItems": 2,
                        "items": {"type": "string"},
                    },
                    "watch_items": {
                        "type": "array",
                        "minItems": 2,
                        "items": {"type": "string"},
                    },
                    "probability": {
                        "type": "string",
                        "description": "Qualitative probability, not an invented numeric percentage.",
                    },
                },
                "required": [
                    "kind",
                    "title",
                    "description",
                    "key_drivers",
                    "watch_items",
                    "probability",
                ],
            },
        },
        "verify_next": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["id", "text", "why"],
            },
        },
        "summary_pl": {"type": "string", "minLength": 80},
    },
    "required": [
        "thesis",
        "catalysts",
        "checklist",
        "red_flags",
        "one_off_risk",
        "forum_insights",
        "alignment_score",
        "potential",
        "scenarios",
        "verify_next",
        "summary_pl",
    ],
}

_TOOLS = [
    {
        "name": _TOOL_NAME,
        "description": (
            "Zapisz strukturalny werdykt analizy inwestycyjnej zgodnie z "
            "przyjętym schematem (PLAN §8 / skill/SKILL.md 'Output contract')."
        ),
        "input_schema": _VERDICT_SCHEMA,
    }
]
_TOOL_CHOICE = {"type": "tool", "name": _TOOL_NAME}

# Same tolerant JSON extractor shape as thesis_ai._extract_json, duplicated
# (not imported) so this module stays free of the thesis/strategies import
# chain — it only ever needs to parse a fallback text blob.
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_TOOL_LEAK_MARKERS = ("<parameter", "</parameter", "</thesis>", "<tool_use", "</tool_use>")


class AnalysisUnavailable(Exception):
    """Raised when no verdict could be produced — no API key configured, every
    transport attempt failed, or the response carried no usable tool_use/JSON.

    `reason` distinguishes the three causes so the caller (app/api/analyses.py)
    can map each to its own HTTP status + Polish message instead of a single
    catch-all 503 that blamed a missing key even when the key was present and
    something else failed:
      * "no_key"    — ANTHROPIC_API_KEY not configured.
      * "transport" — every transport attempt raised.
      * "parse"     — the response carried no usable tool_use/JSON.

    `detail` is an optional short, secret-free diagnostic string (e.g. the
    last transport exception's text, truncated) the API layer may surface to
    the caller. Never caught to fabricate a verdict."""

    def __init__(self, message: str, *, reason: str, detail: str | None = None):
        super().__init__(message)
        self.reason = reason
        self.detail = detail


@dataclass
class AnalysisResult:
    """The parsed verdict + provenance the endpoint persists into `Analysis`."""

    verdict: dict
    input_tokens: int | None
    output_tokens: int | None
    model: str
    engine: str = "ai"


# --------------------------------------------------------------- settings/dep


def _resolve_settings(settings):
    """Injected settings, or the lazily-loaded pydantic `Settings` (deferred so
    this module imports without pydantic-settings in the sandbox)."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


# ------------------------------------------------------------------ transport


def default_transport(settings):
    """Build the production transport: a callable
    ``(messages, model, tools, tool_choice) -> dict`` returning the raw
    Anthropic Messages-API response shape (``{"content": [...], "usage": {...}}``).

    Resolution order (both lazy so import stays PyPI-free):
      1. the official `anthropic` SDK if it is importable;
      2. a stdlib `urllib` POST with the correct headers.

    `messages` may include a ``{"role": "system", ...}`` entry — pulled out and
    sent as the API's dedicated ``system`` field (the Anthropic Messages API,
    unlike some others, does not accept "system" inside the messages array).
    This keeps the injected-transport signature simple for tests while still
    being correct against the real API. Never exercised in-session — the
    tests inject a stub instead."""

    api_key = getattr(settings, "anthropic_api_key", None)

    def _call(messages: list[dict], model: str, tools: list[dict], tool_choice: dict) -> dict:
        system_text = "\n\n".join(
            m["content"] for m in messages if m.get("role") == "system"
        )
        api_messages = [m for m in messages if m.get("role") != "system"]

        try:
            import anthropic  # lazy: optional dependency

            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                system=system_text or None,
                messages=api_messages,
                tools=tools,
                tool_choice=tool_choice,
            )
            content = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    content.append(
                        {
                            "type": "tool_use",
                            "name": getattr(block, "name", None),
                            "input": getattr(block, "input", None),
                        }
                    )
                else:
                    content.append({"type": "text", "text": getattr(block, "text", "")})
            usage = getattr(resp, "usage", None)
            return {
                "content": content,
                "usage": {
                    "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
                },
            }
        except ImportError:
            pass  # fall through to stdlib

        import urllib.request  # lazy: stdlib, but keep import local

        body: dict = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "messages": api_messages,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        if system_text:
            body["system"] = system_text
        request = urllib.request.Request(
            _API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": api_key or "",
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            method="POST",
        )
        from app.services.anthropic_http import urlopen_with_certifi

        with urlopen_with_certifi(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    return _call


# ----------------------------------------------------------- response parsing


def _extract_json_fallback(text: str):
    """Tolerant JSON extraction from a plain-text answer — only used when a
    (stub, test-only) transport returns text instead of a tool_use block."""
    trimmed = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(trimmed)
    except ValueError:
        start, end = trimmed.find("{"), trimmed.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(trimmed[start : end + 1])
            except ValueError:
                return None
        return None


def _extract_verdict(raw) -> dict | None:
    """Pull the verdict out of the Anthropic response envelope: prefer the
    forced tool_use block's already-parsed `input`; fall back to scanning any
    text blocks for embedded JSON (keeps hand-written stub transports simple
    in tests)."""
    if not isinstance(raw, dict):
        return None
    content = raw.get("content")
    if not isinstance(content, list):
        return None

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            payload = block.get("input")
            if isinstance(payload, dict):
                return payload

    text = "".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    )
    if not text.strip():
        return None
    parsed = _extract_json_fallback(text)
    return parsed if isinstance(parsed, dict) else None


def _extract_usage(raw) -> tuple[int | None, int | None]:
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if not isinstance(usage, dict):
        return None, None
    return usage.get("input_tokens"), usage.get("output_tokens")


def _verdict_validation_errors(verdict: dict) -> list[str]:
    """Guard against formally-valid but decision-useless tool payloads."""
    errors: list[str] = []
    if not str(verdict.get("summary_pl") or "").strip():
        errors.append("summary_pl is empty")
    for field in ("thesis", "one_off_risk", "summary_pl"):
        text = str(verdict.get(field) or "").lower()
        if any(marker in text for marker in _TOOL_LEAK_MARKERS):
            errors.append(f"{field} contains tool/XML markup")

    scenarios = verdict.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < 3:
        errors.append("scenarios must contain at least negative/base/positive cases")
    else:
        kinds = {s.get("kind") for s in scenarios if isinstance(s, dict)}
        missing = {"negative", "base", "positive"} - kinds
        if missing:
            errors.append(f"scenarios missing kinds: {', '.join(sorted(missing))}")
        for idx, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                errors.append(f"scenario {idx} is not an object")
                continue
            if not str(scenario.get("description") or "").strip():
                errors.append(f"scenario {idx} has empty description")
            if len(scenario.get("key_drivers") or []) < 2:
                errors.append(f"scenario {idx} needs at least two key_drivers")
            if len(scenario.get("watch_items") or []) < 2:
                errors.append(f"scenario {idx} needs at least two watch_items")
    return errors


def _repair_messages(messages: list[dict], errors: list[str]) -> list[dict]:
    correction = (
        "\n\nKOREKTA TECHNICZNA: poprzednia odpowiedź naruszyła kontrakt JSON: "
        + "; ".join(errors)
        + ". Zwróć ponownie wyłącznie tool_use `zapisz_analize`. "
        "Pole `scenarios` musi zawierać co najmniej scenariusz negative, base "
        "i positive z opisem bazującym na dossier, BiznesRadar expectations "
        "oraz forum_intelligence. `summary_pl` nie może być puste. "
        "Nie wolno umieszczać znaczników XML ani tekstu serializacji "
        "tool-call w polach tekstowych."
    )
    repaired: list[dict] = []
    for message in messages:
        if message.get("role") == "user":
            repaired.append({**message, "content": str(message.get("content") or "") + correction})
        else:
            repaired.append(dict(message))
    return repaired


# --------------------------------------------------------------------- cache


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(settings, ticker, prompt_bundle: dict, model: str) -> Path:
    """One JSON file per (ticker, prompt-hash, model) — a hit skips the
    transport entirely (cost control), same shape as `thesis_ai._cache_path`."""
    base_dir = Path(getattr(settings, "ai_cache_dir", None) or _DEFAULT_CACHE_DIR)
    prompt_hash = _short_hash(
        _json(
            {
                "system": prompt_bundle.get("system", ""),
                "user": prompt_bundle.get("user", ""),
            }
        )
    )
    digest = _short_hash(_json({"ticker": ticker or "", "model": model, "prompt": prompt_hash}))
    return base_dir / f"{ticker or 'unknown'}_{digest}.json"


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


# --------------------------------------------------------------- entry point


def run_analysis(
    prompt_bundle: dict,
    *,
    settings=None,
    transport=None,
    ticker: str | None = None,
) -> AnalysisResult:
    """Run one Claude verdict pass (P5.4).

    `prompt_bundle` is the `{"system", "user", "snapshot"}` dict from
    `services/prompts.build_analysis_prompt`. `transport`/`settings` are
    injectable for testing (a `StubTransport` replaces the network call
    exactly like `thesis_ai`).

    Raises `AnalysisUnavailable` — never fabricates a verdict — when:
      * no `anthropic_api_key` is configured;
      * every transport attempt raised;
      * the response carried no usable tool_use block / parseable JSON.
    """
    settings = _resolve_settings(settings)

    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        raise AnalysisUnavailable(
            "ANTHROPIC_API_KEY is not configured.", reason="no_key"
        )

    model = getattr(settings, "anthropic_model", None) or "claude-sonnet-4-6"
    cache_enabled = bool(getattr(settings, "ai_cache_enabled", True))

    cache_file = _cache_path(settings, ticker, prompt_bundle, model)
    if cache_enabled:
        cached = _cache_read(cache_file)
        if cached is not None:
            try:
                cached_result = AnalysisResult(**cached)
            except TypeError:
                cached_result = None
            if cached_result is not None and not _verdict_validation_errors(cached_result.verdict):
                return cached_result

    transport = transport or default_transport(settings)
    messages = [
        {"role": "system", "content": prompt_bundle.get("system", "")},
        {"role": "user", "content": prompt_bundle.get("user", "")},
    ]

    last_exc: Exception | None = None
    validation_errors: list[str] = []
    for _ in range(_MAX_ATTEMPTS):
        try:
            raw = transport(
                _repair_messages(messages, validation_errors) if validation_errors else messages,
                model,
                _TOOLS,
                _TOOL_CHOICE,
            )
        except Exception as exc:  # noqa: BLE001 — bounded retry, then give up
            last_exc = exc
            continue

        verdict = _extract_verdict(raw)
        if verdict is None:
            last_exc = AnalysisUnavailable(
                "Claude API response carried no usable verdict.", reason="parse"
            )
            validation_errors = ["missing tool_use/input verdict"]
            continue

        validation_errors = _verdict_validation_errors(verdict)
        if validation_errors:
            last_exc = AnalysisUnavailable(
                "Claude API verdict failed validation: " + "; ".join(validation_errors),
                reason="parse",
            )
            continue

        input_tokens, output_tokens = _extract_usage(raw)
        result = AnalysisResult(
            verdict=verdict,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            engine="ai",
        )

        if cache_enabled:
            _cache_write(cache_file, asdict(result))

        return result

    if validation_errors:
        raise AnalysisUnavailable(
            f"Claude API response failed validation after {_MAX_ATTEMPTS} attempts: {last_exc}",
            reason="parse",
            detail="; ".join(validation_errors)[:200],
        )
    detail = str(last_exc)[:200] if last_exc is not None else None
    raise AnalysisUnavailable(
        f"Claude API transport failed after {_MAX_ATTEMPTS} attempts: {last_exc}",
        reason="transport",
        detail=detail,
    )
