"""Story 6-0 — offline shape tests for hermes-config/config.yaml against the
REAL Hermes schema (rewritten in Story 6-0 to close F5; see
docs/external/hermes-agent/RECONCILIATION-NOTES.md).

These tests parse the YAML directly; they do NOT bring up Docker, do NOT
make Discord API calls, and do NOT make Anthropic API calls. They catch
documented drift modes without any operational dependency.

Live-Discord round-trip is a Phase 3.5 manual-verification item (env-gated
on DISCORD_BOT_TOKEN + ANTHROPIC_API_KEY presence) and is not in scope here.

Previous version of this file encoded Story 5-4's invented schema (top-level
`provider:`, `fallback_providers:`, `gateway.discord.*`, `mcp_clients:`).
The rewrite tracks the real schema docs:
  https://hermes-agent.nousresearch.com/docs/user-guide/configuration
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


def test_hermes_config_yaml_parses_with_real_schema(config: dict[str, Any]) -> None:
    """File parses + has the real top-level shape (model / auxiliary /
    mcp_servers / discord). The Story 5-4 invented top-level keys
    (provider / fallback_providers / gateway / mcp_clients) MUST be absent."""
    assert isinstance(config, dict)
    for key in ("model", "auxiliary", "mcp_servers", "discord"):
        assert key in config, f"missing real-schema top-level key: {key}"
    for forbidden in ("provider", "fallback_providers", "gateway", "mcp_clients"):
        assert forbidden not in config, (
            f"invented top-level key {forbidden!r} must not reappear "
            f"(see RECONCILIATION-NOTES §3)"
        )


def test_hermes_config_model_block(config: dict[str, Any]) -> None:
    """The main `model:` block points at mailbot-api with provider='custom'
    and the hermes_aux task alias."""
    model = config["model"]
    assert model["provider"] == "custom"
    assert model["base_url"] == "http://mailbot-api:8000/v1"
    assert model["default"] == "hermes_aux"
    assert model["api_key"] == "${MAILBOT_ROUTER_KEY}"


def test_hermes_config_auxiliary_routes_through_mailbot_api(
    config: dict[str, Any],
) -> None:
    """Both `auxiliary.compression` and `auxiliary.title_generation` route
    through mailbot-api so the Router sees every Hermes-internal LLM call
    (Rule Ω end-to-end). caller_origin granularity is lost via this
    surface (see RECONCILIATION-NOTES §1.6) — that's a known follow-up,
    not a regression."""
    aux = config["auxiliary"]
    for block_name in ("compression", "title_generation"):
        block = aux[block_name]
        assert block["provider"] == "custom"
        assert block["base_url"] == "http://mailbot-api:8000/v1"
        assert block["model"] == "hermes_aux"
        assert block["api_key"] == "${MAILBOT_ROUTER_KEY}"
        # Invented `headers:` key must NOT reappear — the real schema
        # has no documented per-auxiliary header propagation.
        assert "headers" not in block, (
            f"auxiliary.{block_name}.headers not supported in real schema; "
            f"see RECONCILIATION-NOTES §1.6"
        )


def test_hermes_config_mcp_servers_mapping_with_mailbot_api(
    config: dict[str, Any],
) -> None:
    """`mcp_servers` is a MAPPING keyed by server name (not a list of dicts
    like the invented `mcp_clients`). The mailbot-api entry points at /mcp/
    (trailing slash per Story 6-6.6 F6 fix) with bearer-auth headers."""
    mcp_servers = config["mcp_servers"]
    assert isinstance(mcp_servers, dict)
    mailbot_api = mcp_servers["mailbot-api"]
    # Story 6-6.6 F6 closure: URL has trailing slash. The original Story 6-0
    # rewrite used `/mcp` without the slash; the 6-0 walk surfaced F6 (POST
    # /mcp → 307 → 404 because FastAPI Mount needs the trailing slash AND
    # FastMCP's inner-route default doubled the path). The paired server-
    # side fix in `build_mcp_server` sets `streamable_http_path="/"`.
    assert mailbot_api["url"] == "http://mailbot-api:8000/mcp/"
    assert isinstance(mailbot_api.get("headers"), dict)
    assert mailbot_api["headers"]["Authorization"] == "Bearer ${MAILBOT_ROUTER_KEY}"
    # The invented `transport: streamable_http` field must NOT reappear —
    # the real schema makes HTTP transport implicit when `url:` is present.
    assert "transport" not in mailbot_api


def test_hermes_config_discord_at_top_level_not_under_gateway(
    config: dict[str, Any],
) -> None:
    """The Discord block lives at the top level (real schema), NOT under
    `gateway:` (the Story 5-4 invention). Intents are NOT in config and
    bot_token is env-driven, not file-driven."""
    discord = config["discord"]
    assert isinstance(discord, dict)
    # require_mention explicit (operational safety — single-user deploy
    # defaults to false so Adam's DMs work without an @mention).
    assert "require_mention" in discord
    # The behaviorally significant defaults are explicitly declared.
    assert "allow_mentions" in discord
    assert isinstance(discord["allow_mentions"], dict)
    # These keys MUST NOT reappear in config (real Hermes contract):
    for forbidden in ("bot_token", "intents", "slash_commands"):
        assert forbidden not in discord, (
            f"discord.{forbidden} was a Story 5-4 invention; real Hermes "
            f"manages it elsewhere (env vars / runtime registration / Discord "
            f"Developer Portal); see RECONCILIATION-NOTES §1.4, §1.5"
        )


# --- Story 10-6-5: per-turn tool-surface fidelity (WALK-10-6-4-F1) ----------
#
# The Discord chat surface was polluted by unrelated user-installed Hermes
# toolsets (tts / image_gen / vision / file / todo / …), so a real "find my
# unread emails" turn ran on qwen but emitted tool_calls_count=0 — the 26
# registered mailbot-api MCP verbs were drowned. The fix is a repo-tracked
# `platform_toolsets.discord` allow-list in config.yaml that keeps only the
# toolsets a MailBot email turn needs + the mailbot-api MCP server, so the
# email verbs dominate the surface. These are offline YAML-shape drift gates
# (no Docker/Discord/Anthropic dependency) that red-gate a re-pollution
# regression. AC-1/AC-6 live-Discord proof is a Phase 3.5 manual item.

# Toolsets that must NOT be on the Discord surface — the exact noise
# WALK-10-6-4-F1 observed qwen enumerate ("TTS / task / image / write-file"),
# PLUS `skills` (added after the 10-6-5 AC-1 live walk). The `skills` toolset
# resolves the installed 88-skill catalog's tools onto the turn surface at
# runtime (incl. a competing `gmail_get_unread_emails`); on "find my unread
# emails" qwen picked that over the MailBot `find_emails` verb (router_calls
# id=14913/14914, tool_calls_count=1, wrong tool). It is a distinct pollution
# channel from the built-in toolsets and must stay OFF Discord so the
# mailbot-api MCP verbs are the dominant email surface.
_NOISE_TOOLSETS_FORBIDDEN_ON_DISCORD = frozenset(
    {
        "tts",
        "image_gen",
        "vision",
        "video",
        "file",
        "browser",
        "terminal",
        "code_execution",
        "web",
        "todo",
        "delegation",
        "computer_use",
        "skills",
    }
)

# The minimal keep-set a MailBot email turn actually needs.
_REQUIRED_DISCORD_TOOLSETS = frozenset(
    {
        "mailbot-api",  # the 26 email verbs — the whole point (MCP server name)
        "messaging",  # Rule R cross-platform notification send
        "cronjob",  # Story 6-10 digest / notification-pull jobs
        "memory",  # defender-persona session hygiene
        "clarify",  # AGENTS.md "ask for clarification" tiebreaker
    }
)


def _discord_allowlist(config: dict[str, Any]) -> list[str]:
    """Resolve `platform_toolsets.discord` with descriptive failures.

    CR-10-6-5-2 / CR-10-6-5-3 (reviewer sonnet-5): the three drift gates below
    previously indexed `config["platform_toolsets"]["discord"]` directly, which
    raised a bare `KeyError` when the block regressed to absent (obscuring the
    real regression during triage) and silently char-iterated when the value
    was authored as a YAML scalar/string instead of a list (`set("a,b")`
    produces a misleading missing/leaked diff instead of a clear type error).
    This helper turns both into descriptive AssertionErrors."""
    platform_toolsets = config.get("platform_toolsets")
    assert isinstance(platform_toolsets, dict), (
        "config.platform_toolsets must be a mapping keyed by platform "
        "(WALK-10-6-4-F1 tool-surface fidelity fix); got "
        f"{type(platform_toolsets).__name__}"
    )
    discord_list = platform_toolsets.get("discord")
    assert isinstance(discord_list, list), (
        "platform_toolsets.discord must be a YAML LIST of toolset names, not "
        f"a {type(discord_list).__name__} — a bare scalar would silently "
        "char-iterate under set(); author it as a `- item` block"
    )
    return [str(entry) for entry in discord_list]


def test_hermes_config_has_discord_toolset_allowlist(config: dict[str, Any]) -> None:
    """`platform_toolsets.discord` exists and is a non-empty explicit list.
    This is the WALK-10-6-4-F1 fix: without an explicit allow-list Hermes
    enables the full built-in toolset swarm on the Discord surface, drowning
    the mailbot-api verbs."""
    discord_list = _discord_allowlist(config)
    assert discord_list, (
        "platform_toolsets.discord must be a non-empty explicit allow-list "
        "so only the listed toolsets reach the per-turn surface"
    )


def test_hermes_config_discord_allowlist_keeps_mailbot_verbs(
    config: dict[str, Any],
) -> None:
    """The allow-list keeps the mailbot-api MCP server + the minimal
    MailBot-turn toolsets. If mailbot-api is dropped, the 26 email verbs
    leave the surface — the exact failure this story closes."""
    discord_list = set(_discord_allowlist(config))
    missing = _REQUIRED_DISCORD_TOOLSETS - discord_list
    assert not missing, (
        f"platform_toolsets.discord is missing required entries: {sorted(missing)}; "
        f"mailbot-api (the email verbs) MUST stay on the surface"
    )


def test_hermes_config_discord_allowlist_excludes_noise_toolsets(
    config: dict[str, Any],
) -> None:
    """The noise built-in toolsets WALK-10-6-4-F1 saw qwen enumerate
    (tts / image_gen / vision / file / todo / …) MUST NOT be on the Discord
    surface — they are what drowned the email verbs. Red-gates a
    re-pollution regression."""
    discord_list = set(_discord_allowlist(config))
    leaked = _NOISE_TOOLSETS_FORBIDDEN_ON_DISCORD & discord_list
    assert not leaked, (
        f"noise toolsets leaked back onto the Discord surface: {sorted(leaked)}; "
        f"these crowd out the mailbot-api email verbs (WALK-10-6-4-F1)"
    )


def test_hermes_config_every_mcp_server_is_on_the_discord_allowlist(
    config: dict[str, Any],
) -> None:
    """CR-10-6-5-1 (reviewer sonnet-5): guard against a future SECOND MCP
    server auto-injecting its tools onto the Discord surface, bypassing the
    allow-list and re-polluting it without any test catching it. Hermes
    preserves MCP-server names in `platform_toolsets` separately from
    configurable toolsets (`_save_platform_tools.preserved_entries`), so a
    new `mcp_servers` entry that is NOT also named in `platform_toolsets.discord`
    is exactly that silent re-pollution vector. This test forces any new MCP
    server to be an explicit, reviewed decision in the Discord allow-list."""
    mcp_servers = config.get("mcp_servers") or {}
    assert isinstance(mcp_servers, dict)
    discord_list = set(_discord_allowlist(config))
    unlisted = set(mcp_servers) - discord_list
    assert not unlisted, (
        f"mcp_servers {sorted(unlisted)} are registered but NOT named in "
        f"platform_toolsets.discord; a new MCP server's tools would auto-inject "
        f"onto the Discord surface unaccounted-for (WALK-10-6-4-F1 re-pollution "
        f"vector). Add each to the allow-list deliberately, or scope it off Discord."
    )


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
    """No real-looking secret appears in the file. Every secret-bearing
    field uses the ${ENV_VAR} substitution form."""
    raw_text = _HERMES_CONFIG.read_text(encoding="utf-8")
    for pattern in _SECRET_LIKE_PATTERNS:
        match = pattern.search(raw_text)
        assert match is None, (
            f"secret-like substring detected: {pattern.pattern}; "
            f"matched text starts with {match.group(0)[:12]!r}…"
        )
