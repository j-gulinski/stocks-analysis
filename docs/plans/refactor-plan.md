# Plan: learning-first refactor (the one live plan)

Status: proposed · supersedes all prior plan drafts on merge
Owner: Kuba · Prepared: 2026-07-18 · Anchor deadline: SNT report 2026-08-05

One primitive carries the architecture: `build_dossier(company, as_of=T)`
— live analysis is `T=now`, backtest is `T=past`, same code path. The
verdict model (skills/workbench-verdict, **v2.5**) is already hardened by
57 simulations recorded in `docs/simlab/`; implementation now catches the
code up to the model.

## Phases

**R0 — Publication dates (1–2 days).** `refresh.py` currently discards
the BiznesRadar "Data publikacji" row. Parse and store it per
(company, period, statement) as first-class facts; backfill from stored
immutable DocumentVersions (no re-scraping); fixture + tests per
scraper-doctor. Output: PIT-coverage report per company/period. Strict
rule (already encoded in `Price`): no availability timestamp → excluded
from replay, named as gap, never approximated.

**R1 — As-of dossier (3–4 days).** Refactor `metrics.py` composition
into `services/dossier.py` keyed on `as_of`; ban naive "latest" reads in
analysis paths (Haiku sweep). `GET /api/companies/{t}/dossier?as_of=`
read-only over stored data. **Dossier contract (final, from simlab):**
company/size; quarterly+annual normalized income with **r/r AND k/k**
tables; gross-margin series **with pre-event own median**; operating
leverage; one-off share + continuing-ops bridge (generalized);
**profit-driver split** (price/volume/mix where derivable); **revenue vs
own pre-shock trendline**; volume/engagement KPI series where collected
(units, LFL, procedures, screens); C/Z history + own median + basis;
C/WK; net cash decomposition; **OCF-vs-net-profit series +
receivables/inventory turns** (v2.4 veto input); recurring-revenue
share; dividend payout; **backlog series r/r** (gap until collector);
document manifest; forum leads labelled; named gaps.

**R2 — Verdict live (2–3 days, parallel with R0/R1 on as_of=now).**
New `stock-company-verdict` AgentRun workflow: Opus drafter with
SKILL.md as system prompt; separate-Opus verifier whose charter is the
two-layer check (computed lineage first, then "would the owner reject
this for the SNT reasons"); lean `VerdictSnapshot` table (company,
case_id, dossier_fingerprint, model_version, payload, status); verdicts
render on company page, substance first. Acceptance: Kuba reads SNT +
holdings verdicts; rejections → `docs/failure-ledger.md` rows → checks.

**R3 — Case library + harness (3–4 days).** Corpus in
`docs/simlab/corpus.md` (78 pre-registered scenarios) becomes executable:
harness builds PIT dossiers for runnable scenarios (coverage report
decides), runs draft+verify through the queue, computes truths from
price/report data (never typed from memory), scores **process-first**
per the locked philosophy. Seed C1 (myfund operations CSV — **owner
input required**) and C2 (thread picks from retained transcripts,
outcomes independently priced). All [R]-labelled hand-sims re-run here.

**R4 — Scoring + regression gate (2–3 days).** `CaseScore` per
(case, model_version, engine_version); walk-forward threshold tooling;
holdout registry chosen once and listed; promotion rule: new skill
version replays the whole battery, no degradation on holdout; Lab
screen with denominators. Bulletproof declaration criteria unchanged
(≥20 fresh scenarios, zero patches, return-by-class ordering).

**R5 — Live pipeline (3–4 days).** `sieve_v2` two-tier funnel (tier 1
market-wide from MarketFactorRow: kills → size → revenue r/r →
operating-margin trend → C/Z vs own median; tier 2 per-company for top
~40: both motors + windfall/one-off veto on rank); kill drawer kept;
v1 evaluator deleted same slice. Watch loop wired: verdict falsifiers →
`ThesisFalsifier` rows; report-day+1 re-verification; fired falsifiers
top of Research agenda; V8 outcome scoring per model version. First
live scored case: SNT after 2026-08-05. The three 2026-07-18 live
verdicts (TAR attractive / APR neutral / LBW neutral — see
docs/simlab/live-verdicts-2026-07-18.md) enter the ledger with their
dated falsifiers as watch-loop cases T19–T21.

**R6 — Deletions + doc re-encoding (2 days, after R2+R3 owner-accepted).**
valuation-engine-v4 ceremony (math kept as optional library),
templates/near-duplicate gates, superseded research-v3 judgment layers,
plumbing-heavy skill sections → code; VISION/STRATEGY superseded by
APPROACH.md; `test_vision_contract.py` → `test_approach_contract.py`
re-encoding invariants v2 (re-encoded, never weakened); one clean
migration; CHANGELOG.

## Agent routing

| Tier | Model | Work |
|---|---|---|
| Orchestrator | Fable | sequencing, owner Q&A batching, accept/reject triage; never verifies own draft |
| Hard | Opus | verdict drafts + independent verification, scoring-method review, patch review |
| Medium | Sonnet | R0/R1/R5 implementation, harness, extraction, fixtures |
| Mechanical | Haiku | latest-read sweeps, lineage checks, fixture shaping, test loops, pl-PL checks |

Requested tier vs actual host recorded honestly in docs/model-usage.md.

## Decisions pending owner (block the phase named, nothing else)

1. Checklist strike-pass on SKILL.md v2.5 — makes the model yours;
   blocks R2 acceptance, not R0/R1. (~30 min)
2. Myfund full operations CSV — blocks C1 in R3.
3. SNT profile confirm in-app — blocks the 2026-08-05 calendar job.
4. F13: unit definition for portfolio game studios in the kompounder
   gate — deliberately open until R3 real-data runs on PlayWay/11bit.
5. Tier-2 sieve depth (proposal: top 40) and VerdictSnapshot storage
   (proposal: new lean table) — defaults apply unless overridden.

## Definition of done (per phase)

Owner reads the primary artifact and would act on it, or the rejection
is ledgered with the check it spawns · focused tests green · frontend
production build when touched · one browser interaction proving the
outcome · CHANGELOG + model-usage rows. Full suite at R6.
