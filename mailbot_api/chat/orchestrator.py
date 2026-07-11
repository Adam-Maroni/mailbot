"""Draft-reply chat orchestrator — Story 5-9 (Epic 5 capstone).

Wires the conversational draft-reply flow on the mailbot-api side:

  1. Look up target email's sensitivity (Story 3-3 precondition layer mirror at
     the chat surface — refuse confidential and require token for sensitive
     BEFORE dispatching the Router).
  2. Optionally dispatch ``tone_style_mirror`` (Story 5-3) when the caller has
     no pre-fetched tone signals; the caller is responsible for response-cache
     hits.
  3. Dispatch ``draft_reply`` (Story 5-3, Opus-bound per FR-4.4).
  4. Return the draft + defender warnings to the caller (Hermes / chat surface)
     which surfaces the send/refine/cancel choice to the user.
  5. On user "send" confirmation, ``accept_draft`` invokes
     ``propose_action(SEND_REPLY)`` which writes the pending_actions row and
     starts Story 4-6's cooling-off ticker.

**Epic 6 dependency (Adam-decided, retro 2026-06-02):** the drainer is not
wired into ``mailbot_api/worker.py`` until Story 6-6. This orchestrator
validates UP TO the cooling-off transition; full end-to-end Outlook send +
Graph adapter dispatch is validated in Epic 6, NOT here. Do NOT add drainer
wiring code in this story.

This orchestrator is the verb-side counterpart to the Hermes-side chat
client. Hermes calls into mailbot-api via the OpenAI-compatible chat
completions endpoint (Story 2-10) for inference; this orchestrator
coordinates the verb surface for the action side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import EMAIL_SENSITIVITY_BY_GRAPH_ID
from mailbot_api.prompts.draft_reply.v1 import DraftReplyOutput
from mailbot_api.prompts.tone_style_mirror.v1 import ToneStyleMirrorOutput
from mailbot_api.router import ask_router
from mailbot_api.router.errors import ErrorCode, RouterError, RouterResult
from mailbot_api.verbs.propose_action import propose_action

# Defender-tone canonical strings — pinned in Story 5-5's SOUL.md / SKILL.md.
_CONFIDENTIAL_REFUSAL = (
    "Confidential emails admit no API override. The body stays on your VPS, period."
)
_SENSITIVE_ESCALATION_PROMPT = (
    "This email is sensitive. Say 'yes, escalate' to authorize an API draft "
    "for this one email (single-use, 10-min token)."
)


@dataclass(frozen=True)
class DraftReplyRequest:
    """Inputs to ``handle_draft_reply``.

    ``user_message`` is the most recent user Discord turn that triggered the
    draft. The CALLER is responsible for running Story 5-7's ``redact()`` on
    this string before constructing the request — the orchestrator does NOT
    re-redact (idempotent + cheap, but staying inside the layer of
    responsibility from architecture).

    ``target_email_id`` is the resolved Graph message id (typically from
    Story 5-8's ``resolve_reference``).

    ``tone_signals_blob`` is an optional pre-fetched tone-style fingerprint.
    When None the orchestrator dispatches ``tone_style_mirror``; when populated
    that step is skipped. The Hermes-side caller (or Epic 6's wiring) is
    responsible for the response-cache layer.

    ``confirmation_token`` is the sensitivity confirmation token from Story
    4-7's ``mint_sensitivity_token`` — required when the email is sensitive
    and the user already confirmed via the recognized phrase 'yes, escalate'
    (Story 10-5-6; the old '/confirm' slash form never reached the agent,
    F-10-5-1).
    """

    user_message: str
    target_email_id: str
    tone_signals_blob: str | None = None
    confirmation_token: str | None = None


@dataclass(frozen=True)
class DraftReplyOutcome:
    """Result of ``handle_draft_reply`` or ``accept_draft``.

    ``state`` is the load-bearing field — the chat surface (Hermes) inspects
    it to decide what to surface to the user.

    For the "draft_presented" state the draft + subject + tone signals +
    defender warnings are populated and the chat surface presents the
    [send / refine / cancel] choice.

    For "confidential_refused" / "needs_sensitivity_token" the
    ``defender_message`` carries the exact text to surface.

    For "router_error" ``router_error`` carries the structured error for
    forensics; ``defender_message`` may also be populated with a
    user-facing apology / clarifying turn.

    For "invalid_email" / "missing_recipient" the chat surface surfaces a
    clarifying turn rather than dispatching anything.
    """

    state: Literal[
        "draft_presented",
        "confidential_refused",
        "needs_sensitivity_token",
        "router_error",
        "invalid_email",
        "missing_recipient",
        "send_proposed",
    ]
    draft_body: str | None = None
    suggested_subject: str | None = None
    tone_signals_used: tuple[str, ...] = ()
    defender_warnings: tuple[str, ...] = ()
    defender_message: str | None = None
    proposed_action_id: int | None = None
    router_error: RouterError | None = None


async def _lookup_email_sensitivity(
    db_path: str, target_email_id: str
) -> tuple[str | None, str | None, str | None, str | None] | None:
    """Return (sensitivity, subject, body_preview, from_address) or None when
    the email is not found / soft-deleted."""
    row = await fetchone(
        db_path, EMAIL_SENSITIVITY_BY_GRAPH_ID, (target_email_id,)
    )
    if row is None:
        return None
    return (row[0], row[1], row[2], row[3])


def _result_error(result: RouterResult) -> RouterError | None:
    """Defensive accessor: per RouterResult contract ok=False ⇒ error is not
    None; return as-is for the caller to handle."""
    return result.error


async def handle_draft_reply(
    req: DraftReplyRequest,
    *,
    db_path: str,
    caller_origin: str = "chat-orchestrator",
) -> DraftReplyOutcome:
    """Run the prepare-draft phase: sensitivity routing → tone → draft."""
    # AC-2: chat-surface sensitivity gate.
    lookup = await _lookup_email_sensitivity(db_path, req.target_email_id)
    if lookup is None:
        return DraftReplyOutcome(state="invalid_email")
    sensitivity, subject, body_preview, from_address = lookup

    # Treat NULL sensitivity as invalid here — Story 3-3's precondition layer
    # would refuse anyway; the chat surface gets a clearer signal.
    if sensitivity is None:
        return DraftReplyOutcome(state="invalid_email")

    # Story 5-9 CR-2 (F2) — fail-closed allowlist instead of blocklist.
    # Only "normal" and "sensitive" (with a confirmation token) proceed; any
    # other value (current confidential, future highly_confidential / pii / etc.)
    # is refused with the confidential message. Defender posture wins.
    if sensitivity == "confidential":
        return DraftReplyOutcome(
            state="confidential_refused",
            defender_message=_CONFIDENTIAL_REFUSAL,
        )

    if sensitivity == "sensitive" and req.confirmation_token is None:
        return DraftReplyOutcome(
            state="needs_sensitivity_token",
            defender_message=_SENSITIVE_ESCALATION_PROMPT,
        )

    if sensitivity not in ("normal", "sensitive"):
        # Unknown sensitivity value — refuse with the confidential message to
        # fail closed. Story 5-5's SOUL.md "when in doubt, choose the quieter
        # option" tiebreaker informs this default.
        return DraftReplyOutcome(
            state="confidential_refused",
            defender_message=_CONFIDENTIAL_REFUSAL,
        )

    # AC-3: tone_style_mirror (optional) then draft_reply.
    #
    # Story 5-9 CR-4 (F4) — semantics: tone_signals_blob is None → dispatch
    # tone_style_mirror. An empty STRING is treated as "caller has pre-fetched
    # signals (cold-start)" — the orchestrator does NOT dispatch tone_style_mirror
    # in that case. Callers that want "dispatch tone" use None; callers that
    # know there are no tone signals available (first contact with recipient)
    # use "".
    tone_signals_str = req.tone_signals_blob if req.tone_signals_blob is not None else ""
    if req.tone_signals_blob is None:
        # Dispatch tone_style_mirror. Epic 6 wires the full prior-emails-sample
        # fetcher; for this story we pass a placeholder + the recipient.
        #
        # Story 5-9 CR-1 (F1) — DO NOT pass `confirmation_token` here. Sensitivity
        # tokens are task_type-bound (Story 4-7 consume() checks task_type
        # equality); the user-confirmed token is scoped to `draft_reply`. Passing
        # it to a tone_style_mirror Router call would fail consume() with a
        # task_type mismatch and the Router would return
        # NEEDS_SENSITIVITY_CONFIRMATION, breaking every sensitive draft where
        # tone signals aren't pre-cached.
        #
        # Privacy rationale: tone_style_mirror is NOT the privacy-sensitive
        # operation. It receives a recipient address + (Epic-6-wired) prior
        # emails sample — nothing from THIS email. draft_reply IS the sensitive
        # operation because it consumes the source email's body. Only
        # draft_reply needs the token.
        tone_result = await ask_router(
            task_type="tone_style_mirror",
            content={
                "recipient_address": from_address or "",
                "prior_emails_sample": "",
            },
            db_path=db_path,
            caller_origin=caller_origin,
            email_id=req.target_email_id,
            confirmation_token=None,  # CR-1 fix; see comment above.
        )
        if not tone_result.ok:
            return DraftReplyOutcome(
                state="router_error", router_error=_result_error(tone_result)
            )
        tone_output = tone_result.output
        if isinstance(tone_output, ToneStyleMirrorOutput):
            tone_signals_str = ", ".join(tone_output.tone_attributes)
        else:
            # Story 5-9 CR-3 (F3) fix: Router-internal contract violation —
            # surface as router_error rather than silently falling through to
            # an empty-tone draft.
            return DraftReplyOutcome(
                state="router_error",
                router_error=RouterError(
                    code=ErrorCode.PROVIDER_ERROR,
                    message="tone_style_mirror output is not a ToneStyleMirrorOutput",
                    retryable=False,
                ),
            )

    # Dispatch draft_reply.
    draft_result = await ask_router(
        task_type="draft_reply",
        content={
            "source_email": (
                f"Subject: {subject or ''}\n"
                f"From: {from_address or ''}\n"
                f"Body: {body_preview or ''}"
            ),
            "thread_context": "",  # Epic 6 wires thread hydration.
            "tone_signals": tone_signals_str,
        },
        db_path=db_path,
        caller_origin=caller_origin,
        email_id=req.target_email_id,
        confirmation_token=req.confirmation_token,
    )
    if not draft_result.ok:
        return DraftReplyOutcome(
            state="router_error", router_error=_result_error(draft_result)
        )

    draft_output = draft_result.output
    if not isinstance(draft_output, DraftReplyOutput):
        # Story 5-9 CR-6 (F6) fix: removed the dead `if False else` branch.
        # Router-internal contract violation — defensive fallback.
        return DraftReplyOutcome(
            state="router_error",
            router_error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="draft_reply output not a DraftReplyOutput",
                retryable=False,
            ),
        )

    return DraftReplyOutcome(
        state="draft_presented",
        draft_body=draft_output.draft_body,
        suggested_subject=draft_output.suggested_subject,
        tone_signals_used=tuple(draft_output.tone_signals_used),
        defender_warnings=tuple(draft_output.defender_warnings),
    )


async def accept_draft(
    target_email_id: str,
    draft_body: str,
    recipient_address: str,
    *,
    db_path: str,
) -> DraftReplyOutcome:
    """Run the user's "send" confirmation: propose SEND_REPLY → cooling_off.

    Per Epic 6 dependency: this story's responsibility ends here. The drainer
    (Story 4-4) does not run in worker.py yet (Story 6-6 wires it). The
    pending_actions row IS written; the cooling_off ticker (Story 4-6)
    transitions it to "pending" after 60s; the drainer's apply step lands in
    Epic 6.
    """
    # Story 5-9 CR-7 (F7) fix: refuse empty draft_body. Without this guard, an
    # empty body would land in pending_actions.payload and Epic 6's drainer
    # would try to send a blank email. Defender posture: better to refuse the
    # send than to send junk to the recipient.
    if not draft_body or not draft_body.strip():
        return DraftReplyOutcome(state="missing_recipient", defender_message="draft body is empty")
    if not recipient_address:
        return DraftReplyOutcome(state="missing_recipient")

    out = await propose_action(
        email_id=target_email_id,
        action_type=ActionType.SEND_REPLY.value,
        payload={"body": draft_body, "to": recipient_address},
        db_path=db_path,
    )

    if not out.ok:
        # Story 5-9 CR-6 (F6) related: propose_action's ProposeActionError
        # shape is distinct from RouterError; surface via state=router_error
        # with ErrorCode.PROVIDER_ERROR as the closest match (the chat surface
        # inspects state, not code).
        return DraftReplyOutcome(
            state="router_error",
            router_error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=(out.error.message if out.error else "propose_action failed"),
                retryable=False,
            ),
        )

    return DraftReplyOutcome(
        state="send_proposed",
        proposed_action_id=out.action_id,
    )


__all__ = [
    "DraftReplyOutcome",
    "DraftReplyRequest",
    "accept_draft",
    "handle_draft_reply",
]
