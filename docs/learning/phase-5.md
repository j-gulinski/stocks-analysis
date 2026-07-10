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

## Keyless Codex operation

The app and Codex are two cooperating processes. The app exposes a local MCP
server from `.codex/config.toml`; Codex calls its tools inside the current
session. If that transport is unavailable, the JSON scripts are equivalent to
small C# console commands: one claims the work, one saves the draft, and one
saves the verifier result. Both paths write the same database rows and neither
requires an OpenAI API key.

Prompt-injection isolation is also a data-contract concern. The application
does not try to decide whether a sentence is malicious. It labels source
payloads as untrusted data and tells the Codex worker which instruction layers
are authoritative. This is similar to keeping a C# `SourceText` value separate
from executable commands instead of passing both through one string parser.

The model policy is guidance, not an SDK selector. It is like a C# strategy
registry that returns the required role and validation scope; it cannot know
which concrete model Codex is hosting. That concrete value is recorded only
when the Codex session exposes it, so the audit trail never mistakes a role
label for a deployment name.
