"""Anti-fatigue gating layer — Story 6-4.

Pure helpers that the four-tier dispatcher (`mailbot_api.notifications.tiers`)
calls BEFORE writing to `notifications_outbox`. Side-effect-free except for
the dedup helper which optionally returns the row id to collapse.

Three gates:

1. **Quiet hours** — 22:00–08:00 local (env `MAILBOT_LOCAL_TZ`, default UTC).
   Urgent bypasses; important is HELD (still enqueued, but quiet_hours_held
   flag would be set if we had the column — Story 6-5 sweeps respect it via
   the row's enqueued_at timestamp). Informational is dropped (pull-only anyway).
2. **Mute** — `notification_mutes` table (Story 5-6 schema).
3. **Dedup** — 5+ same-category-same-tier within the last hour → collapse
   to a summary message via UPDATE.

These helpers are NOT applied to `tier='urgent'` (urgent always delivers
per FR-7.4) and NOT applied to `tier='silent'` (silent always logs).
"""

from __future__ import annotations

import logging
import zoneinfo
from datetime import datetime, timedelta, timezone, tzinfo

from mailbot_api.config import get_secret_optional
from mailbot_api.db import connection, queries

logger = logging.getLogger(__name__)


# Documented quiet-hours boundaries per AC-1.
_QUIET_START_HOUR = 22  # 22:00
_QUIET_END_HOUR = 8     # 08:00

# Dedup window + threshold per AC-2.
_DEDUP_WINDOW = timedelta(hours=1)
_DEDUP_THRESHOLD = 5


def _local_tz() -> tzinfo:
    """Resolve Adam's timezone from env. Defaults to UTC.

    Invalid zone name falls back to UTC with a warning log (so a typo in
    the deploy `.env` doesn't crash the dispatcher). On Windows where the
    IANA tz db isn't bundled, ``zoneinfo`` may not even resolve ``"UTC"``
    — in that case we use the stdlib ``timezone.utc`` directly.
    """
    tz_name = get_secret_optional("MAILBOT_LOCAL_TZ", "UTC")
    if tz_name == "UTC":
        # Stdlib path — works without the IANA tz db (Windows-friendly).
        return timezone.utc
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except zoneinfo.ZoneInfoNotFoundError:
        logger.warning(
            "MAILBOT_LOCAL_TZ unknown — falling back to UTC",
            extra={
                "event": "fatigue.tz.unknown",
                "configured": tz_name,
            },
        )
        return timezone.utc


def is_quiet_hours(now: datetime | None = None) -> bool:
    """Return True iff the current LOCAL time is 22:00–08:00.

    `now` defaults to `datetime.now(timezone.utc)`; passing an explicit
    value enables deterministic testing without monkey-patching the
    stdlib clock.
    """
    when_utc = now or datetime.now(timezone.utc)
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    local = when_utc.astimezone(_local_tz())
    hour = local.hour
    # Window wraps midnight — hour >= 22 OR hour < 8.
    return hour >= _QUIET_START_HOUR or hour < _QUIET_END_HOUR


async def is_muted(category: str, *, db_path: str) -> bool:
    """Reads the Story 5-6 `notification_mutes` table for the category.

    A row with `muted_until` in the future OR NULL (indefinite) means the
    category is muted. Expired rows are NOT auto-cleaned (a fast scheduler
    sweep would belong in Story 6-9 / cleanup); we just treat them as
    not-muted at read time.
    """
    row = await connection.fetchone(
        db_path, queries.NOTIFICATION_MUTES_SELECT_BY_CATEGORY, (category,)
    )
    if row is None:
        return False
    muted_until = row[1]
    if muted_until is None:
        return True  # indefinite mute
    # Compare as ISO strings — they're lexicographically sortable in UTC Z form.
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return bool(muted_until > now_iso)


async def should_dedup(
    category: str, tier: str, *, db_path: str
) -> tuple[bool, int | None]:
    """Returns (should_collapse, latest_id) where `should_collapse` is True
    iff the count of same-category-same-tier rows in the last hour is >=
    the threshold (5). `latest_id` is the most-recent row's id — the
    dispatcher rewrites THAT row's message to the summary form.
    """
    cutoff = (datetime.now(timezone.utc) - _DEDUP_WINDOW).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    row = await connection.fetchone(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_COUNT_SAME_CATEGORY_LAST_HOUR,
        (category, tier, cutoff),
    )
    if row is None:
        return False, None
    count = int(row[0])
    latest_id = row[1]
    if count >= _DEDUP_THRESHOLD and latest_id is not None:
        return True, int(latest_id)
    return False, None


__all__ = [
    "is_quiet_hours",
    "is_muted",
    "should_dedup",
    "_QUIET_START_HOUR",
    "_QUIET_END_HOUR",
    "_DEDUP_THRESHOLD",
]
