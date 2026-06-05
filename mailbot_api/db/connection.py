"""SQLite connection layer per architecture AR-D8-1/2 and AR-D14-1.

- stdlib sqlite3 only (no SQLAlchemy, no aiosqlite, no ORM).
- Every connection applies: journal_mode=WAL, synchronous=NORMAL, busy_timeout=5000, foreign_keys=ON.
- Reads run synchronously on the event loop (sub-ms in WAL per AR-D8-1).
- Writes dispatch through asyncio.get_running_loop().run_in_executor so slow
  writes/checkpoints never stall the chat-serving FastAPI process.
- One connection per call; short-lived; closed promptly.
- Each write runs inside an explicit BEGIN IMMEDIATE / COMMIT transaction (per CR-2)
  to avoid torn writes across multi-statement future use.

NOTE: Story 1-4 will move the os.environ read for MAILBOT_DB_PATH into config.py's
get_secret() — at which point the lint rule from 1-4 will flag any os.environ
read here. For now (1-3), the path is passed in as a parameter to make this
module pure; the caller (main.py lifespan + tests) supplies the path.

KNOWN LIMITATION (per CR-5, architecture-accepted): reads run synchronously on the
event loop. Architecture AR-D8-1 permits this on the assumption that WAL reads
are sub-millisecond. If a slow read ever blocks chat-serving latency, refactor
fetchone/fetchall to also dispatch through run_in_executor. No story currently
owns this future migration.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA busy_timeout=5000;",
    "PRAGMA foreign_keys=ON;",
)


@contextmanager
def get_connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection with project pragmas applied.

    Connection uses sqlite3's default `isolation_level=""` (deferred transactions)
    so that explicit BEGIN/COMMIT inside callers controls write atomicity.
    `check_same_thread=False` is safe because we hand out one connection per
    call and never share connections across awaits.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        conn.commit()  # PRAGMA writes need to commit to take effect on first connection
        yield conn
    finally:
        conn.close()


def _fetchone_sync(db_path: str, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
    with get_connection(db_path) as conn:
        cur = conn.execute(query, params)
        row: tuple[Any, ...] | None = cur.fetchone()
        return row


def _fetchall_sync(db_path: str, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    with get_connection(db_path) as conn:
        cur = conn.execute(query, params)
        return list(cur.fetchall())


def _execute_write_sync(db_path: str, query: str, params: tuple[Any, ...]) -> int:
    """Run a write inside an explicit BEGIN IMMEDIATE / COMMIT transaction.

    BEGIN IMMEDIATE acquires the write lock up front so concurrent writers
    fail fast (within busy_timeout=5000ms) rather than deadlocking later.
    """
    with get_connection(db_path) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(query, params)
            rowcount = cur.rowcount
            conn.commit()
            return rowcount
        except Exception:
            conn.rollback()
            raise


def _execute_write_returning_sync(
    db_path: str, query: str, params: tuple[Any, ...]
) -> tuple[Any, ...] | None:
    """Run an UPDATE/DELETE/INSERT with a RETURNING clause inside the standard
    BEGIN IMMEDIATE / COMMIT envelope and return the (first) returned row.

    Story 6-15 CR-2: introduced for `OAUTH_STATE_BUMP_REFRESH_FAILURE` which
    needs the post-bump value of `consecutive_refresh_failures` to make a
    race-safe threshold-crossing decision. The previous read-modify-decide
    pattern (snapshot in memory, BUMP, decide from snapshot+1) could
    double-fire or miss-fire when two callers raced.
    """
    with get_connection(db_path) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(query, params)
            row: tuple[Any, ...] | None = cur.fetchone()
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise


def _execute_insert_returning_id_sync(db_path: str, query: str, params: tuple[Any, ...]) -> int:
    """Run an INSERT inside BEGIN IMMEDIATE / COMMIT, returning lastrowid.

    Used by `pending_actions` / `action_grants` INSERTs that need the new
    AUTOINCREMENT id back. Story 4-2 introduced this wrapper because the
    standard `execute_write` returns rowcount, not lastrowid.

    CR-4 (4-2 review): the lastrowid None-check runs BEFORE commit so a
    RuntimeError leaves no orphan row behind. With sqlite3 + INTEGER PRIMARY
    KEY AUTOINCREMENT this branch is defensive (lastrowid is always populated
    after a successful INSERT), but if a future caller passes an UPSERT that
    can no-op on conflict, the defensive check matters and the
    rollback-on-RuntimeError semantics make it correct.
    """
    with get_connection(db_path) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(query, params)
            new_id = cur.lastrowid
            if new_id is None:
                raise RuntimeError("INSERT did not produce a lastrowid")
            conn.commit()
            return new_id
        except Exception:
            conn.rollback()
            raise


async def fetchone(
    db_path: str, query: str, params: tuple[Any, ...] = ()
) -> tuple[Any, ...] | None:
    """Async wrapper around sqlite3 fetchone. Reads run synchronously on the event loop
    (sub-ms in WAL per AR-D8-1); no executor dispatch needed."""
    return _fetchone_sync(db_path, query, params)


async def fetchall(
    db_path: str, query: str, params: tuple[Any, ...] = ()
) -> list[tuple[Any, ...]]:
    """Async wrapper around sqlite3 fetchall. Reads run synchronously on the event loop."""
    return _fetchall_sync(db_path, query, params)


async def execute_write(
    db_path: str, query: str, params: tuple[Any, ...] = ()
) -> int:
    """Async wrapper for sqlite3 write statements (INSERTs/UPDATEs/DELETEs).

    Dispatches through run_in_executor so a slow write/checkpoint never blocks the
    asyncio event loop (per AR-D8-1). Runs inside BEGIN IMMEDIATE / COMMIT.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _execute_write_sync, db_path, query, params)


async def execute_insert_returning_id(
    db_path: str, query: str, params: tuple[Any, ...] = ()
) -> int:
    """Async wrapper for INSERTs that need the new AUTOINCREMENT id back.

    Dispatches through run_in_executor. Same transaction semantics as
    execute_write (BEGIN IMMEDIATE / COMMIT).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _execute_insert_returning_id_sync, db_path, query, params)


async def execute_write_returning(
    db_path: str, query: str, params: tuple[Any, ...] = ()
) -> tuple[Any, ...] | None:
    """Async wrapper for UPDATE/INSERT/DELETE ... RETURNING ... statements.

    Story 6-15 CR-2: introduced for atomic bump-and-read of
    `oauth_state.consecutive_refresh_failures` so threshold-crossing
    decisions read the post-bump DB value, not a stale in-memory snapshot.
    Same transaction semantics as `execute_write` (BEGIN IMMEDIATE / COMMIT).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _execute_write_returning_sync, db_path, query, params)
