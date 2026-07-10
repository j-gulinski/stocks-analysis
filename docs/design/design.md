# Legacy UI design reference

`mockups.html` contains the completed Phase-4 watchlist and stock screens. It is
kept as design history, but it no longer defines the product information
architecture. New frontend work follows `research-workspace.md`; this file still
documents the original palette and component lineage.

## Tokens (`src/styles/_variables.scss`)

| SCSS variable | Value | Use |
|---|---|---|
| `$surface-0` | `#0e1217` | page background |
| `$surface-1` | `#151b22` | metric cards, subtle panels |
| `$surface-2` | `#1b232c` | raised cards (bordered) |
| `$border` | `#2a3440` | hairline borders, table row separators |
| `$border-strong` | `#3a4653` | hover borders |
| `$text-primary` | `#e8edf2` | headings, key numbers |
| `$text-secondary` | `#9fb0bf` | supporting text, table values |
| `$text-muted` | `#64748b` | labels, hints, timestamps |
| `$accent` | `#378add` | active tab underline, links, revenue bars |
| `$accent-bg` | `rgba(55, 138, 221, 0.15)` | accent badges/buttons bg |
| `$accent-text` | `#58a6ff` | text on accent-bg |
| `$success` | `#1d9e75` | margin bars, fills |
| `$success-bg` | `rgba(29, 158, 117, 0.15)` | score/pass badges bg |
| `$success-text` | `#3fd0a4` | positive numbers, pass icons |
| `$danger-bg` | `rgba(226, 75, 74, 0.15)` | risk badges bg |
| `$danger-text` | `#f28b8a` | negative numbers, fail icons |
| `$warning-bg` | `rgba(239, 159, 39, 0.15)` | mid-score badges bg |
| `$warning-text` | `#efb454` | unknown/stale indicators |
| `$radius` | `8px` (controls) / `12px` (cards) | |

Typography: system stack (`-apple-system, Segoe UI, Roboto, sans-serif`), body 13–14 px, headings 500 weight (never 600+), metric numbers 20 px/500. Sentence case everywhere. Numbers formatted `pl-PL` (comma decimals, thin-space thousands), currency `zł`, negative in `$danger-text`, positive in `$success-text`.

## Component rules

- **Score badge (AI 0–100):** pill, 12 px, 500 weight — ≥70 success, 40–69 warning, <40 danger, `brak` muted text when no analysis.
- **Prescore checklist row:** icon (`check`/`x`/`help` = pass/fail/unknown) + item name in `$text-primary` + evidence numbers in `$text-muted` on the same line. Header shows `n / total` badge.
- **Metric cards:** `$surface-1`, no border, radius 8, label 12 px muted above 20 px value. Grid `auto-fit minmax(100px, 1fr)`.
- **Raised cards:** `$surface-2`, 0.5 px `$border`, radius 12, padding 12–16 px.
- **Tables:** no vertical rules; 0.5 px row separators; numeric columns right-aligned; header 12 px muted 500.
- **Tabs:** text + 2 px accent underline for active; inactive `$text-muted`. Order: Przegląd, Finanse, Wykresy, Prognoza, Forum, Analiza AI.
- **Charts (recharts):** revenue bars `$accent`, margin bars/lines `$success`, older-than-TTM bars at 45 % opacity; axis labels 11 px muted; both "quarterly sequence" and "y/y quarter comparison" views.
- **Forecast form:** two-column grid `label | input(right-aligned)`; each label carries a muted hint with the default's source (e.g. `· śr. 4 kw.`); result panel is a metric list with forward C/Z verdict line vs own median.
- **Freshness:** relative Polish text (`dziś 08:12`, `wczoraj`, `5 dni`) — warning color when > 3 days.
- **Icons:** Tabler icons (outline), 13–18 px, inherit color.
- Flat surfaces only: no gradients, no shadows; hover = background shift to `$surface-1` or border to `$border-strong`.
