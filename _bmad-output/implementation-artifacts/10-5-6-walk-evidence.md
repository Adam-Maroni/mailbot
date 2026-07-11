# Story 10-5-6 — AC-6 Live Discord Walk Evidence (2026-07-11, Adam-hands-on + orchestrator DB verification)

**Run mode:** interactive — Adam drove Discord, orchestrator captured DB evidence per checkpoint against the live prod stack (`/data/mailbot.db`, mailbot-api NOT restarted; hermes-config + mailbot_api bind-mounts live).

**Overall verdict: FAIL** — CP1 + CP2 PASS clean; CP3 + CP4 FAIL end-to-end. AC-6 requires all four recognized control phrases to deterministically issue their verb AND complete; two do not. **10-5-6 → `in-progress`.** Two upstream defects filed per N.5.

**Key distinction the walk established:** the **recognized-phrase dispatch layer this story owns is proven working** (CP1 `cancel` + CP2 `pause`/`resume` fire their verbs and move the DB; CP3 `yes, escalate` DID fire `mint_sensitivity_token`). The failures are **upstream of 10-5-6's charter** — the escalation token is minted but never *consumed* into a real Opus draft, and a stuck sensitive-refusal loop bricks the session so `use qwen` is never even recognized.

---

## Baseline (before walk)
- `pause_state.paused = 0` (stale reason `F4-walk-10-5-1` from 07-07)
- `degraded_mode_state.active = 0`
- `router_calls` max id = **14670**
- no open `pending_actions`

---

## CP1 — `cancel` → **PASS**

**Transcript (abridged):** `draft a reply to last email received` → agent found BoursoBank newsletter → `send` → **`propose_action` fired**, "Action proposed (ID: 39). Cooling off for 60 seconds." → (grant-mint looped on a clock-skew bug, see F-below) → `cancel` (bare, no id) → **`mcp_mailbot_api_cancel_action` fired** → "Cancelled. Action 39 will not send."

**DB evidence:**
```
pending_actions id=39: status='cancelled', proposed_at=11:22:33, terminal_at=11:23:06 (~33s, in-window)
action_history for 39: (none — never applied/dispatched to Graph)
open actions after: none
```
**Verdict: PASS.** Bare `cancel` deterministically issued `cancel_action`; the row went `cancelled`; nothing dispatched. The recognized-phrase dispatch worked even without an explicit id (resolved the single pending action).

**Side finding surfaced (F-10-5-6-W4, MEDIUM — grant-mint clock skew):** on `send`, the agent's `mint_grant` looped ~6× on *"timestamp issue / server clock is ahead"* failures (~$0.05 haiku burned), then **falsely narrated "Reply sent."** while the grant was never minted. This is the false-narration class but on the Tier-2/3 grant path (NOT one of 10-5-6's 4 control verbs). Root cause: `expires_at` timestamp handling in the grant-mint choreography (agent-supplied timestamp vs server clock). Filed per N.5.

---

## CP2 — `pause` / `resume` → **PASS** (strongest checkpoint)

**Transcript:** `pause` → **`mcp_mailbot_api_pause_router` fired** → "Router paused." Then, **while paused**, `resume` → **`mcp_mailbot_api_resume_router` fired** → "Router resumed."

**DB evidence:**
```
pause_state AFTER: paused=0, reason='unspecified',
  paused_at =2026-07-11T11:24:58  (advanced from 07-07 → fresh pause wrote a real row)
  resumed_at=2026-07-11T11:25:22  (~24s later → real resume cleared it)
```
**Verdict: PASS.** Both verbs fired for real (timestamps advanced to today). Critically, **`resume` typed in chat WHILE PAUSED both fired `resume_router` and produced a reply** — the exact F-10-5-4 gap (earlier 10-5 walk: resume-from-chat bounced with raw 502s) is closed end-to-end via plain NL.

---

## CP3 — `yes, escalate` → **FAIL end-to-end** (dispatch fired; consumption + draft did not)

**Baseline:** router_calls max id=14712; `escalation_armed`=None; `user_confirmations` empty.

**Transcript:** `draft a reply to "Alerte de sécurité"` (sensitive Google alert) → agent refused-with-offer *"Say yes, escalate to authorize the draft."* → `yes, escalate` → **`mcp_mailbot_api_mint_sensitivity_token` fired** → BUT agent re-rendered the refusal envelope. Typo retry `yes, ecalate` (missing s) → refusal (correctly not recognized — exact-match). Exact retry `yes, escalate` (arm still live, 127s old) → refusal AGAIN.

**DB evidence:**
```
escalation_armed: (1, armed_at=11:29:41)                 ← the phrase DID arm (dispatch works)
user_confirmations id=3: scope='sensitivity_token', created_at=11:29:41, consumed_at=NULL  ← MINTED, NEVER CONSUMED
router_calls 14716-14720: task_type='chat_completions_tool_call',
  model_chosen_reason='sensitivity_gate:refused', outcome='failed'   ← 4-5 refusals on the target email
draft_reply rows created this CP3: 0                     ← the Opus draft pipeline NEVER dispatched
```
**Verdict: FAIL (end-to-end).** The recognized phrase `yes, escalate` **correctly issued `mint_sensitivity_token`** (arm set + `user_confirmations` row minted) — the 10-5-6 dispatch contract half works. But the token was **never consumed** (`consumed_at=NULL`) and **no `draft_reply` Opus row was ever created** — the mint→token→draft chain is broken, so the sensitive draft never happens and the agent falls back to re-rendering the refusal. This is **F-10-5-2-W2 NOT closed end-to-end** + the F-10-5-11 draft-pipeline-unreachable-from-chat gap.

---

## CP4 — `use qwen` → **FAIL** (never reached — session bricked by CP3)

**Baseline:** router_calls max id=14719.

**Transcript:** `use qwen` → returned the **sensitivity refusal envelope** (verbatim from CP3) — completely unrelated to a model-override request.

**DB evidence:**
```
router_calls 14720: task_type='chat_completions_tool_call',
  model_chosen_reason='sensitivity_gate:refused', outcome='failed'
new one_shot rows this CP4: 0     ← set_model_oneshot NEVER fired
new qwen rows this CP4: 0
```
**Verdict: FAIL.** `use qwen` never reached the recognized-phrase layer — the session was **stuck in CP3's sensitive-refusal loop**, short-circuiting every subsequent turn to `sensitivity_gate:refused` regardless of content. `set_model_oneshot` never fired; the F-10-5-6-W1 literal bug could not be fairly tested because the session was bricked upstream. This is the **F-10-5-7 session-brick class** ("one sensitive attempt poisons the session") resurfacing.

---

## Scorecard

| CP | Phrase | Recognized-phrase dispatch (10-5-6 contract) | End-to-end AC-6 | Verdict |
|----|--------|-----------------------------------------------|-----------------|---------|
| 1 | `cancel` | ✅ issued `cancel_action`, DB moved | ✅ | **PASS** |
| 2 | `pause`/`resume` | ✅ both fired, DB 0→1→0, resume-while-paused replied | ✅ | **PASS** |
| 3 | `yes, escalate` | ✅ issued `mint_sensitivity_token` (armed+minted) | ❌ token unconsumed, 0 draft_reply | **FAIL** |
| 4 | `use qwen` | ❌ never reached (session bricked by CP3) | ❌ | **FAIL** |

**AC-6 = FAIL.** The 10-5-6 charter (README + persona recognized-phrase contract + drift test) is CORRECT and CR-clean; CP1/CP2 prove the dispatch layer works. The two FAILs are upstream defects (escalation-consumption + session-brick) that block the end-to-end proof.

---

## Findings filed per N.5

- **F-10-5-6-W2 (HIGH) — escalation token minted but never consumed into a draft dispatch.** `yes, escalate` fires `mint_sensitivity_token` (arm + `user_confirmations` row created), but the token is never threaded into a `draft_reply` Router call as `confirmation_token` — `consumed_at` stays NULL, 0 `draft_reply` rows, 4× `sensitivity_gate:refused`. The API-layer authorization (10-5-2) and the persona dispatch (10-5-6) both work; the **glue that consumes the confirmation into the actual sensitive draft dispatch does not**. Compounded by F-10-5-11 (the persona cannot reach the real `draft_reply` Opus pipeline from chat — CP1 showed it hand-writing drafts in haiku instead). This is what blocks 10-5-2's AC-4 and 10-5-6's AC-6 CP3 end-to-end.
- **F-10-5-6-W3 (HIGH) — stuck sensitive-refusal loop bricks the session.** After the CP3 sensitive-refusal, every subsequent turn (`yes, escalate` exact, `use qwen`) short-circuited to `sensitivity_gate:refused` and re-rendered the same envelope regardless of content — `use qwen` (CP4) never reached the recognized-phrase layer. This is the F-10-5-7 "one sensitive attempt poisons the session until reset" class resurfacing; it makes the recognized-phrase contract unreachable once a session is poisoned, undermining the very determinism 10-5-6 exists to guarantee.
- **F-10-5-6-W4 (MEDIUM) — grant-mint clock-skew loop + false "Reply sent."** On CP1 `send`, `mint_grant` looped ~6× on server-clock-vs-supplied-timestamp `expires_at` failures, burned ~$0.05 haiku, then falsely narrated "Reply sent." while no grant was minted. False-narration class on the Tier-2/3 grant path (not a 10-5-6 control verb). Root cause: `expires_at` timestamp derivation in the grant-mint choreography.

**Spend this walk:** ~$0.20 haiku (chat turns; the draft/escalation never reached Opus — no Opus spend because the draft pipeline never dispatched). Per `feedback_anthropic_spend_source_of_truth.md`, Console is authoritative for any real total.

**Environment left:** `escalation_armed` standing (self-expires in 10 min from 11:29:41); no override armed; not paused; not degraded; action 39 cancelled (nothing sent). Mailbox as found.

---

## CP4 deep-dive (2026-07-11, follow-up investigation — "keep investigating on 4")

**Question:** did CP4 (`use qwen`) fail on its own merits, or only as collateral of CP3's session-brick?

**Answer: collateral. The verb is not broken.** Called `set_model_oneshot(db_path=…, model='qwen')` DIRECTLY against the live stack (bypassing the persona):
```
ok=True model='qwen2.5:3b-instruct-q4_K_M' expires_at='2026-07-11T14:50:11Z'  (set_at 14:45:11 + 300s exactly)
active override read-back: model=qwen…, expires_at=14:50:11, set_at=14:45:11
```
Real 5-min TTL, zero confabulation. The F-10-5-6-W1 machinery is sound — the story always said the bug was the persona not *calling* the verb, not the verb itself. Confirmed.

**ROOT CAUSE of W2 + W3 located — `router.py:2088-2095` (the `chat_completions_tool_call` sensitive branch):**
- The branch refuses a sensitive dispatch unless a `confirmation_token` is passed **as a call argument** (`if confirmation_token is None … : refuse + record_pending_sensitive_refusal`).
- It does **NOT** consult `escalation_armed` (via `consume_escalation_arm`), and does **NOT** consult a pre-recorded `user_confirmations` row for `(email_id, task_type)`.
- Meanwhile the intended handshake (user_confirmation.py:294 `consume_escalation_arm`) is only wired into `mint_sensitivity_token` — which DID fire (arm set, `user_confirmations id=3` recorded) — but the tool-call DISPATCH that actually attempts the sensitive draft never looks at that recorded confirmation or the arm. So: mint records a confirmation → dispatch ignores it → refuses → re-writes `pending_sensitive_refusal` → the row (keyed on the shared `unknown-external` origin per 10-5-2 CR-8) sits and short-circuits EVERY later turn, `use qwen` included.

**In one sentence:** the arm/mint half (10-5-2/10-5-6) and the dispatch-authorization half (`chat_completions_tool_call`) were both built but never wired to each other — the dispatch only honors an inline `confirmation_token` arg, never the recorded `user_confirmations` row or the arm. **The fix locus for W2/W3 is precise: `router.py:~2095` must consult `escalation_armed` / the recorded `user_confirmations` row before refusing** (mirroring what `mint_sensitivity_token` already does), so the arm minted by `yes, escalate` actually unlocks the very next sensitive dispatch. That also stops the `pending_sensitive_refusal` accumulation that bricks the session (W3).

**CP4 verdict: FAIL was collateral, not intrinsic.** `set_model_oneshot` is verified working with a real TTL; a clean-session re-test of `use qwen` would isolate the persona-recognition half (not re-run here to avoid more paid/haiku churn — the verb is proven; the persona-reach is gated on clearing the W3 brick).

**Cleanup performed:** reset the test-armed override (throwaway process only — live API untouched); cleared the stale `pending_sensitive_refusal` (`unknown-external`) + `escalation_armed` rows. Final state: 0 pending refusal, 0 arm, not paused, not degraded, router_calls max id 14720. `user_confirmations id=3` (consumed_at=NULL) left as W2 evidence.

---

## W2/W3 FIX IMPLEMENTED + LIVE-VERIFIED (2026-07-11, dev=opus-4-8)

**Fix (router.py sensitive branch, ~2095):** before refusing a no-inline-token sensitive `chat_completions_tool_call`, call `authorize_sensitive_dispatch(email_id, task_type)` — the SAME user-gated escalation primitive `mint_sensitivity_token` uses, applied AT THE DISPATCH SEAM. Closes the mint→relay-token gap the persona kept dropping (W2) and stops the `pending_sensitive_refusal` accumulation that bricked the session (W3).

**Round 1 (single-use arm) — 3 gate tests + live proof.** Re-walk showed `yes, escalate` now gets PAST the gate (4 `escalation-confirmed` ok dispatches vs. last walk's pure refusal loop), session recovered, real forward progress (hydrate+draft). **Residual surfaced:** the persona fans out SEVERAL sensitive calls per turn; a single-use arm authorized only the first, so 2nd/3rd re-refused mid-flow (3 interspersed refusals, 1 standing pending row).

**Round 2 (refinement — Adam-directed) — scope authorization to (email, task) for the TTL window.** New `authorize_sensitive_dispatch` records a TTL-windowed, re-readable `escalation_dispatch` grant (migration 028 widens the `user_confirmations.scope` CHECK) on first authorization and PEEKS it on subsequent same-(email, task) dispatches — one `yes, escalate` covers the whole turn; a DIFFERENT email still refuses (blast-radius preserved).

- **$0 live proof (freshly-restarted process, migration 028 applied):** ONE arm → THREE same-email dispatches all `ok=True`; different email off the same arm → `ok=False`/`sensitivity_blocks_api`. Exactly as designed.
- **Migration 028 dry-run on a COPY of prod DB:** 2→2 rows preserved, indexes intact, `escalation_dispatch` INSERT accepted. Then applied to live DB via restart (verified).
- **Final Discord re-walk (Adam, 2026-07-11 17:21):** ONE `yes, escalate` → mint succeeded → **1 pre-arm refusal + 2 `escalation-confirmed` authorized dispatches + 1 `escalation_dispatch` grant recorded + 0 standing pending_sensitive_refusal** (session clean, NOT bricked). Monotonic improvement across the three walks:

| Walk | `yes, escalate` | `sensitivity_gate:refused` | Session after |
|---|---|---|---|
| original (pre-fix) | 2× typed, still failed | 4-5 (hard loop) | **bricked** |
| re-walk (round-1 fix) | worked, re-refused mid-flow | 3 interspersed | 1 pending left |
| **final (refined)** | **1×, covered the turn** | **1 (pre-arm only)** | **clean, 0 pending** |

**Verdict: W2 CLOSED + W3 CLOSED, code + live verified.** `yes, escalate` reliably authorizes the sensitive escalation for the whole turn, scoped to the exact email, with no session brick. Gates: ruff/mypy clean, full suite **1864+2+3** (+5 net vs 1859: 5 new dispatch-seam tests). Migration 028 applied live.

**RESIDUAL (separate defect, NOT this fix's scope) — F-10-5-11 persists:** the draft is STILL hand-written in haiku ("the Router's draft_reply task isn't directly exposed via MCP"), 0 Opus `draft_reply` rows in all three walks. The escalation now correctly authorizes the cloud path, but the persona does not dispatch the real Opus draft pipeline. This is the draft-pipeline-reachability gap (3rd walk it's bitten) — its own story-sized fix, tracked separately.

**Spend:** ~$0.04 haiku across the re-walks (no Opus — draft never reached the pipeline). Console-authoritative. Environment left clean (0 arm/pending/grant, not paused/degraded).
