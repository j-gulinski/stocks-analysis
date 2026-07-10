# Target plan — evidence-first fundamental research platform

**Status:** accepted direction after the 2026-07-09 audit. This is the binding
architecture and RT.0–RT.7 order. `TASKS.md` owns execution status; `PLAN.md`
is the compact stable architecture map; closed detail belongs in archives,
validation notes, learning notes and git.

## 1. Product north star

Build a company-specific fundamental research workbench, not a ratio dashboard
or automated buy/sell oracle. For every company the system should:

1. gather statements, issuer disclosures, market data and qualitative leads;
2. preserve source, publication time, fetch/version lineage and conflicts;
3. expose traceable facts, gaps and company-specific operating drivers;
4. let the user build/challenge thesis, falsifiers, forecasts and scenarios;
5. run versioned, bounded AI extraction/critique/synthesis with strict review;
6. store evidence, assumptions, skill/model version and feedback behind runs;
7. reopen the case after new information and support honest walk-forward replay.

```text
start/check → discover or choose company → refresh → resolve gaps
→ business/drivers → thesis/falsifiers → scenarios → Codex review
→ approve/annotate/reject → monitor next checks
```

The application owns durable data, calculations and research state. Codex is an
operator/reviewer over that state, never the source of truth.

## 2. Current foundation and material gaps

Retain the polite BiznesRadar/PortalAnaliz ingestion, long-form statements,
canonical fields, pure metrics/forecast/insights/thesis/scenario services,
watchlist/workspace UI, explicit unknowns, strategy skill/rubric, evidence
ledger, provider-neutral runs, queue lifecycle and deterministic replay.

Remaining architecture gaps are the reason for the RT order:

- refresh-serving rows need immutable source/publication lineage and `as_of`
  reads;
- every AI run needs a frozen input/evidence snapshot, validated output,
  cost/latency and child-call provenance;
- company templates need cash conversion, working capital, capex, returns,
  dilution, segments and normalized one-offs;
- current multiple reversion is sensitivity, not an operating-driver scenario;
- issuer IR and primary ESPI/EBI facts need claim-level citations;
- replay needs point-in-time availability, corporate actions, delistings,
  declared universe, frozen versions and mixed outcomes; current small-n work
  is diagnostic evidence only.

## 3. Product model: one research case

Add a durable `ResearchCase` per company and purpose with explicit state:

```text
new → ingesting → data_review → business_model → thesis
    → scenarios → review → monitoring
```

Any state may be `blocked` with named missing evidence. User edits remain
separate from model suggestions.

The canonical company workspace progressively exposes:

- **Brief:** state, freshness, blockers, four key numbers, signals and next
  checks;
- **Evidence:** source versions, facts, conflicts, missing items and locators;
- **Business/Performance:** segments, drivers, normalized financials, cash
  conversion, working capital, returns and dilution;
- **Thesis:** thesis/counter-thesis, catalysts, mispricing rationale,
  falsifiers, next checks and version history;
- **Scenarios:** editable assumptions, provenance labels, valuation bridge,
  sensitivities and probabilities;
- **Review:** evidence-linked extraction/critique/synthesis, provenance, cost,
  validation and user feedback;
- **Monitor/Journal:** what changed, decision, confidence and later learning.

Do not repeat the same conclusion in deterministic thesis, AI refinement,
valuation and final verdict cards. Keep one canonical read with labelled
facts, calculations, assumptions, suggestions and approved conclusions.

### 3.0 Investor decision loop

The thin decision loop runs before deep infrastructure is complete and reuses
the session-driven operating model: append-only journal, deterministic
what-changed diff, explicit falsifier states with thesis-at-risk ordering,
minimal read-only positions and UI alignment. It is raw material for RT.6
calibration. Review monthly whether a feature changed a real decision.

### 3.1 UI/UX direction

RT.4 is the major workflow-first overhaul: persistent case header, progressive
research path, evidence one click away, explicit provenance/status, editable
driver scenarios with deltas, activity drawer, responsive/accessibility QA and
no empty shells before their data exists. The first compact Discover/Research/
Brief/Evidence/Scenarios/Review slice is live; persistent case editing,
evidence drawer, template-aware views and automated screenshot/accessibility
gates remain open.

## 4. Evidence and provenance contracts

### 4.1 Immutable source layer

- `source_documents`: company, source type, canonical URL, period,
  `published_at`, `fetched_at`, content hash, parser and fetch status.
- `document_versions`: immutable raw content when a document changes.
- `facts`: typed value/text, unit, period/effective date, `known_at`, source
  version, page/section locator, extractor version, confidence and verification.
- `events`: ESPI/EBI/issuer event, publication time, category, claims and links.
- `data_conflicts`: explicit disagreement plus resolution rule; never silently
  overwrite one fact with another.

Current `report_values`/`indicator_values` remain serving tables but must gain
lineage or be rebuildable from immutable facts.

### 4.2 Research and AI provenance

Target entities are `research_cases`, `case_steps`, `thesis_versions`,
`assumption_sets`, `scenario_sets`, `analysis_runs`, `model_calls` and
`feedback`. Each displayed claim must answer: source, known time, rule/model/
skill, and editor. No model call occurs outside a durable run record.

### 4.3 Source order

| Priority | Source | Use | Constraint |
|---|---|---|---|
| 0 | BiznesRadar, PortalAnaliz | current metrics and discovery context | never sole evidence for a material event |
| 1 | issuer IR, official ESPI/EBI/PAP | reports, guidance, contracts, governance | store raw document/publication time and locator |
| 2 | official/licensed market data | long history, corporate actions, total return | prove GPW coverage, terms and depth |
| 3 | NBP, GUS, PSE/URE and sector data | only template-relevant external drivers | version IDs and publication dates |
| 4 | KRS/RDF and governance documents | ownership, filings, related-party checks | preserve originals and assess terms |
| 5 | news, transcripts, forums | discovery and language history | secondary, labelled and corroborated |

Starting points: [PAP ESPI/EBI](https://biznes.pap.pl/),
[NBP API](https://api.nbp.pl/), [GUS API](https://api.stat.gov.pl/),
[KRS/RDF](https://ekrs.ms.gov.pl/) and [PSE data](https://www.pse.pl/dane-systemowe).
Every adapter needs a terms/source note, polite rate policy, fixture and
data-quality test.

## 5. Company templates

Use a versioned deterministic `CompanyTemplate` selected from business tags and
confirmed/overridden by the user. A template declares required facts, driver
tree, scenario equations, valuation methods, red flags and external inputs.
Start only with real watchlist needs:

| Archetype | Drivers | Valuation examples |
|---|---|---|
| Industrial/consumer | volume, mix, margin, fixed cost, working capital, capex | forward C/Z, EV/EBITDA, FCF |
| Bank/financial | volume, NIM, fees, cost of risk, capital | C/WK vs ROE, C/Z |
| Developer/real estate | presales, handovers, ASP, land bank, net debt | P/NAV, C/Z |
| Software/services | growth/ARR, retention, utilization, wages, cash conversion | EV/Sales with context, EV/EBITDA, FCF |
| Gaming/event-driven | timing, units, price, platform share, pipeline | event cash flow/EV |
| Energy/resources | volume, commodity/spread, availability, costs, capex, debt | EV/EBITDA, FCF, NAV |
| Biotech/holding | runway, milestones, dilution / stakes, asset values, discount | risk-adjusted value / SOTP |

Malik/OBS remains a lens over a suitable template, never a forced multiple.

## 6. Scenario engine v2

Keep current own-history multiple reversion as labelled valuation sensitivity.
RT.4 scenarios must contain:

1. template driver assumptions;
2. projected income/cash-flow/balance-sheet outputs;
3. valuation bridge to equity value/share;
4. evidence or explicit `human_assumption`/`model_suggestion` per input;
5. catalyst, counter-driver, horizon and falsifier;
6. probability with origin and rationale.

Probabilities are not silently fixed or invented. Show unweighted ranges beside
weighted values. Pure functions own authoritative math; models can suggest or
explain but never calculate the saved result.

## 7. AI and Codex architecture

Replace ad-hoc provider paths with one explicit `AnalysisOrchestrator` and
narrow adapters. Dossier reads are deterministic/network-free. AI jobs expose
progress, cancellation, quota and durable traces.

Roles: low-cost extractor/classifier; deterministic-first verifier; strong
research synthesizer; separate adjudicator for material conflicts; low-cost or
deterministic narrator. Required guards: strict DTOs, source spans, unit/period/
currency/scope/sign/share validation, deterministic score/math, `known_at <=
as_of`, source-as-data prompt boundary, bounded retries/budget, frozen input
snapshot, versioned skill and eval regression gate.

Routing is cost-aware, not strongest-everywhere. GPT-5.3 high is reserved for
testing/mechanical work; Luna medium handles basic implementation; Terra high
is the default implementation tier; Sol high handles material
synthesis/adjudication and strict verification; Sol ultra is exceptional only.
Use the stronger suitable model at its full appropriate reasoning level; do not
lower model quality or reasoning merely to optimize an assumed budget limit.
Record actual model, reasoning, role and any substitution/escalation.

The default local loop is session-triggered:

```text
doctor/start → poll → ingest → queue → claim one
→ matching skill → strict verifier → save/reject/needs-human
```

`workbench start` and the UI are idempotent and stop at the claim boundary.
Periodic/hosted polling is opt-in and an RT.7 decision. MCP/plugin surfaces
follow a stable CLI/API contract; do not document fictional commands.

### Judge loop

The separate `seasoned-investor-judge` observes a complete trace plus gold
facts/outcomes and grades source/citation, units/periods/math, template and
valuation choice, thesis/falsifiers, scenario coherence, calibration, gaps,
usability, cost and latency. It may recommend changes but cannot rewrite
production facts/prompts/code. Candidate routing/prompt/template changes must
pass training and untouched holdout cases before promotion.

## 8. Evaluation and honest backtesting

Keep parser/data evaluation, AI workflow evaluation and investment replay
separate. Do not publish strategy performance until the dataset has immutable
`known_at` facts, point-in-time universe, failures/delistings, corporate-action
and total-return handling, frozen strategy/template/model versions and no later
restatements in earlier reads.

Start with 20–30 mixed historical cases, freeze evidence at publication dates,
replay deterministic metrics/thesis/scenarios, and evaluate 3/6/12/24-month
total/benchmark-relative returns, adverse excursion, falsification timing and
calibration on an untouched holdout. Small-n summaries are diagnostic, never
proof; optimize transparent deterministic parameters only.

## 9. Delivery order

1. **RT.0:** trustworthy local baseline, fixtures, smoke and diagnostics.
2. **RT.1:** explicit runs, snapshots, validation, deterministic scores and
   consolidated provider/cost accounting.
3. **RT.2:** immutable evidence, primary disclosures and claim citations.
4. **Stage IL:** journal, monitor, falsifiers, positions and UI alignment.
5. **RT.3:** cash conversion/depth, templates and point-in-time screening.
6. **RT.4:** operating scenarios, case workflow and visual QA.
7. **RT.5:** Responses API, role routing, stable CLI/skill and optional MCP.
8. **RT.6:** gold cases, judge, calibration and walk-forward replay.
9. **RT.7:** auth/deploy/backups/monitoring and pilot-driven expansion.

No deployment or backtest claim precedes the relevant evidence/evaluation gates.

## 10. Definition of success

For a pilot company the user can start the app, see fresh/missing/conflicting
sources, trace important claims, understand drivers, edit reproducible
scenarios, run a cited/verifier-labelled AI review, give feedback without
rewriting history, see what changed after a report, record a decision quickly,
and replay an earlier `as_of` without future leakage.
