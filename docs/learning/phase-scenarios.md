# Stage SC — Scenario simulation engine + AI valuation agent

## What was built
On top of the one-shot investment thesis (stage TH), each stock now gets a
**small set of scenarios** — negative/base/positive, each a *"multiple reverts
to this quartile of the company's own history"* projection with a target price,
an implied upside, a repricing horizon and a probability (Σ=1). An optional
Claude-API refiner may add company-specific *event* scenarios (grounded in the
dossier's own gaps) and reword narratives, always behind a deterministic
no-key fallback. On top of the scenario set, an **AI valuation agent** reads
everything (dossier + scenarios) and produces a stock-potential read: how much
upside, at what confidence, and what would change the assessment. Both extend
`thesis_ai.py`'s pattern; rendered in `ScenariosPanel.tsx` directly below
`ThesisPanel` — an analysis entrance, never a signal.

## Concepts worth understanding

**A scenario set is a strategy-pattern *projector*, not a simulator**
(`services/scenarios.py`, `build_scenario_set(inputs, profile) -> ScenarioSet`)
— despite the stage's name, this is **not** Monte-Carlo; it is three fixed,
named projections (reversion to Q1/median/Q3 of the company's own multiple
history) computed once, deterministically. Think of `ScenarioSet` as an
immutable DTO collection a C# method would return — `record`-style
dataclasses with `to_dict()` mirroring the API's Pydantic shape exactly, the
same pattern as `InvestmentThesis` in stage TH.

**Generalising a metric via a thin alias** (`metrics.compute_multiple_history`)
— stage TH only computed *own-history* stats for C/Z. Scenarios need the same
math for C/WK and EV/EBITDA too, so the function was generalised and the old
name kept as `compute_pe_history = ` an alias returning an identical object.
This is the Python equivalent of widening a method's parameter type while
keeping a legacy overload for source compatibility — nothing that already
called `compute_pe_history` had to change.

**AI agents are decorators over pure compute, with a widened allow-list**
(`services/scenarios_ai.py`, `services/valuation_ai.py`) — same shape as
`thesis_ai.py`: an injectable transport `(messages, model) -> dict`, bounded
rounds, a JSON-file cache, a deterministic no-key fallback that never raises.
The fabrication guard is *wider* here because this layer legitimately
**computes new numbers** (target prices, upsides, EV) instead of only reusing
thesis numbers — so the allowed-set is `sourced inputs ∪ engine-computed
numbers ∪ cited worked-case comparables`. In C# terms: a decorator wrapping a
pure service, with an allow-list validator between the decorator and the
network call — any number the model invents outside that list rejects the
whole round and the caller silently gets the last good (or deterministic)
result back.

**Probability renormalisation ≈ normalising weights before a weighted
average** — when the AI adds an event scenario, the returned probabilities
rarely sum to exactly 1 (e.g. 1.2). The engine divides every weight by the
total and clamps to `[0, 1]`, then asserts `|Σ−1| ≤ 0.01`. This is the same
idiom as normalising weights before `Σ wᵢxᵢ` in any weighted-average
calculation — trust the shape of the model's answer, not its arithmetic.

**A confidence heuristic is just a small rules table** (`valuation_ai.py`,
`_confidence_level`) — two integers (how many key indicators are computable,
how many own-history observations exist) map to `low`/`medium`/`high` through
fixed, named thresholds, exactly like a lookup table or a C# `switch`
expression over ranges. The AI may reword *why* but never *which enum value* —
the level is re-imposed after every round, same trick as the thesis engine's
weights.

**A green test suite is not a correctness proof** — WP5 hand-built one more
scenario input reusing DEC's real fixture numbers (own C/Z history + EPS, but
no price — a gap stage TH had already documented) and hit a real `TypeError`:
the code only labelled a gap when the *target price* was missing, not when
the *current price* was missing while a target price was still computable.
13/13 green tests had never exercised that specific combination. Fixed with a
three-line guard + one new regression test — a reminder that hand-checking one
more edge case, even after the suite is green, is how these are found.

## Where to look
`services/scenarios.py` (`ScenarioInputs`/`Scenario`/`ScenarioSet`,
`select_valuation_multiple`, `_build_scenario`) → `tests/test_scenarios.py`
(14 checks, incl. the WP5 regression) → `services/scenarios_ai.py` →
`tests/test_scenarios_ai.py` (14 checks, stub transport) →
`services/valuation_ai.py` (`_confidence_level`, `assess_potential`) →
`tests/test_valuation_ai.py` (25 checks, incl. corpus integrity) →
`components/ScenariosPanel.tsx`. Spec: `docs/plan-stage-scenarios.md`;
validation + the WP5 defect write-up: `docs/validation-scenarios.md`.
