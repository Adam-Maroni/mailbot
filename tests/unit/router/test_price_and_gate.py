"""Unit tests for the price_and_gate seam (Story 11.6.1, re-scoped).

Tests the consolidated per-call cost gate IN ISOLATION across its branches —
the testability win the extraction exists for. Two asymmetries are pinned
explicitly because a naive extraction could silently normalize them:
  * force bypass applies ONLY when force_capable=True (ask_router); a
    force_capable=False caller (dispatch_tool_call) refuses unconditionally.
  * the refusal message carries the "pass force=True" suffix ONLY for
    force-capable callers.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from mailbot_api.router.budget import PER_CALL_REFUSAL_THRESHOLD_USD
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.gate import GateOutcome, price_and_gate

_LOGGER_NAME = "mailbot_api.router.gate"
_REFUSAL_EVENT = "budget.per_call.refused"
_OPUS = "claude-opus-4-7"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


def _refusal_records(caplog: pytest.LogCaptureFixture) -> list[Any]:
    return [r for r in caplog.records if getattr(r, "event", None) == _REFUSAL_EVENT]


def test_clean_pass_under_threshold_no_log(caplog: pytest.LogCaptureFixture) -> None:
    """Cheap local model, tiny token count → proceed, no log, error is None."""
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        out = price_and_gate(
            model=_QWEN,
            estimated_tokens_in=10,
            max_tokens_out=64,
            email_id=None,
            force_capable=True,
        )
    assert isinstance(out, GateOutcome)
    assert out.refused is False
    assert out.error is None
    assert out.estimated_cost >= 0.0
    assert _refusal_records(caplog) == []


def test_over_threshold_refuses_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Opus + huge output cap → over threshold → refuse + budget.per_call.refused."""
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        out = price_and_gate(
            model=_OPUS,
            estimated_tokens_in=1000,
            max_tokens_out=100_000,
            email_id="abc",
            force_capable=True,
        )
    assert out.refused is True
    assert out.error is not None
    assert out.error.code == ErrorCode.PER_CALL_THRESHOLD_EXCEEDED
    assert out.estimated_cost > PER_CALL_REFUSAL_THRESHOLD_USD
    recs = _refusal_records(caplog)
    assert len(recs) == 1
    assert getattr(recs[0], "model", None) == _OPUS
    assert getattr(recs[0], "email_id", None) == "abc"


def test_force_bypass_only_when_force_capable(caplog: pytest.LogCaptureFixture) -> None:
    """force=True + force_capable=True → bypass: proceed, no refuse, no log."""
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        out = price_and_gate(
            model=_OPUS,
            estimated_tokens_in=1000,
            max_tokens_out=100_000,
            email_id=None,
            force=True,
            force_capable=True,
        )
    assert out.refused is False
    assert out.error is None
    assert out.estimated_cost > PER_CALL_REFUSAL_THRESHOLD_USD  # would've refused
    assert _refusal_records(caplog) == []


def test_force_ignored_when_not_force_capable() -> None:
    """force=True but force_capable=False (dispatch_tool_call shape) → force is
    ignored, still refuses. Guards against normalizing the asymmetry away."""
    out = price_and_gate(
        model=_OPUS,
        estimated_tokens_in=1000,
        max_tokens_out=100_000,
        email_id=None,
        force=True,  # should have NO effect
        force_capable=False,
    )
    assert out.refused is True
    assert out.error is not None


def test_refusal_message_suffix_differs_by_force_capability() -> None:
    """force-capable → message ends with the override hint; non-capable → bare.
    Pins the exact byte-for-byte messages the two callsites emitted pre-extraction."""
    capable = price_and_gate(
        model=_OPUS, estimated_tokens_in=1000, max_tokens_out=100_000,
        email_id=None, force_capable=True,
    )
    bare = price_and_gate(
        model=_OPUS, estimated_tokens_in=1000, max_tokens_out=100_000,
        email_id=None, force_capable=False,
    )
    assert capable.error is not None and bare.error is not None
    assert capable.error.message.endswith("; pass force=True to override")
    assert not bare.error.message.endswith("; pass force=True to override")
    # Both share the same cost/threshold prefix.
    assert bare.error.message.startswith("estimated cost $")
    assert "per-call threshold $" in bare.error.message


def test_exactly_at_threshold_passes() -> None:
    """Boundary: cost EXACTLY == threshold must PROCEED, because the gate is a
    strict `>`. This genuinely pins `>` vs `>=`: opus with tokens_in=0,
    max_tokens_out=8000 prices to exactly $0.20 (== PER_CALL_REFUSAL_THRESHOLD_USD).
    A regression to `>=` would refuse here and flip this test red."""
    out = price_and_gate(
        model=_OPUS,
        estimated_tokens_in=0,
        max_tokens_out=8000,
        email_id=None,
        force_capable=False,
    )
    # Sanity: this input really does land ON the threshold, not merely under it.
    assert out.estimated_cost == pytest.approx(PER_CALL_REFUSAL_THRESHOLD_USD, abs=1e-9)
    # Strict `>` ⇒ cost == threshold is NOT over ⇒ proceed.
    assert out.refused is False
    assert out.error is None


def test_one_epsilon_over_threshold_refuses() -> None:
    """Boundary companion: one step OVER the threshold (max_tokens_out 8000→8001)
    must REFUSE — proves the at-threshold pass above isn't just 'never refuses'."""
    out = price_and_gate(
        model=_OPUS,
        estimated_tokens_in=0,
        max_tokens_out=8001,
        email_id=None,
        force_capable=False,
    )
    assert out.estimated_cost > PER_CALL_REFUSAL_THRESHOLD_USD
    assert out.refused is True
