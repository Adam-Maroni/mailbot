"""Story 5-4 AC-5 — offline shape tests for hermes-config/config.yaml.

These tests parse the YAML directly; they do NOT bring up Docker, do NOT
make Discord API calls, and do NOT make Anthropic API calls. They catch
documented drift modes without any operational dependency.

Live-Discord round-trip is a Phase 3.5 manual-verification item (env-gated
on DISCORD_BOT_TOKEN + ANTHROPIC_API_KEY presence) and is not in scope here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HERMES_CONFIG = _REPO_ROOT / "hermes-config" / "config.yaml"


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    assert _HERMES_CONFIG.exists(), f"expected {_HERMES_CONFIG} to exist"
    return yaml.safe_load(_HERMES_CONFIG.read_text(encoding="utf-8"))


def test_hermes_config_yaml_parses(config: dict[str, Any]) -> None:
    """AC-5: file parses + has the documented top-level shape."""
    assert isinstance(config, dict)
    for key in ("provider", "auxiliary", "fallback_providers", "gateway", "mcp_clients"):
        assert key in config, f"missing top-level key: {key}"


def test_hermes_config_provider_block(config: dict[str, Any]) -> None:
    """AC-5: provider block points at mailbot-api with the hermes_aux alias."""
    provider = config["provider"]
    assert provider["base_url"] == "http://mailbot-api:8000/v1"
    assert provider["model"] == "hermes_aux"
    assert provider["api_key"] == "${MAILBOT_ROUTER_KEY}"


def test_hermes_config_auxiliary_caller_origins(config: dict[str, Any]) -> None:
    """AC-5: auxiliary.compression + .title_generation set the exact
    X-Mailbot-Caller-Origin header values Story 2-10 propagates into
    router_calls. Drift breaks cost-attribution accuracy."""
    aux = config["auxiliary"]

    compression = aux["compression"]
    assert compression["provider"] == "custom"
    assert compression["base_url"] == "http://mailbot-api:8000/v1"
    assert compression["headers"]["X-Mailbot-Caller-Origin"] == "hermes-aux-compression"

    title_gen = aux["title_generation"]
    assert title_gen["provider"] == "custom"
    assert title_gen["base_url"] == "http://mailbot-api:8000/v1"
    assert title_gen["headers"]["X-Mailbot-Caller-Origin"] == "hermes-aux-title"


def test_hermes_config_mcp_clients_points_at_mailbot_api_mcp(config: dict[str, Any]) -> None:
    """AC-5: at least one mcp_clients entry points at mailbot-api's /mcp."""
    clients = config["mcp_clients"]
    assert isinstance(clients, list) and clients
    matching = [c for c in clients if c.get("url") == "http://mailbot-api:8000/mcp"]
    assert matching, f"no mcp_clients entry pointing at /mcp; got {clients}"
    assert matching[0]["transport"] == "streamable_http"


def test_hermes_config_discord_intents_minimal(config: dict[str, Any]) -> None:
    """AC-5: gateway.discord.intents has at least the four required intents."""
    discord = config["gateway"]["discord"]
    intents = discord["intents"]
    assert isinstance(intents, list)
    required = {"DIRECT_MESSAGES", "MESSAGE_CONTENT", "GUILDS", "GUILD_MESSAGES"}
    assert required.issubset(set(intents)), (
        f"missing required Discord intents: {required - set(intents)}"
    )


def test_hermes_config_fallback_emergency_only(config: dict[str, Any]) -> None:
    """AC-5: exactly one fallback_providers entry pointing at api.anthropic.com
    with Opus per NFR-OPS-6."""
    fallbacks = config["fallback_providers"]
    assert isinstance(fallbacks, list)
    assert len(fallbacks) == 1, f"expected 1 fallback entry; got {len(fallbacks)}"
    entry = fallbacks[0]
    assert entry["provider"] == "anthropic"
    assert entry["base_url"] == "https://api.anthropic.com"
    assert entry["model"] == "claude-opus-4-7"
    assert entry["api_key"] == "${ANTHROPIC_API_KEY}"


# Patterns that smell like hard-coded secrets — none should appear anywhere
# in the rendered config.yaml text. Compiled once at module load.
_SECRET_LIKE_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),  # Anthropic key
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),  # OpenAI / generic
    # Discord bot tokens: prefix MT[A-Z]... — match a long base64-ish chunk.
    # The literal env-substitution string ${DISCORD_BOT_TOKEN} should pass.
    re.compile(r"\b[A-Z][A-Za-z0-9]{22,}\.[A-Za-z0-9]{6}\.[A-Za-z0-9_-]{27}"),
)


def test_hermes_config_no_hardcoded_secrets() -> None:
    """AC-5: no real-looking secret appears in the file. Every secret-bearing
    field uses the ${ENV_VAR} substitution form."""
    raw_text = _HERMES_CONFIG.read_text(encoding="utf-8")
    for pattern in _SECRET_LIKE_PATTERNS:
        match = pattern.search(raw_text)
        assert match is None, (
            f"secret-like substring detected: {pattern.pattern}; "
            f"matched text starts with {match.group(0)[:12]!r}…"
        )
