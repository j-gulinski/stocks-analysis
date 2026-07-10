# Phase 5 — approval at the persistence boundary

The MCP save path is now a small application-service guard, similar to a C#
validator called before `DbContext.SaveChanges()`. It does not run a model and
it does not decide whether a company is attractive. It only prevents an
investment result from being labelled `pass` unless the deterministic scenario
snapshot, the current operating-bridge fingerprint and the independent strict
verifier all refer to the same inputs.

The important distinction is between a nullable workflow result and an
approved result. `draft` and `needs-human` are valid durable states because
missing evidence should remain visible. `pass` is narrower: every required
check must pass, and a stale fingerprint is rejected before the transaction is
committed. This is the database equivalent of checking an immutable version key
before joining two C# aggregates.

The tests cover both sides of the boundary: a complete fixture can move from
`needs-human` to `pass`, while a changed bridge remains `needs-human`. The
contract still does not implement a provider call; that is the next RT5.1–RT5.3
slice.
