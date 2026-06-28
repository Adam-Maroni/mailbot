"""Story 9-7 AC-6: ``anchor_calibrated_eval`` prompt-module package.

The strong-model evaluator used by ``benchmark/scoring/subjective.py`` to
score per-row subjective outputs (``draft_reply`` / ``summary_short``)
1-5 across the rubric axes, calibrated against the 20 hand-anchored
examples from Story 9-5 (in ``evals/anchors/<task>_anchors.jsonl``).

Per the per-task prompt convention (``mailbot_api/prompts/<task>/<vN>.py``),
the v1 module exposes:

* ``VERSION = "v1"``
* ``SYSTEM`` — byte-stable evaluator instruction
* ``USER_TEMPLATE`` — format string accepting ``{anchors_block}`` and
  ``{item_block}`` keys built by ``benchmark/scoring/subjective.py``
* ``OUTPUT_SCHEMA = SubjectiveAutoEvalOutput`` — Pydantic shape with
  ``overall_score`` (1-5) and per-axis scores
"""
