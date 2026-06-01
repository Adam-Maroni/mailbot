"""Integration tests for migration `011_derived_fields.sql` + EMAIL_DERIVED_FIELDS_SELECT.

Story 3-1 AC-1, AC-2, AC-6:
  - The migration adds embedding_dtype and embedding_shape columns to emails.
  - Three new indexes are created: ix_emails_importance_score,
    ix_emails_sensitivity_at, ix_emails_class_fine.
  - The EMAIL_DERIVED_FIELDS_SELECT query selects all derived-field columns
    plus the new W-5 companions cleanly.

Per the Middleware-Real-Bootstrap MailBot reframing: tests run against a real
on-disk SQLite (tmp_path) with real migrations applied — NEVER a mocked DB.
"""

from __future__ import annotations

from pathlib import Path

from mailbot_api.db.connection import execute_write, fetchone, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import EMAIL_DERIVED_FIELDS_SELECT


def test_migration_011_adds_embedding_dtype_and_shape_columns(tmp_path: Path) -> None:
    """AC-1: embedding_dtype and embedding_shape columns are present on emails."""
    db_path = str(tmp_path / "test.db")
    applied = apply_pending_migrations(db_path)

    # All 11 migrations should land on a fresh DB.
    assert "011_derived_fields.sql" in applied

    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)").fetchall()}

    assert "embedding_dtype" in cols, "Migration 011 must add embedding_dtype (W-5 companion column)"
    assert "embedding_shape" in cols, "Migration 011 must add embedding_shape (W-5 companion column)"


def test_migration_011_creates_three_new_indexes(tmp_path: Path) -> None:
    """AC-1: ix_emails_importance_score, ix_emails_sensitivity_at, ix_emails_class_fine."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    with get_connection(db_path) as conn:
        idx_names = {row[1] for row in conn.execute("PRAGMA index_list(emails)").fetchall()}

    assert "ix_emails_importance_score" in idx_names
    assert "ix_emails_sensitivity_at" in idx_names
    assert "ix_emails_class_fine" in idx_names


def test_migration_011_is_recorded_in_migrations_table(tmp_path: Path) -> None:
    """AC-2: _migrations table records 011 with an applied_at timestamp."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT filename, applied_at FROM _migrations WHERE filename = ?",
            ("011_derived_fields.sql",),
        ).fetchone()

    assert row is not None
    assert row[0] == "011_derived_fields.sql"
    assert row[1]  # applied_at is a non-empty ISO-8601 string


def test_migration_011_is_idempotent_on_already_migrated_db(tmp_path: Path) -> None:
    """AC-2: running the lifespan again on an already-migrated DB skips 011.

    Second call returns empty list — no re-application.
    """
    db_path = str(tmp_path / "test.db")
    first = apply_pending_migrations(db_path)
    assert "011_derived_fields.sql" in first

    second = apply_pending_migrations(db_path)
    assert second == []  # nothing pending the second time


def test_migration_011_applies_cleanly_when_db_is_at_010(tmp_path: Path) -> None:
    """AC-2 explicit: seed a DB through migration 010, then run the lifespan,
    and assert ONLY 011 is applied this call (not all 11 re-run).

    Per the reviewer (CR-3): the other AC-2 tests start from a fresh DB and
    apply all migrations at once. This test exercises the "DB already at 010,
    apply 011 in isolation" path explicitly — the realistic deployment scenario
    when this story ships to a running stack.
    """
    db_path = str(tmp_path / "test.db")

    # Stage 1: apply migrations up through 010 by temporarily hiding 011.
    real_migrations_dir = Path(__file__).resolve().parent.parent.parent / "mailbot_api" / "db" / "migrations"
    staging_dir = tmp_path / "migrations_through_010"
    staging_dir.mkdir()
    for sql_path in sorted(real_migrations_dir.glob("*.sql")):
        # Only copy migrations 001..010 — leave 011 out for stage 2.
        prefix = sql_path.name[:3]
        if prefix.isdigit() and int(prefix) <= 10:
            (staging_dir / sql_path.name).write_text(sql_path.read_text(encoding="utf-8"), encoding="utf-8")

    applied_stage_1 = apply_pending_migrations(db_path, staging_dir)
    assert "011_derived_fields.sql" not in applied_stage_1
    # Sanity: every migration from 001 through 010 should have applied.
    # 003 was skipped historically; 010 is the highest pre-Story-3-1 prefix.
    applied_joined = " ".join(applied_stage_1)
    for i in (1, 2, 4, 5, 6, 7, 8, 9, 10):
        assert f"{i:03d}_" in applied_joined, f"Migration {i:03d}_ missing from stage 1"

    # Stage 2: now point at the real migrations dir (with 011 + any later
    # migrations present) and run. Story 3-3 added migration 012, so stage 2
    # may apply more than just 011 — we verify that 011 IS in the applied list
    # AND nothing older (≤ 010) ran (the bookkeeping table guarded those).
    applied_stage_2 = apply_pending_migrations(db_path, real_migrations_dir)
    assert "011_derived_fields.sql" in applied_stage_2, (
        f"Expected 011 to apply in stage 2, got {applied_stage_2}"
    )
    # Nothing ≤ 010 should re-apply (already in the _migrations bookkeeping).
    older = [m for m in applied_stage_2 if m.split("_")[0].isdigit() and int(m.split("_")[0]) <= 10]
    assert older == [], f"Unexpected re-application of pre-010 migrations: {older}"

    # Verify the columns landed.
    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)").fetchall()}
    assert "embedding_dtype" in cols
    assert "embedding_shape" in cols


async def test_email_derived_fields_select_returns_all_columns(tmp_path: Path) -> None:
    """AC-6: EMAIL_DERIVED_FIELDS_SELECT executes cleanly and returns 37 columns
    for one row keyed by graph_id (all NULL before derivation runs)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    # Seed one minimal email row directly via the migration's column set.
    # AR-PAT-2 plural snake_case + AR-PAT-3 ISO-8601 Z timestamps.
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at) VALUES (?, ?)",
        ("seed-graph-id-3-1-test", "2026-06-01T00:00:00Z"),
    )

    row = await fetchone(db_path, EMAIL_DERIVED_FIELDS_SELECT, ("seed-graph-id-3-1-test",))
    assert row is not None
    # 7 derived fields × 5 companions + 2 W-5 extras = 37 columns
    # (sensitivity, class_coarse, class_fine, summary_short, importance_score,
    # action_extraction, embedding) × (value, prompt_v, conf, model, at)
    # + embedding_dtype + embedding_shape.
    assert len(row) == 37

    # All values should be NULL on a freshly-seeded row (nothing derived yet).
    assert all(value is None for value in row), f"Expected all derived fields to be NULL pre-derivation, got: {row}"
