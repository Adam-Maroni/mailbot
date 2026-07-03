"""Story 3-3 AC-5 + AC-6: Router precondition layer integration tests.

Verifies the FR-2.3 hard invariant: no Router call for any other task on
email_id is permitted until sensitivity_at IS NOT NULL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchall
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

_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_HAIKU = "claude-haiku-4-5-20251001"


class _FakeAdapter:
    def __init__(self, model_id: str, payload: dict[str, Any]) -> None:
        self.model_id = model_id
        self.payload = payload
        self.call_count = 0

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        self.call_count += 1
        return AdapterResponse(
            text=json.dumps(self.payload),
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=30,
            raw={"mock": True},
        )


_POLICY_YAML = f"""\
version: "test-precondition-v1"

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
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "any"
  hermes_aux:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state():
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


async def _seed_email_with_sensitivity(
    db_path: str,
    *,
    graph_id: str,
    sensitivity: str | None = None,
) -> None:
    if sensitivity is None:
        await execute_write(
            db_path,
            "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) VALUES (?, ?, ?, ?, ?)",
            (graph_id, "2026-06-01T00:00:00Z", "s", "x@y.com", "b"),
        )
    else:
        await execute_write(
            db_path,
            "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
            "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                graph_id,
                "2026-06-01T00:00:00Z",
                "s",
                "x@y.com",
                "b",
                sensitivity,
                "2026-06-01T00:01:00Z",
                "v1",
                0.9,
                _QWEN,
            ),
        )


async def test_precondition_refuses_unclassified_email(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: ask_router with email_id whose sensitivity_at is NULL → SENSITIVITY_NOT_CLASSIFIED."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter(_QWEN, {"class_coarse": "newsletter", "confidence": 0.9}))
    await _seed_email_with_sensitivity(db_path, graph_id="email-1", sensitivity=None)

    result = await ask_router(
        task_type="coarse_class",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="email-1",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_NOT_CLASSIFIED

    # Story 9.5.2 Run 3 (Path B, symmetric AC-3): refusal now writes a
    # `sensitivity_gate:refused` audit row (contract inverted from the
    # original no-row-on-refusal invariant).
    rows = await fetchall(
        db_path, "SELECT model_chosen_reason FROM router_calls", ()
    )
    assert len(rows) == 1
    assert rows[0][0] == "sensitivity_gate:refused"


async def test_precondition_allows_classified_email(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: after sensitivity_at is populated, the same call proceeds."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter(_QWEN, {"class_coarse": "newsletter", "confidence": 0.9}))
    await _seed_email_with_sensitivity(db_path, graph_id="email-1", sensitivity="normal")

    result = await ask_router(
        task_type="coarse_class",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="email-1",
    )

    assert result.ok is True

    # router_calls row should now exist.
    rows = await fetchall(db_path, "SELECT id FROM router_calls", ())
    assert len(rows) == 1


async def test_precondition_blocks_sensitive_to_haiku(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: a 'sensitive' email + API-bound task (Haiku) → SENSITIVITY_BLOCKS_API."""
    db_path = _setup(tmp_path)
    # Haiku adapter not even registered — we shouldn't get that far.
    await _seed_email_with_sensitivity(db_path, graph_id="email-1", sensitivity="sensitive")

    result = await ask_router(
        task_type="summary_short",  # routes to Haiku per the policy fixture
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="email-1",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    assert result.error.model_attempted == [_HAIKU]

    # Story 9.5.2 Run 3 (Path B, symmetric AC-3): refusal now writes a
    # `sensitivity_gate:refused` audit row (contract inverted from the
    # original no-row-on-refusal invariant).
    rows = await fetchall(
        db_path, "SELECT model_chosen_reason FROM router_calls", ()
    )
    assert len(rows) == 1
    assert rows[0][0] == "sensitivity_gate:refused"


async def test_precondition_blocks_confidential_to_haiku(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: 'confidential' email + API-bound task → SENSITIVITY_BLOCKS_API."""
    db_path = _setup(tmp_path)
    await _seed_email_with_sensitivity(db_path, graph_id="email-1", sensitivity="confidential")

    result = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="email-1",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API


async def test_precondition_allows_sensitive_to_local_qwen(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: 'sensitive' email + LOCAL task (Qwen) → proceeds normally.

    The gate is API-bound-only. Sensitive bodies CAN flow to local models per
    FR-2.5 — sensitivity blocks only the Anthropic API.
    """
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter(_QWEN, {"class_coarse": "human", "confidence": 0.9}))
    await _seed_email_with_sensitivity(db_path, graph_id="email-1", sensitivity="sensitive")

    result = await ask_router(
        task_type="coarse_class",  # routes to Qwen per the policy fixture
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="email-1",
    )

    assert result.ok is True

    # router_calls row exists — dispatch happened.
    rows = await fetchall(db_path, "SELECT id FROM router_calls", ())
    assert len(rows) == 1


async def test_precondition_bypassed_when_email_id_is_none(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: ad-hoc Router calls (email_id=None) bypass the precondition entirely.

    Hermes-aux compression, cache-warmer probes, sender-reputation summary,
    thread-continuity note — none of these are email-scoped tasks.
    """
    db_path = _setup(tmp_path)
    register_adapter(_HAIKU, _FakeAdapter(_HAIKU, {"text": "compressed message"}))
    # No email seeded; no email_id passed.

    result = await ask_router(
        task_type="hermes_aux",
        content={"messages": "compress me"},
        db_path=db_path,
        email_id=None,
    )

    assert result.ok is True
    rows = await fetchall(db_path, "SELECT id FROM router_calls", ())
    assert len(rows) == 1


async def test_precondition_refuses_when_email_row_missing(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5 edge case: email_id passed but the row doesn't exist → SENSITIVITY_NOT_CLASSIFIED.

    A missing row is treated the same as sensitivity_at=NULL — both fail the
    precondition. Better fail-closed than fail-open.
    """
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter(_QWEN, {"class_coarse": "newsletter", "confidence": 0.9}))
    # No seed call.

    result = await ask_router(
        task_type="coarse_class",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="nonexistent-id",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_NOT_CLASSIFIED


async def test_precondition_does_not_block_sensitivity_class_itself(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: sensitivity_class IS the gate; it must dispatch even when sensitivity_at IS NULL."""
    db_path = _setup(tmp_path)
    register_adapter(
        _QWEN,
        _FakeAdapter(_QWEN, {"sensitivity": "normal", "confidence": 0.9, "reason": "ordinary"}),
    )
    await _seed_email_with_sensitivity(db_path, graph_id="email-1", sensitivity=None)

    result = await ask_router(
        task_type="sensitivity_class",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="email-1",
    )

    assert result.ok is True
    rows = await fetchall(db_path, "SELECT id FROM router_calls", ())
    assert len(rows) == 1
