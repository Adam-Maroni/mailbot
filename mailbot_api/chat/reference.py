"""Conversational reference-resolution orchestrator — Story 5-8.

Wires the chat-side reference-resolution flow end-to-end on the mailbot-api
side: assembles the context (recent Discord turns + projections + cached
sender summaries + cold-startable Hermes memory), dispatches via
``ask_router(task_type="reference_resolution", caller_origin="verb-ask-router")``
per ``router/policy.yaml``, and returns the parsed verdict to the chat
orchestrator (Story 5-9).

FR-4.3 ≥ 90% accuracy is validated in Epic 7 (Story 7-7 shadow-mode rollouts);
THIS story's responsibility is to ensure the ``router_calls`` rows exist with
``task_type="reference_resolution"`` so Epic 7's sampler can pull them.

Per AR-PAT-1 Rule C this module dispatches via the Router, NOT directly to
``db.queries`` — projections + sender summaries are passed IN by the chat
orchestrator (Story 5-9), not fetched here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from mailbot_api.prompts.reference_resolution.v1 import ReferenceResolutionOutput
from mailbot_api.router import ask_router
from mailbot_api.router.errors import RouterError, sanitize_error
from mailbot_api.verbs.schemas import EmailProjection


@dataclass(frozen=True)
class DiscordTurn:
    """One Discord chat turn — the unit of conversational context."""

    role: Literal["user", "assistant"]
    content: str
    at: str  # ISO-8601 UTC Z timestamp


@dataclass(frozen=True)
class ReferenceContext:
    """The pre-assembled context for one reference-resolution call.

    Story 5-9's chat orchestrator builds this by:
      * walking the last 10 Discord turns into ``recent_turns``;
      * pulling projections from emails referenced in the prior 3 turns into
        ``candidate_projections``;
      * pre-fetching ``sender_reputation_summary`` rows for senders named in
        the latest user turn into ``sender_summaries``;
      * passing Hermes persistent-memory's ``relevant_senders`` blob (or
        ``None`` on cold-start) into ``relevant_senders_memory``.

    The orchestrator is read-only against memory; this resolver does NOT write
    back. Cold-start (memory=None) is the documented happy path.
    """

    recent_turns: tuple[DiscordTurn, ...]
    candidate_projections: tuple[EmailProjection, ...] = ()
    sender_summaries: tuple[str, ...] = ()
    relevant_senders_memory: str | None = None


@dataclass(frozen=True)
class ReferenceResolutionResult:
    """Verdict returned from ``resolve_reference``.

    Result-state matrix:

      * ``ok=True, ambiguous=False`` — confident resolution. ``resolved_email_ids``
        carries the picked id(s) (typically one, occasionally several when the
        user's phrasing legitimately refers to multiple emails). Chat
        orchestrator (Story 5-9) proceeds to the downstream action.
      * ``ok=True, ambiguous=True`` — model resolved to multiple plausible
        candidates AND wants the user to disambiguate. Per the Story 5-3
        prompt contract, ``resolved_email_ids`` MAY be non-empty (carries the
        2-4 plausible candidates) — the orchestrator surfaces them as choices
        rather than acting on any one of them. The Story 5-9 capstone MUST
        check ``ambiguous`` before treating ``resolved_email_ids`` as a single
        action target.
      * ``ok=False, ambiguous=True`` — graceful-degradation path. Either the
        context was invalid (empty / wrong-role last turn) or the Router
        returned ok=False. ``resolved_email_ids`` is empty; ``error`` carries
        the RouterError (when from Router) or None (when from validation).
        Story 5-9 surfaces a clarifying turn.
      * ``ok=False, ambiguous=False`` — not currently produced by this
        orchestrator; reserved for future explicit-failure semantics.

    Story 5-8 CR-2 decision: ``resolved_email_ids`` IS allowed to be
    non-empty when ``ambiguous=True``. The Story 5-3 reference_resolution
    SYSTEM block explicitly authorizes this (`"return BOTH ids in
    resolved_email_ids AND set ambiguous=True"`). Story 5-9 must not act on
    those ids without first surfacing the disambiguation choice.
    """

    ok: bool
    resolved_email_ids: tuple[str, ...]
    reasoning: str
    confidence: float
    ambiguous: bool
    router_call_id: int | None
    error: RouterError | None


def build_reference_resolution_content(context: ReferenceContext) -> dict[str, Any]:
    """Build the ``content`` dict for ``ask_router(task_type=reference_resolution)``.

    The keys MUST match the Story 5-3 reference_resolution/v1.py USER_TEMPLATE
    placeholders exactly: ``user_message``, ``recent_context``,
    ``candidate_projections``.

    Per the Story 5-3 placeholder-injection contract:
      * ``relevant_senders_memory`` rides ``recent_context`` after a
        ``--- relevant_senders ---`` separator (omitted when ``None``).
      * ``sender_summaries`` rides ``candidate_projections`` after a
        ``--- sender_summaries ---`` separator (omitted when empty).

    Pure function — no I/O.
    """
    # Most recent user message — take from the last user turn in recent_turns.
    user_message = ""
    for turn in reversed(context.recent_turns):
        if turn.role == "user":
            user_message = turn.content
            break

    # recent_context: oldest-first chronological dump of the last 10 turns.
    turn_lines = [f"{t.role}: {t.content}" for t in context.recent_turns]
    recent_context = "\n".join(turn_lines)
    if context.relevant_senders_memory is not None:
        recent_context += "\n--- relevant_senders ---\n" + context.relevant_senders_memory

    # candidate_projections: one projection per line + optional sender_summaries.
    # Story 5-8 CR-3 fix: nullable EmailProjection fields (subject /
    # from_address / class_coarse can be None) used to render as literal
    # "None" via Python's default str() — the LLM would see "from=None" /
    # "class=None" / "subject='None'" and silently degrade FR-4.3 accuracy.
    # Replace with "unknown" sentinels so the prompt context stays
    # human-readable.
    def _projection_line(p: EmailProjection) -> str:
        subject = p.subject or "unknown"
        from_addr = p.from_address or "unknown"
        class_coarse = p.class_coarse or "unknown"
        return f"id={p.email_id} subject={subject!r} from={from_addr} class={class_coarse}"

    proj_lines = [_projection_line(p) for p in context.candidate_projections]
    candidate_projections = "\n".join(proj_lines)
    if context.sender_summaries:
        candidate_projections += (
            "\n--- sender_summaries ---\n" + "\n".join(context.sender_summaries)
        )
    # Story 5-8 CR-4 fix: when candidate_projections starts empty but
    # sender_summaries is non-empty, the prior `"\n".join([])` + `+= "\n..."`
    # produced a leading "\n" injected into the LLM's USER_TEMPLATE. Strip.
    candidate_projections = candidate_projections.lstrip("\n")

    return {
        "user_message": user_message,
        "recent_context": recent_context,
        "candidate_projections": candidate_projections,
    }


async def resolve_reference(
    context: ReferenceContext,
    *,
    db_path: str,
    caller_origin: str = "verb-ask-router",
) -> ReferenceResolutionResult:
    """Dispatch reference resolution via the Router and return the parsed verdict.

    Returns ``ambiguous=True`` (and an empty ``resolved_email_ids``) when:
      * the context has no recent turns OR the most recent turn is not from
        the user (no dispatch);
      * the Router returns ``ok=False`` (graceful degradation — chat orchestrator
        surfaces a clarifying question);
      * the Router returns ``ok=True`` and the prompt itself flagged ambiguous.

    Story 5-9's chat orchestrator consumes ``ambiguous`` and surfaces the
    appropriate clarifying turn.
    """
    # Context validation — refuse without dispatch when the input shape can't
    # plausibly produce a resolution. This protects the cost-discipline center
    # from no-op Router calls.
    if not context.recent_turns or context.recent_turns[-1].role != "user":
        return ReferenceResolutionResult(
            ok=False,
            resolved_email_ids=(),
            reasoning="invalid context: missing user turn",
            confidence=0.0,
            ambiguous=True,
            router_call_id=None,
            error=None,
        )

    content = build_reference_resolution_content(context)

    # email_id=None per Story 3-3 cross-email-task bypass — reference resolution
    # operates over the chat surface, not on a single email; the precondition
    # layer's sensitivity gate doesn't apply.
    result = await ask_router(
        task_type="reference_resolution",
        content=content,
        db_path=db_path,
        caller_origin=caller_origin,
        email_id=None,
    )

    # Story 5-8 CR-6 (forward-compat canary): router_call_id is not on the
    # current RouterResult contract; future Router work may surface it. When
    # that lands, ``result.router_call_id`` (or whatever the new field name is)
    # MUST be threaded into this dataclass field. The two assertions below are
    # the canary: if a future RouterResult sprouts a router_call_id attribute,
    # the assertion below fires at first dispatch and forces a revisit. Until
    # then, this surface returns None and Epic 7's sampler queries router_calls
    # by task_type + timestamp.
    assert not hasattr(result, "router_call_id"), (
        "RouterResult now exposes router_call_id — Story 5-8 must plumb it through; "
        "see mailbot_api/chat/reference.py canary."
    )
    router_call_id: int | None = None

    if not result.ok:
        # Router-level failure → graceful-degradation path.
        # Story 5-8 CR-5: RouterResult validator guarantees ok=False ⇒ error != None.
        # Use assert (not a defensive else branch) to keep the contract explicit.
        err = result.error
        assert err is not None, "RouterResult.ok=False contract violation: error is None"
        # Story 5-8 CR-1 decision: strip the "Exception: " prefix that
        # sanitize_error prepends. We're sanitizing a known string, not an
        # exception traceback; the prefix is noise for the chat surface.
        wrapped = sanitize_error(Exception(err.message))
        sanitized_msg = wrapped.removeprefix("Exception: ")
        return ReferenceResolutionResult(
            ok=False,
            resolved_email_ids=(),
            reasoning=sanitized_msg,
            confidence=0.0,
            ambiguous=True,
            router_call_id=router_call_id,
            error=err,
        )

    # Happy path — parse the prompt output back into the typed model.
    parsed_output = result.output
    if isinstance(parsed_output, ReferenceResolutionOutput):
        parsed = parsed_output
    elif parsed_output is not None:
        parsed = ReferenceResolutionOutput.model_validate(parsed_output.model_dump())
    else:
        # Router said ok=True but no output — treat as ambiguous fallback.
        return ReferenceResolutionResult(
            ok=False,
            resolved_email_ids=(),
            reasoning="router ok but produced no output",
            confidence=0.0,
            ambiguous=True,
            router_call_id=router_call_id,
            error=None,
        )

    return ReferenceResolutionResult(
        ok=True,
        resolved_email_ids=tuple(parsed.resolved_email_ids),
        reasoning=parsed.reasoning,
        confidence=parsed.confidence,
        ambiguous=parsed.ambiguous,
        router_call_id=router_call_id,
        error=None,
    )


__all__ = [
    "DiscordTurn",
    "ReferenceContext",
    "ReferenceResolutionResult",
    "build_reference_resolution_content",
    "resolve_reference",
]
