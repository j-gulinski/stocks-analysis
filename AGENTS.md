# Stock Analysis Workbench — agent guide

Personal GPW research pipeline. The human (Kuba) owns every decision.
**`docs/VISION.md` is supreme** — read it first, always. If any doc, test,
or code conflicts with VISION, the other artifact is wrong.

## Read first, in order

1. `docs/VISION.md` — binding intent, invariants V1–V10, FORBIDDEN list,
   drift gate.
2. `docs/PRODUCT.md` — what each stage shows and does.
3. `docs/ARCHITECTURE.md` — invariants, data/source/job boundaries, model
   routing, status vocabulary, valuation gates.
4. `docs/ROADMAP.md` — live slices and gates.
5. `docs/STRATEGY.md` — the one Workbench strategy (sieve + valuation lens
   + learning loop).
6. `README.md` — stack, start/stop, test commands.
7. `skills/workbench-actions/SKILL.md` — user-triggered capabilities; update
   with every affected UI/API/CLI/queue boundary.
8. `skills/scraper-doctor/SKILL.md` — every scraper/data problem starts here.
9. `skills/verify-workbench-vision/SKILL.md` — browser-first V1–V10 acceptance
   after every implementation session; unit tests do not replace it.

`docs/source-materials/` holds evidence inputs referenced by path and
SHA-256 — never move, edit, or surface their authors in the product (V2).

## Anti-drift pipeline (mandatory)

Chat alignment does not survive sessions; only contracts do. Therefore:

1. **Start** every session by reading `docs/VISION.md` and running
   `backend/.venv/bin/pytest backend/tests/test_vision_contract.py`.
2. **During work**, when you are about to introduce any of: a second sieve,
   an author-labelled anything, a default scenario number, a self-attested
   verifier check, one-job queue semantics, or a parallel implementation —
   stop; that is drift, not design freedom.
3. **Before completion**, run the drift gate (VISION §Drift gate): vision
   tests green, FORBIDDEN list checked against the diff, invariants cited
   in your summary.
4. **Never weaken `test_vision_contract.py` to make it pass.** If an
   invariant seems wrong, ask Kuba; only he changes VISION.

## Implementation workflow

1. Classify the work with the routing table in `docs/ARCHITECTURE.md`; use
   bounded workers with disjoint targets and a separate verifier pass when
   that improves quality.
   Model names and reasoning efforts are exact requests, not decorative tier
   labels: use the lowest effective effort, record the actual host separately,
   and never describe Ultra as a model. Future slice routing belongs only in
   `docs/ROADMAP.md`; completed-run evidence belongs only in
   `docs/model-usage.md`.
2. Reproduce or trace current behavior first. Treat existing docs/tests as
   untrusted when they conflict with the user outcome or VISION.
3. Make the smallest coherent change that establishes one observable
   vertical outcome. Delete legacy paths you replace (V10).
4. Verify proportionally: run the Vision drift test and focused deterministic
   tests, then use `skills/verify-workbench-vision/SKILL.md` against the running
   app after every implementation session. A full suite is reserved for
   release/cross-cutting risk; test count never replaces browser acceptance.

## Verification quality bar (V5)

- A review that only confirms is invalid. Every verification — code review,
  artifact verification, slice acceptance — must produce either concrete
  findings (with severity and location) or a per-check justification why
  none exist, tied to computed evidence (recomputation diffs, test output,
  browser observation).
- Computable checks are computed: math, schema, lineage, fingerprints,
  duplicate-vector distance, probability structure. Agent attestation is
  acceptable only for judgment calls, and must cite the evidence examined.
- "All checks passed" with no artifacts and no findings = automatic
  rejection of the verification itself.
- Verifier and drafter are different workers; a verifier that edits the
  draft becomes a drafter and forfeits the verdict.

## Conventions

- Financial semantics in `services/fields.py`; calculations in pure, tested
  services. Prefer existing patterns.
- During ordinary work use at most one forward Alembic migration per coherent
  schema slice; local DB state is disposable and never earns compatibility or
  backfill migrations. At the active Roadmap clean-baseline gate, after the
  canonical implementation is finished, delete the historical revision chain,
  generate one baseline migration, drop/recreate the local DB, migrate from
  empty and rebuild only canonical data.
- Preserve user changes in dirty worktrees; no unrelated cleanup.
- Secrets only in `backend/.env`; never print or commit them.
- Kuba is a mid-level C# developer: explain non-obvious Python/frontend
  design with C#/.NET analogies when handing off.
- No mockups, tracked screenshots, handoff documents, competing plans, or
  archives; tests and git preserve evidence.
- Before completion: update the active Roadmap slice, `CHANGELOG.md`
  (release-level only), one concise row in `docs/model-usage.md`, and
  `skills/workbench-actions/SKILL.md` when a user-facing boundary moved.

## Branch discipline

`main` is the working/integration branch. Before integrating a remote
branch, check whether the work already exists on `origin/main`; port only
verified relevant changes. Never delete remote branches without approval.

When asked to continue until stopped, each verified bounded slice selects
the next eligible Roadmap outcome; stop only when no eligible work remains,
user or external authority is required, or a quality gate blocks progress.
