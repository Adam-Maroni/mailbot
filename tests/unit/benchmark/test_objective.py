"""Story 9-7 AC-3: ``score_classification`` unit tests.

Hand-computed accuracy + macro F1 + confusion matrix on a 5-row fixture.
"""

from __future__ import annotations

from benchmark.schemas import BenchmarkRunRow
from benchmark.scoring.objective import score_classification
from evals.corpus_schema import CorpusItem, CorpusLabels


def _row(
    corpus_item_id: str, predicted_label: str, outcome: str = "ok"
) -> BenchmarkRunRow:
    output_json = (
        '{"class_coarse":"' + predicted_label + '"}' if predicted_label else None
    )
    return BenchmarkRunRow.model_validate(
        {
            "run_id": "run-1",
            "corpus_item_id": corpus_item_id,
            "task_type": "coarse_class",
            "model": "qwen2.5:3b-instruct-q4_K_M",
            "prompt_version": "v1",
            "cohort_key": "cohort-abc",
            "output_json": output_json,
            "tokens_in": 10,
            "tokens_out": 5,
            "cached_tokens_in": 0,
            "cost_usd": 0.0,
            "latency_ms": 12,
            "outcome": outcome,
            "status": "completed",
            "scorer_model": "claude-opus-4-7-20251220",
            "anchors_version": "v1",
            "router_policy_version": "test-policy-v1",
            "ran_at": "2026-06-28T00:00:00Z",
        }
    )


def _item(corpus_id: str, class_coarse: str) -> CorpusItem:
    return CorpusItem.model_validate(
        {
            "id": corpus_id,
            "category": "transactional",
            "raw_subject": "subj",
            "raw_body": "body",
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


def test_score_classification_hand_computed_accuracy() -> None:
    """5 rows, 4 correct → accuracy 0.8; per-class confusion matrix populated."""
    items_by_id = {
        "c1": _item("c1", "transactional"),
        "c2": _item("c2", "transactional"),
        "c3": _item("c3", "newsletter"),
        "c4": _item("c4", "newsletter"),
        "c5": _item("c5", "human_personal"),
    }
    rows = [
        _row("c1", "transactional"),
        _row("c2", "transactional"),
        _row("c3", "newsletter"),
        _row("c4", "newsletter"),
        _row("c5", "newsletter"),  # wrong: should be human_personal
    ]
    metrics = score_classification(
        rows, items_by_id, task_type="coarse_class",
        output_field_name="class_coarse", ground_truth_attr="class_coarse",
    )
    assert metrics.accuracy == 0.8
    assert metrics.ok_count == 5
    assert metrics.total_count == 5
    # Confusion: 2x transactional-transactional, 2x newsletter-newsletter,
    # 1x human_personal-newsletter.
    assert metrics.confusion_matrix["transactional"]["transactional"] == 2
    assert metrics.confusion_matrix["newsletter"]["newsletter"] == 2
    assert metrics.confusion_matrix["human_personal"]["newsletter"] == 1
    # Per-class checks: human_personal has 0 TP, 0 FP (no one predicted it),
    # 1 FN (the c5 mis-classification).
    hp = metrics.per_class["human_personal"]
    assert hp["precision"] == 0.0
    assert hp["recall"] == 0.0
    assert hp["support"] == 1.0


def test_score_classification_skips_failed_rows() -> None:
    """outcome != 'ok' rows don't reduce accuracy but DO count in total_count."""
    items_by_id = {"c1": _item("c1", "transactional"), "c2": _item("c2", "newsletter")}
    rows = [
        _row("c1", "transactional"),
        _row("c2", "", outcome="schema_failed"),  # not scored
    ]
    metrics = score_classification(
        rows, items_by_id, task_type="coarse_class",
        output_field_name="class_coarse", ground_truth_attr="class_coarse",
    )
    assert metrics.accuracy == 1.0
    assert metrics.ok_count == 1
    assert metrics.total_count == 2


def test_score_classification_insufficient_data_returns_zeros() -> None:
    """All rows failed → all-zero metrics, total_count > 0."""
    items_by_id = {"c1": _item("c1", "transactional")}
    rows = [_row("c1", "", outcome="provider_error"), _row("c1", "", outcome="timeout")]
    metrics = score_classification(
        rows, items_by_id, task_type="coarse_class",
        output_field_name="class_coarse", ground_truth_attr="class_coarse",
    )
    assert metrics.accuracy == 0.0
    assert metrics.ok_count == 0
    assert metrics.total_count == 2
    assert metrics.per_class == {}


def test_score_classification_macro_precision_recall_f1() -> None:
    """Hand-computed macro F1 on a balanced 4-row fixture."""
    items_by_id = {
        "c1": _item("c1", "transactional"),
        "c2": _item("c2", "newsletter"),
        "c3": _item("c3", "transactional"),
        "c4": _item("c4", "newsletter"),
    }
    rows = [
        _row("c1", "transactional"),
        _row("c2", "transactional"),  # wrong
        _row("c3", "transactional"),
        _row("c4", "newsletter"),
    ]
    metrics = score_classification(
        rows, items_by_id, task_type="coarse_class",
        output_field_name="class_coarse", ground_truth_attr="class_coarse",
    )
    # transactional: TP=2, FP=1, FN=0 → P=2/3, R=1.0, F1=0.8
    # newsletter:    TP=1, FP=0, FN=1 → P=1.0, R=0.5, F1=0.667
    # macro F1 ≈ (0.8 + 0.667) / 2 ≈ 0.733
    assert abs(metrics.f1_macro - 0.7333) < 0.01
    assert abs(metrics.precision_macro - (2 / 3 + 1.0) / 2) < 0.01
    assert abs(metrics.recall_macro - (1.0 + 0.5) / 2) < 0.01
