# Stock Analysis Workbench

Personal GPW fundamental-research workbench: evidence + point-in-time data →
deterministic metrics/company templates/scenarios → versioned strategy skills
and controlled AI review/judge loops. The Malik / OBS strategy is the first
investment lens, not the whole product. The live UI contract is `docs/design.md`;
HTML mockups remain under `docs/design/`.

**Product north star:** `docs/north-star.md` is the binding user workflow and
decision test for every run. It takes precedence over feature convenience or
dashboard breadth; `docs/plan-research-platform.md` specifies the architecture
that serves it.

## Read on demand (don't preload everything)

- `PLAN.md` — architecture & module specs; read the SECTION relevant to the
  task (§2 layout, §4 schema, §6 scrapers, §7 metrics/frontend, §8 AI,
  §9a deploy, §10 extension points).
- `TASKS.md` — task breakdown, stable IDs ("do P1.3").
- `docs/north-star.md` — **binding product outcome and user operating loop**;
  read at the start of any product/workflow/discovery/UI change.
- `docs/plan-research-platform.md` — **binding next-stage architecture and
  RT.0–RT.7 order**: evidence lineage, company templates, scenario v2,
  OpenAI/Codex orchestration, judge loop and honest backtesting.
- `skills/workbench-research/SKILL.md` — local app operator/research workflow;
  use it for start/status/diagnosis or Codex-facilitated company research.
- `skills/scraper-doctor/SKILL.md` — **any scraper/data problem starts
  here**: diagnostic ladder + verified quirks ledger (BR slug/`,Q` redirect
  trap, robots rules, indicator label traps, price-chain order, storage
  rules). Do not re-derive these.
- `CHANGELOG.md` — decisions digest; historical detail lives in `docs/archive/`.
- `docs/strategy-malik.md` — source-cited Malik spec the thesis + scenario
  engines implement (principles → dossier field or labelled gap).
- `docs/validation-thesis.md` — thesis validation: DGN/SNT cases + current-cap
  sanity, explicit gaps + deferred live run.
- `docs/validation-scenarios.md` — scenario-simulation acceptance evidence;
  completed stage detail is archived under `docs/archive/plans/`.
- `docs/project-guardrails.md` — product and quality bar; read at the start
  and end of every phase/work package to keep the app evidence-grounded and
  avoid low-quality feature drift.
- `docs/source-materials/` — strategy sources; `skill/SKILL.md` must stay
  faithful to them. `docs/learning.md` — compact learning notes; historical
  phase detail is under `docs/archive/learning/`.

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
- **Implementation-phase migrations:** keep each schema slice to one forward
  Alembic migration. Do not add compatibility/follow-up migrations for a
  locally generated database during implementation; local DB state and data
  may be discarded or recreated from the current migration chain.
- **Model-usage statistics:** every implementation, review, testing, or
  research session adds one row to `docs/model-usage.md` before completion.
  Record the stable task ID, work type, model role, selected tier/model,
  reasoning level, concrete host model, any substitution or escalation, and
  verification result. If the host does not expose the concrete deployment,
  say so explicitly; never infer it from a role label. Use the ledger to audit
  whether work was routed to the lightest suitable model and divided between
  worker, analyst, and verifier roles correctly.
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
  idiomatic readable code, comment the *why*, update `docs/learning.md` after
  each phase, C#/.NET analogies when explaining.
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
| **Testing / mechanical** | GPT-5.3 · high | Tests, formatting, linting, repository exploration, log reading, small mechanical edits, simple bug fixes, documentation, repetitive refactors, dependency bumps, and simple scripts. |
| **Basic implementation** | Luna · medium | Small bounded UI/API edits, straightforward CRUD, simple wiring and low-risk fixes. |
| **Default implementation** | Terra · high | Feature implementation, API development, ordinary debugging, tests, medium refactors, code review, architecture comprehension, DB queries, and scoped performance work. |
| **High-complexity** | Sol · high | System architecture, multi-service changes, financial calculations, data pipelines, concurrency, security, hard debugging, migration planning, and deep synthesis. |
| **Hardest** (exceptional) | Sol · ultra | Critical production incidents, security-sensitive work, investment-policy changes, or architectural redesign after Sol high has proved insufficient. Never the default. |

Use the stronger suitable model at its full appropriate reasoning level. Do not
lower model quality or reasoning merely to optimize an assumed budget limit:
GPT-5.3 high is testing/mechanical only, Luna medium is basic implementation,
Terra high is ordinary implementation, and Sol high/ultra is for complex or
critical work. Record the selected model/reasoning pair, actual host model and
any substitution or escalation.

When classification is uncertain, choose the lightest plausible tier and
escalate only on evidence; basic implementation defaults to Luna medium,
ordinary implementation defaults to Terra high, testing/mechanical work uses
GPT-5.3 high, and high-complexity work starts at Sol high. Never start at
Hardest. If a named model is unavailable
on the current Codex host, use the closest available model at the same reasoning
level and record the substitution. This is a host constraint, not a reason to
change the requested model tier.

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

### Delegation and judge loop

- For medium or high-complexity work, use a manager → bounded workers →
  independent judge/verifier loop when the task can be split meaningfully.
  The manager owns the plan and integration; workers have disjoint write
  targets or produce drafts; the judge reads the integrated result, tests and
  evidence and does not merely repeat the worker's conclusion.
- Use `worker_standard` for mechanical/data-gathering slices, `analyst_deep`
  for cross-source synthesis, and `verifier_strict` for decision-relevant or
  UI-visible output. A worker draft is never an approval.
- Do not delegate trivial edits, tightly coupled changes, or work where
  coordination overhead exceeds the risk. Never allow parallel workers to
  edit overlapping files without an explicit integration pass.
- After a worker completes, run the judge in a separate context or clearly
  separate review pass with the worker's conclusion treated as untrusted.
  Verify source grounding, deterministic numbers, schema, look-ahead, tests
  and relevant guardrails. Record worker/judge roles and actual model metadata
  in `docs/model-usage.md`.
- If the current Codex surface does not expose separate agents, do not pretend
  that multiple agents ran: perform sequential worker-style passes and an
  independent judge pass, and record that limitation in the ledger.

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
