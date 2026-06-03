---
name: mailbot
description: "MailBot verb surface — Outlook triage + draft-reply + cost reporting via 22 MCP tools."
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
`requires_per_action_confirmation=True`, you ask the user to confirm. If it
returns `requires_sensitivity_token=True`, you mint a sensitivity token after
the user types `/confirm`.

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
Tier-2 and Tier-3 actions are NOT revertible via this path; the user must take
a new compensating action manually.

Tier-handling responsibility: Tier-1 only. If the verb returns
`INVERSE_UNAVAILABLE`, surface the limitation to the user.

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

### Turn structure 3 — "delete that"

User: (prior turn referenced an email) "delete that."

Steps:

1. Call the Router with `task_type="reference_resolution"`. If ambiguous or
   empty, ask for clarification.
2. Call `propose_action(email_id, ActionType.DELETE)`. The verb classifies
   DELETE as Tier-3 AND `requires_sensitivity_token=True` (per Adam's Story
   4-1 CR-2 decision — DELETE always requires a token regardless of the
   email's sensitivity classification, as a belt-and-suspenders defender
   posture).
3. Verb returns `ok=False` with `requires_per_action_confirmation=True` AND
   `requires_sensitivity_token=True`. Surface the proposed-action card to the
   user with reasoning ("you asked me to delete this; here's what I'd delete;
   say `/confirm <email_id> delete` to authorize").
4. User types `/confirm <email_id> delete`. Slash-command dispatcher (Story
   5-6) routes to `mint_sensitivity_token(email_id, "delete")`. Receive token.
5. Re-call `propose_action(email_id, ActionType.DELETE,
   confirmation_token=<token>)`. The verb writes a pending row with
   `cooling_off`.
6. The 60-second cooling-off window applies. User can `/cancel <action_id>`.
7. Drainer applies the delete via the Outlook Graph write adapter. The email
   leaves. The action row reaches `status="applied"`.

Banned: never short-circuit to step 5 without step 4. Never proceed past step 1
if `resolved_email_ids` is empty (you cannot delete an email you cannot
identify; ask for clarification instead).

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
