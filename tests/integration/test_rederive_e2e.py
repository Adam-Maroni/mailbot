"""Story 3-8 AC-8: rederive plan + execute end-to-end tests.

Reuses the fake-adapter pattern from test_pipeline_e2e.py.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.ingest.rederive import (
    VALID_RE_DERIVATION_TASKS,
    execute_rederive,
    plan_rederive,
)
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_QWEN = "qwen2.5:3b-instruct-q4_K_M"


class _FakeAdapter:
    model_id = _QWEN

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls = 0

    async def call(self, system, user, max_tokens_out, temperature=0.0):
        self.calls += 1
        return AdapterResponse(
            text=json.dumps(self._payload),
            tokens_in=5,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=10,
            raw={},
        )

    async def embed(self, text):
        raise RuntimeError("no embed")


_POLICY_YAML = f"""\
version: "test-rederive-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
"""


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
    return db_path


async def _seed_email_classified(
    db_path: str,
    *,
    graph_id: str,
    received_at: str = "2026-05-15T00:00:00Z",
    coarse_class: str | None = None,
    coarse_prompt_v: str = "v1",
) -> None:
    """Seed an email row WITH sensitivity_at populated (precondition satisfied)."""
    sql = (
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model"
    )
    vals = [graph_id, received_at, "s", "x@y.com", "body",
            "normal", "2026-05-01T00:00:00Z", "v1", 0.9, _QWEN]
    if coarse_class is not None:
        sql += ", class_coarse, class_coarse_at, class_coarse_prompt_v, class_coarse_model"
        vals += [coarse_class, "2026-05-02T00:00:00Z", coarse_prompt_v, _QWEN]
    sql += ") VALUES (" + ", ".join("?" * len(vals)) + ")"
    await execute_write(db_path, sql, tuple(vals))


async def _seed_email_unclassified(db_path: str, *, graph_id: str) -> None:
    """Seed an email row WITHOUT sensitivity_at (blocks non-sensitivity rederivation)."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) "
        "VALUES (?, ?, ?, ?, ?)",
        (graph_id, "2026-05-15T00:00:00Z", "s", "x@y.com", "body"),
    )


async def test_valid_rederivation_tasks_includes_all_seven(_clean_state: Any) -> None:
    """All 7 ingest tasks are valid re-derivation targets."""
    expected = {
        "sensitivity_class",
        "coarse_class",
        "fine_class",
        "summary_short",
        "importance_scoring",
        "action_extraction",
        "embedding",
    }
    assert set(VALID_RE_DERIVATION_TASKS) == expected


async def test_plan_rederive_coarse_class_selects_rows_with_old_prompt_v(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2: rows with prompt_v != target are selected; rows at target are not."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"class_coarse": "newsletter", "confidence": 0.9}))
    # Row 1: NO class_coarse → should be selected.
    await _seed_email_classified(db_path, graph_id="r-1")
    # Row 2: class_coarse already at v1 (matches target) → NOT selected.
    await _seed_email_classified(db_path, graph_id="r-2", coarse_class="human", coarse_prompt_v="v1")
    # Row 3: class_coarse at OLD v0 (doesn't match v1) → selected.
    await _seed_email_classified(db_path, graph_id="r-3", coarse_class="human", coarse_prompt_v="v0")

    plan = await plan_rederive(
        task="coarse_class",
        since=date(2026, 4, 1),
        prompt_version=None,  # resolves to policy's "v1"
        db_path=db_path,
    )

    assert plan.task == "coarse_class"
    assert plan.prompt_version == "v1"
    assert plan.model == _QWEN
    assert set(plan.email_ids) == {"r-1", "r-3"}
    assert plan.count == 2
    assert plan.blocked_by_sensitivity_count == 0


async def test_plan_rederive_blocks_when_any_row_unclassified(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-4: non-sensitivity task with any sensitivity_at IS NULL row → blocked count > 0."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"class_coarse": "newsletter", "confidence": 0.9}))
    await _seed_email_unclassified(db_path, graph_id="unc-1")

    plan = await plan_rederive(
        task="coarse_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        db_path=db_path,
    )

    assert plan.count == 1
    assert plan.blocked_by_sensitivity_count == 1


async def test_plan_rederive_sensitivity_does_not_self_block(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-4: sensitivity_class is the gate itself; not blocked by its own NULL."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"sensitivity": "normal", "confidence": 0.9, "reason": "ok"}))
    await _seed_email_unclassified(db_path, graph_id="unc-1")

    plan = await plan_rederive(
        task="sensitivity_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        db_path=db_path,
    )

    assert plan.count == 1
    assert plan.blocked_by_sensitivity_count == 0


async def test_execute_rederive_coarse_class_writes_value_and_idempotency(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-3: execute_rederive dispatches + writes + records idempotency."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"class_coarse": "newsletter", "confidence": 0.9}))
    await _seed_email_classified(db_path, graph_id="r-1")

    plan = await plan_rederive(
        task="coarse_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        db_path=db_path,
    )
    result = await execute_rederive(plan=plan, db_path=db_path)

    assert result.processed == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.aborted is False

    row = await fetchone(
        db_path,
        "SELECT class_coarse, class_coarse_prompt_v FROM emails WHERE graph_id = ?",
        ("r-1",),
    )
    assert row is not None
    assert row[0] == "newsletter"
    assert row[1] == "v1"

    idem = await fetchall(
        db_path,
        "SELECT task_type FROM derivations_idempotency WHERE email_id = ?",
        ("r-1",),
    )
    assert idem == [("coarse_class",)]


async def test_execute_rederive_sensitivity_clears_downstream_fields(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: re-deriving sensitivity wipes downstream derived fields first."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"sensitivity": "sensitive", "confidence": 0.9, "reason": "x"}))
    # Seed with populated downstream values.
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model, "
        "class_coarse, class_coarse_at, class_coarse_prompt_v, class_coarse_model, "
        "summary_short, summary_short_at, summary_short_prompt_v, summary_short_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "r-1", "2026-05-15T00:00:00Z", "s", "x@y.com", "body",
            "normal", "2026-05-01T00:00:00Z", "v0", 0.5, _QWEN,
            "human", "2026-05-02T00:00:00Z", "v1", _QWEN,
            "old summary", "2026-05-02T00:00:00Z", "v1", "claude-haiku-4-5-20251001",
        ),
    )
    # Also seed an idempotency row so we can confirm it's cleared.
    await execute_write(
        db_path,
        "INSERT INTO derivations_idempotency (email_id, task_type, idempotency_key, applied_at) "
        "VALUES (?, ?, ?, ?)",
        ("r-1", "coarse_class", "old-key", "2026-05-02T00:00:00Z"),
    )

    plan = await plan_rederive(
        task="sensitivity_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        db_path=db_path,
    )
    # Row 1 already has sensitivity_at + prompt_v=v0 (policy is v1) → selected.
    assert plan.count == 1

    result = await execute_rederive(plan=plan, db_path=db_path)
    assert result.succeeded == 1

    # Downstream fields cleared.
    row = await fetchone(
        db_path,
        "SELECT class_coarse, class_coarse_at, summary_short, summary_short_at "
        "FROM emails WHERE graph_id = ?",
        ("r-1",),
    )
    assert row == (None, None, None, None)

    # Idempotency row deleted.
    idem = await fetchall(
        db_path,
        "SELECT task_type FROM derivations_idempotency WHERE email_id = ?",
        ("r-1",),
    )
    assert idem == []

    # New sensitivity classification persisted.
    sens_row = await fetchone(
        db_path,
        "SELECT sensitivity, sensitivity_prompt_v FROM emails WHERE graph_id = ?",
        ("r-1",),
    )
    assert sens_row[0] == "sensitive"


async def test_execute_rederive_zero_rows_no_op(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2: an empty plan returns processed=0, no router calls."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"class_coarse": "newsletter", "confidence": 0.9}))
    # No emails seeded.

    plan = await plan_rederive(
        task="coarse_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        db_path=db_path,
    )
    assert plan.count == 0

    result = await execute_rederive(plan=plan, db_path=db_path)
    assert result.processed == 0
    assert result.succeeded == 0
    assert result.failed == 0


async def test_execute_rederive_uses_cli_rederive_caller_origin(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-7: dispatches carry caller_origin='cli-rederive'."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeAdapter({"class_coarse": "newsletter", "confidence": 0.9}))
    await _seed_email_classified(db_path, graph_id="r-1")

    plan = await plan_rederive(
        task="coarse_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        db_path=db_path,
    )
    await execute_rederive(plan=plan, db_path=db_path)

    rows = await fetchall(
        db_path,
        "SELECT caller_origin FROM router_calls WHERE task_type = 'coarse_class'",
        (),
    )
    assert rows == [("cli-rederive",)]


async def test_plan_rederive_unknown_task_raises(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2: unknown task value raises ValueError before any DB work."""
    db_path = _setup(tmp_path)

    with pytest.raises(ValueError, match="unknown task"):
        await plan_rederive(
            task="bogus_task",
            since=date(2026, 4, 1),
            prompt_version=None,
            db_path=db_path,
        )
