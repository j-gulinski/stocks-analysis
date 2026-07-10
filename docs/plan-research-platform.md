# Target plan — evidence-first fundamental research platform

**Status:** accepted direction after the 2026-07-09 top-down audit. This plan
supersedes the old assumption that deployment is the next major stage and that
backtesting can be added later without changing storage. Completed work in
`TASKS.md` remains valid history; the next work is tracked as stages RT.0–RT.7.

## 1. Product north star

The product is a **company-specific fundamental research workbench**, not a
ratio dashboard and not an automated buy/sell oracle. For a selected company it
should:

1. gather financial statements, issuer disclosures, market data, qualitative
   claims and relevant sector/macro inputs;
2. preserve every source with publication time and provenance;
3. turn sources into traceable facts and explicitly identify conflicts/gaps;
4. explain the business model and the few operating drivers that matter for
   this company;
5. let the user build and challenge a thesis, forecast and scenario set;
6. use a versioned investment skill plus controlled model calls to extract,
   critique and synthesize — never to silently invent facts or math;
7. store the exact evidence, assumptions, skill/model version and user feedback
   behind every research run;
8. re-open the case after new information and show what changed;
9. support honest walk-forward evaluation once point-in-time data exists.

The expected daily flow is:

```text
open a Codex task or the web app
  -> start/check the local workbench
  -> discover transparent BiznesRadar candidates or choose a known company
  -> start/continue a research case + choose analysis purpose
  -> refresh sources
  -> resolve data-quality blockers
  -> review business model and key drivers
  -> review/update thesis and falsifiers
  -> edit company-suitable scenarios
  -> run evidence-grounded AI critique/synthesis
  -> approve, annotate or reject conclusions
  -> monitor the explicit next checks
```

The application owns durable data, calculations and research state. Codex is a
conversational operator and reviewer over that system, not the database and not
the only way to use the app.

## 2. What exists now

### Strong foundation to retain

- Polite, isolated BiznesRadar and PortalAnaliz fetch/parse/upsert paths.
- Long-form statement/indicator storage and a shared canonical field mapper.
- Pure metrics, forecast, insights and Malik/OBS thesis logic with substantial
  unit coverage.
- A usable watchlist and stock workspace with source-data drill-down.
- Explicit unknowns, one-off checks and the principle that forum content is
  opinion, not fact.
- A version-controlled strategy skill, rubric and worked examples.
- Structured AI output, token logging, caching and analysis history.

### Material gaps found by the audit

1. **The test baseline is not green.** On 2026-07-09, `pytest -q` produced two
   failures: a stale fixture-date expectation and a forward-C/Z expectation
   changed by the newer quote. Frontend build could not run because dependencies
   were not installed in this worktree (`next: command not found`). Deployment
   is therefore not the next responsible milestone.
2. **No point-in-time truth.** Forced refresh deletes/replaces statement rows;
   report values have no source-document id, publication timestamp or revision
   history. A backtest cannot know what was available on a historical date.
3. **Analysis snapshots are built but discarded.** The prompt assembler returns
   a snapshot, yet `analyses` stores only prescore/output/tokens. This directly
   contradicts the old plan's reproducibility and backtest claims.
4. **Hidden AI work is attached to reads.** `build_dossier()` can call thesis,
   scenario and valuation AI refiners when an API key is configured. Loading a
   watchlist can therefore trigger several blocking model calls per company,
   outside the explicit analysis quota and without a durable run record.
5. **AI plumbing is fragmented.** Thesis, scenarios, valuation, forum
   distillation and final analysis duplicate transports/caches/contracts and
   are tied to one provider. The final tool payload is extracted as a dict but
   not validated through the API DTO before persistence.
6. **The model writes a score that should be deterministic.** The rubric exists,
   but `alignment_score` is still model-generated. Prose may be model-generated;
   arithmetic, caps and score lineage should not be.
7. **Scenarios are not yet company-specific operating scenarios.** The current
   negative/base/positive trio keeps earnings constant, swaps in own-history
   multiple quartiles and uses fixed 25/50/25 probabilities. That is a useful
   valuation sensitivity, but not a simulation of what could happen to the
   business. EBITDA TTM is explicitly absent, so the energy path often falls
   back to C/Z.
8. **Important collected data is not fully used.** Cash-flow statements are
   scraped, but the strategy still labels cash-flow quality as a human-only gap.
   Working capital, cash conversion, capex intensity and dilution are missing
   from the central evidence pack.
9. **Primary-company evidence is too thin.** The system has aggregated
   financials and forum discussion but no immutable issuer reports, ESPI/EBI
   events, report notes, management guidance, shareholder/insider events,
   buybacks, dilution or source citations at claim level.
10. **Backtesting was overclaimed.** Daily prices plus current overwritten
    financials are insufficient. Honest research evaluation also needs report
    publication dates, total-return/corporate-action-aware prices, historical
    index membership or a declared universe, delistings and frozen strategy
    versions.

## 3. Product model: a research case, not one dossier response

Add a durable `ResearchCase` per company and purpose. A case moves through
explicit states:

```text
new -> ingesting -> data_review -> business_model -> thesis
    -> scenarios -> review -> monitoring
```

A case may also be `blocked` with named missing evidence. Each stage produces a
reviewable artifact and keeps user edits separate from model suggestions.

The stock page should open on a compact decision brief, then expose:

- **Evidence** — sources, freshness, conflicts, missing items and exact cited
  facts.
- **Business** — segments, revenue model, cost drivers, capital intensity,
  competitive position and company-specific KPIs.
- **Performance** — statements, normalized history, cash conversion, working
  capital, returns on capital and dilution.
- **Thesis** — thesis, catalyst, why it may be mispriced, counter-thesis,
  falsifiers, next checks and thesis-version history.
- **Scenarios** — editable operating assumptions, valuation bridge,
  sensitivities and probabilities.
- **AI review** — extraction/critique/synthesis runs with citations, model/skill
  provenance, cost and validation status.
- **Journal** — user feedback, decision, confidence, position notes and what was
  learned later.

Do not duplicate the same conclusion in deterministic thesis, AI-refined
thesis, AI valuation and final verdict cards. The target is one canonical case
with deterministic facts/calculations and separately labelled interpretations.

### 3.1 UI/UX overhaul at RT.4

The current dark workspace is a useful functional baseline, not the final
information architecture. Perform the major UI/UX overhaul in RT.4, once the
evidence ledger, company templates and scenario contract are stable. Designing
it earlier would optimize screens around structures that RT.1–RT.3 replace.

The overhaul must be workflow-first:

- one persistent case header with company, `as_of`, workflow state, freshness,
  blockers and primary actions;
- a progressive research path instead of equal-weight tabs and repeated verdict
  cards;
- compact decision brief first, evidence and source documents one click away;
- clear visual separation of sourced fact, deterministic calculation, human
  assumption, model suggestion and approved conclusion;
- scenario editing that shows driver dependencies and the valuation bridge,
  with changes/deltas visible before saving;
- an activity/run drawer for refresh and AI progress rather than blocking page
  loads;
- responsive layouts, keyboard navigation, accessible contrast/focus, Polish
  financial formatting and helpful empty/error/conflict states;
- no dashboard density for its own sake: company-specific content determines
  which panels appear.

Process: audit the existing screens with screenshots and task walkthroughs;
make low-fidelity flow/wireframes; update the design tokens/components; build
the case workspace; verify representative industrial, financial and
event-driven companies at desktop and mobile widths with Playwright screenshots
and manual interaction. Keep `docs/design/` as history/reference, and add the
new approved research-workspace specification there before implementation.

**First slice implemented 2026-07-09.** `docs/design/research-workspace.md`
now binds the `Discover -> Research -> Brief/Evidence/Financials/Scenarios/
Review` hierarchy. The source-seed Discover screen, compact research queue,
single canonical Brief, eight-period financial default and exception-first
Review are live. This does not close RT.4: persistent ResearchCase state,
template-aware views, scenario driver editor, Monitor/Journal, evidence drawer
and automated accessibility/screenshot gates still depend on RT.3–RT.6.

## 4. Evidence and data architecture

### 4.1 Immutable source layer

Introduce these concepts incrementally:

- `source_documents` — company, source type, canonical URL, title, period,
  `published_at`, `fetched_at`, content hash, MIME type, local/object-store path,
  parser version and fetch status.
- `document_versions` — immutable raw version when a document changes.
- `facts` — typed value/text fact with unit, period/effective date,
  `known_at`, source-document id, page/section locator, extractor version,
  confidence and verification state.
- `events` — ESPI/EBI/issuer events with publication time, category, extracted
  claims and source links.
- `data_conflicts` — two sources disagree; do not silently pick one without a
  recorded resolution rule.

Current `report_values`/`indicator_values` remain a serving layer for the UI.
They must gain lineage or be rebuildable from immutable facts. Refresh appends
source versions; it must not destroy the historical state needed for `as_of`.

### 4.2 Research and AI provenance

- `research_cases` and `case_steps` — current workflow state and blockers.
- `thesis_versions` — thesis/counter-thesis/catalysts/falsifiers as of a time.
- `assumption_sets` and `scenario_sets` — human vs model origin, approval state,
  units and evidence links.
- `analysis_runs` — purpose, status, frozen `as_of`, complete input snapshot,
  evidence ids, skill version/hash, provider/model/config, output, validation
  result, cost, latency and user.
- `model_calls` — child calls used by an analysis run, including retries and
  escalation reason. No model call happens without a run record.
- `feedback` — accepted/rejected/edited conclusion plus user reason.

The invariant is: **every displayed claim can answer “from which source, known
when, produced by which rule/model/skill, and edited by whom?”**

### 4.3 Source expansion order

| Priority | Source/input | Purpose | Rule |
|---|---|---|---|
| 0 | BiznesRadar + PortalAnaliz | Keep current metrics and idea context working | Aggregator/forum; never the sole evidence for a material event |
| 1 | Issuer IR reports and official ESPI/EBI publications (PAP) | Reports, guidance, contracts, backlog, buybacks, dilution, management changes | Store raw document and publication time; cite page/section |
| 2 | Official market/corporate-action data or a licensed vendor | Long price history, dividends, splits, rights, delistings, benchmark returns | Prove GPW coverage, terms, total-return handling and historical depth before selection |
| 3 | NBP API | FX/gold and macro drivers for exposed companies | Attach only through a company template; no generic macro commentary |
| 3 | GUS APIs | Sector/demand context | Version variable ids and publication dates |
| 3 | Sector authorities/data (for example PSE/URE for energy) | Company-relevant external drivers | Adapter is enabled only for matching templates |
| 4 | KRS/RDF and issuer governance documents | Annual filings, ownership/governance and related-party checks | Evaluate automation/terms first; preserve original documents |
| 5 | News, transcripts and social/forum sources | Discovery and management-language history | Always secondary and labelled; corroborate material claims |

Official starting points researched in this audit:

- ESPI/EBI publications: <https://biznes.pap.pl/>
- NBP public Web API: <https://api.nbp.pl/>
- GUS API portal: <https://api.stat.gov.pl/>
- KRS/RDF portal: <https://ekrs.ms.gov.pl/>
- PSE system data: <https://www.pse.pl/dane-systemowe>

Availability on a web page is not permission for high-volume scraping. Every
adapter needs a source/terms note, rate policy, fixture and data-quality test.

## 5. Company-specific analytical templates

Replace “sector chooses one multiple” with a versioned `CompanyTemplate`.
Template selection is deterministic from sector/business tags, then confirmed
or overridden by the user. Each template declares required facts, driver tree,
scenario equations, relevant valuation methods, red flags and external inputs.

Initial templates should follow the actual watchlist, not attempt every sector
at once. Candidate library:

| Archetype | Operating drivers | Useful valuation views |
|---|---|---|
| Industrial / consumer | volume, price/mix, gross margin, fixed costs, working capital, capex | forward C/Z, EV/EBITDA, FCF yield |
| Bank / financial | volumes, asset yield/funding cost, NIM, fees, cost of risk, opex, capital | C/WK vs sustainable ROE, C/Z |
| Developer / real estate | presales, handovers, ASP, gross margin, land bank, net debt | P/NAV, C/Z, EV/EBITDA where appropriate |
| Software / services / SaaS | organic growth/ARR, retention, utilization, wage costs, margin, cash conversion | EV/Sales only with growth/margin context, EV/EBITDA, FCF yield |
| Gaming / event-driven | release timing, units, price, platform share, marketing, pipeline | event cash flow / EV; explicit hit/miss scenarios |
| Energy / resources | volume, commodity/spread, availability, unit costs, capex, net debt | EV/EBITDA, FCF yield, asset/NAV where supported |
| Biotech | cash runway, milestones, probability, funding/dilution | staged/risk-adjusted value only after the necessary evidence exists |
| Holding / asset play | stakes, asset values, holding costs, net cash/debt | sum of parts and discount to NAV |

The generic Malik/OBS profile remains an investment-style lens layered over a
company template. It should not force C/Z on a company whose economics require
a different driver model.

## 6. Scenario engine v2

Keep current own-history multiple reversion as a **valuation sensitivity**, not
the whole scenario engine. A scenario must contain:

1. operating assumptions for the template's driver tree;
2. projected income/cash-flow/balance-sheet outputs;
3. valuation assumption(s) and an explicit bridge to equity value per share;
4. evidence or a clear `human_assumption` / `model_suggestion` label for every
   input;
5. catalyst, counter-driver, horizon and falsifier;
6. probability with origin and rationale.

Default scenarios are negative/base/positive, but their drivers and number may
vary by company. Probabilities are not fixed 25/50/25 and are not silently
invented by a model. The model may propose relative probabilities; the UI shows
them as unapproved until the user confirms them. Always display an unweighted
range beside any probability-weighted value so false precision is visible.

Scenario math is pure and unit-tested. Models may suggest assumptions or
explain outputs but may not perform the authoritative calculation.

## 7. AI and Codex architecture

### 7.1 One explicit run orchestrator

Replace the five ad-hoc AI paths with an `AnalysisOrchestrator` and provider
adapters. A dossier GET is deterministic and network-free. Every AI action is an
explicit job with progress, cancellation, quota and a durable trace.

Suggested roles:

- **Extractor/classifier** — source-document structure, claims, tags and
  candidate KPIs. Low-cost model.
- **Verifier** — checks each extraction against cited source spans, units,
  periods and arithmetic. Deterministic validators run first; model verification
  is targeted only at unresolved fields.
- **Research synthesizer** — business model, thesis/counter-thesis and
  scenario critique from the approved evidence pack. Strong model.
- **Adjudicator** — invoked only for material conflicts, failed validation or a
  high-impact conclusion. Strong model, separate prompt/context.
- **Narrator** — compresses an already validated result for the UI. Low-cost
  model or deterministic templates.

Model routing is cost-aware and evaluated, not “use the strongest everywhere.”
The user explicitly permits GPT-5.3 as a candidate for repeated bounded loops
when it is available in the configured account. Current mini/nano-class models
are candidates for simple classification, extraction and rendering; a stronger
model is reserved for material synthesis/adjudication and the final judge.
Treat names as configuration candidates, not permanent constants. Configure by
role (`AI_MODEL_CLASSIFY`, `AI_MODEL_EXTRACT`, `AI_MODEL_VERIFY`,
`AI_MODEL_ANALYZE`, `AI_MODEL_ADJUDICATE`, `AI_MODEL_JUDGE`) and benchmark
quality/cost/latency against the repository eval set before changing defaults.
Do not rely on a limited-preview model for the core path.

Each role has a `ModelPolicy`: permitted models in priority order, reasoning
level, maximum calls/iterations, input/output token ceiling, PLN/USD budget,
timeout and escalation conditions. The orchestrator always tries deterministic
logic first, then the cheapest policy-compliant model. Parallel cheap passes are
used only when the eval set shows that independent extraction/checking adds
accuracy; repeated agreement alone is not treated as proof. The strong judge
receives a compact validated trace plus disputed source spans rather than every
raw document, controlling judge cost without hiding relevant evidence.

OpenAI Responses API is the default target because it supports versioned skills,
structured outputs, tools, background runs and eval traces. Keep a narrow
provider interface so the existing Anthropic path can serve as a temporary
fallback during migration rather than duplicating business logic.

### 7.2 Guarded cheap-model loops

The loop is bounded and evidence-driven:

```text
cheap extraction
  -> schema + unit + period + arithmetic + citation validation
  -> pass: persist proposed facts
  -> fail: retry only failed fields with error feedback (maximum N)
  -> still fail/material conflict: strong-model adjudication or human review
```

Required guards:

- strict structured outputs parsed into Pydantic models;
- source-span ids on every extracted claim;
- no uncited material claim in a final research artifact;
- deterministic recomputation of all financial math and strategy scores;
- checks for units, currency, consolidation scope, period, sign and shares;
- `known_at <= analysis.as_of` on historical runs;
- prompt-injection boundary: source documents are data, never instructions;
- bounded iterations, token/cost budget and explicit escalation reason;
- per-role model policy and a run-level total budget; stop or request approval
  before crossing it rather than silently switching to an expensive model;
- frozen input snapshot and versioned skill for reproducibility;
- eval regression gate before model/prompt/template promotion.

The existing no-fabricated-number check is useful but insufficient by itself:
it can approve a real number attached to the wrong concept. Citation + semantic
field validation is the stronger invariant.

### 7.3 Codex task experience

Build the integration in two steps:

1. **CLI + repository skill first.** Add a stable `workbench` command with
   `doctor`, `start`, `stop`, `status`, `refresh TICKER`, `case TICKER`,
   `analyze TICKER --purpose ...`, `feedback`, and `backtest`. A separate
   `skills/workbench-research/SKILL.md` tells Codex how to start/check the app,
   walk through the case stages, report blockers and open the relevant local
   page. The existing `skill/SKILL.md` remains the investment-analysis skill.
2. **MCP/plugin only when the CLI contract is stable.** Expose typed tools such
   as `start_workbench`, `refresh_company`, `get_case`, `run_analysis`,
   `save_feedback` and `run_backtest`. This lets a Codex task organize the full
   process without scraping the UI. The web app remains the rich evidence and
   scenario editor.

Starting services is an operational action; it should be idempotent, report
ports/log locations and never spawn duplicate servers. A new Codex task may
start the local app automatically when the user asks to research a company, but
merely discussing the repository should not.

### 7.4 Seasoned-investor judge and improvement loop

The last step of an analysis/evaluation cycle is a **separate judge model** with
a versioned `seasoned-investor-judge` skill. Its job is to observe and test the
cheaper model, not to restate the same answer with a more expensive model.

The evaluation harness will:

1. start the application in an isolated test profile and wait for health checks;
2. seed or select a frozen case at a declared `as_of` date;
3. drive the same public API/CLI (and a small Playwright UI smoke path) a user
   uses to refresh evidence, open a case, build scenarios and run the cheap
   model workflow;
4. capture the complete trace: selected template, source citations, extracted
   facts, validation/retry results, assumptions, scenario math, thesis and UI/API
   failures;
5. give the trace plus gold facts/outcomes — never hidden future data for the
   original analysis step — to the judge;
6. score it against a fixed rubric and return structured failure labels plus
   targeted improvement proposals;
7. apply candidate prompt/template/routing changes only in an experiment branch,
   rerun the training cases and then the untouched holdout cases;
8. present the diff, cost/latency change and regressions for user approval before
   changing a production default.

Judge rubric dimensions:

- source and citation correctness;
- financial-period, unit, consolidation-scope and arithmetic correctness;
- correct company-template and valuation-method choice;
- quality of thesis, counter-thesis, catalyst and falsifiers;
- internal coherence of operating assumptions and scenario outputs;
- uncertainty calibration and absence of unsupported precision;
- relevance/specificity to the company instead of generic investing prose;
- whether the workflow found and surfaced material missing evidence;
- usability of the final brief and next-check list;
- total model cost, latency and number of escalations.
- cost-adjusted quality: a more expensive candidate must deliver a material,
  measured improvement on the holdout set.

The judge may recommend: a prompt change, a new deterministic validator, a
template change, additional evidence, a routing/escalation change or a new gold
case. It may **not** directly rewrite approved facts, scores, prompts or code in
production. Historical realized returns can later grade calibration, but are
kept outside the judge context when evaluating whether an original analysis was
honest with the information available at that time.

This is the intended cheap-model optimization loop:

```text
cheap workflow -> validators -> judge grade -> failure taxonomy
     -> candidate improvement -> training replay -> holdout replay
     -> human approval -> versioned promotion (or reject)
```

### 7.5 Reusable-skill promotion policy

Turn a workflow into a repository skill only after it has been performed more
than once and has a stable input/output boundary. A skill must name its trigger,
reuse public CLI/API contracts, avoid hidden external calls, include failure
handling and pass validation plus one forward test before it is relied on.
Version the skill with the run trace whenever it can change an analytical
conclusion.

The first operational skill, `skills/workbench-research/`, owns repeatable
start/doctor/status/browser facilitation now. Extend it when `case`, `analyze`,
`feedback` and `backtest` commands actually exist; do not document fictional
commands. Promote focused `evidence-extraction`, `scenario-review` and
`seasoned-investor-judge` skills only after their RT.2/RT.4/RT.6 contracts and
gold cases are stable. This keeps skills small, testable and cheaper to invoke
than one monolithic prompt.

## 8. Evaluation and backtesting

### 8.1 Three different evaluations

Keep these separate:

1. **Data/parser evaluation** — fixture accuracy, source reconciliation and
   field-level precision/recall.
2. **AI workflow evaluation** — extraction accuracy, citation correctness,
   unsupported-claim rate, scenario-template choice and thesis quality on a
   labelled corpus. Store traces and use graders plus deterministic checks.
3. **Investment research backtest** — whether frozen historical reads and
   assumptions were useful out of sample. This is not the same as testing an
   LLM prompt.

### 8.2 Honest backtest prerequisites

Do not publish a strategy performance result until the dataset has:

- `known_at` publication timestamps and immutable historical facts;
- point-in-time company universe or a precisely declared sampled universe;
- delisted/failed names to avoid survivorship bias;
- split, rights, dividend and other corporate-action handling;
- total-return outcome prices and a suitable benchmark such as sWIG80TR;
- frozen strategy/template/model versions;
- no use of later restatements, forum posts or report values in earlier runs.

Start with a **walk-forward historical case replay**, not a market-wide optimizer:

- choose 20–30 mixed outcomes, including failures and delistings;
- freeze evidence at each report publication date;
- run deterministic metrics/scenarios and save the model output once;
- evaluate 3/6/12/24-month total return, benchmark-relative return, maximum
  adverse excursion, thesis falsification timing and probability calibration;
- reserve an out-of-time holdout; never tune and report on the same cases.

Only after this works should a broader factor backtest or weight optimization be
considered. Optimize transparent deterministic parameters, not opaque prose.
Use the OpenAI Batch API for non-urgent large eval runs where suitable; current
official documentation describes 50% lower cost and completion within 24 hours.

## 9. Revised delivery order

### RT.0 — Restore a trustworthy baseline

Green backend suite, reproducible frontend install/build, real fixture coverage,
one end-to-end local smoke run and explicit diagnostics for source/API status.

### RT.1 — Remove hidden AI and persist run provenance

Make dossier reads pure; create explicit run/job records; persist complete input
snapshots; validate outputs; compute scores deterministically; consolidate AI
transport/config/cost accounting.

### RT.2 — Evidence ledger and primary disclosures

Add immutable source documents/facts/events and `as_of` reads. Implement issuer
IR + ESPI/EBI ingestion for a small pilot set. Every material claim in the case
links to evidence.

### RT.3 — Fundamental depth and company templates

The first low-request Discover slice now preserves and parses one market-wide
BiznesRadar rating document as source evidence; it is a candidate seed, not the
strategy rank. Next compute cash conversion, working capital, capex, returns on
capital, dilution and segment/KPI evidence. Implement 2–3 templates chosen from
real watchlist companies and the selection/override mechanism, then extend
Discover with point-in-time, template-aware screening rules.

### RT.4 — Scenario engine v2 and research-case UI

Operating-driver scenarios, editable assumptions, deterministic valuation
bridge, falsifiers, case workflow and change tracking. Migrate the current
multiple-reversion output into the sensitivity section. Complete the dedicated
workflow-first UI/UX overhaul only after RT.1–RT.3 contracts are stable, with
approved wireframes and desktop/mobile visual QA.

### RT.5 — OpenAI skill/orchestration and Codex workflow

Provider abstraction, Responses API structured runs, guarded role-based model
routing, eval traces, stable `workbench` CLI, repository workflow skill, then
optional MCP/plugin.

### RT.6 — Calibration and walk-forward research evaluation

Gold extraction/evidence corpus, known-company calibration, mixed-outcome
historical replay and the automated application-driving seasoned-investor
judge loop. Prompt/template/model changes must improve training and untouched
holdout gates without violating cost/correctness ceilings. This replaces the
current three-company qualitative calibration task.

### RT.7 — Deploy, monitor and expand

Only now finish auth/deployment/backups/background jobs. Add source adapters and
templates based on real research gaps. Scheduled refresh should ingest sources
and create a review queue; it must not silently rewrite an approved thesis.

## 10. Definition of success

The revised platform is successful when, for a pilot company, the user can:

- start the workbench from a Codex task or normally in the browser;
- see which sources are fresh, missing or conflicting;
- trace every important number/claim to a source and publication time;
- understand the company-specific drivers rather than only generic ratios;
- edit assumptions and obtain reproducible scenario math;
- run an AI review whose evidence, skill/model version, cost and validation are
  visible;
- give feedback that changes the next review without rewriting history;
- re-open after a new report and see fact/thesis/scenario changes;
- replay the same case at an earlier `as_of` date without future leakage.

That is a comprehensive research tool. A larger source list or a more eloquent
model response without these properties is not.
