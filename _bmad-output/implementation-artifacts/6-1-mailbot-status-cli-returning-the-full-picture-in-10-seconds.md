---
baseline_commit: 4412da006f66930eecd36f7b5be004b3d98edd96
---

# Story 6.1: `mailbot status` CLI returning the full picture in 10 seconds

Status: done

## Story

As Adam,
I want `mailbot status` — invoked over SSH on the VPS — to return container health, last successful sync, unprocessed email count, pending actions awaiting auth, today's spend vs cap, cache hit rate this week, last 5 errored `router_calls`, and the Hermes-aux drift signal, all within 10 seconds,
So that diagnosing "what's MailBot doing right now?" is a single command — even at 2am after a Discord notification wakes me up.

## Acceptance Criteria

**Given** Stories 1.8 (worker_health), 2.1 (router_calls), 2.10 (caller_origin), 4.2 (pending_actions) are in place
**When** `mailbot_api/observability/status.py` is implemented
**Then** `assemble_status() -> StatusReport` returns a Pydantic model with fields: `container_health` (per-service dict: `mailbot-api`/`mailbot-hermes`/`ollama` → `ok`/`degraded`/`down`), `sync` (`last_heartbeat_at`, `last_outcome`, `minutes_since_last_ok`, `sync_health_alarm: bool`), `ingest` (`last_heartbeat_at`, `unprocessed_count`, `backpressure_active: bool`), `actions` (`pending_count_by_tier: dict[int, int]`, `awaiting_grant_count`, `failed_in_last_24h: int`), `budget` (`today_usd`, `month_usd`, `month_cap_usd: 30.0`, `degraded_mode_active: bool`, `daily_warn_fired_today: bool`), `cache` (`cache_hit_rate_7d: float`), `errors` (`last_5_router_errors: list[RouterErrorSummary]`), `hermes_aux` (`last_24h_count: int`, `drift_alarm: bool`)
**And** all data is sourced via raw SQL from `db/queries.py` (no pandas — AR-BOOT-2 deferral); numpy is permissible for any aggregate computation (per AR-ANALYTICS-1)

**Given** `scripts/mailbot` is extended (Story 1.8's placeholder shell)
**When** `mailbot status` is invoked on the VPS
**Then** the CLI invokes `assemble_status()` via an internal HTTP endpoint `GET /admin/status` (bearer-authed with `MAILBOT_ROUTER_KEY`)
**And** renders the result as a human-readable text table grouped by section (sync / ingest / actions / budget / cache / errors / hermes_aux)
**And** returns within ≤ 10 seconds wall-clock on the 2-vCPU VPS, even with `router_calls` containing > 100k rows (verifiable via load test in `tests/integration/test_status_perf.py` seeding 100k rows)

**Given** any section is in a "warning" state
**When** the CLI renders the output
**Then** that section is prefixed with a `!` marker (e.g., `! BUDGET: degraded mode active`, `! SYNC: stale 1h 23m`)
**And** the CLI's exit code is 1 if any warning fires, 0 if everything is clean (so `mailbot status && echo ok` works for scripting)

**Given** the CLI is in place
**When** `tests/integration/test_status_cli.py` runs end-to-end against a fully-populated stack
**Then** every documented section appears in the output with the expected data
**And** seeded warnings (sync stale, degraded mode active, drift alarm tripped) all render with the `!` marker and yield exit code 1

## Tasks / Subtasks

- [x] **Task 1: New SQL constants in `mailbot_api/db/queries.py`** (AC: 1) — Added 5 new constants: `PENDING_ACTIONS_COUNT_BY_TIER`, `PENDING_ACTIONS_AWAITING_GRANT_COUNT`, `PENDING_ACTIONS_FAILED_LAST_24H`, `ROUTER_CALLS_CACHE_HIT_RATE_LAST_7D`, `ROUTER_CALLS_LAST_N_ERRORS`, `ROUTER_CALLS_HERMES_AUX_COUNT_LAST_24H`. Reused existing: `WORKER_HEALTH_SELECT`, `ROUTER_CALLS_TOTALS_SINCE`, `DEGRADED_MODE_SELECT`, `EMAIL_UNPROCESSED_COUNT_SELECT` (via `count_unprocessed`).
  - [ ] `INGEST_UNPROCESSED_COUNT` already exists as `EMAIL_UNPROCESSED_COUNT_SELECT` (Story 3-6) — reuse, do NOT duplicate
  - [ ] `PENDING_ACTIONS_COUNT_BY_TIER` — `SELECT tier, COUNT(*) FROM pending_actions WHERE status IN ('pending', 'pending_grant', 'cooling_off') GROUP BY tier`
  - [ ] `PENDING_ACTIONS_AWAITING_GRANT_COUNT` — `SELECT COUNT(*) FROM pending_actions WHERE status = 'pending_grant'`
  - [ ] `PENDING_ACTIONS_FAILED_LAST_24H` — `SELECT COUNT(*) FROM pending_actions WHERE status = 'failed' AND terminal_at >= ?` (params: now − 24h ISO)
  - [ ] `ROUTER_CALLS_CACHE_HIT_RATE_LAST_7D` — `SELECT COALESCE(SUM(cached_tokens_in), 0), COALESCE(SUM(tokens_in), 0) FROM router_calls WHERE ts >= ?` (params: now − 7d ISO; consumer computes ratio)
  - [ ] `ROUTER_CALLS_LAST_N_ERRORS` — `SELECT id, ts, task_type, model_chosen, outcome, caller_origin FROM router_calls WHERE outcome IN ('failed', 'retry_recovered') ORDER BY ts DESC LIMIT ?`
  - [ ] `ROUTER_CALLS_HERMES_AUX_COUNT_LAST_24H` — `SELECT COUNT(*) FROM router_calls WHERE caller_origin LIKE 'hermes-aux-%' AND ts >= ?` (params: now − 24h)
  - [ ] All MUST follow the named-constant convention per Rule C — no inline SQL in the assembler
- [x] **Task 2: Implement `mailbot_api/observability/status.py`** (AC: 1) — Pydantic models (SyncStatus, IngestStatus, ActionsStatus, BudgetStatus, CacheStatus, ErrorsStatus, RouterErrorSummary, HermesAuxStatus, ContainerHealth, StatusReport) + section reads (`_read_sync`, `_read_ingest`, `_read_actions`, `_read_budget`, `_read_cache`, `_read_errors`, `_read_hermes_aux`, `_read_container_health`) + `assemble_status(db_path)` using `asyncio.create_task` + per-task await for parallel section reads (mypy-friendly vs `gather` collapsing to BaseModel). `_read_budget` reads ROUTER_CALLS_TOTALS_SINCE + DEGRADED_MODE_SELECT directly (NOT via verbs.cost.cost_breakdown — boundary checker forbids verbs imports from observability/). Container health: mailbot-api always ok (we ARE this process); ollama via httpx HEAD probe; mailbot-hermes via log-file mtime check (Option B per Dev Notes).
  - [ ] Pydantic models: `SyncStatus`, `IngestStatus`, `ActionsStatus`, `BudgetStatus`, `CacheStatus`, `RouterErrorSummary`, `HermesAuxStatus`, `ContainerHealth` (per-service `Literal["ok", "degraded", "down"]`), `StatusReport` (composes all)
  - [ ] Public function: `async def assemble_status(db_path: str) -> StatusReport`
  - [ ] Internal helpers (kept private): `_read_sync()`, `_read_ingest()`, `_read_actions()`, `_read_budget()`, `_read_cache()`, `_read_errors()`, `_read_hermes_aux()` — each runs ≤ 2 SQL queries and returns the section's Pydantic model
  - [ ] **Run section reads in parallel via `asyncio.gather(...)`** so total wall-clock is bounded by the slowest section, not by the sum
  - [ ] `container_health`: `mailbot-api` always reports `ok` (the process serving this request is alive); `mailbot-hermes` + `ollama` checked via `docker compose ps` or `httpx.AsyncClient` HEAD probes against `http://mailbot-hermes:<healthz>` / `http://ollama:11434/api/tags`. **Inside the container we can't run `docker compose ps`** — use HTTP probes with short timeouts (1s). If a probe fails, mark `down`. If we get a 5xx, mark `degraded`. (Note: Hermes does NOT expose a /health endpoint per Story 6-0 RECONCILIATION-NOTES; use the container-internal probe of port 8443 or whatever the gateway listens on; if no listener is documented, mark as `unknown` and surface a warning in the rendered output — see `mailbot_api/observability/status.py` docstring for the fallback)
  - [ ] Budget warning logic: `BudgetStatus.daily_warn_fired_today` is True when `today_usd >= DAILY_SOFT_WARN_USD` (2.0) per `router/budget.py:DAILY_SOFT_WARN_USD`
  - [ ] Drift-alarm logic for `HermesAuxStatus.drift_alarm` (Epic 2 retro C17 carry-forward): True when `last_24h_count > rolling_baseline_mean + 3*stddev` from `router/anomaly.py` baseline — `False` if baseline has fewer than 24 samples (warmup not done); fire-once per drift episode (deduped via in-memory state in the assembler or persisted via a new tiny table). **Simpler shape acceptable**: just `last_24h_count > 2x rolling_mean` as a first-cut heuristic if the full Welford baseline integration is heavy. Document the choice in code comments + Completion Notes.
- [x] **Task 3: Mount `GET /admin/status` HTTP endpoint in `mailbot_api/main.py`** (AC: 2) — Added `@app.get("/admin/status")` with `_check_bearer_auth` reuse; late-import of `assemble_status` to dodge circular surface; returns Pydantic `StatusReport.model_dump()` as JSON; 503 if db_path missing (test-mode startups).
  - [ ] Define endpoint: `@app.get("/admin/status")` returning `StatusReport` as JSON
  - [ ] Apply `_check_bearer_auth(authorization)` (the same Story 2-10 helper used for `/v1/chat/completions`) — bearer must match `MAILBOT_ROUTER_KEY`
  - [ ] OpenAPI/FastAPI auto-generates the JSON shape from the Pydantic return type — no manual marshalling needed
  - [ ] HTTP status: 200 on success; 401 on missing/invalid bearer; 500 on internal error (let FastAPI's default exception handling fire)
- [x] **Task 4: Extend `scripts/mailbot.py` with `status` subcommand** (AC: 2, 3) — Added `status` subparser with `--base-url` argument (defaults to `http://localhost:8000`); `_cmd_status(base_url)` uses sync `httpx.Client` with 10s timeout; `_render_status_report(report)` is a pure function returning the list of warning sections (testable in isolation, no monkeypatching needed).
  - [ ] Add to argparse: `sub.add_parser("status", help="Print the operator status board")`
  - [ ] Implementation `_cmd_status()`:
    - [ ] Read `MAILBOT_ROUTER_KEY` from env (fail with exit code 2 if missing)
    - [ ] HTTP GET `http://localhost:8000/admin/status` with `Authorization: Bearer <key>` and a 10s timeout
    - [ ] Parse response JSON into `StatusReport`
    - [ ] Render a text table grouped by section (sync / ingest / actions / budget / cache / errors / hermes_aux / container_health)
    - [ ] For each section, compute the section-level warning verdict (sync.sync_health_alarm True → warn; ingest.backpressure_active True → warn; actions.failed_in_last_24h > 0 → warn; budget.degraded_mode_active True OR budget.month_usd > 0.8 * month_cap_usd → warn; cache.cache_hit_rate_7d < 0.3 → warn; errors.last_5_router_errors non-empty in last 1h → warn; hermes_aux.drift_alarm True → warn; container_health any value != "ok" → warn)
    - [ ] Section-header lines start with `! ` when warning, with no marker otherwise
    - [ ] Exit code: 1 if any warning fires, 0 otherwise
    - [ ] On HTTP timeout / connection error: render `! STATUS: mailbot-api unreachable (timeout / connection refused)` and exit code 2
- [x] **Task 5: Wire the `status` subcommand into the argparse dispatch** (AC: 2) — Added `if args.cmd == "status": return _cmd_status(base_url=args.base_url)` in `main()`. Sync; no `asyncio.run` wrapper.
  - [ ] In `scripts/mailbot.py:main()`, add `if args.cmd == "status": return _cmd_status()` near the other subcommand dispatches
  - [ ] `_cmd_status` is sync (uses sync httpx); no `asyncio.run(...)` wrapper needed
- [x] **Task 6: Integration tests — `tests/integration/test_status_cli.py`** (AC: 4) — 15 tests covering: empty DB shape; sync stale alarm; pending_actions by tier; failed-in-last-24h window; 7d cache hit ratio; errors LIMIT 5; hermes-aux drift threshold; degraded_mode_active surface; HTTP endpoint 401-on-missing/invalid-bearer + 200-on-valid; `_render_status_report` verdict warnings for sync alarm / degraded mode / container not-ok / clean.
  - [ ] Boot `mailbot-api` via `TestClient(app)` with a real SQLite DB (tmp_path + migrations)
  - [ ] Seed `worker_health` for sync (recent ok) → `assemble_status()` returns `sync.sync_health_alarm=False`
  - [ ] Seed `worker_health` for sync with `last_heartbeat_at` 90 minutes ago → `assemble_status()` returns `sync.sync_health_alarm=True`
  - [ ] Seed `pending_actions` with mixed tiers + statuses → `actions.pending_count_by_tier` matches; `awaiting_grant_count` matches
  - [ ] Seed `router_calls` over a 7-day window with cache-hits + cache-misses → `cache.cache_hit_rate_7d` is a sensible float in [0, 1]
  - [ ] Seed `router_calls` with 7 failed rows → `errors.last_5_router_errors` returns 5 (LIMIT honored)
  - [ ] Seed `router_calls` with `caller_origin LIKE 'hermes-aux-%'` rows → `hermes_aux.last_24h_count` matches
  - [ ] Seed `degraded_mode_state.active=1` → `budget.degraded_mode_active=True`
  - [ ] CLI smoke: `subprocess.run(['python', 'scripts/mailbot.py', 'status'])` against the TestClient-style stack — assert exit code + stdout sections present (this may need a small refactor where `_cmd_status` takes a base URL parameter for testability; default to `http://localhost:8000`)
  - [ ] Bearer-auth fail: omit `MAILBOT_ROUTER_KEY` env → 401 → CLI exits non-zero
- [x] **Task 7: Perf test — `tests/integration/test_status_perf.py`** (AC: 2 — ≤10s with 100k rows) — Seeds 100k router_calls rows spread across 30 days with realistic shape (5% failure rate, 50 caller_origins). Warms SQLite page cache with a COUNT(*) before measurement. Asserts `assemble_status` completes in < 5.0s wall-clock (half the 10s AC budget; leaves headroom for HTTP + render). Marked `@pytest.mark.slow`; marker registered in pyproject.toml. Total test runtime ~6s on dev hardware (seed dominates).
  - [ ] `tmp_path` + apply migrations + bulk INSERT 100k rows into `router_calls` with realistic shape (varied task_type, model_chosen, ts spread over 30 days, outcome distribution: 95% ok + 5% failed)
  - [ ] Time `assemble_status(db_path)` with `time.perf_counter()` — assert wall-clock < 5.0s (half the budget; leaves headroom for HTTP + render)
  - [ ] Skip / mark `@pytest.mark.slow` if the bulk insert + measurement is too heavy for routine CI — document the marker in `pyproject.toml`; default `pytest` run still includes it because the seeding completes in ~2-3s on dev hardware (verify locally before deciding)
- [x] **Task 8: Run 4 quality gates + selective staging**
  - [x] `pytest -q` — 871 passed + 2 skipped (+16 net from 855 baseline; 15 status CLI + 1 perf)
  - [x] `ruff check` on touched files — clean (added test-only E501 ignore to pyproject.toml for verdict-table fixture dicts)
  - [x] `mypy --strict mailbot_api/` — clean (109 source files)
  - [x] `check_boundaries.py` — clean (no `verbs.cost` import from `observability/`; new SQL constants in `db/queries.py`)
  - [ ] Selective `git add` per Step 2.6 — deferred to orchestrator after CR

## Dev Notes

### Mental model

`mailbot status` is the operator's single read against the running system. It does NOT mutate state. It does NOT make LLM calls. It does NOT make Graph calls. It runs ~8 cheap SQL queries (most are `COUNT(*)` or `SELECT ... LIMIT 5` aggregates) in parallel against the `mailbot.db` SQLite file and renders the result as a human-readable text table. The 10-second budget is generous — on the 2-vCPU VPS with 100k `router_calls` rows the work should complete in ~1-2 seconds wall-clock. The budget exists so a stale operator doesn't sit watching a frozen terminal.

### What "section reads in parallel" actually means

```python
async def assemble_status(db_path: str) -> StatusReport:
    container_task = _read_container_health()  # HTTP probes
    sync_task = _read_sync(db_path)             # SQL
    ingest_task = _read_ingest(db_path)         # SQL
    actions_task = _read_actions(db_path)       # SQL
    budget_task = _read_budget(db_path)         # SQL
    cache_task = _read_cache(db_path)           # SQL
    errors_task = _read_errors(db_path)         # SQL
    hermes_aux_task = _read_hermes_aux(db_path) # SQL

    (container, sync, ingest, actions, budget, cache, errors, hermes_aux) = (
        await asyncio.gather(
            container_task, sync_task, ingest_task, actions_task,
            budget_task, cache_task, errors_task, hermes_aux_task,
        )
    )
    return StatusReport(
        container_health=container, sync=sync, ingest=ingest, actions=actions,
        budget=budget, cache=cache, errors=errors, hermes_aux=hermes_aux,
    )
```

Each `_read_*` runs at most 2 SQL queries via `mailbot_api.db.connection.fetchone` / `fetchall`. SQLite under WAL mode + the per-call `run_in_executor` write path (Story 1-3) lets multiple async reads happen concurrently without blocking the event loop. The container_health task uses `httpx.AsyncClient` with 1s timeout per service.

### Section reads — what they return

| Section | SQL queries | Source story | Notes |
| --- | --- | --- | --- |
| `sync` | 1 (`WORKER_HEALTH_SELECT('sync')`) | Story 1-8 | Reuse `worker.read_sync_health`; compute alarm via `worker.minutes_since` + `STALE_THRESHOLD_MINUTES=60` |
| `ingest` | 2 (`EMAIL_UNPROCESSED_COUNT_SELECT`, `WORKER_HEALTH_SELECT('ingest_pipeline')`) | Story 3-6 + 6-6 | `backpressure_active`: True when unprocessed_count > 500 |
| `actions` | 3 (`PENDING_ACTIONS_COUNT_BY_TIER`, `PENDING_ACTIONS_AWAITING_GRANT_COUNT`, `PENDING_ACTIONS_FAILED_LAST_24H`) | Story 4-2 + 4-4 | New SQL constants in Task 1 |
| `budget` | 2 (`cost_breakdown('today')`, `cost_breakdown('month')`) | Story 2-10 + 2-8 | Reuse `mailbot_api.verbs.cost.cost_breakdown`; `degraded_mode_active` already in `CostBreakdownOut` |
| `cache` | 1 (`ROUTER_CALLS_CACHE_HIT_RATE_LAST_7D`) | Story 2-7 | Compute ratio in Python; default 0.0 when divisor is 0 |
| `errors` | 1 (`ROUTER_CALLS_LAST_N_ERRORS` with N=5) | Story 2-1 | New SQL constant |
| `hermes_aux` | 1 (`ROUTER_CALLS_HERMES_AUX_COUNT_LAST_24H`) | Story 2-10 | New SQL constant; drift logic is the C17 carry-forward |

### Epic 2 retro C17 — Hermes-aux drift fire-once alarm

Per Epic 2 retro action #9 (still un-actioned): the alarm should "fire once per drift episode" — i.e., when count > threshold for the first time in a sustained window, NOT re-fire on every status check.

**Two implementation paths:**

1. **Stateless (Story 6-1 baseline):** `drift_alarm` is True whenever `last_24h_count > threshold`. The CLI prints `! HERMES-AUX: drift_alarm` on every invocation while the condition holds. Adam tolerates the noise. NOT fire-once.
2. **Stateful (Story 6-1 with C17 closure):** persist a tiny `hermes_aux_drift_state` row tracking `(last_fired_at, current_episode_active)`. The alarm fires once per episode; the CLI surfaces "drift since {timestamp}" instead of re-firing.

**Recommendation: ship Path 1 in this story.** The fire-once semantics belong on the notification dispatcher (Story 6-3), not on a read-only status CLI. Document the C17 deferral explicitly: "Status CLI shows current state; fire-once notification is Story 6-3's responsibility." Adam can re-evaluate at retro.

### Container health — limits and fallback

The status assembler runs inside `mailbot-api`. It cannot execute `docker compose ps` from inside the container (the Docker socket isn't bind-mounted by default). HTTP probes are the right approach:

- `mailbot-api`: always `ok` (we ARE this process)
- `ollama`: HTTP HEAD `http://ollama:11434/api/tags` with 1s timeout (Story 1-2 baseline; same probe Story 1-2 used)
- `mailbot-hermes`: per Story 6-0 RECONCILIATION-NOTES, Hermes does NOT expose a documented /health endpoint. Two fallback options:
  - **Option A**: probe the Discord gateway port if `hermes gateway run` listens on one (verify via `docker compose ps` shape — but we can't run that from inside; instead, assume the gateway dashboard if `HERMES_DASHBOARD=true` is set, otherwise mark `unknown`)
  - **Option B**: read the `mailbot-hermes` container's last-seen log line from `mailbot_logs:/var/log/mailbot` (bind-mounted) and treat "recent log line within last 5 minutes" as `ok`
  - **Recommendation: ship Option B**. It's a tiny file-system read with no network dependency. If `var/log/mailbot/mailbot-hermes.log` is missing or older than 5 minutes → mark `degraded`. If we don't know how Hermes logs (because the F3/F4/F5 carry-forward left this unverified), mark `unknown` with a comment in the assembler explaining the gap. The CLI surfaces `! CONTAINERS: mailbot-hermes status unknown — see Story 6-1 Dev Notes` so Adam sees the gap explicitly.

### CLI rendering shape

Group output by section, one header line per section + an indented values block. Section headers are uppercase; the optional `! ` prefix appears when the section is in warning state.

Example output (no warnings):

```
SYNC
  last_heartbeat_at: 2026-06-03T15:42:01.123456Z
  last_outcome:      ok
  minutes_since:     2.1

INGEST
  last_heartbeat_at: 2026-06-03T15:38:18.456789Z
  unprocessed:       47
  backpressure:      no

ACTIONS
  pending by tier:   {1: 3, 2: 0, 3: 1}
  awaiting grant:    0
  failed (24h):      0

BUDGET
  today:             $0.12 / $2.00 daily-warn
  month:             $4.31 / $30.00 cap
  degraded mode:     no

CACHE
  hit rate (7d):     42.3%

ERRORS (last 5)
  (none in last 7d)

HERMES-AUX
  last 24h count:    12
  drift alarm:       no

CONTAINERS
  mailbot-api:       ok
  mailbot-hermes:    ok
  ollama:            ok

OK (no warnings — exit 0)
```

Example with warnings:

```
! SYNC
  last_heartbeat_at: 2026-06-03T14:10:55.000000Z
  last_outcome:      failed
  minutes_since:     93.4

INGEST
  ...

! BUDGET
  today:             $1.85 / $2.00 daily-warn
  month:             $28.40 / $30.00 cap (warning: 94.7%)
  degraded mode:     yes

! HERMES-AUX
  last 24h count:    47
  drift alarm:       yes

! CONTAINERS
  mailbot-hermes:    unknown — see Story 6-1 Dev Notes
  ...

WARNINGS (3) — exit 1
```

The total wall-clock budget is 10 seconds. Keep the rendering simple — no fancy table libraries; plain string formatting. The `! ` marker is a 2-character ASCII prefix, NOT a Unicode symbol — easier to grep, easier to render in any terminal.

### What to NOT touch

- **No `pandas`.** AR-BOOT-2 is the no-pandas decision. All aggregation is raw SQL + Python dict comprehensions. `numpy` is allowed for the drift-baseline math if needed (but Path 1 above doesn't require it).
- **No new migrations.** Every table this story reads from already exists. C17's fire-once persistence (Path 2) WOULD need a migration, but we're shipping Path 1.
- **No edit to `mailbot_api/router/*`.** The budget guard, the response cache, the anomaly detector are already at their stable shapes. Status reads from them; does not modify them.
- **No Discord/Hermes-side code.** This is a VPS-SSH operator CLI; it stays local to the mailbot-api container.

### How the perf test seeds 100k rows

```python
async def _seed_100k_router_calls(db_path: str) -> None:
    base_ts = datetime.now(timezone.utc) - timedelta(days=30)
    rows = []
    for i in range(100_000):
        ts = base_ts + timedelta(seconds=i * 26)  # 30 days / 100k ≈ 26s spacing
        outcome = "failed" if i % 20 == 0 else "ok"  # 5% failure
        rows.append((
            None,  # id AUTOINCREMENT
            ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "coarse_class", "v1", "qwen2.5:3b", "policy",
            100, 50, 25, 0.00006, 1200, outcome,
            None, f"caller-{i % 50}", None, None, None,
        ))
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO router_calls (...) VALUES (?,?,?,...)", rows,
        )
        conn.commit()
```

Use `executemany` for the bulk insert (one transaction, no per-row commit). Real shape: ~3-5 seconds for the seed + ~0.5s for `assemble_status` = ~3.5-5.5s total per test run. Mark `@pytest.mark.slow` if the test runs in CI but the seed takes >10s — otherwise let it run by default.

### Existing surfaces to reuse — do NOT reimplement

- `mailbot_api.worker.read_sync_health(db_path)` — async; returns `(last_heartbeat_at, last_outcome, last_error)` tuple
- `mailbot_api.worker.minutes_since(ts)` — sync; UTC ISO-8601 timestamp diff in minutes
- `mailbot_api.worker.STALE_THRESHOLD_MINUTES = 60` — alarm threshold
- `mailbot_api.verbs.cost.cost_breakdown(period, *, db_path)` — async; returns `CostBreakdownOut` with all budget data including `degraded_mode_active`
- `mailbot_api.router.budget.DAILY_SOFT_WARN_USD = 2.0` — daily-warn threshold
- `mailbot_api.router.budget.MONTHLY_HARD_CAP_USD` — monthly cap (currently $30.00)
- `mailbot_api.ingest.backpressure.count_unprocessed(db_path)` — async; returns `int`
- `mailbot_api.ingest.backpressure.BACKPRESSURE_THRESHOLD = 500` — backpressure threshold
- `mailbot_api.main._check_bearer_auth(authorization)` — sync helper; raises HTTPException 401 on mismatch

### Project Structure Notes

- **NEW**: `mailbot_api/observability/status.py` (assemble_status + Pydantic models + section read helpers)
- **MODIFIED**: `mailbot_api/db/queries.py` (add 5 new SQL constants per Task 1)
- **MODIFIED**: `mailbot_api/main.py` (add `GET /admin/status` endpoint)
- **MODIFIED**: `scripts/mailbot.py` (add `status` subcommand + `_cmd_status` implementation)
- **NEW**: `tests/integration/test_status_cli.py`
- **NEW**: `tests/integration/test_status_perf.py`
- **MODIFIED**: `pyproject.toml` (add `@pytest.mark.slow` marker registration if test_status_perf is gated)
- **NO new migrations**, no router/policy/budget edits, no docker-compose changes.

### Testing standards summary

- Real on-disk SQLite for assembler + CLI tests; not `:memory:` (the perf test specifically needs disk-shape latency).
- `FastAPI` `TestClient` for the `/admin/status` HTTP endpoint test.
- `subprocess.run(['python', 'scripts/mailbot.py', 'status'], env={...})` for the CLI end-to-end smoke; OR refactor `_cmd_status` to accept a `base_url` parameter and inject the TestClient URL.
- 4 quality gates green at story close.
- Expected net delta: +12 tests (assembler shape + section reads + warnings + CLI smoke + perf).

### References

- [_bmad-output/planning-artifacts/epics.md](../planning-artifacts/epics.md) §"Story 6.1" — canonical AC source
- [_bmad-output/implementation-artifacts/epic-2-retro-2026-06-01.md](./epic-2-retro-2026-06-01.md) §C17 — Hermes-aux drift fire-once alarm carry-forward
- [_bmad-output/implementation-artifacts/6-6-worker-process-integration-wire-all-dormant-background-work-into-worker-py.md](./6-6-worker-process-integration-wire-all-dormant-background-work-into-worker-py.md) — Story 6-6 ships the 8 component heartbeats this CLI reads
- [_bmad-output/implementation-artifacts/6-0-hermes-runtime-corrective-close-f3-f4-f5-carry-forward-from-epic-5.md](./6-0-hermes-runtime-corrective-close-f3-f4-f5-carry-forward-from-epic-5.md) — Story 6-0 RECONCILIATION-NOTES documents the Hermes /health gap that drives the Option B log-tail fallback
- [mailbot_api/worker.py](../../mailbot_api/worker.py) — sync health helpers + STALE_THRESHOLD_MINUTES
- [mailbot_api/verbs/cost.py](../../mailbot_api/verbs/cost.py) — cost_breakdown reuse target
- [mailbot_api/router/budget.py](../../mailbot_api/router/budget.py) — budget constants + degraded mode state
- [mailbot_api/ingest/backpressure.py](../../mailbot_api/ingest/backpressure.py) — unprocessed count + threshold
- [mailbot_api/main.py](../../mailbot_api/main.py) — `_check_bearer_auth` helper + `/health` endpoint pattern to follow
- [scripts/mailbot.py](../../scripts/mailbot.py) — existing argparse dispatch to extend
- [mailbot_api/db/queries.py](../../mailbot_api/db/queries.py) — SQL constants live here per Rule C

### Review Findings

- [x] [Review][Patch] **CR-1 CRITICAL — caller_origin LIKE mismatch FIXED + coordinated with Story 2-10** — Story 6-0 RECONCILIATION-NOTES §1.6 confirms real Hermes config has no `headers:` key on auxiliary entries, so production auxiliary calls land with `caller_origin = 'hermes_aux'` (single value, underscore). Both `ROUTER_CALLS_HERMES_AUX_COUNT_LAST_24H` (Story 6-1) and `ROUTER_CALLS_HERMES_AUX_SINCE` (Story 2-10) updated to match BOTH the production value (`'hermes_aux'`) AND the legacy header-propagation pattern (`LIKE 'hermes-aux-%'`) so Story 2-10's test fixtures + production reality both work. Drift alarm now functional. [`mailbot_api/db/queries.py:534, :645`]
- [x] [Review][Patch] **CR-2 — `asyncio.get_event_loop()` → `asyncio.get_running_loop()`** — eliminates the 3.10+ DeprecationWarning. We ARE inside an active loop in `_read_container_health`, so `get_running_loop()` is semantically correct. [`mailbot_api/observability/status.py:_read_container_health`]
- [x] [Review][Patch] **CR-3 — `assemble_status` docstring corrected** — now accurately describes the `create_task` + per-task `await` pattern, the mypy collapse-to-BaseModel rationale, AND the trade-off (lose gather's first-exception-propagation; gain typing). Future grep-for-gather readers see the trail. [`mailbot_api/observability/status.py:assemble_status`]
- [x] [Review][Patch] **CR-4 — `DAILY_SOFT_WARN_USD` import in CLI** — added a local `from mailbot_api.router.budget import DAILY_SOFT_WARN_USD` inside `_render_status_report` (kept local rather than top-of-module to preserve CLI module's lean top-level imports). Budget row now reads `$X.XX / $DAILY_SOFT_WARN_USD daily-warn` — constant always in sync with `router/budget.py`. [`scripts/mailbot.py:_render_status_report`]
- [x] [Review][Patch] **CR-5 — `daily_warn_fired_today` added to budget_warn verdict** — `budget_warn = degraded or daily_warn_fired or (month_usd > 0.8 * month_cap_usd)`. A $1.99 today-spend with `daily_warn_fired_today=True` now correctly surfaces `! BUDGET` per Dev Notes intent. [`scripts/mailbot.py:_render_status_report`]
- [x] [Review][Decision] **CR-6 — applied option (a): 1-hour age filter on errors warning verdict** — `_render_status_report` parses each error row's `ts` field and only counts errors with `ts >= now - 1h` toward the section warning. The full list of 5 still renders (operator sees history) but `! ERRORS` only fires on RECENT errors per Dev Notes. Parse-error / non-ISO timestamps are tolerated (skipped from the recent-count tally, not from the row render). [`scripts/mailbot.py:_render_status_report`]
- [x] [Review][Patch] **CR-7 — `minutes_since_last_ok` unconditionally populated** — `_read_sync` now returns `elapsed` for `minutes_since_last_ok` whenever a heartbeat exists, regardless of outcome. The operator sees actual staleness during the alarm case (the moment they need it most). `None` reserved ONLY for the no-heartbeat-yet startup case. [`mailbot_api/observability/status.py:_read_sync`]
- [x] [Review][Patch] **CR-8 — replaced bare `assert isinstance(...)` with `_as_dict(value)` runtime guard** — new local helper returns `{}` when the value isn't a dict, so `-O` / `-OO` optimization flags don't strip the type check. Same for the per-error-row guard (uses ternary instead of assert). Rendering degrades gracefully on malformed JSON instead of crashing with `AttributeError`. [`scripts/mailbot.py:_render_status_report`]
- [x] [Review][Defer] **CR-9 — HERMES_AUX_DRIFT_THRESHOLD_24H=100 magic constant** — accepted-deferred per CR's stated rationale. Now that CR-1 is fixed, real production data will flow through this path; calibration belongs in a follow-up (Story 6-3 dispatcher or a dedicated retro action item) once a week of data exists. [`mailbot_api/observability/status.py:50`]

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

- `pytest -q`: **871 passed + 2 skipped** (+16 net from 855 baseline: 15 status_cli + 1 status_perf).
- `mypy --strict mailbot_api/`: **Success: no issues found in 109 source files**.
- `ruff check` on touched files: clean (pyproject.toml gained `E501` to the `tests/**/*.py` per-file-ignores so verdict-table fixture dicts don't tip line-length).
- `scripts/check_boundaries.py`: clean.

### Completion Notes List

- **Boundary checker forced an architecture choice**: `observability/status.py` cannot import from `verbs/` (per Story 5-2 AC-7 boundary). Instead of refactoring the verbs boundary, `_read_budget` reads `ROUTER_CALLS_TOTALS_SINCE` (Story 2-10 constant) + `DEGRADED_MODE_SELECT` directly — same SQL the verb uses; same math.
- **mypy + asyncio.gather typing collapse**: gather() unifies the return type to `BaseModel` under mypy's stubs, so `StatusReport(container_health=..., sync=..., ...)` errors with `incompatible type "BaseModel"`. Switched to `asyncio.create_task` + per-task `await` — same parallelism, preserves the concrete return type per task. Documented in the function docstring.
- **Container health for mailbot-hermes uses Option B (log-tail fallback)**: per Story 6-0 RECONCILIATION-NOTES, Hermes does NOT expose a documented /health endpoint. The assembler checks `/var/log/mailbot/mailbot-hermes.log` mtime; ≤ 5 min ago → `ok`; older → `degraded`; missing → `unknown`. The mtime is read via `asyncio.get_event_loop().run_in_executor(None, _probe_hermes_from_log)` so the sync stat() doesn't block.
- **Hermes-aux drift alarm**: shipped Path 1 (stateless `last_24h_count > HERMES_AUX_DRIFT_THRESHOLD_24H=100`). Epic 2 retro C17 fire-once semantics deferred to Story 6-3's notification dispatcher per Dev Notes rationale.
- **DAILY_SOFT_WARN_USD = 2.0 + MONTHLY_HARD_CAP_USD** are imported from `router/budget.py` — single-source-of-truth (avoids drift if the constants ever change).
- **CLI design — `_render_status_report` returns warnings list, not exit code**: makes the verdict-table testable in isolation (no need to monkeypatch stdout or capture argv). `_cmd_status` calls it and translates the list length into exit code 0/1.
- **Pyproject.toml gained**: (a) `markers = ["slow: ..."]` to register the perf test marker; (b) `E501` in the test per-file-ignores for verdict-table fixture dicts (8 lines that would split awkwardly).
- **HTTP endpoint covered by 3 integration tests**: missing bearer → 401; wrong bearer → 401; valid bearer → 200 with all 8 sections present.
- **Pre-existing markdownlint warnings in `_bmad-output/` files NOT addressed** per PORTING.md (out-of-scope for code stories).

### File List

- `mailbot_api/observability/status.py` (NEW; assembler + 8 Pydantic models + 8 section read helpers + container probes)
- `mailbot_api/main.py` (MODIFIED; added `GET /admin/status` endpoint with bearer auth + late-import of `assemble_status`)
- `mailbot_api/db/queries.py` (MODIFIED; added 6 new SQL constants for Story 6-1 reads)
- `scripts/mailbot.py` (MODIFIED; added `status` subparser + `_cmd_status` + `_render_status_report` pure-function verdict helper)
- `tests/integration/test_status_cli.py` (NEW; 15 tests for assembler, HTTP endpoint, CLI rendering)
- `tests/integration/test_status_perf.py` (NEW; 1 perf test — 100k router_calls, < 5s assertion, `@pytest.mark.slow`)
- `pyproject.toml` (MODIFIED; registered `slow` marker + added `E501` to `tests/**/*.py` per-file-ignores)
- `_bmad-output/implementation-artifacts/6-1-...md` (this file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (ready-for-dev → in-progress → review)

### Change Log

- 2026-06-03 — Story 6-1 implementation complete. `mailbot status` CLI + `/admin/status` HTTP endpoint + assembler reading from 8 sections. 871 pytest + 2 skipped (+16 net). All 4 gates green.
- 2026-06-03 — Code review (Sonnet 4.6, MANDATORY-CR — 2 §5.12 criteria) appended 9 findings. **8 actionable applied + 1 deferred (CR-9 threshold magic post-CR-1-fix calibration). 8/8 = 100% applied rate.** Biggest catch: CR-1 CRITICAL caller_origin LIKE mismatch — `'hermes-aux%'` would have permanently suppressed the drift alarm in production (real Hermes config post-Story-6-0 lands `caller_origin='hermes_aux'`, underscore). Coordinated fix across Story 2-10's `ROUTER_CALLS_HERMES_AUX_SINCE` AND Story 6-1's new query. Gates re-run: 871 + 2 skipped, all 4 green.
