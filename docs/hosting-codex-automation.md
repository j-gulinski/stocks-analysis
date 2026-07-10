# Hosting, Codex attachment and communication automation

Date: 2026-07-10
Status: recommended architecture; exploration only, no deployment authorized.

## Recommendation

Use a **hybrid personal deployment first**:

- Vercel: Next.js UI and the only public browser entry point.
- Railway: FastAPI, PostgreSQL, short-lived scheduled ingestion jobs and a
  small notification dispatcher.
- Codex on the user's Mac (or a private always-on host): claims durable
  `agent_runs`, performs 5.3 Spark research/drafting, invokes the strongest
  verifier and saves the result.
- Slack first for short verified alerts; optional e-mail digest through a
  transactional mail API such as Resend.

Do **not** put a ChatGPT/Codex subscription credential inside Railway. The
hosted app queues work; the subscription-entitled Codex task consumes it when
available. If true 24/7 model execution becomes necessary, add a separate
OpenAI API worker and accept API billing rather than trying to reuse a personal
Codex session on a server.

```mermaid
flowchart LR
    U["Browser"] --> V["Vercel Next.js + Auth.js"]
    V -->|"Bearer + user email"| A["Railway FastAPI"]
    A --> P[("Railway Postgres")]
    R["Railway cron: ingest + enqueue"] --> A
    C["Codex task on trusted Mac"] -->|"HTTPS MCP/API, scoped token"| A
    C -->|"5.3 draft"] --> X["Strong verifier"]
    X --> P
    P --> N["Notification outbox"]
    N --> S["Slack webhook"]
    N --> E["Optional email digest"]
```

This preserves the existing architectural boundary: the UI and schedulers
create durable work; Codex is an operator, not an invisible request handler.

## Why this topology fits the current code

The repository already has most of the domain plumbing:

- the Next route proxy accepts `BACKEND_URL` and `BACKEND_API_TOKEN`;
- FastAPI exposes `/api/health` and durable `agent_runs`;
- Alembic/PostgreSQL are the system of record;
- `codex_pre_session.py` ingests ESPI/EBI and queues a brief;
- `codex_pick_agent_run.py` claims work and returns a skill contract;
- analysis save/verification closes the original queue row;
- the local stdio MCP server reuses the same `stock_tools` functions.

Missing production pieces are narrow but important: Auth.js, backend bearer
middleware, a remote HTTPS tool boundary, notification outbox/deduplication,
deploy manifests, backups and source-egress validation.

## Codex attachment options

### A. Recommended now — local Codex worker against hosted app

Add a bearer-protected **Streamable HTTP MCP** endpoint beside FastAPI, or a
small HTTPS adapter over the existing queue/dossier/save API. Reuse
`stock_tools`; do not duplicate analysis logic in the transport.

The Codex task runs on a trusted Mac and wakes periodically:

1. list one queued `agent_run`;
2. claim it atomically;
3. execute its repository skill;
4. save draft + source manifest;
5. run the strict verifier;
6. persist verified/rejected/needs-human;
7. let the server notification outbox announce the result.

Codex thread automations can wake the same task on a schedule while retaining
context. The database still owns continuity, so a lost/compacted thread cannot
change the source of truth.

Trade-off: jobs wait while the Mac/Codex task is offline. This is already an
honest state in the UI and is acceptable for the personal pilot.

### B. Fully hosted later — OpenAI API worker

Run an always-on Railway worker that consumes `agent_runs` and uses the OpenAI
Responses API/Agents SDK. The hosted model may call the workbench through a
remote MCP server; remote MCP supports Streamable HTTP or HTTP/SSE. Restrict
`allowed_tools`, require approval for sensitive mutations and log tool data.

This gives true 24/7 analysis, retries and predictable scheduling, but uses an
OpenAI API key and API billing. It should land only after model-policy budgets,
judge evaluation and the untouched holdout are credible.

### C. Not recommended as the investment runtime — Codex SDK in the web app

The official Codex SDK is server-side and useful for coding-focused Codex
threads, CI/CD and developer workflows. Official guidance recommends Codex as
an MCP specialist inside an Agents SDK workflow when the larger workflow is
not purely coding. This makes it useful for deployment/code maintenance, but it
does not justify coupling investment analysis requests directly to a Codex SDK
thread or storing a personal login token in the app.

## Railway/Vercel service layout

### Vercel

- `frontend/` root.
- `BACKEND_URL=https://<api-domain>`.
- `BACKEND_API_TOKEN`, Auth.js secrets and allowlisted Google accounts stay
  server-side.
- Route handlers remain the sole browser-to-backend path.

Vercel cron can call a route, but Vercel functions have duration limits and a
cron invocation is still a function request. Keep polite scraping and model
workers off this lane.

### Railway project

1. `api`: FastAPI long-running service; healthcheck `/api/health`; pre-deploy
   command `alembic upgrade head`.
2. `postgres`: managed database; private connection for services.
3. `ingest-cron`: short-lived command (pre-session ESPI/EBI, discovery source
   refresh, watchlist refresh); queues work and exits.
4. `notifier`: initially a short-lived cron that drains a Postgres outbox; an
   always-on worker is unnecessary at personal scale.
5. Optional later `model-worker`: OpenAI API consumer, only for fully hosted
   analysis.

Railway cron runs in UTC, has a five-minute minimum interval and skips a new
run if the previous one still runs. To handle Warsaw daylight-saving time,
trigger a cheap periodic command and let Python decide whether the local-market
window is due, recording an idempotency key for that window.

Do not add Redis initially. The existing Postgres queue is enough for one user
and one worker. Add Redis/Celery only after actual retry/fan-out load proves the
need.

## Communication flow

### Slack first

Use one private channel, for example `#stocks-workbench`, and a Slack incoming
webhook stored only as a Railway secret. Incoming webhooks accept an HTTPS JSON
POST and are bound to one selected channel.

Send only compact events:

- `verified`: ticker, one-line conclusion, scenario range, confidence, report
  link and source timestamp;
- `needs-human`: exact blocking source/question and report link;
- `source-alert`: material ESPI/EBI title, company and why it entered review;
- `worker-failed`: run id, safe error category and retry state;
- daily digest: queued/completed/rejected counts and the top three next checks.

Never send raw forum posts, credentials, full dossier JSON or hidden model
reasoning. A webhook cannot delete a sent message, so notifications must be
deduplicated before sending.

For inbound commands later, create a proper Slack app with signed request
verification and narrow commands such as `/stock SNT` or `/deep SNT`. These
commands only enqueue work; they do not bypass the verifier or mutate the
watchlist without an explicit user action.

### Optional email

Use a transactional provider for outgoing mail rather than a Gmail connector.
The documented OpenAI Gmail connector tools are for searching/reading mail,
not sending. Resend provides a simple HTTPS send endpoint and an
`Idempotency-Key`; a verified sending domain is required for normal delivery.

Email should be a daily or weekly digest, not one message per source event.
Slack handles immediacy; email handles an archive-friendly summary.

## Notification contract

Add a small durable `notification_outbox` before sending anything:

- `event_key` unique, e.g. `analysis-run:123:verified:slack`;
- `channel`: `slack` or `email`;
- `payload`: prepared safe summary, never raw source/model context;
- `status`: pending/sending/sent/failed;
- `attempt_count`, `next_attempt_at`, `sent_at`, safe error;
- link to `agent_run` / `analysis_run` / `event_report`.

Insert the outbox row in the same DB transaction that changes the verified run
status. The dispatcher retries delivery without repeating the investment work.

## Security and operational gates

- Auth.js allowlist on Vercel; backend rejects missing/invalid bearer tokens.
- Separate tokens for the Next proxy, Codex read tools and Codex mutating tools.
- Mutating remote tools require approval or a narrow allowlist.
- Encrypt provider/source/Slack/mail secrets in hosting dashboards only.
- Keep source snapshots and analysis manifests out of Slack/email.
- Daily Postgres backups plus a tested local restore.
- Validate BiznesRadar/PortalAnaliz from the cloud before moving ingestion;
  cloud IP blocking may require a trusted home/VPS ingestion agent.
- Healthchecks cover API/DB; job heartbeats and stale-run recovery cover workers.
- A notification is never proof of a verified result; it links back to the
  immutable app record.

## Proposed delivery order

1. **H0 — no deployment:** finish report/evidence/scenario/judge gates locally.
2. **H1 — hosted read path:** Railway API+Postgres, Vercel UI, auth, bearer
   boundary, backups; no scheduler/model automation.
3. **H2 — ingestion automation:** Railway cron queues source deltas and briefs;
   no model credentials in cron.
4. **H3 — local Codex attachment:** HTTPS MCP/API tool surface, scoped tokens,
   scheduled Codex queue consumer.
5. **H4 — Slack outbox:** verified/needs-human/failure messages; digest.
6. **H5 — optional e-mail:** daily digest with idempotent send.
7. **H6 — fully hosted model worker only if needed:** OpenAI API, strict
   budgets, traces, judge/holdout gate.

## Acceptance

- Browser access requires an allowlisted account.
- Direct backend/MCP access without the correct token is rejected.
- Scheduler creates at most one run per source/window policy.
- Turning off Codex leaves jobs queued, never falsely running.
- Only verifier-approved content is labelled verified in app/notifications.
- Slack/email delivery is idempotent and contains no sensitive/raw content.
- A failed notification can retry without re-running analysis.
- Postgres backup restores locally and preserves evidence/run lineage.

## Official references

- [OpenAI Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Run Codex as an MCP server with the Agents SDK](https://learn.chatgpt.com/docs/mcp-server)
- [OpenAI remote MCP and connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)
- [Railway cron, workers and queues](https://docs.railway.com/guides/cron-workers-queues)
- [Railway private networking](https://docs.railway.com/private-networking)
- [Railway monorepo deployment](https://docs.railway.com/guides/deploying-a-monorepo)
- [Vercel cron jobs](https://vercel.com/docs/cron-jobs)
- [Slack incoming webhooks](https://api.slack.com/messaging/webhooks)
- [Resend send e-mail API](https://resend.com/docs/api-reference/emails/send-email)
