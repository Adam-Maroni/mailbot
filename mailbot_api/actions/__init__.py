"""Authorized-actions package — Epic 4.

Re-exports the public surface of `types.py` so downstream verbs/drainer can
import the contract via the package root:

    from mailbot_api.actions import ActionType, tier_for
"""

from __future__ import annotations

from mailbot_api.actions.recovery_action import RecoveryAction
from mailbot_api.actions.types import (
    ACTION_PROPERTIES,
    EMAIL_LESS_ACTIONS,
    MOVE_FAMILY,
    REVERT_OF_ACTION_ID_KEY,
    ActionProperties,
    ActionType,
    is_move_family,
    is_send_family,
    requires_grant,
    tier_for,
)

__all__ = [
    "ACTION_PROPERTIES",
    "ActionProperties",
    "ActionType",
    "EMAIL_LESS_ACTIONS",
    "MOVE_FAMILY",
    "REVERT_OF_ACTION_ID_KEY",
    "RecoveryAction",
    "is_move_family",
    "is_send_family",
    "requires_grant",
    "tier_for",
]
