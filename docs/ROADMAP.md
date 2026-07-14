# Delivery roadmap

The only live delivery document. Defers to `docs/VISION.md`. The 2026-07
reset replaced the three-sieve / method-pack contract with the single
Workbench strategy pipeline; legacy paths are deleted, not preserved (V10).

## Current state (2026-07 reset)

Foundations that stay: FastAPI + Next.js, immutable document/snapshot
lineage, `ResearchCase`, deterministic engines, the `AgentRun` DB queue with
Codex-host execution, drafter/verifier separation.

Author-branded, seeded, generic-completion and one-job-and-stop paths are gone
from callable product surfaces. Historical audit rows may remain unread in the
database; they have no compatibility API or UI (V10).

## Slices

| # | Outcome | Exit gate | Status |
|---|---|---|---|
| S0 | Binding docs + executable drift gate | VISION/PRODUCT/STRATEGY/AGENTS rewritten; `test_vision_contract.py` passes and fails on planted drift | complete · 2026-07-14 |
| S1 | One exclusion-first sieve over expanded market snapshot | multi-page market snapshot stored immutably; `workbench_sieve_v1` returns survivors + inspectable kills; single-sieve UI; forbidden: filter tabs | next · sieve honestly blocked until factor batch exists |
| S2 | Phase-aware Research list, single detail renderer | list rows render per-phase substance incl. valuation strip; legacy dossier tabs deleted; agenda on top | implemented · browser gate pending |
| S3 | Company-specific valuation with structural gates | Codex-drafted assumptions/probabilities bound to evidence; backend auto-rejects seed-equality, near-duplicates, default mixes, missing rationale; adversarial verifier contract; legacy scenario defaults deleted | implemented · live/browser gate pending |
| S4 | Portfolio precision + auto-coverage | real TWR/XIRR from daily series (+operations when available); robust mapping with overrides; warning-not-blackout reconciliation; sync auto-queues research/valuation for uncovered or stale holdings by weight × staleness | in progress |
| S5 | Queue clearing | run-queue skill drains the queue with lease recovery and failure caps; auto-queue producers (sync, staleness, falsifier) documented | implemented · live empty-queue gate pending |
| S6 | Outcome scoring (learning loop v1) | first scenario-outcome job scores a valued company against an actual report; calibration visible per engine version | queued |
| S7 | Report-calendar awareness | holdings' next report dates tracked; re-research/re-valuation queued around publication | queued |
| S8 | Point-in-time replay gate | frozen universe, adjusted total returns, holdout — precondition for any performance claim | blocked · historical data missing |

## External/user dependencies

- myfund operations endpoint (probe with configured key; else CSV/XLS
  export import) — affects S4 depth, not S4 delivery.
- BiznesRadar premium session for market pages where anonymous truncates.
- S8 needs point-in-time universe and total-return series.

## Definition of done for any slice

Focused tests + relevant backend suite green, frontend production build
green, runtime healthy, one browser interaction proving the user outcome,
drift gate run (VISION), docs/CHANGELOG/model-usage updated. Verification
follows AGENTS.md — adversarial, with findings or justified none.
