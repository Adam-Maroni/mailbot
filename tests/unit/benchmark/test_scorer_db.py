"""Unit tests for ``benchmark/scorer_db.py`` + ``BenchmarkScoreRow`` (Story 9-7 AC-2, 3).

Real-disk SQLite (``tmp_path``) per the Middleware-Real-Bootstrap MailBot
reframing. The single-writer monopoly + INSERT OR REPLACE semantics are
the load-bearing contracts validated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmark.db import record_benchmark_run
from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from benchmark.scorer_db import (
    encode_extra_json,
    read_run_runs,
    read_run_scores,
    record_benchmark_score,
)
from mailbot_api.db.migrations_runner import apply_pending_migrations


def _score_row(**overrides: object) -> BenchmarkScoreRow:
    base: dict[str, object] = {
        "run_id": "run-1",
        "cohort_key": "cohort-abc",
        "task_type": "coarse_class",
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "prompt_version": "v1",
        "scorer_model": "objective:mechanical",
        "evaluator_role": "primary",
        "metric_name": "accuracy",
        "metric_value": 0.95,
        "sample_count": 20,
        "outcome": "ok",
        "extra_json": None,
        "computed_at": "2026-06-28T00:00:00Z",
    }
    base.update(overrides)
    return BenchmarkScoreRow.model_validate(base)


def _run_row(**overrides: object) -> BenchmarkRunRow:
    base: dict[str, object] = {
        "run_id": "run-1",
        "corpus_item_id": "corpus-v1-001",
        "task_type": "coarse_class",
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "prompt_version": "v1",
        "cohort_key": "cohort-abc",
        "output_json": '{"class_coarse":"transactional"}',
        "tokens_in": 10,
        "tokens_out": 5,
        "cached_tokens_in": 0,
        "cost_usd": 0.0,
        "latency_ms": 12,
        "outcome": "ok",
        "status": "completed",
        "scorer_model": "claude-opus-4-7-20251220",
        "anchors_version": "v1",
        "router_policy_version": "test-policy-v1",
        "ran_at": "2026-06-28T00:00:00Z",
    }
    base.update(overrides)
    return BenchmarkRunRow.model_validate(base)


def test_benchmark_score_row_rejects_extra_fields() -> None:
    """AC-2: extra=forbid on BenchmarkScoreRow."""
    with pytest.raises(ValidationError):
        BenchmarkScoreRow.model_validate(
            {
                **_score_row().model_dump(),
                "definitely_not_a_field": True,
            }
        )


def test_benchmark_score_row_rejects_unknown_evaluator_role() -> None:
    """AC-2: closed-set evaluator_role Literal enforcement."""
    with pytest.raises(ValidationError):
        _score_row(evaluator_role="tertiary")


def test_benchmark_score_row_rejects_unknown_outcome() -> None:
    """AC-2: closed-set outcome Literal enforcement."""
    with pytest.raises(ValidationError):
        _score_row(outcome="weird_state")


async def test_record_benchmark_score_writes_and_returns_id(tmp_path: Path) -> None:
    """AC-3.1: record_benchmark_score returns the inserted id."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    new_id = await record_benchmark_score(db_path, _score_row())
    assert new_id > 0


async def test_record_benchmark_score_upsert_overwrites_on_unique_conflict(tmp_path: Path) -> None:
    """AC-3.1: INSERT OR REPLACE overwrites prior row keyed on the 7-column UNIQUE."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    first_id = await record_benchmark_score(db_path, _score_row(metric_value=0.5))
    second_id = await record_benchmark_score(db_path, _score_row(metric_value=0.95))
    assert second_id != 0
    # SQLite's INSERT OR REPLACE deletes + inserts, so id rolls forward.
    # Either way the read-back must reflect the LATEST value.
    rows = await read_run_scores(db_path, "run-1")
    assert len(rows) == 1, f"upsert must collapse to one row; got {len(rows)}"
    assert rows[0].metric_value == 0.95
    # And the new id must be the second insert (REPLACE deletes then inserts).
    assert first_id != second_id


async def test_read_run_scores_returns_pydantic_shapes(tmp_path: Path) -> None:
    """AC-3.3: read_run_scores returns BenchmarkScoreRow instances."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    await record_benchmark_score(
        db_path,
        _score_row(
            metric_name="accuracy",
            metric_value=0.9,
            extra_json=encode_extra_json({"confusion_matrix": {"a": {"a": 9, "b": 1}}}),
        ),
    )
    await record_benchmark_score(
        db_path,
        _score_row(metric_name="precision_macro", metric_value=0.88, extra_json=None),
    )

    rows = await read_run_scores(db_path, "run-1")
    assert len(rows) == 2
    by_metric = {r.metric_name: r for r in rows}
    assert by_metric["accuracy"].metric_value == 0.9
    assert by_metric["accuracy"].extra_json is not None
    assert "confusion_matrix" in by_metric["accuracy"].extra_json
    assert by_metric["precision_macro"].extra_json is None


async def test_read_run_runs_returns_pydantic_shapes(tmp_path: Path) -> None:
    """AC-3.2: read_run_runs returns BenchmarkRunRow instances; mirror schema closed-set."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    await record_benchmark_run(db_path, _run_row())
    await record_benchmark_run(db_path, _run_row(corpus_item_id="corpus-v1-002"))

    rows = await read_run_runs(db_path, "run-1")
    assert len(rows) == 2
    assert all(isinstance(r, BenchmarkRunRow) for r in rows)
    assert {r.corpus_item_id for r in rows} == {"corpus-v1-001", "corpus-v1-002"}


async def test_read_run_scores_empty_for_unknown_run(tmp_path: Path) -> None:
    """Empty list on unknown run_id — no rows raised, no exceptions."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    rows = await read_run_scores(db_path, "no-such-run")
    assert rows == []


def test_encode_extra_json_sorts_keys() -> None:
    """encode_extra_json sorts keys for stable diffs across re-runs."""
    a = encode_extra_json({"b": 1, "a": 2})
    b = encode_extra_json({"a": 2, "b": 1})
    assert a == b
    assert a.index('"a"') < a.index('"b"')


def test_encode_extra_json_preserves_unicode() -> None:
    """encode_extra_json uses ensure_ascii=False so labels stay readable."""
    out = encode_extra_json({"per_class": {"naïve": {"f1": 0.7}}})
    assert "naïve" in out
