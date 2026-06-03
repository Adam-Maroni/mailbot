"""Story 6-4 integration: anti-fatigue gating + posture + unmute round-trip.

Coverage:

- quiet-hours boundary semantics (22:00 / 08:00 / mid-day)
- mute suppression for urgent / important / informational (urgent honors mute)
- dedup collapse at the 5-in-1h threshold; <5 still inserts new rows
- urgent-only posture: drops important + informational; urgent always delivers
- /resume lifts the urgent-only posture
- unmute_category clears a mute idempotently
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import (
    NOTIFICATION_MUTES_UPSERT,
    NOTIFICATIONS_OUTBOX_COUNT_ALL,
)
from mailbot_api.notifications import fatigue, posture
from mailbot_api.notifications.tiers import (
    send_important,
    send_urgent,
)
from mailbot_api.verbs.router_control import resume_router
from mailbot_api.verbs.unmute_category import unmute_category


@pytest.fixture
async def _db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "fatigue.db")
    apply_pending_migrations(db_path)
    return db_path


# ---- quiet hours -----------------------------------------------------------


def test_is_quiet_hours_at_23_utc_is_true() -> None:
    when = datetime(2026, 6, 3, 23, 0, tzinfo=timezone.utc)
    assert fatigue.is_quiet_hours(when) is True


def test_is_quiet_hours_at_07_utc_is_true() -> None:
    when = datetime(2026, 6, 3, 7, 0, tzinfo=timezone.utc)
    assert fatigue.is_quiet_hours(when) is True


def test_is_quiet_hours_at_12_utc_is_false() -> None:
    when = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    assert fatigue.is_quiet_hours(when) is False


def test_is_quiet_hours_boundary_22_utc_is_true() -> None:
    when = datetime(2026, 6, 3, 22, 0, tzinfo=timezone.utc)
    assert fatigue.is_quiet_hours(when) is True


def test_is_quiet_hours_boundary_08_utc_is_false() -> None:
    # 08:00 is the END boundary — 08:00 itself is NOT quiet hours
    # (window is [22, 08), not [22, 08]).
    when = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
    assert fatigue.is_quiet_hours(when) is False


# ---- mute ------------------------------------------------------------------


async def test_mute_blocks_urgent(_db: str) -> None:
    """Even urgent honors mute. Adam asked for the category to be quiet."""
    await execute_write(
        _db,
        NOTIFICATION_MUTES_UPSERT,
        ("noisy", None, "2026-06-03T00:00:00Z"),  # indefinite mute
    )
    await send_urgent("urgent message", "noisy", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 0


async def test_mute_blocks_important(_db: str) -> None:
    await execute_write(
        _db,
        NOTIFICATION_MUTES_UPSERT,
        ("noisy", None, "2026-06-03T00:00:00Z"),
    )
    await send_important("important message", "noisy", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 0


async def test_mute_does_not_block_other_categories(_db: str) -> None:
    await execute_write(
        _db,
        NOTIFICATION_MUTES_UPSERT,
        ("noisy", None, "2026-06-03T00:00:00Z"),
    )
    await send_urgent("urgent message", "different", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 1


# ---- dedup -----------------------------------------------------------------


async def test_dedup_collapses_when_5_existing_in_1h(_db: str) -> None:
    """AC-2: '≥ 5 in an hour' triggers collapse. The dispatcher reads BEFORE
    the new INSERT, so the 6th call (when 5 already exist) is the one that
    collapses onto the latest row instead of inserting."""
    for i in range(5):
        await send_urgent(f"msg-{i}", "spam", db_path=_db)
    # 5 rows so far; the 6th call hits the >=5 threshold and collapses.
    await send_urgent("msg-6-latest", "spam", db_path=_db)

    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    # Still 5 rows — the 6th was collapsed onto row 5.
    assert count is not None and count[0] == 5

    # The 5th row's message was rewritten to the summary form.
    from mailbot_api.db.connection import fetchall
    rows = await fetchall(
        _db,
        "SELECT message FROM notifications_outbox ORDER BY id ASC",
        (),
    )
    assert "5 spam alerts in the last hour" in rows[-1][0]
    assert "msg-6-latest" in rows[-1][0]


async def test_dedup_under_threshold_inserts_new_row(_db: str) -> None:
    for i in range(3):
        await send_urgent(f"msg-{i}", "spam", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 3


# ---- urgent-only posture --------------------------------------------------


async def test_posture_urgent_only_drops_important(_db: str) -> None:
    await posture.set_urgent_only("manual self-reflection", db_path=_db)
    await send_important("important msg", "test", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 0


async def test_posture_urgent_only_lets_urgent_through(_db: str) -> None:
    await posture.set_urgent_only("manual self-reflection", db_path=_db)
    await send_urgent("urgent msg", "test", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 1


async def test_posture_get_set_lift_roundtrip(_db: str) -> None:
    assert await posture.is_urgent_only_active(_db) is False
    await posture.set_urgent_only("noisy episode", db_path=_db)
    assert await posture.is_urgent_only_active(_db) is True
    p = await posture.get_posture(_db)
    assert p.urgent_only is True
    assert p.reason == "noisy episode"
    lifted = await posture.lift_urgent_only(db_path=_db)
    assert lifted is True
    assert await posture.is_urgent_only_active(_db) is False
    # idempotent: a second lift returns False (no posture was active)
    assert await posture.lift_urgent_only(db_path=_db) is False


# ---- /resume lifts posture -------------------------------------------------


async def test_resume_lifts_urgent_only_posture(_db: str) -> None:
    await posture.set_urgent_only("manual test", db_path=_db)
    out = await resume_router(db_path=_db)
    assert out.ok is True
    assert out.posture_lifted is True
    assert "lifted urgent-only posture" in out.message
    assert await posture.is_urgent_only_active(_db) is False


async def test_resume_when_no_posture_active_does_not_claim_lift(_db: str) -> None:
    out = await resume_router(db_path=_db)
    assert out.ok is True
    assert out.posture_lifted is False
    assert "urgent-only" not in out.message


# ---- unmute verb -----------------------------------------------------------


async def test_unmute_clears_a_mute(_db: str) -> None:
    await execute_write(
        _db,
        NOTIFICATION_MUTES_UPSERT,
        ("noisy", None, "2026-06-03T00:00:00Z"),
    )
    out = await unmute_category("noisy", db_path=_db)
    assert out.ok is True
    assert out.was_muted is True

    # Now sending urgent on that category succeeds.
    await send_urgent("urgent msg", "noisy", db_path=_db)
    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 1


async def test_unmute_idempotent_when_not_muted(_db: str) -> None:
    out = await unmute_category("never_muted", db_path=_db)
    assert out.ok is True
    assert out.was_muted is False


# ---- CR MED-4 — Story 6-5 forward-compat regression ------------------------


async def test_important_during_quiet_hours_still_enqueues(_db: str) -> None:
    """CR MED-4: important-tier sends during quiet hours STILL enqueue (the
    row sits in the outbox with tier='important' waiting for Story 6-5's
    08:00 digest sweeper). This guard prevents a future refactor from
    accidentally dropping important rows during quiet hours and breaking
    Story 6-5's digest assembly."""
    from unittest.mock import patch

    # Force the quiet-hours gate to return True regardless of actual clock.
    with patch(
        "mailbot_api.notifications.tiers.fatigue.is_quiet_hours",
        return_value=True,
    ):
        await send_important("held msg", "test", db_path=_db)

    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 1


# ---- CR HIGH-1 — collapse target races out of `pending` --------------------


async def test_dedup_collapse_misses_falls_through_to_insert(_db: str) -> None:
    """CR HIGH-1 regression guard: if the dedup count picks a row that's
    already been delivered (delivery_status != 'pending'), the UPDATE
    rowcount = 0 and the dispatcher must fall through to INSERT instead
    of silently dropping the notification.

    The CR HIGH-1 fix is two-part: (a) the count query now filters on
    delivery_status='pending' (so post-ack rows don't bias the threshold),
    and (b) the dispatcher has a defensive rowcount-check fallback.
    """
    # Seed 5 already-delivered rows (the count-query filter eliminates them).
    from mailbot_api.db.connection import execute_write

    for i in range(5):
        await send_urgent(f"old-{i}", "alarm", db_path=_db)
    # Manually flip all 5 to 'ok' to simulate post-delivery state.
    await execute_write(
        _db,
        "UPDATE notifications_outbox SET delivery_status='ok' WHERE tier='urgent' AND category='alarm'",
        (),
    )

    # A 6th send should INSERT (not collapse) because the 5 'ok' rows
    # don't count toward the dedup threshold post-CR-HIGH-1.
    await send_urgent("new-alarm", "alarm", db_path=_db)

    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 6  # 5 ok + 1 new pending

    from mailbot_api.db.connection import fetchone as _f
    new_row = await _f(
        _db,
        "SELECT message, delivery_status FROM notifications_outbox "
        "WHERE delivery_status='pending' AND category='alarm'",
        (),
    )
    assert new_row is not None
    assert new_row[0] == "new-alarm"
