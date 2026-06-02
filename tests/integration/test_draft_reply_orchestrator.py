"""Story 5-9 AC-5 — integration tests for the draft-reply chat orchestrator.

DB-real per Step 2.4.7 reframing (real migrations + real SQLite). The Router
(``ask_router``) is monkeypatched so we control the result shape per test;
``propose_action`` runs for real against the seeded DB for the accept_draft path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.chat import orchestrator as orch_mod
from mailbot_api.chat.orchestrator import (
    DraftReplyRequest,
    accept_draft,
    handle_draft_reply,
)
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.prompts.draft_reply.v1 import DraftReplyOutput
from mailbot_api.prompts.tone_style_mirror.v1 import ToneStyleMirrorOutput
from mailbot_api.router.errors import ErrorCode, RouterError, RouterResult


@pytest.fixture()
async def db_path(tmp_path: Path) -> str:
    db = tmp_path / "draft.db"
    apply_pending_migrations(str(db))
    return str(db)


async def _seed_email(
    db_path: str,
    graph_id: str,
    sensitivity: str | None,
    from_address: str = "alice@example.com",
    subject: str = "Meeting tomorrow",
    body_preview: str = "Can you make it at 2pm?",
) -> None:
    """Seed one row in emails for the orchestrator's sensitivity lookup."""
    await execute_write(
        db_path,
        (
            "INSERT INTO emails (graph_id, received_at, from_address, subject, "
            "body_preview, sensitivity, sensitivity_at, change_marker) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            graph_id,
            "2026-06-02T11:00:00Z",
            from_address,
            subject,
            body_preview,
            sensitivity,
            "2026-06-02T11:00:00Z" if sensitivity else None,
            f"cm-{graph_id}",  # propose_action requires change_marker != NULL for Tier-3
        ),
    )


def _fail_if_called(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    raise AssertionError("ask_router must NOT be called in this test")


def _make_draft_router(monkeypatch, tone_output=None, draft_output=None):
    """Helper: install a monkeypatched ask_router that returns tone then draft."""
    calls: list[dict] = []

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        if kwargs["task_type"] == "tone_style_mirror":
            return RouterResult(
                ok=True,
                output=tone_output
                or ToneStyleMirrorOutput(
                    tone_attributes=["concise", "no_emoji"],
                    signature_pattern="Best,\nAdam",
                    salutation_pattern="Hi {name},",
                ),
                model_used="claude-opus-4-7",
            )
        if kwargs["task_type"] == "draft_reply":
            return RouterResult(
                ok=True,
                output=draft_output
                or DraftReplyOutput(
                    draft_body="Confirmed — Tuesday 2pm.",
                    suggested_subject="Re: Meeting tomorrow",
                    tone_signals_used=["concise"],
                    defender_warnings=[],
                ),
                model_used="claude-opus-4-7",
            )
        raise AssertionError(f"unexpected task_type: {kwargs['task_type']!r}")

    monkeypatch.setattr(orch_mod, "ask_router", _fake)
    return calls


# ---- AC-2: sensitivity routing ----


@pytest.mark.asyncio
async def test_confidential_email_refused_no_router_call(monkeypatch, db_path: str) -> None:
    """AC-5 #1: confidential → state=confidential_refused + defender message;
    Router is NOT called."""
    await _seed_email(db_path, "g-conf", "confidential")
    monkeypatch.setattr(orch_mod, "ask_router", _fail_if_called)

    out = await handle_draft_reply(
        DraftReplyRequest(user_message="reply to that", target_email_id="g-conf"),
        db_path=db_path,
    )
    assert out.state == "confidential_refused"
    assert out.defender_message is not None
    assert "Confidential emails admit no API override" in out.defender_message
    assert out.draft_body is None


@pytest.mark.asyncio
async def test_sensitive_without_token_returns_needs_sensitivity_token(
    monkeypatch, db_path: str
) -> None:
    """AC-5 #2: sensitive without confirmation_token → needs_sensitivity_token;
    Router is NOT called."""
    await _seed_email(db_path, "g-sens", "sensitive")
    monkeypatch.setattr(orch_mod, "ask_router", _fail_if_called)

    out = await handle_draft_reply(
        DraftReplyRequest(user_message="reply", target_email_id="g-sens"),
        db_path=db_path,
    )
    assert out.state == "needs_sensitivity_token"
    assert out.defender_message is not None
    assert "/confirm" in out.defender_message
    assert "draft_reply" in out.defender_message


@pytest.mark.asyncio
async def test_sensitive_with_token_proceeds_to_dispatch(monkeypatch, db_path: str) -> None:
    """AC-5 #3: sensitive + token → Router IS called with confirmation_token
    propagated and task_type='draft_reply' eventually."""
    await _seed_email(db_path, "g-sens", "sensitive")
    calls = _make_draft_router(monkeypatch)

    out = await handle_draft_reply(
        DraftReplyRequest(
            user_message="reply",
            target_email_id="g-sens",
            confirmation_token="tok-abc",
        ),
        db_path=db_path,
    )
    assert out.state == "draft_presented"
    # Story 5-9 CR-1 fix: tone_style_mirror does NOT receive the token (it's
    # task_type-bound to draft_reply per Story 4-7 consume() semantics; passing
    # it would fail at Router consume() with a task_type mismatch). draft_reply
    # IS the privacy-sensitive call and DOES receive the token.
    for c in calls:
        if c["task_type"] == "tone_style_mirror":
            assert c["confirmation_token"] is None, (
                "tone_style_mirror MUST NOT receive the sensitivity token "
                "(Story 4-7 task_type binding would reject it)"
            )
        elif c["task_type"] == "draft_reply":
            assert c["confirmation_token"] == "tok-abc"
    assert any(c["task_type"] == "draft_reply" for c in calls)
    assert any(c["task_type"] == "tone_style_mirror" for c in calls)


@pytest.mark.asyncio
async def test_sensitive_with_token_works_when_tone_consume_would_reject_mismatched_task_type(
    monkeypatch, db_path: str
) -> None:
    """Story 5-9 CR-1 + F8: REGRESSION GUARD. Simulate Story 4-7's consume()
    semantics: a Router that rejects ANY tone_style_mirror call carrying a
    confirmation_token (task_type mismatch). If the orchestrator passes the
    draft_reply-scoped token to tone_style_mirror, this test fails — exactly
    the runtime bug F1 caught."""
    await _seed_email(db_path, "g-sens", "sensitive")

    async def _consume_aware_fake(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs["task_type"] == "tone_style_mirror":
            # Story 4-7 semantics: any token reaching tone_style_mirror is
            # rejected because the token was minted for draft_reply.
            if kwargs.get("confirmation_token") is not None:
                return RouterResult(
                    ok=False,
                    error=RouterError(
                        code=ErrorCode.NEEDS_SENSITIVITY_CONFIRMATION,
                        message="token task_type mismatch (minted for draft_reply, used for tone_style_mirror)",
                        retryable=False,
                    ),
                )
            # No token → tone_style_mirror proceeds. (Tone is NOT
            # privacy-sensitive; Router precondition layer doesn't gate it
            # the same way it gates draft_reply on a sensitive email.)
            return RouterResult(
                ok=True,
                output=ToneStyleMirrorOutput(
                    tone_attributes=["concise"],
                    signature_pattern=None,
                    salutation_pattern=None,
                ),
                model_used="claude-opus-4-7",
            )
        if kwargs["task_type"] == "draft_reply":
            # draft_reply gets the token and consumes it successfully.
            assert kwargs.get("confirmation_token") == "tok-draft"
            return RouterResult(
                ok=True,
                output=DraftReplyOutput(
                    draft_body="Confirmed.",
                    suggested_subject="Re: x",
                    tone_signals_used=["concise"],
                    defender_warnings=[],
                ),
                model_used="claude-opus-4-7",
            )
        raise AssertionError(f"unexpected task_type: {kwargs['task_type']!r}")

    monkeypatch.setattr(orch_mod, "ask_router", _consume_aware_fake)

    out = await handle_draft_reply(
        DraftReplyRequest(
            user_message="reply to that",
            target_email_id="g-sens",
            confirmation_token="tok-draft",
        ),
        db_path=db_path,
    )
    # The fix: tone_style_mirror is called WITHOUT a token; consume_aware_fake
    # returns ok; then draft_reply is called WITH the token; consume succeeds.
    assert out.state == "draft_presented"
    assert out.draft_body == "Confirmed."


# ---- AC-3: tone + draft dispatch ----


@pytest.mark.asyncio
async def test_normal_email_happy_path_produces_draft(monkeypatch, db_path: str) -> None:
    """AC-5 #4: normal email → draft_presented with body/subject populated."""
    await _seed_email(db_path, "g-norm", "normal")
    _make_draft_router(monkeypatch)

    out = await handle_draft_reply(
        DraftReplyRequest(user_message="reply to that", target_email_id="g-norm"),
        db_path=db_path,
    )
    assert out.state == "draft_presented"
    assert out.draft_body == "Confirmed — Tuesday 2pm."
    assert out.suggested_subject == "Re: Meeting tomorrow"
    assert out.tone_signals_used == ("concise",)
    assert out.defender_warnings == ()


@pytest.mark.asyncio
async def test_tone_signals_blob_skips_tone_dispatch(monkeypatch, db_path: str) -> None:
    """AC-5 #5: pre-populated tone_signals_blob → ask_router called ONCE
    (draft_reply only, not tone_style_mirror)."""
    await _seed_email(db_path, "g-norm", "normal")
    calls = _make_draft_router(monkeypatch)

    out = await handle_draft_reply(
        DraftReplyRequest(
            user_message="reply",
            target_email_id="g-norm",
            tone_signals_blob="concise, no_emoji",
        ),
        db_path=db_path,
    )
    assert out.state == "draft_presented"
    assert len(calls) == 1
    assert calls[0]["task_type"] == "draft_reply"
    # The blob propagated as-is into the draft_reply content.
    assert calls[0]["content"]["tone_signals"] == "concise, no_emoji"


# ---- AC-2 edge cases ----


@pytest.mark.asyncio
async def test_unknown_sensitivity_value_fails_closed(monkeypatch, db_path: str) -> None:
    """Story 5-9 CR-2 (F2): unknown sensitivity value (e.g., a future
    'highly_confidential') MUST refuse with confidential_refused rather than
    silently proceeding to Opus dispatch. Fail-closed defender posture."""
    await _seed_email(db_path, "g-future", "highly_confidential")
    monkeypatch.setattr(orch_mod, "ask_router", _fail_if_called)
    out = await handle_draft_reply(
        DraftReplyRequest(user_message="x", target_email_id="g-future"),
        db_path=db_path,
    )
    assert out.state == "confidential_refused"


@pytest.mark.asyncio
async def test_tone_router_returns_wrong_output_type_returns_router_error(
    monkeypatch, db_path: str
) -> None:
    """Story 5-9 CR-3 (F3): tone_style_mirror ok=True but output is the WRONG
    type → state=router_error rather than silent fallthrough with empty tone."""
    await _seed_email(db_path, "g-norm", "normal")

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs["task_type"] == "tone_style_mirror":
            # Wrong output type — DraftReplyOutput where tone expected.
            return RouterResult(
                ok=True,
                output=DraftReplyOutput(
                    draft_body="wrong shape",
                    suggested_subject="x",
                    tone_signals_used=[],
                    defender_warnings=[],
                ),
                model_used="opus",
            )
        raise AssertionError("draft_reply should not be called after tone-fail")

    monkeypatch.setattr(orch_mod, "ask_router", _fake)
    out = await handle_draft_reply(
        DraftReplyRequest(user_message="x", target_email_id="g-norm"),
        db_path=db_path,
    )
    assert out.state == "router_error"
    assert out.router_error is not None


@pytest.mark.asyncio
async def test_invalid_email_id_returns_invalid_email(monkeypatch, db_path: str) -> None:
    """AC-5 #6: unknown graph_id → invalid_email; no Router call."""
    monkeypatch.setattr(orch_mod, "ask_router", _fail_if_called)
    out = await handle_draft_reply(
        DraftReplyRequest(user_message="x", target_email_id="g-does-not-exist"),
        db_path=db_path,
    )
    assert out.state == "invalid_email"


@pytest.mark.asyncio
async def test_null_sensitivity_returns_invalid_email(monkeypatch, db_path: str) -> None:
    """AC-5 #7: sensitivity IS NULL (not yet classified) → invalid_email."""
    await _seed_email(db_path, "g-unclass", sensitivity=None)
    monkeypatch.setattr(orch_mod, "ask_router", _fail_if_called)
    out = await handle_draft_reply(
        DraftReplyRequest(user_message="x", target_email_id="g-unclass"),
        db_path=db_path,
    )
    assert out.state == "invalid_email"


@pytest.mark.asyncio
async def test_router_failure_on_draft_reply_returns_router_error(
    monkeypatch, db_path: str
) -> None:
    """AC-5 #8: draft_reply step returns ok=False → state=router_error."""
    await _seed_email(db_path, "g-norm", "normal")

    async def _fake(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs["task_type"] == "tone_style_mirror":
            return RouterResult(
                ok=True,
                output=ToneStyleMirrorOutput(
                    tone_attributes=["concise"],
                    signature_pattern=None,
                    salutation_pattern=None,
                ),
                model_used="claude-opus-4-7",
            )
        return RouterResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="opus unavailable",
                retryable=True,
            ),
        )

    monkeypatch.setattr(orch_mod, "ask_router", _fake)

    out = await handle_draft_reply(
        DraftReplyRequest(user_message="x", target_email_id="g-norm"),
        db_path=db_path,
    )
    assert out.state == "router_error"
    assert out.router_error is not None
    assert out.router_error.code is ErrorCode.PROVIDER_ERROR


# ---- AC-3 accept_draft → propose_action happy path ----


@pytest.mark.asyncio
async def test_accept_draft_writes_pending_actions_row(db_path: str) -> None:
    """AC-5 #9: accept_draft → propose_action → pending_actions row with
    action_type='send_reply', status in {cooling_off, pending}."""
    await _seed_email(db_path, "g-norm", "normal")

    out = await accept_draft(
        target_email_id="g-norm",
        draft_body="Confirmed.",
        recipient_address="alice@example.com",
        db_path=db_path,
    )
    assert out.state == "send_proposed"
    assert out.proposed_action_id is not None

    row = await fetchone(
        db_path,
        "SELECT action_type, status FROM pending_actions WHERE id = ?",
        (out.proposed_action_id,),
    )
    assert row is not None
    assert row[0] == "send_reply"
    assert row[1] in ("cooling_off", "pending")


@pytest.mark.asyncio
async def test_accept_draft_missing_recipient_returns_state(db_path: str) -> None:
    """Edge case: empty recipient_address → state=missing_recipient; no
    propose_action dispatch."""
    out = await accept_draft(
        target_email_id="g-norm",
        draft_body="Confirmed.",
        recipient_address="",
        db_path=db_path,
    )
    assert out.state == "missing_recipient"
    assert out.proposed_action_id is None


@pytest.mark.asyncio
async def test_accept_draft_refuses_empty_draft_body(db_path: str) -> None:
    """Story 5-9 CR-7 (F7): accept_draft MUST refuse empty draft_body so the
    Epic 6 drainer never sees a blank send in pending_actions.payload."""
    for empty_body in ("", "   ", "\n\n"):
        out = await accept_draft(
            target_email_id="g-norm",
            draft_body=empty_body,
            recipient_address="alice@example.com",
            db_path="anything",  # never reached — guard fires first
        )
        assert out.state == "missing_recipient", (
            f"empty draft_body={empty_body!r} must be refused"
        )
        assert out.proposed_action_id is None
