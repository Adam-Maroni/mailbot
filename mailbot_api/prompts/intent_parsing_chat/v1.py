"""intent_parsing_chat prompt v1 — Story 5-3.

Parses a single Discord message from Adam into a structured intent + optional
filter shape. Qwen-first per Rule N (cost discipline); the Router escalates to
Haiku on schema-fail-retry per Story 2-4. Interactive lane — chat latency matters.

The prompt MUST NOT fabricate ``target_email_ids``: every id must come from the
current chat context or be deferred to a follow-up verb call. ``ambiguous`` is
the correct intent when the message could parse two equally-plausible ways.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mailbot_api.verbs.schemas import FindEmailsFilter

VERSION: str = "v1"

SYSTEM = (
    "You parse a single Discord message from the user into a structured intent "
    "shape. Reply with valid JSON matching the schema; no preamble.\n"
    "Allowed intents:\n"
    "  find_emails        — user wants to retrieve a set of emails by filter\n"
    "  list_unread        — user wants the recent unread set (no filter needed)\n"
    "  summarize_thread   — user wants a summary of a thread (target_email_ids names one or more)\n"
    "  draft_reply        — user wants a reply drafted (target_email_ids names exactly one)\n"
    "  count_query        — user wants a count, not the list itself\n"
    "  send_action        — user is approving / sending a previously-drafted action\n"
    "  delete_action      — user wants emails deleted (Tier-3; verb decides authorization)\n"
    "  mute_category      — user wants a category muted\n"
    "  label_emails       — user wants emails labeled with a local category\n"
    "  small_talk         — user is making conversation (greeting, thanks, idle chit-chat)\n"
    "  ambiguous          — the message could parse two equally-plausible ways\n"
    "Defender tone: never fabricate target_email_ids. Every id must come from the "
    "current chat context or wait for a follow-up verb call (e.g., find_emails). If "
    "the user references 'that one' or a person by name without enough context to "
    "resolve, return intent='ambiguous' and an empty target_email_ids list — the "
    "chat orchestrator will then run reference_resolution.\n"
    "When the intent maps to a find/count query (find_emails, list_unread, "
    "count_query), populate proposed_filter with the parsed filter and at least "
    "ONE non-null filter field; otherwise leave proposed_filter as null.\n"
    "An empty object proposed_filter={} is NOT a valid 'no filter' signal — "
    "every FindEmailsFilter field would coerce to null and the chat orchestrator "
    "would misinterpret an all-null filter as an active filter. Use null when "
    "there is no filter to express.\n"
    "confidence reflects calibrated certainty in the parse, not in the downstream "
    "action — be honest about ambiguity. A clear 'show me unread from Sarah' is 0.95; "
    "a vague 'check on that' is 0.2 and probably intent=ambiguous."
)

USER_TEMPLATE = (
    "Recent Discord context (most recent last):\n{recent_context}\n\n"
    "User message:\n{user_message}\n"
)


class IntentParsingChatOutput(BaseModel):
    """Parsed intent + optional filter for a single Discord chat turn."""

    model_config = ConfigDict(frozen=True)

    intent: Literal[
        "find_emails",
        "list_unread",
        "summarize_thread",
        "draft_reply",
        "count_query",
        "send_action",
        "delete_action",
        "mute_category",
        "label_emails",
        "small_talk",
        "ambiguous",
    ] = Field(description="Top-level chat intent classified from the user message.")
    target_email_ids: list[str] = Field(
        default_factory=list,
        description="Graph message ids the message refers to; empty when intent doesn't target specific emails.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated confidence in the parse (0.0 = no confidence; 1.0 = certain).",
    )
    proposed_filter: FindEmailsFilter | None = Field(
        default=None,
        description="Parsed filter shape when intent maps to a find/count query; null otherwise.",
    )


OUTPUT_SCHEMA: type[BaseModel] = IntentParsingChatOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "IntentParsingChatOutput",
]
