"""Story 6-3 integration: four-tier dispatcher + outbox pull/ack + recovery.

Coverage:

1. send_urgent / send_important enqueue rows in notifications_outbox with
   correct tier values.
2. send_informational / send_silent never write to DB.
3. pull_pending_notifications returns up to limit urgent rows, atomically
   claiming each (delivery_status: pending → delivering, attempt_count
   bumped).
4. pull_pending_notifications respects FIFO ordering and never returns
   `important`-tier rows.
5. ack_notification(ok) finalizes a delivering row to ok + delivered_at set.
6. ack_notification(failed) under cap returns row to pending + last_error
   set + attempt_count preserved at the bumped value.
7. ack_notification(failed) at-or-past the 5-attempt cap flips to terminal
   failed_max_retries.
8. recovery sweep reclaims rows stuck in delivering for > 60s.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import (
    NOTIFICATIONS_OUTBOX_COUNT_ALL,
    NOTIFICATIONS_OUTBOX_FETCH_BY_ID,
)
from mailbot_api.notifications.outbox_recovery import reclaim_stuck_deliveries
from mailbot_api.notifications.tiers import (
    send_important,
    send_informational,
    send_silent,
    send_urgent,
)
from mailbot_api.verbs.ack_notification import ack_notification
from mailbot_api.verbs.pull_pending_notifications import (
    pull_pending_notifications,
)


@pytest.fixture
async def _db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "notify.db")
    apply_pending_migrations(db_path)
    return db_path


# ---- send_<tier> behavior ----------------------------------------------------


async def test_send_urgent_enqueues_with_correct_tier(_db: str) -> None:
    await send_urgent("urgent test", "health", db_path=_db)
    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (1,))
    assert row is not None
    assert row[1] == "urgent"
    assert row[2] == "health"
    assert row[3] == "urgent test"
    assert row[5] == "pending"
    assert row[6] == 0


async def test_send_important_enqueues_distinct_tier(_db: str) -> None:
    await send_important("important test", "digest", db_path=_db)
    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (1,))
    assert row is not None
    assert row[1] == "important"
    assert row[2] == "digest"


async def test_send_informational_no_db_no_discord(_db: str, caplog) -> None:
    """Story 6-4: send_informational is now async + accepts optional db_path
    for the gating layers. Calling with db_path=None skips gates entirely
    (legacy path) — still log-only, still no DB write."""
    import logging

    caplog.set_level(logging.INFO)
    await send_informational("info test", "ambient")

    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 0
    assert any(
        r.message == "notification informational" for r in caplog.records
    )


async def test_send_silent_log_only(_db: str, caplog) -> None:
    import logging

    caplog.set_level(logging.INFO)
    send_silent("silent test", "ambient")

    count = await fetchone(_db, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count is not None and count[0] == 0
    assert any(r.message == "notification silent" for r in caplog.records)


# ---- pull_pending_notifications behavior -----------------------------------


async def test_pull_returns_oldest_first(_db: str) -> None:
    """FIFO ordering — earliest enqueued_at returned first."""
    await send_urgent("first", "a", db_path=_db)
    await asyncio.sleep(0.01)
    await send_urgent("second", "a", db_path=_db)
    await asyncio.sleep(0.01)
    await send_urgent("third", "a", db_path=_db)

    out = await pull_pending_notifications(limit=10, db_path=_db)
    assert out.count == 3
    assert out.notifications[0].message == "first"
    assert out.notifications[1].message == "second"
    assert out.notifications[2].message == "third"


async def test_pull_respects_limit(_db: str) -> None:
    for i in range(5):
        await send_urgent(f"msg-{i}", "test", db_path=_db)

    out = await pull_pending_notifications(limit=2, db_path=_db)
    assert out.count == 2


async def test_pull_atomically_claims(_db: str) -> None:
    """A second pull must NOT re-return rows the first pull already claimed."""
    for i in range(3):
        await send_urgent(f"msg-{i}", "test", db_path=_db)

    out1 = await pull_pending_notifications(limit=10, db_path=_db)
    out2 = await pull_pending_notifications(limit=10, db_path=_db)

    assert out1.count == 3
    assert out2.count == 0  # all already claimed


async def test_pull_skips_already_delivering(_db: str) -> None:
    """Manually flip a row to `delivering` — pull should not return it."""
    await send_urgent("urgent", "test", db_path=_db)
    await execute_write(
        _db,
        "UPDATE notifications_outbox SET delivery_status='delivering' WHERE id=?",
        (1,),
    )

    out = await pull_pending_notifications(limit=10, db_path=_db)
    assert out.count == 0


async def test_pull_excludes_important_tier(_db: str) -> None:
    """Important-tier rows belong to Story 6-5's digest, NOT this story's pull."""
    await send_urgent("urgent msg", "u", db_path=_db)
    await send_important("important msg", "i", db_path=_db)

    out = await pull_pending_notifications(limit=10, db_path=_db)
    assert out.count == 1
    assert out.notifications[0].tier == "urgent"


async def test_pull_bumps_attempt_count(_db: str) -> None:
    await send_urgent("u", "test", db_path=_db)
    out = await pull_pending_notifications(limit=10, db_path=_db)
    assert out.notifications[0].attempt_count == 1


async def test_pull_caps_limit_at_25(_db: str) -> None:
    """Caller asking for 100 gets clamped to 25 (Discord rate-limit defense).

    Story 6-4 dedup would collapse same-category sends after 5 in an hour,
    so use distinct categories to keep 30 rows distinct.
    """
    for i in range(30):
        await send_urgent(f"msg-{i}", f"test-{i}", db_path=_db)

    out = await pull_pending_notifications(limit=100, db_path=_db)
    assert out.count == 25


# ---- ack_notification behavior ---------------------------------------------


async def test_ack_ok_finalizes_row(_db: str) -> None:
    await send_urgent("u", "test", db_path=_db)
    out_pull = await pull_pending_notifications(limit=1, db_path=_db)
    nid = out_pull.notifications[0].id

    ack = await ack_notification(nid, "ok", db_path=_db)
    assert ack.ok is True
    assert ack.final_status == "ok"

    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (nid,))
    assert row is not None
    assert row[5] == "ok"  # delivery_status
    assert row[9] is not None  # delivered_at populated


async def test_ack_failed_under_cap_returns_pending(_db: str) -> None:
    await send_urgent("u", "test", db_path=_db)
    out_pull = await pull_pending_notifications(limit=1, db_path=_db)
    nid = out_pull.notifications[0].id

    ack = await ack_notification(nid, "failed", "discord 500", db_path=_db)
    assert ack.ok is True
    assert ack.final_status == "pending"

    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (nid,))
    assert row is not None
    assert row[5] == "pending"
    assert row[8] == "discord 500"  # last_error


async def test_ack_failed_at_cap_flips_terminal(_db: str) -> None:
    await send_urgent("u", "test", db_path=_db)
    # Manually set attempt_count to 5 (already at cap).
    await execute_write(
        _db,
        "UPDATE notifications_outbox SET attempt_count=5, delivery_status='delivering' "
        "WHERE id=?",
        (1,),
    )

    ack = await ack_notification(1, "failed", "5th failure", db_path=_db)
    assert ack.ok is True
    assert ack.final_status == "failed_max_retries"

    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (1,))
    assert row is not None
    assert row[5] == "failed_max_retries"
    assert row[8] == "5th failure"


# ---- recovery behavior -----------------------------------------------------


async def test_recovery_reclaims_stuck_delivering(_db: str) -> None:
    """A row stuck in 'delivering' for > 60s gets flipped back to 'pending'."""
    await send_urgent("u", "test", db_path=_db)
    stuck_iso = (datetime.now(timezone.utc) - timedelta(seconds=90)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    await execute_write(
        _db,
        "UPDATE notifications_outbox SET delivery_status='delivering', "
        "last_attempt_at=? WHERE id=?",
        (stuck_iso, 1),
    )

    reclaimed = await reclaim_stuck_deliveries(_db)
    assert reclaimed == 1

    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (1,))
    assert row is not None
    assert row[5] == "pending"


async def test_recovery_leaves_recently_delivering_alone(_db: str) -> None:
    """A row stuck only 5s should NOT be reclaimed."""
    await send_urgent("u", "test", db_path=_db)
    recent_iso = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    await execute_write(
        _db,
        "UPDATE notifications_outbox SET delivery_status='delivering', "
        "last_attempt_at=? WHERE id=?",
        (recent_iso, 1),
    )

    reclaimed = await reclaim_stuck_deliveries(_db)
    assert reclaimed == 0

    row = await fetchone(_db, NOTIFICATIONS_OUTBOX_FETCH_BY_ID, (1,))
    assert row is not None
    assert row[5] == "delivering"  # unchanged


# ---- CR HIGH-1 lesson carried forward — JSON serialization round-trip ------


async def test_pull_result_serializes_to_json_without_crash(_db: str) -> None:
    """Story 6-8 CR HIGH-1: ensure FastMCP transport-boundary serialization
    (model_dump_json) works for the new Pydantic shape — no PNG-bytes-like
    pitfall."""
    import json

    await send_urgent("u", "test", db_path=_db)
    out = await pull_pending_notifications(limit=1, db_path=_db)

    payload = out.model_dump_json()
    decoded = json.loads(payload)
    assert decoded["count"] == 1
    assert decoded["notifications"][0]["message"] == "u"
    assert decoded["notifications"][0]["tier"] == "urgent"
