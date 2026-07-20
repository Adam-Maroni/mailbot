# Story 10.7.7 — AC-7 clause-3 live walk evidence (2026-07-20)

**Walk:** Adam sent "find my unread emails" on real Discord, 10:02→10:05 AM (Hermes on live qwen2.5:3b via Ollama, mailbot-api restarted with the new code, migration 029 applied, `is_read` seeded via full re-sync → 86 genuinely-unread rows).

**Discord reply (READ THE REPLY, per the 10.7.6 lesson):**
> mcp_mailbot_api_find_emails... (×6) — Working — 2 min — iteration 6/90 …
> **"I keep calling mcp_mailbot_api_find_emails with the same input and getting the same result, so I'm stopping instead of looping. If you were asking for unread emails, try rephrasing, or narrow the request (e.g. a sender or a date range) so I have something new to search on."**

**router_calls evidence (id > 15398 pre-walk baseline; 8 rows):**

| id | task_type | model | reason | outcome | cost | tcc | tool |
|----|-----------|-------|--------|---------|------|-----|------|
| 15399 | chat_completions_tool_call | qwen2.5:3b | policy:...tool_call:default | ok | 0.0 | 1 | **find_unread_emails** (wrong namespace, F-10-7-6-R1 residual) |
| 15400 | chat_completions_tool_call | qwen2.5:3b | policy:...tool_call:default | ok | 0.0 | 1 | find_emails `{"filter":{}}` |
| 15401–15404 | chat_completions_tool_call | qwen2.5:3b | policy:...tool_call:default | ok | 0.0 | 1 | find_emails `{}` ×4 |
| **15405** | chat_completions_tool_call | qwen2.5:3b | policy:...tool_call:default | **failed** | **0.0** | — | **GUARD FIRED — NO_PROGRESS terminal** |
| 15406 | hermes_aux | claude-haiku-4-5 | policy:hermes_aux:default | ok | 0.000249 | — | non-tool TEXT call (179 in / 14 out) |

**Verdict signals:** qwen rows=7 · find_emails invoked=5 · max tool_calls_count=1 · **guard fired at the 5th identical find_emails (id 15405, $0)** · total cost = **$0.0002**.

## Assessment — the guard WORKED; two honest caveats

**What PASSED (the load-bearing F-10-7-6-R2 fix):**
- **The runaway is DEAD.** 6 calls / iteration 6/90 / ~2 min — vs 10.7.6's ~60 calls / iteration 55/90 / 26 min. The guard detected the same-verb-same-args storm and returned `NO_PROGRESS` at the 5th identical `find_emails({})`.
- **The `NO_PROGRESS` message rendered in Discord** as a calm, user-actionable reply (not a 502, not a silent hang). Graceful-200 boundary render confirmed live.
- **No paid tool-call escalation, no 502, no rate-limit breach.** The qwen tool-loop was killed at $0; there was NO escalation of the tool-calling loop to a paid model (contrast 10.7.6 rows 15293–15295 → haiku → HTTP 502 rate-limit breach).

**Caveat 1 — one $0.0002 haiku TEXT row (id 15406), not a strict $0 turn.** After the guard fired, Hermes made ONE non-tool `hermes_aux` text call on haiku (179 tok in / 14 out, $0.000249) — almost certainly to format the final user message. This is NOT the AC-3 breach 10.7.6 hit (that was the tool-LOOP escalating to paid + 502). It's a downstream single text completion costing a fraction of a cent. Strictly, the turn was **~$0.0002, not $0.** Whether that clears AC-3 ("fails closed at $0… MUST NOT escalate to a paid model") is Adam's call — the *loop* failed closed at $0; a separate Hermes text-compose step used the paid text lane.

**Caveat 2 — the unread reply was NEVER rendered (find_unread_emails mis-binding + empty find_emails).** qwen's FIRST call (id 15399) was `find_unread_emails` — the wrong-namespace mis-binding (F-10-7-6-R1, an out-of-repo Hermes/tool primitive, NOT fixed by this story). It then fell to `find_emails({})` with an EMPTY filter — it never set `unread_only:true`, so it never exercised AC-1's new filter, and got recent-all (which it correctly recognized as non-progress → storm → guard). **So AC-1's user-visible payload (a real unread-emails list) was NOT demonstrated this walk** — qwen didn't select the `unread_only` filter. The `unread_only` capability is proven by offline tests + 86 live is_read=0 rows exist, but the model didn't reach for it.

## Net
The BLOCKING defect this story owned — **F-10-7-6-R2 runaway loop → paid escalation → 502** — is FIXED and proven live: the guard stops the storm at $0 and renders a graceful terminal message. But the walk did NOT produce a usable *unread* reply, because qwen (a) mis-bound to `find_unread_emails` then (b) called `find_emails` without `unread_only`. That's the SELECTION layer (F-10-7-6-R1 + a new "qwen doesn't set unread_only" gap), DOWNSTREAM of and distinct from the runaway this story fixed.

---

## Walk-fix attempt + walks #2/#3 → DECISIVE: Qwen-3B argument-population ceiling (F-10-7-7-W1)

**Walk-fix applied (Task 8.5):** three model-facing description/prompt edits directing "unread → find_emails(unread_only=true); no separate find_unread_emails tool" (the proven 10.7.5 SELECTION lever).

**Walk #2 (11:13) + Walk #3 (11:16, fresh Hermes):** both returned the SAME guard stop-message. Router evidence: **one** `chat_completions_tool_call` row each (id 15442, 15443), qwen, `outcome=failed`, $0 — the guard fired on the FIRST mailbot dispatch (`repeat_count=4`). Restarting Hermes did NOT change it (killed the cross-turn-contamination theory).

**Two decisive log facts:**
1. **`find_emails` NEVER executed at the MCP verb level** — across all walks the only `mcp.tool.ok` events are the `pull_pending_notifications` cron. The 4 "identical calls" the guard counts are tool-call INTENTIONS in the transcript Hermes replays (the model re-emits the same call), intercepted at the `/v1/chat/completions` seam BEFORE the verb.
2. **`repeated_args_redacted: "{}"`** (added a guard-fire arg-diagnostic to see this) — qwen calls `find_emails` with a **completely empty args object**: no `filter`, no `unread_only`. The walk-fix did NOT move it AT ALL.

**Verdict (Adam-decided 2026-07-20): F-10-7-7-W1 is a Qwen-3B ARGUMENT-POPULATION CEILING.** The description/prompt lever moved tool SELECTION in 10.7.5 but does NOT move ARGUMENT-population here — qwen picks `find_emails` (right tool) but won't fill in `unread_only` no matter how the description/instruction is worded. In-repo structural fixes are constrained: the chat tool list is Hermes-supplied (`request.tools`, main.py:856), so a `find_unread_emails` alias tool can only be added in `hermes-config` (out of this repo). 

**Disposition:** the three description/prompt edits were **REVERTED** (dead prompt-bloat degrades a 3B/Q4 context per the 10.7.0 spike). **KEPT:** the runaway guard (the real, proven win), the `unread_only` FILTER capability (migration 029 + schema + query — correct, tested, ready for a bigger-local-model or a Hermes-side alias), and the guard-fire arg-diagnostic (`repeated_args_redacted`). **Escalated:** the $0-local-unread-reply gap goes to the qwen-management epic (bigger local model vs Hermes-side find_unread_emails alias vs haiku-floor). Story STAYS `review`; Epic 10.6 clause 3b STAYS OPEN.
