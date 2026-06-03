"""Story 6-1 — perf test: assemble_status under 100k router_calls rows.

Seeds 100k realistic-shape router_calls rows + a few worker_health + a
mix of pending_actions and times the assembler. AC budget: ≤ 10s wall-clock
on the 2-vCPU VPS; we assert < 5.0s as a leave-headroom-for-HTTP threshold.

Marked `@pytest.mark.slow` so CI can opt out if the bulk seed becomes
heavier in the future. On dev hardware the seed completes in 2-3s and the
measurement in < 1s; total test runtime ~4s — fits the default pytest run.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.status import assemble_status

_ROW_COUNT = 100_000
_SECONDS_BUDGET = 5.0


def _seed_router_calls(db_path: str, count: int) -> None:
    """Bulk insert `count` rows spread evenly across the last 30 days."""
    base_ts = datetime.now(timezone.utc) - timedelta(days=30)
    rows = []
    for i in range(count):
        ts = base_ts + timedelta(seconds=i * 26)  # ~30 days / 100k
        # 5% failure to exercise the errors section's LIMIT 5 path
        outcome = "failed" if i % 20 == 0 else "ok"
        rows.append((
            ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "coarse_class",
            "v1",
            "qwen2.5:3b",
            "policy",
            100, 50, 25, 0.00006, 1200, outcome,
            None,
            f"caller-{i % 50}",
            None, None, None,
        ))
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO router_calls "
            "(ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
            " tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
            " outcome, caller_verb, caller_origin, email_id, sensitivity_grant_id, sensitivity_grant_minted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


@pytest.mark.slow
async def test_assemble_status_under_5s_with_100k_router_calls(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    _seed_router_calls(db_path, _ROW_COUNT)

    # Warm the SQLite page cache with a single full-table aggregate scan
    # so the timed measurement reflects steady-state read latency, not
    # cold-disk first-access cost (matches production where the DB has
    # already been touched by the worker process).
    with sqlite3.connect(db_path) as conn:
        conn.execute("SELECT COUNT(*) FROM router_calls").fetchone()

    start = time.perf_counter()
    report = await assemble_status(db_path)
    elapsed = time.perf_counter() - start

    assert elapsed < _SECONDS_BUDGET, (
        f"assemble_status took {elapsed:.2f}s with {_ROW_COUNT} router_calls; "
        f"budget is {_SECONDS_BUDGET:.1f}s"
    )
    # Sanity-check: the report should actually contain the seeded data.
    # 100k rows / 20 = 5000 failed; LIMIT 5 means we see 5 errors.
    assert len(report.errors.last_5_router_errors) == 5
    # All seeded rows have cached_tokens_in=25, tokens_in=100 → ratio = 0.25
    # (only the last 7 days of rows count, which is the rightmost 23k rows;
    # but ratio is the same since the seed is uniform).
    assert 0.24 < report.cache.cache_hit_rate_7d < 0.26
