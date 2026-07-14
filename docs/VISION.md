# VISION — binding intent (owner: Kuba)

This is the supreme document. Every other doc, skill, test, and code path
defers to it. Only Kuba changes this file. An agent that finds a conflict
between this file and any other artifact must treat the other artifact as
wrong and fix it.

## The idea in one sentence

**Sieve the GPW down to companies worth attention, collect their data, verify
it hard, and valuate them company-by-company — because agents can analyze a
volume of data no human investor could, and that scale is the edge.**

The four stages are a single pipeline, not four apps:

```
Discover (exclude the worst) → Research (collect + understand)
    → Valuation (the center: company-specific scenarios)
    → Portfolio (my real money, analyzed the most)
```

## Invariants (numbered — cite them in reviews)

V1. **One sieve.** Discover runs exactly one versioned Workbench strategy.
    It is exclusion-first: its job is to filter out the worst and the
    not-improving, not to rank the best. It mixes health, valuation-vs-own-
    history, and improvement factors freely. Excluded companies keep their
    kill reasons and are inspectable.

V2. **No author branding.** Source investor materials feed the strategy, but
    the product never displays tactic authors, method-pack names, or
    per-author perspectives. There is one Workbench strategy and one
    valuation engine, versioned. Provenance of source materials stays in
    `docs/source-materials/` for audit only.

V3. **Phase-aware Research.** The Research list shows substance for the phase
    each company is in — collection progress while collecting, understanding
    + main gap once researched, and a Discover-style evidence strip with the
    scenario price range once valued. Process metadata (job states, run IDs)
    never leads.

V4. **Valuation is the center and must be company-specific.** Every scenario
    set (bad / base / good, optional event) is drafted by the Codex skill
    from that company's frozen research evidence: assumptions bound to
    facts, probabilities with stated evidence rationale. Two companies with
    near-identical assumption vectors or probability mixes is a defect the
    backend rejects structurally. No template seeds, no default percentages.

V5. **Verification is adversarial or it is invalid.** A verifier that only
    confirms is failing. Every verification must attach computed evidence
    and either concrete findings or per-check justification why none exist.
    Checks that can be computed are computed by the backend and are not
    delegated to agent self-reporting.

V6. **The queue gets cleared.** Analysis throughput is the product. The
    Codex run-queue skill processes jobs until the queue is empty (with
    lease recovery and failure caps), not one-job-and-stop.

V7. **Portfolio first.** Real holdings are analyzed the most: sync
    auto-queues research and valuation for uncovered or stale holdings,
    prioritized by position weight × staleness. Import must be precise —
    real TWR/XIRR from the daily value/contribution series and operations
    history, robust ticker mapping, and reconciliation that warns instead of
    blacking out analytics.

V8. **The engine learns.** Every scenario is scored against actual results
    when the next report lands (direction, range hit, calibration). Scores
    are stored per engine version and visible. This is how the valuation
    engine improves instead of drifting.

V9. **Decision support, never commands.** No buy/sell instruction, no
    automated trading. Kuba owns every decision. Every material claim is a
    sourced fact, a deterministic calculation, a named assumption, or an
    explicit gap.

V10. **No backward compatibility.** Legacy paths are deleted, not preserved.
     One canonical implementation per capability.

## FORBIDDEN (drift alarms — grep-able)

- Multiple Discover sieves or filter tabs; any author-named sieve.
- Author names (Malik, OBS, Areczeks, Elendix, PortalAnaliz-as-method) in UI
  copy, API labels, or artifact names. (`portalanaliz.pl` may appear as a
  *data source* citation only.)
- Hardcoded scenario seeds or probabilities (`INDUSTRIAL_SEED`,
  `SOFTWARE_SEED`, 25/50/25 or any constant mix) anywhere.
- Verifier booleans accepted without computed evidence or findings.
- One-job-and-stop queue semantics; "never poll" language in run skills.
- Research list rows that lead with job/process metadata.
- Portfolio analytics fully disabled by a reconciliation mismatch.
- New "method pack", "perspective", or "persona" abstractions.

## Drift gate (mandatory before completing any slice)

1. Re-read this file.
2. Run `backend/.venv/bin/pytest backend/tests/test_vision_contract.py` —
   these tests encode the invariants; they must pass.
3. Check the FORBIDDEN list against your diff.
4. If your change makes an invariant impossible, stop and ask Kuba — do not
   reinterpret.
