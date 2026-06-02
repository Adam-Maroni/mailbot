"""Story 5-5 AC-4 — structural offline tests for the three Hermes persona
files (SOUL.md, AGENTS.md, skills/mailbot/SKILL.md).

These tests verify the files exist, contain the load-bearing markers from the
AC text, enumerate the documented surfaces (Rules J/N/P/R, 11 verbs, the
ask_router non-exposure note), and carry no embedded secrets. They do NOT
exercise Hermes's loader — that's a Phase 3.5 manual-verification surface.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HERMES_CONFIG = _REPO_ROOT / "hermes-config"
_SOUL = _HERMES_CONFIG / "SOUL.md"
_AGENTS = _HERMES_CONFIG / "AGENTS.md"
_SKILL = _HERMES_CONFIG / "skills" / "mailbot" / "SKILL.md"


_ELEVEN_VERBS = (
    "find_emails",
    "hydrate_email",
    "get_thread",
    "count_emails",
    "get_sender_summary",
    "propose_action",
    "mint_grant",
    "revoke_grant",
    "cancel_action",
    "revert_action",
    "mint_sensitivity_token",
)

_SECRET_LIKE_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b[A-Z][A-Za-z0-9]{22,}\.[A-Za-z0-9]{6}\.[A-Za-z0-9_-]{27}"),
)


def test_three_persona_files_exist() -> None:
    """AC-4: all three files exist at the expected paths."""
    assert _SOUL.exists(), f"missing {_SOUL}"
    assert _AGENTS.exists(), f"missing {_AGENTS}"
    assert _SKILL.exists(), f"missing {_SKILL}"


def test_soul_md_carries_load_bearing_identity_markers() -> None:
    """AC-4: SOUL.md contains the defender identity sentence, all 4 banned
    anti-patterns by label, and the quiet-bias section."""
    text = _SOUL.read_text(encoding="utf-8")
    assert "defender of your attention" in text, "missing identity sentence"
    for n in (1, 2, 3, 4):
        assert f"Banned anti-pattern {n}:" in text, f"missing 'Banned anti-pattern {n}:' label"
    assert "Quiet bias" in text, "missing 'Quiet bias' section header"


def test_agents_md_documents_all_four_rules_and_tiebreaker() -> None:
    """AC-4: AGENTS.md has imperative-voice section headers for Rules J/N/P/R
    and the closing 'When in doubt, choose the quieter option' tiebreaker."""
    text = _AGENTS.read_text(encoding="utf-8")
    assert "Rule J — Hydration Discipline" in text, "missing Rule J header"
    assert "Rule N — Cost Discipline" in text, "missing Rule N header"
    assert "Rule P — Authorization Tiers" in text, "missing Rule P header"
    assert "Rule R — Notification Tiering" in text, "missing Rule R header"
    assert "When in doubt, choose the quieter option" in text, (
        "missing tiebreaker section"
    )


@pytest.mark.parametrize("verb", _ELEVEN_VERBS)
def test_skill_md_enumerates_each_of_the_11_mcp_verbs(verb: str) -> None:
    """AC-4: SKILL.md names each of the 11 MCP verbs from Story 5-2."""
    text = _SKILL.read_text(encoding="utf-8")
    assert verb in text, f"SKILL.md missing verb name: {verb}"


def test_skill_md_calls_out_ask_router_not_mcp_exposed() -> None:
    """AC-4: SKILL.md explicitly calls out that ask_router is NOT MCP-exposed
    (so a future agent doesn't try to invoke it as a tool) AND includes the
    two explicit warnings about sensitive + confidential emails from AC-3."""
    text = _SKILL.read_text(encoding="utf-8")
    assert "ask_router` is intentionally NOT MCP-exposed" in text or (
        "ask_router" in text and "NOT MCP-exposed" in text
    ), "SKILL.md must explicitly call out ask_router non-exposure"

    # Sensitive-email warning: mint_sensitivity_token must precede draft_reply.
    assert "mint_sensitivity_token" in text and "confirmation_token" in text, (
        "SKILL.md must document the sensitive-email mint_sensitivity_token handshake"
    )

    # Confidential-email warning: defender-toned refusal.
    assert "Confidential emails admit no API override" in text, (
        "SKILL.md must include the confidential-email refusal message"
    )


@pytest.mark.parametrize("file_path", [_SOUL, _AGENTS, _SKILL])
def test_persona_files_have_no_embedded_secrets(file_path: Path) -> None:
    """AC-4: none of the three files contains a real-looking secret. Catches
    accidental copy-paste of a key or token into the persona docs."""
    text = file_path.read_text(encoding="utf-8")
    for pattern in _SECRET_LIKE_PATTERNS:
        match = pattern.search(text)
        assert match is None, (
            f"{file_path.name}: secret-like substring detected by {pattern.pattern}; "
            f"first 12 chars: {match.group(0)[:12]!r}"
        )
