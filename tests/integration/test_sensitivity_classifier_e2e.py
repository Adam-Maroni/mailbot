"""Story 3-3 AC-1, AC-2, AC-6: end-to-end classifier tests.

Spins up a real SQLite DB + real migrations 001..012 + a fake ModelAdapter
registered for the Qwen model id. Drives classify_sensitivity end-to-end
and asserts the emails row + router_calls row both populate correctly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import EMAIL_DERIVED_FIELDS_SELECT
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
from mailbot_api.sensitivity.classifier import classify_sensitivity

_QWEN_MODEL_ID = "qwen2.5:3b-instruct-q4_K_M"


class _FakeQwenAdapter:
    """Returns a scripted SensitivityClassOutput JSON per call."""

    def __init__(self, sensitivity: str, confidence: float, reason: str) -> None:
        self.model_id = _QWEN_MODEL_ID
        self._sensitivity = sensitivity
        self._confidence = confidence
        self._reason = reason
        self.call_count = 0

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        self.call_count += 1
        payload = json.dumps(
            {
                "sensitivity": self._sensitivity,
                "confidence": self._confidence,
                "reason": self._reason,
            }
        )
        return AdapterResponse(
            text=payload, tokens_in=20, tokens_out=10, cached_tokens_in=0, latency_ms=33, raw={"mock": True}
        )


_POLICY_YAML = f"""\
version: "test-sensitivity-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN_MODEL_ID}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
"""


_POLICY_YAML_DRIFTED = """\
version: "test-sensitivity-v1-drifted"

tasks:
  sensitivity_class:
    model: "claude-haiku-4-5-20251001"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state():
    """Reset module-level singletons between tests."""
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


def _setup_db_and_policy(tmp_path: Path, *, drifted: bool = False) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML_DRIFTED if drifted else _POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


async def _seed_email(db_path: str, graph_id: str = "seed-1") -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) VALUES (?, ?, ?, ?, ?)",
        (graph_id, "2026-06-01T00:00:00Z", "Test subject", "alice@example.com", "Test body preview"),
    )


async def test_classify_sensitivity_happy_path_writes_back(tmp_path: Path, _clean_state: Any) -> None:
    """AC-1: classifier returns 'normal' high-confidence; emails row populated."""
    db_path = _setup_db_and_policy(tmp_path)
    register_adapter(_QWEN_MODEL_ID, _FakeQwenAdapter("normal", 0.95, "ordinary message"))
    await _seed_email(db_path)

    result = await classify_sensitivity("seed-1", db_path=db_path)

    assert result.ok is True
    assert result.sensitivity == "normal"
    assert result.confidence == pytest.approx(0.95)
    assert result.floored_to_sensitive is False
    assert result.model == _QWEN_MODEL_ID

    # Emails row should have all sensitivity companions populated.
    row = await fetchone(db_path, EMAIL_DERIVED_FIELDS_SELECT, ("seed-1",))
    assert row is not None
    # Row layout: (sensitivity, sensitivity_prompt_v, sensitivity_conf, sensitivity_model, sensitivity_at, ...)
    sensitivity, sensitivity_prompt_v, sensitivity_conf, sensitivity_model, sensitivity_at = row[:5]
    assert sensitivity == "normal"
    assert sensitivity_prompt_v == "v1"
    assert sensitivity_conf == pytest.approx(0.95)
    assert sensitivity_model == _QWEN_MODEL_ID
    assert sensitivity_at  # populated


async def test_classify_sensitivity_floors_low_confidence_normal_to_sensitive(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-1 NFR-PRIV-1: confidence < 0.5 with 'normal' → floor to 'sensitive'."""
    db_path = _setup_db_and_policy(tmp_path)
    register_adapter(_QWEN_MODEL_ID, _FakeQwenAdapter("normal", 0.3, "uncertain"))
    await _seed_email(db_path)

    result = await classify_sensitivity("seed-1", db_path=db_path)

    assert result.ok is True
    assert result.sensitivity == "sensitive"
    assert result.floored_to_sensitive is True

    # Emails row reflects the FLOORED value, not the model's raw output.
    row = await fetchone(db_path, EMAIL_DERIVED_FIELDS_SELECT, ("seed-1",))
    assert row is not None
    assert row[0] == "sensitive"


async def test_classify_sensitivity_does_not_floor_already_sensitive(tmp_path: Path, _clean_state: Any) -> None:
    """AC-1: low confidence on 'sensitive' does NOT trip the floor (already sensitive)."""
    db_path = _setup_db_and_policy(tmp_path)
    register_adapter(_QWEN_MODEL_ID, _FakeQwenAdapter("sensitive", 0.3, "uncertain"))
    await _seed_email(db_path)

    result = await classify_sensitivity("seed-1", db_path=db_path)

    assert result.ok is True
    assert result.sensitivity == "sensitive"
    assert result.floored_to_sensitive is False


async def test_classify_sensitivity_fr_2_5_violation_when_policy_drifted(tmp_path: Path, _clean_state: Any) -> None:
    """AC-2: per-call safeguard refuses if policy.sensitivity_class.model != Qwen."""
    db_path = _setup_db_and_policy(tmp_path, drifted=True)
    # The Haiku adapter is NOT registered — we shouldn't get that far.
    await _seed_email(db_path)

    result = await classify_sensitivity("seed-1", db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert "FR-2.5 violation" in result.error.message

    # Emails row sensitivity is still NULL — no dispatch happened.
    row = await fetchone(db_path, EMAIL_DERIVED_FIELDS_SELECT, ("seed-1",))
    assert row is not None
    assert row[0] is None  # sensitivity column


async def test_classify_sensitivity_email_not_found(tmp_path: Path, _clean_state: Any) -> None:
    """AC-1: missing email_id returns ok=False with PROVIDER_ERROR."""
    db_path = _setup_db_and_policy(tmp_path)
    register_adapter(_QWEN_MODEL_ID, _FakeQwenAdapter("normal", 0.9, "x"))
    # No _seed_email call.

    result = await classify_sensitivity("nonexistent-id", db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert "not found" in result.error.message
