---
name: stock-thesis-review
description: Revisit one due Stock Analysis Workbench ResearchCase after a claimed review job or explicitly selected material event. Use only for that claimed row; never poll or create a recurring worker.
---

# Review one research case

1. Read `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, and the claimed row's frozen
   context. Load the current verified/provisional research snapshot and the new
   stored evidence available by the row's cutoff.
2. Compare what the prior thesis expected with what changed. Separate primary
   evidence, deterministic result changes, human assumptions, and forum leads.
3. Update the company-specific drivers, counter-thesis, catalysts, falsifiers,
   gaps, and next dated check. State explicitly when evidence does not justify
   a thesis change.
4. Run the independent strict verifier required by the row. Save an immutable
   ResearchSnapshot linked to the same `agent_run_id`; do not overwrite prior
   history.
5. Never issue a buy/sell instruction, mutate the portfolio, claim a future
   review early, or create another worker.
