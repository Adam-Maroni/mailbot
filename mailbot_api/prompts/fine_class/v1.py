"""Fine-class prompt v1 — Story 3-2.

Invoked ONLY after `coarse_class == "human"` (per Story 3-5's pipeline
ordering). The SYSTEM block names this precondition explicitly so the model
does not second-guess the upstream classification — it is given a "this is a
human-class email; refine the relationship type" frame.

Six labels: personal / professional / family / cold_outreach / automated / unknown.
The `automated` label exists as an escape valve when an upstream
misclassification slipped through (the human-class precondition was wrong);
Story 3-5 logs these and they feed into Epic 7's calibration corpus.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You refine the relationship type of an email that has already been "
    "classified as a HUMAN-sent message (a real person addressing the "
    "recipient). Reply with valid JSON matching the schema; no preamble. "
    "Trust the upstream human-class label; your job is only to refine.\n"
    "Six labels:\n"
    "  - personal: friend, partner, family-equivalent close contact\n"
    "  - professional: colleague, manager, business contact, vendor\n"
    "  - family: blood or chosen family (sibling, parent, child, in-law)\n"
    "  - cold_outreach: a stranger or near-stranger trying to start a conversation "
    "(recruiter, sales, networking)\n"
    "  - automated: an automated message that LOOKS human-written but is from a "
    "system — use this if you suspect the upstream coarse_class was wrong\n"
    "  - unknown: insufficient signal to choose with confidence\n"
    "Confidence reflects honest uncertainty: a clear known-relationship case is "
    "0.9+; a borderline professional/cold_outreach case is 0.5–0.7."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


class FineClassOutput(BaseModel):
    """Six-label fine-grained classification for human-class email."""

    class_fine: Literal["personal", "professional", "family", "cold_outreach", "automated", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)


OUTPUT_SCHEMA: type[BaseModel] = FineClassOutput

__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "FineClassOutput"]
