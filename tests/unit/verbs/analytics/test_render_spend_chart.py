"""Tests for mailbot_api/verbs/analytics/render_spend_chart.py — Story 6-8.

The verb renders a 1200×800 PNG horizontal bar chart of cost-per-task over
a today/week/month window. Tests cover:

- valid PNG output + dimensions
- top-task identification
- empty-data graceful path (no division-by-zero, valid PNG with placeholder)
- period window math (today / week / month boundaries)
- sort order (highest-cost first)
- monthly subtitle rendering
- AR-ANALYTICS-2 "never write to disk" invariant
- matplotlib `plt.close` memory hygiene
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow, record_router_call
from mailbot_api.verbs.analytics import RenderSpendChartOut, render_spend_chart
from mailbot_api.verbs.analytics.render_spend_chart import _period_window_start

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def _fresh_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "spend.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed(
    db_path: str,
    *,
    task_type: str,
    cost: float,
    ts: datetime | None = None,
    model: str = "qwen2.5:3b",
    caller_origin: str = "verb-ask-router",
) -> None:
    """Insert a single router_calls row via the audit-writer boundary.

    `ts` defaults to now-UTC; pass an older datetime to exercise period-window
    math.
    """
    effective_ts = ts if ts is not None else datetime.now(timezone.utc)
    row = RouterCallRow(
        task_type=task_type,
        prompt_version="v1",
        model_chosen=model,
        # Story 9.2: closed-set vocabulary; was "policy" pre-9.2.
        model_chosen_reason=f"policy:{task_type}:default",
        cost_usd_estimated=cost,
        tokens_in=100,
        cached_tokens_in=0,
        outcome="ok",
        caller_origin=caller_origin,
        ts=effective_ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )
    await record_router_call(row, db_path=db_path)


def _png_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Parse width/height from the PNG IHDR chunk.

    PNG layout: 8-byte signature + 25-byte IHDR chunk (length=13 bytes, type
    'IHDR', width:uint32, height:uint32, ...). Width is at offset 16, height
    at offset 20, both big-endian uint32.
    """
    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "not a PNG"
    width, height = struct.unpack(">II", image_bytes[16:24])
    return width, height


# ---------------------------------------------------------------------------
# Test 1: PNG validity
# ---------------------------------------------------------------------------


async def test_render_returns_valid_png(_fresh_db: str) -> None:
    await _seed(_fresh_db, task_type="coarse_class", cost=0.10)
    await _seed(_fresh_db, task_type="fine_class", cost=0.05)
    await _seed(_fresh_db, task_type="summary_short", cost=0.02)

    out = await render_spend_chart("today", db_path=_fresh_db)

    assert isinstance(out, RenderSpendChartOut)
    assert out.mime_type == "image/png"
    assert out.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")  # PNG magic
    assert len(out.image_bytes) > 1000  # sanity: not a stub


# ---------------------------------------------------------------------------
# Test 2: Dimensions are exactly 1200x800
# ---------------------------------------------------------------------------


async def test_render_dimensions_are_1200_x_800(_fresh_db: str) -> None:
    await _seed(_fresh_db, task_type="coarse_class", cost=0.10)
    out = await render_spend_chart("today", db_path=_fresh_db)
    width, height = _png_dimensions(out.image_bytes)
    assert width == 1200
    assert height == 800


# ---------------------------------------------------------------------------
# Test 3: top_task matches the highest-cost task in the period
# ---------------------------------------------------------------------------


async def test_render_top_task_is_highest_cost(_fresh_db: str) -> None:
    await _seed(_fresh_db, task_type="coarse_class", cost=0.05)
    await _seed(_fresh_db, task_type="fine_class", cost=0.20)
    await _seed(_fresh_db, task_type="summary_short", cost=0.10)

    out = await render_spend_chart("today", db_path=_fresh_db)

    assert out.top_task == "fine_class"
    assert out.task_count == 3
    assert out.total_usd == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# Test 4: Empty data returns a valid PNG with placeholder + zero totals
# ---------------------------------------------------------------------------


async def test_render_empty_data_returns_placeholder_png(_fresh_db: str) -> None:
    out = await render_spend_chart("today", db_path=_fresh_db)

    assert out.task_count == 0
    assert out.total_usd == 0.0
    assert out.top_task == ""
    # The empty-path STILL returns a valid PNG (defensive — Discord-side
    # dispatcher always has something to attach).
    assert out.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = _png_dimensions(out.image_bytes)
    assert width == 1200
    assert height == 800


# ---------------------------------------------------------------------------
# Test 5: Period windows — today / week / month
# ---------------------------------------------------------------------------


async def test_period_today_excludes_yesterday(_fresh_db: str) -> None:
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    await _seed(_fresh_db, task_type="coarse_class", cost=0.10, ts=yesterday)
    await _seed(_fresh_db, task_type="fine_class", cost=0.20)  # default = now

    out = await render_spend_chart("today", db_path=_fresh_db)

    # `today` = since 00:00:00Z today. Yesterday's row is excluded.
    assert out.task_count == 1
    assert out.top_task == "fine_class"
    assert out.total_usd == pytest.approx(0.20)


async def test_period_week_includes_5_days_ago_but_not_30_days_ago(
    _fresh_db: str,
) -> None:
    now = datetime.now(timezone.utc)
    five_days_ago = now - timedelta(days=5)
    thirty_days_ago = now - timedelta(days=30)

    await _seed(_fresh_db, task_type="coarse_class", cost=0.10, ts=five_days_ago)
    await _seed(_fresh_db, task_type="fine_class", cost=0.99, ts=thirty_days_ago)

    out = await render_spend_chart("week", db_path=_fresh_db)

    # 5 days ago is INSIDE the 7-day window; 30 days ago is OUTSIDE.
    assert out.task_count == 1
    assert out.top_task == "coarse_class"
    assert out.total_usd == pytest.approx(0.10)


async def test_period_month_includes_current_month_rows(_fresh_db: str) -> None:
    """CR MED-4 fix: seed at `now` (no explicit ts) — always within the
    current month regardless of clock-of-day. The previous `now - 1h` seed
    flaked on the 1st of the month before 01:00 UTC because `one_hour_ago`
    landed on the previous month, outside the `month` window."""
    await _seed(_fresh_db, task_type="summary_short", cost=0.50)

    out = await render_spend_chart("month", db_path=_fresh_db)

    assert out.task_count == 1
    assert out.total_usd == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Test 6: Sort order (highest cost first)
# ---------------------------------------------------------------------------


async def test_render_sorts_descending_by_cost(_fresh_db: str) -> None:
    """The verb sorts in Python after the SQL GROUP BY because SQLite's
    GROUP BY doesn't guarantee row order. Verify the top_task lands on the
    highest-cost task regardless of insertion order."""
    await _seed(_fresh_db, task_type="summary_short", cost=0.30)
    await _seed(_fresh_db, task_type="fine_class", cost=0.10)
    await _seed(_fresh_db, task_type="coarse_class", cost=0.20)

    out = await render_spend_chart("today", db_path=_fresh_db)

    assert out.top_task == "summary_short"
    assert out.total_usd == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Test 7: Monthly subtitle is rendered (smoke — verify PNG renders without
# crashing on the month-only code path).
# ---------------------------------------------------------------------------


async def test_render_month_period_does_not_crash_with_subtitle(
    _fresh_db: str,
) -> None:
    """The month period adds a `$X of $30 month cap` subtitle (defender tone).
    Test that rendering month-with-data succeeds — visual subtitle inspection
    is deferred to Phase 3.5."""
    await _seed(_fresh_db, task_type="coarse_class", cost=1.50)

    out = await render_spend_chart("month", db_path=_fresh_db)

    assert out.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert out.period == "month"
    width, height = _png_dimensions(out.image_bytes)
    assert width == 1200
    assert height == 800


# ---------------------------------------------------------------------------
# Test 8: No disk write — AR-ANALYTICS-2 invariant
# ---------------------------------------------------------------------------


async def test_render_never_writes_png_to_disk(
    _fresh_db: str, tmp_path: Path
) -> None:
    """Per AR-ANALYTICS-2, the verb returns bytes — it must NEVER write the
    rendered PNG to disk. Verify by snapshotting the temp dir before/after."""
    await _seed(_fresh_db, task_type="coarse_class", cost=0.10)

    before = set(tmp_path.rglob("*"))
    out = await render_spend_chart("today", db_path=_fresh_db)
    after = set(tmp_path.rglob("*"))

    new_files = after - before
    # Only the SQLite db's WAL/SHM sidecars are allowed; no .png file
    png_files = [p for p in new_files if p.suffix == ".png"]
    assert png_files == [], f"verb leaked PNG files to disk: {png_files}"
    assert out.image_bytes  # but bytes WERE returned


# ---------------------------------------------------------------------------
# Test 9: plt.close was called — memory hygiene regression guard
# ---------------------------------------------------------------------------


async def test_render_calls_plt_close_to_release_fig(_fresh_db: str) -> None:
    """The agg renderer caches per-Figure state; without an explicit
    `plt.close(fig)` the long-running worker process leaks. Patch
    `plt.close` and confirm at least one invocation per render call."""
    await _seed(_fresh_db, task_type="coarse_class", cost=0.10)

    with patch(
        "mailbot_api.verbs.analytics.render_spend_chart.plt.close"
    ) as mock_close:
        await render_spend_chart("today", db_path=_fresh_db)

    assert mock_close.call_count >= 1, (
        "plt.close was not called — Figure leaked"
    )


# ---------------------------------------------------------------------------
# Test 10: Invalid period raises ValueError (defensive — Literal at type-time,
# explicit guard at runtime)
# ---------------------------------------------------------------------------


async def test_render_invalid_period_raises(_fresh_db: str) -> None:
    """Mirrors Story 5-6 CR-2 defensive guard in cost.py — MCP-decoded JSON
    at runtime could pass a string the Literal annotation forbids; the verb
    raises explicitly."""
    with pytest.raises(ValueError, match="invalid period"):
        await render_spend_chart("year", db_path=_fresh_db)  # type: ignore[arg-type]


def test_period_window_start_today_format() -> None:
    """Helper exposed for window-math verification."""
    out = _period_window_start("today")
    # Format: YYYY-MM-DDT00:00:00Z
    assert out.endswith("T00:00:00Z")
    assert len(out) == 20


def test_period_window_start_month_format() -> None:
    out = _period_window_start("month")
    # Format: YYYY-MM-01T00:00:00Z (always starts at first of month)
    assert "-01T00:00:00Z" in out


def test_period_window_start_invalid_raises() -> None:
    with pytest.raises(ValueError):
        _period_window_start("year")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CR HIGH-1 regression: PNG bytes must JSON-serialize without raising. Bare
# `bytes` fields crash pydantic_core.to_json on non-UTF-8 sequences (every
# real PNG). The field_serializer must base64-encode for the MCP transport.
# ---------------------------------------------------------------------------


async def test_model_dump_json_does_not_crash_on_png_bytes(_fresh_db: str) -> None:
    """Mimics FastMCP's _convert_to_content serialization path: call
    `model_dump_json()` on the verb result. Pre-fix this crashed with
    `PydanticSerializationError: invalid utf-8 sequence`. Post-fix the
    `field_serializer(when_used="json")` base64-encodes the PNG bytes."""
    import base64
    import json

    await _seed(_fresh_db, task_type="coarse_class", cost=0.10)
    out = await render_spend_chart("today", db_path=_fresh_db)

    # The critical path — must not raise.
    json_payload = out.model_dump_json()
    decoded = json.loads(json_payload)

    # JSON carries a base64 string, not raw bytes.
    assert isinstance(decoded["image_bytes"], str)
    # The base64 string decodes back to the original PNG bytes.
    round_tripped = base64.b64decode(decoded["image_bytes"])
    assert round_tripped == out.image_bytes
    assert round_tripped.startswith(b"\x89PNG\r\n\x1a\n")


def test_model_dump_python_keeps_raw_bytes() -> None:
    """`when_used="json"` must NOT touch `mode="python"` dumps — Python
    callers (the verb side, MCP wrapper before serialization) need raw
    bytes for in-process consumers."""
    raw_png_magic = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    model = RenderSpendChartOut(
        image_bytes=raw_png_magic,
        period="today",
        total_usd=0.0,
        task_count=0,
        top_task="",
    )
    py_dump = model.model_dump(mode="python")
    assert py_dump["image_bytes"] == raw_png_magic
    assert isinstance(py_dump["image_bytes"], bytes)
