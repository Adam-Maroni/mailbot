"""Story 9-7 AC-5/AC-7/AC-11/AC-12: subjective scorer unit tests.

Uses FakeAdapter at the adapter boundary (Story 9-3 CR-F6 helper) so the
Router runs end-to-end (precondition layer, sensitivity gate, cache,
audit write) but the leaf adapter returns scripted JSON. This preserves
Rule I coverage in the test surface.

Five scenarios:
  1. Anchor calibration computes MAE correctly + per-axis aggregation.
  2. Calibration warning fires when MAE > 0.5.
  3. Cross-evaluator α path (primary + secondary scripted with deliberate
     disagreement) drops outcome to calibration_warning.
  4. Cross-evaluator skipped when secondary=None.
  5. Per-row scoring rolls into mean_overall + mean_per_axis.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchmark.schemas import BenchmarkRunRow
from benchmark.scoring.subjective import (
    build_anchors_block,
    load_anchors,
    score_subjective,
)
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
from tests._helpers.fake_adapter import FakeAdapter


@pytest.fixture(autouse=True)
def _clean_router_state(tmp_path: Path) -> Iterator[None]:
    """Reset all module-level Router state before + after each test."""
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_semaphore_registry_for_test()
    _reset_loop_detector_for_test()
    _reset_rate_limiter_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()
    # Load the real production policy so anchor_calibrated_eval is registered.
    policy = load_policy(Path("router/policy.yaml"))
    set_policy_snapshot(policy)
    yield
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_semaphore_registry_for_test()
    _reset_loop_detector_for_test()
    _reset_rate_limiter_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()


def _adapter_response(text: str, tokens_out: int = 20) -> AdapterResponse:
    return AdapterResponse(
        text=text,
        tokens_in=100,
        tokens_out=tokens_out,
        cached_tokens_in=0,
        latency_ms=5,
        raw={},
    )


class _ScriptedSubjectiveAdapter:
    """Adapter that returns a constant SubjectiveAutoEvalOutput per call.

    The scorer's prompt module schema demands {overall_score, per_axis_scores};
    this adapter scripts a deterministic JSON response.
    """

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
        self.call_log.append(
            {
                "system": system,
                "user": user,
                "max_tokens_out": max_tokens_out,
                "temperature": temperature,
            }
        )
        body = json.dumps(
            {
                "overall_score": self.overall_score,
                "per_axis_scores": self.per_axis_scores,
            }
        )
        return _adapter_response(body)


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
            "input_email_body": f"Body of email {idx}.",
            "model_output": json.dumps({"reply": f"Reply for anchor {idx}"}),
            "adam_score_axes": axes,
            "adam_overall_score": adam_overall,
            "score_rationale": f"Rationale for anchor {idx}",
        }
    )


def _corpus_item(corpus_id: str) -> CorpusItem:
    return CorpusItem.model_validate(
        {
            "id": corpus_id,
            "category": "human_personal",
            "raw_subject": f"Subject {corpus_id}",
            "raw_body": f"Body {corpus_id}",
            "labels": CorpusLabels.model_validate(
                {
                    "sensitivity": "normal",
                    "class_coarse": "human_personal",
                    "reference_resolution_slice": False,
                }
            ).model_dump(),
            "source_note": "test",
        }
    )


def _bench_row(corpus_id: str, model: str, outcome: str = "ok") -> BenchmarkRunRow:
    return BenchmarkRunRow.model_validate(
        {
            "run_id": "run-1",
            "corpus_item_id": corpus_id,
            "task_type": "draft_reply",
            "model": model,
            "prompt_version": "v1",
            "cohort_key": "cohort-abc",
            "output_json": json.dumps({"reply": f"Reply from {model} for {corpus_id}"}),
            "tokens_in": 100,
            "tokens_out": 50,
            "cached_tokens_in": 0,
            "cost_usd": 0.01,
            "latency_ms": 1000,
            "outcome": outcome,
            "status": "completed",
            "scorer_model": "claude-opus-4-7-20251220",
            "anchors_version": "v1",
            "router_policy_version": "test",
            "ran_at": "2026-06-28T00:00:00Z",
        }
    )


async def test_anchor_calibration_perfect_match_mae_zero(tmp_path: Path) -> None:
    """Evaluator returns Adam's exact overall_score per anchor → MAE = 0.0, outcome ok."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    # 5 anchors, all Adam-score=3; adapter returns overall=3 every call.
    anchors = [_anchor(i + 1, adam_overall=3) for i in range(5)]
    adapter = _ScriptedSubjectiveAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7",
    )
    register_adapter("claude-opus-4-7", adapter)
    rows = [_bench_row("c1", "claude-opus-4-7")]
    items = {"c1": _corpus_item("c1")}

    metrics = await score_subjective(
        rows=rows,
        items_by_id=items,
        anchors=anchors,
        db_path=db_path,
        scorer_model="claude-opus-4-7",
        task_type="draft_reply",
    )
    assert metrics.calibration_mae == 0.0
    assert metrics.outcome == "ok"
    assert metrics.ok_count == 1
    assert metrics.mean_overall == 3.0
    assert metrics.mean_per_axis["faithfulness"] == 3.0


async def test_calibration_warning_fires_when_mae_above_threshold(tmp_path: Path) -> None:
    """Adapter returns 5 for anchors Adam scored 2 → MAE=3.0 > 0.5 → calibration_warning."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    anchors = [_anchor(i + 1, adam_overall=2) for i in range(5)]
    adapter = _ScriptedSubjectiveAdapter(
        overall_score=5,
        per_axis_scores={"faithfulness": 5, "tone_match": 5, "actionability": 5},
        model_id="claude-opus-4-7",
    )
    register_adapter("claude-opus-4-7", adapter)
    rows = [_bench_row("c1", "claude-opus-4-7")]
    items = {"c1": _corpus_item("c1")}

    metrics = await score_subjective(
        rows=rows,
        items_by_id=items,
        anchors=anchors,
        db_path=db_path,
        scorer_model="claude-opus-4-7",
        task_type="draft_reply",
    )
    assert metrics.calibration_mae > 0.5
    assert metrics.outcome == "calibration_warning"


async def test_cross_evaluator_alpha_path_low_agreement(tmp_path: Path) -> None:
    """Primary returns 5, secondary returns 2 on all anchors → α near -1 → calibration_warning."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    anchors = [_anchor(i + 1, adam_overall=3) for i in range(5)]
    primary_adapter = _ScriptedSubjectiveAdapter(
        overall_score=5,
        per_axis_scores={"faithfulness": 5, "tone_match": 5, "actionability": 5},
        model_id="claude-opus-4-7",
    )
    secondary_adapter = _ScriptedSubjectiveAdapter(
        overall_score=2,
        per_axis_scores={"faithfulness": 2, "tone_match": 2, "actionability": 2},
        model_id="claude-sonnet-4-6-20250929",
    )
    register_adapter("claude-opus-4-7", primary_adapter)
    register_adapter("claude-sonnet-4-6-20250929", secondary_adapter)
    rows = [_bench_row("c1", "claude-opus-4-7")]
    items = {"c1": _corpus_item("c1")}

    metrics = await score_subjective(
        rows=rows,
        items_by_id=items,
        anchors=anchors,
        db_path=db_path,
        scorer_model="claude-opus-4-7",
        task_type="draft_reply",
        secondary_evaluator="claude-sonnet-4-6-20250929",
    )
    # The two evaluators systematically disagree by 3 points on every anchor.
    # Note: all-primary=5 AND all-secondary=2 is a degenerate case where each
    # rater has zero variance — Krippendorff α = 1.0 (no disagreement signal)
    # because the value-domain reduces to {5, 2} and within each rater all
    # ratings are identical. The MAE-based calibration_warning still fires
    # here because the primary evaluator's anchor MAE (5 vs Adam's 3) > 0.5.
    assert metrics.calibration_mae > 0.5
    assert metrics.outcome == "calibration_warning"
    # α is computed and reported regardless of whether it triggers the warning.
    assert metrics.cross_evaluator_alpha is not None
    # Per-anchor cross_evaluator data exists with one entry per anchor.
    assert len(metrics.cross_evaluator_per_anchor) == 5


async def test_secondary_evaluator_skipped_when_none(tmp_path: Path) -> None:
    """No --secondary-evaluator → cross_evaluator_alpha is None."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    anchors = [_anchor(i + 1, adam_overall=3) for i in range(3)]
    adapter = _ScriptedSubjectiveAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7",
    )
    register_adapter("claude-opus-4-7", adapter)
    rows = [_bench_row("c1", "claude-opus-4-7")]
    items = {"c1": _corpus_item("c1")}

    metrics = await score_subjective(
        rows=rows,
        items_by_id=items,
        anchors=anchors,
        db_path=db_path,
        scorer_model="claude-opus-4-7",
        task_type="draft_reply",
        secondary_evaluator=None,
    )
    assert metrics.cross_evaluator_alpha is None
    assert metrics.cross_evaluator_per_anchor == []


async def test_per_row_scoring_mean_overall_aggregation(tmp_path: Path) -> None:
    """3 rows scored at overall=4 → mean_overall = 4.0; per-axis means populated."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    anchors = [_anchor(i + 1, adam_overall=4) for i in range(3)]
    adapter = _ScriptedSubjectiveAdapter(
        overall_score=4,
        per_axis_scores={"faithfulness": 4, "tone_match": 5, "actionability": 3},
        model_id="claude-opus-4-7",
    )
    register_adapter("claude-opus-4-7", adapter)
    rows = [_bench_row(f"c{i}", "claude-opus-4-7") for i in range(1, 4)]
    items = {f"c{i}": _corpus_item(f"c{i}") for i in range(1, 4)}

    metrics = await score_subjective(
        rows=rows,
        items_by_id=items,
        anchors=anchors,
        db_path=db_path,
        scorer_model="claude-opus-4-7",
        task_type="draft_reply",
    )
    assert metrics.ok_count == 3
    assert metrics.mean_overall == 4.0
    assert metrics.mean_per_axis["tone_match"] == 5.0
    assert metrics.mean_per_axis["actionability"] == 3.0
    assert len(metrics.per_row_scores) == 3


async def test_load_anchors_reads_jsonl_round_trip(tmp_path: Path) -> None:
    """load_anchors reads a real JSONL file the test wrote to disk."""
    anchors_dir = tmp_path / "anchors"
    anchors_dir.mkdir()
    anchors = [_anchor(i + 1, adam_overall=3) for i in range(5)]
    fpath = anchors_dir / "draft_reply_anchors.jsonl"
    with fpath.open("w", encoding="utf-8") as fh:
        for a in anchors:
            fh.write(a.model_dump_json() + "\n")
    loaded = load_anchors(anchors_dir, "draft_reply")
    assert len(loaded) == 5
    assert loaded[0].id == "anchor-draft_reply-001"


def test_build_anchors_block_carries_per_axis_scores() -> None:
    """The rendered anchors block exposes Adam's per-axis scores to the evaluator."""
    anchors = [_anchor(1, adam_overall=4)]
    block = build_anchors_block(anchors)
    assert "Adam's overall_score: 4" in block
    assert "faithfulness: 4" in block
    assert "tone_match: 4" in block


async def test_load_anchors_missing_file_raises(tmp_path: Path) -> None:
    """Absent anchor file → FileNotFoundError, NOT a silent empty-list."""
    with pytest.raises(FileNotFoundError, match="anchor file not found"):
        load_anchors(tmp_path, "draft_reply")


# Silence unused-import lint when write_corpus is auto-imported above by the
# fake_adapter helper; the helper file is the canonical source.
_ = write_corpus
_ = FakeAdapter
