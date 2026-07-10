# UI Refactor Plan v2 — analyst workbench, redesigned

Rewritten 2026-07-09 after the user rejected the v1 visual direction ("too
tight", wrong colors). This version has two jobs: (1) record what changed in
the app and why the current UI no longer fits, (2) define the redesign —
information architecture + fresh visual language — sized for what is coming
(RT4.5–RT4.7 and the remaining CX.14 history, plus the extension backlog).
The delivered report-first slice is historical context; remaining UI work is
tracked in `TASKS.md` and the RT.4 plan. Visual reference:
`docs/design/design-v2.md` + `docs/design/mockups-v2.html` (v1 `design.md` /
`mockups.html` stay as archive). CX.14 in `TASKS.md` tracks execution.

## 1. What changed in the application

The app went through three product identities in two days, and the UI still
carries layers of all three:

1. **Data presentation app** (Phases 1–4): watchlist + stock tabs rendering
   scraped financials, charts, forecast, forum.
2. **Decision workspace** (2026-07-08): Brief tab with DecisionCockpit +
   InvestorMemo, watchlist "useful summary" columns, scaling radar, discovery
   checklist.
3. **Codex-operated analyst OS** (2026-07-09, Stage CX): provider-neutral
   `agent_runs`/`analysis_runs` queue with lifecycle states, strict-verifier
   contract (`prediction`/`potential`/`result_quality`), MCP worker bridge,
   ESPI/EBI `event_reports`, deterministic Backtest Lab with availability
   policies, Agent Evaluation replays with outcome windows.

Consequences visible in the code today:

- **Dashboard = 11-section vertical stack** (`page.tsx`, ~1600 lines): brief
  cards → Codex console → Backtest Lab → Agent Evaluation → scaling radar →
  discovery checklist → decision table. The primary work surface (watchlist)
  is at the bottom; operations and research tooling squat above it.
- **Three competing verdict surfaces** on the stock Brief tab
  (DecisionCockpit, InvestorMemo, ThesisPanel) say overlapping things in
  different visual dialects.
- **New contract objects have no shared primitives**: run lifecycle chips,
  verifier badges, provenance/freshness chips, outcome-window strips are each
  improvised per panel with local styles.
- **Events have no home**: `event_reports` are ingested but surfaced nowhere
  except inputs to pre-session briefs.
- **Nav (2 items) no longer matches the app**: Operations, Research and
  Candidates functionality exists but has no destination; Settings became a
  diagnostics page.
- **Design docs drifted**: `design.md`/`mockups.html` describe a 6-tab stock
  page and SCSS `$vars` that no longer exist; the CX-era UI has no approved
  reference at all.

## 2. What is coming (what the redesign must facilitate)

- **CX.11** — walk-forward backtests, learning notes, policy/verifier gates →
  Research area grows (runs, comparisons, accepted lessons).
- **CX.12** — scheduled/background Codex workers claiming queued jobs → global
  queue/worker visibility, honest lifecycle everywhere.
- **CX.13** — agent-evaluation growth: hit rates, confidence calibration,
  per-workflow quality → evaluation dashboards beside backtests.
- **Pre-session brief (Flow 1)** → a "Today" agenda: new ESPI/EBI, stale data,
  needs-human items.
- **Candidate scout (Flow 4)** → Candidate Radar fed by `candidate_runs`
  (replacing the client-side scaling radar + static discovery checklist).
- **Phase 6** — Google-allowlist auth → login page, user menu, per-user
  attribution slot in the topbar.
- **Backlog** — screener over prescore, price/ESPI alerts, hotness score →
  all fit the Candidates/Research/Operations split below without new nav.

## 3. Redesign — information architecture

App shell: **ink sidebar + paper content** (see mockups). Sidebar nav (English
per repo convention), topbar with ticker search, global queue chip, user slot.

| Destination | Contents | Absorbs / prepares for |
|---|---|---|
| **Watchlist** (landing) | "Dziś" strip (new events, needs-human, stale data) · decision table (primary surface) · right operations rail (queue snapshot, backtest/eval status, links) | pre-session agenda (Flow 1); CX.12 queue visibility |
| **Candidates** | Candidate Radar (`candidate_runs`), discovery filters, promote-to-watchlist | scout runs, future screener + hotness score |
| **Research** | Backtest Lab · Agent Evaluation · learning notes | CX.11 walk-forward + CX.13 calibration views |
| **Operations** | full `agent_runs` history, worker status, scheduled jobs, rejected-run audit | CX.12 lifecycle, n8n/cron lanes |
| **Settings** | diagnostics (as today) + Phase 6 account/allowlist | auth |

Stock page (`/stock/{ticker}`): breadcrumb back to Watchlist · **one verdict
band** (merges DecisionCockpit + InvestorMemo headline: working status,
readiness score, downside-first weighted EV, top blockers) · right **context
rail** (quote, provenance chips, latest-analysis verifier badge, next steps) ·
tabs: **Brief · Interpretacja AI · Fundamenty · Wycena · Zdarzenia (new,
ESPI/EBI feed) · Dane**. Existing panels (Thesis, Scenarios, Insights,
Prescore, Charts, Financials, Forum, Analysis) keep their tab homes; they are
restyled, and their improvised status markup is replaced by the shared
primitives.

Shared primitives (one implementation, used everywhere — this is what makes
CX.11–13 UI cheap): `StatusChip` (run lifecycle), `VerifierBadge`,
`ProvenanceChip`, `RunRow` (+ expandable detail well), `OutcomeWindows`,
`MetricTile`, `EmptyState`. Specified in `design-v2.md`.

## 4. Visual language

Full spec in `design-v2.md`. Summary of the decision: v1 (dark `#0e1217`,
13 px, flat, dense) is **discarded**. v2 "Research studio": warm paper
background, white cards with soft shadows, ink text, serif display type
(titles + headline numbers), mono tickers/numbers, indigo accent
(`#3F4FC9`), pos/neg/warn washes for all state chips, 15 px base, 8 pt
spacing grid, 232 px ink sidebar. Product guardrails unchanged: Polish domain
labels, `pl-PL` formatting, verifier/status always visible, explicit
missing-data chips, no recommendation framing.

## 5. Migration slices (ordered, each independently shippable)

1. **Tokens + primitives**: replace `:root` tokens in `globals.scss`, add
   fonts via `next/font`, implement StatusChip/VerifierBadge/ProvenanceChip/
   RunRow/OutcomeWindows/MetricTile/EmptyState; restyle buttons/cards/tables.
   No layout moves yet — the app just changes skin and gains the components.
2. **App shell**: sidebar + topbar layout (`layout.tsx`, `Nav.tsx` →
   `Sidebar.tsx`/`Topbar.tsx`), routes `/research`, `/operations`,
   `/candidates` created with placeholder content.
3. **Dashboard split**: move Backtest Lab + Agent Evaluation panels to
   `/research`; move full queue history to `/operations` (rail keeps compact
   snapshots); move scaling radar + discovery to `/candidates`; add "Dziś"
   strip. `page.tsx` shrinks to Today + table + rail.
4. **Stock page**: verdict band (merge DecisionCockpit + InvestorMemo
   headline; memo details fold into Brief body), context rail, tab restyle;
   add **Zdarzenia** tab reading `GET /api/companies/{ticker}/event-reports`
   (endpoint exists since CX.2).
5. **Panel adoption pass**: Analysis/Backtest/Evaluation/Forum panels swap
   improvised chips for shared primitives; delete dead local styles.
6. **Mobile + polish pass**: icon-rail sidebar, stacked rails, table→cards,
   390 px overflow audit, empty states everywhere.

Backend changes required: **none** (all data already exposed; slice 4 reuses
the existing event-reports endpoint). Each slice needs its own CHANGELOG
entry per repo rules.

## 6. Verification per slice

- `cd frontend && npm run build` green.
- Browser check desktop (≥1280) + mobile (390 px): no horizontal overflow for
  long tickers, chips, warnings.
- Status truthfulness: queued ≠ running wording preserved; verifier state
  visible on every AI-produced result.
- Screenshot compared against `mockups-v2.html` frame for the touched area.
- Bounded GPT-5.3 high–extra-high audit loops are suitable for overflow/copy
  sweeps; investment-facing wording changes still need stronger review.

## 7. Open questions (decide before slice 3)

- Does "Dziś" eventually become its own page (once pre-session briefs are
  saved as verified agenda rows), or stay a strip? Plan assumes strip now,
  page later without nav changes.
- Candidates page ships mostly-empty until `candidate_runs` are produced by
  real scout runs — acceptable, or defer the route to slice 5?
- Dark mode: tokens are structured to allow a dark variant later; not in
  scope for v2 (user chose light-first).
