---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.2: `policy.yaml` schema + loader + watchfiles hot-reload

Status: done

## Story

As Adam,
I want `policy.yaml` to be the single source of truth for per-task routing decisions, with a Pydantic `PolicyTable` schema, a loader that validates on every read, and `watchfiles`-driven hot-reload that swaps the in-memory snapshot atomically (or leaves the running policy in place if validation fails),
So that I can tune routing decisions by editing one file with no restart and no risk of a malformed YAML breaking the running system.

## Context (why this story exists)

Story 2-1 established the audit/error shapes for the Router. Story 2-2 ships the **policy contract** — per-task routing decisions encoded in a YAML file watched at runtime. Every later Router story dispatches against `policy.tasks[task_type]`; if the schema or the snapshot semantics are wrong here, every downstream `ask_router` call inherits the bug.

Architecture §"D11: `policy.yaml` reload semantics" is unambiguous: **validation-or-no-swap with mid-call race acceptable**. In-flight calls finish under the pre-swap policy because each call captures its snapshot at dispatch; this story builds the capture point.

## Acceptance Criteria

**AC-1 (`PolicyEntry` + `PolicyTable` Pydantic models).** `mailbot_api/router/policy.py` (NEW FILE) defines:

- `class PolicyEntry(BaseModel)` with per-task fields:
  - `model: str` — the model id (e.g., `qwen2.5:3b-instruct-q4_K_M`, `claude-haiku-4-5-20251001`, `claude-opus-4-7`)
  - `prompt_version: str` — e.g., `v1`
  - `escalate: bool` — whether schema-validation failure triggers next-tier escalation (per Story 2-4's failure chain)
  - `max_tokens_out: int` — Layer-1 budget guard per FR-6.1, default 4000 if absent at load time (set via Pydantic `Field(default=4000)`)
  - `lane: Literal["interactive", "batch"]` — Story 2-5's queue scheduling
  - `sensitivity: Literal["normal", "sensitive", "confidential", "any"]` — Epic-4's sensitivity gate
  - `notes: str | None = None` — free-form documentation
  - `demotion_hypothesis: str | None = None` — required when escalating per Rule Ω "annotated DEMOTION HYPOTHESIS" pattern
  - `promotion_hypothesis: str | None = None` — symmetric to demotion
- `class PolicyTable(BaseModel)` with:
  - `tasks: dict[str, PolicyEntry]` — keyed by `task_type` string
  - `version: str` — opaque version identifier (string, not semver-enforced — operators decide their own discipline)
- Both models extend Pydantic v2 `BaseModel`; `model_config = ConfigDict(extra="forbid")` so a stray top-level key (typo) fails validation rather than silently passing.

**AC-2 (`PolicyValidationError`).** `mailbot_api/router/policy.py` exposes `class PolicyValidationError(Exception)` carrying a `details: str` attribute (Pydantic's `ValidationError` JSON-shaped error list, stringified — sanitized via `sanitize_error` from Story 2-1 to prevent any error path containing token/file/path data from leaking through the watchfiles log line). The exception's `__str__` returns `f"PolicyValidationError: {self.details}"`.

**AC-3 (`load_policy(path) -> PolicyTable`).** `mailbot_api/router/policy.py` exposes:

- `def load_policy(path: Path) -> PolicyTable` — reads the YAML file via `yaml.safe_load(...)` (NOT `yaml.load` — bandit S506; the project's ruff `S` rule will fail on `yaml.load` anyway), validates against `PolicyTable`, and raises `PolicyValidationError(details)` on any of: `FileNotFoundError`, YAML parse error, Pydantic `ValidationError`.
- The function is pure: it does NOT touch the module-level snapshot. The snapshot is set only by the loader-wrapper described in AC-4.

**AC-4 (`get_policy()` returns module-level snapshot).** `mailbot_api/router/policy.py` exposes:

- A module-level reference `_policy: PolicyTable | None = None` (initialized to `None`).
- `def get_policy() -> PolicyTable` — returns `_policy`. If `_policy is None`, raises `RuntimeError("policy not loaded — initial load_policy_into_snapshot() must succeed before get_policy() is called")`. This raise is acceptable here because `get_policy()` is called from inside the Router (FastAPI app already started) — the only way to hit a `None` snapshot is a programmer error (called `get_policy()` before `startup` ran).
- `def set_policy_snapshot(table: PolicyTable) -> None` — assigns `_policy = table` (single-reference atomic swap per architecture D11). This is the ONLY function that mutates `_policy`; the watcher and the startup loader both call it.

Note on threading/asyncio safety: Python's GIL guarantees single-reference assignment is atomic, so concurrent reads via `get_policy()` see either the old or the new snapshot, never a torn read. No lock needed.

**AC-5 (`policy.yaml` starter file).** Project-root config dir `router/` (NOT under `mailbot_api/router/` — per architecture line ~936-937 the configuration artifacts directory is a separate `router/` at the project root) gets `router/policy.yaml` (NEW FILE) seeded with at minimum:

- `version: "policy-v0-2026-06-01"`
- `tasks.coarse_class` — Qwen-tier entry, lane=batch, sensitivity=any, no escalation
- `tasks.sensitivity_class` — Qwen-tier entry, lane=batch, sensitivity=any (sensitivity classification is local-only per Rule Q; this task type itself is sensitivity-unconstrained because it IS the gate that determines sensitivity)
- `tasks.draft_reply` — Opus-tier entry, lane=interactive, sensitivity=any (drafts can include sensitive content; Epic-4's grant flow is what gates send-side), escalate=false, with `demotion_hypothesis` filled in (e.g., "Haiku v1 holds quality on short replies under 200 words; demote when corpus shows ≥0.85 calibrated score parity")

These three entries are the architecture's "brainstorm policy-v0 starter" reference. The exact model ids must match Story 2-3's Ollama adapter target (`qwen2.5:3b-instruct-q4_K_M`) and Story 2-6's Anthropic targets (`claude-haiku-4-5-20251001`, `claude-opus-4-7`) — but Story 2-2 ships only the YAML; Stories 2-3/2-6 ship the adapters that use those ids.

**AC-6 (watchfiles hot-reload — happy path).** `mailbot_api/router/policy.py` exposes:

- `async def policy_reload_loop(path: Path, *, stop_event: asyncio.Event | None = None) -> None` — runs `async for changes in awatch(path, stop_event=stop_event): ...` (using `watchfiles.awatch`). On each yielded change set:
  1. Call `load_policy(path)`.
  2. On success: call `set_policy_snapshot(new_table)` AND emit structured log line `_log.info("policy reloaded", extra={"event": "policy.reloaded", "version": new_table.version})`.
  3. On `PolicyValidationError`: emit `_log.error("policy reload failed", extra={"event": "policy.reload.failed", "details": err.details})` AND **do NOT** call `set_policy_snapshot` — the prior snapshot stays in place.
- The function is intended to be scheduled via `asyncio.create_task(policy_reload_loop(path, stop_event=app_stop_event))` from the FastAPI lifespan.

**AC-7 (mid-call race semantics).** Mid-call race is acceptable per architecture D11 — but it must be **demonstrably true** that an in-flight call uses the pre-swap snapshot. This story implements the seam by exposing a helper:

- `def snapshot_for_dispatch() -> PolicyTable` — semantically equivalent to `get_policy()` (returns the current `_policy`). The semantic difference is documentary: callers (Story 2-4's `ask_router`) call this once at dispatch time and pass the returned `PolicyTable` instance through the entire call's lifecycle. Concurrent reload + dispatch sees the **same** `PolicyTable` object until the call's `finally` block; subsequent dispatches see the new one. Verified by the AC-9 race test.

**AC-8 (startup contract — fail-fast on bad initial policy).** When the FastAPI app boots:

- The lifespan calls `load_policy(POLICY_YAML_PATH)` BEFORE starting the watcher.
- On success: `set_policy_snapshot(...)` is called; watcher task is created.
- On `PolicyValidationError`: lifespan re-raises (or equivalent abort) — the app does NOT start. Log line `event="policy.startup.failed"` is emitted before the abort. Exit code is non-zero (uvicorn handles this when the lifespan raises).

This story modifies `mailbot_api/main.py`'s `lifespan` to add the policy-load step. The watcher task is stored on `app.state.policy_watcher_task` so the shutdown branch can cancel it.

**AC-9 (graceful shutdown).** When the FastAPI app shuts down:

- The lifespan signals the watcher to stop (`stop_event.set()`).
- `await app.state.policy_watcher_task` — awaits clean exit (with a short timeout fallback; if the watcher hangs, log and proceed to avoid blocking shutdown).
- No zombie threads or tasks remain.

**AC-10 (unit tests — load_policy + validation paths).** `tests/unit/router/test_policy_load.py` (NEW FILE) covers:

- Happy path: load the actual `router/policy.yaml` starter; assert `PolicyTable` instance with ≥3 tasks.
- `FileNotFoundError` → `PolicyValidationError` with descriptive `details`.
- Malformed YAML (e.g., `\t- bad: indent\n`) → `PolicyValidationError`.
- Missing required field on a task (e.g., remove `model` from one task) → `PolicyValidationError` mentioning the offending task key.
- Extra top-level key (e.g., `versions: x` instead of `version: x`) → `PolicyValidationError` (proves `extra="forbid"`).
- Invalid `lane` enum value (`lane: triage`) → `PolicyValidationError`.
- Invalid `sensitivity` enum value → `PolicyValidationError`.

**AC-11 (integration tests — hot-reload + snapshot + race).** `tests/integration/test_policy_reload.py` (NEW FILE) covers:

- Hot-reload happy path: write a valid `policy.yaml` to `tmp_path`, start `policy_reload_loop` as a task, edit the file (change `version`), assert `get_policy().version` reflects the new value within ~1s (poll-with-timeout pattern).
- Hot-reload validation failure: write valid file, start watcher, edit file to invalid YAML; assert `get_policy()` still returns the prior valid snapshot AND a `policy.reload.failed` log line was emitted (capture via `caplog`).
- Mid-call race: snapshot a policy via `snapshot_for_dispatch()`, mutate the on-disk file to a different version, wait for reload to fire, assert the captured snapshot's `version` is still the pre-swap value (proves the seam works). Subsequent `snapshot_for_dispatch()` returns the new version.
- Graceful shutdown: start watcher with a stop_event, set the event, assert the task completes within a short timeout (no zombie).

**AC-12 (boundary enforcement).** `scripts/check_boundaries.py` is extended with a new rule: `yaml.safe_load` and `yaml.load` are only permitted in `mailbot_api/router/policy.py` (which is the only place we read `policy.yaml`). This prevents future stories from re-parsing the policy file elsewhere; downstream consumers MUST go through `get_policy()` / `snapshot_for_dispatch()`. Test extension lives in `tests/unit/test_lint_boundaries.py` with a new fixture.

**AC-13 (all gates green).** ruff, mypy --strict, boundary checker, pytest — all clean. No new mypy issues introduced. Baseline was 173 tests after Story 2-1; new tests bring the total higher.

## Tasks / Subtasks

- [x] **Task 1** — Create `router/policy.yaml` starter file (AC: #5)
  - [x] Subtask 1.1 — Write the three starter task entries with fully-populated fields
  - [x] Subtask 1.2 — Ensure model ids match Story 2-3 and 2-6 targets
- [x] **Task 2** — Implement `mailbot_api/router/policy.py` data shapes (AC: #1, #2)
  - [x] Subtask 2.1 — `PolicyEntry` with all per-task fields + `extra="forbid"`
  - [x] Subtask 2.2 — `PolicyTable` with `tasks: dict[str, PolicyEntry]` + `version: str`
  - [x] Subtask 2.3 — `PolicyValidationError` exception with `details` attribute
- [x] **Task 3** — Implement `load_policy(path)` (AC: #3)
  - [x] Subtask 3.1 — `yaml.safe_load` + Pydantic validation
  - [x] Subtask 3.2 — Wrap `FileNotFoundError` / `yaml.YAMLError` / `ValidationError` in `PolicyValidationError`
  - [x] Subtask 3.3 — `sanitize_error` the `details` before storage
- [x] **Task 4** — Implement `get_policy()` / `set_policy_snapshot()` / `snapshot_for_dispatch()` (AC: #4, #7)
  - [x] Subtask 4.1 — Module-level `_policy: PolicyTable | None`
  - [x] Subtask 4.2 — `get_policy()` with the RuntimeError on None
  - [x] Subtask 4.3 — `set_policy_snapshot()` single-reference assignment
  - [x] Subtask 4.4 — `snapshot_for_dispatch()` semantic helper
- [x] **Task 5** — Implement `policy_reload_loop(path, *, stop_event)` (AC: #6)
  - [x] Subtask 5.1 — `async for changes in awatch(...)` loop
  - [x] Subtask 5.2 — Happy-path swap + structured log
  - [x] Subtask 5.3 — Validation-failure log + no swap
- [x] **Task 6** — Wire FastAPI lifespan startup + shutdown (AC: #8, #9)
  - [x] Subtask 6.1 — Read `mailbot_api/main.py`'s existing lifespan; insert load_policy + watcher start AFTER the migration runner step
  - [x] Subtask 6.2 — Resolve `POLICY_YAML_PATH` via `config.get_secret` (or a new `config.get_path` helper) — env var `MAILBOT_POLICY_PATH` with default `/app/router/policy.yaml` (container default) and a project-root default for dev
  - [x] Subtask 6.3 — On startup `PolicyValidationError`, log `event="policy.startup.failed"` and re-raise
  - [x] Subtask 6.4 — Shutdown: `stop_event.set()` + `await` task with timeout
- [x] **Task 7** — Extend `scripts/check_boundaries.py` with `yaml.safe_load` / `yaml.load` allowlist (AC: #12)
  - [x] Subtask 7.1 — Define `_YAML_LOAD_ALLOW = frozenset({"mailbot_api/router/policy.py"})`
  - [x] Subtask 7.2 — Detect via `ast.Attribute` (`yaml.safe_load`, `yaml.load`) and `ast.ImportFrom`
- [x] **Task 8** — Tests: `tests/unit/router/test_policy_load.py` (AC: #10)
- [x] **Task 9** — Tests: `tests/integration/test_policy_reload.py` (AC: #11)
- [x] **Task 10** — Tests: boundary-checker fixture for `yaml.load` outside policy.py (AC: #12)
- [x] **Task 11** — All gates green (AC: #13)

### Review Findings

- [x] [Review][HIGH] `MAILBOT_SKIP_DB=1` early-return path in lifespan skips policy load entirely — `get_policy()` raises `RuntimeError` for any downstream Router call in test-mode [mailbot_api/main.py:57-60] — When `MAILBOT_SKIP_DB=1`, the lifespan returns before reaching the policy-load block, leaving `_policy = None`. Any future integration test that sets `SKIP_DB=1` for DB bypass but then exercises a Router endpoint (Story 2-4+) will crash at `snapshot_for_dispatch()` with an opaque `RuntimeError` rather than a clear misconfiguration message. Either policy load must be moved outside the DB-skip guard, or a second guard / stub must initialize `_policy` in SKIP_DB mode.

- [x] [Review][Decision] `PolicyTable` accepts `tasks: {}` (empty dict) — decide whether min-length enforcement is in-scope for this story [mailbot_api/router/policy.py:57-63] — `tasks: dict[str, PolicyEntry]` has no minimum length constraint. An operator-shipped `tasks: {}` would pass validation and load cleanly, then silently return `None` for every `task_type` lookup in Story 2-4's `ask_router`. AC-1 does not explicitly require a min-length guard; adding `min_length=1` via Pydantic `Field` is a one-liner. Reviewer decision: add the guard in this story or defer to Story 2-4.

- [x] [Review][Patch] `policy_reload_loop` silently kills the watcher task on any non-`PolicyValidationError` exception from the loop body [mailbot_api/router/policy.py:174-187] — Only `PolicyValidationError` is caught inside the `async for` body. If `sanitize_error`, `set_policy_snapshot`, or `_log.info` raise for any reason, the exception escapes the loop, the task dies, and the lifespan's `finally` block only notices when it `wait_for`s the (already-done) task — with no structured log. Add a broad `except Exception as exc` after `except PolicyValidationError` that logs `event="policy.reload.loop.error"` with the exception type and then `continue`s (or re-raises if the intent is to let the task die with a visible error).

- [x] [Review][Patch] `asyncio.get_event_loop()` deprecated in Python 3.10+; replace with `asyncio.get_running_loop()` in integration test helper [tests/integration/test_policy_reload.py:52-53] — `_wait_for_version` calls `asyncio.get_event_loop().time()` twice. In Python 3.10+ this emits a `DeprecationWarning` when called from a coroutine with a running loop. Replace with `asyncio.get_running_loop().time()` (safe in async context; raises `RuntimeError` if not in a running loop, which is a better failure mode than a deprecation warning).

- [x] [Review][Patch] Boundary check for `yaml.safe_load` does not catch `from yaml import safe_load; safe_load(x)` import-then-call pattern [scripts/check_boundaries.py:168-183] — The AST check only detects the `yaml.safe_load(...)` attribute-call form. `from yaml import safe_load` followed by a bare `safe_load(data)` call is not detected. Subtask 7.2 says "Detect via `ast.Attribute` (`yaml.safe_load`, `yaml.load`) and `ast.ImportFrom`" — but the `ast.ImportFrom` detection only bans `from yaml` imports (already flagged for ollama/anthropic/sqlite3 patterns), not bare-name calls after aliased imports. Add detection: flag any file outside `_YAML_LOAD_ALLOW` that contains `from yaml import` of `safe_load` or `load`, and add a corresponding fixture test.

- [x] [Review][Patch] No positive-pass test for `yaml.safe_load` allowlist (contrast with `router_calls` which has `test_router_calls_insert_in_allowlisted_audit_path_passes`) [tests/unit/test_lint_boundaries.py] — AC-12 boundary enforcement is tested for the violation case only. There is no test confirming that `mailbot_api/router/policy.py` (the allowlisted file) does NOT trigger a boundary violation. Add a parallel test mirroring `test_router_calls_insert_in_allowlisted_audit_path_passes` that copies the yaml-violation fixture into `mailbot_api/router/policy.py` path and asserts `exit_code == 0`.

- [x] [Review][Patch] `_reset_policy_module` fixture directly writes `_policy_mod._policy = None` but `set_policy_snapshot` uses `global _policy` — the direct attribute write bypasses any future concurrency guard if one is added [tests/integration/test_policy_reload.py:67-73] — Low risk today (no lock), but the fixture should call `set_policy_snapshot` with a `None`-sentinel or use the module's own teardown path. Since `set_policy_snapshot` requires a `PolicyTable` (not `None`), the fix is to expose a `_reset_policy_snapshot()` test helper in policy.py (or document that `_policy_mod._policy = None` is the accepted teardown idiom). At minimum add a comment linking to the type-safety concern the pre-review audit identified.

## Dev Notes

### Why `router/` (project root) and not `mailbot_api/router/`

Architecture lines 936-937 explicitly separate the **Python package** `mailbot_api/router/` (code) from the **configuration directory** `router/` (artifacts: `policy.yaml`, `sensitivity_patterns.yaml`). The split is deliberate — config artifacts get mounted as a volume in Docker (so the operator can edit them without rebuilding) while the Python package is baked into the image. Story 1-2's Docker stack should already define the mount; if not, this story flags it and the dev agent adjusts `docker-compose.yml`.

### Why `extra="forbid"` on both models

Without it, `versions: x` (typo for `version`) parses silently as no-version-set and any `version: str` field uses the default (empty string per Pydantic v2). The story-2-4 audit log would then carry `prompt_version=""` and policy-version observability would be broken. `forbid` makes the typo loud at startup.

### Why `sanitize_error` in `PolicyValidationError`

The Pydantic `ValidationError.json()` output can include the offending value. If a future operator accidentally pastes a secret into `policy.yaml` (e.g., `api_key: sk-...` thinking they were configuring an adapter), the validation error would echo it into the log line. Sanitizing the details defensively is consistent with Story 1-4's structured-logging discipline. The text "validation failed" itself is fine; the per-field detail string is what gets sanitized.

### Why a separate `snapshot_for_dispatch()` helper

Functionally identical to `get_policy()` today. The name exists so a code reviewer reading Story 2-4's `ask_router` immediately understands *why* the call is captured once: it's the dispatch-time snapshot per architecture D11. A grep for `get_policy(` in `router.py` would obscure the intent; `snapshot_for_dispatch(` is self-documenting.

### Mid-call race test (AC-11) — how to actually verify

The test:

1. Writes `policy.yaml v=1` to `tmp_path`, calls `load_policy` + `set_policy_snapshot`.
2. Calls `snap = snapshot_for_dispatch()` — captures the v=1 instance.
3. Overwrites the file with `policy.yaml v=2`.
4. Awaits the watcher's reload fire (poll `get_policy().version == "2"` with timeout).
5. Asserts `snap.version == "1"` — the snapshot held by the simulated in-flight call did NOT change identity when `_policy` was reassigned.

This works because Pydantic models are immutable from the perspective of attribute access (the test doesn't mutate the model itself), and Python references are stable: `set_policy_snapshot` rebinds the module-level name, but the local `snap` still points to the old object.

### `watchfiles.awatch` semantics

`watchfiles.awatch(path, stop_event=stop_event)` yields a `set[tuple[Change, str]]` on each detected change. We don't care about the detail of what changed (modify vs add vs delete) — any yield means "re-read the file and try to load." Editor-save behavior varies (atomic rename vs in-place rewrite); `watchfiles` handles both. The path passed should be the **file** path, not its parent directory — but if the editor does atomic-rename + recreate, the inode changes. As of `watchfiles 0.21+` watching the file works for most editors; if the dev encounters editor-specific issues, watch the parent dir and filter on filename in the change handler.

### Files being touched / created

**Created (NEW files):**

- `router/policy.yaml` (project-root config artifact)
- `mailbot_api/router/policy.py`
- `tests/unit/router/test_policy_load.py`
- `tests/integration/test_policy_reload.py`
- `tests/fixtures/lint_violations/violates_yaml_load_outside_policy.py.fixture`

**Updated:**

- `mailbot_api/main.py` — lifespan adds policy load + watcher task
- `scripts/check_boundaries.py` — `yaml.safe_load` / `yaml.load` allowlist rule + AST walk
- `tests/unit/test_lint_boundaries.py` — extended parametrize block

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 2.2`]
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 385-388 (D11 reload semantics) + lines 936-937 (config dir split)]
- [Source: `mailbot_api/router/errors.py:sanitize_error`] — Story 2-1's helper for the `PolicyValidationError.details` redaction
- [Source: `mailbot_api/main.py`] — existing lifespan; insertion point
- [Source: `mailbot_api/db/migrations_runner.py`] — pattern for FastAPI lifespan startup steps
- [Source: `mailbot_api/observability/logging.py`] — structured-log event pattern

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

One regression caught + fixed during gates: `test_lifespan_runs_migrations_on_startup_via_testclient` (Story 1-3 / CR-7) failed because the lifespan now requires `MAILBOT_POLICY_PATH` to point at a real file. Fixed by extending the existing monkeypatch in that test to also set `MAILBOT_POLICY_PATH` to the project-root `router/policy.yaml`. No semantic regression — the existing test just needed the new env contract.

### Completion Notes List

- **`yaml.safe_load` only — `yaml.load` is banned twice.** ruff `S` (bandit S506) flags `yaml.load` at lint; the new boundary check also bans both outside `policy.py`. Layered defense.
- **`PolicyValidationError.details` is sanitized.** Pydantic's JSON-shaped error list can include the offending value — if an operator pastes a secret into `policy.yaml` and breaks validation, the failure log line carries the redacted form (Bearer / sk- / URL token / secret-file paths all stripped per Story 2-1's shared `sanitize_error`).
- **Mid-call race isolation verified by integration test.** `test_policy_reload_mid_call_race_snapshot_isolation` captures a snapshot, mutates the file, awaits reload, and asserts the captured object's `.version` is still pre-swap. This is the architecture D11 contract made executable.
- **`snapshot_for_dispatch()` is documentary, not functional.** Same code as `get_policy()` today; the name exists so a Story 2-4 reviewer immediately understands the dispatch-time-capture intent.
- **Lifespan teardown uses `asyncio.wait_for(timeout=5.0)`.** If the watcher hangs at shutdown, log + cancel rather than block uvicorn forever. The watcher itself respects the `stop_event` so the timeout should never fire in practice; it's a defense-in-depth fallback.
- **`types-PyYAML` added to requirements.txt.** mypy --strict needs the stub. Pinned without version per project convention (`types-` packages float).
- **191 tests pass** (173 baseline after 2-1 → 191 after 2-2, net +18: 11 unit + 5 integration + 1 boundary fixture + 1 lifespan-test fix-up which doesn't add a new test but corrects the existing one to the new env contract). All gates green.

### File List

**Created:**

- `router/policy.yaml` — project-root config artifact with 3 starter task entries
- `mailbot_api/router/policy.py` — `PolicyEntry`/`PolicyTable`/`PolicyValidationError`/`load_policy`/`get_policy`/`set_policy_snapshot`/`snapshot_for_dispatch`/`policy_reload_loop`
- `tests/unit/router/test_policy_load.py` — loader + schema validation tests
- `tests/integration/test_policy_reload.py` — hot-reload + race + shutdown tests
- `tests/fixtures/lint_violations/violates_yaml_load_outside_policy.py.fixture` — boundary fixture

**Updated:**

- `mailbot_api/main.py` — lifespan adds policy load + watcher start/teardown
- `scripts/check_boundaries.py` — `yaml.safe_load`/`yaml.load` allowlist + AST Call/Attribute scan
- `tests/integration/test_db_connection.py` — fix-up: monkeypatch `MAILBOT_POLICY_PATH` in the existing CR-7 lifespan test
- `tests/unit/test_lint_boundaries.py` — extended parametrize block with yaml-bypass fixture
- `requirements.txt` — added `types-PyYAML` for mypy --strict

**Sprint state updates:**

- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 2-2 → review (will → done after code-review + done-gates)

## Change Log

- 2026-06-01 (claude-opus-4-7, autonomous-epic-run) — Implemented Story 2-2: policy schema, loader, watchfiles hot-reload, FastAPI lifespan integration, `yaml.safe_load` boundary enforcement. 191 tests pass; all gates green.
- 2026-06-01 (claude-opus-4-7, autonomous-epic-run) — Applied all 6 code-review findings from claude-sonnet-4-6: **HIGH** decoupled policy load from `MAILBOT_SKIP_DB` branch (new `MAILBOT_SKIP_POLICY` flag for symmetric bypass; new test `test_lifespan_loads_policy_when_db_skipped` proves Router-side code now boots cleanly when DB is skipped); **MEDIUM Decision-Apply** `PolicyTable.tasks` now `min_length=1` (operator-shipped `tasks: {}` fails validation rather than silently breaking every dispatch); **MEDIUM Patch** broad `except Exception` in `policy_reload_loop` with `event="policy.reload.loop.error"` log (defensive — prevents silent task death on non-PolicyValidationError exceptions); **LOW Patch** `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (deprecation fix); **LOW Patch** boundary checker now catches `from yaml import safe_load` bypass via `ast.ImportFrom` walk + new fixture + parametric test; **LOW Patch** added allowlist-passes-clean test `test_yaml_safe_load_in_allowlisted_policy_path_passes` mirroring the router_calls pattern; **LOW Patch** added `_reset_policy_snapshot_for_test()` named helper (replaces direct `_policy_mod._policy = None` writes in test fixtures). 194 tests pass (+3 net new: 1 lifespan SKIP_DB policy test + 1 from-yaml-import bypass parametric + 1 yaml allowlist-passes-clean). All gates green.

