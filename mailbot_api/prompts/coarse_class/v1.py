"""Coarse-class prompt v1 — Story 3-2 spec-conformant body.

Replaces Story 2-4's 5-label stub. The 6-label taxonomy matches Epic 3's
ingest-pipeline contract (epics.md §"Story 3.2" AC-3):

  transactional / newsletter / human / notification / spam_like / unknown

The field name is `class_coarse` (not `label`) so the orchestration in Story 3-5
can map task_type → column_name uniformly: prompts produce `class_coarse`, writes
land in `emails.class_coarse`.

Rule M discipline: SYSTEM is byte-stable across all invocations of this module
so Anthropic's ephemeral prompt cache fires. No per-call interpolation in
SYSTEM. (`coarse_class` will typically dispatch to Qwen per `policy.yaml`, but
the Anthropic-cache discipline applies project-wide for consistency and to
support eventual demotion experiments per `demotion_hypothesis` config.)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You classify the broad kind of email a message is. "
    "Reply with valid JSON matching the schema; no preamble, no commentary. "
    "The six labels are:\n"
    "  - transactional: receipts, order confirmations, password reset codes, account notices\n"
    "  - newsletter: subscriptions, recurring digest content, marketing-style broadcasts\n"
    "  - human: a real person addressing the recipient (personal or professional)\n"
    "  - notification: automated service alerts (calendar invites, build status, system messages)\n"
    "  - spam_like: unsolicited bulk content, scams, phishing-shaped messages\n"
    "  - unknown: insufficient signal to choose any of the above with confidence\n"
    "Be cautious — when in doubt between human and notification, prefer notification. "
    "Confidence should reflect uncertainty honestly: a clear newsletter is 0.95; "
    "a borderline notification/human case is 0.55."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


class CoarseClassOutput(BaseModel):
    """Six-label coarse classification of an email."""

    class_coarse: Literal["transactional", "newsletter", "human", "notification", "spam_like", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)


OUTPUT_SCHEMA: type[BaseModel] = CoarseClassOutput

__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "CoarseClassOutput"]
