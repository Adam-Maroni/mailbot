# MailBot

Personal email triage agent. MailBot sits between Microsoft Outlook and Discord: it syncs your inbox via Microsoft Graph, classifies and prioritizes every email through a cost-disciplined LLM Router (local Qwen 3B for classification and privacy gating, Claude Haiku for summaries and scoring, Claude Opus for draft replies), and takes your instructions conversationally over Discord — with a 4-tier authorization model that never sends or deletes anything without your consent.

**Maturity:** runs live on the local Docker stack; VPS deployment (CP-1) is pending. See [Limitations & current status](#limitations--current-status).

```
Outlook ──Graph delta sync──▶ SQLite ──ingest (Qwen/Haiku)──▶ triaged inbox
                                                │
   Discord (Hermes agent) ◀──MCP verbs + chat──┤
   You: "show me unread"                        │
   You: "draft a reply"  ──propose → grant → cool-off──▶ mailbox write-back
```

---

## Talking to MailBot on Discord

You talk to MailBot in plain language in your Discord channel. The Hermes agent translates your message into read verbs (free, no cloud calls) or action proposals (tier-gated). All example outputs below are **illustrative** — real values will differ, but the shapes match the live contracts.

### Querying your mail

Reads are projection-first: MailBot answers from cached metadata + summaries and only opens a body when you ask about one specific email (capped at 5 body-reads per turn).

**Example — list unread:**

```text
You:  show me unread from today
```

```text
MailBot:  3 unread today:
1. **Invoice #2231 overdue** — billing@acme.com — 09:14
   ⭑ 82 · Payment reminder for the May invoice, due date passed 3 days ago.
2. **Re: Saturday hike** — sarah@example.com — 08:47
   ⭑ 45 · Sarah confirms 10am at the trailhead, asks if you're bringing the dog.
3. **Your weekly digest** — news@substack.com — 06:02
   ⭑ 12 · Newsletter roundup, no action needed.
```

**Example — importance filter:**

```text
You:  anything important this week?
MailBot:  2 emails scored above 70 this week:
1. **Invoice #2231 overdue** — billing@acme.com — ⭑ 82 — action: pay by Friday
2. **Contract renewal — signature needed** — legal@partner.io — ⭑ 78 — deadline 2026-07-08
```

**Example — thread summary:**

```text
You:  summarize that thread
MailBot:  Thread "Contract renewal" (4 messages, oldest first):
Continuity note: Partner sent the renewal 2026-06-28; you asked for a net-45
payment term; they countered net-30 and attached the revised PDF yesterday.
Latest message is waiting on your signature.
```

**Other queries that work the same way:**

| You say | What happens |
| --- | --- |
| "how many unread do I have?" | count only, no listing |
| "who is this person?" / "who is `billing@acme.com`?" | cached sender-reputation summary |
| "what does the email from Sarah say?" | opens that one body (5-per-turn cap) |
| "show me newsletters from this week" | filtered projection list |

You also get a **daily digest at 08:00** automatically — per-category counts, top-importance emails, and a short intro. You don't need to ask for it.

### Drafting and sending a reply

Sends are the most-protected action (Tier 3): draft → your approval → 60-second cooling-off → send. Hard cap of **20 sends per day**.

```text
You:  draft a reply to the invoice email

MailBot:  Here's the draft (tone-matched to billing@acme.com):

  Subject: Re: Invoice #2231 overdue
  ---
  Hi, thanks for the reminder — the payment was scheduled this morning
  and should clear within 2 business days. Apologies for the delay.
  ---
  Tone signals applied: concise, no greeting-name, sign-off "Best".
  ⚠ Defender note: none.

  send / edit: <new body> / refine: <instruction> / cancel

You:  refine: mention the PO number 4471

MailBot:  Updated draft:
  "...the payment for PO 4471 was scheduled this morning..."
  send / edit / refine / cancel

You:  send

MailBot:  ✅ Proposed (action #42, Tier 3). Cooling off for 60 seconds —
  type /cancel 42 to abort. Sends today: 3/20.

  (60s later)  📤 Sent to billing@acme.com.
```

Notes on this flow:

- "send", "send it", "go ahead" all confirm the **existing** proposal — you never need to repeat the request.
- During cooling-off, `/cancel <action_id>` aborts instantly.
- Refinement loops are capped at 5 iterations; MailBot will suggest starting over after that.
- The first draft to a new recipient costs an extra Opus call to fingerprint your tone with that person; it's cached for 30 days, so follow-ups are cheaper.

### Mailbox actions (archive, delete, mark read...)

Every mutation is tier-classified. You'll always see what MailBot intends to do before it happens.

| Tier | Actions (examples) | What you must do |
| --- | --- | --- |
| 0 | read, search, count | nothing — free |
| 1 | mark read/unread, add/remove category, move to triage folder | nothing — auto-applied; revertible for 24h ("undo that") — including triage-move (re-moved to its recorded source folder; moves applied before the pre_state capture shipped refuse with `PRE_STATE_MISSING`) |
| 2 | archive, move (batch) | approve the batch grant in chat |
| 3 | send, delete | grant + confirmation (sends also cool off 60s) |

**Example — Tier-2 batch archive:**

```text
You:  archive the newsletters from this week
MailBot:  Found 6 newsletters. I'll mint a grant for exactly these 6 —
  archive all of them? (yes / list them / no)
You:  yes
MailBot:  ✅ Grant minted (6 emails, archive). Applying... done — 6 archived.
```

The grant is scoped: those 6 emails, that action, that expiry. A 7th email needs a new grant.

**Example — Tier-1 triage move (live-verified pipeline trace, not a chat transcript — see the limitation below):**

```text
propose: move_to_triage_folder, email <id>, destination folder <id>   → action #4 queued (tier 1, no grant)
drain:   picked up ~0.3s later, dispatched POST /me/messages/{id}/move
applied: email physically in the target folder — verified in Outlook
```

<!-- verified 10-1, run_id action-4/2026-07-05 -->

Two real caveats on triage-moves today (both live-observed): the chat path can't resolve folder *names* to folder ids yet, and a moved email drops out of MailBot's local view until a full resync (the delta sync records it as deleted) — though a *reverted* move now repairs the local row on the way back (live-verified: `deleted_at` cleared the moment the revert applied). <!-- verified 10-2, run_id action-6/2026-07-05 -->

**Example — Tier-1 undo:**

```text
You:  undo that mark-as-read
MailBot:  ↩ Reverted — marked unread again. (Tier-1 reverts work within 24h.)
```

**Example — Tier-3 delete (always requires the confirmation token, regardless of the email's sensitivity):**

```text
You:  delete that
MailBot:  This deletes "Your weekly digest" (news@substack.com, 06:02).
  Deletes always require explicit confirmation:
  type  /confirm AAMkAGI2... delete  to authorize.
You:  /confirm AAMkAGI2... delete
MailBot:  ✅ Token accepted, grant minted. Deleted.
```

### Sensitive and confidential emails

The privacy invariant: email bodies classified **sensitive** or **confidential** never reach a cloud API silently.

- **Sensitive** → cloud tasks (summaries, drafts) are blocked until you explicitly confirm, per email, per task. The confirmation mints a single-use token valid 10 minutes.
- **Confidential** → no override exists. The body never leaves the machine. Period.

```text
You:  draft a reply to the email from my lawyer
MailBot:  ⚠ This email is classified sensitive. Drafting sends its content
  to Claude (Anthropic). Confirm with  /confirm AAMkAGX9... draft_reply
  or say "yes, escalate".
You:  yes, escalate
MailBot:  Token minted (valid 10 min, single use). Drafting...
  [draft appears as in the normal flow]
```

```text
You:  summarize the email titled "Salary review — CONFIDENTIAL"
MailBot:  Confidential emails admit no API override. The body stays on
  your machine, period. I can show you its metadata, or you can read it
  directly in Outlook.
```

---

## Slash commands

Typed in the Discord channel. The `/model` family is registered as a native Discord slash command (`scripts/register_discord_commands.py`); the rest are dispatched by the Hermes agent when you type them as a message.

| Command | What it does | Example output (illustrative) |
| --- | --- | --- |
| `/cost [today\|month]` | Cost breakdown per task / model / caller + cache hit rate | `Today: $0.18 — draft_reply $0.11, summaries $0.05, other $0.02. Cache hits: 61%.` |
| `/spend [today\|week\|month]` | Bar-chart PNG of cost per task + summary line | `📊 [chart] $4.11 spent month. Top task: draft_reply ($2.30). Cap: $30.` |
| `/pause [reason]` | Pause the Router (all LLM dispatch stops) | `⏸ Router paused (reason: "manual pause").` |
| `/resume` | Resume the Router | `▶ Router resumed.` |
| `/cancel <action_id>` | Abort a Tier-3 action during its 60s cooling-off | `🚫 Action #42 cancelled.` |
| `/budget reset` | Clear degraded mode after a monthly-cap trip | `Degraded mode cleared.` |
| `/mute <category> [until]` | Mute a notification category | `🔇 Muted "newsletter" until 2026-07-05T08:00Z.` |
| `/unmute <category>` | Lift a mute | `🔔 "newsletter" unmuted.` |
| `/confirm <email_id> <task>` | Mint the sensitivity/delete confirmation token | `Token minted (10 min, single use).` |
| `/model` | Show the current effective routing policy table | table of task → baseline / override / effective model |
| `/model <qwen\|haiku\|opus>` | One-shot: next chat turn uses that model (5-min TTL) | `Next call will use claude-opus-4-7 (one-shot, expires in 5m).` |
| `/model <task> <model>` | Persistent per-task override (survives restarts) | `draft_reply → claude-opus-4-7 (persistent).` |

`/model` overrides never bypass the sensitivity, budget, or degraded-mode gates — they only change which model the Router prefers.

---

## Operator CLI

Run inside the `mailbot-api` container (or on the host with `MAILBOT_DB_PATH` / `MAILBOT_ROUTER_KEY` set): `python scripts/mailbot.py <command>`.

| Command | What it does |
| --- | --- |
| `mailbot status [--base-url URL]` | Full status board: sync, ingest, actions, budget, cache, errors, router, OAuth, containers |
| `mailbot logs [--tail N] [--filter k=v] [-f]` | Tail/filter/follow docker-compose logs |
| `mailbot pause [reason]` / `mailbot resume` | Pause/resume the Router from the terminal |
| `mailbot sync-now` | Run one Graph delta-sync iteration immediately |
| `mailbot replay <action_id>` | Re-queue a failed action for re-drain |
| `mailbot revert <action_id>` | Revert an applied Tier-1 action (within 24h) |
| `mailbot rederive --task=<task> --since=YYYY-MM-DD [--prompt-version vN] [--yes]` | Re-run one ingest task over rows since a date (shows a cost estimate + confirmation first) |

`status`, `pause`, and `resume` require `MAILBOT_ROUTER_KEY`. Sample `mailbot status` (illustrative — a `!` prefix marks a warning section):

```text
SYNC
  last_heartbeat_at: 2026-07-04T08:12:03Z
  last_outcome:      ok
  minutes_since:     2.4

INGEST
  unprocessed:       0
  backpressure:      no

ACTIONS
  pending by tier:   {"1": 0, "2": 0, "3": 1}
  awaiting grant:    1
  failed (24h):      0

BUDGET
  today:             $0.1834 / $2.00 daily-warn
  month:             $4.1120 / $30.00 cap (13.7%)
  degraded mode:     no

CACHE
  hit rate (7d):     61.2%

ERRORS
  (none in last 5 router_calls)

HERMES-AUX
  last 24h count:    14
  drift alarm:       no

ROUTER
  paused:            no

! OAUTH
  refresh failing:   yes (re-auth required)
  consecutive fails: 3
  rotation count:    12
  last rotated at:   2026-07-03T22:10:41Z
  access token:      74.0m past expiry

CONTAINERS
  mailbot-api        ok
  mailbot-hermes     ok
  ollama             ok

WARNINGS: oauth
```

---

## Common errors & how to solve them

Error codes are stable strings (defined in `mailbot_api/router/errors.py`); the same code appears in Discord refusals, `mailbot status` ERRORS rows, and logs.

| What you see | Code | Cause | Fix |
| --- | --- | --- | --- |
| "This email is sensitive. Confirm via /confirm..." | `sensitivity_blocks_api` / `needs_sensitivity_confirmation` | Cloud task requested on a **sensitive** email without a token | `/confirm <email_id> <task>` or say "yes, escalate". Token is single-use, 10-min. If it's **confidential**: no override exists — read it in Outlook. |
| "Confidential emails admit no API override." | `sensitivity_blocks_api` | Email is **confidential** | By design. Nothing to fix. |
| Refusal on a brand-new email | `sensitivity_not_classified` | Ingest hasn't sensitivity-classified it yet | Wait a few minutes, or `mailbot rederive --task=sensitivity_class --since=<date>`. |
| Bot can't read a body you asked about | `CONFIDENTIAL_HYDRATION_BLOCKED` | Body-reads on confidential emails are blocked | Read it in Outlook. |
| Action proposed but nothing happens; `mailbot status` shows "awaiting grant" | status `pending_grant` | Tier-2/3 action needs a grant you haven't approved | Approve in chat ("yes, archive them"). A send whose grant window lapsed silently reverts to `pending_grant` — ask MailBot to re-mint the grant. |
| "This call would cost more than $0.20" | `per_call_threshold_exceeded` | Single call above the per-call refusal threshold | Confirm in chat to force this one call, or trim the request. |
| Cloud tasks refuse; everything routes to local Qwen | `monthly_budget_exceeded` → `degraded_mode_blocked` | $30 monthly hard cap hit → degraded mode | Wait for the month rollover, or `/budget reset` if you accept the overage. Opus one-shots in degraded mode trigger an extra confirmation. |
| "$2 daily spend" warning message | `budget.daily.soft_warn` | Daily soft threshold crossed | Informational only — fires once per day, nothing is blocked. |
| "Rate limited, try again in a bit" | `rate_limited` | Chat lane: 60 calls/hr; ingest lane: 300/hr; body-reads: 5/turn | Wait — the window slides over 60 minutes (body-read cap resets after ~30s idle). |
| Bot refuses and mentions a loop | `loop_detected` | Same prompt dispatched >10× in 5 min — kill-switch | Stop retrying. `/pause`, check `mailbot logs --filter level=error`, then `/resume`. |
| Every request refused; "router is paused" | `PAUSED` state | Manual `/pause`, or auto-pause (e.g. OAuth failing) | `/resume` or `mailbot resume`. Check the reason first in `mailbot status` → ROUTER. |
| Discord alert "sync stale > 1h"; OAUTH section warns "refresh failing: yes"; router auto-paused with `reason: oauth_refresh_failing` | `oauth_refresh_failing` | Microsoft refresh token revoked/expired (fires after 3 consecutive refresh failures) | Follow [docs/auth-recovery.md](docs/auth-recovery.md): mint a new token with `scripts/mint_refresh_token.py`, persist via `scripts/refresh_outlook_oauth.py` (stdin — never as a CLI arg), verify with `mailbot status`. Auto-resume clears the pause on success. |
| Ingest rows stuck; errors mention schema | `schema_validation_failed` | Model returned malformed structured output | Auto-retried (Qwen tasks escalate to Haiku). If persistent, check `mailbot logs`, then `mailbot rederive` the task — prompt-version bumps have fixed this class before. |
| "Daily send cap reached" | `daily_send_cap_exceeded` | Hard cap: 20 sends per UTC day | Wait until UTC midnight. No override. |
| Action failed; mailbox changed underneath | `state_drift_etag` / `target_deleted` / `state_drift_noop` | Email was moved/deleted in Outlook between propose and apply | Re-issue the request against the current mailbox state; `mailbot replay <id>` re-queues if the failure was transient. |
| "unknown action_type" | `INVALID_ACTION_TYPE` | Agent used a non-canonical action name | Self-correcting — the error carries the valid list and the agent retries. Just re-ask if a turn dies on it. |

---

## Setup & architecture

### Requirements

Python 3.12 + Docker Desktop.

```bash
git clone <this repo>
cd mailbot
py -3.12 -m venv .venv           # POSIX: python3.12 -m venv .venv
.venv\Scripts\Activate.ps1       # POSIX: source .venv/bin/activate
pip install -r requirements.txt

make test      # pytest
make lint      # ruff + mypy --strict
make local     # start the local dev stack
```

First-time credentials: register the Entra app ([docs/entra-app-registration.md](docs/entra-app-registration.md)), mint the Outlook refresh token (`python scripts/mint_refresh_token.py`), fill `.env` from `.env.example`. Discord slash-command registration: `python scripts/register_discord_commands.py`.

### Architecture overview

- **3-container Docker stack** on `mailbot-net`: `mailbot-hermes` (Hermes agent runtime, Discord adapter, cron, memory), `mailbot-api` (Router + MCP verbs + sync worker; sole holder of the Anthropic API key), `ollama` (Qwen 3B + `nomic-embed-text`).
- **Router** (`router/policy.yaml`, hot-reloaded): 17 task types → model assignments. Local Qwen serves classification, sensitivity gating, sender/thread summaries, intent parsing, digest intros; Claude Haiku serves email summaries, importance scoring, action extraction; Claude Opus serves draft replies, tone mirroring, refinement. Your `/model` overrides live in `router/policy.user-overrides.yaml`.
- **Cost discipline**: response cache, per-call $0.20 refusal, $2/day soft warn, $30/month hard cap with degraded mode, lane rate limits, loop detector. All LLM traffic flows through a single `ask_router` entry point — nothing bypasses the gates.
- **Storage**: stdlib `sqlite3` with WAL + raw SQL migrations (`mailbot_api/db/migrations/`), no ORM by design.
- **Five enforced code boundaries** (ruff rules): Router / sync / db / config / audit isolation.
- Pinned runtime: FastAPI 0.136.1, Anthropic 0.105.2, Ollama 0.6.2, MCP 1.27.2, Pydantic v2.

### Project layout

```
mailbot_api/          Python package
  db/                   SQL boundary (raw SQL only in queries.py)
  router/               LLM adapter boundary (only anthropic/ollama import site)
  sync/                 Microsoft Graph boundary
  verbs/                Agent-facing MCP tools
  ingest/ actions/ ...  Pipeline + authorization/drainer
router/               Runtime routing config (policy.yaml + user overrides)
docker/               Dockerfile + entrypoint
hermes-config/        Hermes runtime config + the mailbot skill (SKILL.md)
scripts/              Operator CLIs (mailbot.py, OAuth tooling, Discord registration)
evals/ benchmark/     Eval corpus + benchmark runner
tests/                Pytest suite
docs/                 Deep dives (auth-recovery.md, setup-vps-runbook.md, ...)
```

### Deep dives

| Topic | Where |
| --- | --- |
| Agent verb surface (the full contract behind the Discord examples) | `hermes-config/skills/mailbot/SKILL.md` |
| OAuth recovery procedure | `docs/auth-recovery.md` |
| Entra app registration | `docs/entra-app-registration.md` |
| VPS setup runbook (for the future deploy) | `docs/setup-vps-runbook.md` |
| Daily digest + notification pull cron jobs | `hermes-config/skills/mailbot/cron-jobs.md` |
| Full design + implementation plan | `_bmad-output/planning-artifacts/` |

---

## Limitations & current status

Honest snapshot as of 2026-07:

- **Local Docker only.** The stack runs and is live-verified on the local dev machine; VPS deployment (CP-1) is the final ship gate and has not happened yet.
- **Folder moves: walked once, with findings.** The triage-move write path was live-verified end to end on 2026-07-05 (propose → auto-approve → drain → real Graph dispatch → verified in Outlook, one email against a sacrificial folder). <!-- verified 10-1, run_id action-4/2026-07-05 --> The same walk filed real defects: `pause` does not stop the action drainer (they live in different processes), a moved email is recorded locally as *deleted* and stays invisible to MailBot even after it's moved back, and the chat path can't propose a folder move at all yet (no folder-name lookup).
- **Triage-move auto-revert: shipped and walked.** A triage-move now captures its source folder (from Graph, before dispatch — fail-closed: no capture, no move) and `mailbot revert <id>` / "undo that" re-moves the email back within 24h; the revert also repairs the email's local soft-deleted row. Live-verified end to end on 2026-07-05 (move → revert → verified back in Inbox in the Outlook client, same sacrificial-folder rig as the 10-1 walk). <!-- verified 10-2, run_id action-6/2026-07-05 --> Honest caveats: moves applied *before* this shipped have no recorded source folder and refuse with `PRE_STATE_MISSING` (revert those manually in Outlook); Tier-2 moves (batch archive etc.) capture their source folder for the audit trail but are still not auto-revertible.
- **Benchmark calibration in progress** (epics 7 / 9 / 9.5): the model-per-task assignments in `router/policy.yaml` carry promote/demote hypotheses that are still being measured; expect routing to shift as results land.
- **Native Discord slash registration covers the `/model` family only**; the other slash commands are interpreted by the Hermes agent from your typed message (functionally equivalent, no autocomplete).
- Epics 1–6.5 are shipped and largely live-verified; the send flow, sensitivity gates, budget gates, digest, and notifications are all exercised against the real mailbox.
