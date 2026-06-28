"""Story 9-7 AC-4: ``score_extraction`` unit tests.

Hand-constructed action lists exercise TP/FP/FN paths for type / summary /
deadline matching.
"""

from __future__ import annotations

import json

import pytest

from benchmark.schemas import BenchmarkRunRow
from benchmark.scoring.objective import (
    hash_bucket_cosine_similarity,
    score_extraction,
)
from evals.corpus_schema import CorpusItem, CorpusLabels, ExpectedAction


def _extraction_row(corpus_item_id: str, actions: list[dict]) -> BenchmarkRunRow:
    return BenchmarkRunRow.model_validate(
        {
            "run_id": "run-1",
            "corpus_item_id": corpus_item_id,
            "task_type": "action_extraction",
            "model": "claude-haiku-4-5-20251001",
            "prompt_version": "v1",
            "cohort_key": "cohort-abc",
            "output_json": json.dumps({"actions": actions}),
            "tokens_in": 50,
            "tokens_out": 80,
            "cached_tokens_in": 0,
            "cost_usd": 0.001,
            "latency_ms": 200,
            "outcome": "ok",
            "status": "completed",
            "scorer_model": "claude-opus-4-7-20251220",
            "anchors_version": "v1",
            "router_policy_version": "test-policy-v1",
            "ran_at": "2026-06-28T00:00:00Z",
        }
    )


def _item_with_actions(
    corpus_id: str, actions: list[ExpectedAction] | None
) -> CorpusItem:
    return CorpusItem.model_validate(
        {
            "id": corpus_id,
            "category": "transactional",
            "raw_subject": "subj",
            "raw_body": "body",
            "labels": CorpusLabels.model_validate(
                {
                    "sensitivity": "normal",
                    "class_coarse": "transactional",
                    "actions": (
                        [a.model_dump() for a in actions] if actions is not None else None
                    ),
                    "reference_resolution_slice": False,
                }
            ).model_dump(),
            "source_note": "test",
        }
    )


def test_score_extraction_perfect_match_yields_f1_one() -> None:
    """Predicted = expected: all three F1s = 1.0."""
    items = {
        "c1": _item_with_actions(
            "c1",
            [
                ExpectedAction(
                    action_type="reply_needed",
                    summary="confirm hotel booking dates",
                    deadline="2026-07-01T09:00:00Z",
                )
            ],
        )
    }
    rows = [
        _extraction_row(
            "c1",
            [
                {
                    "action_type": "reply_needed",
                    "summary": "confirm hotel booking dates",
                    "deadline": "2026-07-01T09:00:00Z",
                }
            ],
        )
    ]
    metrics = score_extraction(rows, items)
    assert metrics.f1_action_type == 1.0
    assert metrics.f1_summary_similarity == 1.0
    assert metrics.f1_deadline_match == 1.0
    assert metrics.ok_count == 1


def test_score_extraction_summary_mismatch_lowers_summary_f1() -> None:
    """Right type, totally-disjoint summary: type F1 = 1.0, sim F1 < 1.0."""
    items = {
        "c1": _item_with_actions(
            "c1",
            [
                ExpectedAction(
                    action_type="reply_needed",
                    summary="confirm hotel booking dates",
                )
            ],
        )
    }
    rows = [
        _extraction_row(
            "c1",
            [
                {
                    "action_type": "reply_needed",
                    "summary": "completely unrelated text about engines and gears",
                    "deadline": None,
                }
            ],
        )
    ]
    metrics = score_extraction(rows, items)
    # Type matched coarsely → type F1 = 1.0
    assert metrics.f1_action_type == 1.0
    # Summary similarity below threshold → no TP for sim → sim F1 = 0
    assert metrics.f1_summary_similarity == 0.0


def test_score_extraction_missing_expected_is_fn() -> None:
    """Expected 2 actions, predicted 1 → FN reduces F1."""
    items = {
        "c1": _item_with_actions(
            "c1",
            [
                ExpectedAction(action_type="reply_needed", summary="action one matters"),
                ExpectedAction(action_type="payment", summary="action two matters"),
            ],
        )
    }
    rows = [
        _extraction_row(
            "c1",
            [
                {
                    "action_type": "reply_needed",
                    "summary": "action one matters",
                    "deadline": None,
                }
            ],
        )
    ]
    metrics = score_extraction(rows, items)
    # Type: 1 TP, 0 FP, 1 FN → P=1, R=0.5, F1=0.667
    assert abs(metrics.f1_action_type - 2 / 3) < 0.01
    assert "payment" in metrics.per_action_type
    assert metrics.per_action_type["payment"]["recall"] == 0.0


def test_score_extraction_extra_predicted_is_fp() -> None:
    """Predicted 2 actions, expected 1 → FP reduces F1."""
    items = {
        "c1": _item_with_actions(
            "c1", [ExpectedAction(action_type="reply_needed", summary="real action")]
        )
    }
    rows = [
        _extraction_row(
            "c1",
            [
                {"action_type": "reply_needed", "summary": "real action", "deadline": None},
                {"action_type": "payment", "summary": "made up action", "deadline": None},
            ],
        )
    ]
    metrics = score_extraction(rows, items)
    # Type: 1 TP, 1 FP, 0 FN → P=0.5, R=1.0, F1=0.667
    assert abs(metrics.f1_action_type - 2 / 3) < 0.01


def test_score_extraction_skips_items_without_actions_label() -> None:
    """Items where labels.actions is None contribute nothing."""
    items = {"c1": _item_with_actions("c1", None)}
    rows = [_extraction_row("c1", [{"action_type": "reply_needed", "summary": "x"}])]
    metrics = score_extraction(rows, items)
    assert metrics.ok_count == 0
    assert metrics.total_count == 1


def test_hash_bucket_cosine_similarity_self_is_one() -> None:
    """Identical strings → cosine ≈ 1.0."""
    sim = hash_bucket_cosine_similarity("confirm hotel booking", "confirm hotel booking")
    assert sim == pytest.approx(1.0)


def test_hash_bucket_cosine_similarity_disjoint_is_low() -> None:
    """Disjoint vocabulary → cosine ≈ 0.0."""
    sim = hash_bucket_cosine_similarity(
        "alpha beta gamma", "completely orthogonal vocabulary zebra"
    )
    assert sim < 0.2


def test_hash_bucket_cosine_similarity_empty_is_zero() -> None:
    """Either side empty → cosine 0.0 (no division-by-zero)."""
    assert hash_bucket_cosine_similarity("", "anything") == 0.0
    assert hash_bucket_cosine_similarity("anything", "") == 0.0
    assert hash_bucket_cosine_similarity("", "") == 0.0
