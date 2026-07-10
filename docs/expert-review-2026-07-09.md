# Expert review — 2026-07-09

Consolidated feedback from the redesign + roadmap review session (Cowork).
Covers: what changed in the app, the UI redesign (with design references),
and the roadmap review against the user's target operating model —
**"quite automatic in analysis, tactic refined by backtesting: gather past
data, compare how it changed, teach the skill Codex uses."**

Companion artifacts produced in the same session:
`docs/design/design-v2.md` (design system), `docs/design/mockups-v2.html`
(4 mockup frames), `docs/plan-ui-refactor.md` (rewritten v2). This file is
the review record; those files are the working references.

---

## 1. What changed in the application (context for all feedback)

Three product identities accreted in two days, all still visible in the UI:

1. **Data presentation app** (Phases 1–4): watchlist + stock tabs over
   scraped financials, charts, forecast, forum.
2. **Decision workspace** (07-08): Brief tab (DecisionCockpit + InvestorMemo),
   decision-table watchlist, scaling radar, discovery checklist.
3. **Codex-operated analyst OS** (07-09, Stage CX): `agent_runs` queue with
   lifecycle states, strict-verifier contract
   (`prediction`/`potential`/`result_quality`), MCP worker bridge, ESPI/EBI
   `event_reports`, deterministic Backtest Lab with availability policies,
   Agent Evaluation replays with 30/90/180/365 d outcome windows.

## 2. UI feedback and redesign (delivered)

Findings against the current frontend:

- Dashboard is an 11-section vertical stack (~1600-line `page.tsx`) with the
  primary work surface (watchlist) at the bottom; operations/research panels
  squat above it.
- Three overlapping verdict surfaces on the stock Brief tab (DecisionCockpit,
  InvestorMemo, ThesisPanel) in different visual dialects.
- Run lifecycle / verifier / provenance markup is improvised per panel — no
  shared primitives, so every new CX surface reinvents status UI.
- `event_reports` are ingested but have no UI home.
- 2-item nav no longer matches the app; design docs v1 drifted from code.
- User verdict on v1 styling: too tight, wrong colors → **discarded, not
  iterated**.

Redesign decisions (user-approved direction):

- **Visual "Research studio"** (`design-v2.md`): warm paper bg, white cards
  with soft shadows, ink text, serif display for titles/big numbers, mono
  tickers, indigo accent `#3F4FC9`, pos/neg/warn washes, 15 px base, 8 pt
  grid, 232 px ink sidebar. Guardrails kept: Polish domain labels, `pl-PL`
  formatting, verifier/status always visible, explicit missing-data chips.
- **IA**: sidebar Watchlist (landing: "Dziś" strip + decision table + ops
  rail) · Candidates · Research (Backtest + Agent Evaluation move here) ·
  Operations (full queue/worker lifecycle, CX.12-ready) · Settings. Stock
  page: single verdict band + context rail + new **Zdarzenia** tab (reuses
  existing `GET /api/companies/{ticker}/event-reports` — zero backend work).
- **Shared primitives**: StatusChip, VerifierBadge, ProvenanceChip, RunRow,
  OutcomeWindows, MetricTile, EmptyState — one implementation, used
  everywhere, so CX.11–13 UI becomes cheap.
- **Six shippable migration slices** (tokens → shell → dashboard split →
  stock page → primitive adoption → mobile), no backend changes required.
  Detail: `docs/plan-ui-refactor.md` §5.

## 3. Roadmap review vs the target operating model

Target: automatic analysis; tactic refined via backtesting; outcomes teach
the skill Codex uses.

### 3.1 Already in the plan

- **CX.12** — queue + worker pickup contract (`codex_pick_agent_run.py`,
  queue-worker prompt, lifecycle closure on save). Plumbing, in progress.
- **CX.13** — agent-valuation backtests: measures whether saved Codex
  analyses were right (structured-fields-only parser, outcome windows).
- **CX.11** — names walk-forward backtesting + learning notes, verifier-gated.
- Scheduled entry points exist (`codex_pre_session.py`, pre-session API for
  cron/n8n).

### 3.2 Verified gaps (checked against the repo, not just docs)

1. **Nothing schedules or auto-triggers work.** Only a pickup script + prompt
   (`.codex/tasks/stock-queue-worker.md`); no scheduler, no event→queue rules
   (new ESPI report / quarterly results do not auto-enqueue re-analysis).
   Every run starts with a human click. Malik's method itself demands
   quarterly re-verify — currently manual.
2. **The data cannot teach anything yet.** 4 tickers; prices only since
   2026-04-28; all financial rows scraped 2026-07-09; no report publication
   dates. Point-in-time replay correctly returns `insufficient_data`; all
   30–365 d outcome windows missing. A tactic cannot be refined on 4 names
   and ~10 weeks. Price sources today: BiznesRadar only (stooq/Yahoo removed;
   EODHD/GPW noted in changelog as candidates, not wired).
3. **The loop never closes into the skill.** No `skill_version`/rubric hash
   anywhere in backend/frontend (grep-verified) → hit-rates cannot be
   attributed to a skill iteration. WorkedCase corpus = 4 hand-written cases,
   no growth pipeline. CX.13 ends at "learning notes"; no mechanism feeds
   outcomes back into `skill/SKILL.md`, `rubric.md`, `.agents/skills/stock-*`
   or the Malik profile weights.

### 3.3 Proposed roadmap changes

Ordered — data first, otherwise the loop learns nothing:

1. **CX.11 split & promoted to critical path:**
   - CX.11a price-history backfill (BR premium history depth; or re-add
     stooq/EODHD as *backfill-only* source; GPW official as candidate);
   - CX.11b real publication dates from the ESPI archive (honest look-ahead
     boundary — replaces the `estimated_period_lag` proxy);
   - CX.11c universe expansion well beyond the 4-ticker watchlist (politely,
     batch, fixture-tested).
2. **CX.15 Autopilot policies:** an actual scheduler (cron/n8n → existing
   endpoints + a scheduled Codex worker loop over the queue) plus
   event-driven auto-enqueue rules: new ESPI/quarterly report → quick
   re-analysis; stale dossier → refresh; post-report thesis re-verify.
   Per-ticker autopilot toggles + budget caps. Everything still lands behind
   the verifier gate before the UI shows "verified".
3. **CX.16 Skill versioning:** stamp skill + rubric version/hash on every
   `analysis_run` (and thesis/scenario outputs). Small, blocks everything
   downstream if skipped.
4. **CX.17 Case harvester:** when outcome windows complete, auto-draft a
   WorkedCase/example (wins **and** misses) → verifier review → append to
   corpus + `skill/examples/`. This is "gather past data, compare how it
   changed, teach the skill" made concrete.
5. **CX.18 Champion/challenger skill replay:** rerun a candidate skill
   version over frozen `input_snapshot`s (no new HTTP, no look-ahead),
   compare structured predictions vs known outcomes on a holdout period;
   promote only on `verifier_strict` pass with separated train/validation
   periods.

### 3.4 Safety caveat (kept deliberately)

Fully self-tuning weights/prompts would violate `docs/project-guardrails.md`
and would overfit on this data size. Recommended pattern: **auto-propose,
verifier/human approve** — ~95 % of the automation, none of the silent-drift
risk. This matches the existing rule that strategy changes need separated
validation periods + `verifier_strict`.

## 4. Open item — unresolved external plan files

A previous session presented `plan-research-platform.md` and
`research-workspace.md` (seen in chat file cards). **They are not in this
repository** (searched: project tree, docs/, previews/) and their content
could not be recovered from session transcripts. Consequence: whatever they
plan is invisible to repo sessions and to this review. Action: open those
cards → save both files into `docs/` (or paste into chat) so coverage can be
checked against §3.3; until then, TASKS.md + `docs/plan-stage-codex-pivot.md`
remain the only authoritative roadmap.

## 5. Suggested acceptance for "expectations met"

The user's target is reached when, with the app + a scheduled worker running:

- a new ESPI report or quarterly result for a watched ticker produces a
  verified re-analysis in the UI **without a human click**;
- every verified analysis carries workflow, model role, **skill version** and
  structured prediction;
- Agent Evaluation shows non-empty 30/90/180/365 d hit-rates over a growing
  history (real publication dates, multi-year prices, >20 companies);
- at least one skill/rubric revision has been adopted through the
  champion/challenger + verifier path, with the evidence linked in
  `docs/learning/agent-evaluation.md`.
