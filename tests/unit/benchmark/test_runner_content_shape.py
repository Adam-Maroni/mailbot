"""Story 9.5.3 hotfix: benchmark.runner._build_content per-task shape adaptation.

Walk-discovered defect: the benchmark runner passed a single
``{subject, sender, body_preview}`` content dict to every task's
``ask_router`` call, but ``draft_reply`` (Story 5-3) expects
``{source_email, thread_context, tone_signals}``. The mismatch surfaced
as ``prompt render failed: KeyError: 'source_email'`` on 100% of
draft_reply dispatches during Story 9.5.3 AC-5 walk.
"""

from __future__ import annotations

import pytest

from benchmark.runner import _build_content
from evals.corpus_schema import CorpusItem, CorpusLabels


def _corpus_item() -> CorpusItem:
    return CorpusItem(
        id="test-item-001",
        category="transactional",
        source_note="unit test fixture",
        raw_subject="Test subject",
        raw_body="Test body content.",
        labels=CorpusLabels(
            sensitivity="normal",
            class_coarse="business",
        ),
    )


def test_build_content_default_shape_for_ingest_tasks() -> None:
    """Ingest tasks (summary_short, importance_scoring, action_extraction,
    coarse_class, sensitivity_class, fine_class) use the 3-field ingest shape."""
    item = _corpus_item()
    for task in (
        "summary_short",
        "importance_scoring",
        "action_extraction",
        "coarse_class",
        "sensitivity_class",
        "fine_class",
    ):
        content = _build_content(item, task_type=task)
        assert set(content.keys()) == {"subject", "sender", "body_preview"}, task
        assert content["subject"] == "Test subject"
        assert content["body_preview"] == "Test body content."


def test_build_content_draft_reply_shape() -> None:
    """draft_reply uses the {source_email, thread_context, tone_signals} shape
    from Story 5-3's USER_TEMPLATE. Without this adaptation the prompt
    render fails with KeyError: 'source_email' before the adapter is called.
    """
    item = _corpus_item()
    content = _build_content(item, task_type="draft_reply")

    assert set(content.keys()) == {"source_email", "thread_context", "tone_signals"}
    # source_email is the assembled subject + sender + body
    assert "Test subject" in content["source_email"]
    assert "Test body content." in content["source_email"]
    # thread_context and tone_signals are non-empty placeholders (empty strings
    # would render as blank sections in the prompt — placeholders are more
    # legible in the router audit trail).
    assert content["thread_context"]
    assert content["tone_signals"]


def test_build_content_no_task_type_defaults_to_ingest_shape() -> None:
    """Backward compat: calling without task_type falls back to ingest shape.
    (No live caller does this post-hotfix, but preserving the signature
    default keeps the pre-hotfix API contract intact.)"""
    item = _corpus_item()
    content = _build_content(item)
    assert set(content.keys()) == {"subject", "sender", "body_preview"}


def test_build_content_unknown_task_type_raises_not_implemented() -> None:
    """CR-F4/F6 (2026-07-03): the pre-patch else-branch silently returned
    the ingest 3-tuple for any unknown task_type, so tasks the grid opts
    in (notably ``reference_resolution`` via
    ``labels.reference_resolution_slice``) crashed at prompt-render with
    an obscure ``KeyError``. Post-patch: raise ``NotImplementedError``
    at cell-dispatch with a message listing the known task types."""
    item = _corpus_item()
    with pytest.raises(NotImplementedError) as excinfo:
        _build_content(item, task_type="reference_resolution")
    msg = str(excinfo.value)
    assert "reference_resolution" in msg
    assert "content-shape adapter" in msg
    # Message enumerates known types so the developer can see what IS supported.
    assert "draft_reply" in msg
    assert "summary_short" in msg
