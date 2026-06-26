"""Story 9-4 AC-6 sub-bullet 2 — `inspect_policy` end-to-end via MCP wrapper.

Pattern mirrors `test_mcp_server_extended_tools.py` — in-memory client/server
transport, real on-disk SQLite migrations, real policy snapshot loaded from
a tmp_path-rooted alternative layout, real MCP wrapper dispatch (no monkey-
patched verb).

This is the integration layer's complement to `tests/unit/verbs/test_inspect_policy.py`'s
unit tests of the markdown composition logic. The unit tests exercise the
verb in isolation with `_resolve_policy_dir` patched; this e2e test
exercises the FULL stack: MCP client → server → wrapper → verb → policy
snapshot → markdown.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


_BASELINE_YAML = f"""\
version: "test-e2e-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
"""


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Mirrors test_mcp_server_extended_tools.py — clear in-memory singletons."""
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_oneshot_override_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_oneshot_override_for_test()


def _setup_db(tmp_path: Path) -> str:
    db = tmp_path / "x.db"
    apply_pending_migrations(str(db))
    return str(db)


def _setup_policy(
    tmp_path: Path,
    *,
    overrides_yaml: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write baseline + (optionally) overrides under tmp_path, prime the
    policy snapshot, and patch `_resolve_policy_dir` so the verb's
    baseline/override re-readers point at this layout."""
    (tmp_path / "policy.yaml").write_text(_BASELINE_YAML, encoding="utf-8")
    if overrides_yaml is not None:
        (tmp_path / "policy.user-overrides.yaml").write_text(
            overrides_yaml, encoding="utf-8"
        )
        set_policy_snapshot(
            load_policy(
                tmp_path / "policy.yaml",
                overrides_path=tmp_path / "policy.user-overrides.yaml",
            )
        )
    else:
        set_policy_snapshot(load_policy(tmp_path / "policy.yaml"))
    monkeypatch.setattr(
        "mailbot_api.verbs.router_control._resolve_policy_dir",
        lambda: tmp_path,
    )


@pytest.mark.asyncio
async def test_inspect_policy_mcp_round_trip_baseline_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 e2e baseline-only: client.call_tool('inspect_policy') returns
    the markdown table + multi-state lines + correct task / override counts.

    The full stack runs: MCP client → server transport → tool wrapper →
    verb → policy snapshot → markdown composition. No monkey-patching of
    the verb itself — only the policy directory resolution.
    """
    db_path = _setup_db(tmp_path)
    _setup_policy(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("inspect_policy", {})
    payload = json.loads(result.content[0].text)
    assert payload["task_count"] == 2
    assert payload["override_count"] == 0
    assert "🔧" not in payload["markdown"]
    assert "Current degraded mode state: Not active" in payload["markdown"]
    assert "Active one-shot override: None" in payload["markdown"]
    # File path field points at the resolved overrides path (the file may
    # not exist on baseline-only state; only the path resolution matters).
    assert payload["file_path"].endswith("policy.user-overrides.yaml")
    assert str(tmp_path) in payload["file_path"]


@pytest.mark.asyncio
async def test_inspect_policy_mcp_round_trip_one_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 e2e with one override active: the markdown table marks the
    overridden row with the 🔧 prefix and override_count == 1."""
    overrides_yaml = f"tasks:\n  draft_reply:\n    model: {_OPUS}\n"
    db_path = _setup_db(tmp_path)
    _setup_policy(tmp_path, overrides_yaml=overrides_yaml, monkeypatch=monkeypatch)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("inspect_policy", {})
    payload = json.loads(result.content[0].text)
    assert payload["task_count"] == 2
    assert payload["override_count"] == 1
    assert payload["markdown"].count("🔧") == 1
    # The 🔧 row contains the override model (opus).
    overridden_line = next(
        line
        for line in payload["markdown"].split("\n")
        if line.startswith("|") and "🔧" in line
    )
    assert _OPUS in overridden_line
    assert "draft_reply" in overridden_line


@pytest.mark.asyncio
async def test_inspect_policy_mcp_markdown_table_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 e2e markdown sanity: the rendered output contains a well-
    formed markdown table (header + separator + N task rows) when fetched
    via the MCP wrapper."""
    db_path = _setup_db(tmp_path)
    _setup_policy(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("inspect_policy", {})
    payload = json.loads(result.content[0].text)
    table_lines = [
        line for line in payload["markdown"].split("\n") if re.match(r"^\|.*\|$", line)
    ]
    # 1 header + 1 separator + 2 task rows = 4 lines.
    assert len(table_lines) == 1 + 1 + 2, (
        f"unexpected table-row count via MCP wrapper: got {len(table_lines)}; "
        f"markdown: {payload['markdown']!r}"
    )
