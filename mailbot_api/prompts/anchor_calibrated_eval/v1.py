"""Anchor-calibrated subjective scorer prompt v1 — Story 9-7 AC-6.

The strong-model evaluator that scores per-row ``draft_reply`` and
``summary_short`` outputs 1-5 across the per-task rubric axes, using the
hand-anchored examples from Story 9-5 as inline calibration (the full
anchor set per-row; a leave-one-out subset during anchor calibration —
F-ANCHOR-ANSWER-KEY-LEAK fix, Story 9.5.4; count wording removed from
SYSTEM per CR2026-07-04B-W1 so the instruction stays true for both).

The USER_TEMPLATE accepts pre-rendered ``{anchors_block}`` +
``{item_block}`` strings (built by
``benchmark/scoring/subjective.py::build_subjective_eval_payload``).
The SYSTEM block is byte-stable so Anthropic ephemeral prompt cache (Rule M)
fires across the anchor calibration calls + N per-row scoring calls
within a single scorer invocation.

Output is task-agnostic: ``overall_score`` ∈ {1..5} +
``per_axis_scores: dict[str, int]`` where the keys are the rubric axes
(``faithfulness``/``tone_match``/``actionability`` for draft_reply;
``faithfulness``/``concision``/``actionability`` for summary_short). The
evaluator is instructed which axes to emit via the rendered anchors
block — anchors explicitly carry their per-axis labels.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

VERSION: str = "v1"

SYSTEM = (
    "You are a strict evaluator. Score the model output 1-5 across the listed "
    "rubric axes using the anchored examples as calibration. Each anchor "
    "carries Adam's overall score plus per-axis scores; calibrate against "
    "those values, do NOT use your own absolute scale.\n"
    "Reply with valid JSON matching the schema; no preamble, no commentary, "
    "no markdown fences around the JSON. The 'overall_score' is your holistic "
    "verdict 1-5 (not necessarily the mean of the per-axis scores — Adam may "
    "weight faithfulness more heavily). The 'per_axis_scores' dict keys must "
    "exactly match the rubric axes named in the anchored examples for the "
    "task; do not invent new axes; do not omit any axis.\n"
    "Scoring discipline:\n"
    "  - 1: severe failure (hallucinated content, contradicts the inbound, "
    "no actionable signal)\n"
    "  - 2: significant problems (wrong tone, missed primary action, "
    "partial hallucination)\n"
    "  - 3: acceptable but mediocre (does the job, no flair, minor gaps)\n"
    "  - 4: good (faithful, tonally appropriate, surfaces the action)\n"
    "  - 5: excellent (Adam would ship this verbatim)\n"
    "Be honest. A '4' is good; do not reflexively output 5 to look agreeable."
)

USER_TEMPLATE = (
    "## Anchored calibration examples\n"
    "{anchors_block}\n\n"
    "## Item to score\n"
    "{item_block}\n"
)


class SubjectiveAutoEvalOutput(BaseModel):
    """Subjective auto-eval verdict for one item (Story 9-7 AC-5/AC-6).

    The ``per_axis_scores`` dict keys are task-dependent (set by the
    rubric for ``draft_reply`` / ``summary_short``); the model is
    instructed via the rendered anchors block to use the correct axes.
    The scorer module re-validates the axis keys against the expected
    set on parse so a model that ignores instructions surfaces as a
    schema failure rather than silently corrupting the metric rows.

    Pre-review self-audit FIX (LOW): per-axis values are range-validated
    to [1, 5] matching ``overall_score`` so a malformed evaluator
    response with out-of-range axis values surfaces as a schema failure
    rather than feeding garbage into downstream per-axis aggregation.
    """

    overall_score: int = Field(ge=1, le=5)
    per_axis_scores: dict[str, int]

    @field_validator("per_axis_scores")
    @classmethod
    def _check_per_axis_range(cls, value: dict[str, int]) -> dict[str, int]:
        for axis, score in value.items():
            if not 1 <= score <= 5:
                raise ValueError(
                    f"per_axis_scores[{axis!r}] must be in range 1-5; got {score}"
                )
        return value


OUTPUT_SCHEMA: type[BaseModel] = SubjectiveAutoEvalOutput

__all__ = [
    "OUTPUT_SCHEMA",
    "SYSTEM",
    "SubjectiveAutoEvalOutput",
    "USER_TEMPLATE",
    "VERSION",
]
