# Stock Analysis Workbench

Personal GPW research pipeline: one exclusion-first market sieve, tailored
company research, company-specific valuation scenarios, and portfolio-first
coverage. Codex structures and challenges the evidence; the user makes every
investment decision.

## Product stages

- **Discover** — exclude weak or stagnant companies with one inspectable sieve.
- **Research** — collect and understand company-specific evidence.
- **Valuation** — draft and verify company-specific scenarios and prices.
- **Portfolio** — keep real holdings covered by the freshest verified analysis.

Binding documentation:

- [`docs/PRODUCT.md`](docs/PRODUCT.md) — user outcome, screens, copy, non-goals;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data and Codex boundaries;
- [`docs/STRATEGY.md`](docs/STRATEGY.md) — the Workbench sieve and valuation lens;
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

Core system invariants live in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §Invariants; Product and Strategy
retain their user- and method-specific rules. Agents start from
[`AGENTS.md`](AGENTS.md).

See `CHANGELOG.md` for release-level decisions and `docs/model-usage.md` for the
model-routing audit ledger.
