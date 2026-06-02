"""Integration tests for migrations 015/016/017 and their CHECK constraints.

Story 4-2 AC-4 + AC-13 + AC-14:
  - Migrations 015/016/017 land and create pending_actions / action_grants /
    action_history with expected columns + indexes.
  - CHECK constraints reject invalid action_type / tier / status / budget_consumed.
  - The hand-written CHECK(action_type IN (...)) list in 015 + 016 stays
    in sync with mailbot_api.actions.types.ActionType Tier-1/2/3 members.

Per the Middleware-Real-Bootstrap MailBot reframing: tests use real on-disk
SQLite via tmp_path, NOT a mocked DB layer.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from mailbot_api.actions.types import ActionType, tier_for
from mailbot_api.db.connection import get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "mailbot_api" / "db" / "migrations"
)


def _apply_and_open(tmp_path: Path) -> str:
    """Apply the full migration chain to a fresh DB; return the db_path."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


def test_migration_015_pending_actions_table_shape(tmp_path: Path) -> None:
    """AC-1: pending_actions has the 12 expected columns with correct nullability."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(pending_actions)").fetchall()}

    expected_cols = {
        "id",
        "email_id",
        "action_type",
        "tier",
        "payload",
        "proposed_at",
        "proposed_by_grant_id",
        "change_marker_at_propose",
        "status",
        "retry_count",
        "failure_reason",
        "terminal_at",
        "budget_consumed",
    }
    assert set(cols.keys()) == expected_cols
    # Nullability spot-checks (notnull column index = 3). Note: SQLite reports
    # notnull=0 for INTEGER PRIMARY KEY AUTOINCREMENT columns even though the
    # PK constraint enforces non-null at insert time. We assert the columns
    # that should be explicitly nullable + the columns we declared NOT NULL.
    assert cols["email_id"][3] == 0  # nullable per AC
    assert cols["action_type"][3] == 1
    assert cols["tier"][3] == 1
    assert cols["status"][3] == 1
    assert cols["proposed_at"][3] == 1
    assert cols["change_marker_at_propose"][3] == 0  # nullable for Tier-1/2 + email-less Tier-3
    assert cols["failure_reason"][3] == 0
    assert cols["terminal_at"][3] == 0
    assert cols["proposed_by_grant_id"][3] == 0
    # PK + AUTOINCREMENT: id reports pk=1 (index 5), and is non-null by PK semantics.
    assert cols["id"][5] == 1


def test_migration_015_creates_three_indexes(tmp_path: Path) -> None:
    """AC-1: ix_pending_actions_status_proposed_at / _email_id / _action_type."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        idx_names = {row[1] for row in conn.execute("PRAGMA index_list(pending_actions)").fetchall()}
    assert "ix_pending_actions_status_proposed_at" in idx_names
    assert "ix_pending_actions_email_id" in idx_names
    assert "ix_pending_actions_action_type" in idx_names


def test_migration_016_action_grants_table_shape(tmp_path: Path) -> None:
    """AC-2: action_grants has the 6 expected columns + the action_type/expires_at index."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(action_grants)").fetchall()}
        idx_names = {row[1] for row in conn.execute("PRAGMA index_list(action_grants)").fetchall()}
    assert cols == {"id", "action_type", "email_ids", "expires_at", "minted_at", "revoked_at"}
    assert "ix_action_grants_action_type_expires_at" in idx_names


def test_migration_017_action_history_table_shape(tmp_path: Path) -> None:
    """AC-3: action_history has action_id PK + pre_state + applied_at + reverted_at."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(action_history)").fetchall()}
    assert set(cols.keys()) == {"action_id", "pre_state", "applied_at", "reverted_at"}
    assert cols["action_id"][5] == 1  # pk flag (index 5) — action_id is PRIMARY KEY


def test_migrations_idempotent_on_already_migrated_db(tmp_path: Path) -> None:
    """AC-4: re-running the migration runner on an already-applied DB is a no-op."""
    db_path = _apply_and_open(tmp_path)
    second = apply_pending_migrations(db_path)
    assert second == []


def test_invalid_action_type_rejected_by_check_constraint(tmp_path: Path) -> None:
    """AC-4: CHECK(action_type IN (...)) rejects unknown action_type values."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_actions (action_type, tier, payload, proposed_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                ("not_a_real_action", 1, "{}", "2026-06-02T00:00:00Z", "pending"),
            )


def test_invalid_tier_value_rejected_by_check_constraint(tmp_path: Path) -> None:
    """AC-4: tier=0 (or any other-than-1/2/3) rejected — second-layer FR-5.6 defense."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_actions (action_type, tier, payload, proposed_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                ("delete", 0, "{}", "2026-06-02T00:00:00Z", "pending"),
            )


def test_invalid_status_rejected_by_check_constraint(tmp_path: Path) -> None:
    """AC-4: status outside the 7-state set rejected."""
    db_path = _apply_and_open(tmp_path)
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_actions (action_type, tier, payload, proposed_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                ("delete", 3, "{}", "2026-06-02T00:00:00Z", "weird_status"),
            )


def _parse_check_constraint_action_types(migration_file: Path) -> set[str]:
    """Extract the action_type list from a CHECK(action_type IN ('a', 'b', ...)) block.

    Strips comment lines (those starting with `--`) before matching so the
    header-comment's `CHECK(action_type IN (...))` placeholder text doesn't
    fool the regex into matching the wrong block.
    """
    raw = migration_file.read_text(encoding="utf-8")
    # Drop comment lines entirely.
    code = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("--")
    )
    match = re.search(
        r"CHECK\(action_type IN \(([^)]+)\)\)",
        code,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"No CHECK(action_type IN (...)) found in {migration_file.name}")
    quoted = re.findall(r"'([^']+)'", match.group(1))
    return set(quoted)


def test_check_constraint_in_sync_with_enum_for_015() -> None:
    """AC-14: 015's CHECK(action_type IN (...)) equals Tier-1/2/3 ActionType values."""
    parsed = _parse_check_constraint_action_types(_MIGRATIONS_DIR / "015_pending_actions.sql")
    expected = {at.value for at in ActionType if tier_for(at) >= 1}
    assert parsed == expected, (
        f"Drift in 015_pending_actions.sql CHECK(action_type IN (...)) vs "
        f"ActionType Tier-1/2/3 enum. In-migration-only={parsed - expected}, "
        f"In-enum-only={expected - parsed}"
    )


def test_check_constraint_in_sync_with_enum_for_016() -> None:
    """AC-14: 016's CHECK(action_type IN (...)) equals Tier-1/2/3 ActionType values."""
    parsed = _parse_check_constraint_action_types(_MIGRATIONS_DIR / "016_action_grants.sql")
    expected = {at.value for at in ActionType if tier_for(at) >= 1}
    assert parsed == expected, (
        f"Drift in 016_action_grants.sql CHECK(action_type IN (...)) vs "
        f"ActionType Tier-1/2/3 enum. In-migration-only={parsed - expected}, "
        f"In-enum-only={expected - parsed}"
    )
