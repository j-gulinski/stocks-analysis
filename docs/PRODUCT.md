# Product contract

Defers to `docs/VISION.md`. This file specifies what each stage shows and
does. UI copy is concise Polish; internals stay out of the reading path.

## Purpose

The Stock Analysis Workbench is one investor's GPW analysis pipeline:
sieve the market down, collect and verify company evidence, produce
company-specific valuation scenarios, and keep the real portfolio covered by
current, verified analysis. Codex agents do the volume work; Kuba owns every
decision. It is decision support, never a signal service.

## Stage 1 — Discover: one sieve, exclusion-first

Goal: reduce ~800 GPW companies to the few dozen worth research, by kicking
out the worst and the not-improving — with every kill explainable.

- Exactly one versioned Workbench sieve (`workbench_sieve_vN`). No filter
  tabs, no per-author sieves, no alternative strategies on screen.
- The sieve runs server-side over a versioned market-wide factor snapshot
  (multiple BiznesRadar market pages stored as immutable documents). Two
  layers:
  1. **Wykluczenia (hard kills)** — distress-level financial health,
     quality collapse, negative equity, sustained revenue+margin decay,
     extreme leverage, illiquidity. Any hit excludes the company and stores
     the reason.
  2. **Wymóg poprawy** — survivors must show real improvement signals
     (profitability trend, revenue dynamics, quality score, valuation below
     own history). Standing still is grounds for exclusion; cheapness alone
     is not admission.
- Survivors are ordered by improvement evidence, but the order is secondary;
  membership is the product. Each row shows the two-to-four factors that
  mattered: value, direction vs own history, source, freshness.
- Excluded companies remain inspectable in an `Odrzucone` drawer with their
  kill reasons — the sieve is auditable and tunable, never a black box.
- Factor coverage gaps are visible; missing data is a gap, never a negative
  fact and never silent exclusion (except where the rule itself is about
  missing fundamentals, e.g. no publishable equity).
- One action per row: `Dodaj do Research`. Reading Discover writes nothing.
- Explain domain terms in Polish (Altman EM-Score, F-Score) as data lenses,
  never as verdicts.

## Stage 2 — Research: collect broadly, understand one company

`ResearchCase` remains the single unit. Adding a ticker or Discover
candidate atomically creates/reuses the company and case and queues the
initial research job. Auto-created cases (from Portfolio coverage) appear
the same way, marked with their origin.

### The list is phase-aware (V3)

Rows show substance for the phase the company is in, evidence-dense like
Discover rows — never job IDs first:

- **Zbieranie** — what is being collected now, sources completed/remaining,
  honest progress.
- **Zbadana** — one-line current understanding (thesis kernel), freshness,
  the main gap, next useful action.
- **Wyceniona** — adds the valuation strip: bad/base/good (+event) price
  range, probability-weighted value vs current price, upside %, catalyst,
  and verification status.
- **W portfelu** — adds position weight and portfolio priority; holdings
  sort first (weight × staleness), then Discover candidates, then the rest.

The list opens with the `Do sprawdzenia` agenda derived only from stored
state: new evidence since last snapshot, stale cases, fired falsifiers,
valuations awaiting assumptions, uncovered holdings. Zero-write to open.

### The company view

One canonical renderer over verifier-gated snapshots (no legacy modes):
**Brief** (current understanding, freshness, main gap, next action) →
**Business & drivers** → **Performance** (result bridge, sector KPIs) →
**Evidence** (documents, claims, conflicts, gaps) → **Outlook** (driver-by-
driver next quarter / 12 months, resolved questions, catalysts) →
**Thesis** (why now, counter-thesis, falsifiers, next dated checks) →
**Valuation summary** (current scenario set inline, link to the workspace) →
**History** (what changed between snapshots). Run metadata and verifier
internals live in an audit drawer.

Layers stay: common spine → sector/archetype pack → company overlay
(segments, KPIs, company-specific questions) proposed by Codex, confirmable
by Kuba. Research answers its own frozen questions from sources; it never
hands them back as homework.

## Stage 3 — Valuation: the center (V4)

Goal: convert researched drivers into explicit, company-specific
bad/base/good (+optional event) scenarios with prices and probabilities that
could only belong to this company.

- Valuation starts from a frozen research snapshot and deterministic sourced
  base values. The Codex skill drafts everything company-specific:
  - scenario mechanisms tied to this company's drivers and catalysts;
  - assumption values each bound to research facts (fact IDs) or named as
    explicit judgment with rationale;
  - probabilities with stated evidence rationale — never a house default.
- Python computes all math deterministically: projected P&L, cash
  conversion, FCF, EPS, valuation bridge, per-share outcomes, weighted
  value. A non-positive forward EPS has no earnings-multiple price.
- The backend enforces company-specificity structurally (see
  ARCHITECTURE — valuation gates): template-seed equality, cross-company
  near-duplicate vectors, probability defaults, missing evidence rationale,
  and math mismatches are auto-rejected before any verifier opinion.
- Verification is adversarial (V5): the strict verifier must attach findings
  or per-check justification; computable checks are computed, not attested.
- Kuba can override any assumption; overrides create a new version and a
  recompute — the draft lineage stays.
- Scenario outcomes are scored when actuals land (V8) and engine calibration
  is visible per version.
- The main result is one comparison row per scenario: probability, revenue /
  result / EPS / FCF effects, price range, catalyst, falsifier — plus the
  weighted value against the current price.

## Stage 4 — Portfolio: my real money, analyzed the most (V7)

- Source: myfund API (`getPortfel`) for state + daily series; operations
  history via API when available, else file export import. No password
  scraping.
- Sync stores dated snapshots, updates holdings, and computes real returns:
  TWR from the daily value/contribution series, XIRR from derived external
  flows; method and gaps stated inline.
- Robust instrument mapping: explicit ticker, name matching against known
  companies, and persisted manual overrides for the rest. Unmapped rows are
  visible, not dropped.
- Reconciliation mismatches warn with the affected figures — they never
  black out the dashboard.
- **Auto-coverage:** after each sync (and on staleness/falsifier events) the
  backend queues research and valuation jobs for uncovered or stale mapped
  holdings, prioritized by weight × staleness. This is the automatic path;
  Kuba reviews results, not queue buttons.
- Show value, cost, gain/loss, cash, allocation, concentration, liquidity,
  contribution history, benchmark, and the aggregated scenario range from
  current verified valuations; surface stale coverage, fired falsifiers,
  and evidence-labelled shared downside exposure without implying correlation.
- Codex explains portfolio risk; it never initiates a transaction (V9).

## Interaction rules

- Navigation: `Discover`, `Research`, `Valuation`, `Portfolio` + `System`
  utility. Polish domain copy; no `triage/ingest/worker` jargon, no raw
  workflow IDs in the reading path.
- Progressive disclosure: conclusion first, evidence one click away,
  internals last.
- Honest states everywhere: `oczekuje`, `zbieranie danych`, `szkic`,
  `prowizoryczny`, `zweryfikowany`, `odrzucony`, `wymaga interwencji`.
- Empty/stale/conflict/rejected are first-class states — but they must say
  what is missing and what will fix it, not just exist as badges.

## Non-goals

- No trading, no buy/sell commands, no silent portfolio mutation (queueing
  analysis jobs for holdings is expected automation, not mutation).
- No decorative scores without factor contributions.
- No expert personas, author-branded methods, or consensus theater (V2).
- No performance claims before the calibration/backtest gate
  (STRATEGY — learning loop) passes.
- No parallel implementations of the same capability (V10).

## Acceptance test

The pipeline works when: a company can be kicked out or surface in the one
sieve with explainable reasons → be added (or auto-added via Portfolio) to
Research → get collected, verified evidence and a confirmed profile → get a
company-specific verified scenario set whose assumptions trace to its own
facts → show up in Portfolio exposure with real return math — while the
queue drains automatically and every artifact stays versioned, inspectable,
and honestly labelled.
