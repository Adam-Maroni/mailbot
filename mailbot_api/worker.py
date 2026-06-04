"""Background worker process for mailbot-api container.

Per AR-D7-1: this is the second process inside `mailbot-api`. Started by
`docker/entrypoint.sh` via `python -m mailbot_api.worker` and backgrounded.
The entrypoint's `wait -n` causes the container to exit if this process dies,
which docker-compose's `restart: unless-stopped` then recovers.

Story 1-8 shipped the sync loop in isolation. Story 6-6 promotes the worker
to host the full mailbot-api scheduler — sync, cache warmer, ingest pipeline,
anomaly detector, cooling-off ticker, plus the continuous `pending_actions`
drainer wired to the real `OutlookGraphWriteAdapter`. Every component writes
its own `worker_health` heartbeat so `mailbot status` (Story 6.1) can read a
single source of truth.

Backwards compatibility note: Story 1-8's public symbols (`sync_loop`,
`WorkerState`, `_run_sync_iteration`, `_check_alarm`, `minutes_since`,
`upsert_heartbeat`, `read_sync_health`, the SYNC_INTERVAL_SECONDS and
STALE_THRESHOLD_MINUTES constants) are preserved verbatim — existing tests
(`tests/integration/test_worker_health_alarm.py` et al.) reach into them
directly. The new `_worker_main` entry layers the scheduler on top WITHOUT
removing any of those surfaces.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from mailbot_api.actions.cooling_off import cooling_off_tick
from mailbot_api.actions.drainer import run_loop as drainer_run_loop
from mailbot_api.actions.outlook_adapter import OutlookGraphWriteAdapter
from mailbot_api.config import SecretMissing, get_secret
from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import (
    OAUTH_STATE_ACCESS_TOKEN_SELECT,
    WORKER_HEALTH_SELECT,
)
from mailbot_api.ingest.backpressure import run_drain_loop
from mailbot_api.notifications import tiers as notification_tiers
from mailbot_api.observability.logging import configure_logging
from mailbot_api.observability.scheduler import Scheduler, upsert_worker_health
from mailbot_api.router.anomaly import AnomalyDetector
from mailbot_api.router.cache_warmer import CacheWarmer
from mailbot_api.sync.sync_worker import SyncResult, run_once

logger = logging.getLogger(__name__)

# Per FR-1.1: sync every 4 minutes (aligned to Anthropic 5-min cache TTL).
SYNC_INTERVAL_SECONDS = 240
NOTIFICATION_RECOVERY_INTERVAL_SECONDS = 10  # Story 6-3: reclaim stuck deliveries

# Story 6-6 cron-split intervals — all LLM-free critical infra lives in the
# mailbot-api scheduler per AR-D13-1.
INGEST_PIPELINE_INTERVAL_SECONDS = 300       # every 5 minutes
COOLING_OFF_INTERVAL_SECONDS = 1             # every 1 second; honors AC's "fast tick"
CACHE_WARMER_INTERVAL_SECONDS = 240          # every 4 minutes (Rule M)
ANOMALY_INTERVAL_SECONDS = 3600              # hourly

# Stale threshold per FR-1.5: alarm fires after 60 min without an `ok` heartbeat.
STALE_THRESHOLD_MINUTES = 60


def _parse_utc_iso8601(value: str) -> datetime:
    # Lenient: accepts both microsecond-precision (post-2026-06-02) and
    # legacy second-precision timestamps. `fromisoformat` handles both
    # natively once the `Z` suffix is normalized to a UTC offset.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class WorkerState:
    """Per-process state for alarm debouncing (one entry per epoch loop)."""

    alarm_fired_for_episode: bool = False


async def upsert_heartbeat(
    db_path: str, *, component: str, outcome: str, error: str | None = None
) -> None:
    """Write (component, now, outcome, error) into worker_health (single-row-per-component).

    CR-5 (2026-06-03): the canonical owner of this write is
    `mailbot_api.observability.scheduler.upsert_worker_health` (Story 6-6).
    This Story 1-8 surface is preserved verbatim and now delegates to the
    scheduler implementation so both call sites stay in lockstep if the
    query ever changes.
    """
    await upsert_worker_health(
        db_path, component=component, outcome=outcome, error=error,
    )


async def read_sync_health(db_path: str) -> tuple[str | None, str | None, str | None]:
    """Return (last_heartbeat_at, last_outcome, last_error) for component='sync'.

    Returns (None, None, None) when no row exists yet (first 4 min of startup).
    """
    row = await fetchone(db_path, WORKER_HEALTH_SELECT, ("sync",))
    if row is None:
        return (None, None, None)
    return (row[1], row[2], row[3])


def minutes_since(ts_iso8601: str) -> float:
    """Return minutes elapsed since the given UTC ISO-8601 Z timestamp."""
    then = _parse_utc_iso8601(ts_iso8601)
    delta = datetime.now(timezone.utc) - then
    return delta.total_seconds() / 60.0


async def _run_sync_iteration(db_path: str, state: WorkerState) -> SyncResult | None:
    """Run one sync iteration; write heartbeat; check alarm. Returns the result
    or None on failure. NEVER raises — exceptions are caught + logged + heartbeat-failed."""
    try:
        result = await run_once(db_path)
    except Exception as exc:  # noqa: BLE001 — broad catch is the AC-1 contract
        sanitized = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.error(
            "sync iteration failed",
            extra={
                "event": "sync.failed",
                "error_type": type(exc).__name__,
            },
        )
        await upsert_heartbeat(db_path, component="sync", outcome="failed", error=sanitized)
        # Failure does NOT reset the alarm-fired flag.
        return None

    # Success path.
    await upsert_heartbeat(db_path, component="sync", outcome="ok", error=None)
    if state.alarm_fired_for_episode:
        logger.info(
            "sync recovered — clearing alarm",
            extra={"event": "sync.health.recovered"},
        )
    state.alarm_fired_for_episode = False
    return result


async def _check_alarm(db_path: str, state: WorkerState) -> None:
    """Check sync-health staleness; fire alarm + notification if past threshold
    AND not yet fired for this episode."""
    last_heartbeat, last_outcome, _last_error = await read_sync_health(db_path)
    if last_heartbeat is None or last_outcome is None:
        return  # no sync history yet — too early to alarm

    elapsed_minutes = minutes_since(last_heartbeat)
    if last_outcome == "ok" and elapsed_minutes < STALE_THRESHOLD_MINUTES:
        return  # healthy

    if not state.alarm_fired_for_episode:
        logger.error(
            "sync health alarm",
            extra={
                "event": "sync.health.alarm",
                "minutes_since_last_ok": elapsed_minutes,
                "last_outcome": last_outcome,
            },
        )
        # Story 6-3: route via the four-tier dispatcher so Hermes pulls
        # this and posts to Discord.
        await notification_tiers.send_urgent(
            f"sync stale > {STALE_THRESHOLD_MINUTES} min "
            f"(elapsed={elapsed_minutes:.1f}m, last_outcome={last_outcome})",
            "health",
            db_path=db_path,
        )
        state.alarm_fired_for_episode = True


async def sync_loop(
    db_path: str,
    *,
    interval_seconds: int = SYNC_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    iterations: int | None = None,
) -> None:
    """The worker's standalone sync loop — preserved verbatim from Story 1-8 so
    `tests/integration/test_worker_health_alarm.py` still drives the alarm
    contract via this entry. Story 6-6's `_worker_main` no longer calls this
    function in production (the scheduler drives sync directly via
    `_sync_iteration_with_alarm`), but the entry must keep working in tests.

    Catches all Exception in `_run_sync_iteration` so the loop continues across
    failures. BaseException (KeyboardInterrupt, SystemExit) propagates by design.
    """
    if sleep is None:
        sleep = asyncio.sleep
    state = WorkerState()
    iteration_count = 0
    while iterations is None or iteration_count < iterations:
        await _run_sync_iteration(db_path, state)
        await _check_alarm(db_path, state)
        iteration_count += 1
        if iterations is not None and iteration_count >= iterations:
            break
        await sleep(interval_seconds)


# --- Story 6-6 scheduler-integration helpers ---

def _make_sync_iteration_factory(
    db_path: str, state: WorkerState
) -> Callable[[], Awaitable[None]]:
    """Build a coro-factory for the scheduler that runs one sync iteration
    AND checks the alarm. Preserves Story 1-8's per-iteration shape under the
    scheduler's per-task boundary; the scheduler also writes a heartbeat after,
    so two heartbeats land per iteration (once by `_run_sync_iteration` itself,
    once by the scheduler wrapper) — both target `component="sync"` with the
    same outcome, so the ON CONFLICT upsert squashes them to one effective row.
    """

    async def _iter() -> None:
        await _run_sync_iteration(db_path, state)
        await _check_alarm(db_path, state)

    return _iter


@dataclass
class _CachedAccessToken:
    """Mutable closure cell holding the most-recent access token.

    `OutlookGraphWriteAdapter.access_token_provider` is a SYNC callable —
    we can't await `oauth.get_access_token` from inside it. The drainer's
    async loop refreshes this cell periodically (and on demand at boot);
    the provider returns whatever the most-recent refresh wrote.

    If the access token is stale when a drainer dispatch fires, the
    dispatched call gets a 401 and the drainer's retry chain on the next
    tick succeeds once the refresher has caught up. This matches the
    documented "drainer reads what sync just persisted" pattern.
    """

    value: str = ""


async def _refresh_access_token_cache(
    db_path: str, cache: _CachedAccessToken
) -> None:
    """Read the cached access token from oauth_state into the closure cell."""
    row = await fetchone(
        db_path, OAUTH_STATE_ACCESS_TOKEN_SELECT, ("microsoft_graph",)
    )
    if row is not None and row[0]:
        cache.value = str(row[0])


async def _worker_main(db_path: str) -> None:
    """Story 6-6 worker entry — wires all dormant background work.

    Construction order:
      0. (Story 6-11) Initialize per-process pipeline runtime — policy
         snapshot, sensitivity patterns, adapter registry, budget guard,
         pause state. Must precede `register_interval_task("ingest_pipeline",
         ...)` because the FR-2.5 per-call safeguard in
         `mailbot_api/sensitivity/classifier.py` reads `snapshot_for_dispatch()`
         on every ingest tick.
      1. Build sync state + heartbeat-producing iteration factory.
      2. Construct managed instances (CacheWarmer, AnomalyDetector).
      3. Construct OutlookGraphWriteAdapter from the sync token provider.
      4. Register all interval tasks on the scheduler.
      5. Register managed tasks on the scheduler.
      6. Launch the drainer as a separate asyncio task (continuous, not periodic).
      7. Start the scheduler + await shutdown signal.

    Shutdown: SIGTERM / SIGINT triggers a clean teardown via the shutdown
    event — scheduler stops all interval + managed tasks, drainer task is
    cancelled, the process exits.
    """
    # Story 6-11 (F17 closure): mirror the FastAPI lifespan + CLI init so the
    # worker process's `run_drain_loop` → `process_email` → `classify_sensitivity`
    # → `snapshot_for_dispatch()` chain finds a populated policy snapshot
    # rather than RuntimeError("policy not loaded"). The helper is idempotent
    # at the migration step (apply_pending_migrations is a no-op the second
    # call) and the snapshot setters overwrite per-process module globals.
    from mailbot_api.ingest.pipeline import init_pipeline_runtime
    await init_pipeline_runtime(db_path)
    logger.info(
        "worker pipeline runtime initialized",
        extra={"event": "worker.startup.pipeline_runtime_ready"},
    )

    sync_state = WorkerState()

    # Outlook write-back adapter + sync-callable token cache.
    # The adapter wants a SYNC token provider; we feed it a closure that
    # reads the `_CachedAccessToken` cell. A background refresher task
    # (registered on the scheduler below) polls oauth_state and updates the
    # cell so the provider sees the latest cached token at dispatch time.
    #
    # Tier-1 LOCAL_CATEGORY actions short-circuit inside the adapter's
    # `apply()` per Story 4-5's design — no Graph call, so the token is
    # irrelevant for them.
    token_cache = _CachedAccessToken()
    # Warm the cache once at boot — if no row exists yet (first deploy),
    # the cell stays empty and the adapter sees "" until sync persists
    # a token (then the next refresher tick updates the cell).
    await _refresh_access_token_cache(db_path, token_cache)
    outlook_adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: token_cache.value,
    )

    scheduler = Scheduler(db_path=db_path)

    # Interval tasks (scheduler-driven).
    scheduler.register_interval_task(
        "sync",
        SYNC_INTERVAL_SECONDS,
        _make_sync_iteration_factory(db_path, sync_state),
    )
    # AC: "ingest pipeline writes worker_health heartbeats per batch
    # (component='ingest_pipeline')".
    #
    # CR-2 (2026-06-03) note on AC drift: the AC text refers to Story 3-6's
    # `ingest_pipeline_interval_task`, which is itself a thin wrapper that
    # calls `run_drain_loop(max_batches=1)` in a `while not stop: ... sleep`
    # loop. We register `run_drain_loop` directly here because the
    # scheduler already owns the `while not stop: ... sleep` shape — going
    # through the wrapper would duplicate that. Functionally identical.
    scheduler.register_interval_task(
        "ingest_pipeline",
        INGEST_PIPELINE_INTERVAL_SECONDS,
        lambda: run_drain_loop(db_path=db_path, max_batches=1),
    )
    scheduler.register_interval_task(
        "cooling_off",
        COOLING_OFF_INTERVAL_SECONDS,
        lambda: cooling_off_tick(db_path),
    )
    # Story 6-3: notification outbox recovery — re-claims rows stuck in
    # `delivering` state for > 60s back to `pending` so Hermes can re-pull.
    # 10s cadence matches Hermes's expected poll cadence.
    from mailbot_api.notifications.outbox_recovery import reclaim_stuck_deliveries
    scheduler.register_interval_task(
        "notification_outbox_recovery",
        NOTIFICATION_RECOVERY_INTERVAL_SECONDS,
        lambda: reclaim_stuck_deliveries(db_path),
    )
    # CR-1 (2026-06-03) note: `oauth_token_refresh` is NOT in the canonical
    # AC text but IS load-bearing for the AC requirement "a Tier-3 send
    # proposal flows through cooling-off → drainer → adapter → applied".
    # OutlookGraphWriteAdapter takes a SYNC `Callable[[], str]` token
    # provider but `oauth.get_access_token` is async, so the adapter reads
    # from the `_CachedAccessToken` cell which this task keeps warm.
    # Without it, the cell would only have whatever was loaded at boot
    # (or the empty string for fresh deploys), and Tier-2/3 sends would
    # 401 after the first hourly token rotation.
    scheduler.register_interval_task(
        "oauth_token_refresh",
        SYNC_INTERVAL_SECONDS,  # aligned with sync; access tokens last ~1h
        lambda: _refresh_access_token_cache(db_path, token_cache),
    )

    # Managed tasks (self-lifecycle).
    cache_warmer = CacheWarmer(
        db_path, warm_interval_seconds=CACHE_WARMER_INTERVAL_SECONDS,
    )
    scheduler.register_managed_task("cache_warmer", cache_warmer)

    anomaly = AnomalyDetector(db_path, interval_seconds=ANOMALY_INTERVAL_SECONDS)
    scheduler.register_managed_task("anomaly", anomaly)

    # Drainer runs as its own continuous task (claim-and-drain semantics
    # are continuous, not periodic).
    drainer_shutdown = asyncio.Event()

    async def _drainer_with_heartbeat() -> None:
        # Wrap the drainer's tick so we get an `actions_drainer` heartbeat on
        # every iteration. The drainer's own `run_loop` is the inner driver
        # because it owns the per-tick exception handling + sleep interval.
        # Heartbeat-per-iteration: we drive it via a thin outer loop that
        # calls `run_loop` with `iterations=1`-ish semantics — but `run_loop`
        # doesn't support that, so instead we use the scheduler heartbeat-poll
        # pattern via the drainer_shutdown event.
        await drainer_run_loop(
            db_path,
            adapter=outlook_adapter,
            shutdown_event=drainer_shutdown,
        )

    async def _drainer_heartbeat_loop() -> None:
        # Poll the drainer's liveness and write `actions_drainer` heartbeats.
        # Mirrors the Scheduler._run_managed_heartbeat_loop pattern but is
        # inlined here because the drainer is owned by `_worker_main` (not
        # the scheduler) — it has different shutdown semantics.
        while not drainer_shutdown.is_set():
            outcome = "ok" if not drainer_task.done() else "failed"
            error = None if outcome == "ok" else "drainer_task_not_running"
            try:
                await upsert_worker_health(
                    db_path,
                    component="actions_drainer",
                    outcome=outcome,
                    error=error,
                )
            except Exception:  # noqa: BLE001 — last-ditch
                logger.exception("drainer heartbeat write failed")
            try:
                await asyncio.wait_for(drainer_shutdown.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass

    drainer_task = asyncio.create_task(
        _drainer_with_heartbeat(), name="worker.drainer"
    )
    heartbeat_task = asyncio.create_task(
        _drainer_heartbeat_loop(), name="worker.drainer_heartbeat"
    )

    # Start the scheduler.
    await scheduler.start()

    # Wire SIGTERM / SIGINT to a shutdown event.
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("worker shutdown signal", extra={"event": "worker.shutdown"})
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    # `loop.add_signal_handler` only works on Unix. On Windows the signals
    # are delivered as `KeyboardInterrupt` which propagates out of the await
    # naturally — no extra wiring needed.
    try:
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
    except (NotImplementedError, AttributeError):
        # Windows: no add_signal_handler — KeyboardInterrupt propagates.
        pass

    try:
        await shutdown_event.wait()
    finally:
        drainer_shutdown.set()
        # Stop the scheduler first so its tasks see the shutdown event.
        await scheduler.stop()
        # Cancel + await the drainer.
        drainer_task.cancel()
        heartbeat_task.cancel()
        for t in (drainer_task, heartbeat_task):
            try:
                await asyncio.wait_for(t, timeout=30.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


def main() -> None:
    """Entry point for `python -m mailbot_api.worker`."""
    configure_logging()
    try:
        db_path = get_secret("MAILBOT_DB_PATH")
    except SecretMissing as exc:
        logger.error(
            "worker startup failed — missing secret",
            extra={"event": "worker.startup.failed", "secret": exc.name},
        )
        raise

    # Apply any pending migrations before entering the loop. The FastAPI lifespan
    # also runs migrations on its side; the second call is a no-op (idempotent).
    apply_pending_migrations(db_path)

    asyncio.run(_worker_main(db_path))


if __name__ == "__main__":
    main()
