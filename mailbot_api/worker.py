"""Background worker process for mailbot-api container.

Per AR-D7-1: this is the second process inside `mailbot-api`. Started by
`docker/entrypoint.sh` via `python -m mailbot_api.worker` and backgrounded.
The entrypoint's `wait -n` causes the container to exit if this process dies,
which docker-compose's `restart: unless-stopped` then recovers.

Story 1-8: continuous sync loop every 4 minutes (FR-1.1) + worker_health
heartbeat upsert + sync-health alarm at the >1h staleness threshold.
Future stories add the ingest pipeline (Epic 3), pending_actions drainer
(Epic 4), and cache warmer (Epic 2) as additional concurrent tasks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from mailbot_api.config import SecretMissing, get_secret
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import WORKER_HEALTH_SELECT, WORKER_HEALTH_UPSERT
from mailbot_api.notifications import send_urgent
from mailbot_api.observability.logging import configure_logging
from mailbot_api.observability.timestamps import utc_z_now
from mailbot_api.sync.sync_worker import SyncResult, run_once

logger = logging.getLogger(__name__)

# Per FR-1.1: sync every 4 minutes (aligned to Anthropic 5-min cache TTL).
SYNC_INTERVAL_SECONDS = 240

# Stale threshold per FR-1.5: alarm fires after 60 min without an `ok` heartbeat.
STALE_THRESHOLD_MINUTES = 60


def _utc_iso8601() -> str:
    return utc_z_now()


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
    """Write (component, now, outcome, error) into worker_health (single-row-per-component)."""
    await execute_write(
        db_path,
        WORKER_HEALTH_UPSERT,
        (component, _utc_iso8601(), outcome, error),
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
        send_urgent(
            f"sync stale > {STALE_THRESHOLD_MINUTES} min "
            f"(elapsed={elapsed_minutes:.1f}m, last_outcome={last_outcome})"
        )
        state.alarm_fired_for_episode = True


async def sync_loop(
    db_path: str,
    *,
    interval_seconds: int = SYNC_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    iterations: int | None = None,
) -> None:
    """The worker's main sync loop. Iterates forever in production; tests pass
    `iterations` to bound the loop and `sleep` to swap asyncio.sleep for a fake
    that advances synthetic time.

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

    asyncio.run(sync_loop(db_path))


if __name__ == "__main__":
    main()
