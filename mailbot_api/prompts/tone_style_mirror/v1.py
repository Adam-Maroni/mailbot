"""tone_style_mirror prompt v1 — Story 5-3.

Extracts a per-recipient tone fingerprint from a small concatenated sample of
prior emails Adam sent TO THIS RECIPIENT. The fingerprint feeds ``draft_reply``
on later turns. Invoked ONCE per recipient and cached via the Story 2-7 response
cache against ``(recipient_address, prompt_version, model)`` for 30 days
(``response_cache_ttl_seconds: 2592000`` in ``router/policy.yaml``). Tone evolves
slowly; a 30-day TTL is the deliberate cost/freshness trade.

The model MUST NOT invent attributes that aren't supported by the sample. When
the sample contains ≥ 2 emails, every tone_attribute MUST cite a trait visible
in at least 2 of them (the model should self-restrict to traits it can defend).

Routes to Opus per Rule N's cost-vs-quality split — tone is a tier-1 product
capability; the call is amortized across many draft_reply turns by the response
cache, so the per-recipient Opus dollars cost is paid once per ~30 days.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

VERSION: str = "v1"

SYSTEM = (
    "You extract a tone-and-style fingerprint from a sample of emails Adam sent "
    "to a single recipient. Reply with valid JSON matching the schema; no preamble.\n"
    "Output expectations:\n"
    "  tone_attributes — ≤ 10 short snake_case strings naming stylistic traits.\n"
    "    Examples: 'concise', 'formal', 'uses_first_names', 'avoids_emoji',\n"
    "    'prefers_bullets', 'short_paragraphs', 'casual_signoff'. When the sample\n"
    "    contains ≥ 2 emails, every attribute MUST be visible in at least 2 of\n"
    "    them. When the sample contains 1 email, attribute the single email's\n"
    "    style but mark lower confidence by limiting yourself to ≤ 3 attributes.\n"
    "    When the sample is empty (no prior contact), return tone_attributes=[]\n"
    "    and both signature_pattern and salutation_pattern as null.\n"
    "  signature_pattern — Adam's typical sign-off if detectable (e.g., 'Best,\\nAdam').\n"
    "    null when the sample is too small or the sign-offs vary too much.\n"
    "  salutation_pattern — Adam's typical opening pattern (e.g., 'Hi <name>,' or\n"
    "    'Hello <name>,'). null when not detectable.\n"
    "Defender tone: be honest about what you can see. Inventing 'uses_first_names' "
    "for a sample where Adam wrote 'Dear Sir' twice is a banned anti-pattern."
)

USER_TEMPLATE = (
    "Recipient address: {recipient_address}\n\n"
    "Prior emails Adam sent to this recipient (oldest first; may be empty):\n"
    "{prior_emails_sample}\n"
)


class ToneStyleMirrorOutput(BaseModel):
    """Per-recipient tone fingerprint; consumed by draft_reply."""

    model_config = ConfigDict(frozen=True)

    tone_attributes: list[str] = Field(
        max_length=10,
        description="≤ 10 short snake_case stylistic traits visible in the sample.",
    )
    signature_pattern: str | None = Field(
        default=None,
        description="Typical sign-off pattern if detectable; null when not.",
    )
    salutation_pattern: str | None = Field(
        default=None,
        description="Typical salutation pattern if detectable; null when not.",
    )


OUTPUT_SCHEMA: type[BaseModel] = ToneStyleMirrorOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "ToneStyleMirrorOutput",
]
