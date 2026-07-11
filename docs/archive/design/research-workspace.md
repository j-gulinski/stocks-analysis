# Research workspace — compact UX contract

**Status:** first vertical slice implemented 2026-07-09. This page defines the
workflow surface; [`TASKS.md`](../../../TASKS.md) owns status and
[`plan-research-platform.md`](../../plan-research-platform.md) owns future
architecture.

## Product path

```text
Discover → Research queue → Brief → Evidence/Financials
                         → Scenarios → Codex Review → Monitor/Journal
```

The live tabs are deliberately compact: `Raport` = Brief, `Wykresy` =
Scenarios, `Źródła` = Evidence/Financials audit, and `Codex` = Review/history.
Monitor and Journal are Brief/queue actions, not empty tabs. Add a surface only
when its data exists.

| Surface | One decision it should support |
|---|---|
| Discover | Is this candidate worth researching? |
| Research | Which case needs attention, and why? |
| Brief | What is the current read and next check? |
| Evidence | Which claims are supported, missing or conflicted? |
| Financials | Are the economics improving and durable? |
| Scenarios | Which drivers and valuation bridge set the range? |
| Review | What is disputed, unsupported or unresolved? |

AI is a review method, not a separate domain. Forum posts are leads, not facts;
Malik/OBS is a disclosed lens, not the master answer.

## Contracts

**Discover:** seed candidates from the cached immutable BiznesRadar rating
document. Show source, period and capture time; never call it a strategy score
or recommendation. Missing F-Score is missing, not zero. Start a research case
only after `Rozpocznij analizę`.

**Queue:** show state, freshness, one risk/gap, one next action and the latest
change line. Order fired falsifiers, flipped checks, stale evidence, then
freshness; held positions sort above watch-only cases at equal risk. Never rank
by forum/model activity or scenario upside.

**Monitor/Journal:** after ingestion, create at most one diff card per affected
company for changed checks, falsifiers, one-offs, valuation history or new
reports/ESPI. Falsifier changes need rule evidence or a human reason. The
append-only journal takes under a minute: decision, size, confidence, reasoning,
review date and attached thesis version. Positions are read-only context and
never change scores.

**Brief:** one canonical read: state/rationale, lens/evidence coverage, four
key numbers, up to four signals, two reasons for, two against and two next
checks. Full scenarios, statements and AI prose live elsewhere. Current
multiple-reversion output is labelled valuation sensitivity until RT.4 driver
scenarios exist.

**Review:** exceptions first—changed checks, red flags, one-offs and next
checks. Collapse full generated records, metadata and history. Future RT.5/RT.6
review adds evidence-linked disagreements and judge labels.

## Visual and accessibility bar

Calm dark reading surface; fewer bordered cards; stable 1240px desktop content;
15px/1.5 body; Polish financial formatting; restrained semantic colors; 44px
touch targets; visible focus and AA contrast; horizontal scrolling only inside
intentional mobile workflow/table regions; no page overflow at 390px.

Every component needs loading, empty, stale, error and conflict states, plus a
visible provenance/status label for model output.

## First-slice evidence and open items

Verified: Brief reduction from ~2,995px to ~1,430px at 1280px, no desktop or
390px page overflow, production Next build/type check, and browser checks for
Discover, Research and company workflow tabs.

Open: component accessibility audit, automated screenshot baselines, scenario
comparison, evidence locator, persistent ResearchCase, Monitor/Journal and the
seasoned-investor judge run. These are IL.5 and RT4.5–RT6 work.
