"""Story 9-7 AC-6: ``anchor_calibrated_eval/v1.py`` prompt-module unit tests.

Validates the AR-PAT-5 4-export shape (VERSION + SYSTEM + USER_TEMPLATE +
OUTPUT_SCHEMA), resolution via ``resolve_prompt``, and the
``SubjectiveAutoEvalOutput`` schema's score-range enforcement.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mailbot_api.prompts import resolve_prompt
from mailbot_api.prompts.anchor_calibrated_eval.v1 import (
    OUTPUT_SCHEMA,
    SYSTEM,
    USER_TEMPLATE,
    VERSION,
    SubjectiveAutoEvalOutput,
)


def test_version_is_v1() -> None:
    assert VERSION == "v1"


def test_resolve_prompt_picks_up_module() -> None:
    """Story 2-4 AC-3 dynamic resolver finds the new module."""
    module = resolve_prompt("anchor_calibrated_eval", "v1")
    assert module.version == "v1"
    assert module.system == SYSTEM
    assert module.user_template == USER_TEMPLATE
    assert module.output_schema is OUTPUT_SCHEMA


def test_system_is_byte_stable_string() -> None:
    """Rule M: SYSTEM must be a non-empty str (caches by content hash)."""
    assert isinstance(SYSTEM, str)
    assert len(SYSTEM) > 100, "SYSTEM should carry calibration instructions"


def test_user_template_accepts_anchors_and_item_keys() -> None:
    """USER_TEMPLATE renders with the two payload keys built by subjective.py."""
    rendered = USER_TEMPLATE.format(
        anchors_block="(anchor1)\n(anchor2)",
        item_block="(item under test)",
    )
    assert "(anchor1)" in rendered
    assert "(item under test)" in rendered


def test_output_schema_accepts_valid_payload() -> None:
    out = SubjectiveAutoEvalOutput.model_validate(
        {
            "overall_score": 4,
            "per_axis_scores": {"faithfulness": 5, "tone_match": 4, "actionability": 3},
        }
    )
    assert out.overall_score == 4
    assert out.per_axis_scores["faithfulness"] == 5


def test_output_schema_rejects_out_of_range_overall() -> None:
    with pytest.raises(ValidationError):
        SubjectiveAutoEvalOutput.model_validate(
            {"overall_score": 6, "per_axis_scores": {"faithfulness": 3}}
        )


def test_output_schema_rejects_zero_overall() -> None:
    with pytest.raises(ValidationError):
        SubjectiveAutoEvalOutput.model_validate(
            {"overall_score": 0, "per_axis_scores": {"faithfulness": 3}}
        )


def test_output_schema_accepts_empty_per_axis() -> None:
    """Schema-level acceptance — axis-set validation lives in the scorer
    (it knows which axes apply to which task; the prompt module does not)."""
    out = SubjectiveAutoEvalOutput.model_validate(
        {"overall_score": 3, "per_axis_scores": {}}
    )
    assert out.per_axis_scores == {}
