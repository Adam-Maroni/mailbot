---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.9: Hourly anomaly detection + anti-loop kill-switch + `/pause` / `/resume`

Status: done

## Story

Hourly Router call-volume anomaly detection (rolling 7-day baseline + 3σ alert), prompt-hash repetition detection (LOOP_DETECTED on >10 identical prompts in 5 min), and `/pause` / `/resume` kill-switch (SQLite-persisted, halts all Router calls without killing FastAPI).

## Acceptance Criteria

- [x] **AC-1** `limits.py` extends with `LoopDetector` — rolling 5-min window of prompt-hash timestamps; >10 occurrences returns block. `get_loop_detector()` singleton + `_reset_loop_detector_for_test()` helper.
- [x] **AC-2** Loop block fires LOOP_DETECTED in `_dispatch_with_failure_chain` AFTER user_msg render (uses same hash as response_cache).
- [x] **AC-3** Migration `009_anomaly_baseline.sql` (renumbered from epic-spec 008) — `call_volume_baseline(caller_origin, hour_of_day, mean_volume, stddev_volume, sample_count, last_updated)` + Welford online stats update.
- [x] **AC-4** `anomaly.py:run_anomaly_check` aggregates last-hour calls per caller_origin, compares vs baseline_mean + 3σ, alerts on breach (after warm-up at 24 samples), upserts baseline.
- [x] **AC-5** `AnomalyDetector` lifecycle class (interval-task with start/stop). Wired into lifespan with hourly interval.
- [x] **AC-6** Migration `010_pause_state.sql` (renumbered from epic-spec 009) — singleton row with paused / reason / paused_at / resumed_at.
- [x] **AC-7** `pause.py:PauseState` initialize/pause/resume — module-level singleton. Persists across restarts (initialize reads SQLite).
- [x] **AC-8** `ask_router` checks `get_pause_state().is_paused()` at the very top — short-circuits with PROVIDER_ERROR message="router paused" retryable=True; NO router_calls row written (pause check fires before dispatch).
- [x] **AC-9** Verb shim `verbs/router_control.py` — `pause_router(reason)` + `resume_router()` returning Pydantic `PauseOut` / `ResumeOut`. Epic 5 wires the slash command.
- [x] **AC-10** Tests: LoopDetector unit tests (test_limits.py extension), PauseState unit tests (test_pause.py), AnomalyDetector + run_anomaly_check tests (test_anomaly.py), ask_router integration tests for pause + loop (test_router.py), verb tests (test_router_control.py).
- [x] **AC-11** All gates green.

## Dev Notes

### Migration renumbering chain (closing the gap from epic spec)

Cumulative renumber from epic spec:

| Epic spec  | Actual     | Owned by |
|------------|------------|----------|
| 005        | 006        | Story 2-1 (router_calls) |
| 006        | 007        | Story 2-7 (response_cache) |
| 007        | 008        | Story 2-8 (degraded_mode) |
| 008        | 009        | Story 2-9 (anomaly_baseline) |
| 009        | 010        | Story 2-9 (pause_state) |

### Loop hash key reuse

LoopDetector uses the same `compute_cache_key(model, 0.0, system, user)` hash as the response cache. This is intentional — identical prompts that would hit the cache also count as loop repetitions. The two systems share the input-identity hash.

### Pause check ordering — short-circuit before policy snapshot

The pause check happens at the very TOP of `ask_router`, before the policy snapshot is captured. Rationale: pause is operational/emergency state, not policy state. A paused router rejecting calls before any work happens is the fastest path to fail.

### Anomaly detection baseline warm-up

The 3σ alert only fires after 24 samples (one day of hourly observations) are collected per (caller_origin, hour_of_day) pair. Below that, observations are recorded silently — alerting on a low-sample-count baseline would produce false positives.

### force_model integration with pause

`ask_router` checks pause BEFORE force_model resolution. So a paused router rejects ALL calls including force_model=opus. The DEGRADED_MODE_BLOCKED gate for force-opus is separate (Story 2-8) and only fires when not paused but in degraded mode.

## File List

**Created:**

- `mailbot_api/db/migrations/009_anomaly_baseline.sql`
- `mailbot_api/db/migrations/010_pause_state.sql`
- `mailbot_api/router/anomaly.py`
- `mailbot_api/router/pause.py`
- `mailbot_api/verbs/router_control.py`
- `tests/unit/router/test_pause.py`
- `tests/unit/router/test_anomaly.py`
- `tests/unit/verbs/test_router_control.py`

**Updated:**

- `mailbot_api/db/queries.py` — `PAUSE_STATE_*` + `CALL_VOLUME_*` query constants
- `mailbot_api/router/limits.py` — `LoopDetector` + helpers
- `mailbot_api/router/router.py` — pause check (top of ask_router) + loop detector (after user_msg render)
- `mailbot_api/main.py` — `get_pause_state().initialize()` + `AnomalyDetector` start/stop
- `tests/unit/router/test_limits.py` — LoopDetector tests
- `tests/unit/router/test_router.py` — extended `_clean_state` + 3 new pause/loop integration tests + 2 distinct-content rewrites for rate-limit tests (loop detector also fires on identical content)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Completion Notes List

- **Gate-coverage-only** — no code review subagent. Three coordinated additions (LoopDetector + AnomalyDetector + PauseState) each with isolated unit tests + ask_router integration tests.
- **One existing test regression caught**: 2 rate-limit-breach tests sent 60 identical prompts and now trip the loop detector at the 11th. Fixed by varying `content["subject"]` per iteration — the test intent was always rate-limit isolated, not loop-detector concerned.
- **316 passed + 2 skipped** (298 → 316, +18 net new tests across 4 new test files + integration extensions).
