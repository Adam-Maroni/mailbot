"""Unit tests for mailbot_api/router/limits.py (Story 2-5)."""

from __future__ import annotations

import pytest

from mailbot_api.router.limits import (
    LIMIT_BATCH_PER_HOUR,
    LIMIT_ESCALATIONS_PER_HOUR,
    LIMIT_INTERACTIVE_PER_HOUR,
    LoopDetector,
    SlidingWindowRateLimiter,
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
    enforce_rate_limit,
    get_loop_detector,
)


@pytest.fixture(autouse=True)
def _clean_limiter() -> None:
    _reset_rate_limiter_for_test()
    yield
    _reset_rate_limiter_for_test()


def test_sliding_window_under_limit_passes() -> None:
    lim = SlidingWindowRateLimiter()
    for _ in range(10):
        assert lim.try_acquire("dim-a", 60) is True


def test_sliding_window_breach_at_limit_plus_one() -> None:
    lim = SlidingWindowRateLimiter()
    for _ in range(60):
        assert lim.try_acquire("dim-a", 60) is True
    assert lim.try_acquire("dim-a", 60) is False


def test_sliding_window_dimensions_isolated() -> None:
    lim = SlidingWindowRateLimiter()
    for _ in range(60):
        lim.try_acquire("dim-a", 60)
    # dim-b is independent.
    assert lim.try_acquire("dim-b", 60) is True


def test_enforce_rate_limit_interactive_allows_up_to_60() -> None:
    for _ in range(LIMIT_INTERACTIVE_PER_HOUR):
        assert enforce_rate_limit("interactive", "policy") is None
    assert enforce_rate_limit("interactive", "policy") == "lane:interactive"


def test_enforce_rate_limit_batch_allows_up_to_300() -> None:
    for _ in range(LIMIT_BATCH_PER_HOUR):
        assert enforce_rate_limit("batch", "policy") is None
    assert enforce_rate_limit("batch", "policy") == "lane:batch"


def test_enforce_rate_limit_escalations_capped_at_20() -> None:
    # Escalations dimension is checked AFTER the lane dimension, and the
    # lane has its own budget. Using batch (300/hr) keeps lane within budget
    # while the escalation reason exhausts the escalation dimension.
    for _ in range(LIMIT_ESCALATIONS_PER_HOUR):
        assert (
            enforce_rate_limit("batch", "policy:escalation:qwen2.5:3b-instruct-q4_K_M→claude-haiku-4-5-20251001")
            is None
        )
    assert (
        enforce_rate_limit("batch", "policy:escalation:qwen2.5:3b-instruct-q4_K_M→claude-haiku-4-5-20251001")
        == "escalations"
    )


def test_enforce_rate_limit_unknown_lane_skips_lane_check() -> None:
    # An unknown lane string passes through the lane gate.
    assert enforce_rate_limit("custom-lane", "policy") is None
    # ... and a force_model with a non-escalation reason also passes.
    assert enforce_rate_limit("custom-lane", "override") is None


# ---- Story 9.5.3 hotfix: benchmark-runner short-circuit ----


def test_enforce_rate_limit_benchmark_runner_short_circuits() -> None:
    """Story 9.5.3 walk-discovered defect: the benchmark runner dispatches
    100-200 cells in a single walk, but draft_reply is `lane: interactive`
    (60/hr). Without a carve-out, AC-5 walks are structurally impossible.

    Mirrors the `caller_origin='cache-warmer'` carve-out at limits.py:100 —
    benchmark-runner is a controlled, one-shot spend gate (Story 9-6 cost
    gate authorizes each run in advance), so the per-hour rate limit is
    orthogonal.
    """
    # Exhaust the interactive lane first with a normal caller.
    for _ in range(LIMIT_INTERACTIVE_PER_HOUR):
        enforce_rate_limit("interactive", "policy")
    # Normal caller now sees the breach.
    assert enforce_rate_limit("interactive", "policy") == "lane:interactive"
    # But a benchmark-runner-origin call passes through the lane gate.
    assert (
        enforce_rate_limit("interactive", "override:api:force_model", caller_origin="benchmark-runner")
        is None
    )


def test_enforce_rate_limit_benchmark_scorer_also_short_circuits() -> None:
    """Same carve-out extends to `benchmark-scorer` (Story 9-7 subjective
    auto-eval also dispatches 100+ cells against the anchor calibration
    prompt). Explicit allowlist entry (CR-F5 2026-07-03, was startswith
    prefix pre-patch)."""
    for _ in range(LIMIT_INTERACTIVE_PER_HOUR):
        enforce_rate_limit("interactive", "policy")
    assert (
        enforce_rate_limit("interactive", "override:api:force_model", caller_origin="benchmark-scorer")
        is None
    )


def test_enforce_rate_limit_unlisted_benchmark_prefix_does_not_bypass() -> None:
    """CR-F5 (2026-07-03): a caller_origin like ``benchmark-unauthorized`` or
    ``benchmark-experimental`` must NOT bypass the interactive lane cap.
    Only the explicit allowlist entries (``benchmark-runner``,
    ``benchmark-scorer``) short-circuit; the pre-patch ``startswith``
    check widened the trust surface to any future benchmark-*-prefixed
    caller without cost-gate coverage."""
    for _ in range(LIMIT_INTERACTIVE_PER_HOUR):
        enforce_rate_limit("interactive", "policy")
    # Unauthorized benchmark-* prefix sees the lane breach.
    assert (
        enforce_rate_limit(
            "interactive", "policy", caller_origin="benchmark-unauthorized"
        )
        == "lane:interactive"
    )


def test_enforce_rate_limit_escalation_with_breach_lane_returns_lane_first() -> None:
    """Order: lane check fires first; escalation check only reached if lane passes."""
    for _ in range(LIMIT_INTERACTIVE_PER_HOUR):
        enforce_rate_limit("interactive", "policy")
    # Now interactive is exhausted; an escalation still returns the lane breach,
    # not the escalation breach.
    assert (
        enforce_rate_limit("interactive", "policy:escalation:qwen2.5:3b-instruct-q4_K_M→claude-haiku-4-5-20251001")
        == "lane:interactive"
    )


# ---- Story 2-9 LoopDetector ----


@pytest.fixture(autouse=True)
def _clean_loop_detector() -> None:
    _reset_loop_detector_for_test()
    yield
    _reset_loop_detector_for_test()


def test_loop_detector_first_10_pass() -> None:
    det = LoopDetector()
    for _ in range(10):
        assert det.check_and_record("hash-a") is False


def test_loop_detector_11th_blocks() -> None:
    det = LoopDetector()
    for _ in range(10):
        det.check_and_record("hash-a")
    assert det.check_and_record("hash-a") is True


def test_loop_detector_isolated_per_hash() -> None:
    det = LoopDetector()
    for _ in range(10):
        det.check_and_record("hash-a")
    # Different hash is unaffected.
    assert det.check_and_record("hash-b") is False


def test_get_loop_detector_returns_singleton() -> None:
    assert get_loop_detector() is get_loop_detector()
