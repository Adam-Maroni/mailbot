"""Story 10.5.2 (Epic 10.5 Cluster B) — structured sensitivity-refusal envelope.

Design: retro §8.5 (action B7). The Router *decides* (typed facts:
classification, task, reason); the chat boundary *speaks*. This module owns
the typed envelope carried on ``RouterError`` plus the pure message builder
that renders the four-beat user-facing prose.

Why a structured envelope (F-10-5-6 leak fixed BY CONSTRUCTION):
  A typed envelope has an explicit field allow-list. The internal Graph email
  id is simply NOT a printable field on ``SensitivityRefusal`` — only a short,
  non-reversible ``email_ref`` display token is carried — so the id-leak that
  reached Discord as part of a raw HTTP-502 becomes structurally impossible
  rather than scrub-dependent.

The four-beat contract (retro §8.5):
  name the state → consequence in user terms → the one action that works →
  expectations. No trace, no internal id, no dead-end instruction.

Load-bearing rule: a message may only offer actions that actually work.
  - sensitive → offers "yes, escalate" (genuine only because Story 10.5.2
    Task 4 fixes F-10-5-7 so the escalation path actually attaches).
  - confidential → offers NO escalation (none exists by design, NFR-PRIV-2).
  - not-yet-classified → does NOT suggest ``mailbot rederive`` (it crashes
    every invocation until Story 10.5.4 fixes F-10-6-3).
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The three classifications a refusal envelope can describe. ``not_classified``
# is the NULL-sensitivity_at / missing-row case; the router surfaces it as
# ErrorCode.SENSITIVITY_NOT_CLASSIFIED.
RefusalClassification = Literal["sensitive", "confidential", "not_classified"]


def email_ref_for(email_id: str) -> str:
    """Derive a short, non-reversible display reference from a Graph email id.

    The internal Graph message id is long, opaque, and (per F-10-5-6) must
    never reach Discord. This produces a stable 8-char tag (``email #a1b2c3d4``
    shape) so a user can correlate a refusal with a follow-up without the raw
    id ever being printable. It is a one-way hash prefix — it does NOT round-
    trip back to the Graph id.
    """
    digest = hashlib.sha256(email_id.encode("utf-8")).hexdigest()[:8]
    return f"email #{digest}"


class SensitivityRefusal(BaseModel):
    """Typed envelope carried on a sensitivity ``RouterError``.

    Explicit field allow-list — the raw Graph email id is deliberately NOT a
    field. ``email_ref`` is the only email-identifying value and it is a
    one-way display token (see :func:`email_ref_for`). Frozen so every
    consumer reads by value.

    Fields:
      - email_ref: short non-reversible display token (never the Graph id).
      - task: the task_type the user asked for (e.g. ``draft_reply``).
      - classification: sensitive | confidential | not_classified.
      - reason: short machine reason (mirrors the RouterError.code intent).
      - user_facing_guidance: the four-beat prose the Discord boundary relays
        verbatim/paraphrased (reuses the RecoveryAction ``user_facing_guidance``
        contract / "Rule S").
    """

    model_config = ConfigDict(frozen=True)

    email_ref: str = Field(
        description="Short non-reversible display token; NEVER the Graph email id.",
    )
    task: str = Field(description="The task_type the user requested.")
    classification: RefusalClassification
    reason: str = Field(description="Short machine reason mirroring the error code.")
    user_facing_guidance: str = Field(
        description="Four-beat prose the Discord boundary relays to the user.",
    )


def build_guidance(classification: RefusalClassification) -> str:
    """Pure builder: (classification) → four-beat user-facing prose.

    Wording per retro §8.5. Deliberately carries NO email id, NO trace, and —
    for the not-yet-classified case — NO ``rederive`` suggestion (it crashes
    until Story 10.5.4).
    """
    if classification == "sensitive":
        return (
            "⚠️ That email is classified sensitive. Drafting or summarizing it "
            "would send its contents to Claude's cloud API — I've held off, so "
            "nothing left your mailbox. To go ahead just this once, reply "
            "**'yes, escalate'** (authorizes this one email, this one task, for "
            "10 minutes)."
        )
    if classification == "confidential":
        return (
            "🔒 That email is classified confidential. No cloud override exists — "
            "by design, its contents never go to an external API. Read it "
            "directly in Outlook."
        )
    # not_classified
    return (
        "⏳ That email isn't sensitivity-classified yet, so I can't route it to "
        "the cloud API until it is. The ingest worker classifies new mail "
        "automatically within a few minutes — try again shortly."
    )


def build_refusal(
    *,
    email_id: str,
    task: str,
    classification: RefusalClassification,
    reason: str,
) -> SensitivityRefusal:
    """Construct a :class:`SensitivityRefusal` from raw router-side facts.

    ``email_id`` is consumed ONLY to derive the non-reversible ``email_ref`` —
    it is never stored on the envelope, so it cannot leak downstream.
    """
    return SensitivityRefusal(
        email_ref=email_ref_for(email_id),
        task=task,
        classification=classification,
        reason=reason,
        user_facing_guidance=build_guidance(classification),
    )


__all__ = [
    "RefusalClassification",
    "SensitivityRefusal",
    "build_guidance",
    "build_refusal",
    "email_ref_for",
]
