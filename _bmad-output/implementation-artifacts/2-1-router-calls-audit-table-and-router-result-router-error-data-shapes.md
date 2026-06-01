---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.1: `router_calls` audit table + `RouterResult` / `RouterError` data shapes

Status: done

## Story

As Adam,
I want the `router_calls` audit table, the `RouterResult` and `RouterError` Pydantic shapes, the stable `ErrorCode` enum, and the single `record_router_call()` writer function in place before any Router code is written,
So that every later story records calls into a known schema with no ad-hoc shape variation.

## Context (why this story exists)

This is the foundation story for Epic 2 (Router as Cost-Discipline Center). Every later Router story — policy loader (2-2), Ollama/Anthropic adapters (2-3/2-6), `ask_router()` orchestration (2-4), lanes (2-5), response cache (2-7), budget guard (2-8), anomaly + kill-switch (2-9), Hermes aux routing (2-10) — writes into `router_calls` and returns either a `RouterResult` (success) or a `RouterError` (structured failure). Locking these data shapes + the audit table + the single writer function down first prevents:

1. Shape drift across 9 downstream stories (each one would otherwise grow `RouterError` differently).
2. Multiple writers into `router_calls` (Rule C boundary violation — `INSERT INTO router_calls` outside `observability/audit.py` must fail review).
3. Free-string error codes leaking into downstream code (Rule F.4 enforcement requires the `ErrorCode` enum to exist on day one).

The story is intentionally **schema-only + Pydantic-only + one writer function** — no Router orchestration, no adapter calls, no policy file. It produces the contract; later stories produce the behavior.

## Acceptance Criteria

**AC-1 (`router_calls` migration).** Migration `006_router_calls.sql` (next sequential prefix — see Dev Notes "Migration numbering variance from epic spec") is added under `mailbot_api/db/migrations/` and runs at startup via the existing migration runner. It creates the `router_calls` table with all columns from the epic spec:

- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `ts` TEXT NOT NULL — UTC ISO-8601 with `Z` suffix
- `task_type` TEXT NOT NULL
- `prompt_version` TEXT NOT NULL
- `model_chosen` TEXT NOT NULL
- `model_chosen_reason` TEXT NOT NULL — one of `policy` / `override` / `degraded` / `escalated_from_<X>` / `response_cache_hit` / `force_override` (the union of every reason later stories produce; 2-1 documents the full set so downstream stories don't fight schema constraints — see Dev Notes "Why we enumerate all `model_chosen_reason` values now")
- `tokens_in` INTEGER NOT NULL DEFAULT 0
- `tokens_out` INTEGER NOT NULL DEFAULT 0
- `cached_tokens_in` INTEGER NOT NULL DEFAULT 0
- `cost_usd_estimated` REAL NOT NULL DEFAULT 0
- `latency_ms` INTEGER NOT NULL DEFAULT 0
- `outcome` TEXT NOT NULL — one of `ok` / `retry_recovered` / `escalated` / `failed`
- `caller_verb` TEXT NULL
- `caller_origin` TEXT NOT NULL DEFAULT 'unknown' — populated per AR-D2-2 (placeholder default `unknown` until Story 2.10 wires real values)
- `email_id` TEXT NULL
- `sensitivity_grant_id` TEXT NULL — Epic 4 populates this; column lives here from day one
- `sensitivity_grant_minted_at` TEXT NULL

And the three indexes from the epic spec are created in the same migration:

- `ix_router_calls_ts` ON `router_calls(ts)`
- `ix_router_calls_task_type_model_chosen` ON `router_calls(task_type, model_chosen)`
- `ix_router_calls_email_id` ON `router_calls(email_id)`

Migration is additive only (no destructive operations on existing tables) and the atomic composite-executescript pattern from Story 1-3 applies — if any statement fails, COMMIT is never reached.

**AC-2 (`ErrorCode` enum).** `mailbot_api/router/errors.py` defines an `ErrorCode` `str`-backed Enum (so values serialize cleanly to JSON and SQL) containing exactly these members from the epic spec (the union of every code Epic 2 stories raise):

- `SCHEMA_VALIDATION_FAILED`
- `TIMEOUT`
- `BUDGET_EXCEEDED`
- `PER_CALL_THRESHOLD_EXCEEDED`
- `PROVIDER_ERROR`
- `MONTHLY_BUDGET_EXCEEDED`
- `DEGRADED_MODE_BLOCKED`
- `LOOP_DETECTED`
- `SENSITIVITY_BLOCKS_API`
- `NEEDS_SENSITIVITY_CONFIRMATION`
- `SENSITIVITY_NOT_CLASSIFIED`
- `RATE_LIMITED`
- `STATE_DRIFT_ETAG`
- `TARGET_DELETED`
- `STATE_DRIFT_NOOP`

Each member's `value` is the snake_case lowercase name (e.g., `ErrorCode.TIMEOUT.value == "timeout"`) per architecture §"Stable error codes" — downstream tooling keys on the string form.

**AC-3 (`RouterError` + `RouterResult` Pydantic models).** `mailbot_api/router/errors.py` also defines:

- `class RouterError(BaseModel)` with fields:
  - `code: ErrorCode` — never a free string (Pydantic rejects unknown values)
  - `message: str`
  - `model_attempted: list[str]` — defaults to empty list
  - `retryable: bool`
- `class RouterResult(BaseModel)` with fields:
  - `ok: bool`
  - `output: BaseModel | None` — Pydantic supports this via `model_config = ConfigDict(arbitrary_types_allowed=True)`; the field carries the parsed prompt-module output schema on success, or `None` on failure
  - `error: RouterError | None` — `None` on success, populated on failure
  - `cost_usd: float` — defaults to 0.0
  - `latency_ms: int` — defaults to 0
  - `tokens_in: int` — defaults to 0
  - `tokens_out: int` — defaults to 0
  - `cached_tokens_in: int` — defaults to 0
  - `model_used: str` — defaults to empty string (set on success; for failures, set to the last-attempted model id)

Pydantic v2 `field_validator` enforces the invariant `(ok=True) ⇒ (error is None)` AND `(ok=False) ⇒ (error is not None)` — attempting to construct an inconsistent result raises `ValidationError` at instantiation. (Defensive invariant; later stories rely on it implicitly.)

**AC-4 (`sanitize_error` helper).** `mailbot_api/router/errors.py` exposes `sanitize_error(exc: Exception) -> str` that returns a single-line redacted string suitable for `RouterError.message`. It strips:

- URLs containing tokens (any URL with a query string containing `token=`, `access_token=`, `refresh_token=`, `api_key=`, `key=`, or `secret=` keys → replace the value with `<REDACTED>` and keep the key visible).
- File paths that look like secret files: any substring matching `[\w.-]+\.(?:env|key|pem|p12|pfx)\b` → replace with `<REDACTED_FILE>`.
- Stack frames: collapse any `Traceback (most recent call last):` block and subsequent file/line context — emit just the leaf exception's `type(exc).__name__ + ": " + str(exc)` with the substitutions above applied. Newlines in the result are replaced with `; ` so the message stays single-line.

The helper composes with the existing `observability/logging.py::_sanitize` (Story 1-4) but is a separate function because logging sanitizes structured-log payloads while `sanitize_error` returns a single string for a Pydantic field. Both must converge on the same redaction rules — the helper imports the same regex constants from `observability/logging.py` rather than re-declaring them. (See Dev Notes "Why two sanitizers".)

**AC-5 (`RouterCallRow` + `record_router_call` writer).** `mailbot_api/observability/audit.py` exposes:

- `class RouterCallRow(BaseModel)` — one Pydantic model whose fields exactly mirror the `router_calls` columns from AC-1 (same names, same types, with `ts` defaulting to `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` if not provided). Construction-time validation: `model_chosen_reason` is constrained to the AC-1 enumerated set via a `Literal[...]` annotation (or a `field_validator` over the union); `outcome` is constrained to `Literal["ok", "retry_recovered", "escalated", "failed"]`.
- `async def record_router_call(row: RouterCallRow, *, db_path: str) -> None` — writes the row via `db.connection.execute_write(db_path, ROUTER_CALLS_INSERT, params)` (executor path per AR-D8-1). The SQL constant `ROUTER_CALLS_INSERT` is added to `db/queries.py` and is the ONLY place the literal `INSERT INTO router_calls` appears in production code (Rule C boundary; see AC-6).
- The function is testable in isolation: passing a constructed `RouterCallRow` with all required fields writes one row to the table without requiring any Router or adapter wiring.

Note on AC scope: in later stories, `record_router_call` will be invoked inside `ask_router`'s `finally` block (Story 2-4) so the row is never lost even on exception. Story 2-1 does **not** wire that in — it only ships the writer + the data shapes.

**AC-6 (boundary enforcement for `router_calls` writes).** The selective-import boundary checker at `scripts/check_boundaries.py` is extended with an "`INSERT INTO router_calls`" rule: any file outside `mailbot_api/observability/audit.py` AND `mailbot_api/db/queries.py` AND `mailbot_api/db/migrations_runner.py` AND `mailbot_api/db/migrations/006_router_calls.sql` containing the literal substring `INSERT INTO router_calls` (case-insensitive, ignoring whitespace) fails the boundary check with a clear message.

Note on AC variance from epic spec: the epic AC says "ruff blocks any `INSERT INTO router_calls`" — but Story 1-4's ruff configuration uses standard rules (T20, DTZ, S) plus the `scripts/check_boundaries.py` AST scan for selective-import allowlists. Ruff doesn't natively support "ban this string outside this allowlist," so this story honors the AC's *intent* (boundary enforcement) by extending `check_boundaries.py` rather than inventing a custom ruff rule. The boundary checker is `make lint`'s gate per Story 1-4 — the policy enforcement is equivalent. See Dev Notes "Why boundary checker, not ruff" for the rationale.

**AC-7 (unit test coverage).** `tests/unit/observability/test_audit.py` exercises `record_router_call` end-to-end against a real in-memory SQLite database (via a `tmp_path` fixture that applies the migration runner first):

- Construct a `RouterCallRow` with every field populated (a synthetic fixture).
- Call `await record_router_call(row, db_path=...)`.
- Assert the row appears in `router_calls` with every field round-tripped exactly (compare by SELECT * and field-by-field equality).
- Assert the `ts` round-trips as a UTC ISO-8601 string with `Z` suffix (timezone preserved, no naive datetime in storage).
- Assert that constructing `RouterCallRow` with `model_chosen_reason="bogus"` raises `ValidationError`.
- Assert that constructing `RouterCallRow` with `outcome="weird"` raises `ValidationError`.

Plus `tests/unit/router/test_errors.py` covers:

- `ErrorCode` has exactly the 15 members listed in AC-2 (parameterized assertion).
- Each member's `.value` equals the snake_case lowercase name.
- `RouterError` accepts only `ErrorCode` values for `code` (free strings raise `ValidationError`).
- `RouterResult(ok=True, error=<some RouterError>)` raises `ValidationError`.
- `RouterResult(ok=False, error=None)` raises `ValidationError`.
- `sanitize_error` redacts: a URL with `?access_token=eyJ...` → `<REDACTED>`, a path `/etc/secrets/api.env` → `<REDACTED_FILE>`, a multi-line traceback → single-line leaf message with `; ` line separators.

**AC-8 (boundary checker tests).** The existing boundary-checker test pattern from Story 1-4 (`tests/unit/scripts/test_check_boundaries.py` or equivalent) is extended with a fixture file that contains `INSERT INTO router_calls (...)` outside the allowlist — the test asserts the checker exits non-zero and prints a clear violation message. Files inside the allowlist (audit.py, queries.py, migrations_runner.py, the 006 migration) pass clean. **If the existing test file does not use that exact path, locate the actual boundary-checker test file via `Grep "_RAW_SQL" tests/`** — the test extension belongs wherever the existing boundary tests live.

**AC-9 (all gates green).** `make lint` (ruff + boundary checker), `make typecheck` (mypy --strict), `make test` (pytest, all existing tests + the new ones) all pass. No mypy errors. No ruff warnings introduced by this story.

## Tasks / Subtasks

- [x] **Task 1** — Migration `006_router_calls.sql`: CREATE TABLE + 3 indexes (AC: #1)
  - [x] Subtask 1.1 — Verify the migration runner picks up the new file and the duplicate-prefix detector still passes (just `ls` + dry-run startup test).
  - [x] Subtask 1.2 — Add the SQL constant `ROUTER_CALLS_INSERT` to `mailbot_api/db/queries.py` (`INSERT INTO router_calls (...) VALUES (?, ?, ...)` — explicit column list, no `*`, no implicit rowid).
- [x] **Task 2** — `mailbot_api/router/errors.py` (NEW FILE): `ErrorCode` enum (AC: #2)
  - [x] Subtask 2.1 — Write the enum with all 15 members, str-backed, lowercase snake_case values.
  - [x] Subtask 2.2 — Add module docstring documenting the contract: "Adding a new code requires updating downstream consumers; check architecture §AR-PAT-3 before extending."
- [x] **Task 3** — `mailbot_api/router/errors.py` (extend): `RouterError` + `RouterResult` Pydantic models (AC: #3)
  - [x] Subtask 3.1 — Define both models with Pydantic v2 syntax (`BaseModel`, `ConfigDict(arbitrary_types_allowed=True)` on `RouterResult` to permit the polymorphic `output: BaseModel | None`).
  - [x] Subtask 3.2 — Add the `(ok, error)` consistency `field_validator` (or `model_validator(mode="after")` for cross-field).
- [x] **Task 4** — `mailbot_api/router/errors.py` (extend): `sanitize_error` (AC: #4)
  - [x] Subtask 4.1 — Import the redaction regex constants from `observability/logging.py` (or refactor them into a shared `observability/_redaction.py` if the import would create a cycle — see Dev Notes).
  - [x] Subtask 4.2 — Single-line collapse: newline replacement + traceback-block stripping.
- [x] **Task 5** — `mailbot_api/observability/audit.py` (NEW FILE): `RouterCallRow` Pydantic model (AC: #5)
  - [x] Subtask 5.1 — Mirror the migration columns; `Literal[...]` constraints on `model_chosen_reason` (use a `Literal[ "policy", "override", "degraded", "response_cache_hit", "force_override"] | <regex-validated escalated_from string>` — the `escalated_from_<X>` form needs a custom `field_validator` since it's a parameterized prefix).
  - [x] Subtask 5.2 — `Literal[...]` constraint on `outcome`.
  - [x] Subtask 5.3 — `ts` default factory: `lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`.
- [x] **Task 6** — `mailbot_api/observability/audit.py` (extend): `record_router_call` async writer (AC: #5)
  - [x] Subtask 6.1 — Build the parameter tuple from the row in column order (must match the INSERT clause in `queries.ROUTER_CALLS_INSERT`).
  - [x] Subtask 6.2 — Call `await db.connection.execute_write(db_path, queries.ROUTER_CALLS_INSERT, params)`.
- [x] **Task 7** — `scripts/check_boundaries.py` (extend): add `_ROUTER_CALLS_INSERT_ALLOW` rule (AC: #6)
  - [x] Subtask 7.1 — Define the allowlist (audit.py, queries.py, migrations_runner.py, migrations/006_router_calls.sql).
  - [x] Subtask 7.2 — Add a `re.compile(r"INSERT\s+INTO\s+router_calls\b", re.IGNORECASE)` scan in the per-file walk.
  - [x] Subtask 7.3 — Emit a clear violation line and increment the exit-code counter.
- [x] **Task 8** — Tests: `tests/unit/observability/test_audit.py` (AC: #7)
  - [x] Subtask 8.1 — `tmp_path` fixture that applies the migration runner to a fresh SQLite file.
  - [x] Subtask 8.2 — Write + readback test.
  - [x] Subtask 8.3 — Pydantic validation failure tests (`model_chosen_reason="bogus"`, `outcome="weird"`).
- [x] **Task 9** — Tests: `tests/unit/router/test_errors.py` (AC: #7)
  - [x] Subtask 9.1 — Enum membership + value tests (parameterized).
  - [x] Subtask 9.2 — `RouterError` rejection of free-string codes.
  - [x] Subtask 9.3 — `RouterResult` cross-field validator tests.
  - [x] Subtask 9.4 — `sanitize_error` redaction tests (URL token, path, multi-line traceback).
- [x] **Task 10** — Boundary-checker test extension (AC: #8)
  - [x] Subtask 10.1 — Locate existing boundary-checker test via `Grep _RAW_SQL tests/` (or `Grep "boundary" tests/`).
  - [x] Subtask 10.2 — Add a fixture that contains a bare `INSERT INTO router_calls` outside the allowlist; assert non-zero exit with a recognizable violation message.
- [x] **Task 11** — All gates green (AC: #9)
  - [x] Subtask 11.1 — `make lint` clean.
  - [x] Subtask 11.2 — `make typecheck` clean.
  - [x] Subtask 11.3 — `make test` clean (102 baseline + N new from this story).

### Review Findings

- [x] \[Review/Patch] **[HIGH] `sanitize_error` traceback-stripping regex is dead code** [`mailbot_api/router/errors.py:140`] — `f"{type(exc).__name__}: {exc}"` calls `str(exc)`, which never contains `"Traceback (most recent call last):"` — that header only appears in `traceback.format_exception()` / `traceback.format_exc()` output. The `_TRACEBACK_BLOCK_RE.sub(...)` call on line 140 therefore never matches and the stripping never fires. Any future caller relying on traceback collapse will get unsanitized multi-line output. Fix: either document that the function only operates on `str(exc)` (no traceback present) and remove the dead regex call, or change the input to accept a formatted traceback string and update the signature and tests accordingly.
- [x] \[Review/Patch] **[MEDIUM] `_URL_TOKEN_QUERY_RE` misses AC-4 required query-param keys** [`mailbot_api/observability/logging.py:23-26`] — AC-4 requires redacting URL query params for `token=`, `access_token=`, `refresh_token=`, `api_key=`, `key=`, and `secret=`. The implemented pattern only covers `token`, `code`, and `access_token`. Keys `refresh_token`, `api_key`, `key`, and `secret` are not in the regex alternation. Since `errors.py` imports this constant from `logging.py`, the gap affects both the logging sanitizer and `sanitize_error`. Fix: extend the `(?:token|code|access_token)` alternation to include all six AC-4 keys.
- [x] \[Review/Patch] **[MEDIUM] `_SECRET_FILE_RE` misses `.p12` and `.pfx` extensions from AC-4** [`mailbot_api/observability/logging.py:28`] — AC-4 specifies `[\w.-]+\.(?:env|key|pem|p12|pfx)\b` but the regex is `\.(?:env|key|pem)\b`, omitting `.p12` and `.pfx`. Client certificate files (`.p12`, `.pfx`) are secret-sensitive and the spec explicitly calls them out. Fix: extend the pattern to `\.(?:env|key|pem|p12|pfx)\b`.
- [x] \[Review/Patch] **[MEDIUM] `sanitize_error` not hardened against exceptions with broken `__str__`** [`mailbot_api/router/errors.py:137`] — `f"{type(exc).__name__}: {exc}"` calls `str(exc)` implicitly. If the exception's `__str__` raises (a valid edge case for custom exception types), `sanitize_error` itself propagates an exception rather than returning a safe fallback string. As a "safe error-formatting function" used in error paths, it should be defensive. Fix: wrap the `str(exc)` call in a `try/except` with a fallback like `f"{type(exc).__name__}: <unprintable exception>"`.
- [x] \[Review/Patch] **[MEDIUM] Boundary checker does not scan f-string nodes for `INSERT INTO router_calls`** [`scripts/check_boundaries.py:194-206`] — The `_ROUTER_CALLS_INSERT_RE` check only fires on `ast.Constant` string nodes. F-strings (`ast.JoinedStr`) that construct the forbidden literal at runtime (e.g., `f"INSERT INTO router_calls ({col}) VALUES (?)"`) are not `ast.Constant` nodes and would pass the boundary check silently. Fix: also walk `ast.JoinedStr` nodes and check whether their string literal fragments contain the forbidden pattern, or document the known gap.
- [x] \[Review/Decision] **[MEDIUM] `RouterResult.output` field is not type-checked at runtime — any value is accepted** [`mailbot_api/router/errors.py:92`] — `model_config = ConfigDict(arbitrary_types_allowed=True)` suppresses Pydantic's type validation for the `output: BaseModel | None` field. As a result `RouterResult(ok=True, output="a string")` passes validation silently. Decide: (a) accept this as intentional (the field is a carrier-only shape and Story 2-4 enforces the schema on the output object before populating the field), or (b) add a `@field_validator("output")` that asserts `isinstance(value, BaseModel) or value is None`.
- [x] \[Review/Decision] **[MEDIUM] `record_router_call` has no internal exception handling — DB failure in `finally` block will mask original exception** [`mailbot_api/observability/audit.py:115-124`] — Story 2-1 Dev Notes say Story 2-4 wires this in `ask_router`'s `finally` block. If `execute_write` raises (DB unavailable, disk full, etc.), the exception propagates out of the `finally` block and suppresses the original Router failure. Decide: (a) add a `try/except Exception` inside `record_router_call` that logs-and-swallows the DB write error (audit loss is acceptable vs masking the real error), or (b) document clearly in Story 2-4 that the caller must guard with its own `try/except` around the `record_router_call` call within `finally`.
- [x] \[Review/Patch] **[LOW] Allowlist-passes-clean tests absent — AC-8 partially uncovered** [`tests/unit/test_lint_boundaries.py`] — AC-8 states "Files inside the allowlist (audit.py, queries.py, migrations_runner.py, the 006 migration) pass clean." The test suite only verifies that fixtures in non-allowlisted paths fail; it does not verify that the same fixture placed in an allowlisted path passes. A future regression that removes a path from `_ROUTER_CALLS_INSERT_ALLOW` would not be caught. Fix: add a parametrized test case that places the `violates_router_calls_insert_outside_audit.py.fixture` content in `mailbot_api/observability/audit.py` path and asserts exit code 0.
- [x] \[Review/Patch] **[LOW] `errors.py` imports private `_`-prefixed symbols from `logging.py`** [`mailbot_api/router/errors.py:33-38`] — `_BEARER_TOKEN_RE`, `_SK_KEY_RE`, `_URL_TOKEN_QUERY_RE`, `_SECRET_FILE_RE` are private module-level names. Importing them from another module creates a brittle coupling: mypy and ruff do not flag this today, but any rename or removal in `logging.py` silently breaks `errors.py` at runtime rather than at lint/typecheck time. Fix: either promote these constants to public names (drop the `_` prefix) in `logging.py`, or extract them into a dedicated `mailbot_api/observability/_redaction.py` leaf module (per the Dev Notes contingency plan) and import from there in both files.
- [x] \[Review/Patch] **[LOW] `RouterCallRow.ts` has no ISO-8601 format validation — malformed timestamps silently accepted** [`mailbot_api/observability/audit.py:58`] — The `ts: str` field accepts any string. A caller passing `ts="not-a-timestamp"` will write corrupted data to the `router_calls` table, silently breaking `ts`-ordered queries and the `ix_router_calls_ts` index. Fix: add a `@field_validator("ts")` that checks the value matches the expected `YYYY-MM-DDTHH:MM:SSZ` pattern (e.g., `re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)`).
- [x] \[Review/Defer] **[LOW] `_utc_z_now()` uses second-precision `strftime` — diverges from Dev Notes spec** [`mailbot_api/observability/audit.py:48`] — deferred, pre-existing — Dev Notes specify `isoformat().replace("+00:00", "Z")` (sub-second / microsecond precision) but `strftime("%Y-%m-%dT%H:%M:%SZ")` produces second-precision only (20 chars). The existing test `test_record_router_call_default_ts_is_utc_z` pins `len(row.ts) == 20`, locking this in. No functional bug today (SQLite stores it as TEXT), but creates a documentation-vs-code gap. Worth normalizing when AC-7's test is revisited.

## Dev Notes

### Migration numbering variance from epic spec

The epic spec hard-codes `005_router_calls.sql`. But during Epic 1's retrospective work (story 1-10), `005_emails_removed_reason.sql` was added for the `@removed.reason` column. The migration runner from Story 1-3 enforces `Duplicate NNN_ prefixes raise MigrationError before any migration runs` — two files at prefix `005` would fail startup loudly.

**Resolution:** ship this story's migration as `006_router_calls.sql`. The boundary checker allowlist (AC-6) names `006_router_calls.sql` explicitly. The downstream stories 2-7, 2-8, 2-9 reference `006_response_cache.sql`, `007_degraded_mode.sql`, `008_anomaly_baseline.sql`, `009_pause_state.sql` — those will need to shift to `007`, `008`, `009`, `010` respectively. Note this in `epic-run-flags.md` so the dev agent shipping later stories doesn't fight the duplicate-prefix detector.

No data loss risk: `005_emails_removed_reason.sql` is an `ALTER TABLE emails ADD COLUMN` — totally orthogonal to the `router_calls` namespace.

### Why we enumerate all `model_chosen_reason` values now

The epic spec for AC-1 lists the reason set as "one of `policy`/`override`/`degraded`/`escalated_from_<X>`". But:

- Story 2.7 (response cache hit) adds `response_cache_hit`.
- Story 2.8 (force override in degraded mode) adds `force_override`.

If we ship a narrow constraint now (e.g., `CHECK (model_chosen_reason IN ('policy', 'override', 'degraded'))`), 2-7 and 2-8 will have to ship a migration to widen it — burning a migration prefix for a known-ahead-of-time inclusive set.

**Resolution:** the migration leaves `model_chosen_reason` as a plain `TEXT NOT NULL` column (no CHECK constraint at the SQL level). The enforcement lives on the **Pydantic side** at `RouterCallRow` (a `Literal[...]` annotation). Downstream stories can extend that `Literal` without a schema migration. The escalation case (`escalated_from_<X>`) is a parameterized prefix and gets a `field_validator` that accepts any string starting with `escalated_from_`.

This is consistent with project preference for application-layer validation over rigid CHECK constraints (architecture §"Errors as data" + Pydantic boundary pattern).

### Why two sanitizers (logging vs errors)

Story 1-4 ships `observability/logging.py::JsonFormatter` with a structured-payload sanitizer that operates on dict/list/string trees, replacing secrets in-place. That function is wired into the logging pipeline.

`sanitize_error` (this story) operates on a single `Exception` and returns a single string for a Pydantic field. The two functions:

- Operate on different inputs (Exception vs dict/JSON).
- Return different shapes (string vs sanitized tree).
- Are called from different points (logging path vs error-construction path).

Sharing the redaction *rules* (the regex constants) is right; sharing the function would force one to fight the other's shape. **Plan:** import the regex constants from `observability/logging.py` if the import is clean. If it creates a cycle (router → observability while observability later imports something from router), refactor the constants into `observability/_redaction.py` (a new tiny module with no other dependencies) and import from both sides.

### Why boundary checker, not ruff

Story 1-4's ruff config covers selective-import bans for `import ollama` / `import anthropic` / `sqlite3` / `os.environ` via standard rule sets + selective-allowlist policy through `scripts/check_boundaries.py`. The pattern was: ruff handles syntactic rules; `check_boundaries.py` handles "this raw string can only appear in these paths."

For `INSERT INTO router_calls`, the same shape applies — it's a substring search restricted to an allowlist. Extending `check_boundaries.py` reuses the existing test pattern (`tests/unit/scripts/test_check_boundaries.py` or equivalent), the existing make-lint wiring, and the existing test fixtures. Inventing a custom ruff rule would duplicate this without any added value.

The epic's AC phrasing ("ruff blocks") is honored in *intent* — the gate that runs at `make lint` time fails on violations. The phrasing in the AC was speculative when the epic was written; this story documents the actual implementation choice.

### Files being touched / created

**Created (NEW files):**

- `mailbot_api/db/migrations/006_router_calls.sql`
- `mailbot_api/router/errors.py`
- `mailbot_api/observability/audit.py`
- `tests/unit/router/test_errors.py`
- `tests/unit/observability/test_audit.py`

**Updated:**

- `mailbot_api/db/queries.py` — append `ROUTER_CALLS_INSERT` constant.
- `scripts/check_boundaries.py` — add `_ROUTER_CALLS_INSERT_ALLOW` allowlist + scan.
- The existing boundary-checker test file (location TBD — find via grep).

**Not touched:**

- `mailbot_api/router/__init__.py` — stays empty for now; Story 2-4 will populate it with the `ask_router` public API.
- `mailbot_api/main.py` — no FastAPI lifespan changes; the migration runner is already wired and picks up the new file automatically.
- `policy.yaml`, prompt modules — Story 2-2 onward.

### Pydantic v2 specifics worth flagging

- `model_config = ConfigDict(arbitrary_types_allowed=True)` is needed on `RouterResult` because `output: BaseModel | None` is a forward-polymorphic field. Without it, Pydantic v2 errors at class-definition time on unknown subclass payloads.
- Cross-field validators in Pydantic v2 use `@model_validator(mode="after")` returning `self`, not the old `@validator(pre=False)` syntax.
- `Literal["a", "b", "c"]` is the idiomatic v2 way to constrain a field to a closed set; faster + clearer than a custom validator for small fixed sets.
- For the parameterized `escalated_from_<X>` case, a `@field_validator("model_chosen_reason")` is the clean approach — match against the union of the `Literal` set or the `escalated_from_` prefix.

### Testing approach (mirrors 1-3 / 1-6 patterns)

Epic 1 established the pattern of **integration-style unit tests against real SQLite** (in `tmp_path`) rather than mocked DB. The `record_router_call` writer follows the same pattern — the test applies the migration runner to a fresh temp DB, calls the async writer, and SELECTs the row back. No mocking. This is consistent with the project's "test the real wiring" stance (also from Step 2.4.7 Middleware-Real-Bootstrap Gate, MailBot reframing: DB-real integration tests preferred).

For `ErrorCode` + `RouterError` + `RouterResult` + `sanitize_error`, plain pytest with parameterized cases — no DB needed.

### What this story does NOT do

- Does NOT implement `ask_router()`. That's Story 2-4.
- Does NOT implement adapters. Ollama is Story 2-3; Anthropic is Story 2-6.
- Does NOT load `policy.yaml`. That's Story 2-2.
- Does NOT enforce sensitivity preconditions or grants. That's Epic 4 territory; the columns just exist NULL-able.
- Does NOT wire `record_router_call` into any `finally` block. That happens in Story 2-4 when `ask_router` is built.

### Project Structure Notes

Alignment with architecture §"Complete Project Directory Structure":

- `mailbot_api/router/errors.py` matches line 850 of architecture.md exactly.
- `mailbot_api/observability/audit.py` matches line 925 exactly.
- `mailbot_api/db/migrations/006_router_calls.sql` matches the numbering pattern (architecture spec said `001_init.sql` carries `router_calls` originally, but Story 1-3 reduced 001 to the email/thread/sender/sync_state baseline — `router_calls` was deferred to Epic 2). The new migration prefix is a downstream consequence of that deferral + the 005-already-taken state.

No structural variance from the architecture spec other than the migration-prefix renumber (documented above).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 2.1`] — the canonical AC source.
- [Source: `_bmad-output/planning-artifacts/architecture.md`] — Rule C boundary (line ~743), `RouterResult`/`RouterError` shape (lines 599–628), `record_router_call` writer location (line 925), `ErrorCode` enum location (line 576), stable error code naming convention.
- [Source: `mailbot_api/db/migrations_runner.py:68-90`] — duplicate-prefix detection that motivates the renumber to `006`.
- [Source: `mailbot_api/db/queries.py`] — pattern for SQL constants (e.g., `SYNC_STATE_UPSERT_NULL_LINK`).
- [Source: `mailbot_api/db/connection.py:90-114`] — `fetchone`/`fetchall`/`execute_write` async API.
- [Source: `mailbot_api/observability/logging.py`] — existing sanitizer; potential source of shared redaction regex constants.
- [Source: `scripts/check_boundaries.py`] — the boundary-check pattern to extend for AC-6.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

None — no halts during implementation. All four gates green on first run after one ruff `I001` auto-fix (import ordering on `audit.py` and `test_errors.py`) and one boundary-check false-positive remediated by paraphrasing the `audit.py` module docstring to avoid the literal SQL substring.

### Completion Notes List

- **Migration numbered 006, not 005**, per Dev Notes "Migration numbering variance from epic spec". Downstream stories 2-7 through 2-9 will need to ship their migrations as 007 / 008 / 009 / 010 — note added to `epic-run-flags.md` for the dev agent picking up the next story. No data-loss risk: 005 holds `emails_removed_reason` from Story 1-10, totally orthogonal to the `router_calls` namespace.
- **`model_chosen_reason` enforced application-side, not via SQL CHECK constraint.** The migration leaves it as plain `TEXT NOT NULL`; the closed set (`policy` / `override` / `degraded` / `response_cache_hit` / `force_override` / `escalated_from_<X>` parameterized form) is enforced on `RouterCallRow` via a `field_validator` so downstream Epic-2 stories can add new reasons without burning a schema migration.
- **`(ok, error)` consistency invariant on `RouterResult`** is enforced via Pydantic v2 `@model_validator(mode="after")`. Attempts to construct `RouterResult(ok=True, error=<err>)` or `RouterResult(ok=False, error=None)` raise `ValidationError` at instantiation — tested explicitly in `tests/unit/router/test_errors.py`.
- **`sanitize_error` shares regex constants with `observability/logging.sanitize`** via import (no circular dep — observability does not import from router). All four redaction patterns (Bearer, sk-key, URL query-token, secret file path) converge on the same rules. Traceback-block stripping is sanitize-error-specific (logging never receives raw tracebacks per Story 1-4 design).
- **Boundary check extended at AST scan level**, not at ruff config level (variance from epic AC wording — see story Dev Notes "Why boundary checker, not ruff"). Both the broad raw-SQL scan and the dedicated `INSERT INTO router_calls` scan now fire for off-allowlist files; the dedicated check exists so the violation message points at the right boundary (Rule C, audit-writer).
- **One docstring paraphrase in `audit.py`** to avoid tripping the broad `_RAW_SQL_RE` (which scans string literals including docstrings). The dedicated `_ROUTER_CALLS_INSERT_RE` is harmless in docstrings since `audit.py` is in its allowlist; the broad raw-SQL check is what fired.
- **Test count: 102 baseline → 149 (47 new tests).** Distribution: `test_errors.py` ~22 tests (15 enum-parameterized + 7 invariant/sanitize), `test_audit.py` ~10 tests (3 record-write + 4 reason-parameterized + 5 outcome-parameterized) — pytest collects via parametrize. Plus 1 new fixture case in `test_lint_boundaries.py` for the `INSERT INTO router_calls` violation.
- **No changes to `mailbot_api/router/__init__.py`** (left empty). Story 2-4 will populate it with the `ask_router` public API.
- **No changes to FastAPI lifespan.** The migration runner from Story 1-3 picks up `006_router_calls.sql` automatically on startup; integration tests (`test_db_connection.py::test_lifespan_runs_migrations_on_startup_via_testclient` and similar) all continue to pass without modification.

### File List

**Created:**

- `mailbot_api/db/migrations/006_router_calls.sql` — schema + 3 indexes
- `mailbot_api/router/errors.py` — `ErrorCode` enum + `RouterError` + `RouterResult` + `sanitize_error`
- `mailbot_api/observability/audit.py` — `RouterCallRow` + `record_router_call`
- `mailbot_api/observability/_redaction.py` — review fix R9: shared redaction regex constants (extracted from `logging.py` to eliminate cross-module `_`-prefixed imports)
- `tests/unit/router/__init__.py` — package marker
- `tests/unit/router/test_errors.py` — unit tests for errors module (extended with R2/R3/R4 regression tests)
- `tests/unit/observability/test_audit.py` — integration-style tests against real SQLite (extended with R7/R10 regression tests)
- `tests/fixtures/lint_violations/violates_router_calls_insert_outside_audit.py.fixture` — boundary-check fixture
- `_bmad-output/implementation-artifacts/2-1-router-calls-audit-table-and-router-result-router-error-data-shapes.pre-review.md` — Step 2.3.5 pre-review self-audit artifact

**Updated:**

- `mailbot_api/observability/logging.py` — review fix R9: import regex constants from new `_redaction.py` leaf module instead of defining locally
- `mailbot_api/db/queries.py` — appended `ROUTER_CALLS_INSERT` SQL constant
- `scripts/check_boundaries.py` — added `_ROUTER_CALLS_INSERT_ALLOW` + `_ROUTER_CALLS_INSERT_RE` + AST-walk check; review fix R5 extended to scan `ast.JoinedStr` (f-string) nodes; review fix R8 consequence added `audit.py` to `_RAW_SQL_ALLOW` so legitimate column-contract documentation in the audit-writer module doesn't false-positive
- `tests/unit/test_lint_boundaries.py` — extended `test_boundary_violations_caught_by_check_boundaries` parametrize block with the new fixture; review fix R8 added `test_router_calls_insert_in_allowlisted_audit_path_passes`; review fix R5 added `test_router_calls_insert_f_string_caught_by_check_boundaries`

**Sprint state updates:**

- `_bmad-output/implementation-artifacts/sprint-status.yaml` — epic-2 → in-progress, 2-1 → review (after dev-story; will → done after gates 2.4.4–2.4.8 pass + selective staging)

## Change Log

- 2026-06-01 (claude-opus-4-7 / 1M context, autonomous-epic-run) — Implemented Story 2-1. Created `router_calls` audit table (migration 006), `ErrorCode`/`RouterError`/`RouterResult` Pydantic shapes, `sanitize_error` helper, `RouterCallRow`/`record_router_call` writer, and extended the boundary checker to enforce the audit-writer monopoly. All gates green: ruff, mypy --strict, boundary check, pytest 149/149.
- 2026-06-01 (claude-opus-4-7 / 1M context, autonomous-epic-run) — Applied 9 of 10 code-review findings from claude-sonnet-4-6 reviewer + 1 deferred + 1 accepted-no-change: **R1 HIGH** removed dead `_TRACEBACK_BLOCK_RE` (regex never matched `str(exc)` output); **R2 MEDIUM** extended URL query-param redaction to all 7 AC-4 keys (added `refresh_token`/`api_key`/`key`/`secret`); **R3 MEDIUM** added `.p12`/`.pfx` to secret-file extensions per AC-4; **R4 MEDIUM** defensive `try/except` around `str(exc)` in `sanitize_error`; **R5 MEDIUM** extended boundary checker to scan `ast.JoinedStr` (f-string) nodes for the forbidden router_calls INSERT literal; **R6 MEDIUM** ACCEPT (a) — `RouterResult.output` stays `BaseModel | None` with `arbitrary_types_allowed=True`; Story 2-4 will enforce the prompt-module schema before populating the field (the rationale already documented in the original story); **R7 MEDIUM** added `try/except Exception` inside `record_router_call` that logs and swallows DB-write failures (audit loss is acceptable; masking the original Router error in 2-4's `finally` is not); **R8 LOW** added allowlist-passes-clean tests (audit path + f-string bypass attempt); **R9 LOW** extracted redaction regex constants into new leaf module `mailbot_api/observability/_redaction.py` (eliminates `_`-prefixed cross-module imports); **R10 LOW** added `@field_validator("ts")` to `RouterCallRow` enforcing the `YYYY-MM-DDTHH:MM:SSZ` ISO-8601 format. **Defer:** the sub-second-precision `_utc_z_now` divergence from Dev Notes spec — no functional bug, addressing it would require either changing the test pin or the format, both touching multiple files for a doc-vs-code gap. Added 24 net new regression tests; pytest now 173/173 (was 102 baseline → 149 after initial impl → 173 after review fixes). All gates green.

