"""Story 5-4 AC-4 — sanity-check hermes-config/config.yaml without bringing
the Docker stack up.

Catches drift in the Hermes config shape that would otherwise only surface
when the live container fails to start. Run before any `docker compose up`
that touches the Hermes service.

Usage:
    python scripts/check_hermes_config.py

Exit code 0 on success; 1 on any assertion failure (with a one-line message).
Stdlib-only (no Pydantic, no httpx) so it works in a fresh venv.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "hermes-config" / "config.yaml"

_REQUIRED_TOP_KEYS = ("provider", "auxiliary", "fallback_providers", "gateway", "mcp_clients")
_EXPECTED_BASE_URL = "http://mailbot-api:8000/v1"
_EXPECTED_MCP_URL = "http://mailbot-api:8000/mcp"
_EXPECTED_AUX_BLOCKS = {
    "compression": "hermes-aux-compression",
    "title_generation": "hermes-aux-title",
}


def _fail(msg: str) -> None:
    """Print a failure line to stderr and exit 1."""
    print(f"FAIL: {msg}", file=sys.stderr)  # noqa: T201 — scripts/ may print
    sys.exit(1)


def main() -> int:
    if not _CONFIG_PATH.exists():
        _fail(f"hermes-config/config.yaml not found at {_CONFIG_PATH}")

    try:
        raw_text = _CONFIG_PATH.read_text(encoding="utf-8")
        config: Any = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        _fail(f"YAML parse failed: {exc}")
        return 1  # unreachable; for type-checkers
    except OSError as exc:
        _fail(f"OS error reading config: {exc}")
        return 1

    if not isinstance(config, dict):
        _fail(f"top-level must be a mapping; got {type(config).__name__}")
        return 1

    for key in _REQUIRED_TOP_KEYS:
        if key not in config:
            _fail(f"missing required top-level key: {key}")

    provider = config["provider"]
    if not isinstance(provider, dict):
        _fail("provider must be a mapping")
    if provider.get("base_url") != _EXPECTED_BASE_URL:
        _fail(
            f"provider.base_url drift: expected {_EXPECTED_BASE_URL!r}, "
            f"got {provider.get('base_url')!r}"
        )
    if provider.get("model") != "hermes_aux":
        _fail(f"provider.model drift: expected 'hermes_aux', got {provider.get('model')!r}")
    if provider.get("api_key") != "${MAILBOT_ROUTER_KEY}":
        _fail(
            "provider.api_key must use ${MAILBOT_ROUTER_KEY} env-substitution "
            f"form; got {provider.get('api_key')!r}"
        )

    auxiliary = config["auxiliary"]
    if not isinstance(auxiliary, dict):
        _fail("auxiliary must be a mapping")
    for block_name, expected_origin in _EXPECTED_AUX_BLOCKS.items():
        block = auxiliary.get(block_name)
        if not isinstance(block, dict):
            _fail(f"auxiliary.{block_name} must be a mapping; got {type(block).__name__}")
            continue
        if block.get("provider") != "custom":
            _fail(
                f"auxiliary.{block_name}.provider must be 'custom'; "
                f"got {block.get('provider')!r}"
            )
        headers = block.get("headers", {})
        if not isinstance(headers, dict):
            _fail(f"auxiliary.{block_name}.headers must be a mapping")
            continue
        actual_origin = headers.get("X-Mailbot-Caller-Origin")
        if actual_origin != expected_origin:
            _fail(
                f"auxiliary.{block_name}.headers.X-Mailbot-Caller-Origin drift: "
                f"expected {expected_origin!r}, got {actual_origin!r}"
            )

    mcp_clients = config["mcp_clients"]
    if not isinstance(mcp_clients, list) or not mcp_clients:
        _fail("mcp_clients must be a non-empty list")
    found_mailbot_mcp = any(
        isinstance(c, dict) and c.get("url") == _EXPECTED_MCP_URL for c in mcp_clients
    )
    if not found_mailbot_mcp:
        _fail(f"mcp_clients must include an entry with url={_EXPECTED_MCP_URL!r}")

    gateway = config["gateway"]
    if not isinstance(gateway, dict) or "discord" not in gateway:
        _fail("gateway.discord block missing")
    discord = gateway["discord"]
    if discord.get("bot_token") != "${DISCORD_BOT_TOKEN}":
        _fail(
            "gateway.discord.bot_token must use ${DISCORD_BOT_TOKEN} env-substitution "
            f"form (not a hard-coded secret); got {discord.get('bot_token')!r}"
        )

    print("OK: hermes-config/config.yaml shape verified.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
