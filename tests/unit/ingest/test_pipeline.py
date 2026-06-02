"""Unit tests for `mailbot_api/ingest/pipeline.py`.

Created retroactively per Epic 4 retro action item #2 (Adam, 2026-06-02).
AC-8 of Story 3-5 listed `tests/unit/ingest/test_pipeline.py` as a required
deliverable; the original ship put all 7 tests at the integration tier in
`tests/integration/test_pipeline_e2e.py`. This file fills the gap with
unit-level checks against the pure-logic surfaces of the pipeline that do
NOT need an integration harness:

  - `ProcessEmailResult` field defaults + retryable propagation (CR-3-5-4 + CR-3-5-5)
  - `RunBatchResult` field defaults + `retryable_failed` counter (CR-3-5-5)
  - `_is_sensitivity_blocks_api` predicate over RouterResult shapes

Mocking out `ask_router` / `classify_sensitivity` / `embed_email` to exercise
`process_email` end-to-end at the unit tier was considered and rejected:
the project convention (see tests/unit/ingest/test_idempotency.py) is to
unit-test PURE FUNCTIONS and integration-test orchestration. The integration
suite already covers all 7 process_email branches against real adapters at
the boundary.
"""

from __future__ import annotations

from mailbot_api.ingest.pipeline import (
    ProcessEmailResult,
    RunBatchResult,
    _is_sensitivity_blocks_api,
)
from mailbot_api.router.errors import ErrorCode, RouterError, RouterResult

# --------------------------------------------------------------------------- #
# ProcessEmailResult — field defaults & retryable propagation
# --------------------------------------------------------------------------- #


def test_process_email_result_default_fields_are_independent_lists() -> None:
    """CR-3-5-4: `Field(default_factory=list)` produces a fresh list per instance.

    Pydantic v2 already handles this safely with the bare `= []` form, but
    the project convention uses `Field(default_factory=list)` explicitly.
    This test pins the invariant — if a future contributor copies the pattern
    into a non-Pydantic dataclass, the shared-mutable-default bug would
    silently appear; here we prove it does NOT for the Pydantic model.
    """
    a = ProcessEmailResult(ok=True, email_id="a")
    b = ProcessEmailResult(ok=True, email_id="b")
    a.steps_run.append("sensitivity_class")
    a.steps_blocked_by_sensitivity.append("summary_short")
    a.steps_inapplicable.append("fine_class")
    a.steps_skipped.append("embedding")
    # b's lists must be untouched.
    assert b.steps_run == []
    assert b.steps_blocked_by_sensitivity == []
    assert b.steps_inapplicable == []
    assert b.steps_skipped == []


def test_process_email_result_retryable_defaults_to_false() -> None:
    """CR-3-5-5: `retryable` is False by default (failures are terminal unless flagged)."""
    r = ProcessEmailResult(ok=False, email_id="x")
    assert r.retryable is False


def test_process_email_result_carries_retryable_signal() -> None:
    """CR-3-5-5: an explicit `retryable=True` survives model construction."""
    r = ProcessEmailResult(
        ok=False,
        email_id="x",
        failed_at="summary_short",
        retryable=True,
        error=RouterError(code=ErrorCode.RATE_LIMITED, message="hit", retryable=True),
    )
    assert r.retryable is True
    assert r.error is not None
    assert r.error.retryable is True


def test_process_email_result_partial_due_to_sensitivity_default_false() -> None:
    r = ProcessEmailResult(ok=True, email_id="x")
    assert r.partial_due_to_sensitivity is False


# --------------------------------------------------------------------------- #
# RunBatchResult — retryable_failed counter
# --------------------------------------------------------------------------- #


def test_run_batch_result_default_retryable_failed_zero() -> None:
    """CR-3-5-5: `retryable_failed` defaults to 0 so older callers stay compatible."""
    r = RunBatchResult(
        processed=10, succeeded=8, failed=2, partial_due_to_sensitivity=1
    )
    assert r.retryable_failed == 0


def test_run_batch_result_retryable_failed_carries_through() -> None:
    r = RunBatchResult(
        processed=10,
        succeeded=7,
        failed=3,
        partial_due_to_sensitivity=1,
        retryable_failed=2,
        errors=["a: summary_short (rate_limited)", "b: summary_short (rate_limited)"],
    )
    assert r.retryable_failed == 2
    assert r.failed == 3  # 2 retryable + 1 permanent


def test_run_batch_result_list_defaults_are_independent() -> None:
    """CR-3-5-4: same invariant as ProcessEmailResult for the batch type."""
    a = RunBatchResult(processed=1, succeeded=1, failed=0, partial_due_to_sensitivity=0)
    b = RunBatchResult(processed=1, succeeded=1, failed=0, partial_due_to_sensitivity=0)
    a.errors.append("a-error")
    a.email_ids.append("a-1")
    assert b.errors == []
    assert b.email_ids == []


# --------------------------------------------------------------------------- #
# _is_sensitivity_blocks_api predicate
# --------------------------------------------------------------------------- #


def test_is_sensitivity_blocks_api_true_on_blocking_error() -> None:
    rr = RouterResult(
        ok=False,
        model_used="",
        error=RouterError(
            code=ErrorCode.SENSITIVITY_BLOCKS_API,
            message="sensitive — API blocked",
            retryable=False,
        ),
    )
    assert _is_sensitivity_blocks_api(rr) is True


def test_is_sensitivity_blocks_api_false_on_other_errors() -> None:
    """Only the SENSITIVITY_BLOCKS_API code triggers the graceful-skip branch.

    The pipeline must abort on every other error code (including the
    superficially similar SENSITIVITY_NOT_CLASSIFIED — that one means the
    precondition layer is upstream of where it should be, never a graceful skip).
    """
    other_codes = [
        ErrorCode.SENSITIVITY_NOT_CLASSIFIED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.TIMEOUT,
        ErrorCode.SCHEMA_VALIDATION_FAILED,
        ErrorCode.PROVIDER_ERROR,
    ]
    for code in other_codes:
        rr = RouterResult(
            ok=False,
            model_used="",
            error=RouterError(code=code, message="x", retryable=False),
        )
        assert _is_sensitivity_blocks_api(rr) is False, f"misfired on {code}"


def test_is_sensitivity_blocks_api_false_on_success() -> None:
    rr = RouterResult(
        ok=True,
        model_used="qwen2.5:3b-instruct-q4_K_M",
        output=None,
        error=None,
    )
    assert _is_sensitivity_blocks_api(rr) is False


def test_router_result_invariant_ok_false_requires_error() -> None:
    """Pydantic validator on RouterResult guarantees `_is_sensitivity_blocks_api`
    never receives an `ok=False, error=None` shape — the predicate's defensive
    `error is None` branch is unreachable by construction. Pinned here so a
    future relaxation of the validator surfaces the predicate gap.
    """
    import pytest

    with pytest.raises(Exception):  # noqa: B017 — Pydantic raises ValidationError
        RouterResult(ok=False, model_used="", error=None)
