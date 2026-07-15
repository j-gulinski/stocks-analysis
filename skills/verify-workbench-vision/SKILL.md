---
name: verify-workbench-vision
description: Run evidence-based acceptance of the live Stock Analysis Workbench in the in-app browser against docs/VISION.md V1–V10 and the active Roadmap exit gate. Use after every implementation session that changes UI, API reads, queue behavior, data visibility, Research, Valuation, Discover, or Portfolio; when asked whether the current implementation aligns with requirements; or whenever product drift is suspected.
---

# Verify Workbench Vision

Treat the running product as the primary acceptance artifact. Unit tests protect
deterministic contracts; they never substitute for observing the user flow.

## Prepare

1. Read `docs/VISION.md`, the relevant `docs/PRODUCT.md` section and the active
   `docs/ROADMAP.md` exit gate. Do not reinterpret V1–V10.
2. Inspect the current diff and name the user-visible flow it can affect.
3. Run `./workbench doctor`. Start the app only when needed. Never reset or
   refetch disposable data unless the user or active Roadmap gate authorizes it.
4. Load the `browser:control-in-app-browser` skill and use the in-app browser
   against `http://127.0.0.1:3000`. If representative data is missing, report a
   blocked check; never turn an empty fixture into a pass.

## Exercise the real flow

Begin with the changed flow and complete it as Kuba would. Then run a compact
cross-stage smoke through Discover → Research list → company → Valuation →
Portfolio wherever the active Roadmap says the stage is eligible. Use clicks,
expansion state, ordering, labels and displayed values as evidence; do not pass
from source inspection alone.

Check the relevant invariants:

- **V1:** Discover offers one exclusion-first sieve, no filter/sieve selector,
  and inspectable kill reasons.
- **V2:** Product copy, labels and artifact-facing UI contain no author or
  method branding. A domain may appear only as a data-source citation.
- **V3:** Research rows lead with phase substance. The company page leads with
  current valuation when present, then Brief. Business, Performance, Outlook,
  Thesis and History open independently. Evidence/sources are a separate,
  collapsed, selectable workspace; the page does not expose all data at once.
- **V4:** Valuation opens on methodology and the bad/base/good result, not an
  assumption editor. It exposes the BiznesRadar Street baseline, the
  Workbench variance bridge, independent relative/intrinsic methods and reverse
  expectations. Probability posture and mechanisms are company-specific; a
  weighted value appears only for a complete computed tree. When two current
  valuations exist, compare their probability/assumption vectors;
  near-identical values are a finding, not proof of consistency.
- **V5:** Verifier/process metadata stays in an audit surface. For computable
  gates, inspect the backing API or stored artifact and recompute rather than
  accepting a badge or prose assertion.
- **V6:** Explicit queue execution can drain all eligible jobs with visible
  bounded failures; passive page loads do not claim work.
- **V7:** Portfolio keeps reconciled analytics visible, identifies affected
  figures when reconciliation fails, and prioritizes uncovered holdings.
- **V8:** When the Roadmap marks learning eligible, outcome scores are visible
  per engine version. Before then, record the gate as not yet eligible.
- **V9:** Every material claim is visibly sourced, calculated, assumed or a
  gap. No screen issues a buy/sell command.
- **V10:** Each capability has one current route and renderer. After a declared
  clean-baseline gate, legacy modes, compatibility tabs, adapters, fields and
  v1/v2 artifacts are absent—not merely hidden from the current view.

Also test the active Roadmap exit-gate wording literally. An invariant checklist
does not replace the slice-specific outcome.

## Use proportionate automated checks

Always run the Vision drift gate:

```bash
backend/.venv/bin/pytest backend/tests/test_vision_contract.py
```

Run only focused deterministic tests for calculations, schemas, lineage or the
changed boundary. A full backend suite is a release/cross-cutting risk decision,
not the default acceptance ritual. Never count test quantity as product proof.

## Produce an adversarial verdict

For every relevant check, record one of:

- a finding with severity, URL/action, V-number, observed evidence and expected
  behavior;
- a no-finding justification naming the URL/action and concrete value, label,
  expansion state or recomputation examined; or
- blocked/not-yet-eligible with the exact missing precondition.

Reject “all checks passed” without evidence. One open severity-1/2 Vision
finding fails acceptance. A verifier that edits the implementation becomes a
drafter and cannot issue the final verdict in the same pass.

Do not create tracked screenshots, a handoff report or a second plan. Keep
browser captures transient. Put the outcome in the response, update the one
Roadmap gate, and add one concise `docs/model-usage.md` row only when the
implementation/review session is complete.
