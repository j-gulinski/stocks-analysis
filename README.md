# Stock Analysis Workbench

Personal GPW stock-analysis app implementing the Paweł Malik / OBS strategy:
BiznesRadar financials + PortalAnaliz forum threads → metrics, quarterly
charts, next-quarter forecasts and (Phase 5) AI strategy verdicts.

Docs: `PLAN.md` (architecture) · `TASKS.md` (task breakdown) · `CHANGELOG.md`
(decision log — required for every change) · `docs/design/` (UI reference) ·
`docs/learning/` (concept notes for a C# dev learning this stack).

## Run locally (backend, Phases 0–3)

```bash
# 1. Database
docker compose up -d postgres

# 2. Backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Create `backend/.env` (gitignored) with exactly what you need — no copying
templates around:

```ini
DATABASE_URL=postgresql+psycopg://stocks:stocks@localhost:5432/stocks

# PortalAnaliz (optional — public threads work without login)
# Values with special characters (# $ " spaces) must be double-quoted!
PA_USERNAME=your_login
PA_PASSWORD="your password"

# Phase 5:
# ANTHROPIC_API_KEY=sk-ant-...
```

Interactive API docs: http://localhost:8000/docs

## Run locally (frontend, Phase 4)

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` (gitignored) only if your backend is NOT on the
default `http://localhost:8000`:

```ini
BACKEND_URL=http://localhost:8000
```

App: http://localhost:3000 — add a ticker on the watchlist, hit refresh
(~20–30 s, polite scraping), then explore the stock page tabs.

## Troubleshooting

- **Settings shows a DB error / everything 502s** — Postgres isn't up:
  `docker compose up -d postgres`. The health endpoint now says this outright.
- **Refresh finishes but metrics show „b/d”** — the app stored statement rows
  it doesn't recognize. Check `GET /api/companies/{ticker}/mapping-report`:
  rows with `canonical: null` need an alias added in
  `backend/app/services/fields.py` (raw data is already stored — no re-scrape).
- **Which source is failing?** — Settings → „Źródła danych” shows per-domain
  last success / errors (from `fetch_log`), and every refresh returns a
  per-page status summary shown on the stock page.
- **Backend won't start after editing `.env`** — quote values containing
  special characters: `PA_PASSWORD="p@ss #123"`.
- **Parser broke after a site redesign** — record real pages
  (`python scripts/record_fixtures.py TICKER`) and run
  `pytest tests/test_biznesradar_parser.py -v`; fix only the parser module.

## Tests

```bash
cd backend
pytest            # runs on in-memory SQLite, no network, no Docker needed
```

One-time (task P1.1): record real BiznesRadar pages as fixtures and activate
the structural parser tests:

```bash
python scripts/record_fixtures.py DEC   # any ticker you follow
pytest tests/test_biznesradar_parser.py -v
```

If a structural test fails after recording, BiznesRadar's markup differs from
the synthetic fixtures — extend `app/scrapers/biznesradar.py` /
`app/services/fields.py` (aliases), nothing else.

## Quick tour (API)

```bash
curl -X POST localhost:8000/api/watchlist -H 'Content-Type: application/json' -d '{"ticker":"DEC"}'
curl -X POST 'localhost:8000/api/companies/DEC/refresh'          # ~20–30 s (polite delays)
curl 'localhost:8000/api/companies/DEC'                           # full dossier + prescore
curl 'localhost:8000/api/companies/DEC/forecast-defaults'         # Excel-style prefill
```

## Changelog discipline

Every code/schema/plan change needs a `CHANGELOG.md` entry. Enable the guard:

```bash
git init                                  # if not done yet
git config core.hooksPath .githooks
```

## Deployment (Phase 6, later)

Vercel (Next.js frontend, Auth.js Google allowlist) + Railway (this backend +
Postgres). The browser talks only to the Next proxy; see PLAN §9a.
