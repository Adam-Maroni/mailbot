"""Posture state — Story 6-4 (single-row `posture_state` table).

The `urgent_only` posture is the "I'm becoming noisy, going quiet" mode:
when active, the dispatcher drops `tier='important'` and `tier='informational'`
calls; `tier='urgent'` always delivers; `tier='silent'` still logs.

The auto-trigger (response-rate < 30% over 7 days) is deferred per the
Story 6-4 scope reduction (Hermes-side message-from-Adam ingest not yet
shipped). The manual setter `set_urgent_only(reason)` IS shipped. The
posture lifts when Adam runs `/resume` (Story 6-3 wired this — see
`mailbot_api/verbs/router_control.py:resume_router`).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)


class PostureState(BaseModel):
    """Snapshot of the single-row posture_state table."""

    urgent_only: bool
    set_at: str | None = None
    reason: str | None = None


async def get_posture(db_path: str) -> PostureState:
    """Read the current posture. The single-row table is seeded by migration
    020 so this should never return None; defensive against migration drift."""
    row = await connection.fetchone(db_path, queries.POSTURE_STATE_SELECT, ())
    if row is None:
        # Migration 020 should have inserted the row; surface the gap.
        logger.warning(
            "posture_state row missing",
            extra={"event": "posture.row.missing"},
        )
        return PostureState(urgent_only=False)
    return PostureState(
        urgent_only=bool(row[0]),
        set_at=row[1],
        reason=row[2],
    )


async def is_urgent_only_active(db_path: str) -> bool:
    """Convenience for the dispatcher's hot path. One SELECT, no shape build."""
    row = await connection.fetchone(db_path, queries.POSTURE_STATE_SELECT, ())
    if row is None:
        return False
    return bool(row[0])


async def set_urgent_only(reason: str, *, db_path: str) -> None:
    """Activate urgent-only posture. Records `set_at` + `reason` for audit."""
    now = utc_z_now()
    rowcount = await connection.execute_write(
        db_path, queries.POSTURE_STATE_SET_URGENT_ONLY, (now, reason)
    )
    if rowcount == 0:
        logger.warning(
            "posture.set_urgent_only no row updated",
            extra={"event": "posture.set.no_row"},
        )
        return
    logger.warning(
        "urgent-only posture activated",
        extra={
            "event": "posture.urgent_only.activated",
            "reason": reason,
            "set_at": now,
        },
    )


async def lift_urgent_only(*, db_path: str) -> bool:
    """Deactivate urgent-only posture. Returns True iff the posture was
    actively urgent-only before this call (so callers can decide whether
    to emit a defender-toned "back to normal" message).

    CR LOW-2/LOW-4: ``posture_state`` clears ``set_at`` + ``reason`` on
    lift (single-row singleton semantics — only "current" state survives).
    The lift event is logged at WARNING level with ``lifted_at`` so the
    "noisy episode ended" timestamp lives in log archives even though it's
    cleared from the row. Pre-lift `set_at` + `reason` are also emitted
    in the event so the episode duration is reconstructible.
    """
    # Read pre-lift state so we can include set_at + reason in the audit event.
    pre_state = await get_posture(db_path)
    if not pre_state.urgent_only:
        return False
    await connection.execute_write(
        db_path, queries.POSTURE_STATE_LIFT_URGENT_ONLY, ()
    )
    lifted_at = utc_z_now()
    logger.warning(
        "urgent-only posture lifted",
        extra={
            "event": "posture.urgent_only.lifted",
            "lifted_at": lifted_at,
            "pre_lift_set_at": pre_state.set_at,
            "pre_lift_reason": pre_state.reason,
        },
    )
    return True


__all__ = [
    "PostureState",
    "get_posture",
    "is_urgent_only_active",
    "set_urgent_only",
    "lift_urgent_only",
]
