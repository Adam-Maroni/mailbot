"""Story 9-3 AC-3 + AC-5 — budget + degraded-mode gate inheritance.

The one-shot override MUST NOT punch through:
  - $0.20 per-call cost refusal (one-shot does NOT carry implicit force=True)
  - Degraded-mode opus-block (DEGRADED_MODE_BLOCKED)

On either gate refusal, the override REMAINS ARMED within its TTL —
Adam re-issues without re-typing `/model`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.budget import _reset_guard_for_test, get_guard
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.verbs.router_control import (
    _get_active_oneshot_override,
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
)

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


# Two policy variants: budget-gate test uses a HIGH max_tokens_out so the
# $0.20 threshold trips; degraded-mode test uses a cheaper budget.
_POLICY_HIGH_COST = f"""\
version: "test-budget-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1000000  # absurdly high — guarantees estimated cost > $0.20
    lane: "interactive"
    sensitivity: "any"
"""

_POLICY_NORMAL = f"""\
version: "test-degraded-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state() -> Any:
    _clear_registry_for_tests()
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    yield
    _clear_registry_for_tests()
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()


def _setup_with_policy(tmp_path: Path, policy_yaml: str) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(policy_yaml, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_path))
    return db_path


def _draft_content() -> dict[str, Any]:
    return {
        "source_email": "From: x@y.com\nSubject: test\nBody: preview",
        "thread_context": "(empty)",
        "tone_signals": "(none)",
    }


def _good_draft_response() -> AdapterResponse:
    return AdapterResponse(
        text=json.dumps(
            {
                "draft_body": "ok",
                "suggested_subject": "re: test",
                "tone_signals_used": [],
                "defender_warnings": [],
            }
        ),
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=12,
        raw={"mock": True},
    )


# ---------------------------------------------------------------------------
# AC-3 — $0.20 per-call budget gate
# ---------------------------------------------------------------------------


async def test_oneshot_override_refused_by_budget_gate_remains_armed(
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """AC-3: when the override targets a model whose estimated cost exceeds
    $0.20 (and `force=True` was NOT explicitly passed), the call is refused
    with PER_CALL_THRESHOLD_EXCEEDED. The override REMAINS ARMED."""
    db_path = _setup_with_policy(tmp_path, _POLICY_HIGH_COST)

    # Register adapters but they should NEVER be called — budget gate fires first.
    from tests._helpers.fake_adapter import FakeAdapter

    register_adapter(_HAIKU, FakeAdapter([], model_id=_HAIKU))
    register_adapter(_OPUS, FakeAdapter([], model_id=_OPUS))

    _set_oneshot_override(model=_OPUS, ttl_seconds=300, session_id="test")
    assert _get_active_oneshot_override() is not None

    result = await ask_router("draft_reply", _draft_content(), db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PER_CALL_THRESHOLD_EXCEEDED, (
        f"expected PER_CALL_THRESHOLD_EXCEEDED; got {result.error.code}"
    )

    # AC-3 invariant: override remains armed.
    active = _get_active_oneshot_override()
    assert active is not None, (
        "Override must remain armed when budget gate refuses (consume-on-actual-use)."
    )
    assert active.model == _OPUS


# ---------------------------------------------------------------------------
# AC-3 — Degraded-mode opus-block
# ---------------------------------------------------------------------------


async def test_oneshot_override_to_opus_in_degraded_mode_blocked_remains_armed(
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """AC-3: when degraded mode is active AND the override targets opus,
    the existing DEGRADED_MODE_BLOCKED refusal fires UNCHANGED. The
    override REMAINS ARMED — Adam re-issues after `/budget reset` or
    after the degraded mode clears."""
    db_path = _setup_with_policy(tmp_path, _POLICY_NORMAL)

    # Enter degraded mode (use the private helper directly; test-only escape)
    guard = get_guard()
    await guard.initialize(db_path)
    await guard._enter_degraded_mode(db_path)
    assert guard.is_degraded() is True

    from tests._helpers.fake_adapter import FakeAdapter

    register_adapter(_OPUS, FakeAdapter([], model_id=_OPUS))

    _set_oneshot_override(model=_OPUS, ttl_seconds=300, session_id="test")

    result = await ask_router("draft_reply", _draft_content(), db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.DEGRADED_MODE_BLOCKED, (
        f"expected DEGRADED_MODE_BLOCKED; got {result.error.code}"
    )

    # AC-3 invariant: override remains armed.
    active = _get_active_oneshot_override()
    assert active is not None, (
        "Override must remain armed when degraded-mode-opus gate refuses."
    )
    assert active.model == _OPUS
