"""Story 4-7 — Router sensitivity-token handshake integration tests.

End-to-end: mint → ask_router(confirmation_token=...) → consume → dispatch
+ router_calls row carries the grant_id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
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
from mailbot_api.verbs.mint_sensitivity_token import mint_sensitivity_token

_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_HAIKU = "claude-haiku-4-5-20251001"


class _FakeAdapter:
    def __init__(self, model_id: str, payload: dict[str, Any]) -> None:
        self.model_id = model_id
        self.payload = payload

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        return AdapterResponse(
            text=json.dumps(self.payload),
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=30,
            raw={"mock": True},
        )


_POLICY_YAML = f"""\
version: "test-handshake-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state():
    _clear_registry_for_tests()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _clear_registry_for_tests()
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


async def _seed_email(
    db_path: str, *, graph_id: str, sensitivity: str,
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-06-02T00:00:00Z", "s", "x@y.com", "b",
            sensitivity, "2026-06-02T00:01:00Z", "v1", 0.9, _QWEN,
        ),
    )


async def test_sensitive_email_without_token_blocks_api(
    tmp_path: Path, _clean_state: Any,
) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-sens", sensitivity="sensitive")
    result = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-sens",
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    assert "confirmation token" in result.error.message.lower()


async def test_sensitive_email_with_invalid_token_returns_needs_confirmation(
    tmp_path: Path, _clean_state: Any,
) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-sens", sensitivity="sensitive")
    result = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-sens",
        confirmation_token="not-a-real-token",
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.NEEDS_SENSITIVITY_CONFIRMATION


async def test_sensitive_email_with_valid_token_succeeds_and_writes_grant_id(
    tmp_path: Path, _clean_state: Any,
) -> None:
    db_path = _setup(tmp_path)
    register_adapter(_HAIKU, _FakeAdapter(_HAIKU, {"summary": "ok"}))
    await _seed_email(db_path, graph_id="e-sens", sensitivity="sensitive")
    # Mint the matching token.
    mint_out = await mint_sensitivity_token("e-sens", "summary_short", db_path=db_path)
    assert mint_out.ok
    assert mint_out.token is not None

    result = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-sens",
        confirmation_token=mint_out.token,
    )
    assert result.ok is True

    # router_calls row carries the grant_id.
    rows = await fetchall(
        db_path,
        "SELECT sensitivity_grant_id, sensitivity_grant_minted_at "
        "FROM router_calls WHERE email_id = ?",
        ("e-sens",),
    )
    assert len(rows) == 1
    grant_id, minted_at = rows[0]
    assert grant_id == mint_out.grant_id
    assert minted_at is not None
    assert minted_at.endswith("Z")


async def test_confidential_email_refuses_even_with_token(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """NFR-PRIV-2: confidential admits no override. The token, even if it
    were somehow minted (it can't be — mint_sensitivity_token refuses for
    confidential), wouldn't unlock the API path."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-conf", sensitivity="confidential")
    # Pass a syntactically-valid-looking but bogus token.
    result = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-conf",
        confirmation_token="some-bogus-token",
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    assert "confidential" in result.error.message.lower()


async def test_token_single_use_second_ask_router_with_same_token_refused(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """Mint → consume on first ask_router → second ask_router with same token
    returns NEEDS_SENSITIVITY_CONFIRMATION."""
    db_path = _setup(tmp_path)
    register_adapter(_HAIKU, _FakeAdapter(_HAIKU, {"summary": "ok"}))
    await _seed_email(db_path, graph_id="e-sens", sensitivity="sensitive")
    mint_out = await mint_sensitivity_token("e-sens", "summary_short", db_path=db_path)

    first = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-sens",
        confirmation_token=mint_out.token,
    )
    assert first.ok is True

    second = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-sens",
        confirmation_token=mint_out.token,
    )
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == ErrorCode.NEEDS_SENSITIVITY_CONFIRMATION


async def test_mismatched_task_type_token_refused(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """Token minted for (email_id, task_type=A) is rejected when used for task_type=B."""
    db_path = _setup(tmp_path)
    register_adapter(_HAIKU, _FakeAdapter(_HAIKU, {"summary": "ok"}))
    await _seed_email(db_path, graph_id="e-sens", sensitivity="sensitive")
    mint_out = await mint_sensitivity_token("e-sens", "different_task", db_path=db_path)

    result = await ask_router(
        task_type="summary_short",
        content={"subject": "s", "sender": "x@y.com", "body_preview": "b"},
        db_path=db_path,
        email_id="e-sens",
        confirmation_token=mint_out.token,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.NEEDS_SENSITIVITY_CONFIRMATION
