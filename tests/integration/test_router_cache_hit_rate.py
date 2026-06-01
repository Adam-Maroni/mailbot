"""Per-task cache-hit-rate aggregation via raw SQL against router_calls
(Story 2-6 AC-8). No pandas — architecture AR-BOOT-2 deferral.
"""

from __future__ import annotations

from pathlib import Path

from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow, record_router_call


async def test_cache_hit_rate_raw_sql_aggregation(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    # Three Haiku calls for the same task_type: 1 cold + 2 warm.
    rows = [
        RouterCallRow(
            task_type="summary_short",
            prompt_version="v1",
            model_chosen="claude-haiku-4-5-20251001",
            model_chosen_reason="policy",
            tokens_in=100,
            tokens_out=20,
            cached_tokens_in=0,
            outcome="ok",
        ),
        RouterCallRow(
            task_type="summary_short",
            prompt_version="v1",
            model_chosen="claude-haiku-4-5-20251001",
            model_chosen_reason="policy",
            tokens_in=100,
            tokens_out=20,
            cached_tokens_in=80,
            outcome="ok",
        ),
        RouterCallRow(
            task_type="summary_short",
            prompt_version="v1",
            model_chosen="claude-haiku-4-5-20251001",
            model_chosen_reason="policy",
            tokens_in=100,
            tokens_out=20,
            cached_tokens_in=80,
            outcome="ok",
        ),
    ]
    for row in rows:
        await record_router_call(row, db_path=db_path)

    # Per-task cache-hit-rate query (raw SQL, no pandas).
    result = await fetchone(
        db_path,
        "SELECT SUM(cached_tokens_in) * 1.0 / NULLIF(SUM(tokens_in), 0) "
        "FROM router_calls WHERE task_type = ?",
        ("summary_short",),
    )
    assert result is not None
    cache_hit_rate = result[0]
    # 160 cached / 300 input = 0.5333...
    assert cache_hit_rate is not None
    assert abs(cache_hit_rate - (160.0 / 300.0)) < 1e-9
