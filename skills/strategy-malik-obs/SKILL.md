---
name: strategy-malik-obs
description: Apply the source-grounded Paweł Malik/OBS fundamental lens to an existing Stock Analysis Workbench research snapshot or valuation job. Use when Codex must assess an earnings-improvement thesis, durable versus one-off results, gross-margin and operating-leverage drivers, forward valuation versus the company's own history, catalyst/backlog, margin of safety, falsifiers, and scenario probabilities. Do not use as a market-wide substitute for missing facts, a universal score, or buy/sell advice.
---

# Malik / OBS strategy

Use this method only on sourced company research. Read
`../../docs/STRATEGY.md`; consult the retained raw OBS thread or BiznesRadar
workflow transcript only when exact source interpretation is required.

## Core question

State what must happen for the company's next quarter/year results to improve,
why the market may not fully price it, and which evidence would prove the thesis
wrong. Cheapness without this mechanism is not a positive result.

## Analysis order

1. **Understand the business.** Name segments, revenue mechanism, capacity or
   demand constraints, seasonality, and company-specific operating drivers.
2. **Read the result bridge.** Trace revenue -> gross profit/margin -> selling
   and administration costs -> operating result -> normalized net result.
   Explain gross-margin trend and operating leverage rather than merely listing
   growth percentages.
3. **Normalize quality.** Separate core repeatable earnings from asset sales,
   revaluations, FX, tax, discontinued operations, provisions, base effects,
   and other one-offs. Reconcile operating cash flow, working capital, and
   capex when available.
4. **Forecast drivers.** Build downside/base/upside and optional event paths
   for the next quarter and year from explicit sourced or human assumptions.
   Python owns all saved financial calculations.
5. **Value in context.** Prefer the appropriate forward multiple and compare it
   with the same company's own history. State when a sector method is more
   appropriate. Keep own-history reversion as a sensitivity, not the scenario
   mechanism.
6. **Demand a catalyst.** Name the contract/backlog, margin recovery, capacity,
   product, capital return, corporate event, or other mechanism, its horizon,
   evidence, and whether it appears priced in.
7. **Check safety and behavior.** Assess net cash/debt, cash conversion,
   liquidity, dilution/capex needs, management delivery, governance, and the
   risk of emotional attachment to a weakening thesis.

Index membership and company size are neutral context. Small-company
inefficiency may explain where the method often looks, but it is not a company
risk, automatic score, or exclusion of WIG20/mWIG40/sWIG80.

## Required result

Return a concise Polish method read containing:

- mechanism-based thesis and counter-thesis;
- evidence-backed result drivers and normalized one-off assessment;
- catalyst, backlog/visibility, horizon, priced-in view, and gaps;
- balance/cash-conversion margin of safety;
- downside/base/upside scenario narratives and probability rationale;
- deterministic quarter/year marker and valuation outputs supplied by the
  Workbench, not recomputed by prose;
- falsifiers and next dated evidence checks;
- method coverage: known factors, unknown factors, and source references.

Do not collapse the result into a decorative universal score. If a fit score is
requested, show every weighted contribution, exclude unknowns, apply explicit
one-off/balance/catalyst caps, and let the independent verifier own the final
number.

## Verification

- Never invent catalyst, backlog, management quality, forecast inputs, target
  price, or historical multiple.
- Forum statements remain attributed leads until corroborated.
- Produce a complete `provisional` read when ordinary evidence is missing;
  reserve `needs-human` for identity, access, fabrication, schema, math, or
  look-ahead failures.
- Require a separate strict verifier for scenario probabilities, method fit,
  calculation linkage, and final status.
- Never recommend or execute a trade or change a portfolio position.
