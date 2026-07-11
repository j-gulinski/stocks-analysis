# Stock Analysis Workbench

Personal GPW research second brain: evidence -> tailored company research ->
driver scenarios -> portfolio perspective. Codex structures and challenges the
analysis; the user makes every investment decision.

## Product stages

- **Discover** — compare explainable sieves and add a company to Research.
- **Research** — build a sourced, company/sector-tailored knowledge base.
- **Valuation** — test strategy-linked quarter/year and price scenarios.
- **Portfolio** — synchronize myfund data, history, exposures, and perspectives.

Binding documentation:

- [`docs/PRODUCT.md`](docs/PRODUCT.md) — user outcome, screens, copy, non-goals;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data and Codex boundaries;
- [`docs/STRATEGY.md`](docs/STRATEGY.md) — investor methods and sieve contracts;
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — the only live delivery plan.

Source material under `docs/source-materials/` is evidence input, not product
documentation. Git history replaces the old archive/task diary.

## Start locally

Prerequisites: Docker Desktop, Node.js 20+, and Python 3.11+.

```bash
./workbench doctor
./workbench start
./workbench status
```

Open [http://localhost:3000](http://localhost:3000). Stop Workbench-owned
backend/frontend processes with:

```bash
./workbench stop
```

Postgres deliberately remains running between sessions. The operator never
prints secret values. Local credentials belong only in `backend/.env`; browser
requests use the Next.js `/api` proxy.

## Tests

```bash
cd backend
./.venv/bin/pytest

cd ../frontend
npm run build
```

Parser changes require recorded fixtures. Primary actions also require focused
API tests and a browser interaction proving the user outcome; tracked
screenshots are not acceptance evidence.

## Manual components

Only use this path when diagnosing the operator:

```bash
docker compose up -d postgres

cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm run dev
```

## Core boundaries

- GET/read paths do not fetch sources, queue jobs, claim work, or call models.
- Every external request uses `backend/app/scrapers/http.py`.
- Source facts, deterministic calculations, human assumptions, Codex
  suggestions, and verifier conclusions remain distinguishable.
- Financial and portfolio math is deterministic and tested.
- Only an executing Codex worker claims one queued job; no recurring hidden
  worker is created.
- Removing or archiving a case never destroys accumulated company knowledge.
- No buy/sell instruction, automatic trade, or unsupported backtest claim.

See `CHANGELOG.md` for release-level decisions and `docs/model-usage.md` for the
model-routing audit ledger.
