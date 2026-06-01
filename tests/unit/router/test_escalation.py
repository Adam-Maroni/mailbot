"""Unit tests for mailbot_api/router/escalation.py (Story 2-4 AC-4)."""

from __future__ import annotations

import pytest

from mailbot_api.router.escalation import next_tier


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("qwen2.5:3b-instruct-q4_K_M", "claude-haiku-4-5-20251001"),
        ("claude-haiku-4-5-20251001", "claude-opus-4-7"),
        ("claude-opus-4-7", None),
        ("off-chain-model", None),
        ("", None),
    ],
)
def test_next_tier(current: str, expected: str | None) -> None:
    assert next_tier(current) == expected
