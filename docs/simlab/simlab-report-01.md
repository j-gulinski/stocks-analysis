# Simlab report 01 — verdict skill under fire

Date: 2026-07-18 · Skill: workbench-verdict v2.0 → v2.1
Method: strict drafter pass (skill text only, point-in-time dossier only,
no hindsight) → score vs sealed ground truth → failure analysis → patch →
re-run → counter-test. Drafter and critic run as separated passes; note
honestly: both executed by the orchestrating model in isolated roles (no
API key available in the container for literal sub-agent calls) — what is
being tested is the **skill text**, which is exactly what production
agents will receive.

## SIM-1 · T1 Mercator Medical, as-of 2021-04-20 · skill v2.0

Dossier (verified via press sources; `simlab/T1-mercator-dossier.json`):
FY2020 revenue 1 839M (+240% r/r), net profit 936M vs 6M in 2019, EBITDA
margin ~55% vs 6–8% own history, C/Z 4,2 vs own median ~13–18, high net
cash, buyback recommended at 400–770 PLN, factory #3 underway, management
citing demand > supply by 200bn gloves/yr. Q4'20 net 346M vs Q3'20 354M
(first flat quarter). One-off share: **low** — profits were core
glove sales.

**v2.0 verdict (honest strict run):** `attractive` — spełnia 10/11
policzalnych, 3 nieznane. Revenue ✓, both motors ✓, profit quality ✓
(one-off veto does NOT fire — the windfall was core business), valuation
0,25× own median ✓, catalysts named (operacyjny: capacity; struktura
kapitału: buyback above market price), trio partially ✓ (backlog b/d),
net cash ✓. No red flag on the v2.0 list fires: not one-off accounting,
not net loss+debt, not only-cheap, not hype. Teza v2.0 would write:
"popyt strukturalnie przewyższa podaż, moce rosną, wycena skrajnie
niska" — fluent, cited, wrong.

**Ground truth:** 2021 quarterly net 286 → 116 → 40 → −7,7M; price 370 →
~250 (XI 2021) → ~45 (X 2022). **−88% in 18 months.**

**Score: CRITICAL FAIL.** The skill as written rates the decade's
biggest GPW value trap attractive, with every claim properly cited. This
is precisely the "looks rigorous but isn't" failure mode — citations and
process cannot save a model missing the durability question.

### Root causes (failure ledger F5–F8)

- **F5 — asymmetric own-history discipline.** The skill compared
  *valuation* to own history but never *margins* to own history. 55% vs
  6–8% was the loudest fact in the dossier and no checklist item asked
  about it.
- **F6 — ultra-low multiple read as pure opportunity.** C/Z 4 on record
  profits is the market pricing mean reversion. v2.0 had no
  market-disagreement test; the cheaper it got, the better it scored.
- **F7 — r/r blindness at cycle tops.** All growth tests are r/r; all
  pass at the peak by construction. The q/q inflection (Q4 flat, spot
  prices stalling) had nowhere to register.
- **F8 — management signals taken as durability evidence.** The 400–770
  buyback and "demand exceeds supply" narrative fed the catalyst item;
  management anchored at the peak is a bias, not evidence.

### Patch → v2.1

New checklist item 5 (margin sustainability vs own history) carrying a
**cyclical-peak veto** with a structural-rebuttal escape and a
normalized-earnings restatement requirement; golden rules 10 (ultra-low
multiple = burden of proof flips) and 11 (q/q trajectory always read);
two red flags (exogenous-shock windfall; competitor capacity wave);
buyback-at-peak de-weighted; veto list in verdict classes extended.

## SIM-2 · T1 re-run · skill v2.1

Item 5 fires: EBITDA margin ~7× own pre-covid median, driver exogenous
(pandemic demand shock), structural rebuttal absent (no long-term
contracts in dossier, commodity-like product, gaps name competitor
capacity as unknown while Asian producers expand), q/q inflection
present. **Cyclical-peak veto → verdict `weak`.** Normalized
restatement: own historical ~6–8% EBITDA margin on even the enlarged
scale implies normalized net profit in the low tens of millions →
normalized C/Z ≈ 40–80, not 4,2. Teza: "Brak trwałej tezy — wynik
szczytowo-cykliczny; rynek wycenia rewersję (golden rule 10)."
Falsifiers the run produces: glove spot prices, Q1'21 q/q direction,
competitor capacity additions — all the things that actually broke.

**Score: PASS.** Correct class, correct mechanism, correct falsifiers.

## SIM-3 · T4 XTB, as-of 2022-01-15 · skill v2.1 · over-fire counter-test

Purpose: prove the new veto doesn't turn the model into a reflexive
"everything above historical margins is a trap" permabear.

Dossier (reconstructed from knowledge, directionally verified figures;
label: re-verify before reuse): 2020 net ~402M on volatility boom; 2021
net ~229M (down r/r); revenue 2021 below 2020; **active clients roughly
doubled to ~190k and still growing**, entry into new geographies,
brokerage with structural net cash; price ~17 PLN, cap ~2,0 bld, C/Z ~9
on 2021.

**v2.1 verdict:** profitability above pre-2020 own history and the
trigger driver (volatility) is exogenous — item 5 is *examined* — but
the structural-rebuttal branch holds: a doubled, still-growing recurring
client base is exactly the "growing recurring customer/asset base"
evidence the veto requires to stand down. Veto does not fire. Verdict:
`neutral` (r/r profit declining blocks attractive on its own terms),
teza: revenue per client mean-reverts around a structurally larger base;
falsifier: client growth stalling; verify_next: revenue-per-client
decomposition.

**Ground truth:** 2022 net ~766M; stock roughly doubled within 12 months.

**Score: PASS (no false veto).** `neutral` on a winner is acceptable —
the model missed upside but told no lies and named the exact variable
(client base) that drove the win. `weak` here would have been an
over-fire; it did not happen because the veto demands *absence* of
structural evidence, not mere presence of a shock.

## Scoreboard

| Sim | Case | Skill | Verdict | Truth | Result |
|---|---|---|---|---|---|
| 1 | MRC 2021-04 (trap) | v2.0 | attractive | −88% | **CRITICAL FAIL** |
| 2 | MRC 2021-04 (trap) | v2.1 | weak (veto) | −88% | PASS |
| 3 | XTB 2022-01 (winner) | v2.1 | neutral | ~+90% | PASS (no over-fire) |

## Queue — the remaining battery (next sessions)

| # | Case | As-of | Attacks | Expected |
|---|---|---|---|---|
| T2 | Rainbow Tours | 2023-06 | can the model still say *attractive* to a genuine winner post-patch (false-negative check) | attractive |
| T3 | CD Projekt | 2020-11 | priced-for-perfection + event branch discipline | weak/neutral, event isolated |
| T5 | Bumech | 2022-09 | commodity-peak variant of the veto (coal) | weak |
| T6 | Stalprodukt-class | any | only-cheap, no catalyst, years of nothing | neutral/weak, "brak tezy" stated |
| T7 | synthetic 2-indicator dossier | — | insufficient_data honesty (no invented verdict) | insufficient_data |
| T8 | SNT | 2026-07 | replay on your real data vs your two documented rejections | no repeat of either rejection |
| R | regression | — | every patched version re-runs SIM 1–3 before promotion | no degradation |

Rule going forward (also for production): **every patch must re-run the
full accumulated battery** — SIM-3-style counter-tests are mandatory for
every new veto, because each veto added is a false-negative risk bought.

## What this changes in the plans

- The failure ledger now has 8 rows (2 SNT + F5–F8 + 2 design notes) and
  has already produced one shipped skill version — the learning loop
  demonstrably works *before* any code exists.
- Dossier contract additions required by v2.1 (feed into R1):
  margin-vs-own-history series with pre-event median, q/q sequential
  table alongside r/r, and a `profit_driver` classification
  (price/volume/mix) so the exogenous-shock test has computed inputs.
- T2/T3/T5–T8 remain open: the skill is **not yet declared bulletproof**
  — one trap caught and one non-over-fire is evidence, not proof. The
  battery continues next session.
