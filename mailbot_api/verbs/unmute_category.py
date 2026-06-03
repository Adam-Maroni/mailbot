"""``unmute_category`` verb — Story 6-4 AC-3.

Companion to Story 5-6's ``mute_category``. Adam types ``/unmute <category>``
in Discord; Hermes routes to this MCP tool which clears the
``notification_mutes`` row for the category.

The verb returns ``was_muted=True`` iff a row was actually deleted, so the
Hermes-side response can distinguish "okay, cleared the mute" from "that
category wasn't muted in the first place."
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from mailbot_api.db import connection, queries

logger = logging.getLogger(__name__)


class UnmuteCategoryOut(BaseModel):
    """Result of unmute_category."""

    ok: Literal[True] = True
    category: str
    was_muted: bool


async def unmute_category(category: str, *, db_path: str) -> UnmuteCategoryOut:
    """Clear the notification_mutes row for ``category``.

    Returns ``was_muted=False`` if the category had no mute in place (the
    operation is idempotent — calling unmute on an unmuted category is a
    no-op, not an error).
    """
    rowcount = await connection.execute_write(
        db_path, queries.NOTIFICATION_MUTES_DELETE_BY_CATEGORY, (category,)
    )
    was_muted = rowcount > 0
    logger.info(
        "category unmuted",
        extra={
            "event": "notification.unmuted",
            "category": category,
            "was_muted": was_muted,
        },
    )
    return UnmuteCategoryOut(category=category, was_muted=was_muted)


__all__ = ["UnmuteCategoryOut", "unmute_category"]
