# Architecture notes — cross-cutting design decisions

This file collects architectural decisions that span multiple components and
that aren't easily captured inline in a single source file. The canonical
architecture doc is `_bmad-output/planning-artifacts/architecture.md`; this
file is the working memo for decisions that need fast-write access during
implementation.

## AR-D13-1 — Cron split between Hermes and mailbot-api

**Decision (Story 6-6, 2026-06-03):** the project runs TWO cron schedulers
side by side. Hermes owns agent-involving jobs; mailbot-api owns LLM-free
critical infra.

### Why split

The original Rule X read "one cron scheduler" — but that conflates two
different reliability domains:

- **Hermes** can be down for arbitrary periods (image restart, config edit,
  upgrade). The agent recovers; conversation state persists.
- **Sync** (Outlook → SQLite) CANNOT be down — the FR-1.1 promise is
  "fresh inbox within 4 minutes." Adam's trust signal hinges on this.

If sync lived in Hermes cron and Hermes restart-looped (as it did during the
Epic 5 Phase 3.5 walk before Story 6-0's fix), sync would silently stop.
Tying sync availability to Hermes uptime breaks the inbox-freshness promise.

So: the LLM-free critical infra lives in a separate scheduler inside
`mailbot-api`. Its uptime is decoupled from Hermes's. Hermes hosts only the
jobs that need the agent (digest, weekly drift, weekly sampling).

### Where each job lives

**Hermes cron (declared via `hermes cron add` per Story 6-0 docs probe):**

- `daily_digest_0800` — Story 6.5; invokes `compose_digest()` MCP verb +
  generates an intro paragraph via Qwen + posts to Discord
- `weekly_drift_sun_0900` — Epic 7; runs the KL-divergence drift report
- `weekly_sampling_sun_0930` — Epic 7; samples production rows for the eval
  corpus

These all involve the agent (LLM dispatch) and conversation-level effects
(Discord posts). Hermes is their natural home — its cron context already
has the gateway + LLM provider configured.

**mailbot-api scheduler (this story):**

- `sync` — Story 1-8; every 4 minutes (FR-1.1, aligned to Anthropic cache TTL)
- `ingest_pipeline` — Story 3-6; every 5 minutes; one drain batch per tick
- `cooling_off` — Story 4-6; every 1 second; promotes due `cooling_off` rows
  to `pending`
- `cache_warmer` — Story 2-7; every 4 minutes (Rule M)
- `anomaly` — Story 2-9; hourly; volume-anomaly detection across caller_origin
- `oauth_token_refresh` — Story 6-6; aligned to sync; keeps the
  drainer's Outlook adapter token cache warm
- `actions_drainer` — Story 4-4 + 6-6; continuous loop (not periodic); claims
  + dispatches `pending_actions` via `OutlookGraphWriteAdapter`

None of these need the agent. They all read/write SQLite and HTTP-call
external services (Graph, Ollama). They CAN'T live in Hermes cron because
Hermes uptime is decoupled from `mailbot-api` uptime by design.

### Where future-story jobs land

- Story 6.3 `notifications_outbox` delivery (every 10s) → mailbot-api scheduler
- Story 6.4 daily engagement-metric tick (07:00 local) → mailbot-api scheduler
- Story 6.5 daily digest (08:00) → Hermes cron (it's the canonical
  agent-job)

When Story 6.3 / 6.4 ship, they `register_interval_task` on the existing
scheduler — no architectural change needed.

### Worker process structure

`mailbot_api/worker.py:_worker_main` boots:

1. `_CachedAccessToken` cell + initial oauth_state read
2. `OutlookGraphWriteAdapter` constructed with the cell as token provider
3. `Scheduler` instance — 4 interval tasks (sync, ingest, cooling_off,
   oauth_token_refresh) + 2 managed tasks (cache_warmer, anomaly)
4. Continuous drainer task launched separately (claim-and-drain semantics
   are continuous, not periodic)
5. Heartbeat poll loop for the drainer (writes `actions_drainer` rows)
6. SIGTERM / SIGINT wired to a shutdown event for clean teardown

`worker_health` is the single source of truth for `mailbot status` (Story
6.1): one row per component, upserted on every iteration.

### What this rules out

- A single cron scheduler with mixed Hermes/mailbot-api ownership.
- Sync running inside Hermes (the original Rule X reading) — it must be in
  mailbot-api.
- The mailbot-api scheduler invoking LLM dispatch (caller_origin discipline
  requires those calls to flow through Hermes cron's agent context, not
  through the scheduler).

### What this doesn't address

- Cross-scheduler observability — if Hermes cron's `daily_digest_0800` fails,
  the mailbot-api scheduler doesn't know. Story 6.3's notification dispatcher
  is the eventual coordination point; until then, Hermes-side failures go
  to Hermes logs.
- Hermes cron job-declaration mechanism — real Hermes manages cron via the
  `hermes cron add` CLI (per Story 6-0 RECONCILIATION-NOTES). The
  declarations are runtime, not file-driven. Story 6.5 will document the
  operator commands for `daily_digest_0800` setup.
