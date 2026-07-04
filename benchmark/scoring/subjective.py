"""Story 9-7 AC-5, AC-7, AC-11, AC-12: anchor-calibrated subjective scorer.

Scores ``draft_reply`` and ``summary_short`` ``benchmark_runs`` rows by
dispatching the strong-model evaluator (Opus by default for primary;
Sonnet by default for secondary cross-evaluator) through
``ask_router(task_type="anchor_calibrated_eval", force_model=<scorer>,
force=True, caller_origin="benchmark-scorer", email_id=None)`` per Rule I.

Three load-bearing pieces:

1. **Anchor calibration** (AC-5) — the evaluator is FIRST run against
   the 20 hand-anchored items themselves. MAE between the evaluator's
   ``overall_score`` and Adam's ``adam_overall_score`` is reported in
   the ``calibration_mae`` metric row. If MAE > 0.5, every per-model
   subjective row for the batch gets ``outcome="calibration_warning"``.

2. **Per-row scoring** (AC-5) — for each ``benchmark_runs`` row with
   ``outcome="ok"``, the evaluator scores the model output. Per-task
   aggregation rolls into ``subjective_overall`` + per-axis rows.

3. **Cross-evaluator Krippendorff α** (AC-7) — opt-in via
   ``secondary_evaluator``; the secondary evaluator scores the SAME 20
   anchors, and α is computed via ``benchmark/agreement.py`` on the two
   evaluators' anchor scores. α < 0.6 trips ``calibration_warning``.

The module dispatches through the real Router so Story 2-7 response
cache (24h TTL on ``anchor_calibrated_eval`` per AC-6) absorbs re-runs
within the cache window — AC-12 is exercised by counting cache-hit
short-circuits.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from benchmark.agreement import krippendorff_alpha_ordinal
from benchmark.schemas import BenchmarkRunRow
from evals.corpus_schema import AnchorItem, CorpusItem

# Re-export the prompt module's schema so callers don't need to reach
# across the mailbot_api/prompts boundary just for the shape.
from mailbot_api.prompts.anchor_calibrated_eval.v1 import SubjectiveAutoEvalOutput

_logger = logging.getLogger(__name__)

_CALIBRATION_MAE_THRESHOLD: float = 0.5
_CROSS_EVALUATOR_ALPHA_THRESHOLD: float = 0.6

# Per-task expected axes (mirrors evals/corpus_schema._DRAFT_REPLY_AXES /
# _SUMMARY_SHORT_AXES so anchor validation + scorer validation share
# the same axis set).
_TASK_AXES: dict[str, frozenset[str]] = {
    "draft_reply": frozenset({"faithfulness", "tone_match", "actionability"}),
    "summary_short": frozenset({"faithfulness", "concision", "actionability"}),
}


@dataclass(frozen=True)
class _AnchorCalibrationResult:
    """Per-evaluator anchor calibration outcome."""

    per_anchor_auto_scores: list[int]
    per_anchor_adam_scores: list[int]
    per_anchor_ids: list[str]
    mae: float


@dataclass(frozen=True)
class _PerRowSubjectiveScore:
    """One row of per-model subjective scoring."""

    corpus_item_id: str
    overall_score: int
    per_axis_scores: dict[str, int]


@dataclass(frozen=True)
class SubjectiveMetrics:
    """Output of ``score_subjective`` for one (task, model) batch.

    Field semantics:
      * ``mean_overall``: mean of per-row overall_score (per AC-5).
      * ``mean_per_axis``: per-axis mean across the rows.
      * ``calibration_mae``: anchor MAE for the PRIMARY evaluator. NOT
        comparable to values recorded before the Story 9.5.4 leave-one-out
        fix (2026-07-04) — pre-fix MAE was computed against answer-key-
        contaminated context (the scored anchor sat in its own calibration
        block with Adam's score visible).
      * ``cross_evaluator_alpha``: None if no secondary; else α in [-1, 1].
      * ``outcome``: ``"ok"`` / ``"calibration_warning"`` /
        ``"insufficient_data"``. Calibration warning trips when MAE > 0.5
        OR α < 0.6.
      * ``ok_count`` / ``total_count``: same semantics as objective scorers.
    """

    mean_overall: float
    mean_per_axis: dict[str, float]
    per_row_scores: list[_PerRowSubjectiveScore]
    calibration_mae: float
    calibration_per_anchor: list[dict[str, float | str | int]]
    cross_evaluator_alpha: float | None
    cross_evaluator_per_anchor: list[dict[str, float | str | int]] = field(default_factory=list)
    outcome: str = "ok"
    ok_count: int = 0
    total_count: int = 0


def load_anchors(anchors_dir: Path, task_type: str) -> list[AnchorItem]:
    """Read the 20-item JSONL anchor file for ``task_type``.

    Path: ``<anchors_dir>/<task_type>_anchors.jsonl``. Raises
    ``FileNotFoundError`` if absent (fail-loud — silently scoring on an
    empty calibration set would defeat the AC-5 contract).
    """
    path = anchors_dir / f"{task_type}_anchors.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"anchor file not found at {path}; Story 9-5 AC-3 requires 20 anchors per task"
        )
    items: list[AnchorItem] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("//"):
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}: line {line_num}: invalid JSON: {exc.msg}"
                ) from exc
            try:
                items.append(AnchorItem.model_validate(row))
            except Exception as exc:
                raise ValueError(
                    f"{path}: line {line_num}: schema validation failed: {exc}"
                ) from exc
    return items


def build_anchors_block(anchors: list[AnchorItem]) -> str:
    """Render the given anchors as a markdown calibration block.

    Each anchor section carries the input subject/body, the model_output
    being scored, Adam's per-axis scores, his overall score, and the
    score_rationale. The evaluator uses this to calibrate its scoring.
    """
    blocks: list[str] = []
    for idx, a in enumerate(anchors, start=1):
        axis_lines = "\n".join(
            f"  - {axis}: {score}" for axis, score in sorted(a.adam_score_axes.items())
        )
        blocks.append(
            f"### Anchor {idx} (id={a.id})\n"
            f"Input subject: {a.input_email_subject}\n"
            f"Input body:\n{a.input_email_body}\n\n"
            f"Model output to score:\n{a.model_output}\n\n"
            f"Adam's per-axis scores:\n{axis_lines}\n"
            f"Adam's overall_score: {a.adam_overall_score}\n"
            f"Score rationale: {a.score_rationale}\n"
        )
    return "\n".join(blocks)


def build_item_block(model_output: str, raw_subject: str, raw_body: str) -> str:
    """Render the item-under-test block sent to the evaluator."""
    return (
        f"Input subject: {raw_subject}\n"
        f"Input body:\n{raw_body}\n\n"
        f"Model output to score:\n{model_output}\n"
    )


def _build_payload(
    anchors_block: str, item_block: str
) -> dict[str, str]:
    """Build the ``content`` dict for ``ask_router`` per the v1 USER_TEMPLATE."""
    return {"anchors_block": anchors_block, "item_block": item_block}


async def _dispatch_eval(
    db_path: str,
    scorer_model: str,
    anchors_block: str,
    item_block: str,
) -> SubjectiveAutoEvalOutput | None:
    """Dispatch one auto-eval call through ask_router; return parsed shape or None.

    Returns ``None`` on dispatch failure (the caller decides whether the
    failure tips the batch into ``insufficient_data`` or just gets
    skipped). Per Rule I, every call goes through the real Router.
    """
    from mailbot_api.router.router import ask_router

    result = await ask_router(
        task_type="anchor_calibrated_eval",
        content=_build_payload(anchors_block, item_block),
        db_path=db_path,
        force_model=scorer_model,
        force=True,
        caller_origin="benchmark-scorer",
        caller_verb="scorer.anchor_calibrated_eval",
        email_id=None,
    )
    if not result.ok or result.output is None:
        return None
    if isinstance(result.output, SubjectiveAutoEvalOutput):
        return result.output
    # Some Router paths return the raw dict; defensively re-validate.
    try:
        return SubjectiveAutoEvalOutput.model_validate(result.output)
    except Exception:
        return None


async def _run_anchor_calibration(
    anchors: list[AnchorItem],
    db_path: str,
    scorer_model: str,
) -> _AnchorCalibrationResult:
    """Run the auto-eval against each anchor in ``anchors``; compute MAE.

    F-ANCHOR-ANSWER-KEY-LEAK fix (Story 9.5.4 walk, 2026-07-04): each anchor is
    scored against a leave-one-out block of the OTHER anchors. Sending the full
    block put the item under test — with Adam's overall_score and rationale —
    inside its own calibration context, so the evaluator could read the answer
    key for the item it was scoring (observed live: opus reproduced Adam's
    labels 39/40, confounding both MAE and Krippendorff α).
    """
    auto_scores: list[int] = []
    adam_scores: list[int] = []
    ids: list[str] = []
    for anchor in anchors:
        loo_block = build_anchors_block([a for a in anchors if a.id != anchor.id])
        item_block = build_item_block(
            model_output=anchor.model_output,
            raw_subject=anchor.input_email_subject,
            raw_body=anchor.input_email_body,
        )
        parsed = await _dispatch_eval(db_path, scorer_model, loo_block, item_block)
        if parsed is None:
            # Pre-review self-audit FIX (LOW): log the dispatch failure
            # at WARNING so the operator can grep for silent drops.
            # Skip this anchor in the MAE; the Krippendorff α path later
            # aligns by anchor_id and tolerates the missing data.
            _logger.warning(
                "scorer.anchor_calibration_dispatch_failed scorer_model=%s anchor_id=%s",
                scorer_model,
                anchor.id,
            )
            continue
        auto_scores.append(parsed.overall_score)
        adam_scores.append(anchor.adam_overall_score)
        ids.append(anchor.id)

    if not auto_scores:
        return _AnchorCalibrationResult(
            per_anchor_auto_scores=[],
            per_anchor_adam_scores=[],
            per_anchor_ids=[],
            mae=float("inf"),
        )
    n = len(auto_scores)
    mae = sum(abs(a - b) for a, b in zip(auto_scores, adam_scores, strict=True)) / n
    return _AnchorCalibrationResult(
        per_anchor_auto_scores=auto_scores,
        per_anchor_adam_scores=adam_scores,
        per_anchor_ids=ids,
        mae=mae,
    )


async def score_subjective(
    rows: list[BenchmarkRunRow],
    items_by_id: dict[str, CorpusItem],
    anchors: list[AnchorItem],
    db_path: str,
    scorer_model: str,
    task_type: str,
    secondary_evaluator: str | None = None,
) -> SubjectiveMetrics:
    """Score subjective rows for one (task_type, model) batch.

    Workflow:
      1. Render the anchors block once (input to every PER-ROW dispatch;
         calibration dispatches build their own leave-one-out blocks).
      2. Run anchor calibration on the PRIMARY evaluator → MAE.
      3. (Optional) Run anchor calibration on the SECONDARY evaluator →
         compute Krippendorff α on the 20-anchor pair-scores.
      4. For each ``benchmark_runs`` row with ``outcome="ok"``, dispatch
         the per-row scorer and aggregate overall + per-axis means.
      5. Tip outcome to ``calibration_warning`` if MAE > 0.5 or α < 0.6.
    """
    total_count = len(rows)
    anchors_block = build_anchors_block(anchors)

    primary = await _run_anchor_calibration(anchors, db_path, scorer_model)
    calibration_per_anchor: list[dict[str, float | str | int]] = [
        {
            "anchor_id": aid,
            "auto_score": int(auto),
            "adam_score": int(adam),
            "abs_error": float(abs(auto - adam)),
        }
        for aid, auto, adam in zip(
            primary.per_anchor_ids,
            primary.per_anchor_auto_scores,
            primary.per_anchor_adam_scores,
            strict=True,
        )
    ]

    # Per-row scoring.
    expected_axes = _TASK_AXES.get(task_type, frozenset())
    per_row: list[_PerRowSubjectiveScore] = []
    ok_count = 0
    for row in rows:
        if row.outcome != "ok" or row.output_json is None:
            continue
        item = items_by_id.get(row.corpus_item_id)
        if item is None:
            continue
        # The model_output to score is the JSON the dispatched model produced.
        # Per AC-5 the evaluator scores against the parsed JSON shape; we
        # serialize back to a markdown-friendly form so the evaluator's
        # prompt is consistent across tasks.
        item_block = build_item_block(
            model_output=row.output_json,
            raw_subject=item.raw_subject,
            raw_body=item.raw_body,
        )
        parsed = await _dispatch_eval(
            db_path, scorer_model, anchors_block, item_block
        )
        if parsed is None:
            # Pre-review self-audit FIX (LOW): operator visibility for
            # silent dispatch failures on per-row scoring.
            _logger.warning(
                "scorer.per_row_dispatch_failed scorer_model=%s task=%s "
                "model=%s corpus_item_id=%s",
                scorer_model,
                row.task_type,
                row.model,
                row.corpus_item_id,
            )
            continue
        # Validate per-axis keys match the task; drop the row on mismatch
        # rather than silently merging into a partial aggregate.
        if expected_axes and frozenset(parsed.per_axis_scores.keys()) != expected_axes:
            _logger.warning(
                "scorer.per_axis_keys_mismatch scorer_model=%s task=%s "
                "model=%s corpus_item_id=%s expected=%s got=%s",
                scorer_model,
                row.task_type,
                row.model,
                row.corpus_item_id,
                sorted(expected_axes),
                sorted(parsed.per_axis_scores.keys()),
            )
            continue
        per_row.append(
            _PerRowSubjectiveScore(
                corpus_item_id=row.corpus_item_id,
                overall_score=parsed.overall_score,
                per_axis_scores=dict(parsed.per_axis_scores),
            )
        )
        ok_count += 1

    if per_row:
        mean_overall = sum(p.overall_score for p in per_row) / len(per_row)
        # Per-axis mean across rows. We use the expected_axes set as the
        # ordered axis list so the output is task-stable.
        mean_per_axis: dict[str, float] = {}
        for axis in sorted(expected_axes):
            values = [p.per_axis_scores[axis] for p in per_row if axis in p.per_axis_scores]
            if values:
                mean_per_axis[axis] = sum(values) / len(values)
    else:
        mean_overall = 0.0
        mean_per_axis = {}

    # Cross-evaluator α path.
    alpha: float | None = None
    cross_per_anchor: list[dict[str, float | str | int]] = []
    if secondary_evaluator is not None:
        secondary = await _run_anchor_calibration(anchors, db_path, secondary_evaluator)
        # Align the two evaluators' per-anchor score lists by anchor_id so
        # an evaluator that failed on a specific anchor doesn't corrupt the
        # pairing.
        primary_by_id = {
            aid: score
            for aid, score in zip(
                primary.per_anchor_ids, primary.per_anchor_auto_scores, strict=True
            )
        }
        secondary_by_id = {
            aid: score
            for aid, score in zip(
                secondary.per_anchor_ids, secondary.per_anchor_auto_scores, strict=True
            )
        }
        all_ids = sorted(set(primary_by_id) | set(secondary_by_id))
        primary_aligned: list[float | None] = [
            float(primary_by_id[aid]) if aid in primary_by_id else None for aid in all_ids
        ]
        secondary_aligned: list[float | None] = [
            float(secondary_by_id[aid]) if aid in secondary_by_id else None for aid in all_ids
        ]
        try:
            alpha = krippendorff_alpha_ordinal(
                {"primary": primary_aligned, "secondary": secondary_aligned}
            )
        except ValueError:
            # Too few pairable observations — surface as None, the caller
            # will write the metric with outcome="insufficient_data".
            alpha = None
        for aid, p_score, s_score in zip(
            all_ids, primary_aligned, secondary_aligned, strict=True
        ):
            cross_per_anchor.append(
                {
                    "anchor_id": aid,
                    "primary_score": float(p_score) if p_score is not None else -1.0,
                    "secondary_score": float(s_score) if s_score is not None else -1.0,
                    "delta": (
                        float(abs(p_score - s_score))
                        if p_score is not None and s_score is not None
                        else -1.0
                    ),
                }
            )

    # Decide outcome.
    outcome = "ok"
    if not per_row:
        outcome = "insufficient_data"
    elif primary.mae > _CALIBRATION_MAE_THRESHOLD:
        outcome = "calibration_warning"
    elif alpha is not None and alpha < _CROSS_EVALUATOR_ALPHA_THRESHOLD:
        outcome = "calibration_warning"

    return SubjectiveMetrics(
        mean_overall=mean_overall,
        mean_per_axis=mean_per_axis,
        per_row_scores=per_row,
        calibration_mae=primary.mae,
        calibration_per_anchor=calibration_per_anchor,
        cross_evaluator_alpha=alpha,
        cross_evaluator_per_anchor=cross_per_anchor,
        outcome=outcome,
        ok_count=ok_count,
        total_count=total_count,
    )


__all__ = [
    "SubjectiveAutoEvalOutput",
    "SubjectiveMetrics",
    "build_anchors_block",
    "build_item_block",
    "load_anchors",
    "score_subjective",
]
