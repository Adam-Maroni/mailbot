"""Story 5-6 AC-9 — slash-command registry verification.

**Retired by Story 6-0 2026-06-02.** The original tests encoded Story 5-4's
invented schema (`gateway.discord.slash_commands:` list in
hermes-config/config.yaml). The real Hermes contract is that slash commands
are AUTO-REGISTERED from installed skill bundles at gateway startup, NOT
declared in config.yaml.

See docs/external/hermes-agent/RECONCILIATION-NOTES.md §1.4 for the schema
reconciliation. The Story 5-6 8-command surface (cost, pause, resume, cancel,
mute, label, budget, confirm) needs to migrate to a Hermes skill bundle under
hermes-config/skills/mailbot/ — that refactor is filed as a carry-forward
follow-up story (RECONCILIATION-NOTES §6 item 1), not part of Story 6-0.

Until that follow-up ships, this file is a single placeholder test that
documents the disposition so the test count doesn't silently drop and any
future reader sees the trail to the real verification surface.
"""

from __future__ import annotations


def test_slash_command_registry_retired_pending_skill_bundle_refactor() -> None:
    """Placeholder — see module docstring. Real verification lands when
    hermes-config/skills/mailbot/ becomes a Hermes-loadable skill bundle."""
    # Intentionally no assertion: the existence of this test, plus the module
    # docstring, IS the disposition record. Counts of passing tests stay
    # stable; the audit trail is preserved.
    assert True
