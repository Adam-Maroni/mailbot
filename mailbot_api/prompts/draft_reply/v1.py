"""draft_reply prompt v1 — Story 5-3.

Produces a reply draft in Adam's tone, plus a suggested subject, a small list of
tone signals the model picked up from the source/sample, and a defender warnings
list for anything that needs Adam's eyes before sending. Routes to Opus per FR-4.4
(draft quality is a tier-1 product capability); the routing decision lives in
``router/policy.yaml`` per Rule G and was already shipped in Story 2-4 — this
story ships the prompt module body that ``ask_router(task_type='draft_reply',...)``
finally has to resolve to.

This prompt does NOT send. The agent surfaces the draft to Adam in Discord with
inline send/edit/refine/cancel controls (Story 5-9); only on explicit "send" does
``propose_action(ActionType.SEND_REPLY, ...)`` fire, which then goes through
Story 4-6's cooling-off and Story 4-4's drainer.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

VERSION: str = "v1"

SYSTEM = (
    "You draft a reply to an email in Adam's voice. Reply with valid JSON matching "
    "the schema; no preamble.\n"
    "Defender voice (mandatory):\n"
    "  - conservative, terse, never apologetic-when-unnecessary\n"
    "  - never adds emoji or exclamation points unless the source email used them\n"
    "  - surfaces commitments and deadlines explicitly via defender_warnings\n"
    "  - never invents facts about Adam's availability, plans, or commitments — when\n"
    "    in doubt, ask a clarifying sentence rather than asserting\n"
    "Source context: you receive the source email + the thread context + the tone\n"
    "signals the model previously extracted from prior sent emails to this\n"
    "recipient. tone_signals may be empty on first contact — in that case fall\n"
    "back to a neutral professional baseline (concise, no emoji, first-name basis\n"
    "only if the source uses first names).\n"
    "Output expectations:\n"
    "  draft_body — the reply itself, ready to send. No 'Draft:' prefix. No\n"
    "    placeholder text like '[insert reason here]'.\n"
    "  suggested_subject — the proposed subject line. Usually 'Re: <original>'\n"
    "    unless the thread topic has shifted.\n"
    "  tone_signals_used — ≤ 5 short snake_case strings naming the stylistic cues\n"
    "    you applied (e.g., 'first_name_basis', 'no_emoji', 'short_paragraphs').\n"
    "  defender_warnings — anything Adam should double-check before sending. Empty\n"
    "    list when the reply is straightforward. Surface here: commitments to\n"
    "    deadlines, agreements to meet, dollar figures, sharing of sensitive\n"
    "    information, or anything you inferred from incomplete context."
)

USER_TEMPLATE = (
    "Source email:\n{source_email}\n\n"
    "Thread context (older messages in the same thread, oldest first):\n"
    "{thread_context}\n\n"
    "Tone signals from prior sent emails to this recipient (may be empty):\n"
    "{tone_signals}\n"
)


class DraftReplyOutput(BaseModel):
    """A defender-voice draft reply + suggested subject + tone + warnings."""

    model_config = ConfigDict(frozen=True)

    draft_body: str = Field(description="The reply text in Adam's voice; ready to send.")
    suggested_subject: str = Field(description="Proposed subject line for the reply.")
    tone_signals_used: list[str] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "≤ 5 short snake_case stylistic cues the model applied. "
            "Empty list on first-contact drafts (no tone signals available)."
        ),
    )
    defender_warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Items Adam should double-check before sending (commitments, deadlines, "
            "dollar figures, inferences from incomplete context). Empty list when the reply is straightforward."
        ),
    )


OUTPUT_SCHEMA: type[BaseModel] = DraftReplyOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "DraftReplyOutput",
]
