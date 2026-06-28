"""Story 9-7 AC-9: integration tests for ``benchmark.scorer`` CLI.

Five scenarios using fake-adapter fixtures (no real API spend):
  1. Happy path objective — seeded benchmark_runs rows for classification get
     scored end-to-end through the CLI's main(); benchmark_scores rows land.
  2. Happy path subjective — anchor calibration + per-row scoring produce
     benchmark_scores rows with calibration_mae and subjective_overall.
  3. Calibration warning fires when MAE > 0.5.
  4. Cross-evaluator α path with --secondary-evaluator writes the α row.
  5. Unique-constraint enforcement — second scorer run for same (run, task,
     model, metric) overwrites via INSERT OR REPLACE.

All adapter dispatches use FakeAdapter + ScriptedSubjectiveAdapter
registered via register_adapter, preserving Rule I coverage end-to-end
through the Router precondition layer + lane semaphore + audit write.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchmark.db import record_benchmark_run
from benchmark.schemas import BenchmarkRunRow
from benchmark.scorer import main as scorer_main
from benchmark.scorer_db import read_run_scores
from evals.corpus_schema import (
    AnchorItem,
    CorpusItem,
    CorpusLabels,
    write_corpus,
)
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter


@pytest.fixture(autouse=True)
def _clean_state(tmp_path: Path) -> Iterator[None]:
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_semaphore_registry_for_test()
    _reset_loop_detector_for_test()
    _reset_rate_limiter_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()
    set_policy_snapshot(load_policy(Path("router/policy.yaml")))
    yield
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_semaphore_registry_for_test()
    _reset_loop_detector_for_test()
    _reset_rate_limiter_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()


class _ScriptedSubjectiveAdapter:
    def __init__(
        self,
        overall_score: int,
        per_axis_scores: dict[str, int],
        model_id: str = "scripted-evaluator",
    ) -> None:
        self.overall_score = overall_score
        self.per_axis_scores = per_axis_scores
        self.model_id = model_id
        self.call_log: list[dict[str, Any]] = []

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        self.call_log.append({"system": system, "user": user, "max_tokens_out": max_tokens_out})
        body = json.dumps(
            {"overall_score": self.overall_score, "per_axis_scores": self.per_axis_scores}
        )
        return AdapterResponse(
            text=body,
            tokens_in=100,
            tokens_out=20,
            cached_tokens_in=0,
            latency_ms=5,
            raw={},
        )


def _corpus_item(corpus_id: str, class_coarse: str = "transactional") -> CorpusItem:
    return CorpusItem.model_validate(
        {
            "id": corpus_id,
            "category": "transactional",
            "raw_subject": f"Subject {corpus_id}",
            "raw_body": f"Body {corpus_id}",
            "labels": CorpusLabels.model_validate(
                {
                    "sensitivity": "normal",
                    "class_coarse": class_coarse,
                    "reference_resolution_slice": False,
                }
            ).model_dump(),
            "source_note": "test-fixture",
        }
    )


def _bench_run_row(
    corpus_id: str,
    task_type: str,
    model: str,
    output_payload: dict[str, Any],
    outcome: str = "ok",
) -> BenchmarkRunRow:
    return BenchmarkRunRow.model_validate(
        {
            "run_id": "run-9-7-test",
            "corpus_item_id": corpus_id,
            "task_type": task_type,
            "model": model,
            "prompt_version": "v1",
            "cohort_key": "test-cohort-abc",
            "output_json": json.dumps(output_payload),
            "tokens_in": 100,
            "tokens_out": 50,
            "cached_tokens_in": 0,
            "cost_usd": 0.0,
            "latency_ms": 100,
            "outcome": outcome,
            "status": "completed",
            "scorer_model": "claude-opus-4-7-20251220",
            "anchors_version": "v1",
            "router_policy_version": "test",
            "ran_at": "2026-06-28T00:00:00Z",
        }
    )


def _anchor(idx: int, adam_overall: int, task: str = "draft_reply") -> AnchorItem:
    axes = (
        {"faithfulness": adam_overall, "tone_match": adam_overall, "actionability": adam_overall}
        if task == "draft_reply"
        else {"faithfulness": adam_overall, "concision": adam_overall, "actionability": adam_overall}
    )
    return AnchorItem.model_validate(
        {
            "id": f"anchor-{task}-{idx:03d}",
            "task": task,
            "corpus_item_id": None,
            "input_email_subject": f"Subject {idx}",
            "input_email_body": f"Body {idx}",
            "model_output": json.dumps({"reply": f"Reply {idx}"}),
            "adam_score_axes": axes,
            "adam_overall_score": adam_overall,
            "score_rationale": f"Rationale {idx}",
        }
    )


def _write_anchors(anchors_dir: Path, task: str, anchors: list[AnchorItem]) -> None:
    anchors_dir.mkdir(parents=True, exist_ok=True)
    fpath = anchors_dir / f"{task}_anchors.jsonl"
    with fpath.open("w", encoding="utf-8") as fh:
        for a in anchors:
            fh.write(a.model_dump_json() + "\n")


async def _seed_classification_run(
    db_path: str, corpus_path: Path, *, n_items: int = 5
) -> None:
    items = [_corpus_item(f"c{i}") for i in range(1, n_items + 1)]
    write_corpus(corpus_path, items)
    # All 5 rows correct → accuracy 1.0
    for it in items:
        await record_benchmark_run(
            db_path,
            _bench_run_row(
                it.id,
                "coarse_class",
                "qwen2.5:3b-instruct-q4_K_M",
                {"class_coarse": "transactional"},
            ),
        )


async def _seed_subjective_run(
    db_path: str, corpus_path: Path, *, n_items: int = 3
) -> None:
    items = [_corpus_item(f"c{i}") for i in range(1, n_items + 1)]
    write_corpus(corpus_path, items)
    for it in items:
        await record_benchmark_run(
            db_path,
            _bench_run_row(
                it.id,
                "draft_reply",
                "claude-opus-4-7",
                {"reply": f"Drafted reply for {it.id}"},
            ),
        )


def test_scenario_1_happy_path_objective(tmp_path: Path) -> None:
    """AC-9.1: classification rows scored end-to-end via the CLI's main()."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    corpus_path = tmp_path / "corpus.jsonl"
    import asyncio

    asyncio.run(_seed_classification_run(db_path, corpus_path))

    exit_code = scorer_main(
        [
            "--run-id", "run-9-7-test",
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(tmp_path / "anchors"),  # empty: no subjective dispatch needed
        ]
    )
    assert exit_code == 0

    scores = asyncio.run(read_run_scores(db_path, "run-9-7-test"))
    metric_names = {s.metric_name for s in scores}
    assert "accuracy" in metric_names
    assert "precision_macro" in metric_names
    assert "recall_macro" in metric_names
    assert "f1_macro" in metric_names
    assert "ok_rate" in metric_names

    # Accuracy = 1.0 because all 5 predictions matched ground truth.
    accuracy_row = next(s for s in scores if s.metric_name == "accuracy")
    assert accuracy_row.metric_value == 1.0
    assert accuracy_row.scorer_model == "objective:mechanical"
    assert accuracy_row.evaluator_role == "primary"
    assert accuracy_row.outcome == "ok"
    assert accuracy_row.extra_json is not None
    # Confusion matrix carried.
    payload = json.loads(accuracy_row.extra_json)
    assert "confusion_matrix" in payload


def test_scenario_2_happy_path_subjective(tmp_path: Path) -> None:
    """AC-9.2: subjective scorer + anchor calibration → calibration_mae + subjective_overall."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    corpus_path = tmp_path / "corpus.jsonl"
    anchors_dir = tmp_path / "anchors"
    _write_anchors(anchors_dir, "draft_reply", [_anchor(i + 1, adam_overall=3) for i in range(3)])
    import asyncio

    asyncio.run(_seed_subjective_run(db_path, corpus_path, n_items=2))

    # Adapter returns 3 every time → MAE = 0.0 on anchors, mean_overall = 3.0 on per-row.
    adapter = _ScriptedSubjectiveAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7-20251220",
    )
    register_adapter("claude-opus-4-7-20251220", adapter)

    exit_code = scorer_main(
        [
            "--run-id", "run-9-7-test",
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(anchors_dir),
            "--scorer-model", "claude-opus-4-7-20251220",
            "--yes",
        ]
    )
    assert exit_code == 0

    scores = asyncio.run(read_run_scores(db_path, "run-9-7-test"))
    by_name = {s.metric_name: s for s in scores}
    assert "calibration_mae" in by_name
    assert by_name["calibration_mae"].metric_value == 0.0
    assert "subjective_overall" in by_name
    assert by_name["subjective_overall"].metric_value == 3.0
    assert by_name["subjective_overall"].outcome == "ok"
    assert "subjective_faithfulness" in by_name
    assert by_name["subjective_faithfulness"].metric_value == 3.0


def test_scenario_3_calibration_warning_fires(tmp_path: Path) -> None:
    """AC-9.3: MAE > 0.5 → outcome=calibration_warning on per-model rows."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    corpus_path = tmp_path / "corpus.jsonl"
    anchors_dir = tmp_path / "anchors"
    _write_anchors(anchors_dir, "draft_reply", [_anchor(i + 1, adam_overall=2) for i in range(3)])
    import asyncio

    asyncio.run(_seed_subjective_run(db_path, corpus_path, n_items=1))

    # Adapter returns 5 for everything; Adam's anchors are 2 → MAE = 3.0 > 0.5
    adapter = _ScriptedSubjectiveAdapter(
        overall_score=5,
        per_axis_scores={"faithfulness": 5, "tone_match": 5, "actionability": 5},
        model_id="claude-opus-4-7-20251220",
    )
    register_adapter("claude-opus-4-7-20251220", adapter)

    exit_code = scorer_main(
        [
            "--run-id", "run-9-7-test",
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(anchors_dir),
            "--scorer-model", "claude-opus-4-7-20251220",
            "--yes",
        ]
    )
    assert exit_code == 0

    scores = asyncio.run(read_run_scores(db_path, "run-9-7-test"))
    cal_mae = next(s for s in scores if s.metric_name == "calibration_mae")
    assert cal_mae.metric_value > 0.5
    overall = next(s for s in scores if s.metric_name == "subjective_overall")
    assert overall.outcome == "calibration_warning"


def test_scenario_4_cross_evaluator_alpha_path(tmp_path: Path) -> None:
    """AC-9.4: --secondary-evaluator writes cross_evaluator_alpha row."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    corpus_path = tmp_path / "corpus.jsonl"
    anchors_dir = tmp_path / "anchors"
    _write_anchors(anchors_dir, "draft_reply", [_anchor(i + 1, adam_overall=3) for i in range(3)])
    import asyncio

    asyncio.run(_seed_subjective_run(db_path, corpus_path, n_items=1))

    primary = _ScriptedSubjectiveAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7-20251220",
    )
    secondary = _ScriptedSubjectiveAdapter(
        overall_score=4,
        per_axis_scores={"faithfulness": 4, "tone_match": 4, "actionability": 4},
        model_id="claude-sonnet-4-6-20250929",
    )
    register_adapter("claude-opus-4-7-20251220", primary)
    register_adapter("claude-sonnet-4-6-20250929", secondary)

    exit_code = scorer_main(
        [
            "--run-id", "run-9-7-test",
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(anchors_dir),
            "--scorer-model", "claude-opus-4-7-20251220",
            "--secondary-evaluator", "claude-sonnet-4-6-20250929",
            "--yes",
        ]
    )
    assert exit_code == 0

    scores = asyncio.run(read_run_scores(db_path, "run-9-7-test"))
    assert any(s.metric_name == "cross_evaluator_alpha" for s in scores), (
        "AC-9.4: cross_evaluator_alpha row MUST be written when --secondary-evaluator is passed"
    )


def test_scenario_5_unique_constraint_enforcement(tmp_path: Path) -> None:
    """AC-9.5: re-running the scorer for the same (run, task, model, metric) overwrites."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    corpus_path = tmp_path / "corpus.jsonl"
    import asyncio

    asyncio.run(_seed_classification_run(db_path, corpus_path, n_items=3))

    # First scorer run.
    rc1 = scorer_main(
        [
            "--run-id", "run-9-7-test",
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(tmp_path / "anchors"),
        ]
    )
    assert rc1 == 0
    first_scores = asyncio.run(read_run_scores(db_path, "run-9-7-test"))
    first_count = len(first_scores)

    # Second scorer run — same args; INSERT OR REPLACE collapses identical rows.
    rc2 = scorer_main(
        [
            "--run-id", "run-9-7-test",
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(tmp_path / "anchors"),
        ]
    )
    assert rc2 == 0
    second_scores = asyncio.run(read_run_scores(db_path, "run-9-7-test"))
    assert len(second_scores) == first_count, (
        f"AC-9.5: row count MUST stay stable across re-runs; first={first_count}, second={len(second_scores)}"
    )
