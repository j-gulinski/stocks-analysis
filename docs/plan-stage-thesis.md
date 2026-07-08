# Stage plan — Investment-thesis layer (rule-based, pre-Phase-5)

**Status:** planned 2026-07-08. Owner: implementation sessions per WP.
**Read alongside:** PLAN §7 (metrics/frontend), §8 (AI layer — the *later*
consumer, not this stage), §10 (extension points), §13 (learning);
`services/insights.py` (this stage composes ON TOP of it);
`skills/scraper-doctor/SKILL.md` (authoritative quirks — never re-derived).

## Process & models (binding, user requirement 2026-07-08)

- Planning/orchestration: top-level session. **Implementation agents: opus.**
  **Testing/debugging/verification agents: sonnet** (plan-conformance
  verifiers count as testing).
- Loop per WP: implementation agent → separate fresh-context verifier judging
  against this plan's acceptance criteria (deviations, regressions, fabricated
  numbers, broken tests). Fail → fix → re-verify; a WP is done only after a
  verifier PASS. Stage ends with a fresh-context plan-conformance review.

## Goal

Turn the computed dossier into a **per-stock investment-thesis read in the
spirit of Paweł Malik ("OBS")**: a weighted pros/cons view, an *entry-point
quality* judgment, and a "what to check next" list — the entrance point for
deeper human analysis. The app's core purpose is weighing whether a stock is a
plausible investment (the way Malik found Digital Network / Synektik early),
using his philosophy plus general fundamental analysis. This layer is
**rule-based composition** from already-computed metrics/insights — pure
functions, like `insights.py`.

**Extensibility requirement (user, 2026-07-08):** the Malik read is the *first
instance* of a **generic investor-strategy framework**, not a hardcoded
special case. Strategy = data (criteria, weights, thresholds, per-stock
applicability); the engine is strategy-agnostic; worked examples (DGN@20, SNT)
are stored as structured cases so a future stage can calibrate weights against
them and add other investors' strategies. See "Extensibility & learning
plug-in" below.

## Non-goals (explicit)

- **No buy/sell signals.** Output is an entry point to human analysis, framed
  as such, with a standing not-advice disclaimer (PLAN §12; Malik: *"odradzam
  naśladownictwo"*).
- **Deterministic-first; Claude-API calls only via the optional WP2b refiner.**
  The WP2 engine is the default and the **only** path exercised in-sandbox or
  when no key is set. WP2b adds an *optional* engine-level iterative refiner
  **behind a no-key fallback** (`engine: "deterministic"` vs `"ai"`); still
  **no** Phase-5 `skill/`, `analysis/`, `claude_client.py`, `analyses` table, or
  AI tab (those stay Phase 5). Relationship to Phase 5: the WP1 spec is a
  *precursor input* to the future `skill/SKILL.md` (P5.1); the Phase-5 AI
  *verdict* lives in the `analyses` table + AI tab, **not** the dossier — WP2b
  only deepens the dossier's own `thesis` block, so the two don't collide. See
  WP2b.
- **No new scraping sources.** Validation reuses the existing refresh path
  only. BiznesRadar **archiwum page 1 only**, low volume, all HTTP via
  `scrapers/http.py`. Quirks (BR slug/`,Q` redirect trap, robots page-1 rule,
  price chain) are taken from `skills/scraper-doctor/SKILL.md` and **not
  re-derived**.
- **No duplication of `insights.py`.** The thesis engine *consumes* the
  `Insight` objects (which already carry verdict, importance, `brief`, comment,
  and Malik-principle wording); it must not recompute indicators or emit
  numbers that diverge from them.
- **No learning loop this stage.** Profiles-as-data + stored cases +
  `evaluate_case` make the architecture ready; the actual tuner (fitting
  weights/thresholds to example cases and other investors' analyses) is a
  future stage.

## Sandbox / testing reality (state honestly, do not paper over)

The session sandbox has **no PyPI**. Therefore:
- **Pure layers** (`services/thesis.py`, `test_thesis.py`) run **in-session**
  with the system Python + hand-built dicts/fixtures — `thesis.py` may import
  only `insights`/`metrics` (both third-party-free), keeping it runnable.
- **DB/API layers** (`dossier.py`, `api/schemas.py`) are **compile-checked**
  in-session only; wiring them needs SQLAlchemy/Pydantic.
- **Full `pytest`, migrations, and the live UI are deferred to the user's
  machine.** Every WP states which checks are in-session vs deferred.
- **No network egress (discovered in WP4):** the sandbox proxy refuses CONNECT
  to non-allowlisted hosts, incl. biznesradar.pl — live scraping is impossible
  in-session. WP4 therefore validates on recorded/synthetic fixtures and ships
  `backend/scripts/validate_thesis.py` for the live run on the user's machine.

---

## WP1 — Source-grounded strategy spec

**Scope.** Research Malik's actual philosophy from the web (blog, interviews,
podcasts, forum) and **reconcile it with what the project already encodes**
(`docs/source-materials/`, the "sweet spot < 1 mld zł" concept in
`metrics.classify_size`, the `insights.py` playbook). Produce a cited spec that
the thesis engine implements against. Verify principles against sources — do
not invent.

**Deliverables.**
- `docs/strategy-malik.md` — the spec. Sections: (a) philosophy in one page
  (stock-picking-not-timing, thesis-first, sprawozdania-first); (b) **screening
  principles table** — each row: *principle · ≥1 citation (URL + access date,
  or source-material file) · computed dossier field it maps to, OR an explicit
  "needs human/AI check" gap*; (c) **valuation doctrine** — forward C/Z vs the
  company's *own* history (prefer `latest_forecast.result.forward.pe`, fall back to
  `ttm.pe`, be honest which), margin of safety = low valuation + backlog + net
  cash together; (d) **entry-quality decision rule** with explicit thresholds
  the engine will use (see WP2); (e) reconciliation notes vs existing docs.

**Candidate primary sources** (WP1 executor verifies each resolves; not
exhaustive): portalanaliz.pl author page, gazetagieldowa.pl, YouTube interview
`TZmetBqYAOI`, "Nic za darmo" podcast #153, propfirm.pl 2026 interview,
doradca.tv write-up, X `@PawelMalik_GG`; plus the three existing files in
`docs/source-materials/`.

**Acceptance (mechanically checkable).**
1. Spec cites **≥5 distinct primary web sources**, each with a resolvable URL
   and access date, **plus** explicit reconciliation with all three
   `docs/source-materials/` files.
2. **Every screened principle has ≥1 citation.** No principle without a source.
3. Every principle row names **either** a computed dossier field **or** a
   labelled gap ("needs human/AI check") — no orphan principles.
4. The "sweet spot < 1 mld zł" claim and the forward-C/Z-vs-own-history claim
   are each backed by a citation (not asserted from the codebase alone).
5. Doc length ≤ ~3 pages; Polish domain terms, matches CLAUDE.md style.

**Verifier checklist.** Open each cited URL / confirm each source-material
quote; confirm every principle has a citation and a field-or-gap mapping;
confirm no fabricated principle (spot-check 3 against sources); confirm
CHANGELOG entry exists.

---

## WP2 — Thesis engine (backend, pure)

**Scope.** Generic, strategy-agnostic thesis engine + the Malik strategy as
its first data-defined profile. New package `backend/app/services/strategies/`:

- `base.py` — the **common strategy interface** as dataclasses:
  `StrategyProfile` (id, label, spec-doc ref) holding `Criterion` entries
  (id, investor-principle tag, dossier-field selector, direction, weight,
  thresholds, applicability by size class/sector group) + entry-quality rule
  parameters. Pure data + tiny helpers; no I/O.
- `malik.py` — the **Malik profile as data only** (weights/thresholds/
  applicability cited to `docs/strategy-malik.md` sections). No engine logic.
- `cases.py` — `WorkedCase` schema (ticker, as-of, partial input snapshot with
  per-field source labels, expected read, citation, gaps list) +
  `evaluate_case(profile, case)` helper. DGN@20/SNT content lands in WP4.
  This seeds the future calibration set; no tuner now.

New pure module `backend/app/services/thesis.py`:
`build_thesis(inputs, profile) -> InvestmentThesis` — composes the read from
the existing dossier pieces for ANY profile. **Consumes**
`insights.CompanyInsights` + `prescore` + `pe_history` + `ttm` + `net_cash` +
`dividends` + `latest_forecast`; **recomputes nothing**. Weighs what was
fetched — a missing indicator is weighed as absent, never invented. All
Malik-specific numbers/labels live in `malik.py`, none in `thesis.py`.

**Output** — dataclass `InvestmentThesis` (mirrors `insights.py` style;
`to_dict()` shape below), added to the dossier as `thesis`:
- `entry_quality: {code, label, rationale}` — `code ∈ {attractive, neutral,
  weak, insufficient_data}`; Polish label + composed rationale. **Framed as an
  entry point for analysis, not a buy signal.**
- `pros: list[{id, text, weight, principle}]`, `cons: […]` — weighted,
  ordered by weight desc; `text` drawn from the source `Insight.comment/brief`;
  `principle` = the Malik principle tag from WP1.
- `verify_next: list[{id, text, why}]` — "Co sprawdzić dalej": composed from
  `insights.missing[]`, one-off risk, and the principles WP1 marked
  "needs human/AI check" (backlog/catalyst, management credibility, thesis
  re-verification after next report). This is the human-analysis entrance.
- `thesis_read: str` — composed Polish paragraph weighing pros vs cons (values
  quoted from computed fields), ending with `disclaimer`.
- `disclaimer: str` — fixed Polish not-advice line.
- `valuation_basis: str` — states whether forward (`latest_forecast.result.forward.pe`)
  or trailing (`ttm.pe`) C/Z was used, and flags when no forecast exists.
- `strategy: {id, label}` — which profile produced the read (first: `malik`).

**Reference entry-quality rule (WP1 confirms/tunes against sources):**
`attractive` = valuation good (C/Z < 0.85× own median, forward preferred)
AND a visible growth signal (revenue-growth good OR gross-margin rising OR
net-profit-trend good) AND net cash ≥ 0, with no dominant red flag; small/micro
size adds weight (sweet spot). `weak` = valuation above own median ("market
already pricing the improvement") OR ≥2 high-importance `bad` factors OR net
loss with net debt. `insufficient_data` = fewer than 3 computable key
indicators OR neither a valuation nor a growth signal available. Else
`neutral`. All thresholds/weights live as data on the Malik profile in
`malik.py` (cited to the spec); the engine reads them from the profile and
contains no strategy-specific literals.

**Wiring.** `dossier.build_dossier` calls
`thesis.build_thesis(..., profile=MALIK)` after `insights` (Malik = the only
registered profile this stage); `api/schemas.py` gains `ThesisOut` (incl.
`strategy`) nested in `DossierOut`.

**Acceptance.**
1. `thesis.py` + `strategies/*` are pure (imports only `insights`/`metrics`/
   stdlib) and import cleanly under system Python **in-session**.
2. New `backend/tests/test_thesis.py` runs **green in-session** over ≥3
   archetypes (small profitable industrial → `attractive`/`neutral`; a
   large/`moloch` cap → sweet-spot penalty; a cash-burning biotech →
   `weak`/`insufficient_data`), asserting: every pro/con/`verify_next` text is
   traceable to an input field; **no number appears that is not in the inputs**
   (fabrication guard); missing inputs route to `verify_next`, never to a
   fabricated pro/con; disclaimer present.
3. Engine **reuses** `Insight` objects — a spot-check shows thesis numbers
   equal the corresponding `insights` numbers (no divergence).
4. `dossier.py` + `schemas.py` **compile-check** in-session; full `pytest`
   deferred (noted in CHANGELOG).
5. Money/format rules honoured (tys. PLN statements; PLN mcap/price; `pl-PL`;
   reported mcap beats price×shares — inherited via `ttm`). Idiomatic,
   commented-why, C# analogy in the learning note (WP5).
6. **Genericity tested:** `test_thesis.py` runs the engine with a second, toy
   profile (different weights/thresholds/applicability) over the same inputs
   and asserts the read changes accordingly; `thesis.py` contains **no
   strategy-specific literals** (thresholds/weights only in `malik.py`).
7. `cases.py` defines `WorkedCase` + `evaluate_case`, unit-tested on a
   synthetic case (DGN/SNT content arrives in WP4).

**Verifier checklist.** Re-run `test_thesis.py` in-session; diff-review
`thesis.py` for any literal number not sourced from inputs; grep `thesis.py`
for strategy-specific thresholds (must live in `malik.py` only); confirm the
toy-profile genericity test exists and passes; confirm forward-C/Z preference
+ honest fallback; byte-compile `dossier.py`/`schemas.py`; confirm CHANGELOG
entry.

---

## WP2b — Iterative Claude-API thesis refiner

**Scope.** An **optional** engine component that takes the deterministic
`build_thesis` output and **iterates with the Claude API** to refine it against
the stored `WorkedCase` corpus while following the active `StrategyProfile`.
**Deterministic-first:** with no key (the sandbox default) the refiner returns
the WP2 read verbatim, marked `engine: "deterministic"`. This is **not** the
Phase-5 analysis product (that stays `skill/` + `analyses` table + AI tab — see
reconciliation); WP2b deepens the dossier `thesis` block only.

**Deliverables.**
- **ONE new module** `backend/app/services/thesis_ai.py` —
  `refine_thesis(inputs, profile, *, transport=None, settings=None) -> dict`
  (`InvestmentThesis`-shaped, plus an `engine` provenance key and an optional
  `ai_notes` block). Holds the bounded iteration loop, the injectable transport,
  the validation/fabrication guard, and the JSON-file cache. No new table,
  endpoint, or `skill/`.
- **Injectable transport.** `transport` is a callable `(messages, model) ->
  dict`. `default_transport()` tries `import anthropic` (lazy, *inside* the
  function) and falls back to a stdlib `urllib.request` POST to
  `https://api.anthropic.com/v1/messages` — so the module imports and tests run
  with **no PyPI**. In-session tests inject a `StubTransport` (scripted
  responses). The default transport is never exercised in-session (no egress).
- **Config** (added to `Settings` in `config.py`, read via `get_settings()`;
  documented in `.env.example`; never committed): reuse `anthropic_api_key`,
  `anthropic_model`; add `anthropic_max_iterations: int = 2` (small default) and
  `ai_cache_enabled: bool = True`. Cache dir `backend/.cache/thesis_ai/` added to
  `.gitignore`.
- **Iteration protocol** (bounded N = `anthropic_max_iterations`): each round
  sends (a) the full `ThesisInputs` serialized, (b) the active `StrategyProfile`
  rules serialized, (c) the `WorkedCase` corpus (comparison set). The model
  returns structured JSON = a refined thesis in the **same `InvestmentThesis`
  shape** + per-change rationale + case-similarity notes. A validation layer
  enforces the schema and **strips/rejects any number not present in the
  supplied inputs** — the WP2 fabrication guard applies to the AI path too.
  Iteration **stops early** on convergence (a round makes no change) or on
  validation failure (fall back to the last valid refinement, else the
  deterministic read). The fixed Polish `DISCLAIMER` + not-a-buy-signal framing
  are re-imposed on every AI output.
- **Caching.** Simple JSON file per key `(ticker, input-hash, model,
  profile-version)` under the gitignored cache dir; a hit skips the transport
  (cost control). A DB `analyses`-style cache table is the later option —
  **noted, not built**.
- **Provenance.** The dossier `thesis` block carries `strategy {id,label}` (WP2)
  **and** `engine ∈ {deterministic, ai}`; `ai_notes` (iterations, per-change
  rationale, case-similarity) is present only on the AI path.
- **Wiring.** `dossier.build_dossier` calls `refine_thesis(...)` in place of the
  raw `build_thesis(...)` for the thesis block; with no key this is a
  transparent pass-through (identical body + `engine: "deterministic"`).

**Acceptance (mechanically checkable, no real key required).**
1. `thesis_ai.py` imports cleanly under system Python **in-session** (the SDK
   import is lazy/guarded; only stdlib + `insights`/`thesis`/`strategies` load
   at import time).
2. New `tests/test_thesis_ai.py` runs **green in-session** with a
   `StubTransport`, covering: (a) **happy path** → a valid refinement merges,
   `engine == "ai"`; (b) **malformed response** → clean fallback to
   last-valid/deterministic, **no exception**; (c) **iteration limit** →
   transport called ≤ `max_iterations`, never more; (d) **fabrication guard** →
   a scripted number absent from the inputs is stripped/rejected and the final
   read contains **no number not in the inputs** (same guard as
   `test_thesis.py`); (e) **convergence** → an unchanged round stops early.
3. **No-key fallback:** with `anthropic_api_key = None`, `refine_thesis` returns
   exactly `build_thesis(inputs, profile).to_dict()` plus `engine:
   "deterministic"`, and **never raises** (asserted).
4. **Caching:** two identical calls with a counting stub invoke the transport
   **once** and write one JSON file under the gitignored dir;
   `ai_cache_enabled = False` bypasses the cache (asserted via call count).
5. **Provenance + framing:** every AI-path output carries `engine: "ai"`,
   `strategy`, and the fixed `DISCLAIMER`; the deterministic path carries
   `engine: "deterministic"`. **No secret literal** in code; `.env.example`
   lists the four config vars; `.gitignore` ignores the cache dir.
6. **Deferred real call** (documented, not run in-session): `cd backend &&
   ANTHROPIC_API_KEY=… python scripts/thesis_ai_smoke.py SNT` runs one real
   refinement against the live Messages API and prints `engine`, the iteration
   count, and the refined read. The exact command + env var are stated here and
   in the CHANGELOG.

**Verifier checklist.** Re-run `test_thesis_ai.py` in-session (stub) → green;
confirm the five scripted paths + no-key fallback + cache tests exist; grep
`thesis_ai.py` to confirm the `anthropic` import is lazy/guarded and no API-key
literal is present; confirm the fabrication guard rejects the scripted
out-of-inputs number; confirm `.env.example` + `.gitignore` updated; confirm
`DISCLAIMER` and the `engine` marker are set per path; confirm the deferred
real-call command is documented; confirm CHANGELOG entry.

**Reconciliation with Phase 5 (P5.1–P5.6).** WP2b is an **engine-level,
deterministic-first iterative refiner of the dossier `thesis` block** — it does
**not** deliver the Phase-5 analysis product. Unchanged in Phase 5:
`skill/SKILL.md` + `rubric.md` + `examples/` (P5.1–P5.3, the analyst-instruction
set — WP2b may later consume it but does not require it now); the `analyses`
table, `POST/GET .../analyses` endpoints, **Analiza AI** tab + run history +
`AI_DAILY_LIMIT` (P5.6/P5.7); forum distillation (P5.9). What **shrinks**: the
Claude transport + `.env` config + response-cache pattern now exist (WP2b), so
P5.4 `claude_client.py` **builds on / reuses** the WP2b transport instead of
starting from scratch, and the dossier already carries the `engine` marker.
Recorded in TASKS.md Phase 5 intro — the P5 tasks are **not** rewritten.

---

## WP3 — Thesis rendering (frontend)

**Scope.** New `frontend/src/components/ThesisPanel.tsx`, rendered on the
Overview tab **at the top** — order becomes: **Teza inwestycyjna** (thesis) →
**Analiza spółki** (`InsightsPanel`, the per-indicator evidence) → **Prescore
strategii** → chart. Thesis is the synthesis; insights are the evidence it is
built from.

**Deliverables.**
- `ThesisPanel.tsx`: entry-quality badge + rationale, weighted **Mocne strony
  tezy** / **Ryzyka dla tezy**, **Co sprawdzić dalej** list, `thesis_read`
  paragraph, `valuation_basis` note, a small "wg strategii: <label>" chip
  (from `thesis.strategy`) **and a small `silnik: deterministyczny/AI`
  provenance chip** (from `thesis.engine`, WP2b), disclaimer.
- `src/lib/types.ts`: `Thesis` interface (incl. `engine`) + `Dossier.thesis`.
- `stock/[ticker]/page.tsx`: render `ThesisPanel` above `InsightsPanel` with a
  `Teza inwestycyjna` section label.

**Acceptance.**
1. Values render **as-is** from the backend (no client-side number formatting —
   same rule as `InsightsPanel`).
2. Empty/degraded states handled: `insufficient_data` shows a clear Polish
   message, not a blank card; missing forecast shows the trailing-C/Z note.
3. Nav/tab labels English, domain content Polish (user decision).
4. `npm run build` / typecheck is **deferred to the user's machine** (stated);
   in-session check = types align with `ThesisOut` (field-by-field diff).
5. **Engine provenance chip** renders `silnik: deterministyczny` or `silnik: AI`
   from `thesis.engine`; degraded / `insufficient_data` states are **unchanged**
   regardless of the `engine` value (deterministic vs ai).

**Verifier checklist.** Diff `types.ts` against `schemas.ThesisOut`
field-by-field; read `ThesisPanel.tsx` for as-is rendering + disclaimer +
degraded-state branch; confirm Overview order; confirm CHANGELOG entry.

---

## WP4 — Validation: DGN/SNT historical + current-cap sanity

**Scope.** Two parts, honesty first. (1) **Historical catches** — would the
criteria have flagged **Digital Network (DGN) near 20 PLN** and **early
Synektik (SNT)**? (2) **Current sanity** — run on several current small/mid/
large caps for correctness (numbers traceable) and comparability (engine reads
sensibly across sizes/sectors). Refresh is low-volume, **archiwum page 1
only**, via `scrapers/http.py`; confirm DGN/SNT slugs resolve using the
scraper-doctor redirect-trap note — **do not re-derive** it. No new sources.
**Engine-path note:** WP4 validation runs the **deterministic** engine (no key
in the sandbox); the AI refiner (WP2b) is exercised only via the stub transport
in `test_thesis_ai.py`, with the real-call check deferred to the user's machine.

**Deliverables.**
- `docs/validation-thesis.md`: per ticker — engine `entry_quality`, top
  pros/cons, and **hand-checked numbers vs the dossier API / BiznesRadar**;
  plus an explicit **gaps** subsection.
- Historical subsection: for DGN/SNT, reconstruct only what BR history depth +
  the forum digest actually permit; **document what cannot be reconstructed**
  (e.g. fundamentals at the past entry date, delisting/rename, shallow own-C/Z
  history) rather than fabricating a backtest.
- DGN + SNT recorded as structured `WorkedCase` entries (via
  `strategies/cases.py`): partial inputs with per-field source labels,
  expected read, explicit gaps. These seed the future calibration set;
  `evaluate_case` runs on whatever input subset exists.

**Acceptance.**
1. **≥4 current tickers** covering ≥1 small (or micro), ≥1 mid, ≥1 large —
   each with `entry_quality` and **every reported number cross-checked**
   against the dossier/BR (deviations noted). *Sandbox rescope (no egress):
   in-session this runs fixture-based plus engine-level comparability; the
   live ≥4-ticker run executes via `scripts/validate_thesis.py` on the user's
   machine and its results get appended to the validation doc. The deferral
   must be explicit in the doc — never papered over.*
2. Comparability holds: a large WIG20-style "moloch" carries the sweet-spot
   penalty; a profitable small-cap with low own-history C/Z + net cash reads
   toward `attractive` — documented, not asserted.
3. DGN + SNT each have a written verdict on whether criteria *would* have
   flagged them, **with a gaps list** where data doesn't allow it. No invented
   historical figures — any number is labelled with its source or marked
   unavailable.
4. Politeness respected: refreshes are archiwum-page-1, low volume; no
   pagination; note in the doc that the quirks ledger was followed, not
   re-derived.
5. DGN/SNT `WorkedCase` entries exist, load, and `evaluate_case` runs on them
   (or the doc states exactly why inputs are too thin to evaluate).

**Verifier checklist.** Re-fetch 1–2 tickers' dossiers and re-check a sample of
the documented numbers; confirm each historical claim is either sourced or
marked unavailable (no bare numbers); grep the diff/doc for any `,2`/`,3`
archiwum pagination (must be none); confirm CHANGELOG entry.

---

## WP5 — Final conformance + memory/changelog

**Scope.** Verify all WP acceptance criteria are met end-to-end; run every
in-session-runnable test; then compact the memory.

**Deliverables.**
- `docs/learning/phase-thesis.md` (≤1 page): what was built, 3–5 concepts, C#
  analogies (e.g. thesis engine ≈ a pure mapping/aggregation service over DTOs;
  weighting ≈ a strategy-pattern scorer), where to look in the code.
- CLAUDE.md on-demand doc index updated to list `docs/strategy-malik.md`.
- Final CHANGELOG entry (date · scope · what + why + decisions) summarising the
  stage; per-WP entries may also exist.

**Acceptance.**
1. `pytest`-in-session subset (pure layers: `test_thesis.py`, and unaffected
   `test_insights.py`/`test_metrics.py`) green; DB/API compile-checks pass;
   deferred checks explicitly listed.
2. CLAUDE.md doc index references the new spec; learning note present with C#
   analogies; final CHANGELOG entry present.
3. A fresh-context reader can, from this file alone, tell for each WP whether
   it passed.

**Verifier checklist.** Run the in-session test subset; open CLAUDE.md and
confirm the index entry; confirm learning note + final CHANGELOG entry;
re-read each WP's acceptance and tick it against the delivered artifacts.

---

## Risks & honesty rules (binding)

- **Historical fundamentals may be unavailable.** BR pages are current; own-C/Z
  history is only as deep as BR shows; DGN may be renamed/delisted. WP4
  **documents these gaps rather than faking a backtest.** No historical number
  without a source or an "unavailable" label.
- **Missing indicator ≠ invented verdict.** Weigh what was fetched; route gaps
  to `verify_next`. The fabrication guard in `test_thesis.py` enforces this.
- **Don't duplicate `insights.py`.** Thesis is synthesis + weighting + entry
  judgment + verify-next + not-advice framing; it reuses `Insight` numbers so
  the UI never shows two different values for the same metric.
- **Not investment advice.** Standing disclaimer; entry-quality is an analysis
  entrance, never a signal.
- **Scraping stays polite.** No new sources; archiwum page 1 only; quirks from
  the ledger, not re-derived.
- **Simple first, but strategy-as-data.** Profiles/cases are plain typed data
  modules (no YAML/DB/config parsing, no ML, no tuner this stage); the only
  "config surface" is the `StrategyProfile` interface the user asked for.

## Extensibility & learning plug-in (user requirement 2026-07-08)

The Malik thesis is instance #1 of a generic framework. Next evolutions add
other investors' strategies and learn from worked examples. Plug-in points:

- **New investor strategy** = a new data profile module in
  `services/strategies/` (criteria/weights/thresholds/applicability citing its
  own spec doc) + registration; zero engine changes expected.
- **Calibration set / comparison corpus** = `WorkedCase` entries (DGN@20, SNT
  first; later more, incl. other investors' documented catches). Cases carry
  partial inputs + expected reads + explicit gaps, so evaluation stays honest.
  **Now** this same corpus is the comparison set sent to the WP2b Claude-API
  refiner each round (compare the live stock against the stored successes).
- **Future learning stage** (NOT built now) deepens the refiner three ways:
  (a) **grow the corpus** with other investors' worked examples (more
  `WorkedCase` entries → a richer comparison set for the API calls); (b) **tune
  profile weights/thresholds** from `evaluate_case` results across the case set;
  (c) let the **refiner propose profile adjustments** stored as new profile
  *versions*. Profiles are data, so every tuning = producing a new profile
  version (DB/JSON serialization of profiles is the natural extension then);
  example analyses from other investors land as new cases + new profiles, not
  engine code.

## Stage tasks

Tracked in `TASKS.md` under **Stage TH — Investment-thesis layer** (IDs
`TH.1`–`TH.5` plus `TH.2b`, stable for referencing in sessions, e.g. "do
TH.2b").
