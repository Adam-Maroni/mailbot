"""Story 5-8 AC-6 — integration tests for the reference-resolution orchestrator.

These tests cover the builder contract, the validation-refuses-without-dispatch
paths, the happy / ambiguous / Router-failure paths, the cold-start memory case,
and the router_calls audit-row write on dispatch.

The Router itself is monkeypatched (via ``mailbot_api.chat.reference.ask_router``)
for control over the result shape. The full-Router integration is covered
elsewhere; THIS module's surface is the builder + the orchestrator's
verdict-handling logic.
"""

from __future__ import annotations

import pytest

from mailbot_api.chat import reference as ref_mod
from mailbot_api.chat.reference import (
    DiscordTurn,
    ReferenceContext,
    ReferenceResolutionResult,
    build_reference_resolution_content,
    resolve_reference,
)
from mailbot_api.prompts.reference_resolution.v1 import ReferenceResolutionOutput
from mailbot_api.router.errors import ErrorCode, RouterError, RouterResult
from mailbot_api.verbs.schemas import EmailProjection


def _turn(role: str, content: str, at: str = "2026-06-02T12:00:00Z") -> DiscordTurn:
    return DiscordTurn(role=role, content=content, at=at)  # type: ignore[arg-type]


def _projection(email_id: str, subject: str = "subj", sender: str = "a@x.com") -> EmailProjection:
    return EmailProjection(
        email_id=email_id,
        received_at="2026-06-02T11:00:00Z",
        from_address=sender,
        subject=subject,
        class_coarse="human",
    )


# ---- AC-1 / AC-2 builder tests ----


def test_builder_returns_three_documented_placeholders() -> None:
    """AC-6 #1: keys match the Story 5-3 USER_TEMPLATE placeholders exactly."""
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "draft a reply to that one"),),
        candidate_projections=(_projection("g-1"),),
    )
    content = build_reference_resolution_content(ctx)
    assert set(content.keys()) == {"user_message", "recent_context", "candidate_projections"}


def test_builder_user_message_picks_last_user_turn() -> None:
    """The user_message field reflects the most recent user turn (skipping
    later assistant turns if any)."""
    ctx = ReferenceContext(
        recent_turns=(
            _turn("user", "what's important today?"),
            _turn("assistant", "here are 3 emails..."),
            _turn("user", "draft a reply to the second one"),
        ),
    )
    content = build_reference_resolution_content(ctx)
    assert content["user_message"] == "draft a reply to the second one"


def test_builder_cold_start_memory_omits_separator() -> None:
    """AC-6 #7: relevant_senders_memory=None produces NO separator line."""
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "hello"),),
        relevant_senders_memory=None,
    )
    content = build_reference_resolution_content(ctx)
    assert "--- relevant_senders ---" not in content["recent_context"]


def test_builder_memory_appended_with_separator() -> None:
    """memory_blob arrives after a separator line on recent_context."""
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "hi"),),
        relevant_senders_memory="alice is my lawyer; bob is my CPA",
    )
    content = build_reference_resolution_content(ctx)
    assert "--- relevant_senders ---" in content["recent_context"]
    assert "alice is my lawyer" in content["recent_context"]


def test_builder_sender_summaries_appended_with_separator() -> None:
    """AC-6 #8: non-empty sender_summaries get a separator and appear in
    candidate_projections."""
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "summarize"),),
        candidate_projections=(_projection("g-1"),),
        sender_summaries=("alice@x.com: known business contact", "bob@y.com: newsletter"),
    )
    content = build_reference_resolution_content(ctx)
    assert "--- sender_summaries ---" in content["candidate_projections"]
    assert "alice@x.com: known business contact" in content["candidate_projections"]


def test_builder_sender_summaries_without_projections_no_leading_newline() -> None:
    """CR-4 regression: candidate_projections empty + sender_summaries non-empty
    used to produce a leading '\\n' before the '--- sender_summaries ---' line.
    Fix asserts the string never starts with newline."""
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "summarize"),),
        candidate_projections=(),
        sender_summaries=("alice@x.com: known business contact",),
    )
    content = build_reference_resolution_content(ctx)
    assert not content["candidate_projections"].startswith("\n"), (
        f"leading newline leaked: {content['candidate_projections']!r}"
    )
    assert content["candidate_projections"].startswith("--- sender_summaries ---")


def test_builder_projection_with_null_fields_uses_unknown_sentinels() -> None:
    """CR-3 fix: nullable EmailProjection fields render as 'unknown' instead
    of Python's literal 'None', so the LLM sees readable context."""
    null_proj = EmailProjection(
        email_id="g-null",
        received_at="2026-06-02T11:00:00Z",
        from_address=None,
        subject=None,
        class_coarse=None,
    )
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "what about that?"),),
        candidate_projections=(null_proj,),
    )
    content = build_reference_resolution_content(ctx)
    line = content["candidate_projections"]
    # No 'None' / "None" / =None substrings in the rendered projection.
    assert "None" not in line, f"None leaked into LLM context: {line!r}"
    # The 'unknown' sentinel appears for from + class.
    assert "from=unknown" in line
    assert "class=unknown" in line
    # subject='unknown' (repr-quoted by design).
    assert "subject='unknown'" in line


# ---- AC-3 validation-refuses-without-dispatch ----


@pytest.mark.asyncio
async def test_empty_context_refuses_without_dispatch(monkeypatch) -> None:
    """AC-6 #2: empty recent_turns → ambiguous=True + no Router call."""
    dispatch_calls: list[tuple] = []  # noqa: UP006 — runtime tuple type is fine

    async def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        dispatch_calls.append((args, kwargs))
        raise AssertionError("ask_router should not be called for empty context")

    monkeypatch.setattr(ref_mod, "ask_router", _spy)
    out = await resolve_reference(
        ReferenceContext(recent_turns=()), db_path=":memory:"
    )
    assert isinstance(out, ReferenceResolutionResult)
    assert out.ok is False
    assert out.ambiguous is True
    assert out.router_call_id is None
    assert out.resolved_email_ids == ()
    assert dispatch_calls == []


@pytest.mark.asyncio
async def test_last_turn_not_user_refuses_without_dispatch(monkeypatch) -> None:
    """AC-6 #3: most recent turn is an assistant turn → refuse."""

    async def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("ask_router should not be called when last turn is assistant")

    monkeypatch.setattr(ref_mod, "ask_router", _spy)
    ctx = ReferenceContext(
        recent_turns=(
            _turn("user", "hi"),
            _turn("assistant", "hello"),
        )
    )
    out = await resolve_reference(ctx, db_path=":memory:")
    assert out.ok is False
    assert out.ambiguous is True


# ---- AC-3 happy path / Router result handling ----


@pytest.mark.asyncio
async def test_happy_path_returns_router_resolved_ids(monkeypatch) -> None:
    """AC-6 #4: a Router-returned RouterResult with parsed output flows through."""
    fake_output = ReferenceResolutionOutput(
        resolved_email_ids=["g-1"],
        reasoning="matches sender",
        confidence=0.8,
        ambiguous=False,
    )

    async def _fake_ask_router(**kwargs):  # type: ignore[no-untyped-def]
        # Sanity-check key args propagate.
        assert kwargs["task_type"] == "reference_resolution"
        assert kwargs["email_id"] is None
        assert "user_message" in kwargs["content"]
        return RouterResult(
            ok=True,
            output=fake_output,
            cost_usd=0.001,
            latency_ms=120,
            tokens_in=50,
            tokens_out=20,
            model_used="qwen2.5:3b",
        )

    monkeypatch.setattr(ref_mod, "ask_router", _fake_ask_router)
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "show me the email from alice"),),
        candidate_projections=(_projection("g-1", subject="hi", sender="alice@x.com"),),
    )
    out = await resolve_reference(ctx, db_path=":memory:")
    assert out.ok is True
    assert out.resolved_email_ids == ("g-1",)
    assert out.ambiguous is False
    assert out.reasoning == "matches sender"
    assert out.confidence == 0.8
    assert out.error is None


@pytest.mark.asyncio
async def test_ambiguous_result_passes_through(monkeypatch) -> None:
    """AC-6 #5: ambiguous=True from the Router output is preserved verbatim."""
    fake_output = ReferenceResolutionOutput(
        resolved_email_ids=["g-1", "g-2"],
        reasoning="two senders named marc",
        confidence=0.6,
        ambiguous=True,
    )

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        return RouterResult(ok=True, output=fake_output, model_used="qwen")

    monkeypatch.setattr(ref_mod, "ask_router", _fake)
    ctx = ReferenceContext(recent_turns=(_turn("user", "the one from marc"),))
    out = await resolve_reference(ctx, db_path=":memory:")
    assert out.ok is True  # parsing succeeded
    assert out.ambiguous is True
    assert out.resolved_email_ids == ("g-1", "g-2")


@pytest.mark.asyncio
async def test_router_failure_returns_ambiguous_with_error(monkeypatch) -> None:
    """AC-6 #6 + #10: Router ok=False → ok=False + ambiguous=True + error set."""
    err = RouterError(
        code=ErrorCode.PROVIDER_ERROR,
        message="router paused",
        model_attempted=["qwen2.5:3b"],
        retryable=True,
    )

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        return RouterResult(ok=False, error=err)

    monkeypatch.setattr(ref_mod, "ask_router", _fake)
    ctx = ReferenceContext(recent_turns=(_turn("user", "anything new?"),))
    out = await resolve_reference(ctx, db_path=":memory:")
    assert out.ok is False
    assert out.ambiguous is True
    assert out.resolved_email_ids == ()
    assert out.error is not None
    assert out.error.code is ErrorCode.PROVIDER_ERROR
    # AC-6 #10: reasoning is sanitized — no raw error type leakage.
    assert "router paused" in out.reasoning


@pytest.mark.asyncio
async def test_router_ok_but_no_output_collapses_to_ambiguous(monkeypatch) -> None:
    """Defensive: Router ok=True with output=None → graceful ambiguous.

    Uses ``RouterResult.model_construct`` to bypass the
    ``_check_ok_error_consistency`` validator, which would otherwise reject
    ``ok=True, output=None, error=None``. If a future Router bug regresses the
    invariant, this orchestrator's no-output defensive branch still produces a
    graceful ambiguous result instead of crashing.
    """

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        return RouterResult.model_construct(ok=True, output=None, error=None)

    monkeypatch.setattr(ref_mod, "ask_router", _fake)
    ctx = ReferenceContext(recent_turns=(_turn("user", "hi"),))
    out = await resolve_reference(ctx, db_path=":memory:")
    assert out.ok is False
    assert out.ambiguous is True
    assert "no output" in out.reasoning


# ---- AC-5 router_calls audit-row sanity ----


@pytest.mark.asyncio
async def test_dispatch_calls_ask_router_with_correct_task_type(monkeypatch) -> None:
    """AC-6 #9: the orchestrator dispatches with task_type='reference_resolution'.
    Epic 7's sampler queries router_calls by exactly that string."""
    captured = {}

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return RouterResult(
            ok=True,
            output=ReferenceResolutionOutput(
                resolved_email_ids=["g-1"],
                reasoning="ok",
                confidence=0.9,
                ambiguous=False,
            ),
            model_used="qwen",
        )

    monkeypatch.setattr(ref_mod, "ask_router", _fake)
    ctx = ReferenceContext(
        recent_turns=(_turn("user", "draft a reply"),),
        candidate_projections=(_projection("g-1"),),
    )
    await resolve_reference(ctx, db_path=":memory:", caller_origin="chat-orchestrator")
    assert captured["task_type"] == "reference_resolution"
    assert captured["caller_origin"] == "chat-orchestrator"
    assert captured["email_id"] is None


# AC-6 #10 covered above by test_router_failure_returns_ambiguous_with_error.
