"""Integration tests for db/connection.py and db/migrations_runner.py.

Per the Middleware-Real-Bootstrap MailBot reframing (Step 2.4.7): tests run against
a real on-disk SQLite (tmp_path) with real migrations — NEVER mocked DB.

pytest-asyncio asyncio_mode = "auto" — async tests don't need decorators.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write, fetchall, fetchone, get_connection
from mailbot_api.db.migrations_runner import (
    MigrationError,
    _apply_one_migration_atomically,
    _open_connection,
    apply_pending_migrations,
)


def test_pragmas_applied_on_every_connection(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    with get_connection(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


async def test_fetchone_select_one(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    with get_connection(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    row = await fetchone(db_path, "SELECT 1", ())
    assert row == (1,)


async def test_execute_write_then_fetchone(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    with get_connection(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    rowcount = await execute_write(db_path, "INSERT INTO t (x) VALUES (?)", (42,))
    assert rowcount == 1
    row = await fetchone(db_path, "SELECT x FROM t WHERE x = ?", (42,))
    assert row == (42,)


async def test_execute_write_multiple_rows_atomicity(tmp_path: Path) -> None:
    """CR-9: multi-row insert via execute_write — exercises the BEGIN/COMMIT
    transaction path under realistic usage."""
    db_path = str(tmp_path / "test.db")
    with get_connection(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER PRIMARY KEY)")
        conn.commit()
    # Three writes through execute_write
    for x in (1, 2, 3):
        rowcount = await execute_write(db_path, "INSERT INTO t (x) VALUES (?)", (x,))
        assert rowcount == 1
    rows = await fetchall(db_path, "SELECT x FROM t ORDER BY x", ())
    assert rows == [(1,), (2,), (3,)]


async def test_execute_write_rolls_back_on_constraint_violation(tmp_path: Path) -> None:
    """CR-2: explicit transaction means a failed write does NOT commit a partial row."""
    db_path = str(tmp_path / "test.db")
    with get_connection(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER PRIMARY KEY)")
        conn.commit()
    await execute_write(db_path, "INSERT INTO t (x) VALUES (?)", (1,))
    with pytest.raises(Exception):
        # Same primary key — UNIQUE constraint violation, rolled back.
        await execute_write(db_path, "INSERT INTO t (x) VALUES (?)", (1,))
    rows = await fetchall(db_path, "SELECT x FROM t", ())
    assert rows == [(1,)]  # Only the first write committed.


async def test_fetchall_returns_list(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    with get_connection(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1), (2), (3)")
        conn.commit()
    rows = await fetchall(db_path, "SELECT x FROM t ORDER BY x", ())
    assert rows == [(1,), (2,), (3,)]


def test_migrations_runner_applies_001_init(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    applied = apply_pending_migrations(db_path)
    assert "001_init.sql" in applied

    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '\\_%' ESCAPE '\\' ORDER BY name"
        ).fetchall()
    table_names = {r[0] for r in rows}
    assert {"emails", "threads", "senders", "sync_state"}.issubset(table_names)


def test_migrations_runner_is_idempotent(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    first = apply_pending_migrations(db_path)
    assert first
    second = apply_pending_migrations(db_path)
    assert second == []


def test_emails_table_has_derived_field_companion_columns(tmp_path: Path) -> None:
    """Per FR-2.1: every derived signal carries *_prompt_v, *_conf, *_model, *_at."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)").fetchall()}

    for derived_field in (
        "sensitivity",
        "class_coarse",
        "class_fine",
        "summary_short",
        "importance_score",
        "action_extraction",
        "embedding",
    ):
        for suffix in ("_prompt_v", "_conf", "_model", "_at"):
            assert f"{derived_field}{suffix}" in cols, f"Missing {derived_field}{suffix}"

    assert "change_marker" in cols  # AR-SCHEMA-2
    assert "deleted_at" in cols  # FR-1.3


def test_migrations_runner_atomic_apply_on_failure(tmp_path: Path) -> None:
    """CR-1 + CR-4: if the migration SQL fails partway, neither the partial DDL
    nor the _migrations row should be persisted."""
    db_path = str(tmp_path / "test.db")
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    # CREATE TABLE `good` succeeds; then INSERT into a non-existent table fails.
    # SQLite accepts arbitrary column-type names (typeless affinity), so the failure
    # must come from a missing-table reference, not a bogus column type.
    (mig_dir / "001_first.sql").write_text(
        "CREATE TABLE good (x INTEGER);\n"
        "INSERT INTO nonexistent_table_for_test_failure (x) VALUES (1);\n"
    )

    with pytest.raises(MigrationError):
        apply_pending_migrations(db_path, mig_dir)

    # Confirm: no _migrations row, no `good` table left half-created.
    conn = _open_connection(db_path)
    try:
        # _migrations table exists (we create it before any migration runs)
        cur = conn.execute("SELECT filename FROM _migrations")
        assert cur.fetchall() == []
        # The `good` table was created in the same transaction as the failing
        # `bad` statement. With explicit BEGIN/ROLLBACK, `good` MUST be gone.
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='good'"
        )
        assert cur.fetchall() == []
    finally:
        conn.close()


def test_migrations_runner_rejects_duplicate_prefixes(tmp_path: Path) -> None:
    """CR-6: two files with the same NNN_ prefix raise a clear error."""
    db_path = str(tmp_path / "test.db")
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_first.sql").write_text("CREATE TABLE a (x INTEGER);\n")
    (mig_dir / "001_second.sql").write_text("CREATE TABLE b (x INTEGER);\n")

    with pytest.raises(MigrationError, match="[Dd]uplicate"):
        apply_pending_migrations(db_path, mig_dir)


def test_lifespan_runs_migrations_on_startup_via_testclient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-7: exercise the real ASGI lifespan path via FastAPI's TestClient context
    manager, which drives startup/shutdown messages through the app exactly as
    uvicorn does. (httpx.ASGITransport does NOT trigger lifespan events on its own.)"""
    from fastapi.testclient import TestClient

    from mailbot_api.main import app

    db_path = str(tmp_path / "lifespan.db")
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    # Story 2-2: lifespan now also loads policy.yaml. Point at the project-root
    # starter file so the lifespan can boot cleanly.
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    # Story 3-3: lifespan also loads sensitivity_patterns.yaml.
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200

    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT filename FROM _migrations ORDER BY filename").fetchall()
    assert ("001_init.sql",) in rows


def test_lifespan_raises_when_db_path_unset_and_not_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-10: missing MAILBOT_DB_PATH without MAILBOT_SKIP_DB=1 is a fatal misconfig."""
    monkeypatch.delenv("MAILBOT_DB_PATH", raising=False)
    monkeypatch.delenv("MAILBOT_SKIP_DB", raising=False)

    from mailbot_api.main import lifespan

    async def _run() -> None:
        async with lifespan(None):  # type: ignore[arg-type]
            pass

    with pytest.raises(RuntimeError, match="MAILBOT_DB_PATH"):
        asyncio.run(_run())


def test_lifespan_skips_db_when_skip_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-10: MAILBOT_SKIP_DB=1 allows static health-only tests to bypass DB setup.

    Story 2-2: also requires MAILBOT_SKIP_POLICY=1 for the prior minimal-static-
    health behavior — DB-skip and policy-skip are now independent flags
    (review fix HIGH: policy load is decoupled from DB-skip branch).
    """
    monkeypatch.delenv("MAILBOT_DB_PATH", raising=False)
    monkeypatch.setenv("MAILBOT_SKIP_DB", "1")
    monkeypatch.setenv("MAILBOT_SKIP_POLICY", "1")

    from mailbot_api.main import lifespan

    async def _run() -> None:
        async with lifespan(None):  # type: ignore[arg-type]
            pass

    # Should not raise.
    asyncio.run(_run())


def test_lifespan_loads_policy_when_db_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story 2-2 / review fix HIGH: SKIP_DB=1 alone does NOT skip policy load.

    Tests that need to exercise Router-side code without a DB set
    MAILBOT_SKIP_DB=1 + MAILBOT_POLICY_PATH=<test fixture>; the policy
    snapshot must be initialized so get_policy() / snapshot_for_dispatch()
    succeed (no opaque RuntimeError from the carrier-only state)."""
    monkeypatch.delenv("MAILBOT_DB_PATH", raising=False)
    monkeypatch.delenv("MAILBOT_SKIP_POLICY", raising=False)
    monkeypatch.setenv("MAILBOT_SKIP_DB", "1")
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    # Story 3-3: lifespan also loads sensitivity_patterns.yaml.
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )

    from mailbot_api.main import lifespan
    from mailbot_api.router.policy import get_policy

    async def _run() -> None:
        async with lifespan(None):  # type: ignore[arg-type]
            # Inside the lifespan, the snapshot must be loaded.
            assert get_policy().version  # non-empty string

    asyncio.run(_run())


def test_apply_one_migration_atomically_with_inline_helper(tmp_path: Path) -> None:
    """Direct unit-style test of the atomic helper used by the runner."""
    db_path = str(tmp_path / "atom.db")
    conn = _open_connection(db_path)
    try:
        conn.execute(
            "CREATE TABLE _migrations (filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.commit()
        mig = tmp_path / "002_test.sql"
        mig.write_text("CREATE TABLE atomtest (x INTEGER);\n")
        _apply_one_migration_atomically(conn, mig)
        # Both the DDL and the bookkeeping insert landed.
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name='atomtest'"
        ).fetchone() is not None
        assert conn.execute(
            "SELECT 1 FROM _migrations WHERE filename='002_test.sql'"
        ).fetchone() == (1,)
    finally:
        conn.close()
