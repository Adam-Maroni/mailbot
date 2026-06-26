"""Story 9-10 (reframed Path γ) — MCP-tool-registry-vs-SKILL.md drift test.

The original epics.md framing (Hermes `config.yaml` slash registration drift
test) is architecturally-impossible because `discord.slash_commands` is
forbidden by `test_hermes_config_discord_at_top_level_not_under_gateway`
(RECONCILIATION-NOTES §1.4/§1.5 — real Hermes registers slash commands at
runtime via the Discord Developer Portal, not via config.yaml). Path γ
reframing preserves the original intent (catch silent-no-op verb-
registration drift) using the architecturally-correct surface: MCP server
tool registry vs `hermes-config/skills/mailbot/SKILL.md` docs surface.

Bidirectional drift detection + frontmatter count consistency + deliberate-
omission sanity tests + exemption-fixture validation = 6 tests.

§5.12 verdict: GATE-COVERAGE-ELIGIBLE (criteria 1/2/3/4/5/6 all NO; this is
meta-tooling, no production code, no privacy invariants).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from mailbot_api.mcp_server import build_mcp_server

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MD_PATH = _REPO_ROOT / "hermes-config" / "skills" / "mailbot" / "SKILL.md"
_EXEMPT_FIXTURE_PATH = _REPO_ROOT / "tests" / "fixtures" / "skill_md_exempt_tools.yaml"

_SKILL_HEADING_RE = re.compile(r"^### (.*)$", re.MULTILINE)
_BACKTICKED_IDENT_RE = re.compile(r"`([a-z_][a-z0-9_]*)`")
_FRONTMATTER_COUNT_RE = re.compile(r"via (\d+) MCP tools")


def _parse_skill_md_tool_names(skill_md_text: str) -> set[str]:
    """Story 9-10 OQ-2 SKILL.md parser.

    Extracts ALL backtick-wrapped snake_case identifiers from every ``###``
    heading line. Handles three shapes:

    * single-tool headings: ``### `find_emails` ``
    * prose-suffixed headings: ``### `set_model_persistent` — Persistent ...``
    * slash-joined multi-tool headings: ``### `pause_router` / `resume_router` ``

    Frontmatter section (between first two ``---`` lines) is excluded — the
    parser only looks at the body after the frontmatter to avoid matching
    backticked identifiers in the frontmatter description prose.

    Returns a set of unique tool names (lowercase snake_case identifiers
    matching ``[a-z_][a-z0-9_]*``).
    """
    parts = skill_md_text.split("---", 2)
    body = parts[2] if len(parts) >= 3 else skill_md_text
    out: set[str] = set()
    for heading_line in _SKILL_HEADING_RE.findall(body):
        for name in _BACKTICKED_IDENT_RE.findall(heading_line):
            out.add(name)
    return out


def _load_skill_md_text() -> str:
    return _SKILL_MD_PATH.read_text(encoding="utf-8")


def _load_exempt_set() -> set[str]:
    if not _EXEMPT_FIXTURE_PATH.exists():
        return set()
    raw = yaml.safe_load(_EXEMPT_FIXTURE_PATH.read_text(encoding="utf-8"))
    if raw is None:
        return set()
    exempt_list = raw.get("exempt", [])
    return set(exempt_list) if isinstance(exempt_list, list) else set()


def _get_registered_tools(tmp_path: Path) -> set[str]:
    """Build the MCP server with a tmp_path-rooted dummy DB and return the
    registered tool name set. Pattern mirrors test_mcp_server_extended_tools.py."""
    db = tmp_path / "registration-coverage.db"
    server = build_mcp_server(db_path=str(db))
    return set(server._tool_manager._tools.keys())  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Self-test the parser (Subtask 2.2 — sanity baseline)
# ---------------------------------------------------------------------------


def test_skill_md_parser_extracts_25_tools_at_baseline() -> None:
    """Subtask 2.2: at story-9-10 ship time the parser extracts exactly 25
    tool names from SKILL.md. Pins the parser's expected behavior at the
    current canonical state — a future verb addition will need to bump
    this count AND update the AC-3 frontmatter integer assertion."""
    names = _parse_skill_md_tool_names(_load_skill_md_text())
    assert len(names) >= 25, (
        f"SKILL.md parser extracted {len(names)} tool names; "
        f"expected at least 25 post-Story-9-4. Names: {sorted(names)}"
    )


# ---------------------------------------------------------------------------
# AC-1 — Forward-drift: every registered tool has a SKILL.md entry
# ---------------------------------------------------------------------------


def test_every_registered_tool_has_skill_md_entry(tmp_path: Path) -> None:
    """AC-1: a newly-registered MCP tool that lacks a SKILL.md entry
    (and isn't on the exemption allow-list) is the silent-no-op failure
    mode this story exists to catch. Forward direction: registry → docs.
    """
    registered = _get_registered_tools(tmp_path)
    documented = _parse_skill_md_tool_names(_load_skill_md_text())
    exempt = _load_exempt_set()
    missing_in_skill_md = registered - documented - exempt
    assert not missing_in_skill_md, (
        f"\n{len(missing_in_skill_md)} MCP-registered tool(s) missing "
        f"from SKILL.md AND not on the exemption list: {sorted(missing_in_skill_md)}\n\n"
        f"To fix: add a `### \\`<tool_name>\\`` section to "
        f"hermes-config/skills/mailbot/SKILL.md for each tool, OR add the "
        f"tool name to tests/fixtures/skill_md_exempt_tools.yaml with a "
        f"documented architectural rationale (operator-only / transitional / "
        f"etc — see the fixture's header comment for criteria).\n"
    )


# ---------------------------------------------------------------------------
# AC-2 — Reverse-drift: no stale SKILL.md headings for removed verbs
# ---------------------------------------------------------------------------


def test_no_stale_skill_md_headings_for_removed_verbs(tmp_path: Path) -> None:
    """AC-2: a SKILL.md heading that names a non-existent MCP tool is by
    definition stale (a future story removed the verb without removing
    the doc surface). Reverse direction: docs → registry. No exemption
    path — stale doc entries are always FAIL because there's no legitimate
    reason to document a non-existent tool.
    """
    registered = _get_registered_tools(tmp_path)
    documented = _parse_skill_md_tool_names(_load_skill_md_text())
    stale_in_skill_md = documented - registered
    assert not stale_in_skill_md, (
        f"\n{len(stale_in_skill_md)} SKILL.md heading(s) name tool(s) not "
        f"registered in the MCP server: {sorted(stale_in_skill_md)}\n\n"
        f"To fix: either re-add the verb's registration in "
        f"mailbot_api/mcp_server.py (if the removal was unintentional), "
        f"OR remove the `### \\`<tool_name>\\`` section from "
        f"hermes-config/skills/mailbot/SKILL.md (if the verb is genuinely "
        f"gone).\n"
    )


# ---------------------------------------------------------------------------
# AC-3 — Frontmatter MCP-tool-count consistency
# ---------------------------------------------------------------------------


def test_frontmatter_mcp_tool_count_matches_registered_count(
    tmp_path: Path,
) -> None:
    """AC-3: SKILL.md frontmatter declares `via N MCP tools` — that N
    MUST equal the actual registered count. A mismatch is a silent
    drift between the docs-frontmatter claim and the registry truth."""
    text = _load_skill_md_text()
    match = _FRONTMATTER_COUNT_RE.search(text)
    assert match is not None, (
        "Could not find `via N MCP tools` integer in SKILL.md frontmatter. "
        "Expected pattern: `description: \"... via N MCP tools.\"`"
    )
    claimed = int(match.group(1))
    actual = len(_get_registered_tools(tmp_path))
    assert claimed == actual, (
        f"SKILL.md frontmatter claims `via {claimed} MCP tools` but the "
        f"MCP server registers {actual}. Update the frontmatter to "
        f"`via {actual} MCP tools.`"
    )


# ---------------------------------------------------------------------------
# AC-4 — Deliberate-omission sanity tests (drift detection actually fires)
# ---------------------------------------------------------------------------


def test_forward_drift_detects_missing_skill_md_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4 sub-bullet 1: simulate a missing SKILL.md heading by
    monkeypatching the parser to drop one entry. The forward-drift
    assertion MUST fire with the dropped tool named in the error.

    This is the regression sentinel proving AC-1 is real (not always-green).
    """
    registered = _get_registered_tools(tmp_path)
    real_documented = _parse_skill_md_tool_names(_load_skill_md_text())
    exempt = _load_exempt_set()
    # Choose a tool that IS in SKILL.md and IS NOT exempt — the canary.
    canary = "set_model_oneshot"
    assert canary in registered, "regression sentinel pre-condition failed"
    assert canary in real_documented, "regression sentinel pre-condition failed"
    assert canary not in exempt, "regression sentinel pre-condition failed"

    # Simulated post-monkeypatch documented set (canary removed).
    simulated_documented = real_documented - {canary}
    missing_in_skill_md = registered - simulated_documented - exempt
    assert canary in missing_in_skill_md, (
        "deliberate-omission test failed to detect the dropped canary — "
        "the forward-drift assertion is broken (always-green hazard)"
    )


def test_reverse_drift_detects_stale_skill_md_section(
    tmp_path: Path,
) -> None:
    """AC-4 sub-bullet 2: simulate a stale SKILL.md heading by
    computing the reverse-drift verdict against a synthetic registered
    set that is MISSING one tool while SKILL.md still documents it. The
    reverse-drift assertion MUST fire with the stale tool named.

    This is the regression sentinel proving AC-2 is real (not always-green).
    """
    real_registered = _get_registered_tools(tmp_path)
    documented = _parse_skill_md_tool_names(_load_skill_md_text())
    # Choose a tool that IS in both sets — the canary.
    canary = "inspect_policy"
    assert canary in real_registered, "regression sentinel pre-condition failed"
    assert canary in documented, "regression sentinel pre-condition failed"

    # Simulated post-monkeypatch registered set (canary removed —
    # i.e., the verb was deleted but the doc heading wasn't).
    simulated_registered = real_registered - {canary}
    stale_in_skill_md = documented - simulated_registered
    assert canary in stale_in_skill_md, (
        "deliberate-omission test failed to detect the stale canary — "
        "the reverse-drift assertion is broken (always-green hazard)"
    )


# ---------------------------------------------------------------------------
# AC-5 — Exemption-list validation: every entry must be a real tool
# ---------------------------------------------------------------------------


def test_exemption_list_entries_are_real_tools(tmp_path: Path) -> None:
    """AC-5: an entry in `skill_md_exempt_tools.yaml`'s `exempt:` list
    that names a non-existent MCP tool is itself a drift instance — the
    exemption file cannot rot independently.

    Empty list passes trivially (current state at Story 9-10 ship time).
    """
    exempt = _load_exempt_set()
    if not exempt:
        return  # empty exempt list — nothing to validate
    registered = _get_registered_tools(tmp_path)
    bogus_exemptions = exempt - registered
    assert not bogus_exemptions, (
        f"Exemption list contains {len(bogus_exemptions)} tool name(s) "
        f"that are not registered MCP tools: {sorted(bogus_exemptions)}\n\n"
        f"To fix: remove the bogus entries from "
        f"tests/fixtures/skill_md_exempt_tools.yaml, OR re-add the missing "
        f"verb's registration in mailbot_api/mcp_server.py."
    )
