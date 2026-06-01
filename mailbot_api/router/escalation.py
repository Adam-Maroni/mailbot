"""Tier-escalation chain per Story 2-4 AC-4.

The chain encodes the canonical model demotion/promotion ladder. Story 2-8's
budget guard uses the REVERSE order (Opus → Haiku → Qwen) for degraded-mode
demotion; this story uses the FORWARD order (Qwen → Haiku → Opus) for
schema-validation-failure escalation.
"""

from __future__ import annotations

_ESCALATION_CHAIN: tuple[str, ...] = (
    "qwen2.5:3b-instruct-q4_K_M",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-7",
)


def next_tier(current_model: str) -> str | None:
    """Return the next-tier model id, or ``None`` if already at the top.

    Models not in the canonical chain (e.g., a custom force_model value) are
    treated as terminal — no escalation. This is intentional: an operator
    forcing an off-chain model takes responsibility for failure handling.
    """
    try:
        idx = _ESCALATION_CHAIN.index(current_model)
    except ValueError:
        return None
    if idx + 1 >= len(_ESCALATION_CHAIN):
        return None
    return _ESCALATION_CHAIN[idx + 1]


__all__ = ["next_tier"]
