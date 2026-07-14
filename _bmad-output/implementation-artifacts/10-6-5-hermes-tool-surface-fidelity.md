# Story 10.6.5: Hermes per-turn tool-surface fidelity — the MailBot email verbs must reach the chat turn

Status: backlog (spawned 2026-07-14 from WALK-10-6-4-F1 at the 10-6-4 Adam-typed Discord walk)
Epic: 10.6 (Capability Reachability) — sprint-status key `10-6-5-hermes-tool-surface-fidelity`

**Spawned by Adam (2026-07-14):** the 10-6-4 Adam-typed Discord walk proved the latency fix (a qwen chat turn completes within budget on the real persona path — done-flip clause 3a) but exposed that the turn's tool surface is polluted by unrelated Hermes skills, so the MailBot email verbs never reach the model. This story closes done-flip **clause 3b** (tool fidelity). Epic 10.6 cannot done-flip without it.

## Story

As Adam,
I want a real Discord chat turn ("find my unread emails") to actually invoke the MailBot email verb (a `find_emails`/peer tool-call), not zero-tool-call improvisation,
So that the cheap lane is genuinely *usable* — the qwen turn reaches the mailbox, closing the "REACHED → USABLE" gap end-to-end (10-6-4 made it fast; this makes it useful).

## Diagnosis (measured live at the 10-6-4 walk — see WALK-10-6-4-F1)

Full evidence: [WALK-10-6-4-F1-hermes-tool-surface-pollution.md](WALK-10-6-4-F1-hermes-tool-surface-pollution.md).

- Adam typed "find my unread emails" → bot replied `qwen (local, free)`: "None of the provided functions can be used to find unread emails... these functions are related to text-to-speech, managing task lists, analyzing images, writing files..." then improvised generic Gmail instructions.
- DB `router_calls`: `2026-07-14T08:50:21Z, task=chat_completions_tool_call, model_chosen=qwen2.5:3b, outcome=ok, tool_calls_count=0`. The turn RAN + completed on qwen (latency fix works) but **zero tool calls** — wrong tools on the surface.
- **The MailBot verbs ARE registered + reachable** (rules out missing-capability): `mailbot-api` FastMCP `ToolManager` exposes 26 tools incl. `find_emails`, `hydrate_email`, `count_emails`, `get_sender_summary`, `propose_action`, `draft_reply` (introspected live); api served a `ListToolsRequest` on the fresh MCP session at 08:50:39Z.
- **Hermes registered a swarm of unrelated user skills this session:** songsee, gif-search, spotify, heartmula, spike, debugging-hermes-tui-commands, node-inspect-debugger, jupyter-live-kernel, python-debugpy, xurl, writing-plans, etc. These crowd out / replace the mailbot-api MCP tools on the persona's per-turn surface.
- **Isolating contrast:** the agent-driven endpoint probe (same code, same qwen) supplied its OWN correct 4-tool email surface → `tool_calls_count=1`, `find_emails` picked, 1.7–4.9s. The ONLY difference is which tools were on the surface → pins the defect to the Hermes tool-registration layer.

**Root cause:** Hermes-side tool-SELECTION/SURFACE problem in this container, NOT a MailBot code defect. Fix locus is `hermes-config/` (this container's skill + MCP registration), NOT `mailbot_api`.

## Scope

Hermes-config only. Do NOT touch `mailbot_api` (the 26 verbs are correct + registered). Two candidate approaches (pick at dev time after inspecting the actual Hermes tool-surface assembly):

### Approach A — prune the Hermes skill/MCP registration
Disable the unrelated user-installed skills (songsee, spotify, gif-search, dev-tooling, TTS/image, etc.) for the MailBot deploy profile so the `mailbot-api` MCP server's tools dominate the per-turn surface. Likely the `hermes-config/` skill registration / `.hub` config or the reconcile profile.

### Approach B — per-turn tool allow-list scoped to the mailbot-api server
If Hermes supports server-scoped or persona-scoped tool filtering for a channel, restrict a MailBot chat turn to only offer the mailbot-api verbs (+ any essential Hermes built-ins). More surgical; survives future skill installs.

Verify against Hermes's real tool-surface assembly (RECONCILIATION-NOTES §6 item 1 — the skill-bundle-under-`hermes-config/skills/mailbot/` migration is adjacent territory).

## Acceptance Criteria

- **AC-1** — On a live Discord "find my unread emails" turn, the DB `router_calls` row shows `tool_calls_count ≥ 1` with a MailBot verb (`find_emails` or peer), NOT `tool_calls_count=0` improvisation. (This is the WALK-10-6-4-F1 reproduction, now passing.)
- **AC-2** — The per-turn tool surface presented to the model contains the MailBot email verbs and is NOT dominated by unrelated skills (TTS/image/task/dev-tooling). Evidence: config diff + the tool list actually sent on a turn (Hermes debug log or a captured request).
- **AC-3** — No regression to the model-independent drain safety gate (reversible executes / irreversible prompts) — unaffected by tool-surface changes, but confirm the confirmation machinery still fires on an irreversible verb.
- **AC-4** — Sensitivity gate preserved (a confidential/sensitive email tool-call still routes per NFR-PRIV-2).
- **AC-5** — MANDATORY-CR reviewer ≠ dev (persona/tool-registration seam). Any `mailbot_api` tests stay green (this should be a Hermes-config-only change; if truly zero `mailbot_api` change, the suite is unchanged).
- **AC-6** — Phase 3.5 live Discord re-walk (Adam-hands-on, $0): "find my unread emails" → qwen invokes `find_emails` → the bot returns actual unread emails. **Closes done-flip clause 3b.** Then a follow-up chained turn ("mark the first one as read") exercises the reversible-execute path live.

## Risks / Notes

- **Config-only, container-scoped.** The fix likely lives in this Hermes container's skill/MCP registration, which may not be a clean repo-tracked file (`hermes-config/` has a large vendored `.hub`/skills tree). Capture the exact change locus + whether it's repo-trackable or a container-runtime setting; if runtime-only, document the setup step for CP-1/deploy (like the `hermes fallback add` runbook carry-forward).
- **Do NOT chase the model.** qwen behaved correctly given the wrong tools — this is not a qwen fidelity issue (contrast the 10-6-1 argument-fidelity work). The 3B model refusing to hallucinate email tools it wasn't given is arguably correct behavior.
- **MCP session-drop (F-10-5-1-W2):** restart hermes after any api restart before the re-walk.
- Relationship: closes WALK-10-6-4-F1. Inside Epic 10.6 done-flip **clause 3b** (Adam split clause 3 into 3a-latency [10-6-4, done] / 3b-tool-fidelity [this story] on 2026-07-14). Sibling to 10-6-4 (latency, clause 3a) and 10-6-2 (draft reach, clause 4). Memory: [[project_reached_not_equal_usable]], [[project_hermes_mcp_namespaces_and_session_drop]].
