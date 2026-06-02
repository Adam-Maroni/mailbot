"""Story 5-6 AC-9 — verify the slash-command registry in hermes-config/config.yaml.

These tests parse the YAML directly; they do NOT bring up Hermes or Discord.
They catch documented drift modes (missing commands, wrong verb targets,
missing ephemeral flags on sensitive surfaces).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HERMES_CONFIG = _REPO_ROOT / "hermes-config" / "config.yaml"

# The 16 MCP tools after Story 5-6 — all 16 are valid verb targets for slash
# commands. `propose_action` is the documented target for `/label` per Story
# 5-6 AC-7.
_VALID_VERB_TARGETS = {
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
    "cost_breakdown",
    "reset_degraded_mode",
    "pause_router",
    "resume_router",
    "mute_category",
}

_REQUIRED_COMMAND_NAMES = {
    "cost",
    "pause",
    "resume",
    "cancel",
    "mute",
    "label",
    "budget",
    "confirm",
}


@pytest.fixture(scope="module")
def slash_commands() -> list[dict[str, Any]]:
    config = yaml.safe_load(_HERMES_CONFIG.read_text(encoding="utf-8"))
    return config["gateway"]["discord"]["slash_commands"]


def test_hermes_config_slash_commands_registered(slash_commands: list[dict[str, Any]]) -> None:
    """AC-9: gateway.discord.slash_commands has at least 8 entries; each has
    name + description + (verb OR subcommands)."""
    assert isinstance(slash_commands, list)
    assert len(slash_commands) >= 8
    for entry in slash_commands:
        assert "name" in entry
        assert "description" in entry
        # Either a top-level verb or a subcommands list (for /budget reset).
        assert "verb" in entry or "subcommands" in entry, (
            f"slash command {entry.get('name')!r} must have verb or subcommands"
        )


def test_hermes_config_slash_command_names(slash_commands: list[dict[str, Any]]) -> None:
    """AC-9: all 8 documented commands appear by name."""
    actual_names = {entry["name"] for entry in slash_commands}
    missing = _REQUIRED_COMMAND_NAMES - actual_names
    assert not missing, f"missing slash commands: {missing}"


def test_hermes_config_slash_command_verb_targets_resolve(
    slash_commands: list[dict[str, Any]],
) -> None:
    """AC-9: every registered slash command's `verb` is one of the 16 MCP
    tools. Drift fails loudly."""
    for entry in slash_commands:
        if "verb" in entry:
            verb = entry["verb"]
            assert verb in _VALID_VERB_TARGETS, (
                f"slash command {entry['name']!r} targets unknown verb {verb!r}; "
                f"valid targets: {sorted(_VALID_VERB_TARGETS)}"
            )
        if "subcommands" in entry:
            for sub in entry["subcommands"]:
                # CR-6: subcommand entries also need name + description + verb.
                assert "name" in sub, f"subcommand of {entry['name']} missing name"
                assert "description" in sub, (
                    f"subcommand {entry['name']}.{sub.get('name')!r} missing description"
                )
                verb = sub.get("verb")
                assert verb in _VALID_VERB_TARGETS, (
                    f"subcommand {entry['name']}.{sub['name']!r} targets unknown "
                    f"verb {verb!r}"
                )


def test_hermes_config_confirm_is_ephemeral(slash_commands: list[dict[str, Any]]) -> None:
    """AC-9: /confirm responses MUST be ephemeral so sensitivity tokens are
    not visible to other server members."""
    confirm = next(c for c in slash_commands if c["name"] == "confirm")
    assert confirm.get("ephemeral") is True, (
        "/confirm must be ephemeral — sensitivity tokens must not leak in shared channels"
    )


def test_hermes_config_cost_is_ephemeral(slash_commands: list[dict[str, Any]]) -> None:
    """AC-9: /cost responses MUST be ephemeral so cost data is not visible
    to other server members (FR-4.8 sensitivity)."""
    cost = next(c for c in slash_commands if c["name"] == "cost")
    assert cost.get("ephemeral") is True, (
        "/cost must be ephemeral — cost data is not for shared channels"
    )


def test_hermes_config_budget_reset_subcommand_is_ephemeral(
    slash_commands: list[dict[str, Any]],
) -> None:
    """AC-9: /budget reset response MUST be ephemeral — budget state is not
    for shared channels."""
    budget = next(c for c in slash_commands if c["name"] == "budget")
    subs = budget.get("subcommands", [])
    reset_sub = next((s for s in subs if s["name"] == "reset"), None)
    assert reset_sub is not None, "/budget must have reset subcommand"
    assert reset_sub.get("ephemeral") is True, (
        "/budget reset must be ephemeral — budget state is not for shared channels"
    )
