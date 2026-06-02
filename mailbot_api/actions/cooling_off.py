"""Cooling-off ticker — Story 4-6.

Tier-3 SEND-family proposals land in `status='cooling_off'` per Story 4-2.
This module ticks every 1s, promoting rows whose proposed_at + COOLING_OFF
window has elapsed to `status='pending'` — at which point the Story 4-4
drainer picks them up.

The COOLING_OFF window is env-configurable to give the operator runtime
override (default 60s; `MAILBOT_COOLING_OFF_SECONDS=0` for tests / scripted
flows that don't need a cancel window).

Race-safety vs `cancel_action` (Story 4-6 AC-2): both flips include an
`AND status='cooling_off'` guard so SQLite's row-level atomicity guarantees
exactly one wins.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from mailbot_api.config import get_secret_optional
from mailbot_api.db.connection import execute_write
from mailbot_api.db.queries import COOLING_OFF_PROMOTE_DUE

_logger = logging.getLogger(__name__)


def _read_cooling_off_seconds() -> int:
    """Read the cooling-off window from env. Default 60s.

    Read on every call so tests + operator overrides take effect mid-process.
    Cheaply mockable in tests via monkeypatch.setenv.
    """
    raw = get_secret_optional("MAILBOT_COOLING_OFF_SECONDS", "")
    if not raw:
        return 60
    try:
        n = int(raw)
    except ValueError:
        _logger.warning(
            "invalid MAILBOT_COOLING_OFF_SECONDS",
            extra={"event": "cooling_off.invalid_env", "raw_value": raw},
        )
        return 60
    return max(0, n)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


async def cooling_off_tick(db_path: str) -> int:
    """One iteration of the cooling-off ticker. Returns the number of rows promoted.

    Promotes every cooling_off row whose proposed_at is older than now()-window.
    Atomic UPDATE with status='cooling_off' guard prevents racing with cancel.
    """
    window_seconds = _read_cooling_off_seconds()
    cutoff = _utc_now() - timedelta(seconds=window_seconds)
    cutoff_iso = _iso(cutoff)
    rowcount = await execute_write(db_path, COOLING_OFF_PROMOTE_DUE, (cutoff_iso,))
    if rowcount > 0:
        _logger.info(
            "cooling-off rows promoted to pending",
            extra={
                "event": "action.cooling_off.promoted",
                "count": rowcount,
                "cutoff": cutoff_iso,
                "window_seconds": window_seconds,
            },
        )
    return rowcount


__all__ = ["cooling_off_tick"]
