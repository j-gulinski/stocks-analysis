# Stock Analysis Workbench

Personal GPW fundamental-research workbench: evidence + point-in-time data →
deterministic metrics/company templates/scenarios → versioned strategy skills
and controlled AI review/judge loops. The Malik / OBS strategy is the first
investment lens, not the whole product. UI designs in `docs/design/` remain a
reference for the completed first vertical slice.

## Read on demand (don't preload everything)

- `PLAN.md` — architecture & module specs; read the SECTION relevant to the
  task (§2 layout, §4 schema, §6 scrapers, §7 metrics/frontend, §8 AI,
  §9a deploy, §10 extension points).
- `TASKS.md` — task breakdown, stable IDs ("do P1.3").
- `docs/plan-research-platform.md` — **binding next-stage architecture and
  RT.0–RT.7 order**: evidence lineage, company templates, scenario v2,
  OpenAI/Codex orchestration, judge loop and honest backtesting.
- `skills/workbench-research/SKILL.md` — local app operator/research workflow;
  use it for start/status/diagnosis or Codex-facilitated company research.
- `skills/scraper-doctor/SKILL.md` — **any scraper/data problem starts
  here**: diagnostic ladder + verified quirks ledger (BR slug/`,Q` redirect
  trap, robots rules, indicator label traps, price-chain order, storage
  rules). Do not re-derive these.
- `CHANGELOG.md` — decisions digest; full detail archived per stage in
  `docs/changelog-archive-*.md` (build day 07-07; Stage TH 07-08).
- `docs/plan-stage-thesis.md` — investment-thesis stage (TH): architecture +
  per-WP acceptance; read the WP relevant to the task.
- `docs/strategy-malik.md` — source-cited Malik spec the thesis + scenario
  engines implement (principles → dossier field or labelled gap).
- `docs/validation-thesis.md` — thesis validation: DGN/SNT cases + current-cap
  sanity, explicit gaps + deferred live run.
- `docs/plan-stage-scenarios.md` — scenario-simulation stage (SC): per-WP
  architecture + acceptance. Validation `docs/validation-scenarios.md` +
  learning `docs/learning/phase-scenarios.md` land in WP5 (SC.5).
- `docs/project-guardrails.md` — product and quality bar; read at the start
  and end of every phase/work package to keep the app evidence-grounded and
  avoid low-quality feature drift.
- `docs/source-materials/` — strategy sources; `skill/SKILL.md` must stay
  faithful to them. `docs/learning/` — phase notes for the user.

## Stack

- `backend/` — Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL
  (docker-compose locally; SQLite in tests), requests + BeautifulSoup.
- `frontend/` — Next.js (App Router, TS) + SCSS global primitives, recharts.
  Domain data/labels Polish, nav labels English (user decision). All API
  calls via the Next route-handler proxy, never directly to the backend.
- Production target remains Vercel + Railway, but deployment is RT.7 after the
  local evidence/scenario/eval workflow is proven. `skill/` is the investment
  strategy skill; the Codex workflow skill lives separately under
  `skills/workbench-research/`.

## Rules (non-negotiable)

- **Changelog discipline:** every change to code/schema/plan/config needs a
  `CHANGELOG.md` entry (date · scope · what + why + decisions). A diff
  without an entry is incomplete — enforced by `.githooks/pre-commit`.
- Simple first, no speculative framework work; implement RT stages in order and
  add company templates/source adapters only for real pilot needs.
- Scrapers: fetch + parse + upsert only. ALL HTTP through
  `scrapers/http.py` (jittered per-domain limits, backoff) — politeness is
  non-negotiable. Parser changes require green fixture tests.
- Meaning lives in `services/fields.py` only; markup in `app/scrapers/`.
  Metrics/forecast/insights: pure functions, unit-tested against
  hand-checked numbers.
- Money: statements tys. PLN in DB; mcap/price PLN; format `pl-PL` in UI.
  Reported mcap (`companies.market_cap`) beats price×shares.
- Secrets only in `backend/.env` (gitignored).
- Learning layer (PLAN §13): user is a mid C# dev learning Python/frontend —
  idiomatic readable code, comment the *why*, `docs/learning/phase-N.md`
  after each phase, C#/.NET analogies when explaining.
- **Guardrail check:** every phase/work package starts and ends by inspecting
  `docs/project-guardrails.md`; do not mark work complete if it violates the
  evidence, UI, model-discipline, or phase-exit checklist there.

## Documentation lifecycle

- `TASKS.md` is the only live execution/status list. Keep it compact: retain
  the ordered queue, open acceptance criteria, stable IDs, blockers and the
  next verification command; do not append session-by-session progress logs.
- `docs/plan-research-platform.md` is the canonical future architecture and
  RT.0–RT.7 order. `PLAN.md` is the stable architecture overview, not a second
  status tracker. Stage plans are detailed working references only while their
  stage is active.
- When a phase, stage, or work package closes, record the durable decision and
  evidence in `CHANGELOG.md`, reduce its completed section to a summary, and
  move detailed task/plan history to `docs/archive/<topic>-<date>.md` when it
  is no longer needed for active implementation. Keep stable IDs and a pointer
  from the live document; never silently delete acceptance evidence.
- Archive stale reviews, superseded designs and completed stage plans instead
  of leaving competing “current” instructions in the active document tree.
- Before starting work, search both live docs and `docs/archive/` for the
  relevant stable ID. Historical archive text is context, not current status.

## Operating policy: model selection and working style

Mission: build and maintain a high-quality stock-analysis workbench while
minimizing cost, latency and unnecessary reasoning. Every decision balances
correctness, maintainability and efficiency. Always pick the **lightest
model + reasoning level that can reliably finish the task at hand**, and
escalate only on evidence — never by default.

### Model routing by effort

Pick the lightest suitable model and reasoning level for the task tier below.
For saved analysis runs, record both `model_role` and the actual `model`; the
role is metadata and does not override this model-routing policy. All
UI-visible investment output must pass `verifier_strict`.

| Work tier | Model and reasoning | Suitable work |
|---|---|---|
| **Testing / mechanical** | GPT-5.3 · high–extra-high | Tests, formatting, linting, repository exploration, log reading, small mechanical edits, simple bug fixes, documentation, repetitive refactors, dependency bumps, and simple scripts. |
| **Medium** (default) | GPT-5.6 Luna · high | Feature implementation, API development, ordinary debugging, tests, medium refactors, code review, architecture comprehension, DB queries, and scoped performance work. |
| **High** | GPT-5.6 Sol · high | System architecture, multi-service changes, trading algorithms, financial calculations, data pipelines, concurrency, security, hard debugging, and migration planning. |
| **Hardest** (exceptional) | GPT-5.6 Sol · ultra | Critical production incidents, extremely difficult bugs, or architectural redesign after the High tier has proved insufficient. Never the default. |

Default to the Medium tier when unsure; never start at Hardest. If a named
model is unavailable on the current Codex host, use the closest available model
at the same reasoning level and record the substitution. This is a host
constraint, not a reason to change the requested model tier.

### Escalation

Start at the lightest suitable tier. Escalate **one tier** only when confidence
is low, multiple implementation attempts fail, the task proves more complex
than expected, or materially deeper reasoning is required. Do not escalate
automatically; record the reason in the session or `agent_run`.

### Required execution workflow

Follow this sequence for every implementation task:

1. Read `docs/project-guardrails.md` and the relevant plan/work-package
   section; inspect the current state and existing diff before making changes.
2. Classify the task using the model-routing table above. Use the matching model
   and reasoning level; record an escalation or host substitution where the
   workflow persists an `agent_run`.
3. Understand the problem, then break it into small independent tasks. Complete
   one at a time and do not broaden scope without user direction.
4. Reuse existing patterns. Make the smallest maintainable change that solves
   the problem; avoid speculative abstractions and unrelated cleanup.
5. Verify proportionally to risk: run focused tests, lint/build checks, or the
   relevant runtime check. Diagnose and fix failures before proceeding.
6. Before completion, re-read the guardrails, update `CHANGELOG.md` and
   `TASKS.md` when required, record decisions/failures honestly, and confirm
   that the result advances the investment workflow.

### Code quality

Write readable code, avoid duplication, preserve existing architecture unless a
redesign is requested, keep commits focused, prefer maintainability over
cleverness, and run the appropriate tests whenever possible.

### Context management & resume protocol

Assume the project may exceed the context window. `TASKS.md` + `CHANGELOG.md`
are the durable memory — never chat history; keep them current with completed
work, remaining tasks, architectural decisions, open issues, assumptions and
technical debt.

When a conversation nears its token limit, don't wait to be asked — produce a
resume package containing: (1) **current status** (done / in progress /
remaining); (2) **important decisions** (architecture, trade-offs, assumptions,
constraints, key implementation details); (3) **files modified** (path ·
purpose · summary of changes); (4) an **ordered checklist** of remaining work;
(5) **known issues** (bugs, TODOs, tech debt, blockers, open questions); and
(6) a ready-to-paste **next prompt** beginning with "Continue the Stocks
Analysis project using the resume below…" that carries all context needed to
continue seamlessly in a fresh conversation.

## Commands

- Preferred operator path: `./workbench doctor` · `./workbench start` ·
  `./workbench status` · `./workbench stop`
- DB: `docker compose up -d postgres`
- Backend: `cd backend && uvicorn app.main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev` (proxy → :8000)
- Tests: `cd backend && pytest` · Migrations: `cd backend && alembic
  revision --autogenerate -m "..." && alembic upgrade head`
- Real-page fixtures: `cd backend && python scripts/record_fixtures.py SNT`

## Imported Claude Cowork project instructions

Skill based tool to analyze stocks
