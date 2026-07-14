# WALK-10-6-4-F1 — Hermes per-turn tool surface polluted by unrelated skills

**Filed:** 2026-07-14, at the Adam-typed Discord walk for Story 10-6-4 (AC-6).
**Severity:** MEDIUM. **Owner side:** Hermes-config (this container), NOT `mailbot_api`.
**Relationship:** does NOT reopen Story 10-6-4 (whose adapter keep_alive/timeout + config scope is complete + proven). This is the Seam-B B1 "trim the per-turn tool surface" lever 10-6-4 explicitly identified as Hermes-runtime-owned and deferred. Blocks the *usefulness* half of Epic 10.6 done-flip **clause 3** (cheap lane REACHED → USABLE), not the latency half.

## Symptom (observed live)

Adam typed **"find my unread emails"** in the real Discord DM. The bot replied `qwen (local, free)`:

> "None of the provided functions can be used to find unread emails. These functions are related to text-to-speech, managing task lists, analyzing images, writing files, and converting text to speech audio. For finding unread emails, you would typically use an email client..." [then improvised generic Gmail settings instructions]

## Evidence

- **DB `router_calls`:** `2026-07-14T08:50:21Z, task=chat_completions_tool_call, model_chosen=qwen2.5:3b-instruct-q4_K_M, reason=policy:chat_completions_tool_call:default, outcome=ok, tool_calls_count=0`. The turn RAN and completed on qwen (latency fix works — no timeout/502), but **zero tool calls** because the email tools weren't on the surface qwen saw.
- **qwen was handed the WRONG tools** — its own words name TTS / task-list / image-analysis / write-file tools. None are MailBot email verbs.
- **The MailBot email verbs ARE registered + reachable** (rules out missing-capability): `mailbot-api` FastMCP `ToolManager` exposes **26 tools** live — `find_emails, hydrate_email, get_thread, count_emails, get_sender_summary, propose_action, mint_grant, revoke_grant, cancel_action, revert_action, mint_sensitivity_token, cost_breakdown, reset_degraded_mode, pause_router, resume_router, set_model_oneshot, set_model_persistent, inspect_policy, mute_category, render_spend_chart, pull_pending_notifications, ack_notification, unmute_category, compose_digest, finalize_digest_delivery, draft_reply`. The api served a `ListToolsRequest` on the fresh MCP session at `08:50:39Z` (session `187872887c…`, `POST /mcp/ 200`).
- **Hermes registered a swarm of unrelated user-installed skills this session** (hermes logs, `reconcile ... action=registered`): songsee, gif-search, spotify, heartmula, spike, debugging-hermes-tui-commands, node-inspect-debugger, jupyter-live-kernel, python-debugpy, xurl, writing-plans, subagent-driven-development, test-driven-development, etc. (most tagged `user-modified, skipping` for reconcile, but their tools/skill-prompts still shape the persona's turn). These crowd out / replace the `mailbot-api` MCP tools on the per-turn surface presented to the model.

## Root cause

Hermes-side tool-SELECTION/SURFACE problem, not a MailBot code defect. This Hermes container carries a large set of unrelated skills/MCP servers; the persona's per-turn tool surface is dominated by them (TTS/image/task/dev-tooling), so the MailBot email verbs don't reach the model — even though they are registered and the MCP session is healthy.

## Contrast that isolates the finding

The agent-driven endpoint probe (same day, same code) supplied its OWN correct 4-tool email surface directly to `/v1/chat/completions` → `tool_calls_count=1`, `find_emails` picked, 1.7–4.9s. Same qwen, same endpoint, same latency fix — the ONLY difference is which tools were on the surface. That pins F1 to the Hermes tool-registration layer, upstream of both the adapter (10-6-4) and the Router.

## Recommended fix (a sibling Hermes-config story)

Options (pick at story time):
1. **Prune the Hermes skill/MCP registration for this container** so the `mailbot-api` MCP server's tools dominate — disable the unrelated user skills (songsee, spotify, dev-tooling, etc.) for the MailBot deploy profile.
2. **Per-turn tool allow-list scoped to the `mailbot-api` server** (if Hermes supports server-scoped tool filtering for a channel/persona), so a MailBot chat turn only ever offers the 26 mailbot verbs.
3. Verify against Hermes's actual tool-surface assembly (RECONCILIATION-NOTES §6 item 1 territory — the skill-bundle-under-`hermes-config/skills/mailbot/` migration).

Analogous to how 10-6-4 itself was spawned from a walk finding: recommend filing + resolving before the Epic 10.6 done-flip, since clause 3's "USABLE" bar is not met while a MailBot chat turn can't reach its own email tools.

## Scope guard

- NOT a 10-6-4 regression: the story's adapter keep_alive/timeout + config diff are correct and L3-proven (the turn completed on qwen with no timeout — the exact thing 10-6-4 fixes). F1 is orthogonal.
- The model-independent drain safety gate is unaffected (a wrong/absent tool call cannot touch the mailbox — `pending_actions`/`action_grants` key on `(action_type, email_id)`, no model column).

Memory: [[project_reached_not_equal_usable]] (this is the sharpest example yet — routed + fast, but not usable because the tools don't reach the turn), [[project_hermes_mcp_namespaces_and_session_drop]].
