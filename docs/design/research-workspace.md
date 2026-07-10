# Research workspace — information architecture and UX contract

**Status:** implemented first vertical slice on 2026-07-09. This specification
supersedes `mockups.html` for navigation, content hierarchy and responsive
behaviour. The old mockups remain a visual-history reference.

## Product path

```text
Discover -> Research -> company Brief -> Evidence -> Financials
         -> Scenarios -> Review -> future Monitor / Journal
```

The application is a research workbench, not a stock leaderboard. Every screen
must make one decision easier:

| Screen | Decision |
|---|---|
| Discover | Is this candidate worth beginning research on? |
| Research | Which active case needs attention, and why? |
| Brief | What is the current read and the next evidence check? |
| Evidence | Which claims are supported, missing or conflicted? |
| Financials | Are the operating economics improving and durable? |
| Scenarios | Which operating assumptions and valuation bridge drive the range? |
| Review | What did the reviewer dispute or fail to support? |

AI is a review method, not a separate domain object. PortalAnaliz posts are
unverified leads. Malik/OBS is a disclosed strategy lens, not the master answer.

## Discover contract

The first release uses one cached, immutable BiznesRadar GPW rating document to
seed candidates. It displays the source's Altman EM-Score rating, Piotroski
F-Score, report period and capture time. This is deliberately a low-request
source screen; it does not call every company endpoint.

- Never call the source rating a strategy score, recommendation or "best stock".
- Missing F-Score is missing, not zero, and fails a minimum-F-Score preset.
- Explain every inclusion with at most two source-rule chips.
- Show the caveat that strategy fit is unverified until a dossier is built.
- No target price, scenario upside, forum volume or model score in discovery.
- A candidate becomes an active research case only after `Rozpocznij analizę`.

The next screener version adds point-in-time, template-aware rules for market
cap/liquidity, growth, margins, cash conversion, leverage and valuation against
own history. Banks, biotech and industrial companies must not share one hidden
P/E formula.

## Research queue contract

The queue exposes one state, two signals, one risk/gap, one next action and
freshness per company. It does not expose scenario upside or rank companies by
forum/model activity. Maintenance actions remain visually subordinate.

## Company Brief limits

The default Brief contains exactly one canonical read:

- one state and short rationale;
- the Malik/OBS lens and evidence coverage as secondary metadata;
- four key numbers and at most four company-selected signals;
- at most two reasons for, two against and two next checks;
- one product-level disclosure.

Full scenarios, raw statements and AI prose never repeat on Brief. Current
multiple-reversion scenarios are explicitly labelled a valuation sensitivity
inside Scenarios until operating-driver scenarios v2 exist.

## Review contract

Review shows exceptions first: checklist changes, red flags, one-off risk and
next checks. The full generated record, model metadata and history are collapsed
by default. The target RT.5/RT.6 version replaces the legacy narrative with
evidence-linked disagreements, unsupported claims and judge failure labels.

## Visual and responsive rules

- Calm dark reading surface; fewer bordered cards, more whitespace/dividers.
- Content width 1240 px; body 15 px/1.5; tertiary text `#8797a8` for AA contrast.
- Green = verified favourable fact, red = verified risk, amber = unresolved
  evidence, blue = action. Never use green alone for expected upside.
- Touch targets at least 44 px for workflow navigation and primary actions.
- Mobile global nav stays one row; company workflow scrolls horizontally.
- Tables show the latest eight periods by default; full history stays inside its
  own horizontal scroller behind an explicit control.
- No document-level horizontal overflow at desktop or 390 px.

## Acceptance evidence from the first slice

- Live SNT Brief reduced from about 2,995 px to 1,430 px at 1280 px desktop.
- Desktop Discover, Research and all five company workflow tabs have no page
  overflow after fixing the historical table boundary.
- At 390 px, Brief and Research have no horizontal overflow; workflow tabs
  remain reachable by horizontal scrolling.
- Production Next build and TypeScript check pass; browser interaction verified
  Discover, Research, Brief and every company workflow tab.

Still open: component-level accessibility audit, automated screenshot baselines,
scenario comparison matrix, evidence locator drawer, persistent ResearchCase
state, Monitor/Journal, and the seasoned-investor judge run.
