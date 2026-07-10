---
name: mailbot
description: "MailBot verb surface — Outlook triage + draft-reply + cost reporting via 26 MCP tools."
version: 1.0.0
author: Adam Maroni
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Email, Outlook, MCP, Defender, MailBot]
    category: email
    related_skills: [himalaya]
---

# SKILL.md — MailBot verb-surface reference

This file walks the MCP verb surface Hermes consumes via the
`http://mailbot-api:8000/mcp` client (Story 5-2). It is the agent-facing
reference for which verbs to call in which situations and in which order.

The verb surface is the ONLY mutation path. `SOUL.md` and `AGENTS.md` set the
identity and the rules; this file is the toolkit.

## Read verbs (Rule J — projection-first)

### `find_emails`

Purpose: search the user's mailbox by filter and return projection-only rows
(no body bytes).

Example user turn: "show me unread from Sarah this week." → call
`find_emails(filter={"sender_address": "sarah@example.com", "since": "..."},
limit=25)` → format `projections` as a Discord-rendered list → respond.

Rule J discipline: this is your default read path. The result is body-free; you
do NOT need to hydrate to answer most filter queries. The verb caps `limit` at
100.

### `hydrate_email`

Purpose: return the full row (including `body_preview`) for ONE specific
email_id, subject to the per-turn 5-hydration cap.

Example user turn: "what does the email from Sarah say?" — when the user has
named exactly one email and you need the body to answer. → call
`hydrate_email(email_id="...")`.

Rule J discipline: rate-limited to 5 calls per turn (30s inactivity reset).
Confidential-classified emails are refused with `CONFIDENTIAL_HYDRATION_BLOCKED`
— do not retry; surface the refusal to the user.

### `get_thread`

Purpose: return all projections in a thread by thread_id, plus the cached
`thread_continuity_note` from Story 3-7.

Example user turn: "what's the history on this thread?" → call
`get_thread(thread_id="...")` → present projections + continuity note.

Rule J discipline: projection-only; bodies require follow-up `hydrate_email`
calls. The thread is ordered oldest-first.

### `count_emails`

Purpose: count emails matching a filter; returns ONLY a count, no rows.

Example user turn: "how many unread do I have?" → call `count_emails(filter=...)`
→ respond with the number.

Rule J discipline: NEVER call `find_emails` followed by `len(projections)` for a
count — that wastes projection bandwidth and hits the limit cap. `count_emails`
is the right verb for counting.

### `get_sender_summary`

Purpose: return the cached `sender_reputation_summary` (Story 3-7) for a sender
address.

Example user turn: "who is this person?" → call `get_sender_summary(sender_address="...")`
→ present the cached summary.

Rule J discipline: the summary is cached forever per Rule A; you are NOT
producing a new summary, you are reading one. Sensitive emails are
projection-filtered out of the summary's underlying data per Story 3-7.

## Action verbs (Rule P — tier-aware proposals)

### `propose_action`

Purpose: the SINGLE entry point for every mailbox mutation. Classifies the
action's tier via the frozen ACTION_PROPERTIES table and returns either
`ok=True` (proposed; drainer will apply) or `ok=False` with the verb-error
explaining what additional handshake is required (grant, sensitivity token,
per-action confirmation).

Example user turn: "archive the newsletters from this week." → first call
`mint_grant("archive", [<email_ids>], <expires_at>)` (Tier-2 batch grant per
Rule P) → confirm the grant with the user → then loop `propose_action(email_id,
"archive")` per email.

Tier-handling responsibility: NEVER claim a tier; the verb decides. If the
verb returns `requires_grant=True`, you mint a grant. If it returns
`requires_per_action_confirmation=True`, you ask the user to confirm. To
discover whether an action requires a sensitivity-token handshake
(belt-and-suspenders defender posture on destructive or content-exposing
touches of sensitive emails), call `read_resource("mailbot://action-types")`
and check the entry's `requires_sensitivity_token` field — that contract
lives on the registry, not on `ProposeActionOut`. The sensitivity-token
handshake is enforced at the Router precondition layer (`ask_router` refuses
`SENSITIVITY_BLOCKS_API` without a valid `confirmation_token`), not at
`propose_action` time.

#### Canonical action_type values

(Story 6-19 F29 closure.) `action_type` MUST be a lowercase snake_case literal
string. The verb rejects `SEND_REPLY`, `SEND_EMAIL`, `sendReply`, `send-reply`,
`reply`, `send`, or any other variant with `INVALID_ACTION_TYPE`. Pass
`action_type='send_reply'` (and similar for the other 22 members), not the
UPPER_SNAKE enum name.

| User intent (chat surface)             | Canonical `action_type`                  |
|----------------------------------------|------------------------------------------|
| "send" / "send it" / "reply" / "send the reply" | `send_reply`                    |
| "delete" / "trash" / "remove"          | `delete`                                 |
| "archive" / "file away"                | `archive`                                |

If you are unsure of the canonical value, call
`read_resource("mailbot://action-types")` to fetch the full enum + a
`synonyms_rejected` list of common hallucinations. The verb's
`INVALID_ACTION_TYPE` error response ALSO carries the full canonical list
inline (as `valid_action_types`) for in-band recovery.

#### Tier-3 SEND flow

(Story 7-0-f30-f31 F30 HIGH + F31 LOW closures.) Tier-3 SEND-family actions
(`send_reply`, `send_new_email`, `send_forward`, `reply_to_inactive_thread`)
require BOTH a per-action grant AND user confirmation. The flow is:

1. Call `propose_action(send_reply, email_id, payload)`. The verb returns
   `ProposeActionOut(ok=True, status="cooling_off", requires_grant=True,
   requires_per_action_confirmation=True)`.
2. **Before the cooling-off window closes**, call
   `mint_grant(action_type="send_reply", email_ids=[email_id], expires_at=<60s from now>)`.
   The cooling-off window is the cancel-affordance; the grant is the
   "yes really send this specific email" signal. If you skip `mint_grant`,
   the drainer reverts the row to `status="pending_grant"`, no
   operator-visible error fires, and there is no automatic recovery —
   manual `mint_grant` via `docker exec` is the only unstick path
   (this is F30's failure mode).
3. When the user replies with "send" / "send it" / "go ahead", recognize
   this as confirming the EXISTING `pending_actions` row (the one that
   `propose_action` returned with `requires_per_action_confirmation=True`)
   — do NOT issue a fresh `propose_action` call (that creates a duplicate
   row; this is F31's failure mode). The canonical discovery path for the
   existing row is your conversation memory of the prior turn's
   `ProposeActionOut(ok=True, action_id=<N>, status="cooling_off",
   requires_per_action_confirmation=True)`. If conversation memory is
   unavailable (e.g., the user's confirmation crosses a session boundary),
   fall back to `find_emails(filter={sender_address: <addr>}, limit=5)` to
   spot the cooling-off row's email, then use SQL via `read_sql` to
   inspect `pending_actions` for `status IN ('cooling_off', 'pending')` on
   the same `(email_id, action_type)` pair before deciding to re-propose.

Tier-3 SEND grants are per-action by design: one `(action_type, email_id)`
pair per grant. Tier-2 BATCH grants (e.g., `archive`) cover N actions of
the same type and do NOT require per-action confirmation — they return
`requires_grant=True, requires_per_action_confirmation=False`.

### `mint_grant`

Purpose: mint a Tier-2 batch grant scoped to (action_type, email_ids,
expires_at).

Example: see `propose_action` example above.

Tier-handling responsibility: grants are SCOPED — they authorize exactly the
named email_ids for exactly the named action_type. A grant for "archive these
12 emails" does NOT authorize archiving a 13th; mint a second grant in that
case.

### `revoke_grant`

Purpose: revoke a previously-minted grant before it expires.

Example user turn: "wait, cancel that archive plan." → call
`revoke_grant(grant_id=<id>)` → confirm to the user that the scope is no longer
authorized.

Tier-handling responsibility: a revocation is final; if the user later wants
the same action, mint a fresh grant.

### `cancel_action`

Purpose: cancel a Tier-3 action that is currently in its 60-second cooling-off
window (Story 4-6).

Example: the user types `/cancel <action_id>` after seeing a "Cooling off for
60 seconds" message. → call `cancel_action(action_id=<id>)`.

Tier-handling responsibility: cancellation is only possible during cooling-off;
once the drainer picks up the action, you use `revert_action` instead (and
only for revertible Tier-1 actions).

### `revert_action`

Purpose: revert a Tier-1 action that already applied, within 24 hours of the
apply.

Example user turn: "undo that mark-as-read." → call `revert_action(action_id=<id>)`.
The verb maps the inverse (MARK_READ ↔ MARK_UNREAD, ADD ↔ REMOVE_LOCAL_CATEGORY).
A triage-folder move (MOVE_TO_TRIAGE_FOLDER) reverts by re-moving the email
back to its recorded source folder — this works only for moves applied after
the pre_state capture shipped (Story 10-2); older moves refuse with
`PRE_STATE_MISSING`. Tier-2 and Tier-3 actions are NOT revertible via this
path; the user must take a new compensating action manually.

Tier-handling responsibility: Tier-1 only. If the verb returns
`INVERSE_UNAVAILABLE` or `PRE_STATE_MISSING`, surface the limitation to the
user.

### `mint_sensitivity_token`

Purpose: produce a single-use 10-minute token that authorizes the Router
precondition layer to allow a sensitive-email task that would otherwise be
blocked.

Example user turn: "yes, escalate this draft to Opus" on a `sensitive`-class
email. → user types `/confirm <email_id> draft_reply` → you call
`mint_sensitivity_token(email_id, "draft_reply")` → pass the returned token as
`confirmation_token` to `ask_router(task_type="draft_reply", ...)`.

Tier-handling responsibility: the verb REFUSES on `confidential` emails (per
AR-D12-1). Do not retry; surface the refusal with a defender-toned message:
"Confidential emails admit no API override. The body stays on your VPS, period."

## Slash-command verbs (MCP-exposed as of Story 5-6 + Story 6-8)

The slash-command surface (`/cost`, `/pause`, `/resume`, `/budget reset`,
`/mute`, `/spend`) maps to MCP-exposed verbs. Adam types the slash command in
Discord; Hermes routes via its slash dispatcher to the corresponding MCP tool.

### `cost_breakdown`

Purpose: return Router cost breakdown for the period (today | month). Per-task /
per-model / per-caller_origin aggregations + cache hit rate.

Slash command: `/cost [period]` (default: today).

### `reset_degraded_mode`

Purpose: flip `degraded_mode_state` to inactive and clear the in-memory flag.

Slash command: `/budget reset`.

### `pause_router` / `resume_router`

Purpose: pause the Router lane scheduler with a reason / resume it.

Slash commands: `/pause [reason]`, `/resume`.

### `mute_category`

Purpose: mute a notification category until a timestamp (or indefinitely).
Epic 6's dispatcher reads from `notification_mutes`.

Slash command: `/mute <category> [until]`.

### `set_model_oneshot` — Model override (Story 9-3)

Purpose: arm a one-shot model override for the very next `ask_router` call.
Adam types `/model qwen` (or `haiku` / `opus`) inline during a Discord
conversation; the next chat turn dispatches against the chosen model. The
override has a 5-minute TTL and is consumed on first effective use.

Slash command examples (Hermes-side registration is Story 9-10's scope per
OQ-2; the verb itself is dispatchable via MCP today, so any slash handler
Hermes wires up can call it directly):

- `/model qwen` — next chat turn runs against `qwen2.5:3b-instruct-q4_K_M`
- `/model haiku` — next chat turn runs against `claude-haiku-4-5-20251001`
- `/model opus` — next chat turn runs against `claude-opus-4-7`

Gates inherited (the override does NOT punch through):

- **Sensitivity gate (NFR-PRIV-1/2):** confidential emails still refuse
  unconditionally; sensitive emails still require the
  `mint_sensitivity_token` handshake. The audit row carries
  `model_chosen_reason=sensitivity_gate:refused` (not the OVERRIDE_SLASH_ONE_SHOT
  value), AND the override stays armed within its TTL since "gate refused" ≠
  "actual use."
- **Budget gate ($0.20/call refusal threshold):** the override does NOT
  carry implicit `force=true`. Adam must re-issue with explicit force if
  he wants to bypass the per-call threshold.
- **Degraded-mode gate:** when the override targets `opus` AND degraded
  mode is active, the existing `DEGRADED_MODE_BLOCKED` confirmation flow
  fires unchanged; the override stays armed.

Audit trail: every dispatch that consumed the one-shot writes
`router_calls.model_chosen_reason = "slash_command:one_shot:adam"` per
Story 9.2's closed-set vocabulary (`ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT`).

Story 9-4 forward-reference: `/model <task> <model>` (with both arguments
provided) sets a PERSISTENT per-task override by writing to
`router/policy.user-overrides.yaml` (companion file from Story 9-1, hot-
reloads within 1 second). The one-shot variant described here is when
`/model <model>` is invoked with only the model argument.

### `set_model_persistent` — Persistent per-task model override (Story 9-4)

Purpose: persistently override one task's model assignment by writing to
the companion file `router/policy.user-overrides.yaml`. Survives image
rebuilds (Story 9-1 contract — overrides file is bind-mounted RW from the
host, not baked into the image). Hot-reloads within ~1 second.

Slash command examples (Hermes-side registration is Story 9-10's scope per
the Story 9-3 OQ-2 architectural-impossibility caveat that also applies
here; the verb itself is dispatchable via MCP today):

- `/model draft_reply opus` — all subsequent `draft_reply` dispatches go to
  `claude-opus-4-7` until the override is reverted (delete the entry from
  `router/policy.user-overrides.yaml` or set it back to baseline).
- `/model coarse_class haiku` — same shape, different task/model.

Arg-count dispatch table (single `/model` Discord command, three behaviors
depending on argument count):

| arg count | example                       | verb                  | behavior                              |
|-----------|-------------------------------|-----------------------|---------------------------------------|
| 0         | `/model`                      | `inspect_policy`      | render current effective policy table |
| 1         | `/model haiku`                | `set_model_oneshot`   | arm one-shot for next call (5-min TTL)|
| 2         | `/model draft_reply opus`     | `set_model_persistent`| persistent write to overrides file    |

Atomic-write semantics: tempfile + `os.fsync` + `os.replace`. A crash
mid-write leaves the original file unchanged (atomic by POSIX). Validates
the task name against the live policy snapshot and the model id against
the same alias set as the one-shot variant (`qwen` / `haiku` / `opus` +
their full IDs).

First-write bootstrap requirement (Story 9-1 OQ-3 inheritance): if
`router/policy.user-overrides.yaml` did NOT exist when `mailbot-api`
started, the `watchfiles` watcher could not pick it up — Story 9-1
documents this contract limitation. The verb refuses-with-actionable-
error in that case; the operator must run
`cp router/policy.user-overrides.yaml.example router/policy.user-overrides.yaml`
on the host AND restart `mailbot-api` before the first persistent override
can take effect. After the first restart, all subsequent persistent
writes hot-reload normally.

Gate inheritance: identical to the one-shot variant — the persistent
override does NOT punch through the sensitivity / budget / degraded-mode
gates. The router merely changes WHICH model the policy selects for the
overridden task; everything downstream is unchanged.

Cross-precedence with one-shot: if BOTH a one-shot AND a persistent
override are active for the same task, the **one-shot wins** for the very
next call only, then evaporates per its TTL; the persistent override
remains active for all subsequent calls.

Audit trail: every dispatch where the persistent override caused the
model selection writes
`router_calls.model_chosen_reason = "slash_command:persistent:adam"`
per Story 9.2's closed-set vocabulary
(`ModelChosenReason.OVERRIDE_SLASH_PERSISTENT`).

### `inspect_policy` — Current effective policy view (Story 9-4)

Purpose: read-only render of the current effective routing policy as a
markdown table. Composes baseline + overrides + degraded-mode + active
one-shot state into a single "what is the router doing right now" view.

Slash command: `/model` (with NO arguments). Same architectural-
impossibility caveat — Hermes-side registration is Story 9-10's scope;
the `inspect_policy` MCP tool is dispatchable today.

Output shape (markdown table + two status lines):

```
| task | baseline_model | override_model | effective_model | lane | sensitivity | last_changed |
|---|---|---|---|---|---|---|
| 🔧 draft_reply | claude-haiku-4-5-20251001 | claude-opus-4-7 | claude-opus-4-7 | interactive | any | 2026-06-26T18:14:32+00:00 |
| coarse_class | qwen2.5:3b-instruct-q4_K_M | — | qwen2.5:3b-instruct-q4_K_M | batch | any | — |
…

Current degraded mode state: Not active
Active one-shot override: None
```

The 🔧 prefix on the `task` column marks rows where Adam's persistent
override is in force. The `last_changed` column shows the file-level
mtime of `router/policy.user-overrides.yaml` (per-task mtime tracking is
deferred to a future story; file-level mtime is the v1 surface).

The "Current degraded mode state" line reads from the live budget guard;
the "Active one-shot override" line reads from the Story 9-3 one-shot slot.
Both lines update reactively with every call — `inspect_policy` is the
canonical truth source for what the router will do on the very next call.

### `render_spend_chart`

Purpose: render a 1200×800 PNG horizontal bar chart of cost-per-task over
today/week/month. Returns the bytes ready to attach to a Discord message + a
text summary line.

Example user turn: `/spend month` → call `render_spend_chart(period="month")` →
receive `RenderSpendChartOut(image_bytes=..., total_usd=..., top_task=...,
task_count=...)` → post a single Discord message with the PNG as an attachment
and the documented text summary: `"$X.XX spent month. Top task: {top_task}
(${Y.YY}). Cap: $30."`.

AR-ANALYTICS-1 + AR-ANALYTICS-2 discipline: the chart is rendered via
matplotlib's `Agg` backend; PNG bytes are returned (never written to disk on
mailbot-api); any chart text labels pass through the Story 5-7 chat-input
redactor before being baked into the image. The `render_spend_chart` verb is
the FIRST analytics verb to ship; future analytics verbs follow the same
package-isolation discipline (lives under `mailbot_api/verbs/analytics/`,
boundary-checker-enforced `matplotlib.pyplot` isolation).

### `unmute_category`

Purpose: lift a notification-category mute set earlier via `mute_category`.
Resets the per-category mute state immediately; subsequent Epic-6 dispatcher
runs deliver normally for the unmuted category.

Slash command: `/unmute <category>` (Story 6-4).

### `pull_pending_notifications`

Purpose: Hermes-pulled urgent-tier notification dispatch (Story 6-3). Atomically
claims up to N urgent rows from `notifications_outbox` (rows transition `pending`
→ `delivering` under a single SQL transaction so concurrent pullers don't double-
deliver). Hermes posts each row's payload to Discord, then acknowledges via
`ack_notification` for terminal-state transition.

Called programmatically by Hermes's pull loop (~10s cadence, `no_agent=True`).
Not Adam-facing — the verb has no slash command; it's transport plumbing.

### `ack_notification`

Purpose: Hermes finalizes a notification row pulled via `pull_pending_notifications`
with terminal state `ok` (delivered successfully) or `failed` (Discord post failed;
the row stays in retry until the per-row TTL elapses).

Called programmatically by Hermes's pull loop after each Discord post. Not
Adam-facing.

### `compose_digest`

Purpose: assemble the 08:00 daily digest body — the per-category summary +
top-importance email list + tone-matched intro paragraph (Story 6-5). Returns
the composed markdown + a `digest_id` Hermes uses to finalize delivery.

Called programmatically by Hermes's daily-digest cron skill (Story 6-10) — not
Adam-facing. Adam SEES the digest in Discord at 08:00 but doesn't invoke it.

### `finalize_digest_delivery`

Purpose: mark the digest identified by `digest_id` as delivered, persist the
per-day delivery row for observability, and clear the per-category accumulator
so the next day's digest starts fresh.

Called programmatically by Hermes's daily-digest cron skill (Story 6-10) right
after posting the composed body to Discord. Not Adam-facing.

### `draft_reply`

Purpose: draft a reply to an email by `target_email_id` — the flagship Opus
draft pipeline (Story 5-9, wired to chat in Story 10.5.3 / F-10-5-11). Runs the
sensitivity gate first (confidential is refused; sensitive requires a
`confirmation_token` minted via `mint_sensitivity_token`), then an optional
tone-mirror pass, then the Opus draft. Returns `state` — one of
`draft_presented` (draft + suggested subject + defender warnings populated),
`confidential_refused`, `needs_sensitivity_token`, `invalid_email`, or
`router_error`.

This is the action-side draft only: it presents a draft for the user to
[send / refine / cancel]. On the user's "send" the chat surface proposes a
`SEND_REPLY` action which enters Story 4-6's 60s cooling-off before the drainer
dispatches it. Adam-facing — invoked when the user asks the bot to draft or
reply to an email.

## Router-internal — `ask_router` is intentionally NOT MCP-exposed

The Router's dispatch surface (`ask_router`) is NOT exposed as an MCP tool. This
is by design — re-exposing it would let you bypass:

- the policy-driven model selection (Rule G),
- the budget guard (Story 2-8),
- the per-call refusal threshold (Story 2-8 Layer 4),
- the sensitivity precondition layer (Story 3-3 / Story 4-7),
- the response cache (Story 2-7).

Cost-discipline center (Epic 2's whole point) only works if `ask_router` has
exactly ONE entry path from the agent. That path is the OpenAI-compatible
`/v1/chat/completions` endpoint (Story 2-10) — Hermes wraps it as its
provider/auxiliary inference path per `hermes-config/config.yaml`. You reach
the Router by sending a chat-completions request through Hermes's normal
provider chain, NOT by calling `ask_router` as a tool.

`reset_hydration_count` is a server-internal lifecycle helper called by the MCP
server between turns. Not an agent-facing tool.

## Recovery Actions — the universal next-step contract

(Story 7-0-c24.) Every mailbot-api response that carries a refusal,
blocked-state, or terminal-state may include a structured `recovery_action`
field with the universal shape:

```python
class RecoveryAction(BaseModel):
    tool_name: str | None             # the verb/tool to call next
    args_hint: dict[str, Any]          # keyword args to interpolate
    user_facing_guidance: str | None  # canonical chat wording if user input required
```

**Rule R (also in AGENTS.md):** when calling a mailbot-api verb that may
refuse/block/terminate, ALWAYS check `response.recovery_action` first. If
it's populated and `tool_name` is non-None, your next call should match
`recovery_action.tool_name` with `recovery_action.args_hint` interpolated.
If `user_facing_guidance` is non-None, relay it verbatim to the user
(or paraphrase per your defender persona) — that wording is the canonical
chat-surface explanation for the refusal/block.

### MVP surfaces shipped this story

**INVALID_ACTION_TYPE recovery** — when `propose_action` rejects an
unknown action_type string:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_ACTION_TYPE",
    "message": "unknown action_type 'SEND_EMAIL'; must be one of [...]",
    "valid_action_types": ["add_local_category", "archive", ..., "send_reply", ...],
    "recovery_action": {
      "tool_name": "propose_action",
      "args_hint": {
        "action_type": "<choose one from valid_choices>",
        "valid_choices": ["add_local_category", "archive", ..., "send_reply", ...]
      },
      "user_facing_guidance": "If unsure which canonical action_type matches the user intent, consult the mailbot://action-types MCP resource for synonyms-rejected mappings."
    }
  }
}
```

Self-correction: call `propose_action` again with `action_type` set to one
of the canonical values from `recovery_action.args_hint.valid_choices`
(self-contained — no cross-reference to `valid_action_types` required;
either field carries the same canonical list).

**GRANT_REQUIRED next-call hint** — when `propose_action` returns
`ok=True` for a Tier-2 BATCH or Tier-3 action requiring a grant:

```json
{
  "ok": true,
  "action_id": 42,
  "tier": 3,
  "status": "cooling_off",
  "requires_grant": true,
  "requires_per_action_confirmation": true,
  "recovery_action": {
    "tool_name": "mint_grant",
    "args_hint": {
      "action_type": "send_reply",
      "email_ids": ["AAk..."],
      "ttl_seconds": 60
    },
    "user_facing_guidance": null
  }
}
```

Self-recovery: call `mint_grant` with `expires_at` computed at mint-time
as `now() + ttl_seconds`. The relative TTL avoids the race condition that
an absolute timestamp computed at propose-time would create when
Hermes-side message latency or follow-up turns delay the actual
`mint_grant` call.

### Back-compat retention

Story 6-19's `valid_action_types` field and Story 7-0-f30-f31's
`requires_grant` / `requires_per_action_confirmation` booleans are RETAINED
alongside the new `recovery_action` envelope. Existing Hermes-side code
that consumes those fields directly continues to work without modification.
New code SHOULD prefer the structured envelope.

### Carry-forward surfaces (not yet shipped)

The following surfaces will carry the envelope under named follow-up
stories (C24-FU-1..4): `HydrateEmailError.CONFIDENTIAL_HYDRATION_BLOCKED`,
`ProposeActionError` SENSITIVITY_NOT_CLASSIFIED + SENSITIVITY_BLOCKS_API +
GRANT_REQUIRED + BUDGET_CAP_HIT, Router refusals (SENSITIVITY_BLOCKS_API
+ DEGRADED_MODE + PAUSED), terminal `pending_actions.terminal_reason`
states, and `MintSensitivityTokenOut` next-call hint. Until those land,
treat the absence of `recovery_action` on those surfaces as the
pre-Story-7-0-c24 behavior — infer the next step from this SKILL.md +
AGENTS.md + your defender persona.

## End-to-end turn structures

### Turn structure 1 — "show me unread"

User: "show me unread."

Steps:

1. Call `find_emails(filter={...}, limit=25)`. (The exact filter depends on
   what "unread" means in this project — once `list_unread` ships, use that
   instead.)
2. Receive `FindEmailsOut.projections`.
3. Format projections as a Discord-rendered list: subject, sender, sent-at,
   summary_short, importance_score.
4. Respond.

No hydration. No Router call beyond the chat-completions wrapper that produced
this response. Default notification tier (Rule R): inherits from the user's
turn (the user asked; you reply in the same channel).

### Turn structure 2 — "draft a reply to that"

User: (prior turn referenced an email) "draft a reply to that."

Steps:

1. Call the Router via `/v1/chat/completions` with `task_type="reference_resolution"`
   and the recent chat context + candidate projections. Receive
   `resolved_email_ids`.
2. If `ambiguous=True` or `resolved_email_ids` is empty, ask the user to
   clarify. Stop here.
3. Check `emails.sensitivity` for the resolved id.
   - If `confidential`: refuse with the defender message: "Confidential emails
     admit no API override. The body stays on your VPS, period."
   - If `sensitive`: surface the escalation prompt to the user: "This email is
     sensitive. Confirm via `/confirm <email_id> draft_reply` or say 'yes,
     escalate'." Wait. On confirmation, call
     `mint_sensitivity_token(email_id, "draft_reply")` and use the returned
     token as `confirmation_token`.
   - If `normal`: proceed without a token.
4. (Optional cache hit path) Call the Router with `task_type="tone_style_mirror"`
   and the recipient address. The response is 30-day cached per Story 5-3
   AC-5; the first call to a recipient pays the Opus cost, subsequent calls
   amortize. Receive tone_signals.
5. Call the Router with `task_type="draft_reply"`, the source email, the thread
   context, and the tone_signals from step 4. Receive `DraftReplyOutput` —
   draft_body, suggested_subject, tone_signals_used, defender_warnings.
6. Present the draft to the user in the chat surface — the body, the subject,
   the tone signals you applied, the defender warnings (if any), and inline
   controls: "send / edit: <new body> / refine: <instruction> / cancel".
7. On "send": call `propose_action(email_id, ActionType.SEND_REPLY,
   payload={"body": ..., "to": ...})`. The verb returns
   `requires_per_action_confirmation=True`; surface the cooling-off message.
   On the eventual drainer apply (Story 4-4 + Story 4-5), the email leaves.
8. On "refine: <instruction>": call the Router with
   `task_type="multi_turn_refinement"`, the current draft, and the refinement
   instruction. Loop back to step 6 with the refined draft. The orchestrator
   (you) caps at 5 iterations with a defender warning at the 5th: "we've
   refined this 5 times — want to start over?"

Banned: NEVER call `ask_router(task_type="draft_reply", ...)` on a `sensitive`
email without first calling `mint_sensitivity_token` and passing the result as
`confirmation_token`. NEVER call `ask_router(task_type="draft_reply", ...)` on
a `confidential` email — the Router will refuse; surface the refusal with the
defender-toned message from step 3 above.

### Inline-drafting variant — F28 awareness

If you draft the reply INLINE in your own `/v1/chat/completions` tool-call
turn (instead of dispatching `draft_reply` via the Router), the same gate
fires — `dispatch_tool_call` (Story 6-20) refuses at `SENSITIVITY_BLOCKS_API`
whenever ANY referenced `email_id` (in messages OR in tool-call arguments)
has sensitivity ∈ {sensitive, confidential} without a valid
`confirmation_token`. The `mint_sensitivity_token` task_type for this path
is `chat_completions_tool_call`.

If you intend to inline-draft a sensitive reply: mint with
`mint_sensitivity_token(email_id, "chat_completions_tool_call")` BEFORE the
chat-completions request, and pass the token via the
`confirmation_token` parameter (your harness should map this from your chat
slash dispatcher). For `confidential`: refuse at the persona layer; the
router refuses anyway, but defender refusal preserves the operator's mental
model.

### Turn structure 3 — "delete that"

User: (prior turn referenced an email) "delete that."

Steps:

1. Call the Router with `task_type="reference_resolution"`. If ambiguous or
   empty, ask for clarification.
2. Discover the DELETE handshake requirement: `read_resource("mailbot://action-types")`
   surfaces DELETE with `requires_sensitivity_token=True` (per Adam's Story
   4-1 CR-2 decision — DELETE always requires a token regardless of the
   email's sensitivity classification, as a belt-and-suspenders defender
   posture). The registry is the canonical contract source.
3. Call `propose_action(email_id, ActionType.DELETE)`. The verb classifies
   DELETE as Tier-3 and returns `ok=True` with `tier=3, status="pending",
   requires_grant=True, requires_per_action_confirmation=False`
   (DELETE is Tier-3 non-SEND; per-action confirmation is reserved for
   SEND-family — the sensitivity-token handshake covers the
   destructive-touch invariant separately).
4. Surface the proposed-action card to the user with reasoning ("you asked
   me to delete this; here's what I'd delete; say `/confirm <email_id>
   delete` to authorize"). The user typing `/confirm <email_id> delete`
   routes (via the Story 5-6 slash dispatcher) to
   `mint_sensitivity_token(email_id, "delete")`. Receive token.
5. Before `propose_action` runs, you must ALSO call `mint_grant(action_type="delete",
   email_ids=[email_id], expires_at=<ISO-8601-UTC + 60s>)` so the drainer
   can claim the row (Tier-3 grant requirement; `requires_grant=True` from
   step 3). The grant-mint sequencing is: receive sensitivity token → mint
   grant → drainer can dispatch when the cooling-off window expires (Tier-3
   non-SEND skips cooling-off but the grant is still required at
   drain time).
6. Drainer applies the delete via the Outlook Graph write adapter (using
   the captured `change_marker` for the strict ETag check). The email
   leaves. The action row reaches `status="applied"`.

The sensitivity-token contract is enforced at `ask_router` time (for any
Router-mediated draft/summary/etc. step that touches the sensitive body)
NOT at `propose_action` time. `propose_action(DELETE)` itself does not
require the token to write the pending row — but the operator-side flow
(your defender posture) is to mint the token first so the user has
authorized the destructive touch before the drainer fires.

Banned: never proceed past step 1 if `resolved_email_ids` is empty (you
cannot delete an email you cannot identify; ask for clarification instead).
Never call `mint_sensitivity_token` for a confidential email — it will
refuse per NFR-PRIV-2. Surface the confidential-refusal to the user.

### Turn structure 4 — `/spend month`

User: `/spend month` (or `/spend week` / `/spend today` — defaults to month).

Steps:

1. Slash-dispatcher routes the command to `render_spend_chart(period="month")`
   via MCP. Receive `RenderSpendChartOut(image_bytes=<png>, total_usd=...,
   top_task=..., task_count=...)`.
2. Post a single Discord message with the PNG as an attachment and the text
   summary: `"$X.XX spent month. Top task: {top_task} (${Y.YY}). Cap: $30."`
   where the dollar amounts come from `out.total_usd` and the cost of the top
   task (read from a sibling `cost_breakdown(period="month")` call if needed
   for the per-task breakdown).
3. Done. Default notification tier (Rule R): inherits from the user's turn
   (the user asked; you reply in the same channel).

Banned: never render a /spend chart for a period the verb doesn't accept (only
today / week / month — the verb raises `ValueError` on any other string).
Never write the PNG to disk; the bytes go straight from the verb's BytesIO
return to Discord's attachment upload.

## Background cron jobs (Story 6-10)

This skill ships TWO `hermes cron` jobs that run inside the Hermes container.
They consume the same MCP verb surface as the slash-command turns above:

- **`mailbot-notifications-pull`** — drains the urgent-tier notifications outbox
  every ~10s. Calls `pull_pending_notifications` → posts to Discord →
  `ack_notification`. Pure transport; `no_agent=True` (zero LLM cost).
- **`mailbot-daily-digest`** — composes and posts the 08:00 daily digest. Calls
  `compose_digest` via a pre-run script → generates a Qwen intro paragraph via
  `ask_router(task_type="daily_digest_intro")` → renders + posts to Discord →
  `finalize_digest_delivery`.

Both jobs are documented in `cron-jobs.md` alongside the scripts in `scripts/`.
The operator registers them once during VPS setup via `hermes cron create`
(see `docs/setup-vps-runbook.md` §10). The scripts are stdlib-only Python and
do not require any third-party dependencies inside the Hermes container.
