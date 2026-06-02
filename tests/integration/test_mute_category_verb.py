"""Story 5-6 AC-9 — DB-real integration tests for mute_category verb.

Tests run against an on-disk SQLite with the real migration chain applied
(per Step 2.4.7 MailBot-reframing — DB-real integration boundary).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.mute_category import MuteCategoryOut, mute_category


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    db = tmp_path / "mute.db"
    apply_pending_migrations(str(db))
    return str(db)


@pytest.mark.asyncio
async def test_mute_category_inserts_row(db_path: str) -> None:
    """AC-9: bounded mute persists a row with the supplied muted_until."""
    out = await mute_category(
        "newsletters",
        db_path=db_path,
        muted_until="2026-06-09T00:00:00Z",
    )
    assert isinstance(out, MuteCategoryOut)
    assert out.ok is True
    assert out.category == "newsletters"
    assert out.muted_until == "2026-06-09T00:00:00Z"
    assert out.previously_muted is False
    assert "muted until 2026-06-09T00:00:00Z" in out.message

    row = await fetchone(
        db_path,
        "SELECT category, muted_until, muted_at FROM notification_mutes WHERE category = ?",
        ("newsletters",),
    )
    assert row is not None
    assert row[0] == "newsletters"
    assert row[1] == "2026-06-09T00:00:00Z"
    assert row[2].endswith("Z")  # UTC ISO-8601 Z


@pytest.mark.asyncio
async def test_mute_category_indefinite_uses_null(db_path: str) -> None:
    """AC-9: muted_until=None persists as NULL (indefinite mute)."""
    out = await mute_category("transactional", db_path=db_path)
    assert out.ok is True
    assert out.muted_until is None
    assert "muted indefinitely" in out.message

    row = await fetchone(
        db_path,
        "SELECT muted_until FROM notification_mutes WHERE category = ?",
        ("transactional",),
    )
    assert row is not None
    assert row[0] is None


@pytest.mark.asyncio
async def test_mute_category_upsert_overwrites_existing(db_path: str) -> None:
    """AC-9: a second /mute on the same category sets previously_muted=True
    AND overwrites the row's muted_until with the second call's value."""
    await mute_category("low_importance", db_path=db_path, muted_until="2026-06-09T00:00:00Z")

    out2 = await mute_category(
        "low_importance",
        db_path=db_path,
        muted_until="2026-07-09T00:00:00Z",
    )
    assert out2.ok is True
    assert out2.previously_muted is True
    assert out2.muted_until == "2026-07-09T00:00:00Z"

    rows = await fetchall(
        db_path,
        "SELECT category, muted_until FROM notification_mutes WHERE category = ?",
        ("low_importance",),
    )
    assert len(rows) == 1
    assert rows[0][1] == "2026-07-09T00:00:00Z"


@pytest.mark.asyncio
async def test_mute_category_upsert_can_change_indefinite_to_bounded(db_path: str) -> None:
    """Edge case: an indefinite mute can be upgraded to a bounded mute."""
    await mute_category("digest", db_path=db_path)  # indefinite
    out2 = await mute_category(
        "digest",
        db_path=db_path,
        muted_until="2026-06-09T00:00:00Z",
    )
    assert out2.previously_muted is True
    assert out2.muted_until == "2026-06-09T00:00:00Z"
