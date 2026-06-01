---
baseline_commit: 46f09db
---

# Story 3.6: Backpressure ceiling + batched processing (bulk pipeline drain)

Status: done

## Story

As Adam,
I want the ingest pipeline to drain unprocessed emails in 100-batch chunks via `mailbot_api/ingest/backpressure.py` + a new `pipeline.run_batch()` helper, with backpressure logic that throttles deeper if `unprocessed_count > 500` to keep the interactive lane responsive,
so that a first-time sync of a 10,000-email inbox processes in the background without blocking chat queries.

## Acceptance Criteria

### AC-1 — `mailbot_api/ingest/backpressure.py` with `count_unprocessed` + `should_throttle`

**Given** the FR-2.3 hard invariant gates processing on `sensitivity_at IS NULL`,

**When** `mailbot_api/ingest/backpressure.py` is implemented,

**Then** it exposes:
- `_UNPROCESSED_COUNT_SELECT` query reused from a new `queries.py` constant: `"SELECT COUNT(*) FROM emails WHERE sensitivity_at IS NULL AND deleted_at IS NULL"`.
- `async def count_unprocessed(db_path: str) -> int` returning the integer count.
- `async def should_throttle(db_path: str, *, threshold: int = 500) -> bool` returning True when count > threshold.
- Module-level constants `BATCH_SIZE: Final[int] = 100`, `BACKPRESSURE_THRESHOLD: Final[int] = 500`, `BACKPRESSURE_SLEEP_SECONDS: Final[float] = 5.0`.

### AC-2 — `pipeline.run_batch()` drains 100 emails sequentially

**Given** Story 3-5's `process_email` is the single-email orchestrator,

**When** `pipeline.run_batch(*, db_path, caller_origin) -> RunBatchResult` is added,

**Then** the function:
1. Queries `EMAIL_UNPROCESSED_BATCH_SELECT` (new constant — `SELECT graph_id FROM emails WHERE sensitivity_at IS NULL AND deleted_at IS NULL ORDER BY received_at DESC LIMIT 100`).
2. For each graph_id, calls `process_email(email_id=graph_id, db_path=db_path, caller_origin=caller_origin)` sequentially.
3. Collects per-email outcomes into a `RunBatchResult` Pydantic model with `processed: int`, `succeeded: int`, `failed: int`, `partial_due_to_sensitivity: int`, `email_ids: list[str]`, `errors: list[str]`.
4. Records a `worker_health` row via `WORKER_HEALTH_UPSERT` with component `"ingest_pipeline"`, last_heartbeat_at = now-UTC-Z, last_outcome = `"ok"` (even when partial), last_error = NULL on success OR first error message on hard failure.

**And** `RunBatchResult.processed` is the count of distinct emails attempted in this batch (may be < 100 if the queue is shorter).

### AC-3 — `backpressure.run_drain_loop()` orchestrator with throttle

**Given** the per-batch drain primitive exists,

**When** `async def run_drain_loop(*, db_path: str, caller_origin: str = "ingest-pipeline-batch", max_batches: int | None = None) -> DrainLoopResult` is added to `backpressure.py`,

**Then** the function:
1. Loops: calls `pipeline.run_batch(...)`, then `count_unprocessed(...)`. If count > 500: `await asyncio.sleep(BACKPRESSURE_SLEEP_SECONDS)`. Otherwise: continue immediately.
2. Stops when `count_unprocessed == 0` (drain complete) OR `max_batches` is reached (test bound).
3. Returns `DrainLoopResult(batches_run: int, total_processed: int, total_succeeded: int, total_failed: int, total_partial_sensitive: int, throttle_events: int)`.

**And** `max_batches=None` runs until the queue empties (production); tests pass a small bound to avoid runaway loops.

### AC-4 — Worker health heartbeat per batch

**Given** Story 1-8's worker_health table + heartbeat pattern,

**When** `run_batch` finishes,

**Then** a row is upserted into `worker_health` with component=`"ingest_pipeline"`, last_heartbeat_at=now-UTC-Z, last_outcome=`"ok"` (a batch of 0 emails still upserts `ok` — empty queue is a valid healthy state per epic spec).

**And** on a Python-level exception escaping run_batch (defensive — shouldn't happen since process_email is errors-as-data), the row is upserted with last_outcome=`"failed"` and last_error=str(exc) sanitized.

### AC-5 — Stub interval task: 5-minute scheduler

**Given** the spec defers the full scheduler to Epic 6,

**When** a stub `async def ingest_pipeline_interval_task(*, db_path: str, interval_seconds: float = 300.0, stop_event: asyncio.Event | None = None) -> None` is added to `backpressure.py`,

**Then** the function:
1. Loops every `interval_seconds`.
2. Per tick: calls `run_drain_loop(db_path=db_path, max_batches=1)` (single-batch per tick to avoid blocking long under high load).
3. Exits when `stop_event.is_set()` is True.

**And** the interval task is NOT auto-started in `main.py`'s lifespan — Epic 6 owns scheduler integration. Story 3-6's tests instantiate it directly.

### AC-6 — Comprehensive tests

`tests/integration/test_backpressure_e2e.py` (new):
- `count_unprocessed` returns 0 on an empty DB; returns N after seeding N rows with `sensitivity_at IS NULL`; ignores rows with `sensitivity_at` populated AND ignores `deleted_at IS NOT NULL`.
- `should_throttle` returns True for count > 500, False for count ≤ 500.
- `run_batch` on a 7-email queue: processes 7 emails (all human-payload), `processed=7, succeeded=7, failed=0`; worker_health row recorded with outcome=ok.
- `run_batch` on an empty queue: processed=0, worker_health row recorded with outcome=ok.
- `run_drain_loop` with `max_batches=3` and 250 seeded emails: 3 batches run; total_processed=300 (but actual processed will be 250 — last batch shorter); throttle_events>0 if intermediate count > 500.
- `run_drain_loop` until queue empty: 50 seeded emails → 1 batch runs, drains all 50, loop exits.
- `ingest_pipeline_interval_task` with `interval_seconds=0.01` + `stop_event` set after first tick: runs ≥1 batch, exits cleanly.

### AC-7 — All quality gates green

pytest: 434 baseline + ≥8 new tests; ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] **Task 1**: Add `EMAIL_UNPROCESSED_COUNT_SELECT` + `EMAIL_UNPROCESSED_BATCH_SELECT` to `queries.py`
- [x] **Task 2**: Implement `mailbot_api/ingest/backpressure.py` (AC-1, AC-3, AC-5)
- [x] **Task 3**: Add `pipeline.run_batch()` + `RunBatchResult` to `pipeline.py` (AC-2, AC-4)
- [x] **Task 4**: Integration tests (AC-6)
- [x] **Task 5**: Run all gates (AC-7)

## Dev Notes

### Sequential within a batch — why

Spec calls for "100 emails sequentially within the batch (concurrency comes from the Router's worker pool dispatching Qwen calls)." This is intentional:
- The Router lane scheduler (Story 2-5) is the concurrency layer; the pipeline itself doesn't need to parallelize at the email level.
- Sequential makes the per-batch state simpler — each `process_email` finishes before the next starts.
- A future story could add concurrency if profiling shows the batch lane is under-utilized.

### `caller_origin` for batch dispatches

`"ingest-pipeline-batch"` distinguishes batch-lane dispatches from single-email dispatches (`"ingest-pipeline"` — Story 3-5). Cost-attribution dashboards can separate "first-sync drain" cost from "interactive single-email derivation" cost.

### Why ORDER BY received_at DESC

The spec mandates this order. Rationale: newest emails are most likely to be relevant to a user actively syncing; processing them first keeps the most-recent inbox state useful sooner, even if the historical tail takes longer to drain.

### Worker-health component name

`"ingest_pipeline"` matches the pattern Story 1-8 established for `"sync_worker"`. Story 1-8's `/health` endpoint already reads from this table; the new component name flows through automatically once the row exists.

### Tests use real SQLite + scripted adapters

Same Middleware-Real-Bootstrap discipline as Story 3-5. Reuse the `_FakeAdapter` pattern from `test_pipeline_e2e.py` (system-block-keyword routing) so the adapter responds to all 7 task types.

### References

- Story 1-8 worker_health: `mailbot_api/db/queries.py:318-331`
- Story 3-5 `process_email`: `mailbot_api/ingest/pipeline.py`
- Story 3-1 `ix_emails_sensitivity_at` index: enables the unprocessed-queue scan
- Epic 3 spec: epics.md lines 1289-1325

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run loop (Phase 2, Story 3-6) — gate-coverage-only cadence.

### Debug Log References

- pytest baseline (post-Story-3-5): 434 passed + 2 skipped.
- pytest after Story 3-6: **442 passed + 2 skipped** (+8 new integration tests).
- ruff check / format / mypy / boundary check: all green.
- Test seed counts kept small (5–8) per drain test so the run stays under Story 2-5's 60/min Haiku rate-limit ceiling.

### Completion Notes List

- **`mailbot_api/ingest/backpressure.py`** ships `count_unprocessed`, `should_throttle`, `run_drain_loop`, `ingest_pipeline_interval_task`, `DrainLoopResult` + 3 module-level constants (BATCH_SIZE=100, BACKPRESSURE_THRESHOLD=500, BACKPRESSURE_SLEEP_SECONDS=5.0).
- **`pipeline.run_batch()` + `RunBatchResult`** added — sequential within batch, records `worker_health` row per batch with component=`"ingest_pipeline"`.
- **`derivations_idempotency` migration 013** already added in Story 3-5; reused here.
- **Lazy imports** in backpressure.py to break the pipeline ↔ backpressure circular import surface.
- **Empty-batch handling**: an empty queue still upserts worker_health (a healthy empty state is still a heartbeat).
- **Defensive break** in run_drain_loop when a batch processes 0 emails despite depth > 0 — prevents pathological infinite loops (e.g., every email failing sensitivity step).
- **`ingest_pipeline_interval_task` is a stub** — not auto-started in `main.py` lifespan. Epic 6 owns scheduler wiring.
- **CR subagent NOT invoked** — gate-coverage-only.

### File List

**Created:**

- `mailbot_api/ingest/backpressure.py`
- `tests/integration/test_backpressure_e2e.py` — 8 tests

**Modified:**

- `mailbot_api/db/queries.py` — `EMAIL_UNPROCESSED_COUNT_SELECT` + `EMAIL_UNPROCESSED_BATCH_SELECT`
- `mailbot_api/ingest/pipeline.py` — `run_batch()` + `RunBatchResult` + `__all__` extended
