"""Cache warmer per Story 2-7.

Every ``warm_interval_seconds`` (default 240s = 4 minutes, aligned to
Anthropic's 5-minute ephemeral cache TTL per Rule M), iterate the active
policy snapshot and issue a probe call for each task marked
``cache_warm: true``. The probe goes through ``ask_router`` with
``caller_origin="cache-warmer"`` so it's excluded from rate-limit
accounting and clearly identifiable in audit rows.

Warmer failures log ``event="cache_warmer.failed"`` and continue —
best-effort per AR-PAT process patterns.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mailbot_api.router.policy import get_policy

_log = logging.getLogger(__name__)

_PROBE_CONTENT: dict[str, Any] = {
    "subject": "[cache-warmer probe]",
    "sender": "warmer@mailbot.local",
    "body_preview": "(warmer probe — ignore)",
}


class CacheWarmer:
    """Lifecycle wrapper for the interval-driven warmer task."""

    def __init__(
        self,
        db_path: str,
        *,
        warm_interval_seconds: float = 240.0,
        ask_router_fn: Any = None,
    ) -> None:
        self.db_path = db_path
        self.warm_interval_seconds = warm_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        # `ask_router_fn` injection point — tests pass a fake to avoid
        # transitive Router + adapter wiring during interval-loop tests.
        if ask_router_fn is None:
            from mailbot_api.router.router import ask_router

            self._ask_router = ask_router
        else:
            self._ask_router = ask_router_fn

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        _log.info(
            "cache warmer started",
            extra={
                "event": "cache_warmer.started",
                "interval_seconds": self.warm_interval_seconds,
            },
        )

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._warm_one_pass()
            except Exception as exc:  # noqa: BLE001 — defensive top-of-loop
                _log.info(
                    "cache warmer pass failed",
                    extra={
                        "event": "cache_warmer.failed",
                        "exc_type": type(exc).__name__,
                    },
                )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.warm_interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def _warm_one_pass(self) -> None:
        try:
            policy = get_policy()
        except RuntimeError:
            # Policy not loaded yet — silently skip this pass.
            return

        for task_type, entry in policy.tasks.items():
            if not getattr(entry, "cache_warm", False):
                continue
            try:
                await self._ask_router(
                    task_type,
                    _PROBE_CONTENT,
                    db_path=self.db_path,
                    caller_origin="cache-warmer",
                )
            except Exception as exc:  # noqa: BLE001 — per-task failure tolerant
                _log.info(
                    "cache warmer probe failed",
                    extra={
                        "event": "cache_warmer.failed",
                        "task_type": task_type,
                        "exc_type": type(exc).__name__,
                    },
                )

    async def stop(self, *, timeout: float = 5.0) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        _log.info(
            "cache warmer stopped",
            extra={"event": "cache_warmer.stopped"},
        )


__all__ = ["CacheWarmer"]
