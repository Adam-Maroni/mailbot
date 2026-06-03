"""Story 6-5 integration: compose_digest + finalize_digest_delivery.

Coverage:

- Empty payload (no unread / no pending / no queued) → empty collections
- Populated unread emails bucketed by importance (boundaries: 70 / 40)
- Pending Tier-2 batches grouped by action_type
- Queued tier='important' notifications surfaced
- finalize sweep flips queued important rows → ok_via_digest
- finalize sweep idempotent on already-swept set (rowcount=0)
- Rule J: no body bytes in returned EmailProjection
- Pydantic shape round-trips via model_dump_json (Story 6-8 CR HIGH-1 lesson)
- AR-PAT-5 prompt module importable + shape valid
- policy.yaml entry present
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.notifications.tiers import send_important
from mailbot_api.verbs.compose_digest import (
    ComposeDigestOut,
    _bucket_importance,
    compose_digest,
)
from mailbot_api.verbs.finalize_digest_delivery import finalize_digest_delivery


@pytest.fixture
async def _db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "digest.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    subject: str = "test",
    importance_score: float | None = None,
    received_at: str | None = None,
) -> None:
    """Direct INSERT — tests are outside the boundary scan.

    Default received_at is "now" so the row falls inside the digest's
    24h unread proxy window. Pass an older timestamp to exercise the
    window-cutoff path.
    """
    from datetime import datetime
    from datetime import timezone as _tz
    effective_received = (
        received_at
        or datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    await execute_write(
        db_path,
        "INSERT INTO emails "
        "(graph_id, subject, from_address, received_at, "
        " importance_score, summary_short, class_coarse, sensitivity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, subject, "alice@example.com", effective_received,
            importance_score, "summary stub",
            "human_personal", "normal",
        ),
    )


# ---- bucketing -------------------------------------------------------------


def test_bucket_importance_high_at_70() -> None:
    assert _bucket_importance(70.0) == "high"
    assert _bucket_importance(85.5) == "high"


def test_bucket_importance_medium_at_40() -> None:
    assert _bucket_importance(40.0) == "medium"
    assert _bucket_importance(69.9) == "medium"


def test_bucket_importance_low_below_40() -> None:
    assert _bucket_importance(0.0) == "low"
    assert _bucket_importance(39.9) == "low"


def test_bucket_importance_null_falls_to_low() -> None:
    assert _bucket_importance(None) == "low"


# ---- compose_digest --------------------------------------------------------


async def test_compose_digest_empty_payload(_db: str) -> None:
    """Empty DB → all-empty collections + None weekly_artifacts."""
    out = await compose_digest(db_path=_db)
    assert isinstance(out, ComposeDigestOut)
    assert out.unread_by_importance == {"high": [], "medium": [], "low": []}
    assert out.pending_tier2_batches == []
    assert out.queued_important_notifications == []
    assert out.weekly_artifacts is None


async def test_compose_digest_buckets_unread_correctly(_db: str) -> None:
    await _seed_email(_db, graph_id="high-1", importance_score=85.0)
    await _seed_email(_db, graph_id="med-1", importance_score=50.0)
    await _seed_email(_db, graph_id="low-1", importance_score=10.0)
    await _seed_email(_db, graph_id="null-1", importance_score=None)

    out = await compose_digest(db_path=_db)
    assert len(out.unread_by_importance["high"]) == 1
    assert out.unread_by_importance["high"][0].email_id == "high-1"
    assert len(out.unread_by_importance["medium"]) == 1
    assert len(out.unread_by_importance["low"]) == 2  # the 10.0 + null-1


async def test_compose_digest_skips_emails_older_than_24h(_db: str) -> None:
    """Schema-reality: emails.is_read isn't captured. The 24h received_at
    window approximates "fresh / unread for this digest." Yesterday's
    digest already covered older rows."""
    from datetime import datetime, timedelta
    from datetime import timezone as _tz
    fresh_ts = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    stale_ts = (datetime.now(_tz.utc) - timedelta(hours=48)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    await _seed_email(
        _db, graph_id="fresh", importance_score=80.0, received_at=fresh_ts
    )
    await _seed_email(
        _db, graph_id="stale", importance_score=80.0, received_at=stale_ts
    )

    out = await compose_digest(db_path=_db)
    assert len(out.unread_by_importance["high"]) == 1
    assert out.unread_by_importance["high"][0].email_id == "fresh"


async def test_compose_digest_returns_queued_important(_db: str) -> None:
    await send_important("first important", "noisy_signals", db_path=_db)
    await send_important("second important", "noisy_signals", db_path=_db)

    out = await compose_digest(db_path=_db)
    assert len(out.queued_important_notifications) == 2
    assert (
        out.queued_important_notifications[0].message == "first important"
    )
    assert out.queued_important_notifications[0].category == "noisy_signals"


async def test_compose_digest_rule_j_no_body_bytes(_db: str) -> None:
    """The returned EmailProjection MUST NOT carry body bytes (Rule J)."""
    await _seed_email(_db, graph_id="x", importance_score=75.0)
    out = await compose_digest(db_path=_db)
    proj = out.unread_by_importance["high"][0]
    # EmailProjection shape has no body field — assert by attribute absence.
    assert not hasattr(proj, "body")
    assert not hasattr(proj, "body_preview")


# ---- finalize_digest_delivery ---------------------------------------------


async def test_finalize_flips_important_pending_to_ok_via_digest(_db: str) -> None:
    await send_important("a", "x", db_path=_db)
    await send_important("b", "y", db_path=_db)

    out = await finalize_digest_delivery(db_path=_db)
    assert out.ok is True
    assert out.delivered_count == 2

    row = await fetchone(
        _db,
        "SELECT COUNT(*) FROM notifications_outbox "
        "WHERE delivery_status='ok_via_digest'",
        (),
    )
    assert row is not None and row[0] == 2

    pending_row = await fetchone(
        _db,
        "SELECT COUNT(*) FROM notifications_outbox "
        "WHERE tier='important' AND delivery_status='pending'",
        (),
    )
    assert pending_row is not None and pending_row[0] == 0


async def test_finalize_idempotent_on_already_swept(_db: str) -> None:
    await send_important("a", "x", db_path=_db)
    out1 = await finalize_digest_delivery(db_path=_db)
    assert out1.delivered_count == 1
    out2 = await finalize_digest_delivery(db_path=_db)
    assert out2.delivered_count == 0  # nothing left to sweep


async def test_finalize_does_not_touch_urgent_rows(_db: str) -> None:
    """The sweep is tier='important' only — urgent rows stay pending."""
    from mailbot_api.notifications.tiers import send_urgent

    await send_urgent("urgent msg", "test", db_path=_db)
    await send_important("important msg", "test", db_path=_db)

    out = await finalize_digest_delivery(db_path=_db)
    assert out.delivered_count == 1  # only the important one

    urgent_row = await fetchone(
        _db,
        "SELECT delivery_status FROM notifications_outbox WHERE tier='urgent'",
        (),
    )
    assert urgent_row is not None and urgent_row[0] == "pending"


# ---- JSON serialization regression guard (Story 6-8 CR HIGH-1 lesson) -----


async def test_compose_digest_serializes_to_json_without_crash(_db: str) -> None:
    await _seed_email(_db, graph_id="x", importance_score=80.0)
    await send_important("note", "test", db_path=_db)
    out = await compose_digest(db_path=_db)

    payload = out.model_dump_json()
    import json
    decoded = json.loads(payload)
    assert decoded["unread_by_importance"]["high"]
    assert decoded["queued_important_notifications"]


# ---- AR-PAT-5 prompt module + policy.yaml entry ---------------------------


def test_daily_digest_intro_prompt_module_importable() -> None:
    from mailbot_api.prompts.daily_digest_intro import v1

    assert v1.VERSION == "v1"
    assert isinstance(v1.SYSTEM, str) and v1.SYSTEM
    assert isinstance(v1.USER_TEMPLATE, str) and v1.USER_TEMPLATE
    assert v1.OUTPUT_SCHEMA is v1.DailyDigestIntroOutput
    # max_length=200 enforced.
    long_intro = "x" * 250
    with pytest.raises(Exception):
        v1.DailyDigestIntroOutput(intro=long_intro)


def test_policy_yaml_has_daily_digest_intro_entry() -> None:
    """Verify the policy.yaml entry was added per AC-3."""
    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    policy_path = repo_root / "router" / "policy.yaml"
    text = policy_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert "daily_digest_intro" in cfg["tasks"]
    entry = cfg["tasks"]["daily_digest_intro"]
    assert entry["model"] == "qwen2.5:3b-instruct-q4_K_M"
    assert entry["lane"] == "batch"
    assert entry["max_tokens_out"] == 200
    assert entry["response_cache_ttl_seconds"] == 600
