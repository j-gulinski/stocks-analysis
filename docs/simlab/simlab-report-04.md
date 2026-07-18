# Simlab report 04 — corpus execution round

Date: 2026-07-18 · Skill v2.3 → v2.4 · New sims: 30 · Cumulative: 54
All cases this round are [R] reconstructed from model knowledge with
directional confidence (mechanism-decisive figures only), run strictly
point-in-time under the current skill text. These are **logic
simulations**: they test whether the skill's rules produce the right
verdict for the right mechanism on that fact pattern. Every one is
queued for a real-data re-run in the harness (R3); none is a
performance claim.

## Scoreboard

| # | Case · as-of | Arch | Verdict (v2.3/2.4) | Deciding mechanism | Truth | Result |
|---|---|---|---|---|---|---|
| 25 | JSW · 2022-06 | WIND-M | weak | margins ~10× own history, spot coal, state governance | −50% | PASS |
| 26 | PCC Rokita · 2022-10 | WIND-M | weak | chemical spread windfall, mostly spot | −45% | PASS |
| 27 | TIM · 2022-05 | WIND-D adv. | weak | PV-boom demand base > trend | +40% (tender) | PASS (process) |
| 28 | Sunex → covered in R03 | — | — | — | — | — |
| 29 | Enter Air · 2021-03 | REC | attractive | recovery-to-trend, bookings visible, normalized C/Z ~6 | +100% | PASS |
| 30 | Benefit Systems · 2021-05 | REC→KOMP | attractive | card count = units, normalized below own median | +300%/3y | PASS |
| 31 | AmRest · 2021-03 | REC ctr | weak/neutral | leverage eats the recovery; gate cond. 3 fails | flat/− | PASS |
| 32 | Kruk · 2016-06 | STD | attractive | EPS +25%, PEG<1, ERC growing | +100%/2y | PASS |
| 33 | Kruk · 2018-05 | DECEL | neutral | at ATH, q/q growth fading; Italy costs in notes | −40% | PASS-lean* |
| 34 | Kruk · 2020-05 | REC | attractive | covid write-downs vs intact recoveries, deep below median | +200% | PASS |
| 35 | Budimex · 2022-10 | STD+BKLG | attractive | backlog **with indexation clauses** = healthy-margin backlog, net cash, C/Z<median | +200% | PASS |
| 36 | Rafako · 2021-03 | BKLG | weak | fixed-price legacy backlog = risk not cushion (item 8 note), chronic losses, debt | −80% | PASS |
| 37 | CCC · 2018-05 | KOMP ctr | weak | units yes, but LFL weak, leverage-funded rollout — gate 2/3/5 fail | −80% | PASS |
| 38 | Pepco · 2023-06 | KOMP ctr | neutral/weak | LFL negative q/q (gate 4), governance overhang | −40% | PASS |
| 39 | Dino · 2020-04 | KOMP | attractive (komp.) | units intact through covid, PEG improved on dip | +150% | PASS |
| 40 | Inter Cars · 2020-06 | STD | attractive | distribution motors on, C/Z below median | +150% | PASS |
| 41 | Auto Partner · 2023-09 | DECEL | neutral | margin squeeze q/q despite r/r growth (rule 11) | −25% | PASS |
| 42 | Kęty · 2016-01 | STD | attractive/neutral | steady motors, fair price — boundary case | + steady | PASS |
| 43 | Wittchen · 2022-11 | REC | attractive | travel-adjacent recovery, margins own-range, C/Z ~7 | +80% then fade | PASS |
| 44 | Text · 2016-06 | KOMP | attractive (komp.) | MRR units, funded, PEG≈1 | + (choppy path) | PASS |
| 45 | Text · 2019-03 | WATCH | falsifier fires | churn/competition q/q → re-verify, hold thesis | −30% then + | PASS (process) |
| 46 | XTB · 2023-06 | STD | attractive | client base compounding, normalized C/Z ~7, capital returns | ~+100% | PASS |
| 47 | Synektik · 2023-02 | STD | attractive | H1 profit +280%, robots ramp, backlog record, fwd C/Z <10 | +200% | PASS |
| 48 | DGN · 2023-03 | STD | attractive | C/Z ~6, dividend, structural DOOH growth | +300% | PASS |
| 49 | CDR · 2021-06 | PWE ctr | weak | no cheapness after crash (C/Z ~30 on broken earnings), trust broken | −40% | PASS |
| 50 | Mabion · 2021-03 | EVT | weak | optional event (Novavax) priced as certainty, no revenue base | −80% | PASS |
| 51 | CI Games · 2023-09 | EVT | weak | one-title launch priced, launch-history base rates | −60% | PASS |
| 52 | 11 bit · 2024-08 | EVT | weak | F2 priced for perfection, franchise concentration | −50% | PASS |
| 53 | Creepy Jar · 2021-02 | WIND-D | neutral/weak | covid engagement base, one title | −60% | PASS |
| 54 | PlayWay · 2021-01 | DECEL | neutral | engagement base + title concentration; **gate ambiguity logged (F13)** | −40% | PASS-lean* |
| 55 | Ursus · 2017-06 | PROM | weak | announced contracts never cash, losses+debt+dilution | −95% | PASS |
| 56 | Braster · 2017-10 | DIL | weak | pre-revenue burn, serial raises | −95% | PASS |
| 57 | Columbus · 2020-10 | WIND-D+PROM | weak | subsidy-scheme revenue, working capital balloon, PR-heavy | −90% | PASS |
| 58 | GetBack · 2017-11 | ACC | weak | **revaluation-gain profits (item-4 veto) + bond-fed leverage**; OCF divergence flagged | −100% | PASS |
| 59 | Próchnik · 2016-06 | CHEAP | weak | chronic loss + no thesis; cheapness unto delisting | −100% | PASS |
| 60 | synthetic OCF-divergence | ACC | v2.3: neutral (hole) → v2.4: weak | **FAIL → patch v2.4**: divergence now blocks attractive | — | PASS after patch |
| 61 | synthetic NC promise-rich | INSUF | insufficient_data | promises never substitute for numbers | — | PASS |

*PASS-lean: mechanism right, but the deciding dossier signal (Kruk's
Italy cost creep; PlayWay unit definition) is at the edge of what a
point-in-time dossier plausibly showed — both flagged for priority
real-data re-runs, not counted as clean wins.

## The instructive five

**GetBack (#58) — the corpus's hardest case, and item 4 held.** What
catches it at Nov 2017 is not fraud detection (not claimed, not
possible): it is that profits leaned on **portfolio revaluation gains**
— paper, model-based, explicitly listed in the one-off veto — while
growth ran on accelerating bond issuance. Risk-profile verdict `weak`
for reasons that were knowable. The synthetic twin (#60) then proved
the *general* cash-divergence hole outside collector accounting and
produced v2.4's veto with the collector carve-out — Kruk regression
confirms the carve-out works (collectors judged on recoveries vs book,
not raw OCF).

**Rafako vs Budimex (#36/#35) — one item, both directions.** Same
sector, same metric, opposite verdicts for the stated reason: backlog
is safety only at healthy margin. Rafako's fixed-price legacy book is
the trap; Budimex's indexation-clause book plus net cash is the real
trio. The backlog-quality note earned its place in one pair.

**CCC and Pepco vs Dino (#37/#38 vs #39) — the gate discriminates.**
Three store-rollout stories; only the self-funded one with positive LFL
passes. Leverage-funded units (CCC) and negative-LFL units (Pepco) fail
on named conditions, not vibes. This is the anti-"quality at any price"
proof the kompounder gate owed us.

**TIM (#27) — the adversarial case behaved.** The veto was right (PV
windfall base), the outcome was positive anyway (Würth tender). Scored
PASS on process by pre-registration — this case exists so the harness
never learns to grade itself on lottery outcomes.

**Text 2019 (#45) — watch loop under stress.** Falsifier fires on churn,
re-verification holds the thesis rather than panic-exiting, the drawdown
reverses. The ledger's job — surface and re-verify, not flinch — shown
on a real whipsaw.

## Ledger and design notes

F13 (open, no patch): the kompounder gate's "unit" definition for
portfolio game studios is ambiguous — deliberately left unresolved
until real-data runs on PlayWay/11bit force a decision with evidence.
F14 → patched as v2.4. Counter-test inventory now four permanent
guards: XTB, Answear, Rainbow, Kruk-carve-out.

## Cumulative status

54 sims · 4 patches (all failure-driven, all regression-tested) ·
0 unresolved regressions · verdict distribution across corpus so far:
attractive 17, neutral 12, weak 22, insufficient 3 — with truths
ordered correctly by class (attractive avg strongly positive, weak avg
deeply negative; denominators small, so this is a sanity signal, not a
statistic).

Remaining before "bulletproof": (1) real-data re-runs of everything
[R] via the harness — especially the two PASS-lean cases; (2) scenario
#50, the SNT 2026 replay on your repo data against your two documented
rejections; (3) one fresh ≥20-scenario round with zero patches. The
skill text is now stable enough that R0–R2 implementation can start in
parallel without fear of churn underneath it.
