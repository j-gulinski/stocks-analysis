# Stock Analysis Workbench

Personal GPW fundamental-research workbench. The current vertical slice combines
BiznesRadar financials, PortalAnaliz context, deterministic metrics/forecast/
thesis/scenarios and an optional AI verdict. The binding next-stage plan adds
point-in-time evidence, company-driver scenarios, controlled model routing,
judge evaluation and a Codex-facilitated research workflow.

Docs: `docs/plan-research-platform.md` (binding target) · `PLAN.md` (overview
and first-build history) · `TASKS.md` (task breakdown) · `CHANGELOG.md`
(decision log — required for every change) · `docs/design.md` (UI reference) ·
`docs/learning.md` (compact C#/.NET learning index).

## Start locally (recommended)

```bash
./workbench doctor       # read-only: dependencies/config/services/stored source health
./workbench start        # start services + detached pre-session/queue attempt
./workbench status
./workbench start --open # same, then open the app on macOS
./workbench stop         # stops owned app processes; leaves Postgres running
```

The command is idempotent and stores only local PID/log state under the
gitignored `.workbench/` directory. It never prints secret values. On macOS,
`start` opens Docker Desktop when it is installed but not running.
After the health gate passes, the first start also launches a detached,
session-triggered hook. It polls ESPI/EBI, queues a brief only after complete
ingestion, and claims at most one queue item for Codex; inspect
`.workbench/session-hook.log` for its result. Re-running `start` while the app
or hook is already active does not duplicate the attempt.

### Start from Codex

Add or open this repository as a local Codex project (the project folder must
be `/Users/jgulinski/Claude/Projects/stocks-analyzis`), then ask:

> Start the Stock Analysis Workbench, open it, and verify doctor/status.

Codex should use the repository `workbench-research` skill and run the same
stable contract:

```bash
cd /Users/jgulinski/Claude/Projects/stocks-analyzis
./workbench start --open
./workbench doctor
./workbench status
```

No additional shell access or secret sharing is required. Selecting the local
project gives Codex access to this folder; credentials stay in the gitignored
`backend/.env` and diagnostics report only whether they are configured. A local
scheduled Codex worker can also run `./workbench start` before claiming queued
analyses, so you do not need to start the web app first. The worker follows
`.codex/tasks/stock-queue-worker.md`, claims one leased row and saves only a
verifier-gated result; it does not hide an AI subprocess inside the web server.
The Mac and the Codex local host still need to be awake and available when that
job runs.

## Expected scenario workflow

Scenarios are a controlled research loop, not a separate scraper and not a
buy/sell signal:

1. Add a ticker and refresh it. The refresh stores source evidence; it does not
   ask a model to invent assumptions.
2. Open the company page. Every dossier read deterministically rebuilds the
   negative/base/positive scenario set from the latest stored facts, the
   company's own multiple history, current price and the active earnings basis.
3. Open **Wykresy**. Review the scenario probabilities, target-multiple bridge,
   price range and warnings. The headline potential is the probability-weighted
   result; it is conditional, not a recommendation.
4. Use the forecast editor on the same screen to change operating assumptions.
   Preview first, save a named forecast only when the assumptions are yours,
   then reload the dossier. The saved forecast becomes the preferred forward
   earnings input where the current engine supports it.
5. Queue **Analiza Codex** after the deterministic set is coherent. The Codex
   worker (Terra) may research and draft, but the strict verifier (Sol) owns
   final potential interpretation, confidence, result quality and company score.
   Only a current `pass` result may appear as verified in the prepared report.
6. After a new report or material event, refresh and compare again. Old model
   output remains audit history and must not silently replace the new dossier.

Current limitation: scenario v1 is mainly a multiple-reversion sensitivity
against the company's own history. It is useful for valuation ranges, but it is
not yet the RT.4 company-driver simulator (for example backlog conversion,
units/prices or contract timing). The UI labels this limitation explicitly.

## Run components manually

```bash
# 1. Database
docker compose up -d postgres

# 2. Backend (Python 3.11+)
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Create `backend/.env` (gitignored) with exactly what you need — no copying
templates around:

```ini
DATABASE_URL=postgresql+psycopg://stocks:stocks@localhost:5433/stocks

# PortalAnaliz (optional — public threads work without login)
# Values with special characters (# $ " spaces) must be double-quoted!
PA_USERNAME=your_login
PA_PASSWORD="your password"

# Phase 5:
# ANTHROPIC_API_KEY=sk-ant-...
# AI_DAILY_LIMIT=20          # logical analysis runs; 0 disables
# AI_DAILY_CALL_LIMIT=60     # actual provider attempts, retries included
# AI_DAILY_TOKEN_LIMIT=500000
```

Interactive API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm ci
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

## Deployment (RT.7, later)

Vercel (Next.js frontend, Auth.js Google allowlist) + Railway (this backend +
Postgres). Deployment follows the evidence/scenario/evaluation pilot rather
than preceding it; see `docs/plan-research-platform.md`.
