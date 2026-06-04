# MailBot Hermes Cron Jobs — Verified Deployment Spec

Two `hermes cron` jobs registered inside the running Hermes container deliver MailBot's notification + digest surface. This document is the contract: paths, env vars, schedule formats, delivery target shape, and operator setup steps — all **verified live 2026-06-04** during the Story 6-10 Phase 3.5 walk.

---

## §1. Hard contract facts from the live walk

These rules MUST be honored; each one corresponds to a failure mode we hit and corrected during the walk.

| # | Rule | What goes wrong if you ignore it |
| --- | --- | --- |
| 1 | Cron scripts must live in `~/.hermes/scripts/` (= `/opt/data/scripts/` inside the container), not under the skill bundle. Hermes's cron validator rejects absolute paths AND traversal-via-symlink. | `Failed to create job: Script path must be relative to ~/.hermes/scripts/` OR `Script path escapes the scripts directory via traversal` |
| 2 | Script files must be **copies** (not symlinks) AND owned by `hermes:hermes`. | Traversal rejection (symlinks) or permission denied at cron tick (root-owned files Hermes user cannot read). |
| 3 | The `--deliver` flag requires the `platform:chat_id` form (e.g., `discord:1511105368468623532`). Bare `discord` produces a silent delivery skip. | `errors.log` shows `no delivery target resolved for deliver=discord`. Discord receives nothing. |
| 4 | `DISCORD_HOME_CHANNEL` must be populated in `.env` AND the Hermes container must be **recreated** (`docker compose up -d mailbot-hermes`) to pick up new env vars. `docker compose restart` keeps the old env cached and is NOT enough. | Env var shows empty inside the container even though `.env` has it set. |
| 5 | Hermes's cron scheduler `every <duration>` parser **rejects sub-minute cadences**. Minimum is `1m`. | `Failed to create job: Invalid duration: '10s'. Use format like '30m', '2h', or '1d'` |
| 6 | `every 1m` is recurring; bare `1m` is a one-shot delay (`Schedule: once in 1m`). Use the `every` prefix for recurring jobs. | Cron fires once, then never again, with no error. |
| 7 | Hermes's **cron-with-agent contract** is: the pre-run script's **stdout becomes the agent's prompt input**. Empty stdout → `script produced no output, skipping AI call` → no agent run → no Discord delivery. | Job runs every minute but never produces a message. |
| 8 | The `hermes cron create` CLI's `--no-agent` flag DOES NOT correctly reach the underlying tool's validator on some Hermes versions (live-verified bug, 2026-06-04). The validator fires `create requires either prompt or at least one skill` even when `--no-agent --script <name>` is passed. **Workaround**: call the cronjob tool function directly via `python3 -c` rather than the CLI (see §4 below). | `Failed to create job: create requires either prompt or at least one skill` even though `--no-agent --script ...` is on the command line. |

---

## §2. Job 1 — `mailbot-notifications-pull` (urgent-tier delivery loop)

**Purpose:** Drain the urgent-tier `notifications_outbox` queue. Posts each pending notification as a Discord message and acks the row terminal.

**Schedule:** `every 1m` (recurring; minimum supported cadence). Worst-case urgent SLA is ~90 seconds (60s pull cadence + Discord API latency + ack buffer). Note: this is a downgrade from Story 6.3's ~30s aspiration but is the actual Hermes constraint.

**Mode:** `no_agent=True` — pure transport, no LLM cost. Script's stdout becomes the cron delivery payload Hermes posts to Discord verbatim.

**Script path** (inside container): `/opt/data/scripts/pull_and_deliver.py`

**Env vars (read by the script inside Hermes):**

- `MAILBOT_ROUTER_KEY` (required) — bearer token for MCP auth. From `.env` via `docker-compose.yml` passthrough. P5 fix: `.strip()` applied so whitespace-only values surface as `cron.pull.missing_api_key`.
- `MAILBOT_MCP_URL` (optional; default `http://mailbot-api:8000/mcp/`)
- `MAILBOT_PULL_LIMIT` (optional; default `10`; server caps at 25 per `pull_pending_notifications` AC)

**Delivery target:** `discord:$DISCORD_HOME_CHANNEL` (your Discord DM channel ID with the bot).

**Exit code policy:** Always exits 0 even on transient failure. Cron retries on next tick. Structured failure logs land on stderr.

**Empty-tick behavior** (design-decision §4 Q2): silent — no stdout, no log line. Prevents 8000+ no-op log lines per day.

---

## §3. Job 2 — `mailbot-daily-digest` (08:00 daily digest)

**Purpose:** Compose and post the 08:00 daily digest. Two-phase:
1. Pre-run script (`digest_prepare.py`) calls `compose_digest` MCP tool → writes payload to both a file AND stdout (the stdout part is the AGENT'S prompt input per §1 rule 7).
2. Agent step generates the Qwen intro paragraph via `ask_router(task_type="daily_digest_intro")` → renders the digest → posts to Discord → calls `finalize_digest_delivery`.

**Schedule:** `0 8 * * *` — 5-field cron, 08:00 UTC daily.

**Mode:** `no_agent=False` (default) — agent runs each tick with the `mailbot` skill attached.

**Pre-run script path:** `/opt/data/scripts/digest_prepare.py`

**⚠️ F11 BLOCKER — verified live 2026-06-04:** The agent step needs to call `compose_digest` and `finalize_digest_delivery` as MCP tools, which requires OpenAI tool-calling support on `/v1/chat/completions`. This is exactly the carry-forward filed as Story 6-9 (F11 closure). Until F11 closes, the agent fires but exhausts retries with "Empty response (no content or reasoning)" — same signature as Story 6-6.9's F9 investigation. The digest will deliver a "No reply: the model returned empty content after retries" stub message to Discord. **This is a known F11 dependency, NOT a Story 6-10 bug.** Story 6-10 ships the cron registration, the script, the stdout-as-prompt contract, and the delivery wiring — all live-verified. The agent's tool-calling path is Story 6-9's territory.

**Env vars** (same as Job 1, plus):

- `MAILBOT_DIGEST_OUTPUT` (optional; default `/opt/data/cron/output/digest-payload.json`) — debug side-channel; the agent reads from stdin via the prompt, not from this file.

**Empty-payload behavior** (Story 6.5 AC): the agent prompt instructs the agent to post the terse fallback ("Inbox is clean. Nothing pending. Have a good day.") when every collection is empty.

---

## §4. Operator setup — verified live procedure

After `setup_vps.sh` completes and the stack is up:

### §4.1 — Confirm `.env` has the right Discord vars

```sh
# In the repo root on the host (PowerShell):
Select-String -Path .env -Pattern '^DISCORD' |
  ForEach-Object {
    if ($_.Line -match '=$') { "$($_.Line)<EMPTY>" }
    else { ($_.Line -split '=', 2)[0] + '=<set>' }
  }
```

Expected: `DISCORD_BOT_TOKEN`, `DISCORD_HOME_CHANNEL`, `DISCORD_ALLOWED_USERS` all `=<set>` (NOT `<EMPTY>`).

⚠️ Common gap: `.env` may have `DISCORD_CHANNEL_ID` instead of `DISCORD_HOME_CHANNEL` (Story 4-0 credential capture's name vs Hermes's documented contract). Rename if needed.

### §4.2 — Recreate the Hermes container (not just restart)

```sh
docker compose up -d mailbot-hermes
```

This is required to pick up env-var changes per rule 4. `docker compose restart` does NOT re-evaluate `.env`.

### §4.3 — Verify Discord vars reached the container

```sh
docker exec mailbot-hermes sh -c 'echo channel_set=$([ -n "$DISCORD_HOME_CHANNEL" ] && echo yes || echo no), length=${#DISCORD_HOME_CHANNEL}'
```

Expected: `channel_set=yes, length=19` (Discord channel IDs are 18-19 digits).

### §4.4 — Copy scripts into Hermes's expected location + fix ownership

```sh
docker exec mailbot-hermes sh -c '
  mkdir -p /opt/data/scripts &&
  cp /opt/data/skills/mailbot/scripts/pull_and_deliver.py /opt/data/scripts/ &&
  cp /opt/data/skills/mailbot/scripts/digest_prepare.py /opt/data/scripts/ &&
  cp /opt/data/skills/mailbot/scripts/_mcp_client.py /opt/data/scripts/ &&
  chown -R hermes:hermes /opt/data/scripts/ &&
  chmod +x /opt/data/scripts/pull_and_deliver.py /opt/data/scripts/digest_prepare.py &&
  ls -la /opt/data/scripts/
'
```

Note: rule 2 — **copies, not symlinks**. Hermes rejects symlinks as traversal.

### §4.5 — Register Job 1 (the pull loop) — workaround for the `--no-agent` CLI bug

The Hermes CLI has a bug (rule 8) where `--no-agent` doesn't reach the validator. Workaround: call the tool function directly via Python.

```sh
docker exec mailbot-hermes sh -c '
  cd /opt/hermes && python3 -c "
import os, json
os.chdir(\"/opt/data\")
from tools.cronjob_tools import cronjob
result = cronjob(
    action=\"create\",
    schedule=\"every 1m\",
    name=\"mailbot-notifications-pull\",
    script=\"pull_and_deliver.py\",
    no_agent=True,
    deliver=\"discord:\" + os.environ[\"DISCORD_HOME_CHANNEL\"],
)
print(json.dumps(json.loads(result), indent=2))
" && chown hermes:hermes /opt/data/cron/jobs.json
'
```

The `chown` at the end is **load-bearing**: the Python invocation runs as root by default; `jobs.json` ends up root-owned; the Hermes cron ticker (running as `hermes`) can't read it. Without the chown, you get `IOError reading jobs.json: Permission denied` in `errors.log`.

### §4.6 — Register Job 2 (the daily digest) — same workaround applied

```sh
docker exec mailbot-hermes sh -c '
  cd /opt/hermes && python3 -c "
import os, json
os.chdir(\"/opt/data\")
from tools.cronjob_tools import cronjob
result = cronjob(
    action=\"create\",
    schedule=\"0 8 * * *\",
    name=\"mailbot-daily-digest\",
    script=\"digest_prepare.py\",
    skill=\"mailbot\",
    deliver=\"discord:\" + os.environ[\"DISCORD_HOME_CHANNEL\"],
)
print(json.dumps(json.loads(result), indent=2))
" && chown hermes:hermes /opt/data/cron/jobs.json
'
```

Note: this job uses `skill=\"mailbot\"` and NO `no_agent=True` — the agent runs each tick.

### §4.7 — Verify both jobs registered

```sh
docker exec -u hermes mailbot-hermes hermes cron list
```

Expected output shape:

```
  <job_id_1> [active]
    Name:      mailbot-notifications-pull
    Schedule:  every 1m
    Repeat:    ∞
    Deliver:   discord:<numeric_channel_id>
    Script:    pull_and_deliver.py
    Mode:      no-agent (script stdout delivered directly)

  <job_id_2> [active]
    Name:      mailbot-daily-digest
    Schedule:  0 8 * * *
    Repeat:    ∞
    Deliver:   discord:<numeric_channel_id>
    Skills:    mailbot
    Script:    digest_prepare.py
```

Both `Deliver:` lines MUST end with a numeric channel id (NOT bare `discord`). If you see bare `discord`, re-register with the channel-id form per §4.5/§4.6.

### §4.8 — Smoke-test Job 1 (pull loop)

```sh
docker exec mailbot-api python -c "import asyncio; from mailbot_api.notifications.tiers import send_urgent; asyncio.run(send_urgent(message='cron pull smoke test', category='health', db_path='/data/mailbot.db'))"
```

Within ~90 seconds (worst-case cron cadence + Discord API), `[health] cron pull smoke test` should appear in your Discord DM, wrapped in Hermes's auto-added "Cronjob Response: ..." framing.

### §4.9 — Smoke-test Job 2 (digest)

```sh
docker exec -u hermes mailbot-hermes hermes cron run mailbot-daily-digest
```

⚠️ Until F11 (Story 6-9) closes, expect: `"No reply: the model returned empty content after retries..."` instead of a proper digest. The cron registration + script + delivery wiring all work; the agent's tool-calling path doesn't yet. Once F11 closes, retry this smoke test.

---

## §5. Troubleshooting (from the live walk)

| Symptom | Root cause | Fix |
| --- | --- | --- |
| `Failed to create job: Script path must be relative to ~/.hermes/scripts/` | You passed an absolute path | Copy script into `/opt/data/scripts/` per §4.4; use bare filename |
| `Script path escapes the scripts directory via traversal` | You used a symlink | Copy the file, don't symlink |
| `Failed to create job: Invalid duration: '10s'` | Sub-minute cadence | Use `every 1m` or longer |
| `Schedule: once in 1m` (job fires once and stops) | Missing `every` prefix | Use `every 1m` not bare `1m` |
| `Failed to create job: create requires either prompt or at least one skill` (with `--no-agent --script` already passed) | Hermes CLI `--no-agent` flag doesn't reach validator | Use the Python-call workaround in §4.5 |
| `cron.scheduler: ... no delivery target resolved for deliver=discord` | Used `--deliver discord` without channel id | Re-register with `discord:<channel_id>` per §4.5 |
| `channel_set=no` or env var empty in container | `docker compose restart` keeps old env | Run `docker compose up -d mailbot-hermes` |
| `cron.scheduler: ... script produced no output, skipping AI call` (digest job) | Script writes payload to file only, not stdout | Verify `digest_prepare.py` calls `sys.stdout.write(json.dumps(payload))` at end |
| `IOError reading jobs.json: Permission denied` in errors.log | `jobs.json` ownership flipped to root after direct-Python tool call | `docker exec mailbot-hermes chown hermes:hermes /opt/data/cron/jobs.json` |
| Cron tick fires (`Last run: ok`), stdout populated, but Discord receives nothing | Delivery target mismatch — `Deliver: discord` instead of `discord:<id>` | Re-register per §4.5 |
| Agent step (Job 2) returns "Empty response (no content or reasoning) after 3 retries" | **F11** — `/v1/chat/completions` drops `tools=[...]` parameter | Wait for Story 6-9 closure |

---

## §6. Why this story does NOT depend on Story 6-9 (F11) — for the pull loop only

**Job 1 (pull loop):** `no_agent=True`. The script invokes MCP tools directly via JSON-RPC over `/mcp/` (not `/v1/chat/completions`). No tool-calling-via-chat needed. **Verified live 2026-06-04 — works end-to-end against real Discord.**

**Job 2 (digest):** `no_agent=False`. The agent invokes MCP tools via `/v1/chat/completions` with `tools=[...]` — which is F11's exact gap. **Verified live 2026-06-04 — fails identically to Story 6-6.9's F9 investigation.** Will work once Story 6-9 ships F11.
