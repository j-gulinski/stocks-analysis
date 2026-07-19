# Loop journal (append-only)

Iteration 1: doing the R0 BiznesRadar publication-date parser contract, touching `backend/app/scrapers/biznesradar.py`, `backend/tests/test_biznesradar_parser.py`, `docs/loop-journal.md`, `CHANGELOG.md`, and `docs/model-usage.md`, done when publication dates are retained one-to-one with selected periods as strict ISO `date` values or `None`, duplicate/skipped columns remain aligned, the metadata row is not emitted as a financial row, focused and Vision contract tests pass, and an independent verifier accepts the computed evidence.

Iteration 1 drift check:

- a. Authorized by R0: “Parse and store it per (company, period, statement) as first-class facts; backfill from stored immutable DocumentVersions (no re-scraping); fixture + tests per scraper-doctor.” This declared increment implements only the prerequisite parser contract.
- b. It preserves APPROACH's process-at-T requirement and V5/V9/V10: publication timing is retained as source metadata, unknown or malformed dates remain `None` rather than inferred, verification is independent and computed, and there is one parser path with no compatibility branch.
- c. The increment was not exceeded. The diff contains only the declared parser, parser tests and ledgers; persistence, backfill, migrations and coverage reporting remain untouched.
- d. Grep clean: added product/code lines contain no author/persona branding, probabilities, target prices or `latest` reads. No analysis path changed. Unknown publication dates are represented as `None`, never imputed.
- e. No test was weakened, skipped or deleted. Existing assertions remain and new alignment/retention assertions were added. Focused parser tests: 66 passed. Vision contract: 10 passed. `git diff --check`: clean.

Iteration 1 verification: independent read-only verifier accepted with no findings. It recomputed duplicate/skipped/malformed/missing cases, found zero mismatches across 174 recorded ABS/CRB/SNT period-date pairs, confirmed equal period/date lengths and confirmed `Data publikacji` is absent from financial rows. Live browser smoke found no regression in the eligible Discover → Research → SNT company → Valuation → Portfolio flow; the parser-only metadata is intentionally not persisted or displayed yet.

Heartbeat: Iteration 1 complete; R0 parser contract verified, ledgers updated, no owner gate blocks the next R0 increment.

Resume state:

- Last completed task: R0 Iteration 1 — `ReportTable` retains strict publication dates aligned to selected periods and excludes the metadata row from financial rows.
- Verification: 66 focused parser tests and 10 Vision tests passed; independent verifier accepted 174 recorded pairs with zero mismatches plus adversarial alignment cases; browser smoke passed; drift grep and `git diff --check` were clean.
- Current phase: R0 — Publication dates (incomplete).
- Earliest next unblocked task: declare the next bounded R0 increment for storing the parsed date per `(company, period, statement)` as a first-class fact, without yet combining it with backfill or PIT-coverage reporting unless the declaration explicitly includes them.
- Owner gates: none for the next R0 increment. The checklist strike-pass blocks R2 acceptance, myfund CSV blocks C1 in R3, SNT profile confirmation blocks its calendar job, and F13 remains an R3 owner decision.

Iteration 2: doing the R0 publication-date fact persistence contract, touching `backend/app/services/evidence.py`, `backend/app/services/refresh.py`, `backend/tests/test_evidence_ledger.py`, `docs/loop-journal.md`, `CHANGELOG.md`, and `docs/model-usage.md`, done when every parsed statement period stores one immutable source-version-bound publication-date Fact (including an explicit `not_reported` fact for an unknown date), statement/period lineage stays exact, identical refresh remains idempotent, focused and Vision contract tests pass, and an independent verifier accepts the computed evidence.

Iteration 2 drift check:

- a. Authorized by R0: “Parse and store it per (company, period, statement) as first-class facts; backfill from stored immutable DocumentVersions (no re-scraping); fixture + tests per scraper-doctor.” This increment implements only the first-class fact persistence portion.
- b. It preserves APPROACH's process-at-T requirement and V5/V9/V10: the publication date is a typed immutable source fact distinct from the actual fetch-time `known_at`; an unavailable date is stored as `not_reported`, never inferred; verification is independent and computed; and there is one canonical persistence path with no compatibility branch.
- c. The increment was not exceeded. The diff contains only the declared date-fact helper, statement refresh persistence, focused tests and ledgers; historical backfill, PIT selection, coverage reporting, schema changes and UI remain untouched.
- d. Grep clean: added product/code lines contain no author/persona branding, probabilities, target prices or `latest` reads. No analysis selector changed. Unknown and malformed publication dates are explicit `not_reported` facts with `effective_date=None`, never imputed.
- e. No test was weakened, skipped or deleted. Existing fact-count assertions advanced only by the 20 new publication facts, and new tests assert unique tuple cardinality, valid/malformed/missing dates, source lineage and idempotency. Focused parser/refresh/evidence/Vision run: 97 passed. `git diff --check`: clean.

Iteration 2 verification: independent read-only verifier passed with no findings. It recomputed 20 facts for 20 unique `(statement, frequency, period)` tuples; confirmed exact `effective_date` values and explicit `not_reported` states; bound all nine quarterly income facts to one immutable source version with `known_at == fetched_at`; confirmed identical forced refresh remains 9 documents / 9 versions / 271 facts; and confirmed a changed quarterly version advances to 379 facts while the old as-of revenue remains 50,000 and current revenue becomes 51,000. Its exact evidence/Vision command passed 18 tests. Live browser acceptance found no regression: Discover showed one `workbench_sieve_v1` with 118 survivors and inspectable gaps; Research remained phase-led; SNT showed 143.28/255.20/410.84 PLN scenarios with weighting deliberately unpublished; Valuation remained methodology/result-first; Portfolio retained TWR/XIRR and partial analytics; browser warnings/errors were empty.

Heartbeat: Iteration 2 complete; R0 publication dates now persist as immutable first-class facts, and the next unblocked R0 increment is historical backfill from stored DocumentVersions without re-scraping.
