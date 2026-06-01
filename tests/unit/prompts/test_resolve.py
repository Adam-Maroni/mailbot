"""Unit tests for mailbot_api/prompts/__init__.py:resolve_prompt (Story 2-4 AC-3)."""

from __future__ import annotations

import sys

import pytest

from mailbot_api.prompts import PromptResolutionError, resolve_prompt


def test_resolve_prompt_loads_coarse_class_v1() -> None:
    module = resolve_prompt("coarse_class", "v1")
    assert isinstance(module.system, str)
    assert isinstance(module.user_template, str)
    assert hasattr(module.output_schema, "model_validate_json")


def test_resolve_prompt_missing_module_raises() -> None:
    with pytest.raises(PromptResolutionError, match="prompt module not found"):
        resolve_prompt("nonexistent_task", "v1")


def test_resolve_prompt_does_not_wedge_on_failed_import() -> None:
    """Story 2-4 review fix MEDIUM regression: a failed import must NOT
    leave a negative-cache entry in sys.modules. A subsequent call for
    the SAME path must re-attempt the import."""
    failing_path = "mailbot_api.prompts.nonexistent_task.v1"
    # Pre-condition: the bad path is not yet in sys.modules.
    assert failing_path not in sys.modules

    # First call: fails.
    with pytest.raises(PromptResolutionError):
        resolve_prompt("nonexistent_task", "v1")

    # The negative-cache entry must have been popped — sys.modules should
    # NOT contain the failed path.
    assert failing_path not in sys.modules

    # A second call also fails (because the module still doesn't exist),
    # but it must re-attempt the import — not return the cached failure.
    with pytest.raises(PromptResolutionError):
        resolve_prompt("nonexistent_task", "v1")
    assert failing_path not in sys.modules
