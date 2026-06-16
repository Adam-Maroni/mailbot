"""One-shot model override slot per Story 9-3.

This module owns the module-level single-slot global `_oneshot_override`
that the chat-side `/model <model>` slash command sets and that the next
`ask_router` call consumes.

OQ-1 Option B (Adam-decided 2026-06-14): single-slot global, NOT keyed by
session_id. Matches MailBot's single-user deployment reality; the TTL
(5 min) + consume-on-use already provide bounded-lifetime guarantees.

**Architectural placement** (Story 5-2 AC-7 boundary): the slot lives
HERE in `mailbot_api/router/` (the consumer's territory) rather than in
`mailbot_api/verbs/router_control.py` (the verb's territory). The verb
sets the slot via `_set_oneshot_override(...)`; the router peeks and
consumes via `_get_active_oneshot_override()` / `_consume_oneshot_override()`.
This placement keeps the verb-import-isolation boundary intact —
`router.py` reaches into a router-internal module, NOT into a verb.

**Lifecycle:**

  - Module-level state RESETS on container restart by design (operator
    state, not durable state).
  - Replacement is last-write-wins with a structured `oneshot_override.replaced`
    warning emitted via Python's logging.
  - Expired entries are evicted on read (`_get_active_oneshot_override`),
    not just on write — so a stale slot is treated as no override.

**Consume contract:** `_consume_oneshot_override()` returns the active
override AND clears the slot atomically. Atomic here means "no `await`
between read-and-clear" — single-threaded asyncio semantics make this
trivially safe within one task.

**module-singleton:** per-process one-shot override; single-user
assumption per OQ-1; reset on container restart.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

_DEFAULT_ONESHOT_TTL_SECONDS = 300


def _now_utc() -> datetime:
    """Indirection so tests can monkeypatch the clock without touching
    `datetime` globally (which would break other modules importing it
    separately)."""
    return datetime.now(timezone.utc)


class OneShotOverride(BaseModel):
    """Module-level one-shot override per Story 9-3 OQ-1.

    ``session_id`` is captured for audit trail visibility (structured-log
    breadcrumb) but does NOT key the lookup — the override slot is a single
    global per-process per OQ-1 Option B.
    """

    model: str = Field(..., description="Full model ID (post-alias-normalization)")
    expires_at: str = Field(..., description="ISO-8601 UTC Z-suffixed expiry timestamp")
    set_at: str = Field(..., description="ISO-8601 UTC Z-suffixed set timestamp")
    session_id: str | None = Field(
        None,
        description=(
            "Audit-only: the MCP session that set the override. NOT used as a "
            "lookup key per OQ-1 Option B."
        ),
    )


# Module-level single-slot per OQ-1.
_oneshot_override: OneShotOverride | None = None


def _iso_z(dt: datetime) -> str:
    """Format datetime as microsecond-precision ISO-8601 UTC Z-suffixed."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _set_oneshot_override(
    *,
    model: str,
    ttl_seconds: int = _DEFAULT_ONESHOT_TTL_SECONDS,
    session_id: str | None = None,
) -> OneShotOverride:
    """Write the module-level slot with a new override.

    If an active override already exists, log a structured-log replacement
    warning (`event="oneshot_override.replaced"`) and overwrite.
    """
    global _oneshot_override
    now = _now_utc()
    new_override = OneShotOverride(
        model=model,
        expires_at=_iso_z(now + timedelta(seconds=ttl_seconds)),
        set_at=_iso_z(now),
        session_id=session_id,
    )
    if _oneshot_override is not None:
        _log.warning(
            "oneshot_override replaced — previous model=%s, new model=%s",
            _oneshot_override.model,
            new_override.model,
            extra={
                "event": "oneshot_override.replaced",
                "previous_model": _oneshot_override.model,
                "new_model": new_override.model,
            },
        )
    _oneshot_override = new_override
    return new_override


def _get_active_oneshot_override() -> OneShotOverride | None:
    """Return the active override, evicting if expired.

    Eviction on read (AC-1) — not just on write. A stale override left in
    the slot after TTL expiry is treated as no override.
    """
    global _oneshot_override
    if _oneshot_override is None:
        return None
    expires_at = datetime.fromisoformat(
        _oneshot_override.expires_at.replace("Z", "+00:00")
    )
    if _now_utc() >= expires_at:
        _oneshot_override = None
        return None
    return _oneshot_override


def _consume_oneshot_override() -> OneShotOverride | None:
    """Return the active override AND clear the slot atomically.

    "Atomic" here means "no await between read-and-clear" — single-threaded
    asyncio semantics make this trivially safe within one task.
    """
    global _oneshot_override
    active = _get_active_oneshot_override()
    if active is None:
        return None
    _oneshot_override = None
    return active


def _reset_oneshot_override_for_test() -> None:
    """Test-only: clear the slot between tests."""
    global _oneshot_override
    _oneshot_override = None


__all__ = [
    "OneShotOverride",
    "_consume_oneshot_override",
    "_get_active_oneshot_override",
    "_reset_oneshot_override_for_test",
    "_set_oneshot_override",
]
