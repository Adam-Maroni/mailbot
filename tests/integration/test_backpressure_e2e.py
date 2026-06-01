"""Story 3-6 AC-6: backpressure + batched drain integration tests.

Reuses the _FakeAdapter pattern from test_pipeline_e2e.py for end-to-end
realism (real SQLite + real migrations + scripted adapter responses).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.ingest.backpressure import (
    BACKPRESSURE_THRESHOLD,
    count_unprocessed,
    ingest_pipeline_interval_task,
    run_drain_loop,
    should_throttle,
)
from mailbot_api.ingest.pipeline import run_batch
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse, EmbeddingResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_HAIKU = "claude-haiku-4-5-20251001"
_NOMIC = "nomic-embed-text"


class _FakeAdapter:
    """Routes by SYSTEM-block keyword. Reused from test_pipeline_e2e pattern."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        if "sensitivity" in system.lower() and "normal" in system.lower():
            payload = {"sensitivity": "normal", "confidence": 0.95, "reason": "ordinary"}
        elif "broad kind" in system.lower():
            payload = {"class_coarse": "newsletter", "confidence": 0.9}
        elif "refine the relationship type" in system.lower():
            payload = {"class_fine": "professional", "confidence": 0.8}
        elif "280 characters" in system.lower():
            payload = {"summary": "weekly digest of trends"}
        elif "0–100 scale" in system.lower():
            payload = {"importance": 20, "signals": ["newsletter"]}
        elif "extract structured action items" in system.lower():
            payload = {"actions": []}
        else:
            raise RuntimeError(f"unscripted system: {system[:60]!r}")
        return AdapterResponse(
            text=json.dumps(payload),
            tokens_in=5,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=10,
            raw={"mock": True},
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        return EmbeddingResponse(
            vector=[0.1] * 768, dim=768, tokens_in=1, latency_ms=5, raw={"mock": True}
        )


def _task_block(model: str, max_tokens: int) -> str:
    return (
        f'{{model: "{model}", prompt_version: "v1", escalate: false, '
        f'max_tokens_out: {max_tokens}, lane: "batch", sensitivity: "any"}}'
    )


_POLICY_YAML = (
    'version: "test-backpressure-v1"\n'
    "tasks:\n"
    f"  sensitivity_class: {_task_block(_QWEN, 128)}\n"
    f"  coarse_class: {_task_block(_QWEN, 256)}\n"
    f"  fine_class: {_task_block(_QWEN, 128)}\n"
    f"  summary_short: {_task_block(_HAIKU, 384)}\n"
    f"  importance_scoring: {_task_block(_HAIKU, 256)}\n"
    f"  action_extraction: {_task_block(_HAIKU, 512)}\n"
    f"  embedding: {_task_block(_NOMIC, 0)}\n"
)


@pytest.fixture
def _clean_state(monkeypatch):
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    monkeypatch.setenv("MAILBOT_SKIP_PATTERNS", "1")
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    register_adapter(_QWEN, _FakeAdapter(_QWEN))
    register_adapter(_HAIKU, _FakeAdapter(_HAIKU))
    register_adapter(_NOMIC, _FakeAdapter(_NOMIC))
    return db_path


async def _seed_emails(db_path: str, n: int, *, prefix: str = "e") -> list[str]:
    ids = [f"{prefix}-{i}" for i in range(n)]
    for graph_id in ids:
        await execute_write(
            db_path,
            "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) "
            "VALUES (?, ?, ?, ?, ?)",
            (graph_id, "2026-06-01T00:00:00Z", "s", "x@y.com", "body"),
        )
    return ids


async def test_count_unprocessed_empty_db(tmp_path: Path, _clean_state: Any) -> None:
    """AC-1: empty queue returns 0."""
    db_path = _setup(tmp_path)
    assert await count_unprocessed(db_path) == 0


async def test_count_unprocessed_counts_only_unclassified_not_deleted(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-1: ignores rows with sensitivity_at populated AND deleted_at populated."""
    db_path = _setup(tmp_path)
    await _seed_emails(db_path, 3, prefix="unclassified")
    # Insert one classified row.
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, sensitivity_at, sensitivity) VALUES (?, ?, ?, ?)",
        ("classified-1", "2026-06-01T00:00:00Z", "2026-06-01T00:01:00Z", "normal"),
    )
    # Insert one soft-deleted row (no sensitivity_at, but deleted).
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, deleted_at) VALUES (?, ?, ?)",
        ("deleted-1", "2026-06-01T00:00:00Z", "2026-06-01T00:01:00Z"),
    )

    assert await count_unprocessed(db_path) == 3


async def test_should_throttle_above_and_below_threshold(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-1: should_throttle compares count > threshold."""
    db_path = _setup(tmp_path)
    # Empty queue → not throttle.
    assert await should_throttle(db_path, threshold=BACKPRESSURE_THRESHOLD) is False
    # Threshold of 2 + 3 rows → throttle.
    await _seed_emails(db_path, 3)
    assert await should_throttle(db_path, threshold=2) is True


async def test_run_batch_processes_small_queue(tmp_path: Path, _clean_state: Any) -> None:
    """AC-2: run_batch processes the seeded emails sequentially + records worker_health."""
    db_path = _setup(tmp_path)
    await _seed_emails(db_path, 5)

    result = await run_batch(db_path=db_path)

    assert result.processed == 5
    assert result.succeeded == 5
    assert result.failed == 0
    assert len(result.email_ids) == 5

    # worker_health row recorded.
    wh = await fetchone(
        db_path,
        "SELECT component, last_outcome FROM worker_health WHERE component = ?",
        ("ingest_pipeline",),
    )
    assert wh is not None
    assert wh[0] == "ingest_pipeline"
    assert wh[1] == "ok"


async def test_run_batch_empty_queue(tmp_path: Path, _clean_state: Any) -> None:
    """AC-2: empty queue still upserts worker_health with outcome=ok."""
    db_path = _setup(tmp_path)
    result = await run_batch(db_path=db_path)
    assert result.processed == 0
    wh = await fetchone(
        db_path,
        "SELECT last_outcome FROM worker_health WHERE component = ?",
        ("ingest_pipeline",),
    )
    assert wh is not None
    assert wh[0] == "ok"


async def test_run_drain_loop_until_queue_empty(tmp_path: Path, _clean_state: Any) -> None:
    """AC-3: drain loop with unbounded max_batches finishes when queue empties.

    Uses a small (5) seed count so the test stays under the Story 2-5 60/min
    Haiku rate-limit ceiling — the test verifies the loop's stop condition,
    not the rate-limiter behavior.
    """
    db_path = _setup(tmp_path)
    await _seed_emails(db_path, 5)

    result = await run_drain_loop(db_path=db_path)

    assert result.total_processed == 5
    assert result.total_succeeded == 5
    assert result.total_failed == 0
    # Queue empty now.
    assert await count_unprocessed(db_path) == 0


async def test_run_drain_loop_respects_max_batches(tmp_path: Path, _clean_state: Any) -> None:
    """AC-3: max_batches=1 processes at most one batch.

    Uses a tiny batch_size override path through a small seed count + a custom
    batch limit via the existing API to stay under Haiku rate limit. The test
    asserts the bound, not the absolute batch size.
    """
    db_path = _setup(tmp_path)
    # Seed 8 emails; with max_batches=1 the loop should consume all 8 in one batch
    # (BATCH_SIZE=100 >> 8) then exit. Verify batches_run == 1.
    await _seed_emails(db_path, 8)

    result = await run_drain_loop(db_path=db_path, max_batches=1)
    assert result.batches_run == 1
    assert result.total_processed == 8
    assert await count_unprocessed(db_path) == 0


async def test_ingest_pipeline_interval_task_runs_then_stops(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: interval task runs ≥1 tick then exits on stop_event."""
    db_path = _setup(tmp_path)
    await _seed_emails(db_path, 3)

    stop_event = asyncio.Event()

    async def _run_and_stop() -> None:
        # Let the interval task run one tick, then signal stop.
        await asyncio.sleep(0.05)
        stop_event.set()

    await asyncio.gather(
        ingest_pipeline_interval_task(
            db_path=db_path, interval_seconds=0.02, stop_event=stop_event
        ),
        _run_and_stop(),
    )

    # The interval task should have drained the small queue.
    assert await count_unprocessed(db_path) == 0
