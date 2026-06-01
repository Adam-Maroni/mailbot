"""Story 3-2 AC-9: schema-rejection-path tests.

Each OUTPUT_SCHEMA's Pydantic constraints (Field(ge=..., le=...), Field(max_length=...),
Literal[...]) must reject invalid payloads at parse time so the Router's
schema-fail-retry chain fires for ill-formed model output.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mailbot_api.prompts.action_extraction.v1 import ActionExtractionOutput, ActionItem
from mailbot_api.prompts.coarse_class.v1 import CoarseClassOutput
from mailbot_api.prompts.fine_class.v1 import FineClassOutput
from mailbot_api.prompts.importance_scoring.v1 import ImportanceScoringOutput
from mailbot_api.prompts.sensitivity_class.v1 import SensitivityClassOutput
from mailbot_api.prompts.summary_short.v1 import SummaryShortOutput


def test_sensitivity_class_rejects_confidence_above_one() -> None:
    """AC-9: confidence > 1.0 fails Field(ge=0, le=1)."""
    with pytest.raises(ValidationError):
        SensitivityClassOutput(sensitivity="normal", confidence=1.5, reason="impossible confidence")


def test_sensitivity_class_rejects_unknown_literal() -> None:
    """AC-9: sensitivity outside {normal, sensitive, confidential} fails Literal."""
    with pytest.raises(ValidationError):
        SensitivityClassOutput(sensitivity="other", confidence=0.5, reason="bad")


def test_sensitivity_class_rejects_reason_too_long() -> None:
    """AC-9 implicit: reason > 200 chars fails Field(max_length=200)."""
    with pytest.raises(ValidationError):
        SensitivityClassOutput(sensitivity="normal", confidence=0.5, reason="x" * 201)


def test_coarse_class_rejects_unknown_literal() -> None:
    """AC-9: class_coarse outside the 6-label taxonomy fails Literal."""
    with pytest.raises(ValidationError):
        CoarseClassOutput(class_coarse="garbage", confidence=0.5)


def test_coarse_class_rejects_confidence_above_one() -> None:
    """CR-6: confidence > 1.0 fails Field(ge=0, le=1)."""
    with pytest.raises(ValidationError):
        CoarseClassOutput(class_coarse="newsletter", confidence=1.5)


def test_fine_class_rejects_unknown_literal() -> None:
    """AC-9 implicit: fine_class outside the 6-label taxonomy fails Literal."""
    with pytest.raises(ValidationError):
        FineClassOutput(class_fine="random", confidence=0.5)


def test_fine_class_rejects_confidence_above_one() -> None:
    """CR-6: confidence > 1.0 fails Field(ge=0, le=1)."""
    with pytest.raises(ValidationError):
        FineClassOutput(class_fine="professional", confidence=1.5)


def test_summary_short_rejects_too_long_summary() -> None:
    """AC-9: summary > 280 chars fails Field(max_length=280)."""
    with pytest.raises(ValidationError):
        SummaryShortOutput(summary="x" * 281)


def test_importance_scoring_rejects_score_above_100() -> None:
    """AC-9: importance > 100 fails Field(ge=0, le=100)."""
    with pytest.raises(ValidationError):
        ImportanceScoringOutput(importance=150, signals=["clearly_out_of_range"])


def test_importance_scoring_rejects_too_many_signals() -> None:
    """AC-9: signals list > 5 items fails Field(max_length=5)."""
    with pytest.raises(ValidationError):
        ImportanceScoringOutput(importance=50, signals=["a", "b", "c", "d", "e", "f"])


def test_action_extraction_rejects_malformed_deadline() -> None:
    """AC-9: deadline_at not matching strict ISO-8601 Z regex fails field_validator."""
    with pytest.raises(ValidationError):
        ActionItem(type="deadline", summary="vague", deadline_at="2026-06-01")


def test_action_extraction_rejects_iso_without_z_suffix() -> None:
    """AC-9 corollary: an ISO timestamp missing the Z suffix fails."""
    with pytest.raises(ValidationError):
        ActionItem(
            type="deadline",
            summary="missing Z",
            deadline_at="2026-06-01T12:00:00",
        )


def test_action_extraction_rejects_unknown_action_type() -> None:
    """AC-9: type outside the 6 ActionItem types fails Literal."""
    with pytest.raises(ValidationError):
        ActionItem(type="malicious_action", summary="rejected")


def test_action_extraction_accepts_null_deadline() -> None:
    """AC-9 positive control: deadline_at=None is permitted."""
    item = ActionItem(type="info_only", summary="no deadline", deadline_at=None)
    assert item.deadline_at is None


def test_action_extraction_accepts_empty_actions_list() -> None:
    """AC-9 positive control: empty actions list is permitted."""
    out = ActionExtractionOutput(actions=[])
    assert out.actions == []


def test_action_extraction_summary_rejects_too_long() -> None:
    """AC-9 implicit: summary > 120 chars fails Field(max_length=120)."""
    with pytest.raises(ValidationError):
        ActionItem(type="reply_needed", summary="x" * 121)
