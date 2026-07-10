# Implementation Tasks

Companion to `PLAN.md`. Each phase ends with a runnable increment. Check off as we go; IDs are stable for referencing in sessions ("do P1.3").

Every completed phase additionally gets a one-page learning note `docs/learning/phase-N.md` (PLAN §13) — concepts introduced, C# analogies, where to look in the code. Not listed per phase to keep this file about the build.

---

## Phase 0 — Scaffold

**Goal:** empty but running skeleton of everything.
**Done when:** `docker compose up` starts Postgres, backend serves `/api/health`, frontend renders a page, first Alembic migration applies.

- [x] P0.1 Repo layout per PLAN §2; move source docs into `docs/source-materials/`; `.gitignore` (`.env`, `node_modules`, `__pycache__`, `.next`)
- [x] P0.2 `docker-compose.yml` with postgres 16 + volume; `backend/.env.example` (DATABASE_URL, PA_USERNAME, PA_PASSWORD, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
- [x] P0.3 Backend skeleton: FastAPI app factory, `config.py` (pydantic-settings), `/api/health` (checks DB connection) — no CORS needed, browser talks only to the Next proxy
- [x] P0.4 SQLAlchemy setup + all models from PLAN §4 + initial Alembic migration
- [x] P0.5 Frontend skeleton: `create-next-app` (TS, App Router), SCSS setup (variables, globals, dark theme base), route-handler proxy `app/api/[...path]` → `BACKEND_URL` (localhost:8000 in dev), api helper (`src/lib/api.ts`) calling the proxy, empty watchlist page
- [x] P0.6 README: how to run backend, frontend, DB locally

## Phase 1 — Module B: BiznesRadar + prices

**Goal:** one command/endpoint fills the DB with full financials for a ticker.
**Done when:** for a real ticker (e.g. DEC or NVT) all statements Q+Y, indicators, dividends, profile and prices are in Postgres; parser tests green against fixtures.

- [x] P1.0 Shared fetch helper `scrapers/http.py`: per-domain rate limiter with randomized jitter (BR 2–4 s, PA 1.5–3 s), realistic UA, exponential backoff on 403/429/5xx + hard stop after repeated failures, `fetch_log` writes — **all scraper requests go through this**
- [x] P1.1 Record fixtures: real SNT (GPW) + CRB (NewConnect) captures cover
  all nine page types, use profile-resolved canonical slugs and pass the
  structural/parser matrix; synthetic fixtures remain for small focused cases.
- [x] P1.2 Generic `report-table` parser: headers/periods, rows, `span.value` extraction, number + period normalization, units (tys. PLN); unit tests on fixtures
- [x] P1.3 Statement scrapers: income (Q+Y), balance, cashflow → upsert into `report_values`
- [x] P1.4 Indicator scrapers: wskaźniki wartości rynkowej (C/Z, C/WK, EV/EBITDA history) + rentowności → `indicator_values`
- [x] P1.5 Dividends scraper → `dividends`; profile scraper (name, sector, shares outstanding) → `companies`
- [x] P1.6 `stooq.py`: daily CSV → `prices` (initial load + incremental by date)
- [x] P1.7 Refresh orchestration: `POST /api/companies/{ticker}/refresh?scope=&force=` — sequential fetch, ~2 s delay, 24 h cache via `fetch_log`, per-page error isolation (one failed page ≠ failed refresh)
- [x] P1.8 Read endpoints: `/financials`, `/indicators`, `/dividends`, `/prices` + watchlist CRUD (`/api/watchlist`)
- [~] P1.9 BiznesRadar premium session (user has an account): optional
  `BR_USERNAME/BR_PASSWORD`, login before fetches, longer histories; summary
  gains a `br_login` entry. Login recipe is verified as fixed `POST /login/`
  with `email/password` and an `account-settings` marker. Remaining gap:
  browser-cookie handoff is not implemented; if a browser-only session shows
  richer data than backend credentials, capture/import needs a separate tool.
  `/prognozy` empty consensus columns are now reported explicitly.

## Phase 2 — Module A: PortalAnaliz forum

**Goal:** forum threads linked to companies and synced incrementally.
**Done when:** linking a real thread URL pulls all posts; second sync fetches only new ones; posts readable via API.

- [x] P2.1 phpBB login with `.env` credentials (port logic from reference: form tokens, session cookies); login test endpoint for `/ustawienia`
- [x] P2.2 Thread parser: pagination, post_no, author, ISO timestamp, text + HTML (structure per reference scraper); fixture test on saved thread page
- [x] P2.3 Topic linking: `POST /api/forum/topics` {url, ticker} → resolve canonical topic id, store in `forum_topics`
- [x] P2.4 Sync: full first pull, incremental after (from max post_no); all requests via `scrapers/http.py` (jittered delays, backoff); `POST /api/forum/topics/{id}/sync`
- [x] P2.5 Read endpoint: `GET /api/companies/{ticker}/forum?page=&author=` (paginated, newest first)
- [x] P2.6 Post upvotes: `forum_posts.upvotes` (migration 0002), live-verified
  `a.post-reputation` parsing plus selector/text fallbacks, `sort=top` API + UI
  toggle; the authenticated recorder stores a minimal sanitized real fixture
  with no account/session/post content.

## Phase 3 — Module C backend: metrics, prescore, forecast, dossier

**Goal:** everything computed that the UI and the AI both need.
**Done when:** dossier endpoint for a refreshed ticker returns metrics matching hand-checked BiznesRadar numbers; forecast reproduces the Novita transcript example within rounding.

- [x] P3.1 `metrics.py`: quarterly series — revenue r/r, marża brutto na sprzedaży, sales margin after SG&A, net margin, operating leverage, one-off share; unit tests with hand-checked values
- [x] P3.2 TTM aggregates: net profit, EPS, market cap (latest price × shares), C/Z TTM; C/Z-vs-own-history stats (median, quartiles, current percentile)
- [x] P3.3 Net cash/debt from balance sheet; dividend continuity summary
- [x] P3.4 Deterministic prescore: 8 rules from PLAN §7, each → pass/fail/unknown + evidence numbers; JSON output shared by UI and AI prompt
- [x] P3.5 `forecast.py`: default assumptions derived from history (PLAN §7 table), pure compute → full forecast P&L, EPS, EBITDA, y/y comparison, forward C/Z; save/list scenarios (JSONB)
- [x] P3.6 `dossier.py` + `GET /api/companies/{ticker}` — single JSON: company, freshness, metrics series, TTM, prescore, latest forecast summary, forum stats (post count, last post)

## Phase 4 — Module C frontend: watchlist + stock pages

**Goal:** the app replaces the Excel workflow end to end.
**Done when:** you can add a ticker, refresh it, browse financials/charts, build and save a forecast, and read the forum — all in the UI.

- [x] P4.1 Layout: nav, dark SCSS theme with tokens from `docs/design/design.md`, loading/error states, PLN/percent formatters (`pl-PL`) — all Phase 4 UI follows `docs/design/mockups.html`
- [x] P4.2 Watchlist page: table per PLAN §7, add/remove ticker, refresh button with progress state, freshness indicator
- [x] P4.3 Stock page shell + **Przegląd** tab: key numbers, prescore checklist with evidence, price chart (recharts)
- [x] P4.4 **Finanse** tab: statement tables Q/Y with period columns (BiznesRadar-like layout)
- [x] P4.5 **Wykresy** tab: przychody, marża brutto %, zysk ze sprzedaży, zysk netto — quarterly sequence + y/y quarter grouping (his two Excel views)
- [x] P4.6 **Prognoza** tab: assumption form prefilled with defaults, live recompute, forward C/Z result vs historical C/Z range, save/load scenarios
- [x] P4.7 **Forum** tab: link-topic form, post timeline, author filter, pagination
- [x] P4.8 `/settings` (nav in English per user decision): status checks (DB, PA login, Anthropic key present)

## Stage TH — Investment-thesis layer (rule-based, pre-Phase-5)

**Goal:** per-stock investment-thesis read in Malik's spirit — weighted
pros/cons + entry-point quality + "what to check next", composed from the
computed dossier (pure functions, like `insights.py`). Entrance point for human
analysis, **not** a buy signal; **not** the Phase 5 Claude layer. Full spec:
`docs/plan-stage-thesis.md`.
**Done when:** `docs/strategy-malik.md` is source-cited; `thesis.py` +
`test_thesis.py` green in-session; `ThesisPanel` renders traceable numbers;
DGN/SNT + current-cap validation documented with gaps; memory/changelog updated.

- [x] TH.1 Source-grounded strategy spec `docs/strategy-malik.md` (≥5 primary
  web sources + reconcile 3 source-material files; every principle cited +
  mapped to a computed field or a labelled gap; entry-quality thresholds)
- [x] TH.2 Generic engine `services/thesis.py` + `services/strategies/`
  (`base.py` StrategyProfile/Criterion interface, `malik.py` profile-as-data,
  `cases.py` WorkedCase + evaluate_case) + `test_thesis.py` (in-session):
  entry quality, weighted pros/cons, `verify_next`, forward-C/Z preference,
  honest gaps, fabrication guard, toy-profile genericity test; wire into
  `dossier.py` + `api/schemas.py` (compile-check)
- [x] TH.2b Optional Claude-API iterative thesis refiner `services/thesis_ai.py`
  + config (`anthropic_max_iterations`, `ai_cache_enabled`) + `test_thesis_ai.py`
  (stub transport): **injectable transport** (anthropic SDK if importable →
  stdlib `urllib` POST → `StubTransport` in tests), bounded N-round refine of the
  WP2 read against the `WorkedCase` corpus + active profile, schema +
  fabrication-guard validation, JSON-file cache keyed by
  `(ticker, input-hash, model, profile-version)`, **no-key fallback** to the
  deterministic read with an `engine: deterministic|ai` marker; stub-tested paths
  (happy/malformed/iteration-limit/fabrication/convergence + cache), real-call
  smoke deferred to user (`ANTHROPIC_API_KEY=… python scripts/thesis_ai_smoke.py
  SNT`). Deterministic-first — does **not** replace Phase 5 (`skill/`/`analyses`/
  AI tab). Full spec: `docs/plan-stage-thesis.md` §WP2b
- [x] TH.3 `ThesisPanel.tsx` top of Overview (above InsightsPanel) + `types.ts`
  `Thesis`; as-is rendering, degraded states, disclaimer (build deferred to user)
- [x] TH.4 Validation `docs/validation-thesis.md`: DGN/SNT historical (with
  gaps, no fabricated figures) + ≥4 current small/mid/large caps, numbers
  cross-checked; archiwum page 1 only, quirks not re-derived; DGN/SNT recorded
  as `WorkedCase` entries *(in-session part done + verifier-approved: fixture
  pipeline + size-lens comparability + DGN/SNT `WorkedCase`s, documented with
  gaps per the rescoped WP4 acceptance #1. **Deferred to the user's machine**
  (sandbox has no egress): the live ≥4-ticker cross-check + DGN/SNT deep
  backtest via `cd backend && python scripts/validate_thesis.py DGN SNT …` —
  results append to `docs/validation-thesis.md`.)*
- [x] TH.5 Conformance + memory: in-session test subset green, `docs/learning/
  phase-thesis.md` (C# analogies), CLAUDE.md doc index + final CHANGELOG entry

## Stage SC — Scenario simulation engine (deterministic-first + AI)

**Goal:** per-stock simulation-based scenarios (negative/base/positive + event)
— each with coherent probability, data-grounded narrative, sector-relevant
target valuation (C/Z · C/WK · EV/EBITDA) off own + comparable multiple history,
repricing horizon, implied upside, and a probability-weighted EV vs current
price — plus an AI valuation agent (potential + confidence + what-would-change).
Extends the `thesis_ai.py` deterministic-first pattern; surfaced next to
`ThesisPanel`, framed as an analysis entry point, not a signal. Full spec:
`docs/plan-stage-scenarios.md`.
**Done when:** `scenarios.py`/`test_scenarios.py` + `scenarios_ai.py`/
`test_scenarios_ai.py` + `valuation_ai.py`/`test_valuation_ai.py` green
in-session; `ScenariosPanel` renders traceable numbers; corpus enriched with
sourced multiples/durations incl. ≥1 miss; validation + memory/changelog updated.

- [x] SC.1 Compact context: CLAUDE.md index + archive closed Stage-TH changelog
  entries into `docs/changelog-archive-thesis-2026-07-08.md` (quirks ledger left
  byte-identical); no code change
- [x] SC.2 Clean project: remove provably-dead code (per-item zero-reference
  grep proof in the CHANGELOG); full runnable test suite green as the safety proof
- [x] SC.3 Scenario engine: pure `services/scenarios.py` (multiple-reversion
  targets off own + corpus multiple history, Σ-prob=1, weighted EV) +
  `services/scenarios_ai.py` (bounded rounds, cache, fabrication guard over
  inputs∪engine∪corpus, no-key fallback) + `test_scenarios.py` (≥9) +
  `test_scenarios_ai.py` (≥10); wire `scenarios` block into `dossier.py`/
  `schemas.py`; `ScenariosPanel.tsx` + `types.ts`; `scripts/scenarios_smoke.py`
- [x] SC.4 AI valuation agent `services/valuation_ai.py` (potential + confidence
  + what-would-change; same guard/cache/fallback) + `test_valuation_ai.py` (≥8);
  enrich `strategies/cases.py` WorkedCase corpus with sourced multiples/durations
  incl. ≥1 documented miss (lazy CORPUS + import purity preserved); wire
  `valuation` block into dossier/schemas + panel/types
- [x] SC.5 Validation `docs/validation-scenarios.md` (hand-checked targets/EV,
  fixture-first, gaps explicit) + exact test counts + `docs/learning/
  phase-scenarios.md` (C# analogies) + CLAUDE.md index + final CHANGELOG entry

## Phase 5 — Module D: strategy skill + Claude analysis

**Goal:** one click → structured verdict on strategy alignment and potential.
**Done when:** analysis of a real watchlist stock returns valid schema, sensible Polish summary, stored history; verdicts reference actual evidence (numbers, forum posts).

**Reconciliation with Stage TH (TH.2b, 2026-07-08).** The Claude transport,
`.env` config, and response-cache pattern now exist from TH.2b's engine-level
thesis refiner (`services/thesis_ai.py`), and the dossier `thesis` block already
carries an `engine: deterministic|ai` marker. So **P5.4 (`claude_client.py`)
builds on / reuses that transport** rather than starting fresh. P5.1–P5.3
(skill/rubric/examples), P5.5 (prompt assembly for the full verdict + forum
distillation), P5.6–P5.7 (`analyses` table, endpoints, Analiza AI tab + history,
`AI_DAILY_LIMIT`), and P5.9 remain as-is — the Phase-5 *analysis product* is
distinct from TH.2b's thesis-block refinement. Tasks below are not rewritten.

- [x] P5.1 Author `skill/SKILL.md`: distill the 4 source docs (philosophy, 14-point checklist, 7 golden rules, catalyst taxonomy, one-off guidance, red flags, valuation via forward C/Z vs own history). **Draft done — review together before wiring it in (P5.4+)**
- [x] P5.2 `skill/rubric.md`: item weights → alignment_score 0–100; explicit "unknown ≠ fail" scoring rule
- [x] P5.3 `skill/examples/`: 2–3 worked examples distilled from obs.txt reasoning (real thesis → outcome) — OPTEX (win), TOYA (durable discount), Suntech (documented miss)
- [x] P5.4 `claude_client.py`: anthropic SDK, forced JSON output (tool use) with schema from PLAN §8, retries, token logging — `run_analysis` + `AnalysisUnavailable` (no deterministic fallback); 17 pure tests green
- [x] P5.5 `prompts.py`: system = SKILL.md + rubric; user = dossier JSON + token-capped recent forum posts + prescore; deterministic assembly (snapshot returned; note: not persisted — `analyses` table has no snapshot column)
- [x] P5.6 Endpoints: `POST /api/companies/{ticker}/analyses` (run), `GET .../analyses` (history); persist output + tokens + requesting user email; global `AI_DAILY_LIMIT` cap (429 with Polish message when hit) — no migration needed (`analyses` already in 0001); 4 client-gated tests deferred to user machine
- [x] P5.7 **Analiza AI** tab: run button, verdict card (score, thesis, catalysts, red flags, verify-next), history list with diff vs previous run — `AnalysisPanel`, tsc green
- [ ] P5.8 Calibration pass — **superseded by RT.6**. Do not tune a skill to
  3–4 familiar winners. Build mixed-outcome training + untouched holdout cases,
  then use the judge loop and walk-forward protocol below.
- [x] P5.9 Forum distiller (PLAN §8): batched cheap-model pass over already-synced posts → per-post cached claims {type, claim, confidence, source post ids}; upvote-weighted ordering within token budget; zero extra forum requests; verdict prompt consumes claims, never raw posts as facts — file cache, 15 pure tests

## Stage CX — Codex-centered analyst operating system

**Goal:** pivot from the Claude API as the app's analysis backend to Codex as
the supervised analyst/operator. The app remains the durable data store and
readable UI; Codex uses repo skills, local scripts and MCP tools to gather,
analyze, verify and save structured results. Model choice is precision/risk
first: bounded routine tasks use an appropriate worker model, deeper synthesis
and all UI-visible verification use stronger supervised roles. Full spec:
`docs/plan-stage-codex-pivot.md`.
**Done when:** Claude/Anthropic app dependencies are removed or archived,
provider-neutral analysis/agent runs are stored in Postgres, Codex skills can
save verified analyses visible in the UI, ESPI/EBI and candidate/backtest flows
are tool-accessible, and verifier-gated outputs are auditable.

- [x] CX.1 Plan and contracts: `docs/plan-stage-codex-pivot.md` with diagrams
  for scheduled, manual-chat, UI-requested, candidate and backtest flows;
  supervised-agent policy; model-role routing; durable DB outputs; project
  guardrails; changelog entry. No code/schema changes.
- [x] CX.2 Provider-neutral storage: add analysis/agent/verification/event/
  candidate/backtest run storage with `workflow`, `model_role`, `model`,
  `agent_run_id`, `verification_status`, and `input_snapshot`; keep old
  `analyses` readable until UI migration.
- [x] CX.3 Local script contract: JSON scripts for dossier read, analysis save,
  ESPI polling, candidate scan and backtest replay; mutating scripts require
  verification metadata and never expose secrets.
- [x] CX.4 Repo skills: `.agents/skills/stock-*` workflows for pre-session
  brief, quick analysis, deep analysis, candidate scout, backtest review and
  strict verification; subtasks route by precision/risk to `worker_standard`;
  future sessions inspect `docs/project-guardrails.md` before and after each
  phase/work package.
  - 2026-07-10 routing refinement: `stock-deep-analysis` uses
    `gpt-5.3-codex-spark` for long primary-source research and the full draft.
    The strongest configured `verifier_strict` model independently owns final
    prediction/confidence/result quality and pass/fail; both passes are stored
    in the frozen model trace.
- [x] CX.5 MCP server: expose stable app tools (`get_company_dossier`,
  `save_analysis_run`, `list_queued_agent_runs`, etc.) to Codex with structured
  JSON and explicit approval policy for mutating tools.
- [x] CX.6 ESPI/EBI ingestion: fixture-tested event scraper(s), watchlist poller,
  materiality storage and pre-session brief integration; all HTTP through
  `scrapers/http.py`; scheduled pre-session entrypoint queues GPT/Codex brief
  work after fetching watched-company reports.
- [x] CX.7 UI queue and results: web app can queue Codex workflows, show
  queued/running/completed/rejected states, and render verified Codex analysis
  with source links and verifier badges.
- [x] CX.8 Backtest and learning loop: point-in-time snapshots, deterministic
  replay, future outcome attachment, look-ahead tests, UI Backtest Lab.
- [x] CX.9 Codex-first UI + compatibility runway: active user-facing analysis
  path uses provider-neutral `agent_runs`/`analysis_runs`, workflow status and
  MCP/scripts; legacy Phase-5 endpoints/modules may remain only as explicit
  compatibility until sunset.
  - 2026-07-09 progress: user-facing frontend path retired. Analysis tab now
    queues Codex and renders provider-neutral `analysis_runs`; Settings uses
    `/diagnostics/workflow-status` instead of provider-key status. Backend
    compatibility routes/modules remain for the next removal/archive slice.
  - 2026-07-09 progress: added the result-quality verifier loop for quick/deep
    company analysis and a save-time contract guard. Verified outputs now need
    structured `prediction`, deterministic `potential`, and `result_quality`
    fields; downside/limited scenarios and one-off gaps must be surfaced before
    the UI can show an analysis as verified.
  - 2026-07-10 closed: the active user-facing path is provider-neutral
    (queue → agent_runs/analysis_runs → verifier-gated report). Remaining
    legacy endpoints/modules exist only as the explicit compatibility runway
    this task allows; their removal/archive is CX.10's scope.
- [ ] CX.10 Legacy model-provider sunset/archive: remove or archive
  Anthropic/Claude config, clients, direct analysis endpoint behavior and
  compatibility tests after provider-neutral saved-analysis flows cover the
  same user needs. Done when active code/docs pass an `rg
  "Claude|ANTHROPIC|anthropic"` sweep except historical archives and explicit
  migration notes.
  - Ordering note (2026-07-10): blocked by RT1.3's remaining legacy-path
    migration (direct-client compatibility + forum distillation behind the
    orchestrator); run the sweep only after that lands so removal is a delete,
    not a rewrite.
- [ ] CX.11 Backtest data-readiness + prediction learning: add historical
  report availability/publication dates or point-in-time snapshots, expand
  historical prices, then run walk-forward multi-asset strategy reviews.
  `gpt-5.3-codex-spark` can run candidate/backtest loops and anomaly
  summaries; 5.5/verifier is required before changing strategy weights or
  saving prediction-quality conclusions.
  - 2026-07-09 progress: added opt-in `estimated_period_lag` research policy
    for deterministic backtests. Default remains strict `scraped_at`; estimated
    runs are marked research-only / `needs-human` and cannot justify strategy
    changes without verifier review and better source dating.
  - 2026-07-09 progress: Backtest Lab now supports inline stored-run
    drill-down. It fetches `GET /api/backtest-runs/{id}`, exposes the
    financial-availability policy in the run form, and shows verifier state,
    policy warnings, observation checks and outcome windows in the dashboard.
  - Scope note (2026-07-10 de-duplication): CX.11 now owns **data readiness
    only** (publication dates/point-in-time snapshots, historical price depth).
    The "walk-forward strategy reviews" half is owned by CX.16 (pragmatic,
    research-only) and RT6.6 (strict); do not log replay work here.
- [x] CX.12 Web-triggered / Codex-scheduled queue execution: keep the web API as
  durable queue creation, but add a Codex worker pickup contract so a manual,
  background or scheduled Codex run can claim queued jobs, execute the relevant
  skill/MCP/script workflow and close the `agent_run` lifecycle when output is
  saved.
  - 2026-07-09 progress: added `codex_pick_agent_run.py`, a reusable
    `.codex/tasks/stock-queue-worker.md` prompt, and lifecycle closure in
    `save_analysis_run`/`codex_save_analysis.py` so saved output updates the
    original queue row instead of leaving it stuck.
  - 2026-07-09 progress: added `complete_agent_run` plus
    `codex_complete_agent_run.py` for watchlist-level jobs such as
    `stock-candidate-scout` that do not produce a single company analysis row.
    A supervised `gpt-5.3-codex-spark` worker attempted a candidate-scout claim
    and correctly stopped because the queue was empty.
  - 2026-07-10 progress: Discover now defaults to recall-first `rating >= 5`
    with no mandatory F-Score, retains up to 300 candidates and labels missing
    F-Score as a gap. Every immutable BR market snapshot ensures one durable,
    concurrency-safe aggregate `stock-candidate-scout` job (`recall-v1`), with
    a 12-name evaluation budget and no automatic watchlist/company crawl.
    Pickup consumes the frozen source list; per-company candidate persistence,
    bounded dossier-refresh transitions and a continuously scheduled worker
    remain follow-ups.
  - 2026-07-10 progress: live runtime verified `246/384` recall candidates;
    job `#4` was created once and reused on an identical request. Company-page
    requests now queue `stock-deep-analysis` with 5.3 Spark research/drafting
    and reserve prediction/result-quality approval for the strongest verifier.
  - 2026-07-10 progress: created an active local Codex automation that runs
    every ten minutes, starts/checks the workbench, claims exactly one oldest
    row and applies the 5.3-research/strong-verifier contract. Runtime proof:
    candidate-scout `#4` completed with verifier `pass`; SNT deep-analysis `#5`
    was subsequently claimed, researched by Spark, independently verified by
    `gpt-5.6-sol`, and closed as `needs-human` (not left queued/running). Its
    deterministic read is neutral, `+9.8%`, score `54/100`; catalyst/backlog
    are confirmed, governance is partial, and approval waits for versioned
    issuer evidence plus human governance review. The automation is host-local
    and must be recreated on another Mac; durable queue/claim/save contracts
    stay in repo.
    After completion, Discover polls that exact run and shows its verified
    batch status plus per-ticker source-prescreen scores without presenting
    them as full investment ratings.
  - 2026-07-10 closed: durable queue creation, claim/save lifecycle and the
    worker contract are runtime-proven. The remaining "continuously scheduled
    worker" follow-up is deliberately NOT part of this task anymore — periodic
    execution is reclassified as an opt-in variant under CX.15d; the default
    operating model is session-triggered (CX.15).
- [ ] CX.13 Agent valuation backtests: evaluate saved `analysis_runs` and
  valuation memos against future price/source outcomes. See
  `docs/plan-agent-valuation-backtest.md`. First slice is schema + Python replay
  for saved agent outputs only; verifier review is required before any prompt or
  strategy rule changes.
  - 2026-07-09 progress: implemented the first deterministic replay slice for
    structured saved `analysis_runs`: DB models/migration, service, API,
    Codex script, MCP tool, frontend contracts and tests. Prose-only outputs are
    not inferred; they are marked `unknown` / `needs-human`.
  - 2026-07-09 progress: added the dashboard Agent Evaluation panel so saved
    agent-output replays can be created and inspected in the UI with verifier
    state, model role, structured prediction source, outcome windows and
    missing-data warnings.
  - 2026-07-09 progress: saved a CBF `stock-quick-analysis` output with the
    required structured prediction/potential/result-quality fields. Agent
    evaluation parses it correctly as a negative prediction with `-10.1%`
    potential, but the replay remains `needs-human` until future 30/90/180/365d
    price windows are present.
  - 2026-07-09 progress: Analysis tab now surfaces those structured fields in
    the selected saved run: direction/potential manifest chip, prediction
    horizon, deterministic potential range, scenario validity, confidence,
    source fields and `result_quality` notes.
  - Next: run evaluations only after new verified outputs contain the required
    structured prediction fields; use `gpt-5.3-codex-spark` for repeated replay
    sweeps/anomaly summaries and `verifier_strict`/5.5 high before changing
    prompts, thresholds or strategy notes.
- [ ] CX.14 UI workbench refactor: restructure the dashboard into primary
  watchlist surface plus compact operations rail, make queue execution state
  explicit, and improve provenance/status density. See `docs/plan-ui-refactor.md`.
  - 2026-07-09 progress: first Analysis-tab density slice completed. Saved runs
    now behave more like a compact manifest plus selected detail panel with
    verifier/model/source badges always visible. Next UI slice should move to
    dashboard composition: primary watchlist surface plus operations rail.
  - 2026-07-09 progress: queue truthfulness slice completed. Dashboard and stock
    Analysis tab now show recent `agent_runs` across statuses, explicitly frame
    `queued` as waiting for Codex/MCP execution, and surface
    `outputs.analysis_run_id` when a worker saved an analysis. A 5.3 audit pass
    then added 30s silent polling and mobile wrapping for the Analysis toolbar.
  - 2026-07-10 progress: company pages are report-first. The default screen is
    a concise prepared report plus key charts; full financial tables, forum
    leads, checklist details and historical model output moved behind Source/
    Codex audit views. Old `needs-human` analyses are no longer selected as the
    current report. A current model result must be verifier `pass` and match the
    normalized valuation snapshot.
  - 2026-07-10 progress: the prepared report now leads with deterministic or
    verifier-owned potential, scenario confidence and company score; strategy
    size fit is excluded from visible risks. Catalyst, backlog and governance
    are displayed as Codex research outcomes/statuses, not instructions to the
    user. First refresh has one honest progress surface, watchlist rows use a
    compact decision read, and queued jobs identify the external-worker
    dependency.
  - Scope note (2026-07-10 de-duplication): remaining dashboard-composition
    work (primary watchlist surface + operations rail) is owned by RT4.5/RT4.6
    and `docs/design/research-workspace.md`. This ID stays for history; log
    new UI work under RT.4.
- [ ] CX.15 Session-triggered operating model (pull-based ESPI + queue; decided
  2026-07-10): the workbench is a local, at-the-desk tool, so ingestion and
  queue execution are triggered by the user's session, not by an always-on
  scheduler. Malik-style decisions have hours-not-minutes latency needs; a
  10-minute poller adds GPW load and silently stops when the Mac sleeps.
  - [ ] CX.15a ESPI completeness watermark: persist `last_polled_at` per source
    and extend `scrapers/espi.py` to paginate the GPW list until
    `published_at <= watermark` (hard page cap + existing per-domain politeness
    limits). Fixture tests for multi-page walk and cap stop. This makes
    once-per-session polling retrospectively complete — a busy reporting
    evening must not scroll a watched report off page 1 unseen.
  - [ ] CX.15b `workbench start` pre-session hook: after health checks, run the
    pre-session brief (poll ESPI → ingest → enqueue triage) and process the
    queue once. Idempotent; failures reported as diagnostics, never blocking
    startup.
  - [ ] CX.15c UI re-check actions: a "Sprawdź komunikaty ESPI" button on the
    Research header calling the existing `prepare_pre_session_brief`, and a
    "process queue once" action for mid-session pickup. Both show run progress
    in the activity surface, no page-blocking work.
  - [ ] CX.15d Reclassify periodic execution as an **optional variant**: the
    10-minute host-local Codex automation (CX.12) and any future hosted poller
    are opt-in for hosts that want away-capture; default is off. Document the
    variant + recreation steps next to `.codex/tasks/stock-queue-worker.md`;
    a hosted poller/scheduled refresh remains an RT.7 decision.
  - Acceptance: with the scheduler disabled, opening the workbench surfaces all
    watched-company ESPI/EBI reports published since the previous session
    exactly once, queued triage runs to completion or reports why not, and no
    background process is required for correctness.
- [ ] CX.16 Retrospective cohort replay (added 2026-07-10): first empirical
  validation of the deterministic analysis layer against realized 1–3-year GPW
  outcomes. Answers "would this tool have made the right call?" — the honest
  version of "test on stocks that performed well".
  - [ ] CX.16a Cohort selection with anti-bias rules, frozen BEFORE any replay
    runs and stored as an immutable document: from a declared universe snapshot
    (BR rating/coverage list), pick N solid winners (top 1–3y total return,
    filtered to durable businesses — profitable, revenue-backed, no one-event
    biotech/gaming spikes), N matched controls (similar cap/sector/liquidity at
    T with mediocre/poor outcome), and ≥3 failures/delistings if reconstructible.
    Winners-only testing is invalid — it measures sensitivity but not whether
    the tool also says yes to losers; a scorer that always says "buy" passes it.
    BR-today sampling omits delisted names: record this survivorship limit on
    every result.
  - [ ] CX.16b Point-in-time reconstruction at `as_of=T` per case: deterministic
    dossier built only from quarters published before T using the existing
    `estimated_period_lag` research policy (CX.11), price at T from stored
    history. Record the restatement caveat: current BR tables may show restated,
    not as-published, values.
  - [ ] CX.16c Replay + storage: prescore, checklist verdicts, deterministic
    thesis and scenario range computed at T; persisted as research-only
    `analysis_runs` (never UI-verified, never watchlist-visible).
  - [ ] CX.16d Outcome comparison: 1/2/3y total return (include dividends where
    stored) vs a sWIG80-based benchmark; falsifier hit-timing where
    reconstructible. Report: prescore separation winners vs controls, veto
    false-kill rate (vetoed future winners), descriptive checklist-item vs
    outcome table, and per-case qualitative cards ("what the tool would have
    said, what it missed") — for a single investor the cards are the primary
    learning artifact, the statistics are diagnostic only at n≈30.
  - Hard honesty rules: NO AI-refined thesis or model verdict in scored replay
    results — models know these companies' actual outcomes from training data,
    so historical "AI calls" are contaminated by construction; deterministic
    layer only. Hold out one third of the cohort untouched before any
    weight/threshold tuning; results never justify strategy changes without
    the RT.6 verifier gate. Small-n results are diagnostic, not proof.
  - Relationships: builds on CX.11's `estimated_period_lag` policy + backtest
    service/Lab and CX.13's replay storage. CX.16 is the pragmatic precursor
    of RT6.6 — same question, estimated publication lags instead of strict
    point-in-time data. RT6.6 supersedes these results once real publication
    timestamps/corporate actions exist; until then everything stays
    research-only. Winner/control cases become candidate RT6.1 gold cases.
    Distinct from CX.13, which grades outputs that were actually saved at the
    time; CX.16 replays hypothetical historical reads.
  - [ ] CX.16e Multi-`as_of` expansion (added 2026-07-10): grow sample size by
    replaying each company at several **event-anchored** decision points — the
    natural valid points in time are report publications, not arbitrary dates.
    Statistical honesty rules: rows from the same company are NOT independent
    samples (overlapping outcome windows share one trajectory), so headline
    stats aggregate per company (cluster-by-company; prefer non-overlapping
    12m outcome windows), and 10 companies × 8 dates is closer to 10–15
    effective observations than 80. The unique value of the per-company time
    series is a different question breadth cannot answer: **thesis
    trajectory** — did score/falsifiers strengthen or break correctly between
    consecutive reports (Malik's "sell when the thesis stops confirming").
  - [ ] CX.16f Masked AI replay (optional; soft evidence only): training-data
    contamination cannot be truly removed — a model cannot un-know an outcome,
    and "pretend it's 2023" suppresses only explicit leakage, not shaped
    priors. Permitted mitigations, in required order: (1) contamination probe
    per case — separately ask the model what it knows about the company and
    its subsequent performance; any outcome knowledge excludes the case from
    AI replay; (2) masked dossier — strip name/ticker/city/identifying ESPI
    strings, keep numbers and neutralized qualitative claims (works best
    precisely for obscure GPW small caps); (3) score the model on **process,
    not calls** — one-off detection, falsifier choice, claim extraction
    checked against the documents, where ground truth is in the source, not
    in the future. Outcome-scored AI results are labelled
    `contamination-risk` and never gate a change alone; deterministic replay
    (CX.16a–d) remains the only clean layer.
- [ ] CX.17 Evidence-backed automation of `verify_next` checks (added
  2026-07-10): progressively convert today's human-only gaps (backlog/order
  book, guidance credibility, governance events) into computed, cited
  dossier features — the honest version of "the tool learns to do the
  qualitative work". Path: RT2.3 ledger ingestion supplies versioned issuer
  documents → AI **extraction with mandatory source citations** turns them
  into typed facts (backlog values, guidance statements, related-party
  events) → deterministic comparators compute the feature (e.g. a
  promise-vs-delivery tracker: guidance given in report N vs realized in
  N+2, per management team) → CX.16/RT6.6 replay measures whether the
  feature separates outcomes → weights/thresholds change only through the
  RT6.4 holdout-gated loop. Models extract and summarize; they never own the
  judgment number. Not learnable end-to-end at n≈30–100 without overfitting —
  the learning loop tunes transparent parameters and extraction quality, not
  prose opinions.

### Relationship to the RT roadmap

Stage CX records the provider-neutral Codex queue, MCP, evaluation and
backtest capabilities already built on `main`. Its unfinished compatibility,
data-readiness and UI items are retained as historical work IDs, but new work
must satisfy the stricter evidence-first gates in RT.1, RT.2, RT.5 and RT.6
below. In particular, existing replay infrastructure is not proof that the
current data is point-in-time or backtest-ready.

**Execution order of the open items (2026-07-10):** RT stages proceed in
numeric order as before. The open CX items slot in as follows — CX.15
(session-triggered ops) is independent and may run now; CX.16 (cohort replay)
may run now as research-only since its dependencies (estimated-lag policy,
backtest service) already exist, and it feeds RT6.1 gold cases; CX.10 (legacy
sunset) waits for RT1.3's remaining legacy migration; CX.11 is data-readiness
only and naturally lands with RT.2 evidence work; CX.13 continues as verified
outputs accumulate; CX.14's remaining scope is executed as part of RT4.5/4.6,
not separately. Stage IL below interleaves with RT.2–RT.4: IL.1/IL.2 first,
none of it blocked on ledger completeness.

## Stage IL — Investor decision loop (added 2026-07-10; interleaves with RT.2–RT.4)

Rationale: the RT stages build research infrastructure; these thin slices make
the daily investing loop pay off now. Principles they implement, decided in
the 2026-07-10 usability review: "what changed since I last looked" is the
highest-frequency investor question; the journal is the cheapest high-value
feature and produces the decision/confidence data RT.6 calibration and CX.16
replay need anyway; the sell side (falsifiers) deserves a surface equal to the
buy side; the tool improves decisions only if a feature changes one — check
that monthly. All slices reuse existing contracts (CX.15 session model,
dossier state, `event_reports`); none require the evidence ledger to be
complete.

- [ ] IL.1 Decision journal: one table + one form (ticker, date, decision
  buy/hold/sell/pass/trim, size, confidence, reasoning, thesis snapshot id,
  planned review date). Entry points on the company Brief and the Research
  queue; append-only (corrections are new entries, history never rewritten).
  Under one minute to record. Feeds CX.16 calibration and RT6.1 gold cases.
- [ ] IL.2 "What changed" monitor diff: after a session's ingestion (CX.15b),
  each affected company gets one diff card vs the stored thesis — flipped
  checklist verdicts, touched falsifiers, new one-off flags, valuation-vs-own-
  history move, new ESPI/report titles. Pure comparison of dossier state
  before/after refresh; no new scraping, no model calls. The card is the
  queue's stated reason a case needs attention.
- [ ] IL.3 Falsifiers first-class + thesis-at-risk ordering: falsifier rows get
  explicit status (`holding` / `warning` / `fired`) updated by IL.2 diffs and
  human toggle with a required one-line reason. Research queue default sort
  becomes thesis-at-risk (fired falsifiers > flipped checklist > stale
  evidence > freshness). Implements Malik row 13 — "sell when the thesis stops
  confirming" — as a surface, not a memory.
- [ ] IL.4 Minimal position ledger (read-only): ticker, entry date/price,
  size, linked journal entry/thesis version. No broker sync, no P&L
  dashboard. Purpose: the queue shows real-money-at-risk first, and the Brief
  can flag the ~10 % position-sizing rule (Malik row 15). Positions never
  influence scoring or verdicts.
- [ ] IL.5 UI simplification/alignment slice: declare the canonical screen set
  in `docs/design/research-workspace.md` and map the four live tabs onto it
  (ends the tabs-vs-contract drift); progressive disclosure — a surface
  appears only when its data exists, no empty Evidence/Business shells before
  RT.2/RT.3; Brief gains the falsifier strip, the latest "what changed" line
  and the journal button while keeping exactly one canonical read per company;
  Playwright screenshot pass at 1280/390 px for changed surfaces.
- Acceptance: after a new report lands for a held company, one session shows —
  with no always-on process — what changed vs the thesis and whether a
  falsifier fired, lets the user record the decision in under a minute, and
  the queue orders by thesis-at-risk. No duplicated verdict surface returns.

## Stages RT.0–RT.7 — Research-platform roadmap (binding next work)

**Goal:** evolve the completed first vertical slice into the evidence-first,
company-specific research workflow in `docs/plan-research-platform.md`.
Deployment is RT.7, after the local pilot proves provenance, scenarios and
evaluation. IDs below are stable.

### RT.0 — Trustworthy baseline

- [x] RT0.1 Fix the two currently failing backend tests and prove the full suite
  is green without weakening assertions; document why fixture/current-price
  expectations drifted.
- [~] RT0.2 Reproduce frontend from a clean install (`npm ci`, typecheck,
  production build); add a minimal browser smoke test for add → refresh → stock
  brief → forecast/scenario → analysis history. **Clean install/build/audit and
  manual browser smoke are green; persist the automated Playwright path after
  the RT.4 workflow contracts replace the current overlapping views.**
- [x] RT0.3 Finish real-fixture gaps: SNT (GPW) + CRB (NewConnect) cover every
  BR page type; premium login succeeds with the fixed endpoint/session marker;
  authenticated PA capture proves `a.post-reputation` and is sanitized before
  persistence. Recorder/login/parser focused suites are green.
- [x] RT0.4 Add one `doctor` command/report covering DB, backend, frontend,
  credentials, source reachability and model providers; run one documented
  end-to-end local pilot. The 2026-07-10 pilot recovered a stale-worktree
  Compose port collision, passed `doctor/start/status`, completed a live SNT
  financial refresh (nine polite requests), traversed Brief/Evidence/
  Financials/Scenarios/Review and found no browser-console errors.
- [x] RT0.5 Reconcile README/PLAN/TASKS with actual commands, routes and source
  chain; remove stale Yahoo/stooq/Claude-only claims.

### RT.1 — Explicit, reproducible AI runs

- [x] RT1.1 Remove `thesis_ai`, `scenarios_ai` and `valuation_ai` calls from
  `build_dossier`; GET endpoints are deterministic, side-effect-free and tested
  to make zero provider calls.
- [~] RT1.2 Add analysis-run provenance + `model_calls`: status/purpose/as-of, complete
  input snapshot, evidence ids, skill hash/version, provider/model/config,
  validation, tokens/cost/latency, retries/escalation and user. **Core run and
  verdict-call provenance extend the current `analyses` table without
  overwriting a conflicting pilot `analysis_runs` contract; child distillation attempts, exact
  retry rows and price-based cost calculation move into RT1.3/RT1.6.**
- [~] RT1.3 Introduce a single run orchestrator + provider interface; migrate
  existing Anthropic calls behind it before adding OpenAI. Replace file-only
  production caches with durable hash/idempotency records. **The verdict path
  now uses `analysis/orchestrator → executor → AnthropicProvider`, supports
  scoped `Idempotency-Key`, durable validated request reuse and per-attempt
  rows. Legacy direct-client compatibility and forum distillation still need
  migration before OpenAI is added.**
- [~] RT1.4 Define strict Pydantic output contracts and validate before
  persistence/rendering. Handle refusal, truncation, malformed evidence and
  stale run states explicitly. **Strict/no-coercion validation, stable ids,
  cache revalidation, failed/succeeded/stale recovery and distinct provider
  truncation/refusal/invalid-output states are implemented; material claim to
  evidence-id enforcement remains RT2/RT5.3.**
- [~] RT1.5 Compute strategy score/vetoes and all financial math
  deterministically. Models produce evidence-linked interpretations, not the
  authoritative number. **Alignment weights, unknown handling and current
  vetoes are server-owned and tested; future company-template/scenario math
  remains RT3–RT4.**
- [~] RT1.6 Add async job progress/cancellation and quota/cost accounting for
  every child call; hidden refiners cannot bypass the limit. **Verdict attempts
  record heartbeat/status/cache/billed/token/latency data. Atomic UTC-day run,
  provider-attempt and measured-token limits include retries; zero disables a
  budget, and stale work is claimed once and conservatively marked
  unknown-billed. Hidden forum model calls stay disabled until migrated.
  Monetary price snapshots/reservations, async progress/cancellation and every
  future child role remain.**

### RT.2 — Point-in-time evidence ledger + primary disclosures

- [~] RT2.1 Migrate immutable source documents/versions, typed facts with
  `known_at` + page/section locator, events and explicit data conflicts.
  **Migration `0008` adds the complete ledger contracts; BR report/indicator
  versions, typed facts and cross-document conflicts are active. Official
  event ingestion and object storage remain.**
- [~] RT2.2 Make current report/indicator serving rows traceable to source facts;
  refresh appends versions and supports an `as_of` read instead of destroying
  historical truth. **New report/indicator rows carry immutable fact pointers;
  identical content deduplicates, changed/failed versions are preserved, and
  point-in-time APIs select the latest complete parsed version per document.
  Legacy rows remain honestly unlinked until refreshed.**
- [ ] RT2.3 Pilot issuer-IR and official ESPI/EBI ingestion for 3–5 watchlist
  companies: periodic/current reports, guidance, material contracts/backlog,
  buybacks, dilution and management/shareholder events.
  - De-duplication note (2026-07-10): supersedes CX.6's `event_reports`-level
    ingestion for evidence purposes — RT2.3 output is ledger-grade (immutable
    versions, claim-level citations). CX.15a's `last_polled_at` watermark +
    pagination applies to this ingestion path too; implement once, share it.
- [ ] RT2.4 Build source-quality/terms/rate notes and parser fixtures; material
  case claims must cite immutable source spans.
- [ ] RT2.5 Evaluate one corporate-action-aware, long-history market-data source
  against GPW coverage, licensing, delistings and total-return needs before
  choosing it.

### RT.3 — Fundamental depth + company templates

- [~] RT3.0 Add a low-request market discovery funnel. **One cached, immutable
  BiznesRadar GPW rating document now seeds transparent candidates with report
  period, Altman EM-Score rating and Piotroski F-Score; missing values remain
  missing and the UI explicitly withholds strategy-fit claims. Template-aware,
  point-in-time filters for liquidity, growth, margins, cash conversion,
  leverage and own-history valuation remain after RT3.1–RT3.3. A 2026-07-10
  source audit identified consecutive-snapshot deltas and a separately labelled
  NewConnect universe as the next high-value BR extensions; technical buy/sell
  signals remain explicitly out of scope.**
- [ ] RT3.1 Compute operating cash flow vs profit, cash conversion, capex
  intensity, working-capital/receivables/inventory trends, ROIC/ROE where valid,
  share-count dilution and normalized one-offs. **First normalized-one-off
  slice now keeps reported and continuing TTM net/EPS/C/Z, requires a complete
  discontinued-operation bridge and feeds decision valuation from continuing
  earnings. BR sector medians, per-share reconciliation and stored-volume
  liquidity remain verifier-gated follow-ups.**
- [ ] RT3.2 Add segment/geography/KPI facts and a versioned `CompanyTemplate`
  contract: required evidence, driver tree, scenario equations, valuation views,
  red flags and optional external series.
- [ ] RT3.3 Implement and hand-check 2–3 templates selected from real watchlist
  archetypes; deterministic selection plus visible user override.
- [ ] RT3.4 Add relevant official macro/sector adapters only for a template that
  consumes them (first candidates: NBP, GUS, PSE/URE); no generic macro feed.

### RT.4 — Research case + operating-driver scenarios

- [ ] RT4.1 Persist research-case state, blockers, thesis/counter-thesis,
  catalysts, falsifiers, next checks, user decisions and version history.
- [ ] RT4.2 Scenario engine v2: template driver assumptions → statements/cash
  flow/balance bridge → valuation → equity value/share; pure math with unit and
  sensitivity tests.
- [ ] RT4.3 Track each assumption as sourced fact, human assumption or model
  suggestion. Model suggestions and probabilities require user approval.
- [ ] RT4.4 Move current own-history multiple reversion into a valuation
  sensitivity; show unweighted ranges alongside probability-weighted values.
- [~] RT4.5 Rework stock UI around Evidence, Business, Performance, Thesis,
  Scenarios, AI review and Journal; show fact/thesis/scenario changes after a
  new report instead of multiple overlapping verdict cards. **The first slice
  consolidates the duplicated Brief, moves full scenarios out, reframes AI as
  Review and separates Evidence/Financials. A second report-first slice makes
  the prepared report and key charts the default while moving raw evidence and
  run history to explicit audit views. Persistent case changes,
  Business/Thesis editing and Journal remain.**
- [~] RT4.6 UI/UX overhaul: audit existing screens/task flows; create and approve
  research-workspace wireframes + updated design tokens; implement a persistent
  case header, progressive workflow/navigation, evidence provenance states,
  non-blocking run progress, scenario driver/valuation bridge editor and strong
  empty/error/conflict states. **Three independent UX reviews converged on the
  new `docs/design/research-workspace.md`; Discover, Research, compact Brief,
  progressive workflow tabs, higher-contrast typography and mobile table
  containment are implemented. The case-state contract, evidence drawer and
  driver editor remain.**
- [~] RT4.7 Verify industrial, financial and event-driven cases at desktop and
  mobile widths with Playwright interactions/screenshots plus accessibility,
  keyboard, contrast and `pl-PL` formatting checks. Store the approved design
  spec in `docs/design/`; do not treat visual polish as proof of analytical
  correctness. **Manual in-app browser QA is green at 1280 px and 390 px for
  Discover, Research, all five SNT workflow tabs and raw table containment;
  automated screenshots, keyboard/axe checks and representative financial/
  event-driven cases remain.**

### RT.5 — OpenAI orchestration + Codex-facilitated workflow

- [ ] RT5.1 Add OpenAI Responses API adapter with strict structured outputs,
  background jobs and versioned skill attachment. Configure models by role
  (classify/extract/verify/analyze/adjudicate/judge), never as a hard-coded
  “latest” id. Include GPT-5.3 as a user-approved bounded-loop candidate when
  available, plus smaller model candidates for simpler work.
- [ ] RT5.1b Implement `ModelPolicy` per role: ordered allowed models, reasoning
  level, max calls/iterations/tokens/cost/timeout and explicit escalation
  conditions; enforce a run-level budget and persist the selection reason.
- [ ] RT5.2 Implement bounded cheap-model extraction/verification loops:
  deterministic schema/unit/period/arithmetic/citation checks → retry failed
  fields only → strong-model or human escalation. Test whether independent
  cheap passes add value; never equate self-agreement with correctness.
- [ ] RT5.3 Add prompt-injection isolation for untrusted source documents and
  evidence-id requirements for all material claims.
- [~] RT5.4 Build an idempotent `workbench` CLI: `doctor`, `start`, `stop`,
  `status`, `refresh`, `case`, `analyze`, `feedback`, `backtest`. **The four
  operator commands are implemented; add research commands with their RT.2–RT.6
  domain contracts rather than wrapping unstable endpoints early. README now
  documents the exact local-project prompt/command Codex uses to start, open and
  health-check the app, plus the expected scenario run sequence.**
- [~] RT5.5 Create `skills/workbench-research/SKILL.md` so a Codex task starts
  or checks the app when asked to research a company, facilitates the case
  stages, reports blockers and opens the relevant UI. Keep `skill/SKILL.md` as
  the investment-analyst skill. **The operator/research skill is created,
  validated and forward-tested for the commands that exist; extend its case
  workflow only as the remaining CLI contract lands.**
- [ ] RT5.6 After the CLI stabilizes, expose the same typed contract through an
  optional MCP/plugin; do not make Codex UI automation the only interface.

### RT.6 — Seasoned-investor judge + evaluation/backtest

- [ ] RT6.1 Build gold data/extraction/scenario cases with mixed outcomes and a
  failure taxonomy; split training/calibration from untouched holdout cases.
- [ ] RT6.2 Create a versioned `seasoned-investor-judge` skill and structured
  rubric: source correctness, accounting/units/periods, template choice,
  thesis/counter-thesis/falsifiers, scenario coherence, uncertainty,
  company-specificity, missing-evidence detection, usability, cost and latency.
  Judge input should be a compact validated trace plus disputed spans so its
  own cost stays proportionate.
- [ ] RT6.3 Build an isolated evaluator that launches the app, waits for health,
  seeds a frozen `as_of` case, drives the public CLI/API plus a small Playwright
  user path, runs scenarios/cheap models and captures the full trace for the
  judge.
- [ ] RT6.4 Implement the bounded improvement loop: judge failure labels →
  candidate prompt/template/validator/routing change in an experiment → replay
  training → replay holdout → cost/regression report → explicit user approval
  before versioned promotion. Judge never edits production directly.
- [ ] RT6.5 Add AI trace/dataset evals and regression gates; use batch processing
  for non-urgent large evaluation jobs when cost-effective.
- [ ] RT6.6 Add point-in-time walk-forward case replay with 3/6/12/24-month
  total/benchmark-relative return, adverse excursion, thesis-break timing and
  probability calibration. Require publication timestamps, corporate actions,
  delistings and no future leakage. First pragmatic slice: CX.16 cohort replay
  (estimated-lag policy, research-only); RT6.6 re-runs and supersedes it once
  strict point-in-time data exists.
- [ ] RT6.7 Consider market-wide factor backtesting/weight tuning only after the
  case replay is credible; keep a final out-of-time holdout.

## RT.7 / legacy Phase 6 — Deploy & polish (Vercel + Railway, Google allowlist)

**Goal:** app live for you and allowlisted friends; everyone else hits a login wall.
**Done when:** friend signs in with Google on the Vercel URL and runs the full workflow; non-allowlisted account is rejected; direct Railway URL without token returns 401; DB backup restores locally.

**Scheduling decision (2026-07-09):** these tasks remain useful, but execute
after RT.0–RT.6 prove the local research workflow. Adapt deploy topology for
durable source documents, background analysis jobs and run traces before RT.7.

**2026-07-10 exploration:** `docs/hosting-codex-automation.md` selects a
hybrid first deployment: Vercel UI; Railway API/Postgres/short-lived ingestion
and notifier jobs; subscription-entitled Codex remains on a trusted Mac and
connects through a scoped HTTPS MCP/API boundary. Slack is the first alert lane
through a durable outbox; e-mail is an optional digest. A fully hosted model
worker uses the OpenAI API and billing only after RT.5/RT.6 gates. No deploy or
external notification has been authorized yet.

- [ ] P6.1 Backend Dockerfile + Railway: service from repo, managed Postgres plugin, env vars (PLAN §9), `alembic upgrade head` on release, healthcheck on `/api/health`
- [ ] P6.2 Backend auth middleware: require `Authorization: Bearer $API_TOKEN` when set (skip when unset = local dev); read `X-User-Email` into request context for analyses/forecasts attribution
- [ ] P6.3 Auth.js on frontend: Google provider, `signIn` callback checks `ALLOWED_EMAILS`, middleware guards all pages, `/api/auth/*` excluded from proxy; login page (Polish) + user menu with sign-out
- [ ] P6.4 Proxy hardening: attach bearer token + `X-User-Email` server-side; deploy frontend to Vercel (envs, prod `BACKEND_URL`), verify end to end with a second Google account
- [ ] P6.5 Backups: `pg_dump` script against Railway `DATABASE_URL` + restore-locally instructions; document env setup for both dashboards in README
- [ ] P6.6 Housekeeping: error toasts, empty states, refresh-all-watchlist button
- [ ] P6.7 (Optional/extension) Nightly watchlist + forum refresh via Railway cron hitting an internal refresh endpoint
- [ ] P6.8 Remote Codex boundary: bearer-protected Streamable HTTP MCP or thin
  HTTPS tool adapter reusing `stock_tools`; separate read/mutate scopes and no
  personal Codex credential in hosting secrets.
- [ ] P6.9 Notification outbox + Slack dispatcher; optional idempotent e-mail
  digest after Slack proves useful. Only verified/needs-human/failure summaries,
  never raw forum/dossier/model context.

---

## Extension backlog

Template-aware market-wide screener after the source-seed MVP · portfolio/position/risk module ·
forum topic auto-discovery · full-thread evidence-aware summarization · alerts ·
additional company templates and non-GPW markets · home/VPS ingestion agent if
cloud IPs are blocked. ESPI/EBI, Playwright workflow checks and honest
walk-forward evaluation are no longer extensions; they are RT.2/RT.0/RT.6.
