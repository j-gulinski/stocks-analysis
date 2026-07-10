# Phase IL — decision loop notes

This slice adds the small investor workflow around the existing dossier:

- the decision journal is an append-only table, like an audit log rather than
  a mutable settings row;
- the thesis snapshot is hashed when saved, so a later dossier refresh cannot
  silently change the context of an old decision;
- the monitor stores a deterministic baseline and compares only selected stored
  values and ESPI identifiers; it does not call a scraper or AI model;
- the queue button claims one durable `AgentRun` and stops there. Codex owns the
  actual research, verifier pass and save operation.

For a C# analogy, `DecisionJournalEntry` is similar to an immutable event record
and the Pydantic request/response classes are lightweight DTOs. The monitor
service is deliberately a pure function layer: given two dictionaries, it
returns change records, which makes it straightforward to unit-test without a
database or HTTP server.

The runtime check also exposed a practical development issue: rebuilding a
Next.js `.next` directory while an older dev process is serving it can produce
missing chunk errors. Restarting the managed frontend after a production build
restores a coherent runtime bundle.

IL.3 adds a useful state-machine boundary: `holding`, `warning` and `fired` are
stored facts about the user’s thesis process, not computed verdicts. The API
requires a reason for every transition, similar to requiring an audit comment
when changing a workflow state in a C# service. The research queue can then use
the stored state for ordering without pretending it discovered the evidence.

IL.4 keeps portfolio data as a separate read model. The CSV importer behaves
like a small ETL boundary: validate explicit mappings, preserve unmatched rows
for the user, and use a stable source reference for idempotency. A future
myfund adapter uses the documented endpoint and still treats a remote error as
needs-human; a successful HTTP response is not assumed to mean a valid mapping
or a safe portfolio sync.
