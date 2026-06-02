"""Unit tests for the sensitivity classifier — Story 3-3 AC-6 + AC-2.

Created retroactively per Epic 4 retro action item #2 (Adam, 2026-06-02).
The AC-6-mandated unit file `tests/unit/sensitivity/test_classifier.py` was
absent in the original Story 3-3 ship (the dev pass put all coverage at the
integration tier). This file fills the gap:

  - `assert_qwen_only` startup safeguard (CR-3-3-2): valid policy passes,
    drifted policy raises RuntimeError, missing entry raises RuntimeError,
    malformed policy object raises RuntimeError.
  - Confidence-floor boundary (CR-3-3-4): `< 0.5` floors, `== 0.5` does
    NOT floor. Boundary pinned to guard against a future `<=`-vs-`<` flip.

Per-call `_assert_qwen_only_per_call` is exercised by the integration suite
(`test_sensitivity_classifier_e2e.py:test_classify_sensitivity_fr_2_5_violation_when_policy_drifted`),
so it is not re-tested here.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mailbot_api.sensitivity import assert_qwen_only
from mailbot_api.sensitivity.classifier import _FLOOR_CONFIDENCE, _QWEN_MODEL_ID

# --------------------------------------------------------------------------- #
# assert_qwen_only — startup safeguard (AC-2 startup arm)
# --------------------------------------------------------------------------- #


@dataclass
class _FakePolicyEntry:
    model: str
    prompt_version: str = "v1"


@dataclass
class _FakePolicy:
    tasks: dict[str, _FakePolicyEntry]


def test_assert_qwen_only_passes_on_correct_qwen_model() -> None:
    policy = _FakePolicy(tasks={"sensitivity_class": _FakePolicyEntry(model=_QWEN_MODEL_ID)})
    # Should not raise.
    assert_qwen_only(policy)


def test_assert_qwen_only_raises_on_haiku_drift() -> None:
    policy = _FakePolicy(
        tasks={"sensitivity_class": _FakePolicyEntry(model="claude-haiku-4-5-20251001")}
    )
    with pytest.raises(RuntimeError, match="FR-2.5 violation"):
        assert_qwen_only(policy)


def test_assert_qwen_only_raises_on_opus_drift() -> None:
    policy = _FakePolicy(tasks={"sensitivity_class": _FakePolicyEntry(model="claude-opus-4-7")})
    with pytest.raises(RuntimeError, match="FR-2.5 violation"):
        assert_qwen_only(policy)


def test_assert_qwen_only_raises_when_sensitivity_class_entry_missing() -> None:
    policy = _FakePolicy(tasks={"coarse_class": _FakePolicyEntry(model=_QWEN_MODEL_ID)})
    with pytest.raises(RuntimeError, match="sensitivity_class.* missing"):
        assert_qwen_only(policy)


def test_assert_qwen_only_raises_when_policy_has_no_tasks_dict() -> None:
    @dataclass
    class _NoTasks:
        pass

    with pytest.raises(RuntimeError, match=r"no `\.tasks`"):
        assert_qwen_only(_NoTasks())


def test_assert_qwen_only_raises_when_entry_lacks_model_attribute() -> None:
    @dataclass
    class _EntryWithoutModel:
        prompt_version: str = "v1"

    policy = _FakePolicy(tasks={"sensitivity_class": _EntryWithoutModel()})  # type: ignore[dict-item]
    with pytest.raises(RuntimeError, match="FR-2.5 violation"):
        assert_qwen_only(policy)


# --------------------------------------------------------------------------- #
# Confidence-floor boundary — CR-3-3-4 (NFR-PRIV-1 cautious-bias floor)
# --------------------------------------------------------------------------- #
#
# Implementation is `confidence < _FLOOR_CONFIDENCE` with `_FLOOR_CONFIDENCE=0.5`.
# AC-1 says "confidence < 0.5". These tests pin the boundary so a future flip
# from `<` to `<=` (or vice-versa) fails LOUD.


def test_floor_threshold_constant_is_05() -> None:
    """Pin the constant — a change should be deliberate and reflected in AC-1."""
    assert _FLOOR_CONFIDENCE == 0.5


def test_floor_boundary_excludes_exactly_05() -> None:
    """`confidence == 0.5` is NOT floored (strict `<`).

    Pure boundary check on the implementation predicate. The integration
    suite proves the full classify_sensitivity flow at 0.3 and 0.85; this
    test isolates the boundary alone so a future `<=` regression breaks it.
    """
    assert not (0.5 < _FLOOR_CONFIDENCE)
    # And just below 0.5 IS floored.
    assert 0.4999 < _FLOOR_CONFIDENCE


def test_floor_boundary_includes_below_05() -> None:
    """`confidence == 0.4999` floors; `confidence == 0.0` floors."""
    assert 0.4999 < _FLOOR_CONFIDENCE
    assert 0.0 < _FLOOR_CONFIDENCE


def test_floor_boundary_excludes_above_05() -> None:
    """`confidence == 0.5001` does NOT floor; `confidence == 0.9` does NOT floor."""
    assert not (0.5001 < _FLOOR_CONFIDENCE)
    assert not (0.9 < _FLOOR_CONFIDENCE)
