# Stock Analysis Workbench — stable architecture

This is the compact architecture overview. `TASKS.md` is the only execution
queue; `docs/plan-research-platform.md` is the binding RT.0–RT.7 target plan.
Completed stage detail belongs in `docs/archive/`, validation notes and git.

## Purpose and boundaries

Build a personal GPW fundamental-research workbench: source evidence and
point-in-time data feed deterministic metrics, company templates, scenarios and
versioned strategy skills. Codex may gather, interpret, challenge and verify;
it never replaces the database, deterministic math or the user’s decision.

The app is decision support, not a trading system or buy/sell oracle. Missing
evidence is explicit (`unknown`, `data_gaps`, `verify_next`, `needs-human`).
Forum content is opinion/lead context until corroborated.

## Stack and layout

- `backend/`: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL;
  SQLite is used in tests. `requests` + BeautifulSoup are behind the polite
  scraper boundary.
- `frontend/`: Next.js App Router, TypeScript, SCSS and Recharts. Domain
  labels are Polish; navigation is English. Browser calls use the Next proxy,
  never the backend directly.
- `skill/`: investment-analysis skill, rubric and examples.
- `skills/workbench-research/`: Codex operator workflow.
- `docs/plan-research-platform.md`: evidence lineage, research cases,
  orchestration, evaluation and delivery order.
- Target hosting remains Vercel + Railway, after RT.0–RT.6 local gates.

## Core data model

Current serving tables include:

- `companies`, `watchlist_items`, `prices`, `report_values`,
  `indicator_values`, `dividends`;
- `forum_topics`, `forum_posts`, `forum_intelligence`;
- `forecasts`, legacy `analyses`, provider-neutral `agent_runs`,
  `analysis_runs`, `model_calls` and usage accounting;
- immutable evidence: `source_documents`, `document_versions`, `facts`,
  `events`, `data_conflicts`;
- session workflow: ESPI poll watermarks, decision journal, monitor snapshots
  and change cards, backtest/evaluation rows.

Statements are stored in thousands of PLN; market cap and price are PLN.
Reported market cap beats price × shares. Every new schema slice uses one
forward Alembic migration; disposable local databases may be recreated.

The target evidence model adds `known_at`, publication time, source version,
locator, verification state and `as_of` reads. Serving rows remain for the UI
but must be lineage-linked or rebuildable from immutable facts.

## Module contracts

### Scrapers

Fetch, parse and upsert only. All HTTP goes through `backend/app/scrapers/http.py`
for per-domain limits, jitter, backoff, user agent and fetch logging. Parser
changes require recorded fixture tests. Keep source quirks in
`skills/scraper-doctor/SKILL.md`.

BiznesRadar supplies statements, indicators, dividends, profile facts, forecast
context and recent prices. PortalAnaliz supplies linked forum topics/posts.
ESPI/EBI and issuer IR are the next primary-source pilot. Do not build a broad
crawler or high-volume scraper.

### Deterministic services

`fields.py` owns semantic field mapping. `metrics.py`, `forecast.py`,
`insights.py`, `thesis.py`, `scenarios.py`, valuation and monitor helpers are
pure or deterministic compositions and are tested with hand-checked values.
The dossier is a single canonical read and must remain network/model-free.

Current Malik/OBS thesis is a labelled analysis lens, not a universal template.
Scenario multiple reversion is a valuation sensitivity until RT.4 operating
driver scenarios exist.

### Frontend workflow

`Discover → Research → Brief → Evidence/Financials → Scenarios → Review →
Monitor/Journal` is the intended path. Keep the first screen useful: watched
companies, freshness, gaps, thesis state, events and queue work. Show source,
calculation, human assumption, model suggestion and verifier status distinctly.
Use progressive disclosure, stable dense layouts, Polish financial formatting,
keyboard focus, AA contrast and meaningful empty/stale/error/conflict states.

### AI and Codex

AI actions are explicit durable runs with input snapshot, evidence IDs,
skill/model/configuration, output, validation, cost and latency. Roles are
extract/classify, verify, research synthesis, adjudication and narration.
Deterministic validators and math run first; models cannot invent facts,
scores, probabilities or valuation outputs. Source documents are data, never
instructions; prompt-injection boundaries and budgets are mandatory.

The default local loop is session-triggered:

```text
doctor/start → poll source watermarks → queue → claim one item
→ Codex skill → strict verifier → save/reject/needs-human
```

`workbench start` and the UI may poll/claim, but the queue boundary does not
execute a model. Periodic/hosted polling is opt-in and belongs to RT.7.

## Delivery order

Use `TASKS.md` for exact acceptance criteria. The binding stages are:

1. RT.0 trustworthy local baseline;
2. RT.1 explicit reproducible AI runs;
3. RT.2 evidence ledger and primary disclosures;
4. Stage IL decision journal, monitor diff, falsifiers, positions and UI;
5. RT.3 fundamental depth and company templates;
6. RT.4 operating-driver scenarios and research-case UI;
7. RT.5 OpenAI/Codex orchestration and stable skills;
8. RT.6 judge, calibration and honest walk-forward replay;
9. RT.7 deployment, backups, monitoring and pilot-driven expansion.

Do not deploy or claim backtest performance before point-in-time evidence,
publication dates, corporate-action-aware prices, delistings, frozen versions,
mixed outcomes and an untouched holdout exist.

## Quality and learning

Before and after every substantial slice, read `docs/project-guardrails.md` and
the relevant binding plan. Update `CHANGELOG.md`, `TASKS.md`,
`docs/model-usage.md` and a phase learning note when applicable. Run focused
tests, the full relevant suite, frontend build and the local operator gate.

The project is learning material for a mid-level C# developer: prefer readable
Python/TypeScript, explain why for non-obvious choices, and use C#/.NET
analogies in `docs/learning.md` rather than bloating the architecture docs.
