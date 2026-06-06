"""Sensitivity-class prompt v3 — Story 6-21 (F27 closure).

v2 -> v3 bump: 2 borderline-case examples added BEFORE the cautious-bias
paragraph to anti-anchor against v2's single high-confidence-normal example.

F27 evidence (Story 6-6.5 fifth-pass walk, 2026-06-06): qwen2.5:3b
classified the CP-B "Following up on yesterday" fixture as `normal` with
confidence 0.95 despite the body containing family-medical signal (parent's
diagnosis + treatment clinic recommendation) + private-financial signal
(debt between friends). qwen's reason: "Brief personal follow-up, no
sensitive information." The NFR-PRIV-1 cautious-bias floor at
``mailbot_api/sensitivity/classifier.py`` only downgrades when
``confidence < 0.5`` — qwen returned 0.95, so the backstop never fired.

Working hypothesis (confirmed by Story 6-21 spec rationale): v2's single
positive example (``confidence: 0.9`` for routine meeting confirmation)
anchors qwen's confidence distribution toward high-confidence-normal
labels. 3B-parameter models weight example outputs heavily in their
parameter generation; without a counter-example showing borderline-case
confidence in the 0.65-0.75 range, qwen has no in-prompt signal that
uncertainty is even possible.

The fix is anti-anchoring: two borderline-case examples co-located with
the schema enumeration, showing health/financial/family signal density
classified ``sensitive`` with confidence 0.65 + 0.70 BEFORE the
cautious-bias paragraph. Co-locating "sensitive at moderate confidence"
with the existing "normal at high confidence" gives qwen a distribution
to interpolate over.

NFR-PRIV-1 cautious bias preserved verbatim from v2: when uncertain
between ``normal`` and ``sensitive``, the SYSTEM block instructs the model
to prefer ``sensitive``. The classifier wrapper's ``confidence < 0.5``
downgrade remains in effect.

Rule M discipline: SYSTEM is byte-stable across calls. No interpolation.
The v2 -> v3 bump itself respects Rule M — prior calls hashed against
v2's SYSTEM keep their cache identity; v3 starts a fresh cache namespace.
This is the same discipline v2 used vs. v1 (per v2.py:18-21 docstring).

Pair-shipped with ``router/sensitivity_patterns.yaml`` augmentation for
two new ``force_sensitive`` regex patterns (medical-diagnosis + outstanding-
debt) as defense-in-depth backstop against future qwen drift. The pattern
overrides upgrade ``normal`` -> ``sensitive`` regardless of what qwen v3
returns. See Story 6-21 AC-3 + F27 in epic-6-run-flags.md.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

# Re-export v1's `SensitivityClassOutput` so isinstance() checks across the
# codebase remain version-agnostic. The Pydantic schema is byte-stable
# v1 -> v2 -> v3 (only the SYSTEM prompt text changed); the output shape
# (sensitivity / confidence / reason) is identical. Same pattern v2 uses
# (v2.py:38) so the version-coupling failure mode is consistent.
from mailbot_api.prompts.sensitivity_class.v1 import SensitivityClassOutput

VERSION: Final[str] = "v3"

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
    # Story 6-21 (F27 closure): borderline-case examples added BEFORE the
    # cautious-bias paragraph for anti-anchoring. 3B-parameter models weight
    # example outputs heavily; co-locating "sensitive at moderate confidence"
    # with the existing "normal at high confidence" gives qwen a distribution
    # to interpolate over, reducing the over-stated-confidence-normal failure
    # mode that F27 surfaced.
    "Borderline cases — when health, financial, family, or interpersonal "
    "signals appear in casual-sounding correspondence, classify as sensitive "
    "with confidence in the 0.65-0.75 range. Examples:\n"
    '  {"sensitivity": "sensitive", "confidence": 0.70, "reason": "Mentions '
    'parent medical diagnosis and treatment clinic recommendation despite '
    'informal tone."}\n'
    '  {"sensitivity": "sensitive", "confidence": 0.65, "reason": "Discusses '
    'outstanding debt between friends and personal financial commitments."}\n'
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
    # CR-1 (preserved from v2): tail-recency restatement of the reason length
    # cap. Small-parameter models (qwen2.5:3b) weight tail instructions more
    # heavily; preserving the tail position keeps the v1/v2 behavioral contract.
    "Keep the reason under 200 characters."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


OUTPUT_SCHEMA: type[BaseModel] = SensitivityClassOutput

__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "SensitivityClassOutput"]
