---
baseline_commit: 42bfdbd3b5b42a5a1f96b6e6a0d8dd60133453e5
---

# Story 10.7.7: Stop the `find_emails` runaway loop — give "unread" a truthful backing signal + guard turn-termination so a local turn fails closed at $0

Status: review

## Story

**As** the MailBot operator (Adam) relying on the $0 local qwen lane to actually answer "find my unread emails" on Discord,
**I want** `find_emails` to (a) have a truthful `unread`/`is_read` signal so qwen's correct intent lands on a query that can be satisfied, and (b) be protected by a turn-termination / loop guard so a local turn that keeps re-invoking a tool fails closed at $0 instead of looping for 26 minutes, escalating to the paid lane, and 502-ing,
**so that** the clause-3 walk produces a real, usable unread-emails reply at $0 — discharging Epic 10.6 clause 3b (the founding cost thesis's final gate) that Story 10.7.6 left REACHED-but-NOT-USABLE.

## Context & boundary honesty (read before implementing)

This is the **clause-3 sequel** to Story 10.7.6. 10.7.6 fixed tool SELECTION (dropped the `memory` attractor → qwen reaches `find_emails`, `memory` scored 0 picks vs 9/11). Its 2026-07-18 live walk then FAILED one layer deeper (`F-10-7-6-R2`, promoted to BLOCKING): the turn ran away.

**What the failed 10.7.6 walk established (the evidence this story acts on).** Adam sent "find my unread emails" on real Discord (11:49→12:15 UTC). `router_calls` 15230–15295 (66 rows, 26 min):
- `find_emails` invoked **~60 times**, all with **empty `input:{}`**, `outcome=ok` on each individual call.
- Discord showed `mcp_mailbot_api_find_emails ×60` + `Working — 24 min — iteration 55/90`. **No unread-emails reply ever rendered.**
- The agent loop then **escalated OFF qwen to `claude-haiku-4-5`** (rows 15293–15295, `outcome=failed`) — the paid lane — which hit **`HTTP 502: rate limit breached: lane:interactive`** (`limits.py:114`, 60/hr).

**Two distinct root causes (both grep-confirmed in code — the story fixes BOTH):**

1. **No truthful `unread` signal (the WHY of the loop).** `FindEmailsFilter` (`mailbot_api/verbs/schemas.py:96-117`) has all-optional fields and **no `unread_only`** — the schema comment (:99-100) states `emails.is_read is not captured today`. There is **no `is_read` column on the `emails` table** (grep: `is_read` appears ONLY as the `mark_read`/`mark_unread` ACTION verbs in migrations `015`/`016`, never as a readable column). So "find my **unread** emails" has no backing query. qwen calls `find_emails({})` → gets all-recent-emails (or an unsatisfying result), can't reconcile it with "unread", and re-issues the call expecting a different outcome. Empty `{}` is a *valid* filter (returns everything up to `limit=25`), so the call never errors — it just never satisfies the intent, which is the loop's fuel.

2. **No turn-termination / fail-closed guard (the runaway + cost-thesis breach).** The turn-level re-invocation loop is owned by **Hermes's agent harness** (`iteration N/90`), NOT the mailbot-api router (whose escalation chain is separately capped at 1 hop per row, `router.py:1208`). Nothing on the mailbot side detects "same tool + same args re-invoked N times in one turn" and short-circuits. Worse, when the local loop exhausts, it **escalates to the PAID lane** — the exact outcome `project_local_model_is_safety_net` says must not happen (a runaway LOCAL loop should fail closed at $0, not spill to paid).

**What this story CAN do (achievable, in-repo scope):**
- Add a truthful `unread` capability to `find_emails` — either a real `is_read` column populated from Graph at sync time, OR (if that is too large) an explicit, honest "unread is not supported; here is what I CAN filter" contract so the model gets a terminating answer instead of looping. (Task 1 decides which, measure-first.)
- Add a mailbot-api-side **repeat-invocation / turn-termination guard**: detect the same-verb-same-args re-invocation storm within a turn/session window and return a terminal result (or a structured "already answered / no-progress" signal) so the turn ends.
- Add a **fail-closed-at-$0 guard** so a runaway LOCAL-lane loop does NOT escalate to the paid lane (the escalation-on-loop-exhaustion is the cost-thesis breach).

**What this story CANNOT do (the honest boundary):**
- **It cannot fix Hermes's agent-loop cap directly** — the `iteration N/90` counter is Hermes-side (out-of-repo). This story guards the loop from the MAILBOT side (terminal results + fail-closed) so Hermes's loop has a reason to stop; a complementary Hermes-side loop/escalation-policy change may still be filed as a residual if the mailbot-side guard is insufficient at the walk.
- **It does not re-litigate SELECTION** — 10.7.6's memory-drop stands and is kept.
- **The done-gate is the live walk (AC-8), not the code diff** — same discipline as 10.7.6 (`feedback_live_walk_load_bearing_clause_early`). Read the returning DISCORD REPLY, not just `router_calls` rows (the durable lesson from 10.7.6's walk: an invocation row ≠ a usable turn).

## Acceptance Criteria

**AC-1 — The `unread` intent gets a real, truthful answer (path (a), Adam-decided 2026-07-18).** An `is_read` boolean is captured on the `emails` table (populated from the Microsoft Graph `isRead` property at sync time — the field exists upstream, it was simply never persisted locally), and `FindEmailsFilter` gains an `unread_only` field that filters on it. "Find my unread emails" returns the user's *genuinely unread* mail. The earlier fallback option (a terminal "unread unavailable" honest-contract) is REJECTED — Adam's decision: unread filtering is a baseline inbox capability, and deferring it just re-files this story later. Path (a) is the fix; there is no (b).

**AC-2 — Repeat-invocation guard: a same-verb/same-args storm within a turn terminates.** A mailbot-api-side guard detects the same tool invoked with equivalent args ≥ N times within a single turn/session window and returns a terminal result (or a structured `NO_PROGRESS`/`ALREADY_ANSWERED` signal the harness treats as final) instead of serving the (N+1)th identical call. N + the window are documented and drift-tested. The guard must NOT break legitimate distinct repeat calls (different args, or a genuine second user turn).

**AC-3 — Fail-closed at $0: a runaway LOCAL-lane loop does NOT escalate to the paid lane.** When the repeat-invocation guard (AC-2) fires on a LOCAL-model turn, the turn fails closed at $0 with a structured error — it MUST NOT escalate to `claude-haiku-4-5`/any paid model (the 10.7.6 walk's rows 15293–15295 breach). Preserves `project_local_model_is_safety_net`: local stays $0; irreversible or paid actions stay behind the existing gates. A legitimate single escalation on a NON-loop failure is unchanged.

**AC-4 — No selection regression.** `platform_toolsets.discord` still `[mailbot-api, cronjob, clarify]` (10.7.6's trim intact); qwen still reaches `find_emails` (not `memory`/`turn`). The offline drift gates from 10.7.6 still pass. This story adds a layer; it must not re-open selection.

**AC-5 — Offline tests for every code path.** New/changed behavior (schema field, guard, fail-closed branch, unread query) is covered by offline unit/integration tests (real SQLite where DB is touched; no Docker/Discord/Anthropic). If AC-1 path (a) adds a migration, it ships with a migration test + the `is_read` populate path is integration-tested against a real SQLite fixture.

**AC-6 — Cost-thesis + safety invariants re-verified.** Tests assert: (i) the guard-fired path emits $0 (no paid adapter call); (ii) sensitivity/authorization gates are untouched (the guard is a loop-terminator, not an auth bypass); (iii) `mint_sensitivity_token`/grant flows still gate writes.

**AC-7 — Clause-3 live re-walk PASSES (Adam-hands-on, L3, $0) — the done-gate.** A real Discord "find my unread emails" turn produces a **usable unread-emails reply rendered in Discord**, backed by `router_calls` with `model_chosen=qwen2.5:*` AND `tool_calls_summary` naming `find_emails`, **`tool_calls_count` bounded (no ~60× storm), NO escalation to a paid model, terminates in a sane wall-clock (not 26 min), no 502.** Verified by READING THE DISCORD REPLY (the 10.7.6 lesson), not router rows alone. This is the load-bearing clause-3 gate = Epic 10.6 clause 3b. NOT done until Adam signs. On FAIL: record the new dominant defect, re-open.

## Tasks / Subtasks

- [x] **Task 1 (AC-1): Scope the `is_read` capture from Graph.** Confirmed: the sync worker's `_upsert_message` (sync_worker.py:214-256) reads Graph fields via `message.get(...)`. Graph `isRead` was available in the payload but never read/persisted — the upsert passed only 10 columns, none of them a read flag. Landing point: right after `has_attachments` extraction (:220). No stripping upstream; the flag was simply dropped at the upsert. *(Recon for Task 2; path (a) pinned.)*

- [x] **Task 2 (AC-1): Implement `is_read` capture + `unread_only` filter.** Migration `029_emails_is_read.sql` adds `emails.is_read INTEGER` (NULL = unknown until next sync; NO backfill — honest posture, only 0/1 when Graph says so) + partial index `ix_emails_is_read`. `EMAIL_UPSERT` gains `is_read` col+param+ON CONFLICT update; sync worker populates from `message.get("isRead")` (True→1, False→0, absent→NULL). `FindEmailsFilter` gains `unread_only: bool | None`; `_build_where_and_params` appends `is_read = 0` (NULL excluded by SQLite 3-valued logic). Schema comment (schemas.py) updated. count_emails inherits the filter via the shared builder. Tests: `test_migration_029_emails_is_read.py` (8 tests: migration, idempotency, unread filter, sync-populate true/false/absent).

- [x] **Task 3 (AC-2): Implement the repeat-invocation guard.** Placed at the `dispatch_tool_call` router seam (NOT the MCP wrapper) — the transcript Hermes replays each turn IS the storm evidence, and it's the one seam that both terminates the loop AND governs escalation. `_max_repeated_tool_invocation(messages)` counts identical (name, normalized-args) assistant tool_calls; at ≥ `_REPEAT_INVOCATION_THRESHOLD` (4) the router returns a terminal `NO_PROGRESS` ToolCallResult with a calm rephrase message. Args normalized via sorted-key JSON so key-order variants collapse. Tests: storm terminates, below-threshold passes, distinct-args never trips.

- [x] **Task 4 (AC-3): Fail-closed-at-$0 on guard-fire.** The guard fires BEFORE any `call_with_tools` and `dispatch_tool_call` has no escalation chain, so a fired guard invokes NO adapter (local OR paid) → $0 by construction. Audit row `_emit_no_progress_audit_row` records `outcome=failed`, `cost_usd_estimated=0.0`. Test asserts zero qwen AND zero haiku invocations + `cost_usd == 0.0` on a local storm (and on a forced paid-model storm too — a runaway is a runaway). `_model_is_local` helper added for the log signal.

- [x] **Task 5 (AC-4): Selection-regression guard.** `test_hermes_config.py` (17 tests) green — no config change in this story; `platform_toolsets.discord` untouched, `memory` not re-added.

- [x] **Task 6 (AC-5, AC-6): Full offline test pass + invariant tests.** All new paths covered (19 new tests). $0-on-guard-fire asserted (adapter-invocation counts + cost). Boundary render (`_no_progress_completion`) returns graceful 200 not 502 (full-endpoint TestClient test). Guard is a loop-terminator carrying NO tool_calls — cannot bypass the sensitivity/grant pipeline (it fires with an error result, no action surface).

- [x] **Task 7 (all offline ACs): Run the 4 gates** — ruff clean, mypy clean (mailbot_api), boundary checker (ruff) clean, pytest full suite green (1977→1996, +19). Counts in Completion Notes.

- [x] **Task 8.5 (F-10-7-7-W1 walk-fix ATTEMPT + REVERT, 2026-07-20): the prompt lever does NOT move Qwen-3B argument-population.** Tried three model-facing edits (system instruction + field desc + tool desc, all directing "unread → find_emails(unread_only=true); no find_unread_emails tool" — the 10.7.5 SELECTION lever). **Walks #2 (11:13) + #3 (11:16, fresh Hermes) both FAILED identically.** Added a guard-fire arg-diagnostic (`repeated_args_redacted`) which gave the DECISIVE evidence: qwen calls `find_emails` with args **`{}`** — no filter, no unread_only — and the prompt edits moved it ZERO. Also proven: `find_emails` never reached the MCP verb (only `pull_pending_notifications` cron executes); the guard intercepts the repeated tool-call INTENTION at the dispatch seam. **Verdict (Adam 2026-07-20): F-10-7-7-W1 = Qwen-3B ARGUMENT-POPULATION CEILING** — prompting fixes SELECTION (10.7.5) but not ARGUMENT-population. The three prompt edits were **REVERTED** (dead bloat degrades a 3B/Q4 context per the 10.7.0 spike). KEPT: runaway guard, `unread_only` filter capability (migration 029), guard arg-diagnostic. In-repo structural fix blocked: chat tools are Hermes-supplied (`request.tools`), so a `find_unread_emails` alias needs `hermes-config` (out of repo). Escalated to the qwen-management epic. ruff+mypy clean; drift tests updated to pin the REVERTED state.

- [ ] **Task 8 (AC-7): Clause-3 live walk — 3 attempts 2026-07-20 → ❌ FAIL ×3 (Adam-signed). Story STAYS `review`; gap escalated to qwen-management epic (F-10-7-7-W1 ceiling).** Adam sent "find my unread emails" on real Discord (mailbot-api restarted w/ new code, migration 029 applied, `is_read` seeded via full re-sync → 86 live `is_read=0` rows). **What PASSED (this story's owned fix):** the runaway is DEAD — 6 calls / iteration 6/90 / ~2 min (vs 10.7.6's ~60 / 55-of-90 / 26 min); the guard fired at the 5th identical `find_emails({})` (`router_calls` id 15405, `outcome=failed`, $0) and the `NO_PROGRESS` message RENDERED in Discord; NO tool-loop escalation to paid, NO 502, NO rate-limit breach. **Why FAIL:** the usable UNREAD reply never rendered — qwen's 1st call was `find_unread_emails` (wrong-namespace mis-binding, **F-10-7-6-R1**, out-of-repo) then it fell to `find_emails({})` with an EMPTY filter — **it never set `unread_only:true`**, so AC-1's new capability was never exercised and the reply was the guard's stop-message, not an unread list. Also NOT strictly $0: one downstream `hermes_aux` TEXT call on haiku (id 15406, $0.000249) fired after the guard to compose the final message (NOT the 10.7.6 paid-loop-escalation breach, but not $0 either). **New dominant defect: F-10-7-7-W1** (qwen does not select `unread_only`; compounded by F-10-7-6-R1 find_unread_emails mis-binding) — the SELECTION layer, downstream of and distinct from the runaway this story fixed. Story STAYS `review`, re-opened. See `10-7-7-walk-evidence.md`. *(Adam-decided FAIL 2026-07-20; runaway-fix proven, usable-unread NOT rendered.)*

### Review Findings

<!-- Appended by bmad-code-review 2026-07-20 (reviewer: claude-opus-4-7, dev: claude-fable-5). 3 layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor. 4 patch, 0 decision-needed, 0 defer, 7 dismissed. Findings left as action items (story → in-progress). -->

- [x] [Review][Patch] **FIXED** — Repeat-invocation guard counted transcript-wide (lifetime), which could false-positive a legitimate call repeated across separate successful turns. **Reworked `_max_repeated_tool_invocation` to count the TRAILING CONSECUTIVE RUN** of the model's latest identical (name, normalized-args) choice: any distinct call breaks the run, so only a genuine unbroken within-turn storm trips it — no reliance on the out-of-repo "fresh transcript per turn" assumption. New tests: `test_max_repeated_run_resets_on_intervening_distinct_call`, `test_max_repeated_lifetime_repeats_across_turns_do_not_trip`. [mailbot_api/router/router.py:1889]
- [x] [Review][Patch] **FIXED** — AC-6(ii)/(iii) sensitivity non-bypass now TESTED: `test_sensitive_storm_terminates_without_auth_bypass` (a confidential-email storm returns NO_PROGRESS carrying NO tool_calls — no action surface, no id leak) + `test_non_storm_sensitive_call_still_hits_sensitivity_gate` (a below-threshold sensitive call still refused with SENSITIVITY_BLOCKS_API — the guard did not weaken the gate). [tests/integration/test_no_progress_boundary_and_invariants.py]
- [x] [Review][Patch] **FIXED** — `test_threshold_is_pinned_to_4` asserts `_REPEAT_INVOCATION_THRESHOLD == 4` as a literal drift-pin (mirrors test_budget.py's `== 0.20`). [tests/integration/test_dispatch_tool_call_no_progress_guard.py]
- [x] [Review][Patch] **FIXED** — the threshold comment + function docstring rewritten to describe the trailing-consecutive-run behavior accurately (the "current choice" wording now matches: the latest choice's unbroken tail). [mailbot_api/router/router.py:1865]

## Dev Notes

### Root-cause evidence (grep-confirmed, 2026-07-18)
- `mailbot_api/verbs/schemas.py:96-117` — `FindEmailsFilter`, all fields optional, **no `unread_only`**; comment :99-100 "emails.is_read is not captured today."
- `is_read` grep: appears ONLY in migrations `015_pending_actions.sql:27` / `016_action_grants.sql:19` as the `mark_read`/`mark_unread` ACTION-type enum — **no readable `is_read` column on `emails`**.
- `mailbot_api/mcp_server.py:270-286` — `find_emails` wrapper: takes `filter: FindEmailsFilter`, `limit=25`; empty `{}` is a valid filter (returns recent emails); per-call `_log_ok`/`_log_error`; `_session_id_from_ctx(ctx)` available (the guard seam).
- `mailbot_api/router/limits.py:113-119` — `lane:interactive` 60/hr breach → the exact 502 the walk hit.
- `mailbot_api/router/router.py:1208` — escalation capped at 1 hop PER ROW, but nothing caps per-TURN re-invocation; escalation-on-loop-exhaustion is the paid-lane spill.
- Turn-level `iteration N/90` loop cap is **Hermes-side (out-of-repo)** — this story guards from the mailbot side.

### Architecture compliance
- Verb changes go through `mailbot_api/verbs/` + the `mcp_server.py` wrapper (Rule-J projections, AR-PAT-4 boundary catch). Any DB write (path (a) migration + sync populate) uses `db/queries.py` single-writer + a new migration (next number after the highest existing).
- The guard is a loop-TERMINATOR, not an auth change — sensitivity (FR-2.3/2.5) + grant gates stay exactly as-is (AC-6).
- Fail-closed-at-$0 honors `project_local_model_is_safety_net` — local lane keeps acting under budget pressure gated by REVERSIBILITY; a loop-terminate is a read-side no-op, safe to fail closed.

### Files likely to touch
- `mailbot_api/verbs/schemas.py` — `FindEmailsFilter` (+ `unread_only` if path (a)).
- `mailbot_api/verbs/find_emails.py` — honor the new filter / terminal contract.
- `mailbot_api/db/migrations/0XX_emails_is_read.sql` (adds `emails.is_read`) + `mailbot_api/sync/` upsert populate from Graph `isRead`.
- `mailbot_api/mcp_server.py` — repeat-invocation guard at the verb-dispatch seam.
- `mailbot_api/router/router.py` — fail-closed-at-$0 on guard-fire (no escalation).
- `tests/unit/` + `tests/integration/` — guard, fail-closed, unread query, migration.
- `_bmad-output/implementation-artifacts/story-run-flags.md` — update F-10-7-6-R2 disposition after the walk.
- `_bmad-output/implementation-artifacts/10-7-7-walk-evidence.md` (new, at walk time).

### Testing requirements
- Offline unit/integration only for the diff (real SQLite where DB touched). Live proof is AC-7's walk.
- **MANDATORY-CR** reviewer ≠ dev (touches the router escalation seam + a new dispatch guard + possibly the schema/migration — load-bearing). The CR should specifically probe: does the guard fail closed at $0 (no paid call)? does it break legitimate repeat calls? is the unread path honest (no silent papering)?
- Read the Discord reply at the walk, not just `router_calls` (the 10.7.6 durable lesson, `project_clause3_walk_failed_runaway_loop`).

### Run-mode note
Tasks 1–7 are dev-story / autonomous-run compatible. **Task 8 (clause-3 walk) is Adam-hands-on and NOT autonomous compatible** — a dev agent HALTS and logs.

### References
- `_bmad-output/implementation-artifacts/10-7-6-walk-evidence.md` — the FAIL that spawned this story (66 rows, 26 min, ~60× loop, paid escalation, 502).
- `_bmad-output/implementation-artifacts/story-run-flags.md` § F-10-7-6-R2 (BLOCKING) + § Story 10-7-6 Manual Verification (FAIL).
- `mailbot_api/verbs/schemas.py:96-117`, `mailbot_api/mcp_server.py:270-286`, `mailbot_api/router/limits.py:113-119`, `mailbot_api/router/router.py:1208`, migrations `015`/`016`.
- Memory: `project_clause3_walk_failed_runaway_loop`, `project_local_model_is_safety_net`, `project_reached_not_equal_usable`, `feedback_live_walk_load_bearing_clause_early`, `project_qwen_cpu_toolcall_latency`, `feedback_reviewer_model_substitution`, `ops_msys_path_mangling_docker_exec`.

## Dev Agent Record

### Agent Model Used
claude-fable-5 (dev). MANDATORY-CR reviewer: claude-opus-4-7 (different model, per feedback_reviewer_model_substitution).

### Debug Log

- **Seam choice for the guard (AC-2/AC-3):** the story spec suggested the MCP `find_emails` wrapper (`mcp_server.py`, `_session_id_from_ctx`). On code-read that seam terminates a call but does NOT govern escalation and has no view of the model. The `dispatch_tool_call` router seam is strictly better: it already walks the request transcript (`_resolve_email_ids_from_messages`), has no escalation chain (so a terminal return is $0 by construction — 10.7.6's paid spill was Hermes-side, but MailBot's job is to stop FEEDING the loop), and knows the model. Placed the guard there, after model/reason resolution, before every gate + adapter call.
- **Storm detection = transcript-counting, not a stateful counter.** Hermes replays the whole growing transcript each turn, so N prior identical assistant tool_calls in `messages` = the model is on its (N+1)th no-op. Pure function `_max_repeated_tool_invocation` — no process-global state, no test-bleed, resettable-free.
- **Threshold = 4** (fires on the 5th identical call). Kills the observed 60× storm at ~1/12th of its length while a legitimate 2nd/3rd distinct call carries different args → different key → never trips.
- **Unread NULL posture (AC-1):** `is_read = 0` filter excludes NULL by SQLite 3-valued logic. Deliberately NO backfill of pre-029 rows — defaulting historical mail to "unread" would falsely surface long-read mail. NULL = unknown-until-next-sync, documented in the migration.
- **Drift gate caught the new enum:** `test_errors.py::test_error_code_has_exactly_16_members` failed on the added `NO_PROGRESS` code — the intended membership drift-gate. Updated expected set + renamed to `_17_members`.

### Completion Notes List

- **AC-1 (truthful unread signal):** migration `029_emails_is_read.sql` (+`is_read INTEGER`, +partial index `ix_emails_is_read`); `EMAIL_UPSERT` + sync worker populate from Graph `isRead`; `FindEmailsFilter.unread_only`; `find_emails`/`count_emails` honor `is_read = 0`. "Find my unread emails" now lands on a satisfiable query. 8 tests.
- **AC-2 (repeat-invocation guard):** `_max_repeated_tool_invocation` + `_REPEAT_INVOCATION_THRESHOLD=4` at the `dispatch_tool_call` seam → terminal `NO_PROGRESS`. Distinct calls + below-threshold repeats pass through. 7 tests (incl. 3 pure-helper).
- **AC-3 (fail-closed at $0):** guard fires before any adapter call; `dispatch_tool_call` has no escalation chain → zero adapter invocations (local AND paid), `cost_usd == 0.0`, audit row `outcome=failed cost=0.0`. Asserted on both a local storm and a forced-paid storm.
- **AC-4 (no selection regression):** no config change; `test_hermes_config.py` 17/17 green; `memory` not re-added.
- **AC-5/AC-6 (offline + invariants):** `_no_progress_completion` renders a graceful 200 (not 502) at the `/v1/chat/completions` boundary (full-endpoint TestClient test); guard carries NO tool_calls so it cannot bypass the sensitivity/grant pipeline. 4 tests.
- **AC-7 (clause-3 live walk): ❌ FAIL ×3 (2026-07-20, Adam-signed).** Walk #1: runaway fixed + guard rendered live, but qwen mis-bound to find_unread_emails then find_emails without unread_only. Walk-fix (3 prompt/description edits) applied + CR-clean → walks #2/#3 FAILED identically. **DECISIVE:** a guard arg-diagnostic showed qwen sends `find_emails({})` — empty args, unread_only NEVER set, prompt edits moved it ZERO. **F-10-7-7-W1 = Qwen-3B argument-population ceiling** (prompting fixes SELECTION not ARGUMENT-population). Prompt edits REVERTED (bloat degrades 3B); runaway guard + unread_only filter capability + arg-diagnostic KEPT. Structural fix (find_unread_emails alias) needs hermes-config (out of repo) → escalated to qwen-management epic. Story stays `review`; clause 3b stays OPEN.
- **Walk-fix MANDATORY-CR (reviewer opus-4-7 ≠ dev fable-5, 2026-07-20):** the walk-fix (before revert) was reviewed clean — 0 HIGH/MEDIUM, 1 LOW + 1 NIT, both applied — but the fix itself was then disproven by the live walk (the reviewer's probes couldn't catch that a 3B model would ignore an otherwise-well-formed directive; only the walk could). The revert supersedes it.
- **Gates:** ruff clean (full repo, incl. boundary rules), mypy clean (134 files), pytest **2002 passed** / 3 skipped / 3 deselected (**+25 net** vs 1977 baseline). baseline_commit 42bfdbd.
- **MANDATORY-CR (reviewer opus-4-7 ≠ dev fable-5):** converged in 1 round. 4 Patch findings, **4/4 applied (100%)**, 0 defer, 7 dismissed. Fixes: (1) guard reworked from transcript-wide lifetime count → **trailing-consecutive-run** count (prevents false NO_PROGRESS across separate successful turns — the load-bearing AC-2 correctness fix); (2) AC-6 sensitivity non-bypass now TESTED (confidential-storm terminates with no action surface + non-storm sensitive call still hits SENSITIVITY_BLOCKS_API); (3) threshold literal-pinned (`== 4`); (4) doc/code comment reconciled. +6 tests from the CR round.

### File List

- `mailbot_api/db/migrations/029_emails_is_read.sql` (new) — adds `emails.is_read` + partial index.
- `mailbot_api/db/queries.py` — `EMAIL_UPSERT` gains `is_read` column/param/ON-CONFLICT update.
- `mailbot_api/sync/sync_worker.py` — `_upsert_message` extracts + persists Graph `isRead`.
- `mailbot_api/verbs/schemas.py` — `FindEmailsFilter.unread_only` + updated schema-reality comment.
- `mailbot_api/verbs/find_emails.py` — `_build_where_and_params` honors `unread_only` (`is_read = 0`).
- `mailbot_api/router/errors.py` — new `ErrorCode.NO_PROGRESS`.
- `mailbot_api/router/router.py` — `_max_repeated_tool_invocation`, `_normalize_tool_args`, `_iter_assistant_tool_calls`, `_model_is_local`, `_REPEAT_INVOCATION_THRESHOLD`, `_emit_no_progress_audit_row`, guard block in `dispatch_tool_call`, `Final` import; **walk-fix: `_QWEN_TOOLCALL_SYSTEM_INSTRUCTION` gains the unread_only + no-find_unread_emails directives**.
- `mailbot_api/mcp_server.py` — **walk-fix: `find_emails` tool description gains the imperative unread_only clause + find_unread_emails neutralization**.
- `mailbot_api/main.py` — `_no_progress_completion` render helper + wire into the tools-dispatch branch.
- `tests/integration/test_migration_029_emails_is_read.py` (new) — AC-1, 8 tests.
- `tests/integration/test_dispatch_tool_call_no_progress_guard.py` (new) — AC-2/AC-3, 7 tests.
- `tests/integration/test_no_progress_boundary_and_invariants.py` (new) — AC-5/AC-6, 4 tests.
- `tests/unit/router/test_errors.py` — enum drift gate updated for `NO_PROGRESS` (16→17).
- `_bmad-output/implementation-artifacts/10-7-7-find-emails-turn-termination-and-unread-signal.md` — this story file.
- `_bmad-output/implementation-artifacts/10-7-7.pre-review.md` (new) — pre-review self-audit.

### Change Log
- 2026-07-20 — AC-1 through AC-6 implemented + tested (+19 tests, all gates green). AC-7 clause-3 live re-walk DEFERRED to Adam-hands-on (done-gate). Story → review pending MANDATORY-CR + Adam walk.

### Change Log
- 2026-07-18 — Story drafted (ready-for-dev) after Story 10.7.6's clause-3 walk FAILED with a runaway `find_emails` loop (F-10-7-6-R2). Fixes the two grep-confirmed root causes: (1) no truthful `unread`/`is_read` signal (the loop's fuel) and (2) no turn-termination / fail-closed-at-$0 guard (the runaway + paid-lane breach). Done-gate is the live Discord walk reading the actual reply. NOT autonomous compatible (Task 8 halts).
- 2026-07-18 (Adam decision) — AC-1 PINNED to path (a): capture real `is_read` from Graph + add `unread_only` filter. The honest-terminal-contract fallback (b) is REJECTED — unread filtering is a baseline inbox capability, deferring it just re-files this story. Adam also flagged that the missing `is_read` column is an architecture gap that should have been caught far sooner (the sync worker persisted sender/subject/date but dropped the read/unread flag Graph provides by default) — noted as a process finding for the Epic 10.7 retro (architect-agent schema-completeness review at ingest-design time).
