"""reference_resolution prompt v1 — Story 5-3.

Resolves pronouns and oblique references ("that one", "the lawyer", "Marc's last
email") against the recent Discord context + cached sender_reputation_summary +
Hermes persistent memory's `relevant_senders` entries + candidate projections.
Qwen-first per Rule N; Router escalates to Haiku on schema-fail-retry.

The prompt MUST refuse to invent ``email_id`` values not present in the provided
context — when no plausible candidate exists, return an empty resolved_email_ids
list and set ambiguous=True so the chat orchestrator surfaces a clarifying turn
rather than proceeding silently. FR-4.3 ≥ 90% accuracy is validated in Epic 7
(Story 7-7) — this prompt is the surface that produces the rows.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

VERSION: str = "v1"

SYSTEM = (
    "You resolve a reference in the user's most recent message to one or more "
    "email_id values from the provided context. Reply with valid JSON matching "
    "the schema; no preamble.\n"
    "Resolution surface (use in this order):\n"
    "  1. The candidate_projections list — exact id matches go here\n"
    "  2. The recent Discord turns — 'that one' usually refers to the most recent\n"
    "     email mentioned by id or by subject\n"
    "  3. The sender_reputation_summary entries — when the user names a person\n"
    "     ('Marc', 'the lawyer'), match to the sender_address whose summary mentions\n"
    "     that name or role\n"
    "  4. Hermes persistent memory's relevant_senders entries — for longer-tail\n"
    "     references the user has used before\n"
    "Defender tone: never hallucinate. If the reference cannot be resolved to an "
    "email_id present in candidate_projections or recent_context, return an empty "
    "resolved_email_ids list and ambiguous=True. The chat orchestrator will then "
    "ask the user to clarify. Inventing a Graph id is a defender-banned anti-pattern.\n"
    "When two equally-plausible candidates exist (e.g., 'the email from Marc' and "
    "there are two senders named Marc), return BOTH ids in resolved_email_ids AND "
    "set ambiguous=True so the orchestrator surfaces the disambiguation choice to "
    "the user.\n"
    "reasoning must be ≤ 200 characters and cite the specific signal that drove "
    "the pick (e.g., 'most recent thread mentioned in turn N-1; sender matches')."
)

USER_TEMPLATE = (
    "Recent Discord context (most recent last):\n{recent_context}\n\n"
    "Candidate projections (subset of emails available to resolve against):\n"
    "{candidate_projections}\n\n"
    "User message:\n{user_message}\n"
)

# Placeholder injection contract for the Story 5-8 orchestrator:
#
#   {recent_context}        — orchestrator builds a combined blob from the last
#                             10 Discord turns AND Hermes persistent memory's
#                             `relevant_senders` entries (when present). The
#                             SYSTEM block lists "Hermes persistent memory" as
#                             a resolution surface; the orchestrator threads
#                             memory entries through this placeholder rather
#                             than introducing a dedicated `{hermes_memory}`
#                             slot so the prompt stays format-stable across
#                             cold-start (no memory) and steady-state.
#
#   {candidate_projections} — orchestrator builds a combined blob from the
#                             projections of emails referenced in the prior 3
#                             turns AND the cached `sender_reputation_summary`
#                             rows for any sender named in the user's message.
#                             The SYSTEM block lists both as resolution
#                             surfaces; the orchestrator threads them through
#                             this placeholder for the same format-stability
#                             reason. Format hint (orchestrator-side, not
#                             enforced by this prompt): one projection per
#                             line, sender summaries appended after a `---`
#                             separator.
#
#   {user_message}          — verbatim user turn.



class ReferenceResolutionOutput(BaseModel):
    """Resolved email_ids + reasoning for a referential chat turn."""

    model_config = ConfigDict(frozen=True)

    resolved_email_ids: list[str] = Field(
        default_factory=list,
        description="Graph message ids resolved from the reference; empty when no candidate exists.",
    )
    reasoning: str = Field(
        max_length=200,
        description="≤ 200-char justification — what signal made the model pick these ids.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated confidence in the resolution.",
    )
    ambiguous: bool = Field(
        description=(
            "True when the resolution had to guess between multiple plausible candidates "
            "OR when no candidate was found at all; the chat orchestrator surfaces a clarifying turn."
        ),
    )


OUTPUT_SCHEMA: type[BaseModel] = ReferenceResolutionOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "ReferenceResolutionOutput",
]
