"""Story 6-6 worker-process scheduler — owns all LLM-free critical-infra interval tasks.

Two registration shapes are supported:

* `register_interval_task(component, interval_seconds, coro_factory)` — the scheduler
  drives a `while True: await coro_factory(); heartbeat; await sleep(interval)` loop
  itself. Used for tasks without their own lifecycle (sync, ingest, cooling_off).
* `register_managed_task(component, instance)` — the scheduler tracks an instance
  with `.start()` / `.stop()` of its own (e.g. `CacheWarmer`, `AnomalyDetector`).
  Heartbeats for managed tasks are written by a separate wrapper task that polls
  the instance, since their internal loop is opaque to the scheduler.

Per-iteration semantics for *interval* tasks:
  1. timer start
  2. await coro_factory()  (catches all `Exception`; `BaseException` propagates)
  3. write worker_health row: outcome="ok" on success, "failed"+sanitized_error otherwise
  4. log `event="scheduler.slow_task"` if duration > 120s (per AC-5)
  5. sleep(interval_seconds) — interruptible via the shutdown event

The scheduler NEVER lets a single task's failure crash the worker — every per-task
loop has its own `try/except Exception` boundary. `BaseException` (Cancelled,
SystemExit, KeyboardInterrupt) propagates by design to allow clean shutdown.

Component names are stable identifiers consumed by Story 6.1's `mailbot status`
CLI (and by the existing Story 1-8 sync-health alarm). Do not rename casually.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from mailbot_api.db.connection import execute_write
from mailbot_api.db.queries import WORKER_HEALTH_UPSERT
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)

# Threshold above which an iteration is flagged as slow (per AC-5).
SLOW_TASK_THRESHOLD_SECONDS: float = 120.0

# Default heartbeat interval for managed tasks (we poll the instance's task
# state at this cadence to report liveness in worker_health).
MANAGED_HEARTBEAT_INTERVAL_SECONDS: float = 60.0


class ManagedLifecycle(Protocol):
    """Subset of the lifecycle contract `CacheWarmer` / `AnomalyDetector` expose."""

    async def start(self) -> None: ...
    async def stop(self, *, timeout: float = ...) -> None: ...


def _sanitize_error(exc: BaseException) -> str:
    """Truncate the message so we never blow out the `last_error` column on
    a verbose adapter exception."""
    return f"{type(exc).__name__}: {str(exc)[:200]}"


async def upsert_worker_health(
    db_path: str,
    *,
    component: str,
    outcome: str,
    error: str | None = None,
) -> None:
    """Write one row into worker_health. The canonical owner of this write
    (Story 6-6 CR-5 disposition: scheduler is the single point of definition;
    `mailbot_api.worker.upsert_heartbeat` delegates here for the Story 1-8
    surface, so both call sites stay in lockstep if the query ever changes)."""
    await execute_write(
        db_path,
        WORKER_HEALTH_UPSERT,
        (component, utc_z_now(), outcome, error),
    )


@dataclass
class _IntervalEntry:
    """Registered interval task — driven by the scheduler's own loop."""

    component: str
    interval_seconds: float
    coro_factory: Callable[[], Awaitable[object]]


@dataclass
class _ManagedEntry:
    """Registered managed task — owns its own loop, exposes start()/stop()."""

    component: str
    instance: ManagedLifecycle
    heartbeat_interval_seconds: float = MANAGED_HEARTBEAT_INTERVAL_SECONDS


@dataclass
class Scheduler:
    """Worker-process scheduler. Construct once per worker boot.

    Usage::

        scheduler = Scheduler(db_path)
        scheduler.register_interval_task("sync", 240.0, sync_factory)
        scheduler.register_managed_task("cache_warmer", CacheWarmer(db_path))
        await scheduler.start()
        # ... worker runs until shutdown signal
        await scheduler.stop()
    """

    db_path: str
    _interval_entries: list[_IntervalEntry] = field(default_factory=list)
    _managed_entries: list[_ManagedEntry] = field(default_factory=list)
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    _started: bool = False

    def register_interval_task(
        self,
        component: str,
        interval_seconds: float,
        coro_factory: Callable[[], Awaitable[object]],
    ) -> None:
        """Register a scheduler-driven interval task."""
        if self._started:
            raise RuntimeError(
                "cannot register tasks after Scheduler.start(); "
                f"attempted: {component!r}"
            )
        self._interval_entries.append(
            _IntervalEntry(
                component=component,
                interval_seconds=interval_seconds,
                coro_factory=coro_factory,
            )
        )

    def register_managed_task(
        self,
        component: str,
        instance: ManagedLifecycle,
        *,
        heartbeat_interval_seconds: float = MANAGED_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        """Register a managed task with its own start()/stop() lifecycle."""
        if self._started:
            raise RuntimeError(
                "cannot register tasks after Scheduler.start(); "
                f"attempted: {component!r}"
            )
        self._managed_entries.append(
            _ManagedEntry(
                component=component,
                instance=instance,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
        )

    async def start(self) -> None:
        """Spawn one asyncio task per registered entry. Returns once all tasks
        are scheduled (does NOT block on them — call `stop()` to tear down)."""
        if self._started:
            return
        self._started = True
        self._stop_event.clear()

        for entry in self._interval_entries:
            self._tasks.append(
                asyncio.create_task(
                    self._run_interval_loop(entry),
                    name=f"scheduler.interval.{entry.component}",
                )
            )

        for managed in self._managed_entries:
            await managed.instance.start()
            self._tasks.append(
                asyncio.create_task(
                    self._run_managed_heartbeat_loop(managed),
                    name=f"scheduler.managed.{managed.component}",
                )
            )

        logger.info(
            "scheduler started",
            extra={
                "event": "scheduler.started",
                "interval_tasks": [e.component for e in self._interval_entries],
                "managed_tasks": [e.component for e in self._managed_entries],
            },
        )

    async def stop(self, *, timeout: float = 30.0) -> None:
        """Signal all tasks to stop and await their teardown."""
        if not self._started:
            return
        self._stop_event.set()

        # Stop managed instances first so they can flush.
        for managed in self._managed_entries:
            try:
                await managed.instance.stop(timeout=timeout)
            except Exception as exc:  # noqa: BLE001 — defensive on third-party stop()
                logger.warning(
                    "managed task stop failed",
                    extra={
                        "event": "scheduler.managed.stop_failed",
                        "component": managed.component,
                        "error": _sanitize_error(exc),
                    },
                )

        # Now cancel + await scheduler-owned tasks.
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        self._tasks.clear()
        self._started = False
        logger.info("scheduler stopped", extra={"event": "scheduler.stopped"})

    async def _run_interval_loop(self, entry: _IntervalEntry) -> None:
        """Per-interval-task loop. Heartbeats + slow-task warnings on every iteration.

        The slow-task warning (AC-5) fires unconditionally after the task
        attempt completes — including when the task raised. A task that hangs
        for >120s and then fails is exactly the case we want to flag for
        investigation, so the warning lives outside the try/except branches
        per CR-3 (Story 6-6 review 2026-06-03).
        """
        while not self._stop_event.is_set():
            start_monotonic = time.monotonic()
            failed: bool = False
            failure_error: str | None = None
            try:
                await entry.coro_factory()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — single-task isolation
                failed = True
                failure_error = _sanitize_error(exc)
                logger.error(
                    "interval task failed",
                    extra={
                        "event": "scheduler.interval.failed",
                        "component": entry.component,
                        "duration_seconds": time.monotonic() - start_monotonic,
                        "exc_type": type(exc).__name__,
                    },
                )

            # Slow-task warning fires unconditionally — slow-then-failed is
            # exactly the case CR-3 caught as a monitoring blind spot.
            duration = time.monotonic() - start_monotonic
            if duration > SLOW_TASK_THRESHOLD_SECONDS:
                logger.warning(
                    "scheduler slow task",
                    extra={
                        "event": "scheduler.slow_task",
                        "component": entry.component,
                        "duration_seconds": duration,
                        "outcome": "failed" if failed else "ok",
                    },
                )

            # Heartbeat — always written, regardless of success/failure.
            try:
                await upsert_worker_health(
                    self.db_path,
                    component=entry.component,
                    outcome="failed" if failed else "ok",
                    error=failure_error,
                )
            except Exception:  # noqa: BLE001 — last-ditch; never crash the loop
                logger.exception("heartbeat write failed")

            # Wait for next tick or shutdown, whichever comes first.
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=entry.interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def _run_managed_heartbeat_loop(self, managed: _ManagedEntry) -> None:
        """Managed-task heartbeat poll loop. Reports outcome=ok as long as the
        underlying instance's task is running and not cancelled.

        We can't reach into the third-party loop to detect per-iteration
        success — managed components handle their own per-iteration failure
        logging. The scheduler-side heartbeat reports liveness only."""
        while not self._stop_event.is_set():
            # Look up the underlying task (managed instances expose `._task`
            # by convention — see CacheWarmer / AnomalyDetector). If absent
            # or done, report failed.
            inner_task = getattr(managed.instance, "_task", None)
            if inner_task is None or inner_task.done():
                outcome = "failed"
                error = "managed_task_not_running"
            else:
                outcome = "ok"
                error = None

            try:
                await upsert_worker_health(
                    self.db_path,
                    component=managed.component,
                    outcome=outcome,
                    error=error,
                )
            except Exception:  # noqa: BLE001 — last-ditch
                logger.exception("managed heartbeat write failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=managed.heartbeat_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass


__all__ = [
    "MANAGED_HEARTBEAT_INTERVAL_SECONDS",
    "SLOW_TASK_THRESHOLD_SECONDS",
    "ManagedLifecycle",
    "Scheduler",
    "upsert_worker_health",
]
