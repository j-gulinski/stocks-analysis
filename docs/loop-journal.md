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
