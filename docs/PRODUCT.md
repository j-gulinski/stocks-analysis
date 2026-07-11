# Product contract

## Purpose

The Stock Analysis Workbench is a personal GPW research second brain. It should
help one investor discover companies, build durable company knowledge, test
valuation scenarios, and understand the portfolio. It is not a generic stock
database, a trading signal, or an autonomous adviser.

Codex gathers, structures, challenges, and verifies the analysis. The user owns
every investment decision. Every material statement must be a sourced fact, a
deterministic calculation, a named assumption, or an explicit gap.

## The four product stages

### 1. Discover

Goal: compare a small number of genuinely different, explainable sieves and
choose which companies deserve deeper work.

- Show three sieve columns: financial health, Malik/OBS operating improvement,
  and Portal Analiz value/catalyst opportunities.
- A company may appear in more than one sieve. Comparison and overlap matter
  more than a universal rank.
- Every result shows the two or three factors that caused membership, factor
  coverage, gaps, source, and freshness.
- Explain domain terms in Polish. `AAA` means a strong Altman financial-health
  classification; Piotroski F-Score is a nine-part change/quality test. Neither
  is an investment verdict.
- WIG20, mWIG40, sWIG80, sector, and size are neutral filters or context, never
  yellow warnings or silent exclusions.
- One action exists: `Dodaj do Research`. No triage ceremony, hidden queueing,
  auto-promotion, or model call occurs while reading Discover.
- Do not expose forecast-growth rankings, worker diagnostics, or workflow
  tutorials on the main screen.

Only the financial-health sieve may be shown as complete until the other two
have their required market-wide facts. Missing coverage must remain visible;
thin data must not be relabelled as an investor philosophy.

### 2. Research

Goal: gather broad evidence and turn it into a tailored, durable understanding
of one company.

`ResearchCase` is the single unit shown in Research. Adding a ticker or a
Discover candidate atomically creates or reuses the company, creates or reuses
its case, and queues exactly one initial research job. The case appears
immediately with an honest collection status.

Every company uses three layers:

1. a common spine: business model, performance, cash/balance sheet, governance,
   events, thesis, risks, sources, and gaps;
2. a versioned sector/archetype pack: for example bank, developer,
   industrial/consumer, software/services, gaming/event, energy/resources, or
   holding/biotech;
3. a company overlay proposed by Codex and confirmable by the user: segments,
   operating drivers, company-specific KPIs, competitors, source questions,
   and unusual risks.

The primary company view contains:

- **Brief** — current understanding, freshness, main gap, and next useful
  action;
- **Business & drivers** — how the company makes money and what moves results;
- **Performance** — result bridge and sector-specific KPIs;
- **Evidence** — primary documents, sourced claims, conflicts, and gaps;
- **Thesis** — why now, counter-thesis, catalysts, governance, falsifiers, and
  next checks;
- **History** — what changed since earlier evidence and thesis versions.

Technical run metadata, raw DTOs, provenance internals, and verifier detail
belong in an audit drawer. A fixed renderer consumes typed, verified research
snapshots; Codex does not generate arbitrary page layouts.

### 3. Valuation

Goal: convert researched company drivers into explicit quarter/year scenarios
and possible price outcomes.

- Valuation starts only from a research snapshot and sourced deterministic base
  values.
- Malik/OBS, Areczeks, and Elendix are separate, versioned method packs. The UI
  may compare or deliberately combine them; it must not hide a blend behind one
  score.
- The user edits company-specific Polish assumptions for downside, base,
  upside, and an optional event path.
- Codex selects relevant drivers, explains scenario mechanisms, and assigns
  evidence-backed probabilities. Python calculates the projected P&L, cash
  flow, balance-sheet markers, valuation bridge, and per-share outcomes.
- The main result is one comparison: probability, revenue/result/EPS/FCF or
  sector marker effects, valuation/price range, catalyst, and falsifier.
- Own-history multiple reversion remains a labelled sensitivity, not the
  operating scenario itself.
- The strict verifier checks source lineage, math reconciliation, current
  fingerprints, probability coherence, and look-ahead boundaries before a
  result is labelled verified.

The user receives decision support, never a buy/sell command.

### 4. Portfolio

Goal: understand actual holdings, their history, concentration, and forward
scenario exposure.

- Prefer the documented myfund API or exports; do not scrape or store the
  user's login password.
- Synchronisation stores dated portfolio and position snapshots and updates
  existing holdings. It does not skip a ticker merely because it appeared
  before.
- Show current value, cost, gain/loss, cash, allocation, contribution history,
  sector/company concentration, liquidity, and an appropriate total-return
  benchmark.
- Compute TWR/XIRR only when the required cash-flow history exists and state
  the method and gaps.
- Aggregate the latest verified company scenarios into a portfolio range and
  surface stale research, fired falsifiers, correlated downside, and uncovered
  positions.
- Codex explains portfolio risks and perspectives but never changes a company
  valuation because the user owns it or initiates a transaction.

## Interaction and copy rules

- The complete navigation is `Discover`, `Research`, `Valuation`, `Portfolio`;
  `System` is a secondary utility. During the reset, expose a stage only after
  its vertical meets the Roadmap gate—do not ship empty placeholder screens.
- Use concise Polish domain copy. Avoid `triage`, `prescreen`, `ingest`,
  `worker`, `deployment`, raw workflow IDs, and English DTO labels in the main
  reading path.
- Do not explain a process with a permanent “typical path” rail when the
  information architecture already makes the next action clear.
- Use progressive disclosure: useful conclusion first, evidence one click
  away, internals last.
- Show honest states: `oczekuje`, `zbieranie danych`, `szkic`, `prowizoryczny`,
  `zweryfikowany`, `odrzucony`, or `wymaga interwencji`.
- Empty, stale, partial, conflict, source-failure, and verifier-rejection states
  are first-class product states.

## Non-goals

- No automated trading, buy/sell recommendation, or silent watchlist/portfolio
  mutation.
- No broad autonomous crawler, hidden provider call, recurring Codex worker, or
  read endpoint with side effects.
- No decorative score without factor contributions and calibration evidence.
- No backtest-performance claim before point-in-time facts, adjusted return
  series, delistings, corporate actions, mixed cases, and a holdout exist.
- No deletion of accumulated company evidence merely because a case is hidden
  or archived.

## Product acceptance test

A useful release lets the user compare why companies surfaced, add one to
Research in a single action, watch evidence become a tailored verified company
memory, test explicit result and price scenarios, and see how those scenarios
change the real portfolio. Every step must preserve source, time, assumptions,
and prior versions.
