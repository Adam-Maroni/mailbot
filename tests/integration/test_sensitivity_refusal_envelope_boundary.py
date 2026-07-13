"""Story 10.5.2 (Epic 10.5 Cluster B, B7 / F-10-5-6) — envelope carried on
RouterError + rendered gracefully (200, not 502) at the /v1/chat/completions
boundary.

Two layers:
  A) Router-level: dispatch_tool_call / ask_router refusals carry a typed
     `refusal_envelope` with the four-beat guidance and NO Graph id.
  B) Boundary-level: a sensitivity-blocked chat request renders the four-beat
     message as a normal 200-shape completion — the raw HTTP-502 retry ladder
     is gone (F-10-5-6), and the Graph email id never appears in the body.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import (
    ChatCompletionFunctionDef,
    ChatCompletionToolDef,
    ErrorCode,
)
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test
from mailbot_api.router.router import dispatch_tool_call

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_SECRET_GRAPH_ID = "AAMkAGI2-secret-graph-id-do-not-leak-0xDEADBEEF"

_POLICY_YAML = f"""\
version: "test-10-5-2-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
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
def _clean_state() -> Any:
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
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


async def _seed_email(db_path: str, *, graph_id: str, sensitivity: str | None) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-06-02T00:00:00Z", "s", "x@y.com", "b",
            sensitivity,
            "2026-06-02T00:01:00Z" if sensitivity is not None else None,
            "v1", 0.9, _QWEN,
        ),
    )


def _tools() -> list[ChatCompletionToolDef]:
    return [
        ChatCompletionToolDef(
            type="function",
            function=ChatCompletionFunctionDef(
                name="propose_action",
                description="Propose an action on an email.",
                parameters={"type": "object", "properties": {"email_id": {"type": "string"}}},
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Layer A — router-level: refusal carries the envelope, no id leak
# ---------------------------------------------------------------------------


async def test_confidential_refusal_carries_envelope_no_id_leak(
    tmp_path: Path, _clean_state: Any
) -> None:
    """A confidential refusal from dispatch_tool_call carries a typed envelope
    whose fields never contain the Graph id."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity="confidential")
    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "summarize this"}],
        tools=[t.model_dump() for t in _tools()],
        tool_choice="auto",
        model=_HAIKU,
        is_force_override=False,
        db_path=db_path,
        caller_origin="test",
        caller_verb="hermes_aux_tools",
        email_id=_SECRET_GRAPH_ID,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    env = result.error.refusal_envelope
    assert env is not None
    assert env.classification == "confidential"
    # No escalation offered for confidential.
    assert "yes, escalate" not in env.user_facing_guidance.lower()
    # The Graph id must not appear ANYWHERE in the serialized envelope.
    assert _SECRET_GRAPH_ID not in env.model_dump_json()


async def test_not_classified_refusal_carries_envelope_no_rederive(
    tmp_path: Path, _clean_state: Any
) -> None:
    """A not-yet-classified refusal carries the envelope; guidance never
    suggests `mailbot rederive` (crashes until 10-5-4)."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity=None)
    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "summarize this"}],
        tools=[t.model_dump() for t in _tools()],
        tool_choice="auto",
        model=_HAIKU,
        is_force_override=False,
        db_path=db_path,
        caller_origin="test",
        caller_verb="hermes_aux_tools",
        email_id=_SECRET_GRAPH_ID,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_NOT_CLASSIFIED
    env = result.error.refusal_envelope
    assert env is not None
    assert env.classification == "not_classified"
    assert "rederive" not in env.user_facing_guidance.lower()


async def test_sensitive_no_token_refusal_offers_escalation(
    tmp_path: Path, _clean_state: Any
) -> None:
    """A sensitive-without-token refusal carries an envelope offering
    'yes, escalate'."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity="sensitive")
    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "draft a reply"}],
        tools=[t.model_dump() for t in _tools()],
        tool_choice="auto",
        model=_HAIKU,
        is_force_override=False,
        db_path=db_path,
        caller_origin="test",
        caller_verb="hermes_aux_tools",
        email_id=_SECRET_GRAPH_ID,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    env = result.error.refusal_envelope
    assert env is not None
    assert env.classification == "sensitive"
    assert "yes, escalate" in env.user_facing_guidance.lower()
    assert _SECRET_GRAPH_ID not in env.model_dump_json()


# ---------------------------------------------------------------------------
# Layer B — boundary-level: 200 graceful render, not 502, no id in body
# ---------------------------------------------------------------------------


def _bootstrap_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    db_path = str(tmp_path / "app.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-router-key-xyz")
    from mailbot_api.main import app

    return app, db_path


def test_chat_boundary_renders_confidential_refusal_as_200_not_502(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _clean_state: Any
) -> None:
    """F-10-5-6: a confidential-blocked tool-call chat request returns a
    graceful 200 completion (the four-beat message), NOT a raw 502, and the
    Graph email id never appears in the response body.

    Story AI-1 Phase 2 (10-6-1): the confidential API-block gate only fires for
    an API-BOUND model (`_API_BOUND_MODEL_RE`) — a LOCAL model reading
    confidential content never leaves the device, so it is privacy-exempt by
    design (see test_chat_boundary_confidential_served_locally_no_api_block for
    the default-path behavior). Since the default alias now routes to the local
    lane (qwen), this test forces an API model (`model=_HAIKU`) to exercise the
    API-bound confidential-refusal render this test was written to guard."""
    import asyncio

    app, db_path = _bootstrap_app(tmp_path, monkeypatch)
    # Seed the email BEFORE the client context so we don't touch the loop the
    # TestClient drives. Migrations were already applied in _bootstrap_app.
    asyncio.run(_seed_email(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity="confidential"))
    with TestClient(app) as client:
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key-xyz"},
            json={
                # Force an API-bound model so the confidential gate fires — the
                # F-10-5-6 graceful-refusal render is the behavior under test.
                "model": _HAIKU,
                "stream": False,
                "messages": [
                    {"role": "user", "content": "summarize this email"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "toolu_1",
                                "type": "function",
                                "function": {
                                    "name": "propose_action",
                                    "arguments": json.dumps({"email_id": _SECRET_GRAPH_ID}),
                                },
                            }
                        ],
                    },
                ],
                "tools": [t.model_dump() for t in _tools()],
            },
        )
    # Graceful, NOT 502.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    content = body["choices"][0]["message"]["content"]
    assert "confidential" in content.lower()
    assert "outlook" in content.lower()
    # The id must not leak anywhere in the response.
    assert _SECRET_GRAPH_ID not in resp.text


def test_chat_boundary_confidential_served_locally_no_api_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _clean_state: Any
) -> None:
    """Story AI-1 Phase 2 (10-6-1, AC-5) — the privacy-model consequence of
    routing the default chat tool-call to the local lane: a confidential email
    is NOT API-blocked when served by the LOCAL model (qwen). Confidential
    content read by a local model never leaves the device, so the
    `SENSITIVITY_BLOCKS_API` gate (API-bound-only) correctly does not fire — the
    request is served locally and returns a normal 200. The id still must not
    leak in the response.

    This is the deliberate, documented behavior (local = privacy-safe;
    NFR-PRIV-2 blocks EXTERNAL APIs, not local inference). It is asserted
    explicitly so a future regression that starts API-blocking the local lane
    (or, worse, silently routing confidential content to an API) is caught."""
    import asyncio

    app, db_path = _bootstrap_app(tmp_path, monkeypatch)
    asyncio.run(_seed_email(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity="confidential"))

    # Register a fake qwen adapter so the local dispatch has an adapter to reach
    # (the real Ollama isn't running in unit/integration CI). It returns a plain
    # text completion — the point is the request is SERVED, not API-blocked.
    from mailbot_api.router.models import ToolCallAdapterResponse
    from mailbot_api.router.registry import register_adapter

    class _LocalFake:
        async def call(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
            raise NotImplementedError

        async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
            return ToolCallAdapterResponse(
                text="served locally",
                tool_calls=[],
                tokens_in=5,
                tokens_out=3,
                cached_tokens_in=0,
                latency_ms=4,
                finish_reason="stop",
                raw={"mock": True},
            )

    with TestClient(app) as client:
        register_adapter(_QWEN, _LocalFake())
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key-xyz"},
            json={
                # Default alias → routes to the local lane (qwen) post-AC-5.
                "model": "hermes_aux",
                "stream": False,
                "messages": [
                    {"role": "user", "content": "summarize this email"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "toolu_1",
                                "type": "function",
                                "function": {
                                    "name": "propose_action",
                                    "arguments": json.dumps({"email_id": _SECRET_GRAPH_ID}),
                                },
                            }
                        ],
                    },
                ],
                "tools": [t.model_dump() for t in _tools()],
            },
        )
    # Served locally — NOT an API block, NOT a 502.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # It is NOT the confidential-refusal envelope (that only fires for API models).
    content = body["choices"][0]["message"]["content"]
    assert "admits no api override" not in content.lower()
    # The id still never leaks in the response body.
    assert _SECRET_GRAPH_ID not in resp.text
    # The dispatch was attributed to the local model in the audit trail.
    import asyncio as _aio

    from mailbot_api.db.connection import fetchone as _fetchone

    async def _reason() -> tuple[Any, ...] | None:
        return await _fetchone(
            db_path,
            "SELECT model_chosen FROM router_calls WHERE task_type = 'chat_completions_tool_call'",
            (),
        )

    row = _aio.run(_reason())
    assert row is not None
    assert row[0] == _QWEN
