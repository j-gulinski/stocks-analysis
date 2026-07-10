# Changelog / decision log

Context ledger for future work: every meaningful change lands here with the
task IDs it implements and any decisions or deviations from PLAN.md.
Format: date · scope · what + why. Newest first.

Enforcement: `.githooks/pre-commit` rejects commits that touch code without
touching this file (`git config core.hooksPath .githooks` after `git init`),
and CLAUDE.md instructs AI sessions to treat a change without an entry as
incomplete.

Older detail is archived verbatim, newest stage first: the closed Stage-TH
entries (2026-07-08) in `docs/changelog-archive-thesis-2026-07-08.md` and the
twelve build-day entries (2026-07-07) in `docs/changelog-archive-2026-07-07.md`;
their durable technical findings live in the quirks ledger
(`skills/scraper-doctor/SKILL.md`). The two digests at the bottom of this file
keep the decisions scannable.

---

## 2026-07-10 · CX.15 — session-triggered operating model; periodic/hosted execution reclassified as optional

Decision: the workbench's default running scenario is pull-based and local.
Ingestion and queue execution are triggered by the user's session
(`workbench start` pre-session hook + explicit UI re-check/process actions),
not by an always-on scheduler. Rationale: Malik-style fundamental decisions
have hours-not-minutes latency needs, a ten-minute ESPI poller adds GPW load
against the politeness rules for no actionable benefit, and host-local
automation silently stops when the Mac sleeps anyway.

Correctness while away comes from retrospective completeness, not real-time
capture: new task CX.15a adds a per-source `last_polled_at` watermark and
paginate-until-watermark ESPI ingestion (hard page cap, existing per-domain
limits), so once-per-session polling cannot miss a watched report that
scrolled off page 1. CX.15b/c add the `workbench start` hook and the
"Sprawdź komunikaty ESPI" / "process queue once" UI actions on the existing
`prepare_pre_session_brief` contract.

The ten-minute host-local Codex automation (CX.12) and any future hosted
poller are reclassified as an **opt-in variant, default off** (CX.15d); a
hosted poller stays an RT.7 decision taken only if away-capture becomes a
real need. Updated: `docs/plan-research-platform.md` (§7.3 operating model,
RT.7 hosting-optional), `.codex/tasks/stock-queue-worker.md` (default
trigger), `TASKS.md` (CX.15 with acceptance criteria). Task hygiene in the
same pass: CX.12 and CX.9 marked done — their runtime-proven/delivered scope
is complete, with the leftover scheduled-worker follow-up moved to CX.15d and
legacy removal already owned by CX.10.

## 2026-07-10 · cleanup — conservative dead-code removal (branch refactor/complexity-reduction)

Complexity-reduction pass; behaviour unchanged (406 backend tests green,
`tsc --noEmit` clean). Dead code confirmed via vulture (full-tree run, 60%
confidence), an AST import graph, and per-name grep across app/scripts/tests
plus doc-referenced entry points before every removal.

Removed — backend: `api/analyses.py` `count_analyses_today` +
`_start_of_today_utc` (its docstring claimed `diagnostics.py` imports it — it
doesn't; the daily-cap arithmetic lives in the orchestrator/ledger path),
`_snapshot_hash`, and `_json_safe` (the live copies are the same-named private
helpers in `agent_evaluation.py`/`backtest.py`, which is why vulture alone
missed it); `api/schemas.py` `VerificationRunOut` + `CandidateRunOut` (no
route or serializer uses them); `services/analysis_contracts.py`
`ForumDistillation`/`ForumDistillationClaim` (the live distillation contract
is `forum_distiller.DistilledClaim`); `services/thesis_ai.py` `extract_json`
alias (`scenarios_ai` uses only `numbers`/`parse_response`); unused imports
(ruff F401) in `mcp/stock_tools.py`, `api/analyses.py`,
`services/analysis_contracts.py`, `tests/test_valuation_ai.py`.

Removed — frontend: orphaned `MetricCards.tsx` and `ThesisPanel.tsx`
(superseded by AnalysisPanel/CompanyReport; zero imports at HEAD and in the
working tree) plus their now-orphaned scss rules in `globals.scss`
(`.verdict` block, `.points-empty`, `.principle`, `.thesis-read`,
`.valuation-basis`); stale ThesisPanel references in the ScenariosPanel
header comment.

Deliberately NOT removed (decisions): `Event`/`CandidateRun` ORM models are
code-dead but schema-bound (tables created by migrations 0008/0003) — removal
needs an explicit drop-table migration decision; `thesis_ai.refine_thesis` is
a fully-tested WP2b feature awaiting integration, not dead; `pa-scraper/`
stays as the documented scraper reference (PLAN.md §"reference only");
`analysis_contract.py` vs `analysis_contracts.py` naming left alone — both
are live with different roles (codex save-path checker vs verdict pydantic
contract).

## 2026-07-10 · CX.12/CX.14/RT5.4 — live queue pickup and decision-first report UX

Closed the gap between durable queue creation and real local pickup. A
host-local Codex automation now runs every ten minutes, starts and health-checks
the workbench, claims one oldest job, uses 5.3 Spark for bounded research/draft
work and reserves quick/deep approval for the strongest strict verifier. The
first runtime proof completed candidate-scout `#4` with verifier `pass`. SNT
deep-analysis `#5` was then claimed and closed by the same contract: Spark
prepared the bounded research draft and `gpt-5.6-sol` independently corrected
and verified it. The terminal verdict is `needs-human`, not a stuck queue row:
potential `+9.8%`, neutral 540-day direction, confidence `0.45`, company score
`54/100`, catalyst/backlog confirmed and governance partial. Approval remains
blocked because the cited issuer pages are frozen as URLs rather than stored
`DocumentVersion` evidence and governance promise-keeping/related-party review
still requires a human judgment. The repository prompt now
requires catalyst, backlog/order book and management/governance source
completion, and records `confirmed`/`partial`/`not_found` rather than pushing
those checks back to the user. Company size/sweet-spot fit remains strategy
context and is explicitly forbidden as a standalone risk or score input. The
automation is local Codex state, not a deployable backend worker; another host
must recreate it, and a sleeping/offline Mac cannot execute it.

Reworked the prepared report around the actual decision summary: estimated
scenario potential, scenario confidence, a verifier score (or honest prescore
fallback) and valuation basis now lead. Long deterministic uncertainty prose
is compressed; confidence rationale is collapsed; catalyst/backlog/governance
have three visible research-status cards. Raw discontinued-operation anomalies
stay in the result-quality bridge rather than leaking as the main watchlist
risk, while strategy-size factors are filtered from visible pros/risks. The
analysis history now polls completed analysis rows as well as queue rows,
prevents duplicate deep jobs while one is active and labels queued work as FIFO
waiting for the external cyclic worker.

Replaced the contradictory first-refresh UI with one progress surface and a
single retry path; established-company refresh runs as a compact activity row.
Watchlist rows now summarize potential, confidence and deterministic score and
prefer a prepared result-quality warning over raw insight text. Scraper-doctor
also isolated the ABS missing-name symptom: the live profile uses a generic h1
with the legal name in h2. `parse_profile` now accepts that non-generic h2
fallback, covered by a focused test and recorded ABS real-fixture matrix.
The same live refresh exposed that `br_login` echoed the configured account
identifier into the browser-visible source summary; it now returns only the
authentication state, with a regression test preventing credential-identity
leakage.

The completed candidate-scout output is no longer hidden in queue JSON.
Discover polls the exact evaluation job, shows its verified batch summary and
adds compact per-ticker `prescreen Codex x/100` context for evaluated names.
The label deliberately says source prescreen rather than company/investment
score, and the row keeps only the organized next-stage classification instead
of dumping the worker's raw evidence and English action prose.

README now explains starting/opening the app from a local Codex project and the
expected scenario workflow: refresh evidence, deterministic dossier rebuild,
review/edit/save forecast assumptions, then queue a verifier-gated Codex read.
It states the current multiple-reversion limitation instead of implying that
company-driver scenario v2 already exists.

Final validation: all 406 backend tests pass, frontend TypeScript validation
passes, and the live SNT report was reloaded in the in-app browser without the
raw `477.7%` warning or company-size-as-risk wording. The report still exposes
the deterministic `+9.8%` potential and continuing-earnings basis while the
non-approved deep result remains visibly gated as `needs-human`.
The report now distinguishes that terminal review state from unfinished work:
it may show the verifier-owned score, confidence and researched
catalyst/backlog/governance findings with an explicit `wymaga przeglądu` badge,
but it still cannot present the row as verified.

## 2026-07-10 · RT.7 exploration — hosted Codex boundary and communication flow

Added `docs/hosting-codex-automation.md` after checking the current code and
official OpenAI, Railway, Vercel, Slack and Resend documentation. The selected
first topology keeps the existing Vercel UI + Railway API/Postgres direction,
adds short-lived Railway ingestion/notifier jobs, and leaves
subscription-entitled Codex on a trusted Mac connected through a future scoped
HTTPS MCP/API boundary. The hosted app queues durable work; it does not embed a
personal Codex credential. A fully hosted 24/7 model worker is a later OpenAI
API/billing option behind RT.5/RT.6 evaluation and budget gates.

Slack is the recommended first communication lane through a transactional
Postgres notification outbox; e-mail is an optional digest via a transactional
provider. Notifications carry only prepared verified/needs-human/failure
summaries and links, never raw forum posts, dossier JSON or model reasoning.
Recorded auth, scoped-token, idempotency, backup, cloud-source-egress and
Warsaw/UTC scheduling gates plus staged P6.8/P6.9 follow-ups. This is an
architecture decision only: no hosting account, deployment, webhook or message
was created.

## 2026-07-10 · RT3.1/RT4.5 — continuing-earnings bridge and report-first company UI

Changed the company workspace from a growing data dashboard into a prepared
report. The default Raport view now presents one executive read, four key
numbers, a result-quality bridge, the most important pros/risks/next checks and
the relevant operating chart. Scenario/price views remain curated in Wykresy;
financial tables, prescore detail and unverified forum material moved behind
the Źródła audit tab, while historical model output moved to Codex. Old
`needs-human` rows are no longer selected as current analysis. A saved model
result must be verifier `pass` and match the normalized valuation snapshot.
The company-page action now queues the full `stock-deep-analysis` workflow:
5.3 Spark owns source research/drafting, while the strongest verifier owns the
final prediction, result quality and approval.

Added a deterministic bridge between reported and continuing earnings.
Quarter metrics expose the explicit discontinued result, continuing net and
its share of reported net. TTM continuing net/EPS/C/Z is computed only when all
four source quarters explicitly contain the discontinued row; missing is never
silently treated as zero. Reported figures remain available for reconciliation,
but prescore, thesis, own-history current C/Z and scenario fallback EPS use the
continuing basis when complete. SNT therefore shows the economic bridge in
prose instead of promoting the raw `477.7%` proxy to a KPI. Because the stored
ledger still lacks the issuer/ESPI explanation, the cause is labelled
`unresolved_from_stored_evidence` and the report remains a draft.

The isolated report component was routed to `gpt-5.3-codex-spark` under the
session's lightweight-task rule. The primary feedback loop caught a missing
first-pass artifact and then rejected a resumed pass that drifted from the
typed dossier contract; the corrected component passed the production
TypeScript build. Focused backend metrics/API tests cover the complete bridge,
the missing-row guard and the report DTO.

Final in-app browser QA caught two presentation/runtime regressions that static
checks could not: the verbose `477.7%` insight still leaked into the prepared
risk list, and the report chart still plotted reported rather than continuing
net profit. The duplicate was removed, the chart now prefers continuing net
where the bridge exists, and raw values remain in audit data. Running `next
build` beside the live dev server also temporarily mixed production/development
RSC assets; the owned processes were restarted and the final SNT Raport/Codex
checks have zero console errors. The SNT demo is left open on Raport.

## 2026-07-10 · Research tactics — PortalAnaliz track records and expanded BiznesRadar roles

Completed bounded, read-only learning audits without persisting forum authors
or post bodies. The strongest accessible PortalAnaliz record was the collective
FIPA portfolio's reported `+239.7%` over 2020–2023, with contemporary
transactions, some cash-flow/benchmark disclosure and substantial drawdowns.
It merits medium-high research-priority confidence but remains `needs-human`
for verified alpha because the exact TWR/XIRR method is absent. The individual
2011–2020 IKE record is longer but less reproducible: its `+380%` value increase
and claimed 31% average annual return cannot be reconciled without dated
contributions. The deep-analysis/verifier skills now allow credible
long-duration authors to prioritize process tactics only—pre-trade case and
maximum price, explicit invalidation, thesis-delta, patience and concentration
review. Reputation cannot promote a forum claim to fact, prediction confidence
or stock score.

The BiznesRadar audit identified useful controlled extensions: consecutive
market-snapshot deltas for candidate scheduling, a separate NewConnect recall
universe, sector-relative context with fiscal/peer caveats, per-share
reconciliation checks and liquidity/execution labels from stored volume. These
are recorded as verifier/backtest-gated follow-ups. RSI/MACD, candlestick and
BR buy/sell labels remain out of scope. The learning note explains the
report/read-model split and both source audits for a C# developer.

## 2026-07-10 · CX.12 — recall-first Discover and idempotent scout queue

Broadened the default Discover funnel so useful ideas are not discarded before
Codex review. The fixed `recall-v1` policy keeps BiznesRadar numeric ratings of
at least 5 without requiring Piotroski F-Score; missing F-Score is now an
explicit caveat rather than an implicit rejection. The API can return up to 300
matches while the UI still renders 15 initially and reveals more on demand.
Presentation presets no longer affect the automatic evaluation payload.

Every immutable market-rating source version now ensures exactly one aggregate
`stock-candidate-scout` job. Migration `0009` adds a nullable unique
`agent_runs.idempotency_key`, so cached reads, identical forced refreshes and
concurrent page loads cannot flood the queue. A changed source version creates
one new job. Its frozen payload retains the full recall shortlist, but the 5.3
worker evaluates only a 12-name budget in batches of four; it performs a
source-only prescreen, never broad-refreshes companies and never mutates the
watchlist. The UI reports the job id/status honestly, including that `queued`
means waiting for the Codex worker. Focused discovery/pickup tests cover recall,
missing values, provenance, dedupe and changed-version behavior.

## 2026-07-10 · CX.4 — cost-aware deep research, strong final judgment

Refined `stock-deep-analysis` model routing at the user's request. Long
source-completion loops, official-web research and full memo drafting now
default to `gpt-5.3-codex-spark`. Research stops on evidence coverage rather
than an artificially small page budget, while repeated searches that add no
primary evidence remain forbidden. Official evidence is persisted through app
adapters when supported; otherwise it remains an explicit `needs-human` input.

The strongest configured `verifier_strict` model (currently `gpt-5.5` high)
independently checks the frozen dossier/source manifest and owns the final
prediction, confidence, result-quality fields and verification status. Queue
worker guidance and the model-role plan now match the skill. A detailed 5.3
draft alone can no longer be saved as verified, and deep runs record both
drafting and verifier roles/models in `input_snapshot.model_trace`.

## 2026-07-10 · RT0.3/RT0.4 — real-source baseline, runtime exit gate and result-quality correction

Closed the remaining trustworthy-baseline source gates. Recorded complete
ticker-specific BiznesRadar fixture matrices for SNT (GPW, canonical slug
`SYNEKTIK`) and CRB (NewConnect), covering profile, quarterly/annual income,
balance, cash flow, both indicator pages, dividends and first-page price
history. The live premium session passed the fixed `/login/` marker check.
PortalAnaliz topics were found to return a login page with HTTP 200
anonymously, so `record_topic_fixture.py` now uses the configured
`ForumClient`, refuses non-post/non-vote captures and stores only the minimal
sanitized parser structure. The live vote selector is `a.post-reputation`;
session ids, account data, authors, locations, signatures and post bodies are
not persisted. The phpBB credential POST was also moved onto the shared polite
HTTP path, closing an existing all-HTTP-through-`scrapers/http.py` violation.

The browser pilot exposed a decision-relevant quality bug in SNT rather than
only checking that pages rendered. The old one-off proxy measured
`|EBIT - profit_on_sales|` and called earnings repeatable even though the
statement contained `256 562 tys. zł` from discontinued operations. Added
canonical mappings for extraordinary/discontinued rows; the shared pure metric
now includes those explicit magnitudes, so SNT reports `477,7%`, fails profit
quality and warns that net profit/C/Z are distorted. Backtests reuse the same
function. Thesis `verify_next` now reuses the evidence-specific insight comment
instead of a narrower hard-coded explanation. Deterministic valuation
confidence is capped at medium when a high-importance negative signal remains;
coverage/history depth alone can no longer label this case high confidence.

Added the user's mandatory runtime phase-exit gate to
`docs/project-guardrails.md`: every phase/work package must pass
`./workbench doctor`, idempotent `start`, `status`, backend HTTP health and
frontend readiness, with matching logs inspected on failure. The pilot caught
an operational collision because a stale Codex worktree with the same Compose
project name recreated Postgres on host `5432` while the current primary
checkout correctly expected `5433`; after the stale `start --open` completed,
the primary checkout recreated the container from its current Compose file and
remained healthy. Run operator commands from the checkout being verified.

Model routing followed the session policy: GPT-5.3-Codex-Spark handled the
bounded one-file guardrail wording, live selector insertion and thesis wording
lineage edits. The primary/strong loop reviewed every diff, sent formatting
feedback where needed, ran focused tests and owned the multi-file diagnosis,
financial semantics, confidence policy and browser verification.

RT0.4 live pilot: `doctor/start/status` passed; a non-forced SNT financial
refresh completed with nine polite HTTP requests and all source surfaces OK;
Brief/Evidence/Financials/Scenarios/Review loaded, scenario live-preview POSTs
were confirmed `save:false` with zero persisted forecasts, and browser console
errors were empty. Focused parser/login/HTTP/metrics/insights/thesis/scenario/
valuation/backtest suites are green; full backend/frontend/runtime exit results
also pass: the complete backend `pytest` suite, Next.js production build
(compile + lint/typecheck + static generation), `git diff --check`, fixture
secret-marker scan, final `doctor`, idempotent `start` and `status`. Backend
health is HTTP 200, frontend readiness is green and both stored source-health
checks pass. The workbench is intentionally left running.

## 2026-07-10 · Documentation merge — one evidence-first Codex roadmap

Reconciled the parallel Codex-agent/evaluation work and the evidence-first RT
roadmap without erasing either history. Existing CX queue, MCP, ESPI/EBI,
verification and replay capabilities remain documented, while RT.0–RT.7 is the
binding delivery order for provenance, company templates, operating-driver
scenarios, controlled model routing, judge evaluation and honest backtesting.
The implemented `research-workspace.md` controls workflow/IA; the light
Research-studio v2 remains a visual proposal to reconcile in a later UI slice.
No incomplete task was promoted to done during the merge.

The merged `./workbench` operator was also reconciled with the main project's
Compose port (`5433`, configured through `DATABASE_URL`). It now derives the
database host/port without exposing credentials instead of hard-coding the old
worktree's `5432`; doctor/status/start and the migration readiness gate all use
the same endpoint. This was caught by starting the merged app from the primary
checkout rather than treating test success as an operational handoff.

## 2026-07-09 · Expert review doc — roadmap vs automation/learning expectations

Added `docs/expert-review-2026-07-09.md`: consolidated session feedback in one
place — the UI-drift analysis behind the v2 redesign (pointing to
`design-v2.md`/`mockups-v2.html`/`plan-ui-refactor.md`), and the roadmap
review against the user's target ("automatic analysis; backtesting refines
the tactic and teaches the Codex skill"). Grep-verified gaps recorded: no
scheduler/auto-enqueue rules (pickup contract only), insufficient historical
data (4 tickers, prices since 2026-04-28, no publication dates → all outcome
windows missing), and no loop closure into the skill (no skill/rubric version
stamped on runs, 4-case WorkedCase corpus, learning notes only). Proposed WPs:
CX.11 split into price backfill / ESPI-archive publication dates / universe
expansion, plus CX.15 autopilot policies, CX.16 skill versioning, CX.17 case
harvester, CX.18 champion/challenger skill replay over frozen
`input_snapshot`s — all under an auto-propose / verifier-approve rule per
project guardrails. Also flagged: `plan-research-platform.md` and
`research-workspace.md` from an earlier session are not in the repo and need
to be saved into `docs/` before coverage can be checked. No TASKS.md changes
yet — proposals await user acceptance.

## 2026-07-09 · CX.14 redesign proposal — "Research studio" design v2 + IA

Analyzed the UI drift after the CX pivot and produced the full redesign
proposal for CX.14. The app accreted three product identities (data
presentation → decision workspace → Codex-operated analyst OS) and the UI
still stacks all of them: an 11-section dashboard with the watchlist at the
bottom, three overlapping verdict surfaces on the stock Brief tab, per-panel
improvised status/verifier/provenance markup, ingested `event_reports` with
no UI home, and a 2-item nav that no longer matches the app. Design docs v1
had also drifted from code (tabs, tokens).

Decisions (user-driven): the v1 visual direction (dark `#0e1217`, 13 px,
flat, dense) is **discarded, not iterated** — user rejected it as too tight
with wrong colors. New direction chosen from three options: light "Research
studio" (warm paper, white cards + soft shadows, serif display type, mono
tickers, indigo accent, 15 px base, 8 pt grid, ink sidebar). Scope chosen:
full app UI; deliverable: proposal + mockup, no code changes yet.

Deliverables: `docs/design/design-v2.md` (token/type/layout/component spec;
shared primitives StatusChip/VerifierBadge/ProvenanceChip/RunRow/
OutcomeWindows/MetricTile/EmptyState so CX.11–13 surfaces stop improvising),
`docs/design/mockups-v2.html` (4 frames: watchlist workbench with "Dziś"
strip + operations rail, stock page with single verdict band + context rail +
new "Zdarzenia" tab, Research page, component sheet + palette alternates —
populated with the real 2026-07-09 app state: ASB/CBF/DCR/SNT, CBF −10,1%
weighted EV, backtest run #7 `estimated_period_lag·120d`, evaluation
needs-human with missing outcome windows). Rewrote `docs/plan-ui-refactor.md`
as v2: change analysis, new IA (Watchlist / Candidates / Research /
Operations / Settings + stock verdict band), six ordered migration slices
(tokens+primitives → shell → dashboard split → stock page → primitive
adoption → mobile), per-slice verification, open questions. Marked v1
`design.md` superseded (kept as archive). No backend changes required by the
plan; the new Zdarzenia tab reuses the existing
`GET /api/companies/{ticker}/event-reports` endpoint.

## 2026-07-09 · CX.9/SC correction - verifier loop + consensus-backed scenarios

Tightened the Codex analysis quality gate after the CBF review showed scenarios
could be read as recommendations even when the underlying potential was weak.
Added `.agents/skills/stock-result-verifier` and wired quick/deep analysis
skills plus the strict verifier around a feedback loop: draft analysis must
state structured `prediction`, `potential`, and `result_quality`; the verifier
compares those fields against the dossier, result causes, one-off risk,
scenario warnings and deterministic valuation before a run may be saved as
verified. `save_analysis_run` now rejects `pass` outputs for quick/deep company
analysis when those structured fields are missing.

Fixed deterministic scenario framing. The UI no longer colors/labels the
internal `positive` path as bullish unless its actual upside is positive, and
scenario sets now emit `quality_warnings` when the weighted expected value or
all priced paths are negative. C/Z scenarios now prefer BiznesRadar
`/prognozy` analyst-consensus net income as forward EPS when available and
internally sane; the driver is disclosed in each scenario assumption. CBF now
uses the stored 2026 BiznesRadar consensus EPS, moving the upper-quartile path
to a small positive upside while keeping the weighted expected value negative,
which is a more honest read than the previous trailing-EPS-only downside set.

Live source check: `https://www.biznesradar.pl/prognozy/PZU` parses with
`2026/2027/2028 konsensus` columns, but the anonymous scraper response returned
empty consensus values for revenue, EBITDA, net income and C/Z at verification
time. The app will use those fields when they contain numbers; if the logged-in
browser shows extra values, the next work item is session/credential handoff,
not a parser change.

Follow-up in the browser confirmed the same PZU table shape with empty
2026-2028 consensus cells in the in-app browser context. The refresh summary
now distinguishes this state as `kolumny konsensusu bez wartości` instead of
collapsing it into a vague "brak konsensusu", with a fixture-backed regression
covering empty consensus columns.

Saved a new CBF `stock-quick-analysis` run using the corrected scenario set
(`analysis_run_id=2`, `agent_run_id=3`, `verification_status=pass`). The saved
output includes structured `prediction.direction=negative`, deterministic
`potential.value_pct=-10.1`, `range_pct=[-22.18, 3.7]`, and `result_quality`
notes that keep scenario validity limited until cash-flow and net-level quality
checks are done. Agent-evaluation replay now parses the structured fields
correctly, but remains `needs-human` because all 30/90/180/365-day future price
windows are still missing from stored history.

Exposed the same structured contract in the Analysis tab. Saved Codex runs now
show a compact manifest chip for direction/potential, selected-run badges for
analysis id/status/verifier/source/model, a structured strip for prediction,
potential range, scenario validity and confidence, plus labelled
`result_quality` notes. This makes CBF's `negative -10.1%` / limited-scenario
read visible in the UI instead of buried in JSON. A follow-up
`gpt-5.3-codex-spark` audit loop checked the strip for null/zero handling,
object confidence, source fields, result-quality rendering and mobile wrapping;
the resulting patch made missing `source_fields` and blank `result_quality`
notes explicit for partial or malformed outputs.

Session model tracking: bounded audit/design work was delegated to
`gpt-5.3-codex-spark` style worker loops, while scenario policy, verifier
contracts and code changes were supervised in the stronger orchestrator role.
The Analysis-tab UI slice was deterministic frontend work kept in the stronger
orchestrator role; future copy/style sweeps and DOM-overflow audits are good
`gpt-5.3-codex-spark` loop candidates, but investment-facing interpretation
still requires verifier/5.5 review.

Verification so far: focused scenario/API regression passed earlier, full
backend regression passed earlier in the CX slice, `cd frontend && npm run
build` passes, and browser checks on `http://localhost:3001/stock/CBF`
confirmed the Analysis tab renders the CBF structured fields on desktop and at
390px mobile width with no horizontal overflow. The same 5.3 audit identified
queue truthfulness (`queued/running/completed/rejected` plus completed output
ids) as the next UI refactor slice, not part of this completed contract strip.

Implemented that queue-truthfulness slice next. Dashboard and stock Analysis
tab now fetch recent `agent_runs` without filtering to only `queued`, label
queued rows as waiting for a Codex/MCP worker rather than running, show claimed,
closed, failed/rejected and needs-human lifecycle text, and expose
`outputs.analysis_run_id` as `analysis #...` when a worker saved output. This
keeps web-triggered jobs honest: the web app creates durable work rows; Codex,
scheduled automation or MCP workers must still pick up and complete them.
A second `gpt-5.3-codex-spark` audit loop found no TypeScript issues, confirmed
the queue-truthfulness plan match, and flagged two polish risks. Both were
fixed: dashboard and stock Analysis workflow rows now silently poll every 30s,
and the stock Analysis toolbar uses wrapping layout to avoid mobile overflow.

## 2026-07-09 · CX.12/CX.13 continuation - queue completion + agent-evaluation UI

Closed another queue lifecycle gap for Codex-operated work. Added
`complete_agent_run` to the MCP toolset and
`backend/scripts/codex_complete_agent_run.py` so watchlist-level jobs such as
`stock-candidate-scout` can close their original `agent_run` even when they do
not produce a single company `analysis_run`. The queue-worker prompt and
`codex_pick_agent_run.py` execution contracts now point candidate/pre-session
workers to that completion path.

Added the dashboard "Agent Evaluation" panel inside the Backtest Lab area. The
UI can create evaluation runs through `POST /api/agent-evaluation-runs`, list
recent saved runs, expand observations, and show verifier state, model role,
structured prediction source, hit/miss/missing outcome windows and data-quality
warnings. Persisted evaluation observations now include ticker metadata in
`known_inputs` so expanded UI rows remain auditable without relying on hidden
company ids.

Session model tracking: a supervised `gpt-5.3-codex-spark` worker attempted the
candidate-scout queue contract and correctly reported an empty queue without
running an unsourced scan. Stronger supervision kept the agent-valuation replay
policy strict: prose-only predictions are still not inferred, and strategy or
prompt changes remain blocked on verifier-reviewed evidence.

Verification: focused backend tests for agent evaluation, agent runs and MCP
tools passed; full backend regression passed (`323 passed, 6 skipped`),
frontend production build passed, `git diff --check` passed, Alembic is at
`0004 (head)`, and browser checks confirmed the Agent Evaluation panel renders
on desktop/mobile with no detected mobile overflow.

## 2026-07-09 · CX.13 start - agent valuation replay

Implemented the first deterministic agent-output evaluation slice. Added
`agent_evaluation_runs` and `agent_evaluation_observations` storage, the
`services/agent_evaluation.py` replay engine, `POST/GET
/api/agent-evaluation-runs`, `backend/scripts/codex_evaluate_agent_runs.py`,
MCP `evaluate_agent_runs`, and frontend API/types for the future UI panel.

The evaluator replays saved `analysis_runs` as point-in-time prediction
objects. It parses only structured fields such as `prediction.direction`,
`potential.value_pct`, `valuation.potential.value_pct`, `expected_upside_pct`,
or `upside_pct`, then attaches later price windows under `outcome` and scores
directional hit/miss. It deliberately does not infer direction from prose;
missing structured prediction becomes `unknown` and the run is marked
`needs-human`.

This gives Codex a path to test whether agent valuation/memo outputs were
useful over time without changing prompts or strategy weights automatically.
Any learning conclusion still requires separated validation periods and
`verifier_strict`.

Local smoke run after migrating to `0004`: a background
`gpt-5.3-codex-spark` worker consumed queued SNT `stock-quick-analysis`
(`agent_run_id=2`) and saved `analysis_run_id=1` as `needs-human`. The first
agent-evaluation replay found one saved SNT analysis, no structured prediction
direction/potential in that output, and missing future 30-day price outcome, so
the evaluation correctly stayed `needs-human`.

## 2026-07-09 · CX.12 start - web-triggered Codex worker bridge

Clarified and implemented the first honest queue-execution bridge. The web/API
queue remains durable task creation; it does not embed a Codex runtime. Added
`backend/scripts/codex_pick_agent_run.py` so a manual, background or scheduled
Codex run can list/claim queued `agent_runs` and receive a workflow-specific
execution contract. Added `.codex/tasks/stock-queue-worker.md` as the reusable
prompt for a Codex queue worker.

Closed a queue lifecycle gap: `save_analysis_run` in MCP and
`codex_save_analysis.py` now update the original `agent_run` when an
`agent_run_id` is supplied, including status, output metadata,
`verification_status`, and `finished_at`. This prevents web-created jobs from
appearing stuck after Codex saves a result.

Added `docs/plan-agent-valuation-backtest.md` for replaying saved agent
valuation/analysis outputs against future outcomes, and
`docs/plan-ui-refactor.md` for the modern workbench layout direction. Added
CX.12-CX.14 to `TASKS.md` and the CX pivot plan.

## 2026-07-09 · CX.11 slice - Backtest Lab drill-down

Wired the frontend Backtest Lab to the stored backtest detail endpoint. Saved
runs now expand inline from the dashboard, fetch and cache
`GET /api/backtest-runs/{id}`, and show the policy note, verifier status,
research-only warnings, per-observation strategy checks and outcome windows.
The run form also exposes the financial availability policy selector, keeping
strict `scraped_at` as the default while making `estimated_period_lag` an
explicit research-mode choice.

Verified the UI against the local app: the dashboard loaded five saved runs,
expanded run `#7`, displayed `verifier: needs-human`,
`estimated_period_lag · 120d`, four observations, and the missing exact report
timestamp warning. This keeps exploratory backtest results visible without
presenting them as verified prediction evidence.

## 2026-07-09 · CX.11 slice — research-only estimated report availability

Added an explicit financial-availability policy to deterministic backtests.
The default remains strict `scraped_at`, preserving the original point-in-time
guard. New opt-in `estimated_period_lag` treats quarterly financial rows as
available a configurable number of days after quarter end and records the
policy in run parameters, observation `known_inputs.availability`, and summary
data-quality warnings. Estimated-lag runs are marked research-only and persisted
with `verification_status="needs-human"` because they are a proxy, not real
publication timestamps.

Wired the policy through all Codex-facing surfaces: Python service, direct JSON
script (`--financial-availability-policy`, `--report-lag-days`), FastAPI
`POST /api/backtest-runs`, MCP `run_backtest`, and frontend request types.
Updated the backtest skill so future sessions use strict mode by default and
treat estimated-lag runs as exploratory until verifier review.

This unblocks exploratory multi-asset replay on the current local data. A sample
run over `ASB`, `CBF`, `DCR`, and `SNT` for 2026-06-30 with 120-day lag produced
non-empty candidate signals and one-day outcomes, but it remains unsuitable for
verified strategy learning until exact source availability dates and longer
price history are added.

## 2026-07-09 · CX docs compacted + backtest readiness gate

Compacted the CX documentation so each file has one job: `TASKS.md` is the
status board, `docs/plan-stage-codex-pivot.md` is the architecture/path, and
this changelog is the decision digest. The current state is now explicit:
CX.9 is a compatibility runway, not full removal. The active user path is
provider-neutral (`agent_runs`, `analysis_runs`, workflow status, MCP/scripts);
legacy `analyses`/Claude modules remain only until a later sunset/archive gate.

Checked multi-asset backtest feasibility with 5.3 Spark sidecar audits and
local commands. The engine can replay multiple stored tickers today, but the
current local data is not yet suitable for a meaningful historical fundamental
signal: the DB has four companies (`ASB`, `CBF`, `DCR`, `SNT`) and prices from
2026-04-28 to 2026-07-08, while all financial report rows were scraped on
2026-07-09. The point-in-time guard correctly turns pre-scrape observations
into `insufficient_data`; short outcome windows can be measured, but prediction
quality cannot be learned from them yet.

Recorded the next path: add report availability/publication dates or historical
snapshots, expand price history, then run walk-forward backtests and verifier
reviews before changing strategy weights. `gpt-5.3-codex-spark` is suitable for
bounded loops such as candidate scans, repeated backtest runs, doc consistency
passes, and anomaly summaries. Stronger 5.5 supervision remains required for
strategy changes, prediction-quality conclusions, and anything saved as
verified UI-visible investment analysis.

Fixed the Codex JSON script command contract so direct documented commands like
`cd backend && python3 scripts/codex_run_backtest.py ...` work without manually
setting `PYTHONPATH`. Verification: direct candidate scan and direct multi-asset
backtest commands pass; script py-compile passes.

## 2026-07-09 · CX.9 cleanup slice — retire user-facing Claude path

Started CX.9 by removing the active user-facing legacy model-call path while
leaving backend compatibility endpoints in place. The stock Analysis tab now
queues `stock-quick-analysis` through provider-neutral `agent_runs` and renders
only `analysis_runs`; Settings uses `GET /api/diagnostics/workflow-status`
instead of a provider-key status card. Frontend API helpers for the old direct
run/history/status path were removed.

Backtest audit follow-up: `gpt-5.3-codex-spark` verified the CX.8 engine and
flagged one contract issue. MCP `run_backtest` now requires `from_date` and
`to_date`, with a regression assertion in `tests/test_mcp_stock_workbench.py`.
Verification at the time of the slice: full backend `pytest` passed (`313
passed, 6 skipped`), frontend `npm run build` passed, and `git diff --check`
was clean.

## 2026-07-09 · CX.8 complete — deterministic backtest replay + Backtest Lab

Added the first real deterministic backtest engine in `services/backtest.py`.
The engine replays stored companies on a quarterly cadence using only
`ReportValue` rows whose `scraped_at` is on or before each `as_of_date`.
Future prices are attached only under `outcome` windows, never under
`known_inputs` or `signal`. Current mutable company scalar fields such as
`market_cap` are deliberately excluded from historical signal inputs until the
app has a historical source for them.

Updated the Codex-facing contracts: `scripts/codex_run_backtest.py` and MCP
`run_backtest` now call the same deterministic service and persist
`backtest_runs` plus `backtest_observations` instead of returning
`engine-not-implemented`. The MCP schema now accepts ticker scopes and outcome
windows. Added `GET/POST /api/backtest-runs` and `GET /api/backtest-runs/{id}`
so the UI and automations can create and inspect saved replays.

Added a compact dashboard Backtest Lab. It lets the user run `malik_v1` over a
date range and optional ticker, then shows recent run status, observation
counts, and average returns by outcome window. The UI keeps this framed as
deterministic replay output; Codex interpretation and verifier-gated learning
notes remain separate workflow steps.

Verification: `gpt-5.3-codex-spark` explored the existing CX.8 contract and
flagged the exact implementation risks used here: no official publication
timestamps, current-company scalar drift, and tests pinned to the old stub.
Added `tests/test_backtest.py`, including a look-ahead regression where a
future-scraped 2024Q1 financial row is excluded from a 2024-03-31 observation
while future price return is attached only as outcome. Focused regression
`cd backend && pytest tests/test_backtest.py tests/test_agent_runs.py
tests/test_mcp_stock_workbench.py` passes (`17 passed`, one existing
Starlette/httpx deprecation warning); `cd frontend && npm run build` passes;
Python compile check for the backtest service/API/MCP/script passes.

## 2026-07-09 · CX.7 complete — UI workflow queue + Codex result visibility

Added the first UI surface for GPT/Codex-operated workflows. The dashboard now
loads recent `agent_runs`, can queue a `stock-candidate-scout` run, and can
trigger the pre-session flow through `POST /api/agent-runs/pre-session`. That
pre-session endpoint fetches GPW ESPI/EBI reports for the watchlist/ticker and
then queues `stock-pre-session-brief`, making the same path usable from the UI,
n8n, cron, or Codex automation. Generic `POST /api/agent-runs` validates
repo-known workflows and stores model role/orchestrator hints without executing
Codex inside FastAPI.

Updated the stock Analysis tab so provider-neutral Codex `analysis_runs` were
first-class visible results, not only compact audit rows. The tab added a
separate `Queue Codex` action for `stock-quick-analysis`; the temporary legacy
button from this slice was later removed in CX.9. It renders queued/running
`agent_runs`, and shows Codex-saved analysis details with workflow/model role,
verification badge, summary fields, watch items, red flags, data gaps,
verify-next items, verifier notes, and source links when present.

Added a hosted/n8n automation lane to the CX plan: hosted systems should enqueue
durable work through HTTP/API, while Codex consumes the queue through stdio MCP
today and a future bearer-token Streamable HTTP MCP transport after deployment.
This preserves the rule that the backend does not try to use a ChatGPT/Codex
subscription as if it were an API key.

Verification: `gpt-5.3-codex-spark` sidecar verifier reviewed the CX.7 slice
and found the provider-neutral detail/status/doc gaps fixed in this entry.
Focused regression `cd backend && pytest tests/test_agent_runs.py
tests/test_gpw_espi.py tests/test_mcp_stock_workbench.py` passes (`20 passed`,
one existing Starlette/httpx deprecation warning); `cd backend && python3 -m
py_compile app/api/agent_runs.py app/api/schemas.py app/scrapers/espi.py
app/mcp/stock_tools.py app/mcp/stock_workbench_server.py
scripts/codex_pre_session.py scripts/codex_poll_espi.py` passes; `cd frontend
&& npm run build` passes. Local visual verification exposed that the developer
Postgres had not yet applied migration `0003`; running `cd backend && alembic
upgrade head` fixed the missing `agent_runs` table, after which the dashboard
queue panel rendered and a test `Candidate scout` run queued successfully.

## 2026-07-09 · CX.6 complete — GPW ESPI/EBI ingestion + scheduled Codex brief queue

Added the first live ESPI/EBI ingestion slice for GPW. New
`app/scrapers/espi.py` parses GPW's server-rendered `espi-ebi-reports` page,
matches reports to watched companies by normalized issuer/company name, fetches
detail pages only for matching companies, and upserts `event_reports` by stable
external id (`source`, `gpw:{geru_id}`). Stored reports keep raw text, parsed
metadata, source URL, published timestamp, and `materiality.level=unreviewed`;
the scraper deliberately does not decide investment meaning.

Updated `codex_poll_espi.py` and MCP `poll_espi_watchlist` from contract-only
status to live GPW ingestion. Added MCP `get_recent_source_deltas` so Codex can
read durable new event rows when preparing a brief. Added
`codex_pre_session.py` plus MCP `prepare_pre_session_brief`: this is the
scheduling-friendly GPT/Codex surface the user requested. It fetches ESPI/EBI
for the watchlist, then queues a `stock-pre-session-brief` `agent_run` with the
event-poll result in `inputs` so a scheduled or manual Codex run can triage,
verify, and save the actual agenda. `.codex/config.toml` keeps these mutating
fetch/queue tools prompt-approved.

Updated the pre-session skill to prefer MCP/scheduled entrypoints and use
script fallbacks only when MCP is unavailable. This keeps GPT feature
exploration open across scheduled runs, manual chat runs, and later UI-triggered
queues, while preserving the rule that source data lives in the database.

Verification: fixture parser tests cover list and detail pages; ingestion tests
cover watchlist matching, idempotent upsert, ticker-scoped polling, recent
deltas, and the scheduled pre-session queue. Focused regression
`cd backend && pytest tests/test_gpw_espi.py tests/test_mcp_stock_workbench.py
tests/test_agent_runs.py` passes (`18 passed`, one existing Starlette/httpx
deprecation warning).

## 2026-07-09 · CX.5 complete — local Stock Workbench MCP server

Added a dependency-free stdio MCP server for Codex under `backend/app/mcp/`.
The server exposes the first stable Stock Workbench tools: `get_watchlist`,
`get_company_dossier`, `list_queued_agent_runs`, `queue_agent_run`,
`claim_agent_run`, `save_analysis_run`, `mark_verification_result`,
`rank_candidates`, `run_backtest`, and `poll_espi_watchlist`. It speaks
newline-delimited JSON-RPC over stdin/stdout and returns structured JSON, while
keeping ESPI and backtest as honest contract-only tools until CX.6/CX.8.

Added `backend/scripts/stock_workbench_mcp.py` as the entrypoint and
`.codex/config.toml` as the project-scoped Codex config. Read tools are
auto-approved in the config; mutating tools (`queue_agent_run`,
`claim_agent_run`, `save_analysis_run`, `mark_verification_result`) keep prompt
approval. This follows the current Codex manual guidance that trusted
project-scoped `.codex/config.toml` files can define MCP stdio servers and
per-tool approval policy.

Updated all six repo skills to prefer MCP tools first and fall back to the
CX.3 scripts when MCP is unavailable. Regression tests cover tool discovery,
stdio initialize/list behavior, queue/claim flow, `get_company_dossier` through
the same `DossierOut` UI contract as the FastAPI endpoint, `save_analysis_run`
round-tripping into the API, bad-input rejection, and contract-only candidate,
ESPI and backtest tools. The dossier test caught an important bug in the first
pass: raw ORM `Company` objects degraded to strings under generic JSON
serialization, so MCP now serializes through the UI DTO instead.

Verification: `cd backend && pytest tests/test_api_phase1.py
tests/test_api_phase3.py tests/test_mcp_stock_workbench.py
tests/test_agent_runs.py tests/test_migrations.py` passes (`31 passed`, one
existing Starlette/httpx deprecation warning); direct MCP stdio initialize +
`tools/list` returns the expected server info and tools; all six skills pass
the Codex skill validator; `cd frontend && npm run build` passes; `git diff
--check` is clean.

## 2026-07-09 · CX.4 complete — repo-local Codex workflow skills

Added six repo-local Codex skills under `.agents/skills/`: pre-session brief,
quick analysis, deep analysis, candidate scout, backtest review, and strict
verification. The skills encode the Stage-CX operating model directly in the
repo: use app scripts/MCP tools for data access, route bounded work to
`worker_standard`, reserve deeper synthesis for `analyst_deep`, require
`verifier_strict` before UI-approved results, and label gaps instead of
inventing facts.

The skills call the JSON contracts from CX.3 (`codex_get_dossier.py`,
`codex_save_analysis.py`, `codex_poll_espi.py`, `codex_candidate_scan.py`, and
`codex_run_backtest.py`) rather than scraping directly from prompts. Each skill
also has minimal `agents/openai.yaml` metadata so Codex can present the workflow
cleanly. Verification: all six folders pass the Codex skill validator, and
`git diff --check` is clean.

## 2026-07-09 · Project guardrails — explicit anti-slop quality bar

Added `docs/project-guardrails.md` as the durable project-quality contract to
inspect at the start and end of every phase/work package. It records the user's
main requirements for the pivot: evidence-grounded GPW analysis, Codex as the
analyst/operator rather than chat-memory source of truth, precision/risk-first
model routing, verifier-gated UI output, dense analyst-workspace UI, no
fabricated numbers, and no generic feature drift.

Updated `AGENTS.md` so future Codex sessions must read the guardrails, and
updated the CX tasks to make guardrail inspection part of the repo-skill and
phase-exit workflow. This is intentionally short and stable so it can be
re-read often without becoming another large plan document.

## 2026-07-09 · CX.3 complete — Codex JSON script contract

Added the local script layer that Codex skills and the later MCP server will
use before any richer integration exists. New shared helper `scripts/codex_common.py`
keeps the contract consistent: JSON in/out, JSON-safe serialization, DB company
lookup, and non-zero JSON errors for script-level failures.

Implemented five scripts:

- `scripts/codex_get_dossier.py <TICKER>` — reads the deterministic app dossier
  as JSON (`--use-ai-refiners` remains explicit, default is deterministic-only).
- `scripts/codex_save_analysis.py <TICKER> ...` — persists a Codex analysis into
  `analysis_runs`, creating an `agent_runs` row when no `--agent-run-id` is
  supplied. It requires `--workflow`, `--model-role`, `--model`, and
  `--verification-status`, matching the CX role-discipline rule.
- `scripts/codex_poll_espi.py` — stable JSON contract for pre-session ESPI/EBI
  polling; currently reports stored event counts and `source-not-implemented`
  until CX.6 adds the real scraper.
- `scripts/codex_candidate_scan.py` — conservative DB-only candidate scan over
  already-stored companies; no broad crawler, no new HTTP.
- `scripts/codex_run_backtest.py` — validates the backtest request shape and
  returns `engine-not-implemented` until CX.8 builds point-in-time replay.

Tests cover the important path: `codex_save_analysis.py` writes both
`agent_runs` and `analysis_runs`, then the `/analysis-runs` API returns the
saved result; the other contract scripts return structured JSON. Verification:
`cd backend && pytest tests/test_agent_runs.py tests/test_migrations.py` passes
(`5 passed`, one existing Starlette/httpx deprecation warning);
`cd backend && python3 -m py_compile scripts/codex_common.py
scripts/codex_get_dossier.py scripts/codex_save_analysis.py
scripts/codex_poll_espi.py scripts/codex_candidate_scan.py
scripts/codex_run_backtest.py app/db/models.py app/api/agent_runs.py
app/api/schemas.py app/main.py` passes.

## 2026-07-09 · CX.2 complete — provider-neutral Codex run storage + UI read path

Implemented the first executable slice of the Codex pivot: durable storage for
Codex-operated workflows and verified outputs, independent of the old Claude
API route. Added ORM models and Alembic migration `0003_codex_agent_runs.py`
for `agent_runs`, `analysis_runs`, `verification_runs`, `event_reports`,
`candidate_runs`, `backtest_runs`, and `backtest_observations`. The schema
records `workflow`, `model_role`, `model`, `agent_run_id`,
`verification_status`, and `input_snapshot` so future Codex skills/MCP tools can
prove which model role produced a result and whether stronger verification
approved it before the UI shows it.

Added `app/api/agent_runs.py` with read endpoints for the new path:
`GET /api/agent-runs`, `GET /api/companies/{ticker}/analysis-runs`, and
`GET /api/companies/{ticker}/event-reports`. Added Pydantic DTOs and registered
the router in `app/main.py`. The frontend API/types now understand
`AnalysisRun`, and `AnalysisPanel` renders a small provider-neutral "Codex
analysis runs" history when rows exist. This is the new UI-visible target for
Codex-saved analysis; the old Claude route remains only as a later removal task
(`CX.9`), not as the direction of travel.

Tests/verification: `cd backend && pytest tests/test_agent_runs.py
tests/test_migrations.py` passes (`3 passed`, one existing Starlette/httpx
deprecation warning); `cd backend && python3 -m py_compile app/db/models.py
app/api/agent_runs.py app/api/schemas.py app/main.py` passes; `cd frontend &&
npm run build` passes.

## 2026-07-09 · Stage CX planned — Codex as supervised analyst/operator

Planned the committed architecture pivot from a Claude-API analysis backend to a
Codex-centered operating model. Added `docs/plan-stage-codex-pivot.md` with
Mermaid diagrams for the complete flows the user wants to run with Codex as the
brain and facilitator: pre-session brief, quick company analysis, deep company
analysis, candidate scouting, backtest/learning loop, and UI-requested Codex
runs. The core decision is now explicit: the web app and Postgres remain the
durable system of record; Codex uses skills, scripts and MCP tools to read data,
run supervised worker agents, verify their work, and save structured results
that the UI renders.

Model-routing decision: precision beats cost. Routine/simple work uses
`worker_standard` with a model chosen by task risk; lighter models are only for
bounded extraction/formatting or low-risk summaries, while analysis-affecting
work uses a stronger model. Deeper synthesis uses `analyst_deep` and all
UI-visible investment output must pass `verifier_strict` (`gpt-5.5` high by
role). The plan requires every persisted Codex-created row to record
`workflow`, `model_role`, `model`, `agent_run_id`, and `verification_status`,
so the app can audit whether the chosen model was appropriate and whether
stronger supervision happened before a result became visible.

`TASKS.md` gained the initial Stage CX (`CX.1`-`CX.9`) plan. Later entries extend
that sequence with the provider sunset and backtest data-readiness gates. No
code, schema, config, or scraper behavior changed in this entry.

## 2026-07-09 · Investor workflow pivot — decision memo on the stock Brief tab

Started the product pivot from "analysis presentation" toward "investor
decision support" with a frontend-only first slice. The stock Brief tab now
includes an **Investor Memo** composed from the existing dossier, thesis,
scenario, valuation, forum-intelligence, and AI-readiness blocks. It derives a
working status (`Kandydat do decyzji` / `Obserwuj aktywnie` / `Odrzuć lub
czekaj` / `Research niepełny`), a research-readiness score, downside-first
scenario read, top decision blockers, catalyst verification hints, and
source/provenance trust tiles. The watchlist also gains a **Scaling radar** that
ranks loaded companies by the pattern from successful scaling-business
investments: revenue acceleration, gross-margin quality, clean earnings,
valuation room, smaller/less-saturated size, forum context, and AI data
readiness. A **BiznesRadar discovery** checklist now sits under the radar with
the exact manual filters to use before adding a ticker: revenue scale, margin
quality, clean result, still-reasonable valuation, and size sweet spot.

Decision: keep this first pivot slice read-only and schema-free. No scraper,
database, prompt, or API contract changed; the memo is a UX composition layer
over already computed data so it can ship safely before deeper workflow storage
(persistent checklist statuses, position sizing, thesis invalidation events)
lands. The memo keeps the not-a-recommendation framing: it chooses the next
research step, not a buy/sell signal. Decision: keep the first BiznesRadar
discovery step manual in the UI instead of adding an untested broad crawler;
the next backend/source step is a fixture-tested BR screener using explicit
filters for scaling businesses, with all HTTP still routed through
`scrapers/http.py` and results flowing into the same scaling-score model before
any company is promoted to the watchlist.
## 2026-07-09 · RT3.0 / RT4.5–RT4.7 — market discovery + workflow-first UI overhaul

Redefined the product around one investor workflow instead of exposing every
implementation concept as a peer. Three independent delegated audits reviewed
the live desktop/mobile app from investor-workflow, content-architecture and
visual-system perspectives. Their shared finding was duplication, not merely a
palette problem: the old Brief repeated thesis, metrics and scenarios while the
AI tab produced a second report; the watchlist ranked partial checklist and
forum-volume concepts beside fragile scenario upside. The new binding design is
`docs/design/research-workspace.md`.

Added the first real `Discover -> Research` funnel. `GET /api/discovery` makes
one polite, cache-aware BiznesRadar request to the GPW rating universe, stores
the immutable raw response in the evidence ledger, parses report period,
financial-condition rating/Altman EM-Score and Piotroski F-Score, and filters/
sorts locally. Missing F-Score is never coerced to zero and fails a minimum
filter. The source score is explicitly preliminary evidence, never the
Malik/OBS score or a recommendation. A live-shape discrepancy (`AAA ( 8,6 )`
produced by nested spans) was diagnosed from the already-preserved raw version,
fixed only in the BiznesRadar parser, and added to the fixture test. The live
page yields 384 candidates without per-company scraping.

Replaced the dense Watchlist table with a Research queue showing one workflow
state, two signals, one risk/gap, one next action and freshness. Removed
watchlist scenario upside, "best match" and forum/AI-volume cards. Global
navigation is now Discover, Research and System. Candidate presets disclose
their exact source thresholds and `Rozpocznij analizę` hands a ticker into the
existing watchlist/dossier workflow.

Rebuilt the company workspace as Brief, Evidence, Financials, Scenarios and
Review. Brief has one canonical read, four key figures, at most four signals,
two arguments per side and two next checks; it no longer renders the full
scenario engine. Scenarios owns the current forecast/valuation output and warns
that bear/base/bull is a multiple sensitivity, not yet an operating-driver
simulation. Review is exception-first and collapses the full legacy generated
record/history. Raw statements default to the newest eight periods, with
explicit full-history expansion inside a contained scroller.

Raised tertiary-text contrast, body size and canvas width; removed card nesting
from the new workflow surfaces; made mobile navigation horizontal and preserved
non-colour status labels. TypeScript and the production Next build pass. Manual
in-app browser QA at 1280 px and 390 px exercised Discover, Research and every
SNT workflow tab. It caught and fixed document-level financial-table overflow;
the final tested views have no horizontal page overflow. The full backend suite
is green (with only the explicitly skipped external/provider cases), alongside
the focused discovery/evidence/migration tests.

**Scope boundary:** this is the first vertical slice, not premature completion
of RT.4. Persistent ResearchCase/Monitor/Journal, source locator drawer,
template-specific discovery fields, scenario matrix/driver bridge and the
seasoned-investor judge/evaluation loop remain on RT.3–RT.6. Model routing still
cannot claim GPT-5.3 until the OpenAI adapter exposes a selectable configured
model; `ModelPolicy` retains GPT-5.3 as the bounded cheap-loop candidate with
deterministic validators and escalation.

---

## 2026-07-09 · RT.0–RT.1 implementation — reproducible local app + explicit analysis runs

Restored a green, reproducible baseline and implemented the first trust boundary
from the research-platform roadmap. Backend fixture assertions now match their
recorded BiznesRadar price while the time-sensitive stale-data test freezes its
clock. The full backend suite is green. The frontend now reproduces with
`npm ci`, builds in production mode, and pins a non-vulnerable PostCSS through
the lockfile override; `npm audit --audit-level=moderate` reports no findings.

Added the root `./workbench` operator contract with read-only `doctor`,
idempotent `start`, owned-process `status` and `stop`. It can start Docker
Desktop/Postgres, runs Alembic, waits for backend/frontend health, stores only
gitignored PID/log state, never prints credentials and leaves Postgres intact
on stop. README and agent instructions now use this path. A browser pilot
opened the watchlist, SNT research page and Settings with no console errors;
it also confirmed that the existing repeated thesis cards and generic fixed
multiple scenarios belong in the planned RT.4 workflow/UI overhaul rather than
being polished in place.

Created and validated `skills/workbench-research/SKILL.md` for repeatable Codex
app operation and research facilitation. A separate forward test exercised its
commands successfully. The skill deliberately documents only commands that
exist; evidence-extraction, scenario-review and seasoned-investor-judge become
separate skills only after their data contracts and gold cases stabilize.

Removed all optional AI refiners from dossier GET assembly: thesis, scenarios
and valuation reads are deterministic and a regression test makes any hidden
provider call fail. Added strict/no-coercion Pydantic verdict contracts with
stable checklist ids, forced expected-tool validation, cache revalidation and
a cache schema version. Strategy alignment arithmetic now lives in a pure
server scorer: unknowns leave the denominator, duplicates cannot double-count,
rounding is explicit, the deterministic profit-quality and loss/net-debt vetoes
apply, and missing catalysts cap the result. Provider-proposed scores are kept
only as input and overwritten in both the persisted output and top-level field.

Migration `0005` extends the current `analyses` table with purpose/status/
`as_of`, frozen full prompt snapshot, evidence ids, skill hash/version,
provider/model configuration, validation, latency/cost/error/completion and
user provenance, and creates child `model_calls`. It deliberately preserves a
separate experimental `analysis_runs`/judge/backtest schema found in the local
pilot DB but absent from this worktree's Alembic history; RT1.3 must reconcile
those contracts instead of overwriting either. A run is committed before
provider work, then finalized as succeeded or failed; successful history hides
failed attempts while those attempts remain auditable. Current scope records
the main verdict call. Per-retry/forum-distillation rows, durable idempotency,
price-based cost and async cancellation remain explicitly in RT1.3/RT1.6.

**Observed external gap:** local stored source health reports eight recent
BiznesRadar failures and no PortalAnaliz failures. No live credential/model
calls were made during diagnostics. RT0.3 remains open for real login/upvote
fixtures and a full live refresh pilot.

**Follow-up diagnosis:** the eight BR failures were the old `/DEC` ticker URLs
from before slug resolution; `/DECORA` succeeded minutes later and subsequent
watchlist companies are healthy. Source diagnostics now distinguish
`healthy`, `recovered`, `degraded` and `unknown`: recovered errors stay visible
as 24-hour history but no longer produce a false active-warning state in
`./workbench doctor` or Settings. This changes presentation only and makes no
new external requests.

**Real-fixture hardening (RT0.3 preparation).** The old BR recorder overwrote
its previous company and built report URLs directly from the ticker—the exact
redirect trap in the quirks ledger. It now fetches the profile first, requires
the canonical slug, optionally verifies the declared market, and writes all
nine page types under `tests/fixtures/real/br/{TICKER}/`. Structural tests
discover every recorded company and cover report, profile, dividend and price
parsers. PortalAnaliz recording now writes `real/pa/topic.html`, which is
actually consumed by a test requiring recognized real vote markup. No real
pages were captured in this change; RT0.3 remains open until one verified GPW
and one verified NewConnect company, the logged-out/login smoke and a voted PA
topic are recorded without committing credentials or cookies.

**RT1.3 explicit execution boundary.** The verdict POST no longer owns prompt,
retry, provider and persistence policy inside the FastAPI route. It now calls a
single analysis orchestrator, which delegates one-attempt HTTP work to a narrow
`AnthropicProvider` through an audited executor. Migration `0006` adds scoped
idempotency hashes, run heartbeats and per-attempt operation/contract/output/
provider/cache/billing fields. Repeating an `Idempotency-Key` returns the same
run; a deliberate new run may reuse a strictly revalidated durable response and
records a non-billable `cached` call referencing its source. Transport retries
produce separate ordered rows, while missing configuration, transport failure
and invalid structured output remain distinct error codes instead of all being
reported as a missing key.

The production orchestrator bypasses the legacy file cache. It also temporarily
uses the deterministic token-capped raw-forum path, visibly labelled as
unverified opinions, rather than allowing up to 40 untracked distillation model
calls. The parent validation trace records this limitation. Forum distillation
must migrate through the same executor before it is re-enabled; atomic billable
quota/cost reservations, stale-run recovery and async cancellation remain
RT1.6 work. The compatibility `claude_client.run_analysis` and its file cache
remain only for existing isolated callers/tests during migration.

**Browser-found Settings correction.** Optional BR/PA credentials that are
absent now return and render a neutral `not_configured` state instead of a red
login error. Actual configured-login failures remain red. This keeps setup
gaps distinct from operational failures while leaving the broader RT.4 UI/UX
overhaul in its planned sequence.

**RT1.6 atomic usage and recovery guard.** Migration `0007` adds a UTC-day
usage ledger. A global row atomically reserves logical runs and actual provider
attempts, while provider rows record logical operations, retries, cache hits,
billable calls, unknown-billing failures and measured input/output tokens.
`AI_DAILY_LIMIT`, `AI_DAILY_CALL_LIMIT` and `AI_DAILY_TOKEN_LIMIT` are separate
ceilings; retries consume attempts, cache hits and missing configuration do not,
and a configured zero now intentionally disables that budget instead of falling
back to 20. Monetary cost remains zero/unpriced until RT5 `ModelPolicy` can
snapshot an evaluated model id and price table—tokens are not converted using
guessed or stale prices.

Provider stop outcomes now distinguish completed, truncated and refused before
contract parsing; invalid structured output remains separate. The official SDK
adapter has an explicit 90-second timeout. Runs/calls whose heartbeat exceeds
the conservative 15-minute window are conditionally claimed once, marked
`stale_interrupted`, and outstanding call billing is recorded as unknown. This
reconciliation runs before new work and is idempotent under competing workers;
successful history remains terminal-success only.

Settings now exposes this ledger read-only: daily run/attempt/token ceilings,
cache and billable counts, and unknown-billing failures. It explicitly states
that monetary pricing is not configured, so a token count is never presented as
a fabricated cost estimate.

**RT2 immutable evidence slice.** Migration `0008` adds stable source-document
identity, immutable raw document versions, typed facts, events and explicit
data-conflict contracts. Immutable rows carry a ticker snapshot and nullable
company link so removing a watchlist item cannot erase the audit trail. Fetch
logs can point to retained versions; new report/indicator serving rows point to
their exact source fact, while legacy rows remain null rather than receiving
fabricated lineage.

Fresh BiznesRadar report and indicator pages are stored before parsing with
requested/effective URL, byte hash, MIME type, parser version and parse result.
Identical forced refreshes reuse the version/facts; changed pages append a new
version and advance current serving pointers; malformed changed pages remain as
failed evidence but cannot blank good current rows. For this mutable aggregator,
`known_at` is the first observed fetch time—not a historical publication label
shown today—preventing corrections from leaking backward into backtests.

Read-only document/fact/conflict APIs support point-in-time selection by taking
the latest complete parsed version of each logical document at `as_of`. This
also treats a row omitted from a later full version as superseded instead of
silently reviving an old fact. Cross-document disagreements create an open
conflict record; same-document version changes are treated as corrections.
Tests cover raw retention, serving lineage, identical/changed/failed pages,
historical `as_of`, conflict idempotency and evidence survival after watchlist
removal. Profile/dividend/price lineage and official issuer/ESPI events follow
on this same contract.

## 2026-07-09 · Top-down roadmap reset — evidence-first research platform + judge loop

Audited the implemented backend/frontend/AI path against the desired product:
a comprehensive, company-specific fundamental-research workflow that can be
facilitated from a Codex task and eventually evaluated historically. Added the
binding target plan `docs/plan-research-platform.md`, revised PLAN/TASKS and
updated the agent read-on-demand index. No application behavior/schema changed
in this planning task.

**Evidence from the audit.** The first vertical slice is substantial (polite
scrapers, canonical fields, pure metrics/forecast/thesis logic, usable stock
workspace, versioned Malik skill, structured AI history), but the next step
cannot honestly be deployment or backtesting. Full `pytest -q` currently has
two drift failures (fixture price date and forward C/Z); frontend build cannot
run in this worktree until dependencies are installed. Refresh may
delete/replace report rows; there is no immutable source-document/publication
lineage or `as_of` reconstruction. Prompt snapshots are assembled but not
persisted. `build_dossier()` may trigger three hidden Claude refiners per stock
when a key is configured, outside the explicit analysis quota/run history.
Transports/caches/contracts are duplicated, the model emits the strategy score,
and the current “scenarios” are fixed-probability own-multiple sensitivities
with constant earnings rather than company operating-driver scenarios.

**Direction/sequence.** New stages RT.0–RT.7 replace “deploy next”: restore a
green/reproducible baseline; make reads deterministic and AI runs explicit with
full provenance; add immutable evidence/facts/events and issuer/ESPI/EBI
sources; deepen cash-flow/working-capital/capex/dilution metrics and introduce
company templates; build operating-driver scenario v2 + a durable research
case; add an OpenAI Responses API adapter, role-based cheap/strong model routing
and a stable `workbench` CLI/repository skill for Codex; then run calibration,
judge evaluation and point-in-time replay before deploy/auth/backups. The old
claim that the existing DB is already backtest-ready was removed: publication
times, revisions, corporate actions, delistings, total-return outcomes and
frozen input/strategy versions are prerequisites.

**AI correctness/cost decision.** Low-cost models handle extraction,
classification and narration through bounded retries over only failed fields.
Deterministic schema/unit/period/arithmetic/citation checks run first; material
unresolved conflicts escalate to a stronger model or human. All authoritative
financial math and strategy scores stay deterministic. Model configuration is
by role, not one hard-coded “latest” model. OpenAI's Responses API is the target
for versioned skills, strict structured outputs, background runs and eval
traces; the existing Anthropic path becomes a temporary adapter during
migration.

**User-added final gate: seasoned-investor judge.** RT.6 now includes an
isolated evaluator that launches the application, waits for health, seeds a
frozen historical/current case, drives the public CLI/API plus a small
Playwright path, runs the cheaper-model scenario workflow and captures its full
trace. A separate strong judge, instructed as a seasoned fundamental investor
and stock-data expert, grades source/accounting correctness, company-template
choice, thesis/counter-thesis/falsifiers, scenario coherence, uncertainty,
specificity, missing-evidence detection, usability, cost and latency. It emits
failure labels and improvement proposals; candidates run on calibration and
untouched holdout cases. The judge never mutates production directly — model,
prompt, template or validator promotion requires regression/cost evidence and
explicit user approval.

**Current official-capability check.** OpenAI documentation reviewed during the
audit supports versioned Agent Skills, Structured Outputs, background Responses
and trace/dataset evals. Current model guidance names a flagship model for
complex work and smaller mini/nano variants for cost/latency; exact model ids
remain configuration/eval decisions. Batch is reserved for non-urgent larger
evals/backtests (official docs currently describe lower cost with a 24-hour
completion window).
## 2026-07-08 · Analyst workspace overhaul — load-on-add, source cleanup, useful summaries

Turned the app toward a decision-first analyst workflow instead of a raw data
dump. The watchlist now shows a useful stock summary: data readiness, best
strategy fit, forum/AI context, current thesis/read, top risk, valuation setup,
operating trend, and freshness. On mobile those rows become stacked cards so the
dashboard does not depend on horizontal scrolling; horizontal scroll remains
reserved for raw statement tables in the Data tab.

Stock pages now open on **Brief**, then **Interpretacja AI**, **Fundamenty**,
**Wycena**, and **Dane**. Newly-added tickers immediately force-refresh after
creation, and shell company pages self-start a first refresh rather than showing
blank analytics as if they were meaningful. The old tab soup is collapsed into
decision, interpretation, evidence, valuation, and source-data areas.

Backend data trust changes: watchlist delete is now a hard delete for the
company-owned analytics (company, analyses, forecasts, prices, dividends,
indicators, reports) while preserving forum topics/posts as detached source
archive. Yahoo and stooq were removed from the live price refresh path and from
the scraper modules/tests; prices now use BiznesRadar history, falling back to
the already-fetched profile quote. BiznesRadar login now reads the form action
and field names from markup instead of assuming fixed `login/password` names.
Settings exposes BiznesRadar login diagnostics. Normal stock refresh reloads
only recent pages from already-linked PortalAnaliz topics, respecting cache
freshness, so forum context feeds AI without crawling stale thread history.

Validation: `frontend npm run build` is green; backend slice
`pytest tests/test_api_phase1.py tests/test_refresh_prices.py tests/test_forum.py
tests/test_br_login.py` is green (28 passed, one upstream TestClient warning).
Future source candidates researched but not wired: GPW has official market-data
pages/services, while EODHD exposes historical EOD/fundamental APIs and supported
exchange/ticker-list endpoints; these should be evaluated as paid/API-key
integrations before adding another live source.

## 2026-07-08 · Frontend UX merge — decision workspace direction

Merged the Codex frontend refresh into the project repo and set the next product
direction: the stock page should read as an analyst workspace, not a dump of
every scraped field. The UI now prioritizes thesis, valuation/scenarios,
evidence, and drill-down tabs; wide financial tables scroll inside their own
container instead of stretching the whole page; stock pages keep Watchlist nav
context; and the AI-analysis action opens the dedicated tab instead of making a
daily-capped call from the header.

Follow-up focus from user feedback: make deletion hard/truthful because stale
company data survives watchlist removal; make newly-added tickers show an honest
"needs refresh/no dossier yet" state instead of misleading blanks; expose API-key
diagnostics for AI analysis; and continue reorganizing collected data into
decision-oriented groups.

## 2026-07-08 · Skill broadened — combined multi-practitioner factor lens (Areczeks + Elendix)

`skill/SKILL.md` gains a **"Broader factor lens — complementary GPW
practitioners"** section, distilled from two PortalAnaliz portfolio threads
(Areczeks t=575; Elendix "Inwestowanie w szanse" t=356), read via the logged-in
browser (sandbox egress to portalanaliz.pl is proxy-blocked, so web_fetch/the
scrapers couldn't reach them; the Chrome extension could). Goal per user: make
the analysis weigh *many* factors, not Malik's alone.

- **Design decision — Malik stays the scoring spine.** The new factors enrich
  `checklist` / `catalysts` / `red_flags` / `verify_next`; `alignment_score`
  stays anchored to the computable Malik factors + `rubric.md`. Any added factor
  the dossier can't compute is `nieznane` (drops out of the denominator per the
  unknown≠fail rule), never a failure — so the lens widens the narrative and
  makes gaps explicit without loosening the number. Frontmatter + intro updated
  to say so.
- **Factors added:** a multiple set beyond C/Z (EV/EBITDA, ROE, C/WK, płynność,
  zadłużenie, 5-yr CAPE, PEG<1, C/P & "cena za aktywnego klienta", EV adjusted
  for held stakes/cash); net-cash-vs-cap deep value + Lynch no-debt guard;
  one-off normalization; capital-return policy (buyback+dividend) as a quality
  signal; insider / major-shareholder cost-basis anchoring. New catalyst types
  (policy/macro programmes, regulatory/trade events, launch event-modelling that
  maps onto the `scenarios` block, contrarian "o spółce jest cicho" low-attention
  signal). Sharper red flags (insider selling while claiming long-term; negative-
  surprise management kept small even when cheap; political/regulatory overhang;
  paying up for growth vs a cheaper peer; retail hype/extrapolated targets;
  behavioural bias / "miłość do spółki"). Portfolio/behavioural discipline (ride-
  winners vs sell-half-at-+100%; ≤20–25% position caps; 10–15% cash reserve;
  benchmark-vs-sWIG80TR honesty) — flagged portfolio-level → `verify_next`, never
  the per-stock score. Faithful short Polish quotes retained for citation.
- **Caveat / follow-up:** the Elendix thread capture covered only its most recent
  page (~6 weeks of a 374-post thread); Areczeks ~84%. The factor set is
  representative but Elendix's full history (position-sizing evolution etc.) is
  not yet mined — offer to fetch earlier pages if deeper coverage is wanted.
  Sources are opinion threads, cited as such; `docs/strategy-malik.md` remains
  the primary source-cited spec and wins on any conflict.

## 2026-07-08 · P5.7 Analiza AI tab + P5.9 forum distiller (Phase 5 nears complete)

**P5.7 — Analiza AI tab (frontend).** Wired the AI-analysis tab into the stock
page: new `AnalysisPanel` (run button → `runAnalysis`; loads history on mount;
verdict card with tone-coloured alignment_score headline, thesis, catalizatory,
checklist with spełnia/nie spełnia/nieznane icons, red flags, one-off risk,
potencjał, forum insights labelled "opinie nie fakty", verify_next, summary_pl,
disclaimer; history table with **score-delta + per-item checklist-change diff**
vs the previous run). `Analysis`/`AnalysisVerdict` types mirror backend
`AnalysisOut` + the `zapisz_analize` tool schema; `api.ts` gains `runAnalysis`/
`listAnalyses` through the same `/api/...` proxy; 429/503 render the backend's
Polish `detail` in `.error-box` (503 reads as intentional config state). New
`.analysis` SCSS scope follows the self-contained `.thesis`/`.scenarios` card
convention (colours all `--text-*`). Header Sparkles button now **switches to
the tab** rather than auto-running, so the daily-capped AI call stays an
explicit action. Added `"AI analysis"` to `TABS`, removed the disabled
placeholder. `tsc --noEmit` exit 0.

**P5.9 — Forum distiller (backend).** `services/forum_distiller.py`: a
cheap-model classification/claim-extraction pass over posts **already synced in
the DB** (zero new forum HTTP). Each post → {fact-claim|opinion|question|noise}
+ extracted claims with confidence, **cached per post** (file cache
`backend/.cache/forum_claims/`, keyed post-id+content-hash+model — no
migration). `distill_company_posts` merges into a deduplicated (union of
source_post_ids), upvote-weighted (reuses `forum.py sort=top` ordering),
budget-truncated `DistilledClaim` list. No key / any failure degrades a post to
an empty distillation — never raises, so the verdict run always completes.
`config.py` gains `ai_distill_model` (default `claude-haiku-4-5`, cheaper than
the verdict model). `prompts.build_analysis_prompt` gains an optional keyword
`forum_claims` (preferred path — claims labelled confidence + source post ids,
marked "opinie nie fakty"); `forum_posts` stays as a backward-compatible legacy
fallback, so `test_analysis_ai.py` is unchanged and green. `api/analyses.py`
distils fetched posts before building the prompt — the verdict never sees raw
post text as fact. `tests/test_forum_distiller.py` 15 pure tests green;
`test_analysis_ai.py` 17/17 still green (no regression).

## 2026-07-08 · Phase 5 wired — Claude client, prompt assembly, analysis endpoints (P5.4–P5.6)

Module D goes from reviewable skill docs (P5.1–P5.3) to an actually-callable
analysis pipeline: dossier + forum → prompt → forced-tool-use Claude verdict →
persisted `Analysis` row, behind a global daily cap.

- **`services/claude_client.py` (P5.4).** `run_analysis()` — its own transport
  (SDK-or-urllib, same dual-path shape as `thesis_ai.default_transport`) but
  forcing structured output via `tool_choice` on a `zapisz_analize` tool whose
  `input_schema` mirrors the PLAN §8 verdict shape exactly. Bounded retry (3
  attempts); best-effort response cache under `backend/.cache/analysis/` keyed
  by ticker+prompt-hash+model. Unlike `thesis_ai`/`scenarios_ai`/
  `valuation_ai`, there is no deterministic verdict to fall back to — no key,
  exhausted retries, or an unparsable response all raise `AnalysisUnavailable`
  rather than fabricate output; `anthropic`/`pydantic_settings` stay
  import-lazy (verified in a fresh subprocess).
- **`services/prompts.py` (P5.5).** `build_analysis_prompt()` assembles
  `system` = `skill/SKILL.md` + `skill/rubric.md`; `user` = a deterministic
  (sorted-key) pretty-JSON slice of the dossier's decision-relevant fields
  (prescore/ttm/pe_history/net_cash/insights/thesis/scenarios/valuation/
  latest_forecast) + recent forum posts newest-first, explicitly labelled as
  unverified opinions, capped at ~30k chars with a truncation marker. Returns a
  `snapshot` of exactly what was sent.
- **`api/analyses.py` (P5.6).** `POST /api/companies/{ticker}/analyses`:
  404 unknown ticker → global daily cap (`settings.ai_daily_limit`, 429 Polish
  message) → dossier + up to 40 recent forum posts → prompt →
  `claude_client.run_analysis` → 503 ("Analiza AI wymaga skonfigurowania
  ANTHROPIC_API_KEY.") on `AnalysisUnavailable` → persists an `Analysis` row
  (model, prescore, output=verdict, alignment_score, tokens, created_by).
  `GET .../analyses` returns history newest-first. Registered in `app/main.py`;
  `AnalysisOut` DTO added to `api/schemas.py` (permissive `output: dict`).
- **Decision: no new migration.** `alembic/versions/0001_initial.py` already
  creates the `analyses` table matching the `Analysis` model column-for-column
  (added ahead of schedule with the model) — confirmed by hand diff;
  `alembic upgrade head` stays at `0004`, `test_migrations.py` needs no change.
- **Tests: `tests/test_analysis_ai.py`** — 17 pure tests pass under bare
  `PYTHONPATH=. python3 tests/test_analysis_ai.py` (import hygiene via
  subprocess isolation, deterministic prompt assembly incl. dossier-key
  filtering / forum ordering / truncation, forced tool-use parsing + token
  extraction, no-key & malformed-response `AnalysisUnavailable`, retry-then-
  succeed & retry-exhausted, cache hit/skip); 4 client-gated tests (happy
  path / 503 / 429 / 404) deferred to `pytest` on the user's machine.
- **Known gap:** the `Analysis` table has no column for the prompt `snapshot`
  (only prescore/output/token counts per the existing model) — reproducibility
  data is available at call time but not persisted; a future migration could
  add it if cross-run diffing becomes a real workflow.

## 2026-07-08 · P1.9 BiznesRadar premium session — scaffolded (real login deferred)

Plumbing for an optional logged-in BiznesRadar session (premium = longer report
/ price history), built without hard-depending on it — anonymous refresh is
byte-for-byte unchanged when no credentials are set.

- **`scrapers/biznesradar.py`** — added `BrLoginError`, `extract_login_fields()`,
  `_looks_logged_in()`, and `class BrClient` (a `requests.Session` wrapper
  mirroring `portalanaliz.ForumClient`), all HTTP via
  `http.fetch(..., session=self.session)`.
- **`config.py`** — added `br_username` / `br_password`.
- **`services/refresh.py`** — `_build_br_session(summary)` logs in only when
  creds are configured and **never aborts** on failure (sets
  `summary["br_login"]` = ok/error/"pominięto (brak danych logowania)" and
  continues anonymously); an optional `session` param is threaded through
  `_get_page` / `_refresh_profile|_reports|_indicators|_dividends` /
  `_fetch_br_history` / `_refresh_prices`. `check_br_login()` diagnostics mirror
  the forum login-status.
- **`api/diagnostics.py`** — `GET /api/diagnostics/br-login-status` (deliberately
  under diagnostics, not `/companies/...`, to avoid being swallowed by
  `GET /companies/{ticker}`). `.env.example` activates `BR_USERNAME/BR_PASSWORD`;
  `conftest.py` neutralises them so a real local `.env` can't trigger a live
  login in tests.
- **Test:** `tests/test_br_login.py` + synthetic `tests/fixtures/br_login.html`
  (clearly marked synthetic). `extract_login_fields`, login success (exact
  payload/URL), and failure paths verified by replaying the assertions directly
  (needs-only requests+bs4); endpoint test + full suite need the user's venv.
- **UNVERIFIED — deferred to the user's machine.** BiznesRadar's real login-page
  markup was unreachable in the sandbox (egress blocked), so
  `extract_login_fields` / `BrClient.LOGIN_PATH` (`/logowanie`) / field names /
  success-check are best-effort guesses tested only against the synthetic
  fixture. On login failure `BrClient` raises (safe: refresh degrades to
  anonymous) rather than silently mis-scraping. Next: record a real BR login
  page, correct the parser, and confirm one real login. P1.9 stays **scaffolded,
  not done**.

## 2026-07-08 · Phase 5 started — strategy skill authored (P5.1–P5.3), pre-wiring review gate

The reviewable half of Module D: the plain-markdown strategy skill that becomes
the Module D analysis system prompt. Authored from the source-cited spec
(`docs/strategy-malik.md`) + a fresh mining pass over `obs.txt` /
`Filozofia_…OBS_Portfel_IKE.md` for real worked cases. **Not wired into any
code path yet** — P5.1 mandates "review together before wiring", so
`claude_client.py`/`prompts.py`/endpoints/tab (P5.4–P5.7) are deliberately not
started.

- **`skill/SKILL.md` (P5.1).** Analyst instructions: three load-bearing ideas
  (stock-picking not timing; sprawozdania/P&L-first with marża brutto + dźwignia
  operacyjna as the motors; teza-first + catalyst + quarterly re-verify); the
  small-cap edge; a compiled "7 golden rules"; the 16-principle checklist mapped
  to concrete dossier fields **or** labelled gaps; a catalyst taxonomy
  (operational / order-book / cyclical / capital-structure / corporate-event +
  a priced-in test); one-off-vs-sustainable guidance; red flags; the valuation
  doctrine (forward C/Z < 0.85× own median, margin-of-safety trio); the
  entry-quality reference mirroring the deterministic engine; the six
  never-fabricate gaps → `verify_next`; forum-claims-are-opinions rule; and the
  PLAN §8 output contract. Domain terms Polish, `summary_pl` Polish.
- **`skill/rubric.md` (P5.2).** Weighted 0–100 score with the load-bearing
  **"unknown ≠ fail"** rule: items are spełnia/nie spełnia/**nieznane**, and
  `nieznane` items are dropped from the denominator (never scored 0) so our data
  gaps don't sink every company. Weights follow Malik's priorities (margin trend
  15, valuation-vs-own-history 15, revenue 12, op-leverage 12, profit-quality
  12, catalyst 10, …). Vetoes/caps: one-off-profit veto (cap 50), net-loss+net-
  debt veto (cap 40), no-catalyst cap (75, encoding "cheap ≠ sufficient");
  < 3 computable indicators ⇒ `insufficient_data`, no number. Bands + an
  explicit "stay consistent with the engine's `entry_quality`" clause.
- **`skill/examples/` (P5.3).** Three real cases as few-shot verdict shapes,
  incl. **one documented miss** so the model learns the failure mode:
  `optex.md` (cheap forward C/Z + quantified backlog catalyst + sell-when-
  catalyst-stops → +100%/6mo), `toya.md` (durable discount + buyback as active
  catalyst; forward C/Z 10 ⇒ ~950 mln vs ~733 mln cap), `suntech.md` (narrative
  "new contracts" catalyst that kept failing, held via rationalisation — Malik's
  own confessed *"samousprawiedliwienie błędnych decyzji"*), + a README.
- Scope: docs/skill only, no code, no schema, no HTTP. Next (after review):
  P5.4 `claude_client.py` reuses the TH.2b `thesis_ai` transport/cache; P5.5
  `prompts.py`; P5.6 endpoints + `analyses` table + `AI_DAILY_LIMIT`; P5.7
  Analiza AI tab.

## 2026-07-08 · Fix 4 pre-existing DB/API test failures surfaced by first full `pytest` run

The Stage-UX/SC work was verified in-sandbox with a pytest *shim* (no PyPI/DB);
the first real `cd backend && pytest` on the user's machine (204 passed / 6
skipped) surfaced 4 failures — none a product regression, both classes
pre-existing and only reachable with the real DB/TestClient the sandbox lacks.

- **`test_api_phase1.py::test_force_refresh_replaces_stale_periods` — stale
  assertion, not a regression.** It asserted the refresh summary
  `.startswith("ok (99 values)")` with a closing paren, but `refresh.py:372/344`
  intentionally enriches the summary with table detail — `ok (99 values; 11
  rows × 9 periods; 2023Q1–2025Q1)` — so the `)` stopped matching. The
  enrichment is the current, intended behaviour (`_table_detail`); the test
  predates it. Fixed by matching the stable prefix `"ok (99 values"` (still
  catches a DB error or wrong count).
- **`test_module_imports_without_pypi` in test_thesis_ai / test_scenarios_ai /
  test_valuation_ai — test-isolation bug, not a broken lazy-import.** Each
  asserted `"pydantic_settings" not in sys.modules`. The lazy-import property
  is real (the modules don't import it at top level; the tests pass in
  isolation), but under the *full* suite an earlier test imports `app.config`
  (which does `from pydantic_settings import BaseSettings`), leaving it in the
  shared `sys.modules` — so the in-process assertion was order-dependent.
  Fixed by probing in a **fresh subprocess** (`python -c "import
  app.services.<mod>; assert 'pydantic_settings' not in sys.modules"`,
  cwd=backend), which actually enforces "importing *us* pulls neither dep"
  regardless of suite order — and still fails loudly if someone adds an eager
  `import pydantic_settings`/`anthropic` to the module. `anthropic` assertion
  unchanged (it was never installed, so never polluted).
- Scope: 4 test files only, no product code touched; `py_compile` green on all
  four. Re-run `cd backend && pytest` to confirm 208 passed / 6 skipped.

## 2026-07-08 · UX/UI pass over the whole flow + two pl-PL cosmetics fixed at root (Stage UX, Part A)

Frontend readability/hierarchy pass with the new thesis + scenario features,
plus the two long-flagged cosmetic bugs fixed **at their backend source** (not
patched in the UI). No architecture change; the plan-fixed Overview order
(MetricCards → Teza → Scenariusze → Analiza → Prescore → Kurs) is kept.

**Backend root-cause fixes (services layer, pure fns — tests stay green):**
- **`strategies/malik.py` — "Mała spółka (Mała spółka)" duplication.**
  `size_pro_text`/`size_con_text` hardcoded the size-class word *and* injected
  `{size}` (the company's size label), so a small cap rendered "Mała spółka
  (Mała spółka) — sweet spot…" and a moloch "Duża spółka (Duża spółka) — …";
  micro/mid were even wronger ("Mała spółka (Mikro spółka)", "Duża spółka
  (Średnia spółka)"). Fix: drop the hardcoded word, let `{size}` carry the real
  label once, and reword the con size-agnostically ("większe spółki są lepiej
  pokryte…") so **all four** sweet-spot/penalised sizes read correctly.
  `base.py` docstring gained a one-line "don't repeat the class word" guard.
- **pl-PL decimal comma unified everywhere numbers are displayed** (the "+1.8"
  vs "+1,8 p.p." bug). Root cause: `insights.py` printed the margin-trend p.p.
  in the *comment* with `:+.1f` (dot) while the *summary brief* used
  `.replace(".", ",")` (comma) — the two disagreed on the same card; runway
  years and the liquidity ratio had the same dot/comma split; and **all**
  `metrics.py` prescore evidence used dots (`_fmt` was `:g`, others raw `:.1f`).
  Fix: one comma convention through small shared helpers — `insights._signed`
  (+ reuse of `_fmt_x`), and `metrics._num`/`_signed_pct` (+ `_fmt` now commas);
  every displayed decimal now matches `pl-PL` like the rest of the app. Integer
  percentages (`:+.0f%`) were already correct and left as-is.
- **Tests (+3, pl-PL + no-dup regression locks):** `test_thesis.py`
  `test_size_factor_label_not_duplicated` (pro/con carry the label once);
  `test_metrics.py` `test_prescore_evidence_uses_pl_decimal_comma`
  (`"Ostatnie 2 kw.: +10,0% i +14,0%."`, one-off "1,1%");
  `test_insights.py` `test_gross_margin_trend_uses_pl_decimal_comma` (comment
  "+1,5 p.p." == summary brief, no "+1.5").

**Frontend (visual hierarchy · colour semantics · degraded states · mobile):**
- **`ThesisPanel` — verdict as a hero.** The entry-quality verdict was a small
  pill equal in weight to the meta chips; now it leads the card as an icon +
  large label (`.thesis .verdict`, tone-coloured). The **icon is a non-colour
  cue** (`IconCircleCheck`/`IconCircleDot`/`IconAlertTriangle`/`IconHelpCircle`)
  so the verdict never relies on colour alone; strategy/engine demoted to muted
  chips.
- **`ScenariosPanel` — valuation made primary.** Added a `.scenarios .headline`
  at the top of the card: the probability-weighted **Oczekiwany potencjał** as a
  26 px signed number (colour + sign) with the `bieżący → oczekiwany` price
  reconciliation; a `.headline-gap` amber note ("wycena niedostępna — brak ceny
  docelowej…") for the no-priced-scenario case. Removed the now-redundant bottom
  "Wartość oczekiwana" strip (folded into the headline) — the per-scenario rows
  read as the supporting detail. All numbers still via `lib/format.ts`
  (`fmtPct`/`fmtPln`/`signClass`) — no raw `toFixed`/`Intl` in components.
- **Degraded state — stale price.** Stock header shows a `kurs sprzed N dni`
  warning badge when the quote is >5 days old, so the scenario valuation
  (computed off that price) is read with the caveat rather than trusting it
  silently. (No-key state needs nothing new: thesis/scenarios/valuation always
  render deterministically; the `silnik: deterministyczny` chip + the disabled
  "Analizuj — Faza 5" button already read as intentional.)
- **Responsive (phone).** Stock header `.spread` now wraps (`flexWrap`); the
  ~10-column watchlist table is wrapped in a new `.table-wrap` (horizontal
  scroll) instead of overflowing the viewport; the forecast form/result grid
  used an inline `gridTemplateColumns` that defeated the mobile 1-col collapse —
  moved to a `.grid-2.wide-left` class with a real `@media(max-width:760px)`
  override.
- **`globals.scss`** carries all new tokens/classes (`.thesis .verdict`,
  `.scenarios .headline`, `.grid-2.wide-left`, `.table-wrap`) — every colour a
  `--text-*` variable; nav labels stay English per the standing user decision,
  domain copy Polish.

Verification (in-session): backend pure suite **126 passed / 0 failed** via the
`/tmp` pytest shim (test_thesis 14, test_thesis_ai 17, test_metrics 21,
test_insights 16, test_forecast 5, test_scenarios 14, test_scenarios_ai 14,
test_valuation_ai 25 — +3 vs the 123 baseline, no regression); `py_compile`
green on the four touched backend files; `tsc --noEmit` exit 0; `sass` compile
of `globals.scss` exit 0. Deferred to the user's machine (no PyPI/DB/egress in
sandbox): `cd backend && pytest` full DB/API suite; `cd frontend && npm run
build`; and real-browser rendering of the hero/headline/stale-badge + the
mobile watchlist scroll.

### Part B — static previews of the post-Part-A panels (real engine output)

Visual previews of the redesigned **Teza inwestycyjna** + **Scenariusze** cards
for the user, filled with REAL deterministic engine output (no hand-typed
numbers), under `docs/previews/`. Rationale: let the user see the Part A
hierarchy/colour changes on a concrete company before the DB/API path is run on
their machine.

- **Data path (no invented numbers).** `docs/previews/_render_engine_output.py`
  rebuilds the *pure* half of `dossier.build_dossier` (parsers → `fields` →
  `metrics` → `insights` → `thesis` → `scenarios` → `valuation_ai`, exactly like
  `scripts/validate_thesis.py`) on the committed **DECORA (DEC)** fixtures
  (`backend/tests/fixtures/br_*.html`; identical to
  `backend/.cache/validation/DEC_*.html`). The one deliberate divergence from
  `validate_thesis.py`: the current price is sourced the way `dossier.py` sources
  it (stored Price rows) — here the committed `stooq_daily.csv` latest close
  **24,50 zł**, which equals DECORA's reported market cap ÷ shares — so the panel
  renders with a live weighted potential instead of a `None` price. Every AI
  refiner runs on its **no-key deterministic** path. Output →
  `docs/previews/dossier-DEC.json` (thesis + scenarios + valuation + insights).
- **Real engine numbers (DEC, Malik/OBS).** verdict `attractive` ("Ciekawy punkt
  wejścia w analizę"); C/Z reversion (own history median 11,35 / q1 10,78 / q3
  11,85, n=8; eps 2,545; price 24,50); scenarios −/base/+ = 27,44 zł (**+12,0%**)
  / 28,89 zł (**+17,92%**) / 30,16 zł (**+23,1%**), p 0,25/0,50/0,25; weighted EV
  **28,84 zł (+17,71%)**; valuation potential **+17,71%** (pasmo +12,0…+23,1%),
  confidence **high** (7 key indicators ≥5, n=8 ≥4).
- **Render vehicles.** `scenarios-DEC-after.html` — self-contained (CSS compiled
  by hand from `globals.scss`, DOM mirrors `ThesisPanel.tsx`/`ScenariosPanel.tsx`
  1:1, numbers via the `lib/format.ts` pl-PL rules, zero external requests,
  viewport set → opens on a phone). `scenarios-DEC-after.png` (+ `.svg` source) —
  a native-SVG render rasterised with ImageMagick, because the sandbox has **no
  headless browser** (no chromium/playwright; `pip` egress 403) and ImageMagick's
  MSVG ignores `<foreignObject>`, so HTML can't be screenshotted; the PNG is a
  faithful *static* preview, the HTML is the pixel-faithful one. Generators
  `_render_html.py` / `_render_svg.py` kept next to the previews for
  reproducibility.
- **Deliberately skipped.** A pre-Part-A "before" variant: `ThesisPanel.tsx` /
  `ScenariosPanel.tsx` are **untracked** (created in Stage TH/SC), so `HEAD` has
  no earlier version to diff against — not recoverable from git. **SNT** preview:
  only a markdown web-extraction exists (`fixtures/live-20260708/SNT_*.md`), which
  the BeautifulSoup parsers can't read (per `docs/validation-thesis.md`) and which
  carries no C/Z history — so no real scenario set is computable; DEC is the one
  committed fixture-backed ticker that runs the full pipeline. (`docs/previews/`
  also holds four zero-byte `_inspect_*.png` stubs — leftover crop scratch the
  sandbox FUSE mount refused to `unlink`; safe to delete.)

## 2026-07-08 · Stage SC complete — scenario simulation engine + AI valuation agent (WP5 closeout, SC.1–SC.5)

Final in-session conformance pass for stage SC (`docs/plan-stage-scenarios.md`).
Per-WP entries already exist below (WP1 memory compaction, WP2 cleanup, WP3
scenario engine, WP4 valuation agent + corpus); this entry is the stage-level
digest + honest final numbers per plan §WP5.

**Exact test counts (this session, shim rebuilt from scratch in `/tmp`; repo
untouched):** 176 passed / 0 failed / 0 error / 29 skipped across 15
importable files, + 2 genuine collection errors. Per file: `test_thesis` 13,
`test_thesis_ai` 17, `test_metrics` 20, `test_insights` 15, `test_forecast` 5,
`test_biznesradar_parser` 33 (+6 skip — `real_br_*.html` never recorded),
`test_http` 6, `test_stooq` 8, `test_forum` 3 (+3 skip — needs FastAPI
`TestClient`), `test_yahoo` 3 (+2 skip — needs `TestClient`/SQLAlchemy `db`),
**`test_scenarios` 14** (13 from WP3 + 1 new WP5 regression test, ≥9
required), **`test_scenarios_ai` 14** (≥10 required), **`test_valuation_ai`
25** (≥8 required, incl. corpus-integrity tests); `test_api_phase1` 0+12 skip,
`test_api_phase3` 0+6 skip (both need `TestClient` per-test, not collection
errors this run — see methodology note in `docs/validation-scenarios.md`);
`test_migrations`/`test_refresh_prices` genuine collection errors (`import
sqlalchemy`/`alembic` at module top). **Stage-TH baseline unchanged**
(thesis/thesis_ai/metrics/insights identical counts) — no regression.
`py_compile` 65/65 (whole backend) / 41/41 (`app`+`scripts`, same baseline
subset as after WP4). `tsc --noEmit` exit 0.

**Defect found and fixed this session (not just documented).** Cross-checking
a scenario built from DEC's real fixture numbers (own C/Z history + EPS from
`docs/validation-thesis.md`, but — as that doc already notes — no price in the
fixture) crashed `services/scenarios.py` with a `TypeError`: `_build_scenario`
only routed to its "labelled gap" branch when `target_price`/`mult_value` were
missing, never when `current_price` alone was missing while a target price
was still computable. The narrative formatter then tried `_fmt_signed(None)`.
In production this is reachable whenever a company has computable
EPS/book-value/EBITDA but no price at all (every price source failed one
refresh, or a fresh listing) — `dossier.py` calls `build_scenario_set`
unconditionally, so this would 500 the whole `/api/companies/{ticker}`
endpoint, not just degrade the scenarios section. Fixed with a minimal added
branch (labels the missing-price gap instead of formatting `None`; the
current-price-present branch is byte-for-byte unchanged) plus a new regression
test, `test_missing_current_price_labels_gap_no_crash`
(`tests/test_scenarios.py`, now 14/14). Full suite re-confirmed green after the
fix (176 passed, up from 175 before this test existed). Full write-up incl.
root cause: `docs/validation-scenarios.md` §"Defekt znaleziony i naprawiony".

**Fixture-first policy confirmed.** `test_scenarios.py`/`test_scenarios_ai.py`/
`test_valuation_ai.py` use exclusively hand-built `ScenarioInputs`/
`StubTransport` — zero live HTTP in the test suite itself.

**Live BR validation: attempted, deferred (precise reason, not silently
skipped).** One polite request this session through `app.scrapers.http.fetch`
(the same path production uses, no bypass) to
`https://www.biznesradar.pl/notowania/DEC` → `FetchBlockedError` (proxy 403 on
CONNECT), matching stage TH's finding exactly; not retried, archiwum untouched,
0 pagination. Scenarios/valuation add no new scraping surface (plan
§Non-goals) — they consume already-computed dossier fields — so a live probe
here would only re-exercise the already-documented parser limitation from
`docs/validation-thesis.md` (`web_fetch` reaches BR but returns markdown, not
HTML); not repeated, reasoned out explicitly in the validation doc instead of
silently reusing the old finding.

**Docs written.** `docs/validation-scenarios.md` (hand-checked cz/cwk/ev_ebitda
target/upside/weighted-EV numbers reproduced by a live run this session, not
copied from test comments; probability-coherence + multiple-selection checks;
confidence-heuristic worked examples at all 3 levels; corpus enrichment
summary incl. the SUNTECH miss; the defect write-up; exact test counts;
explicit gaps/deferred section). `docs/learning/phase-scenarios.md` (≤1 page,
5 concepts incl. the strategy-pattern projector, the `compute_pe_history` →
`compute_multiple_history` alias, the widened AI fabrication guard, probability
renormalisation, the confidence rules-table, and the WP5 debugging lesson;
C#/.NET analogies throughout per CLAUDE.md's learning-layer rule).
`TASKS.md` Stage SC boxes SC.1–SC.5 ticked (all WPs verifier-passed). CLAUDE.md
"Read on demand" index already listed `docs/plan-stage-scenarios.md` +
`docs/validation-scenarios.md` + `docs/learning/phase-scenarios.md` since WP1
(SC.1) — re-checked, still accurate, still 69/70 lines; no further edit needed.

**User-machine runbook (deferred, documented not skipped):** `cd backend &&
pytest` (full DB/API suite, 24 tests); `cd frontend && npm run build`;
`ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py <TICKER>` (real Claude
refinement for both scenarios and valuation); live BR cross-check for
DGN/OPTEX/SUNTECH entry-era fundamentals via `scripts/validate_thesis.py`.

Why / decisions:
- **Debugging counts as testing (plan's own model split).** The plan assigns
  "testing/debugging/verification" to this WP5 pass; the current-price crash
  was found and fixed here rather than left as a passive note, because it is a
  small, well-contained, test-covered fix squarely inside that remit — not a
  redesign of WP3's already-verifier-approved engine.
- **Honesty over convenience in test-count methodology.** This session's shim
  reports client/db-gated tests as individual skips (with a precise per-test
  reason) rather than blanket per-file collection errors; the *outcome*
  (deferred to the user machine) is identical to earlier sessions, only the
  reporting granularity differs — called out explicitly so the numbers are
  never mistaken for a silent change in what's covered.
- **No new live BR probe beyond one reconfirmation.** Stage SC adds no new
  scraping surface; repeating the already-documented `web_fetch`
  markdown-vs-HTML finding would burn a live request for zero new information,
  so this session did the cheaper, still-honest thing: one polite
  `scrapers/http.py` attempt to reconfirm no egress, and an explicit
  explanation of why a second `web_fetch` probe was skipped rather than just
  silently omitted.

Refs SC.1–SC.5 (stage SC complete, all 5 WPs verifier-passed across the
session history; this entry closes the stage per plan §WP5 acceptance).

## 2026-07-08 · AI valuation agent + WorkedCase enrichment (WP4 / SC.4)

An API-agent step that reads **all gathered data + the WP3 scenario set** and
produces a **stock-potential valuation** (how much potential, at what confidence,
what would change it), plus a real-multiples/repricing-durations enrichment of the
WorkedCase corpus **including a documented miss** (survivorship-bias guard).
Deterministic-first, every number traceable, framed as *an analysis entry point,
not a signal*.

**What + why (files created / changed):**

- **`services/valuation_ai.py` (new)** — `assess_potential(inputs, scenario_set,
  profile, *, ticker, corpus, transport, settings)`, extending the
  `thesis_ai`/`scenarios_ai` pattern: injectable transport, bounded rounds
  (`anthropic_max_iterations`), JSON-file cache
  (**`backend/.cache/valuation_ai/`**, keyed on ticker+input+**scenario-set**
  hash+model+profile), lazy SDK/pydantic import, deterministic no-key fallback
  (never raises). Produces a `valuation` block:
  - **`potential`** `{value_pct, range_pct, basis_label}` — anchored to the set's
    weighted EV; the no-key `value_pct == scenario_set.weighted_expected_upside_pct`
    exactly (deterministic contract). `range_pct` = the [min,max] scenario upside
    band. When no scenario is priced → `None` + a labelled gap, never a guess.
  - **`confidence`** `{level, rationale}` — a **deterministic heuristic with the
    amended explicit thresholds**: `< min_key_indicators` (3 for Malik) **or**
    `multiple_history.n == 0` ⇒ **low**; `≥ 5` key indicators **AND** `n ≥ 4` ⇒
    **high**; everything between (3–4, or ≥5 with n<4) ⇒ **medium**. The
    number-bearing facts (the counts + the level) stay sourced; the AI may only
    reword the rationale. Verified at all three levels in tests.
  - **`what_would_change`** `[{id,text,why}]` — the thesis `verify_next` gaps
    (catalyst, backlog, management, …) **+** the scenario reversion assumption;
    never empty while the strategy carries verify-gaps. An invented gap id from
    the model is ignored, and no deterministic gap is silently dropped.
  - **Fabrication guard** — prose numbers ⊆ `input_numbers ∪ scenario_numbers ∪
    corpus_numbers ∪ engine_valuation_numbers` (the last = this valuation's own
    computed coverage counts + potential value/range, mirroring WP3b's
    `engine_scenario_numbers`). A stray figure rejects the round → last-valid /
    deterministic fallback. Model literal stays `'claude-sonnet-4-6'`.
- **`services/thesis.py`** — new public `count_computable_key_indicators(inputs,
  profile)` delegating to the existing `_collect_signals` (the single source of
  the `computable` count), so the confidence heuristic reads coverage from the
  SAME number the entry gate uses — **no recompute / no divergence** (PLAN
  non-goal). Additive; `test_thesis.py` still 13/13.
- **`services/strategies/cases.py`** — WorkedCase corpus enriched with real,
  **sourced** figures, each number living only in the `sources` dict / `citation`
  / `as_of` / `gaps` (never in the reconstructed fundamentals, which stay all
  `MissingData` — zero bare numbers). New `outcome` field ("hit"/"miss"/"").
  Corpus is now **DGN (hit)** — "+2500% w ciągu 5 lat" (≈60 mies. from POS
  02.2023) [DGN]; **OPTEX (entry-pattern)** — sourced entry multiples C/Z ~12,
  prognoza <10, rosnący backlog, po spadku kursu [F][M1; strategy-malik.md
  zasada 8]; **Suntech (documented MISS)** — thesis catalyst (nowe znaczące
  kontrakty) never materialised, held against his own discipline
  ("samousprawiedliwianie błędnych decyzji") [F; M1 §7], entry ~2,40 zł [F];
  **SNT (unverified placeholder)**, kept. What is **not** sourced (DGN's "~20
  PLN", every entry multiple/own-history) stays a labelled gap deferred to
  `scripts/validate_thesis.py` on a machine with egress — **no invented history**.
  The **PEP 562 lazy `CORPUS`** (`__getattr__`) + the circular-import guard
  (thesis→strategies→cases→thesis) are preserved; the enriched numbers land in
  the WP3b/WP4a allowed-set via the untouched `scenarios_ai.collect_corpus_numbers`
  (reads `sources`/`gaps`/`citation`), so `test_thesis_ai.py` stays **17/17**.
- **`services/dossier.py`** — calls `valuation_ai.assess_potential(scenario_inputs,
  scenarios_block, malik.MALIK, ticker=…)` after the scenarios → new dossier
  **`valuation`** block (pass-through with no key).
- **`api/schemas.py`** — `ValuationPotentialOut`/`ValuationConfidenceOut`/
  `WhatWouldChangeOut`/`ValuationOut`, nested `valuation: ValuationOut` in
  `DossierOut` (required backend-side; the deterministic dict shape matches the
  schema field-by-field, verified in-session).
- **Frontend** — `lib/types.ts` gains `Valuation` (+ nested), `Dossier.valuation?`
  **optional** (mirrors the `scenarios?` graceful-degradation pattern);
  `ScenariosPanel.tsx` renders the valuation inside the scenarios card below the
  weighted-EV strip (potential %/range, confidence badge + rationale, "co
  zmieniłoby ocenę" list, framing, engine chip), all numeric fields through the
  `lib/format.ts` pl-PL helpers (`fmtPct`/`signClass`) — **no raw
  `toFixed`/`toLocaleString`/`Intl` literal in the component** (grep-clean);
  `stock/[ticker]/page.tsx` passes `dossier.valuation`; `styles/globals.scss`
  adds a small `.scenarios .valuation` block (reuses the scenarios-scoped
  `.thesis-title`/`.scenario-metrics`/`.framing`/`.ai-note`). `tsc --noEmit` exits
  0. One shared disclaimer covers the scenarios+valuation card (identical
  `DISCLAIMER` — not double-rendered).
- **`scripts/scenarios_smoke.py`** — extended to also print the valuation block
  (engine, iterations, potential %/range, confidence level+rationale,
  what-would-change, narrative). Deferred real-key runbook:
  `cd backend && ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py SNT`.

**Tests (new + regression, in-session):**

- **`tests/test_valuation_ai.py` (new) — 25/25** in-session (bare Python
  `__main__` runner, no PyPI): confidence heuristic at **all three levels**
  (low via <3 computable, low via n==0, medium at 3–4, medium at ≥5 with n<4,
  high at ≥5 & n≥4); no-key fallback (`potential == weighted upside`); happy-path
  merge (`engine=="ai"`); malformed/transport-error fallback; iteration cap;
  convergence; cache hit + cache-disabled; fabrication guard (stray 888,8
  rejected; scenario `35` + injected-corpus `7,3` allowed); framing + DISCLAIMER
  preserved; invented what-would-change id ignored; **corpus integrity** — lazy
  + import-pure `CORPUS`, ≥1 documented miss, every number sourced (no bare
  fundamental), enriched multiples/durations citable (2500/60/12/10/2,4),
  `evaluate_case` runs on all four.
- **Regression (no WP3 baseline drop):** `test_thesis.py` 13/13, `test_thesis_ai.py`
  **17/17** (corpus enrichment did not break it), `test_scenarios.py` 13/13,
  `test_scenarios_ai.py` 14/14. `python -m py_compile` green over all 41 backend
  `*.py`. `tsc --noEmit` exits 0.
- **Verified green in-session (established `/tmp` pytest shim, same
  technique as the TH/WP2 verifiers):** `test_metrics`/`test_insights`/
  `test_forecast` + `test_biznesradar_parser`/`test_http`/`test_stooq`/
  `test_forum`/`test_yahoo` — that subset **93 passed / 6 skipped**; full
  in-session suite **175 passed / 6 skipped / 0 failed**. Genuinely deferred
  to the user's machine only: the DB/API suite
  (`test_api_phase1`/`test_api_phase3`/`test_migrations`/`test_refresh_prices`,
  plus the client/DB-dependent parts of `test_forum`/`test_yahoo`),
  `npm run build`, and the real-key `ANTHROPIC_API_KEY` smoke.

**Decisions / deviations:**

- **Enriched numbers encoded in the `sources`/`gaps`/`citation` channels** (not a
  new typed numeric field) so `scenarios_ai.collect_corpus_numbers` folds them in
  **without touching WP3 code** — the handoff's "enriched CORPUS becomes citable
  automatically" holds literally. The only structured addition is the digit-free
  `outcome` tag.
- **Suntech is a thesis/catalyst miss, not a multiple-derating miss** — recorded
  honestly (the sources document the catalyst failing + a discipline error, not a
  cheap-multiple slide). It still serves the survivorship-bias guard; the
  distinction is stated in the case's `gaps`.
- **`engine_valuation_numbers` added to the allowed-set** (beyond the plan's
  literal `inputs ∪ scenarios ∪ corpus`) so the deterministic coverage counts the
  rationale must quote are traceable — the exact WP3b precedent
  (`engine_scenario_numbers`); the honesty rule "a deterministic computation from
  those inputs is traceable" governs.

## 2026-07-08 · Scenario simulation engine (WP3 / SC.3)

The stage's main feature: per stock, a coherent **negative / base / positive**
trio of multiple-reversion scenarios + an optional Claude-API refiner, surfaced
next to `ThesisPanel`. Deterministic-first (no key ⇒ traceable fallback), every
number traceable, framed as *an analysis entry point, not a signal*.

**What + why (files created / changed):**

- **`services/scenarios.py` (new, pure)** — the deterministic projector.
  `build_scenario_set(inputs, profile)` selects the sector multiple
  (`select_valuation_multiple`: C/Z generally, **C/WK** finance/realestate,
  **EV/EBITDA** energy — derived from `malik.py` applicability, *no* second copy
  of the sector map), reverts it toward the company's OWN-history quartiles
  (Q1/median/Q3) and computes target price, implied upside, horizon and the
  set-level probability-weighted EV. Probabilities **0.25/0.50/0.25 = 1.00 by
  construction**. Target math per doctrine: C/Z `pe×eps`, C/WK `pwk×bvps`
  (`bvps = equity_tys×1000/shares`), EV/EBITDA `(mult×ebitda_tys×1000 −
  net_debt)/shares` (`net_debt = −net_cash`). **Missing driver ⇒ labelled gap +
  `None` target, never a guessed price** (C/Z fallback when a sector driver is
  absent; if C/Z too is unavailable → `None` + a verify-note). Imports only
  `thesis`/`strategies`/stdlib (deliberately **not** `thesis_ai`), so it runs
  under the bare sandbox Python; carries its own fabrication-guard number
  vocabulary (`input_numbers`/`computed_numbers`/`prose_numbers`).
- **`services/scenarios_ai.py` (new)** — the refiner, extending the
  `thesis_ai.py` pattern: injectable transport, bounded rounds
  (`anthropic_max_iterations`), JSON-file cache (`backend/.cache/scenarios_ai/`),
  lazy SDK/pydantic import, deterministic no-key fallback (never raises). The
  model may reword narratives, adjust probabilities and **add event scenarios**
  grounded in the dossier's `verify_next` gaps; **coherence (Σ=1) is re-imposed
  by us** (renormalise every round). **Widened fabrication allowed-set**:
  `input_numbers ∪ corpus_numbers ∪ engine_scenario_numbers` (sourced inputs ∪
  cited corpus ∪ deterministic-computed) — a stray prose figure rejects the
  round. Model literal stays `'claude-sonnet-4-6'`.
- **`services/thesis_ai.py`** — three single-line **public aliases**
  (`numbers`/`extract_json`/`parse_response`) so the refiner reuses the helpers
  without reaching into privates. No behaviour change (`test_thesis_ai.py` still
  17/17).
- **`services/metrics.py`** — generalised `compute_pe_history` → new
  `compute_multiple_history(values, current)` returning `{median,q1,q3,current,
  percentile,**n**}` (works for any multiple series). `PeHistoryStats` kept as an
  alias of the new `MultipleHistoryStats`; `compute_pe_history` kept as a thin
  alias — every existing C/Z call site unchanged. **Decision:** `n` flows onto
  the `pe_history` dict; `PeHistoryOut` left untouched (pydantic drops the extra
  key) to keep the deferred DB/API leg's blast-radius zero.
- **`services/dossier.py`** — builds `ScenarioInputs`, calls
  `build_scenario_set` then `simulate_scenarios` → new dossier **`scenarios`**
  block. Loads the selected multiple's own-history series (parametrised by
  indicator code, same query shape as `cz`). **`ebitda_ttm=None` (labelled gap):
  EBITDA TTM is not computed anywhere yet**, so energy names fall back to their
  own C/Z history rather than fabricate an EV/EBITDA (the math is implemented +
  unit-tested via direct inputs; WP-later can feed real EBITDA).
- **`api/schemas.py`** — `ScenarioTargetMultipleOut`/`ScenarioHorizonOut`/
  `ScenarioOut`/`ScenarioSetOut`, nested `scenarios: ScenarioSetOut` in
  `DossierOut`.
- **Frontend** — `components/ScenariosPanel.tsx` (Overview order
  MetricCards → Teza → **Scenariusze** → Analiza → Prescore → Kurs), mirrors
  `ThesisPanel` incl. the `silnik` engine chip + disclaimer + the "punkt wejścia
  w analizę, nie sygnał" framing; degrades when `scenarios` is absent. Values go
  through `lib/format.ts` pl-PL helpers (`fmtPln`/`fmtPct`) — **no
  `toFixed`/`toLocaleString`/`Intl` literal in the panel** (grep-clean),
  reconciling "use pl-PL helpers" with the plan's as-is grep rule. `lib/types.ts`
  gains `Scenario`/`ScenarioSet` (field-by-field) + optional `Dossier.scenarios`.
  `globals.scss` self-contained `.scenarios` card. `tsc --noEmit` exits 0.
- **`scripts/scenarios_smoke.py` (new)** — deferred real-key runbook mirroring
  `thesis_ai_smoke.py`: prints engine, iterations, the scenario set + weighted EV.

**Tests (in-session, bare `python3` + `/tmp` pytest shim):**

- `tests/test_scenarios.py` **13/13** — hand-checked targets/upsides/weighted-EV
  for C/Z, C/WK and EV/EBITDA (computation shown in comments), multiple-selection
  by sector, probability Σ=1, neg≤base≤pos ordering, `missing_driver_labels_gap`
  (None target, no invented number), C/Z fallback, and `every_scenario_number_is_
  traceable` (prose ⊆ inputs ∪ computed).
- `tests/test_scenarios_ai.py` **14/14** — happy-path AI merge, malformed
  fallback, iteration-limit, convergence, fabrication guard (stray rejected),
  corpus-number allowed, engine-number allowed, probability renormalisation after
  an added event scenario (`|Σ−1|≤0.01`), no-key fallback, cache hit/skip +
  disabled bypass, framing+DISCLAIMER preserved.
- **No regression:** the stage-TH/WP2 baseline **123 passed** is reproduced green
  (test_thesis 13, test_thesis_ai 17, test_metrics 20, test_insights 15,
  test_forecast 5, test_biznesradar_parser 33 (+6 skip), test_http 6, test_stooq
  8, test_forum 3, test_yahoo 3); + the 27 new = **150 passed in-session**.
  (`test_forum 3` / `test_yahoo 3` are the **pure subsets** — 3-of-6 and 3-of-5;
  the skipped remainder needs the deferred DB/client fixture.)
  `py_compile` green over all 40 `backend/**/*.py`; `tsc --noEmit` exits 0.

**Deferred to the user's machine (documented, not run in-session — no PyPI /
egress / DB):** `cd backend && pytest` (full DB/API); `cd frontend && npm run
build`; `ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py <TICKER>` (real
refinement). Learning note (`docs/learning/phase-scenarios.md`) is a **WP5**
deliverable — hook recorded here per WP3 acceptance #7.

**Decisions / deviations:** (1) `scenarios.py` keeps its **own** number-extraction
vocabulary rather than importing `thesis_ai` — module purity (the acceptance
import allow-list) beats DRY here; the refiner still reuses `thesis_ai`'s
transport/parse/cache. (2) AI event scenarios carry **no** target price/upside
(a catalyst's magnitude isn't computed) and the default horizon band — honest
until WP4's corpus supplies real repricing durations. (3) The fabrication guard
checks **prose** numbers ⊆ allowed; structured numbers are engine-controlled
(kept-deterministic or our renormalised probabilities / recomputed weighted EV),
matching "deterministic-computed scenario numbers" in the allowed-set.
(4) **Plan doc amended** (`docs/plan-stage-scenarios.md` WP3c text + acceptance
#6 + the verifier/protocol restatements) so spec matches code: the "render
as-is / same rule as `ThesisPanel`" wording is corrected to **permit the
`lib/format.ts` pl-PL helpers for numeric fields** — `ThesisPanel` renders only
backend prose, but `ScenariosPanel` renders raw numbers (target
price/upside/probability/weighted EV) that must format pl-PL like `MetricCards`
(CLAUDE.md); the grep still bars raw `toFixed`/`toLocaleString`/`Intl` literals
in the component.

---

## 2026-07-08 · Clean project: remove provably-dead code (WP2 / SC.2)

Conservative dead-code sweep before the scenario engine lands — prove-before-delete,
green tests as the safety proof. The codebase was already clean (an `ast` unused-import
scan over `backend/app` + `backend/scripts` reported **zero** unused imports/names both
before and after), so the removals are small; the bulk of the WP is the *proof* that it
is clean. **No files moved/renamed/merged (0 structural changes)**; no frontend source
touched; the "do NOT touch" list respected (all byte-unchanged).

**Removal ledger** (path · why dead · proof — nothing removed without a green proof):

| # | Path | What / why dead | Proof |
|---|------|-----------------|-------|
| 1 | `backend/app/services/forecast.py` | fn `_last_quarters(income, count)` — superseded: `default_assumptions` and `compute_forecast` both inline `sort_periods(income.keys())[-n:]` and never call it | `grep -rn "_last_quarters" backend/ --include='*.py'` → **only its own def line**; zero references in-file or repo-wide (frontend/docs/tests incl.). Removed the 2-line fn (−4 lines w/ spacing). No import left orphaned (`IncomeSeries`/`sort_periods`/`next_period`/`previous_year_period` all still used; strict re-scan of the file = 0). |
| 2 | `backend/tests/test_biznesradar_parser.py` | unused imports `date`, `ParseError`, `page_url`, `parse_price_history` — imported but referenced by no test in the file | per-name word-boundary `grep` across all 303 lines → each appears **only on its import line**; these names occur repo-wide in tests **only** in this file (only as imports). The symbols stay live in `app/scrapers/biznesradar.py` and elsewhere — only the redundant local bindings dropped (−4 lines). Post-edit strict `ast` scan of `backend/tests` = **0** candidates. |

Tool: a stdlib-`ast` unused-import scanner (no PyPI; `ruff`/`pyflakes` are the equivalent
on the user's machine), cross-checked by word-boundary `grep` per candidate.

**Deliberately KEPT (borderline — recorded so the choice is auditable):**
- **Frontend unused exports** — `fmtTys` (`src/lib/format.ts`), `getIndicators` + `getDividends`
  (`src/lib/api.ts`) are currently unreferenced, but they are coherent **library surfaces**,
  not orphaned files/modules: `api.ts` is a one-wrapper-per-endpoint client and those two
  mirror the **live** FastAPI routes `GET /companies/{t}/indicators` + `/dividends`; `fmtTys`
  is one primitive in the format-helper family. Pruning a library surface is the kind of
  gratuitous restructuring the WP forbids, doubly so with the frontend mid-Stage-TH
  (uncommitted). `tsc --noEmit` has no `noUnusedLocals`, so this is not a compile gate.
- `strategies/__init__.py` `base`/`cases` — a naive scan flags them, but they are legitimate
  `__all__` package re-exports (the `__all__`-aware scan correctly reports them used).
- `Criterion.thresholds` (`strategies/base.py`) — documented **PLAN §10 extension point**
  ("unused by the verdict-based engine today, kept so the data shape is ready"), not dead.
- Gitignored artifacts (`__pycache__/`, `.DS_Store`, `.next/**/*.old`) — not source; out of scope.
- The protected set — `stooq.py`/`yahoo.py` (live price-chain legs), `live-20260708/` evidence
  fixtures, `record_fixtures.py`/`record_topic_fixture.py`, `thesis_ai_smoke.py`/`validate_thesis.py`,
  `skills/scraper-doctor/SKILL.md` — all confirmed **byte-unchanged**. The dividend-layer gap
  (`docs/validation-thesis.md`) is a user product decision — **not** touched.

**Safety proof (in-session; counts re-run AFTER cleanup):**
- **`py_compile` green: 53/53** (`app`+`tests`+`scripts`, the Stage-TH baseline set) and
  **58/58** whole backend incl. `alembic`. No files removed ⇒ counts unchanged.
- **In-session test suite: 123 passed / 0 failed** (bare `python3` for the two `__main__`
  runners + a minimal `pytest` shim built in `/tmp`, repo untouched — same technique as the
  TH verifier). Per file: `test_thesis` 13, `test_thesis_ai` 17, `test_metrics` 20,
  `test_insights` 15, `test_forecast` **5**, `test_biznesradar_parser` **33 (+6 skip)**,
  `test_http` 6, `test_stooq` 8, `test_forum` 3 (+3 skip), `test_yahoo` 3 (+2 skip) — identical
  to the TH baseline; the two touched files (`test_forecast`, `test_biznesradar_parser`) stay
  green. In-file skips 11; the DB/API files (`test_api_phase1` 12, `test_api_phase3` 6,
  `test_migrations` 1, `test_refresh_prices` 5 = 24) are **collection-skipped** in-session
  (import sqlalchemy/fastapi at top) — deferred to the user machine. (The "123 passed, 29
  skipped" TH figure: the **123 passes are identical**; only the deferred-file skip tally
  differs by counting method — my harness AST-counts 24 deferred tests vs pytest's 18-ish —
  no pass lost, no fail.)
- **`tsc --noEmit` exit 0** (no frontend change).
- **Unused-import `ast` scan over `backend/app` + `backend/scripts`: ZERO** (acceptance #6);
  **0 structural moves** (acceptance #6 trivially met).

**Deferred (documented, not run in-session):** `cd backend && pytest` (full DB/API suite +
real fixtures) on the user's machine confirms no import broke — the 24 collection-skipped
tests are the leg that exercises the edited modules through the DB/API path.

Why / decisions:
- **Prove-before-delete + conservatism win over volume.** The plan anticipates a small (even
  empty) cleanup; the deliverable's value is the zero-unused proof + no-orphans finding as much
  as the two removals. Everything ambiguous (unused *library* exports, extension-point fields)
  was **kept and ledgered**, not guessed-away.
- **`git diff` note for the verifier:** the WP2 *code* delta is exactly `forecast.py` (−4) +
  `test_biznesradar_parser.py` (−4). Every other modified/untracked path in the tree
  (`schemas.py`, `config.py`, `dossier.py`, `.env.example`, `types.ts`, `page.tsx`,
  `globals.scss`, `tsconfig.tsbuildinfo`, the `strategies/`, `thesis*.py`, docs, …) is
  **pre-existing uncommitted Stage-TH work**, unchanged here (Stage TH is entirely uncommitted).
  Refs SC.2.

## 2026-07-08 · Memory: compact context for stage SC (WP1 / SC.1)

Re-consolidated project memory **before** any scenario code lands, so the new
work starts from a small always-loaded core. **Docs-only — no code/schema/config
touched;** `skills/scraper-doctor/SKILL.md` (quirks ledger) left **byte-for-byte
unchanged**.

- **CLAUDE.md (66 → 69 lines, ≤70 budget held).** The "Read on demand" index now
  lists `docs/plan-stage-scenarios.md` (+ the WP5-added
  `docs/validation-scenarios.md` / `docs/learning/phase-scenarios.md`); the
  changelog-archive pointer generalised to `docs/changelog-archive-*.md` (build
  day 07-07 + Stage TH 07-08); `docs/strategy-malik.md` relabelled as the spec
  the thesis **+ scenario** engines implement (scenarios reuse the same
  valuation doctrine).
- **Changelog archive.** The closed Stage-TH block — the six TH.* build entries
  (TH.1–TH.5, incl. TH.2b), the WP4b live-run note, the WP4 sandbox-rescope note,
  and the three Stage-TH plan entries, i.e. the whole contiguous 2026-07-08 TH
  section (~524 lines) — moved **verbatim** into the new
  `docs/changelog-archive-thesis-2026-07-08.md` (byte-identical, only relocated;
  mirrors the `docs/changelog-archive-2026-07-07.md` pattern: header pointing
  back to CHANGELOG + quirks ledger, then the entries). Left in `CHANGELOG.md`:
  both digests (Stage TH + build day), the most recent post-stage verification
  entry, and the current SC-plan entry — the always-loaded file drops from 841
  lines to the digests-plus-recent core. The top archive pointer and the
  Stage-TH digest cross-reference now name the new archive.
- **TASKS.md.** The **Stage SC** section (SC.1–SC.5) was already added by the
  SC-plan step; left as-is with every box **unticked** (ticked only after each
  WP's verifier PASS).

Why / decisions:
- **Compaction goal over the literal enumeration.** The plan lists "the six TH.*
  build entries + the WP4b/rescope entries"; I additionally moved the three
  Stage-TH *plan* entries so the live `CHANGELOG.md` keeps **only** the two
  digests + the post-stage verification of Stage TH (the deliverable's "leave in
  CHANGELOG.md" end-state) and the whole contiguous TH section relocates as one
  block — matching the 2026-07-07 precedent. No changelog content is lost (every
  moved entry is findable in the archive); acceptance #2 (digests + pointer
  retained) still holds.
- **Quirks ledger sacrosanct.** `skills/scraper-doctor/SKILL.md` untouched
  (`git diff` empty; md5 unchanged) — its knowledge survives compaction intact.

In-session regression (WP1 changed no code, so behaviour cannot move):
`test_thesis.py` **13/13** + `test_thesis_ai.py` **17/17** green under bare
`python3`; `test_metrics.py` **20/20** + `test_insights.py` **15/15** green under
the minimal pytest shim (built in `/tmp`, repo untouched). The git working tree
already carried the uncommitted Stage-TH files (untracked + modified `.py`/`.ts`);
the WP1 delta on top of that is **`.md`-only** (`CLAUDE.md`, `CHANGELOG.md`, the
new archive). Full `pytest`/DB path unchanged — still the user-machine leg. Refs
SC.1.

## 2026-07-08 · Plan: scenario-simulation stage (stage SC, SC.1–SC.5)

Planning-only change (no code). Added `docs/plan-stage-scenarios.md` — the stage
that answers the user's "single-scenario output is unhelpful": per stock a small
set of **negative/base/positive + event scenarios**, each with a coherent
probability (Σ≈1), a data-grounded narrative, a **target valuation from the
sector-relevant multiple** (C/Z generally, C/WK for banks/deweloperzy, EV/EBITDA
for surowce/energetyka) read against the company's **own** multiple history
*only* (*"a nie tylko do rynku czy branży"*), a repricing horizon, implied
upside, and a set-level probability-weighted EV vs current price. The worked-case
corpus feeds the repricing horizon, the AI's probability/timing sanity-check and
WP4's confidence — not the target number. Plus an **AI valuation agent** that
consumes all data + the scenarios → stock-potential + confidence + "what would
change the assessment". Also added `TASKS.md` **Stage SC** (SC.1–SC.5, unticked).

Why / decisions:
- **Extends the TH.2b pattern, deterministic-first.** `services/scenarios_ai.py`
  + `services/valuation_ai.py` reuse `thesis_ai.py`'s injectable transport,
  JSON-file cache, and fabrication guard behind a **no-key fallback** (engine:
  deterministic|ai). The deterministic core `services/scenarios.py` is a pure
  function layer (own-multiple reversion off `metrics.compute_pe_history`
  generalised to any multiple) that always yields a coherent set — the AI is
  never on the critical path. Not a stochastic Monte-Carlo (documented
  non-goal); discrete scenarios, simple-first.
- **Wider-but-still-closed fabrication guard.** Unlike the thesis (which only
  reuses insight numbers), scenarios legitimately *compute* new numbers (target
  price, upside, EV, probabilities, horizons). So the allowed-set is
  `inputs ∪ deterministic-computed scenario numbers ∪ cited worked-case corpus
  numbers` — every figure traceable to fetched data, a labelled assumption, a
  deterministic computation, or a cited comparable. Missing per-share driver
  (EBITDA TTM / book value) → labelled gap + `None` target, never a guess.
- **Corpus enrichment feeds evidence.** WP4 adds real, sourced multiples +
  repricing durations to the WorkedCase corpus **incl. ≥1 documented miss**
  (survivorship-bias guard), so horizons and confidence cite comparables. Lazy
  `CORPUS` (PEP 562) + import purity preserved; DGN "~20 PLN" stays
  UNVERIFIED/unused.
- **Housekeeping WPs first.** WP1 compacts memory (CLAUDE.md index + archive the
  closed Stage-TH changelog entries into a new
  `docs/changelog-archive-thesis-2026-07-08.md`, quirks ledger left byte-identical);
  WP2 removes provably-dead code with a per-item zero-reference grep proof and
  the full test suite green as the safety proof.
- **Sandbox honesty carried over:** no PyPI/egress in-session → pure layers +
  stub-transport tests run in-session, DB/API/`npm build`/real-key smoke/live BR
  deferred to the user's machine with exact runbook commands. Per-WP
  fresh-context verifier (sonnet) against this plan; implementation = opus.
- **P5 reconciliation:** scenarios_ai/valuation_ai transports are reused by
  P5.4; the Phase-5 analysis product (skill/analyses/AI tab) stays separate.
  Learning note `docs/learning/phase-scenarios.md` lands in WP5.

## 2026-07-08 · docs/validation: fresh-context verification pass + dividend-row correction (TH post-stage)

Independent fresh-context verification of the just-closed Stage TH (sonnet
agents, hands-on). **Docs-only change — no code, test, or strategy-data file
touched.** One documentation defect found and fixed; two cosmetic nits recorded;
one pre-existing layer gap surfaced for a user product decision. `test_thesis.py`
**13/13** + `test_thesis_ai.py` **17/17** re-confirmed.

**Verified green (exact counts).** `py_compile` **53/53** files green; import
purity holds (no pydantic/anthropic/fastapi/sqlalchemy/requests after importing
thesis/thesis_ai/strategies), `cases.CORPUS` lazy-builds DGN+SNT with no circular
import. Beyond the documented bare-`python3` runbook, a minimal **pytest shim**
(fixture/parametrize/raises/approx + faked pure conftest helpers, built in `/tmp`,
repo untouched) ran the pure suites in-sandbox too: `test_metrics` 20/20,
`test_insights` 15/15, `test_forecast` 5/5, `test_biznesradar_parser` 33 + 6 skip
(genuine — `real_br_*.html` never recorded), `test_http` 6/6, `test_stooq` 8/8,
`test_forum` 3 + 3 skip, `test_yahoo` 3 + 2 skip → **123 passed, 0 failed, 29
attributed skips**. Only `test_migrations.py` + `test_refresh_prices.py` (import
sqlalchemy at top) and the API/DB fixtures truly need the user machine. This
CORRECTS the "Stage TH complete" entry's line that `test_insights`/`test_metrics`
"cannot run" in-session (a bracketed correction note was added inside that entry).

**Defect found + fixed (the point of the pass).** The E2E replay — the unmodified
`scripts/validate_thesis.py` functions over the on-disk DEC cache (byte-identical
to the committed fixtures) — reproduces **23 of 24** documented numbers exactly.
The one miss was a real doc defect: `docs/validation-thesis.md` "silnik ↔ strona"
table carried a `Dywidenda | 3 lata z rzędu, stopa 4,9% | … | 0` row implying the
**thesis engine** judges dividend for DEC. **False** — the live DEC thesis output
has no dividend entry anywhere (`insights.missing == ["pe_vs_history"]` only).
Root cause (pinned by running the code): `insights.py`
`_GROUP_PLAYBOOK["industrial"]` has no `"dividend"` (only finance/energy/realestate
groups do), so `spec_dividend()` never runs for DEC (sector "Materiały budowlane" →
industrial), `idx.get("dividend")` is `None` in `build_thesis`, and the criterion
is silently skipped. The dividend **data** parses correctly (2023–2025, DPS
1,20 zł, 4,9% — matches the page); the gap is purely indicator selection. Fix:
the engine cell now reads "wskaźnik nieoceniany przez tezę dla grupy `industrial`"
with an explanatory note under the table. Fabrication guard on the live output:
**32** input numbers vs **9** read numbers, **0** invented. `evaluate_case`: DGN
"0/4" + SNT "0/2" → `insufficient_data`, `matches=True`.

**Layer gap left to the user (product decision, not a bug to fix now).**
`strategies/malik.py`'s `dividend` Criterion has no sector-applicability
restriction, while the insights playbook excludes dividend for **5 of 8** sector
groups → a real dividend history is invisible to the thesis engine (no pro, no
con, no `verify_next` flag) for industrial/tech/biotech/consumer/other companies.
This is **pre-existing `insights.py` behavior, not introduced by Stage TH**.
Whether to add dividend to more playbooks, restrict the malik criterion, or route
never-selected criteria to `verify_next` is left to the user — recorded in the
validation doc, no code change here.

**Two cosmetic nits recorded (out-of-scope, user decision).** (1) already-flagged
`insights.py` "+1.8 p.p."/"+1,8 p.p." pl-PL punctuation mismatch; (2) new —
`malik.py`'s `size_pro_text` hardcodes "Mała spółka ({size})", so a small-cap pro
renders "Mała spółka (Mała spółka) — sweet spot…" (duplication; micro reads fine).
Both need their own test + CHANGELOG entry; neither touched here.

**Other checks + politeness.** No-key fallback returns exactly
`build_thesis().to_dict()` + `engine:"deterministic"` (no `ai_notes`, no cache dir
created). `classify_size` sanity on real numbers: SNT reported mcap 3 213 775 722
→ **mid**; **one** polite live `web_fetch` of
`https://www.biznesradar.pl/notowania/PKNORLEN` (200, redirect →`/notowania/ORLEN`,
markdown) → hand-read "Kapitalizacja: 159 977 814 352" → **large** (size factor
flips PRO→CON; small=attractive/mid=neutral/large=neutral). Frontend `tsc
--noEmit` strict whole-app exit 0 (TypeScript 5.9.3, 28 files); `types.ts` ↔
`ThesisOut` field-by-field; `ThesisPanel` degraded states/chips/disclaimer/order
verified. **Politeness: 1 live request total this session, 0 retries, archiwum
untouched, 0 pagination, SNT not re-fetched.**

**Unchanged user-machine runbook** (still deferred — needs PyPI / a DB / npm / a
real key / egress): `cd backend && pytest` (full DB/API suite);
`scripts/validate_thesis.py DGN SNT DEC <large-cap>` (live ≥4-ticker cross-check);
`ANTHROPIC_API_KEY=… python scripts/thesis_ai_smoke.py SNT` (one real refinement).
No Alembic migration this change (latest remains 0004). Refs TH.4.

## 2026-07-08 · Data correctness + source rework + dynamic per-company analysis

Big verification round after user testing showed wrong classifications,
missing indicators and dead price sources. Backend + tests; frontend entry
below is part of the same change set.

**Size/mcap correctness (the ">1 mld shown as small" bug):**
- Profile parser now extracts the REPORTED `Kapitalizacja:` and
  `Enterprise Value:` (DOM-first, handles full integers and scaled
  "2,82 mld"; stored via migration 0004 on `companies`). `compute_ttm`
  prefers the reported figure — price×shares stays only a fallback and its
  deviation is exposed (`market_cap_check_pct`), so a stale price or a
  misparsed share count can no longer shrink a company below the small-cap
  threshold. Shares regex requires `:`+digits — the free-float row
  ("Liczba akcji w wolnym obrocie") can't be captured anymore.
- `classify_size` (micro <150 mln / small <1 mld / mid <5 mld / large):
  feeds the prescore evidence ("Kapitalizacja X mln zł (wg BiznesRadar) —
  Średnia spółka; próg 1 mld.") and the insights header chips.
- Self-healing prices: future-dated rows (an old bug wrote them and the
  `last_day >= today` guard then froze the chain on "aktualne" forever) are
  purged on every refresh; future bars are never stored again.

**Missing wskaźniki:**
- `match_indicator` is code-first (`data-field="CZ"`…) with the verified
  exact-label fallback; a guessed code never overrides a live-verified
  label on conflict. New mappings: C/ZO→`czo` (own code — never cz!),
  EV/Przychody→`ev_revenue`, short "Marża netto"/"Marża operacyjna",
  "Marża zysku ze sprzedaży"→`sales_margin`. Deliberately unmapped: Graham
  C/WK and "Marża zysku brutto" (PRETAX margin, not gross-sales).
- Dropped indicator rows are now VISIBLE: refresh summary lists
  "pominięte: …"; mapping-report gained `indicators_never_seen`.

**Comparability between stocks:**
- `load_income_series` is rank-aware: parent-shareholders net profit
  ("akcjonariuszy jednostki dominującej") beats the group row regardless of
  page order → EPS/C/Z now consistent across statement layouts.
- Reverse gross derivation (pos + selling + admin) when a layout reports
  profit-on-sales without a gross row; balance mappings extended with
  section totals (aktywa obrotowe, zobowiązania krótko-/długoterminowe,
  zapasy) for liquidity/gearing ratios.

**Price sources (stooq dead, Yahoo flaky — user-verified):**
- NEW source: BiznesRadar archiwum notowań, PAGE 1 ONLY (~50 sessions) —
  robots.txt allows page 1 and disallows `,N` pagination, so the app never
  paginates. Same politely-fetched domain, `parse_price_history` finds the
  table by header labels.
- Chain rework: incremental = BR archiwum → Yahoo → profile quote (stooq
  SKIPPED daily — it answers "access denied"; knocking daily would be
  impolite); backfill = Yahoo (5y in 1 request) → stooq (one chance) → BR
  archiwum → profile quote. Yahoo hardened: query1+query2 hosts,
  browser-ish headers, no second host after a hard block. Bossa EOD files
  evaluated and rejected (login-gated since 2026). `/health/scrapers` now
  tracks yahoo and both stooq hosts; failures are logged, not just
  successes.

**Dynamic per-company analysis (new `services/insights.py`, pure):**
- Sector groups (finance/biotech_med/tech/energy/realestate/consumer/
  industrial/other from BR "Branża") + size class pick WHICH indicators are
  judged: banks by ROE/C-WK/dividend, biotechs by cash runway, industrials
  by gross-margin trend/operating leverage, energy by EV/EBITDA/debt…
  Each indicator gets a verdict (plus/neutralnie/minus) with a Polish
  one-liner tied to this company's numbers.
- Honesty rules: missing data lands in `missing[]` with WHY it matters —
  never fabricated; `data_notes` flag stale price, derived mcap,
  reported/derived divergence >20%, financial-statement layout; `coverage`
  says how many of the selected indicators were computable.
- **Summary is COMPOSED from computed values** (user feedback on the first
  iteration: template counts like "3 na plus" are useless) — e.g. "Duża
  spółka, energetyka / surowce (156,98 mld zł). Na plus: EV/EBITDA 5,8;
  one-offy 8,3% zysku oper.; dywidenda 27 lat z rzędu. Na minus: C/Z 24,5
  vs własna mediana 7,8; ROE 4,3%." Only metrics that exist appear.
- Dossier gained `insights`; schemas + TS types extended accordingly.

**Tests:** suite updated for all of the above; new `test_insights.py`,
`test_refresh_prices.py` (chain order, stooq-skip, future-purge),
parser tests for mcap/EV/free-float/scaled forms + price history; fixtures
extended with trap rows (free float, Graham, pretax margin). Pure layers
(fields/metrics/insights/parsers) executed green in-session against fixture
+ live-shape data; DB/API layers compile-checked — run `cd backend &&
pytest` locally (sandbox has no PyPI). Real-page recording:
`python scripts/record_fixtures.py SNT` now also records the archiwum page.

**Memory consolidation (user request):** CLAUDE.md trimmed to a short
always-loaded core with an on-demand doc index; build-day changelog entries
archived to `docs/changelog-archive-2026-07-07.md` with a digest below;
quirks ledger restructured (BR items unmisfiled from the Prices section,
chain-order contradiction resolved, 2026-07-08 findings added).

## 2026-07-08 · Frontend: dynamic insights panel + mcap provenance notes

Frontend side of the sector/size-aware analysis (`insights` block in the
dossier API):

- **types.ts** mirrors the new backend shapes: `Company.market_cap` /
  `enterprise_value`, `Ttm.market_cap_source` ("reported" | "derived") +
  `market_cap_check_pct`, and `Dossier.insights` (`Insights`, `KeyIndicator`,
  `MissingIndicator`). Indicator values arrive preformatted as strings —
  rendered as-is, no client-side number formatting.
- **New `InsightsPanel`** on the Przegląd tab, ABOVE the prescore (dynamic
  analysis is the entry point, the static checklist follows): size/sector
  chips + summary, key indicators sorted by importance (imp. 3 tagged
  "kluczowy", verdict badges plus/neutralnie/minus/b-d), Mocne strony /
  Ryzyka in a `grid-2`, "Czego brakuje w danych" prefixed with the coverage
  note, and warning-toned `data_notes` at the bottom. Empty sections are
  skipped.
- **globals.scss:** added `.badge.neutral` / `.badge.muted` variants (the
  verdict palette needed non-signal tones) and a scoped `.insights` block —
  hairline dividers between sections inside one card, list markers colored
  by verdict instead of the text.
- **MetricCards:** the Kapitalizacja card now footnotes provenance —
  "szacunkowa (kurs × liczba akcji)" when the value is derived, and a warn
  note "rozbieżność źródeł X%" when the reported/derived gap exceeds 20%.

Verified with `tsc --noEmit` and a standalone `sass` compile (no dev server
in this environment).

---

## 2026-07-07 · Consolidated digest — build day (full text in `docs/changelog-archive-2026-07-07.md`)

One day, twelve entries: planning → scaffold → scrapers → analytics →
frontend → five production-debugging rounds on real tickers (SNT, CBF, DEC).
Decisions that still govern the code:

- **Architecture:** monorepo FastAPI + Next.js; PostgreSQL (SQLite in
  tests); scrapers fetch+parse+upsert only; metrics/forecast pure functions;
  one polite fetch path (`scrapers/http.py`, jittered per-domain delays,
  backoff, hard stop); 24 h page cache; changelog discipline + pre-commit
  hook; learning notes per phase (C# analogies).
- **Production topology:** Vercel + Railway, Auth.js Google allowlist,
  browser→backend only via the Next proxy with a static bearer (Phase 6).
- **Units:** statements tys. PLN; price PLN; mcap PLN;
  `eps = ttm × 1000 / shares` in exactly one place.
- **The big scraping discoveries** (all in the quirks ledger): BR slug
  redirect drops `,Q` (→ `companies.br_slug`, migration 0003); explicit
  `,Q`/`,Y` always; header-row scan + "Data publikacji" exclusion;
  `IncomeGrossProfit` actually = profit-on-sales; data-field codes are row
  identity; replace-semantics on forced refresh + ON CONFLICT upserts after
  two UniqueViolation crashes; stooq denies non-browser clients (HTTP 200
  body!); Yahoo added as price source; profile quote as last resort;
  long-form indicator labels ("Cena / Zysk") with tightened slashes.
- **Product decisions:** English nav labels, Polish domain data; refresh
  summaries with shape+range detail; `requests: ok (n HTTP)` transparency;
  diagnostics endpoints (`/health/scrapers`, mapping-report); forum upvotes
  groundwork (migration 0002); P1.9 BR premium login and P5.9 forum
  distiller planned; ESPI/EBI poller + hotness backtests parked as
  extensions.

## 2026-07-08 · Stage TH digest — investment-thesis layer

Decisions that govern the thesis layer (full per-WP detail archived in
`docs/changelog-archive-thesis-2026-07-08.md`):

- **Strategy = data, engine = generic:** a strategy is a `StrategyProfile`
  (frozen dataclasses in `services/strategies/`), the engine `thesis.py` is
  strategy-agnostic — no `if strategy == "malik"` anywhere; genericity is
  unit-tested with a toy profile. New investors = new profile modules, zero
  engine change (PLAN §10).
- **Reuse, don't recompute:** `thesis.py` consumes `insights.py` verdicts and
  never re-derives a number, so the UI can't show two values for one metric; a
  fabrication guard (shared by the deterministic and AI paths) forbids any read
  number absent from the inputs — missing indicators route to `verify_next`.
- **Deterministic-first AI (TH.2b):** `thesis_ai.py` refines the read via an
  injectable Claude transport behind a **no-key fallback** (`engine:
  deterministic|ai`); the model may reword/re-pick but weights, principle tags,
  label and disclaimer are re-imposed by us. Its transport/config/cache are
  reused by P5.4 — but the Phase-5 analysis product (`skill/`, `analyses`, AI
  tab) stays separate.
- **Honesty over a backtest:** DGN/SNT are stored as thin `WorkedCase`s with
  explicit gaps (no fabricated historical figures); the live ≥4-ticker
  cross-check is deferred to the user's machine (`scripts/validate_thesis.py`),
  never papered over. Not investment advice — entry-quality is an analysis
  entrance, never a signal.
- **Extensibility staged, not built:** WorkedCase corpus + `evaluate_case` +
  profiles-as-data make the calibration/other-investor-strategies stage a
  data exercise (new profile *versions*), not engine surgery — deliberately
  deferred this stage.
