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

## Opt-in periodic variant (CX.15d)

The default remains session-triggered: `./workbench start` runs the local
pre-session hook once and stops at the durable queue claim boundary. No daemon,
cron entry or hosted scheduler is installed by the repository.

If a user deliberately enables periodic polling, schedule only the existing
pre-session ingestion command, for example:

```bash
cd /Users/jgulinski/Claude/Projects/stocks-analyzis/backend
python scripts/codex_pre_session.py --trigger local-schedule --pretty
```

The job may poll ESPI/EBI and create one `stock-pre-session-brief` queue item
after complete ingestion. It must not call `process-one`, claim work, invoke a
model, or approve a result. The scheduled runner must prevent overlapping
invocations and keep source politeness/rate limits enabled. A failed or
incomplete poll remains visible as `ok: false` and must not create a queue item.

A hosted scheduler may use the same private API contract at
`POST /api/agent-runs/pre-session`, but only behind deployment authentication
and network access controls. Hosted polling is still ingestion-plus-queueing;
Codex remains the supervised local operator and owns claim, research,
verification and save. Personal Codex or provider credentials never move to the
hosted job.

## Notifications

Add Slack/email only after the queue and event contracts are stable. Messages
should identify company, event/source, freshness, severity and a link back to
the case; never include secrets or imply a buy/sell instruction.

## Gates

Before deployment: green tests, reproducible frontend build, auth, backups,
monitoring, source politeness, rate/cost limits, failure recovery and a
manual verification path. See `TASKS.md` RT.7 and the project guardrails.
