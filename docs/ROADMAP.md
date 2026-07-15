# Delivery roadmap

The only live delivery document. Defers to `docs/VISION.md`. The 2026-07
reset replaced the three-sieve / method-pack contract with the single
Workbench strategy pipeline; legacy paths are deleted, not preserved (V10).

## Current state (2026-07 reset)

Foundations that stay: FastAPI + Next.js, immutable document/snapshot
lineage, `ResearchCase`, deterministic engines, the `AgentRun` DB queue with
Codex-host execution, drafter/verifier separation.

The 2026-07-14 live acceptance review disproved the prior S2/S3 completion
claims: legacy `valuation-snapshot-v1` rows were still selected as current,
author-labelled judgment and 30/50/20 probabilities reached the UI, Research
was led by verifier-process warnings, and the company renderer expanded nearly
the full snapshot. Tests were green because they covered new writes, not legacy
current-read eligibility or the reading hierarchy. S2 and S3 are therefore one
reopened recovery slice; S4 does not resume until it passes.

The first `verify-workbench-vision` browser run reproduced the same failures on
the running app: the Research agenda was filled by historical-verifier notices,
the ABS page led with that warning and rendered every numbered section open,
and `/valuation/ABS` placed the editable assumption grid before the scenario
result. ABS still displayed 30/50/20. Discover passed the one-sieve smoke and
Portfolio kept partial analytics visible, proving that a green regression suite
was supporting evidence but not an S2–S3 acceptance verdict.

The recovery implementation has canonical current-read selectors, a
result-first/collapsed-detail renderer, and a one-file clean baseline. The
2026-07-15 baseline audit then found stale artifact tables and an incomplete
valuation-specificity vector. The baseline was regenerated after deleting those
paths, the disposable local database was recreated again, and Discover plus the
stored Portfolio snapshot were rehydrated. Research and Valuation are now
honestly empty: recreating a user-selected company artifact is a cost-bearing
action that awaits Kuba's renewed authorization rather than silently restoring
the retired SNT rows.

The 2026-07-14 owner review then rejected the economic content of that SNT
artifact. The Research run missed issuer evidence that was publicly available
for the Syn2bio non-cash demerger, retained radiopharma business, order book and
recurring revenues; the valuation misread BiznesRadar forward trading C/Z as a
target multiple, discounted both earnings and the multiple, and attached
32/46/22 probabilities without a computable calibration trail. S2–S3 is
therefore reopened again on outcome quality, regardless of its green schema and
browser checks. The shared polite fetcher was sending Requests' default
user-agent because `setdefault` did not replace it; after correcting that policy,
the issuer index plus H1, ESPI 23, ESPI 28 and ESPI 36 were retained canonically.
Kuba then explicitly authorized continuing SNT under the frozen profile. The
2026-07-15 successor uses retained issuer evidence and BiznesRadar consensus as
the baseline expectation curve rather than as a valuation answer. Research
first failed strict review on claim classification and net-income scope, was
repaired, and passed with the stale frozen-profile wording preserved as a minor
finding. Valuation Run 4 was rejected because its frozen Research lineage and
capital-cost/multiple anchors were not auditable. Run 5 repaired those defects
and passed: `valuation-engine-v3` now models a 78/365 FY2026 stub plus four full
years, keeps the PLN 261.324m Syn2Bio gain non-recurring, separates FCFF DCF
from own-history P/E and EV/EBITDA cross-checks, and reverse-solves the current
price. Probability posture is uncalibrated, so no scenario percentage or
weighted target is published. Browser verification found and then closed one
V4 rendering defect: five-year paths, sensitivity and reverse expectations are
now visible rather than trapped in the artifact payload. A later cross-stage
strict review caught one remaining severity-2 contradiction: Discover still
ranked SNT on the Syn2Bio-distorted `+1953.65%` net-profit growth and `5.97x`
C/Z even though valuation excluded the same one-off. Market batch v6 now
freezes the detailed continuing-operation bridge and uses `+80.6217%` and
`21.7714x`, preserves raw/correction lineage, and blocks comparison with raw
C/Z history. Fresh batch #2 moves SNT from #5/80.7 to #26/63.2. The same repair
places the pre-demerger multiple caveat adjacent to valuation methods. A fresh
independent verifier recomputed the batch and valuation fingerprints and passed
the result with no severity-1/2 findings. S4 still waits for Kuba's economic
acceptance of this output.

Kuba then rejected the valuation's treatment of future potential and directed
an authenticated review of an eight-thread user-nominated PortalAnaliz cohort,
prioritizing cases with benchmark-relative self-reported outperformance while
retaining weaker and contrary evidence. The robust author-neutral mechanic was
not a higher multiple or a
second lens: observable operating drivers must bridge into forecast lines,
capital needs and the hurdle already embedded in price. The sole canonical
contract therefore advances to `company-valuation-v4` /
`valuation-snapshot-v3` / `valuation-engine-v4`. Every core scenario now uses
the same named company drivers; five fiscal-period revenue, EBITDA-margin,
depreciation, capex, NWC, tax and financing contributions reconcile exactly to
the five-year path (including scenario-vs-base anchor deltas); terminal growth
reconciles to reinvestment × incremental ROIC; deterministic output exposes
runway, cash conversion, price hurdles, DCF present-value gaps and annualized
future-relative repricing. No investor
identity, portfolio execution rule or default probability enters the product.

## Current execution order

This section is the only implementation plan. Do not create a competing plan,
task diary or handoff document.

| Order | Roadmap outcome | Observable exit gate | Codex route | Status |
|---|---|---|---|---|
| 1 | S2–S3 canonical Research + Valuation implementation and legacy deletion | Finish the canonical Research/Valuation schema, services, API and UI; delete every legacy Research/Valuation engine path, verifier adapter, method/author field and compatibility branch rather than filtering it; Research leads with phase substance; company view shows valuation/Brief first with independent collapsed details/evidence; Valuation leads with methodology and result, exposes an exact evidence→driver→forecast→value bridge, reinvestment/runway, Street variance, five-year paths, independent methods, sensitivity and reverse expectations; owner acceptance requires economically valid source use plus either a computed probability tree or explicit non-publication | Product/deletion boundary: `gpt-5.6-sol` high. Bounded implementation: `gpt-5.6-terra` medium. Mechanical deletion/tests: `gpt-5.3-codex-spark` when available, else `gpt-5.6-luna` low with the fallback recorded. Independent acceptance: `gpt-5.6-sol` high | implemented and independently code-verified · canonical v4/v3 potential bridge, 361-test deterministic suite, build and honest-empty live flow pass; a representative cost-bearing canonical artifact and its company-specific browser/economic acceptance await owner authorization |
| 2 | Clean baseline + empty-database rebuild + S5 queue gate | Only after order 1 code is finished: delete all historical Alembic revisions, generate one canonical baseline migration from the final models, drop and recreate the entire local PostgreSQL database, migrate empty → head, prove ORM/schema parity, refetch the market/source corpus, sync Portfolio, rebuild only canonical Research v3 and valuation-snapshot-v3/engine-v4 artifacts, and drain the queue to empty; no row, schema column, enum, API response or UI label from a legacy engine survives; browser proves Discover → Research → company → Valuation → Portfolio | Schema/reset mechanics: no model or `gpt-5.3-codex-spark` when available. Queue orchestration: `gpt-5.6-terra` medium. Research drafts: `gpt-5.6-terra` high. Valuation drafts and strict verification: `gpt-5.6-sol` high | reopened · regenerated baseline, PostgreSQL empty→head parity, Discover refetch and Portfolio sync pass; the canonical Research/Valuation queue rebuild awaits renewed owner authorization |
| 3 | S4 Portfolio precision + auto-coverage | Real TWR/XIRR, mapping and reconciliation gates pass; sync queues canonical coverage by weight × staleness; only current verified v3 valuations aggregate | Deterministic math: no model. Implementation and ordinary portfolio interpretation: `gpt-5.6-terra` medium. Complex cross-company synthesis: `gpt-5.6-sol` high. Strict verification: `gpt-5.6-sol` high | paused · S2–S3 economic acceptance reopened |
| 4 | S6 Outcome scoring | First actual report scores direction, range hit and calibration against a canonical v3 valuation; result visible per engine version | Scoring: no model. Explanation/UI: `gpt-5.6-terra` medium. Method review: `gpt-5.6-sol` high | queued |
| 5 | S7 Report-calendar awareness | Report dates drive idempotent re-Research/re-Valuation around publication | Collection/normalization: no model. Calendar wiring: `gpt-5.6-terra` medium. Mechanical tests: `gpt-5.3-codex-spark` when available, else `gpt-5.6-luna` low with the fallback recorded | queued |
| 6 | S8 Point-in-time replay gate | Frozen universe, adjusted total returns and holdout support the first defensible performance evaluation | Replay math: no model. Architecture and methodology: `gpt-5.6-sol` high. Independent audit: `gpt-5.6-sol` high | blocked · historical data missing |

## Slice history

| # | Outcome | Exit gate | Status |
|---|---|---|---|
| S0 | Binding docs + executable drift gate | VISION/PRODUCT/STRATEGY/AGENTS rewritten; `test_vision_contract.py` passes and fails on planted drift | complete · 2026-07-14 |
| S1 | One exclusion-first sieve over expanded market snapshot | seven-page market snapshot stored immutably; `workbench_sieve_v1` returns at most 100 survivors ordered by one measurable 0–100 score + inspectable kills; single-sieve UI; forbidden: filter tabs | complete · 2026-07-14 |
| S2–S3 | Canonical Research + Valuation implementation and legacy deletion | Current execution order 1; replaces the invalid S2 complete/S3 implemented claims | v4 potential-bridge implementation and independent code verdict pass · honest-empty browser smoke passes; representative valuation rendering and owner economic acceptance await an authorized canonical artifact after the clean-baseline re-rebuild 2026-07-15 |
| S4 | Portfolio precision + auto-coverage | Current execution order 3 | paused |
| S5 | Clean-baseline data and queue rebuild | Current execution order 2 | reopened · legacy-table deletion required a regenerated clean baseline and empty-DB rebuild; Discover and Portfolio are rehydrated, canonical Research/Valuation await owner authorization |
| S6 | Outcome scoring (learning loop v1) | first scenario-outcome job scores a valued company against an actual report; calibration visible per engine version | queued |
| S7 | Report-calendar awareness | holdings' next report dates tracked; re-research/re-valuation queued around publication | queued |
| S8 | Point-in-time replay gate | frozen universe, adjusted total returns, holdout — precondition for any performance claim | blocked · historical data missing |

## External/user dependencies

- myfund operations endpoint (probe with configured key; else CSV/XLS
  export import) — affects S4 depth, not S4 delivery.
- BiznesRadar premium session for market pages where anonymous truncates.
- S8 needs point-in-time universe and total-return series.

## Definition of done for any slice

Vision drift test + focused deterministic tests green, frontend production
build green when affected, runtime healthy, and
`skills/verify-workbench-vision/SKILL.md` completed against the real primary
flow. Run the full backend suite only for release/cross-cutting risk. Update
docs/CHANGELOG/model-usage. Verification follows AGENTS.md — adversarial, with
findings or justified none; test count is never acceptance evidence by itself.
