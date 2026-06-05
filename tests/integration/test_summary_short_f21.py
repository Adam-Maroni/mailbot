"""Story 6-14 F21 regression tests: summary_short Haiku call must succeed when
the model emits valid JSON and must continue to fail on prose-only output.

Background: F21 root cause was prompt-side drift — `summary_short/v1.py`'s
SYSTEM block was the only ingest-task prompt missing the standard "Reply with
valid JSON matching the schema" instruction every sibling carries. Haiku
literally obeyed the original instruction ("write a one-line summary"),
returned prose, and `model_validate_json` rejected every call. Every router
call ended `outcome=failed` with non-zero cost (~$0.001 per call, both legs
billed) until Story 6-14 patched the SYSTEM block.

The tests below lock the fix in three layers:

  (1) **Structural**: assert `summary_short` SYSTEM contains the JSON-output
      instruction substring. Prevents future authors from accidentally
      removing it again.
  (2) **Router happy path (AC-3)**: a JSON `{"summary": "..."}` response from
      a fake adapter yields `outcome="ok"` on the first leg (no retry
      consumed) when ask_router dispatches a `summary_short` task. This is
      the F21 fix's contract: well-instructed Haiku produces JSON; router
      accepts it cleanly.
  (3) **Router F21-shape counter-test**: a prose-only response (the F21
      production failure shape) on BOTH legs yields `outcome="failed"` with
      `SCHEMA_VALIDATION_FAILED`. Locks in the failure path so a future
      author cannot accidentally relax `model_validate_json` to accept
      prose-with-no-JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import fetchall, fetchone
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

_HAIKU = "claude-haiku-4-5-20251001"


class _FakeAdapter:
    """Scripted adapter — yields each response in `responses` per call."""

    def __init__(self, model_id: str, responses: list[str]) -> None:
        self.model_id = model_id
        self.responses = list(responses)
        self.call_log: list[dict[str, Any]] = []

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        self.call_log.append({"system": system, "user": user})
        if not self.responses:
            raise RuntimeError("FakeAdapter exhausted")
        text = self.responses.pop(0)
        return AdapterResponse(
            text=text,
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=30,
            raw={"mock": True},
        )


_POLICY_YAML = f"""\
version: "test-summary-short-f21-v1"

tasks:
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 384
    lane: "batch"
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


def _content() -> dict[str, str]:
    return {
        "subject": "Re: Tuesday review",
        "sender": "sarah@example.com",
        "body_preview": "Moving the meeting from Friday 3pm to Tuesday 2pm. Let me know.",
    }


# ---------- Layer 1: structural lock-in (no router needed) ----------


def test_summary_short_system_block_instructs_json_output() -> None:
    """F21 structural regression: SYSTEM must contain the JSON-output instruction.

    Every other ingest-task prompt (coarse_class, fine_class, sensitivity_class,
    importance_scoring, action_extraction) carries some variant of "Reply with
    valid JSON matching the schema; no preamble". `summary_short` was the
    sole drift case prior to Story 6-14. This test locks the contract so a
    future edit that strips the JSON instruction is caught at test time, not
    after a week of paying for failed Haiku calls.
    """
    from mailbot_api.prompts.summary_short.v1 import SYSTEM

    assert "valid JSON" in SYSTEM, (
        "summary_short SYSTEM must instruct the model to emit valid JSON — "
        "removing this instruction causes F21 to recur. See Story 6-14 Dev Notes."
    )
    assert "no preamble" in SYSTEM or "no commentary" in SYSTEM, (
        "summary_short SYSTEM must forbid preamble / commentary so Haiku does "
        "not wrap JSON in prose framing that fails model_validate_json."
    )


# ---------- Layer 2: router happy path (AC-3 positive) ----------


async def test_summary_short_with_valid_json_response_yields_outcome_ok(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-3: a Haiku response shaped as `{"summary": "..."}` (which the post-fix
    SYSTEM prompt instructs) succeeds on the first leg.

    Pre-fix, this same test would also pass — the failure mode was about the
    PROMPT not eliciting JSON, not about the router's ability to accept JSON.
    But asserting the happy path here ensures we have a positive test on
    the summary_short → ask_router → router_calls.outcome="ok" path that
    didn't exist before Story 6-14.
    """
    db_path = _setup(tmp_path)
    adapter = _FakeAdapter(
        _HAIKU,
        [json.dumps({"summary": "Sarah moves Friday 3pm meeting to Tuesday 2pm."})],
    )
    register_adapter(_HAIKU, adapter)

    result = await ask_router(
        task_type="summary_short",
        content=_content(),
        db_path=db_path,
    )

    assert result.ok is True, f"expected ok=True, got error={result.error}"
    assert result.output is not None
    # CR-3: explicitly assert the summary content — empty-string would satisfy
    # `Field(max_length=280)` so a FakeAdapter returning `{"summary": ""}` would
    # silently green-light an empty cached summary into `emails.summary_short`.
    # Lock the content contract so future drift in result.output extraction or
    # `_extract_value_and_confidence` (pipeline.py:122-123) is caught.
    assert result.output.summary == "Sarah moves Friday 3pm meeting to Tuesday 2pm."  # type: ignore[attr-defined]
    # Exactly one adapter call — no retry leg consumed (JSON parsed cleanly).
    assert len(adapter.call_log) == 1

    row = await fetchone(db_path, "SELECT outcome, model_chosen FROM router_calls", ())
    assert row == ("ok", _HAIKU)


# ---------- Layer 3: F21-shape counter-test (AC-3 counter) ----------


async def test_summary_short_with_prose_response_still_fails_with_schema_validation_error(
    tmp_path: Path, _clean_state: Any
) -> None:
    """F21 reproducer (counter-test): if a model emits prose (no JSON) for both
    the first and retry leg — the exact production failure shape — the router
    MUST yield `outcome="failed"` with `SCHEMA_VALIDATION_FAILED` and write the
    audit row. This locks in two contracts:

      (a) The router's `model_validate_json` boundary is not silently weakened
          to accept prose (which would mask future regressions of F21's shape).
      (b) The retry leg's stricter-JSON prefix is still applied — visible as
          "valid JSON matching this schema" appearing in `adapter.call_log[1]`'s
          user message.

    This is the canonical F21 failure trace: every router_calls row at ids
    389/392/396/.../425 looked exactly like this (outcome=failed, both legs
    billed, no escalation per policy.yaml).
    """
    db_path = _setup(tmp_path)
    # Both legs return prose — the F21 production shape.
    adapter = _FakeAdapter(
        _HAIKU,
        [
            "Sarah moves Friday 3pm meeting to Tuesday 2pm.",
            "Sarah moves Friday 3pm meeting to Tuesday 2pm.",
        ],
    )
    register_adapter(_HAIKU, adapter)

    result = await ask_router(
        task_type="summary_short",
        content=_content(),
        db_path=db_path,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SCHEMA_VALIDATION_FAILED

    # Retry leg fired (router.py:622) — second call's user prompt carries the
    # stricter-JSON prefix. This locks in the contract that the retry leg
    # remains the second line of defense against schema-shaped drift.
    assert len(adapter.call_log) == 2
    assert "valid JSON matching this schema" in adapter.call_log[1]["user"]

    # CR-2: assert the billing consequence — this is the LITERAL F21 contract
    # ("outcome=failed DESPITE BILLING"). The economic harm of F21 was non-zero
    # `cost_usd_estimated` on failed calls. The router accumulates BOTH legs'
    # cost via estimate_cost_usd() at router.py:589 + :643 and writes the sum
    # via record_router_call(). A future change that stopped accumulating
    # retry-leg costs in the audit row would silently restore the F21
    # economic-harm shape (failure without billing visibility); this assertion
    # locks the contract that failed calls record the FULL accumulated cost.
    rows = await fetchall(
        db_path,
        "SELECT outcome, model_chosen, cost_usd_estimated FROM router_calls",
        (),
    )
    assert len(rows) == 1
    assert rows[0][0] == "failed"
    assert rows[0][1] == _HAIKU
    assert rows[0][2] > 0, (
        "cost_usd_estimated must be > 0 on a failed-after-billing call — this "
        "is the literal F21 contract (outcome=failed DESPITE BILLING). Both "
        "adapter legs returned scripted token counts so estimate_cost_usd "
        "should produce a positive sum on the audit row."
    )


# ---------- Layer 4: AC-3 literal — recorded Haiku response via httpx.MockTransport ----------


async def test_summary_short_recorded_haiku_response_via_mocktransport_yields_outcome_ok(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-3 literal: 'a test asserts the success path against a recorded real
    Anthropic response (Story 6-11 pattern via `httpx.MockTransport`)'.

    Layers 2 + 3 above use `_FakeAdapter` to exercise the router's
    schema-validation contract directly — the canonical project pattern for
    router-level schema-validation tests. This layer honors AC-3's literal
    wording by exercising the FULL stack through `AnthropicAdapter` via
    `httpx.MockTransport`: a recorded-shape Anthropic Messages API response
    is fed to the real `AnthropicAdapter.call()` (HTTP serialization, response
    parsing, cache-tag handling, usage extraction) which then routes through
    `ask_router` (schema validation, audit-row write).

    The recorded response shape is byte-identical to what the live Anthropic
    API returns for a post-fix Haiku `summary_short` call: a `content[0].text`
    field containing the JSON literal `{"summary": "..."}` as Haiku will
    produce when the SYSTEM block instructs JSON output.

    CR-1 closure: where _FakeAdapter tests the router's schema-validation
    boundary, this test catches HTTP-layer parsing bugs in AnthropicAdapter
    that a `_FakeAdapter` would silently bypass (e.g., the Anthropic SDK
    upgrade that bricked Story 2-6's cached_tokens_in handling, or a
    response.text extraction drift on multi-block content arrays).
    """
    import anthropic
    import httpx

    from mailbot_api.router.models import AnthropicAdapter

    db_path = _setup(tmp_path)

    # Recorded-shape mock: Anthropic Messages API success response carrying
    # the JSON literal `{"summary": "..."}` in content[0].text (the shape
    # Haiku produces post-fix when SYSTEM instructs JSON output).
    recorded_summary = '{"summary": "Sarah moves Friday 3pm meeting to Tuesday 2pm."}'
    captured_requests: list[httpx.Request] = []

    def _haiku_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "msg_01f21regression",
                "type": "message",
                "role": "assistant",
                "model": _HAIKU,
                "content": [{"type": "text", "text": recorded_summary}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 716,  # matches F21 reference row id=389
                    "output_tokens": 48,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        )

    transport = httpx.MockTransport(_haiku_handler)
    client = anthropic.AsyncClient(
        api_key="test-key-f21",
        http_client=httpx.AsyncClient(
            transport=transport,
            base_url="https://api.anthropic.com",
        ),
    )
    real_anthropic_adapter = AnthropicAdapter(
        model_id=_HAIKU, client=client, timeout_seconds=60.0
    )
    # Register the REAL AnthropicAdapter (not a FakeAdapter) so the router
    # exercises the full SDK request-serialization + response-parsing path.
    register_adapter(_HAIKU, real_anthropic_adapter)

    result = await ask_router(
        task_type="summary_short",
        content=_content(),
        db_path=db_path,
    )

    # Schema validation passes — recorded Haiku JSON parses as SummaryShortOutput.
    assert result.ok is True, f"expected ok=True, got error={result.error}"
    assert result.output is not None
    assert result.output.summary == (  # type: ignore[attr-defined]
        "Sarah moves Friday 3pm meeting to Tuesday 2pm."
    )

    # Exactly one HTTP request — first-leg success means no retry-leg fired.
    assert len(captured_requests) == 1
    # Sanity: the request body carried the patched SYSTEM with the JSON
    # instruction — confirms the prompt registry surfaced the post-fix prompt
    # via resolve_prompt() → ask_router's prompt-render pipeline.
    body = json.loads(captured_requests[0].content)
    system_text = body["system"][0]["text"]
    assert "valid JSON" in system_text, (
        "AnthropicAdapter must receive the post-fix SYSTEM (with JSON "
        "instruction) in the wire request. If this assertion fails, the "
        "prompt-registry → router → adapter pipeline is bypassing the patched "
        "SYSTEM block, which would silently restore F21."
    )

    # Audit row recorded as ok + non-zero cost (tokens were consumed).
    row = await fetchone(
        db_path,
        "SELECT outcome, model_chosen, cost_usd_estimated FROM router_calls",
        (),
    )
    assert row is not None
    assert row[0] == "ok"
    assert row[1] == _HAIKU
    assert row[2] > 0, "ok-outcome rows must record positive cost when tokens were consumed"
