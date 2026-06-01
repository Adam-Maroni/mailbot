"""Unit tests for mailbot_api/router/policy.py loader + schema (Story 2-2 AC-10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.router.policy import (
    PolicyEntry,
    PolicyTable,
    PolicyValidationError,
    load_policy,
)

_VALID_POLICY = """\
version: "test-v1"

tasks:
  coarse_class:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  draft_reply:
    model: "claude-opus-4-7"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1500
    lane: "interactive"
    sensitivity: "any"
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_policy_happy_path(tmp_path: Path) -> None:
    p = _write(tmp_path, _VALID_POLICY)
    table = load_policy(p)
    assert isinstance(table, PolicyTable)
    assert table.version == "test-v1"
    assert set(table.tasks.keys()) == {"coarse_class", "draft_reply"}
    assert isinstance(table.tasks["coarse_class"], PolicyEntry)
    assert table.tasks["coarse_class"].lane == "batch"
    assert table.tasks["draft_reply"].lane == "interactive"


def test_load_policy_loads_project_root_starter() -> None:
    """The shipped router/policy.yaml at the project root must parse cleanly."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    policy_path = repo_root / "router" / "policy.yaml"
    assert policy_path.exists(), f"Expected {policy_path} to exist"
    table = load_policy(policy_path)
    assert len(table.tasks) >= 3
    assert "coarse_class" in table.tasks
    assert "sensitivity_class" in table.tasks
    assert "draft_reply" in table.tasks


def test_load_policy_file_not_found(tmp_path: Path) -> None:
    p = tmp_path / "missing.yaml"
    with pytest.raises(PolicyValidationError) as ei:
        load_policy(p)
    assert "policy file not found" in ei.value.details


def test_load_policy_malformed_yaml(tmp_path: Path) -> None:
    p = _write(tmp_path, "::: not yaml :::\n- random\n  : nope")
    with pytest.raises(PolicyValidationError) as ei:
        load_policy(p)
    assert "YAML parse failed" in ei.value.details


def test_load_policy_top_level_not_mapping(tmp_path: Path) -> None:
    p = _write(tmp_path, "- just a list\n- of items\n")
    with pytest.raises(PolicyValidationError) as ei:
        load_policy(p)
    assert "must be a mapping" in ei.value.details


def test_load_policy_missing_required_task_field(tmp_path: Path) -> None:
    bad = _VALID_POLICY.replace(
        '    model: "qwen2.5:3b-instruct-q4_K_M"\n    prompt_version: "v1"\n',
        '    prompt_version: "v1"\n',
        1,
    )
    p = _write(tmp_path, bad)
    with pytest.raises(PolicyValidationError):
        load_policy(p)


def test_load_policy_extra_top_level_key_rejected(tmp_path: Path) -> None:
    """extra='forbid' should fail on a typo like versions: instead of version:."""
    bad = _VALID_POLICY + 'versions: "typo"\n'
    p = _write(tmp_path, bad)
    with pytest.raises(PolicyValidationError):
        load_policy(p)


def test_load_policy_invalid_lane(tmp_path: Path) -> None:
    bad = _VALID_POLICY.replace('lane: "batch"', 'lane: "triage"', 1)
    p = _write(tmp_path, bad)
    with pytest.raises(PolicyValidationError):
        load_policy(p)


def test_load_policy_invalid_sensitivity(tmp_path: Path) -> None:
    bad = _VALID_POLICY.replace('sensitivity: "any"', 'sensitivity: "PRIVATE"', 1)
    p = _write(tmp_path, bad)
    with pytest.raises(PolicyValidationError):
        load_policy(p)


def test_policy_entry_extra_field_rejected() -> None:
    with pytest.raises(Exception):  # ValidationError surface
        PolicyEntry.model_validate(
            {
                "model": "x",
                "prompt_version": "v1",
                "escalate": False,
                "lane": "batch",
                "sensitivity": "any",
                "unknown_field": "bogus",
            }
        )


def test_policy_entry_default_max_tokens_out() -> None:
    entry = PolicyEntry.model_validate(
        {
            "model": "x",
            "prompt_version": "v1",
            "escalate": False,
            "lane": "batch",
            "sensitivity": "any",
        }
    )
    assert entry.max_tokens_out == 4000


def test_policy_validation_error_str_format() -> None:
    err = PolicyValidationError("something broke")
    assert str(err) == "PolicyValidationError: something broke"
    assert err.details == "something broke"
