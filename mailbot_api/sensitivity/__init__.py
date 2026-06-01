"""Sensitivity classification + pattern-override package (Story 3-3).

Public surface:
  - `classify_sensitivity`, `SensitivityResult` (from classifier.py)
  - `load_patterns`, `PatternTable`, `PatternEntry`, `apply_pattern_override`,
    `PatternValidationError` (from patterns.py)
  - `assert_qwen_only` — startup-time FR-2.5 hard safeguard (AC-2)
"""

from __future__ import annotations

from mailbot_api.sensitivity.classifier import SensitivityResult, classify_sensitivity
from mailbot_api.sensitivity.patterns import (
    PatternEntry,
    PatternTable,
    PatternValidationError,
    apply_pattern_override,
    get_patterns,
    load_patterns,
)


def assert_qwen_only(policy: object) -> None:
    """Startup-time FR-2.5 hard safeguard.

    Called from `mailbot_api/main.py`'s FastAPI lifespan after `load_policy`
    succeeds. Verifies `policy.tasks["sensitivity_class"].model` equals the
    only acceptable Qwen model id. Raises `RuntimeError` if policy.yaml
    drifted at boot — fail-fast so the container exits cleanly and a CI
    pipeline catches the regression before traffic starts.

    Per-call enforcement lives in `classify_sensitivity` itself (handles the
    hot-reload-drift case where policy.yaml changes mid-process).
    """
    from mailbot_api.sensitivity.classifier import _QWEN_MODEL_ID

    tasks = getattr(policy, "tasks", None)
    if not isinstance(tasks, dict):
        raise RuntimeError("assert_qwen_only: policy object has no `.tasks` dict — cannot verify FR-2.5")
    entry = tasks.get("sensitivity_class")
    if entry is None:
        raise RuntimeError("assert_qwen_only: policy.tasks['sensitivity_class'] is missing — FR-2.5 requires the entry")
    model = getattr(entry, "model", None)
    if model != _QWEN_MODEL_ID:
        raise RuntimeError(
            f"assert_qwen_only: FR-2.5 violation — policy.tasks['sensitivity_class'].model "
            f"is {model!r} (expected {_QWEN_MODEL_ID!r}). Sensitivity classification "
            f"must dispatch to Qwen only. Refusing to start."
        )


__all__ = [
    "PatternEntry",
    "PatternTable",
    "PatternValidationError",
    "SensitivityResult",
    "apply_pattern_override",
    "assert_qwen_only",
    "classify_sensitivity",
    "get_patterns",
    "load_patterns",
]
