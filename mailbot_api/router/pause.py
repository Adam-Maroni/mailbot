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
    """A global, system-wide flag (not per-request) that stops the bot from
    calling any model.

    When set, ``ask_router`` short-circuits *before adapter dispatch*, so no
    ``ModelAdapter`` is ever invoked. It's a guardrail that prevents two things
    at once: (1) spending money on LLM token consumption, and (2) triggering
    write actions against the mailbox (e.g. Microsoft Graph writes — sending or
    moving mail).

    Pause **fails closed**: if it can't read its own state (e.g. a DB error), it
    treats the system as *paused*, because a guardrail whose job is to stop
    writes must err toward stopping them rather than silently re-opening the
    write path.

    Cross-process note: ``get_pause_state()`` (not the per-process in-memory
    mirror) is the source of truth at decision time — see its docstring for the
    F4 staleness bug this closes. See also ``docs/CONCEPTS.md``.
    """

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

    async def snapshot_now(self, db_path: str) -> tuple[bool, str | None]:
        """Story 10.5.1 (F4, CRITICAL) — authoritative CROSS-PROCESS pause read
        as ONE atomic (paused, reason) pair from a SINGLE ``fetchone``.

        ``is_paused()`` returns the per-process in-memory mirror seeded once at
        ``initialize()``. That mirror is stale in any process that did not run
        the pause verb: the worker-process drainer seeded ``_paused=False`` at
        its own boot and never re-read the DB, so an API-process pause left the
        drainer dispatching Graph writes while "paused" (259ms-after-propose
        F4). This reader hits the ``pause_state`` singleton row (migration 010)
        — the cross-process source of truth — at decision time.

        Returning both values from one read closes the CR-13 inconsistency
        window: separate ``is_paused``+``reason`` reads could straddle a resume
        and log ``paused=True`` with ``reason=None``. Callers that need both
        (the drainer gate + its audit row) MUST use this single-read snapshot.

        Fail-closed: any read failure is treated as PAUSED (with ``reason=None``)
        so a DB hiccup can never silently re-open the write path. The pause gate
        exists precisely to stop writes; erring toward "paused" is the safe
        direction.
        """
        try:
            row = await connection.fetchone(db_path, queries.PAUSE_STATE_SELECT, ())
        except Exception:  # noqa: BLE001 — fail-closed: a read error must not re-open writes
            _log.exception(
                "pause_state authoritative read failed — failing closed (treating as paused)",
                extra={"event": "router.pause.read_failed"},
            )
            return True, None
        if row is None or not bool(row[0]):
            return False, None
        reason = row[1]
        return True, (str(reason) if reason is not None else None)

    async def is_paused_now(self, db_path: str) -> bool:
        """Authoritative cross-process pause boolean (single-value convenience
        over :meth:`snapshot_now`). Use ``snapshot_now`` when the reason is also
        needed so both come from one read."""
        paused, _reason = await self.snapshot_now(db_path)
        return paused

    async def reason_now(self, db_path: str) -> str | None:
        """Authoritative cross-process pause reason (single-value convenience
        over :meth:`snapshot_now`). Returns ``None`` when not paused or
        unreadable — the reason is advisory (log/audit context)."""
        _paused, reason = await self.snapshot_now(db_path)
        return reason

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
