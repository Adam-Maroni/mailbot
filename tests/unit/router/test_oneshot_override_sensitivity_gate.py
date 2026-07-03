"""Story 9-3 AC-3 + AC-5 — sensitivity gate inheritance test matrix.

The one-shot override MUST NOT punch through the existing
sensitivity-token precondition layer (Story 4-7). For each combination of
(task_type, sensitivity_level, token-presence), the test verifies:

  - When the gate fires (sensitive-without-token + API model; confidential
    always), `ask_router` returns `SENSITIVITY_BLOCKS_API`.
  - The audit row carries `model_chosen_reason=SENSITIVITY_GATE_REFUSED`
    rather than `OVERRIDE_SLASH_ONE_SHOT` — the override never took
    effect because the gate fired first.
  - The override REMAINS ARMED within its TTL (consume-on-actual-use:
    gate refusal ≠ actual use).
  - Normal-sensitivity calls dispatch successfully with `OVERRIDE_SLASH_ONE_SHOT`.

Refuses to consume on gate refusal is the load-bearing invariant —
without it, a `/model opus` accidentally typed against a sensitive
thread silently expires Adam's intent without giving him a chance to
re-issue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import (
    _clear_registry_for_tests,
)
from mailbot_api.actions.sensitivity_tokens import (
    mint as _mint_token,
)
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.budget import _reset_guard_for_test
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


# Policy: 4 task_types use Haiku (Anthropic, API-bound) so the
# sensitivity gate fires when the override targets an API model.
_POLICY_YAML = f"""\
version: "test-oneshot-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "any"
  importance_scoring:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  action_extraction:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "batch"
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


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


async def _seed_email(db_path: str, *, graph_id: str, sensitivity: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id,
            "2026-06-15T00:00:00Z",
            "test subject",
            "x@y.com",
            "body preview",
            sensitivity,
            "2026-06-15T00:01:00Z",
            "v1",
            0.9,
            _QWEN,
        ),
    )


def _content_for_task(task_type: str) -> dict[str, Any]:
    """Provide enough fields to satisfy each task's prompt template.

    The exact prompt-template variable names are an implementation detail
    of `mailbot_api.prompts.<task>.v1.render(...)`. We over-provision a
    generic dict that covers all 4 task surfaces. Missing keys surface as
    `KeyError` at render time → `prompt_render_failed` RouterError.
    """
    base = {
        "subject": "test",
        "sender": "x@y.com",
        "body_preview": "preview",
        "body": "body content",
        "thread_excerpt": "prior",
        "user_intent": "concise reply",
        # draft_reply needs source_email + thread_context + tone_signals
        "source_email": "From: x@y.com\nSubject: test\nBody: preview",
        "thread_context": "(empty thread)",
        "tone_signals": "(none)",
        # importance_scoring + summary_short + action_extraction passthrough
        "summary": "preview",
    }
    return base


_VALID_RESPONSE_PER_TASK: dict[str, str] = {
    "draft_reply": json.dumps(
        {
            "draft_body": "ok",
            "suggested_subject": "re: test",
            "tone_signals_used": [],
            "defender_warnings": [],
        }
    ),
    "summary_short": json.dumps({"summary": "ok"}),
    "importance_scoring": json.dumps({"importance": 50, "signals": []}),
    "action_extraction": json.dumps({"actions": []}),
}


def _good_response_for_task(task_type: str) -> AdapterResponse:
    return AdapterResponse(
        text=_VALID_RESPONSE_PER_TASK[task_type],
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=12,
        raw={"mock": True},
    )


# ---------------------------------------------------------------------------
# Parametrized matrix — 4 tasks × 3 sensitivities × {with-token, without}
# = 24 cases. Each verifies gate behavior + override-armed state.
# ---------------------------------------------------------------------------


_API_BOUND_TASKS = ["draft_reply", "summary_short", "importance_scoring", "action_extraction"]
_SENSITIVITIES = ["normal", "sensitive", "confidential"]
_TOKEN_PRESENCE = [True, False]  # True = mint + pass token, False = no token


def _expected_gate_verdict(sensitivity: str, with_token: bool) -> str:
    """Return one of: 'allowed' | 'sensitivity_blocks_api' | 'needs_sensitivity_confirmation'."""
    if sensitivity == "normal":
        return "allowed"
    if sensitivity == "confidential":
        # NFR-PRIV-2: confidential is unconditionally refused on API models.
        return "sensitivity_blocks_api"
    # sensitive:
    if with_token:
        return "allowed"
    return "sensitivity_blocks_api"


@pytest.mark.parametrize("task_type", _API_BOUND_TASKS)
@pytest.mark.parametrize("sensitivity", _SENSITIVITIES)
@pytest.mark.parametrize("with_token", _TOKEN_PRESENCE)
async def test_oneshot_override_inherits_sensitivity_gate(
    task_type: str,
    sensitivity: str,
    with_token: bool,
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """AC-3 + AC-5: the one-shot override does NOT punch through the
    sensitivity gate. For every (task, sensitivity, token) tuple, the
    refusal verdict matches the pre-9.3 behavior — the override changes
    nothing about gate enforcement.

    AC-3 sub-invariant: gate refusal does NOT consume the override.
    Adam re-issues a non-sensitive call; the override remains armed.
    """
    db_path = _setup(tmp_path)

    # Register a Haiku adapter so the "allowed" cases dispatch cleanly.
    # CR-F6: import from shared helper, not the cross-module private symbol.
    from tests._helpers.fake_adapter import FakeAdapter

    register_adapter(
        _HAIKU,
        FakeAdapter([_good_response_for_task(task_type)], model_id=_HAIKU),
    )
    # Also register Opus (the override target) so allowed paths dispatch.
    register_adapter(
        _OPUS,
        FakeAdapter([_good_response_for_task(task_type)], model_id=_OPUS),
    )

    # Seed the email row with the parametrized sensitivity.
    email_id = f"email-{task_type}-{sensitivity}"
    await _seed_email(db_path, graph_id=email_id, sensitivity=sensitivity)

    # Arm the override targeting OPUS (an API-bound model — the gate's scope).
    _set_oneshot_override(
        model=_OPUS, ttl_seconds=300, session_id="test-session"
    )
    # Sanity: override is armed before the call.
    assert _get_active_oneshot_override() is not None

    # Optionally mint a token (only meaningful for sensitive+with_token).
    confirmation_token: str | None = None
    if with_token and sensitivity == "sensitive":
        token = _mint_token(email_id, task_type)
        confirmation_token = token.token_value

    # Issue the call.
    result = await ask_router(
        task_type,
        _content_for_task(task_type),
        db_path=db_path,
        email_id=email_id,
        confirmation_token=confirmation_token,
    )

    expected = _expected_gate_verdict(sensitivity, with_token)

    if expected == "sensitivity_blocks_api":
        assert result.ok is False, f"expected refused; got {result}"
        assert result.error is not None
        assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API, (
            f"expected SENSITIVITY_BLOCKS_API; got {result.error.code}"
        )
        # AC-3 invariant: override remains armed after gate refusal.
        active = _get_active_oneshot_override()
        assert active is not None, (
            "Override must remain armed when sensitivity gate refuses "
            "(consume-on-actual-use; gate refusal ≠ actual use)."
        )
        assert active.model == _OPUS

        # Story 9.5.2 Run 3 (Path B, symmetric AC-3): gate refusal now emits
        # a `sensitivity_gate:refused` audit row (contract inverted from the
        # original Story 4-7 no-row-on-refusal invariant to close the
        # vocabulary-wired-but-never-emitted gap).
        row = await fetchone(
            db_path,
            "SELECT model_chosen_reason FROM router_calls WHERE task_type = ?",
            (task_type,),
        )
        assert row is not None, (
            "expected `sensitivity_gate:refused` router_calls row on refusal; got None"
        )
        assert row[0] == "sensitivity_gate:refused", (
            f"expected model_chosen_reason='sensitivity_gate:refused'; got {row[0]!r}"
        )
    else:
        # Allowed case — dispatch succeeds + audit row carries
        # OVERRIDE_SLASH_ONE_SHOT.
        assert result.ok is True, f"expected ok; got {result}"
        # Override is CONSUMED on actual dispatch.
        assert _get_active_oneshot_override() is None, (
            "Override must be consumed on successful dispatch."
        )
        # Audit row carries the override reason.
        row = await fetchone(
            db_path,
            "SELECT model_chosen, model_chosen_reason FROM router_calls "
            "WHERE task_type = ? ORDER BY ts DESC LIMIT 1",
            (task_type,),
        )
        assert row is not None
        assert row[0] == _OPUS  # the override model
        assert row[1] == "slash_command:one_shot:adam"
