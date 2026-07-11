# North star — personal GPW company-learning loop

This is the binding product direction. It captures the user's stated working
method and the durable decisions from the live architecture, design, guardrails
and Malik/OBS lens. It is a **research and decision-support workflow**: inside
the app Codex acts as an opinionated analyst — it reasons through every step
(via the `stock-*` skills) and commits to a scored, probability-weighted
scenario judgment — but the user makes every buy/sell/hold decision. It is not
third-party investment advice, not autonomous trading, and not a promise that
the system can select winners. The scored judgment is decision support for the
user's own call, and its worth is measured by calibration against real
outcomes. See `docs/plan-scored-scenario-judgment.md` for the planning brief.

## The outcome we are building

The Workbench helps the user continuously get to know GPW companies well enough
to form, record, challenge and revisit an independent view of a business at a
given price. A good long-term holding is the result of repeated evidence-led
review, not a one-off screen or model score.

The app should make it realistic to repeat this loop every quarter:

```text
bounded GPW universe → quick visual/financial triage → learn the business
→ read reports and primary disclosures → write a price-aware thesis
→ record decision and falsifiers → revisit after each material update
```

The durable result is a personal, dated knowledge base: price at review,
evidence, the user's commentary, thesis, confidence, invalidation conditions,
next check and what later proved right or wrong.

## Intended first-pass universe

Start from a transparent main-market GPW universe, normally excluding WIG20 and
mWIG40. This is a **user preference and starting queue**, not a claim that large
companies cannot be attractive. The expected first-pass list is roughly 350
companies (the live discovery snapshot currently returns ~384 raw rows before
these exclusions); obvious unsuitable cases and businesses outside the user's
current circle of competence reduce the active learning queue toward roughly 200.

Preferences must be editable and never silently become facts or permanent
exclusions:

- favour businesses whose economics and drivers can be understood and checked;
- be cautious with single-project, hype-led or highly binary stories, including
  gaming and biotech, unless the user deliberately opens an exception case;
- do not call a company a “mine”, “grzanka”, or uninvestable without recorded
  evidence and a reversible human reason.

## The operating loop

1. **Maintain the universe.** Discover provides a low-request, source-labelled
   starting list and explains why an item surfaced. It does not automatically
   add a company to the watchlist or make an investment judgment.
2. **Fast triage.** Review the chart and revenue/results trend. Mark a dated
   human outcome: `skip for now`, `revisit later`, or `research case`. Preserve
   the review price and short personal comment.
3. **Learn the business.** For a promoted case, read the report, identify how
   the company makes money, operating drivers, cash conversion, debt, one-offs
   and what could change the next results.
4. **Resolve qualitative evidence.** Review primary reports/ESPI/EBI first,
   then use forum threads and conferences as labelled leads. Codex gathers,
   summarizes and points out gaps; it never turns a forum opinion into a fact.
5. **Make the price-aware thesis and scored scenario read.** State why results
   may improve or weaken, what is or is not priced in, catalyst, counter-thesis,
   risks, falsifiers, valuation range and next evidence check. Codex commits to
   multiple scenario outcomes — each with a probability and its modelled effect
   on C/Z, other markers, price and future potential — plus an overall
   conviction score and confidence. A multiple alone is never enough.
6. **Record the human decision.** The journal stores the user's buy/sell/hold/
   no-action decision, price, confidence and rationale. The app provides
   decision support, never an instruction to trade.
7. **Revisit and learn.** Each quarter or material event compares the new
   evidence with the prior thesis. Keep holdings while the documented
   perspective holds; surface fired falsifiers and record why a thesis changed.

## Codex's job

Codex is an evidence-grounded research operator, scored analyst and independent
critic. It runs the full judgment pipeline through the `stock-*` skills —
explore → collect → aggregate/group/value → explore outcomes → score — using
Codex reasoning at every step:

- order the queue, collect permitted stored/source evidence, extract facts and
  identify missing primary evidence;
- draft structured case notes and challenge the user's thesis with explicit
  counter-evidence;
- commit to a scored, probability-weighted read: multiple scenario outcomes,
  each with a probability and its modelled effect on C/Z, other markers, price
  and future potential, plus an overall conviction score and confidence
  (contract in `docs/plan-scored-scenario-judgment.md`);
- require a separate strict verifier before any UI result is marked verified;
  the verifier owns the final scored fields;
- retain sources, timestamps, assumptions and model/run metadata.

Codex does **not** replace the user's final decision, silently widen the
universe, auto-add positions, execute trades, invent deterministic markers or
valuation inputs, or present an unverified draft as an approved conclusion. The
score is an opinion to inform the human, never an instruction to trade.

## Product priorities and acceptance test

Prioritize the shortest useful path through the loop over more dashboards or
generic agent machinery:

1. reliable, polite universe/discovery evidence;
2. dated quick triage with a human note and next action;
3. a progressive research case with report/ESPI/forum/conference evidence;
4. thesis, falsifiers, scenarios and journal/monitoring tied to the same case;
5. honest feedback on what changed and what the user learned.

Every feature must answer: **does this help the user understand a company,
sharpen Codex's scored scenario judgment, make a dated and reversible decision,
or re-evaluate it after new evidence?** If not, it is secondary. Success is a
repeated quarterly habit, a more useful company memory, and a scored judgment
that stays honest over time—not a score chased for its own sake, a prettier
screener or an automated portfolio. The scored scenario read earns trust only
by being calibrated against what actually happens.

## Relationship to existing strategy material

The Malik/OBS material is the first analytical lens: statements first, revenue
and margin/operating leverage, profit quality, valuation versus the company’s
own history, catalyst, backlog and balance-sheet safety. It remains a labelled
lens, not a rule that flattens the user's preferences or a universal template.
See `docs/strategy-malik.md` for sources and the exact evidence mapping.
