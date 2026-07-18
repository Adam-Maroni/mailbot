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
#
# Story 10.7.3: `messaging` REMOVED from the required set. Its `send_message`
# verb is the F-10-6-5-W1 defect-#1 mis-pick (qwen picks `send_message` from
# `messaging` over `find_emails`). On the Adam-only, DM-first, single-platform
# Discord deploy the `messaging`/Rule R cross-platform PUSH is not exercised by
# email-reading turns — Hermes delivers to Discord via its native gateway and
# the urgent/digest path is the PULL-based pull_pending_notifications + cron
# skill (Story 6-3 / 6-10), not the messaging toolset. So messaging is a
# mis-pick attractor with no load-bearing use on the email surface; trimming it
# shrinks the per-turn menu toward the email verbs.
#
# Story 10.7.6: `memory` REMOVED from the required set. It was the dominant
# mis-pick attractor on the FAILED clause-3 live walk (F-10-7-CLAUSE3-W1,
# 2026-07-17: 9/11 router_calls rows [15096-15104] picked `memory`, cascading
# into `{name:memory, action:remove}`, never reaching `find_emails`). The
# `messaging` drop (10.7.3) left `memory` standing as the new dominant
# attractor. Its stated function — defender-persona session hygiene — is NOT
# lost by the drop: the persona reference rides the `.skills_prompt_snapshot.json`
# mechanism (config.yaml:184-186 precedent, mirroring the `skills` drop), NOT
# the `memory` toolset. Confirmed on the live resolver (Task 1, AC-2) before
# shipping the edit — not inferred (the CR-10-7-3 discipline).
_REQUIRED_DISCORD_TOOLSETS = frozenset(
    {
        "mailbot-api",  # the 26 email verbs — the whole point (MCP server name)
        "cronjob",  # Story 6-10 digest / notification-pull jobs
        "clarify",  # AGENTS.md "ask for clarification" tiebreaker
    }
)

# Story 10.7.3: toolsets trimmed off the Discord surface as mis-pick attractors
# (distinct rationale from the built-in noise set above — these are functional
# toolsets deliberately scoped OFF the email-reading surface). `messaging`
# exposes `send_message`, the F-10-6-5-W1 defect-#1 peer qwen mis-picks over
# `find_emails`. A regression that re-adds it red-gates here. A future
# multi-platform deploy that needs Rule R cross-platform push must re-evaluate
# this trade-off deliberately, not inherit the cut silently.
_TRIMMED_TOOLSETS_10_7_3 = frozenset({"messaging"})

# Story 10.7.6: `memory` trimmed off the Discord surface as the dominant
# mis-pick attractor left standing after 10.7.3 dropped `messaging`. On the
# FAILED clause-3 live walk (F-10-7-CLAUSE3-W1, 2026-07-17) qwen picked `memory`
# on 9 of 11 router_calls rows (15096-15104) and never reached `find_emails`.
# The persona-hygiene function rides `.skills_prompt_snapshot.json`, not this
# toolset, so the drop costs nothing on the email surface. A regression that
# re-adds it red-gates here.
_TRIMMED_TOOLSETS_10_7_6 = frozenset({"memory"})

# The union of every toolset deliberately trimmed off the Discord surface as a
# mis-pick attractor across stories. New trims extend this union.
_TRIMMED_TOOLSETS = _TRIMMED_TOOLSETS_10_7_3 | _TRIMMED_TOOLSETS_10_7_6


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


def test_hermes_config_discord_allowlist_excludes_messaging_send_peer(
    config: dict[str, Any],
) -> None:
    """Story 10.7.3: the `messaging` toolset MUST NOT be on the Discord
    surface. Its `send_message` verb is F-10-6-5-W1 defect #1 — qwen picks
    `send_message` over `find_emails` on a "find my unread emails" turn
    (10-7-0 spike §1 / epics.md §4350). On the Adam-only single-platform
    deploy, `messaging` has no load-bearing use on email turns (native-gateway
    delivery + pull-based notifications), so it is trimmed as a mis-pick
    attractor. Red-gates a regression that re-adds it."""
    discord_list = set(_discord_allowlist(config))
    leaked = _TRIMMED_TOOLSETS_10_7_3 & discord_list
    assert not leaked, (
        f"Story 10.7.3-trimmed toolsets leaked back onto the Discord surface: "
        f"{sorted(leaked)}; `messaging` exposes the `send_message` mis-pick peer "
        f"(F-10-6-5-W1 defect #1). A multi-platform deploy needing Rule R push "
        f"must re-add it deliberately, not by regression."
    )


def test_hermes_config_discord_allowlist_excludes_memory_attractor(
    config: dict[str, Any],
) -> None:
    """Story 10.7.6: the `memory` toolset MUST NOT be on the Discord surface.
    It was the dominant mis-pick attractor on the FAILED clause-3 live walk
    (F-10-7-CLAUSE3-W1, 2026-07-17): 9 of 11 router_calls rows (15096-15104)
    picked `memory` — cascading into `{name:memory, action:remove}` — and qwen
    never reached `find_emails`. 10.7.3 dropped `messaging`, which left `memory`
    standing as the new dominant attractor. Its defender-persona session-hygiene
    function is NOT lost: the persona reference rides `.skills_prompt_snapshot.json`
    (config.yaml:184-186 precedent), not the `memory` toolset — confirmed on the
    live resolver (AC-2) before shipping the edit. Red-gates a regression that
    re-adds it."""
    discord_list = set(_discord_allowlist(config))
    leaked = _TRIMMED_TOOLSETS_10_7_6 & discord_list
    assert not leaked, (
        f"Story 10.7.6-trimmed toolsets leaked back onto the Discord surface: "
        f"{sorted(leaked)}; `memory` was the dominant mis-pick attractor on the "
        f"failed clause-3 live walk (F-10-7-CLAUSE3-W1, 9/11 rows). Its "
        f"persona-hygiene function rides `.skills_prompt_snapshot.json`, not this "
        f"toolset. A regression that re-adds it must be a reviewed decision."
    )


def test_hermes_config_discord_allowlist_excludes_all_trimmed_attractors(
    config: dict[str, Any],
) -> None:
    """CR-10-7-6-3: consolidated exclusion gate over the `_TRIMMED_TOOLSETS`
    union. The union was previously decorative (defined, never asserted against),
    so a future story that extends it but forgets to add a dedicated per-story
    exclusion test would get zero coverage despite the union's name implying it
    is load-bearing. This test wires it: EVERY toolset ever trimmed as a
    mis-pick attractor (messaging 10.7.3 + memory 10.7.6 + any future addition)
    must stay off the Discord surface. Extending `_TRIMMED_TOOLSETS` now grants
    the new trim free regression coverage."""
    discord_list = set(_discord_allowlist(config))
    leaked = _TRIMMED_TOOLSETS & discord_list
    assert not leaked, (
        f"trimmed mis-pick attractors leaked back onto the Discord surface: "
        f"{sorted(leaked)}. Every toolset in `_TRIMMED_TOOLSETS` (messaging, "
        f"memory, …) was deliberately scoped off the email surface; re-adding "
        f"one must be a reviewed decision, not a regression."
    )


def test_hermes_config_required_and_trimmed_sets_are_disjoint() -> None:
    """CR-10-7-6-4: the required keep-set and the trimmed attractor sets must
    never overlap. Both `keeps_mailbot_verbs` and the `excludes_*` tests
    evaluate only against the live YAML list, so a future edit that added a
    toolset to BOTH `_REQUIRED_DISCORD_TOOLSETS` and a `_TRIMMED_TOOLSETS_*`
    constant would create a silent self-contradiction between the two Python
    constants that neither live-list test would surface. This asserts the
    constants themselves are internally consistent."""
    overlap = _REQUIRED_DISCORD_TOOLSETS & _TRIMMED_TOOLSETS
    assert not overlap, (
        f"toolset(s) {sorted(overlap)} appear in BOTH _REQUIRED_DISCORD_TOOLSETS "
        f"and _TRIMMED_TOOLSETS — a required toolset cannot also be a trimmed "
        f"attractor. Resolve the contradiction in the Python constants."
    )


def test_hermes_config_10_7_6_clarify_kept_rationale_documented() -> None:
    """Story 10.7.6 AC-3 (CR-10-7-6-5): the KEEP-SET comment must durably
    record WHY `clarify` was explicitly kept (not an attractor on the failed
    walk; legitimate tiebreaker). `clarify`'s mere presence in the YAML list is
    caught by `keeps_mailbot_verbs`, but the AC-3 explicit-rationale requirement
    is documentation, not membership — a future edit could delete the rationale
    prose while `clarify` stays listed and no other gate would notice. This
    mirrors the doc-gate pattern used for the TRIMMED / BOUNDARY blocks."""
    raw_text = _HERMES_CONFIG.read_text(encoding="utf-8")
    keep_start = raw_text.find("# KEEP-SET rationale:")
    assert keep_start != -1, (
        "config.yaml must contain the `# KEEP-SET rationale:` comment block"
    )
    # The KEEP-SET block ends where the first TRIMMED note begins.
    keep_end = raw_text.find("# TRIMMED (Story", keep_start)
    assert keep_end != -1, (
        "the `# KEEP-SET rationale:` block must precede the TRIMMED notes"
    )
    keep_block = raw_text[keep_start:keep_end]
    assert "clarify" in keep_block, (
        "the KEEP-SET block must name `clarify` (AC-3)"
    )
    assert "KEPT by Story 10.7.6" in keep_block, (
        "the KEEP-SET block must record the AC-3 explicit `clarify`-kept "
        "rationale (`KEPT by Story 10.7.6` — not an attractor on the failed "
        "walk, legitimate tiebreaker) so the decision is durably documented, "
        "not just true today (CR-10-7-6-5)"
    )


def test_hermes_config_10_7_3_boundary_documented() -> None:
    """Story 10.7.3 AC-5: the config file must honestly record what this
    toolset-level allow-list CANNOT do — remove the intra-`mailbot-api`
    `pull_pending_notifications` attractor (the spike's dominant real-surface
    mis-pick, §1). That verb lives inside the `mailbot-api` MCP server, not a
    separable toolset, so `platform_toolsets.discord` (toolset granularity)
    cannot drop it without dropping all 26 email verbs. This gate red-gates a
    future edit that quietly claims full surface-scoping without the filed
    intra-mailbot-api residual.

    CR-10-7-3-P (reviewer sonnet-5): scope the substring match to the actual
    `# BOUNDARY` comment block (between the `# BOUNDARY` marker and the
    `platform_toolsets:` key), NOT the whole file. An unscoped `in raw_text`
    would pass if the two strings survived anywhere else (a stray reference,
    an unrelated future comment) even after the BOUNDARY prose was deleted —
    exactly the drift this gate is meant to catch."""
    raw_text = _HERMES_CONFIG.read_text(encoding="utf-8")
    boundary_start = raw_text.find("# BOUNDARY")
    assert boundary_start != -1, (
        "config.yaml must contain the Story 10.7.3 `# BOUNDARY` comment block "
        "documenting what the toolset-level allow-list CANNOT do (AC-5)"
    )
    # The BOUNDARY note ends at the `platform_toolsets:` key it precedes.
    boundary_end = raw_text.find("platform_toolsets:", boundary_start)
    assert boundary_end != -1, (
        "the `# BOUNDARY` block must precede the `platform_toolsets:` key it "
        "annotates (AC-5 scoping)"
    )
    boundary_block = raw_text[boundary_start:boundary_end]
    assert "pull_pending_notifications" in boundary_block, (
        "the Story 10.7.3 `# BOUNDARY` note must name the "
        "pull_pending_notifications attractor (AC-5) — it is the intra-"
        "mailbot-api verb the toolset-level allow-list cannot remove"
    )
    assert "F-10-7-3-R1" in boundary_block, (
        "the Story 10.7.3 `# BOUNDARY` note must reference the F-10-7-3-R1 "
        "residual (per-verb mailbot-api surface scoping) so the boundary is "
        "not silently claimed as delivered"
    )


def test_hermes_config_10_7_6_memory_trim_documented() -> None:
    """Story 10.7.6 AC-7: the config file must honestly record that `memory`
    was trimmed as the dominant clause-3 mis-pick attractor, and cite the
    failed-walk finding (F-10-7-CLAUSE3-W1) that licensed the removal. This
    boundary-honesty gate red-gates a future edit that drops the toolset without
    leaving the rationale on the surface (or that re-adds `memory` while the
    prose still claims it was trimmed).

    Scoped to the `# TRIMMED (Story 10.7.6)` comment block, delimited by its
    start marker and a DEDICATED `# END TRIMMED (Story 10.7.6)` end-marker
    (CR-10-7-6-2). The end-marker replaces the earlier bare `platform_toolsets:`
    substring anchor, which was vulnerable to a false-fail: prose inside the
    block (or a future edit between the marker and the real YAML key) could
    contain the literal `platform_toolsets:` and truncate the scoped block early
    while the required content survived later in the file. Matching CR-10-7-3-P
    discipline — an unscoped match would pass on a stray reference elsewhere."""
    raw_text = _HERMES_CONFIG.read_text(encoding="utf-8")
    trim_start = raw_text.find("# TRIMMED (Story 10.7.6)")
    assert trim_start != -1, (
        "config.yaml must contain the Story 10.7.6 `# TRIMMED (Story 10.7.6)` "
        "comment block documenting the `memory` attractor removal (AC-7)"
    )
    trim_end = raw_text.find("# END TRIMMED (Story 10.7.6)", trim_start)
    assert trim_end != -1, (
        "the Story 10.7.6 `# TRIMMED` block must be closed by a dedicated "
        "`# END TRIMMED (Story 10.7.6)` end-marker (CR-10-7-6-2 block-scoping "
        "fix) so the doc-gate anchors on it, not the bare `platform_toolsets:` "
        "substring"
    )
    trim_block = raw_text[trim_start:trim_end]
    assert "memory" in trim_block, (
        "the Story 10.7.6 `# TRIMMED` note must name the `memory` toolset it "
        "removed (AC-7)"
    )
    assert "F-10-7-CLAUSE3-W1" in trim_block, (
        "the Story 10.7.6 `# TRIMMED` note must cite F-10-7-CLAUSE3-W1 — the "
        "failed clause-3 walk finding that licensed the `memory` drop (AC-7)"
    )
    assert ".skills_prompt_snapshot.json" in trim_block, (
        "the Story 10.7.6 `# TRIMMED` note must record the persona-survives "
        "rationale (`.skills_prompt_snapshot.json`, not the `memory` toolset) so "
        "the drop is not silently claimed free of persona cost (AC-7)"
    )
    # CR-10-7-6-1: the block must NOT overstate the confirmation level — the
    # persona-survives claim is carried by analogy, not independently verified.
    # Gate the honesty-bound so a future edit can't quietly re-inflate it to
    # "CONFIRMED... not inferred" for the persona-behavior claim.
    assert "HONESTY BOUND" in trim_block, (
        "the Story 10.7.6 `# TRIMMED` note must keep the CR-10-7-6-1 `HONESTY "
        "BOUND` disclaimer distinguishing the live-confirmed toolset-disabled "
        "state from the analogy-carried persona-survives claim (not "
        "independently verified for `memory`; exercised at the AC-8 walk)"
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
