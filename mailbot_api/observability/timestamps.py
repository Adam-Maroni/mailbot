"""Shared UTC timestamp helpers — microsecond-precision ISO-8601 with `Z` suffix.

Single source for `utc_z_now()` across the codebase. Pre-Epic-5 retro decision:
microsecond precision so back-to-back same-second writes (drainer + audit-burst
surfaces) are strictly orderable by `ts` alone.

Format: `YYYY-MM-DDTHH:MM:SS.ffffffZ` (27 chars). The `_TS_FORMAT_RE` validator
in this module is **lenient**: it also accepts the legacy second-precision
shape `YYYY-MM-DDTHH:MM:SSZ` (20 chars) so existing DB rows written before this
change continue to parse. Writes use microseconds; reads accept either.

Why strict monotonicity (not just "microsecond precision"): Windows clock
resolution is ~16ms — back-to-back `datetime.now()` calls in a tight loop
CAN produce identical microsecond strings. The drainer + audit burst-write
surfaces order rows by `ts` alone, so identical ts strings break ordering.
This module enforces strict monotonicity by tracking the last-issued
timestamp under a thread lock and bumping the microsecond field by 1 if a
duplicate would be returned. The drift is bounded in practice: any real
gap of even a few microseconds resets the bump to 0, so the issued time
tracks wall-clock time within a few microseconds of truth even under
sustained burst load.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone

# Lenient regex: microseconds optional. Old (20-char) rows still validate;
# new writes always carry microseconds (27 chars).
_TS_FORMAT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")

_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_MICROSECOND = timedelta(microseconds=1)
_monotonic_lock = threading.Lock()
_last_issued: str = ""


def utc_z_now() -> str:
    """UTC ISO-8601 with `Z` suffix, microsecond precision, strictly monotonic.

    Example: `2026-06-02T14:23:45.123456Z`. Strictly monotonic across
    back-to-back calls — if the wall-clock value would equal or precede the
    most recently issued value (e.g. on Windows where `datetime.now()` has
    ~16ms resolution), advance by 1 microsecond instead.
    """
    global _last_issued
    candidate = datetime.now(timezone.utc).strftime(_FORMAT)
    with _monotonic_lock:
        if candidate <= _last_issued:
            # Parse `_last_issued`, add 1 microsecond, re-format. Avoids the
            # corner-case where the wall clock momentarily reads backward
            # (NTP correction) by guaranteeing forward motion regardless.
            last_dt = datetime.strptime(_last_issued, _FORMAT).replace(tzinfo=timezone.utc)
            bumped = last_dt + _MICROSECOND
            candidate = bumped.strftime(_FORMAT)
        _last_issued = candidate
    return candidate


def is_valid_ts(value: str) -> bool:
    """True if `value` matches the lenient UTC ISO-8601 Z-suffix shape.

    Accepts both microsecond-precision (post-2026-06-02) and second-precision
    (legacy DB rows) timestamps. Use in Pydantic validators to gate stored
    `ts` strings without rejecting historical data.
    """
    return bool(_TS_FORMAT_RE.match(value))
