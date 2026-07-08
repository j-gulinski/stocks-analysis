"""Optional iterative Claude-API refiner for the scenario set (stage SC / WP3b —
docs/plan-stage-scenarios.md §"WP3b").

`scenarios.build_scenario_set` produces a *deterministic* trio (negative / base /
positive) off the company's own multiple history. This module can iterate a
bounded number of rounds with the Claude API to sharpen it — reworded
narratives, adjusted probabilities, and **company-specific event scenarios**
grounded in the dossier's `verify_next` gaps (catalyst, backlog, …) — while
staying inside the same two hard guard-rails as `thesis_ai.refine_thesis`:

  * **Deterministic-first.** With no API key (the sandbox default) it returns the
    deterministic set verbatim, marked ``engine: "deterministic"``. It never
    raises on the no-key path — the dossier always gets a scenario block.
  * **No fabricated numbers (widened allowed-set).** Every number the model
    quotes in prose must be a subset of
    ``input_numbers(inputs) ∪ corpus_numbers ∪ engine_scenario_numbers`` — the
    sourced inputs, the *cited* worked-case comparables, and the numbers the
    **deterministic** engine already computed (target prices, upsides,
    horizons, weighted EV). A stray figure rejects the whole round, falling back
    to the last valid set (else the deterministic one).

Coherence (Σ probability = 1) is **re-imposed by us**, never trusted from the
model: after each round every probability is renormalised (divide by total,
clamp to [0,1]), so an AI-added event scenario keeps the set coherent.

Design notes (for a C# dev): same shape as `thesis_ai` — `simulate_scenarios`
is a decorator over the pure `build_scenario_set` with an **injected
`transport`** delegate; the Anthropic SDK + pydantic `Settings` are imported
lazily *inside* functions (via `thesis_ai`), so the module loads under a bare
system Python with no PyPI. Think renormalisation ≈ normalising weights before a
weighted average.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.services import scenarios, thesis, thesis_ai
from app.services.strategies import base, cases

# Scenario kinds the model may emit. It may reword/adjust the deterministic
# negative/base/positive and ADD `event` scenarios — never invent a new kind.
_VALID_KINDS = frozenset({"negative", "base", "positive", "event"})

# Gitignored cache dir, separate from the thesis refiner's (plan §Non-goals).
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "scenarios_ai"


# ------------------------------------------------------------- settings/dep


def _resolve_settings(settings):
    """Injected settings, or the lazily-loaded pydantic `Settings` (deferred so
    this module imports without pydantic-settings in the sandbox)."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


def _as_dict(scenario_set) -> dict:
    """Accept either a `ScenarioSet` or an already-serialised dict."""
    if hasattr(scenario_set, "to_dict"):
        return scenario_set.to_dict()
    if isinstance(scenario_set, dict):
        return dict(scenario_set)
    raise TypeError("deterministic_set must be a ScenarioSet or dict")


# --------------------------------------------------------- number vocabulary


def collect_corpus_numbers(corpus) -> set[float]:
    """Numbers a scenario may legitimately CITE from the worked-case corpus —
    the reconstructed inputs plus the sourced text (citations, sources, gaps,
    expected read). Empty until WP4 enriches the corpus with real multiples /
    repricing durations; guarded here so those figures are allowed, not
    fabricated."""
    nums: set[float] = set()
    for case in corpus or ():
        case_inputs = getattr(case, "inputs", None)
        if case_inputs is not None:
            nums |= thesis_ai.collect_input_numbers(case_inputs)
        texts = [
            getattr(case, "ticker", "") or "",
            getattr(case, "as_of", "") or "",
            getattr(case, "citation", "") or "",
        ]
        texts += list(getattr(case, "gaps", None) or [])
        texts += list((getattr(case, "sources", None) or {}).values())
        texts += [str(v) for v in (getattr(case, "expected_read", None) or {}).values()]
        for text in texts:
            nums |= thesis_ai.numbers(str(text))
    return nums


# ------------------------------------------------------------- serialization


def _serialize_inputs(inputs: scenarios.ScenarioInputs) -> dict:
    ti = inputs.thesis_inputs
    company = ti.insights
    return {
        "company": {
            "size_code": company.size_code,
            "size_label": company.size_label,
            "sector_group": company.sector_group,
            "sector_group_label": company.sector_group_label,
            "sector": company.sector,
            "summary": company.summary,
        },
        # Data gaps the model may ground an EVENT scenario in (never invented).
        "open_gaps": [{"id": m.id, "name": m.name, "why": m.why} for m in company.missing],
        "drivers": inputs.to_dict(),
        "ttm": ti.ttm,
        "pe_history": ti.pe_history,
        "net_cash": ti.net_cash,
        "latest_forecast": ti.latest_forecast,
    }


def _serialize_profile(profile: base.StrategyProfile) -> dict:
    # The verify_gaps (catalyst, backlog, management, …) are the qualitative
    # hooks an event scenario is allowed to be built around.
    return {
        "id": profile.id,
        "label": profile.label,
        "verify_gaps": [
            {"id": g.id, "text": g.text, "why": g.why} for g in profile.verify_gaps
        ],
    }


def _serialize_corpus(corpus) -> list[dict]:
    out: list[dict] = []
    for case in corpus or ():
        out.append(
            {
                "ticker": case.ticker,
                "as_of": case.as_of,
                "citation": case.citation,
                "sources": case.sources,
                "gaps": case.gaps,
                "expected_read": case.expected_read,
            }
        )
    return out


# ------------------------------------------------------------------- prompt

_INSTRUCTIONS = (
    "You refine a rule-based, discrete set of valuation SCENARIOS for a "
    "Warsaw-listed (GPW) stock, in the spirit of Pawel Malik's strategy plus "
    "general fundamental analysis. You are given: the company context + open "
    "data gaps, the active strategy profile (with qualitative verify-gaps), a "
    "corpus of worked cases, and the current DETERMINISTIC scenario set "
    "(negative/base/positive reversion of the stock's OWN valuation multiple).\n\n"
    "Return ONLY a single JSON object (no markdown, no prose outside it) with "
    "exactly these keys:\n"
    '  "scenarios": [ {"id": string, "kind": one of '
    '["negative","base","positive","event"], "label": string, '
    '"probability": number 0..1, "narrative": string (Polish), '
    '"drivers": [string], "assumptions": [string]} ],\n'
    '  "changes": [{"field": string, "rationale": string}],\n'
    '  "case_similarity": [{"ticker": string, "note": string}]\n\n'
    "HARD RULES:\n"
    "1. Keep the three deterministic scenarios (ids negative/base/positive); you "
    "may reword their narrative/label/drivers/assumptions and adjust their "
    "probability, but do NOT change their computed target price / multiple / "
    "horizon.\n"
    "2. You MAY add company-specific `event` scenarios, but ONLY grounded in the "
    "given open gaps or the strategy verify-gaps (catalyst, backlog, …). An "
    "event scenario carries no fabricated target price.\n"
    "3. NEVER introduce a number (percentage, ratio, PLN amount, multiple, "
    "duration, count) that is not already present in the dossier inputs, the "
    "worked-case corpus, or the deterministic scenarios. Quote figures verbatim. "
    "Any invented number invalidates your whole answer.\n"
    "4. Probabilities are renormalised automatically to sum to 1 — provide "
    "relative weights; do not worry about exact normalisation.\n"
    "5. Domain language stays Polish. These are an ENTRANCE to analysis, never a "
    "buy/sell signal. Do not add a disclaimer; it is appended automatically.\n"
    "6. If you cannot improve the set, return it unchanged (a valid, converged "
    "answer)."
)


def _build_prompt(serial_inputs, serial_profile, serial_corpus, current) -> str:
    payload = {
        "strategy_profile": serial_profile,
        "scenario_inputs": serial_inputs,
        "worked_cases": serial_corpus,
        "current_scenarios": {
            "valuation_multiple": current.get("valuation_multiple"),
            "current_price": current.get("current_price"),
            "weighted_expected_price": current.get("weighted_expected_price"),
            "scenarios": current.get("scenarios"),
        },
    }
    return _INSTRUCTIONS + "\n\nDATA:\n" + json.dumps(
        payload, ensure_ascii=False, default=str
    )


# -------------------------------------------------------- validate / merge


def _str_or(value, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _prob_or(value, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return fallback


def _sanitize_str_list(value, fallback: list) -> list:
    if not isinstance(value, list):
        return list(fallback)
    out = [str(x) for x in value if isinstance(x, (str, int, float)) and str(x).strip()]
    return out or list(fallback)


def _sanitize_notes(raw) -> list:
    """Coerce `changes`/`case_similarity` to JSON-safe capped provenance (shown
    in `ai_notes`, NOT company claims — outside the number guard)."""
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


def _renormalize(scenario_list: list) -> list:
    """Re-impose Σ probability = 1 (divide by total, clamp to [0,1]). Our
    deterministic computation, so the renormalised values are allowed numbers."""
    total = sum(s["probability"] for s in scenario_list)
    if total <= 0:
        equal = round(1.0 / len(scenario_list), 4) if scenario_list else 0.0
        for s in scenario_list:
            s["probability"] = equal
        return scenario_list
    for s in scenario_list:
        s["probability"] = round(min(max(s["probability"] / total, 0.0), 1.0), 4)
    return scenario_list


def _merge_kept(det_scenario: dict, proposed: dict) -> dict:
    """Keep the deterministic STRUCTURED numbers (target price, multiple,
    horizon); take only the model's reworded prose + relative probability."""
    kept = dict(det_scenario)
    kept["narrative"] = _str_or(proposed.get("narrative"), kept["narrative"])
    kept["label"] = _str_or(proposed.get("label"), kept["label"])
    kept["drivers"] = _sanitize_str_list(proposed.get("drivers"), kept["drivers"])
    kept["assumptions"] = _sanitize_str_list(proposed.get("assumptions"), kept["assumptions"])
    kept["probability"] = _prob_or(proposed.get("probability"), kept["probability"])
    return kept


def _build_event(proposed: dict, det: dict) -> dict:
    """An AI-only event scenario: a qualitative catalyst, no fabricated price."""
    return {
        "id": _str_or(proposed.get("id"), "event"),
        "kind": "event",
        "label": _str_or(proposed.get("label"), "Scenariusz zdarzeniowy"),
        "probability": _prob_or(proposed.get("probability"), 0.0),
        "narrative": _str_or(proposed.get("narrative"), ""),
        "target_multiple": {
            "type": det.get("valuation_multiple"),
            "value": None,
            "basis_label": "scenariusz zdarzeniowy — bez wyceny mnożnikowej",
        },
        "target_price": None,
        "implied_upside_pct": None,
        "horizon": dict(scenarios.DEFAULT_HORIZON),
        "drivers": _sanitize_str_list(proposed.get("drivers"), []),
        "assumptions": _sanitize_str_list(proposed.get("assumptions"), []),
    }


def _validate_and_merge(parsed: dict, det: dict) -> dict | None:
    """Enforce the schema and merge onto the deterministic set. Returns the
    merged set (probabilities renormalised, weighted EV recomputed) or None on
    ANY failure (caller falls back to the last valid set)."""
    if not isinstance(parsed, dict):
        return None
    proposed = parsed.get("scenarios")
    if not isinstance(proposed, list) or not proposed:
        return None

    det_by_id = {s["id"]: s for s in det["scenarios"]}
    proposed_by_id: dict[str, dict] = {}
    events: list[dict] = []
    for item in proposed:
        if not isinstance(item, dict):
            return None
        sid, kind = item.get("id"), item.get("kind")
        if not isinstance(sid, str) or kind not in _VALID_KINDS:
            return None
        if sid in det_by_id:
            proposed_by_id[sid] = item
        elif kind == "event":
            events.append(item)
        else:
            return None  # a new non-event id would be an invented core scenario

    # Canonical order: the three deterministic scenarios first, events after.
    merged: list[dict] = []
    for det_scenario in det["scenarios"]:
        proposal = proposed_by_id.get(det_scenario["id"])
        merged.append(_merge_kept(det_scenario, proposal) if proposal else dict(det_scenario))
    for event in events:
        merged.append(_build_event(event, det))

    _renormalize(merged)
    wprice, wupside = scenarios.weighted_expected(merged, det.get("current_price"))

    return {
        **det,
        "scenarios": merged,
        "weighted_expected_price": wprice,
        "weighted_expected_upside_pct": wupside,
        "framing": scenarios.FRAMING,
        "disclaimer": thesis.DISCLAIMER,
    }


def _refinable(scenario_set: dict) -> dict:
    """The parts the model may change — used for convergence comparison."""
    return {
        "scenarios": [
            {
                "id": s["id"],
                "label": s["label"],
                "narrative": s["narrative"],
                "probability": s["probability"],
                "drivers": s["drivers"],
                "assumptions": s["assumptions"],
            }
            for s in scenario_set["scenarios"]
        ],
        "weighted_expected_price": scenario_set.get("weighted_expected_price"),
    }


# --------------------------------------------------------------------- cache


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(settings, ticker, inputs, profile, model) -> Path:
    """One JSON file per (ticker, input-hash, model, profile id+rules-hash)."""
    base_dir = Path(getattr(settings, "ai_cache_dir", None) or _DEFAULT_CACHE_DIR)
    key = _json(
        {
            "ticker": ticker or "",
            "input": _short_hash(_json(_serialize_inputs(inputs))),
            "model": model,
            "profile": f"{profile.id}:{_short_hash(_json(_serialize_profile(profile)))}",
        }
    )
    return base_dir / f"{ticker or 'unknown'}_{_short_hash(key)}.json"


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
        pass  # cache is best-effort; a write failure must never break the set


# --------------------------------------------------------------- entry point


def simulate_scenarios(
    inputs: scenarios.ScenarioInputs,
    profile: base.StrategyProfile,
    deterministic_set=None,
    *,
    ticker: str | None = None,
    corpus=None,
    transport=None,
    settings=None,
) -> dict:
    """Refine the deterministic scenario set with the Claude API, or pass it
    through.

    Returns a `ScenarioSet`-shaped dict plus an ``engine`` provenance key:
    ``"deterministic"`` (no key, or every AI round failed → identical body) or
    ``"ai"`` (≥1 valid refinement merged; carries an ``ai_notes`` block with the
    model, iteration count, per-change rationale and case-similarity). Never
    raises on the no-key path.
    """
    settings = _resolve_settings(settings)
    det = (
        _as_dict(deterministic_set)
        if deterministic_set is not None
        else scenarios.build_scenario_set(inputs, profile).to_dict()
    )

    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        return {**det, "engine": "deterministic"}

    model = getattr(settings, "anthropic_model", None) or "claude-sonnet-5"
    max_iterations = int(getattr(settings, "anthropic_max_iterations", 2) or 2)
    cache_enabled = bool(getattr(settings, "ai_cache_enabled", True))
    if corpus is None:
        corpus = getattr(cases, "CORPUS", ())

    cache_file = _cache_path(settings, ticker, inputs, profile, model)
    if cache_enabled:
        cached = _cache_read(cache_file)
        if cached is not None:
            return cached

    transport = transport or thesis_ai.default_transport(settings)
    # Widened allowed-set: sourced inputs ∪ cited corpus ∪ deterministic-computed.
    allowed = (
        scenarios.input_numbers(inputs)
        | collect_corpus_numbers(corpus)
        | scenarios.scenario_numbers(det)
    )
    serial_inputs = _serialize_inputs(inputs)
    serial_profile = _serialize_profile(profile)
    serial_corpus = _serialize_corpus(corpus)

    current = det
    applied = 0
    notes: dict | None = None

    for _ in range(max_iterations):
        prompt = _build_prompt(serial_inputs, serial_profile, serial_corpus, current)
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
        # Fabrication guard: a prose number outside the allowed-set rejects the
        # round (structured numbers are engine-controlled: kept-deterministic or
        # our renormalised probabilities / recomputed weighted EV).
        if scenarios.prose_numbers(merged) - allowed:
            break
        if _refinable(merged) == _refinable(current):
            break  # converged — a round that changed nothing
        current = merged
        applied += 1
        notes = {
            "changes": _sanitize_notes(parsed.get("changes")),
            "case_similarity": _sanitize_notes(parsed.get("case_similarity")),
        }

    if applied == 0:
        return {**det, "engine": "deterministic"}

    result = {
        **current,
        "engine": "ai",
        "ai_notes": {"model": model, "iterations": applied, **(notes or {})},
    }
    # Belt-and-suspenders: the merged set must still be clean.
    if scenarios.prose_numbers(result) - allowed:
        return {**det, "engine": "deterministic"}

    if cache_enabled:
        _cache_write(cache_file, result)
    return result
