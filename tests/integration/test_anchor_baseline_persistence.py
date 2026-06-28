"""Story 9-11 AC-9: anchor baseline persistence + drift-helper integration.

Verifies:
  * The audit produces a baseline file that validates against
    ``evals/schemas/anchor_baseline.schema.json``.
  * ``compare_against_current`` is exposed via ``benchmark.__init__::__all__``.
  * The helper flags ``drift_detected=True`` when ``alpha_delta`` exceeds
    the 0.1 threshold OR the verdict band changed.
  * Per-anchor scores in the file are sorted by ``anchor_id`` (diff-
    friendliness invariant).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import benchmark
from benchmark.anchor_baselines import (
    BaselineSnapshot,
    PerAnchorScore,
    compare_against_current,
    load_baseline,
)
from benchmark.anchor_stability_audit import (
    _compose_baseline,
    _serialize_baseline,
    _write_baseline_atomic,
)

_SCHEMA_PATH = Path("evals/schemas/anchor_baseline.schema.json")


def _make_snapshot(
    *,
    alpha: float,
    verdict: str,
    pairs: list[PerAnchorScore],
    baseline_date: str = "2026-06-28",
    primary: str = "claude-opus-4-7-20251220",
    secondary: str = "claude-sonnet-4-5",
    anchors_version: str = "v1",
) -> BaselineSnapshot:
    return _compose_baseline(
        primary_evaluator=primary,
        secondary_evaluator=secondary,
        anchors_version=anchors_version,
        per_anchor_scores=pairs,
        alpha=alpha,
        verdict=verdict,  # type: ignore[arg-type]
        baseline_date=baseline_date,
    )


def _pair(idx: int, primary: int, secondary: int, task: str = "summary_short") -> PerAnchorScore:
    return PerAnchorScore(
        anchor_id=f"anchor-{task}-{idx:03d}",
        task=task,  # type: ignore[arg-type]
        primary_score=primary,
        secondary_score=secondary,
        delta=abs(primary - secondary),
    )


def test_compare_against_current_is_publicly_exported() -> None:
    """AC-9: helper must be importable from the top-level benchmark package."""
    assert "compare_against_current" in benchmark.__all__
    assert "load_baseline" in benchmark.__all__
    assert "BaselineSnapshot" in benchmark.__all__
    # The names must resolve to the same callables (not just docstrings).
    assert benchmark.compare_against_current is compare_against_current
    assert benchmark.load_baseline is load_baseline


def test_persisted_baseline_validates_against_json_schema(tmp_path: Path) -> None:
    """AC-9 + AC-4: round-trip a baseline through file → JSON Schema validator."""
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    pairs = [_pair(i + 1, primary=4, secondary=3 if i % 2 == 0 else 4) for i in range(5)]
    snapshot = _make_snapshot(alpha=0.85, verdict="trusted", pairs=pairs)
    out_path = tmp_path / "v1.json"
    _write_baseline_atomic(_serialize_baseline(snapshot), out_path)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    # Will raise jsonschema.ValidationError if shape drifts.
    jsonschema.validate(instance=payload, schema=schema)
    # Round-trips through the Pydantic loader as well (defense in depth).
    reloaded = load_baseline(out_path)
    assert reloaded.krippendorff_alpha == 0.85
    assert reloaded.verdict == "trusted"
    assert len(reloaded.per_anchor_scores) == 5


def test_persisted_per_anchor_scores_sorted_by_anchor_id(tmp_path: Path) -> None:
    """AC-9 diff-friendliness: per_anchor_scores ordering is anchor_id ascending."""
    # Pass pairs in deliberately shuffled order.
    pairs = [
        _pair(7, primary=4, secondary=4),
        _pair(2, primary=3, secondary=4),
        _pair(11, primary=5, secondary=3),
        _pair(1, primary=2, secondary=2),
    ]
    snapshot = _make_snapshot(alpha=0.8, verdict="trusted", pairs=pairs)
    out_path = tmp_path / "v1.json"
    _write_baseline_atomic(_serialize_baseline(snapshot), out_path)
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    ids = [row["anchor_id"] for row in payload["per_anchor_scores"]]
    assert ids == sorted(ids)


def test_compare_against_current_identical_baselines_no_drift(tmp_path: Path) -> None:
    """Byte-identical baselines → alpha_delta=0, verdict_changed=False, no drift."""
    pairs = [_pair(i + 1, primary=4, secondary=4) for i in range(5)]
    baseline = _make_snapshot(alpha=1.0, verdict="trusted", pairs=pairs)
    out_path = tmp_path / "v1.json"
    _write_baseline_atomic(_serialize_baseline(baseline), out_path)

    comparison = compare_against_current(out_path, baseline)
    assert comparison.alpha_delta == 0.0
    assert comparison.verdict_changed is False
    assert comparison.drift_detected is False
    assert comparison.per_anchor_diffs == []


def test_compare_against_current_alpha_drift_flagged(tmp_path: Path) -> None:
    """alpha_delta > 0.1 magnitude AND verdict band same → drift_detected=True."""
    pairs = [_pair(i + 1, primary=4, secondary=4) for i in range(5)]
    baseline = _make_snapshot(alpha=0.90, verdict="trusted", pairs=pairs)
    current = _make_snapshot(alpha=0.78, verdict="uncertain", pairs=pairs)
    # NOTE: alpha drift = -0.12 (> 0.1 threshold) AND verdict band changed
    # from trusted to uncertain — either condition alone is sufficient.
    out_path = tmp_path / "v1.json"
    _write_baseline_atomic(_serialize_baseline(baseline), out_path)
    comparison = compare_against_current(out_path, current)
    assert abs(comparison.alpha_delta - (-0.12)) < 1e-9
    assert comparison.verdict_changed is True
    assert comparison.drift_detected is True


def test_compare_against_current_per_anchor_diffs_recorded(tmp_path: Path) -> None:
    """Anchors whose scores changed between baseline + current appear in diffs."""
    baseline_pairs = [_pair(i + 1, primary=4, secondary=4) for i in range(3)]
    current_pairs = [
        _pair(1, primary=4, secondary=4),  # unchanged
        _pair(2, primary=5, secondary=3),  # both moved
        _pair(3, primary=4, secondary=4),  # unchanged
    ]
    baseline = _make_snapshot(alpha=0.95, verdict="trusted", pairs=baseline_pairs)
    current = _make_snapshot(alpha=0.93, verdict="trusted", pairs=current_pairs)
    out_path = tmp_path / "v1.json"
    _write_baseline_atomic(_serialize_baseline(baseline), out_path)
    comparison = compare_against_current(out_path, current)
    # Only one anchor changed: anchor-summary_short-002.
    assert len(comparison.per_anchor_diffs) == 1
    d = comparison.per_anchor_diffs[0]
    assert d.anchor_id == "anchor-summary_short-002"
    assert d.baseline_primary == 4
    assert d.current_primary == 5
    assert d.baseline_secondary == 4
    assert d.current_secondary == 3
    # alpha_delta = -0.02 → below threshold; verdict unchanged → no drift.
    assert comparison.drift_detected is False


def test_compare_against_current_anchor_set_drift_sentinels(tmp_path: Path) -> None:
    """Anchors missing from one side surface with -1 sentinel scores."""
    baseline_pairs = [_pair(i + 1, primary=4, secondary=4) for i in range(3)]
    current_pairs = [
        _pair(1, primary=4, secondary=4),
        _pair(4, primary=3, secondary=3),  # new anchor not in baseline
    ]
    baseline = _make_snapshot(alpha=0.95, verdict="trusted", pairs=baseline_pairs)
    current = _make_snapshot(alpha=0.95, verdict="trusted", pairs=current_pairs)
    out_path = tmp_path / "v1.json"
    _write_baseline_atomic(_serialize_baseline(baseline), out_path)
    comparison = compare_against_current(out_path, current)
    diffs_by_id = {d.anchor_id: d for d in comparison.per_anchor_diffs}
    # anchor-summary_short-002 missing from current → sentinel current_* = -1.
    assert "anchor-summary_short-002" in diffs_by_id
    assert diffs_by_id["anchor-summary_short-002"].current_primary == -1
    # anchor-summary_short-004 missing from baseline → sentinel baseline_* = -1.
    assert "anchor-summary_short-004" in diffs_by_id
    assert diffs_by_id["anchor-summary_short-004"].baseline_primary == -1


def test_load_baseline_raises_on_missing_file(tmp_path: Path) -> None:
    """Fail-loud on absent baseline (silently defaulting would defeat drift detection)."""
    with pytest.raises(FileNotFoundError):
        load_baseline(tmp_path / "does-not-exist.json")


def test_load_baseline_raises_on_schema_violation(tmp_path: Path) -> None:
    """Required-field missing → ValueError chained from Pydantic."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "baseline_date": "2026-06-28",
                "primary_evaluator": "opus",
                "secondary_evaluator": "sonnet",
                # anchors_version missing → Pydantic should reject.
                "per_anchor_scores": [
                    {
                        "anchor_id": "x",
                        "task": "summary_short",
                        "primary_score": 3,
                        "secondary_score": 3,
                        "delta": 0,
                    }
                ],
                "krippendorff_alpha": 0.9,
                "verdict": "trusted",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema validation failed"):
        load_baseline(bad)
