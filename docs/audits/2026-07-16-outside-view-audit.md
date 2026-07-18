# Outside-view audit — paths, goals, and where the real edge is

Date: 2026-07-16. Requested by Kuba. Scope: full — the audit may challenge
VISION.md, stages, and the process apparatus. Owner decisions taken before
writing: the edge that matters is **Kuba's investment edge** (alpha vs
sWIG80/WIG), the analysis should use **Malik/OBS-style practitioner
arguments**, **V2 (author neutrality) is dropped**, and a full rewrite is
allowed.

## 1. Verdict

The app has a solid data spine and a broken analytical brain. The 2026-07
reset optimized the wrong thing: it built an impressive provenance and
verification bureaucracy around analyses that no longer say anything an
investor would recognize. The one canonical output (SNT) was rejected twice
by the owner on economic content — after passing every structural gate,
strict verifier, and browser acceptance. That is the whole audit in one
sentence: **the gates measure lineage, not judgment, and the judgment was
deliberately removed.**

Delivery evidence, not opinion: ~31.5k LOC across backend/frontend, seven
docs, eleven skills, a queue, leases, fingerprints, drift gates — and after
all of it, exactly one company analyzed, twice reopened, with S6 (learning
loop) and S8 (replay) blocked. VISION's own founding claim — *"agents can
analyze a volume of data no human investor could, and that scale is the
edge"* — is falsified by the project's own history. The process weight makes
scale impossible.

## 2. Root causes of the slop

### 2.1 V2 removed the investment philosophy and replaced it with nothing

`skills/company-valuation/SKILL.md` states it openly: *"The engine
deliberately does not contain investor playbooks, sector scorecards or
hard-coded scenario recipes."* Every run asks a general-purpose model to
re-derive an investment philosophy from scratch. The predictable output is
generic MBA prose — the slop.

Compare what was deleted. The `malik-obs-analyst` skill (still in your
Cowork skills, gutted from the repo — `skills/strategy-malik-obs/` is an
empty directory) is a real analytical instrument: three load-bearing ideas
(stock-picking not timing; sprawozdania-first with gross margin + operating
leverage as the two motors; teza + katalizator before entry), 7 golden
rules, a 16-point checklist, a catalyst taxonomy with a priced-in test, and
a one-off veto. STRATEGY.md's "12 mechanics" is a lossy compression of that:
it kept the nouns ("improvement beats cheapness", "cash is evidence") and
lost the *operating procedure* — what to look at first, what vetoes what,
what caps a score, when to walk away.

Concretely lost in the abstraction: gross-margin trend and operating
leverage as the primary motors; forward C/Z vs the company's **own** history
as the valuation spine; the one-off veto on "attractive"; the
margin-of-safety trio (low valuation + rising backlog + net cash); the
small-cap sweet spot; quarterly thesis re-verification with sell discipline;
"if you cannot name the catalyst, that is the finding."

### 2.2 Process crowds out analysis

`company-valuation/SKILL.md` is ~150 lines; roughly 80% is leases, frozen
fingerprints, contract versions, adapter names, and save-gate mechanics.
The analyst instructions are a few sentences. The strict verifier audits
provenance, schema, reconciliation arithmetic — all computable, none of
which caught: forward trading C/Z misread as a target multiple, publicly
available demerger evidence missed, or 32/46/22 probabilities invented.
Every defect the owner actually cared about was an *economic reasoning*
defect, invisible to the gate apparatus by construction.

### 2.3 Precision inversion

The valuation engine demands five-year FCFF paths, exact driver-delta
reconciliation across seven line contributions, and terminal growth =
reinvestment × incremental ROIC — for GPW small caps with no consensus,
lumpy one-offs, and thin disclosure. Meanwhile the inputs that actually
decide a Malik-style case — backlog, cash conversion trend, insider
reference prices, governance — are named "gaps". The tool is precise where
precision is fake and vague where the money is. Malik's actual method is
forward C/Z vs own history, profit quality, and a concrete unpriced
catalyst. That is a weekend of engineering, not an engine.

### 2.4 The sieve hunts the wrong way

`workbench_sieve_v1` is a defensible generic quant screen (exclusions +
percentile momentum blend). But it encodes nobody's hunting pattern. Malik's
funnel is: small caps → statements readable → the two motors turning →
cheap on forward C/Z vs own history → catalyst not priced. The current
score can rank a company #5 on a one-off-distorted +1953% profit jump
(it did, for SNT) — the exact trap the 7 golden rules exist to veto.

## 3. Outside view — where a real edge exists

The edge question is: what can this tool do that moves Kuba's returns and
that the market (and existing tools) does not already do?

**E1. Structural coverage vacuum on GPW small/mid caps.** Post-MiFID II
coverage collapsed; GPW's paid coverage program (PWPA, 5th edition
2025–2027) covers just 65 companies of ~800 listed, 31 of them from sWIG80
— the exchange itself is paying analysts because nobody else covers these
names. Where no professional reads the reports, fundamental work is not in
the price. This is the same pond OBS fished (31%/yr XIRR over 9 documented
years) and it is still under-fished.

**E2. Generic AI reports are already commodity — do not compete there.**
Gielda.AI, GPW.watch, PulsRynku already mass-produce AI reports for every
GPW ticker. One more "AI analysis" per company is worthless. The edge is
the opposite of coverage-for-everyone: a disciplined practitioner checklist
applied consistently, with vetoes, priced-in tests, and falsifiers — the
thing generic reports structurally cannot do because they must always say
something about every stock.

**E3. Consistency at breadth.** No human applies a 16-point checklist to
~800 companies every quarter; every retail investor (including OBS) covers
~10–20 names and misses the rest. An agent applying *the same strict
framework* market-wide each reporting season — and shortlisting only what
passes — is the genuine scale edge VISION reached for. Scale of *filtering
by a proven method*, not scale of report generation.

**E4. Speed and language on filing days.** GPW earnings season concentrates
hundreds of PDF-only, Polish-language reports into days; ESPI current
reports (contracts, backlog, buybacks) drop continuously. Foreign AI tools
don't parse them; Polish portals headline the big names. Same-day reading
of small-cap filings against a standing thesis — "did the motors keep
turning, did the catalyst advance, did the falsifier fire?" — is a real
time edge, repeatable every quarter.

**E5. A thesis ledger that learns.** Nobody on this market — retail or
tool — systematically records teza + katalizator + falsifier with dates,
re-verifies each quarter, and scores calibration per engine version. V8 was
the best idea in VISION. It survives the pivot intact.

What is *not* an edge: DCF sophistication, verification ceremony, another
screener UI (BiznesRadar is better and is already your data source), and
probability trees on companies with no calibration data.

## 4. The pivot

One sentence: **stop building a valuation bureaucracy; build OBS-at-scale —
a machine that hunts the coverage vacuum with a named practitioner
checklist, keeps a falsifiable thesis ledger, and re-verifies it every
reporting season.**

### Keep (it is good and paid for)

- Scrapers, immutable document/snapshot lineage, point-in-time discipline
  (BiznesRadar, issuer/ESPI adapters, polite fetcher). This is the moat's
  foundation — calibration and replay are impossible without it.
- Portfolio sync, TWR/XIRR, mapping, report-calendar (S4/S7 work).
- The queue and drafter ≠ verifier as a *lightweight* sanity check.
- V8 outcome scoring / calibration — promote it, don't defer it.
- Honest-gap culture (missing data is a gap, never a synthetic signal).

### Kill

- **V2 author neutrality.** Analyses argue explicitly: "per OBS rule 5 this
  profit jump is one-off — veto", "forward C/Z 6.2 vs own 5-year median
  9.1". Named frameworks are the cure for slop, not a branding sin.
- The valuation engine as the center: driver-delta reconciliation, terminal
  ROIC identity, conditional probability trees, `valuation-engine-v4`. Keep
  the deterministic math library; retire the ceremony.
- The 12-mechanic "Workbench strategy" abstraction and the one-sieve dogma.
- Most structural gates and the drift-gate liturgy. Keep: math
  recomputation, no-look-ahead, source lineage. Drop: template-equality,
  cross-company near-duplicate vectors, focus-marker choreography.
- The current SKILL.md style. A skill is analyst instructions first;
  plumbing goes in code.

### Build (the new path shape)

`Hunt → Dossier → Verdict → Watch` — same four-station pipeline, different
brain:

1. **Hunt** — Malik-pattern funnel over the market snapshot: small/mid cap,
   revenue up, gross-margin trend up, operating leverage present, forward
   C/Z below own history, one-off share low. Exclusions stay (distress,
   negative equity, illiquidity). Output: a shortlist with *reasons in the
   framework's language*, plus the kill drawer you already have.
2. **Dossier** — the existing collectors produce the computed dossier the
   `malik-obs-analyst` skill already expects: metrics, prescore, C/Z
   history, one-offs, insider/buyback facts, forum leads as leads.
3. **Verdict** — the restored (repo-owned, versioned) `malik-obs-analyst`
   checklist as the actual system prompt: teza, katalizator with priced-in
   test, checklist read, red flags, one-off veto, alignment score,
   upside/downside frame, falsifiers with dates, `verify_next`. Valuation
   inside the verdict is Malik-simple: forward C/Z vs own history +
   bad/base/good earnings paths; DCF only where the business supports it.
4. **Watch** — the thesis ledger: report calendar + same-day ESPI/quarterly
   re-verification of every open thesis and every holding; falsifier fired
   → surfaced; outcomes scored (V8) per checklist version.

Portfolio stays the priority consumer (V7 unchanged): holdings are watched
hardest, uncovered holdings auto-queue.

### Sequencing — three moves, each independently useful

1. **Restore the brain (days).** Bring `malik-obs-analyst` (+ its rubric
   and `docs/strategy-malik.md`) back into the repo as the versioned
   Verdict skill; rewrite VISION/STRATEGY to name the framework; run it on
   SNT and your current holdings against existing dossiers. This alone
   answers "not using recommended investors arguments."
2. **Re-aim the sieve (week).** `workbench_sieve_v2` = the Hunt funnel
   above (needs gross-margin trend + one-off share in the market snapshot;
   both derivable from data you already scrape). Run it market-wide; the
   shortlist is the first artifact with real edge content.
3. **Wire the Watch loop (weeks).** ESPI/report-day re-verification over
   the thesis ledger + V8 scoring. This is where the compounding,
   unreplicable asset grows: a dated, scored history of theses.

## 5. Honesty constraints that survive the pivot

Decision support, never signals (V9) — a checklist verdict is an analysis
entrance, not a recommendation; Malik's own caveat stays in the prompt. No
performance claims before point-in-time replay (S8 gate unchanged). LLM
reading of Polish filings must keep claim-level citations to retained
documents — that part of the verification culture earned its keep. And the
alignment score is a fit-to-framework measure, never a return forecast.

## Sources

- [SII — Startuje nowy Program Wsparcia Pokrycia Analitycznego, lista 65 spółek](https://www.sii.org.pl/18250/analizy/newsroom/startuje-nowy-program-wsparcia-pokrycia-analitycznego-oto-lista-65-spolek.html)
- [GPW — Program Wsparcia Pokrycia Analitycznego](https://www.gpw.pl/aktualnosc?cmn_id=108324&title=Program+Wsparcia+Pokrycia+Analitycznego)
- [Parkiet — GPW przedstawiła listę 65 spółek objętych nową edycją płatnych analiz](https://www.parkiet.com/firmy/art42622131-gpw-przedstawila-liste-65-spolek-objetych-nowa-edycja-platnych-analiz)
- [Gielda.AI — raporty AI dla akcji GPW](https://gielda.ai/ai-report), [GPW.watch](https://www.gpw.watch/), [PulsRynku — analizy AI spółek GPW](https://pulsrynku.com/analiza-gpw)
- Repo evidence: `docs/VISION.md`, `docs/STRATEGY.md`, `docs/ROADMAP.md` (SNT rejection history), `skills/company-valuation/SKILL.md`, `docs/source-materials/obs.txt`, Cowork skill `malik-obs-analyst`.
