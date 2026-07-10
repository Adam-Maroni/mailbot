"""Story 10.5.4 Task 2 (AC-2, F5/F6): operator move-family resurrection primitive.

A move soft-deletes the local row (F5) and EMAIL_UPSERT never resurrects it (F6).
The 10-2 revert path clears the soft-delete only inside the 24h window; rows
outside it (the retained 10-1 walk subject, retro B5) had no recovery path.
`resurrect_email` is a local-DB-only repair that clears the soft-delete without a
Graph write.
"""

from __future__ import annotations

from pathlib import Path

from mailbot_api.actions.resurrect import resurrect_email
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations


async def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    deleted_at: str | None = None,
    removed_reason: str | None = None,
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "deleted_at, removed_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-07-05T00:00:00Z", "s", "x@y.com", "body", deleted_at, removed_reason),
    )


async def _seed_move_action(db_path: str, *, email_id: str) -> None:
    """Seed a move-family pending_actions row — the CR-10-5-4-1 corroboration
    the default resurrect path now requires (structural evidence a MOVE, not a
    permanent delete, caused the soft-delete)."""
    await execute_write(
        db_path,
        "INSERT INTO pending_actions (email_id, action_type, tier, payload, "
        "proposed_at, status) VALUES (?, ?, ?, ?, ?, ?)",
        (email_id, "move_to_triage_folder", 1, "{}", "2026-07-05T11:00:00Z", "applied"),
    )


async def test_resurrect_move_soft_deleted_row_clears_soft_delete(tmp_path: Path) -> None:
    """AC-2: a move-family soft-deleted row (removed_reason='deleted') with a
    corroborating move action is restored."""
    db_path = await _setup(tmp_path)
    await _seed_email(
        db_path, graph_id="walk-subj",
        deleted_at="2026-07-05T12:00:00Z", removed_reason="deleted",
    )
    await _seed_move_action(db_path, email_id="walk-subj")

    result = await resurrect_email("walk-subj", db_path=db_path)

    assert result.ok is True
    assert result.graph_id == "walk-subj"
    row = await fetchone(
        db_path,
        "SELECT deleted_at, removed_reason FROM emails WHERE graph_id = ?",
        ("walk-subj",),
    )
    assert row == (None, None)


async def test_resurrect_refuses_unknown_email(tmp_path: Path) -> None:
    db_path = await _setup(tmp_path)
    result = await resurrect_email("nope", db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "EMAIL_NOT_FOUND"


async def test_resurrect_reports_already_live_row(tmp_path: Path) -> None:
    """A live row (deleted_at IS NULL) is not a silent success — already_live flagged."""
    db_path = await _setup(tmp_path)
    await _seed_email(db_path, graph_id="live-1")  # deleted_at NULL

    result = await resurrect_email("live-1", db_path=db_path)

    assert result.ok is False
    assert result.already_live is True
    assert result.error is not None
    assert result.error.code == "NOT_SOFT_DELETED"


async def test_resurrect_refuses_non_move_delete_reason_by_default(tmp_path: Path) -> None:
    """A 'changed' removal is not a move-delete; default guard refuses it."""
    db_path = await _setup(tmp_path)
    await _seed_email(
        db_path, graph_id="chg-1",
        deleted_at="2026-07-05T12:00:00Z", removed_reason="changed",
    )

    result = await resurrect_email("chg-1", db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "REASON_NOT_MOVE_DELETE"


async def test_resurrect_allow_any_reason_widens_guard(tmp_path: Path) -> None:
    db_path = await _setup(tmp_path)
    await _seed_email(
        db_path, graph_id="chg-2",
        deleted_at="2026-07-05T12:00:00Z", removed_reason="changed",
    )

    result = await resurrect_email("chg-2", db_path=db_path, allow_any_reason=True)

    assert result.ok is True
    row = await fetchone(
        db_path,
        "SELECT deleted_at, removed_reason FROM emails WHERE graph_id = ?",
        ("chg-2",),
    )
    assert row == (None, None)


async def test_resurrect_refuses_deleted_reason_without_move_action(tmp_path: Path) -> None:
    """CR-10-5-4-1: a 'deleted' soft-delete with NO move-family action on record
    (i.e. a possible permanent Graph delete) is refused on the default path."""
    db_path = await _setup(tmp_path)
    await _seed_email(
        db_path, graph_id="perm-del",
        deleted_at="2026-07-05T12:00:00Z", removed_reason="deleted",
    )
    # No move action seeded → no corroboration.

    result = await resurrect_email("perm-del", db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NO_MOVE_FAMILY_ACTION"

    # --force bypasses the corroboration requirement.
    forced = await resurrect_email("perm-del", db_path=db_path, allow_any_reason=True)
    assert forced.ok is True


async def test_cmd_resurrect_cli_exit_codes(tmp_path: Path) -> None:
    """The `mailbot resurrect` CLI maps success→0 and refusal→2."""
    from scripts import mailbot as cli

    db_path = await _setup(tmp_path)
    await _seed_email(
        db_path, graph_id="cli-subj",
        deleted_at="2026-07-05T12:00:00Z", removed_reason="deleted",
    )
    await _seed_move_action(db_path, email_id="cli-subj")

    ok = await cli._cmd_resurrect(graph_id="cli-subj", force=False, db_path_arg=db_path)
    assert ok == 0

    # Second run: already live → refusal exit 2.
    again = await cli._cmd_resurrect(graph_id="cli-subj", force=False, db_path_arg=db_path)
    assert again == 2

    # Unknown id → refusal exit 2.
    missing = await cli._cmd_resurrect(graph_id="nope", force=False, db_path_arg=db_path)
    assert missing == 2
