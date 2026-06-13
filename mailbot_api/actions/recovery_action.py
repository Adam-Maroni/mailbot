"""Story 7-0-c24 — `RecoveryAction` envelope: the universal next-step contract.

The single Pydantic shape every refusal/blocked/terminal mailbot-api response
carries so Hermes can drive the agent forward without inferring next-steps
from SKILL.md + AGENTS.md + SOUL.md + main-inference Haiku's training prior.

See _bmad-output/implementation-artifacts/7-0-c24-design-decision.md for the
full surface enumeration + per-surface tool_name/args_hint templates and the
MVP-vs-full-propagation scope-cleave decision.

MVP scope (this story): the envelope is added to ProposeActionError
(INVALID_ACTION_TYPE migrates Story 6-19's valid_action_types field into
this envelope; the legacy field is retained per back-compat convention) +
ProposeActionOut (success-return with requires_grant=True populates the
envelope with a mint_grant next-call hint). Broader propagation across
HydrateEmailError + Router refusals + terminal action states +
MintSensitivityTokenOut is named carry-forward stories C24-FU-1..4.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecoveryAction(BaseModel):
    """The structured next-step envelope.

    Fields:
      - tool_name: the verb / MCP tool / Router task_type the agent SHOULD
        call next. ``None`` when the recovery path is "ask the user" (no
        machine-driven next-call). Examples: ``"mint_grant"``,
        ``"mint_sensitivity_token"``, ``"propose_action"``, ``"ask_router"``.
      - args_hint: keyword arguments the agent should interpolate into the
        next call. ``dict[str, Any]`` because the envelope can't statically
        type every verb's parameter set; documented per-surface in
        SKILL.md.
      - user_facing_guidance: canonical wording for the agent to relay in
        chat IF the recovery path requires user input. ``None`` when the
        agent can auto-recover without user-visible explanation.

    Frozen for safety: every consumer reads the envelope by value, not by
    reference. Mutation attempts raise ValidationError (the Pydantic v2
    contract on ``ConfigDict(frozen=True)``).
    """

    model_config = ConfigDict(frozen=True)

    tool_name: str | None = Field(
        default=None,
        description=(
            "The verb / MCP tool / Router task_type the agent should call "
            "next. None when the recovery path requires user input."
        ),
    )
    args_hint: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Keyword arguments to interpolate into the next call. Shape "
            "varies per surface; see SKILL.md Recovery Actions section."
        ),
    )
    user_facing_guidance: str | None = Field(
        default=None,
        description=(
            "Canonical wording the agent should relay in chat when the "
            "recovery path requires user input. None for silent auto-recover."
        ),
    )


__all__ = ["RecoveryAction"]
