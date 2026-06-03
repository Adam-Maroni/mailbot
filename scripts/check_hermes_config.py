"""Story 6-0 — sanity-check hermes-config/config.yaml against the REAL Hermes
schema (rewritten from Story 5-4's invented schema after the Phase 3.5 F5
finding closed in Story 6-0; see
docs/external/hermes-agent/RECONCILIATION-NOTES.md).

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
from typing import Any, NoReturn

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "hermes-config" / "config.yaml"
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Env vars that MUST be non-empty before `docker compose up mailbot-hermes`.
# Empty DISCORD_ALLOWED_USERS means the bot rejects every message silently
# (per RECONCILIATION-NOTES §1.5); failing loud here is cheaper than
# debugging "bot doesn't respond" later.
_REQUIRED_ENV_VARS = ("DISCORD_BOT_TOKEN", "DISCORD_ALLOWED_USERS", "MAILBOT_ROUTER_KEY")

# Real-schema top-level keys (per docs/external/hermes-agent/RECONCILIATION-NOTES.md §1.2)
_REQUIRED_TOP_KEYS = ("model", "auxiliary", "mcp_servers", "discord")

# MailBot's required routing endpoints
_EXPECTED_BASE_URL = "http://mailbot-api:8000/v1"
_EXPECTED_MCP_URL = "http://mailbot-api:8000/mcp/"  # Story 6-6.6 F6 fix: trailing slash required

# Auxiliary task families that MUST route through mailbot-api
# (so Rule Ω end-to-end coverage holds for every LLM call Hermes makes,
# including its own helper jobs).
_EXPECTED_AUX_BLOCKS = ("compression", "title_generation")


def _fail(msg: str) -> NoReturn:
    """Print a failure line to stderr and exit 1. Never returns — the
    NoReturn annotation lets callers omit defensive `continue` after a
    `_fail()` call without losing the control-flow invariant."""
    print(f"FAIL: {msg}", file=sys.stderr)  # noqa: T201 — scripts/ may print
    sys.exit(1)


def _check_router_endpoint(
    block_name: str,
    block: Any,
    expected_base_url: str,
    model_field: str = "model",
) -> None:
    """Common shape check for any provider-style block routing through mailbot-api.

    Real Hermes schema quirk: the top-level `model:` block names the model under
    `default:`, while `auxiliary.<task>:` blocks name it under `model:`. Pass
    ``model_field="default"`` when checking the top-level block.
    """
    if not isinstance(block, dict):
        _fail(f"{block_name} must be a mapping; got {type(block).__name__}")
        return
    if block.get("provider") != "custom":
        _fail(
            f"{block_name}.provider must be 'custom' (real Hermes schema); "
            f"got {block.get('provider')!r}"
        )
    if block.get("base_url") != expected_base_url:
        _fail(
            f"{block_name}.base_url drift: expected {expected_base_url!r}, "
            f"got {block.get('base_url')!r}"
        )
    if block.get(model_field) != "hermes_aux":
        _fail(
            f"{block_name}.{model_field} drift: expected 'hermes_aux' "
            f"(policy.yaml task); got {block.get(model_field)!r}"
        )
    if block.get("api_key") != "${MAILBOT_ROUTER_KEY}":
        _fail(
            f"{block_name}.api_key must use ${{MAILBOT_ROUTER_KEY}} env-substitution "
            f"form; got {block.get('api_key')!r}"
        )


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

    # --- Story 5-4 invention guard ---
    # If anyone re-introduces the invented keys, fail loud.
    _INVENTED_TOP_KEYS = ("provider", "fallback_providers", "gateway", "mcp_clients")
    for forbidden in _INVENTED_TOP_KEYS:
        if forbidden in config:
            _fail(
                f"top-level key {forbidden!r} is from the Story 5-4 invented schema "
                f"and was dropped in Story 6-0. See "
                f"docs/external/hermes-agent/RECONCILIATION-NOTES.md §3 for the "
                f"correct shape."
            )

    # --- Main provider (model: block; named under `default:` not `model:`) ---
    _check_router_endpoint(
        "model", config["model"], _EXPECTED_BASE_URL, model_field="default"
    )

    # --- Auxiliary helper-model routing ---
    auxiliary = config["auxiliary"]
    if not isinstance(auxiliary, dict):
        _fail("auxiliary must be a mapping")
    for block_name in _EXPECTED_AUX_BLOCKS:
        block = auxiliary.get(block_name)
        if block is None:
            _fail(
                f"auxiliary.{block_name} block missing — every Hermes-internal "
                f"helper call must route through mailbot-api so the Router sees it"
            )
        _check_router_endpoint(f"auxiliary.{block_name}", block, _EXPECTED_BASE_URL)

    # --- MCP servers ---
    mcp_servers = config["mcp_servers"]
    if not isinstance(mcp_servers, dict):
        _fail("mcp_servers must be a mapping (real Hermes schema), not a list")
    mailbot_mcp = mcp_servers.get("mailbot-api")
    if not isinstance(mailbot_mcp, dict):
        _fail("mcp_servers['mailbot-api'] entry missing or not a mapping")
    elif mailbot_mcp.get("url") != _EXPECTED_MCP_URL:
        _fail(
            f"mcp_servers['mailbot-api'].url drift: expected {_EXPECTED_MCP_URL!r}, "
            f"got {mailbot_mcp.get('url')!r}"
        )
    elif not isinstance(mailbot_mcp.get("headers"), dict) or mailbot_mcp[
        "headers"
    ].get("Authorization") != "Bearer ${MAILBOT_ROUTER_KEY}":
        _fail(
            "mcp_servers['mailbot-api'].headers.Authorization must be "
            "'Bearer ${MAILBOT_ROUTER_KEY}' for MCP-level auth"
        )

    # --- Discord block ---
    discord = config["discord"]
    if not isinstance(discord, dict):
        _fail("discord must be a mapping (top-level, not under gateway:)")
    # require_mention is the most operationally significant flag — default
    # must be set explicitly so a future config edit can't silently flip it.
    if "require_mention" not in discord:
        _fail("discord.require_mention must be set explicitly (true or false)")
    if "allow_mentions" not in discord:
        _fail("discord.allow_mentions block missing")

    # No bot_token / intents / slash_commands in config — they're env-var-driven
    # or runtime-registered per the real Hermes contract.
    _DISCORD_INVENTED_KEYS = ("bot_token", "intents", "slash_commands")
    for forbidden in _DISCORD_INVENTED_KEYS:
        if forbidden in discord:
            _fail(
                f"discord.{forbidden} is from the Story 5-4 invented schema "
                f"and was dropped in Story 6-0. See RECONCILIATION-NOTES.md §1.4, §1.5."
            )

    # --- .env presence + required-vars guard ---
    # Best-effort: parse .env and warn (not fail) on missing/empty required
    # vars. Story 6-0 review CR-6: surface DISCORD_ALLOWED_USERS empty-string
    # silent failure before `docker compose up` rather than after the bot
    # rejects every message.
    if _ENV_PATH.exists():
        env_lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
        env_map: dict[str, str] = {}
        for raw in env_lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_map[key.strip()] = value.strip()
        missing = [v for v in _REQUIRED_ENV_VARS if not env_map.get(v)]
        if missing:
            # WARN (not _fail) — config-shape is fine, but operator must
            # populate .env before stack-up. Exit 0 still — the verifier's
            # primary job is config-shape correctness.
            print(  # noqa: T201
                f"WARN: .env missing or empty for: {', '.join(missing)} — "
                f"mailbot-hermes will start but Discord will reject all messages "
                f"(see RECONCILIATION-NOTES §1.5).",
                file=sys.stderr,
            )
    else:
        print(  # noqa: T201
            f"WARN: .env not found at {_ENV_PATH} — "
            f"required vars cannot be checked. Copy .env.example to .env "
            f"and populate before `docker compose up`.",
            file=sys.stderr,
        )

    print("OK: hermes-config/config.yaml shape verified against real Hermes schema.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
