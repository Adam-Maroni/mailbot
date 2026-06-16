"""Tests for mailbot_api/verbs/router_control.py — set_model_oneshot (Story 9.3).

Covers AC-1 (set_model_oneshot verb + OneShotOverride shape + TTL),
AC-6 (TTL expiry + consume-on-use behavior), and OQ-1 (single-slot global
flag — keying neither by session_id nor by caller_origin).

The override slot is a module-level singleton in router_control.py; tests
use the _reset_oneshot_override_for_test() helper for isolation.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest

from mailbot_api.verbs.router_control import (
    OneShotOverride,
    SetModelOneShotOut,
    _consume_oneshot_override,
    _get_active_oneshot_override,
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
    set_model_oneshot,
)


@pytest.fixture(autouse=True)
def _clean_oneshot() -> Generator[None, None, None]:
    """Reset the module-level slot between tests."""
    _reset_oneshot_override_for_test()
    yield
    _reset_oneshot_override_for_test()


# ---------------------------------------------------------------------------
# Category 1 — OneShotOverride shape
# ---------------------------------------------------------------------------


def test_oneshot_override_has_required_fields() -> None:
    """The shape must carry model + expires_at + set_at + session_id (audit-only)."""
    override = OneShotOverride(
        model="claude-haiku-4-5-20251001",
        expires_at="2026-06-14T12:05:00.000000Z",
        set_at="2026-06-14T12:00:00.000000Z",
        session_id="mcp-abc123",
    )
    assert override.model == "claude-haiku-4-5-20251001"
    assert override.expires_at == "2026-06-14T12:05:00.000000Z"
    assert override.set_at == "2026-06-14T12:00:00.000000Z"
    assert override.session_id == "mcp-abc123"


def test_oneshot_override_session_id_is_optional() -> None:
    """session_id is audit-only (OQ-1 Option B); None is acceptable."""
    override = OneShotOverride(
        model="qwen2.5:3b-instruct-q4_K_M",
        expires_at="2026-06-14T12:05:00.000000Z",
        set_at="2026-06-14T12:00:00.000000Z",
        session_id=None,
    )
    assert override.session_id is None


# ---------------------------------------------------------------------------
# Category 2 — _set_oneshot_override / _get_active_oneshot_override
# ---------------------------------------------------------------------------


def test_set_then_get_returns_same_override() -> None:
    """Setting then immediately reading returns the same override."""
    override = _set_oneshot_override(
        model="claude-haiku-4-5-20251001",
        ttl_seconds=300,
        session_id="mcp-abc",
    )
    active = _get_active_oneshot_override()
    assert active is not None
    assert active.model == override.model
    assert active.session_id == "mcp-abc"


def test_get_when_no_override_set_returns_none() -> None:
    """Fresh module state returns None."""
    assert _get_active_oneshot_override() is None


def test_set_with_default_ttl_is_300_seconds() -> None:
    """AC-1: TTL defaults to 5 minutes (300 seconds)."""
    before = datetime.now(timezone.utc)
    override = _set_oneshot_override(model="claude-opus-4-7")
    after = datetime.now(timezone.utc)
    expires_at = datetime.fromisoformat(override.expires_at.replace("Z", "+00:00"))
    delta = (expires_at - before).total_seconds()
    delta_max = (expires_at - after).total_seconds()
    # Should be approximately 300s from set-time (allow small clock skew window)
    assert 299 <= delta <= 301
    assert 299 <= delta_max + (after - before).total_seconds() <= 301


def test_set_replaces_existing_override() -> None:
    """AC-1: setting a new override replaces an existing one (last-write-wins)."""
    _set_oneshot_override(model="claude-haiku-4-5-20251001", session_id="A")
    second = _set_oneshot_override(model="claude-opus-4-7", session_id="B")
    active = _get_active_oneshot_override()
    assert active is not None
    assert active.model == "claude-opus-4-7"
    assert active.session_id == "B"
    assert active.set_at == second.set_at


def test_replacement_emits_structured_warning_log(caplog: pytest.LogCaptureFixture) -> None:
    """AC-1: replacement logs `event="oneshot_override.replaced"`."""
    import logging

    _set_oneshot_override(model="claude-haiku-4-5-20251001", session_id="A")
    # CR-F3: the `oneshot_override.replaced` warning is emitted by
    # `_log = logging.getLogger(__name__)` in `mailbot_api.router.oneshot`
    # (post-Task-6.5 relocation). The logger= arg targets the actual emitter.
    with caplog.at_level(logging.WARNING, logger="mailbot_api.router.oneshot"):
        _set_oneshot_override(model="claude-opus-4-7", session_id="B")
    # The replacement warning must fire with the structured event tag.
    assert any(
        getattr(record, "event", None) == "oneshot_override.replaced"
        for record in caplog.records
    ), f"Expected oneshot_override.replaced event; got: {[(r.message, getattr(r, 'event', None)) for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Category 3 — TTL eviction on read
# ---------------------------------------------------------------------------


def test_expired_override_evicted_on_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1, AC-6: expired overrides are evicted on read, not just on write."""
    # Set at T=0
    _set_oneshot_override(model="claude-haiku-4-5-20251001", ttl_seconds=300)
    assert _get_active_oneshot_override() is not None

    # Fast-forward by patching the clock used inside the helper.
    # The helper uses datetime.now(timezone.utc); patch via monkeypatch on
    # the module-level reference.
    import mailbot_api.router.oneshot as rc_module  # Story 9-3 boundary fix moved the slot here

    real_now = datetime.now(timezone.utc)
    fake_now = real_now + timedelta(seconds=301)

    class _FakeDatetime:
        @staticmethod
        def now(tz: timezone | None = None) -> datetime:
            return fake_now if tz else fake_now.replace(tzinfo=None)

    monkeypatch.setattr(rc_module, "_now_utc", lambda: fake_now)

    # T=301s — expired
    assert _get_active_oneshot_override() is None
    # Also evicted from the slot (subsequent reads stay None even without
    # advancing the clock further — eviction is permanent).
    monkeypatch.setattr(rc_module, "_now_utc", lambda: real_now)
    assert _get_active_oneshot_override() is None


def test_non_expired_override_not_evicted_on_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override within its TTL stays active across multiple reads."""
    import mailbot_api.router.oneshot as rc_module  # Story 9-3 boundary fix moved the slot here

    real_now = datetime.now(timezone.utc)
    monkeypatch.setattr(rc_module, "_now_utc", lambda: real_now)

    _set_oneshot_override(model="claude-haiku-4-5-20251001", ttl_seconds=300)
    # Advance clock by 100s — still within TTL
    monkeypatch.setattr(
        rc_module, "_now_utc", lambda: real_now + timedelta(seconds=100)
    )
    assert _get_active_oneshot_override() is not None
    # Read again — should remain active
    assert _get_active_oneshot_override() is not None


# ---------------------------------------------------------------------------
# Category 4 — _consume_oneshot_override
# ---------------------------------------------------------------------------


def test_consume_returns_override_and_clears_slot() -> None:
    """AC-2: consume returns the active override AND clears the slot atomically."""
    _set_oneshot_override(model="claude-haiku-4-5-20251001")
    consumed = _consume_oneshot_override()
    assert consumed is not None
    assert consumed.model == "claude-haiku-4-5-20251001"
    # Slot is cleared
    assert _get_active_oneshot_override() is None
    assert _consume_oneshot_override() is None


def test_consume_when_no_override_returns_none() -> None:
    """Consume on a fresh slot returns None."""
    assert _consume_oneshot_override() is None


def test_consume_on_expired_override_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired override consumed returns None (caller observes empty slot)."""
    import mailbot_api.router.oneshot as rc_module  # Story 9-3 boundary fix moved the slot here

    real_now = datetime.now(timezone.utc)
    monkeypatch.setattr(rc_module, "_now_utc", lambda: real_now)
    _set_oneshot_override(model="claude-haiku-4-5-20251001", ttl_seconds=300)

    monkeypatch.setattr(
        rc_module, "_now_utc", lambda: real_now + timedelta(seconds=301)
    )
    assert _consume_oneshot_override() is None


# ---------------------------------------------------------------------------
# Category 5 — set_model_oneshot verb (the agent-facing surface)
# ---------------------------------------------------------------------------


async def test_set_model_oneshot_accepts_full_id() -> None:
    """AC-1: full model IDs are accepted verbatim."""
    out = await set_model_oneshot(
        db_path="unused",  # unused for this verb (no DB writes)
        model="claude-haiku-4-5-20251001",
        session_id="mcp-test",
    )
    assert isinstance(out, SetModelOneShotOut)
    assert out.ok is True
    assert out.model == "claude-haiku-4-5-20251001"
    assert out.session_id == "mcp-test"
    assert out.error is None


@pytest.mark.parametrize(
    ("alias", "full_id"),
    [
        ("qwen", "qwen2.5:3b-instruct-q4_K_M"),
        ("haiku", "claude-haiku-4-5-20251001"),
        ("opus", "claude-opus-4-7"),
    ],
)
async def test_set_model_oneshot_normalizes_aliases(alias: str, full_id: str) -> None:
    """AC-1: shorthand aliases normalize to full IDs."""
    out = await set_model_oneshot(db_path="unused", model=alias)
    assert out.ok is True
    assert out.model == full_id


async def test_set_model_oneshot_rejects_unknown_model() -> None:
    """AC-1: unknown models return ok=False without writing the slot."""
    out = await set_model_oneshot(db_path="unused", model="nonsense-model")
    assert out.ok is False
    assert out.model is None
    assert out.error is not None
    assert "unknown model" in out.error.lower()
    # Slot must NOT have been written
    assert _get_active_oneshot_override() is None


async def test_set_model_oneshot_unknown_does_not_replace_existing() -> None:
    """AC-1: rejecting an unknown model leaves any existing override untouched."""
    _set_oneshot_override(model="claude-haiku-4-5-20251001", session_id="A")
    out = await set_model_oneshot(db_path="unused", model="nonsense", session_id="B")
    assert out.ok is False
    active = _get_active_oneshot_override()
    assert active is not None
    assert active.model == "claude-haiku-4-5-20251001"
    assert active.session_id == "A"


async def test_set_model_oneshot_returns_expires_at_iso() -> None:
    """expires_at is ISO-8601 UTC Z-suffixed (matches RouterCallRow.ts shape)."""
    out = await set_model_oneshot(db_path="unused", model="haiku")
    assert out.expires_at is not None
    assert out.expires_at.endswith("Z")
    # Parseable
    parsed = datetime.fromisoformat(out.expires_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Category 6 — OQ-1 sanity test: single-slot global keying (not session-keyed)
# ---------------------------------------------------------------------------


async def test_override_set_with_session_a_consumed_from_session_b() -> None:
    """OQ-1 Option B regression sentinel: the override slot is a single-slot
    global, NOT keyed by session_id. Setting from session A and reading from
    a context that would have session_id B returns the SAME override.

    If a future story introduces session-keyed lookups (e.g., multi-user),
    this test will fail and force re-architecture per OQ-1's documented
    decision trail.
    """
    out = await set_model_oneshot(
        db_path="unused", model="haiku", session_id="mcp-session-A"
    )
    assert out.ok is True

    # Read from a context that would have a different session_id (we don't
    # pass session_id to the helpers — they don't accept one. The helpers
    # operate on the module-level slot directly).
    active = _get_active_oneshot_override()
    assert active is not None
    assert active.model == "claude-haiku-4-5-20251001"
    # The session_id captured is the AUDIT-ONLY value from the set-time
    assert active.session_id == "mcp-session-A"
