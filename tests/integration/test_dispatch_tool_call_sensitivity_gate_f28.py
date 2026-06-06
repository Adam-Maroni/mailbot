"""Story 6-20 — F28 closure: dispatch_tool_call sensitivity-gate relocation.

F28 (PRIVACY INVARIANT VIOLATION, 2026-06-06 Story 6-6.5 fifth-pass walk):
Hermes's Haiku-4.5 main-inference drafted a reply INLINE in its own
``chat_completions_tool_call`` instead of dispatching the ``draft_reply`` MCP
tool. Story 4-7's sensitivity-token gate at ``ask_router(task_type='draft_reply')``
never fired. Sensitive body (family-medical CP-B fixture) reached cloud API
without ``mint_sensitivity_token`` mediation.

Fix (Adam-decided 2026-06-06 option A + strictest-placement): relocate the
gate to ``dispatch_tool_call``'s precondition layer AND broaden it to gate
ALL ``chat_completions_tool_call`` when ANY referenced email has sensitivity
∈ {sensitive, confidential} — whether referenced via the legacy ``email_id``
parameter OR via the request's messages (assistant tool_calls arguments OR
tool-role content).

12 tests covering AC-5:
  1-5: resolver pure-function unit tests
  6:   F28 reproducer — sensitive email in tool-result content → refused
  7:   confidential in tool-result content + token → still refused (NFR-PRIV-2)
  8:   sensitive + valid token → dispatch succeeds + grant_id on audit row
  9:   normal in tool-result content → unchanged passthrough
  10:  no email_id anywhere → unchanged behavior
  11:  legacy email_id param path → gate fires (regression coverage)
  12:  refusal path writes NO router_calls row
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import (
    _clear_registry_for_tests,
)
from mailbot_api.actions.sensitivity_tokens import (
    mint as _mint_token,
)
from mailbot_api.db.connection import execute_write, fetchall
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
from mailbot_api.router.models import ToolCallAdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import (
    _resolve_email_ids_from_messages,
    dispatch_tool_call,
)

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_TOOL_CALL_TASK_TYPE = "chat_completions_tool_call"


# ---------------------------------------------------------------------------
# Fixtures + harness
# ---------------------------------------------------------------------------


_POLICY_YAML = f"""\
version: "test-f28-v1"

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
    # CR-6-20-2 (2026-06-06, sonnet-4-6 review): also reset registry + policy
    # snapshot BEFORE the test runs so a prior test's leaked adapter or policy
    # cannot influence this test's gate behavior. Without these pre-yield
    # resets, an adapter registered for _HAIKU by another test file could
    # silently satisfy the gate's dispatch path in tests 6/7/11/12 (which
    # rely on the gate refusing BEFORE dispatch).
    _clear_registry_for_tests()
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
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


async def _seed_email(db_path: str, *, graph_id: str, sensitivity: str) -> None:
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


class _FakeToolAdapter:
    """Adapter that returns a canned successful tool-call response."""

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
        tool_choice: Any = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse:
        return ToolCallAdapterResponse(
            text="ok",
            tool_calls=[],
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=12,
            finish_reason="stop",
            raw={"mock": True},
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
# Tests 1-5 — resolver pure-function unit tests
# ---------------------------------------------------------------------------


def test_resolver_collects_email_ids_from_assistant_tool_calls() -> None:
    """AC-5.1 — resolver walks assistant tool_calls[].function.arguments JSON."""
    messages = [
        {"role": "user", "content": "draft a reply"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {
                        "name": "propose_action",
                        "arguments": json.dumps({"email_id": "e1", "subject": "x"}),
                    },
                }
            ],
        },
    ]
    assert _resolve_email_ids_from_messages(messages) == {"e1"}


def test_resolver_collects_email_ids_from_tool_result_content() -> None:
    """AC-5.2 — resolver walks tool-role content JSON. F28's actual surface."""
    messages = [
        {
            "role": "tool",
            "tool_call_id": "toolu_1",
            "content": json.dumps(
                {"ok": True, "email": {"email_id": "e_hydrated", "subject": "x"}}
            ),
        },
    ]
    assert _resolve_email_ids_from_messages(messages) == {"e_hydrated"}


def test_resolver_dedupes_repeated_ids() -> None:
    """AC-5.3 — multiple tool_calls referencing the same id collapse to one entry."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {
                        "name": "hydrate_email",
                        "arguments": json.dumps({"email_id": "e1"}),
                    },
                },
                {
                    "id": "toolu_2",
                    "type": "function",
                    "function": {
                        "name": "propose_action",
                        "arguments": json.dumps({"email_id": "e1", "action_type": "SEND_REPLY"}),
                    },
                },
            ],
        },
    ]
    assert _resolve_email_ids_from_messages(messages) == {"e1"}


def test_resolver_traverses_nested_payloads() -> None:
    """AC-5.4 — resolver collects email_id at any nesting depth (dict + list)."""
    messages = [
        {
            "role": "tool",
            "tool_call_id": "t1",
            "content": json.dumps(
                {
                    "args": {
                        "primary": {"email_id": "e3"},
                        "others": [{"email_id": "e4"}, {"unrelated": True}],
                    }
                }
            ),
        }
    ]
    assert _resolve_email_ids_from_messages(messages) == {"e3", "e4"}


def test_resolver_handles_malformed_tool_call_arguments_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-5.5 — malformed JSON in tool_calls[].function.arguments is silently
    skipped (returns empty set) + DEBUG log fires for caller-side bug
    visibility. Sensitivity-gate concern is solely that we did not MISS an
    email_id; downstream tool-dispatch will surface the malformed args."""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {
                        "name": "propose_action",
                        "arguments": '{"not_json',  # malformed
                    },
                }
            ],
        }
    ]
    with caplog.at_level(logging.DEBUG, logger="mailbot_api.router.router"):
        assert _resolve_email_ids_from_messages(messages) == set()
    assert any(
        rec.message.startswith("dispatch_tool_call arg parse failed")
        or "dispatch_tool_call.arg_parse_failed"
        in getattr(rec, "event", "")
        for rec in caplog.records
    ), "DEBUG log for malformed JSON should fire"


# ---------------------------------------------------------------------------
# Tests 6-12 — dispatch_tool_call gate behavior
# ---------------------------------------------------------------------------


async def test_dispatch_tool_call_gates_on_sensitive_email_in_tool_result_content(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.6 — the F28 REPRODUCER.

    Sensitive email body landed via tool-result content (mirroring the
    hydrate_email return shape). Pre-fix: gate never fires because email_id
    parameter is None. Post-fix: gate fires on the resolved id.
    """
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e_sens", sensitivity="sensitive")

    messages = [
        {"role": "user", "content": "draft a reply to that"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {
                        "name": "hydrate_email",
                        "arguments": json.dumps({"email_id": "e_sens"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "toolu_1",
            "content": json.dumps(
                {
                    "ok": True,
                    "email": {
                        "email_id": "e_sens",
                        "subject": "Following up on yesterday",
                        "body_text": "family-medical content",
                    },
                }
            ),
        },
    ]
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id=None,
        confirmation_token=None,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    assert "e_sens" in result.error.message

    # AC-2 §5 — refusal MUST NOT write a router_calls row.
    rows = await fetchall(
        db_path, "SELECT COUNT(*) FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert rows[0][0] == 0


async def test_dispatch_tool_call_gates_on_confidential_email_unconditional(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.7 — NFR-PRIV-2: confidential admits NO override even with a token."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e_conf", sensitivity="confidential")

    messages = [
        {
            "role": "tool",
            "tool_call_id": "t1",
            "content": json.dumps(
                {"ok": True, "email": {"email_id": "e_conf", "subject": "x"}}
            ),
        }
    ]
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id=None,
        # Token supplied — must NOT unlock confidential per NFR-PRIV-2.
        confirmation_token="bogus-but-syntactically-valid",
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    assert "confidential" in result.error.message.lower()
    assert "e_conf" in result.error.message


async def test_dispatch_tool_call_allows_sensitive_email_when_valid_token_supplied(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.8 — sensitive email + valid token → dispatch + grant_id on audit row."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e_sens", sensitivity="sensitive")
    register_adapter(_HAIKU, _FakeToolAdapter())

    minted = _mint_token("e_sens", _TOOL_CALL_TASK_TYPE)

    messages = [
        {
            "role": "tool",
            "tool_call_id": "t1",
            "content": json.dumps(
                {"ok": True, "email": {"email_id": "e_sens", "subject": "x"}}
            ),
        }
    ]
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id=None,
        confirmation_token=minted.token_value,
    )
    assert result.ok is True, f"expected ok=True, got error={result.error}"

    rows = await fetchall(
        db_path,
        "SELECT sensitivity_grant_id, sensitivity_grant_minted_at, task_type "
        "FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    grant_id, minted_at, task_type = rows[0]
    assert grant_id == minted.grant_id
    assert minted_at is not None
    assert minted_at.endswith("Z")
    assert task_type == _TOOL_CALL_TASK_TYPE


async def test_dispatch_tool_call_unchanged_for_normal_emails_in_messages(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.9 — normal-sensitivity email in messages → no gate refusal, audit
    row written with sensitivity_grant_id IS NULL."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e_norm", sensitivity="normal")
    register_adapter(_HAIKU, _FakeToolAdapter())

    messages = [
        {
            "role": "tool",
            "tool_call_id": "t1",
            "content": json.dumps(
                {"ok": True, "email": {"email_id": "e_norm", "subject": "x"}}
            ),
        }
    ]
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id=None,
        confirmation_token=None,
    )
    assert result.ok is True

    rows = await fetchall(
        db_path,
        "SELECT sensitivity_grant_id FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] is None


async def test_dispatch_tool_call_unchanged_when_no_email_ids_anywhere(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.10 — no email_id in param or messages → no gate fires (legacy
    behavior preserved; existing tool-bearing chat completions stay green)."""
    db_path = _setup(tmp_path)
    register_adapter(_HAIKU, _FakeToolAdapter())

    messages = [{"role": "user", "content": "say hello"}]
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id=None,
        confirmation_token=None,
    )
    assert result.ok is True

    rows = await fetchall(
        db_path,
        "SELECT sensitivity_grant_id FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] is None


async def test_dispatch_tool_call_legacy_email_id_param_path_still_gates(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.11 — legacy single-id param path (Story 6-9 originally shipped)
    continues firing. The multi-id branch subsumes it but the parameter
    surface stays live for direct callers."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e_sens", sensitivity="sensitive")

    messages = [{"role": "user", "content": "go"}]
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id="e_sens",  # legacy parameter surface
        confirmation_token=None,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API
    # CR-6-20-4 (2026-06-06, sonnet-4-6 review): assert the exact legacy
    # message wording, not a disjunction. The single-id legacy path keeps
    # the historical message verbatim (no email_id substring) so existing
    # Story 6-9 callers see no message-shape regression; a future regression
    # that changes the message shape MUST be caught precisely.
    assert (
        "requires per-session confirmation token"
        in result.error.message.lower()
    )


async def test_dispatch_tool_call_refusal_writes_no_audit_row(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-5.12 — precondition-layer refusal writes ZERO router_calls rows.
    Counter-test to lock in the "refusal is a routing-side decision, not a
    dispatch outcome" contract.
    """
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e_conf", sensitivity="confidential")

    messages: list[dict[str, Any]] = []
    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
        email_id="e_conf",
        confirmation_token=None,
    )
    assert result.ok is False

    rows = await fetchall(
        db_path, "SELECT COUNT(*) FROM router_calls", (),
    )
    assert rows[0][0] == 0
