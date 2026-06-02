"""Story 5-4 AC-6 — verify docker-compose.yml's mailbot-hermes service
bind-mounts the repo's hermes-config/ directory and preserves the existing
runtime-state volume mount.

This test parses docker-compose.yml directly (no docker daemon needed) so
it can run in CI without a working Docker socket.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE_FILE = _REPO_ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    assert _COMPOSE_FILE.exists(), f"expected {_COMPOSE_FILE} to exist"
    return yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))


def test_compose_mailbot_hermes_service_exists(compose: dict[str, Any]) -> None:
    """Story 1-2 baseline guard: the mailbot-hermes service is present."""
    services = compose["services"]
    assert "mailbot-hermes" in services


def test_compose_mailbot_hermes_binds_hermes_config(compose: dict[str, Any]) -> None:
    """AC-2 / AC-6: hermes-config/ bind-mount at /opt/data.

    Story 5-4 originally specced :ro but Phase 3.5 walk surfaced that Hermes
    treats /opt/data as its HOME and needs to mkdir cron/ on first run — read-
    only mount crashes the container. Mount is now read-write; see compose
    file comment for the trade-off.
    """
    volumes = compose["services"]["mailbot-hermes"]["volumes"]
    assert isinstance(volumes, list)
    expected = "./hermes-config:/opt/data"
    assert expected in volumes, (
        f"expected {expected!r} in mailbot-hermes.volumes; got {volumes}"
    )


def test_compose_mailbot_hermes_runtime_state_mount_preserved(compose: dict[str, Any]) -> None:
    """AC-6 regression guard: the existing mailbot_hermes_data:/data mount
    is NOT removed by the bind-mount addition."""
    volumes = compose["services"]["mailbot-hermes"]["volumes"]
    runtime_state = "mailbot_hermes_data:/data"
    assert runtime_state in volumes, (
        f"runtime-state volume mount removed; expected {runtime_state!r} "
        f"to remain in mailbot-hermes.volumes; got {volumes}"
    )


def test_compose_mailbot_hermes_env_carries_router_key_and_anthropic(
    compose: dict[str, Any],
) -> None:
    """AC-2 / AC-3: the Hermes container's env block carries
    MAILBOT_ROUTER_KEY (Story 5-4 AC-1) and ANTHROPIC_API_KEY (NFR-OPS-6
    fallback)."""
    env = compose["services"]["mailbot-hermes"]["environment"]
    # Compose env can be list-of-KEY=VALUE or dict; normalize.
    if isinstance(env, list):
        keys = {entry.split("=", 1)[0] for entry in env}
    else:
        keys = set(env.keys())
    assert "MAILBOT_ROUTER_KEY" in keys
    assert "ANTHROPIC_API_KEY" in keys
