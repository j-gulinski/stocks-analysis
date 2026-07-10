"""Scenario simulation engine (stage SC / WP3a — docs/plan-stage-scenarios.md).

What this is
-----------
A **small, discrete set of scenario projections** per stock — a
`negative / base / positive` trio built by reverting the company's *own*
valuation multiple toward its historical quartiles (Q1 / median / Q3), each
carrying a probability, a target valuation, an expected repricing horizon, an
implied upside, and a set-level probability-weighted expected value.

What this is NOT (plan Non-goals, binding)
-----------------------------------------
- **Not** a stochastic Monte-Carlo — three deterministic multiple-reversion
  paths, not thousands of random draws.
- **Not** a buy/sell signal — every scenario is an *if-this-then-that*
  projection with the standing `thesis.DISCLAIMER` and a fixed "punkt wejścia w
  analizę, nie sygnał" framing.
- **Not** a re-computation of any indicator — the target price is a NEW computed
  number (a pure function of sourced inputs), never a restated dossier metric.
- **Missing driver ≠ invented target** — if the sector multiple's per-share
  driver (EBITDA TTM, book value, EPS) is missing, the scenario *labels the gap*
  and yields a `None` target; it never guesses a price (the fabrication guard in
  `test_scenarios.py` enforces this).

Purity (plan acceptance #1). This module imports only `metrics` / `thesis` /
`strategies` + stdlib — no DB, no framework, no PyPI, and (deliberately) not
`thesis_ai`, so it — and `test_scenarios.py` — run under the bare system Python
in the sandbox. It therefore carries its OWN small number-extraction vocabulary
(`_numbers` / `input_numbers`) mirroring the established fabrication-guard
grammar in `thesis_ai`/`test_thesis`, rather than importing it.

For a C# dev: think of `build_scenario_set` as a strategy-pattern *projector* —
it takes the sourced inputs + a `StrategyProfile` and returns a small immutable
result collection (`ScenarioSet`), each element a pure projection. The
`scenarios_ai` refiner then decorates this pure compute with an injected
transport + a validation guard (same shape as the thesis refiner).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from math import isclose, isfinite

from app.services import thesis
from app.services.strategies import base

# --- fixed vocabulary (generic, not strategy data) ---------------------------

# The three deterministic reversion paths. Probabilities are a documented
# default that sums to 1.00 BY CONSTRUCTION (plan §WP3a); the AI refiner may
# add event scenarios and renormalise, but the deterministic set is always
# coherent. Each row: kind, id, Polish label, probability, own-history quartile
# key, and the Polish basis phrase naming that quartile.
_SCENARIO_SPECS: tuple[tuple[str, str, str, float, str, str], ...] = (
    ("negative", "negative", "Wariant ostrożny (dolny kwartyl)", 0.25, "q1",
     "dolny kwartyl własnej historii"),
    ("base", "base", "Wariant bazowy (mediana)", 0.50, "median",
     "mediana własnej historii"),
    ("positive", "positive", "Wariant górnego kwartylu", 0.25, "q3",
     "górny kwartyl własnej historii"),
)

# Multiple-type token → Polish label shown in narratives / basis labels.
_MULTIPLE_LABEL = {"cz": "C/Z", "cwk": "C/WK", "ev_ebitda": "EV/EBITDA"}

# The deterministic engine is still a valuation-sensitivity tool, not a full
# operating model. These labels make the company-side condition explicit while
# stating that its numerical effect is not yet priced into the target.
_OUTCOME_DRIVER = {
    "cz": "EPS / zysk na akcję",
    "cwk": "wartość księgowa na akcję",
    "ev_ebitda": "EBITDA",
}

# Which valuation criterion maps to which multiple-type token. The APPLICABILITY
# (which sector gets which) is NOT re-encoded here — it is read from the
# profile's own criteria (malik.py: `cwk`→finance/realestate, `ev_ebitda`→
# energy), so there is no second copy of the sector mapping to drift.
_CRITERION_MULTIPLE = {"pe_vs_history": "cz", "cwk": "cwk", "ev_ebitda": "ev_ebitda"}

# RT4.3b deliberately starts with the valuation drivers already owned by the
# deterministic engine. Broader revenue/margin trees belong to a versioned
# company template; accepting arbitrary JSON here would make the valuation
# look more precise without equations that can consume it.
_ASSUMPTION_DRIVER_KEYS = {
    "eps": "eps",
    "book_value": "book_value",
    "ebitda_ttm": "ebitda_ttm",
    "shares_outstanding": "shares_outstanding",
    "net_cash": "net_cash",
}

# How each reversion path narrates the multiple move (digit-free leads).
_KIND_LEAD = {
    "negative": "Powrót mnożnika",
    "base": "Powrót mnożnika",
    "positive": "Powrót mnożnika",
}

# Fixed framing line (plan §WP3a): an analysis entrance, never a signal. Kept
# digit-free so it can never trip the fabrication guard.
FRAMING = "To punkt wejścia w analizę, nie sygnał kupna/sprzedaży."

# Default repricing horizon when the corpus has no comparable durations
# (deterministic engine has none — WP4's corpus lets the AI cite real ones).
# The months live in the STRUCTURED fields; the basis label stays digit-free.
_DEFAULT_HORIZON = {
    "low_months": 12,
    "high_months": 24,
    "basis_label": "domyślny zakres — brak porównywalnych repricingów w korpusie",
}

# Public copy for `scenarios_ai` event scenarios (they inherit the same labelled
# default band; WP4's corpus lets the refiner cite real repricing durations).
DEFAULT_HORIZON = dict(_DEFAULT_HORIZON)

# Same number grammar as the deterministic thesis fabrication guard: optional
# sign, digits, optional decimal comma/period.
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


# ------------------------------------------------------------------ data classes


@dataclass
class ScenarioInputs:
    """The sourced pieces the projector consumes.

    Wraps `thesis.ThesisInputs` (so the whole dossier read is available for the
    AI refiner + the fabrication vocabulary) and adds the valuation drivers the
    target math needs. All money in `tys. PLN` except `current_price` (PLN/share)
    and `eps` (PLN/share); `multiple_history` is the own-history stats of the
    SECTOR-relevant multiple (from `metrics.compute_multiple_history`).
    """

    thesis_inputs: thesis.ThesisInputs
    multiple_history: dict = field(default_factory=dict)
    eps: float | None = None  # PLN per share (TTM EPS or sourced forward EPS)
    book_value: float | None = None  # equity, tys. PLN (latest balance)
    ebitda_ttm: float | None = None  # tys. PLN or None (labelled gap)
    shares_outstanding: int | None = None
    current_price: float | None = None  # PLN (from ttm.price)
    net_cash: float | None = None  # tys. PLN (cash − debt)
    market_data: dict = field(default_factory=dict)  # AI-priority premium context
    earnings_basis: dict = field(default_factory=dict)  # provenance for EPS/driver

    def to_dict(self) -> dict:
        return {
            "multiple_history": self.multiple_history,
            "eps": self.eps,
            "book_value": self.book_value,
            "ebitda_ttm": self.ebitda_ttm,
            "shares_outstanding": self.shares_outstanding,
            "current_price": self.current_price,
            "net_cash": self.net_cash,
            "market_data": self.market_data,
            "earnings_basis": self.earnings_basis,
        }


@dataclass
class Scenario:
    id: str
    kind: str  # negative | base | positive | event
    label: str  # Polish
    probability: float  # 0–1
    narrative: str  # Polish, sourced (or a labelled gap)
    target_multiple: dict  # {"type", "value" (float|None), "basis_label"}
    target_price: float | None  # PLN
    implied_upside_pct: float | None
    horizon: dict  # {"low_months", "high_months", "basis_label"}
    drivers: list[str] = field(default_factory=list)  # each traceable
    assumptions: list[str] = field(default_factory=list)  # each labelled
    company_outcome: dict = field(default_factory=dict)  # explicit operating condition

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "probability": self.probability,
            "narrative": self.narrative,
            "target_multiple": self.target_multiple,
            "target_price": self.target_price,
            "implied_upside_pct": self.implied_upside_pct,
            "horizon": self.horizon,
            "drivers": list(self.drivers),
            "assumptions": list(self.assumptions),
            "company_outcome": dict(self.company_outcome),
        }


@dataclass
class ScenarioSet:
    scenarios: list[Scenario]
    valuation_multiple: str  # cz | cwk | ev_ebitda (the effective one used)
    current_price: float | None
    weighted_expected_price: float | None  # PLN
    weighted_expected_upside_pct: float | None
    framing: str
    disclaimer: str
    priced_probability_mass: float | None = None
    quality_warnings: list[str] = field(default_factory=list)
    engine: str = "deterministic"  # scenarios_ai may set "ai"

    def to_dict(self) -> dict:
        return {
            "scenarios": [s.to_dict() for s in self.scenarios],
            "valuation_multiple": self.valuation_multiple,
            "current_price": self.current_price,
            "weighted_expected_price": self.weighted_expected_price,
            "weighted_expected_upside_pct": self.weighted_expected_upside_pct,
            "framing": self.framing,
            "disclaimer": self.disclaimer,
            "priced_probability_mass": self.priced_probability_mass,
            "quality_warnings": list(self.quality_warnings),
            "engine": self.engine,
        }


# ------------------------------------------------------------ number helpers
# Own copy of the fabrication-guard vocabulary (see module docstring: keeping
# this module free of a `thesis_ai` import is what lets it run in-session).


def _numbers(text: str) -> set[float]:
    """Every numeric token in `text`, normalised (Polish comma → dot, rounded)."""
    return {round(float(tok.replace(",", ".")), 4) for tok in _NUM.findall(text)}


def _add_num(nums: set[float], value) -> None:
    """Add a scalar at BOTH 4-dp and 2-dp precision. Prose is formatted at 2 dp
    (`_fmt`), so the 2-dp variant guarantees a quoted figure is inside the
    allowed set even when the stored value carries more precision."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    nums.add(round(float(value), 4))
    nums.add(round(float(value), 2))


def input_numbers(inputs: ScenarioInputs) -> set[float]:
    """Every number the engine is ALLOWED to quote from sourced data — the thesis
    inputs (insights/ttm/pe_history/net_cash/forecast/prescore), the selected
    multiple's own-history stats, and the valuation drivers. Mirrors
    `thesis_ai.collect_input_numbers`, extended with the scenario drivers."""
    ti = inputs.thesis_inputs
    company = ti.insights
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
        str(ti.ttm),
        str(ti.pe_history),
        str(ti.net_cash),
        str(ti.latest_forecast),
        str(ti.prescore),
        str(inputs.multiple_history),
        str(inputs.market_data),
        str(inputs.earnings_basis),
    ]
    nums: set[float] = set()
    for part in parts:
        nums |= _numbers(part)
    for value in (inputs.multiple_history or {}).values():
        _add_num(nums, value)
    for driver in (
        inputs.eps,
        inputs.book_value,
        inputs.ebitda_ttm,
        inputs.shares_outstanding,
        inputs.current_price,
        inputs.net_cash,
    ):
        _add_num(nums, driver)
    return nums


def computed_numbers(scenario_set: dict) -> set[float]:
    """The numbers the engine itself COMPUTED — the structured numeric outputs
    (probabilities, target prices/multiples/upsides, horizons, weighted EV). Used
    together with `input_numbers` as the allowed set for the deterministic-set
    traceability check."""
    nums: set[float] = set()
    _add_num(nums, scenario_set.get("current_price"))
    _add_num(nums, scenario_set.get("weighted_expected_price"))
    _add_num(nums, scenario_set.get("weighted_expected_upside_pct"))
    for sc in scenario_set.get("scenarios", []):
        _add_num(nums, sc.get("probability"))
        _add_num(nums, sc.get("target_price"))
        _add_num(nums, sc.get("implied_upside_pct"))
        tm = sc.get("target_multiple") or {}
        _add_num(nums, tm.get("value"))
        hz = sc.get("horizon") or {}
        _add_num(nums, hz.get("low_months"))
        _add_num(nums, hz.get("high_months"))
    return nums


def prose_numbers(scenario_set: dict) -> set[float]:
    """Every number in the PROSE fields the user reads (narrative, labels,
    basis labels, drivers, assumptions, framing). The fabrication guard requires
    these to be a subset of `input_numbers ∪ computed_numbers`."""
    parts = [
        scenario_set.get("framing", ""),
        scenario_set.get("disclaimer", ""),
    ]
    for sc in scenario_set.get("scenarios", []):
        parts += [sc.get("label", ""), sc.get("narrative", "")]
        parts.append((sc.get("target_multiple") or {}).get("basis_label", ""))
        parts.append((sc.get("horizon") or {}).get("basis_label", ""))
        parts += list(sc.get("drivers") or [])
        parts += list(sc.get("assumptions") or [])
    nums: set[float] = set()
    for part in parts:
        nums |= _numbers(str(part))
    return nums


def scenario_numbers(scenario_set: dict) -> set[float]:
    """EVERY number in a scenario set (structured + prose). This is the
    `engine_scenario_numbers` term of the AI refiner's widened allowed-set —
    a number the deterministic engine legitimately produced."""
    return computed_numbers(scenario_set) | prose_numbers(scenario_set)


# ------------------------------------------------------------- formatting


def _fmt(value: float) -> str:
    """Polish decimal, ≤2 dp, trailing zeros trimmed, so the printed token parses
    back to `round(value, 2)` — keeping the fabrication guard exact (the 2-dp
    variant is always in the allowed set via `_add_num`)."""
    text = f"{round(value, 2):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _fmt_signed(value: float) -> str:
    body = _fmt(value)
    return body if body.startswith("-") else "+" + body


# --------------------------------------------------------- multiple selection


def select_valuation_multiple(sector_group: str | None, profile: base.StrategyProfile) -> str:
    """The sector-appropriate multiple token for `profile` (`cz` | `cwk` |
    `ev_ebitda`).

    Derived from the profile's `entry_rule.valuation` ∩ the criteria that APPLY
    to this sector: a sector-specific valuation criterion (`cwk` for
    finance/realestate, `ev_ebitda` for energy — as encoded in `malik.py`) wins;
    otherwise the generic own-history `cz`. No hard-coded sector set here — the
    applicability lives once, on the criteria.
    """
    rule = profile.entry_rule
    for crit in profile.applicable_criteria(None, sector_group):
        if crit.id in rule.valuation and crit.applies_to_sectors is not None:
            mult = _CRITERION_MULTIPLE.get(crit.id)
            if mult is not None:
                return mult
    return "cz"


# ------------------------------------------------------------- target math


def _target_price(mult_type: str, mult_value: float | None, inputs: ScenarioInputs):
    """Target price (PLN) for one reversion multiple, or (None, note) when a
    driver is missing. Money rules: statements are `tys. PLN` → ×1000 to PLN
    exactly where the equity bridge needs absolute figures."""
    if mult_value is None:
        return None, None
    if mult_type == "cz":
        if inputs.eps is None:
            return None, "Brak EPS (spółka nierentowna lub brak kursu) — ceny nie wyznaczono."
        return round(mult_value * inputs.eps, 2), None
    if mult_type == "cwk":
        if inputs.book_value is None or not inputs.shares_outstanding:
            return None, "Brak wartości księgowej lub liczby akcji — ceny nie wyznaczono."
        bvps = inputs.book_value * 1000.0 / inputs.shares_outstanding  # tys.→PLN
        return round(mult_value * bvps, 2), None
    if mult_type == "ev_ebitda":
        if inputs.ebitda_ttm is None or not inputs.shares_outstanding:
            return None, "Brak EBITDA TTM lub liczby akcji — ceny nie wyznaczono."
        implied_ev = mult_value * inputs.ebitda_ttm * 1000.0  # tys.→PLN
        # net_debt = −net_cash: positive net cash ADDS to equity, net debt SUBTRACTS.
        net_debt_pln = -(inputs.net_cash or 0.0) * 1000.0
        implied_equity = implied_ev - net_debt_pln
        return round(implied_equity / inputs.shares_outstanding, 2), None
    return None, None


def _upside(target_price: float | None, current_price: float | None):
    if target_price is None or current_price is None or current_price == 0:
        return None
    return round((target_price / current_price - 1.0) * 100.0, 2)


def _resolve_multiple(inputs: ScenarioInputs, preferred: str):
    """Pick the EFFECTIVE multiple + its history, falling back to `cz` when the
    preferred multiple's driver/history is unavailable (plan §WP3a). Returns
    (effective_type, history_dict, gap_note|None). Never fabricates: if even
    `cz` is unavailable the history is empty and every target ends up `None`."""

    def driver_ok(mult: str) -> bool:
        if mult == "cz":
            return inputs.eps is not None
        if mult == "cwk":
            return inputs.book_value is not None and bool(inputs.shares_outstanding)
        if mult == "ev_ebitda":
            return inputs.ebitda_ttm is not None and bool(inputs.shares_outstanding)
        return False

    def has_history(hist: dict) -> bool:
        return bool(hist) and hist.get("median") is not None

    pref_hist = inputs.multiple_history or {}
    if driver_ok(preferred) and has_history(pref_hist):
        return preferred, pref_hist, None

    # Fall back to the company's own C/Z history (always carried on the thesis
    # inputs as `pe_history`), labelling the gap honestly.
    cz_hist = (inputs.thesis_inputs.pe_history or {}) if inputs.thesis_inputs else {}
    gap = None
    if preferred != "cz":
        gap = (
            f"Brak danych dla mnożnika {_MULTIPLE_LABEL.get(preferred, preferred)} "
            "— użyto własnej historii C/Z (fallback)."
        )
    if driver_ok("cz") and has_history(cz_hist):
        return "cz", cz_hist, gap
    # Nothing usable → targets will be None, gap surfaced on every scenario.
    full_gap = (gap + " " if gap else "") + (
        "Brak policzalnego mnożnika własnej historii — ceny docelowej nie wyznaczono."
    )
    return "cz", cz_hist, full_gap


def _company_outcome(kind: str, effective: str) -> dict:
    """Describe the operating condition alongside the valuation sensitivity.

    The condition is deliberately qualitative until RT.4 adds driver-based
    operating equations; the target price remains the existing multiple-only
    calculation and says so explicitly in the description.
    """
    driver = _OUTCOME_DRIVER.get(effective, "wynik spółki")
    if kind == "negative":
        return {
            "direction": "negative",
            "label": "Wynik spółki pod presją",
            "description": (
                f"Warunek operacyjny: {driver} pogarsza się lub nie realizuje "
                "poziomu bazowego. Cena docelowa nadal pokazuje wyłącznie "
                "rewersję mnożnika przy bieżącym driverze."
            ),
        }
    if kind == "positive":
        return {
            "direction": "positive",
            "label": "Poprawa wyniku spółki",
            "description": (
                f"Warunek operacyjny: {driver} poprawia się względem poziomu "
                "bazowego. Cena docelowa nadal pokazuje wyłącznie rewersję "
                "mnożnika przy bieżącym driverze."
            ),
        }
    return {
        "direction": "neutral",
        "label": "Stabilny wynik spółki",
        "description": (
            f"Warunek operacyjny: {driver} pozostaje zbliżony do poziomu "
            "bazowego. Cena docelowa nadal pokazuje wyłącznie rewersję "
            "mnożnika przy bieżącym driverze."
        ),
    }


# ------------------------------------------------------------- construction


def _build_scenario(
    spec: tuple, effective: str, hist: dict, inputs: ScenarioInputs, gap_note: str | None
) -> Scenario:
    kind, sid, label, prob, quartile_key, quartile_phrase = spec
    n = hist.get("n") if isinstance(hist.get("n"), int) else 0
    mult_value = hist.get(quartile_key)
    mult_label = _MULTIPLE_LABEL.get(effective, effective)

    target_price, price_note = _target_price(effective, mult_value, inputs)
    upside = _upside(target_price, inputs.current_price)

    earnings_basis = inputs.earnings_basis or {}
    if effective == "cz" and earnings_basis.get("source") == "biznesradar_forecasts":
        year = earnings_basis.get("year")
        year_suffix = f" {year}" if year else ""
        result_driver = f"EPS z konsensusu analityków BiznesRadar{year_suffix}"
        result_assumption = (
            f"Założenie: EPS oparty na konsensusie analityków BiznesRadar{year_suffix}; "
            "to oczekiwanie rynku/analityków, nie zrealizowany wynik"
        )
    else:
        result_driver = "Wynik (zysk / EBITDA / wartość księgowa) utrzymany na bieżącym poziomie"
        result_assumption = (
            "Założenie: brak zmiany wyniku — projekcja czysto wycenowa (sama rewersja "
            "mnożnika)"
        )

    drivers = [
        "Rewersja mnożnika wyceny do poziomu z własnej historii spółki",
        result_driver,
    ]
    assumptions = [
        f"Założenie: mnożnik {mult_label} wraca do poziomu „{quartile_phrase}” "
        "(porównanie do WŁASNEJ historii, nie do rynku/branży)",
        result_assumption,
    ]

    if target_price is None or mult_value is None:
        # Labelled gap — NEVER a fabricated price (plan §Risks).
        note = gap_note or price_note or "Brak danych do wyznaczenia ceny docelowej."
        basis = "brak policzalnej własnej historii mnożnika — ceny nie wyznaczono"
        narrative = (
            f"{_KIND_LEAD[kind]}: {mult_label} miałby wrócić do poziomu "
            f"„{quartile_phrase}”, ale brak danych do wyznaczenia ceny docelowej "
            "(luka danych — patrz założenia)."
        )
        assumptions = [f"Luka danych: {note}"] + assumptions
        return Scenario(
            id=sid,
            kind=kind,
            label=label,
            probability=prob,
            narrative=narrative,
            target_multiple={"type": effective, "value": None, "basis_label": basis},
            target_price=None,
            implied_upside_pct=None,
            horizon=dict(_DEFAULT_HORIZON),
            drivers=drivers,
            assumptions=assumptions,
            company_outcome=_company_outcome(kind, effective),
        )

    basis = f"{quartile_phrase} {mult_label} {_fmt(mult_value)} (n={n})"
    if inputs.current_price is None:
        # WP5 fix: a target price CAN be computable (EPS/book value/EBITDA known)
        # while the current price is not (e.g. every price source failed this
        # refresh, or a fresh listing) — `upside` is honestly `None` from
        # `_upside()`'s own guard, but formatting it via `_fmt_signed`/`_fmt`
        # (which assume a number) used to crash the whole dossier. Never
        # fabricate a comparison; label the gap instead (same honesty rule as
        # a missing multiple driver, just for the OTHER side of the fraction).
        narrative = (
            f"{_KIND_LEAD[kind]} do poziomu „{quartile_phrase}” ({mult_label} "
            f"{_fmt(mult_value)}) przy utrzymanym wyniku — cena docelowa "
            f"{_fmt(target_price)} zł; potencjału wobec bieżącego kursu nie "
            "wyznaczono (brak aktualnej ceny)."
        )
        assumptions = [
            "Luka danych: brak bieżącego kursu — potencjału (upside) wobec "
            "aktualnej ceny nie wyznaczono."
        ] + assumptions
    else:
        narrative = (
            f"{_KIND_LEAD[kind]} do poziomu „{quartile_phrase}” ({mult_label} "
            f"{_fmt(mult_value)}) przy utrzymanym wyniku — cena docelowa "
            f"{_fmt(target_price)} zł, {_fmt_signed(upside)}% wobec bieżącego kursu "
            f"{_fmt(inputs.current_price)} zł."
        )
    if gap_note:  # C/Z fallback in play — say so on the scenario too.
        assumptions = [f"Uwaga: {gap_note}"] + assumptions
    return Scenario(
        id=sid,
        kind=kind,
        label=label,
        probability=prob,
        narrative=narrative,
        target_multiple={"type": effective, "value": mult_value, "basis_label": basis},
        target_price=target_price,
        implied_upside_pct=upside,
        horizon=dict(_DEFAULT_HORIZON),
        drivers=drivers,
        assumptions=assumptions,
        company_outcome=_company_outcome(kind, effective),
    )


def weighted_expected(scenarios: list, current_price: float | None):
    """Probability-weighted expected price (Σ pᵢ·target_priceᵢ over priced
    scenarios) and its implied upside vs the current price. `None` when no
    scenario carries a price."""
    rows = [
        (s["probability"] if isinstance(s, dict) else s.probability,
         s["target_price"] if isinstance(s, dict) else s.target_price)
        for s in scenarios
    ]
    # A partial priced set is not an unconditional expected value. Returning
    # None is safer than silently dropping probability mass or renormalizing
    # the remaining paths into a different question.
    if any(p is not None and tp is None and p > 0 for p, tp in rows):
        return None, None
    priced = [(p, tp) for p, tp in rows if tp is not None and p is not None]
    if not priced:
        return None, None
    wprice = round(sum(p * tp for p, tp in priced), 2)
    wupside = _upside(wprice, current_price)
    return wprice, wupside


def priced_probability_mass(scenarios: list) -> float:
    """Return the probability mass with a deterministic target price."""
    return round(
        sum(
            (s["probability"] if isinstance(s, dict) else s.probability)
            for s in scenarios
            if (s["target_price"] if isinstance(s, dict) else s.target_price) is not None
            and (s["probability"] if isinstance(s, dict) else s.probability) is not None
        ),
        4,
    )


def verify_scenario_simulation(scenario_set: dict) -> dict:
    """Verify deterministic scenario arithmetic without granting strict approval.

    This is a mechanical simulation check. Source lineage, point-in-time
    validity and representative template coverage still belong to
    ``verifier_strict`` and the priced-outcome gate.
    """
    checks: list[dict] = []

    def add(check_id: str, verdict: str, evidence: str) -> None:
        checks.append({"id": check_id, "verdict": verdict, "evidence": evidence})

    rows = scenario_set.get("scenarios")
    if not isinstance(rows, list) or not rows:
        add("scenario_rows", "fail", "Brak scenariuszy do sprawdzenia.")
    else:
        ids = [row.get("id") for row in rows]
        add(
            "scenario_ids_unique",
            "pass" if len(ids) == len(set(ids)) else "fail",
            "Identyfikatory scenariuszy są unikalne."
            if len(ids) == len(set(ids))
            else "Powtórzone identyfikatory scenariuszy.",
        )
        required_kinds = {"negative", "base", "positive"}
        present_kinds = {row.get("kind") for row in rows}
        add(
            "required_kinds_present",
            "pass" if required_kinds.issubset(present_kinds) else "fail",
            "Obecne są warianty negative/base/positive."
            if required_kinds.issubset(present_kinds)
            else "Brakuje jednego z wymaganych wariantów.",
        )
        numeric_values = [
            row.get(field)
            for row in rows
            for field in ("probability", "target_price", "implied_upside_pct")
            if row.get(field) is not None
        ] + [
            scenario_set.get("current_price"),
            scenario_set.get("weighted_expected_price"),
            scenario_set.get("weighted_expected_upside_pct"),
        ]
        finite = all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
            for value in numeric_values
            if value is not None
        )
        add(
            "numbers_finite",
            "pass" if finite else "fail",
            "Wartości liczbowe są skończone."
            if finite
            else "Wynik zawiera NaN, nieskończoność albo nieliczbową wartość.",
        )
        probabilities_valid = all(
            isinstance(row.get("probability"), (int, float))
            and not isinstance(row.get("probability"), bool)
            and isfinite(row["probability"])
            and 0 <= row["probability"] <= 1
            for row in rows
        )
        add(
            "probabilities_in_range",
            "pass" if probabilities_valid else "fail",
            "Prawdopodobieństwa mieszczą się w zakresie 0–1."
            if probabilities_valid
            else "Prawdopodobieństwo jest poza zakresem 0–1.",
        )
        computed_priced_mass = priced_probability_mass(rows)
        add(
            "priced_probability_mass",
            "pass" if isclose(computed_priced_mass, 1.0, abs_tol=0.0001) else "needs-human",
            f"Policzalna masa prawdopodobieństwa = {computed_priced_mass:.4f}; "
            f"niepoliczalna = {round(1.0 - computed_priced_mass, 4):.4f}.",
        )
        if (
            scenario_set.get("weighted_expected_price") is not None
            and not isclose(computed_priced_mass, 1.0, abs_tol=0.0001)
        ):
            add(
                "unpriced_probability_policy",
                "fail",
                "Wartość oczekiwana nie może pomijać niepoliczalnej masy prawdopodobieństwa.",
            )
        else:
            add(
                "unpriced_probability_policy",
                "pass",
                "Niepełna masa nie jest prezentowana jako bezwarunkowa wartość oczekiwana.",
            )
        probabilities = [row.get("probability") for row in rows]
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in probabilities):
            total = sum(probabilities)
            add(
                "probability_sum",
                "pass" if isclose(total, 1.0, abs_tol=0.0001) else "fail",
                f"Suma prawdopodobieństw = {total:.4f}; oczekiwano 1.0000.",
            )
        else:
            add("probability_sum", "fail", "Prawdopodobieństwa muszą być liczbami.")

        current_price = scenario_set.get("current_price")
        priced = [
            row for row in rows
            if isinstance(row.get("probability"), (int, float))
            and isinstance(row.get("target_price"), (int, float))
        ]
        expected_price = scenario_set.get("weighted_expected_price")
        if priced and isinstance(expected_price, (int, float)):
            computed_price = round(
                sum(row["probability"] * row["target_price"] for row in priced), 2
            )
            add(
                "weighted_price_reconciliation",
                "pass" if isclose(computed_price, expected_price, abs_tol=0.01) else "fail",
                f"Policzono {computed_price:.2f}; zapisano {expected_price:.2f}.",
            )
        else:
            add(
                "weighted_price_reconciliation",
                "needs-human",
                "Brak pełnych danych do niezależnego odtworzenia ceny ważonej.",
            )

        expected_upside = scenario_set.get("weighted_expected_upside_pct")
        if isinstance(expected_price, (int, float)) and isinstance(current_price, (int, float)) and isinstance(expected_upside, (int, float)) and current_price != 0:
            computed_upside = round((expected_price / current_price - 1.0) * 100.0, 2)
            add(
                "weighted_upside_reconciliation",
                "pass" if isclose(computed_upside, expected_upside, abs_tol=0.01) else "fail",
                f"Policzono {computed_upside:.2f}%; zapisano {expected_upside:.2f}%.",
            )
        else:
            add(
                "weighted_upside_reconciliation",
                "needs-human",
                "Brak pełnych danych do odtworzenia ważonego potencjału.",
            )

        row_failures = []
        for row in rows:
            target = row.get("target_price")
            current = current_price
            upside = row.get("implied_upside_pct")
            if target is None or current is None or upside is None or current == 0:
                continue
            computed = round((target / current - 1.0) * 100.0, 2)
            if not isclose(computed, upside, abs_tol=0.01):
                row_failures.append(row.get("kind", "unknown"))
        add(
            "row_upside_reconciliation",
            "pass" if not row_failures else "fail",
            "Wiersze scenariuszy mają spójny potencjał."
            if not row_failures
            else f"Niespójne wiersze: {', '.join(row_failures)}.",
        )

        outcome_failures = []
        for row in rows:
            outcome = row.get("company_outcome") or {}
            expected_direction = {"negative": "negative", "base": "neutral", "positive": "positive"}.get(row.get("kind"))
            if expected_direction and outcome.get("direction") != expected_direction:
                outcome_failures.append(row.get("kind", "unknown"))
            if outcome.get("mode") == "priced":
                outcome_failures.append(f"{row.get('kind', 'unknown')}:priced")
        add(
            "outcome_mode_gate",
            "pass" if not outcome_failures else "fail",
            "Wyniki spółki pozostają jakościowe przed priced-outcome gate."
            if not outcome_failures
            else f"Nieprawidłowy outcome: {', '.join(outcome_failures)}.",
        )

    framing = str(scenario_set.get("framing") or "").lower()
    disclaimer = str(scenario_set.get("disclaimer") or "").lower()
    safety_ok = (
        "nie sygnał" in framing
        and ("nie jest rekomendacja" in disclaimer or "nie jest rekomendacją" in disclaimer)
    )
    add(
        "safety_language",
        "pass" if safety_ok else "fail",
        "Framing i disclaimer jasno odróżniają analizę od sygnału inwestycyjnego."
        if safety_ok
        else "Brak wymaganego framingu/disclaimera.",
    )

    if scenario_set.get("engine") == "deterministic":
        add("deterministic_engine", "pass", "Źródłem symulacji jest silnik deterministyczny.")
    else:
        add(
            "deterministic_engine",
            "needs-human",
            "Wynik nie pochodzi wyłącznie z silnika deterministycznego.",
        )

    verdicts = {check["verdict"] for check in checks}
    if "fail" in verdicts:
        status = "failed"
    elif "needs-human" in verdicts:
        status = "needs-human"
    else:
        status = "math_passed"
    return {
        "status": status,
        "checks": checks,
        "summary": (
            "Deterministyczna symulacja przechodzi kontrolę matematyczną; "
            "źródła, point-in-time i priced outcomes nadal wymagają verifier_strict."
            if status == "math_passed"
            else "Symulacja wymaga dalszej kontroli przed użyciem jako priced outcome."
        ),
        "strict_verification_required": True,
    }


def scenario_quality_warnings(scenario_rows: list, weighted_upside: float | None) -> list[str]:
    """Warnings about how to read the scenario set.

    The internal `positive` kind means "upper quartile reversion path", not
    guaranteed positive return. When every priced path is still below the
    current price, surface that explicitly so CBF-like cases cannot be read as a
    recommendation hidden behind a green label.
    """
    upsides = []
    for row in scenario_rows:
        value = row.get("implied_upside_pct") if isinstance(row, dict) else row.implied_upside_pct
        if isinstance(value, (int, float)):
            upsides.append(float(value))

    warnings: list[str] = []
    if upsides and max(upsides) <= 0:
        warnings.append(
            "Wszystkie policzalne warianty mają ujemny potencjał; wariant "
            "górnego kwartylu nie oznacza dodatniego scenariusza."
        )
    if weighted_upside is not None and weighted_upside < 0:
        warnings.append(
            "Wartość oczekiwana scenariuszy jest ujemna; traktuj wynik jako "
            "ostrzeżenie o punkcie wejścia, nie jako pozytywną tezę."
        )
    return warnings


def _driver_assumption_detail(item: dict, *, applied: bool, note: str) -> dict:
    """Keep the original provenance next to the deterministic decision."""
    return {
        "key": item.get("key", ""),
        "value": item.get("value"),
        "unit": item.get("unit"),
        "provenance": item.get("provenance", "human_assumption"),
        "source_ref": item.get("source_ref"),
        "rationale": item.get("rationale", ""),
        "applied": applied,
        "note": note,
    }


def _apply_driver_assumptions(
    inputs: ScenarioInputs, items: list[dict]
) -> tuple[ScenarioInputs, list[dict], list[dict]]:
    """Apply the small, typed RT4.3b driver allow-list to a copy of inputs.

    Model suggestions stay visible but never change math until a human turns
    them into an evidence or human-assumption item. This makes the approval
    boundary explicit even when a whole assumption set is marked approved.
    """
    overlay = replace(inputs)
    applied: list[dict] = []
    ignored: list[dict] = []
    for raw in items:
        item = raw if isinstance(raw, dict) else {}
        key = item.get("key")
        provenance = item.get("provenance")
        if provenance == "model_suggestion":
            ignored.append(
                _driver_assumption_detail(
                    item,
                    applied=False,
                    note="Sugestia modelu wymaga jawnego przyjęcia przez człowieka.",
                )
            )
            continue
        target = _ASSUMPTION_DRIVER_KEYS.get(key)
        value = item.get("value")
        if target is None:
            ignored.append(
                _driver_assumption_detail(
                    item,
                    applied=False,
                    note="Klucz nie ma jeszcze deterministycznego równania.",
                )
            )
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            ignored.append(
                _driver_assumption_detail(
                    item, applied=False, note="Wartość sterownika nie jest liczbą."
                )
            )
            continue
        if target in {"eps", "book_value", "ebitda_ttm", "shares_outstanding"} and value <= 0:
            ignored.append(
                _driver_assumption_detail(
                    item, applied=False, note="Wartość sterownika musi być dodatnia."
                )
            )
            continue
        if target == "shares_outstanding" and int(value) != value:
            ignored.append(
                _driver_assumption_detail(
                    item, applied=False, note="Liczba akcji musi być całkowita."
                )
            )
            continue
        setattr(overlay, target, int(value) if target == "shares_outstanding" else float(value))
        applied.append(
            _driver_assumption_detail(
                item, applied=True, note="Zastosowano w deterministycznej wrażliwości."
            )
        )
    return overlay, applied, ignored


def build_driver_sensitivity(
    inputs: ScenarioInputs,
    profile: base.StrategyProfile,
    approved_assumption_sets: list[dict] | None = None,
) -> dict:
    """Project approved case drivers without replacing the base valuation.

    Each approved negative/base/positive set is applied to a copied
    ``ScenarioInputs`` and re-run through the pure engine. The result compares
    that deterministic projection with the unchanged dossier scenario row.
    Draft/rejected sets are filtered here as a second safety boundary, and
    model suggestions are reported as ignored rather than priced.
    """
    approved = [
        row for row in (approved_assumption_sets or [])
        if isinstance(row, dict)
        and row.get("status") == "approved"
        and row.get("scenario_kind") in {"negative", "base", "positive"}
    ]
    if not approved:
        return {
            "status": "none",
            "note": "Brak zatwierdzonych zestawów sterowników do policzenia wrażliwości.",
            "rows": [],
        }

    baseline = build_scenario_set(inputs, profile).to_dict()
    baseline_by_kind = {row["kind"]: row for row in baseline["scenarios"]}
    rows: list[dict] = []
    for assumption_set in approved:
        kind = assumption_set["scenario_kind"]
        overlay, applied, ignored = _apply_driver_assumptions(
            inputs, assumption_set.get("assumptions") or []
        )
        projected = build_scenario_set(overlay, profile).to_dict()
        projected_row = next(row for row in projected["scenarios"] if row["kind"] == kind)
        baseline_row = baseline_by_kind[kind]
        baseline_price = baseline_row["target_price"]
        projected_price = projected_row["target_price"]
        baseline_upside = baseline_row["implied_upside_pct"]
        projected_upside = projected_row["implied_upside_pct"]
        rows.append(
            {
                "scenario_kind": kind,
                "label": assumption_set.get("label", kind),
                "baseline_target_price": baseline_price,
                "sensitivity_target_price": projected_price if applied else baseline_price,
                "target_price_delta": (
                    round(projected_price - baseline_price, 2)
                    if applied and projected_price is not None and baseline_price is not None
                    else None
                ),
                "baseline_upside_pct": baseline_upside,
                "sensitivity_upside_pct": projected_upside if applied else baseline_upside,
                "upside_delta_pct": (
                    round(projected_upside - baseline_upside, 2)
                    if applied and projected_upside is not None and baseline_upside is not None
                    else None
                ),
                "applied": applied,
                "ignored": ignored,
            }
        )
    return {
        "status": "applied" if any(row["applied"] for row in rows) else "human_review_required",
        "note": (
            "Wrażliwość jest liczona deterministycznie na kopii wejść. Nie zmienia "
            "bazowej ceny; szkice, odrzucone zestawy i sugestie modelu nie są wyceniane."
        ),
        "rows": rows,
    }


def build_scenario_set(
    inputs: ScenarioInputs, profile: base.StrategyProfile
) -> ScenarioSet:
    """Compose the deterministic scenario set for `profile` from `inputs`.

    Selects the sector-appropriate multiple, resolves it (with an honest C/Z
    fallback + gap label when a driver is missing), builds the negative/base/
    positive reversion trio off the own-history quartiles, and computes the
    set-level probability-weighted EV. Probabilities sum to 1.00 by construction.
    Event scenarios are NOT emitted here — the deterministic engine cannot invent
    catalysts (that is the AI refiner's honest, key-gated job).
    """
    company = inputs.thesis_inputs.insights
    preferred = select_valuation_multiple(company.sector_group, profile)
    effective, hist, gap_note = _resolve_multiple(inputs, preferred)

    scenarios = [
        _build_scenario(spec, effective, hist, inputs, gap_note)
        for spec in _SCENARIO_SPECS
    ]
    wprice, wupside = weighted_expected(scenarios, inputs.current_price)
    warnings = scenario_quality_warnings(scenarios, wupside)

    return ScenarioSet(
        scenarios=scenarios,
        valuation_multiple=effective,
        current_price=inputs.current_price,
        weighted_expected_price=wprice,
        weighted_expected_upside_pct=wupside,
        framing=FRAMING,
        disclaimer=thesis.DISCLAIMER,
        priced_probability_mass=priced_probability_mass(scenarios),
        quality_warnings=warnings,
        engine="deterministic",
    )
