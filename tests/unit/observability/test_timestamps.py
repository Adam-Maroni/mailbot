"""Tests for the shared microsecond-precision UTC timestamp helper.

Per Epic 4 retro action item #3 (2026-06-02), `utc_z_now()` returns
microsecond-precision UTC ISO-8601 with `Z` suffix so back-to-back same-second
writes (drainer + audit-burst surfaces) are strictly orderable by `ts` alone.

The validator `is_valid_ts` is **lenient** — accepts both microsecond (new)
and second-precision (legacy DB rows) shapes so existing data continues to
parse without a migration.
"""

from __future__ import annotations

from mailbot_api.observability.timestamps import is_valid_ts, utc_z_now


def test_utc_z_now_format_is_microsecond_precision_with_z_suffix() -> None:
    ts = utc_z_now()
    # `YYYY-MM-DDTHH:MM:SS.ffffffZ` — 27 characters total.
    assert len(ts) == 27
    assert ts.endswith("Z")
    # Position 19 holds the decimal point separating seconds and microseconds.
    assert ts[19] == "."


def test_utc_z_now_strictly_monotonic_across_back_to_back_calls() -> None:
    """The five-epic carryover this fix closes.

    Before microsecond precision, two `utc_z_now()` calls in the same second
    produced equal strings — the drainer / audit burst-write surfaces could
    not be ordered by `ts` alone. With microseconds, back-to-back calls on
    any platform CPython supports produce strictly increasing strings.
    """
    samples = [utc_z_now() for _ in range(50)]
    # Strictly increasing lexicographically (and chronologically, since the
    # format is ordered left-to-right by significance).
    for previous, current in zip(samples, samples[1:]):
        assert current > previous, (
            f"non-monotonic ts pair detected: {previous!r} -> {current!r}"
        )


def test_is_valid_ts_accepts_microsecond_shape() -> None:
    assert is_valid_ts("2026-06-02T14:23:45.123456Z")


def test_is_valid_ts_accepts_legacy_second_precision_shape() -> None:
    """Lenient regex keeps legacy DB rows parseable.

    Pre-2026-06-02 writes from Stories 1-x / 2-x / 3-x / 4-x landed at
    second-precision. Hard-failing those would break read-side queries
    against existing rows (response_cache lookup, oauth_state token expiry
    check, worker heartbeat parse). Accept both shapes.
    """
    assert is_valid_ts("2026-06-02T14:23:45Z")


def test_is_valid_ts_accepts_partial_microsecond_digit_counts() -> None:
    """Some strftime implementations emit fewer than 6 microsecond digits.

    The format spec calls for 6 digits, but the regex is `\\.\\d{1,6}` to be
    tolerant of any explicit caller that supplies a shorter fractional part.
    """
    for fractional in ("1", "12", "123", "1234", "12345", "123456"):
        assert is_valid_ts(f"2026-06-02T14:23:45.{fractional}Z"), fractional


def test_is_valid_ts_rejects_malformed_shapes() -> None:
    bad = [
        "",
        "not-a-timestamp",
        "2026-06-02T14:23:45",  # missing Z
        "2026-06-02 14:23:45Z",  # space instead of T
        "2026-06-02T14:23:45.Z",  # decimal with no digits
        "2026-06-02T14:23:45.1234567Z",  # > 6 microsecond digits
        "2026-06-02T14:23:45.123456",  # missing Z after microseconds
        "2026/06/02T14:23:45Z",  # wrong date separators
    ]
    for value in bad:
        assert not is_valid_ts(value), f"unexpectedly accepted: {value!r}"
