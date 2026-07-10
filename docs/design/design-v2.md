# Design system v2 — "Research studio"

Status: proposed 2026-07-09 (supersedes `design.md`, which is kept as the v1
archive). Visual reference: `mockups-v2.html`. Product/IA rationale:
`docs/plan-ui-refactor.md`.

Direction decided with the user: the v1 look (dark `#0e1217`, 13–14 px, flat,
dense) is **discarded, not iterated**. v2 is a light, editorial "research
studio": warm paper, white cards with soft shadows, ink text, serif display
type for headlines and big numbers, generous spacing. It should read like a
well-set research memo, not a terminal.

Non-negotiables carried over from v1 (product guardrails, not styling):
domain labels Polish / nav labels English, `pl-PL` number formatting with
` zł`, red = negative / green = positive, every AI-visible result shows run
status + verifier state, explicit warning chips for missing data.

## Tokens

CSS custom properties in `globals.scss` (same mechanism as today — only the
values and names change). Prefix stays flat for easy grep.

| Token | Value | Use |
|---|---|---|
| `--paper` | `#F5F3ED` | page background (warm paper) |
| `--card` | `#FFFFFF` | cards, table body |
| `--card-inset` | `#FAF8F4` | wells, table header rows, code/JSON blocks |
| `--sidebar` | `#22252C` | left nav background (ink anchor) |
| `--sidebar-ink` | `#C9CDD6` | sidebar text; active item white on `--accent` |
| `--border` | `#E5E0D5` | hairline card/table borders |
| `--border-strong` | `#D6D0C2` | dividers that must be visible on paper |
| `--ink` | `#22252C` | primary text |
| `--ink-2` | `#5B6270` | secondary text |
| `--ink-3` | `#949BA8` | muted/meta text |
| `--accent` | `#3F4FC9` | primary actions, active tab, links |
| `--accent-ink` | `#32409F` | hover/pressed accent |
| `--accent-wash` | `#ECEEFB` | selected rows, active-chip background |
| `--pos` / `--pos-wash` | `#1B7F5C` / `#E6F4EC` | positive values, `pass` |
| `--neg` / `--neg-wash` | `#C24045` / `#FAEBEB` | negative values, `rejected` |
| `--warn` / `--warn-wash` | `#9A6C0B` / `#FAF2DC` | stale data, `needs-human` |
| `--neutral-wash` | `#EEF0F3` | `queued`/`draft` chips, inactive badges |
| `--radius-card` | `14px` | cards, panels |
| `--radius-ctl` | `10px` | buttons, inputs |
| `--shadow-sm` | `0 1px 2px rgba(28,25,18,.06)` | table rows, chips on hover |
| `--shadow-md` | `0 1px 2px rgba(28,25,18,.05), 0 6px 24px rgba(28,25,18,.07)` | cards |

Rule: color always comes from tokens; no hex literals in component SCSS.

## Typography

| Role | Font | Size/line | Weight |
|---|---|---|---|
| Display (page title) | `"Source Serif 4", Georgia, serif` | 30/38 | 600 |
| Section title | serif stack | 20/28 | 600 |
| Big metric number | serif stack, `font-variant-numeric: tabular-nums` | 26/32 | 600 |
| Body | `Inter, system-ui, sans-serif` | 15/1.55 | 400 |
| Meta / secondary | sans stack | 13/1.5 | 400 |
| Overline label | sans stack, uppercase, `+0.06em` tracking | 12 | 600 |
| Table numbers, tickers | `"JetBrains Mono", ui-monospace, monospace`, tabular | 13.5–14 | 500 |

Serif is reserved for display: titles and headline numbers. All UI chrome,
tables, chips and forms are sans. Tickers are always mono (`CBF`, `SNT`) —
they become visually scannable anchors. Never bold-weight 700+ anywhere.

Fonts load via `next/font` (self-hosted) with the system fallbacks above; the
app must be fully usable on fallbacks alone.

## Space and layout

8 pt grid. Card padding 24 px, gap between cards 24 px, section gap 40 px.
Content max-width 1400 px.

App shell (new): fixed left sidebar 232 px (ink), topbar 56 px (paper, hairline
bottom border), content on paper. Sidebar = nav + global worker/queue status.
Topbar = ticker search, global queue chip, refresh action, user slot (Phase 6).

Workbench pages use a two-column grid: main surface + 360 px right rail
(`grid-template-columns: minmax(0,1fr) 360px`). The rail stacks below main at
≤1080 px; sidebar collapses to icon rail at ≤860 px and to a top drawer at
≤560 px. No horizontal overflow at 390 px — long chips wrap, tables collapse
to stacked cards via `data-label` (mechanism kept from v1).

## Components

- **Card**: white, `--radius-card`, `--shadow-md`, 1 px `--border`. Cards never
  nest; inside a card use inset wells (`--card-inset`) instead.
- **Buttons**: primary = accent fill, white text; secondary = white fill, ink
  text, border; ghost = text-only accent. Height 36 px, radius `--radius-ctl`.
- **StatusChip** (run lifecycle — one component, used everywhere):
  `queued`/`draft` neutral-wash · `claimed`/`running` accent-wash with pulsing
  dot · `completed`/`pass` pos-wash · `needs-human` warn-wash ·
  `rejected`/`failed` neg-wash. Pill, 12 px label, leading 6 px dot.
- **VerifierBadge**: StatusChip variant prefixed "weryfikacja:"; always visible
  on any AI-produced result, never hidden in a tooltip.
- **ProvenanceChip**: source + freshness (`BR · 2 dni temu`); turns warn-wash
  past the staleness threshold (>3 days prices, >1 quarter financials), turns
  neg-wash when the source errored on last refresh.
- **Verdict band**: single decision surface on the stock page (replaces
  stacked cockpit + memo cards): status word set in serif, readiness score,
  weighted-EV read (downside first), top blockers as inline chips.
- **Metric tile**: overline label + serif number + meta line. Grid
  `auto-fit minmax(150px, 1fr)`.
- **RunRow**: one-line manifest for any run (agent/backtest/evaluation):
  mono id + workflow + model-role chip + StatusChip + relative time + optional
  `analysis #id` link. Expands to a detail well, selected state accent-wash.
- **OutcomeWindows**: 30/90/180/365 d strip; each window a mini chip —
  pos/neg-wash for hit/miss, neutral dashed border for `missing`.
- **EmptyState**: inset well, one serif sentence, one primary action, honest
  wording ("Brak zapisanych analiz — dodaj do kolejki" not spinner theater).
- **Tables**: white body, inset header row, hairline row separators, row hover
  `--card-inset`, numeric cells mono right-aligned.

## Charts (recharts)

Paper-friendly: grid lines `--border`, axis text `--ink-3` 12 px, revenue
`--accent`, margins `--pos`, negatives `--neg`, historical overlays at 35 %
opacity. Tooltip = white card with `--shadow-md`. No gradients inside plots.

## Accessibility and tone

All text tokens ≥ 4.5:1 on their backgrounds (ink-3 only for meta ≥ 12 px).
Wash-background chips always pair color with a label word — state is never
color-only. Focus rings: 2 px `--accent` outside offset. Motion: 120 ms ease
on hover/expand only; the pulsing running-dot is the single ambient animation.

## What v1 rules are explicitly dropped

Dark-only palette · 13 px density target · "flat surfaces only, no shadows" ·
"restrained borders as the only hierarchy" · the 2-item top nav as app shell.
Kept: honesty rules (status/verifier visibility, explicit gaps), Polish domain
labels, `pl-PL` formatting, no decorative hero sections, no cards-in-cards.
