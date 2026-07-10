"""Optional iterative Claude-API refiner for the investment-thesis read
(stage TH / WP2b — docs/plan-stage-thesis.md §"WP2b").

What this is
-----------
`build_thesis` (services/thesis.py) produces a *deterministic* entry-point read.
This module can take that read and iterate a bounded number of rounds with the
Claude API to sharpen it — reworded pros/cons, a re-weighed entry verdict,
case-similarity notes — while staying inside two hard guard-rails:

  * **Deterministic-first.** With no API key (the sandbox default) the refiner
    returns the deterministic read verbatim, marked ``engine: "deterministic"``.
    It never raises on the no-key path — the caller always gets a thesis.
  * **No fabricated numbers.** The AI path is held to the *same* fabrication
    guard as ``test_thesis.py``: any number the model emits that is not already
    present in the supplied inputs makes the whole round invalid, and the
    refiner falls back to the last valid read (or the deterministic one).

Design notes (for a C# dev):
  * Think of `refine_thesis` as a decorator/strategy layered over the pure
    `build_thesis`, with an **injected `transport`** (a delegate
    ``Func<messages, model, dict>``) so the network call is swappable — the
    tests inject a scripted stub, production injects a real HTTP client. Same
    idea as passing an ``HttpClient``/``IChatClient`` into a service instead of
    newing one up inside it.
  * **No PyPI at import time.** The Anthropic SDK and pydantic `Settings` are
    imported lazily *inside* functions, so the module (and its tests) load under
    a bare system Python with only the stdlib + our pure `thesis`/`strategies`
    layers. Settings are injectable for the same reason.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.services import thesis
from app.services.strategies import base, cases

# --- generic constants (not strategy data) ----------------------------------

# Entry-quality codes the engine may emit; the AI may re-pick among these but
# cannot invent a new verdict (schema guard).
_VALID_CODES = frozenset(
    {thesis.ATTRACTIVE, thesis.NEUTRAL, thesis.WEAK, thesis.INSUFFICIENT}
)

# The thesis fields the model is allowed to refine. `disclaimer` and `strategy`
# are re-imposed by us on every round (never taken from the model), so they are
# deliberately absent here. Convergence = these fields stop changing.
_REFINABLE_KEYS = (
    "entry_quality",
    "pros",
    "cons",
    "verify_next",
    "thesis_read",
    "valuation_basis",
)

# Where cached refinements live (gitignored). `parents[2]` == the backend/ root.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "thesis_ai"

# Anthropic Messages API wiring — only used by the *default* transport, which is
# never exercised in-session (no egress). No secret literal here.
_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 2000

# Same number grammar the deterministic fabrication guard uses (test_thesis.py):
# an optional sign, digits, optional decimal comma/period.
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


# ------------------------------------------------------------- number helpers
# These are shared verbatim with the tests so the AI path is guarded by exactly
# the same rule as the deterministic engine (no divergence).


def _numbers(text: str) -> set[float]:
    """Every numeric token in `text`, normalised (Polish comma → dot, rounded)
    so "9,5" and "9.5" compare equal."""
    return {round(float(tok.replace(",", ".")), 4) for tok in _NUM.findall(text)}


def collect_input_numbers(inputs: thesis.ThesisInputs) -> set[float]:
    """Every number the engine is *allowed* to quote — the union of numbers in
    the insights (name/value/comment/brief), the missing-data notes, and the
    scalar dossier pieces. Mirrors `_input_numbers` in test_thesis.py."""
    company = inputs.insights
    parts = [
        str(company.coverage),
        str(company.data_notes),
        company.summary,
        company.size_label or "",
    ]
    for ins in company.key_indicators:
        parts += [ins.name, ins.value, ins.comment, ins.brief or ""]
    for miss in company.missing:
        parts += [miss.name, miss.why]
    parts += [
        str(inputs.ttm),
        str(inputs.pe_history),
        str(inputs.net_cash),
        str(inputs.latest_forecast),
        str(inputs.prescore),
    ]
    nums: set[float] = set()
    for part in parts:
        nums |= _numbers(part)
    return nums


def collect_read_numbers(thesis_dict: dict) -> set[float]:
    """Every number the read *shows the user* — prose only. Weights are metadata
    (a claim about the strategy, not the company), so they are excluded, exactly
    like `_output_numbers` in test_thesis.py."""
    eq = thesis_dict.get("entry_quality") or {}
    parts = [
        eq.get("label", ""),
        eq.get("rationale", ""),
        thesis_dict.get("thesis_read", ""),
        thesis_dict.get("valuation_basis", ""),
        thesis_dict.get("disclaimer", ""),
    ]
    for factor in (thesis_dict.get("pros") or []) + (thesis_dict.get("cons") or []):
        parts.append(factor.get("text", ""))
    for item in thesis_dict.get("verify_next") or []:
        parts += [item.get("text", ""), item.get("why", "")]
    nums: set[float] = set()
    for part in parts:
        nums |= _numbers(part)
    return nums


# --------------------------------------------------------------- settings/dep


def _resolve_settings(settings):
    """Return the injected settings, or lazily load the pydantic `Settings`.

    The import is deferred so this module loads without pydantic-settings in the
    sandbox; tests always inject a lightweight stub, so config.py is never
    imported in-session (asserted by a test)."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


def _as_dict(deterministic_thesis) -> dict:
    """Accept either an `InvestmentThesis` or an already-serialised dict."""
    if hasattr(deterministic_thesis, "to_dict"):
        return deterministic_thesis.to_dict()
    if isinstance(deterministic_thesis, dict):
        return dict(deterministic_thesis)
    raise TypeError("deterministic_thesis must be an InvestmentThesis or dict")


# ------------------------------------------------------------- serialization
# The model receives the *full* picture each round: the dossier inputs, the
# active strategy rules, the worked-case comparison corpus, and the current read.


def _serialize_inputs(inputs: thesis.ThesisInputs) -> dict:
    company = inputs.insights
    return {
        "company": {
            "size_code": company.size_code,
            "size_label": company.size_label,
            "sector_group": company.sector_group,
            "sector_group_label": company.sector_group_label,
            "sector": company.sector,
            "coverage": company.coverage,
            "data_notes": company.data_notes,
            "summary": company.summary,
        },
        "key_indicators": [
            {
                "id": ins.id,
                "name": ins.name,
                "value": ins.value,
                "verdict": ins.verdict,
                "importance": ins.importance,
                "comment": ins.comment,
                "brief": ins.brief,
            }
            for ins in company.key_indicators
        ],
        "missing": [
            {"id": m.id, "name": m.name, "why": m.why} for m in company.missing
        ],
        "ttm": inputs.ttm,
        "pe_history": inputs.pe_history,
        "net_cash": inputs.net_cash,
        "latest_forecast": inputs.latest_forecast,
        "prescore": inputs.prescore,
    }


def _serialize_profile(profile: base.StrategyProfile) -> dict:
    rule = profile.entry_rule
    return {
        "id": profile.id,
        "label": profile.label,
        "spec_ref": profile.spec_ref,
        "criteria": [
            {
                "id": c.id,
                "principle": c.principle,
                "weight": c.weight,
                "direction": c.direction,
                "applies_to_sizes": sorted(c.applies_to_sizes)
                if c.applies_to_sizes
                else None,
                "applies_to_sectors": sorted(c.applies_to_sectors)
                if c.applies_to_sectors
                else None,
            }
            for c in profile.criteria
        ],
        "entry_rule": {
            "valuation": sorted(rule.valuation),
            "growth": sorted(rule.growth),
            "veto": sorted(rule.veto),
            "min_key_indicators": rule.min_key_indicators,
            "weak_bad_count": rule.weak_bad_count,
            "high_importance_level": rule.high_importance_level,
            "sweet_spot_sizes": sorted(rule.sweet_spot_sizes),
            "penalised_sizes": sorted(rule.penalised_sizes),
        },
        "verify_gaps": [
            {"id": g.id, "text": g.text, "why": g.why} for g in profile.verify_gaps
        ],
        "size_weight": profile.size_weight,
        "size_principle": profile.size_principle,
    }


def _serialize_corpus(corpus) -> list[dict]:
    """The `WorkedCase` comparison set. Empty until WP4 populates
    `cases.CORPUS`; serialized here so the refiner can compare the live stock
    against documented successes."""
    out: list[dict] = []
    for case in corpus or ():
        out.append(
            {
                "ticker": case.ticker,
                "as_of": case.as_of,
                "expected_read": case.expected_read,
                "citation": case.citation,
                "gaps": case.gaps,
                "sources": case.sources,
                "inputs": _serialize_inputs(case.inputs),
            }
        )
    return out


# ------------------------------------------------------------------- prompt

_INSTRUCTIONS = (
    "You refine a rule-based investment-thesis read for a Warsaw-listed (GPW) "
    "stock, in the spirit of Pawel Malik's strategy plus general fundamental "
    "analysis. You are given: the active strategy profile (criteria, weights, "
    "applicability, entry rule), the computed dossier inputs, a corpus of "
    "worked cases to compare against, and the current deterministic thesis.\n\n"
    "Return ONLY a single JSON object (no markdown, no prose outside it) with "
    "exactly these keys:\n"
    '  "entry_quality": {"code": one of '
    '["attractive","neutral","weak","insufficient_data"], "rationale": string},\n'
    '  "pros": [{"id": string, "text": string}],   // reorder/reword only; ids '
    "MUST come from the current thesis pros/cons\n"
    '  "cons": [{"id": string, "text": string}],   // same id rule\n'
    '  "verify_next": [{"id": string, "text": string, "why": string}],\n'
    '  "thesis_read": string,        // Polish paragraph weighing pros vs cons\n'
    '  "valuation_basis": string,    // Polish, forward vs trailing C/Z\n'
    '  "changes": [{"field": string, "rationale": string}],       // what you '
    "changed and why\n"
    '  "case_similarity": [{"ticker": string, "note": string}]    // vs the '
    "worked cases\n\n"
    "HARD RULES:\n"
    "1. NEVER introduce a number (percentage, ratio, PLN amount, C/Z, year, "
    "count) that is not already present in the dossier inputs. Quote figures "
    "verbatim from the inputs. Any invented number invalidates your whole "
    "answer.\n"
    "2. Keep every pro/con id from the current thesis; you may drop, reorder or "
    "reword them, but do not invent new ids.\n"
    "3. Domain language stays Polish. This is an ENTRANCE to human analysis, "
    "never a buy/sell signal — keep that framing.\n"
    "4. Do not add a disclaimer; it is appended automatically.\n"
    "5. If you cannot improve the current read, return it unchanged (that is a "
    "valid, converged answer)."
)


def _build_prompt(
    serial_inputs: dict, serial_profile: dict, serial_corpus: list, current: dict
) -> str:
    payload = {
        "strategy_profile": serial_profile,
        "dossier_inputs": serial_inputs,
        "worked_cases": serial_corpus,
        "current_thesis": {k: current.get(k) for k in _REFINABLE_KEYS},
    }
    return _INSTRUCTIONS + "\n\nDATA:\n" + json.dumps(
        payload, ensure_ascii=False, default=str
    )


# ------------------------------------------------------------------ transport


def default_transport(settings):
    """Build the production transport: a callable ``(messages, model) -> dict``
    returning the raw Anthropic Messages-API response shape.

    Resolution order (both lazy so import stays PyPI-free):
      1. the official `anthropic` SDK if it is importable;
      2. a stdlib `urllib` POST with the correct headers.

    Never exercised in-session — the tests inject a stub instead."""

    api_key = getattr(settings, "anthropic_api_key", None)

    def _call(messages: list[dict], model: str) -> dict:
        try:
            import anthropic  # lazy: optional dependency

            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model, max_tokens=_MAX_TOKENS, messages=messages
            )
            # Normalise the SDK objects to the plain API dict shape our parser
            # expects, so both transports look identical downstream.
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
    prose. Returns the parsed object or None (malformed)."""
    trimmed = text.strip()
    if trimmed.startswith("```"):
        # ```json ... ``` or ``` ... ```
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


def _parse_response(raw) -> dict | None:
    """Pull the model's JSON out of the Anthropic response envelope."""
    if not isinstance(raw, dict):
        return None
    content = raw.get("content")
    text = ""
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text += block["text"]
    elif isinstance(content, str):
        text = content
    if not text.strip():
        return None
    return _extract_json(text)


# --- public aliases (stage SC / WP3) -----------------------------------------
# `scenarios_ai.py` reuses these helpers verbatim (the plan's "reuse, don't
# duplicate"); exposing a one-line public name avoids reaching into the private
# underscore functions. No behaviour change — `thesis_ai`'s own tests still pass.
numbers = _numbers
parse_response = _parse_response


# -------------------------------------------------------------- validate/merge


def _refinable(thesis_dict: dict) -> dict:
    """Just the fields the model may change — used for convergence comparison."""
    return {k: thesis_dict.get(k) for k in _REFINABLE_KEYS}


def _sanitize_notes(raw) -> list:
    """Coerce the model's `changes`/`case_similarity` to JSON-safe, capped data.
    These are provenance shown in `ai_notes`, NOT company claims, so they sit
    outside the number-fabrication guard that governs the read itself."""
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


def _validate_and_merge(parsed: dict, base_dict: dict, allowed: set[float]):
    """Enforce the schema + fabrication guard and merge the refinement onto the
    deterministic base. Returns the merged thesis dict, or None on ANY failure
    (which makes the caller fall back to the last valid read)."""
    if not isinstance(parsed, dict):
        return None

    # entry_quality: model may re-pick the code, but only from the known set;
    # the label is regenerated from the code (never taken from the model) so
    # code and label can never drift and the label carries no stray numbers.
    eq = parsed.get("entry_quality")
    if not isinstance(eq, dict):
        return None
    code = eq.get("code")
    rationale = eq.get("rationale")
    if code not in _VALID_CODES or not isinstance(rationale, str):
        return None

    # pros/cons: weight + principle are strategy data — we keep the
    # deterministic values and take only the model's (reworded) text, and the
    # id MUST be one the engine already produced (no invented factors).
    meta = {
        f["id"]: (f["weight"], f["principle"])
        for f in base_dict.get("pros", []) + base_dict.get("cons", [])
    }

    def _factors(key: str):
        raw = parsed.get(key)
        if not isinstance(raw, list):
            return None
        built = []
        for f in raw:
            if not isinstance(f, dict):
                return None
            fid, text = f.get("id"), f.get("text")
            if fid not in meta or not isinstance(text, str):
                return None
            weight, principle = meta[fid]
            built.append(
                {"id": fid, "text": text, "weight": weight, "principle": principle}
            )
        return built

    pros = _factors("pros")
    cons = _factors("cons")
    if pros is None or cons is None:
        return None

    verify_raw = parsed.get("verify_next")
    if not isinstance(verify_raw, list):
        return None
    verify = []
    for v in verify_raw:
        if not isinstance(v, dict):
            return None
        vid, vtext, vwhy = v.get("id"), v.get("text"), v.get("why")
        if not all(isinstance(x, str) for x in (vid, vtext, vwhy)):
            return None
        verify.append({"id": vid, "text": vtext, "why": vwhy})

    thesis_read = parsed.get("thesis_read")
    valuation_basis = parsed.get("valuation_basis")
    if not isinstance(thesis_read, str) or not isinstance(valuation_basis, str):
        return None

    # Re-impose the fixed framing: canonical label, disclaimer, and a thesis_read
    # that ends with the disclaimer (not-advice framing survives every round).
    read = thesis_read.rstrip()
    if not read.endswith(thesis.DISCLAIMER):
        read = (read + " " + thesis.DISCLAIMER).strip()

    merged = {
        "entry_quality": {
            "code": code,
            "label": thesis._ENTRY_LABELS[code],
            "rationale": rationale,
        },
        "pros": pros,
        "cons": cons,
        "verify_next": verify,
        "thesis_read": read,
        "disclaimer": thesis.DISCLAIMER,
        "valuation_basis": valuation_basis,
        "strategy": base_dict.get("strategy"),
    }

    # Fabrication guard (the crux): every number the read shows must exist in the
    # inputs. One stray figure → reject the whole round.
    if collect_read_numbers(merged) - allowed:
        return None
    return merged


# --------------------------------------------------------------------- cache


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(settings, ticker, inputs, profile, model) -> Path:
    """One JSON file per (ticker, input-hash, model, profile id+version). The
    profile "version" is a hash of its serialized rules, so any weight/threshold
    change busts the cache without needing an explicit version field."""
    base_dir = Path(getattr(settings, "ai_cache_dir", None) or _DEFAULT_CACHE_DIR)
    key = _json(
        {
            "ticker": ticker or "",
            "input": _short_hash(_json(_serialize_inputs(inputs))),
            "model": model,
            "profile": f"{profile.id}:{_short_hash(_json(_serialize_profile(profile)))}",
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


def refine_thesis(
    inputs: thesis.ThesisInputs,
    profile: base.StrategyProfile,
    deterministic_thesis=None,
    *,
    ticker: str | None = None,
    corpus=None,
    transport=None,
    settings=None,
) -> dict:
    """Refine the deterministic thesis with the Claude API, or pass it through.

    Returns an `InvestmentThesis`-shaped dict plus an ``engine`` provenance key:
    ``"deterministic"`` (no key, or every AI round failed → identical body) or
    ``"ai"`` (at least one valid refinement merged; carries an ``ai_notes``
    block with the model, iteration count, per-change rationale and
    case-similarity notes).

    `deterministic_thesis` may be passed in (as built by `build_thesis`) to
    avoid recomputing it; when omitted it is built here. `transport`/`settings`
    are injectable for testing; `corpus` defaults to `cases.CORPUS` (empty until
    WP4). Never raises on the no-key path.
    """
    settings = _resolve_settings(settings)
    det = (
        _as_dict(deterministic_thesis)
        if deterministic_thesis is not None
        else thesis.build_thesis(inputs, profile).to_dict()
    )

    # No key → deterministic pass-through (exactly the WP2 body + marker).
    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        return {**det, "engine": "deterministic"}

    model = getattr(settings, "anthropic_model", None) or "claude-sonnet-4-6"
    max_iterations = int(getattr(settings, "anthropic_max_iterations", 2) or 2)
    cache_enabled = bool(getattr(settings, "ai_cache_enabled", True))
    if corpus is None:
        # WP4 populates cases.CORPUS; until then the comparison set is empty.
        corpus = getattr(cases, "CORPUS", ())

    # Cache: a hit skips the transport entirely (cost control).
    cache_file = _cache_path(settings, ticker, inputs, profile, model)
    if cache_enabled:
        cached = _cache_read(cache_file)
        if cached is not None:
            return cached

    transport = transport or default_transport(settings)
    allowed = collect_input_numbers(inputs) | collect_read_numbers(det)
    serial_inputs = _serialize_inputs(inputs)
    serial_profile = _serialize_profile(profile)
    serial_corpus = _serialize_corpus(corpus)

    current = det
    applied = 0  # count of valid, changed refinements actually merged
    notes: dict | None = None

    for _ in range(max_iterations):
        prompt = _build_prompt(serial_inputs, serial_profile, serial_corpus, current)
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = transport(messages, model)
        except Exception:  # noqa: BLE001 — any transport error → fall back
            break
        parsed = _parse_response(raw)
        if parsed is None:  # malformed → fall back to last valid
            break
        merged = _validate_and_merge(parsed, det, allowed)
        if merged is None:  # schema / fabrication failure → fall back
            break
        if _refinable(merged) == _refinable(current):
            # A round that changed nothing → converged, stop early.
            break
        current = merged
        applied += 1
        notes = {
            "changes": _sanitize_notes(parsed.get("changes")),
            "case_similarity": _sanitize_notes(parsed.get("case_similarity")),
        }

    if applied == 0:
        # Nothing valid merged (all rounds failed or immediate convergence to the
        # deterministic read) → honest deterministic marker, no ai_notes.
        return {**det, "engine": "deterministic"}

    result = {
        **current,
        "engine": "ai",
        "ai_notes": {"model": model, "iterations": applied, **(notes or {})},
    }
    # Defensive belt-and-suspenders: the merged read must still be clean.
    if collect_read_numbers(result) - allowed:
        return {**det, "engine": "deterministic"}

    if cache_enabled:
        _cache_write(cache_file, result)
    return result
