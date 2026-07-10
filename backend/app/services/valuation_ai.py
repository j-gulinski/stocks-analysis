"""AI valuation agent — stock-potential read on top of the scenario set (stage
SC / WP4a — docs/plan-stage-scenarios.md §"WP4a").

What this is
-----------
`scenarios.build_scenario_set` + `scenarios_ai.simulate_scenarios` give a coherent
scenario set with a probability-weighted expected value. This module reads **all
gathered data + that scenario set** and produces a compact `valuation` block:

  * **`potential`** — how much upside, anchored to the set's weighted EV
    (deterministic: `potential.value_pct == weighted_expected_upside_pct`);
  * **`confidence`** — a `low/medium/high` level from a **deterministic heuristic
    with explicit thresholds** (data coverage = the thesis `computable` count +
    the own-history depth `multiple_history.n`); the AI may reword the rationale
    but the counts and the level stay sourced;
  * **`what_would_change`** — what would move the assessment (the thesis
    `verify_next` gaps + the scenario reversion assumption);
  * a Polish `narrative`, the fixed `framing`, the standing `disclaimer`.

Same two hard guard-rails as `thesis_ai`/`scenarios_ai`:

  * **Deterministic-first.** No API key (the sandbox default) ⇒ the deterministic
    valuation verbatim, marked ``engine: "deterministic"``. Never raises on the
    no-key path — the dossier always gets a valuation block.
  * **No fabricated numbers.** Every number the model quotes in prose must be a
    subset of ``input_numbers(inputs) ∪ scenario_numbers(scenario_set) ∪
    corpus_numbers ∪ engine_valuation_numbers`` — the sourced inputs, the
    scenario set's own computed numbers, the cited worked-case comparables, and
    the numbers THIS deterministic valuation computed (potential + the coverage
    counts). A stray figure rejects the whole round.

Design notes (for a C# dev): same shape as `scenarios_ai` — `assess_potential` is
a decorator over a pure deterministic builder with an **injected `transport`**
delegate; the Anthropic SDK + pydantic `Settings` are imported lazily *inside*
functions (via `thesis_ai`), so the module loads under a bare system Python with
no PyPI. The confidence heuristic ≈ a small rules table mapping two coverage
integers to an enum.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.services import scenarios, scenarios_ai, thesis, thesis_ai
from app.services.strategies import base, cases

# Confidence levels the heuristic may emit (the AI may reword the rationale but
# never re-pick the level — it is re-imposed deterministically every round).
LOW, MEDIUM, HIGH = "low", "medium", "high"
_VALID_LEVELS = frozenset({LOW, MEDIUM, HIGH})

# Heuristic thresholds (plan §WP4a, amended). The LOW cutoff is the profile's own
# `min_key_indicators` (3 for Malik); HIGH needs enough indicators AND enough
# own-history observations for a stable median/quartiles. Fixed, mechanically
# checkable, and asserted at all three levels in test_valuation_ai.py.
_HIGH_KEY_INDICATORS = 5
_STABLE_HISTORY_N = 4

# Fixed framing line (an analysis entrance, never a signal). Digit-free so it can
# never trip the fabrication guard.
FRAMING = "To ocena potencjału — punkt wejścia w analizę, nie sygnał kupna/sprzedaży."

# The prose fields the model may refine. `confidence.level`, `potential.value_pct`
# and `range_pct` are STRUCTURED (deterministic), re-imposed every round and so
# deliberately absent here. Convergence = these stop changing.
_REFINABLE = ("potential_basis_label", "confidence_rationale", "narrative", "what_would_change")

# Gitignored cache dir, separate from the thesis/scenarios refiners (plan §WP4a).
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "valuation_ai"


class ValuationContextError(ValueError):
    """Raised before an Anthropic valuation call when premium context is missing."""


# ------------------------------------------------------------- settings/dep


def _resolve_settings(settings):
    """Injected settings, or the lazily-loaded pydantic `Settings` (deferred so
    this module imports without pydantic-settings in the sandbox)."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


# ---------------------------------------------------- deterministic valuation


def _add_num(nums: set[float], value) -> None:
    """Add a scalar at BOTH 4-dp and 2-dp precision (prose is formatted at 2 dp),
    so a quoted figure is inside the allowed set even at more stored precision."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    nums.add(round(float(value), 4))
    nums.add(round(float(value), 2))


def _fmt(value: float) -> str:
    """Polish decimal, ≤2 dp, trailing zeros trimmed — parses back to
    `round(value, 2)`, keeping the fabrication guard exact."""
    text = f"{round(value, 2):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _fmt_signed(value: float) -> str:
    body = _fmt(value)
    return body if body.startswith("-") else "+" + body


def _confidence_level(computable: int, n: int, min_key: int) -> str:
    """The amended WP4a heuristic, in order (plan §WP4a):
      < min_key indicators OR n == 0            → low
      ≥ 5 indicators AND n ≥ 4                   → high
      everything between (3–4, or ≥5 with n<4)  → medium
    """
    if computable < min_key or n == 0:
        return LOW
    if computable >= _HIGH_KEY_INDICATORS and n >= _STABLE_HISTORY_N:
        return HIGH
    return MEDIUM


def _confidence_rationale(level: str, computable: int, n: int, min_key: int) -> str:
    """Deterministic, sourced rationale (the counts are number-bearing facts the
    AI may reword but not change)."""
    if level == LOW:
        return (
            f"Niska pewność: pokrycie danych jest zbyt płytkie — {computable} "
            f"policzalnych wskaźników kluczowych (próg {min_key}) lub brak własnej "
            f"historii mnożnika (n={n}). Potencjał traktuj wyłącznie orientacyjnie."
        )
    if level == HIGH:
        return (
            f"Wyższa pewność jak na to narzędzie: {computable} policzalnych "
            f"wskaźników kluczowych (≥{_HIGH_KEY_INDICATORS}) i n={n} obserwacji "
            f"własnej historii mnożnika (≥{_STABLE_HISTORY_N}) dają w miarę stabilną "
            "medianę i kwartyle, na których oparte są scenariusze."
        )
    return (
        f"Umiarkowana pewność: pokrycie częściowe — {computable} policzalnych "
        f"wskaźników kluczowych i n={n} obserwacji własnej historii mnożnika. "
        "Wynik zależy od uzupełnienia luk poniżej."
    )


def _scenario_upside_band(scenario_set: dict):
    """(min, max) of the priced scenarios' implied upsides — a labelled band
    around the weighted point estimate. `(None, None)` when nothing is priced."""
    upsides = [
        s.get("implied_upside_pct")
        for s in scenario_set.get("scenarios", [])
        if s.get("implied_upside_pct") is not None
    ]
    if not upsides:
        return None, None
    return min(upsides), max(upsides)


def _what_would_change(deterministic_thesis: dict) -> list[dict]:
    """What would move the assessment: the thesis `verify_next` gaps (catalyst,
    backlog, management, …) plus the scenario reversion assumption. Never empty
    while the strategy carries verify-gaps (it always does)."""
    items: list[dict] = []
    seen: set[str] = set()
    for v in deterministic_thesis.get("verify_next", []) or []:
        vid = v.get("id")
        if not isinstance(vid, str) or vid in seen:
            continue
        items.append({"id": vid, "text": v.get("text", ""), "why": v.get("why", "")})
        seen.add(vid)
    # The scenario mechanic itself is a thing to verify (digit-free — the whole
    # potential rests on the multiple reverting to its own history).
    if "scenario_reversion" not in seen:
        items.append(
            {
                "id": "scenario_reversion",
                "text": "Potwierdź lub obal założenie rewersji mnożnika wyceny do "
                "poziomów z własnej historii spółki.",
                "why": "Cały szacowany potencjał opiera się na powrocie mnożnika "
                "do własnych kwartyli przy utrzymanym wyniku — to założenie, nie "
                "prognoza.",
            }
        )
    return items


def _build_deterministic_valuation(
    inputs: scenarios.ScenarioInputs, scenario_set: dict, profile: base.StrategyProfile
) -> tuple[dict, int, int]:
    """The keyless / fallback valuation. Returns (valuation_dict, computable, n)
    so the caller can build the fabrication allowed-set from the same numbers."""
    computable = thesis.count_computable_key_indicators(inputs.thesis_inputs, profile)
    n = 0
    hist_n = (inputs.multiple_history or {}).get("n")
    if isinstance(hist_n, int):
        n = hist_n
    min_key = profile.entry_rule.min_key_indicators

    level = _confidence_level(computable, n, min_key)
    rationale = _confidence_rationale(level, computable, n, min_key)

    value_pct = scenario_set.get("weighted_expected_upside_pct")
    lo, hi = _scenario_upside_band(scenario_set)
    if value_pct is not None:
        band = ""
        if lo is not None and hi is not None:
            band = f" (pasmo scenariuszy {_fmt_signed(lo)}%…{_fmt_signed(hi)}%)"
        potential = {
            "value_pct": value_pct,
            "range_pct": [lo, hi] if lo is not None and hi is not None else None,
            "basis_label": (
                "wartość oczekiwana ważona prawdopodobieństwem scenariuszy "
                "(rewersja mnożnika do własnej historii, wynik utrzymany)"
            ),
        }
        narrative = (
            f"Szacowany potencjał {_fmt_signed(value_pct)}% wobec bieżącego kursu — "
            f"wartość oczekiwana ważona prawdopodobieństwem scenariuszy{band}. "
            f"{rationale} Ocenę zmienią czynniki z listy „co zmieniłoby ocenę”."
        )
    else:
        potential = {
            "value_pct": None,
            "range_pct": None,
            "basis_label": (
                "brak policzalnej ceny docelowej w scenariuszach — potencjału nie "
                "wyznaczono (luka danych, patrz „co zmieniłoby ocenę”)"
            ),
        }
        narrative = (
            "Potencjału nie wyznaczono — scenariusze nie mają policzalnej ceny "
            f"docelowej (brak sterownika mnożnika). {rationale} Uzupełnij luki "
            "z listy „co zmieniłoby ocenę”."
        )

    # Rebuild the deterministic thesis (pure, cheap) to source the verify gaps.
    det_thesis = thesis.build_thesis(inputs.thesis_inputs, profile).to_dict()

    valuation = {
        "potential": potential,
        "confidence": {"level": level, "rationale": rationale},
        "what_would_change": _what_would_change(det_thesis),
        "narrative": narrative,
        "framing": FRAMING,
        "disclaimer": thesis.DISCLAIMER,
    }
    return valuation, computable, n


# --------------------------------------------------------- number vocabulary


def engine_valuation_numbers(valuation: dict, computable: int, n: int) -> set[float]:
    """The numbers THIS deterministic valuation computed — the coverage counts +
    heuristic thresholds and the potential value/range. Together with the input,
    scenario and corpus numbers this is the AI path's fabrication allowed-set
    (mirrors `scenarios.scenario_numbers` for the WP3b engine term)."""
    nums: set[float] = set()
    for value in (computable, n, _HIGH_KEY_INDICATORS, _STABLE_HISTORY_N):
        _add_num(nums, value)
    pot = valuation.get("potential") or {}
    _add_num(nums, pot.get("value_pct"))
    rng = pot.get("range_pct")
    if isinstance(rng, (list, tuple)):
        for value in rng:
            _add_num(nums, value)
    return nums


def _prose_numbers(valuation: dict) -> set[float]:
    """Every number in the prose the user reads (basis label, confidence
    rationale, narrative, what-would-change texts, framing, disclaimer). The
    guard requires these ⊆ allowed."""
    pot = valuation.get("potential") or {}
    parts = [
        pot.get("basis_label", ""),
        (valuation.get("confidence") or {}).get("rationale", ""),
        valuation.get("narrative", ""),
        valuation.get("framing", ""),
        valuation.get("disclaimer", ""),
    ]
    for item in valuation.get("what_would_change", []) or []:
        parts += [item.get("text", ""), item.get("why", "")]
    nums: set[float] = set()
    for part in parts:
        nums |= thesis_ai.numbers(str(part))
    return nums


# ------------------------------------------------------------------- prompt

_INSTRUCTIONS = (
    "You refine a rule-based STOCK-POTENTIAL valuation for a Warsaw-listed (GPW) "
    "stock, in the spirit of Pawel Malik's strategy plus general fundamental "
    "analysis. You are given: the company context + open data gaps, the active "
    "strategy profile, a corpus of worked cases (with real multiples / repricing "
    "durations), the scenario set with its probability-weighted expected value, "
    "and the current DETERMINISTIC valuation (potential, confidence, "
    "what-would-change).\n\n"
    "Return ONLY a single JSON object (no markdown, no prose outside it) with "
    "exactly these keys:\n"
    '  "potential_basis_label": string,   // reword only; do NOT change the number\n'
    '  "confidence_rationale": string,    // reword; keep the counts + the level\n'
    '  "what_would_change": [{"id": string, "text": string, "why": string}], '
    "// ids MUST come from the current list\n"
    '  "narrative": string,               // Polish paragraph\n'
    '  "changes": [{"field": string, "rationale": string}],\n'
    '  "case_similarity": [{"ticker": string, "note": string}]\n\n'
    "HARD RULES:\n"
    "1. Do NOT change the potential value/range, the confidence LEVEL, or the "
    "coverage counts — they are re-imposed automatically. You may only reword "
    "their prose.\n"
    "2. Keep every what_would_change id from the current list; you may reword or "
    "drop, but do not invent new ids.\n"
    "3. NEVER introduce a number (percentage, ratio, PLN amount, multiple, "
    "duration, count) that is not already present in the inputs, the scenario "
    "set, the worked-case corpus, or the current valuation. Quote figures "
    "verbatim. Any invented number invalidates your whole answer.\n"
    "4. Domain language stays Polish. This is an ENTRANCE to analysis, never a "
    "buy/sell signal. Do not add a disclaimer; it is appended automatically.\n"
    "5. If you cannot improve the valuation, return it unchanged (a valid, "
    "converged answer)."
)


def _serialize_inputs(inputs: scenarios.ScenarioInputs) -> dict:
    ti = inputs.thesis_inputs
    company = ti.insights
    industry_type = _industry_type(inputs)
    return {
        "company": {
            "industry_type": industry_type,
            "size_code": company.size_code,
            "size_label": company.size_label,
            "sector_group": company.sector_group,
            "sector_group_label": company.sector_group_label,
            "sector": company.sector,
            "summary": company.summary,
        },
        "sectorized_prompting": _sector_guidance(industry_type),
        "company_market_data": inputs.market_data,
        "open_gaps": [{"id": m.id, "name": m.name, "why": m.why} for m in company.missing],
        "drivers": inputs.to_dict(),
        "ttm": ti.ttm,
        "pe_history": ti.pe_history,
        "net_cash": ti.net_cash,
    }


def _serialize_profile(profile: base.StrategyProfile) -> dict:
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
                "outcome": getattr(case, "outcome", ""),
                "citation": case.citation,
                "sources": case.sources,
                "gaps": case.gaps,
                "expected_read": case.expected_read,
            }
        )
    return out


def _build_prompt(serial_inputs, serial_profile, serial_corpus, scenario_set, current) -> str:
    payload = {
        "strategy_profile": serial_profile,
        "valuation_inputs": serial_inputs,
        "worked_cases": serial_corpus,
        "scenario_set": {
            "valuation_multiple": scenario_set.get("valuation_multiple"),
            "current_price": scenario_set.get("current_price"),
            "weighted_expected_price": scenario_set.get("weighted_expected_price"),
            "weighted_expected_upside_pct": scenario_set.get("weighted_expected_upside_pct"),
            "scenarios": scenario_set.get("scenarios"),
        },
        "current_valuation": {k: current.get(k) for k in ("potential", "confidence",
                                                          "what_would_change", "narrative")},
    }
    return _INSTRUCTIONS + "\n\nDATA:\n" + json.dumps(payload, ensure_ascii=False, default=str)


def _industry_type(inputs: scenarios.ScenarioInputs) -> str:
    market_data = inputs.market_data or {}
    return (
        market_data.get("industry_type")
        or (market_data.get("priority_values") or {}).get("industry_type")
        or inputs.thesis_inputs.insights.sector_group_label
        or "Pozostałe"
    )


def _sector_guidance(industry_type: str) -> list[str]:
    lowered = industry_type.lower()
    if "gaming" in lowered or "gry" in lowered:
        return [
            "Evaluate UA (User Acquisition) costs explicitly.",
            "Check IP amortization schedules and whether profit is one-off or repeatable.",
            "Treat Steam wishlist / launch signals as catalysts to verify, not facts.",
        ]
    if "real estate" in lowered or "developer" in lowered or "nieruchomo" in lowered:
        return [
            "Shift attention to pre-sales metrics and backlog conversion.",
            "Check land bank value separately from current-period earnings.",
            "Stress dynamic cost inflation parameters before trusting margin expansion.",
        ]
    if "saas" in lowered:
        return [
            "Evaluate ARR/revenue retention and customer acquisition payback where present.",
            "Separate recurring subscription margin from implementation or one-off services.",
            "Treat churn, expansion revenue and cash conversion as key missing-data gaps.",
        ]
    return [
        "Use the supplied industry_type before applying a generic industrial valuation frame.",
        "Prefer ROIC/FCF/EV context over flat financial-table heuristics.",
    ]


def _metric_has_value(metrics: dict, key: str) -> bool:
    item = metrics.get(key)
    if not isinstance(item, dict):
        return False
    return item.get("value") is not None


def validate_valuation_context(inputs: scenarios.ScenarioInputs) -> None:
    """Pre-flight assertion for the Anthropic valuation path."""
    market_data = inputs.market_data or {}
    metrics = market_data.get("advanced_metrics") or {}
    missing = [key.upper() for key in ("roic", "fcf") if not _metric_has_value(metrics, key)]
    if missing:
        industry_type = _industry_type(inputs)
        raise ValuationContextError(
            "ValuationContext missing premium metrics before Anthropic call: "
            f"{', '.join(missing)} (industry_type={industry_type}). "
            "Refresh BiznesRadar premium data into company_market_data first."
        )


# -------------------------------------------------------- validate / merge


def _str_or(value, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


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


def _merge_what_would_change(det_items: list[dict], proposed) -> list[dict]:
    """Take the model's reworded text/why but keep the deterministic ids (no
    invented gaps); fall back to the deterministic list on any shape mismatch."""
    if not isinstance(proposed, list):
        return [dict(i) for i in det_items]
    by_id = {i["id"]: i for i in det_items}
    merged: list[dict] = []
    used: set[str] = set()
    for item in proposed:
        if not isinstance(item, dict):
            continue
        iid = item.get("id")
        if iid not in by_id or iid in used:
            continue
        base_item = by_id[iid]
        merged.append(
            {
                "id": iid,
                "text": _str_or(item.get("text"), base_item["text"]),
                "why": _str_or(item.get("why"), base_item["why"]),
            }
        )
        used.add(iid)
    # Preserve any deterministic item the model dropped — the assessment must not
    # silently lose a gap.
    for item in det_items:
        if item["id"] not in used:
            merged.append(dict(item))
    return merged


def _validate_and_merge(parsed: dict, det: dict) -> dict | None:
    """Enforce the schema and merge the reworded prose onto the deterministic
    valuation (structured facts re-imposed). Returns the merged valuation or None
    on ANY failure (caller falls back to the last valid one)."""
    if not isinstance(parsed, dict):
        return None
    narrative = parsed.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        return None

    det_pot = det["potential"]
    merged_pot = {
        "value_pct": det_pot["value_pct"],  # deterministic — never from the model
        "range_pct": det_pot["range_pct"],
        "basis_label": _str_or(parsed.get("potential_basis_label"), det_pot["basis_label"]),
    }
    det_conf = det["confidence"]
    merged_conf = {
        "level": det_conf["level"],  # deterministic — re-imposed
        "rationale": _str_or(parsed.get("confidence_rationale"), det_conf["rationale"]),
    }
    return {
        "potential": merged_pot,
        "confidence": merged_conf,
        "what_would_change": _merge_what_would_change(
            det["what_would_change"], parsed.get("what_would_change")
        ),
        "narrative": narrative,
        "framing": FRAMING,
        "disclaimer": thesis.DISCLAIMER,
    }


def _refinable(valuation: dict) -> dict:
    """The parts the model may change — used for convergence comparison."""
    return {
        "potential_basis_label": (valuation.get("potential") or {}).get("basis_label"),
        "confidence_rationale": (valuation.get("confidence") or {}).get("rationale"),
        "narrative": valuation.get("narrative"),
        "what_would_change": [
            (i.get("id"), i.get("text"), i.get("why"))
            for i in valuation.get("what_would_change", []) or []
        ],
    }


# --------------------------------------------------------------------- cache


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(settings, ticker, inputs, scenario_set, profile, model) -> Path:
    """One JSON file per (ticker, input+scenario hash, model, profile id+rules).
    The scenario set is hashed too: a different (e.g. AI-refined) set → a fresh
    valuation, never a stale cache hit."""
    base_dir = Path(getattr(settings, "ai_cache_dir", None) or _DEFAULT_CACHE_DIR)
    key = _json(
        {
            "ticker": ticker or "",
            "input": _short_hash(_json(_serialize_inputs(inputs))),
            "scenarios": _short_hash(_json(scenario_set)),
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
        pass  # cache is best-effort; a write failure must never break the read


# --------------------------------------------------------------- entry point


def assess_potential(
    inputs: scenarios.ScenarioInputs,
    scenario_set: dict,
    profile: base.StrategyProfile,
    *,
    ticker: str | None = None,
    corpus=None,
    transport=None,
    settings=None,
) -> dict:
    """Assess stock potential on top of the scenario set, or pass the
    deterministic valuation through.

    Returns a `valuation`-shaped dict plus an ``engine`` provenance key:
    ``"deterministic"`` (no key, or every AI round failed → identical body) or
    ``"ai"`` (≥1 valid refinement merged; carries an ``ai_notes`` block). The
    no-key path returns exactly the deterministic valuation + marker and never
    raises, so the dossier always has a valuation block.
    """
    settings = _resolve_settings(settings)
    det, computable, n = _build_deterministic_valuation(inputs, scenario_set, profile)

    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        return {**det, "engine": "deterministic"}
    validate_valuation_context(inputs)

    model = getattr(settings, "anthropic_model", None) or "claude-sonnet-4-6"
    max_iterations = int(getattr(settings, "anthropic_max_iterations", 2) or 2)
    cache_enabled = bool(getattr(settings, "ai_cache_enabled", True))
    if corpus is None:
        corpus = getattr(cases, "CORPUS", ())

    cache_file = _cache_path(settings, ticker, inputs, scenario_set, profile, model)
    if cache_enabled:
        cached = _cache_read(cache_file)
        if cached is not None:
            return cached

    transport = transport or thesis_ai.default_transport(settings)
    # Allowed-set: sourced inputs ∪ scenario-set numbers ∪ cited corpus ∪ THIS
    # deterministic valuation's own computed numbers (plan §WP4a).
    allowed = (
        scenarios.input_numbers(inputs)
        | scenarios.scenario_numbers(scenario_set)
        | scenarios_ai.collect_corpus_numbers(corpus)
        | engine_valuation_numbers(det, computable, n)
    )
    serial_inputs = _serialize_inputs(inputs)
    serial_profile = _serialize_profile(profile)
    serial_corpus = _serialize_corpus(corpus)

    current = det
    applied = 0
    notes: dict | None = None

    for _ in range(max_iterations):
        prompt = _build_prompt(serial_inputs, serial_profile, serial_corpus, scenario_set, current)
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
        # round (structured numbers are engine-controlled: value/range/level).
        if _prose_numbers(merged) - allowed:
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
    # Belt-and-suspenders: the merged valuation must still be clean.
    if _prose_numbers(result) - allowed:
        return {**det, "engine": "deterministic"}

    if cache_enabled:
        _cache_write(cache_file, result)
    return result
