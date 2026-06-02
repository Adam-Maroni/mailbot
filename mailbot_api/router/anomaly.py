"""Hourly call-volume anomaly detection per Story 2-9.

Each tick (default hourly):
  1. Aggregate by caller_origin over the last hour (via queries.CALL_VOLUME_LAST_HOUR_BY_ORIGIN).
  2. Compare each origin's count vs its rolling 7-day per-hour baseline
     (mean_volume + 3*stddev_volume).
  3. Above threshold → log + (future) send_urgent notification.
  4. Upsert the baseline with this hour's count (rolling sample).

Baseline update uses Welford-ish online stats: each row tracks
(mean, stddev, sample_count); a new sample updates them in-place.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from mailbot_api.db import connection, queries

_log = logging.getLogger(__name__)


# Z-threshold for the alert. Architecture spec: baseline_mean + 3*stddev.
ANOMALY_Z_THRESHOLD = 3.0
# How many samples before the baseline is considered "warmed up" (and
# alerts can fire). Below this we collect data without alerting.
_BASELINE_WARMUP_SAMPLES = 24  # one day of hourly observations


def _format_z(now: datetime) -> str:
    """UTC ISO-8601 with `Z` suffix, microsecond precision.

    Microsecond-precision since 2026-06-02 (Epic 4 retro action item #3) —
    matches the shape produced by :func:`mailbot_api.observability.timestamps.utc_z_now`.
    """
    return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _online_update(
    *, old_mean: float, old_stddev: float, old_n: int, new_value: float
) -> tuple[float, float, int]:
    """Update (mean, stddev, n) with a new sample via Welford's online algorithm."""
    n = old_n + 1
    delta = new_value - old_mean
    new_mean = old_mean + delta / n
    delta2 = new_value - new_mean
    if old_n == 0:
        new_var = 0.0
    else:
        old_var = old_stddev * old_stddev
        new_var = (old_var * (old_n - 1) + delta * delta2) / max(n - 1, 1)
    new_stddev = math.sqrt(max(new_var, 0.0))
    return new_mean, new_stddev, n


async def run_anomaly_check(db_path: str, *, now: datetime | None = None) -> list[str]:
    """Run one anomaly-detection pass against router_calls.

    Returns the list of caller_origin strings that tripped the alert (empty
    list on no anomalies). For Story 2-9 this returns the list for tests +
    a future Story 6.x to wire into notifications.send_urgent.
    """
    now = now or datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    one_hour_ago_iso = _format_z(one_hour_ago)
    hour_of_day = now.hour

    rows = await connection.fetchall(
        db_path,
        queries.CALL_VOLUME_LAST_HOUR_BY_ORIGIN,
        (one_hour_ago_iso,),
    )
    anomalies: list[str] = []
    for caller_origin, count in rows:
        if not caller_origin:
            continue
        observed = int(count)
        baseline_row = await connection.fetchone(
            db_path,
            queries.CALL_VOLUME_BASELINE_SELECT,
            (caller_origin, hour_of_day),
        )
        if baseline_row is None:
            mean = 0.0
            stddev = 0.0
            sample_n = 0
        else:
            mean, stddev, sample_n = baseline_row

        threshold = mean + ANOMALY_Z_THRESHOLD * stddev

        # Alert only after baseline is warmed up.
        if sample_n >= _BASELINE_WARMUP_SAMPLES and observed > threshold:
            anomalies.append(caller_origin)
            _log.error(
                "call volume anomaly",
                extra={
                    "event": "router.anomaly.detected",
                    "caller_origin": caller_origin,
                    "observed": observed,
                    "baseline_mean": mean,
                    "baseline_stddev": stddev,
                    "threshold": threshold,
                },
            )

        # Update baseline with this hour's observation.
        new_mean, new_stddev, new_n = _online_update(
            old_mean=mean,
            old_stddev=stddev,
            old_n=sample_n,
            new_value=float(observed),
        )
        await connection.execute_write(
            db_path,
            queries.CALL_VOLUME_BASELINE_UPSERT,
            (
                caller_origin,
                hour_of_day,
                new_mean,
                new_stddev,
                new_n,
                _format_z(now),
            ),
        )

    return anomalies


class AnomalyDetector:
    """Lifecycle wrapper for the hourly anomaly-check interval task."""

    def __init__(self, db_path: str, *, interval_seconds: float = 3600.0) -> None:
        self.db_path = db_path
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await run_anomaly_check(self.db_path)
            except Exception as exc:  # noqa: BLE001 — defensive
                _log.info(
                    "anomaly check pass failed",
                    extra={
                        "event": "router.anomaly.pass_failed",
                        "exc_type": type(exc).__name__,
                    },
                )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def stop(self, *, timeout: float = 5.0) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None


__all__ = ["AnomalyDetector", "run_anomaly_check"]
