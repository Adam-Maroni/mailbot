"""Pause/resume kill-switch per Story 2-9.

Module-level pause flag with SQLite persistence. When ``is_paused()`` is
True, ``ask_router`` short-circuits before adapter dispatch with
``RouterError(code=PROVIDER_ERROR, message="router paused", retryable=True)``.
In-flight calls at pause time finish normally — we never abort mid-call.

Verb-side handlers live in ``mailbot_api/verbs/router_control.py``.
"""

from __future__ import annotations

import logging

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now

_log = logging.getLogger(__name__)


class PauseState:
    def __init__(self) -> None:
        self._paused: bool = False
        self._reason: str | None = None

    async def initialize(self, db_path: str) -> None:
        row = await connection.fetchone(db_path, queries.PAUSE_STATE_SELECT, ())
        if row is None:
            return
        self._paused = bool(row[0])
        self._reason = row[1]

    def is_paused(self) -> bool:
        return self._paused

    def reason(self) -> str | None:
        return self._reason

    async def pause(self, db_path: str, *, reason: str) -> None:
        now_iso = utc_z_now()
        await connection.execute_write(
            db_path, queries.PAUSE_STATE_PAUSE, (reason, now_iso)
        )
        self._paused = True
        self._reason = reason
        _log.warning(
            "router paused",
            extra={"event": "router.paused", "reason": reason},
        )

    async def resume(self, db_path: str) -> None:
        now_iso = utc_z_now()
        await connection.execute_write(
            db_path, queries.PAUSE_STATE_RESUME, (now_iso,)
        )
        self._paused = False
        self._reason = None
        _log.info(
            "router resumed",
            extra={"event": "router.resumed"},
        )

    async def try_pause_if_unpaused(self, db_path: str, *, reason: str) -> bool:
        # Story 6-15 CR-1: only pause when not already paused; never clobber a
        # foreign reason (operator's manual_hold, future automation, etc.).
        # The check + write are decided synchronously before any await — the
        # asyncio event loop is single-threaded so no other task can mutate
        # _paused between this read and the await. Returns True if we paused.
        if self._paused:
            return False
        await self.pause(db_path, reason=reason)
        return True

    async def try_resume_if_reason(self, db_path: str, *, expected_reason: str) -> bool:
        # Story 6-15 CR-10: collapse the previous three-call check-and-resume
        # (is_paused → reason → resume) into a single atomic helper. The
        # snapshot reads are sync (no await between them) so the only window
        # for a foreign re-pause is during the resume's await; that's
        # unavoidable without a full lock — but bounding the window to the
        # write itself is meaningfully tighter than the prior pattern.
        if not self._paused:
            return False
        if self._reason != expected_reason:
            return False
        await self.resume(db_path)
        return True

    def reset_for_test(self) -> None:
        self._paused = False
        self._reason = None


_PAUSE_STATE = PauseState()


def get_pause_state() -> PauseState:
    return _PAUSE_STATE


def _reset_pause_state_for_test() -> None:
    _PAUSE_STATE.reset_for_test()


__all__ = ["PauseState", "get_pause_state"]
