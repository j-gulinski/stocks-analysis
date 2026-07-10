# Hosting and automation — compact boundary

**Status:** deferred until the local evidence, scenario and evaluation gates
pass. The session-triggered local workflow is the default; see
[`plan-research-platform.md`](plan-research-platform.md) §7 and RT.7.

## Recommended topology

- Vercel: Next.js UI and route-handler proxy.
- Railway: FastAPI plus PostgreSQL, with backups and restricted service access.
- Short-lived jobs: source ingestion, notifications or hosted polling only if
  the watermark-based local workflow proves insufficient.
- Codex: supervised local operator/reviewer. Personal Codex credentials never
  live in the hosted app.

## Operating boundary

Hosted jobs may fetch sources, persist evidence and create a review queue. They
must not silently run or approve investment analysis, rewrite a thesis, or
present unverified output. Every run needs source, `as_of`, skill/model,
cost/status and verifier provenance.

## Notifications

Add Slack/email only after the queue and event contracts are stable. Messages
should identify company, event/source, freshness, severity and a link back to
the case; never include secrets or imply a buy/sell instruction.

## Gates

Before deployment: green tests, reproducible frontend build, auth, backups,
monitoring, source politeness, rate/cost limits, failure recovery and a
manual verification path. See `TASKS.md` RT.7 and the project guardrails.
