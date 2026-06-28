"""Integration tests for migration ``025_benchmark_scores.sql`` (Story 9-7 AC-1).

The migration creates the ``benchmark_scores`` table with the columns,
indexes, and unique constraint specified in the story's AC-1. Tests run
against a real on-disk SQLite (``tmp_path``) with real migrations applied
per the Middleware-Real-Bootstrap MailBot reframing (Story 9-6 precedent).
"""

from __future__ import annotations

from pathlib import Path

from mailbot_api.db.connection import get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations

_MIGRATION_NAME = "025_benchmark_scores.sql"


def test_migration_025_creates_benchmark_scores_table(tmp_path: Path) -> None:
    """AC-1: the benchmark_scores table exists after migrations apply."""
    db_path = str(tmp_path / "test.db")
    applied = apply_pending_migrations(db_path)
    assert _MIGRATION_NAME in applied

    with get_connection(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "benchmark_scores" in tables


def test_migration_025_columns_are_in_expected_order(tmp_path: Path) -> None:
    """AC-1: column ordering matches the story's documented order."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    with get_connection(db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(benchmark_scores)").fetchall()]

    expected = [
        "id",
        "run_id",
        "cohort_key",
        "task_type",
        "model",
        "prompt_version",
        "scorer_model",
        "evaluator_role",
        "metric_name",
        "metric_value",
        "sample_count",
        "outcome",
        "extra_json",
        "computed_at",
    ]
    assert cols == expected


def test_migration_025_creates_three_indexes(tmp_path: Path) -> None:
    """AC-1: indexes on run_id, cohort_key, (task_type, model)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    with get_connection(db_path) as conn:
        idx_names = {
            row[1]
            for row in conn.execute("PRAGMA index_list(benchmark_scores)").fetchall()
        }

    assert "ix_benchmark_scores_run_id" in idx_names
    assert "ix_benchmark_scores_cohort_key" in idx_names
    assert "ix_benchmark_scores_task_model" in idx_names


def test_migration_025_unique_constraint_enforced(tmp_path: Path) -> None:
    """AC-1: UNIQUE constraint on the 7-column key."""
    import sqlite3

    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    common_values = (
        "run-1",
        "cohort-abc",
        "draft_reply",
        "claude-opus-4-7",
        "v1",
        "claude-opus-4-7-20251220",
        "primary",
        "subjective_overall",
        4.2,
        20,
        "ok",
        None,
        "2026-06-28T00:00:00Z",
    )
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO benchmark_scores (run_id, cohort_key, task_type, model, "
            "prompt_version, scorer_model, evaluator_role, metric_name, "
            "metric_value, sample_count, outcome, extra_json, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            common_values,
        )
        conn.commit()
        # Second insert with identical key MUST raise IntegrityError.
        raised = False
        try:
            conn.execute(
                "INSERT INTO benchmark_scores (run_id, cohort_key, task_type, model, "
                "prompt_version, scorer_model, evaluator_role, metric_name, "
                "metric_value, sample_count, outcome, extra_json, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                common_values,
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raised = True
        assert raised, "UNIQUE constraint on the 7-column key must reject duplicate inserts"


def test_migration_025_is_idempotent(tmp_path: Path) -> None:
    """AC-1: re-running migrations is a no-op once 025 is applied."""
    db_path = str(tmp_path / "test.db")
    first = apply_pending_migrations(db_path)
    assert _MIGRATION_NAME in first
    second = apply_pending_migrations(db_path)
    assert second == []
