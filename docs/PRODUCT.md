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
     (revenue, net-profit and profitability trends, valuation below own
     history). Standing still is grounds for exclusion; cheapness alone is not
     admission. Composite health ratings remain safety gates, not improvement
     points.
- Survivors are ordered by one comparable `0–100` potential score: the equal-
  weight mean of within-batch percentiles for revenue momentum, net-profit
  momentum, operating-margin momentum, current operating profitability, and
  current positive C/Z (lower is better). Auditable economic caps prevent
  tiny-base percentage rebounds or extreme multiples from dominating. Health
  composites and leverage are exclusion gates only. The score is an attention
  priority, not a probability forecast. A score requires all five inputs; gaps
  are never imputed. Its factor periods must be recognizable, no more than two
  quarters behind the latest market period, and no more than one quarter apart.
  Stale or misaligned survivors remain visible but unscored and cannot affect
  the score percentiles. Discover returns at most the first 100 ordered
  survivors while preserving the full survivor count.
  The row leads with the single score; its normalized contributions, raw
  values, source versions and freshness stay inspectable one click deeper.
- A material explicitly reported discontinued result cannot win attention via
  distorted net-profit growth or C/Z. When detailed quarterly facts are
  retained before the batch cutoff, Discover freezes a continuing-operation
  bridge and uses its growth and trailing C/Z; the raw market values, threshold,
  fact IDs and document versions remain adjacent. An incomplete bridge makes
  the affected component unavailable without penalty or imputation. A
  continuing-operation C/Z is not compared with raw historical C/Z.
- Retained BiznesRadar analyst expectations are the visible baseline for
  Research: fiscal-year revenue, EBITDA, EBIT and net-income levels, growth,
  range and contributor count. They do not add score points; missing coverage
  is neutral, and Valuation must confirm or challenge the baseline with evidence.
- Excluded companies remain inspectable in an `Odrzucone` drawer with their
  kill reasons — the sieve is auditable and tunable, never a black box.
- Factor coverage gaps are visible; missing data is a gap, never a negative
  fact and never silent exclusion (except where the rule itself is about
  missing fundamentals, e.g. no publishable equity).
- One action per row: `Dodaj do Research`. Reading Discover writes nothing.
- Explain domain terms in Polish (Altman EM-Score, F-Score) as safety gates,
  never as score contributions or verdicts.

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
  range, value vs current price, catalyst and verification status. A weighted
  value and upside appear only when a complete labelled probability tree exists.
- **W portfelu** *(enabled by the S4 portfolio-coverage gate)* — adds position
  weight and portfolio priority; holdings sort first (weight × staleness), then
  Discover candidates, then the rest.

The list opens with the `Do sprawdzenia` agenda derived only from stored
state: new evidence since last snapshot, stale cases, fired falsifiers,
valuations awaiting assumptions and, once S4 enables portfolio auto-coverage,
uncovered holdings. Zero-write to open.

### The company view

One canonical renderer over verifier-gated snapshots (no legacy modes). Its
default reading path is deliberately short:

1. **Decision header** — when a current valuation exists, show its bad/base/good
   range, primary-method values vs current price, probability posture, status
   and nearest catalyst first. Show weighted value/upside only when calculated.
   Otherwise show the missing-valuation state and the next action.
2. **Brief** — current understanding, freshness, main gap and next useful action.
3. **Details on demand** — Business & drivers, Performance, Outlook, Thesis and
   History are separate collapsed sections. Opening one section must not open
   the others.
4. **Evidence and sources** — claims, conflicts, gaps and the source manifest are
   a separate collapsed evidence workspace. Sources may be filtered/selected;
   the page never expands every source and every claim at once.

Run metadata, fingerprints and verifier internals live only in the final audit
drawer. A historical verifier warning may affect the status and next action,
but it does not lead the list or company page as investor-facing content (V3,
V5).

After the recovery reset, History contains only canonical v3 Research created
from the clean baseline. The product has no v1/v2 Research reader,
compatibility badge or legacy-verifier presentation (V10).

Layers stay: common spine → sector/archetype pack → company overlay
(segments, KPIs, company-specific questions) proposed by Codex, confirmable
by Kuba. Research answers its own frozen questions from sources; it never
hands them back as homework.

## Stage 3 — Valuation: the center (V4)

Goal: convert researched drivers into explicit, company-specific
bad/base/good (+optional event) scenarios with prices and probabilities that
could only belong to this company.

- Valuation starts from a frozen Research snapshot and the retained
  BiznesRadar analyst expectation curve. Revenue, EBITDA, EBIT and net-profit
  levels, year-on-year growth, analyst count and range are the visible Street
  baseline—not a price target. Codex must show where its forecast confirms or
  challenges that baseline and which issuer evidence explains the variance.
- Every scenario contains an explicit five-year operating path through revenue,
  EBITDA, EBIT, recurring net income, EPS and FCFF. Reported one-offs are shown
  separately and are never capitalized as recurring earnings.
- Python computes all math deterministically. The company-specific methodology
  selects one primary method and at least one independent method from both
  relative and intrinsic families: recurring P/E, EV/EBITDA, EV/EBIT and FCFF
  DCF. Enterprise-value methods reconcile cash, debt and leases to equity; an
  unknown bridge item disables the affected method instead of becoming zero.
  A partly elapsed first fiscal year is an explicit stub: only remaining FCFF
  is included and every cash flow carries its discount timing from the cutoff.
- Methods are not averaged. The primary method supplies the scenario value;
  cross-checks expose a range and dispersion, while the DCF shows WACC/terminal
  growth sensitivity and terminal-value concentration. Reverse valuation shows
  what growth/margin path and trading multiples the current price implies.
- Scenario probabilities, when published, come from an explicit conditional
  tree whose leaf probabilities are computed by Python. Judgmental nodes are
  labelled `judgmental_unvalidated`; empirical calibration additionally needs
  its frozen point-in-time dataset, sample, Brier score and reliability bins.
  When neither posture is defensible, the result is visibly `uncalibrated` and
  no weighted value is invented.
- The backend enforces company-specificity structurally (see
  ARCHITECTURE — valuation gates): source semantics, Street-to-Codex bridge,
  method math/independence, conditional probabilities, template equality,
  cross-company near-duplicates and lineage are computed before any verifier
  opinion. A current-price-derived forward P/E is market context and cannot
  anchor a target multiple.
- Verification is adversarial (V5): the strict verifier must attach findings
  or per-check justification; computable checks are computed, not attested.
- An explicit human override is separately labelled and creates a recomputed
  version; it cannot masquerade as a reported fact or Street estimate.
- Scenario outcomes are scored when actuals land (V8) and engine calibration
  is visible per version.
- The screen opens with methodology and the scenario result, then the five-year
  Street expectation bridge, method reconciliation, reverse expectations and
  audit trail. It does not lead with an arbitrary one-year input grid.

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
