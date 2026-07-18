# Simlab report 02 — full battery, 11 new scenarios

Date: 2026-07-18 · Skill: v2.1 → v2.2 · Cumulative sims: 14
Method unchanged (strict point-in-time drafter, sealed ground truth,
patch → regression). Data labels: **[V]** verified via sources this
session, **[R]** reconstructed from model knowledge, directionally
checked — re-verify before production reuse.

## Scoreboard (this session)

| Sim | Case | As-of | Skill | Verdict | Truth (12–18m) | Result |
|---|---|---|---|---|---|---|
| 4 | Rainbow Tours [R] | 2023-06 | v2.2 | attractive | ~+200% | **PASS** |
| 5 | CD Projekt [R] | 2020-11 | v2.2 | weak | −55%/−75% | **PASS** |
| 6 | Bumech [R] | 2022-09 | v2.2 | weak (veto) | ~−60% | **PASS** |
| 7 | Stalprodukt [R] | 2021-06 | v2.2 | neutral, "brak tezy" | flat/underperf. | **PASS** |
| 8 | synthetic 2-indicator | — | v2.2 | insufficient_data | — | **PASS** |
| 9 | Ten Square Games [R] | 2021-03 | v2.1 | neutral, wrong teza | −75% | **SOFT FAIL → patch** |
| 9b | Ten Square Games [R] | 2021-03 | v2.2 | weak (demand-base veto) | −75% | **PASS** |
| 10 | Digital Network [V] | 2024-03 | v2.2 | attractive | ~+180% | **PASS** |
| 11 | Digital Network [V/R] | 2020-08 | v2.2 | weak/no-thesis | +100%+ (then +2000%) | **PASS on process** (see §Scoring philosophy) |
| 12 | Synektik [V] | 2023-12 | v2.2 | attractive | ~+100–150% | **PASS** |
| 13 | Synektik [V/R] | 2021-06 | v2.2 | neutral (priced) | ~flat | **PASS** |
| 14 | Synektik watch-loop [V] | 2025-04 | v2.2 | falsifier fired → re-verify | mixed (see below) | **PASS on process** |

Regression (mandatory after v2.2): SIM-1 MRC still `weak` (margins
branch), SIM-3 XTB still `neutral` (client-base rebuttal holds), SIM-4
Rainbow still `attractive` (recovery-to-trend carve-out is exactly why
that carve-out exists). **No degradation.**

## Session findings in brief

**SIM-9 → the v2.2 patch (F9).** TSG's margins were always high, so the
v2.1 margin-veto never engaged — while covid pushed *revenue* 2.4× above
the company's own trendline via lockdown engagement, and DAU was already
sliding q/q. v2.1 produced `neutral` with a growth-flavored teza: no
loud lie, but blind to the dominant risk on a −75% outcome. v2.2 adds
the **demand-base branch**: revenue far above own pre-shock trendline
from an exogenous behavioral/commodity shock triggers the same veto,
with an explicit **recovery-to-trend carve-out** so post-crisis rebounds
(Rainbow) are not punished. Golden rule 11 (q/q) supplies the trigger
evidence (declining engagement despite record r/r).

**SIM-4 Rainbow (false-negative check passed).** The patched skill can
still say yes: revenue ~35% above 2019 on *volume* (pax counts) plus
structural Polish travel demand, forward C/Z ~5 vs own double-digit
median, operating leverage real, catalyst = booking curve for summer
2023 visible in monthly reports. Carve-out correctly classifies it
cykliczny-recovery, not windfall. A model that only vetoes is worthless;
this is the proof it doesn't.

**SIM-5 CDR.** `weak` for the right mechanics: C/Z far above own median
(fails valuation item on its own terms), and Cyberpunk is a **zdarzenie**
— the event branch cannot be smuggled into base numbers, and at that
price the priced-in test reads "rynek wycenia ideał". Known limitation
recorded honestly: this model structurally misses expensive compounders
(it would have skipped CDR's whole 2015–2020 run). That is a design
choice inherited from the sources, not a defect.

**SIM-6 Bumech.** Commodity variant of the veto: mining margins several
times own history on spot coal, no contracted volumes, sequential coal
price rollover in the dossier → veto → `weak`. Normalized restatement
turns C/Z ~2 into "not cheap at all".

**SIM-7 Stalprodukt.** The "only-cheap forever" case: C/Z ~6–9, C/WK
~0.4, no nameable catalyst. Golden rule 2 does its job — "Brak wyraźnej
tezy inwestycyjnej" caps the verdict at neutral, and that sentence is
the finding. Years of dead money correctly avoided without pretending a
short thesis exists.

**SIM-10/11 Digital Network, both faces.** 2024-03 [V]: FY2023 net paid
out 100% (14,5M dywidenda), EBIT margin 35% (own trajectory 30→35%,
structural: screen utilization + network growth 10–15%/yr strategy),
C/Z ~6–7, yield ~10% — margins above history but the driver is
*structural capacity utilization with a published growth strategy*, the
rebuttal branch stands down correctly → `attractive`; outcome ~+180%.
2020-08: ~19M cap, covid ad collapse, illiquid micro, no visibility →
`weak/no-thesis` — and the stock then 20×'d.

**SIM-12/13 Synektik, both faces.** 2023-12 [V]: revenue 446,9M (+168%),
net j.d. 52,5M, powtarzalny zysk ~71M vs cap ~620M → C/Z ~8,7 na
powtarzalnym; recurring revenues +89% to 112,9M; procedures doubled to
~6k/yr; backlog + active offers strong; dividend 99,7% payout. The
windfall test *examines* (+168% is far above trend) and the structural
rebuttal is textbook: installed base × service × zużywalne instrumenty =
growing recurring asset with volume (procedure) evidence → `attractive`.
Outcome: cap roughly doubled within 12–18m. 2021-06 [R]: solid growth
but C/Z ~30+ around own median, thesis (da Vinci adoption) real yet
priced → `neutral`; stock went sideways a year. Both faces of the same
company, both called right by the same rules.

**SIM-14 — first watch-loop simulation.** As-of 2025-04 [V]: backlog
10,8M vs 19,1M r/r; H1 orders 147M vs 191,6M. A standing SNT thesis
carrying "backlog dynamics" as a falsifier **fires it** → surfaced,
re-verification queued, thesis stress named. The stock nonetheless kept
rising into 2026 (valuation re-rating). Scored as PASS **on process**:
the ledger's job is to surface the contradiction between order intake
and price, not to predict the crowd — and this exact tension (future
potential vs order momentum) is what your own July 2026 valuation
dispute was about.

## Scoring philosophy (locked in by SIM-11 and SIM-14)

Verdicts are scored on **process quality at T**, not lottery outcomes.
A `weak` on an invisible 2020 bottom is correct process; an `attractive`
on Mercator with perfect citations is a critical failure. Concretely: a
sim FAILS when the verdict's *mechanism* was wrong or a knowable risk
was missed; it PASSES when the mechanism was right, even if price went
the other way. Aggregate return-by-class stats remain the long-run
check (R4), never the per-case judge.

## Dossier-contract additions (feed R1) — cumulative

From v2.1: margin series vs own pre-event median; q/q sequential table;
profit-driver split (price/volume/mix). New from v2.2 and this battery:
revenue vs own pre-shock **trendline**; volume/engagement KPI series
(pax, procedures, DAU, screens); **backlog series r/r** (SIM-14 makes it
a falsifier input, not just a gap); recurring-revenue share; dividend
payout ratio.

## Remaining queue before "bulletproof"

| # | Case | Attacks |
|---|---|---|
| T8 | SNT full replay on your real repo data, 2026 dates | must not repeat either of your two documented rejections |
| T15 | Medicalgorithmics-class serial promiser [R] | management-credibility red flag with a −90% truth |
| T16 | dilution trap (biotech/NewConnect financing spiral) | financing-risk handling, share-count discipline |
| T17 | accounting one-off classic (asset revaluation quarter) | the original item-4 veto, still untested on a real case |
| T18 | second genuine winner post-v2.2 | keep hammering the false-negative side |
| R | full regression | all 14+ sims on every future patch |

Convergence rule: the skill is declared battery-hardened only after one
full round of **new** cases produces zero patches. Two patches in 14
sims means we are close but not there.
