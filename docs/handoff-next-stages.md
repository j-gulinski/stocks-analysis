# Codex next-stages handoff — 2026-07-11

Session handoff so a fresh Codex thread can continue seamlessly. This is a
**planning/handoff artifact**, not the execution list — `TASKS.md` stays
authoritative for status, `docs/north-star.md` for product direction,
`docs/plan-scored-scenario-judgment.md` for the scored-analysis contract, and
`AGENTS.md` for working rules. If anything here conflicts with those, they win.

## 1. Where Codex stopped

- Last commit: `a4cacbc Plan north star delivery slices`. Codex **planned** the
  north-star delivery slices (NS.2–NS.4) but did not implement them; they are the
  next unchecked items in `TASKS.md` §Execution sequence (items 20–22).
- Uncommitted work from this session sits on top (docs only, no code):
  north-star evolved to scored decision-support, the scored-judgment planning
  brief, an `AGENTS.md` index pointer, a `CHANGELOG.md` entry, and a few tidy-up
  fixes (see §5). Run `git status` before committing.
- A parallel Codex process reset the working tree once mid-session; coordinate /
  commit to avoid clobbering.

## 2. Durable decisions from this session (binding going forward)

1. **Product direction = scored scenario judgment.** Inside the app Codex is an
   opinionated analyst that computes possibilities and their outcomes and commits
   to a scored read; **the user makes every buy/sell/hold decision.** Contract:
   `docs/plan-scored-scenario-judgment.md`; direction: `docs/north-star.md`.
2. **Priority: scored-analysis FIRST** (explicit user decision), ahead of
   NS.2–NS.4. The north-star triage loop follows.
3. **No bare "human input needed".** Push the analysis as far as the evidence
   allows and always return the full computed, verified read (scenarios,
   probabilities, quantified C/Z + marker + price outcomes, conviction score).
   When evidence is incomplete, produce the result anyway and label it
   *provisional / assumption-based* with gaps named — do not withhold it.
   Deterministic base numbers still come only from real data (no invented
   financials); projected deltas come from explicit stated assumptions. Reserve a
   blocked/`needs-human` state for genuine safety/integrity failures (fabrication
   risk, failed math or look-ahead checks), and even then show what was computed
   plus the reason.
4. **Model routing is settled = CX.15g.** Testing/mechanical = GPT-5.3·high;
   basic implementation = Luna·medium; default = Terra·high; high-complexity =
   Sol·high; hardest = Sol·ultra. Record `model_role` + concrete model per
   `docs/model-usage.md`. UI-visible investment output still passes
   `verifier_strict`. (Earlier alternative mappings from this session are void.)
5. **Deterministic math lives in Python `services/`**, unit-tested; the model
   reasons on top of frozen computed values.

## 3. Recommended next stages — scored analysis first

Proposed bounded slices (IDs are suggestions; fold into RT4.6/RT4.7 + RT.6 or
renumber as you like). Each should be a verifiable slice with tests. They build
on what already exists: the scenario engine (RT4.1–4.4), priced simulation
(RT4.5b, `~`) and the deep-analysis skill.

- **SJ.0 — Output contract + schema.** Evolve the saved analysis `output` to the
  per-outcome shape (probability, marker/price deltas, `future_potential`) plus
  the aggregate (`conviction_score` 1–100, confidence, expected/EV, distribution)
  from `docs/plan-scored-scenario-judgment.md` §Output contract. One forward
  migration; refactor `company_score`/`prediction`/`potential`/`scenario_validity`
  as needed (full refactor latitude granted). Acceptance: schema + fixture tests;
  no behavior change yet.
- **SJ.1 — Scenario probabilities.** In the Sol scenario pass, assign
  evidence-anchored probabilities to the existing negative/stable/positive(+event)
  outcomes; normalise to ~100%; persist drivers/assumptions with `source_ids`.
  Acceptance: verifier checks mutual-exclusivity and sum; provenance stored.
- **SJ.2 — Quantified per-outcome impact.** For each outcome project forward C/Z,
  other markers (C/WK, gross margin, operating leverage, net cash/debt,
  EPS/forecast) and price from the deterministic base + explicit assumption
  deltas — Python does the arithmetic. Label *provisional* / *unavailable* when a
  base value is missing rather than inventing it. Reuse the RT4.5b FCF/priced
  bridge. Acceptance: deterministic recomputation tests; provisional labelling.
- **SJ.3 — Conviction score (1–100).** Reproducible blend of strategy fit
  (`prescore`/rubric) + evidence quality + probability-weighted upside/downside;
  expose the basis so the number is explainable; verifier owns it. Acceptance:
  score reproducible from stored inputs; unit tests; size/reputation cannot move
  it by themselves.
- **SJ.4 — "No bare needs-human" delivery.** Replace the terminal
  needs-human-that-withholds path with an always-produced read plus
  provisional/labelled gaps; reserve blocked state for integrity/safety failures
  (show reason). Acceptance: a company with incomplete primary evidence yields a
  full provisional scored read, not an empty block; integrity failures still block
  with a shown reason. (Touches the verifier + `stock-deep-analysis` gate.) Also
  update `docs/project-guardrails.md` §UI standard to add a `provisional` status
  and clarify that `needs_human` is a per-field gap label, not a wholesale
  withhold — keep the guardrails and this direction consistent.
- **SJ.5 — Calibration loop (overlaps RT.6).** Persist predictions with `as_of`;
  after each report/material update compute a calibration metric (Brier-style on
  probabilities, hit/miss on marker direction) with strict no-look-ahead; surface
  in `docs/learning.md` and the UI; feed confidence. Acceptance: calibration
  computed on a replayed case, `verifier_strict`-gated, no performance claim
  beyond what evidence supports.
- **SJ.6 — UI surface.** Show per-outcome possibilities (probability + quantified
  impact), the overall score, and provisional/verified badges without implying a
  trade instruction. Acceptance: desktop + mobile browser QA.

Dependencies to respect: SJ.2 leans on RT4.5b (finish representative persisted
verifier evidence for industrial/financial/event-driven priced outcomes); SJ.5
is effectively the front of RT.6 (judge/calibration/honest replay), which is
still fully open.

**Then the north-star loop** (deferred per priority, still required for the
quarterly habit): NS.2 universe triage ledger → NS.3 transparent universe policy
→ NS.4 promotion + recurring review (`TASKS.md` items 20–22). Continue the RT
roadmap in its binding order where it unblocks the above.

## 4. Doc fixes to do (from the 2026-07-11 audit)

**Do first — it drives the analysis pipeline (behavior-sensitive → Codex):**
- `/.agents/skills/stock-deep-analysis/SKILL.md` still names `gpt-5.3-codex-spark`
  as the default research/drafting model (lines ~14, 39, 70–71, 78, 84). This
  contradicts CX.15g. Update to Terra·high worker for research/draft + Sol·high
  independent verifier (GPT-5.3 only for purely mechanical bounded sub-loops),
  preserving the two-model draft→verify structure and `model_trace` recording.

**Safe / mechanical (remaining):**
- Fix dangling `PLAN §N` references (PLAN.md lost its numbered sections): re-add
  stable section anchors to `PLAN.md` matching what `AGENTS.md:16-18` advertises,
  or reword the citations to the current heading names ("Stack and layout",
  "Core data model", "Module contracts → Scrapers / AI and Codex", "Delivery
  order", "Quality and learning"). Affected: `AGENTS.md:16-18` and `:88`,
  `TASKS.md:96-100`, `skill/SKILL.md:10` and `:300`.
- `README.md:114-118` — the legacy "Phase 5" `ANTHROPIC_API_KEY` block contradicts
  the keyless-Codex direction; relabel as "legacy AI path (removed at CX.10)" now
  and remove when CX.10 closes (CX.10 is still open, so code may still read it).
- Archive `docs/plan-ui-refactor.md` and `docs/plan-agent-valuation-backtest.md`
  to `docs/archive/plans/` once RT4.5–4.7 / RT.6 close (they duplicate
  `plan-research-platform.md` §3.1 and §8).
- Optional: thin the duplicated Malik philosophy prose in `skill/SKILL.md` to
  reference `docs/strategy-malik.md` sections (verify the live prompt keeps enough
  standalone context); optional: add `stock-result-verifier/agents/openai.yaml`
  for symmetry, or confirm its absence is intentional.

**Already applied this session:** README "Spark" → Terra worker/Sol verifier;
`plan-research-platform.md` routing prose collapsed to a pointer;
`north-star.md` universe-number bridging clause (~384 raw before exclusions);
scored-judgment brief self-fixes (`docs/learning/` → `docs/learning.md`, dropped
the non-ladder "extra-high" tier, routing rows aligned to Terra/Sol).

Audit headline: the tree is well-maintained (archive discipline is real, routing
consistent almost everywhere). No true `AGENTS.md`/`CLAUDE.md` duplication
(`CLAUDE.md` is an intentional stub); the two verifier skills are complementary,
not duplicates.

## 5. Known issues / open risks

- **RT4.5b** priced outcomes need representative persisted verifier evidence
  (industrial/financial/event-driven) + source/no-look-ahead approval before SJ.2
  can price broadly; qualitative outcomes remain the fallback.
- **RT.6 / CX.16** no accepted performance claims yet; replay needs point-in-time
  price/evidence and exact anchors; SJ.5 calibration depends on this.
- **DISC.1** Premium forecast collector was removed pending explicit
  permission/terms, durable cursor/lock and a true HTTP-attempt budget.
- **IL.4a** myfund positions stay excluded from analysis inputs and scoring —
  keep it that way.
- **CX.10** legacy Anthropic path still open (see README block above).
- Concurrent Codex edits can reset the tree; commit and coordinate.

## 6. Verification to run before marking work complete

`cd backend && pytest -q` · `./workbench doctor` · `cd frontend && npm run build`
· browser QA (desktop + 390px) for any UI slice · re-read
`docs/project-guardrails.md` at phase start and end.

## 7. Suggested next prompt (paste to continue)

> Continue the Stocks Analysis project using the resume in
> `docs/handoff-next-stages.md`. Work the scored scenario-judgment direction
> FIRST (`docs/plan-scored-scenario-judgment.md`), starting with the doc fix to
> `/.agents/skills/stock-deep-analysis/SKILL.md` (align model routing to CX.15g:
> Terra worker + Sol verifier), then implement SJ.0 → SJ.6 as bounded,
> test-verified slices. Honor the binding rules: the user makes every decision;
> never return a bare "needs-human" — always produce the full computed, verified
> read and label gaps *provisional*, blocking only on integrity/safety failures;
> deterministic math stays in Python; UI-visible output passes `verifier_strict`;
> record `model_role` + model per `docs/model-usage.md`. After the scored-analysis
> slices, resume the north-star loop (NS.2 → NS.3 → NS.4). Read
> `docs/project-guardrails.md` and `docs/north-star.md` before starting, and run
> `pytest -q` + `./workbench doctor` + the frontend build before marking any slice
> complete.
