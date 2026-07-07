---
baseline_commit: 4f56908b95db669116aa5b429c2da9c34de70cdf
---

# Story 10.5.1: Safety / kill-switch coverage + the per-process-singleton bug class

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Adam,
I want `pause` to gate EVERY process that can touch the mailbox — including the worker-process drainer, not just the API process — and the underlying per-process in-memory-singleton pattern (PauseState + BudgetGuard degraded-flag) fixed so safety state is read from a cross-process source of truth, with resume-by-chat reachable while paused,
so that pause is a real kill-switch: when I pause, nothing writes no matter which process would have written, and I can turn it back on from the same Discord chat I paused it from.

## Context — why this story is HIGHEST priority (CRITICAL)

Epic 10's live walk (Story 10-1, §2.2) captured a **real Microsoft Graph mailbox write dispatched 259ms after `propose` while the system was paused** (finding **F4, CRITICAL**). Pause is not a kill-switch. The Epic 10 retro (§5.1) diagnosed the root as a **bug CLASS, not a single bug**: the per-process in-memory singleton — state seeded once at `initialize()` per process, so a safety verb only governs the process that ran it. **PauseState** (F4) and the **BudgetGuard degraded-flag** are two instances of the same root; this story fixes the class, not just PauseState.

Two companion findings ride on the same pause machinery and are in scope here:
- **F1 (HIGH)** — router pause blocks Hermes chat entirely (`hermes_aux` routes through the paused-gated router), so Discord entry and pre-drain inspection are mutually exclusive.
- **F-10-5-4 (HIGH)** — PAUSED chat deadlock: while paused, every chat dispatch 502s, so `resume` typed in chat can never execute; README:293's documented fix "`/resume` or `mailbot resume`" is half-false (only the CLI half works).
- **F3 (LOW)** — paused refusals leave no audit rows.

## Acceptance Criteria

**AC-1 — Pause gates the worker drainer (closes F4, CRITICAL).**
Given a queued Tier-1 move-family intent about to be drained, when the system is paused by the operator (CLI `mailbot pause` → `/admin/pause`, i.e. a pause originating in the API process), then the worker-process drainer refuses to dispatch the Graph write and no write leaves the process. Verified by a **live** `pause → propose/queue → wait ≥1 drainer tick → assert-not-applied` walk against the sacrificial folder (evidence in `10-5-1-walk-evidence.md`), NOT only unit tests. The 259ms-after-propose F4 scenario must be non-reproducible.

**AC-2 — The per-process-singleton read-staleness is fixed for BOTH instances (closes the CLASS).**
Given the pattern where `is_paused()` / `is_degraded()` return an in-memory mirror seeded once per process, when a decision that governs mailbox writes or dispatch is made, then that decision reads the cross-process source of truth (the `pause_state` / `degraded_mode_state` SQLite singleton rows) rather than a stale per-process bool. The fix is applied to **both** `PauseState` and the `BudgetGuard` degraded-flag — fixing PauseState alone and leaving BudgetGuard on the same landmine is a fail (it would re-file the same class under a new name). **Scope boundary:** the July cost re-derive and the estimator/counter-inflation truth (F-10-3-1/-2, retro R4/B2) are **Cluster E / story 10-5-5**, NOT this story. This story fixes the *cross-process read-staleness of the degraded flag*; it does NOT re-derive July spend or change pricing.

**AC-3 — Resume-by-chat is reachable while paused (closes F1 + F-10-5-4).**
Given the system is paused, when Adam types a resume request in Discord chat, then the interpretation dispatch is permitted to run far enough to reach the `resume_router` control path and the system resumes — pause silences ACTION-producing dispatches (propose/apply/write), it does not brick the conversational surface. Demonstrated by a live pause→resume-from-chat walk. The fix must NOT re-open F4 (a paused system must still refuse write/action tool-calls); the permitted surface while paused is the control/status allowlist only.

**AC-4 — Paused refusals are audited (closes F3, LOW).**
Given a dispatch or drain is refused because the system is paused, when the refusal happens, then an audit row is recorded (so a paused-window incident is reconstructable). This closes the "paused refusals leave no trail" gap.

**AC-5 — Regression tests that would have caught F4.**
Given the fix, when the test suite runs, then new tests assert the **cross-process** scenario directly: a pause written to the DB by "process A" (simulated by writing the row / a second PauseState instance) is observed by the drainer's gate WITHOUT that process having called `initialize()` — i.e. the drainer reads live DB state, not a stale in-memory bool. Plus: mid-tick pause still releases claimed rows; the in-worker OAuth auto-pause path (which currently works) is not regressed; resume-while-paused permits only the control surface.

**AC-6 — No regressions; gates green.**
`ruff check .` (line-length 120), `mypy --strict` (python 3.12), `scripts/check_boundaries.py`, and the full `pytest` suite stay green. The current baseline is **1708 passed + 2 skipped + 3 deselected**; net-new tests raise the passed count. No byte-changes to unrelated modules.

## Tasks / Subtasks

- [x] **Task 1 — Make the drainer's pause gate cross-process (AC-1, AC-4).** — drainer.py:488 tick-entry + :517 mid-tick now call `PauseState.is_paused_now(db_path)` (added, fail-closed, copies status.py:332 pattern); paused skips emit `pause_gate:refused` audit row via `record_router_call` (Rule C, no new raw SQL); OAuth path preserved (warm cache + `initialize()` untouched).
  - [x] Fail-closed DB read at tick entry via `is_paused_now`.
  - [x] Mid-tick re-check uses the same authoritative source (fresh read — must observe a pause arising during the tick).
  - [x] Paused-skip audit row via the Rule-C writer (boundaries green).
  - [x] OAuth auto-pause/resume path not broken (warm `is_paused()`/`initialize()` retained).

- [x] **Task 2 — Fix the BudgetGuard degraded-flag read-staleness (AC-2, the CLASS).** — `BudgetGuard.is_degraded_now(db_path)` added (fail-closed); both router DISPATCH gates (router.py:463 ask_router + the dispatch_tool_call gate) read it.
  - [x] Authoritative degraded read on the dispatch-governing sites. **Scope refinement:** the report-only consumers (`inspect_policy`/`cost_breakdown`/`reset_degraded_mode.previously`) were LEFT on in-memory `is_degraded()` — they govern no write and a fail-closed report read would falsely display "Active" on a transient DB error. See Dev Notes / Debug Log.
  - [x] STAYED IN SCOPE — no `add_spend` math / pricing / July re-derive touched (Cluster E handoff to 10-5-5).

- [x] **Task 3 — Make resume-by-chat reachable while paused (AC-3, closes F1 + F-10-5-4).**
  - [x] `dispatch_tool_call` gate conditional: filters `tools` to `_PAUSE_ALLOWED_TOOLS` while paused; `ask_router` gate permits `_PAUSE_ALLOWED_TASK_TYPES={"hermes_aux"}`, refuses the rest. Both audit refusals.
  - [x] `resume_router` verb + `pause.py` primitive unchanged.
  - [x] F4 containment preserved — write/action tools filtered out; `propose_action` still refused; drainer gate (Task 1) still blocks. Verified by tests.

- [x] **Task 4 — Regression tests (AC-5).**
  - [x] `test_pause.py` cross-process staleness (`is_paused_now` sees bare-DB pause without `initialize()`) + live-resume + fail-closed.
  - [x] `test_drainer.py` DB-level pause → 0 dispatches (no worker init) + post-resume drain + mid-tick release + audit row.
  - [x] `test_budget.py` degraded cross-process + live-exit + fail-closed.
  - [x] resume-while-paused dispatch tests (`test_dispatch_tool_call_pause_allowlist.py`): control allowlist permitted, write tool filtered, refusal audited.
  - [x] `test_worker_drainer_wiring.py` still passes + NEW two-instance assertion (API-instance DB pause stops worker-instance real drainer).

- [ ] **Task 5 — Live validation walk (AC-1, AC-3) + gates (AC-6).** — **HALT (Adam-hands-on live walk).** Tasks 1–4 dev-complete; the live pause→propose→drain + pause→resume-from-Discord walk is deferred per the run-mode binding. Logged to `epic-10-5-run-flags.md`.
  - [ ] **DEFERRED (Adam-hands-on):** live pause→propose→drain-tick→assert-not-applied walk against `MailBot-UAT-10-1` + live pause→resume-from-Discord-chat; evidence in `10-5-1-walk-evidence.md`.
  - [x] Gates (AC-6): `ruff check` (mailbot_api/tests/scripts clean) + `mypy --strict` (129 files) + `check_boundaries.py` + `pytest` all green at **1726 passed** (+18 net vs 1708 baseline) + 2 skipped + 3 deselected.

### Phase 3.5 — Adam-signed AC verdicts (2026-07-07)

Signed by Adam after the live co-walk ("Sign it done"). Basis:
`10-5-1-walk-evidence.md` §A (DB-real surrogate 9/9) + §B (live Graph + Discord).

| AC | Verdict | Basis |
| --- | --- | --- |
| AC-1 (F4 CRITICAL) | **PASS** | Live: paused move held (drainer skip logs + audit rows), Adam-confirmed in Outlook the email did NOT move; resume released it (action 38 applied), Adam-confirmed it then moved. 259ms-after-propose scenario non-reproducible. |
| AC-2 (the CLASS) | **PASS** | Cross-process authoritative reads live at drainer + all 3 dispatch gates (ask_router, dispatch_tool_call, dispatch_embedding); BudgetGuard twin proven (§A). |
| AC-3 (F1 chat reachable) | **PASS** | 200 while paused (was 502 deadlock). |
| AC-3 (F-10-5-4 resume-from-chat) | **PASS (router scope)** | Router allowlist fix live-verified (allowed_count 0→12, resume_router offered, agent invoked it). Resume completion blocked ONLY by the external Hermes MCP-transport defect **F-10-5-1-W2** (FILED, out of scope; `resume_router` verb itself proven working via direct call). Adam signed accepting the router contract as fully satisfied and W2 as a separate Hermes-transport story. |
| AC-4 (audit) | **PASS** | `pause_gate:refused` rows live across drainer skips + would-be refusals. |
| AC-5 (regression) | **PASS** | Cross-process F4 regression at 3 layers + degraded twin + namespaced-allowlist test. |
| AC-6 (gates) | **PASS** | ruff/mypy-strict/boundaries clean; suite 1728 passed (+20 net vs 1708). |

Walk-discovered findings: **F-10-5-1-W1 (HIGH)** — namespaced-allowlist gap —
FIXED in-session (in scope). **F-10-5-1-W2 (HIGH)** — Hermes MCP session-drop —
FILED per N.5 for a Hermes-transport story (out of scope). See run-flags.

### Review Findings

Reviewer: claude-sonnet-5 (reviewer ≠ dev per §5.12 MANDATORY-CR). Layers run: Blind Hunter (diff-only), Edge Case Hunter (diff + full project read access), Acceptance Auditor (diff + story + pre-review self-audit). Mode: full (spec present).

- [x] [Review][Decision] **APPLIED (fix now).** `dispatch_embedding` (router.py) migrated to the authoritative cross-process `is_paused_now(db_path)` read + a `pause_gate:refused` audit row — the third pause-enforcement site now matches `ask_router` + `dispatch_tool_call`. Embeddings are local-only/$0 with no resume-path concern, so it stays an UNCONDITIONAL refuse (no interpretation/allowlist branch) — just made cross-process-honest + audited. Disclosure corrected: File List / Debug Log now name router.py's dispatch_embedding gate; pre-review §5.4 "all updated" is now literally true. New regression: `test_embedding_e2e.py::test_dispatch_embedding_paused_refuses_cross_process` (bare-DB pause, no initialize → refused + audit row).

- [x] [Review][Patch] **APPLIED.** `reason_now()` no longer swallows exceptions silently — it now delegates to the new `snapshot_now()` which logs `_log.exception(... router.pause.read_failed)` on the failure path (same pattern as `is_paused_now`/`is_degraded_now`). An operator investigating a paused-window incident now gets a trace.

- [x] [Review][Patch] **APPLIED.** `test_ask_router_paused_returns_provider_error` now asserts the FULL zero-cost refusal row shape (`outcome="failed"`, `cost_usd_estimated == 0.0`, `tokens_in/out == 0`, `cached_tokens_in == 0`) — the "can't pollute spend aggregation" claim is now test-verified, not dev-reasoned.

- [x] [Review][Patch] **APPLIED.** Combined `is_paused_now`+`reason_now` into a single-read `snapshot_now(db_path) -> tuple[bool, str|None]`; `is_paused_now`/`reason_now` are now thin convenience wrappers over it. The drainer (tick-entry + mid-tick) calls `snapshot_now` once, so (paused, reason) come from ONE `fetchone` — closes the CR-13 non-atomic window (no more `paused=True` with `reason=None` straddling a resume).

- [x] [Review][Defer] `ask_router`'s permitted-interpretation branch (router.py:349-375) falls through to full dispatch with no second pause re-check immediately before the real adapter call; safety currently rests entirely on `hermes_aux` being documented as text-only/non-action-producing, not on a structural gate — deferred, defense-in-depth architectural concern, not a demonstrated reachable bug in this diff.
- [x] [Review][Defer] `_PAUSE_ALLOWED_TASK_TYPES` (router.py:281) and `_PAUSE_ALLOWED_TOOLS` (router.py:418-435) are two independently maintained allowlists with no shared invariant or test tying them together — deferred, maintainability/DRY concern, no demonstrated bug today.
- [x] [Review][Defer] `dispatch_tool_call`'s tool-surface filter (router.py:480-508) is computed once at gate-check time with no re-check immediately before the adapter dispatch later in the same function — deferred, same class of TOCTOU concern as the `ask_router` branch above, narrow window, no `await` yielding control between filter and use beyond further gate logic.
- [x] [Review][Defer] `is_paused_now` / `is_degraded_now` (pause.py:240, budget.py:204) use a broad `except Exception` that would also swallow programming/schema bugs under the same fail-closed path as genuine DB-connectivity failures — deferred, this is the documented deliberate fail-closed safety design for a CRITICAL kill-switch; narrowing the catch is a legitimate hardening idea but changes the safety contract's conservatism and needs a human call, not an unambiguous patch.
- [x] [Review][Defer] `_emit_pause_skip_audit_row` (drainer.py:40-66) and `_emit_pause_refusal_audit_row` (router.py:284-318) are near-duplicate helpers (same shape, same reason code, same zero-cost fields) built independently in two modules — deferred, cosmetic DRY/simplification opportunity, no correctness impact.
- [x] [Review][Defer] `_tool_name()`'s dict-shape fallback (router.py:438-455) validates only `function.name`, not the rest of the tool schema — a malformed-but-named dict could still pass the allowlist check — deferred, the fail-safe direction is already correct (unknown/malformed → filtered OUT), and reaching this requires a synthetic malformed-dict-with-valid-control-verb-name shape not evidenced as reachable in this diff.
- [x] [Review][Defer] Drainer mid-tick loop (drainer.py:582) calls `is_paused_now` once per claimed row with no circuit breaker; a transient DB outage during a large batch would produce one `fetchone` + one audit-row write per remaining row — deferred, pre-existing-class DB-under-load concern at current batch sizes (25), already acknowledged as negligible in the pre-review self-audit (§3, LOW).

## Dev Notes

### The bug, in one paragraph (read this first)
`PauseState` ([pause.py:21-104](mailbot_api/router/pause.py)) stores `_paused` as an **in-memory instance attribute** on a **module-level singleton** `_PAUSE_STATE` (line 93). `initialize(db_path)` (line 26) reads the `pause_state` DB row ONCE at process startup into `self._paused`. `is_paused()` (line 33) returns that in-memory bool and **never re-reads the DB**. There are **three processes**: (1) the short-lived **CLI** (`scripts/mailbot.py`) which does NOT touch PauseState — it POSTs `/admin/pause` over HTTP; (2) the **API/uvicorn** process (`main.py`) whose lifespan calls `initialize()` at [main.py:204](mailbot_api/main.py#L204) and whose `/admin/pause` flips ONLY its own `_PAUSE_STATE`; (3) the **worker** process (`worker.py`, `asyncio.run(_worker_main)` at [worker.py:469](mailbot_api/worker.py#L469)) which runs the drainer and binds the REAL `OutlookGraphWriteAdapter` ([worker.py:305](mailbot_api/worker.py#L305)). When the CLI pauses, only the API process's bool flips; the worker's `_PAUSE_STATE` was seeded at ITS boot and never re-reads the DB, so `is_paused()` returns stale `False` and the drainer dispatches the Graph write. **The `pause_state` DB row (migration 010) is already the cross-process source of truth — it's just never read at check time.** That is the entire bug.

### The fix locus is small and precise
The drainer **already has a pause gate** (Story 6-15) at [drainer.py:488-497](mailbot_api/actions/drainer.py#L488) (tick-entry) and [drainer.py:517-528](mailbot_api/actions/drainer.py#L517) (mid-tick). The gate is correct in intent — it even documents "the drainer talks to Graph directly and would otherwise keep burning budget" — but it reads `pause_state.is_paused()` (stale per-process memory). **Make it read the DB row.** Tightest fix per the code map: a fail-closed `PAUSE_STATE_SELECT` read at tick entry ([drainer.py:488](mailbot_api/actions/drainer.py#L488)). The exact live-read pattern already exists to copy: [status.py:332](mailbot_api/observability/status.py#L332) does `connection.fetchone(db_path, queries.PAUSE_STATE_SELECT, ())` for the status board. Do the same in the drainer (or via a new `PauseState.is_paused_now(db_path)` helper so all authoritative consumers share one reader).

### The BudgetGuard twin (AC-2) — same shape, strictly worse
`BudgetGuard` ([budget.py:64-173](mailbot_api/router/budget.py)) is the identical singleton pattern: `_GUARD = BudgetGuard()` (line 165), `is_degraded()` (line 96) returns in-memory `self._degraded_mode_active`, seeded once from `DEGRADED_MODE_SELECT` at `initialize()`, and the `degraded_mode_state` singleton row (migration 008) is the cross-process truth that isn't read at decision time. Seeded at the same two sites as pause ([main.py:193](mailbot_api/main.py#L193), [pipeline.py:745](mailbot_api/ingest/pipeline.py#L745)). **This story fixes the degraded-flag READ** to be cross-process authoritative — same technique as pause. 

**Scope fence (critical — do not cross):** BudgetGuard is worse than pause because its *spend counters* (`today_spend_usd`, `this_month_spend_usd`) are mutated in-memory on every call (`add_spend`, [budget.py:99-131](mailbot_api/router/budget.py#L99)) and never reconciled against the DB — that drift is what trips the $30 cap on phantom spend and stuck degraded mode 07-03→07-06 (~$70 estimator vs ~$27 Console). **That counter-inflation + the July re-derive + pricing truth is Cluster E, story 10-5-5 (retro R4/B2/B8) — OUT OF SCOPE HERE.** This story does the structural read-staleness fix for the degraded *flag*; it does not touch `add_spend` math, `pricing.py`, or re-aggregation. If you find the flag read can't be made honest without re-aggregation, STOP and note it as a 10-5-5 handoff — do not absorb Cluster E.

### The resume-deadlock (AC-3) — a different seam, do not conflate with the write fix
Pause is enforced at the **router-dispatch level** at three sites: `ask_router` [router.py:284](mailbot_api/router/router.py#L284), `dispatch_tool_call` [router.py:1497](mailbot_api/router/router.py#L1497) (the one live chat uses — Hermes sends `tools=[...]`), `dispatch_embedding` [router.py:1121](mailbot_api/router/router.py#L1121). The gate is content-blind: it 502s ALL LLM dispatch, including the chat-interpretation turn (`hermes_aux`). So to resume from chat, the agent must be interpreted, but interpretation is a dispatch, which is refused → deadlock (F-10-5-4). Chat ingress is `POST /v1/chat/completions` ([main.py:509](mailbot_api/main.py#L509)); the 502 translation with `{'error': {'type': 'router_error', 'message': 'router paused'}}` is at [main.py:617-627](mailbot_api/main.py#L617). `resume_router` ([router_control.py:86](mailbot_api/verbs/router_control.py#L86)) has NO gate; `/admin/resume` ([main.py:944](mailbot_api/main.py#L944)) already resumes while paused with no gate — proving the resume primitive is safe. **The fix belongs at the gate blocks** ([router.py:1497](mailbot_api/router/router.py#L1497) + mirror at :284): make them conditional — while paused, permit the interpretation turn but restrict `tools` to a control/status allowlist and refuse write/action tool-calls with `router paused`.

**⚠️ The trap the finding warns about:** do NOT "fix" the deadlock by simply removing the router pause gate. That gate is what stops the LLM from being *driven to propose/apply actions* while paused. Removing it re-opens the F4 class from the other direction. The write-suppression (Task 1 drainer gate + refusing action tool-calls in Task 3) and the interpretation-permission must both hold: **pause suppresses ACTIONS, permits the resume CONTROL path.**

### Read these files before editing (current state → what changes → what to preserve)
- [mailbot_api/router/pause.py](mailbot_api/router/pause.py) — the singleton. Preserve `initialize()`/`is_paused()` as warm cache + the OAuth `try_pause_if_unpaused`/`try_resume_if_reason` atomicity comments (Story 6-15 CR-1/CR-10); ADD an authoritative DB reader. Keep `reset_for_test()`.
- [mailbot_api/actions/drainer.py](mailbot_api/actions/drainer.py) — `run_tick` gates at :488/:517; dispatch at :658 (`adapter.apply(row)`); 2s loop at :686. Preserve the claim/release state machine and mid-tick release semantics.
- [mailbot_api/router/router.py](mailbot_api/router/router.py) — 4 pause gates; degraded-mode demotion at :388/:1591; the per-call refusal at :707/:1881 (untouched — stateless). Change only the two chat gates (:284, :1497) for AC-3.
- [mailbot_api/router/budget.py](mailbot_api/router/budget.py) — `is_degraded()` :96 (change the READ); `add_spend` :99 (DO NOT TOUCH — Cluster E).
- [mailbot_api/worker.py](mailbot_api/worker.py) — worker entry :254; binds real adapter :305; drainer task :409. The worker never calls `get_pause_state().initialize()` today; a per-tick DB read in the drainer is preferable to adding a worker-side refresh loop (tighter — no staleness window).
- [mailbot_api/observability/status.py](mailbot_api/observability/status.py) — :320-332 is the live DB-read pattern to copy.

### Testing standards (match existing conventions)
- Framework: `pytest` + `pytest-asyncio` (async test funcs, no explicit decorator needed — see existing files). Real SQLite via `apply_pending_migrations(str(tmp_path / "x.db"))`.
- Singleton hygiene: autouse fixtures reset the singletons — `_reset_pause_state_for_test()` ([pause.py:100](mailbot_api/router/pause.py#L100)) and `_reset_guard_for_test()` ([budget.py:172](mailbot_api/router/budget.py#L172)). Follow the `@pytest.fixture(autouse=True)` reset pattern in [test_pause.py:20-24](tests/unit/router/test_pause.py#L20).
- The cross-process test is the point: simulate two instances / a bare DB write and prove the authoritative reader sees it WITHOUT `initialize()` on the reader — that's the regression that would have caught F4. `test_pause_persists_across_initialize` (existing, :45) only covers restart-reseed; the new test must cover LIVE cross-process.
- Boundaries: any new DB write goes through the Rule-C audit writer (`observability/audit.py`); raw SQL literals outside the allowlist fail `scripts/check_boundaries.py`. Reads via `mailbot_api.db.connection.fetchone` + a `queries.py` constant.
- Gates: `ruff` line-length 120; `mypy` strict, python 3.12. Baseline suite: 1708 passed + 2 skipped + 3 deselected.

### Run-mode binding
Tasks 1–4 (code + unit/integration tests) are **dev-story / autonomous-story-run compatible**. **Task 5's live walk is Adam-hands-on** — it drives the real Outlook mailbox (move against the `MailBot-UAT-10-1` sacrificial folder) and real Discord (resume-from-chat), following the 9.5.x / 10-1 hands-on binding-marker pattern. A dev agent must HALT before Task 5's live steps and log to a run-flags file rather than executing them autonomously. $0 expected (local stack, move verbs are $0; no Opus).

### CR cadence
This story touches the actions/drainer/router safety seam and the authorization-adjacent kill-switch — **criterion 6 (load-bearing) fires → MANDATORY-CR per §5.12, full scope, reviewer model ≠ dev model** (carry the A5/B4 reviewer-substitution rule from the Epic 9.5 / Epic 10 retros).

### Project Structure Notes
- Package root is `mailbot_api/` at the repo root (not `src/`). Story keys use hyphen notation; this file is `10-5-1-...md`.
- No new modules expected — edits land in existing `router/pause.py`, `router/budget.py`, `actions/drainer.py`, `router/router.py`, plus tests. A new `queries.py` constant is fine if a distinct read shape is needed (else reuse `PAUSE_STATE_SELECT` / `DEGRADED_MODE_SELECT`).
- Sacrificial folder `MailBot-UAT-10-1` is retained empty for move-family walks (Epic 10 residual). The 10-1 walk subject stays soft-deleted (F6 evidence) — its repair is story **10-5-4** (Cluster D), NOT here.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 10.5 Detail] — Story 10.5.1 ACs, done-flip gate clause 2, the bug-CLASS framing.
- [Source: _bmad-output/implementation-artifacts/epic-10-retro-2026-07-07.md#5] — bug-class root-cause analysis (per-process singleton); §7 cluster table; R2/R3 spawn decisions.
- [Source: _bmad-output/implementation-artifacts/10-1-walk-evidence.md#2.2] — F4 evidence (259ms live Graph write while paused); the finding names `router/pause.py:21-34,93-97`.
- [Source: _bmad-output/implementation-artifacts/10-5-walk-evidence.md] — F1 (pause kills chat, S5), F-10-5-4 (resume deadlock, S6), F3 (paused refusals no audit rows).
- [Source: mailbot_api/router/pause.py] / [drainer.py] / [budget.py] / [router.py] — the code being fixed (line anchors inline above).
- [Source: mailbot_api/db/migrations/010_pause_state.sql] / [008_degraded_mode.sql] — the cross-process singleton rows.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev). Code review: claude-sonnet-5 (reviewer ≠ dev per §5.12 MANDATORY-CR).

### Debug Log

- **The class fix is two authoritative DB readers, not a rewrite.** Added `PauseState.is_paused_now(db_path)` / `reason_now(db_path)` (pause.py) and `BudgetGuard.is_degraded_now(db_path)` (budget.py), each hitting the migration-010/008 singleton row at decision time — mirroring the existing status.py:332 live-read pattern. Both fail closed (read error ⇒ treat as paused/degraded) so a DB hiccup can never silently re-open the write path. The warm `is_paused()`/`is_degraded()` + `initialize()` cache stays for the OAuth auto-pause path.
- **Drainer gate (Task 1, AC-1/AC-4):** drainer.py:488 tick-entry gate + :517 mid-tick re-check now call `is_paused_now(db_path)` instead of the stale `is_paused()` mirror. Snapshot once at tick entry (Story 6-15 CR-13 intent preserved); the mid-tick re-check is a deliberate fresh read (it must observe a pause that AROSE during the tick). Paused skips emit a `pause_gate:refused` `router_calls` audit row via the Rule-C `record_router_call` writer — no new raw-SQL writer, boundaries green.
- **Resume-deadlock (Task 3, AC-3):** the two chat gates made conditional. `dispatch_tool_call` (router.py, the tools path Hermes uses) now filters `tools` to `_PAUSE_ALLOWED_TOOLS` (control + status + read-only) while paused — write/action verbs are removed from the surface so the model cannot reach them (F4 containment) while `resume_router` stays reachable. `ask_router` (text path) permits only `_PAUSE_ALLOWED_TASK_TYPES={"hermes_aux"}` (the chat-interpretation lane) and refuses action/ingest task types. Both refusal paths audit via `_emit_pause_refusal_audit_row`. The gate is NOT removed (the trap the finding warns about) — pause still suppresses actions.
- **AC-4 audit vocab:** added `ModelChosenReason.PAUSE_GATE_REFUSED = "pause_gate:refused"` (audit_vocab.py) — a literal member, so `LITERAL_REASONS` auto-accepts it; no audit.py validator edit needed. Docstring counts updated (9→10 literals).
- **Scope-fence handoff to 10-5-5 (Cluster E):** the degraded-flag READ is now authoritative on the two router DISPATCH gates (router.py:463 ask_router + the dispatch_tool_call gate) — the reads that govern a mailbox write, exactly AC-2's requirement. The status-REPORT consumers (`inspect_policy`, `cost_breakdown`, `reset_degraded_mode.previously`) were deliberately LEFT on the in-memory `is_degraded()`: a report read that fails closed would falsely display "degraded/Active" on a transient DB-read error, which is worse for the operator than a momentarily-stale mirror, and those reads govern no write. The `add_spend` counter inflation / July re-derive / pricing remains untouched — that is story 10-5-5.
- **3 pre-existing tests updated to the new (correct) contract** (behavior changes, not regressions): (1) `test_ask_router_paused_returns_provider_error` now asserts a `pause_gate:refused` audit row is written (was: "no router_calls row" — the F3 gap being closed); (2) `test_runner_aborts_on_degraded_mode_blocked` now trips degraded via the DB row, not the in-memory `_degraded_mode_active` shortcut (the exact stale-mirror path this story eliminates); (3) `test_chat_completions_pause_kill_switch_short_circuits` split into two tests asserting the new permit-interpretation-filter-writes contract instead of a blanket 502.

### Completion Notes List

- **AC-1 (F4, CRITICAL):** drainer refuses to dispatch while paused, reading the cross-process DB row. New two-instance integration test (`test_worker_drainer_wiring.py::test_cross_process_pause_stops_worker_drainer_dispatch`) proves a DB-only pause (no worker `initialize`) stops a real `OutlookGraphWriteAdapter` drain loop — zero Graph HTTP calls, row stays pending. Unit tests in `test_drainer.py` cover the same without the network. **Live walk (Task 5) is Adam-hands-on and deferred — see run-flags.**
- **AC-2 (the CLASS):** both `PauseState` and `BudgetGuard` get authoritative cross-process readers; the degraded gate on both router dispatch sites reads the DB. Cross-process staleness tests added for both (`test_pause.py`, `test_budget.py`). Scope fence to Cluster E honored (no counter/pricing/re-derive changes).
- **AC-3 (F1 + F-10-5-4):** resume-by-chat reachable while paused — `dispatch_tool_call` filters to the control allowlist, `ask_router` permits `hermes_aux`. New tests: `test_dispatch_tool_call_pause_allowlist.py` (4), `test_router.py::test_ask_router_paused_permits_hermes_aux_interpretation`, two `test_chat_completions` endpoint tests. F4 containment verified (write tools filtered; propose_action still refused).
- **AC-4 (F3):** paused refusals audited via `pause_gate:refused` `router_calls` rows at the drainer skip, the `ask_router` refusal, and the `dispatch_tool_call` write-tool filter. Asserted in drainer + router + endpoint tests.
- **AC-5:** the cross-process regression that would have caught F4 is present at three layers (pause primitive, drainer unit, worker integration two-instance) plus the degraded twin. Mid-tick pause release + OAuth-path non-regression covered.
- **AC-6:** ruff (mailbot_api/tests/scripts) + mypy --strict (129 files) + check_boundaries all green. Full suite green with net-new tests above the 1708 baseline. (Pre-existing `scratch/` T201s are untracked and out of scope.)

### File List

- `mailbot_api/router/pause.py` — added `snapshot_now` (single-read atomic (paused, reason) pair, fail-closed + logged) with `is_paused_now` / `reason_now` as convenience wrappers over it (CR: atomicity + no-silent-swallow).
- `mailbot_api/router/budget.py` — added `is_degraded_now` authoritative cross-process reader (fail-closed).
- `mailbot_api/router/audit_vocab.py` — added `PAUSE_GATE_REFUSED` literal member + docstring counts.
- `mailbot_api/actions/drainer.py` — tick-entry + mid-tick pause gates now read the DB; `_emit_pause_skip_audit_row` helper.
- `mailbot_api/router/router.py` — conditional pause gates on `ask_router` (task allowlist) + `dispatch_tool_call` (tool allowlist); **`_tool_on_pause_allowlist()` suffix-matches Hermes's `mcp_<server>_<verb>` namespaced tool names (live-walk fix F-10-5-1-W1)**; **`dispatch_embedding` gate migrated to authoritative `is_paused_now` + audit row (CR fix, the third dispatch site)**; `_emit_pause_refusal_audit_row`; both degraded dispatch gates read `is_degraded_now`.
- `mailbot_api/verbs/router_control.py` — `inspect_policy` degraded line kept in-memory (report surface, scope note).
- `mailbot_api/verbs/cost.py` — `cost_breakdown` degraded flag kept in-memory (report surface, scope note).
- `mailbot_api/verbs/budget_admin.py` — `reset_degraded_mode.previously` kept in-memory (report field, scope note).
- `tests/unit/router/test_pause.py` — cross-process staleness + live-resume + fail-closed tests.
- `tests/unit/router/test_budget.py` — degraded cross-process + live-exit + fail-closed tests.
- `tests/unit/actions/test_drainer.py` — DB-level pause short-circuit + post-resume drain + mid-tick release + audit-row tests.
- `tests/unit/router/test_router.py` — updated paused-refusal-audits-row test; new hermes_aux-permitted-while-paused test.
- `tests/integration/test_dispatch_tool_call_pause_allowlist.py` — NEW: paused tool-surface restriction + audit-row tests.
- `tests/integration/test_worker_drainer_wiring.py` — NEW two-instance F4 regression (DB pause stops real drainer).
- `tests/integration/test_chat_completions_tool_calling.py` — replaced the blanket-502 pause test with permit-interpretation-filter-writes + control-tool-permitted tests.
- `tests/integration/test_benchmark_runner.py` — degraded-blocked test trips degraded via DB row, not the in-memory mirror.
- `tests/integration/test_embedding_e2e.py` — NEW `test_dispatch_embedding_paused_refuses_cross_process` (CR fix regression for the third pause site).

### Change Log

- 2026-07-07 — Fixed the per-process in-memory singleton bug CLASS: pause + degraded-flag reads made cross-process authoritative at the write/dispatch-governing sites; drainer pause gate closes F4 (CRITICAL); resume-by-chat unblocked (F1 + F-10-5-4) via conditional gates with a control allowlist; paused refusals audited (F3). Tasks 1–4 dev-complete; Task 5 live walk deferred to Adam-hands-on.
- 2026-07-07 — MANDATORY-CR (sonnet-5 ≠ dev opus-4-8): 1 Decision + 3 Patches APPLIED = 4/4 actionable resolved (100%); 7 Defers documented (DRY/TOCTOU-narrow/architectural, no correctness impact). Decision: `dispatch_embedding` (the 3rd pause site) migrated to authoritative `is_paused_now` + audit row. Patches: `snapshot_now` single-read closes the CR-13 non-atomic (paused,reason) window + logs on read failure; paused-refusal test now asserts the full zero-cost row shape. +2 net tests (dispatch_embedding regression + shape-strengthened assertion). Gates re-green.
- 2026-07-07 — TASK 5 LIVE CO-WALK (Adam-hands-on, real Graph + real Discord): AC-1 F4 confirmed live in Outlook (paused move held, resume released — F4 non-reproducible). **Live defect F-10-5-1-W1 (HIGH) FIXED in-session:** `_PAUSE_ALLOWED_TOOLS` matched bare verb names but Hermes namespaces MCP tools as `mcp_<server>_<verb>` → `allowed_count: 0` filtered out resume_router → F-10-5-4 re-opened; fix = `_tool_on_pause_allowlist()` suffix-match + regression test (live-verified 0→12). **F-10-5-1-W2 (HIGH) FILED (out of scope):** Hermes MCP streamable-HTTP session drops the resume_router call (`Session terminated`, 30s timeout) before it reaches the verb — isolation-proven our verb works via direct call; a Hermes-transport story owns it. AC-3 resume-from-Discord = PARTIAL (router fully fixed; blocked only by the external transport defect). See 10-5-1-walk-evidence.md §B + epic-10-5-run-flags.md.
