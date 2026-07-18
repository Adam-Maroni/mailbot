---
baseline_commit: TBD-at-dev-start
---

# Story 10.7.7: Stop the `find_emails` runaway loop — give "unread" a truthful backing signal + guard turn-termination so a local turn fails closed at $0

Status: ready-for-dev

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

- [ ] **Task 1 (AC-1): Scope the `is_read` capture from Graph.** Confirm the sync worker's delta payload carries the Graph `isRead` property (grep `mailbot_api/sync/`; Graph message resources expose `isRead` by default, so it should already be in the response — verify it's not being stripped). Note the exact field + where in the sync upsert path it lands. Record findings in Dev Notes. *(This is recon for Task 2, not a path-decision — path (a) is pinned.)*

- [ ] **Task 2 (AC-1): Implement `is_read` capture + `unread_only` filter (RED-first).** Migration adds `emails.is_read` (boolean/int, with a sensible default + backfill posture for existing rows — likely NULL/unknown until next sync, documented); sync worker upsert populates `is_read` from Graph `isRead`; `FindEmailsFilter` gains `unread_only: bool | None`; `find_emails` query honors it (`WHERE is_read = 0` when `unread_only`); update the schema comment (schemas.py:99-100) that currently says is_read is not captured. Tests: migration test, sync-populate integration test (real SQLite), unread-filter query test.

- [ ] **Task 3 (AC-2): Implement the repeat-invocation guard.** Locate the per-turn/session dispatch seam (`mcp_server.py` verb wrappers already have `_session_id_from_ctx` + per-call logging — the natural seam). Track (verb, normalized-args, session/turn) counts; at ≥ N identical calls return a terminal `NO_PROGRESS` result. Choose N + window (Dev Notes rationale; small enough to stop a 60× storm fast, large enough not to trip a legitimate 2nd call). RED-first; test the storm terminates and distinct calls pass through.

- [ ] **Task 4 (AC-3): Fail-closed-at-$0 on guard-fire.** Ensure the AC-2 guard path, when the turn is on a LOCAL model, returns the terminal error WITHOUT invoking `next_tier`/escalation (`router.py` escalation chain). Add a test asserting no paid adapter is called when the guard fires on a local turn. Cross-check `project_local_model_is_safety_net`: reversibility gates unchanged.

- [ ] **Task 5 (AC-4): Selection-regression guard.** Re-run 10.7.6's `test_hermes_config.py` drift gates; confirm green. Confirm no config change re-added `memory`. (No new config edit expected in this story.)

- [ ] **Task 6 (AC-5, AC-6): Full offline test pass + invariant tests.** All new paths covered; $0-on-guard-fire asserted; sensitivity/grant gates asserted untouched.

- [ ] **Task 7 (all offline ACs): Run the 4 gates** — ruff, mypy `--strict mailbot_api`, boundary checker (ruff), pytest full suite. Record counts.

- [ ] **Task 8 (AC-7): Clause-3 live re-walk (Adam-hands-on, HALT-and-hand-off).** After offline gates green + hermes restarted, Adam sends "find my unread emails" on real Discord. PASS = a **usable unread reply rendered in Discord** + bounded `find_emails` calls + `model_chosen=qwen2.5:*` + NO paid escalation + no 502 + sane wall-clock. **Read the Discord reply, not just router rows** (10.7.6 lesson). Record in `10-7-7-walk-evidence.md`. On FAIL: record new dominant defect, re-open (do NOT flip done). *(NOT autonomous-run compatible — dev agents HALT here and log.)*

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
_(to be filled by the dev agent)_

### Debug Log References
_(to be filled)_

### Completion Notes List
_(to be filled)_

### File List
_(to be filled)_

### Change Log
- 2026-07-18 — Story drafted (ready-for-dev) after Story 10.7.6's clause-3 walk FAILED with a runaway `find_emails` loop (F-10-7-6-R2). Fixes the two grep-confirmed root causes: (1) no truthful `unread`/`is_read` signal (the loop's fuel) and (2) no turn-termination / fail-closed-at-$0 guard (the runaway + paid-lane breach). Done-gate is the live Discord walk reading the actual reply. NOT autonomous compatible (Task 8 halts).
- 2026-07-18 (Adam decision) — AC-1 PINNED to path (a): capture real `is_read` from Graph + add `unread_only` filter. The honest-terminal-contract fallback (b) is REJECTED — unread filtering is a baseline inbox capability, deferring it just re-files this story. Adam also flagged that the missing `is_read` column is an architecture gap that should have been caught far sooner (the sync worker persisted sender/subject/date but dropped the read/unread flag Graph provides by default) — noted as a process finding for the Epic 10.7 retro (architect-agent schema-completeness review at ingest-design time).
