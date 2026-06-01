"""Backpressure-aware bulk drain orchestrator per Story 3-6.

Wraps the per-email `pipeline.run_batch` with:
  * `count_unprocessed` / `should_throttle` queue depth probes.
  * `run_drain_loop` — iterative batch driver with throttle-on-deep-queue.
  * `ingest_pipeline_interval_task` — Epic-6 scheduler stub.

The drain order is `received_at DESC` — newest emails first so a user
actively syncing sees the most-recent state derived first.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from pydantic import BaseModel

from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import EMAIL_UNPROCESSED_COUNT_SELECT

logger = logging.getLogger(__name__)

BATCH_SIZE: Final[int] = 100
BACKPRESSURE_THRESHOLD: Final[int] = 500
BACKPRESSURE_SLEEP_SECONDS: Final[float] = 5.0


class DrainLoopResult(BaseModel):
    """Aggregate result of `run_drain_loop`."""

    batches_run: int
    total_processed: int
    total_succeeded: int
    total_failed: int
    total_partial_sensitive: int
    throttle_events: int


async def count_unprocessed(db_path: str) -> int:
    """Return the number of unprocessed emails (sensitivity_at IS NULL, not deleted)."""
    row = await fetchone(db_path, EMAIL_UNPROCESSED_COUNT_SELECT, ())
    if row is None:
        return 0
    return int(row[0])


async def should_throttle(db_path: str, *, threshold: int = BACKPRESSURE_THRESHOLD) -> bool:
    """Return True if the unprocessed-queue depth exceeds `threshold`."""
    return await count_unprocessed(db_path) > threshold


async def run_drain_loop(
    *,
    db_path: str,
    caller_origin: str = "ingest-pipeline-batch",
    max_batches: int | None = None,
) -> DrainLoopResult:
    """Drain the unprocessed-emails queue in BATCH_SIZE chunks with backpressure.

    Stops when:
      * `count_unprocessed == 0` (queue drained), OR
      * `max_batches` is reached (test bound).

    Backpressure: after each batch, if `count_unprocessed > BACKPRESSURE_THRESHOLD`,
    sleeps `BACKPRESSURE_SLEEP_SECONDS` before the next batch to keep the
    interactive lane responsive (the per-call rate limits will throttle Anthropic-
    bound steps anyway, but a sleep at the loop level also relieves SQLite contention).

    The function is errors-as-data via individual `process_email` calls — a single
    email failure doesn't abort the loop.
    """
    # Lazy import to avoid a circular import at module load (pipeline imports
    # nothing from backpressure, but the test_pipeline_e2e suite imports from both).
    from mailbot_api.ingest.pipeline import run_batch

    batches_run = 0
    total_processed = 0
    total_succeeded = 0
    total_failed = 0
    total_partial_sensitive = 0
    throttle_events = 0

    while True:
        if max_batches is not None and batches_run >= max_batches:
            break

        # Quick exit if the queue is already empty.
        depth_before = await count_unprocessed(db_path)
        if depth_before == 0:
            break

        result = await run_batch(db_path=db_path, caller_origin=caller_origin)
        batches_run += 1
        total_processed += result.processed
        total_succeeded += result.succeeded
        total_failed += result.failed
        total_partial_sensitive += result.partial_due_to_sensitivity

        # Edge case: if the batch processed 0 emails but the depth was > 0,
        # we'd loop forever. The depth check above + this defensive break
        # together avoid that. (Real-world cause: every row failing the
        # sensitivity step, repeatedly — exit the loop, let the next tick
        # decide whether to retry.)
        if result.processed == 0:
            break

        # Backpressure check after the batch.
        if await should_throttle(db_path):
            throttle_events += 1
            logger.info(
                "ingest drain backpressure",
                extra={
                    "event": "ingest.drain.throttle",
                    "queue_depth": await count_unprocessed(db_path),
                    "threshold": BACKPRESSURE_THRESHOLD,
                    "sleep_seconds": BACKPRESSURE_SLEEP_SECONDS,
                },
            )
            await asyncio.sleep(BACKPRESSURE_SLEEP_SECONDS)

    return DrainLoopResult(
        batches_run=batches_run,
        total_processed=total_processed,
        total_succeeded=total_succeeded,
        total_failed=total_failed,
        total_partial_sensitive=total_partial_sensitive,
        throttle_events=throttle_events,
    )


async def ingest_pipeline_interval_task(
    *,
    db_path: str,
    interval_seconds: float = 300.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Stub scheduler task — runs one drain batch per `interval_seconds`.

    Epic 6 will own the full scheduler. This stub lets tests exercise the
    "interval-driven drain" path and lets a future story integrate it into
    `main.py`'s lifespan.

    Each tick runs `run_drain_loop(max_batches=1)` so a single tick doesn't
    block for an hour under heavy load — the queue keeps draining across ticks.
    """
    stop = stop_event if stop_event is not None else asyncio.Event()
    while not stop.is_set():
        try:
            await run_drain_loop(db_path=db_path, max_batches=1)
        except Exception as exc:  # noqa: BLE001 — defensive; never crash the scheduler
            logger.warning(
                "ingest interval tick failed",
                extra={"event": "ingest.interval.tick_failed", "exc": str(exc)},
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            # Normal tick boundary — continue.
            pass


__all__ = [
    "BACKPRESSURE_SLEEP_SECONDS",
    "BACKPRESSURE_THRESHOLD",
    "BATCH_SIZE",
    "DrainLoopResult",
    "count_unprocessed",
    "ingest_pipeline_interval_task",
    "run_drain_loop",
    "should_throttle",
]
