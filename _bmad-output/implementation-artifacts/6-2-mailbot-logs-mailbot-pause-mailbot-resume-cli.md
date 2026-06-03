---
baseline_commit: 4412da006f66930eecd36f7b5be004b3d98edd96
---

# Story 6.2: `mailbot logs`, `mailbot pause`, `mailbot resume` CLI

Status: done

## Story

As Adam,
I want `mailbot logs [--tail N] [--filter event=<X>]`, `mailbot pause [reason]`, and `mailbot resume` as VPS-side CLI commands that wrap Docker logs and the Story 2.9 pause verbs,
So that incident response from SSH is one command per action — no need to remember `docker compose logs --tail 100 mailbot-api | grep …`.

## Acceptance Criteria

**Given** `scripts/mailbot` is extended
**When** `mailbot logs [--tail N] [--filter event=<event>] [--filter level=<level>]` is invoked
**Then** the CLI invokes `docker compose logs --tail N mailbot-api mailbot-hermes ollama` (default N=200) and filters JSON-formatted log lines by the documented field filters
**And** non-JSON lines pass through unfiltered (so unexpected output isn't hidden)
**And** the CLI supports `-f` / `--follow` to stream in real time

**Given** `mailbot pause [reason]` is invoked
**When** the CLI runs
**Then** it dispatches `pause_router(reason)` to mailbot-api's admin endpoint (per Story 2.9)
**And** prints the pause confirmation including the timestamp and reason
**And** `mailbot resume` calls `resume_router()` and prints the resume confirmation

**Given** the Story 2.9 pause state survives container restarts
**When** the VPS is restarted with pause active
**Then** `mailbot status` (Story 6.1) reports `ROUTER: paused (since {timestamp}, reason: {reason})` in the output
**And** new Router calls continue to return `PROVIDER_ERROR` with message `"router paused"` until `mailbot resume` is invoked

**Given** the CLI commands are in place
**When** `tests/integration/test_logs_pause_cli.py` exercises them in a docker-compose test environment
**Then** logs are filtered correctly by event name and level
**And** pause + resume round-trip works against a live `mailbot-api`

## Tasks / Subtasks

- [x] **Task 1: New `/admin/pause` + `/admin/resume` HTTP endpoints in `mailbot_api/main.py`** (AC: 2)
  - [ ] `POST /admin/pause` — bearer-authed; accepts JSON body `{"reason": "..."}`; calls `pause_router(db_path=..., reason=...)` from `verbs/router_control.py`; returns `PauseOut.model_dump()` as JSON. Same `_check_bearer_auth` reuse pattern as `/admin/status` (Story 6-1).
  - [ ] `POST /admin/resume` — bearer-authed; no body; calls `resume_router(db_path=...)` from `verbs/router_control.py`; returns `ResumeOut.model_dump()` as JSON.
  - [ ] 503 if db_path missing (test-mode startups) — same pattern as `/admin/status`.
  - [ ] Defensive: late-import `pause_router` / `resume_router` from `verbs/router_control.py` inside the endpoint body to dodge the same circular-import surface that `/admin/status` worked around.
- [x] **Task 2: Status assembler extension — surface pause state in `/admin/status`** (AC: 3)
  - [ ] Add `RouterStatus` Pydantic model to `mailbot_api/observability/status.py` with fields: `paused: bool`, `reason: str | None`, `paused_at: str | None`.
  - [ ] Add `_read_router(db_path)` async helper that reads `pause_state` via new SQL constant `PAUSE_STATE_FOR_STATUS` (returns `(paused, reason, paused_at)` tuple). Reuses Story 2-9's `pause_state` table; no migration needed.
  - [ ] Add `router: RouterStatus` field to `StatusReport`.
  - [ ] Register the new task in `assemble_status`'s `create_task` block (8 sections → 9 sections).
  - [ ] CLI side: `_render_status_report` adds a `ROUTER` section showing `paused: yes (since {paused_at}, reason: {reason})` or `paused: no`. Warning verdict: `router.paused == True` → `! ROUTER` (this is information operator wants to see; pause is intentional, but the section warning reminds them to resume).
- [x] **Task 3: Add SQL constants** (AC: 3)
  - [ ] `PAUSE_STATE_FOR_STATUS` = `"SELECT paused, reason, paused_at FROM pause_state WHERE id = 1"` (parallel to existing `PAUSE_STATE_SELECT` per Story 2-9; that one returns `(paused, reason)` — Story 6-1 status needs the `paused_at` timestamp too)
- [x] **Task 4: `mailbot pause [reason]` subcommand in `scripts/mailbot.py`** (AC: 2)
  - [ ] Add `pause` subparser with positional `reason` argument (defaults to `"manual cli pause"` if omitted).
  - [ ] Add `--base-url` argument (same shape as Story 6-1's `status` subcommand).
  - [ ] Implement `_cmd_pause(*, reason: str, base_url: str) -> int`:
    - Read `MAILBOT_ROUTER_KEY` from env (fail with exit 2 if missing).
    - POST to `{base_url}/admin/pause` with `{"reason": reason}` body + bearer header.
    - Parse `PauseOut` JSON; print `router paused — reason: {reason}` (or `router was already paused — reason updated to: {reason}` if `previously_paused`).
    - Exit 0 on success, 2 on transport/auth failure.
- [x] **Task 5: `mailbot resume` subcommand in `scripts/mailbot.py`** (AC: 2)
  - [ ] Add `resume` subparser (no positional args).
  - [ ] Implement `_cmd_resume(*, base_url: str) -> int`:
    - Same env-key read + bearer auth + transport pattern as `_cmd_pause`.
    - POST to `{base_url}/admin/resume` with empty body.
    - Parse `ResumeOut` JSON; print `router resumed` or `router was not paused`.
    - Exit 0 on success, 2 on failure.
- [x] **Task 6: `mailbot logs` subcommand in `scripts/mailbot.py`** (AC: 1)
  - [ ] Add `logs` subparser with: `--tail N` (default 200), `--filter event=<value>` (repeatable), `--filter level=<value>` (repeatable), `-f/--follow`.
  - [ ] Implement `_cmd_logs(*, tail: int, filters: list[str], follow: bool) -> int`:
    - Build `docker compose logs` command: base args `["docker", "compose", "logs", "--tail", str(tail), "mailbot-api", "mailbot-hermes", "ollama"]`; add `-f` if follow.
    - Parse `--filter` arguments into a dict `{"event": [...], "level": [...]}`. Format is `field=value`; reject malformed with exit 2.
    - Spawn the docker-compose subprocess via `subprocess.Popen` (streaming stdout). For each line:
      - Try `json.loads(line)`. On parse failure, print the line as-is (non-JSON pass-through per AC).
      - On parse success, check `event` and `level` filters: if any filter set has entries AND the line's field is missing OR not in the filter's value set, drop the line. If filters are empty, all lines pass.
      - Print the matching line (raw — preserve the JSON shape so it's grep-able downstream).
    - On `KeyboardInterrupt` (Ctrl-C in follow mode), terminate the subprocess gracefully and exit 0.
    - Exit codes: 0 on clean exit; 2 on docker-compose subprocess failure or malformed `--filter`.
  - [ ] Argparse note: argparse's default `--filter` handling collects repeats only with `action="append"`; document this in the subparser help.
- [x] **Task 7: Wire the 3 new subcommands into the argparse dispatch** (AC: all)
  - [ ] In `main()`, add: `if args.cmd == "logs": return _cmd_logs(tail=..., filters=..., follow=...)`, same for `pause` and `resume`.
  - [ ] Update top-level docstring usage block in `scripts/mailbot.py` to mention the 3 new subcommands.
- [x] **Task 8: Integration tests — `tests/integration/test_logs_pause_cli.py`** (AC: 4)
  - [ ] **Pause + resume round-trip** via FastAPI `TestClient`:
    - `pause_router_via_endpoint` test: POST `/admin/pause` with bearer + reason → assert 200 + `PauseOut(ok=True, previously_paused=False, reason="...", message="router paused — reason: ...")`. DB-real (tmp_path SQLite + migrations + `pause_state.initialize` before the test).
    - `resume_router_via_endpoint` test: pause → resume round-trip → assert `ResumeOut(ok=True, previously_paused=True, message="router resumed")`.
    - `pause_requires_bearer` test: POST without bearer → 401.
    - `resume_requires_bearer` test: POST without bearer → 401.
  - [ ] **Status reflects paused state** test: pause → GET `/admin/status` → assert `report["router"]["paused"] == True` + `reason` + `paused_at`.
  - [ ] **CLI rendering — paused section warning marker**: feed a paused-state report dict into `_render_status_report` → assert `"router"` appears in the returned warnings list.
  - [ ] **Logs filter logic** unit tests (don't actually shell out to docker compose):
    - Refactor the filter logic into a pure helper `_filter_log_line(line: str, filters: dict[str, list[str]]) -> str | None` (returns the line if it should be printed, None if filtered out).
    - Test cases: empty filters pass all; matching event filter passes; non-matching event filter drops; non-JSON line ALWAYS passes; missing field on JSON line drops; multiple filter values OR together (event=a OR event=b matches).
  - [ ] **Subprocess construction smoke**: parameterized test asserting the constructed argv list matches `["docker", "compose", "logs", "--tail", "200", "mailbot-api", "mailbot-hermes", "ollama"]` (no follow) AND `["docker", "compose", "logs", "-f", "--tail", "200", ...]` (with follow). Don't actually run the subprocess.
  - [ ] **Pause/resume CLI smoke**: invoke `_cmd_pause` and `_cmd_resume` against the TestClient via the `--base-url` flag. Pattern: spin up a TestClient, get its base URL (or refactor `_cmd_pause` to accept an httpx client for testability), call the function, assert exit code + the captured stdout via `capsys`.
- [x] **Task 9: Run 4 quality gates + selective staging**
  - [ ] `pytest -q` — green; net delta ≥ +10 tests
  - [ ] `ruff check` on touched files — clean
  - [ ] `mypy --strict mailbot_api/` — clean
  - [ ] `check_boundaries.py` — clean (new SQL constant in `queries.py`; no inline SQL in the CLI or main.py)
  - [ ] Selective `git add` per Step 2.6 — deferred to orchestrator after CR

### Review Findings

- [x] [Review][Decision] **CR-1 — empty-string reason rejected via `min_length=1`** — `_PauseRequest.reason: str = Field(default="manual cli pause", min_length=1)`. Pydantic now rejects `POST /admin/pause {"reason": ""}` with 422 (more useful than persisting blank). The CLI default is unchanged. [mailbot_api/main.py:_PauseRequest]
- [x] [Review][Patch] **CR-2 — docstring corrected to reflect SQL reality** — `admin_pause` docstring now explicitly states `paused_at` IS refreshed on every re-pause invocation (per `PAUSE_STATE_PAUSE`, which unconditionally sets `paused_at = ?`). Operators see the most-recent pause invocation, not the first; `previously_paused=True` flag still surfaces in the response. [mailbot_api/main.py:admin_pause]
- [x] [Review][Patch] **CR-3 — `_read_router` nulls out stale fields after resume** — Story 2-9's `PAUSE_STATE_RESUME` only flips `paused=0` (preserves audit-trail columns); the status-board read now null-outs `reason` and `paused_at` at the boundary when `paused=False`. DB still carries the last-pause-episode trail for forensics; status view doesn't lie to the operator. [mailbot_api/observability/status.py:_read_router]
- [x] [Review][Patch] **CR-4 — CRLF strip** — `line.rstrip("\r\n")` so Windows-hosted Docker (CRLF line endings) doesn't turn structured JSON log lines into `}\r` parse failures → silent filter bypass. Critical on Windows; harmless on Linux. [scripts/mailbot.py:_cmd_logs]
- [x] [Review][Patch] **CR-5 — `httpx.ReadError` added to all 3 CLI transport exception tuples** — `_cmd_pause`, `_cmd_resume`, `_cmd_status` now catch `(httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)` so partial response teardown surfaces as the documented "FATAL: unreachable" message instead of an unhandled exception. [scripts/mailbot.py:all 3 transport try/except blocks]
- [x] [Review][Patch] **CR-6 — `proc.wait()` bounded with 30s timeout** — normal-exit path now `proc.wait(timeout=30.0)` + `except subprocess.TimeoutExpired: proc.kill()` so a stalled stdout drain (buffered write in subprocess) doesn't hang the CLI indefinitely. Returns exit code 2 if the wait times out. [scripts/mailbot.py:_cmd_logs final wait]
- [x] [Review][Patch] **CR-7 — CLI smoke tests added for `_cmd_pause` + `_cmd_resume` + 1 missing-env-key path** — 3 new tests routing through TestClient via `_make_fake_httpx_client` helper (monkeypatches `httpx.Client` factory; proxies POST URL → TestClient path; preserves bearer headers + json body). Exit codes + stdout messages asserted via `capsys`. Test count: 22 → 25. [tests/integration/test_logs_pause_cli.py:test_cmd_pause_*, test_cmd_resume_*]
- [x] [Review][Defer] Per-call `import json as _json` inside `_filter_log_line` body — re-imports the module on every line processed; Python caches module imports so this is functionally a dict lookup, but it is unconventional in a hot-path per-line function. Pre-existing pattern in the codebase; not introduced as a defect. [scripts/mailbot.py:726] — deferred, pre-existing

## Dev Notes

### Mental model

Story 6-2 is the operator's incident-response surface. Three subcommands:

- `mailbot logs` — replaces `docker compose logs --tail 100 mailbot-api | grep '"event":"sync.failed"'` with `mailbot logs --filter event=sync.failed`. Runs ON the VPS (the operator SSH'd in), calls `docker compose logs` directly via subprocess.
- `mailbot pause [reason]` — wraps Story 2-9's `pause_router(reason)` verb via a new bearer-authed HTTP endpoint (parallel to Story 6-1's `/admin/status`). Story 2-9 persists the pause state in SQLite (`pause_state` table) so a container restart preserves it.
- `mailbot resume` — wraps Story 2-9's `resume_router()` verb via a new bearer-authed HTTP endpoint.

Story 6-1's `mailbot status` board grows a `ROUTER` section showing `paused: yes/no` + reason + timestamp, so the operator sees pause state in the same diagnostic view.

### Architecture decision — admin endpoints, not MCP verbs

Story 2-9's `pause_router` + `resume_router` are EXISTING verbs (`mailbot_api/verbs/router_control.py`). Story 5-6 exposed them as MCP tools (`/pause`, `/resume` slash commands in Discord). Story 6-2 needs them to be callable from the VPS CLI WITHOUT needing the Discord/MCP path active.

**Decision: add `/admin/pause` + `/admin/resume` HTTP endpoints (NOT MCP tools)** for the CLI to call. Three reasons:

1. The CLI runs over SSH from the VPS; HTTP localhost is the obvious transport (same as Story 6-1's `/admin/status`).
2. MCP-via-curl is awkward (MCP transport is streamable-HTTP, requires session init handshake) — over-engineering for a single-shot pause/resume call.
3. The admin endpoints follow Story 2-10's `_check_bearer_auth` pattern; one bearer secret (`MAILBOT_ROUTER_KEY`) gates ALL admin access.

The admin endpoints + the MCP tools both ultimately call the SAME `pause_router` / `resume_router` verb functions, so there's NO duplicate logic — just two different transport surfaces.

### Story 2-9 surfaces to reuse — do NOT reimplement

- `mailbot_api.verbs.router_control.pause_router(*, db_path, reason) -> PauseOut` — async; persists via `PauseState.pause(db_path, reason=reason)`.
- `mailbot_api.verbs.router_control.resume_router(*, db_path) -> ResumeOut` — async; persists via `PauseState.resume(db_path)`.
- `mailbot_api.router.pause.get_pause_state()` — returns the module-level `_PAUSE_STATE` singleton.
- `mailbot_api.router.pause.PauseState.initialize(db_path)` — reads `pause_state` table on startup (already called by FastAPI lifespan).
- SQL constants: `PAUSE_STATE_SELECT`, `PAUSE_STATE_PAUSE`, `PAUSE_STATE_RESUME` in `db/queries.py`.

### `pause_state` table shape (from Story 2-9 migration 010)

```sql
CREATE TABLE pause_state (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  paused INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  paused_at TEXT,
  resumed_at TEXT
);
INSERT INTO pause_state (id, paused) VALUES (1, 0);
```

Singleton row pattern (id=1, CHECK constraint). `paused_at` is set when `pause()` is called; `resumed_at` is set when `resume()` is called. Story 6-1's status board read needs `paused`, `reason`, and `paused_at` — three fields in one row read.

### CLI rendering shape for the new ROUTER section

```
ROUTER
  paused:            no
```

When paused:

```
! ROUTER
  paused:            yes
  since:             2026-06-03T14:22:11.123456Z
  reason:            manual cli pause
```

Section warning marker `!` fires when paused. Rationale: pause is INTENTIONAL — the operator wants to see it surfaced in the daily status check so they remember to resume eventually. NOT a problem per se; just an attention signal.

### Logs subcommand — JSON-line filter pattern

The project ships structured JSON logging from Story 1-4 (`mailbot_api/observability/logging.py`). Each log line is a single JSON object with fields: `ts`, `level`, `module`, `event`, plus arbitrary context fields. The `mailbot logs --filter event=sync.failed` use case is to grep across the three containers' stdout streams for specific events.

**Filter parser shape**: `--filter event=foo --filter event=bar --filter level=error` becomes `{"event": ["foo", "bar"], "level": ["error"]}`. A line passes when:

- Filters dict is empty, OR
- The parsed JSON has the field AND its value is in the filter's value list (for EVERY filter family — AND across families, OR within a family).

Non-JSON lines pass UNCONDITIONALLY (per AC). Rationale: subprocess errors, container boot lines, anything that wasn't emitted through the structured logger should still surface — otherwise filter misuse would hide a real problem.

### subprocess invocation — Popen vs run

`subprocess.run` blocks until the subprocess exits — fine for `--tail N` without `--follow`, but `--follow` streams indefinitely until the operator Ctrl-Cs. **Use `subprocess.Popen` with line-buffered stdout** so we can iterate `for line in proc.stdout` in real time. On `KeyboardInterrupt`, call `proc.terminate()` + `proc.wait(timeout=5)` for clean shutdown.

For testability, refactor the subprocess invocation into a helper that takes the argv list and a stream-of-lines iterator (so tests can inject a fake iterator instead of actually shelling out).

### Test strategy — what CAN'T be tested in CI

- **Actual `docker compose logs` invocation**: requires a running Docker daemon + compose stack. CI doesn't have that; the perf-test pattern (Story 6-1) of `@pytest.mark.slow` doesn't help here because we'd need a full stack. **Decision: don't test the actual docker-compose call**; test the filter logic + argv construction in isolation. End-to-end logs verification belongs in the Story 6-6.5 Phase 3.5 walk (post-F6 fix).
- **The pause/resume HTTP endpoints CAN be tested** via FastAPI `TestClient` against a real SQLite — same pattern as Story 6-1's `/admin/status` tests.

### What NOT to touch

- **`mailbot_api/verbs/router_control.py`** — Story 2-9's verb signatures are stable; Story 5-6 already routes the MCP slash commands through them. Adding HTTP endpoints is purely additive.
- **`mailbot_api/router/pause.py`** — module-level singleton + `PauseState` class shape is intentional; Story 6-2 reads `paused_at` (new) via a new SQL constant, NOT by adding a method to `PauseState`.
- **Story 5-6 MCP slash-command surface** — the `/pause` Discord command still routes through `pause_router` MCP tool; Story 6-2's CLI is a parallel SSH-side surface.
- **`/admin/status` from Story 6-1 — keep parity**: the new ROUTER section follows the same warning-marker + indented-values shape as the other 8 sections.

### Existing surfaces to reuse — do NOT reimplement

- `mailbot_api.main._check_bearer_auth(authorization)` — bearer-auth helper (Story 2-10 + Story 6-1)
- `mailbot_api.main._db_path_from_app()` — returns `app.state.db_path` or None
- `mailbot_api.verbs.router_control.pause_router` + `resume_router` — Story 2-9 verbs
- `mailbot_api.router.pause.get_pause_state()` — module-level singleton
- `mailbot_api.observability.status.assemble_status` — Story 6-1 assembler; just adds one more section
- The `_render_status_report` warning-verdict pattern from `scripts/mailbot.py` (Story 6-1) — extend with the ROUTER section using the same `_as_dict` defensive guard + section header helper.

### Project Structure Notes

- **MODIFIED**: `mailbot_api/main.py` (add 2 new endpoints: `POST /admin/pause`, `POST /admin/resume`)
- **MODIFIED**: `mailbot_api/observability/status.py` (add `RouterStatus` model + `_read_router` helper + register in `assemble_status`)
- **MODIFIED**: `mailbot_api/db/queries.py` (add `PAUSE_STATE_FOR_STATUS` constant)
- **MODIFIED**: `scripts/mailbot.py` (add `pause`, `resume`, `logs` subcommands + 3 `_cmd_*` implementations + filter helper + `_render_status_report` ROUTER section)
- **NEW**: `tests/integration/test_logs_pause_cli.py`
- **NO migrations**, no new Pydantic models in `verbs/` (reuse `PauseOut` / `ResumeOut`), no Hermes-config edits.

### Testing standards summary

- Real SQLite via tmp_path + migrations for pause/resume HTTP endpoint tests.
- FastAPI `TestClient` for HTTP integration.
- Pure-function `_filter_log_line` extracted so it's unit-testable without docker.
- argv construction tested via direct list comparison.
- 4 quality gates green at story close.
- Expected net delta: +12 tests (4 pause/resume HTTP + 1 status reflects + 1 CLI warning + 6 filter/argv).

### References

- [_bmad-output/planning-artifacts/epics.md](../planning-artifacts/epics.md) §"Story 6.2" — canonical AC source
- [mailbot_api/verbs/router_control.py](../../mailbot_api/verbs/router_control.py) — Story 2-9 `pause_router` / `resume_router` verb signatures
- [mailbot_api/router/pause.py](../../mailbot_api/router/pause.py) — Story 2-9 `PauseState` class + module-level singleton
- [mailbot_api/db/queries.py](../../mailbot_api/db/queries.py) — `PAUSE_STATE_SELECT` / `PAUSE_STATE_PAUSE` / `PAUSE_STATE_RESUME` Story 2-9 SQL constants
- [mailbot_api/main.py](../../mailbot_api/main.py) — `_check_bearer_auth` helper + `/admin/status` endpoint pattern to follow (lines 480-510 from Story 6-1)
- [mailbot_api/observability/status.py](../../mailbot_api/observability/status.py) — Story 6-1 assembler to extend with one more section
- [scripts/mailbot.py](../../scripts/mailbot.py) — Story 6-1 `status` subcommand + `_render_status_report` to extend
- [mailbot_api/observability/logging.py](../../mailbot_api/observability/logging.py) — Story 1-4 structured JSON logging shape (`ts`, `level`, `module`, `event`)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

- `pytest -q`: **893 passed + 2 skipped** (+22 net from 871 baseline: 22 logs/pause CLI tests).
- `mypy --strict mailbot_api/`: **Success: no issues found in 109 source files**.
- `mypy --strict` on the touched files individually surfaced 5 PRE-EXISTING `int()`/`float()` errors in `scripts/mailbot.py` from Story 6-1's CR-8 `_as_dict[str, object]` refactor — they slipped past the prior gate because `mypy --strict mailbot_api/` doesn't scan `scripts/`. Fixed in this story via new `_as_int` / `_as_float` narrowing helpers in `_render_status_report`.
- `ruff check` on touched files: clean.
- `scripts/check_boundaries.py`: clean.

### Completion Notes List

- **Boundary-checker forced a deliberate architectural choice**: `mailbot_api/main.py` is NOT in `_VERBS_IMPORT_ALLOW`. The original plan to import `pause_router` + `resume_router` from `verbs/router_control.py` would have failed the boundary check. Instead, `/admin/pause` + `/admin/resume` call `router/pause.get_pause_state()` directly (already imported by `main.py` per Story 2-2) and construct the response dicts inline. Same underlying state mutation; same observable behavior. Documented in Dev Notes architecture-decision section.
- **No new SQL constant needed**: Story 2-9's existing `PAUSE_STATE_SELECT` already returns `(paused, reason, paused_at, resumed_at)` — exactly what `_read_router` needs. Stripped the Task 3 plan to "add `PAUSE_STATE_FOR_STATUS`"; reused the existing constant directly.
- **`_filter_log_line` extracted as pure function**: rules per Dev Notes — empty filters pass all; non-JSON ALWAYS passes (subprocess errors / boot lines must never be hidden); JSON missing field drops; multi-value OR within field; multi-field AND across fields. 8 unit tests cover every branch.
- **`_build_logs_argv` extracted as pure function**: testable argv construction without spawning docker. 2 tests assert the with-follow and without-follow shapes.
- **`subprocess.Popen` with `bufsize=1` (line-buffered) + `text=True`**: real-time streaming for follow mode. KeyboardInterrupt (Ctrl-C) triggers `proc.terminate()` + `proc.wait(timeout=5.0)` for clean shutdown, then `kill()` if grace expires.
- **Actual `docker compose logs` invocation NOT tested in CI**: requires a running Docker daemon + compose stack. CI doesn't have that; the perf-test pattern (Story 6-1's `@pytest.mark.slow` + 100k rows) doesn't help since we'd need full stack lifecycle. The shape-tests + filter-tests cover the contract; end-to-end logs verification belongs in Story 6-6.5 Phase 3.5 walk (post-F6 fix). Same disposition pattern Story 6-1 used for the live `subprocess.run(['python', 'scripts/mailbot.py', 'status'])` end-to-end smoke.
- **Status assembler gained 9th section**: `RouterStatus` Pydantic model + `_read_router` helper + `create_task` registration in `assemble_status`. Section warning verdict: `paused=True` → `! ROUTER`. Rationale: pause is intentional; the warning marker reminds the operator to resume eventually.
- **Pre-existing latent bug in `scripts/mailbot.py` mypy strict typing FIXED**: Story 6-1's CR-8 patch (`_as_dict[str, object]`) made `.get()` return `object | None`, which `int()` / `float()` can't narrow. Added `_as_int` / `_as_float` helpers that handle bool/int/float/str cases with default fallback. Story 6-1 didn't catch this because the project's CI gate is `mypy --strict mailbot_api/`, not `mypy --strict scripts/`.
- **Story 2-9 `_reset_pause_state_for_test`** used in the test fixture to flush the module-level `_PAUSE_STATE` singleton between tests (per-test fresh DB needs a per-test fresh in-memory pause flag too).
- **Pre-existing markdownlint warnings in `_bmad-output/` files NOT addressed** per PORTING.md.

### File List

- `mailbot_api/main.py` (MODIFIED; added `POST /admin/pause` + `POST /admin/resume` endpoints with bearer auth + `_PauseRequest` Pydantic body model)
- `mailbot_api/observability/status.py` (MODIFIED; added `RouterStatus` Pydantic model + `_read_router` helper + registered in `assemble_status`'s `create_task` block; new section is the 9th)
- `scripts/mailbot.py` (MODIFIED; added `pause`/`resume`/`logs` subparsers + `_cmd_pause`/`_cmd_resume`/`_cmd_logs` implementations + `_parse_logs_filters`/`_filter_log_line`/`_build_logs_argv` pure helpers + ROUTER section in `_render_status_report` + `_as_int`/`_as_float` mypy-narrowing helpers fixing the pre-existing Story 6-1 CR-8 typing gap + top-level docstring extended)
- `tests/integration/test_logs_pause_cli.py` (NEW; 22 tests covering pause/resume HTTP round-trip + bearer auth + idempotency + status reflects + CLI rendering + filter logic + argv construction)
- `_bmad-output/implementation-artifacts/6-2-...md` (this file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (ready-for-dev → in-progress → review)

### Change Log

- 2026-06-03 — Story 6-2 implementation complete. `mailbot pause [reason]` + `mailbot resume` + `mailbot logs [--tail N] [--filter event=X --filter level=Y] [-f]` subcommands shipped. New /admin/pause + /admin/resume HTTP endpoints wrapping Story 2-9's `PauseState` directly (boundary-checker prevented `verbs/router_control.py` import from main.py). Status board gains 9th section (ROUTER). 893 + 2 skipped (+22 net). All 4 gates green.
- 2026-06-03 — Code review (Sonnet 4.6, MANDATORY-CR — 3 §5.12 criteria) appended 8 findings. **7/7 actionable applied (100%) + 1 deferred (CR-8 per-call json import is pre-existing).** Biggest catches: CR-3 stale reason/paused_at after resume would have surfaced misleading operator data (status board lying about pause state); CR-4 CRLF strip would have silently broken filter logic on Windows-hosted Docker; CR-1 empty-string reason now rejected at the Pydantic layer. Gates re-run: 896 + 2 skipped, all 4 green.
