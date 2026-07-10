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

**Approved inputs need an explicit bridge** — RT4.3b keeps the base multiple
valuation unchanged and runs typed `eps`, book value, EBITDA, share-count and
net-cash overlays on copied `ScenarioInputs`. Evidence and human assumptions
can produce a deterministic sensitivity row; model suggestions, unsupported
keys, drafts and rejected sets stay visible but inactive. This mirrors a C#
service boundary where an immutable input record is projected into a separate
what-if result instead of mutating the saved aggregate.

RT4.3c reuses the existing forecast function as a versioned pilot template for
industrial and consumer companies. The bridge is intentionally additive: it
shows projected P&L and the operating target beside the existing multiple-only
baseline, so a missing working-capital or cash-conversion equation cannot hide
inside a confident-looking price.

RT4.3d demonstrates the evidence boundary for cash conversion: operating CF
and capex can be surfaced from canonical cash-flow rows, but a single latest
balance snapshot cannot prove receivable or inventory movement. The UI reports
the partial ratio and keeps that working-capital gap visible, like a C# DTO
with a nullable field rather than silently defaulting it to zero.

The working-capital follow-up uses two comparable balance periods and reports
the change in receivables plus inventory, including its cash direction. If one
period or one canonical row is absent, the result stays a gap. This is the
important distinction between a measured delta and an invented FCF forecast.

The FCF bridge now makes that distinction executable: projected net profit,
depreciation, the measured working-capital cash effect and capex are combined
only for an approved operating what-if row. Historical operating CF is shown
separately because it already contains working-capital movement. This is the
same separation a C# domain service would use between an observed ledger and
a projected record.

RT4.3e keeps the FCF lens deliberately opt-in. A user must approve capex,
working-capital change and the FCF multiple before the system can produce a
price. In C# terms, the valuation method has a required input object and
returns a validation result instead of silently filling missing properties.
