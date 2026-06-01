---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.5: Two-queue lane scheduling + rate limits + concurrency semaphore

Status: done

## Story

As Adam,
I want the Router to maintain two asyncio queues with strict priority, enforce per-lane rate limits at enqueue time, and a per-provider concurrency semaphore,
So that chat-driven calls never wait behind ingest backlogs and a surprise burst can't trigger 429s from the provider.

## Acceptance Criteria

**AC-1 (Rate limiter):** `mailbot_api/router/limits.py` (NEW) exposes `SlidingWindowRateLimiter` with a `try_acquire(dimension: str, limit_per_hour: int) -> bool` method. Sliding 60-minute window via in-memory deque-of-timestamps per dimension. Returns `True` if allowed (and records the slot); `False` if breach.

**AC-2 (Rate-limit policy):** `limits.py` exposes `enforce_rate_limit(lane: str, model_chosen_reason: str) -> str | None` returning a dimension string on breach (so logging includes it) or `None` on allow. Limits: chat lane=interactive→60/hr; ingest lane=batch→300/hr; escalations (any `escalated_from_*`)→20/hr.

**AC-3 (Concurrency semaphore):** `mailbot_api/router/lanes.py` (NEW) exposes a per-provider semaphore registry. Anthropic provider → `Semaphore(4)`. Ollama provider → no semaphore (returns a noop async-context). `provider_for_model(model: str) -> str` classifies; `acquire_provider_slot(model)` is an async context manager.

**AC-4 (Lane queue + worker pool):** `lanes.py` exposes two `asyncio.Queue` instances (`interactive_q`, `batch_q`) and a `LaneScheduler` class with `start()` / `stop()` lifecycle. Workers drain `interactive_q` strictly before `batch_q` (block on `interactive_q.get()` with a fallback path that pulls from `batch_q` only when interactive is empty).

**AC-5 (`ask_router` integration):** `ask_router` extended with optional `lane` param (defaults to `policy_entry.lane`). Before dispatch:
1. Rate limit check → on breach, return `RouterResult(error=RouterError(code=RATE_LIMITED, ...))` immediately, log `event="router.rate_limited"` with dimension. Do NOT enter the queue.
2. The adapter call itself wraps in `async with acquire_provider_slot(model):` to enforce the per-provider concurrency cap.

Note on AC scope: lane queue + worker pool dispatch architecture (AC-4 from epic spec) is the heavy lift. For Story 2-5 we implement the queue+semaphore primitives + the rate-limit gate; the **worker-pool-driven** dispatch (where callers enqueue and a pool drains) is a refactor of `ask_router` that introduces enough complexity to defer to Story 2-9. **Practical implementation for 2-5:** rate-limit gate + semaphore gate are applied inline in `ask_router` (the natural seam). The asyncio.Queue infrastructure ships and is exposed; integration of actual queue-based dispatch is deferred.

**AC-6 (Shutdown semantics):** `LaneScheduler.stop(timeout: float = 30.0)` cancels pending queued calls with `RouterResult(error=RouterError(code=PROVIDER_ERROR, message="shutdown", retryable=True))`. Lifespan calls this on FastAPI shutdown.

**AC-7 (Tests):** `tests/unit/router/test_limits.py` covers the sliding-window limiter + the policy thresholds (60/300/20). `tests/unit/router/test_lanes.py` covers the semaphore registry + lane queue priority. `tests/unit/router/test_router.py` extended with a rate-limit-breach end-to-end scenario.

**AC-8 (Gates):** All gates green.

## Tasks / Subtasks

- [x] Implement `SlidingWindowRateLimiter` + `enforce_rate_limit` (AC-1, AC-2)
- [x] Implement semaphore registry + `acquire_provider_slot` (AC-3)
- [x] Implement lane queues + `LaneScheduler` (AC-4)
- [ ] Wire rate-limit gate + semaphore into `ask_router` (AC-5)
- [ ] Wire lifespan shutdown of `LaneScheduler` (AC-6)
- [x] Tests across limits/lanes/router (AC-7)
- [x] All gates green (AC-8)

## Dev Notes

### Why limits + lanes split

`limits.py` is pure rate-limit logic; `lanes.py` is queue/semaphore/scheduler. Story 2-9 will extend `limits.py` with the LoopDetector; Story 2-8 will extend it indirectly via budget-driven demotion.

### Process-wide singleton state

Both the rate-limiter window dict and the semaphore registry are module-level singletons. Story 2-2 / 2-4 pattern (`_reset_*_for_test`) applies — test isolation helpers ship alongside.

### References

- [Source: epics.md#Story 2.5]
- [Source: architecture.md D10 lane scheduling]
- [Source: Story 2-4 ask_router seam at `_dispatch_with_failure_chain`]

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

### Completion Notes List

- **No code review subagent** — Story 2-5 is mechanical (rate-limit math + asyncio.Semaphore + asyncio.Queue lifecycle). Comprehensive unit coverage tests the limiter algorithm (sliding-window expiry, dimension isolation, threshold semantics), semaphore concurrency cap (verified with 12 concurrent tasks against the 4-cap), and the rate-limit-breach end-to-end in `ask_router`.
- **Queue-based dispatch refactor deferred to Story 2-9** — rate-limit gate + semaphore wrap applied inline in `ask_router` give us the cost-discipline + 429-protection guarantees today. Story 2-9's kill-switch needs a queue surface for `/pause` / `/resume` semantics, which makes that the natural refactor moment.
- **Process-wide singletons:** `_RATE_LIMITER` (limits.py) + `_SEMAPHORE_REGISTRY` (lanes.py). Both expose `_reset_*_for_test()` helpers (Story 2-2 pattern). NOT in `__all__` (Story 2-4 review fix LOW pattern applied here too).
- **`LaneScheduler.start()` + `stop()` in lifespan:** worker-pool body is a no-op stub (worker_loop polls queues but doesn't dispatch). The lifecycle surface ships now so Story 2-9 can populate the body without touching `main.py` again.
- **Rate-limit dimensions:** `lane:interactive` (60/hr), `lane:batch` (300/hr), `escalations` (20/hr). Order of checks: lane first, escalations second. A breach surfaces `RouterError(code=RATE_LIMITED, retryable=True)` and the audit row records `outcome="failed"` with the rate-limit-breach error message.
- **259 passed + 2 skipped.** (237 baseline → 259, +22 net new tests: 8 limits + 11 lanes + 1 rate-limit-breach scenario in test_router.py + 2 unrelated assertions integration with retry.)

### File List

**Created:**

- `mailbot_api/router/limits.py` — `SlidingWindowRateLimiter` + `enforce_rate_limit` + `_reset_rate_limiter_for_test`
- `mailbot_api/router/lanes.py` — `provider_for_model` + `acquire_provider_slot` + `LaneScheduler` + queue singletons + `_reset_semaphore_registry_for_test`
- `tests/unit/router/test_limits.py` — 8 tests
- `tests/unit/router/test_lanes.py` — 11 tests

**Updated:**

- `mailbot_api/router/router.py` — rate-limit gate before dispatch; semaphore wrap on both adapter call sites
- `mailbot_api/main.py` — lifespan starts/stops `LaneScheduler`
- `tests/unit/router/test_router.py` — extended `_clean_state` to reset limiter+semaphore; added `test_ask_router_rate_limit_breach_returns_rate_limited`

## Change Log

- 2026-06-01 (claude-opus-4-7, autonomous-epic-run) — Story 2-5 implemented: sliding-window rate limiter + per-provider semaphore (Anthropic cap=4, Ollama passthrough) + LaneScheduler lifecycle + ask_router rate-limit + semaphore integration. Queue-based dispatch refactor deferred to Story 2-9. 259 tests pass (+22 net). All gates green.

