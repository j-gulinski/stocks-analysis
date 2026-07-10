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
