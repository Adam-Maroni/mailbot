"""Sliding-window rate limiter + lane policy per Story 2-5.

Rate-limit policy (FR-3.x):
  * interactive lane (chat-driven calls) → 60/hr
  * batch lane (ingest-driven calls) → 300/hr
  * escalations (any `policy:escalation:*` reason — Story 9.2 vocabulary) → 20/hr

Architecture §"D10": rate-limit decisions are at enqueue time and surface
``RouterError(code=RATE_LIMITED, retryable=True)`` — the call NEVER enters
the queue on breach. Logged with the dimension that tripped so dashboards
can correlate.

Story 2-9 will extend this module with the LoopDetector (per-prompt-hash
sliding window) and the pause-state flag.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

_log = logging.getLogger(__name__)


# Limits (per-hour) per dimension.
LIMIT_INTERACTIVE_PER_HOUR = 60
LIMIT_BATCH_PER_HOUR = 300
LIMIT_ESCALATIONS_PER_HOUR = 20

_WINDOW_SECONDS = 3600.0


class SlidingWindowRateLimiter:
    """Per-dimension sliding 60-minute window of timestamps.

    Thread-safe via an internal lock — the Router is single-event-loop but
    test helpers may exercise this from multiple threads, and the cost of a
    lock acquisition is negligible compared to a single async hop.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def try_acquire(self, dimension: str, limit_per_hour: int) -> bool:
        """Return ``True`` if the call is within the per-hour budget;
        ``False`` if it would breach. Successful acquires record the slot."""
        now = time.monotonic()
        cutoff = now - _WINDOW_SECONDS
        with self._lock:
            window = self._windows[dimension]
            # Evict expired entries.
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= limit_per_hour:
                return False
            window.append(now)
            return True

    def current_count(self, dimension: str) -> int:
        """Test-helper: how many slots are currently in the window."""
        now = time.monotonic()
        cutoff = now - _WINDOW_SECONDS
        with self._lock:
            window = self._windows[dimension]
            while window and window[0] < cutoff:
                window.popleft()
            return len(window)

    def _reset_for_test(self) -> None:
        with self._lock:
            self._windows.clear()


_RATE_LIMITER = SlidingWindowRateLimiter()


def enforce_rate_limit(
    lane: str,
    model_chosen_reason: str,
    caller_origin: str = "unknown-internal",
) -> str | None:
    """Return a dimension string on breach (caller surfaces it in the
    RouterError + log); ``None`` if the call is allowed.

    Two checks fire per call:
      1. lane-level (interactive=60/hr; batch=300/hr)
      2. escalation-level (20/hr) if reason starts with ``policy:escalation:`` (Story 9.2)

    Both checks must pass for the call to proceed. Breach of either fails
    fast. Order: lane first, then escalation (so a chat-tier-exhausted
    caller sees the lane breach before the escalation breach).

    Story 2-7: ``caller_origin="cache-warmer"`` short-circuits the gate
    entirely — warmer calls are zero-budget probes that keep Anthropic's
    cache warm and would otherwise eat into the regular rate-limit budget.

    Story 9.5.3 hotfix (2026-07-03): ``benchmark-runner`` (Story 9-6) and
    ``benchmark-scorer`` (Story 9-7) also short-circuit. Benchmark walks
    dispatch 100-200 cells in a single invocation which would otherwise
    blow the 60/hr interactive lane on tasks like ``draft_reply``; the
    Story 9-6 cost-gate provides per-walk spend authorization so the
    per-hour lane limit is orthogonal. CR-F5 (2026-07-03): explicit
    allowlist rather than ``startswith("benchmark-")`` to avoid widening
    the trust surface to any future caller that adopts a ``benchmark-*``
    prefix without cost-gate coverage.
    """
    if caller_origin in ("cache-warmer", "benchmark-runner", "benchmark-scorer"):
        return None

    if lane == "interactive":
        if not _RATE_LIMITER.try_acquire("lane:interactive", LIMIT_INTERACTIVE_PER_HOUR):
            _log.warning(
                "rate limit breached",
                extra={"event": "router.rate_limited", "dimension": "lane:interactive"},
            )
            return "lane:interactive"
    elif lane == "batch":
        if not _RATE_LIMITER.try_acquire("lane:batch", LIMIT_BATCH_PER_HOUR):
            _log.warning(
                "rate limit breached",
                extra={"event": "router.rate_limited", "dimension": "lane:batch"},
            )
            return "lane:batch"
    # Unknown lane string → no lane check (defensive — policy validation at
    # Story 2-2 enforces the closed set, but a future force_lane param might
    # bypass it).

    # Story 9.2: vocabulary migrated from "escalated_from_<X>" to
    # "policy:escalation:<from>→<to>". The escalation rate-limit gate keys
    # off the new prefix.
    if model_chosen_reason.startswith("policy:escalation:"):
        if not _RATE_LIMITER.try_acquire("escalations", LIMIT_ESCALATIONS_PER_HOUR):
            _log.warning(
                "rate limit breached",
                extra={"event": "router.rate_limited", "dimension": "escalations"},
            )
            return "escalations"

    return None


def _reset_rate_limiter_for_test() -> None:
    """Test-only helper — clear the limiter window state."""
    _RATE_LIMITER._reset_for_test()


_LOOP_WINDOW_SECONDS = 300.0
_LOOP_THRESHOLD_COUNT = 10


class LoopDetector:
    """Per-prompt-hash sliding window detector per Story 2-9.

    Maintains a rolling 5-minute window of seen prompt-hash timestamps.
    When a hash crosses 10 occurrences in the window, ``check_and_record``
    returns True for that hash until the window slides past the offenders.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check_and_record(self, prompt_hash: str) -> bool:
        """Returns True if the call should be BLOCKED (loop detected),
        False if it should proceed. The record happens whether or not the
        block fires — we want the count to reflect attempted dispatches."""
        now = time.monotonic()
        cutoff = now - _LOOP_WINDOW_SECONDS
        with self._lock:
            window = self._windows[prompt_hash]
            while window and window[0] < cutoff:
                window.popleft()
            window.append(now)
            blocked = len(window) > _LOOP_THRESHOLD_COUNT
            if blocked:
                _log.warning(
                    "loop detected",
                    extra={
                        "event": "router.loop_detected",
                        "prompt_hash_prefix": prompt_hash[:8],
                        "occurrences": len(window),
                    },
                )
            return blocked

    def _reset_for_test(self) -> None:
        with self._lock:
            self._windows.clear()


_LOOP_DETECTOR = LoopDetector()


def get_loop_detector() -> LoopDetector:
    return _LOOP_DETECTOR


def _reset_loop_detector_for_test() -> None:
    _LOOP_DETECTOR._reset_for_test()


__all__ = [
    "LIMIT_BATCH_PER_HOUR",
    "LIMIT_ESCALATIONS_PER_HOUR",
    "LIMIT_INTERACTIVE_PER_HOUR",
    "LoopDetector",
    "SlidingWindowRateLimiter",
    "enforce_rate_limit",
    "get_loop_detector",
]
