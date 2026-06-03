"""``finalize_digest_delivery`` verb — Story 6-5 AC-2.

Sweeps every `tier='important' AND delivery_status='pending'` row in
`notifications_outbox` to `delivery_status='ok_via_digest'` with
`delivered_at=now()`. Hermes calls this once AFTER posting the 08:00
digest message to Discord.

Idempotent: calling on an already-swept set returns `delivered_count=0`.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)


class FinalizeDigestDeliveryOut(BaseModel):
    """Result of finalize_digest_delivery.

    ``delivered_count`` is the number of rows the sweep flipped from
    ``pending`` to ``ok_via_digest``. ``ts`` is the timestamp that was
    written as ``delivered_at`` on every affected row.
    """

    ok: bool = True
    delivered_count: int
    ts: str


async def finalize_digest_delivery(*, db_path: str) -> FinalizeDigestDeliveryOut:
    """Mark all queued `tier='important'` rows as delivered via digest."""
    now = utc_z_now()
    rowcount = await connection.execute_write(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_FINALIZE_DIGEST_DELIVERY,
        (now,),
    )
    logger.info(
        "digest delivery finalized",
        extra={
            "event": "digest.delivery.finalized",
            "delivered_count": rowcount,
            "ts": now,
        },
    )
    return FinalizeDigestDeliveryOut(delivered_count=rowcount, ts=now)


__all__ = ["FinalizeDigestDeliveryOut", "finalize_digest_delivery"]
