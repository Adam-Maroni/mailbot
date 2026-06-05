"""Sensitivity-class prompt v2 — Story 6-18 (F24 closure).

v1 -> v2 bump: the schema fields (`sensitivity`, `confidence`, `reason`) are now
explicitly enumerated in the SYSTEM block. v1 instructed "Reply with valid JSON
matching the schema; no preamble" but never named the schema fields — qwen2.5:3b
deterministically dropped `confidence`, every call hit SCHEMA_VALIDATION_FAILED,
and ingest pipeline blocked 712+ emails (no escalation per FR-2.5 / Rule Q
local-only). See F24 in epic-6-run-flags.md and Story 6-18 Dev Notes for the
root-cause trace; same defect class as F21 (Story 6-14 closure for Haiku
summary_short).

NFR-PRIV-1 cautious bias preserved verbatim from v1: when the model is
uncertain between `normal` and `sensitive`, the SYSTEM block instructs it to
prefer `sensitive` — and a confidence below 0.5 will be downgraded to
`sensitive` by Story 3-3's classifier wrapper regardless of the model's stated
label.

Rule M discipline: SYSTEM is byte-stable across calls. No interpolation. The
v1 -> v2 bump itself respects Rule M — prior calls hashed against v1's SYSTEM
keep their cache identity; v2 starts a fresh cache namespace.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

# Re-export v1's `SensitivityClassOutput` so isinstance() checks across the
# codebase remain version-agnostic. The Pydantic schema is byte-stable across
# v1 -> v2 (only the SYSTEM prompt text changed to enumerate field names); the
# output shape (sensitivity / confidence / reason) is identical. Keeping a
# single canonical class avoids the version-coupling failure mode where
# `classifier.py`'s isinstance(result.output, v2.SensitivityClassOutput) would
# silently fail when test fixtures still load v1 via their policy.yaml. A
# future v3 that reshapes the Pydantic model would replace this re-export with
# its own class definition.
from mailbot_api.prompts.sensitivity_class.v1 import SensitivityClassOutput

VERSION: Final[str] = "v2"

SYSTEM = (
    "You classify the privacy sensitivity of an email body so downstream "
    "processing can route it correctly. Reply with valid JSON matching the "
    "schema; no preamble, no commentary.\n"
    "Required JSON fields (all three MUST be present):\n"
    '  - "sensitivity" (string): exactly one of "normal", "sensitive", or '
    '"confidential"\n'
    '  - "confidence" (float between 0.0 and 1.0): how certain you are of the '
    "label\n"
    '  - "reason" (string, max 200 characters): the specific signal that drove '
    "the decision\n"
    'Example output: {"sensitivity": "normal", "confidence": 0.9, "reason": '
    '"Routine meeting confirmation, no personal data."}\n'
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
    "confidential.\n"
    # CR-1: tail-recency restatement of the reason length cap. Small-parameter
    # models (qwen2.5:3b) weight tail instructions more heavily; v1 had this
    # constraint at the very end of SYSTEM, v2 moved field definitions to the
    # middle for explicit enumeration. Restoring the cap at the tail preserves
    # the v1 behavioral contract while keeping the field enumeration benefit.
    "Keep the reason under 200 characters."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


OUTPUT_SCHEMA: type[BaseModel] = SensitivityClassOutput

__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "SensitivityClassOutput"]
