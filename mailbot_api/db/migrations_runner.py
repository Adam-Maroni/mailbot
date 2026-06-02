"""Migrations runner per architecture AR-D14-1.

- Reads NNN_*.sql files from mailbot_api/db/migrations/ in numeric order.
- Records applied migrations in `_migrations` table.
- Each migration runs inside a single BEGIN / COMMIT transaction wrapping BOTH
  the migration SQL AND the bookkeeping INSERT (per CR-1 + CR-4). Implementation
  uses `executescript` with explicit BEGIN/INSERT/COMMIT appended to the migration
  SQL — executescript correctly handles SQL comment + multi-line statements.
- Duplicate NNN_ prefixes raise a clear error before any migration runs (per CR-6).
- On failure, raises MigrationError so the FastAPI lifespan propagates a clean
  exit code (per CR-3 — sys.exit inside a lifespan is unreliable).

Called once at startup by main.py's FastAPI lifespan handler.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import Counter
from pathlib import Path

from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)

_MIGRATION_FILENAME_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied. Surfaces a clean uvicorn shutdown."""


def _utc_iso8601() -> str:
    """Return the current UTC time as ISO-8601 with Z suffix (AR-PAT-3).

    Microsecond-precision since 2026-06-02 (Epic 4 retro action item #3).
    """
    return utc_z_now()


def _open_connection(db_path: str) -> sqlite3.Connection:
    """Open a fresh sqlite3 connection with project pragmas applied."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_filenames(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("SELECT filename FROM _migrations")
    return {row[0] for row in cur.fetchall()}


def _discover_migrations(migrations_dir: Path) -> list[Path]:
    """Return all NNN_*.sql files in migrations_dir, sorted by numeric prefix.

    Raises MigrationError if two files share the same numeric prefix (per CR-6).
    """
    candidates = []
    for path in migrations_dir.iterdir():
        if not path.is_file():
            continue
        match = _MIGRATION_FILENAME_RE.match(path.name)
        if match is None:
            continue
        candidates.append((int(match.group(1)), path))

    prefix_counts = Counter(prefix for prefix, _ in candidates)
    duplicates = {p: c for p, c in prefix_counts.items() if c > 1}
    if duplicates:
        offending = sorted([path.name for prefix, path in candidates if prefix in duplicates])
        raise MigrationError(
            f"Duplicate migration prefixes detected: {offending}. "
            f"Each NNN_ prefix must be unique."
        )

    candidates.sort(key=lambda x: x[0])
    return [p for _, p in candidates]


def _apply_one_migration_atomically(conn: sqlite3.Connection, migration: Path) -> None:
    """Apply a single migration file atomically.

    Strategy: build a composite SQL script that wraps the migration body in
    `BEGIN; ... INSERT INTO _migrations ...; COMMIT;` and pass it to
    `executescript()`. executescript correctly parses multi-line SQL, comments,
    and statement boundaries (which a naive `.split(";")` does not).

    Atomicity: if any statement in the body raises, the COMMIT is never reached
    and SQLite rolls back the open transaction. The bookkeeping INSERT also lives
    inside the same transaction, so it either lands together with the body or
    not at all (CR-1 + CR-4).
    """
    body = migration.read_text(encoding="utf-8")
    # Embed the filename + applied_at as SQL string literals. Escape single quotes
    # in the filename (defensive; our filename regex disallows them anyway).
    safe_filename = migration.name.replace("'", "''")
    safe_applied_at = _utc_iso8601().replace("'", "''")

    # The bookkeeping INSERT below is built from filename + utc-iso8601 values
    # escaped above. Both inputs are produced internally by this module (filename
    # matches `_MIGRATION_FILENAME_RE`, applied_at is _utc_iso8601()). No
    # user-supplied SQL flows through this string. The S608 noqa annotates the
    # f-string construction site.
    bookkeeping = (
        f"INSERT INTO _migrations (filename, applied_at) "  # noqa: S608
        f"VALUES ('{safe_filename}', '{safe_applied_at}');\n"  # noqa: S608
    )
    composite = (
        "BEGIN;\n"
        + body.rstrip().rstrip(";")
        + ";\n"
        + bookkeeping
        + "COMMIT;\n"
    )

    try:
        # executescript handles multi-statement SQL with comments correctly.
        # On any error in the composite, executescript leaves the transaction
        # open; we ROLLBACK in the except clause to undo whatever ran.
        conn.executescript(composite)
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            # No transaction was active (rare edge case).
            pass
        logger.error(
            'event="db.migration.failed" filename=%r error_type=%s',
            migration.name,
            type(exc).__name__,
        )
        raise MigrationError(f"Migration {migration.name} failed: {type(exc).__name__}") from exc


def apply_pending_migrations(db_path: str, migrations_dir: Path | None = None) -> list[str]:
    """Apply any NNN_*.sql files not yet recorded in `_migrations`. Returns the
    list of filenames that were applied this call (empty if all up-to-date).

    Raises MigrationError on failure — callers (FastAPI lifespan) propagate this
    so uvicorn exits cleanly with code 1 (per CR-3).
    """
    if migrations_dir is None:
        migrations_dir = Path(__file__).parent / "migrations"

    conn = _open_connection(db_path)
    try:
        _ensure_migrations_table(conn)
        applied = _applied_filenames(conn)

        pending = [p for p in _discover_migrations(migrations_dir) if p.name not in applied]
        if not pending:
            return []

        newly_applied: list[str] = []
        for migration in pending:
            _apply_one_migration_atomically(conn, migration)
            newly_applied.append(migration.name)
            logger.info(
                'event="db.migration.applied" filename=%r applied_at=%r',
                migration.name,
                _utc_iso8601(),
            )

        return newly_applied
    finally:
        conn.close()
