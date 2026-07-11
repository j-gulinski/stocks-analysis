# Scored scenario judgment — Codex planning brief

**Status: planning input (requirements brief), not a work-package plan.** This
file states *what* the user wants so a later Codex session can break it into
tasks and an implementation plan. It does not prescribe the implementation.
Where it conflicts with `docs/north-star.md`, north-star wins; where it touches
strategy meaning, `docs/strategy-malik.md` wins; model discipline follows
`docs/project-guardrails.md` and `AGENTS.md` §Operating policy.

## Intent

The user makes **every** buy/sell/hold decision. Inside the app, Codex is an
opinionated analyst that **calculates the possibilities and their outcomes** and
commits to a scored read, using its reasoning as much as possible at each step
through the existing `stock-*` skills. The goal is not a signal; it is a
transparent, calibrated map of what could happen, how likely each path is, and
what each path does to the numbers.

Concretely, for a researched company Codex must produce:

- **multiple scenario outcomes**, each with a **probability (%)** and its
  modelled effect on **forward C/Z**, other markers (C/WK, marża na sprzedaży
  brutto, dźwignia operacyjna, gotówka netto/debt, EPS/forecast), **price**, and
  the company's **future potential**;
- an **overall conviction score (1–100)** plus confidence, derived from the
  scenario set and the strategy fit — the "measurable feedback" number;
- the **thought process**: drivers, assumptions and evidence behind each
  probability and each projected delta.

**Deliver the analysis, don't defer it.** Codex pushes the work as far as the
evidence allows and always returns the full computed, verified read — scenarios,
probabilities, quantified marker/price outcomes and the conviction score. It does
**not** stop at a bare "human input needed" that withholds the analysis. When
primary evidence is incomplete, the result is still produced and clearly labelled
*provisional / assumption-based*, with the gaps named — the user reads the whole
picture and decides. "Verified" here means the calculations, no-look-ahead and
no-fabrication checks passed, not that the analysis was held back.

## Non-negotiable constraints (carry into every task)

1. **Human owns the decision.** No auto-add to watchlist/positions, no trades,
   no "recommendation to buy". The score informs; it never instructs.
2. **Deterministic markers stay in Python** (`services/`), unit-tested against
   hand-checked numbers. Codex does **not** invent base C/Z, price, margins or
   cash. Codex assigns probabilities and projects *deltas* from an explicit,
   stated assumption set; the base values it starts from are the computed ones.
3. **Verifier owns the final scored fields.** A drafting-model score is never
   authoritative. A separate strict verifier (strongest available model) reads
   the frozen dossier/source manifest independently and owns the saved
   probabilities, scenario validity, conviction score and confidence, per the
   existing `stock-deep-analysis` gate.
4. **Evidence-grounded.** Every probability and projected delta cites its
   drivers/assumptions; unknowns are recorded as gaps and routed to
   `verify_next`, never fabricated. Forum/author reputation and company size do
   not move the score by themselves.
5. **Calibrated, not decorative.** Predicted probabilities are stored with an
   `as_of` and later scored against realised outcomes; the score earns trust
   only through calibration (see §Calibration).
6. **Maximum analysis, human decides — never a bare block.** Always compute and
   present the full scored read; downgrade confidence and mark scenarios
   *provisional* when evidence is thin instead of returning an empty
   `needs-human`. The verifier validates and annotates the read — it does not
   suppress it. Reserve a blocked/`needs-human` state only for genuine safety or
   integrity failures (fabrication risk, failed math or look-ahead checks), and
   even then show what was computed plus the explicit reason.

## Pipeline → skills → model tier

Run the judgment through the existing skills, using Codex reasoning at each
step. Model tiers follow `AGENTS.md` §Operating policy (names may be substituted
for the closest available model at the same reasoning level).

| Phase | Skill(s) | Model tier | Produces |
|---|---|---|---|
| **Explore** — order the queue, surface candidates | `stock-candidate-scout`, discovery | Default · GPT-5.6 Terra (high) | ranked, source-labelled leads |
| **Collect** — dossier + source-completion loop, primary evidence | `stock-pre-session-brief`, `stock-deep-analysis` (source pass) | Default · GPT-5.6 Terra (high); GPT-5.3 for purely mechanical sub-loops | frozen dossier + source manifest, gaps recorded |
| **Aggregate / group / value** — organise evidence, compute strategy fit, value vs own history | `stock-deep-analysis` (analysis pass), Malik lens (`skill/`) | High · GPT-5.6 Sol (high) | thesis, checklist read, valuation-vs-history, prescore/alignment inputs |
| **Explore outcomes** — build the scenario set, assign probabilities, project marker/price deltas | `stock-deep-analysis` (scenario pass), `stock-backtest-review` for base rates | High · GPT-5.6 Sol (high); Hardest · Sol (ultra) only on escalation | scenario outcomes with probability + quantified impacts |
| **Score + verify** — own final probabilities, conviction score, confidence | `stock-result-verifier`, `stock-verifier` | High/Hardest · Sol (high; ultra on escalation), `verifier_strict` | verified scored read; *provisional* + labelled when evidence is thin; blocked only on integrity/safety failure |

Deterministic base markers are computed by Python services throughout and passed
in frozen; the models reason *on top of* them.

## Output contract (evolve from the current one)

Evolve the existing `stock-deep-analysis` `output` object rather than adding a
parallel structure. The user has granted **full refactor latitude**: if the
current shape (`company_score`/`alignment_score`, `prediction`, `potential`,
`result_quality.scenario_validity`) cannot cleanly carry the below, refactor it
completely — and apply the same latitude to related features (dossier, scenario
engine, journal, backtest) so the model does not fight a legacy shape.

### Per-outcome scenario object (list, mutually exclusive, probabilities ≈ 100%)

| Field | Meaning |
|---|---|
| `id` / `label` | short handle; Polish domain label allowed (e.g. `baza`, `byczy – katalizator X`, `niedźwiedzi – one-off nie wraca`) |
| `narrative` | the mechanism: what has to happen for this path |
| `probability_pct` | Codex-assigned, evidence-anchored, calibrated over time |
| `horizon` | e.g. next report / 12m |
| `drivers` / `assumptions` | explicit list with `source_ids`; the "thought process" |
| `marker_impact` | per marker `{from, to, delta, basis}` for forward **C/Z**, C/WK, marża na sprzedaży brutto, dźwignia operacyjna, gotówka netto/debt, EPS/forecast |
| `price_impact` | `{return_pct or target, range_pct, basis}` |
| `future_potential` | qualitative + `value_pct`/`range_pct` (evolve current `potential`) |
| `outcome_score` (optional) | attractiveness of this specific path, if useful |

### Overall (aggregate) object

| Field | Meaning |
|---|---|
| `conviction_score` | **1–100** headline; `{value, scale, basis}`; blends strategy fit + evidence quality + probability-weighted upside/risk. Evolves `company_score`/`alignment_score`. |
| `confidence` | how firm the read is given evidence completeness/gaps |
| `expected` | probability-weighted summary: expected return, expected forward C/Z, distribution/upside–downside frame |
| `key_falsifiers` | what would flip the dominant scenario |
| `verify_next` | dated re-checks (catalyst, backlog, governance, cash-flow quality, one-off durability) |

Keep the existing `executive_read`, `thesis`, `evidence`, `risks`,
`forum_context`, `research_resolution`, `backtest_context`, `action_plan` and
the `verification` object; the verifier still owns the authoritative numbers.

## Scoring semantics

- The **1–100 conviction score** is the overall "measurable feedback" number and
  is decision-support, not a target to maximise. Per the user: per-outcome reads
  first (each possibility with its probability and calculated outcome), then an
  overall score on top.
- It must be **reproducible from its inputs** (strategy-fit/prescore, evidence
  quality, probability-weighted upside vs downside) so a reader can see *why* it
  is what it is. No opaque single number.
- Company size/sweet-spot fit is strategy context, not a score input by itself.

### Workbench score base v1

`analysis_scoring.build_codex_score_base` supplies a frozen, deterministic
input only to the Codex analysis and strict-verifier flow. It is deliberately
not included in the general Dossier/UI response as a second rating. Its current
weights reflect the user's priorities: revenue/profit growth 30, durability and
profit quality 20, balance/cash 15, valuation against the company's own
history 15, catalyst/business quality 15 and capital allocation 5. Catalyst and
business quality are explicit research gaps until primary evidence supports
them. One-off-profit quality caps the partial signal at 50; loss plus net debt
caps it at 40. The final verifier-owned conviction score may use the base with
source-grounded qualitative evidence and probability-weighted scenario
outcomes, and must retain the base in its frozen input snapshot.

## Calibration (measurable feedback loop)

- Persist each scenario set with `as_of`, predicted `probability_pct`, projected
  deltas and the conviction score.
- After each material update/report, `stock-result-verifier` / the backtest
  layer compares realised outcome to the predicted set; compute a calibration
  metric (e.g. Brier-style on scenario probabilities, hit/miss on marker
  direction) and surface it in the learning notes (`docs/learning.md`).
- Calibration history feeds trust in the score over time and closes the
  north-star "honest feedback on what the user learned" loop. This is honest
  point-in-time evaluation (no look-ahead), gated by `verifier_strict`.

## Open questions for Codex to resolve during planning

1. Scenario cardinality — fixed (base/bull/bear) or variable per case? How are
   probabilities normalised and mutual-exclusivity enforced?
2. Exact conviction-score formula and weights; how the Malik `prescore`/rubric
   maps in, and whether the rubric needs rescaling to 0–100.
3. Storage/schema changes and migration path from the current `output` shape
   (evolve vs full refactor) — and the same decision for the scenario engine.
4. How much marker projection is deterministic (Python does the arithmetic from
   Codex's stated assumptions) vs model-stated, to keep numbers checkable.
5. UI surface: how per-outcome possibilities + the overall score are shown
   without implying a trade instruction.
6. Calibration metric choice and how it feeds back into confidence.

## Direction-level acceptance

A researched company yields: a small set of mutually-exclusive scenarios, each
with a probability and calculated impact on C/Z, other markers, price and future
potential; an overall 1–100 conviction score with confidence and a transparent
basis; all evidence-grounded, verifier-owned, stored point-in-time, and later
scored for calibration — with the buy/sell/hold decision left entirely to the
user.
