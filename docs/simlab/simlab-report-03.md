# Simlab report 03 — the compounder round

Date: 2026-07-18 · Skill v2.2 → v2.3 · Cumulative sims: 24
Focus per owner instruction: genuine fundamental growth (not
situational windfalls) on the positive side, plus more ways to be wrong
on the negative side. Labels: [V] verified, [R] reconstructed —
directionally checked, re-verify before production reuse.

## Scoreboard (this session)

| Sim | Case | As-of | Skill | Verdict | Truth | Result |
|---|---|---|---|---|---|---|
| 15 | Dino [R] | 2018-06 | v2.2 | neutral "priced" | +400% / 4y | **MISS → patch** |
| 15b | Dino [R] | 2018-06 | v2.3 | attractive (kompounder) | +400% / 4y | **PASS** |
| 16 | Dino [R] | 2023-07 | v2.3 | neutral + deceleration falsifier | −35% / 12m | **PASS (process)** |
| 17 | Answear [R] | 2021-11 | v2.3 | neutral/weak (gate blocked) | ~−60% | **PASS (no over-fire)** |
| 18 | Sunex [R] | 2022-09 | v2.3 | weak (demand-base veto) | ~−70% | **PASS** |
| 19 | Auto Partner [R] | 2021-05 | v2.3 | attractive (standard path) | ~+180% | **PASS** |
| 20 | Voxel [R] | 2022-11 | v2.3 | attractive (post-windfall entry) | ~+250% | **PASS** |
| 21 | Medicalgorithmics [R] | 2018-09 | v2.3 | weak (serial-promiser flag) | ~−85% | **PASS** |
| 22 | Text/LiveChat [R] | 2023-08 | v2.3 | neutral→weak (thesis-break) | ~−45% | **PASS** |

Regression on v2.3 (mandatory): all prior 14 sims re-checked — MRC weak
(gate irrelevant: windfall veto disqualifies), TSG weak (engagement ≠
units, gate condition 1), XTB neutral, Rainbow attractive, SNT-2023
attractive (now arguably `kompounder`: installed base × zużywalne =
units — noted, same class), DGN-2024 attractive. **No degradation; one
enrichment.**

## Session notes (condensed)

**SIM-15/15b — the patch this round exists for.** v2.2's cheap-vs-own-
history spine can never approve a company that is *always* expensive
because it always delivers — exactly the profile you asked for. The
kompounder gate opens a second road with six hard conditions
(replicable units, unit margins stable+, funded runway, q/q volume,
PEG ≤ ~1, mandatory deceleration falsifier). Dino 2018 clears all six:
stores +26%, LFL positive, self-funded rollout, C/Z ~35 vs growth ~40%.

**SIM-16 — the same gate closing.** Dino 2023-07 at ATH: unit adds
decelerating, LFL rolling over q/q, C/Z ~30 vs growth now ~20 → PEG > 1
and the deceleration falsifier fires at the next report. `neutral` with
an explicit exit-stress note before a −35% year. The gate is a door
that swings both ways, which is what keeps it from being a
quality-at-any-price hole.

**SIM-17 — counter-test the new gate (critical).** Answear 2021: revenue
+40% but growth bought with marketing, thin contribution margins, and
the price at C/Z ~35 → fails gate conditions 2 and 5 → no kompounder
label; standard path also says no (not cheap vs history). Truth −60%.
Every new path must fail loudly on its own lookalike trap; it did.

**SIM-18 — v2.2 confirmation on a fresh windfall.** Sunex: heat-pump
boom (subsidy + energy-crisis panic) put revenue ~2,5× above own trend;
margins looked fine — the demand-base branch (the TSG patch) fires, not
the margin branch. Weak before ~−70%. The patch generalizes.

**SIM-19 — the standard path still carries.** Auto Partner 2021:
distribution rollout, revenue +25–30%, motors on, C/Z ~11 below own
median, net cash adequate → plain `attractive`, no gate needed. The
model must not become kompounder-romantic; most of its money is here.

**SIM-20 — entering AFTER the windfall (the Mercator mirror).** Voxel
2022: covid-test revenues gone, core diagnostics growing, valuation on
*normalized* (ex-covid) earnings ~10× and below own median → the same
normalization discipline that vetoed Mercator at the top **approves**
the survivor after the unwind. One mechanism, both directions — this
symmetry is the best evidence the veto is a model, not a mood.

**SIM-21 — serial promiser.** Medicalgorithmics 2018: statistically
cheap-ish, but the dossier's document trail shows repeated guidance
misses and a deteriorating US reimbursement reality vs unchanged
management narrative → red flag "unmet promises" + thesis untrustable →
weak. −85% follows. Checklist item 13 finally tested on a real corpse.

**SIM-22 — cheap-vs-history is not immunity.** Text 2023: C/Z ~12,
well below own median — but MRR growth stalling q/q and an AI
substitution threat named in the dossier's own leads → golden rule 4
(cheap never sufficient) + rule 11 hold the verdict at neutral→weak
with the churn falsifier dated. −45% follows. The spine bends where it
should.

## New failure-ledger rows

F10 compounder blindness (patched, gate); F11 gate lookalike risk
(Answear counter-test now permanent in regression); F12 backlog-quality
(fixed-price order books are not safety — item 8 note; Rafako-class
case queued in corpus for a full sim).

## Scale-up: the corpus is now the battery

Hand-running is the bottleneck: ~24 sims across three sessions.
Per your requirement (tens → hundreds), `simlab-corpus.md` now registers
**78 pre-designed scenarios** across ~45 companies and 2015–2026, each
with archetype, as-of date, pre-registered expected verdict, and truth
status. Pre-registration matters: expectations are written **before**
the run, so the harness cannot grade itself on vibes.

Execution plan for scale (this is R3 in the refactor plan):
- the harness feeds each scenario's point-in-time dossier (built by R0/R1
  from stored BiznesRadar pages + stooq prices) to the verdict skill via
  the existing AgentRun queue — Opus drafter, Opus verifier, Haiku
  lineage sweep;
- truths are computed from price + report data, never typed from memory;
- results land in `CaseScore`; patches follow the same
  fail → patch → full-regression loop demonstrated manually here;
- [R]-labelled sims from these three reports get re-run on real data as
  harness cases — treat today's results as design evidence, not final
  scores.

Cost note honestly: ~78 scenarios × draft+verify ≈ 160–200 Opus calls
per battery pass — run in batches, cache dossiers, and only re-run the
full set on skill patches; nightly incremental otherwise.

## Status

v2.3 is 24/24 on the current set after patches, with three patches
earned from real failures (windfall margins, windfall demand base,
compounder blindness) and two permanent counter-tests guarding against
over-firing (XTB, Answear). **Not yet bulletproof by our own rule** —
that requires one full round of *new* cases with zero patches, at
corpus scale, on real fetched data. The machinery to do that is exactly
R0–R3; nothing about it is speculative anymore.
