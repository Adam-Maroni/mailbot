"""mute_category verb — Story 5-6 AC-2.

Write-side handler for the Discord ``/mute`` slash command. Persists Adam's
intent to mute a notification category, optionally bounded by a UTC ISO-8601
``muted_until`` timestamp. Indefinite mutes (``muted_until=None``) stay active
until the row is deleted (no /unmute slash command in v1).

The READ side is Epic 6's notification tier dispatcher (Story 6-3); it
consults ``notification_mutes`` when classifying outgoing notifications into
urgent / important / informational / silent. This story ships only the writer.

Per Rule C, all SQL lives in ``mailbot_api/db/queries.py`` and reaches SQLite
via the ``db.connection`` async wrappers (fetchone / execute_write).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    NOTIFICATION_MUTES_SELECT_BY_CATEGORY,
    NOTIFICATION_MUTES_UPSERT,
)


class MuteCategoryOut(BaseModel):
    """Result of /mute. ok=True on successful upsert."""

    model_config = ConfigDict(frozen=True)

    ok: bool = Field(description="True on successful upsert into notification_mutes.")
    category: str = Field(description="The muted notification category.")
    muted_until: str | None = Field(
        default=None,
        description="UTC ISO-8601 Z timestamp; null = indefinite mute.",
    )
    previously_muted: bool = Field(
        description="True when a row for this category existed pre-write.",
    )
    message: str = Field(description="Defender-toned human-readable summary.")


async def mute_category(
    category: str,
    *,
    db_path: str,
    muted_until: str | None = None,
) -> MuteCategoryOut:
    """Upsert a notification_mutes row for the given category.

    Args:
        category: free-form category name (no closed taxonomy in v1).
        db_path: SQLite path injected by the MCP server per Story 5-2 AC-3.
        muted_until: UTC ISO-8601 Z timestamp; ``None`` = indefinite mute.

    Returns:
        ``MuteCategoryOut`` with ``previously_muted`` set true when the row
        already existed pre-write.

    Defender-tone message format:
        - bounded mute: ``"category 'X' muted until <ISO-8601>"``
        - indefinite mute: ``"category 'X' muted indefinitely"``
    """
    pre_row = await fetchone(db_path, NOTIFICATION_MUTES_SELECT_BY_CATEGORY, (category,))
    previously_muted = pre_row is not None

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    await execute_write(
        db_path,
        NOTIFICATION_MUTES_UPSERT,
        (category, muted_until, now_iso),
    )

    if muted_until is None:
        message = f"category {category!r} muted indefinitely"
    else:
        message = f"category {category!r} muted until {muted_until}"

    return MuteCategoryOut(
        ok=True,
        category=category,
        muted_until=muted_until,
        previously_muted=previously_muted,
        message=message,
    )


__all__ = ["MuteCategoryOut", "mute_category"]
