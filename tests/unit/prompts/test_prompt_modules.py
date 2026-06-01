"""Story 3-2 AC-8: parametrized test that every ingest-task prompt module
loads cleanly via the AR-PAT-5 registry, and that each OUTPUT_SCHEMA validates
its known-good payload.

Covers the six ingest tasks introduced or updated by Story 3-2:
  - sensitivity_class (new)
  - coarse_class (replaced — 6 labels, class_coarse field)
  - fine_class (new)
  - summary_short (new)
  - importance_scoring (new)
  - action_extraction (new)
"""

from __future__ import annotations

import sys
import types

import pytest
from pydantic import BaseModel

from mailbot_api.prompts import PromptResolutionError, resolve_prompt

_INGEST_TASK_TYPES = (
    "sensitivity_class",
    "coarse_class",
    "fine_class",
    "summary_short",
    "importance_scoring",
    "action_extraction",
)


@pytest.mark.parametrize("task_type", _INGEST_TASK_TYPES)
def test_ingest_prompt_module_resolves_cleanly(task_type: str) -> None:
    """AC-8: every ingest task module loads via the registry as v1."""
    module = resolve_prompt(task_type, "v1")
    assert module.version == "v1"
    assert isinstance(module.system, str) and module.system
    assert isinstance(module.user_template, str) and module.user_template
    assert isinstance(module.output_schema, type)
    assert issubclass(module.output_schema, BaseModel)


_GOOD_PAYLOADS: dict[str, dict] = {
    "sensitivity_class": {
        "sensitivity": "normal",
        "confidence": 0.85,
        "reason": "ordinary correspondence with no privacy signals",
    },
    "coarse_class": {
        "class_coarse": "newsletter",
        "confidence": 0.95,
    },
    "fine_class": {
        "class_fine": "professional",
        "confidence": 0.8,
    },
    "summary_short": {
        "summary": "Sarah confirms Friday 3pm meeting moved to Tuesday 2pm.",
    },
    "importance_scoring": {
        "importance": 42,
        "signals": ["routine_reply", "known_sender"],
    },
    "action_extraction": {
        "actions": [
            {
                "type": "deadline",
                "summary": "Submit expenses by end of week",
                "deadline_at": "2026-06-05T17:00:00Z",
            },
            {
                "type": "info_only",
                "summary": "Heads-up: office closed Monday",
                "deadline_at": None,
            },
        ],
    },
}


@pytest.mark.parametrize("task_type", _INGEST_TASK_TYPES)
def test_output_schema_validates_good_payload(task_type: str) -> None:
    """AC-8: each OUTPUT_SCHEMA accepts a known-good payload cleanly."""
    module = resolve_prompt(task_type, "v1")
    payload = _GOOD_PAYLOADS[task_type]
    instance = module.output_schema(**payload)
    assert isinstance(instance, module.output_schema)


class _FakeOut(BaseModel):
    x: str


def _build_fake_module(name: str, *, version: str | None = "v1") -> types.ModuleType:
    """Build a minimal types.ModuleType usable as a stand-in for a prompt module.

    Helper for the registry-error tests below. If `version` is None, the module
    omits the VERSION constant entirely (used to exercise the missing-VERSION path).
    """
    fake = types.ModuleType(name)
    if version is not None:
        fake.VERSION = version
    fake.SYSTEM = "s"
    fake.USER_TEMPLATE = "{x}"
    fake.OUTPUT_SCHEMA = _FakeOut
    return fake


def test_resolve_prompt_rejects_version_mismatch(monkeypatch) -> None:
    """AC-8 + AC-1: a module exporting VERSION='v2' but resolved as 'v1' raises
    with the exact mismatch message."""
    fake = _build_fake_module("mailbot_api.prompts.coarse_class.v1", version="v2")
    monkeypatch.setitem(sys.modules, "mailbot_api.prompts.coarse_class.v1", fake)
    with pytest.raises(PromptResolutionError, match="VERSION='v2' != requested 'v1'"):
        resolve_prompt("coarse_class", "v1")


def test_resolve_prompt_rejects_version_mismatch_reverse(monkeypatch) -> None:
    """AC-1 reverse direction (CR-7): a module exporting VERSION='v1' but
    resolved as 'v2' raises with the exact mismatch message. Catches the
    failure mode where a real v1 module is mis-routed via a v2 request path."""
    fake = _build_fake_module("mailbot_api.prompts.coarse_class.v2", version="v1")
    monkeypatch.setitem(sys.modules, "mailbot_api.prompts.coarse_class.v2", fake)
    with pytest.raises(PromptResolutionError, match="VERSION='v1' != requested 'v2'"):
        resolve_prompt("coarse_class", "v2")


def test_resolve_prompt_rejects_missing_version_field(monkeypatch) -> None:
    """AC-1: a module missing the VERSION constant entirely is rejected."""
    fake = _build_fake_module("mailbot_api.prompts.coarse_class.v1", version=None)
    monkeypatch.setitem(sys.modules, "mailbot_api.prompts.coarse_class.v1", fake)
    with pytest.raises(PromptResolutionError, match="VERSION must be a non-empty str"):
        resolve_prompt("coarse_class", "v1")


def test_resolve_prompt_rejects_empty_system(monkeypatch) -> None:
    """CR-1: a module with SYSTEM="" must be rejected, not silently load and
    produce empty prompts at inference time."""
    fake = _build_fake_module("mailbot_api.prompts.coarse_class.v1", version="v1")
    fake.SYSTEM = ""
    monkeypatch.setitem(sys.modules, "mailbot_api.prompts.coarse_class.v1", fake)
    with pytest.raises(PromptResolutionError, match="SYSTEM must be a non-empty str"):
        resolve_prompt("coarse_class", "v1")


def test_resolve_prompt_rejects_empty_user_template(monkeypatch) -> None:
    """CR-1: a module with USER_TEMPLATE="" must be rejected."""
    fake = _build_fake_module("mailbot_api.prompts.coarse_class.v1", version="v1")
    fake.USER_TEMPLATE = ""
    monkeypatch.setitem(sys.modules, "mailbot_api.prompts.coarse_class.v1", fake)
    with pytest.raises(PromptResolutionError, match="USER_TEMPLATE must be a non-empty str"):
        resolve_prompt("coarse_class", "v1")


def test_hermes_aux_still_loads_post_story_3_2_registry_extension() -> None:
    """Regression: Story 2-10's hermes_aux module must still load under the
    new 4-export contract (Story 3-2 patched it to add VERSION)."""
    module = resolve_prompt("hermes_aux", "v1")
    assert module.version == "v1"
    # CR-2 fix: was a tautological `"auxiliary" in lower or "auxiliary" in lower`
    # copy-paste error. Assert two distinct substrings present in the hermes_aux
    # SYSTEM block (verified in the file at hermes_aux/v1.py).
    system_lower = module.system.lower()
    assert "auxiliary" in system_lower
    assert "text-processing" in system_lower
