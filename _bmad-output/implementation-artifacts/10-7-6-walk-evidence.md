# Story 10.7.6 — Clause-3 Live Re-Walk Evidence (AC-8 / Task 9)

**Date:** 2026-07-18 (11:49 → 12:15 UTC, ~26 min turn)
**Walker:** Adam (hands-on, real Discord message), driven by autonomous-story-run orchestrator.
**Message sent:** `find my unread emails` (verbatim, real Discord → live Hermes gateway → qwen).
**Surface state:** trimmed config live (`memory` dropped), hermes restarted at Task 1; live resolver pre-walk confirmed `memory ✗ disabled`, `clarify ✓`, `cronjob ✓`, `mailbot-api all tools enabled`.
**Pre-walk baseline:** max `router_calls` id = 15223.

## Verdict: ❌ FAIL — selection fixed, but the turn RUNS AWAY and never renders a usable reply

The `memory`-drop fixed VERB SELECTION (qwen picks `find_emails`, `memory` scored 0), but that exposed a **runaway agent-loop**: qwen re-invoked `find_emails` ~60 times on empty `input:{}` over **26 minutes**, never produced a "here are your unread emails" reply, EVENTUALLY ESCALATED TO A PAID MODEL, and died on an HTTP 502 rate-limit. AC-8 FAILS on the usable-outcome AND no-paid-escalation conditions.

**Discord transcript (Adam, 2026-07-18):**
- `mcp_mailbot_api_find_emails... (×60)` (message edited as the count climbed)
- `Working — 24 min — iteration 55/90, waiting for provider response (streaming)`
- `Retrying in 2.9s (attempt 1/3)...` → `attempt 2/3` → `API failed after 3 retries — HTTP 502: {'error':{'type':'router_error','message':'rate limit breached: lane:interactive'}}`

## Evidence (router_calls, rows id > 15229 — the turn window)

Queried live from `/data/mailbot.db`:
- **66 rows**, window `11:49:04Z → 12:15:20Z` (~26 min).
- **models:** `qwen2.5:3b-instruct-q4_K_M` ×63, `claude-haiku-4-5-20251001` ×3.
- **verbs:** `find_emails` ×59, `find_unread_emails` ×1, `(empty)` ×6.
- **outcomes:** `ok` ×60, `failed` ×6.
- **last 3 rows (15293–15295):** `claude-haiku-4-5-20251001`, `outcome=failed` — the loop escalated OFF qwen onto the PAID lane, which then hit `rate limit breached: lane:interactive` → 502.

(15224–15229 immediately before the turn are the unrelated `ingest-pipeline-*` background classification worker; excluded.)

## Reading

1. **SELECTION fix confirmed (the one thing 10.7.6 owned):** `memory` scored **0 picks** (vs 9/11 on the failed 2026-07-17 walk); the `turn` mis-binding did NOT recur (first pick 15230 stayed in the `mcp_mailbot_api_*` namespace). Dropping `memory` from `platform_toolsets.discord` did exactly what it was scoped to do — it removed the dominant attractor and qwen now reaches `find_emails`.

2. **But clause 3 is NOT usable — a NEW blocking defect is now dominant:** the turn LOOPS. ~60 `find_emails` calls on empty `input:{}`, 26 min wall-clock, 90-iteration agent cap being chewed through, no reply rendered. This is the F-10-7-6-R2 pattern — promoted here from "non-blocking observation" to the **BLOCKING** clause-3 defect.

3. **The cost thesis was violated on this turn:** the runaway loop eventually escalated to `claude-haiku-4-5` (rows 15293–15295), i.e. it spilled onto the PAID lane — the exact outcome the local lane exists to avoid — and that paid lane 502'd on the interactive rate limit. So the turn was neither $0 nor successful.

## Classification of the loop (for the re-open / next lever)

Candidate root causes, to be characterized by the re-opened work (NOT decided here):
- **Empty-arg non-termination:** `find_emails` called with `input:{}` — if the empty-arg call returns a result the agent doesn't treat as terminal (or returns nothing the model can render), qwen re-issues the call. Likely fix surface: default/require args so the first call returns a consumable result, or a Hermes-side agent-loop cap / result-consumption fix.
- **Result-not-consumed:** the tool result may be returned but not fed back to the model in a form that ends the turn.
- **Hermes agent-iteration behavior:** the `iteration 55/90` counter shows Hermes' own loop cap; the 3B model may not emit a terminal "final answer" so Hermes keeps re-prompting.

This is DOWNSTREAM of clause 3's selection layer — it is an ARGUMENT-fidelity / RESULT-consumption / turn-termination problem, a different layer than 10.7.6's toolset-allow-list lever.

## Discharge — NONE. Story re-opens.

- **Story 10.7.6 done-gate (AC-8) — FAILED.** No usable reply; paid escalation occurred; 502. Story stays `review` and re-opens on the loop layer.
- **Epic 10.7 clause 3 / Epic 10.6 clause 3b — NOT discharged.** REACHED (selection) but NOT USABLE (turn runs away) — the exact REACHED-≠-USABLE distinction the epic's own discipline names.
- **F-10-7-6-R2 promoted to BLOCKING** (runaway find_emails loop → no reply → paid escalation → 502). This is the next load-bearing lever.

**What DID advance (bank it):** the `memory`-drop selection fix is real and verified live — a genuine step past the 2026-07-17 failed walk. 10.7.6's config change is correct and worth keeping; it is simply not SUFFICIENT for clause 3 on its own. The remaining gap is a distinct, newly-exposed defect layer.
