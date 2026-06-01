"""Sensitivity-class prompt v1 — Story 3-2 (Qwen-only per FR-2.5).

This prompt MUST stay local — `policy.yaml` locks `sensitivity_class` to the
Qwen Ollama model, and Story 3-3 will add a hard-coded safeguard in the
classifier wrapper that refuses to dispatch if `policy.tasks["sensitivity_class"].model`
is anything but the Qwen model id. Sensitive bodies never leave the device.

NFR-PRIV-1 cautious bias: when the model is uncertain between `normal` and
`sensitive`, the SYSTEM block instructs it to prefer `sensitive` — and a
confidence below 0.5 will be downgraded to `sensitive` by Story 3-3's
classifier wrapper regardless of the model's stated label.

Rule M discipline: SYSTEM is byte-stable across calls. No interpolation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You classify the privacy sensitivity of an email body so downstream "
    "processing can route it correctly. Reply with valid JSON matching the "
    "schema; no preamble.\n"
    "Three sensitivity tiers:\n"
    "  - normal: ordinary correspondence; safe to send to a cloud LLM for "
    "summarization or classification\n"
    "  - sensitive: contains personal/private content the recipient would not "
    "want shared with third parties (health, finances, family matters, "
    "private commentary about other people)\n"
    "  - confidential: contains material that MUST remain on the recipient's "
    "device — legal correspondence, signed NDAs, password reset bodies with "
    "active tokens, two-factor codes, identity documents, intimate content\n"
    "Cautious bias: when uncertain between normal and sensitive, choose "
    "sensitive. When uncertain between sensitive and confidential, choose "
    "confidential. Provide a short reason (≤ 200 chars) naming the specific "
    "signal that drove the decision."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


class SensitivityClassOutput(BaseModel):
    """Three-tier sensitivity classification with cautious-bias confidence."""

    sensitivity: Literal["normal", "sensitive", "confidential"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=200)


OUTPUT_SCHEMA: type[BaseModel] = SensitivityClassOutput

__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "SensitivityClassOutput"]
