# Story 6-10 — Hermes-side Mechanism Design Decision

**Date:** 2026-06-04
**Author:** Amelia (reconnaissance + recommendation)
**Status:** Recommendation pending Adam approval before implementation begins
**Scope:** Pick the Hermes-side mechanism that consumes mailbot-api's two Epic 6 carry-forward contracts:

1. **Story 6.3 pull-based notification delivery** — ~10s pull loop that calls `pull_pending_notifications` MCP tool → posts each pending row to Discord → calls `ack_notification` MCP tool.
2. **Story 6.5 daily digest 08:00 trigger** — wall-clock cron at 08:00 local time that calls `compose_digest` → `ask_router(task_type="daily_digest_intro")` for the Qwen intro → posts to Discord → calls `finalize_digest_delivery`.

---

## §1. Reconnaissance findings

### 1.1 Hermes has a first-class durable cron scheduler

Discovered in `hermes-config/skills/autonomous-ai-agents/hermes-agent/SKILL.md:639-658` (the self-describing Hermes skill bundled with the image). Key facts:

| Surface | Detail |
| --- | --- |
| Driver source | `cron/jobs.py` + `cron/scheduler.py` (inside Hermes) |
| CLI | `hermes cron create SCHED`, `list`, `edit`, `pause`, `resume`, `run`, `remove`, `status` |
| Slash command | `/cron` (manage from chat) |
| Agent tool | `cronjob` (agents can schedule durable jobs from inside a session) |
| Schedule formats | duration (`"30m"`, `"2h"`), "every" phrase (`"every monday 9am"`), 5-field cron (`"0 9 * * *"`), ISO timestamp |
| Per-job knobs | `skills` (bundled-skill access), `model`/`provider` override, `script` (pre-run data collection), `no_agent=True` (makes the script the whole job — pure cron, no LLM), `context_from` (chain output of job A into prompt of job B), `workdir` (run in a specific dir with its `AGENTS.md`/`CLAUDE.md` loaded), multi-platform delivery |
| Lock file | `.tick.lock` in the cron storage dir prevents duplicate ticks across processes |
| Hard interrupt | 3-minute timeout per run |
| Memory isolation | cron sessions pass `skip_memory=True` by default — won't pollute persistent agent memory |
| Delivery framing | cron deliveries are framed with header/footer rather than mirrored into a gateway session — keeps role alternation intact, so the cron output doesn't break the user's ongoing chat |

**Live evidence:** `hermes-config/cron/.tick.lock` (file mtime 2026-06-03 23:39) exists at the bind-mount root. The scheduler IS running in our deployed stack.

### 1.2 Hermes auto-registers installed skills as Discord slash commands

Per RECONCILIATION-NOTES §1.4: skills in `~/.hermes/skills/` (bind-mounted at `/opt/data/skills/` in Docker) get auto-discovered and auto-registered as Discord Application Commands. **But this is for on-demand invocation, not for background work.** Skills can bundle `scripts/` directories (see `hermes-config/skills/creative/comfyui/scripts/`, `hermes-config/skills/creative/excalidraw/scripts/`, etc.) — those scripts run when the skill is invoked, not on a wall-clock schedule.

**Implication for Story 6-10:** skills alone are NOT the right mechanism for our background consumers. We need the cron scheduler. Skills MAY play a supporting role (e.g., the 08:00 digest cron job could grant access to the existing `mailbot` skill bundle so the agent inside the cron run can dispatch MCP tools to mailbot-api).

### 1.3 The `no_agent=True` + `script` combination is the unlock

This is the single most important knob discovered. When `no_agent=True` is set on a cron job:

- The job runs ONLY the `script` (pre-run data collection step).
- No LLM call. No token cost. No model timeout. Pure cron execution.
- The script has access to env vars (so `MAILBOT_ROUTER_KEY` etc. flow through).
- The script can emit content that gets posted via Hermes's multi-platform delivery layer (so Discord posting is one config knob away).

**This is the cleanest possible mechanism for the Story 6.3 pull loop** — the pull loop is pure HTTP plumbing (call MCP tool → post to Discord → call ack MCP tool); we'd be wasting an LLM call on it.

For the Story 6.5 08:00 digest, we DO want the LLM call (the Qwen intro paragraph), so that job uses `no_agent=False` (default) and a script that calls `compose_digest` first, then the agent generates the intro, then the agent posts to Discord and calls `finalize_digest_delivery`. Two different shapes for the two consumers; Hermes accommodates both natively.

### 1.4 RECONCILIATION-NOTES §6 prior decisions

| Carry-forward item | What it said | Implication for 6-10 |
| --- | --- | --- |
| §6.1 `hermes-config/skills/mailbot/` skill-bundle refactor for slash commands | "Owner: Story 6-3 work (or a dedicated follow-up) — the dispatcher contract change is non-trivial." | The slash-command refactor is a SEPARATE story. Story 6-10 should NOT couple itself to a slash-command bundle redesign. It uses the cron scheduler, which is orthogonal to slash registration. |
| §6.2 caller_origin granularity loss in auxiliary calls | "Plan: future `policy.yaml` task entries `hermes_aux_compression` + `hermes_aux_title` distinguished by the model name." | Story 6-10's `ask_router(task_type="daily_digest_intro", caller_origin="hermes-cron-digest")` call already uses an explicit `caller_origin` parameter — no model-name distinction needed for this surface. |
| §6.3 NFR-OPS-6 emergency fallback CLI provisioning | "Operator-runs `hermes fallback add anthropic claude-opus-4-7` from inside the Hermes container during first deploy; document in Story 6-7's `setup_vps.sh` runbook." | Story 6-7 already shipped the runbook with this. Story 6-10's cron-job creation can follow the same pattern: operator-runs `hermes cron create` from inside the container OR the cron-skill ships a setup script that issues the `hermes cron create` calls idempotently. |
| §6.4 Docs-archiver full mirror | "Plan: when Adam has the key, re-run `docs-archiver` for the canonical artifact." | Not relevant to Story 6-10. |

**The pattern §6.3 establishes is the right one for Story 6-10:** the operator (or a setup script run by the operator) issues `hermes cron create ...` calls inside the container as part of first-deploy bootstrapping. The cron jobs persist in Hermes's durable storage (`hermes-config/cron/`) and survive container restarts.

---

## §2. Candidate mechanisms

### Mechanism A — `hermes cron` jobs with `no_agent=True` script for the pull loop + `no_agent=False` agent for the digest

**Pull loop (Story 6.3 consumer):**

```bash
hermes cron create "every 10s" \
  --name "mailbot-notifications-pull" \
  --script "/opt/data/skills/mailbot/scripts/pull_and_deliver.sh" \
  --no-agent \
  --delivery discord
```

The script `pull_and_deliver.sh` (bundled in `hermes-config/skills/mailbot/scripts/`):

1. Calls `pull_pending_notifications` MCP tool via `hermes mcp call mailbot-api pull_pending_notifications`.
2. For each returned row, formats and posts to Discord via `hermes discord post --user $DISCORD_HOME_USER --content "..."`.
3. Calls `ack_notification` MCP tool with the row id + delivery status.
4. Emits structured log line per acked row.

**Digest (Story 6.5 consumer):**

```bash
hermes cron create "0 8 * * *" \
  --name "mailbot-daily-digest" \
  --script "/opt/data/skills/mailbot/scripts/digest_prepare.sh" \
  --skills mailbot \
  --delivery discord
```

The job runs in this order:

1. **Pre-run script `digest_prepare.sh`** — calls `compose_digest` MCP tool, dumps the 4-section payload to a tmp file, exits.
2. **Agent run** — Hermes spawns an agent with the `mailbot` skill bundle attached and the pre-run script output as context. The agent's prompt is "Generate a defender-toned intro paragraph (≤200 chars) for today's digest payload" — this fires `ask_router(task_type="daily_digest_intro", caller_origin="hermes-cron-digest")` via the auxiliary routing path.
3. **Agent post-processing** — agent renders the final message (intro + sections) and posts to Discord via the `messaging` tool.
4. **Agent ack** — agent calls `finalize_digest_delivery` MCP tool.

**Pros:**

- Native Hermes mechanism. Durable, restart-safe, observability built-in (Hermes logs cron tick + run outcomes).
- `no_agent=True` for the pull loop avoids any LLM cost on the high-frequency surface.
- `skills` knob grants the digest agent exactly the MCP access it needs — minimal-privilege.
- Multi-platform delivery is built-in (we use Discord; future Telegram/Slack/etc. would be one knob).
- Three-minute hard interrupt protects against runaway jobs.
- `.tick.lock` prevents duplicate firing — already present in our deployed stack.
- Aligns with the §6.3 NFR-OPS-6 pattern (operator-runs CLI calls during bootstrap).

**Cons:**

- The script files (`pull_and_deliver.sh`, `digest_prepare.sh`) live in `hermes-config/skills/mailbot/scripts/` — they're shell/Python utilities, separate codebase from `mailbot_api/`. Adds a small surface area to maintain.
- First-deploy requires the operator to run `hermes cron create ...` calls (or a setup script that does it). Story 6-7's runbook needs an addendum.
- `hermes cron list` / inspection surface is Hermes-side; debugging from mailbot-api requires shelling into the Hermes container or relying on `hermes cron status` output.

### Mechanism B — Inline cron in mailbot-api worker (host the cron loop ourselves, post to Discord via Hermes HTTP)

Add the pull loop to `mailbot_api/observability/scheduler.py` as a 10s interval task; add the 08:00 digest as a daily interval task; both call `mcp tools/call` against ourselves locally and then POST to a Hermes HTTP endpoint to fire the Discord message.

**Pros:**

- Single codebase (mailbot-api). Easier to maintain. Tests + boundary checks + CR cadence all apply uniformly.
- No operator-side `hermes cron create` step at first deploy.
- The worker_health table already tracks scheduler heartbeats — pull loop + digest would land in the existing observability surface.

**Cons:**

- **This is exactly the schema-reality reframe Epic 6 retired three times.** Story 6.3's epic spec invented "Hermes inbound HTTP webhook for posting to Discord"; the schema-reality reframe replaced it with the pull-based MCP contract because Hermes does NOT expose an inbound HTTP endpoint for arbitrary Discord posting — Discord delivery happens via Hermes's gateway, which is a long-running daemon process, not an HTTP server. There is no `POST /discord/send` endpoint to call.
- Even if we tried to bridge via the cronjob tool (which CAN deliver to Discord), we'd be re-implementing Hermes's cron scheduler in mailbot-api, then asking Hermes to take a single dispatched message — fighting the grain of the existing tool.
- Violates Rule X (mailbot-api Python free of LLM behavior) for the digest's Qwen intro call — mailbot-api would have to orchestrate a Hermes-side LLM call, blurring the boundary.
- Multi-platform delivery would have to be re-built (Hermes does this for free).

**Verdict:** Mechanism B fights the architectural grain. Rejected.

### Mechanism C — External cron (host crontab calling curl against MCP) for the pull loop + `hermes cron` for the digest

Operator sets up host-side `cron` or systemd-timer on the VPS that runs `curl http://localhost:8000/mcp ...` to invoke the pull. The digest still uses `hermes cron` because it needs the Qwen call.

**Pros:**

- Pull loop is dead-simple shell.
- No Hermes-side mechanism dependency for the pull loop.

**Cons:**

- Two different cron mechanisms (host + Hermes) for two related consumers — maintenance burden.
- Host cron has no integration with Hermes's gateway for Discord posting — the script has to manually POST to a Hermes HTTP endpoint. Same problem as Mechanism B: that endpoint doesn't exist.
- Bypasses Hermes's `.tick.lock` + 3-min hard interrupt + multi-platform delivery — re-implements them poorly.

**Verdict:** Rejected. Splits the problem unnaturally and re-introduces the Hermes HTTP fiction.

---

## §3. Recommendation — Mechanism A

**Use `hermes cron` jobs natively for both consumers.** The pull loop runs `no_agent=True` with a pure shell/Python script for zero LLM cost; the daily digest runs `no_agent=False` with a pre-run script + agent run for the Qwen intro paragraph.

### Why this is the right call

1. **Architectural fit.** Hermes ships a durable cron scheduler. Use it. The schema-reality reframe pattern from Epic 6 (three times) said: don't invent contracts when real ones exist. Hermes's cron scheduler is the real contract.
2. **Cost discipline.** `no_agent=True` on the pull loop means zero LLM tokens for 8,640 ticks per day. The only Qwen call is the 08:00 digest intro — once per day, capped at 200 tokens, response-cached at the verb layer.
3. **Operational hygiene.** Durable persistence, `.tick.lock`, 3-min hard interrupt, `skip_memory=True`, structured framing — all free.
4. **Boundary integrity.** Mailbot-api stays free of LLM orchestration (Rule X). The `caller_origin="hermes-cron-digest"` is set in the cron job's `ask_router` call, lands in `router_calls` cleanly, audit + drift alarm work uncoupled.
5. **Maintenance surface is small.** Two shell scripts (~30-50 lines each) in `hermes-config/skills/mailbot/scripts/` + two `hermes cron create` invocations idempotently issued by an addendum to `scripts/setup_vps.sh`. The mailbot-api side is already complete.

### What this story implements

1. **`hermes-config/skills/mailbot/scripts/pull_and_deliver.sh`** — pull-loop script for the 10s cron job. Calls `pull_pending_notifications` MCP, posts each row to Discord, calls `ack_notification`. Idempotent on race losses (uses the `notification.ack.race_loss` observability log per Story 6.3 CR HIGH-2).
2. **`hermes-config/skills/mailbot/scripts/digest_prepare.sh`** — pre-run script for the 08:00 cron job. Calls `compose_digest` MCP, dumps payload to `$HERMES_CRON_OUTPUT/digest-payload.json`, exits 0.
3. **`hermes-config/skills/mailbot/scripts/digest_post.sh`** — post-agent script (or agent-tool-call sequence in the cron run) that takes the agent's intro paragraph + the saved payload, renders the final Discord message, posts via `messaging` tool, calls `finalize_digest_delivery`. (Implementation may collapse this into a single agent-driven flow inside the cron run rather than two separate scripts — TBD at code time.)
4. **`hermes-config/skills/mailbot/SKILL.md`** — amended to document the two cron jobs (separate from the slash-command-facing tool listing). Frontmatter unchanged (Story 6-6.9 already fixed it).
5. **`scripts/setup_vps.sh`** — addendum after `hermes` container is up: idempotently runs `hermes cron create` for both jobs (using `hermes cron list | grep -q <name>` guard so re-runs of setup_vps are no-ops). Documented in `docs/setup-vps-runbook.md` §X.
6. **Walk record** — once the cron jobs are running, append a Phase 3.5 walk record to `epic-6-run-flags.md` documenting: pull-loop end-to-end (urgent notification enqueued → reaches Discord within 30s), digest end-to-end (08:00 on a real day → digest message in Discord), retries on failure, dedup collapse end-to-end.

### What this story does NOT touch

- The slash-command-via-skill-bundle refactor (RECONCILIATION-NOTES §6.1) — separate story, separate scope.
- F11 (chat-completions tool-calling) — Story 6-9's territory. Story 6-10 doesn't need tool-calling support because the cron jobs invoke MCP tools DIRECTLY via `hermes mcp call`, not via the chat-completions endpoint. (This is a meaningful observation: Story 6-10 can ship BEFORE Story 6-9 closes, despite the retro suggesting 6-9 should land first. The dependency is not actually present.)
- `caller_origin` granularity for auxiliary calls (RECONCILIATION-NOTES §6.2) — not relevant to 6-10's surfaces.

### Dependency revision (important)

Story 6-10 was originally filed as Path B's second step (after Story 6-9 F11 closure). **The reconnaissance reveals 6-10 does NOT depend on F11.** The cron jobs invoke MCP tools directly (via `hermes mcp call mailbot-api pull_pending_notifications` and similar) — not via `/v1/chat/completions`. The chat-completions endpoint is for LLM-driven tool-calling; cron-driven direct invocation is a different path.

**Implication:** Story 6-10 can ship in parallel with (or even before) Story 6-9. The done-flip gate amendment:

- **Old (per retro):** `6-9 → 6-10 → walks → done-flip`
- **Revised:** `6-9 || 6-10 (independent) → walks → done-flip`. The 6-6.5 capstone walk still depends on 6-9 (F11 is what makes the Discord round-trip work for the draft-reply flow), but the 6-3 pull loop + 6-5 digest are independent of F11.

This is good news — it means the urgent notification delivery and 08:00 digest can be live well before F11 closes.

---

## §4. Open questions for Adam (before implementation starts)

| # | Question | My default if you say "go" |
| --- | --- | --- |
| 1 | Should the pull loop interval be 10s (as Story 6.3 AC says) or longer? 10s × 8640 ticks/day is a lot of small SQL queries against the outbox even with the index. | 10s as specified; revisit after a week of real load if it shows up in `mailbot status` outputs. |
| 2 | When `notifications_outbox` returns an empty list, should the pull loop emit a "no-op" structured log or stay silent? | Stay silent (no log per empty tick). Story 6.3 already logs per-acked-row; empty-tick logging would be 8,000+ log lines per day. |
| 3 | For the digest, should the agent's intro generation happen INSIDE the cron run (one cron job, agent runs after the pre-script) or as a separate downstream cron job using `context_from` to chain? | Single cron job. `context_from` is for chaining multiple scheduled jobs; the intro generation is sequential within one scheduled run. |
| 4 | Should `pull_and_deliver.sh` retry the same row on a Discord post failure, or trust `ack_notification`'s `failed_<reason>` status + retry-by-re-enqueue? | Single attempt per tick; if delivery fails, `ack_notification(status="failed_<reason>")`. Story 6.3's worker-side retry-with-exponential-backoff loop owns the retry policy; the cron-skill is a thin transport. |
| 5 | First-deploy bootstrapping — should `setup_vps.sh` idempotently run `hermes cron create` for both jobs, or should there be a separate `bootstrap_cron.sh` script? | Add to `setup_vps.sh` (closer to the rest of the runbook). Single source of truth for first-deploy. |
| 6 | Should the cron jobs be `paused: True` at create time (operator must `hermes cron resume` to activate), or auto-active? | Auto-active. Once `setup_vps.sh` finishes, MailBot's notification + digest surface is live. Manual activation is friction without a clear safety benefit. |

---

## §5. Test strategy

Tests live in **two locations**:

1. **`tests/integration/test_mcp_pull_notifications_contract.py`** (mailbot-api side, already exists per Story 6.3) — verifies the `pull_pending_notifications` + `ack_notification` MCP tool contract. Unchanged by 6-10.
2. **`tests/integration/test_hermes_cron_scripts.py`** (new) — verifies the bash scripts work against a `mailbot-api` test fixture: `pull_and_deliver.sh` against a seeded outbox, `digest_prepare.sh` against an empty + populated digest payload. Uses `bash -n` syntax checks + `shellcheck` lint + a docker-fixture-backed integration test (similar shape to Story 6-7's `@manual` docker-in-docker test harness for `test_deploy_scripts.sh`). The actual cron tick is NOT tested in CI; it requires a live Hermes container and falls under the Phase 3.5 walk.

**Walk record covers:**

- Section A (agent-walked): script syntax + shellcheck + dry-run script invocation against a local mailbot-api with a seeded outbox.
- Section B (Adam-walked): live `hermes cron create` of both jobs in the running stack; verify urgent notification appears in Adam's DM within 30s; verify digest fires at next 08:00 with all 4 sections.

---

## §6. Recommendation summary

**Mechanism A: native Hermes cron + bash scripts + idempotent `setup_vps.sh` bootstrapping.**

- Pull loop: `hermes cron create "every 10s" --no-agent --script pull_and_deliver.sh --delivery discord`
- Digest: `hermes cron create "0 8 * * *" --script digest_prepare.sh --skills mailbot --delivery discord` (with agent for the Qwen intro)
- New files: 2-3 bash scripts in `hermes-config/skills/mailbot/scripts/` + `setup_vps.sh` addendum + cron-scripts integration test
- **Story 6-10 does NOT depend on Story 6-9.** Can ship in parallel or first.
- Existing CR cadence v2 applies (MANDATORY-CR per §5.12 — external operator surface + cross-story load-bearing seam — likely 2-3 criteria fire).

**Adam — does this match your read?** If yes, I'll start implementation: scripts first, then `setup_vps.sh` addendum, then tests, then walk record. If you want any of the §4 open questions decided differently before I proceed, say so now.
