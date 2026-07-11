# Phase 3 — metrics, prescore, forecast, dossier

## What was built
The analytics core: quarterly metrics (with the strategy's key gross-margin
series), TTM/P-E aggregates, own-history P/E stats, net cash, the 8-rule
deterministic prescore, the Excel-workflow forecast engine, and the dossier
endpoint that feeds both the future UI and the AI layer.

## Concepts worth understanding

**Pure functions as the domain layer** (`services/metrics.py`,
`services/forecast.py`) — no DB, no framework, plain dataclasses in/out: the
hexagonal "domain assembly" you'd build in C#. All financial math is testable
against hand-checked numbers (`tests/test_metrics.py` mirrors the fixture
values; `test_forecast.py` reproduces the Novita example from the transcript:
pretax 13.0M → net 10.53M → EBITDA 14.6M).

**IO at the edges** (`services/dossier.py`) — the only module that both talks
to the DB and calls the math. It maps stored rows → canonical series (first
mapped row wins), then composes one dossier dict. UI and AI consume the same
contract, so they can never disagree about the numbers.

**Honest unknowns** — every prescore rule returns pass/fail/**unknown** with
evidence. Missing data is never coerced into a verdict; the checklist says
"Za mało danych" instead of guessing. This matters later: the AI prompt gets
the same JSON and must not hallucinate around gaps.

**Units discipline** — statements are tys. PLN, prices PLN, market cap PLN,
EPS PLN/share. Conversions happen in exactly one place per metric
(`eps = ttm × 1000 / shares`). Unit bugs are the classic finance-app failure;
grep for "tys" comments when in doubt.

**Preview vs persist** — `POST /forecasts` with `save=false` computes without
writing (live recompute for the future Prognoza tab); with `save=true` it
stores assumptions + result as JSONB and the dossier's valuation check
switches to forward P/E automatically.

## Where to look
`app/services/metrics.py` → `app/services/forecast.py` →
`app/services/dossier.py` → `app/api/companies.py` → `tests/test_api_phase3.py`.
