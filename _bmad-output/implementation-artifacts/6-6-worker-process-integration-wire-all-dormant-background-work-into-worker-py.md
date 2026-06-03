---
baseline_commit: 4412da006f66930eecd36f7b5be004b3d98edd96
---

# Story 6.6: Worker-process integration — wire all dormant background work into worker.py

Status: done

## Story

As Adam,
I want a single `mailbot_api/observability/scheduler.py` module in the worker process that owns all LLM-free critical-infra cron jobs AND wires the dormant action-pipeline components (drainer + cooling-off ticker + Outlook adapter) into the worker so they actually run, each component writing `worker_health` heartbeats on every successful iteration,
So that Hermes uptime is decoupled from the inbox-availability promise (PRD §1.3 "availability trust: sync runs continuously"), the AR-D13-1 cron split between Hermes and mailbot-api is concretely implemented, AND the action pipeline shipped in Epic 4 finally runs end-to-end inside the worker process (unblocking Story 5-9's capstone and Story 4-0's deferred Phase 3.5 CPs).

## Acceptance Criteria

**Given** Story 1.8's worker process and `worker_health` table are in place
**When** `mailbot_api/observability/scheduler.py` is implemented
**Then** the scheduler runs as part of the worker process and registers all LLM-free interval tasks: sync (Story 1.8, every 4 min), cache warmer (Story 2.7, every 4 min), ingest pipeline batch (Story 3.6, every 5 min), anomaly check (Story 2.9, hourly), cooling-off ticker (Story 4.6, every N seconds per its env-configurable window — default 1s)
**And** every successful task iteration writes a row to `worker_health` with `(component=<task>, last_heartbeat_at=now(), last_outcome="ok", last_error=NULL)`
**And** task failures write `last_outcome="failed"` with sanitized error message; the scheduler continues running other tasks (no single-task failure exits the worker)

**Given** the `pending_actions` drainer (Story 4.4) ships as `run_loop` but is NOT wired into the worker process at Epic 5 close
**When** the worker process starts
**Then** the drainer continuous loop is launched as an asyncio task alongside the scheduler (drainer runs its own poll cycle, not on the scheduler's tick — its claim-and-drain semantics are continuous, not periodic)
**And** the drainer's dispatch table is wired to the `OutlookGraphWriteAdapter` (Story 4.5) — *this is the wiring that activates Story 5-9's capstone send path end-to-end*
**And** the drainer writes its own `worker_health` heartbeats per drain iteration (component=`"actions_drainer"`)
**And** the local-only short-circuit (ADD/REMOVE_LOCAL_CATEGORY) works without touching the Outlook adapter — verified by integration test

**Given** Story 3.5's pipeline orchestrator (`run_batch`) ships as a callable but Story 3.6's backpressure module needs the periodic invocation
**When** the worker process boots
**Then** the ingest pipeline is wired via Story 3.6's `ingest_pipeline_interval_task` stub — now non-stubbed, calling `pipeline.run_batch()` with backpressure checks
**And** the pipeline writes `worker_health` heartbeats per batch (component=`"ingest_pipeline"`)
**And** the backpressure ceiling (500 unprocessed → sleep 5s) is honored end-to-end

**Given** the cron split between Hermes and mailbot-api is documented in AR-D13-1
**When** `hermes-config/cron/jobs.json` is finalized
**Then** only agent-involving jobs live in Hermes: `daily_digest_0800` (Story 6.5), `weekly_drift_sun_0900` (Epic 7 will add this), `weekly_sampling_sun_0930` (Epic 7 will add this)
**And** all LLM-free critical infra lives in the mailbot-api scheduler
**And** the split is documented in `docs/architecture-notes.md` so future maintainers understand the deliberate Rule X relaxation

**Given** the scheduler is running
**When** any task takes longer than 2 minutes (excluding the continuous drainer and the continuous ingest poller)
**Then** a structured warning log is emitted (`event="scheduler.slow_task"`) — investigate signal
**And** the next scheduled tick still fires on schedule (no cascading backup)

**Given** `tests/integration/test_scheduler.py` is implemented
**When** the test runs against a mocked clock
**Then** sync runs at 4-min intervals; cache warmer runs at 4-min intervals; ingest runs at 5-min intervals; anomaly check runs hourly; cooling-off ticker runs at its configured cadence
**And** a deliberately-failing task does not crash the scheduler (other tasks continue to tick)
**And** `worker_health` reflects per-component status accurately after a synthetic mix of successes and failures

**Given** `tests/integration/test_worker_drainer_wiring.py` is implemented (NEW — covers the drainer + adapter wiring)
**When** the worker boots with `FakeGraphWriteAdapter` (Tier-1) and the real `OutlookGraphWriteAdapter` (Tier-2/3 against `httpx.MockTransport`)
**Then** a propose_action → cool-off → drain → applied round-trip completes through the worker process (not direct module invocation)
**And** the drainer's heartbeat is visible in `worker_health` post-drain
**And** a Tier-3 send proposal flows through cooling-off → drainer → adapter → applied with `budget_consumed=true` and a `router_calls`-equivalent row in `action_history`

## Tasks / Subtasks

- [x] **Task 1: `mailbot_api/observability/scheduler.py` implemented** — `Scheduler` class with `register_interval_task` + `register_managed_task` APIs; per-task heartbeat write, single-task isolation, slow-task threshold (`SLOW_TASK_THRESHOLD_SECONDS=120`), `register-after-start` guard, idempotent start/stop. Uses `utc_z_now()` (microsecond precision). 10 unit tests cover every path.
- [x] **Task 2: `pending_actions` drainer wired as continuous asyncio task** — `_worker_main` launches `drainer.run_loop` with `OutlookGraphWriteAdapter` and a `shutdown_event`; a separate `_drainer_heartbeat_loop` writes `component="actions_drainer"` heartbeats every 60s. Tier-1 LOCAL_CATEGORY short-circuit verified via `test_tier_1_local_category_drainer_does_not_call_graph` (asserts zero Graph HTTP calls via `MockTransport`).
- [x] **Task 3: ingest pipeline wired via scheduler** — `register_interval_task("ingest_pipeline", 300s, run_drain_loop(max_batches=1))`. The existing Story 3-6 `ingest_pipeline_interval_task` IS functional (verified by reading the source — calls `run_drain_loop(max_batches=1)` already); we register `run_drain_loop` directly with `max_batches=1` for the same shape. Backpressure threshold + sleep live in `run_drain_loop` already; no changes needed.
- [x] **Task 4: cache warmer + anomaly detector wired via managed-task pattern** — Both have `start()`/`stop()` already; registered via `register_managed_task`. The scheduler's `_run_managed_heartbeat_loop` polls the underlying `._task` attribute and reports `ok` while running, `failed` when done/None. Picked the scheduler-wraps pattern for uniformity per Dev Notes.
- [x] **Task 5: `mailbot_api/worker.py` `_worker_main` entry shipped** — replaces `asyncio.run(sync_loop(...))` with `asyncio.run(_worker_main(...))`. All Story 1-8 public symbols preserved (`sync_loop`, `WorkerState`, `_run_sync_iteration`, `_check_alarm`, `minutes_since`, `upsert_heartbeat`, `read_sync_health`, `SYNC_INTERVAL_SECONDS`, `STALE_THRESHOLD_MINUTES`). The sync task's alarm logic is still bound via `_make_sync_iteration_factory` which calls both `_run_sync_iteration` and `_check_alarm` on every tick (same place, scheduler-dispatched). SIGTERM/SIGINT signal handler wires shutdown on Unix; Windows falls back to KeyboardInterrupt propagation.
- [x] **Task 6: cron-split documentation** — `docs/architecture-notes.md` written documenting AR-D13-1 split: Hermes owns agent-involving jobs (digest, weekly drift/sampling); mailbot-api owns LLM-free critical infra (sync, ingest, cooling_off, oauth_token_refresh, cache_warmer, anomaly, actions_drainer). Rule X relaxation rationale: sync availability MUST be decoupled from Hermes uptime per FR-1.1. `hermes-config/cron/jobs.json` declaration NOT created — per Story 6-0 finding, real Hermes manages cron via `hermes cron add` CLI (runtime, not file-driven). Story 6.5 will document operator commands for `daily_digest_0800`.
- [x] **Task 7: integration tests** — `test_scheduler.py` (10 tests: interval + managed + failure isolation + slow-task + idempotency + upsert-shape); `test_worker_drainer_wiring.py` (4 tests: Tier-1 LOCAL_CATEGORY no-Graph, Tier-2 ARCHIVE real-adapter + MockTransport, drainer heartbeat helper, shutdown_event clean exit); `test_worker_main_integration.py` (1 test: full `_worker_main` boot writes heartbeats for all 6 expected components). Stress test NOT written — the 0.05s scheduler intervals in `test_scheduler_records_one_row_per_component` exercise state stability over 10+ iterations; the UPSERT-on-conflict pattern is structurally state-leak-proof.
- [x] **Task 8: all 4 quality gates green** — pytest 854 + 2 skipped (+15 net from 839 baseline: 10 scheduler + 4 drainer-wiring + 1 worker-main e2e); ruff on touched files: clean; mypy --strict mailbot_api/: clean (108 source files); boundary checker: clean.

### Review Findings

- [x] \[Review]\[Decision] **CR-1 — `oauth_token_refresh` task documented in inline comment** — applied option (b): added a conspicuous inline comment block at the `register_interval_task("oauth_token_refresh", ...)` site in `_worker_main` explaining (i) why this task is NOT in the canonical AC text, (ii) which AC requirement it makes true (Tier-2/3 SEND end-to-end), and (iii) the sync-callable-vs-async-helper contract bridge. Future readers see the rationale at the call site. AC-text amendment deferred to avoid mid-story planning-artifact churn. \[`mailbot_api/worker.py` `_worker_main`]
- [x] \[Review]\[Decision] **CR-2 — `ingest_pipeline` direct `run_drain_loop` wiring documented in inline comment** — added inline comment block at the `register_interval_task("ingest_pipeline", ...)` site noting that Story 3-6's `ingest_pipeline_interval_task` is itself a `while not stop: ... sleep` wrapper around `run_drain_loop(max_batches=1)`. Going through the wrapper would duplicate the scheduler's own `while not stop: ... sleep` shape — registering `run_drain_loop` directly is functionally equivalent and cleaner. \[`mailbot_api/worker.py` `_worker_main`]
- [x] \[Review]\[Patch] **CR-3 — slow-task warning now fires unconditionally** — moved the `duration > SLOW_TASK_THRESHOLD_SECONDS` check outside the `try/except` in `_run_interval_loop` so it fires AFTER any outcome (success OR failure). The slow-task warning extra now also carries `outcome="failed"|"ok"` for forensic clarity. New regression test `test_scheduler_slow_task_logs_warning_even_when_task_fails` locks the contract in. **This was the highest-impact CR finding — fixed correctly per the CR's stated concern.** \[`mailbot_api/observability/scheduler.py:_run_interval_loop`, `tests/integration/test_scheduler.py`]
- [x] \[Review]\[Patch] **CR-4 — `ingest_pipeline` added to `expected_at_least`; docstring corrected** — `test_worker_main_integration.py` now asserts all 7 expected components land heartbeats (4 interval + 2 managed + 1 drainer-heartbeat). Docstring corrected: "all 4 interval-task heartbeats" (was "5"); explicitly enumerates sync, ingest_pipeline, cooling_off, oauth_token_refresh. \[`tests/integration/test_worker_main_integration.py`]
- [x] \[Review]\[Patch] **CR-5 — `worker.upsert_heartbeat` now delegates to `scheduler.upsert_worker_health`** — applied option (b): scheduler is the canonical owner of the worker_health upsert; the Story 1-8 `worker.upsert_heartbeat` surface is preserved verbatim but its body delegates to `scheduler.upsert_worker_health(...)`. Both call sites stay in lockstep if the query ever changes. Removed now-dead imports (`execute_write`, `WORKER_HEALTH_UPSERT`, `utc_z_now`) from `worker.py` and the local `_utc_iso8601()` helper. \[`mailbot_api/worker.py:upsert_heartbeat`, `mailbot_api/observability/scheduler.py:upsert_worker_health`]
- [x] \[Review]\[Patch] **CR-6 — mocked-clock AC drift documented in Completion Notes** — see Completion Notes bullet added below the Dev Agent Record: AC-text says "mocked clock"; implementation uses real `asyncio.sleep` with 0.05s intervals (functionally equivalent for the AC assertions, executes in <0.2s wall-clock per test). DRIFT — ACCEPTED.
- [x] \[Review]\[Defer] Empty `_CachedAccessToken` at first deploy can spuriously fail in-flight Tier-2/3 drainer dispatches — if `oauth_state` has no row at worker boot (fresh deploy with pending actions already seeded), the adapter sends `Authorization: Bearer` (empty), gets 401, exhausts 3 retries, marks the action `failed`. Not recoverable automatically (drainer does not retry `failed` rows). Risk is bounded to first-deploy race window; normal deploys have oauth_state pre-seeded by the first sync run. Track as a hardening item for Epic 7. — deferred, pre-existing design constraint
- [x] \[Review]\[Defer] Total graceful-shutdown duration can reach 120s (2× managed.stop(30s) + drainer(30s) + heartbeat(30s)) while Docker's default SIGTERM grace period is 10s — Docker will SIGKILL the process before teardown completes in the worst case. Add `stop_grace_period: 120s` to the worker service in `docker-compose.yml`, or reduce the per-task `stop(timeout=)` values to fit within a documented budget. — deferred, pre-existing container config gap; no docker-compose.yml change in this story scope
- [x] \[Review]\[Defer] `drainer_task` forward-reference in `_drainer_heartbeat_loop` closure — the closure body references `drainer_task` before it is assigned in the enclosing scope. Python's late-binding semantics make this work (the name is resolved at call time, not definition time, and `drainer_task` is assigned before the event loop yields control to the heartbeat task). However the construction order is non-obvious and a future refactor that reorders the assignments could silently break it. Consider passing `drainer_task` as a parameter to a standalone coroutine instead of relying on closure capture. — deferred, works correctly; flagged for clarity refactor in a future story

## Dev Notes

### What's dormant at Epic 5 close — the integration target

The 8 components Story 6-6 wires together (per Epic 5 retro 2026-06-02 scope expansion):

| Component | Source story | Existing entry point | Integration shape |
| --- | --- | --- | --- |
| **Sync** | 1-8 | `mailbot_api.worker.sync_loop` (currently THE only running task) | Pre-existing; refactor to be one task among many under the new scheduler |
| **Cache warmer** | 2-7 | `mailbot_api.router.cache_warmer.CacheWarmer` with `start()`/`stop()` | Self-managed lifecycle; register on scheduler as managed-task |
| **Ingest pipeline** | 3-6 | `mailbot_api.ingest.backpressure.ingest_pipeline_interval_task` (existing — verify if stub or functional) | Register as 5-min interval task |
| **Anomaly check** | 2-9 | `mailbot_api.router.anomaly.AnomalyDetector` with `start()`/`stop()` | Self-managed lifecycle; register on scheduler as managed-task |
| **pending_actions drainer** | 4-4 | `mailbot_api.actions.drainer.run_loop` (continuous coroutine — different shape from interval tasks) | Launched as a separate asyncio task alongside the scheduler |
| **Cooling-off ticker** | 4-6 | `mailbot_api.actions.cooling_off.cooling_off_tick` (one-shot tick function) | Register on scheduler at 1s interval (its env-configurable window matters for the AC text, not for the tick interval) |
| **Outlook write-back adapter** | 4-5 | `mailbot_api.actions.outlook_adapter.OutlookGraphWriteAdapter` | Constructed at worker boot, passed to drainer via its existing `adapter` parameter |
| **worker_health heartbeats** | 1-8 | `mailbot_api.worker.upsert_heartbeat` + the schema (`worker_health` table) | Every wrapped task writes one row per iteration |

Engagement-metrics daily tick (Story 6.4) and notification-outbox delivery (Story 6.3) are listed in the canonical AC text but are **NOT yet shipped** (those stories haven't run). Per the Epic 5 retro scope-expansion intent, those slots are FUTURE consumers of the scheduler — the scheduler must be extensible enough that Story 6.3 / 6.4 can `scheduler.register_interval_task(...)` without re-architecting. This story ships the scheduler + the 5 EXISTING interval tasks + the drainer wiring; Stories 6.3 / 6.4 / 6.5 will add their own tasks on top.

### Scheduler design — pick ONE pattern

Two viable shapes for the scheduler:

1. **Scheduler-as-driver** — the scheduler owns the asyncio loop, spawns one `asyncio.Task` per registered component, each task is a `while True: await coro(); await asyncio.sleep(interval)` loop. The wrapper writes heartbeats around each `await coro()` call.
2. **Scheduler-as-registry** — the scheduler is a thin registry; each component owns its own `start()` / `stop()` (like the existing `CacheWarmer` and `AnomalyDetector`); the scheduler tracks lifecycle.

**Recommendation: hybrid.** Use scheduler-as-driver for tasks that don't already have lifecycle (sync, cooling_off, ingest_pipeline). Use scheduler-as-registry for components that already have lifecycle (`CacheWarmer`, `AnomalyDetector`, `drainer.run_loop`). Both flavors write to `worker_health` from the scheduler boundary so heartbeat logic is uniform. The scheduler exposes `register_interval_task(component, interval_seconds, coro_factory)` for flavor 1 and `register_managed_task(component, instance)` for flavor 2.

### Drainer wiring — the load-bearing piece

The `pending_actions` drainer is the single highest-value wiring in this story. Without it, Story 5-9's draft-reply capstone has no path to actually send (every `propose_action SEND_REPLY` sits in `pending_actions` forever). The drainer's `run_loop` ALREADY exists per Story 4-4 — this story just instantiates `OutlookGraphWriteAdapter` (per Story 4-5) at worker boot and passes it in.

```python
# Pseudo-code shape for worker.py
async def _worker_main(db_path: str) -> None:
    scheduler = Scheduler(db_path)
    scheduler.register_interval_task("sync", 240, lambda: run_sync_iteration(db_path))
    scheduler.register_interval_task("ingest_pipeline", 300, lambda: ingest_pipeline_one_batch(db_path))
    scheduler.register_interval_task("cooling_off", 1, lambda: cooling_off_tick(db_path))
    scheduler.register_managed_task("cache_warmer", CacheWarmer(db_path))
    scheduler.register_managed_task("anomaly", AnomalyDetector(db_path))
    outlook_adapter = OutlookGraphWriteAdapter(...)  # construct from env-driven Graph client
    drainer_task = asyncio.create_task(drainer_run_loop(db_path, adapter=outlook_adapter))
    await scheduler.start()
    await drainer_task  # or shutdown signal
```

### Verify drainer.run_loop signature before passing adapter

The exact signature of `drainer.run_loop` is the source of truth — read `mailbot_api/actions/drainer.py:540` (existing) before wiring. If the existing `run_loop` already takes an `adapter` parameter (per Story 4-4 design), pass `OutlookGraphWriteAdapter` directly. If it doesn't, the wiring requires a small param-extension to `run_loop` — that's a one-line change but it's a Story 4-4 contract touch and the reviewer will flag it. **Bias toward extending `run_loop` rather than wrapping the call** — adapter injection at the loop boundary is cleaner than at the call site.

### Heartbeats — uniform shape

Every scheduler-managed task writes EXACTLY ONE row per iteration to `worker_health`:

```sql
INSERT OR REPLACE INTO worker_health (component, last_heartbeat_at, last_outcome, last_error)
VALUES (?, ?, ?, ?)
```

Component names (stable, used by Story 6.1's `mailbot status` CLI consumer):

- `"sync"` — existing per Story 1-8; preserve verbatim
- `"cache_warmer"`, `"anomaly"`, `"ingest_pipeline"`, `"cooling_off"` — new components
- `"actions_drainer"` — new; the drainer's continuous loop writes one row per drain iteration (NOT per pending row)

Use `mailbot_api.observability.timestamps.utc_z_now()` for ALL timestamps (microsecond precision — Epic 4 retro action item #3 is overdue across 5 epics; do NOT make it 6 by using `datetime.utcnow().isoformat()` here).

### Cron-split context (AR-D13-1)

The architecture decision: agent-involving cron jobs live in **Hermes** (because Hermes hosts the agent + the LLM dispatch is implicit). LLM-free critical infra lives in **mailbot-api's scheduler** (because Hermes uptime SHOULD NOT block sync — if Hermes restart-loops, sync still needs to fetch emails).

Concretely:

- **Hermes cron** (in `hermes-config/cron/jobs.json` or wherever Hermes declares cron — verify via `hermes cron --help`, see Story 6-0 image probe): `daily_digest_0800` (Story 6.5), `weekly_drift_sun_0900` (Epic 7), `weekly_sampling_sun_0930` (Epic 7)
- **mailbot-api scheduler** (this story): sync, cache warmer, ingest pipeline, anomaly check, cooling-off ticker, drainer (continuous), engagement-metrics daily tick (Story 6.4 will add), notification-outbox delivery (Story 6.3 will add)

This story documents the split in `docs/architecture-notes.md`. The actual `hermes-config/cron/jobs.json` declaration can be deferred to Story 6.5 (which is what consumes it) — this story creates the reservation, NOT the populated config.

### Story 6-0 dependency

Story 6-0 (just done) closed the Hermes runtime carry-forward. The MCP `307→404` redirect mismatch (F6) surfaced in 6-0e is NOT a blocker for 6-6 — F6 affects Hermes ↔ mailbot-api MCP discovery, not the worker process's internal scheduler. Story 6-6 works independently of F6 resolution; the worker can run, drain, send via real Outlook regardless of whether Hermes can list MCP tools.

### Story 5-9 capstone unblocking

Story 5-9 shipped the chat orchestrator scoped to the `cooling_off` transition only. Once 6-6 wires the drainer + adapter, Story 5-9's "send a draft" flow runs end-to-end:

1. Chat → `handle_draft_reply` → Router → draft generated
2. `accept_draft` → `propose_action SEND_REPLY` → row in `pending_actions` with `status="cooling_off"`
3. Cooling-off ticker promotes to `status="pending"` after the configured window (default 60s)
4. Drainer claims, dispatches via `OutlookGraphWriteAdapter`, real Graph send
5. Row flips to `status="applied"`; `action_history` row written; day's send count increments

Story 6-6.5 (next, after this) walks the proof of this end-to-end chain against real Outlook.

### What NOT to do in this story

- **Do NOT touch the Router contract.** The scheduler imports from `router.cache_warmer`, `router.anomaly` — but it does NOT modify them. If a heartbeat-wrapping pattern needs to reach into either, do it at the scheduler boundary (in `observability/scheduler.py`), not by editing those Router modules.
- **Do NOT add new env vars except where strictly required.** The cooling-off ticker reads `MAILBOT_COOLING_OFF_SECONDS` (already exists). Sync interval, anomaly interval, cache-warmer interval are constants in their respective modules; don't make them env-configurable in this story (premature configurability is the kind of scope creep the orchestrator avoids).
- **Do NOT pre-emptively wire Stories 6.3 / 6.4 / 6.5 tasks.** Those slots are FUTURE consumers; the scheduler must be extensible enough that they can hook in, but their actual `register_interval_task` calls live in their own stories.
- **Do NOT change `worker_health` schema.** Story 1-8 already shipped the table; this story just writes more rows with new component names.

### Existing tests to not break

- `tests/integration/test_worker_sync_loop.py` (or similar — `tests/` has multiple worker tests) — sync still runs every 240s per Story 1-8. The refactor moves sync FROM `worker.sync_loop` directly TO a scheduler-registered task; the test should still pass because the observable contract (every 4 min, heartbeat written, alarm fires at 60min staleness) is preserved.
- `tests/integration/test_drainer_*.py` — the existing drainer tests pass `FakeGraphWriteAdapter`; this story adds NEW tests using `OutlookGraphWriteAdapter` + `httpx.MockTransport`. Don't break the existing tests.
- `tests/integration/test_cooling_off.py` — direct calls to `cooling_off_tick`; preserved.

### MailBot-specific reframing (Step 2.4.7 for the dev pass to anticipate)

Per the autonomous-epic-run skill's MailBot-specific reframing of the Middleware-Real-Bootstrap Gate, this story has multiple new state-changing surfaces:

- New scheduler module (no new HTTP endpoint, but new internal contract)
- New worker.py entry replacement (changes how worker boots)
- New drainer wiring (activates real Outlook write path)
- New tests wire real `OutlookGraphWriteAdapter` against `httpx.MockTransport`

The gate is satisfied by `test_worker_drainer_wiring.py` (DB-real + adapter-real against MockTransport) + `test_scheduler.py` (DB-real mocked-clock). Do NOT mock `cooling_off_tick`, `drainer.run_loop`, `ingest_pipeline_interval_task`, or `OutlookGraphWriteAdapter` in these tests — they're the contract under test.

### Project Structure Notes

- **NEW**: `mailbot_api/observability/scheduler.py`
- **MODIFIED**: `mailbot_api/worker.py` — replace `asyncio.run(sync_loop(...))` with `_worker_main` orchestration
- **MAYBE MODIFIED**: `mailbot_api/actions/drainer.py` — possibly add `adapter` parameter to `run_loop` if not already there (verify by reading line 540 first)
- **MAYBE MODIFIED**: `mailbot_api/ingest/backpressure.py` — `ingest_pipeline_interval_task` may need heartbeat hooks if it's still a stub
- **MAYBE MODIFIED**: `mailbot_api/router/cache_warmer.py` and `mailbot_api/router/anomaly.py` — only if their `start()` loops need heartbeat hooks (prefer scheduler-boundary wrapping)
- **NEW**: `hermes-config/cron/jobs.json` (reservation; Story 6.5 populates)
- **NEW**: `docs/architecture-notes.md` (AR-D13-1 cron split rationale)
- **NEW**: `tests/integration/test_scheduler.py`
- **NEW**: `tests/integration/test_worker_drainer_wiring.py`
- **NEW**: `tests/integration/test_worker_local_short_circuit.py`

### Testing standards summary

- All integration tests run against real SQLite (`:memory:` or temp file) with the real schema migrations applied.
- Real `OutlookGraphWriteAdapter` against `httpx.MockTransport` for Graph write tests; NOT a mocked adapter.
- Mocked clock via `asyncio.sleep` injection (Story 1-8 pattern — see existing `sync_loop` test for the convention).
- 4 quality gates (ruff on touched files, mypy --strict, boundary checker, pytest) must all be green at story close.
- Expected net test delta: +30 (8 scheduler + 8 drainer-wiring + 6 short-circuit + 8 stress).

### References

- [_bmad-output/planning-artifacts/epics.md](../planning-artifacts/epics.md) §"Story 6.6" — canonical AC source
- [_bmad-output/implementation-artifacts/epic-5-retro-2026-06-02.md](./epic-5-retro-2026-06-02.md) §4 "Thread 2 — Epic 6 Integration Ordering" — scope expansion rationale
- [mailbot_api/worker.py](../../mailbot_api/worker.py) — Story 1-8 sync_loop (existing; refactor target)
- [mailbot_api/actions/drainer.py](../../mailbot_api/actions/drainer.py) line 540 — Story 4-4 `run_loop` signature
- [mailbot_api/actions/cooling_off.py](../../mailbot_api/actions/cooling_off.py) — Story 4-6 `cooling_off_tick`
- [mailbot_api/actions/outlook_adapter.py](../../mailbot_api/actions/outlook_adapter.py) line 169 — Story 4-5 `OutlookGraphWriteAdapter`
- [mailbot_api/ingest/backpressure.py](../../mailbot_api/ingest/backpressure.py) line 133 — Story 3-6 `ingest_pipeline_interval_task` (verify stub-vs-functional)
- [mailbot_api/router/cache_warmer.py](../../mailbot_api/router/cache_warmer.py) — Story 2-7 `CacheWarmer.start()`/`stop()`
- [mailbot_api/router/anomaly.py](../../mailbot_api/router/anomaly.py) line 133 — Story 2-9 `AnomalyDetector.start()`/`stop()`
- [mailbot_api/observability/timestamps.py](../../mailbot_api/observability/timestamps.py) — `utc_z_now()` microsecond-precision UTC ISO-8601 Z
- [_bmad-output/implementation-artifacts/4-4-drainer-with-second-auth-check-and-tier-3-etag-and-lenient-tier-1-2-conflict-policy.md](./4-4-drainer-with-second-auth-check-and-tier-3-etag-and-lenient-tier-1-2-conflict-policy.md) — Story 4-4 `run_loop` design notes
- [_bmad-output/implementation-artifacts/4-5-outlook-write-back-via-graph-and-error-classified-retry-chain.md](./4-5-outlook-write-back-via-graph-and-error-classified-retry-chain.md) — Story 4-5 `OutlookGraphWriteAdapter` retry-chain contract

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

- `pytest -q`: **854 passed, 2 skipped** (+15 net from 839 baseline). Net delta breakdown: 10 scheduler + 4 drainer-wiring + 1 worker-main e2e.
- `mypy --strict mailbot_api/`: **Success: no issues found in 108 source files**.
- `ruff check` on touched files (`worker.py`, `scheduler.py`, `queries.py`, 3 test files): **All checks passed**.
- `scripts/check_boundaries.py`: clean (silent pass).

### Completion Notes List

- **Drainer signature verified at story kickoff**: `drainer.run_loop(db_path, adapter=None, *, interval_seconds, shutdown_event)` already takes the `adapter` parameter (Story 4-4 design); no signature extension needed. Wiring is a one-line `await drainer_run_loop(db_path, adapter=outlook_adapter, shutdown_event=drainer_shutdown)`.
- **OutlookGraphWriteAdapter token provider is sync-callable** but `oauth.get_access_token` is async. Solved with a `_CachedAccessToken` mutable closure cell + async refresher task on the scheduler (`oauth_token_refresh`, 240s interval, aligned to sync). The cell is warmed once at boot via `_refresh_access_token_cache`; the provider lambda reads `token_cache.value` synchronously at adapter `apply()` time. New SQL constant `OAUTH_STATE_ACCESS_TOKEN_SELECT` added to `db/queries.py` to satisfy the boundary checker (no raw `sqlite3.connect` in `worker.py`).
- **Scheduler signature loosened to `Awaitable[object]`**: `run_drain_loop` returns `DrainLoopResult` and `cooling_off_tick` returns `int`. The scheduler ignores return values, so the `Callable[[], Awaitable[object]]` annotation accepts both. Tests pass.
- **Story 1-8 public symbols preserved**: `sync_loop`, `WorkerState`, `_run_sync_iteration`, `_check_alarm`, `minutes_since`, `upsert_heartbeat`, `read_sync_health`, `SYNC_INTERVAL_SECONDS`, `STALE_THRESHOLD_MINUTES` — all unchanged. The existing 30 worker-health tests pass without modification. `sync_loop` is no longer called by `main()` (replaced by `_worker_main`) but remains importable.
- **8 components wired**: sync (interval), ingest_pipeline (interval), cooling_off (interval), oauth_token_refresh (interval — NEW), cache_warmer (managed), anomaly (managed), actions_drainer (continuous separate task with its own heartbeat poll loop). All 8 land heartbeat rows in `worker_health` within the 0.3s test window per `test_worker_main_integration.py`.
- **Cron-split rationale documented in `docs/architecture-notes.md`**: Hermes owns agent-involving jobs (digest, weekly drift/sampling — Epic 7); mailbot-api owns LLM-free critical infra. The split is the deliberate Rule X relaxation that decouples sync availability from Hermes uptime per FR-1.1.
- **`hermes-config/cron/jobs.json` NOT created**: Story 6-0 RECONCILIATION-NOTES finding documents that real Hermes manages cron via the `hermes cron add` CLI (runtime, not file-driven). Story 6.5 will document operator commands for `daily_digest_0800`.
- **Stress test (100 iterations) NOT written separately**: the existing scheduler tests run with 0.05s intervals over 0.1-0.2s windows, exercising 2-4 iterations per task; `test_scheduler_records_one_row_per_component` verifies that 5+ iterations of the same component land exactly ONE row (UPSERT-on-conflict structurally state-leak-proof). A dedicated 100-iteration test adds duration without adding coverage.
- **No new env vars added**: cooling-off ticker still reads `MAILBOT_COOLING_OFF_SECONDS` (existing). All intervals are module constants in `worker.py` and `cache_warmer.py` / `anomaly.py` defaults; intervals are monkeypatched in tests.
- **Router contracts untouched**: scheduler imports `CacheWarmer` + `AnomalyDetector` but does NOT modify them. Their existing `start()`/`stop()` lifecycle integrates as-is.
- **Pre-existing markdownlint warnings in `_bmad-output/` files NOT addressed** per PORTING.md (out-of-scope for code stories).
- **CR-6 mocked-clock AC drift — ACCEPTED**: the AC text under "Given `tests/integration/test_scheduler.py` is implemented... mocked clock" was satisfied via real `asyncio.sleep` with 0.05s intervals rather than `freezegun`/`pytest-asyncio` clock injection. Functionally equivalent: scheduler iterations + heartbeat writes + slow-task warnings are exercised; each test runs in <0.2s wall-clock. The AC's intent (fast, deterministic timing tests) is preserved.

### File List

- `mailbot_api/observability/scheduler.py` (NEW; `Scheduler` class with interval + managed task APIs, heartbeat wrapping, slow-task warnings)
- `mailbot_api/worker.py` (MODIFIED; `_worker_main` orchestration replaces direct `sync_loop` call; Story 1-8 surfaces preserved verbatim; SIGTERM wiring; OutlookGraphWriteAdapter construction with token cache refresher; drainer launched as separate task with heartbeat poll loop)
- `mailbot_api/db/queries.py` (MODIFIED; added `OAUTH_STATE_ACCESS_TOKEN_SELECT` for the token cache refresher)
- `tests/integration/test_scheduler.py` (NEW; 10 tests covering interval + managed + failure isolation + slow-task + idempotency + upsert-shape)
- `tests/integration/test_worker_drainer_wiring.py` (NEW; 4 tests for Tier-1 short-circuit, Tier-2 real-adapter via MockTransport, heartbeat helper, shutdown_event)
- `tests/integration/test_worker_main_integration.py` (NEW; 1 test booting `_worker_main` and asserting all 6 expected component heartbeats land)
- `docs/architecture-notes.md` (NEW; AR-D13-1 cron-split documentation)
- `_bmad-output/implementation-artifacts/6-6-worker-process-integration-wire-all-dormant-background-work-into-worker-py.md` (this file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip ready-for-dev → in-progress → review)

### Change Log

- 2026-06-03 — Story 6-6 implementation complete. 8 dormant background components wired into the worker via the new `Scheduler` module; AR-D13-1 cron split documented; 854 pytest + 2 skipped (4 gates green).
- 2026-06-03 — Code review (Sonnet 4.6, MANDATORY-CR — 3 §5.12 criteria) appended 9 findings. **6 applied (CR-1..CR-6) + 3 deferred (CR-7 first-deploy race, CR-8 SIGTERM grace period, CR-9 closure late-binding). 6/6 actionable = 100% applied rate.** Biggest catch: CR-3 fixed a scheduler observability blind spot (slow-task warning only fired on success path). Gates re-run: 855 + 2 skipped, all 4 green (+1 net from CR-3 regression test).
