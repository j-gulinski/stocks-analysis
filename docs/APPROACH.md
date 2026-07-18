
## Amendments after simlab hardening (2026-07-18, binding on merge)

The verdict model shipped in `skills/workbench-verdict/SKILL.md` is
v2.5, hardened by 57 simulations (54 corpus + 3 live). Deltas vs the
original draft of this document:

- The funnel's one-off veto generalizes to a **windfall test** with two
  branches (margins vs own history; demand base vs own trendline, with
  a recovery-to-trend carve-out) — from the Mercator and TSG failures.
- A second, stricter road to `attractive` exists: the **kompounder
  gate** (six conditions, deceleration falsifier mandatory) — from the
  Dino miss, counter-tested on Answear/CCC/Pepco.
- **Cash-divergence veto** with a collector carve-out — from the
  GetBack family.
- `weak` requires valuation-above-median **without** an active motor
  (F15) — priced ≠ broken.
- Verdict scoring is **process-at-T**, never lottery outcomes; the
  corpus deliberately contains adversarial cases (TIM, DGN-2020) to
  keep it that way.
- Backlog counts as margin-of-safety **only at healthy margin**
  (Rafako/Budimex pair).

On merge, this document supersedes VISION.md and STRATEGY.md as binding
intent; `test_vision_contract.py` is re-encoded (never weakened) in the
follow-up implementation PR per the plan.
