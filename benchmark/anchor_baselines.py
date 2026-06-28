"""Story 9-11 AC-8: stale-baseline detection helper for Epic-10+ drift checks.

Pure-leaf module:
  * ``load_baseline``    — read a persisted baseline JSON, enforce required
    fields. Pydantic-validated via the same shape the audit CLI writes.
  * ``compare_against_current`` — diff an on-disk baseline against a current
    audit snapshot; flag drift when α moves by > 0.1 OR the verdict changed.

No I/O outside of the explicit ``Path`` argument; no DB; no Router.
The audit CLI itself (``benchmark/anchor_stability_audit.py``) owns the
write side; this module owns the read + compare side so future drift-
detection tooling has a single integration point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VerdictLiteral = Literal["trusted", "uncertain", "untrusted"]

# Drift threshold: α deltas above this magnitude flag drift_detected even if
# the verdict band did not change. 0.1 was chosen as ~1 standard error for a
# 20-anchor ordinal α (back-of-envelope; the actual SE depends on the
# disagreement pattern). Epic 10+ may tune this once a second baseline run
# exists for empirical comparison.
_ALPHA_DRIFT_THRESHOLD: float = 0.1


class PerAnchorScore(BaseModel):
    """One anchor's per-evaluator score pair + delta. Mirrors schema."""

    model_config = ConfigDict(extra="forbid")

    anchor_id: str = Field(min_length=1)
    task: Literal["summary_short", "draft_reply"]
    primary_score: int = Field(ge=1, le=5)
    secondary_score: int = Field(ge=1, le=5)
    delta: int = Field(ge=0, le=4)


class BaselineSnapshot(BaseModel):
    """Full baseline file shape; mirrors evals/schemas/anchor_baseline.schema.json."""

    model_config = ConfigDict(extra="forbid")

    baseline_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    primary_evaluator: str = Field(min_length=1)
    secondary_evaluator: str = Field(min_length=1)
    anchors_version: str = Field(min_length=1)
    per_anchor_scores: list[PerAnchorScore] = Field(min_length=1)
    krippendorff_alpha: float = Field(ge=-1.0, le=1.0)
    verdict: VerdictLiteral


@dataclass(frozen=True)
class PerAnchorDiff:
    """One anchor's score-change between baseline and current."""

    anchor_id: str
    task: str
    baseline_primary: int
    current_primary: int
    baseline_secondary: int
    current_secondary: int
    baseline_delta: int
    current_delta: int


@dataclass(frozen=True)
class BaselineComparison:
    """Output of ``compare_against_current``.

    * ``alpha_delta`` is ``current.alpha - baseline.alpha``; positive means
      the current run agrees MORE with the secondary evaluator than the
      baseline did.
    * ``verdict_changed`` is True iff the verdict band (trusted/uncertain/
      untrusted) flipped between baseline and current.
    * ``drift_detected`` is the union: True iff abs(alpha_delta) >
      _ALPHA_DRIFT_THRESHOLD OR verdict_changed. The threshold can be
      tuned in Epic 10+ once a real baseline + a real follow-up exist.
    * ``per_anchor_diffs`` lists each anchor whose score pair changed
      between baseline and current. Anchors present in only one side are
      flagged with sentinel scores (baseline-missing → baseline_* = -1;
      current-missing → current_* = -1) so the caller can detect anchor-
      set drift.
    """

    alpha_delta: float
    verdict_changed: bool
    drift_detected: bool
    per_anchor_diffs: list[PerAnchorDiff] = field(default_factory=list)


def load_baseline(path: Path) -> BaselineSnapshot:
    """Read + validate a persisted baseline file.

    Raises ``FileNotFoundError`` if absent (fail-loud — silently returning
    a default baseline would defeat drift detection). Raises
    ``ValueError`` on schema-validation failure with the Pydantic error
    chained as the cause.
    """
    if not path.is_file():
        raise FileNotFoundError(f"baseline file not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    try:
        return BaselineSnapshot.model_validate(raw)
    except Exception as exc:
        raise ValueError(
            f"{path}: anchor_baseline schema validation failed: {exc}"
        ) from exc


def compare_against_current(
    baseline_path: Path,
    current: BaselineSnapshot,
) -> BaselineComparison:
    """Diff an on-disk baseline against a current audit snapshot.

    Args:
        baseline_path: persisted baseline JSON path (typically
            ``evals/anchor_baselines/v1.json``).
        current: in-memory snapshot from a re-run of the audit (caller is
            expected to have validated this against the same schema).

    Returns:
        ``BaselineComparison`` with alpha_delta, verdict_changed flag,
        per-anchor drift list, and the unioned ``drift_detected`` flag.
    """
    baseline = load_baseline(baseline_path)

    alpha_delta = current.krippendorff_alpha - baseline.krippendorff_alpha
    verdict_changed = baseline.verdict != current.verdict

    baseline_by_id: dict[str, PerAnchorScore] = {
        s.anchor_id: s for s in baseline.per_anchor_scores
    }
    current_by_id: dict[str, PerAnchorScore] = {
        s.anchor_id: s for s in current.per_anchor_scores
    }
    all_ids = sorted(set(baseline_by_id) | set(current_by_id))

    diffs: list[PerAnchorDiff] = []
    for anchor_id in all_ids:
        b = baseline_by_id.get(anchor_id)
        c = current_by_id.get(anchor_id)
        if b is not None and c is not None:
            # Only record diffs where scores actually changed.
            if (
                b.primary_score == c.primary_score
                and b.secondary_score == c.secondary_score
            ):
                continue
            diffs.append(
                PerAnchorDiff(
                    anchor_id=anchor_id,
                    task=b.task,
                    baseline_primary=b.primary_score,
                    current_primary=c.primary_score,
                    baseline_secondary=b.secondary_score,
                    current_secondary=c.secondary_score,
                    baseline_delta=b.delta,
                    current_delta=c.delta,
                )
            )
        elif b is not None:
            # Anchor present in baseline but missing from current.
            diffs.append(
                PerAnchorDiff(
                    anchor_id=anchor_id,
                    task=b.task,
                    baseline_primary=b.primary_score,
                    current_primary=-1,
                    baseline_secondary=b.secondary_score,
                    current_secondary=-1,
                    baseline_delta=b.delta,
                    current_delta=-1,
                )
            )
        else:
            # Anchor present in current but not in baseline.
            assert c is not None  # union-of-keys → at least one side non-None
            diffs.append(
                PerAnchorDiff(
                    anchor_id=anchor_id,
                    task=c.task,
                    baseline_primary=-1,
                    current_primary=c.primary_score,
                    baseline_secondary=-1,
                    current_secondary=c.secondary_score,
                    baseline_delta=-1,
                    current_delta=c.delta,
                )
            )

    drift_detected = (
        abs(alpha_delta) > _ALPHA_DRIFT_THRESHOLD or verdict_changed
    )
    return BaselineComparison(
        alpha_delta=alpha_delta,
        verdict_changed=verdict_changed,
        drift_detected=drift_detected,
        per_anchor_diffs=diffs,
    )


__all__ = [
    "BaselineComparison",
    "BaselineSnapshot",
    "PerAnchorDiff",
    "PerAnchorScore",
    "VerdictLiteral",
    "compare_against_current",
    "load_baseline",
]
