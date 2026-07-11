"""Opt-in integration test against a real Ollama container (Story 2-3 AC-9).

Gated by `MAILBOT_RUN_REAL_OLLAMA=1`. Phase 3.5 manual-verification artifact
for the latency AC (p95 ≤ 5s over 20 sequential calls per NFR-PERF-3).

Run locally with:

    docker compose up -d ollama
    docker exec mailbot-ollama ollama pull qwen2.5:3b-instruct-q4_K_M
    MAILBOT_RUN_REAL_OLLAMA=1 OLLAMA_URL=http://localhost:11434 \\
        .venv/Scripts/python.exe -m pytest tests/integration/test_ollama_adapter_real.py -v
"""

from __future__ import annotations

import json
import os
import statistics

import pytest

from mailbot_api.router.errors import ChatCompletionToolDef
from mailbot_api.router.models import (
    AdapterResponse,
    OllamaAdapter,
    ToolCallAdapterResponse,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MAILBOT_RUN_REAL_OLLAMA") != "1",
    reason="MAILBOT_RUN_REAL_OLLAMA != 1; opt-in real-Ollama test skipped",
)


def _base_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


async def test_real_ollama_replies_ok() -> None:
    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url=_base_url(),
        timeout_seconds=30.0,
    )
    result = await adapter.call(
        system="You are concise.",
        user="Reply with the word OK and nothing else.",
        max_tokens_out=8,
    )
    assert isinstance(result, AdapterResponse)
    assert "OK" in result.text.upper()
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert result.latency_ms > 0


async def test_real_ollama_p95_latency_under_5s_for_short_replies() -> None:
    """NFR-PERF-3: Qwen 3B p95 ≤ 5s on 2-vCPU CPU-only.

    Note: dev hosts vary; this test asserts the wire-level p95 ≤ 5000ms.
    Failure on a beefy dev box doesn't mean prod will fail; failure on a
    2-vCPU VPS smoke environment is meaningful.
    """
    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url=_base_url(),
        timeout_seconds=30.0,
    )
    latencies_ms: list[int] = []
    for _ in range(20):
        result = await adapter.call(
            system="You are concise.",
            user="Reply with the word OK and nothing else.",
            max_tokens_out=8,
        )
        latencies_ms.append(result.latency_ms)

    p95 = statistics.quantiles(latencies_ms, n=20)[-1]
    assert p95 <= 5000, f"p95 latency {p95}ms exceeded 5000ms target"


async def test_real_ollama_tool_call_exact_argument_fidelity() -> None:
    """Story AI-1: drive the REAL inference surface for a tool call and assert
    exact argument fidelity at temperature 0 on a Graph-style id.

    Skipped without a live Ollama (same MAILBOT_RUN_REAL_OLLAMA=1 gate as the
    other real tests). Mirrors the AI-1 probe's load-bearing finding: temp 0 is
    6/6 exact including long ids.
    """
    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url=_base_url(),
        timeout_seconds=30.0,
    )
    graph_id = "AAMkAGI1AAAt3AABGAAAAAABQ8h1i_QeRZ2GJHu8mMj7Bw="
    archive_tool = ChatCompletionToolDef.model_validate(
        {
            "type": "function",
            "function": {
                "name": "archive_email",
                "description": "Archive an email by its id.",
                "parameters": {
                    "type": "object",
                    "properties": {"email_id": {"type": "string"}},
                    "required": ["email_id"],
                },
            },
        }
    )
    result = await adapter.call_with_tools(
        system="You archive emails by calling the archive_email tool.",
        messages=[{"role": "user", "content": f"Archive the email with id {graph_id}."}],
        tools=[archive_tool],
    )
    assert isinstance(result, ToolCallAdapterResponse)
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.function.name == "archive_email"
    parsed = json.loads(tc.function.arguments)
    assert parsed["email_id"] == graph_id  # exact — no digit transposition
