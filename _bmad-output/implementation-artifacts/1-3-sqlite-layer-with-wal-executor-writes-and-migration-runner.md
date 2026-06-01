# Story 1.3: SQLite layer with WAL, executor writes, and migration runner

Status: done

## Story

As Adam,
I want the SQLite connection layer with WAL mode, `busy_timeout=5000`, async wrappers, and a migrations runner that applies numbered `.sql` files at startup,
so that every later story has a working `db.fetchone()` / `db.execute_write()` interface and a clean way to add tables.

## Acceptance Criteria

**AC-1.** `mailbot_api/db/connection.py` opens SQLite connections to `MAILBOT_DB_PATH`, applies pragmas `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON` on every connection, and exposes async `fetchone(query, params)`, `fetchall(query, params)`, `execute_write(query, params)` functions. Writes dispatch through `run_in_executor` so they never block the event loop. Reads run synchronously on the event loop. Every connection is acquired per-call and closed promptly.

**AC-2.** `mailbot_api/db/migrations_runner.py` creates `_migrations` table if missing, then applies any `NNN_*.sql` file in `mailbot_api/db/migrations/` not yet recorded, in numeric order, inserting a `(filename, applied_at)` row on success. A failed migration aborts startup with a structured log line and non-zero exit.

**AC-3.** Initial migration `mailbot_api/db/migrations/001_init.sql` creates `emails`, `threads`, `senders`, `sync_state` tables per architecture.md §2 schema (incl. derived-field companion columns `*_prompt_v`, `*_conf`, `*_model`, `*_at` per FR-2.1 and `emails.change_marker` per AR-SCHEMA-2). All timestamps stored as TEXT UTC ISO-8601 with `Z` suffix (AR-PAT-3). Table names plural snake_case; column names snake_case (AR-PAT-2). Indexes follow `ix_<table>_<col>` convention.

**AC-4.** `db.fetchone("SELECT 1")` from async context returns `(1,)` and does not raise.

## Tasks / Subtasks

- [ ] Task 1 — `mailbot_api/db/connection.py` with `get_connection() -> sqlite3.Connection` context manager applying pragmas; async wrappers `fetchone`, `fetchall`, `execute_write`
- [ ] Task 2 — `mailbot_api/db/migrations_runner.py` with `apply_pending_migrations(db_path)` function
- [ ] Task 3 — `mailbot_api/db/migrations/001_init.sql` with emails/threads/senders/sync_state tables + indexes
- [ ] Task 4 — `mailbot_api/main.py` startup hook calls `apply_pending_migrations(MAILBOT_DB_PATH)` on FastAPI startup (lifespan handler)
- [ ] Task 5 — Integration tests against a real on-disk SQLite (no mocks — per Middleware-Real-Bootstrap MailBot reframing)
- [ ] Task 6 — Verify all three gates green

## Dev Notes

- Per architecture AR-D14-1: stdlib `sqlite3` only, no SQLAlchemy/aiosqlite/ORM, raw SQL migrations.
- Per architecture AR-D8-1: WAL mode + `busy_timeout=5000` + all writes through `run_in_executor`; reads stay on event loop (sub-ms in WAL).
- Per architecture AR-D8-2: pragmas applied on every connection; one connection per task; short-lived; closed promptly.
- `MAILBOT_DB_PATH` read directly from `os.environ` here is permitted ONLY because story 1-4 has not yet shipped `mailbot_api/config.py` with `get_secret()`. Story 1-4's lint rules WILL flag this — story 1-4 must refactor `db/connection.py` to call `get_secret("MAILBOT_DB_PATH")` instead. Mark this as a known follow-up.
- `emails` table schema: `id`, `graph_id` (TEXT UNIQUE), `change_marker`, `thread_id`, `sender_id`, `received_at` (TEXT UTC), `from_address`, `from_display_name`, `subject`, `body_preview`, `has_attachments` (INTEGER 0/1), `deleted_at` (TEXT, nullable). Plus derived-field columns: `sensitivity` + companion 4-tuple; `class_coarse` + companion; `class_fine` + companion; `summary_short` + companion; `importance_score` + companion; `embedding` (BLOB) + companion. Companion tuple is always `<field>_prompt_v` `<field>_conf` `<field>_model` `<field>_at`.
- `threads` table: `id` (TEXT, conversation_id from Graph), `subject_normalized`, `last_message_at`, `message_count`.
- `senders` table: `id` (TEXT, email address lowercased), `display_name`, `domain`, `first_seen_at`, `sender_reputation_summary` (TEXT, nullable — populated in epic 3).
- `sync_state` table: single-row keyed by `provider="microsoft_graph"`; `delta_link`, `last_sync_at`, `last_sync_messages_seen`.

### References

- architecture.md §AR-D8-1/2 (WAL pragmas)
- architecture.md §AR-D14-1 (stdlib sqlite3 + raw SQL)
- architecture.md §AR-SCHEMA-2 (emails.change_marker)
- architecture.md §"Complete Project Directory Structure" (db/ layout)
- epics.md §"Story 1.3"

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

### Completion Notes List

- 4 new files: `mailbot_api/db/connection.py` (WAL pragmas + async wrappers + explicit BEGIN IMMEDIATE / COMMIT for writes); `mailbot_api/db/migrations_runner.py` (numeric-prefix discovery + duplicate-prefix detection + atomic apply via executescript-wrapped BEGIN/COMMIT); `mailbot_api/db/migrations/001_init.sql` (emails/threads/senders/sync_state + all derived-field companion columns); updated `mailbot_api/main.py` (FastAPI lifespan applies migrations on startup, raises RuntimeError on missing MAILBOT_DB_PATH unless MAILBOT_SKIP_DB=1).
- 1 new test file `tests/integration/test_db_connection.py` with 18 tests — all real on-disk SQLite via tmp_path per Middleware-Real-Bootstrap MailBot reframing.
- Code review (Sonnet 4.6) raised 10 issues; **8 applied** (CR-1 + CR-4 atomic apply via composite executescript with embedded BEGIN/INSERT/COMMIT; CR-2 explicit BEGIN IMMEDIATE/COMMIT in execute_write; CR-3 RuntimeError instead of sys.exit; CR-6 duplicate-prefix detection in `_discover_migrations`; CR-7 lifespan test rewritten to use FastAPI TestClient context-manager which actually drives lifespan events — httpx ASGITransport does NOT trigger lifespan; CR-9 added multi-row execute_write test + rollback-on-constraint test; CR-10 raise on missing MAILBOT_DB_PATH unless MAILBOT_SKIP_DB=1).
- **2 deferred:** CR-5 (sync reads on event loop — architecture AR-D8-1 permits it; documented as known limitation in connection.py module docstring); CR-8 (embedding BLOB needs dtype/shape contract — owned by epic-3 story 3-4 which writes the embedding column; flagged in epic-run-flags.md).
- Self-fix during dev pass: my first `_apply_one_migration_atomically` used `.split(";")` which broke on multi-line SQL comments containing semicolons. Replaced with `executescript` of a composite BEGIN+body+INSERT+COMMIT — executescript correctly handles SQL parsing.
- Gates green: 18 passed, ruff All checks passed, mypy 15 source files no issues. One StarletteDeprecationWarning about httpx (unrelated to story).

### File List

- `mailbot_api/db/connection.py`
- `mailbot_api/db/migrations_runner.py`
- `mailbot_api/db/migrations/001_init.sql`
- `mailbot_api/main.py` (updated to add lifespan)
- `tests/integration/test_db_connection.py`
- `_bmad-output/implementation-artifacts/1-3-sqlite-layer-with-wal-executor-writes-and-migration-runner.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Code Review Findings (Sonnet 4.6)

- [x] **[HIGH] CR-1 — `executescript` silently commits any open transaction, making the _migrations INSERT unreachable on the same connection.** `executescript()` issues an implicit `COMMIT` before running the SQL, which closes any autocommit-mode transaction and also resets connection state. With `isolation_level=None` (autocommit), each `conn.execute()` statement is its own transaction. The sequence `conn.executescript(sql)` → `conn.execute("INSERT INTO _migrations …")` is fine for the INSERT itself, but if `executescript` fails mid-script (e.g., on a multi-statement migration), SQLite has already committed whatever statements ran before the failure. There is no wrapping `BEGIN … ROLLBACK` guard, so a partially-applied migration is silently recorded as "pending" on next startup but may leave the schema in a broken state. Fix: wrap each migration in an explicit `BEGIN; … COMMIT;` block inside the SQL file, or switch from `executescript` to iterating `conn.execute()` calls inside a manual `BEGIN`/`ROLLBACK` transaction.

- [x] **[HIGH] CR-2 — Writes are not wrapped in an explicit transaction; autocommit means each statement commits independently, risking torn writes.** `isolation_level=None` puts the connection in autocommit mode. `_execute_write_sync` calls `conn.execute(query, params)` with no surrounding `BEGIN`. For single-row INSERTs this is safe, but callers expecting atomic multi-statement writes (future stories) will silently get per-statement commits. Architecture AR-D8-1 specifies executor writes but does not prohibit transactions; `execute_write` should at minimum document this constraint, or be refactored to accept a sequence of statements and wrap them in `BEGIN IMMEDIATE … COMMIT`.

- [x] **[HIGH] CR-3 — `sys.exit(1)` inside a FastAPI lifespan does not cleanly abort startup; it raises `SystemExit` which asyncio/uvicorn catches and may swallow or convert to an unclean shutdown.** FastAPI lifespans run inside the uvicorn async machinery. `SystemExit` raised inside an `asynccontextmanager` before the `yield` propagates as an exception through the async generator, which uvicorn logs but may not surface as a non-zero container exit code depending on the version. The intent (abort startup loudly) is not reliably achieved. Fix: raise a `RuntimeError` instead, which propagates through the lifespan and causes uvicorn to exit with code 1.

- [x] **[MEDIUM] CR-4 — `executescript` commits the migration SQL but the subsequent `conn.execute("INSERT INTO _migrations …")` runs in a separate autocommit transaction; a crash between the two leaves the migration applied but unrecorded, causing it to be re-applied on next startup.** This is a TOCTOU/partial-application risk. The migration DDL is committed by `executescript`'s implicit COMMIT, then the bookkeeping INSERT is a separate autocommit transaction. A process kill or power loss in that window re-runs the migration, which will fail if the migration uses `CREATE TABLE` without `IF NOT EXISTS`, or silently create duplicate data if it uses INSERTs. Fix: include the `_migrations` INSERT inside the same transaction as the migration SQL, either via `executescript` appending the INSERT, or by switching to a connection-level transaction.

- [ ] **[MEDIUM] CR-5 `[deferred: architecture-permits-sync-reads-in-WAL; documented as known limitation in connection.py module docstring; no story currently owns the future migration to executor-dispatched reads]` — `fetchone` and `fetchall` run synchronously on the event loop despite the docstring admitting this is a "sub-ms in WAL" assumption.** The async wrappers (`fetchone`, `fetchall`) do not use `run_in_executor`, meaning a slow read (cold page cache, large result set, or lock contention) blocks the entire asyncio event loop and stalls all concurrent FastAPI requests. The architecture permits this for now, but there is no enforcement mechanism (e.g., a query timeout or row limit) to bound the blocking time. This is a latency-correctness risk as the database grows. At minimum, document this as a known limitation with a story reference for future migration to executor-dispatched reads.

- [x] **[MEDIUM] CR-6 — `_discover_migrations` uses `Path.iterdir()` which is non-deterministic on some filesystems; duplicate numeric prefixes (e.g., two files starting with `003_`) silently run both in arbitrary order.** The sort is by integer prefix only, so two files sharing the same number are sorted by Python's stable sort on their original `iterdir()` order (OS-dependent). There is no duplicate-prefix check. Fix: after sorting, assert that all numeric prefixes are unique and raise a clear error if not.

- [x] **[MEDIUM] CR-7 — `test_lifespan_runs_migrations_on_startup` passes `None` as the `_app` argument, which does not exercise any code path that uses the FastAPI app instance; if lifespan ever accesses `_app`, this test would silently miss the failure.** The test calls `lifespan(None)` with a `type: ignore` comment. The current lifespan ignores `_app`, so the test passes. However, this means the test provides no coverage for lifespan code that would use the app (e.g., attaching state via `_app.state`). The test comment acknowledges this with `type: ignore` but the gap is structural: a real lifespan invocation via `TestClient` or `httpx.AsyncClient(app=app, lifespan="auto")` would catch such regressions. Medium severity because the current code is safe, but the test gives false confidence about future lifespan changes.

- [ ] **[MEDIUM] CR-8 `[deferred: epic-3-owns-embedding-write-path; flagged for epic-run-flags.md retro action — needs embedding_dtype + embedding_shape companion columns or JSON serialization decided in story 3-4]` — `embedding BLOB` stores raw bytes but there is no serialization contract enforced at the DB layer; numpy `ndarray.tobytes()` output is architecture-dependent (dtype, endianness, shape) and will silently corrupt on a platform change.** The schema comment says "raw bytes; cosine search uses numpy in verbs" but nothing in the DB layer enforces or records the dtype/shape metadata needed to reconstruct the array. A float32 embedding stored on one machine read back as float64 on another yields a wrong vector with no error. Fix: either store embeddings as a JSON array (portable, self-describing, slightly larger) or add `embedding_dtype` and `embedding_shape` companion columns so the deserializer can reconstruct faithfully.

- [x] **[LOW] CR-9 — `test_fetchall_returns_list` inserts rows using `get_connection` directly (synchronous), bypassing `execute_write`; if a future refactor adds logic to `execute_write` (e.g., logging, retry), this test would miss it.** The setup uses `conn.execute("INSERT INTO t VALUES (1), (2), (3)")` in a raw connection block rather than `await execute_write(...)`. This is a test isolation gap: the async `execute_write` path is only tested by `test_execute_write_then_fetchone`, which only tests a single-row insert. Consider adding a multi-row insert through `execute_write` to verify the executor dispatch path under `fetchall`.

- [x] **[LOW] CR-10 — `lifespan` silently skips migrations when `MAILBOT_DB_PATH` is unset rather than failing loudly.** If the environment variable is missing, `db_path` is `None` and the `if db_path:` block is skipped with no log line. This means the app starts normally but is running against no database — every subsequent DB call will fail at runtime with an unclear error. A missing `MAILBOT_DB_PATH` should be treated as a fatal misconfiguration and raise immediately in the lifespan, not silently degrade.
