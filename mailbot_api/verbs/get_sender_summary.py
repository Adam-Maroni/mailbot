"""get_sender_summary read verb — Story 5-1 AC-6.

Returns sender enrichment from the senders table (Rule G — read-side). The
senders table uses lowercased email address as primary key (per 001_init).
This verb lowercases the input before lookup.

Aggregates message_count and last_seen_at from emails (filtered to
non-soft-deleted) — those numbers are not cached on senders and don't need to be.
"""

from __future__ import annotations

from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import (
    GET_SENDER_AGGREGATE_SELECT,
    GET_SENDER_BASE_SELECT,
)
from mailbot_api.verbs.schemas import (
    GetSenderSummaryOut,
    SenderSummary,
    VerbError,
)


async def get_sender_summary(
    sender_address: str,
    *,
    db_path: str,
) -> GetSenderSummaryOut:
    """Return SenderSummary for `sender_address`. Refuses on unknown sender."""
    addr_normalized = sender_address.lower().strip()
    base = await fetchone(db_path, GET_SENDER_BASE_SELECT, (addr_normalized,))
    if base is None:
        return GetSenderSummaryOut(
            ok=False,
            error=VerbError(
                code="SENDER_NOT_FOUND",
                message=f"no sender with address={sender_address!r}",
            ),
        )

    # base column order: id, display_name, sender_reputation_summary
    sender_id, display_name, reputation = base[0], base[1], base[2]

    # Aggregate from emails. CR finding 3: GET_SENDER_AGGREGATE_SELECT uses
    # `LOWER(from_address) = ?` so mixed-case captures (e.g., "Alice@Example.COM"
    # from Graph) match the lowercased senders.id correctly. Pass the already-
    # lowercased sender_id as the param (no double-lowering needed).
    agg = await fetchone(db_path, GET_SENDER_AGGREGATE_SELECT, (sender_id,))
    message_count = int(agg[0]) if agg and agg[0] is not None else 0
    last_seen_at = agg[1] if agg else None

    return GetSenderSummaryOut(
        ok=True,
        sender=SenderSummary(
            sender_address=sender_id,
            display_name=display_name,
            message_count=message_count,
            last_seen_at=last_seen_at,
            sender_reputation_summary=reputation,
        ),
    )


__all__ = ["get_sender_summary"]
