# Story 10-5-5 — Walk Evidence (Task 6, Adam-hands-on live footer-verify + live re-derive)

**Status:** LIVE WALK EXECUTED 2026-07-11 (Adam-delegated: "run the manual verification yourself"). AC-1 PASS live; AC-3 PASS-WITH-FINDINGS (mechanism live-verified $0; 1 finding filed; real-paid-spend render is Adam's remaining half). Dev + MANDATORY-CR complete at code-L3.
**Run-mode:** HYBRID — Tasks 1-5 + 7 autonomous (done); Task 6 live clauses executed as far as $0 allows by the orchestrator, real-spend + Console reading remain Adam's.
**Baseline commit:** 0d6f082. **Suite at HALT:** 1828 passed / 2 skipped / 3 deselected.
**Stack at walk:** mailbot-hermes / mailbot-api / mailbot-ollama all up. `mailbot_api/` is bind-mounted (new re-derive + footer code live on disk); `scripts/` is NOT (WALK-10-5-4-F1 — the `rederive-cost` CLI subcommand is absent in-container; invoked the module directly via `python -c`). mailbot-api restarted once during the walk to load the bind-mounted footer code (booted clean, no errors).

---

## F-10-5-5-W2 (HIGH) — FIXED 2026-07-11 — AC-2 refusal surfaced as HTTP 502 + retry storm, and the message wrongly cited "degraded mode" on a user override

**Discovered:** 2026-07-11, Adam live Discord walk (real paid turns, post-A1-restart). **FIXED same session** (Adam: "Solve it now"). Filed per N.5, then remediated.

**Fix (shipped 2026-07-11):**
- **W2a (502→graceful 200):** added `_tool_calls_unavailable_completion` in `main.py` (mirrors 10.5.2's `_sensitivity_refusal_completion`); the tool branch renders a `TOOL_CALLS_UNAVAILABLE_DEGRADED` refusal as a graceful 200 (non-stream + stream) BEFORE `_raise_router_error_if_failed`, so Hermes no longer 3×-retries a 502.
- **W2b (accurate wording):** `router.py` captures `_degraded_active` at the gate and branches the refusal message — degraded-shed vs. "the selected model (<qwen>) is a local model and can't handle tool-calling requests; ask without a tool, or switch back to an Anthropic model / clear the one-shot override." No false "degraded" claim on route (b).
- **Tests:** `test_route_b_refusal_message_does_not_claim_degraded` + `test_route_a_refusal_message_does_claim_degraded` (wording), `test_tool_call_to_qwen_renders_graceful_200_not_502` + `test_tool_call_to_qwen_graceful_200_streaming` (endpoint 200-not-502). All green.
- **Live-verified (post-restart, exact repro):** force qwen + tool turn → **HTTP 200** (was 502) with `"the selected model (qwen2.5:3b-instruct-q4_K_M) is a local model and can't handle tool-calling requests. …"`; normal haiku tool turn unaffected (200 + correct footer). W2c (refuse vs. auto-fallback-to-haiku) NOT taken — the graceful refusal is the chosen behavior (honors the user's explicit qwen pick by telling them, rather than silently overriding it).

**Repro (Adam, live):**
1. Paid turns worked correctly first: `id=14658` ("This is a test" → haiku 396/17 $0.0030) + `id=14659` ("Use qwen for next request" → haiku 468/80 $0.0033), both `outcome=ok`, footer `🤖 haiku (Anthropic API) · …` correct.
2. The "use qwen" turn armed a one-shot override (`set_model_oneshot` → qwen).
3. Next turn ("This is a test.") was a tool-calling chat turn → AC-2's `_model_supports_tool_calls` gate saw the model resolved to qwen (via the override — route "b", NOT degraded), returned `TOOL_CALLS_UNAVAILABLE_DEGRADED` with `ok=False`.
4. Ledger `id=14660-14665`: six `chat_completions_tool_call` / `model=qwen2.5:3b-instruct-q4_K_M` / `reason=slash_command:one_shot:adam` / `outcome=failed` / 0 tok rows (the 3× Hermes retries × 2 message attempts). **`degraded_mode_state.active=0` throughout** (last entered/exited 2026-07-06) — degraded was NOT active.
5. Discord surfaced: `API call failed after 3 retries: HTTP 502 … 'tool-calling is unavailable under degraded mode — full-cost models are shed and the local fallback cannot serve tools; resolve the budget (or wait for month-rollover) and retry'` — a wall of retry spam.

**Two defects:**
- **W2a (HIGH — 502 + retry storm):** the AC-2 typed refusal returns `ok=False` → the `/v1/chat/completions` tool branch maps it via `_raise_router_error_if_failed` → **HTTP 502** → Hermes treats 502 as transient → **3× retry ladder** → ugly multi-message spam. The whole POINT of AC-2 was to replace opaque failures with a clean recoverable signal; instead it became a 502 storm. **The fix precedent already exists:** Story 10.5.2 solved this exact shape for sensitivity refusals — `_sensitivity_refusal_completion` (main.py:798) renders them as a graceful 200 chat message, NOT a 502. `TOOL_CALLS_UNAVAILABLE_DEGRADED` must take the same graceful-render path (carry a refusal envelope / be recognized at the boundary and rendered as an assistant message).
- **W2b (MEDIUM — wrong wording):** the message hardcodes "under degraded mode", but this fired on a **user override with degraded OFF**. This is EXACTLY the LOW item flagged in this story's own pre-review §3 ("route (b) non-degraded case yields the same 'under degraded mode' message") and ACCEPTED-WITH-RATIONALE as "rare." Adam hit it in ~90 seconds → the rationale was wrong. Message must be conditional on cause: degraded-shed vs. user-picked-a-tools-incapable-model.

**Open design question (W2c):** should an explicit "use qwen" even refuse a tool turn, or should the router keep a tool-capable model (haiku) for that turn and tell the user qwen can't do tool-calls? (Adam weighed "graceful refusal" vs "fall back to haiku + tell you" — deferred to the fix pass.)

**Fix loci (for the follow-up):** `mailbot_api/main.py` tool branch (`_chat_completions_tools_dispatch` result handling ~:602-626 + `_raise_router_error_if_failed` :881) — route `TOOL_CALLS_UNAVAILABLE_DEGRADED` to a graceful render like `_sensitivity_refusal_completion`; `mailbot_api/router/router.py` :1945-1957 — make the refusal message conditional on degraded-vs-override. **Regression test owed:** an override-to-qwen tool turn (degraded off) → asserts a graceful 200 (not 502) + accurate wording. Candidate: fast-follow amendment to 10-5-5 (it's a defect IN this story's own new code) rather than Cluster G.

**Severity rationale:** HIGH — it's a user-facing failure in the exact feature this story shipped (the `/model` one-shot override, documented behavior), reproduced live on the first try, producing a 502 retry-storm that looks like an outage.

---

## FILED-ELSEWHERE — F-10-5-6-W1 (false-narration; belongs to Story 10-5-6, NOT a 10-5-5 defect)

**Live repro (Adam Discord, 2026-07-11 11:39):** "use qwen for next request" → Hermes replied *"Qwen is now armed... expires at 2026-07-11T09:12:33Z"* but the mailbot-api logs show **`set_model_oneshot` was never called** (only `pull_pending_notifications` in the window). The `09:12:33Z` expiry is **confabulated** — 27 min BEFORE the 09:39:04Z arming turn (a real arm at 09:39 would expire ~09:44). The next turn ("This is a test.") found an empty override slot → `policy:hermes_aux:default` → haiku (ledger `id=14669`/`14670`, both haiku). **Non-deterministic:** the identical phrase DID dispatch `set_model_oneshot` at 11:07 earlier (`reason=slash_command:one_shot:adam`), but only narrated at 11:39 — textbook F-10-5-1/F-10-5-10 persona-self-narration.

**Root cause is Hermes-side (persona narrating a control action without issuing the verb), NOT mailbot_api.** `router/oneshot.py` TTL + eviction logic is correct (TTL 300s, `expires_at = now+300s`, evict-on-read). **This is not a 10-5-5 defect** — it's the exact false-narration class **Story 10-5-6** exists to close (deterministic recognized-phrase dispatch for control verbs). Filed to 10-5-6 (sprint-status row + this note), Adam-decided 2026-07-11 "file to 10-5-6, sign off 10-5-5". Notably, 10-5-5's own surface was TRUTHFUL throughout: haiku served the turn and the footer said haiku (A1 `(Anthropic API)` marker correct); month `$26.53` DB-authoritative (A3 correct); W2 graceful-refusal never needed to fire because the request never reached qwen. Recommend 10-5-6 add "use qwen / model-override" to its recognized-phrase control-verb set.

---

## EXECUTED RESULTS (2026-07-11, orchestrator-delegated)

### AC-1 live — July re-derive + degraded — **PASS** ($0, production DB `/data/mailbot.db`)

- **Pre-state** (`mailbot status`): `month: $70.9478 / $30.00 cap (236.5%)`, `degraded mode: no`. Direct SUM over `[2026-07-01, 2026-08-01)` = **$70.9478 across 3332 rows** (matches).
- **Re-derive** (`rederive_month_cost(db_path='/data/mailbot.db', month='2026-07')`, current-month path → windowed re-seed + clear-eval): rows_scanned 3332, rows_updated 3332, **old_total $70.9478 → new_total $26.5075**, guard_counter re-seeded to $26.5075, degraded_was/now = False/False (no spurious flip).
- **Post-state persisted:** direct SUM = **$26.5075** (persisted to the ledger). `mailbot status` (running API, reads DB-authoritative) now: **`month: $26.5075 / $30.00 cap (88.4%)`, degraded: no**. Idempotent: a second re-derive returned identical $26.5075 (0 drift).
- **Restart survival:** mailbot-api restarted → booted clean (no errors/tracebacks) → guard `initialize()` seeded to **$26.5116** (corrected ledger + a few cents fresh spend). Confirms the fix survives a real process restart.
- **Verdict: PASS** — F-10-3-1/R4 discharged live end-to-end. $70.95/236.5% → $26.51/88.4%, honest and under cap.

### AC-3 live — per-answer footer — **PASS WITH FINDINGS** (mechanism $0-verified; real-spend render is Adam's)

- **Free/local render — PASS (live HTTP):** drove a qwen answer through the live `/v1/chat/completions` (caller_origin `story-10-5-5-footer-verify`, $0). Returned content:
  ```
  Hello there.

  🤖 qwen (local, free)
  ```
  Footer mechanism renders end-to-end through the real endpoint; free branch exact per spec (no dollar noise). usage: 43 in / 4 out.
- **Paid format — verified via the live helper ($0):** `build_answer_footer(...)` in-container with the real month counter renders:
  `🤖 haiku · this reply: $0.0031 (1240 in / 380 out) · July: $Y of $30.00`
  `🤖 opus · this reply: $0.0110 (1133 in / 212 out) · July: $Y of $30.00`
  — exact AC-3 format, exact dollar figure, credit dropped.
- **FINDING F-10-5-5-W1 (MEDIUM) — FIXED 2026-07-11 (amendment A3).** The footer's month-to-date read the in-memory `guard.this_month_spend_usd` mirror, not the DB-authoritative aggregate. Verified live: in a fresh process the footer source read **$0.00** while `_read_budget`'s DB `month_usd` read **$26.5116**; the mirror only reflects the current process's own `add_spend` calls (blind to worker spend, stale until `initialize()`). Same per-process-in-memory-mirror class Cluster A (10-5-1) fixed for the pause/degraded FLAGS. **FIX:** new `main.py::_db_month_to_date_usd(db_path)` reads `ROUTER_CALLS_TOTALS_SINCE` from month-start (the SAME source `status._read_budget` uses); the async handler computes it once per response and threads it into all three footer render sites (`_answer_footer_for_result` now takes `month_spend_usd`; both tool builders take it as a param). Fail-safe: read error → 0.0 (footer still renders). **Live-verified post-restart:** footer month `July: $26.52` == `mailbot status` month `$26.5224` (both DB-authoritative, agree). New regression test `test_footer_month_to_date_is_db_authoritative_not_guard_mirror` (seeds a $12.34 prior-month row → asserts footer month reflects it, not $0 — also guards the silent-$0 missing-import regression caught during the fix). Per-reply cost (from `result.cost_usd`) was already correct — only the month line changed.
- **Remaining Adam-hands-on half:** drive ONE real PAID answer through Discord (real Opus/Haiku spend) to see the paid footer on a genuine turn, and read the Anthropic **Console** pre/post for the authoritative spend delta ("Console-manual" — Admin `cost_report` unreachable on this org). The orchestrator cannot spend real budget or read the Console.

### Console readings (Adam to fill)

- Console month-to-date (pre-walk): `$______` — Console-manual — Adam
- Console month-to-date (post-walk): `$______` — Console-manual — Adam
- Delta (real paid spend this walk): `$______` — Console-manual — Adam

*(Note: the orchestrator's live walk incurred $0 — the only paid answer is Adam's remaining half.)*

---

## Original Task-6 template (for the Adam-hands-on remaining half)

Spend truth for this walk is **Console-manual** per durable memory `feedback_anthropic_spend_source_of_truth.md`: the Admin `cost_report` API is structurally unreachable on Adam's solo org, so Adam reads the Anthropic Console cost page pre- and post-walk and records both readings + the delta labeled "Console-manual." Never report a local estimator figure as absolute spend.

---

## Pre-walk Console reading

- Console month-to-date (pre-walk): `$______` — read <YYYY-MM-DD HH:MM> — "Console-manual"

## AC-1 live — July re-derive + degraded clear ($0, pure DB UPDATE)

**Command:** `mailbot rederive-cost` (current month) OR `mailbot rederive-cost --month 2026-07` (explicit).

- [ ] Pre-state captured: `mailbot status` before → month `$____ / $30 cap (___%)`, degraded mode: `___`.
- [ ] Re-derive ran clean (no crash), reported: rows_scanned `___`, rows_updated `___`, old_total `$____`, new_total `$____`.
- [ ] Post-state: `mailbot status` after → month `$____ / $30 cap` (expect ~$26 honest), degraded mode: `no`.
- [ ] Verdict: **PASS / FAIL** — <one line>. Adam sign: ______

*Note: if degraded had already self-cleared at a prior boot (10-5-2 rebuild logged `degraded false`), the re-derive still corrects the inflated July ledger — record the before/after month totals as the evidence even if degraded was already inactive.*

## AC-3 live — per-answer cost/model footer (small real Opus/Anthropic spend)

**Setup:** live Docker stack up, `mailbot-api` restarted to load this code, real Discord.

- [ ] **Paid answer** (drive a real chat turn that routes to Opus/Haiku): footer rendered in Discord →
  `🤖 ______ · this reply: $______ (____ in / ____ out) · July: $______ of $30.00`
  — exact dollar figure present (not withheld), tokens match the vendor `usage` block.
- [ ] **Free answer** (a qwen-served turn): footer rendered → `🤖 qwen (local, free)` (no dollar noise).
- [ ] (optional) tool-only response preserves `content: null` (no synthetic footer prose) — if exercised.
- [ ] Verdict: **PASS / FAIL** — <one line>. Adam sign: ______

## Post-walk Console reading

- Console month-to-date (post-walk): `$______` — read <YYYY-MM-DD HH:MM> — "Console-manual"
- **Delta (this walk's real spend):** `$______` — "Console-manual"

---

## AC verdict summary (Adam signs at Phase 3.5)

| AC | Clause | Verdict | Adam sign |
| --- | --- | --- | --- |
| AC-1 | July re-derive + degraded clear (live prod DB) | ___ | ___ |
| AC-2 | qwen tool-call typed refusal | code-L3 (autonomous, no live clause) | ___ |
| AC-3 | per-answer footer (live paid + free render) | ___ | ___ |
| AC-4 | MANDATORY-CR reviewer≠dev | PASS (sonnet-5 ≠ opus-4-8, 5/5 applied) | ___ |

Findings discovered during the walk (if any) are FILED per N.5 policy, not silently absorbed.
