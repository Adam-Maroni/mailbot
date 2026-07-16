"""Unit tests for mailbot_api/router/models.py:OllamaAdapter (Story 2-3).

Uses monkeypatched ``ollama.AsyncClient.chat`` — no real network. Real-Ollama
smoke tests live at tests/integration/test_ollama_adapter_real.py behind an
opt-in env var.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import ollama
import pytest

from mailbot_api.router.errors import ChatCompletionToolDef
from mailbot_api.router.models import (
    AdapterProviderError,
    AdapterResponse,
    AdapterTimeout,
    OllamaAdapter,
    ToolCallAdapterResponse,
)


def _canned_response(text: str = "OK", prompt_eval: int = 12, eval_count: int = 3) -> dict[str, Any]:
    return {
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "created_at": "2026-06-01T00:00:00Z",
        "message": {"role": "assistant", "content": text},
        "done": True,
        "done_reason": "stop",
        "total_duration": 1_000_000_000,
        "load_duration": 100_000_000,
        "prompt_eval_count": prompt_eval,
        "prompt_eval_duration": 500_000_000,
        "eval_count": eval_count,
        "eval_duration": 400_000_000,
    }


class _FakeAsyncClient:
    """Minimal stand-in for ollama.AsyncClient with a configurable behavior."""

    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        sleep_before_return: float = 0.0,
        raise_exc: BaseException | None = None,
        host: str = "",
    ) -> None:
        self.response = response or _canned_response()
        self.sleep_before_return = sleep_before_return
        self.raise_exc = raise_exc
        self.host = host
        self.last_kwargs: dict[str, Any] | None = None

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.last_kwargs = kwargs
        if self.sleep_before_return:
            await asyncio.sleep(self.sleep_before_return)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeAsyncClient) -> None:
    """Patch the AsyncClient constructor in the module's import namespace so
    `OllamaAdapter.__init__` picks up the fake."""

    def _factory(host: str = "") -> _FakeAsyncClient:
        fake.host = host
        return fake

    monkeypatch.setattr(ollama, "AsyncClient", _factory)


async def test_ollama_adapter_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(response=_canned_response("OK", prompt_eval=10, eval_count=2))
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url="http://localhost:11434",
        timeout_seconds=5.0,
    )
    result = await adapter.call(
        system="You are concise.",
        user="Reply with the word OK and nothing else.",
        max_tokens_out=8,
    )

    assert isinstance(result, AdapterResponse)
    assert result.text == "OK"
    assert result.tokens_in == 10
    assert result.tokens_out == 2
    assert result.cached_tokens_in == 0
    assert result.latency_ms >= 0
    assert "message" in result.raw


async def test_ollama_adapter_passes_options_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient()
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url="http://localhost:11434",
    )
    await adapter.call(system="sys", user="usr", max_tokens_out=42, temperature=0.5)

    assert fake.last_kwargs is not None
    assert fake.last_kwargs["model"] == "qwen2.5:3b-instruct-q4_K_M"
    assert fake.last_kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert fake.last_kwargs["options"] == {"num_predict": 42, "temperature": 0.5}


async def test_ollama_adapter_latency_ms_reflects_elapsed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(sleep_before_return=0.05)  # 50ms
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    result = await adapter.call(system="s", user="u", max_tokens_out=1)
    # Allow generous slack — Windows timer resolution + scheduler jitter.
    assert result.latency_ms >= 30


async def test_ollama_adapter_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(sleep_before_return=2.0)
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(
        model_id="qwen-test",
        base_url="http://localhost:11434",
        timeout_seconds=0.05,
    )
    with pytest.raises(AdapterTimeout) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert ei.value.model_id == "qwen-test"
    assert ei.value.timeout_seconds == 0.05


async def test_ollama_adapter_wraps_response_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(raise_exc=ollama.ResponseError("upstream 500", 500))
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="qwen-test", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert ei.value.model_id == "qwen-test"
    assert "upstream 500" in ei.value.sanitized_message
    assert "ResponseError" in ei.value.sanitized_message


async def test_ollama_adapter_wraps_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(raise_exc=RuntimeError("boom"))
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="qwen-test", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert "boom" in ei.value.sanitized_message
    assert "RuntimeError" in ei.value.sanitized_message


async def test_ollama_adapter_sanitizes_provider_error_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider errors mentioning bearer tokens / sk- keys / secret files must be redacted."""
    fake = _FakeAsyncClient(
        raise_exc=RuntimeError("auth failed: Bearer eyJhbGciOiJIUzI1NiJ9.xyz")
    )
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert "eyJ" not in ei.value.sanitized_message
    assert "[REDACTED_BEARER]" in ei.value.sanitized_message


async def test_ollama_adapter_cached_tokens_in_always_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient()
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    result = await adapter.call(system="s", user="u", max_tokens_out=1)
    assert result.cached_tokens_in == 0


def test_ollama_adapter_construction_is_side_effect_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No network call should happen on __init__; only call() touches the wire."""
    call_log: list[str] = []

    def _factory(host: str = "") -> _FakeAsyncClient:
        call_log.append(f"client_constructed:{host}")
        return _FakeAsyncClient()

    monkeypatch.setattr(ollama, "AsyncClient", _factory)
    OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    # Constructing the AsyncClient itself is OK — it doesn't open a connection.
    # We just want to assert no chat() was attempted.
    assert call_log == ["client_constructed:http://localhost:11434"]


# ---------------------------------------------------------------------------
# Story AI-1 — OllamaAdapter.call_with_tools (real tool-calling wiring).
#
# The AI-1 live probe (2026-07-11) proved Qwen 2.5 3B tool-calls with 6/6
# exact argument fidelity at temperature 0. These tests exercise the response
# translation + fail-loud contract against mocked Ollama chat responses.
# ---------------------------------------------------------------------------


def _tool_def(name: str = "archive_email") -> ChatCompletionToolDef:
    return ChatCompletionToolDef.model_validate(
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} a message by id",
                "parameters": {
                    "type": "object",
                    "properties": {"email_id": {"type": "string"}},
                    "required": ["email_id"],
                },
            },
        }
    )


def _canned_tool_response(
    *,
    name: str = "archive_email",
    arguments: dict[str, Any] | None = None,
    content: str = "",
    prompt_eval: int = 40,
    eval_count: int = 9,
    done_reason: str = "stop",
) -> dict[str, Any]:
    args = {"email_id": "ABC123"} if arguments is None else arguments
    return {
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "created_at": "2026-07-11T00:00:00Z",
        "message": {
            "role": "assistant",
            "content": content,
            "tool_calls": [{"function": {"name": name, "arguments": args}}],
        },
        "done": True,
        "done_reason": done_reason,
        "prompt_eval_count": prompt_eval,
        "eval_count": eval_count,
    }


def _adapter(monkeypatch: pytest.MonkeyPatch, fake: _FakeAsyncClient) -> OllamaAdapter:
    _install_fake_client(monkeypatch, fake)
    return OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url="http://localhost:11434",
        timeout_seconds=5.0,
    )


async def test_call_with_tools_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="You are a mailbox assistant.",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
    )

    assert isinstance(result, ToolCallAdapterResponse)
    assert result.finish_reason == "tool_calls"
    assert result.text == ""
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.type == "function"
    assert tc.function.name == "archive_email"
    # arguments is a JSON STRING (OpenAI wire shape), not a dict.
    assert isinstance(tc.function.arguments, str)
    assert json.loads(tc.function.arguments) == {"email_id": "ABC123"}
    assert tc.id  # synthesized id present
    assert result.tokens_in == 40
    assert result.tokens_out == 9


async def test_call_with_tools_text_only_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(
        response={
            "model": "qwen2.5:3b-instruct-q4_K_M",
            "message": {"role": "assistant", "content": "I can't do that."},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 5,
            "eval_count": 4,
        }
    )
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[_tool_def()],
    )
    assert result.finish_reason == "stop"
    assert result.tool_calls == []
    assert result.text == "I can't do that."


async def test_call_with_tools_argument_fidelity_long_graph_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load-bearing: a realistic Graph-style id must round-trip EXACTLY through
    the arguments JSON-string (the reliability concern for a 3B/Q4 model)."""
    graph_id = (
        "AAMkAGI1AAAt3AABGAAAAAABQ8h1i_QeRZ2GJHu8mMj7BwB9J_"
        "AAAAAAEMAAB9J-AAAAAA=="
    )
    fake = _FakeAsyncClient(
        response=_canned_tool_response(
            name="move_email",
            arguments={"email_id": graph_id, "folder": "Archive"},
        )
    )
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "move it"}],
        tools=[_tool_def("move_email")],
    )
    assert len(result.tool_calls) == 1
    parsed = json.loads(result.tool_calls[0].function.arguments)
    assert parsed["email_id"] == graph_id  # exact, no corruption
    assert parsed["folder"] == "Archive"


async def test_call_with_tools_tool_choice_none_omits_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(
        response={
            "model": "qwen2.5:3b-instruct-q4_K_M",
            "message": {"role": "assistant", "content": "sure"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 3,
            "eval_count": 2,
        }
    )
    adapter = _adapter(monkeypatch, fake)

    await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[_tool_def()],
        tool_choice="none",
    )
    assert fake.last_kwargs is not None
    assert "tools" not in fake.last_kwargs


async def test_call_with_tools_passes_tools_when_choice_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
        tool_choice="auto",
    )
    assert fake.last_kwargs is not None
    assert "tools" in fake.last_kwargs
    sent = fake.last_kwargs["tools"]
    assert sent[0]["type"] == "function"
    assert sent[0]["function"]["name"] == "archive_email"
    assert "parameters" in sent[0]["function"]
    # Temperature 0 is load-bearing for argument fidelity (AI-1 probe).
    assert fake.last_kwargs["options"]["temperature"] == 0.0


async def test_call_with_tools_prepends_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    await adapter.call_with_tools(
        system="You are a mailbox assistant.",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
    )
    assert fake.last_kwargs is not None
    msgs = fake.last_kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "You are a mailbox assistant."}
    assert msgs[1] == {"role": "user", "content": "archive ABC123"}


async def test_call_with_tools_empty_system_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace/empty system must NOT emit a system message (F14 guard)."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    await adapter.call_with_tools(
        system="   ",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
    )
    assert fake.last_kwargs is not None
    msgs = fake.last_kwargs["messages"]
    assert all(m["role"] != "system" for m in msgs)
    assert msgs[0] == {"role": "user", "content": "archive ABC123"}


async def test_call_with_tools_finish_reason_length_on_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(
        response={
            "model": "qwen2.5:3b-instruct-q4_K_M",
            "message": {"role": "assistant", "content": "partial..."},
            "done": True,
            "done_reason": "length",
            "prompt_eval_count": 5,
            "eval_count": 8,
        }
    )
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "write a long thing"}],
        tools=[_tool_def()],
    )
    assert result.finish_reason == "length"
    assert result.tool_calls == []


async def test_call_with_tools_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(sleep_before_return=2.0)
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(
        model_id="qwen-test",
        base_url="http://localhost:11434",
        timeout_seconds=0.05,
    )
    with pytest.raises(AdapterTimeout) as ei:
        await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[_tool_def()],
        )
    assert ei.value.model_id == "qwen-test"


async def test_call_with_tools_wraps_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(raise_exc=ollama.ResponseError("upstream 500", 500))
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(model_id="qwen-test", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[_tool_def()],
        )
    assert ei.value.model_id == "qwen-test"
    assert "upstream 500" in ei.value.sanitized_message


async def test_call_with_tools_sanitizes_provider_error_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(
        raise_exc=RuntimeError("auth failed: Bearer eyJhbGciOiJIUzI1NiJ9.xyz")
    )
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[_tool_def()],
        )
    assert "eyJ" not in ei.value.sanitized_message
    assert "[REDACTED_BEARER]" in ei.value.sanitized_message


# ---------------------------------------------------------------------------
# Story AI-1 (CR-4) — edge cases: multiple tool_calls; text + tool_calls.
# ---------------------------------------------------------------------------


async def test_call_with_tools_multiple_tool_calls_in_one_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single Ollama response can carry several tool_calls; all must be
    translated, in order, each with a distinct synthesized id (Ollama supplies
    none). CR-4 edge coverage."""
    fake = _FakeAsyncClient(
        response={
            "model": "qwen2.5:3b-instruct-q4_K_M",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "mark_read", "arguments": {"email_id": "A1"}}},
                    {"function": {"name": "archive_email", "arguments": {"email_id": "B2"}}},
                    {"function": {"name": "add_local_category",
                                  "arguments": {"email_id": "C3", "category": "work"}}},
                ],
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 30,
            "eval_count": 12,
        }
    )
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "triage these"}],
        tools=[_tool_def("mark_read"), _tool_def("archive_email"),
               _tool_def("add_local_category")],
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 3
    names = [tc.function.name for tc in result.tool_calls]
    assert names == ["mark_read", "archive_email", "add_local_category"]
    # Arguments round-trip per-call.
    assert json.loads(result.tool_calls[0].function.arguments) == {"email_id": "A1"}
    assert json.loads(result.tool_calls[2].function.arguments) == {
        "email_id": "C3",
        "category": "work",
    }
    # Synthesized ids are all distinct (drain correlation needs uniqueness).
    ids = [tc.id for tc in result.tool_calls]
    assert len(set(ids)) == 3


async def test_call_with_tools_both_text_and_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response carrying BOTH assistant text and a tool_call must preserve
    the text AND the tool_call, with finish_reason=tool_calls (the tool_call
    wins the finish_reason). CR-4 edge coverage."""
    fake = _FakeAsyncClient(
        response=_canned_tool_response(
            name="archive_email",
            arguments={"email_id": "ABC123"},
            content="Archiving that one for you.",
        )
    )
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
    )

    assert result.finish_reason == "tool_calls"
    assert result.text == "Archiving that one for you."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].function.name == "archive_email"


# ---------------------------------------------------------------------------
# Story AI-1 (CR-3) — multi-turn: role:"tool" messages are re-keyed from
# OpenAI `tool_call_id` to Ollama `tool_name` for correlation.
# ---------------------------------------------------------------------------


async def test_call_with_tools_translates_tool_result_message_to_tool_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A multi-turn history with an assistant tool_call followed by its
    OpenAI-shape tool result (`role:"tool"`, keyed by `tool_call_id`) must be
    forwarded to Ollama with `tool_name` (Ollama's correlation key) resolved
    from the prior assistant tool_call's function name — and the meaningless
    `tool_call_id` dropped."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    messages = [
        {"role": "user", "content": "archive ABC123"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_xyz",
                    "type": "function",
                    "function": {"name": "archive_email",
                                 "arguments": '{"email_id":"ABC123"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_xyz", "content": "archived ok"},
        {"role": "user", "content": "now what"},
    ]

    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    assert fake.last_kwargs is not None
    sent = fake.last_kwargs["messages"]
    tool_msgs = [m for m in sent if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_name"] == "archive_email"
    assert "tool_call_id" not in tool_msgs[0]
    assert tool_msgs[0]["content"] == "archived ok"


async def test_call_with_tools_assistant_tool_call_arguments_string_to_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story AI-1 Phase 2 (10-6-1) — a multi-turn history where a PRIOR
    assistant message carries an OpenAI-shape `tool_calls[].function.arguments`
    (a JSON STRING per the OpenAI wire spec) must be forwarded to Ollama with
    that arguments field converted to a DICT — Ollama's `Message.ToolCall`
    model requires a dict and raises pydantic ValidationError on a string.

    This path became REACHED when AI-1 Phase 2 routed default chat tool-calls
    to the local lane (qwen); before that qwen refused all tool-calls at the
    capability gate so a multi-turn echo never reached the Ollama translator.
    Regression witnessed by
    test_sensitivity_refusal_envelope_boundary.py once the default routed to
    qwen (ValidationError on arguments; input_type=str)."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    messages = [
        {"role": "user", "content": "archive ABC123"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_xyz",
                    "type": "function",
                    "function": {
                        "name": "archive_email",
                        "arguments": '{"email_id":"ABC123"}',  # JSON STRING (OpenAI wire)
                    },
                }
            ],
        },
        {"role": "user", "content": "and the next one"},
    ]

    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    assert fake.last_kwargs is not None
    sent = fake.last_kwargs["messages"]
    asst = [m for m in sent if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(asst) == 1
    args = asst[0]["tool_calls"][0]["function"]["arguments"]
    # Converted to a dict for Ollama — NOT the raw JSON string.
    assert isinstance(args, dict), f"expected dict arguments for Ollama, got {type(args)}: {args!r}"
    assert args == {"email_id": "ABC123"}

    # And the shape must survive the REAL ollama library's message validation —
    # this is what actually raised the ValidationError in production.
    ollama.Message.model_validate(asst[0])


async def test_call_with_tools_assistant_tool_call_malformed_args_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense: if a prior assistant `tool_calls` arguments string is NOT valid
    JSON, the translator must not crash — it leaves the value as-is so the
    Ollama layer surfaces its own error rather than the translator raising
    mid-history. (Malformed args are a caller/model bug, not a translator bug.)"""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_bad",
                    "type": "function",
                    "function": {"name": "archive_email", "arguments": "not-json{"},
                }
            ],
        },
    ]

    # Must not raise inside the translator.
    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    assert fake.last_kwargs is not None
    asst = [
        m for m in fake.last_kwargs["messages"]
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    # Left unchanged (still a string) — the translator did not fabricate a dict.
    assert asst[0]["tool_calls"][0]["function"]["arguments"] == "not-json{"


@pytest.mark.parametrize("bad_args", ['42', '[1, 2, 3]', '"just a string"', 'true', 'null'])
async def test_call_with_tools_assistant_args_valid_json_non_object_preserved(
    monkeypatch: pytest.MonkeyPatch, bad_args: str,
) -> None:
    """CR (Blind + Edge Case Hunter, 10-6-1): a `tool_calls[].function.
    arguments` string that is SYNTACTICALLY VALID JSON but decodes to a
    NON-OBJECT (scalar/list/bool/null) must be left UNCHANGED — not substituted
    with the decoded scalar. Ollama requires a dict; forwarding the original
    string lets the ollama validator raise its own diagnostic rather than the
    translator fabricating a different-but-still-invalid non-dict `arguments`.
    The decode guard must reject valid-JSON-but-non-object, not only malformed
    JSON."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_scalar",
                    "type": "function",
                    "function": {"name": "archive_email", "arguments": bad_args},
                }
            ],
        },
    ]

    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    assert fake.last_kwargs is not None
    asst = [
        m for m in fake.last_kwargs["messages"]
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    # Left as the ORIGINAL string — the translator did NOT substitute the
    # decoded scalar/list (which would still be a non-dict Ollama rejects).
    assert asst[0]["tool_calls"][0]["function"]["arguments"] == bad_args


async def test_call_with_tools_does_not_mutate_caller_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR (Blind Hunter isolation claim, 10-6-1): the arg-normalization must not
    alias or mutate the caller's original message dicts. Capture the original
    assistant message + its nested function dict by reference and assert they
    are unchanged after the call (arguments still the original string on the
    CALLER's copy)."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    original_fn = {"name": "archive_email", "arguments": '{"email_id":"ABC123"}'}
    original_tc = {"id": "call_xyz", "type": "function", "function": original_fn}
    original_msg = {"role": "assistant", "content": "", "tool_calls": [original_tc]}
    messages = [original_msg, {"role": "user", "content": "next"}]

    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    # The caller's original structures are untouched: arguments still the STRING.
    assert original_fn["arguments"] == '{"email_id":"ABC123"}'
    assert original_tc["function"] is original_fn
    assert original_msg["tool_calls"][0] is original_tc


async def test_call_with_tools_tool_result_falls_back_to_existing_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a tool result's `tool_call_id` can't be resolved to a prior
    assistant tool_call (none in the supplied window) but the message already
    carries a `tool_name`, that name is preserved rather than dropped."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    messages = [
        {"role": "user", "content": "status?"},
        {"role": "tool", "tool_call_id": "orphan", "tool_name": "read_sql",
         "content": "3 rows"},
    ]
    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    assert fake.last_kwargs is not None
    tool_msgs = [m for m in fake.last_kwargs["messages"] if m.get("role") == "tool"]
    assert tool_msgs[0]["tool_name"] == "read_sql"
    assert "tool_call_id" not in tool_msgs[0]


async def test_call_with_tools_non_tool_messages_pass_through_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The message translation must not disturb plain user/assistant messages
    (identity for non-tool roles)."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "archive ABC123"},
    ]
    await adapter.call_with_tools(system="sys", messages=messages, tools=[_tool_def()])

    assert fake.last_kwargs is not None
    # system prepended, then the three originals verbatim.
    assert fake.last_kwargs["messages"][1:] == messages


# ---------------------------------------------------------------------------
# Story 10-6-4 — keep_alive threaded onto every chat dispatch (AC-1).
#
# F-10-6-1-W1 diagnosis: with no keep_alive, Ollama evicts qwen after 5min idle,
# discarding the prompt KV-cache → the next full-context tool-call turn re-ingests
# ~1658 tokens (~19s cold) and crosses the 30s timeout. keep_alive=-1 pins the
# model resident and preserves the cache → warm turns are ~3.7s. These tests lock
# the kwarg onto BOTH the `call` and `call_with_tools` chat dispatches, and pin
# the never-evict default.
# ---------------------------------------------------------------------------


async def test_keep_alive_default_is_minus_one_on_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit keep_alive ⇒ -1 (never evict) reaches chat() on `call`."""
    fake = _FakeAsyncClient()
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    assert adapter.keep_alive == -1

    await adapter.call(system="s", user="u", max_tokens_out=1)
    assert fake.last_kwargs is not None
    assert fake.last_kwargs["keep_alive"] == -1


async def test_keep_alive_default_is_minus_one_on_call_with_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit keep_alive ⇒ -1 reaches chat() on `call_with_tools` too."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    adapter = _adapter(monkeypatch, fake)

    await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
    )
    assert fake.last_kwargs is not None
    assert fake.last_kwargs["keep_alive"] == -1


async def test_keep_alive_explicit_value_passes_through_on_both_call_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit keep_alive (e.g. a duration string) reaches chat() verbatim
    on both `call` and `call_with_tools`."""
    fake = _FakeAsyncClient(response=_canned_tool_response())
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(
        model_id="x", base_url="http://localhost:11434", keep_alive="30m"
    )
    assert adapter.keep_alive == "30m"

    await adapter.call(system="s", user="u", max_tokens_out=1)
    assert fake.last_kwargs is not None
    assert fake.last_kwargs["keep_alive"] == "30m"

    await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "archive ABC123"}],
        tools=[_tool_def()],
    )
    assert fake.last_kwargs["keep_alive"] == "30m"


async def test_keep_alive_is_top_level_kwarg_not_in_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """keep_alive is a sibling of `options` in the Ollama API — it must NOT be
    smuggled inside the options dict (Ollama would ignore it there)."""
    fake = _FakeAsyncClient()
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    await adapter.call(system="s", user="u", max_tokens_out=1)
    assert fake.last_kwargs is not None
    assert "keep_alive" not in fake.last_kwargs["options"]
    assert "keep_alive" in fake.last_kwargs


# ---------------------------------------------------------------------------
# Story 10-7-1 — `<tool_call>`-as-text rescue parser.
#
# Qwen 2.5 3B on the Hermes chat-template path sometimes emits its tool call as
# a literal `<tool_call>{…}</tool_call>` text block inside `message.content`
# instead of the structured `message.tool_calls` array — the call is chosen but
# silently no-ops (tool_calls_count=0). These tests pin the STRICT rescue: a
# well-formed block (non-empty `name` + a dict `arguments`, or no `arguments`)
# is promoted to a real structured call; a malformed sibling-key block (the
# actual walk shape) is DECLINED and logged, never fabricated into a call.
# Ground truth: WALK-10-7-5-F1 / router_calls id=15022.
# ---------------------------------------------------------------------------


# Log-event names the rescue emits (mirrors router.py's extra={"event": ...}).
_RESCUE_PROMOTED_EVENT = "tool_call.rescue.promoted"
_RESCUE_DECLINED_EVENT = "tool_call.rescue.declined"


def _canned_text_block_response(
    *,
    content: str,
    prompt_eval: int = 40,
    eval_count: int = 9,
    done_reason: str = "stop",
) -> dict[str, Any]:
    """A response with NO structured tool_calls — the tool call (if any) lives
    only as text inside `message.content` (the qwen `<tool_call>`-as-text bug)."""
    return {
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "created_at": "2026-07-16T00:00:00Z",
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": done_reason,
        "prompt_eval_count": prompt_eval,
        "eval_count": eval_count,
    }


def _log_events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        getattr(r, "event", None)
        for r in caplog.records
        if getattr(r, "event", None) is not None
    ]


async def test_rescue_wellformed_text_block_is_promoted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-1: a well-formed `<tool_call>{name, arguments}</tool_call>` in content
    (empty structured array) is promoted to one structured call, finish_reason
    flips to `tool_calls`, and name + args are exact."""
    block = (
        '<tool_call>\n'
        '{"name": "find_emails", "arguments": {"filter": {"unread": true}}}\n'
        '</tool_call>'
    )
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    with caplog.at_level("INFO", logger="mailbot_api.router.models"):
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "find my unread emails"}],
            tools=[_tool_def("find_emails")],
        )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.type == "function"
    assert tc.function.name == "find_emails"
    assert isinstance(tc.function.arguments, str)
    assert json.loads(tc.function.arguments) == {"filter": {"unread": True}}
    assert tc.id  # synthesized id present
    assert _RESCUE_PROMOTED_EVENT in _log_events(caplog)


async def test_rescue_malformed_sibling_key_block_is_declined_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-2: the real walk shape — `name` plus stray sibling keys and NO
    `arguments` object — is STRICTLY declined (not promoted) and logged. A
    wrong-shaped call is worse than no call for the local safety-net lane."""
    block = (
        '<tool_call>\n'
        '{"name": "memory", "action": "add", "target": "user", '
        '"content": "unread_emails"}\n'
        '</tool_call>'
    )
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    with caplog.at_level("WARNING", logger="mailbot_api.router.models"):
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "find my unread emails"}],
            tools=[_tool_def("find_emails")],
        )

    assert result.tool_calls == []
    assert result.finish_reason == "stop"
    assert _RESCUE_DECLINED_EVENT in _log_events(caplog)
    assert _RESCUE_PROMOTED_EVENT not in _log_events(caplog)


async def test_rescue_plain_text_no_block_still_zero_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: a content-only response with NO `<tool_call>` block continues to
    return zero calls (the over-trigger guard). The rescue fires ONLY on a real
    block."""
    fake = _FakeAsyncClient(
        response=_canned_text_block_response(content="I can't do that.")
    )
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[_tool_def()],
    )
    assert result.tool_calls == []
    assert result.finish_reason == "stop"
    assert result.text == "I can't do that."


async def test_rescue_structured_calls_win_content_not_scanned(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-4: when structured `tool_calls` is non-empty, `content` is NOT scanned
    even if it also holds a `<tool_call>` string — no double count, no override,
    no rescue log."""
    block = '<tool_call>{"name": "other_tool", "arguments": {}}</tool_call>'
    response = _canned_tool_response(
        name="archive_email",
        arguments={"email_id": "ABC123"},
        content=block,  # a stray text block alongside the real structured call
    )
    fake = _FakeAsyncClient(response=response)
    adapter = _adapter(monkeypatch, fake)

    with caplog.at_level("INFO", logger="mailbot_api.router.models"):
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "archive ABC123"}],
            tools=[_tool_def()],
        )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1  # not 2 — content not scanned
    assert result.tool_calls[0].function.name == "archive_email"
    assert _RESCUE_PROMOTED_EVENT not in _log_events(caplog)


async def test_rescue_argument_fidelity_long_graph_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5: a rescued call's arguments round-trip EXACTLY, including a long
    Graph-style id (mirrors the structured-path fidelity guard)."""
    graph_id = (
        "AAMkAGI1AAAt3AABGAAAAAABQ8h1i_QeRZ2GJHu8mMj7BwB9J_"
        "AAAAAAEMAAB9J-AAAAAA=="
    )
    inner = json.dumps({"name": "move_email",
                        "arguments": {"email_id": graph_id, "folder": "Archive"}})
    block = f"<tool_call>{inner}</tool_call>"
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "move it"}],
        tools=[_tool_def("move_email")],
    )
    assert len(result.tool_calls) == 1
    parsed = json.loads(result.tool_calls[0].function.arguments)
    assert parsed["email_id"] == graph_id  # exact, no corruption
    assert parsed["folder"] == "Archive"


async def test_rescue_bare_block_no_arguments_promotes_empty_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1 edge: a bare `<tool_call>{"name": ...}</tool_call>` with NEITHER an
    `arguments` key NOR stray sibling keys promotes with empty args `{}`."""
    block = '<tool_call>{"name": "count_emails"}</tool_call>'
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "how many"}],
        tools=[_tool_def("count_emails")],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].function.name == "count_emails"
    assert json.loads(result.tool_calls[0].function.arguments) == {}


async def test_rescue_arguments_as_json_string_is_reserialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1 edge: some emitters nest `arguments` as a JSON STRING rather than a
    dict. The rescue parses it to a dict then re-serializes to the compact wire
    shape so downstream sees a normal `arguments` JSON string."""
    inner = '{"name": "find_emails", "arguments": "{\\"limit\\": 5}"}'
    block = f"<tool_call>{inner}</tool_call>"
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "find 5"}],
        tools=[_tool_def("find_emails")],
    )
    assert len(result.tool_calls) == 1
    assert json.loads(result.tool_calls[0].function.arguments) == {"limit": 5}


async def test_rescue_multiple_blocks_promotes_first_only(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-1 edge: when content holds multiple `<tool_call>` blocks, only the
    FIRST is promoted (single-call semantics — the structured Ollama path
    likewise yields whatever the model emitted; the rescue intentionally does
    not try to reconstruct a multi-call turn from text). The promote event fires
    (a walk can see a rescue happened); extra blocks are simply not promoted.
    CR F1: earlier wording claimed a per-extra log — there is none, and that was
    the misleading claim; single-call semantics is the intended contract."""
    block = (
        '<tool_call>{"name": "find_emails", "arguments": {"filter": {}}}</tool_call>'
        '<tool_call>{"name": "count_emails", "arguments": {}}</tool_call>'
    )
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    with caplog.at_level("INFO", logger="mailbot_api.router.models"):
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "find then count"}],
            tools=[_tool_def("find_emails"), _tool_def("count_emails")],
        )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].function.name == "find_emails"
    assert _RESCUE_PROMOTED_EVENT in _log_events(caplog)


async def test_rescue_whitespace_and_newlines_inside_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1 edge: leading/trailing/interior whitespace and newlines around the
    inner JSON must not defeat the rescue."""
    block = (
        "  <tool_call>\n\n"
        '   {"name": "find_emails",\n     "arguments": {"filter": {"unread": true}}}\n'
        "  </tool_call>  "
    )
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "find unread"}],
        tools=[_tool_def("find_emails")],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].function.name == "find_emails"
    assert json.loads(result.tool_calls[0].function.arguments) == {
        "filter": {"unread": True}
    }


async def test_rescue_empty_name_block_is_declined(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-2 edge: a block whose `name` is empty/missing is declined (a call with
    no tool name is meaningless), logged, not promoted."""
    block = '<tool_call>{"name": "", "arguments": {"x": 1}}</tool_call>'
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    with caplog.at_level("WARNING", logger="mailbot_api.router.models"):
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "do it"}],
            tools=[_tool_def()],
        )
    assert result.tool_calls == []
    assert result.finish_reason == "stop"
    assert _RESCUE_DECLINED_EVENT in _log_events(caplog)


# ---------------------------------------------------------------------------
# Story 10-7-1 — code-review-driven hardening (CR round 1).
# ---------------------------------------------------------------------------


async def test_rescue_unclosed_prefix_is_fast_and_declines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR F3 (ReDoS): a pathological input of many unclosed `<tool_call>`
    prefixes must NOT catastrophically backtrack. The linear `str.find` scan
    finds no closing tag → no block → zero calls, returning promptly. (We assert
    behavior, not wall-clock; the point is the code path is O(n) `str.find`, not
    a backtracking regex.)"""
    content = "<tool_call>" * 20000  # no closing tag anywhere
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=content))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "spam"}],
        tools=[_tool_def()],
    )
    assert result.tool_calls == []
    assert result.finish_reason == "stop"


async def test_rescue_close_tag_inside_string_value_declines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR F4: a literal `</tool_call>` inside a JSON string value truncates the
    tag-anchored block early → invalid inner JSON → STRICT decline (safe
    direction, not an over-promote)."""
    block = '<tool_call>{"name": "find_emails", "arguments": {"note": "</tool_call>"}}</tool_call>'
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "note it"}],
        tools=[_tool_def("find_emails")],
    )
    # Truncated at the inner `</tool_call>` → inner JSON is `{"name": ...
    # "note": "` which is invalid → decline, not a mangled promote.
    assert result.tool_calls == []
    assert result.finish_reason == "stop"


async def test_rescue_nan_infinity_argument_is_declined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR F5: `json` accepts non-standard `NaN`/`Infinity` by default. STRICT
    rescue must reject them (they would re-serialize into a non-JSON-standard
    arguments string) → decline."""
    for token in ("NaN", "Infinity", "-Infinity"):
        block = f'<tool_call>{{"name": "find_emails", "arguments": {{"limit": {token}}}}}</tool_call>'
        fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
        adapter = _adapter(monkeypatch, fake)
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "find"}],
            tools=[_tool_def("find_emails")],
        )
        assert result.tool_calls == [], f"{token} should have declined"
        assert result.finish_reason == "stop"


async def test_rescue_promote_strips_block_from_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR F2: on a successful promote, the raw `<tool_call>` markup is stripped
    from `.text` so a rescued turn is shape-identical to a natively-structured
    one (whose `.text` is prose, not markup). Residual prose is preserved."""
    block = (
        "Sure, let me look. "
        '<tool_call>{"name": "find_emails", "arguments": {"filter": {"unread": true}}}</tool_call>'
    )
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    result = await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "find unread"}],
        tools=[_tool_def("find_emails")],
    )
    assert len(result.tool_calls) == 1
    assert "<tool_call>" not in result.text
    assert "</tool_call>" not in result.text
    assert result.text == "Sure, let me look."  # residual prose, trimmed


async def test_rescue_decline_log_redacts_secrets_in_raw_block(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """CR F9: the decline log's `raw_block` must be sanitized — a Bearer token
    embedded in a malformed block must NOT leak into the WARNING log."""
    block = (
        '<tool_call>{"name": "memory", "action": "add", '
        '"content": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.sig"}</tool_call>'
    )
    fake = _FakeAsyncClient(response=_canned_text_block_response(content=block))
    adapter = _adapter(monkeypatch, fake)

    with caplog.at_level("WARNING", logger="mailbot_api.router.models"):
        result = await adapter.call_with_tools(
            system="sys",
            messages=[{"role": "user", "content": "remember"}],
            tools=[_tool_def()],
        )
    assert result.tool_calls == []
    decline_records = [
        r for r in caplog.records if getattr(r, "event", None) == _RESCUE_DECLINED_EVENT
    ]
    assert len(decline_records) == 1
    raw_block = getattr(decline_records[0], "raw_block", "")
    # CR F7: the logged block is the matched block, not the whole content, and
    # CR F9: the secret is redacted.
    assert "eyJhbGciOiJIUzI1NiJ9" not in raw_block
    assert "[REDACTED_BEARER]" in raw_block
    assert raw_block.startswith("<tool_call>")  # scoped to the matched block
