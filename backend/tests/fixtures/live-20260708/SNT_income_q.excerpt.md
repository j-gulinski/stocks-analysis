EXCERPT of the agent-level `mcp__workspace__web_fetch` extraction of
https://www.biznesradar.pl/raporty-finansowe-rachunek-zyskow-i-strat/SYNEKTIK,Q
(fetched 2026-07-08, HTTP 200, slug URL — ,Q suffix preserved in the request).

FULL web_fetch output = 72,742 characters across 114 lines (too large to store
inline). It is a stripped markdown/text extraction, NOT raw HTML. `grep -c` over
the FULL output for the markers the parsers require:
    report-table   -> 0
    data-field     -> 0
    span.value     -> 0
    table/tr/td tags -> 0
i.e. ZERO HTML structure. The report table renders as a giant single-line
markdown pipe-table. Representative fragments (verbatim from the full output):

--- period header row (line 100) ---
... 2026/Q1  (gru 25) ...            <- period labels ARE present & normalizable

--- data row: "Przychody ze sprzedaży" (line 103) ---
Przychody ze sprzedaży](https://www.biznesradar.pl/spolki-raporty-finansowe-rachunek-zyskow-i-strat/branza:biotechnologia,Q,IncomeRevenues,2,2,0 "Przychody ze sprzedaży")**  | 1 955 | 6 798   k/k +247.72%~branża +54.06% | 6 069   k/k -10.72% | ...

Two fatal losses for the existing pipeline, both visible above:
1. NO `data-field` attribute. The stable row-identity code (`IncomeRevenues`)
   survives ONLY inside a sector-comparison link URL, and only for rows that HAVE
   such a link (derived/subtotal rows and many indicator rows do not). The
   quirks ledger requires code-first identity (IncomeGrossProfit="Zysk ze
   sprzedaży" trap; cz vs czo; "Marża zysku brutto"=pretax trap; label
   duplication across balance sections) — label-only matching re-triggers exactly
   those traps.
2. VALUE + k/k change + ~branża sector comparison are MERGED into one cell
   (`6 798   k/k +247.72%~branża +54.06%`). In HTML these are separate
   value spans (`span.value` plus siblings); the parser reads only span.value. The
   markdown collapses them, so a re-parser must re-segment every cell heuristically.

Conclusion: recovering this into the pipeline needs a brand-new bespoke markdown
parser (untested; CLAUDE.md requires green fixture tests for parser changes;
bypasses the very parser stage under validation) — a disallowed workaround.
