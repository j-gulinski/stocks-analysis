# Agent loop protocol — continuous execution without drift

Paste-trigger for a session (Claude Code or any agent runner):

> Read docs/agent-loop.md and execute the loop from step 1. The live
> plan is docs/plans/refactor-plan.md; binding intent is docs/APPROACH.md.
> Owner gates currently open: [strike-pass pending / myfund CSV pending /
> SNT profile pending — edit to match]. Begin.

## The loop

1. **Orient (every iteration, no exceptions).** Read, in order: the 10
   invariants in `docs/APPROACH.md`, the current phase in
   `docs/plans/refactor-plan.md`, the last 5 rows of
   `docs/failure-ledger.md`, the tail of `CHANGELOG.md` and
   `docs/loop-journal.md`. Select the **earliest incomplete task in the
   earliest incomplete phase** that is not behind an owner gate. Never
   invent tasks not in the plan.
2. **Declare the increment.** Write one sentence into the journal:
   "Iteration N: doing X, touching files Y, done when Z." The increment
   must be shippable in ≤ ~1 hour of work. Parsers start with a recorded
   fixture (scraper-doctor protocol).
3. **Implement.** Smallest change that satisfies Z. Plumbing goes to
   code, never into skills.
4. **Verify (separated).** Run focused tests + the invariant/contract
   test. Where the runner supports subagents, verification runs in a
   context that did not write the code; the verifier must return
   findings or a per-check justification — an empty "all good" is
   rejected and the iteration repeats.
5. **Drift check (the gate before every commit).** Answer in writing,
   in the journal:
   - a. Which plan line authorizes this change? (quote it)
   - b. Which invariants does it touch, and how are they preserved?
   - c. Did I exceed the declared increment? If yes: revert the excess
     first, commit only Z.
   - d. Grep clean: no author/persona names in product paths; no
     probabilities or target prices introduced anywhere; no `latest`
     reads added to analysis paths after R1; unknowns handled as
     `nieznane`, never imputed.
   - e. Did I weaken, skip, or delete any test to pass? (If yes: stop —
     that is drift by definition.)
   Any answer of "no / unsure / can't cite" → do NOT commit; write the
   blocker as an owner question in the journal and pick the next
   unblocked task instead.
6. **Ledger.** CHANGELOG line + model-usage row (requested vs actual
   tier, honestly). Commit with a message citing the plan line.
7. **Heartbeat + continue.** One-line status. If context is near its
   limit, append a resume-state block to the journal (append-only
   ledger, not a plan document) and end cleanly — the next session
   resumes at step 1 and will find it.

## Every 5 iterations — full drift audit

Run the whole test suite; re-read all 10 invariants and grep the diff
since the last audit for violations of each; reconcile journal vs plan
(anything done that the plan didn't ask for gets flagged, not
rationalized); summarize phase progress in ≤5 lines. If the audit finds
drift, the next iteration is the correction, before any new work.

## Hard stops — never push through, ever

- Owner gates: checklist strike-pass, myfund CSV, SNT profile confirm,
  F13, deletion sign-off (R6). Blocked ≠ improvise around.
- Any change to APPROACH invariants, verdict-model semantics, sieve
  thresholds, or scoring rules: propose in the journal with the
  failure-ledger row that motivates it; owner decides. Skill patches
  additionally require the full simlab regression per corpus.md §protocol.
- Destructive operations on stored documents/snapshots (immutability is
  the point-in-time foundation).
- 3 consecutive failed attempts at one task → stop that task, write
  findings, move on; do not burn the loop on a wall.
- Anything that would make an output resemble investment advice.

## Why this shape

Drift happens between iterations, not inside them: each cycle re-reads
the constitution before acting (step 1), declares scope before touching
code (step 2), and must cite its authorization before committing
(step 5a). The journal makes the loop auditable asynchronously — the
owner reads it like a ship's log and intervenes by editing the plan,
never by chasing the agent.
