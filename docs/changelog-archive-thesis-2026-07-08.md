# Changelog archive — Stage TH (2026-07-08, investment-thesis layer)

Full text of the closed Stage-TH changelog entries — the six TH.* build entries
(TH.1–TH.5, including TH.2b), the WP4b live-run note, the WP4 sandbox-rescope
note, and the three Stage-TH plan entries — moved verbatim out of the
always-loaded `CHANGELOG.md` during the 2026-07-08 (WP1 / SC.1) memory
consolidation, mirroring `docs/changelog-archive-2026-07-07.md`. The scannable
decisions stay in the "Stage TH digest" at the bottom of `CHANGELOG.md`; the
durable technical findings live in `skills/scraper-doctor/SKILL.md` (quirks
ledger). Entries are byte-for-byte verbatim, newest first.

---

## 2026-07-08 · Stage TH complete: investment-thesis layer (TH.1–TH.5 + TH.2b)

Closing entry for the rule-based investment-thesis stage (full spec:
`docs/plan-stage-thesis.md`). The stage turns the computed dossier into a
per-stock **entry-point read** in Malik's spirit — the entrance to human
analysis, **not** a buy signal and **not** the Phase-5 AI verdict.

**What the stage delivered** (spec → engine → refiner → panel → validation):
- **TH.1** source-cited spec `docs/strategy-malik.md` (≥5 primary sources + 4
  source-material files reconciled; every principle → a computed dossier field
  or a labelled gap; Synektik "early catch" + DGN "~20 zł" entry flagged
  UNVERIFIED, not asserted).
- **TH.2** generic, strategy-agnostic engine `services/thesis.py` +
  `services/strategies/` (`base.py` StrategyProfile/Criterion/EntryQualityRule
  as frozen data, `malik.py` profile-as-data cited to the spec, `cases.py`
  WorkedCase + evaluate_case). Reuses `insights.py` verdicts, recomputes
  nothing; a fabrication guard forbids any number not in the inputs. Wired into
  `dossier.py` + `schemas.py`.
- **TH.2b** optional Claude-API iterative refiner `services/thesis_ai.py` behind
  a **no-key deterministic fallback** — injectable transport (anthropic SDK →
  stdlib urllib → StubTransport in tests), bounded iteration, the same
  fabrication guard on the AI path, JSON-file cache, `engine: deterministic|ai`
  provenance. Does **not** replace Phase 5 (`skill/`/`analyses`/AI tab).
- **TH.3** `ThesisPanel.tsx` at the top of the Przegląd tab (above
  InsightsPanel) + `types.ts`; values render as-is, degraded states handled,
  strategy + engine chips, standing disclaimer.
- **TH.4** honest validation `docs/validation-thesis.md`: the pure pipeline runs
  end-to-end on parsed pages, size-lens comparability holds (small→attractive,
  mid/large demoted by the sweet-spot penalty, expensive→weak, biotech
  cash-burn→insufficient_data); DGN/SNT recorded as thin `WorkedCase`s (all
  indicators MissingData → `insufficient_data` by construction, no fabricated
  history).
- **TH.5** this entry + `docs/learning/phase-thesis.md` (C# analogies) +
  CLAUDE.md doc index (plan/spec/validation) + TASKS.md Stage-TH ticks.

**Verification process.** Each WP: opus implementation → a separate
fresh-context verifier judging against the plan's acceptance (deviations,
regressions, fabricated numbers, broken tests); fail → fix → re-verify. Every
prior WP (TH.1, TH.2, TH.2b, TH.3, TH.4, plus the WP4b re-check) reached a
verifier PASS; this TH.5 closeout is the stage-level plan-conformance review.
Model split (user requirement 2026-07-08): planning/orchestration top-level,
implementation = opus, testing/verification = sonnet.

**Key decisions** (full rationale in the per-WP entries below): strategy = data,
engine generic (no `if strategy == "malik"`; genericity unit-tested with a toy
profile); verdicts reused from `insights.py` so the UI can never show two values
for one metric; missing ≠ invented (gaps → `verify_next`); deterministic-first
(the AI refiner is never on the critical path); not-advice disclaimer + analysis-
entrance framing on every read.

**Evidence nit fixed (WP4b re-check).**
`backend/tests/fixtures/live-20260708/SNT_income_q.excerpt.md` carried a
diagnostic prose line literally containing `<table`/`<tr`/`<td`, which
BeautifulSoup parsed as a phantom empty `<table>` — so re-running
`parse_report_table` on the excerpt raised "Report table has no rows" instead of
the claimed "No report table found". Rephrased that line (and one
`<span class="value">` mention) without angle brackets; the excerpt is now inert
and reproduces exactly `ParseError: No report table found on page.` No
parser/engine/test code touched.

**In-session verification** (system Python 3.10, no PyPI):
`PYTHONPATH=. python3 tests/test_thesis.py` → **13/13**;
`tests/test_thesis_ai.py` → **17/17**. `test_insights.py`/`test_metrics.py`
**cannot** run this way (they `import pytest` + use fixtures/parametrize) — they
run on the user's machine under pytest. *(Correction 2026-07-08, post-stage
verification: with a minimal pytest shim these DO run in-sandbox — `test_metrics`
20/20, `test_insights` 15/15; see the fresh-context verification entry at the top
of this file.)* `python -m py_compile` green on
`dossier.py`/`schemas.py`/`config.py`. Frontend `tsc --noEmit` green over the
whole app (TypeScript resolves from committed node_modules; only the npm
registry is blocked). **No Alembic migration was added this stage** (latest
remains 0004).

**REMAINING GAPS — user-machine runbook** (each needs PyPI / a DB / npm / a real
key / network egress, unavailable in-sandbox):
1. `cd backend && pytest` — full suite incl. the DB/API path.
2. Migrations: **none added this stage** — run `alembic upgrade head` only when
   bootstrapping a fresh DB (existing DBs already at 0004).
3. `cd frontend && npm run build` — full Next.js production build (typecheck
   alone already passes in-session).
4. `cd backend && python scripts/validate_thesis.py DGN SNT DEC <large-cap>` —
   the deferred live ≥4-ticker validation (small/mid/large), numbers
   cross-checked vs BiznesRadar; append results to `docs/validation-thesis.md`.
5. `cd backend && ANTHROPIC_API_KEY=… python scripts/thesis_ai_smoke.py SNT` —
   one real refinement against the live Messages API (prints `engine`, iteration
   count, refined read).

## 2026-07-08 · validation/thesis: live BR run attempt via agent web_fetch (WP4b / TH.4)

Two jobs: correct a false claim, and attempt the deferred ≥4-ticker live
validation using the agent-level `mcp__workspace__web_fetch` tool (which — unlike
sandbox Python — DOES reach biznesradar.pl).

- **Job 1 — false claim corrected.** `docs/validation-thesis.md` and the WP4
  CHANGELOG entry stated the agent `web_fetch` "też się nie łączy (timeout)" /
  "times out". **Wrong.** web_fetch connects (HTTP 200, follows the SNT→SYNEKTIK
  slug redirect). Corrected in both places; the true constraint is that sandbox
  *Python*/proxy has no egress, while the agent tool reaches BR but returns
  **markdown, not HTML**.
- **Job 2 — feasibility gate FAILED on HTML grounds → deferral stands (now with a
  precise reason).** `web_fetch` returns a stripped markdown/text extraction, not
  raw HTML: `grep -c` over a full income-statement page (72,742 chars) finds
  `report-table`/`data-field`/`span.value`/`<table>`/`<tr>`/`<td>` = **0**. Run on
  the saved markdown, the real parsers confirm it: `parse_profile` → **every field
  None** (shares/mcap/EV/sector/price/slug — all visible in the markdown, none
  reachable); `parse_report_table` → **`ParseError: No report table found`**. The
  `data-field` row-identity codes (quirks-ledger-critical) survive only inside
  sector-comparison link URLs, and value+k/k+sector are merged into one cell — so
  recovering the structure needs a brand-new bespoke markdown parser (untested;
  CLAUDE.md requires green fixture tests; bypasses the very parser stage under
  validation; hand-transcription risks fabrication). Explicitly declined as a
  disallowed workaround. **No parser was hot-fixed.**
- **Orchestrator decision (implemented + documented):** CLAUDE.md's "ALL HTTP via
  `scrapers/http.py`" governs app scraper code (left **untouched**); for THIS
  in-session validation only, fetching BR via the sanctioned `web_fetch` tool was
  permitted PROVIDED politeness was replicated manually. Executed: **2 requests
  total** (≤24 budget), ≥3 s spacing (enforced `sleep`), archiwum page-1 rule moot
  (never fetched), 0 pagination, report page by slug, both 200, 0 retries. Fetching
  stopped at the feasibility probe ("debugging never means fetch more").
- **Evidence saved** for re-check without re-fetching:
  `backend/tests/fixtures/live-20260708/SNT_profile.md` (full profile extraction)
  + `SNT_income_q.excerpt.md` (report-page excerpt + grep counts). `.md` files are
  inert to the fixture tests (which load by exact `*.html` filename, not globbing).
- **Doc:** new `docs/validation-thesis.md` §"Walidacja live (in-session, web_fetch)"
  — feasibility verdict, reproducible evidence, request log, politeness-decision
  note; acceptance table #1/#4 + the bottom politeness section updated (0→2 requests).

Tests unchanged (no engine/parser edits): `test_thesis.py` 13/13, `test_thesis_ai.py`
17/17 re-run green in-session. Still deferred: the live ≥4-ticker run + DB/API path
+ real AI call → user's machine, where `scripts/validate_thesis.py` (real HTTP via
`http.py`) works. Refs TH.4.

## 2026-07-08 · Plan: WP4 acceptance #1 rescoped to sandbox reality (no egress)

WP4 discovered the sandbox has no network egress (proxy 403s CONNECT, incl.
biznesradar.pl), so the "≥4 live current tickers" criterion cannot run
in-session. Plan amended: in-session = fixture-based validation + engine-level
comparability; the live run ships as `backend/scripts/validate_thesis.py` for
the user's machine, results to be appended to `docs/validation-thesis.md`.
Honesty rule unchanged: the deferral is explicit, never papered over.

## 2026-07-08 · validation/thesis: DGN/SNT + current-cap sanity (WP4 / TH.4)

Validated the deterministic thesis engine against what the data actually
allows, honesty first. **Findings digest:** the pure pipeline (parsers →
`fields` → `metrics` → `insights` → `build_thesis(MALIK)`) runs end-to-end over
*parsed* pages and reads sensibly; comparability holds — on identical inputs a
small cap reads `attractive` while mid/large are demoted to `neutral` by the
sweet-spot penalty (spec principle 9), `weak` fires when C/Z is above own median,
`biotech` cash-burn → `insufficient_data`. DGN/SNT could **not** be
back-tested (see below) and are recorded as honest, thin cases.

- **New `backend/scripts/validate_thesis.py`** — runs the *pure* half of
  `dossier.build_dossier` OUTSIDE the DB (no Postgres in-session): fetches BR
  pages **by slug** (redirect-trap), assembles `ThesisInputs`, prints raw parsed
  inputs + the deterministic thesis for hand-checking. ALL HTTP via
  `scrapers/http.py`; pages cached to `backend/.cache/validation/` (gitignored);
  archiwum notowań never fetched (thesis needs no price history → zero pagination
  risk). Mirrors `record_fixtures.py`'s "fetch real pages outside the DB" pattern.
- **Environment reality (stated, not papered over):** the sandbox Python/proxy has
  **no network egress** (proxy 403 to every host incl. biznesradar.pl), so
  `app/scrapers/http.py` and `scripts/validate_thesis.py` make **0 requests** — the
  plan's "no egress → fall back to recorded fixtures" path. The committed fixtures
  are synthetic and model **DECORA (DEC)**; the full pipeline ran on them (real
  *parsed-page* integration, one notch beyond `test_thesis.py`'s hand-built dicts).
  Live DGN/SNT + multi-cap fetches remain **deferred to the user's machine**
  (`python scripts/validate_thesis.py DGN`). *(Correction 2026-07-08, WP4b: an
  earlier version of this entry said the agent `web_fetch` "times out" — that was
  **wrong**. The agent-level `mcp__workspace__web_fetch` tool DOES reach BR; see the
  WP4b entry at the top of this file and docs/validation-thesis.md §"Walidacja
  live".)*
- **DGN / SNT recorded as `WorkedCase` in `strategies/cases.py` `CORPUS`** —
  partial snapshots with per-field source labels + explicit gaps; every
  indicator is `MissingData` (routed to `verify_next`, never invented), so both
  `evaluate_case(MALIK, ·)` → `insufficient_data`, `matches=True` — the honest
  consequence of the data gaps. DGN catch is verified (POS 02.2023, "+2500%/5y"
  [DGN][AUT]) but the "~20 PLN" entry is **unverified** → not used as a number;
  SNT's early-catch attribution is **unverified** → flagged, not asserted as a
  Malik catch (docs/strategy-malik.md §Unverified).
- **`docs/validation-thesis.md`** — per-ticker sections (entry_quality, top
  pros/cons, hand-checked-numbers table vs the fixture with deviations),
  comparability table, DGN/SNT verdicts + gaps, politeness note, engine-path
  note, and an honest acceptance-status table (#1 partial/deferred, #2/#3/#4/#5
  met).

Decisions/deviations: **`cases.CORPUS` built lazily** (module `__getattr__`,
PEP 562) — building a `WorkedCase` touches `thesis.ThesisInputs` and
`app.services.thesis` imports the strategies package, so eager construction
formed a circular import (thesis → strategies → cases → thesis); deferring to
first access keeps `cases.py` import-pure. **One minimal test fix:**
`test_thesis_ai.test_ai_request_payload_carries_inputs_and_profile` now passes
`corpus=()` explicitly (its `worked_cases == []` assertion predated a non-empty
default `CORPUS`); the non-empty default is covered by the injected-corpus test.
In-session: `test_thesis.py` 13/13, `test_thesis_ai.py` 17/17 green. **Acceptance
#1 (≥4 live tickers cross-checked) is only PARTIALLY met in-sandbox** (1 real
parsed-page company + size-lens comparability); live multi-cap fetches deferred
to the user's machine (egress blocked). TASKS.md checkboxes stay unticked
(verifier pass pending).

## 2026-07-08 · frontend/thesis: ThesisPanel on the Przegląd tab (WP3 / TH.3)

Renders the backend `thesis` block as the top card of the stock Overview tab,
above `InsightsPanel`. Frontend-only; no API/proxy changes (the dossier already
carries `thesis`). Values render **as-is** — no client-side number formatting,
same rule as `InsightsPanel`.

- **New `frontend/src/components/ThesisPanel.tsx`** — section "Teza
  inwestycyjna": entry-quality badge (code→tone map, Polish label from the
  backend) + rationale; weighted **Mocne strony tezy** / **Ryzyka dla tezy**
  lists rendered in the delivered (weight-desc) order with a subtle
  principle tag; **Co sprawdzić dalej** (text + why); `thesis_read` paragraph;
  `valuation_basis` note; always-visible muted disclaimer. Two small chips —
  `wg strategii: {label}` (`thesis.strategy`) and the WP2b provenance chip
  `silnik: deterministyczny|AI` (`thesis.engine`); on the AI path an optional
  minimal `model · iteracje` line from `ai_notes`.
- **Degraded states.** `entry_quality.code == "insufficient_data"` → the
  backend's clear Polish label + rationale + whatever partial lists exist (never
  a blank card); empty `pros`/`cons` → honest **brak** placeholder; a dossier
  with no `thesis` block (older cache) → panel returns `null` and the page
  guards the section label too (no orphan, no crash). Degraded rendering is
  identical for `engine` deterministic vs ai.
- **`src/lib/types.ts`** — new `Thesis` (+ `EntryQuality`, `ThesisFactor`,
  `VerifyNextItem`, `StrategyRef`, `AiNotes`) mirroring `schemas.ThesisOut`
  field-by-field (snake_case preserved). `Dossier.thesis` is **optional** on
  purpose (backend has it required) so old cached dossiers render gracefully.
- **`globals.scss`** — self-contained `.thesis` block mirroring the `.insights`
  divider/section look (insights block left untouched; a little duplication over
  a risky hoist — simple first).
- **Overview order** now MetricCards → **Teza inwestycyjna** → Analiza spółki →
  Prescore strategii → Kurs. MetricCards kept as the quick-facts header (the
  plan's order list starts at the thesis and omits it).

Decisions/deviations: `Dossier.thesis` optional (degraded-state requirement);
`weak` badge is amber not red (app reserves red for hard "minus"; this layer
emits no buy/sell signal). In-session checks: field-by-field types↔ThesisOut
diff; grep confirms no `toFixed`/`toLocaleString`/`Intl` on thesis values; JSX
read + Node brace/paren balance sanity. **`npm run build`/typecheck deferred to
the user's machine** (sandbox has no npm registry) — plan WP3 acceptance #4.

## 2026-07-08 · backend/thesis-ai: iterative Claude-API thesis refiner (WP2b / TH.2b)

Implements the optional, deterministic-first Claude-API refiner planned below.
Backend-only; frontend provenance chip is TH.3. No Phase-5 files touched (no
`skill/`, `claude_client.py`, `analyses` table, AI tab); no scrapers, no HTTP
outside the injectable transport (and the real transport is never run in tests).

- **New module `app/services/thesis_ai.py`** — `refine_thesis(inputs, profile,
  deterministic_thesis=None, *, ticker=None, corpus=None, transport=None,
  settings=None) -> dict`. Returns an `InvestmentThesis`-shaped dict + an
  `engine` marker (`"deterministic"` | `"ai"`); the AI path adds `ai_notes`
  (model, iterations, per-change rationale, case-similarity). Bounded loop of
  `anthropic_max_iterations` rounds; each round serialises the full
  `ThesisInputs` + the active `StrategyProfile` rules + the `WorkedCase` corpus
  (`cases.CORPUS`, empty until WP4) + the current read, and asks for structured
  JSON in the same shape. A **validation layer** enforces the schema (codes from
  the fixed set; pro/con ids must already exist; weight/principle/label/
  disclaimer/strategy re-imposed by us) and re-applies the **fabrication guard**
  (numbers in the read must be a subset of the inputs — the exact
  `collect_input_numbers`/`collect_read_numbers` rule shared with
  `test_thesis.py`). Early stop on convergence (a round changes nothing) or on
  malformed/validation/transport failure → fall back to the last valid round,
  else the deterministic read. The fixed Polish `DISCLAIMER` + not-a-signal
  framing are re-imposed every round.
- **Injectable transport.** `default_transport()` tries `import anthropic`
  (lazy) → falls back to a stdlib `urllib` POST to the Messages API with correct
  headers (`x-api-key`, `anthropic-version`). Tests inject a `StubTransport`
  (scripted responses); the default is never exercised in-session.
- **Config** (pydantic `Settings`, `.env.example`): reuse `anthropic_api_key`/
  `anthropic_model`; add `anthropic_max_iterations` (=2) + `ai_cache_enabled`
  (=True). Cache dir `backend/.cache/thesis_ai/` added to `.gitignore`. Settings
  are injectable so config.py/pydantic is NOT imported at module import time.
- **Cache.** JSON file per `(ticker, input-hash, model, profile id+rules-hash)`
  under the gitignored dir; a hit skips the transport. Only successful AI
  refinements are cached (a fallback is not, so a later call can retry).
- **Wiring.** `dossier.build_dossier` builds the deterministic thesis then routes
  it through `refine_thesis(...)` (key present → AI path; absent → transparent
  deterministic pass-through). `api/schemas.py` `ThesisOut` gains `engine` +
  `ai_notes`.

Why / decisions:
- **Deterministic-first, never an error.** No key ⇒ `refine_thesis` returns
  exactly `build_thesis(...).to_dict()` + `engine: "deterministic"` and never
  raises (asserted). If every AI round fails/fabricates, it falls back to the
  same body — honest marker, no `ai_notes`.
- **Same fabrication guard on the AI path.** A stray number (even a "1" in a
  suffix) invalidates the whole round → reject → fall back; the guard rule is
  literally shared with the deterministic engine so the two can't diverge.
- **Strategy data unchanged by the model.** The model may reword/reorder/re-pick
  the verdict, but weights, principle tags, the label, the disclaimer and the
  strategy block are re-imposed by the engine (honest attribution — the model
  can't relabel a general-fundamentals criterion as Malik).

Testing / sandbox reality:
- **In-session (system Python 3.10, no PyPI): `PYTHONPATH=. python3
  tests/test_thesis_ai.py` → 14/14 pass.** Stub-transport paths: happy-path
  merge (`engine: "ai"`), malformed → clean fallback, iteration-limit (transport
  called ≤ max, never more), convergence (unchanged round stops early),
  fabrication guard (out-of-input number rejected; a later fabricating round
  keeps the earlier valid one), no-key fallback (prebuilt + self-built),
  cache hit (transport once, one JSON file) / cache disabled (transport twice),
  disclaimer+strategy preserved, transport-error no-raise, and lazy-import
  proof (`anthropic`/`pydantic_settings` absent from `sys.modules`).
  `tests/test_thesis.py` re-run **13/13** (WP2 unaffected). `test_thesis_ai.py`
  uses plain asserts + a `__main__` runner (no `import pytest`), so pytest also
  collects it on the user's machine.
- **Compile-checked in-session** (`python -m py_compile`, green): `dossier.py`,
  `schemas.py`, `config.py`, `thesis_ai.py`, `scripts/thesis_ai_smoke.py`.
- **Deferred to the user's machine** (needs a real key + DB, documented in the
  plan WP2b acceptance 6): `cd backend && ANTHROPIC_API_KEY=… python
  scripts/thesis_ai_smoke.py SNT` — one real refinement against the live
  Messages API, prints `engine`, iteration count and the refined read. Full
  `pytest` (DB/API path) also deferred.
- TASKS.md TH.2b checkbox intentionally left unticked (ticked after verifier PASS).

**Post-verifier fix (same day):** review found one test-coverage defect — no
test asserted a round's actual *request* (`StubTransport` counted calls but
never recorded `messages`), so a refactor could silently drop the serialized
profile or corpus from the prompt and all tests would still pass. Fixed:
`StubTransport` now records every call's `(messages, model)` in
`self.requests`; two new tests parse the recorded prompt's DATA JSON and
assert the dossier inputs (distinctive numbers/fields), `StrategyProfile`
criteria/entry-rule, and an injected `WorkedCase` corpus (ticker/citation) are
all actually present, plus the empty-corpus case serializes as
`worked_cases: []`. Two nits also addressed: `strategies/cases.py` gains the
explicit (still-empty) `CORPUS: tuple[WorkedCase, ...] = ()` hook — the WP4
slot `thesis_ai.py` already read via `getattr(cases, "CORPUS", ())`, now
discoverable instead of relying on the getattr default — and a new test
confirms a stub response inventing a brand-new pro/con id is rejected
(schema guard was previously only code-reviewed). `tests/test_thesis_ai.py`
now **17/17 pass**; `tests/test_thesis.py` re-run **13/13**, unaffected;
import purity holds (`pydantic`/`anthropic`/`fastapi`/`sqlalchemy`/`requests`
still absent from `sys.modules`).

## 2026-07-08 · Plan: iterative Claude-API refiner added to stage TH (WP2b / TH.2b)

New binding user requirement (2026-07-08) folded into `docs/plan-stage-thesis.md`
+ `TASKS.md` **before implementation** — plan/docs only, no code. The analysis
engine gains an **optional** Claude-API integration that **iterates** with the
model to refine the thesis against the stored `WorkedCase` corpus while following
the active `StrategyProfile`, **deterministic-first behind a no-key fallback**.

- **New plan section WP2b** — one module `services/thesis_ai.py` +
  `refine_thesis(inputs, profile, transport=None)`: **injectable transport**
  (anthropic SDK if importable → stdlib `urllib` POST to the Messages API →
  `StubTransport` in tests, so it imports/tests with no PyPI); bounded N-round
  loop (config `anthropic_max_iterations`, small default) sending the serialized
  inputs + profile rules + `WorkedCase` corpus; structured-JSON refinement in the
  same `InvestmentThesis` shape; schema + **fabrication-guard** validation (no
  number absent from inputs — the AI path too); JSON-file cache keyed by
  `(ticker, input-hash, model, profile-version)` under a gitignored dir;
  early stop on convergence/validation failure; no-key fallback to the
  deterministic read.
- **Provenance:** the dossier `thesis` block gains `engine ∈ {deterministic, ai}`
  alongside `strategy`; the fixed not-advice `DISCLAIMER` is re-imposed on AI
  output; WP3 renders a `silnik: deterministyczny/AI` chip.

Why / decisions:
- **Sandbox honesty:** no PyPI + no guaranteed egress ⇒ transport is injectable
  and acceptance is checkable with a **stub** (happy / malformed / iteration-limit
  / fabrication / convergence + no-key fallback + cache); the real call is a
  deferred user-machine smoke test (`cd backend && ANTHROPIC_API_KEY=… python
  scripts/thesis_ai_smoke.py SNT`).
- **Non-goal rescoped:** the stage is no longer "no Claude-API calls" — it is
  **deterministic-first with an optional refiner behind a fallback**. Phase 5's
  `skill/`, `analyses` table, and Analiza AI tab stay Phase 5.
- **Config, no secrets:** reuse `anthropic_api_key`/`anthropic_model`, add
  `anthropic_max_iterations` + `ai_cache_enabled` to pydantic `Settings`; cache
  dir added to `.gitignore`; no key literal in code.
- **P5 reconciliation:** WP2b's transport/config/cache are **reused by P5.4**;
  P5.1–P5.3/P5.5–P5.9 (skill, full-verdict prompt, endpoints, forum distiller)
  remain the distinct *analysis product*. Noted in TASKS.md Phase 5 intro; tasks
  not rewritten; added `TH.2b`.
- **Learning plug-in deepened:** the cases corpus is the **comparison set** for
  the refiner **now**; the learning stage grows the corpus with other investors'
  examples, tunes profile weights from `evaluate_case`, and lets the refiner
  propose profile adjustments stored as **new profile versions**.

## 2026-07-08 · backend/thesis: generic thesis engine + Malik profile (WP2 / TH.2)

New rule-based investment-thesis layer that composes the dossier's insights into
a per-stock **entry-point read** (weighted pros/cons + entry-quality verdict +
"co sprawdzić dalej"). Backend-only; frontend is TH.3.

- **New package `app/services/strategies/`** (strategy = data, PLAN §10):
  `base.py` (`StrategyProfile`/`Criterion`/`EntryQualityRule`/`VerifyGap`
  dataclasses — id, principle tag, dossier-field selector, direction, weight,
  thresholds, applicability by size class/sector group), `malik.py` (the Malik
  profile **as data only**, every weight/threshold cited to a
  `docs/strategy-malik.md` section in a comment), `cases.py` (`WorkedCase`
  schema + `evaluate_case` — seeds the future calibration set; DGN/SNT content
  lands in WP4).
- **New engine `app/services/thesis.py`** — `build_thesis(inputs, profile)` →
  `InvestmentThesis.to_dict()` (`entry_quality {code,label,rationale}`,
  weighted `pros`/`cons`, `verify_next`, `thesis_read`, fixed `disclaimer`,
  `valuation_basis`, `strategy`). **Strategy-agnostic**: no Malik literal lives
  in the engine (grep-guarded by a test); all weights/thresholds come from the
  profile. **Recomputes nothing** — pro/con text is the source `Insight.comment`
  verbatim, so the UI can never show two values for one metric.
- **Wired** into `dossier.build_dossier` (Malik = the only registered profile)
  and `api/schemas.py` (`ThesisOut` incl. `strategy`, nested in `DossierOut`).

Why / decisions:
- **Verdicts reused, thresholds not duplicated.** insights.py already encodes
  Malik's numeric cut-offs (e.g. C/Z < 0.85× own median); the engine reads its
  good/neutral/bad verdicts. So `Criterion` carries *weights + applicability*,
  not raw-number thresholds — the two layers can't diverge (PLAN non-goal).
- **Forward C/Z preferred, honestly.** `valuation_basis` states forward
  (`latest_forecast.result.forward.pe`) when a forecast exists, else trailing
  `ttm.pe`, else says the valuation can't be assessed. The entry gate uses the
  (trailing-based) `pe_vs_history` verdict to avoid re-deriving; the forward
  re-check is pushed to `verify_next` (thesis_recheck gap).
- **Missing ≠ invented.** Absent indicators route to `verify_next`; the
  human/AI-check gaps (catalyst, backlog, management, cash-flow quality,
  thesis re-check) are standing profile data, always present. A fabrication
  guard test asserts **no number in the read is absent from the inputs**.
- **Not advice.** Fixed Polish disclaimer on every read; entry-quality labels
  framed as an *analysis entrance*, never a buy signal.
- **Genericity is tested**, not asserted: a second toy profile (different
  weights/thresholds, inverted size preference + one contrarian direction) over
  the same inputs flips the read (size pro→con, cheap C/Z pro→con, code
  changes).

Testing / sandbox reality:
- **In-session (system Python 3.10, no PyPI): `PYTHONPATH=. python3
  tests/test_thesis.py` → 13/13 pass.** `test_thesis.py` uses plain asserts +
  a tiny `__main__` runner so it is *also* collected by `pytest` on the user's
  machine (no `import pytest`). Covers 4 archetypes (small industrial →
  attractive; large moloch → sweet-spot penalty demotes to neutral; cash-burn
  biotech → insufficient_data; expensive → weak), the fabrication guard,
  traceability, missing-routing, disclaimer, genericity, and a synthetic
  `evaluate_case`.
- `thesis.py` + `strategies/*` import cleanly under system Python and pull in
  **no FastAPI/SQLAlchemy/Pydantic** (verified) — imports only insights/metrics/
  stdlib, per the pure-layer rule.
- **Deferred to the user's machine:** full `pytest` (incl. the DB/API path),
  Alembic, live UI. `dossier.py` + `schemas.py` here are **byte-compile
  checked only** (`python -m py_compile`, green); they need SQLAlchemy/Pydantic
  to import fully. No scrapers touched; no HTTP anywhere in this WP.
- TASKS.md TH.2 checkbox intentionally left unticked (ticked after verifier PASS
  in WP5).
- **Fix (verifier defect):** the `roe` and `net_margin` criteria in `malik.py`
  were unsourced yet presented as Malik principles (net_margin had no citation;
  roe's comment cited "principle 10", which is balance-sheet safety, not ROE —
  and `docs/strategy-malik.md` has 0 ROE/net-margin hits). Relabelled honestly as
  **general fundamental analysis, not Malik**: new `GENERAL_FUNDAMENTALS =
  "analiza fundamentalna (ogólna)"` tag namespace → principles now read `ROE —
  analiza fundamentalna (ogólna)` / `Marża netto — …`, so the verbatim `principle`
  in pros/cons no longer attributes them to Malik. Grounded in the stage goal
  ("[Malik's] philosophy plus general fundamental analysis",
  `docs/plan-stage-thesis.md` §Goal); docstring corrected to state criteria are
  spec-cited **except** the general-fundamentals-tagged entries. Criteria/weights
  kept (roe still feeds the finance playbook). `test_thesis.py` unchanged → 13/13.

## 2026-07-08 · Plan: model split + generic strategy framework (stage TH update)

User requirements applied to `docs/plan-stage-thesis.md` before TH.2 starts:

- **Process:** planning/orchestration top-level; implementation agents = opus;
  testing/debugging/verification agents = sonnet.
- **Extensibility:** the Malik thesis becomes instance #1 of a generic
  investor-strategy framework — new `services/strategies/` package: `base.py`
  (StrategyProfile/Criterion interface: criteria, weights, thresholds,
  per-stock applicability), `malik.py` (profile as data, cited to the spec),
  `cases.py` (WorkedCase + evaluate_case; DGN@20/SNT content recorded in
  TH.4). Engine `thesis.py` stays strategy-agnostic (genericity unit-tested
  with a toy profile). No learning loop this stage — plug-in points documented
  in the plan ("Extensibility & learning plug-in"). TASKS.md TH.2/TH.4
  updated accordingly.

## 2026-07-08 · Docs: source-grounded Malik strategy spec (WP1 / TH.1)

Docs-only change (no code). Added `docs/strategy-malik.md` — the cited strategy
spec the thesis engine (WP2) implements against. Researched Paweł Malik's actual
philosophy from the web and reconciled it with the in-repo source materials.

Why / decisions:
- **Every principle is sourced.** 16-row screening table, each row cited and
  mapped to a computed dossier field (`insights.py`/`metrics.py`) **or** a
  labelled gap ("needs human/AI check") — no orphan principles, no invention.
- **≥5 primary web sources** (forum IKE thread `t=569`, Stockbroker 2018
  interview, Portal Analiz *O nas* + Malik's own DGN analysis + author list,
  *Nic za darmo* #153) with URLs + access date 2026-07-08, plus reconciliation
  with all four strategy source-material files (md/txt/pdf/docx).
- **Honesty flags baked in:** the **Synektik "early" catch is UNVERIFIED** (no
  primary source found — do not assert); the **DGN catch is verified** but the
  "~20 PLN" entry price is not; the **`< 1 mld zł` size cutoff is our
  operationalisation** of his qualitative small-cap/sWIG80 preference (sWIG80
  avg cap ≈1 mld), **not** a Malik-stated number; the PDF is a *secondary*
  opracowanie (its in-quotes lines not treated as primary); [YT] transcript not
  extracted (cited by title only); "OBS"="Only the Best Stocks" is a folk gloss.
- **Valuation doctrine confirmed from sources:** forward C/Z
  (`latest_forecast.result.forward.pe`, fallback `ttm.pe`) vs the company's
  **own** history; margin of safety = low valuation + backlog + net cash
  together (backlog is a gap). Entry-quality rule from WP2 confirmed/tuned:
  profit-quality (`one_offs`) acts as a veto; catalyst is uncomputable so a
  data-only `attractive` is provisional and must push catalyst → `verify_next`.
- Two sourced **evolutions** noted (foreign stocks; holding horizon) so WP2
  doesn't flatten them. No code touched; CLAUDE.md index update deferred to WP5.

## 2026-07-08 · Docs: investment-thesis stage plan (rule-based, pre-Phase-5)

Planning-only change (no code). Added `docs/plan-stage-thesis.md` — the stage
that turns the computed dossier into a per-stock investment-thesis read in
Malik's spirit: weighted pros/cons + entry-point quality + "what to check next"
(entrance for human analysis, **not** a buy signal). Composed by pure functions
ON TOP of `services/insights.py` — reuses `Insight` numbers, recomputes nothing.

Why / decisions:
- **Distinct from Phase 5.** This is deterministic rule-based composition; the
  Claude verdict (PLAN §8) stays later and lives in `analyses`, so the new
  dossier `thesis` block does not collide. The WP1 strategy spec
  (`docs/strategy-malik.md`) is a *precursor input* to the future `skill/`.
- **Honesty baked into acceptance:** DGN/SNT historical validation documents
  data gaps rather than faking a backtest; missing indicators route to
  `verify_next`, never to invented verdicts; a `test_thesis.py` fabrication
  guard forbids numbers not present in inputs.
- **Sandbox reality stated:** pure `thesis.py`/`test_thesis.py` run in-session
  (no PyPI); `dossier.py`/`schemas.py` compile-checked; full `pytest` + UI
  build deferred to the user's machine.
- **Scraping unchanged:** validation reuses refresh, archiwum page 1 only,
  quirks from `skills/scraper-doctor/SKILL.md` not re-derived; no new sources.
- Five work packages WP1–WP5 with mechanically-checkable acceptance +
  per-WP verifier checklists; tasks `TH.1`–`TH.5` added to `TASKS.md`.

