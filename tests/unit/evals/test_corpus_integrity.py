"""Story 9-5 AC-10: corpus-integrity tests run at PR time.

These tests run against committed files (the canary fixture + the .example
template + the anchor .example templates + VERSION). The gitignored
``evals/email_corpus_v1.jsonl`` + ``evals/anchors/*.jsonl`` are absent in
CI; tests that touch them are skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.anonymizer import _REGEXES
from evals.corpus_schema import AnchorItem, CorpusItem, load_corpus

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CANARY = _PROJECT_ROOT / "evals" / "fixtures" / "canary_5.jsonl"
_CORPUS_EXAMPLE = _PROJECT_ROOT / "evals" / "email_corpus_v1.jsonl.example"
_ANCHORS_DIR = _PROJECT_ROOT / "evals" / "anchors"


def test_canary_fixture_loads() -> None:
    items = load_corpus(_CANARY)
    assert len(items) == 5, f"expected 5 canary items, got {len(items)}"
    for item in items:
        assert isinstance(item, CorpusItem)


def test_example_file_conforms_to_schema() -> None:
    items = load_corpus(_CORPUS_EXAMPLE)
    assert len(items) >= 2
    for item in items:
        assert isinstance(item, CorpusItem)


def test_no_pii_in_committed_corpus() -> None:
    """AC-6: anonymization regexes must produce zero matches on canary + .example."""
    paths = [_CANARY, _CORPUS_EXAMPLE]
    for path in paths:
        items = load_corpus(path)
        for item in items:
            for kind, pattern in _REGEXES.items():
                for field_name, field_val in (
                    ("raw_subject", item.raw_subject),
                    ("raw_body", item.raw_body),
                    ("source_note", item.source_note),
                ):
                    assert not pattern.search(field_val), (
                        f"{path.name} item={item.id} field={field_name} "
                        f"pattern={kind!r} matched — committed corpus must be PII-free"
                    )


def test_canary_fixture_canary_category_coverage() -> None:
    items = load_corpus(_CANARY)
    categories = {item.category for item in items}
    expected = {
        "transactional",
        "newsletter",
        "human_personal",
        "cold_outreach",
        "notification",
    }
    assert categories == expected, (
        f"canary categories {categories} != expected {expected}"
    )


def test_canary_fixture_label_completeness() -> None:
    """AC-7: every canary item has class_coarse / summary_short_anchor /
    importance_score / 1-3 actions (where relevant) + normal sensitivity."""
    items = load_corpus(_CANARY)
    for item in items:
        assert item.labels.sensitivity == "normal", item.id
        assert item.labels.reference_resolution_slice is False, item.id
        assert item.labels.adversarial is False, item.id
        assert item.labels.class_coarse, item.id
        assert item.labels.summary_short_anchor, item.id
        assert item.labels.importance_score is not None, item.id


def test_anchor_version_file_present() -> None:
    """AC-13: VERSION is gitted (not gitignored)."""
    version_path = _ANCHORS_DIR / "VERSION"
    assert version_path.exists(), f"AC-13: {version_path} must be committed"
    assert version_path.read_text(encoding="utf-8").strip() == "v1"


def _anchor_files_present() -> bool:
    # Walk-discovered finding 2026-06-27: file naming is `<task>_anchors.jsonl`
    # where task is the literal task name (e.g., `summary_short`), so the file
    # is `summary_short_anchors.jsonl` — NOT `summary_anchors.jsonl` as the
    # AC-3/AC-11 spec said.
    return (_ANCHORS_DIR / "draft_reply_anchors.jsonl").exists() and (
        _ANCHORS_DIR / "summary_short_anchors.jsonl"
    ).exists()


@pytest.mark.skipif(
    not _anchor_files_present(),
    reason="evals/anchors/*.jsonl absent in CI per AC-11 (gitignored)",
)
def test_anchor_schemas_loadable() -> None:
    """AC-3 + AC-10: when anchor files exist (Adam-host-side), they parse + 20 items each."""
    import json

    for task in ("draft_reply", "summary_short"):
        anchor_path = _ANCHORS_DIR / f"{task}_anchors.jsonl"
        lines = [
            ln
            for ln in anchor_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("//")
        ]
        assert len(lines) == 20, (
            f"AC-3: {anchor_path} has {len(lines)} items, expected exactly 20"
        )
        for idx, line in enumerate(lines, start=1):
            anchor = AnchorItem.model_validate(json.loads(line))
            assert anchor.task == task, (
                f"{anchor_path} line {idx} task={anchor.task!r} != {task!r}"
            )


def test_anchor_example_files_loadable() -> None:
    """AC-11 .example sibling validation (always present, gitted)."""
    import json

    for task in ("draft_reply", "summary_short"):
        example = _ANCHORS_DIR / f"{task}_anchors.jsonl.example"
        if not example.exists():
            continue
        for line in example.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            anchor = AnchorItem.model_validate(json.loads(stripped))
            assert anchor.task == task
