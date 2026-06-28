"""Story 9-7 AC-3, AC-4: objective scorers (classification + extraction).

Pure leaves (no I/O, no DB, no Router dispatch). The caller in
``benchmark/scorer.py`` reads ``benchmark_runs`` rows + ``CorpusItem``s,
calls these scorers, and writes the resulting ``benchmark_scores`` rows
via ``benchmark/scorer_db.py``.

Two surfaces:

* ``score_classification(rows, items_by_id, task_type, output_field_name)``
  — exact-match aggregation; returns ``ClassificationMetrics`` with
  accuracy / macro precision / macro recall / macro F1 / per-class
  confusion matrix.
* ``score_extraction(rows, items_by_id)`` — field-level F1 for the
  ``action_extraction`` task; returns ``ExtractionMetrics``.

Both return ``ok_count`` and ``total_count`` alongside the per-metric
values so the caller can derive ``ok_rate`` (a separate metric row).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from benchmark.schemas import BenchmarkRunRow
from evals.corpus_schema import CorpusItem


@dataclass(frozen=True)
class ClassificationMetrics:
    """Output of ``score_classification``.

    ``confusion_matrix`` shape: ``{true_label: {pred_label: count}}``.
    Per-class precision / recall / F1 in ``per_class``.
    ``ok_count`` = rows with ``outcome="ok"`` and parseable output;
    ``total_count`` = total rows scored (including failures).
    """

    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    confusion_matrix: dict[str, dict[str, int]]
    per_class: dict[str, dict[str, float]]
    ok_count: int
    total_count: int


@dataclass(frozen=True)
class ExtractionMetrics:
    """Output of ``score_extraction``.

    ``per_action_type`` shape: ``{action_type: {precision, recall, f1, support}}``
    where ``support`` is the count of expected items in the ground truth
    for that action_type.

    Three top-level F1 values flow into separate ``benchmark_scores`` rows
    via the caller (one per metric_name):

    * ``f1_action_type`` — coarse: did we predict the right action_type?
    * ``f1_summary_similarity`` — were the summaries close (cosine ≥ 0.6)?
    * ``f1_deadline_match`` — did the deadline strings match exactly?
    """

    f1_action_type: float
    f1_summary_similarity: float
    f1_deadline_match: float
    per_action_type: dict[str, dict[str, float]]
    ok_count: int
    total_count: int


def score_classification(
    rows: list[BenchmarkRunRow],
    items_by_id: dict[str, CorpusItem],
    task_type: str,
    output_field_name: str,
    ground_truth_attr: str,
) -> ClassificationMetrics:
    """Score classification rows for one (task_type) batch.

    Args:
        rows: ``benchmark_runs`` rows for a single (task_type, model) pair.
            Rows with ``outcome != "ok"`` or missing ``output_json`` are
            COUNTED in ``total_count`` but not scored.
        items_by_id: ``CorpusItem`` lookup keyed by ``corpus_item_id``.
        task_type: e.g. ``"coarse_class"``; used only for error messages.
        output_field_name: the key inside ``output_json`` carrying the
            predicted label (e.g. ``"class_coarse"`` for coarse_class).
        ground_truth_attr: the attribute on ``CorpusItem.labels`` carrying
            the ground-truth label (e.g. ``"class_coarse"``).

    Returns:
        ``ClassificationMetrics`` with accuracy, macro precision/recall/F1,
        and per-class confusion matrix. If no rows are scoreable, accuracy
        and per-metric values are 0.0 (the caller writes an
        ``insufficient_data`` outcome row in that case).
    """
    total_count = len(rows)
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    ok_count = 0

    for row in rows:
        if row.outcome != "ok" or row.output_json is None:
            continue
        item = items_by_id.get(row.corpus_item_id)
        if item is None:
            # Corpus item not in the loaded set — skip with no impact on
            # metrics. The caller logs the gap.
            continue
        try:
            parsed = json.loads(row.output_json)
        except json.JSONDecodeError:
            # Should not happen — the runner only writes parseable JSON
            # on ok rows — but defend anyway.
            continue
        pred = parsed.get(output_field_name)
        truth = getattr(item.labels, ground_truth_attr, None)
        if pred is None or truth is None:
            continue
        pred_str = str(pred)
        truth_str = str(truth)
        confusion.setdefault(truth_str, {}).setdefault(pred_str, 0)
        confusion[truth_str][pred_str] += 1
        if pred_str == truth_str:
            correct += 1
        ok_count += 1

    if ok_count == 0:
        return ClassificationMetrics(
            accuracy=0.0,
            precision_macro=0.0,
            recall_macro=0.0,
            f1_macro=0.0,
            confusion_matrix=confusion,
            per_class={},
            ok_count=0,
            total_count=total_count,
        )

    accuracy = correct / ok_count

    # Per-class precision / recall / F1.
    all_labels = set(confusion.keys())
    for true_label, preds in confusion.items():
        all_labels.update(preds.keys())

    per_class: dict[str, dict[str, float]] = {}
    for label in sorted(all_labels):
        tp = confusion.get(label, {}).get(label, 0)
        fp = sum(
            preds.get(label, 0)
            for true_label, preds in confusion.items()
            if true_label != label
        )
        fn = sum(
            count
            for pred_label, count in confusion.get(label, {}).items()
            if pred_label != label
        )
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        support = tp + fn
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(support),
        }

    precision_macro = (
        sum(c["precision"] for c in per_class.values()) / len(per_class)
        if per_class
        else 0.0
    )
    recall_macro = (
        sum(c["recall"] for c in per_class.values()) / len(per_class)
        if per_class
        else 0.0
    )
    f1_macro = (
        sum(c["f1"] for c in per_class.values()) / len(per_class)
        if per_class
        else 0.0
    )

    return ClassificationMetrics(
        accuracy=accuracy,
        precision_macro=precision_macro,
        recall_macro=recall_macro,
        f1_macro=f1_macro,
        confusion_matrix=confusion,
        per_class=per_class,
        ok_count=ok_count,
        total_count=total_count,
    )


# Hash-bucket cosine similarity: a documented per-story heuristic that
# avoids pulling in sentence-transformers (Rule M). The text is tokenized
# on whitespace + lowercased, each token is SHA-256[:_BUCKET_BITS] hashed
# into a fixed-size sparse vector, then cosine similarity is computed.
# This produces a useful signal for "are these summaries semantically
# close" without any ML dependency — exact-match has cosine 1.0 and
# rephrasings of similar content cluster around 0.5-0.8 because shared
# tokens dominate.
_BUCKET_COUNT: int = 256


def _hash_bucket_vector(text: str) -> list[float]:
    """Project text into a {_BUCKET_COUNT}-dim sparse term-frequency vector."""
    vec = [0.0] * _BUCKET_COUNT
    if not text:
        return vec
    for tok in text.lower().split():
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        # Take first 4 bytes for an unsigned int and mod into buckets.
        bucket = int.from_bytes(h[:4], "big") % _BUCKET_COUNT
        vec[bucket] += 1.0
    return vec


def hash_bucket_cosine_similarity(a: str, b: str) -> float:
    """Cosine similarity in [0.0, 1.0] over the hash-bucket TF vectors.

    Heuristic for ``action_extraction`` summary matching — exact match
    is 1.0, totally-disjoint vocabulary is 0.0, paraphrases cluster
    around 0.4-0.8 depending on shared tokens. Documented in Story 9-7
    AC-4 as an explicit Rule M trade-off; future work may swap this for
    a real sentence-transformer-backed similarity.
    """
    va = _hash_bucket_vector(a)
    vb = _hash_bucket_vector(b)
    dot = sum(x * y for x, y in zip(va, vb, strict=True))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(y * y for y in vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_SIMILARITY_THRESHOLD: float = 0.6


def score_extraction(
    rows: list[BenchmarkRunRow],
    items_by_id: dict[str, CorpusItem],
) -> ExtractionMetrics:
    """Score ``action_extraction`` rows for one (model) batch.

    Per-action-type F1. For each (row, predicted_action):
      * Match an expected action by (action_type) AND
        (summary cosine ≥ _SIMILARITY_THRESHOLD)
      * TP: matched. FP: predicted action_type with no matched expected.
        FN: expected action_type with no matched predicted.

    Three top-level F1 metrics rolled up across action types:
      * f1_action_type — type-only (ignores summary; coarse signal)
      * f1_summary_similarity — type + summary-cosine match
      * f1_deadline_match — type + summary + deadline exact-string match
        (None-vs-None counts as match)

    Items with ``labels.actions is None`` are SKIPPED (no ground truth).
    """
    total_count = len(rows)
    ok_count = 0

    # Per-action-type accumulators.
    type_tp: dict[str, int] = {}
    type_fp: dict[str, int] = {}
    type_fn: dict[str, int] = {}

    # Aggregated counts for the three top-level F1s.
    tp_type = 0
    fp_type = 0
    fn_type = 0
    tp_sim = 0
    fp_sim = 0
    fn_sim = 0
    tp_dl = 0
    fp_dl = 0
    fn_dl = 0

    for row in rows:
        if row.outcome != "ok" or row.output_json is None:
            continue
        item = items_by_id.get(row.corpus_item_id)
        if item is None or item.labels.actions is None:
            continue
        try:
            parsed = json.loads(row.output_json)
        except json.JSONDecodeError:
            continue
        predicted = parsed.get("actions")
        if not isinstance(predicted, list):
            continue
        ok_count += 1

        expected = list(item.labels.actions)  # copy; we mark items used
        used_expected: set[int] = set()

        for pred in predicted:
            if not isinstance(pred, dict):
                continue
            pred_type = pred.get("action_type")
            pred_summary = pred.get("summary", "") or ""
            pred_deadline = pred.get("deadline")

            # Try to match an UNUSED expected by (type, summary cosine ≥ thr).
            matched_idx: int | None = None
            for idx, exp in enumerate(expected):
                if idx in used_expected:
                    continue
                if exp.action_type != pred_type:
                    continue
                sim = hash_bucket_cosine_similarity(pred_summary, exp.summary)
                if sim < _SIMILARITY_THRESHOLD:
                    continue
                matched_idx = idx
                break

            if matched_idx is not None:
                used_expected.add(matched_idx)
                exp = expected[matched_idx]
                tp_type += 1
                tp_sim += 1
                if exp.deadline == pred_deadline:
                    tp_dl += 1
                else:
                    fp_dl += 1
                    fn_dl += 1
                if pred_type is not None:
                    type_tp[pred_type] = type_tp.get(pred_type, 0) + 1
            else:
                # Try a coarser type-only match (helps the f1_action_type
                # rollup distinguish "right type, wrong summary" from
                # "wrong type entirely").
                type_only_match: int | None = None
                for idx, exp in enumerate(expected):
                    if idx in used_expected:
                        continue
                    if exp.action_type == pred_type:
                        type_only_match = idx
                        break
                if type_only_match is not None:
                    used_expected.add(type_only_match)
                    tp_type += 1
                    # CR-F2 (MEDIUM): also update the per-action-type dict
                    # so the per_action_type extra_json breakdown stays
                    # consistent with the headline f1_action_type metric.
                    # Without this, Story 9-9's per-action-type analysis
                    # would underreport TP for type-only-matched predictions
                    # vs the global f1_action_type rollup.
                    if pred_type is not None:
                        type_tp[pred_type] = type_tp.get(pred_type, 0) + 1
                    fp_sim += 1
                    fp_dl += 1
                    fn_sim += 1
                    fn_dl += 1
                else:
                    fp_type += 1
                    fp_sim += 1
                    fp_dl += 1
                    if pred_type is not None:
                        type_fp[pred_type] = type_fp.get(pred_type, 0) + 1

        # Unmatched expected items are FN.
        for idx, exp in enumerate(expected):
            if idx in used_expected:
                continue
            fn_type += 1
            fn_sim += 1
            fn_dl += 1
            type_fn[exp.action_type] = type_fn.get(exp.action_type, 0) + 1

    def _f1(tp: int, fp: int, fn: int) -> float:
        if tp == 0 and fp == 0 and fn == 0:
            return 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0.0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    f1_action_type = _f1(tp_type, fp_type, fn_type)
    f1_summary_similarity = _f1(tp_sim, fp_sim, fn_sim)
    f1_deadline_match = _f1(tp_dl, fp_dl, fn_dl)

    per_type: dict[str, dict[str, float]] = {}
    all_types = set(type_tp) | set(type_fp) | set(type_fn)
    for t in sorted(all_types):
        tp_t = type_tp.get(t, 0)
        fp_t = type_fp.get(t, 0)
        fn_t = type_fn.get(t, 0)
        precision = tp_t / (tp_t + fp_t) if (tp_t + fp_t) > 0 else 0.0
        recall = tp_t / (tp_t + fn_t) if (tp_t + fn_t) > 0 else 0.0
        f1_t = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        per_type[t] = {
            "precision": precision,
            "recall": recall,
            "f1": f1_t,
            "support": float(tp_t + fn_t),
        }

    return ExtractionMetrics(
        f1_action_type=f1_action_type,
        f1_summary_similarity=f1_summary_similarity,
        f1_deadline_match=f1_deadline_match,
        per_action_type=per_type,
        ok_count=ok_count,
        total_count=total_count,
    )


__all__ = [
    "ClassificationMetrics",
    "ExtractionMetrics",
    "hash_bucket_cosine_similarity",
    "score_classification",
    "score_extraction",
]
