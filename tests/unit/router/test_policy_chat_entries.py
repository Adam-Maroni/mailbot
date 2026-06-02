"""Story 5-3 AC-9: verify the five chat-side policy.yaml entries match the
fail-loudly invariants table. Loads the live router/policy.yaml so drift
between epics + the shipped policy is caught at gate-sweep time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.router.policy import PolicyEntry, load_policy

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_POLICY_PATH = _PROJECT_ROOT / "router" / "policy.yaml"


@pytest.fixture(scope="module")
def policy_table():
    assert _POLICY_PATH.exists(), f"expected {_POLICY_PATH} to exist"
    return load_policy(_POLICY_PATH)


# AC-9 invariants table: each chat task's required field values.
# Note on response_cache_ttl_seconds: PolicyEntry defaults this to 0 (caching
# disabled). The AC-9 spec calls 0 "absent / null". A value of 0 is the
# authoritative no-cache signal for draft_reply / multi_turn_refinement /
# intent_parsing_chat / reference_resolution; only tone_style_mirror sets it
# explicitly to 2592000 (30 days).
_CHAT_INVARIANTS = {
    "intent_parsing_chat": {
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "prompt_version": "v1",
        "escalate": True,
        "lane": "interactive",
        "max_tokens_out": 384,
        "sensitivity": "any",
        "response_cache_ttl_seconds": 0,
    },
    "reference_resolution": {
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "prompt_version": "v1",
        "escalate": True,
        "lane": "interactive",
        "max_tokens_out": 384,
        "sensitivity": "any",
        "response_cache_ttl_seconds": 0,
    },
    "draft_reply": {
        "model": "claude-opus-4-7",
        "prompt_version": "v1",
        "escalate": False,
        "lane": "interactive",
        "max_tokens_out": 1500,
        "sensitivity": "any",
        "response_cache_ttl_seconds": 0,
    },
    "tone_style_mirror": {
        "model": "claude-opus-4-7",
        "prompt_version": "v1",
        "escalate": False,
        "lane": "interactive",
        "max_tokens_out": 512,
        "sensitivity": "any",
        "response_cache_ttl_seconds": 2592000,
    },
    "multi_turn_refinement": {
        "model": "claude-opus-4-7",
        "prompt_version": "v1",
        "escalate": False,
        "lane": "interactive",
        "max_tokens_out": 1500,
        "sensitivity": "any",
        "response_cache_ttl_seconds": 0,
    },
}


@pytest.mark.parametrize("task_type", list(_CHAT_INVARIANTS.keys()))
def test_chat_policy_entry_exists(policy_table, task_type: str) -> None:
    """AC-9: every chat task type has a policy.yaml entry."""
    assert task_type in policy_table.tasks, f"missing policy entry: {task_type}"
    assert isinstance(policy_table.tasks[task_type], PolicyEntry)


@pytest.mark.parametrize("task_type", list(_CHAT_INVARIANTS.keys()))
def test_chat_policy_entry_fields_match_invariants(policy_table, task_type: str) -> None:
    """AC-9: each chat task entry's fields match the documented invariants
    table. Drift fails loudly with a per-field message."""
    entry = policy_table.tasks[task_type]
    expected = _CHAT_INVARIANTS[task_type]
    for field, expected_value in expected.items():
        actual = getattr(entry, field)
        assert actual == expected_value, (
            f"{task_type}.{field} drifted: expected {expected_value!r}, got {actual!r}"
        )
