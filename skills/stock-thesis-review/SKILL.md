---
name: stock-thesis-review
description: Revisit one due Stock Analysis Workbench research case after its scheduled quarterly date or an explicitly selected material event. Use only for a claimed queue row; never start polling or a recurring worker.
---

# Stock thesis review

Work one claimed, due review row. The database schedules the review; the user
chooses when `$workbench-run-queue` claims it. Do not create a timer, poll a
source or claim a future row.

1. Read `docs/project-guardrails.md`, load the current dossier and freeze the
   queue row's promotion/review context in `input_snapshot`.
2. Compare the original human triage price/note/evidence reason and any later
   journal/thesis snapshot with new stored primary evidence. Treat forum text
   only as a labelled lead.
3. State what changed, what held, falsifiers, scenario changes and the next
   dated check. If there is no material new evidence, say so explicitly.
4. Use `stock-result-verifier` and `stock-verifier`; the strict verifier owns
   any final score/confidence. Save through `save_analysis_run` with this
   `agent_run_id`.
5. Never issue a buy/sell instruction or create another recurring worker.
