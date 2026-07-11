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
