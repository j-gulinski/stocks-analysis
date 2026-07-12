# Product contract

## Purpose

The Stock Analysis Workbench is the investor's default place for analysing GPW
companies. It should help one investor discover companies, build durable
company knowledge, test valuation scenarios, and understand the portfolio
without reconstructing prior work from websites, spreadsheets, notes, or chat.
It is not a generic stock database, a trading signal, or an autonomous adviser.

Codex gathers, structures, challenges, and verifies the analysis. The user owns
every investment decision. Every material statement must be a sourced fact, a
deterministic calculation, a named assumption, or an explicit gap.

## Product north star

For any GPW company, the Workbench should make it practical to answer:

- why the company deserves attention now and which sieve or event surfaced it;
- how the business makes money, what drives results, and what changed;
- which claims are known, assumed, disputed, stale, or still missing;
- how separate, source-backed Polish-market investor methods interpret the same
  evidence, where they agree, and where they disagree;
- what explicit downside, base, upside, and optional event scenarios imply;
- what would falsify the thesis and which dated evidence should be checked next;
- how the company and its scenarios affect the real portfolio.

The product earns its role as the default workspace by preserving one
evidence-linked history across Discover, Research, Valuation, and Portfolio.
Primary documents remain the source of truth; the Workbench retains their
lineage, the resulting analysis, user corrections, assumptions, and prior
versions. The Roadmap states which parts are available now. Planned,
source-blocked, stale, or provisional capability is never presented as
complete.

## Codex and investor-method perspectives

Codex applies versioned analytical lenses reconstructed from retained public
materials of Polish-market investors. A method pack is a Workbench
operationalization, not the author's current opinion, endorsement,
recommendation, or a simulation of the author's voice.

- Company evidence is gathered once into the canonical Research snapshot before
  any method is applied. A method corpus teaches questions and interpretation;
  it is not company evidence.
- Every supported pack names its sources, version, intended scope, required
  inputs, deterministic calculations, judgment questions, blind spots,
  falsifiers, and evaluation maturity.
- Each applicable method remains a separate perspective with its own coverage,
  supporting and contrary evidence, unknowns, and conclusion. Apparent agreement
  between methods is not independent evidence when they consume the same facts.
- Codex may synthesize agreement, disagreement, applicability, and next checks.
  It does not average perspectives into an anonymous expert-consensus score.
- A deliberate composite must be user-selected, separately named and versioned,
  and must expose every constituent contribution. No hidden blend is allowed.
- Draft or source-blocked packs may show why they are unavailable but may not
  invent a company conclusion. A separate strict verifier owns
  decision-relevant conclusions and final status.

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
- **Thesis** — why now, counter-thesis, catalysts, governance, falsifiers,
  separate readings from applicable supported method packs, Codex's attributed
  synthesis of agreement and disagreement, and next checks;
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

## Default working loop

The default session starts with a compact `Do sprawdzenia` agenda inside
Research, not a fifth product stage or a generic market dashboard. It is derived
only from stored state and may surface new evidence since the last snapshot,
stale cases, unresolved conflicts or material gaps, falsifiers testable against
stored facts, valuations awaiting user assumptions, and portfolio positions
without current verified coverage.

1. The user chooses an agenda item, a Discover candidate, or a ticker and opens
   its canonical `ResearchCase`.
2. The company view leads with what changed, the current understanding, the
   strongest evidence, the main uncertainty, and the next useful action.
3. Refreshing sources, requesting quick or deep Codex analysis, confirming the
   company profile, changing assumptions, and queueing verification are
   separate explicit commands. Opening the agenda or company remains a
   zero-write read.
4. Quick and deep analysis are different depths over the same frozen evidence
   and canonical artifact lineage, not competing company verdicts.
5. Valuation and Portfolio reuse the same Research snapshot and link back to it;
   they do not create competing company conclusions.
6. A completed session leaves a newer dated snapshot, an explicit user
   correction or assumption, or a named evidence gap. Chat output alone is
   never the durable result.

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
- "Default place" does not mean cloning every broker terminal, news service, or
  forum. Retain decision-relevant evidence and link to primary sources.
- No simulated expert persona, implied expert endorsement, anonymous expert
  consensus score, or hidden blend of methods.
- No fifth generic dashboard or replacement orchestration framework merely to
  aggregate the existing stages. Evolve the four canonical stages and artifacts
  incrementally.
- No claim that every GPW company, method, or data source is covered. Coverage,
  freshness, and method readiness remain visible.

## Product acceptance test

The north-star workflow is useful when the user can:

- start from the stored agenda or Discover evidence and understand why a
  company needs attention, why it surfaced, and what evidence is stale or
  missing;
- compare genuinely different sieves and their overlap, then add or reactivate
  one company in Research with a single explicit action;
- open one company home that connects its business, result drivers, primary
  evidence, changes, thesis, counter-thesis, valuation history, and portfolio
  context without reconstructing prior work elsewhere;
- confirm or correct the company profile while preserving the model proposal
  and every prior profile and Research snapshot;
- see each applicable supported investor method separately, including its
  sources and version, followed by a Codex synthesis that names agreement,
  disagreement, applicability, and blind spots without hiding a blend;
- edit explicit assumptions, compare deterministic scenarios, and trace every
  decision-relevant claim to a source, calculation, assumption, or gap;
- revisit the company later and see what changed while all prior snapshots,
  method versions, inputs, and verifier decisions remain available; and
- understand how eligible verified company scenarios change portfolio exposure.

An interim release may satisfy a narrower Roadmap gate, but it must label every
missing, draft, planned, stale, provisional, and unsupported capability
honestly. Merely rendering all four screens is not product acceptance.
