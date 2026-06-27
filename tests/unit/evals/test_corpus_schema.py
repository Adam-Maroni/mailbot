"""Story 9-5 AC-1/3/13: focused schema tests for ``evals.corpus_schema``."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.corpus_schema import (
    AnchorItem,
    CorpusItem,
    CorpusLabels,
    ExpectedAction,
    read_anchors_version,
    write_corpus,
)


def _base_labels(**overrides: object) -> CorpusLabels:
    defaults: dict[str, object] = {
        "sensitivity": "normal",
        "class_coarse": "transactional",
    }
    defaults.update(overrides)
    return CorpusLabels(**defaults)  # type: ignore[arg-type]


def _base_item(labels: CorpusLabels | None = None, **overrides: object) -> CorpusItem:
    defaults: dict[str, object] = {
        "id": "corpus-v1-001",
        "category": "transactional",
        "raw_subject": "subj",
        "raw_body": "body",
        "labels": labels or _base_labels(),
        "source_note": "note",
    }
    defaults.update(overrides)
    return CorpusItem(**defaults)  # type: ignore[arg-type]


class TestCorpusLabelsReferenceResolutionInvariant:
    """AC-1 cross-field validator (reference_resolution_slice true/false branches)."""

    def test_slice_false_with_both_none_ok(self) -> None:
        labels = _base_labels()
        assert labels.reference_resolution_slice is False
        assert labels.reference_resolution_turns is None
        assert labels.expected_resolved_email_ids is None

    def test_slice_true_with_both_populated_ok(self) -> None:
        labels = _base_labels(
            reference_resolution_slice=True,
            reference_resolution_turns=[
                {"role": "user", "content": "hi"},
                {"role": "agent", "content": "yes"},
                {"role": "user", "content": "the one from Bob"},
            ],
            expected_resolved_email_ids=["corpus-v1-002"],
        )
        assert labels.reference_resolution_slice is True

    def test_slice_true_with_no_turns_rejects(self) -> None:
        with pytest.raises(ValidationError, match="reference_resolution_turns"):
            _base_labels(
                reference_resolution_slice=True,
                expected_resolved_email_ids=["corpus-v1-002"],
            )

    def test_slice_true_with_no_expected_ids_rejects(self) -> None:
        with pytest.raises(ValidationError, match="expected_resolved_email_ids"):
            _base_labels(
                reference_resolution_slice=True,
                reference_resolution_turns=[
                    {"role": "user", "content": "hi"},
                    {"role": "agent", "content": "yes"},
                    {"role": "user", "content": "ref"},
                ],
            )

    def test_slice_false_with_turns_present_rejects(self) -> None:
        with pytest.raises(ValidationError, match="reference_resolution_turns"):
            _base_labels(
                reference_resolution_slice=False,
                reference_resolution_turns=[
                    {"role": "user", "content": "hi"},
                    {"role": "agent", "content": "yes"},
                    {"role": "user", "content": "ref"},
                ],
            )

    def test_slice_false_with_expected_ids_present_rejects(self) -> None:
        with pytest.raises(ValidationError, match="expected_resolved_email_ids"):
            _base_labels(
                reference_resolution_slice=False,
                expected_resolved_email_ids=["corpus-v1-002"],
            )

    def test_importance_score_in_range(self) -> None:
        _base_labels(importance_score=3)
        with pytest.raises(ValidationError, match="importance_score"):
            _base_labels(importance_score=0)
        with pytest.raises(ValidationError, match="importance_score"):
            _base_labels(importance_score=6)


class TestCorpusLabelsExtraForbid:
    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CorpusLabels(  # type: ignore[call-arg]
                sensitivity="normal",
                class_coarse="newsletter",
                unknown_field="oops",
            )


class TestCorpusItemNonEmptyStrings:
    def test_empty_raw_subject_rejected(self) -> None:
        with pytest.raises(ValidationError, match="raw_subject"):
            _base_item(raw_subject="")

    def test_empty_raw_body_rejected(self) -> None:
        with pytest.raises(ValidationError, match="raw_body"):
            _base_item(raw_body="")

    def test_empty_source_note_rejected(self) -> None:
        with pytest.raises(ValidationError, match="source_note"):
            _base_item(source_note="")


class TestAnchorItemAxesAndScores:
    """AC-3 cross-field validator (axes-keys match task; scores in 1-5)."""

    def test_draft_reply_axes_ok(self) -> None:
        AnchorItem(
            id="anchor-draft_reply-001",
            task="draft_reply",
            corpus_item_id=None,
            input_email_subject="s",
            input_email_body="b",
            model_output="m",
            adam_score_axes={
                "faithfulness": 3,
                "tone_match": 4,
                "actionability": 2,
            },
            adam_overall_score=3,
            score_rationale="r",
        )

    def test_summary_short_axes_ok(self) -> None:
        AnchorItem(
            id="anchor-summary_short-001",
            task="summary_short",
            corpus_item_id="corpus-v1-001",
            input_email_subject="s",
            input_email_body="b",
            model_output="m",
            adam_score_axes={
                "faithfulness": 5,
                "concision": 4,
                "actionability": 3,
            },
            adam_overall_score=4,
            score_rationale="r",
        )

    def test_draft_reply_with_summary_axes_rejected(self) -> None:
        with pytest.raises(ValidationError, match="adam_score_axes"):
            AnchorItem(
                id="anchor-draft_reply-001",
                task="draft_reply",
                input_email_subject="s",
                input_email_body="b",
                model_output="m",
                adam_score_axes={
                    "faithfulness": 3,
                    "concision": 4,  # wrong axis for draft_reply
                    "actionability": 2,
                },
                adam_overall_score=3,
                score_rationale="r",
            )

    def test_summary_short_with_draft_axes_rejected(self) -> None:
        with pytest.raises(ValidationError, match="adam_score_axes"):
            AnchorItem(
                id="anchor-summary_short-001",
                task="summary_short",
                input_email_subject="s",
                input_email_body="b",
                model_output="m",
                adam_score_axes={
                    "faithfulness": 3,
                    "tone_match": 4,  # wrong axis for summary_short
                    "actionability": 2,
                },
                adam_overall_score=3,
                score_rationale="r",
            )

    def test_axis_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="adam_score_axes"):
            AnchorItem(
                id="anchor-draft_reply-001",
                task="draft_reply",
                input_email_subject="s",
                input_email_body="b",
                model_output="m",
                adam_score_axes={
                    "faithfulness": 6,
                    "tone_match": 4,
                    "actionability": 2,
                },
                adam_overall_score=3,
                score_rationale="r",
            )

    def test_overall_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="adam_overall_score"):
            AnchorItem(
                id="anchor-draft_reply-001",
                task="draft_reply",
                input_email_subject="s",
                input_email_body="b",
                model_output="m",
                adam_score_axes={
                    "faithfulness": 3,
                    "tone_match": 4,
                    "actionability": 2,
                },
                adam_overall_score=0,
                score_rationale="r",
            )


class TestAdversarialDefault:
    """AC-5: adversarial defaults to False."""

    def test_default(self) -> None:
        assert _base_labels().adversarial is False

    def test_set_true(self) -> None:
        assert _base_labels(adversarial=True).adversarial is True


class TestReadAnchorsVersion:
    """AC-13: read_anchors_version happy path + missing-file path."""

    def test_happy_path(self, tmp_path: Path) -> None:
        anchors_dir = tmp_path / "anchors"
        anchors_dir.mkdir()
        (anchors_dir / "VERSION").write_text("v3", encoding="utf-8")
        assert read_anchors_version(anchors_dir) == "v3"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        anchors_dir = tmp_path / "anchors"
        anchors_dir.mkdir()
        (anchors_dir / "VERSION").write_text("  v7  \n", encoding="utf-8")
        assert read_anchors_version(anchors_dir) == "v7"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        anchors_dir = tmp_path / "no-anchors-here"
        anchors_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="VERSION"):
            read_anchors_version(anchors_dir)


class TestWriteCorpusAtomic:
    """AC-1: write_corpus uses tempfile + os.replace; atomic."""

    def test_round_trip(self, tmp_path: Path) -> None:
        out = tmp_path / "corpus.jsonl"
        item = _base_item()
        write_corpus(out, [item])
        from evals.corpus_schema import load_corpus

        loaded = load_corpus(out)
        assert len(loaded) == 1
        assert loaded[0].id == item.id

    def test_parent_missing_raises(self, tmp_path: Path) -> None:
        out = tmp_path / "missing-parent" / "corpus.jsonl"
        with pytest.raises(FileNotFoundError):
            write_corpus(out, [])


class TestExpectedActionExtraForbid:
    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExpectedAction(  # type: ignore[call-arg]
                action_type="reply",
                summary="hi",
                unknown_field="oops",
            )
