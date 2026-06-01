---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.7: Response cache + cache warmer

Status: done

## Story

As Adam, I want a SQL-backed response cache keyed on `hash(prompt + model + temperature)` with per-task TTL in `policy.yaml`, plus a cache warmer that re-pings high-volume tasks every 4 minutes (aligned to Anthropic's 5-minute ephemeral TTL), so that identical Router calls are free on repeat AND high-volume tasks pay cached-input pricing.

## Acceptance Criteria

**AC-1** Migration `007_response_cache.sql` (renumbered from epic-spec `006` because Story 2-1 took `006_router_calls.sql`). `response_cache(cache_key PRIMARY KEY, task_type, model, result_json, cost_usd, cached_at, ttl_seconds, hit_count DEFAULT 0)` + `ix_response_cache_task_type_cached_at`.

**AC-2** Extend `PolicyEntry` with `response_cache_ttl_seconds: int = 0` (default 0 → caching disabled) and `cache_warm: bool = False`.

**AC-3** `mailbot_api/router/response_cache.py` (NEW) exposes:
- `compute_cache_key(model: str, temperature: float, system: str, user: str) -> str` — sha256 hex
- `async def lookup(db_path, cache_key) -> RouterResult | None` — returns cached result if exists AND not expired, else None. Increments `hit_count` on hit.
- `async def insert(db_path, cache_key, task_type, model, result_json, cost_usd, ttl_seconds) -> None`

**AC-4** Wire into `ask_router`: pre-dispatch lookup, post-dispatch insert. On hit: build a `RouterResult(ok=True, cost_usd=0, model_used=f"{model}+response_cache", cached_tokens_in=0)` and STILL write a `router_calls` row with `outcome="ok"`, `model_chosen_reason="response_cache_hit"` for observability. The audit row records 0 cost.

**AC-5** Cache write is gated on `policy_entry.response_cache_ttl_seconds > 0` AND on `RouterResult.ok=True` AND on the output being JSON-serializable via `.model_dump_json()`.

**AC-6** `mailbot_api/router/cache_warmer.py` (NEW) exposes `CacheWarmer` class with `start()` / `stop()`. Every `warm_interval_seconds` (default 240 = 4 min): iterate `policy.tasks` for entries with `cache_warm=True`; issue `ask_router(task_type=..., content=..., caller_origin="cache-warmer")` with a static probe content. Failures log `event="cache_warmer.failed"` and continue.

**AC-7** `limits.enforce_rate_limit` skip `caller_origin="cache-warmer"`. Extend signature to take `caller_origin` and short-circuit.

**AC-8** Tests:
- `test_response_cache.py` — compute_cache_key determinism + collision avoidance, lookup hit, lookup miss (no row), lookup expired (TTL passed), insert + readback, hit_count increments
- `test_router.py` extended — cache hit short-circuits adapter; second identical call returns cached RouterResult; both calls produce router_calls rows; cache-warmer origin bypasses rate limit
- `test_cache_warmer.py` — interval task fires; warm-flagged task gets probed; failure logged

**AC-9** All gates green.

## Tasks

- [x] Migration 007 + queries.RESPONSE_CACHE_INSERT/SELECT/UPDATE_HIT_COUNT (AC-1)
- [x] Extend PolicyEntry fields (AC-2)
- [x] Implement response_cache.py (AC-3, AC-5)
- [x] Wire into ask_router (AC-4)
- [x] Implement cache_warmer.py (AC-6)
- [x] Extend limits.enforce_rate_limit (AC-7)
- [x] Tests across (AC-8)
- [x] Gates (AC-9)

## Dev Notes

### Migration renumber chain

Epic spec said `006_response_cache.sql`. Story 2-1 took 006 for router_calls. Shifting to `007_response_cache.sql`. Downstream migrations renumber accordingly: 2-8's `degraded_mode_state` → `008_degraded_mode.sql`; 2-9's anomaly + pause → `009_anomaly_baseline.sql` / `010_pause_state.sql`.

### Why response_cache row is queried EVERY call, not just hot tasks

The `response_cache_ttl_seconds > 0` flag in policy controls whether INSERTS happen; LOOKUPS check unconditionally because policy says "if a row exists, use it." This means changing TTL=0→N starts caching new entries; existing cached rows still serve hits until expiry.

### Why `model_used = "<original>+response_cache"`

Downstream cost-rollup queries can pattern-match on `model_used LIKE '%+response_cache%'` to identify cache-hit rows separately from actual dispatches.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Completion Notes List

- **Migration 007** (renumbered from epic-spec 006 because 006 belongs to router_calls per Story 2-1). Downstream Stories 2-8/2-9 will need 008/009/010 — flagging in epic-run-flags.
- **PolicyEntry extended** with `response_cache_ttl_seconds` (default 0 = disabled) and `cache_warm` (default false). Backward-compatible: existing `policy.yaml` entries without these fields still validate cleanly.
- **Wiring seams in router.py**: lookup at top of dispatch (after user_msg render); insert via `_maybe_cache_result()` helper at BOTH success returns (first-attempt and retry-recovered). Cache write failures are logged + swallowed — they must not clobber a successful Router call.
- **Cache hit fully short-circuits adapter**: `model_used="<original>+response_cache"`, `cost_usd=0`, `cached_tokens_in=0`, audit row `outcome="ok"` + `model_chosen_reason="response_cache_hit"`. Both calls produce router_calls rows (so cache effectiveness is queryable).
- **caller_origin="cache-warmer" bypasses rate limit** via `enforce_rate_limit` short-circuit. Story 2-7 test verifies: an interactive-budget-exhausted environment still permits a cache-warmer probe.
- **CacheWarmer is injectable** (`ask_router_fn` constructor param) so tests don't need transitive Router/adapter wiring; unit tests verify warm-flag iteration + per-task failure tolerance + idempotent stop.
- **No code review subagent** — Story 2-7 is mechanical (SQL CRUD + interval-task loop). Gate coverage is comprehensive: cache key determinism, TTL expiry, hit_count increment, warmer probe gating, rate-limit bypass.
- **283 passed + 2 skipped** (267 → 283, +16 net: 6 response_cache + 4 cache_warmer + 3 router cache-integration + 3 adjustments).

### File List

**Created:**

- `mailbot_api/db/migrations/007_response_cache.sql` — table + index
- `mailbot_api/router/response_cache.py` — compute_cache_key + lookup + insert
- `mailbot_api/router/cache_warmer.py` — CacheWarmer interval-task class
- `tests/unit/router/test_response_cache.py`
- `tests/unit/router/test_cache_warmer.py`

**Updated:**

- `mailbot_api/db/queries.py` — RESPONSE_CACHE_SELECT/INSERT/INCREMENT_HIT constants
- `mailbot_api/router/policy.py` — PolicyEntry adds `response_cache_ttl_seconds`, `cache_warm`
- `mailbot_api/router/router.py` — cache lookup + `_maybe_cache_result` helper + cache-hit RouterResult shape
- `mailbot_api/router/limits.py` — `enforce_rate_limit` accepts `caller_origin`, bypasses for cache-warmer
- `tests/unit/router/test_router.py` — extended template + 3 new cache-integration tests

## Change Log

- 2026-06-01 (claude-opus-4-7, autonomous-epic-run) — Story 2-7 implemented: SQL-backed response cache (migration 007) + CacheWarmer interval-task class + ask_router cache lookup/insert seams + rate-limit bypass for cache-warmer origin. 283 tests pass (+16 net). All gates green.

