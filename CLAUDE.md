# Stock Analysis Workbench

Personal GPW stock-analysis app implementing the Paweł Malik / OBS strategy:
scrape BiznesRadar financials + PortalAnaliz forum → metrics/prescore +
dynamic per-company insights → (Phase 5) Claude-API verdicts. UI designs in
`docs/design/` are the reference for frontend work.

## Read on demand (don't preload everything)

- `PLAN.md` — architecture & module specs; read the SECTION relevant to the
  task (§2 layout, §4 schema, §6 scrapers, §7 metrics/frontend, §8 AI,
  §9a deploy, §10 extension points).
- `TASKS.md` — task breakdown, stable IDs ("do P1.3").
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
- Production: Vercel + Railway, Auth.js Google allowlist (Phase 6; local dev
  runs open). `skill/` — codified strategy for the Claude API layer.

## Rules (non-negotiable)

- **Changelog discipline:** every change to code/schema/plan/config needs a
  `CHANGELOG.md` entry (date · scope · what + why + decisions). A diff
  without an entry is incomplete — enforced by `.githooks/pre-commit`.
- Simple first, no overengineering; extension points live in PLAN §10 —
  don't build them early.
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

- DB: `docker compose up -d postgres`
- Backend: `cd backend && uvicorn app.main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev` (proxy → :8000)
- Tests: `cd backend && pytest` · Migrations: `cd backend && alembic
  revision --autogenerate -m "..." && alembic upgrade head`
- Real-page fixtures: `cd backend && python scripts/record_fixtures.py SNT`
