"""Story 6-19 — F29 closure: `mailbot://action-types` MCP resource tests.

4 integration tests covering AC-4 tests 6-9: the canonical ActionType
enumeration is discoverable via `list_resources` + readable via
`read_resource`, carries per-action metadata (tier, sensitivity,
send-family, email-less), and the entries for `send_reply` /
`send_new_email` match the `ACTION_PROPERTIES` / `EMAIL_LESS_ACTIONS`
ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.types import ActionType
from mailbot_api.mcp_server import build_mcp_server


@pytest.mark.asyncio
async def test_action_types_resource_registered(tmp_path: Path) -> None:
    """AC-4.6 — `list_resources` surfaces a resource with URI
    `mailbot://action-types`, name `action-types`, and a description
    referencing the canonical ActionType enumeration."""
    db_path = str(tmp_path / "x.db")
    server = build_mcp_server(db_path=db_path)

    resources = await server.list_resources()
    matching = [r for r in resources if str(r.uri) == "mailbot://action-types"]
    assert len(matching) == 1, (
        f"expected exactly 1 mailbot://action-types resource, found "
        f"{len(matching)} out of {len(resources)} total resources"
    )
    res = matching[0]
    assert res.name == "action-types"
    assert res.description is not None
    assert "Canonical mailbot ActionType enumeration" in res.description


@pytest.mark.asyncio
async def test_action_types_resource_payload_shape(tmp_path: Path) -> None:
    """AC-4.7 — `read_resource` returns valid JSON with the expected top-
    level keys + 23 action_type entries + sorted-determinism + all
    required per-entry fields + synonyms_rejected with known synonyms."""
    db_path = str(tmp_path / "x.db")
    server = build_mcp_server(db_path=db_path)

    contents = await server.read_resource("mailbot://action-types")
    # FastMCP returns an iterable of ReadResourceContents; we expect one.
    contents_list = list(contents)
    assert len(contents_list) == 1
    body_text = contents_list[0].content
    assert isinstance(body_text, str)
    body: dict[str, Any] = json.loads(body_text)

    # Top-level keys present.
    assert set(body.keys()) >= {"action_types", "synonyms_rejected", "constraint"}

    # 23 entries.
    entries = body["action_types"]
    assert isinstance(entries, list)
    assert len(entries) == 23

    # Per-entry shape.
    required_fields = {
        "value", "tier", "requires_sensitivity_token",
        "is_send_family", "is_email_less",
    }
    # CR-5 (2026-06-06, sonnet-4-6 review): per-entry check is == not >=.
    # The top-level body permits additive evolution (>= on body.keys()),
    # but the per-entry schema is the load-bearing contract — a typo
    # producing an extra key (e.g., "is_send_famly") should fail the test
    # rather than silently pass. Top-level subset check stays at line above.
    for entry in entries:
        assert isinstance(entry, dict)
        assert set(entry.keys()) == required_fields

    # Deterministic sort by `value`. First entry must match
    # min(at.value for at in ActionType).
    assert entries[0]["value"] == min(at.value for at in ActionType)
    # And the sorted-by-value invariant on all entries.
    values = [e["value"] for e in entries]
    assert values == sorted(values)

    # Synonyms_rejected anti-anchor includes the known hallucination cases.
    synonyms = body["synonyms_rejected"]
    assert isinstance(synonyms, list)
    for known in ("send_email", "sendReply", "send", "SEND_EMAIL"):
        assert known in synonyms, f"missing anti-anchor synonym {known!r}"


@pytest.mark.asyncio
async def test_action_types_resource_includes_send_reply_with_correct_metadata(
    tmp_path: Path,
) -> None:
    """AC-4.8 — `send_reply` entry matches ACTION_PROPERTIES ground truth:
    tier=3, requires_sensitivity_token=True, is_send_family=True,
    is_email_less=False."""
    db_path = str(tmp_path / "x.db")
    server = build_mcp_server(db_path=db_path)

    contents = list(await server.read_resource("mailbot://action-types"))
    body = json.loads(contents[0].content)
    entries_by_value = {e["value"]: e for e in body["action_types"]}

    send_reply = entries_by_value["send_reply"]
    assert send_reply["tier"] == 3
    assert send_reply["requires_sensitivity_token"] is True
    assert send_reply["is_send_family"] is True
    assert send_reply["is_email_less"] is False


@pytest.mark.asyncio
async def test_action_types_resource_includes_send_new_email_as_email_less(
    tmp_path: Path,
) -> None:
    """AC-4.9 — `send_new_email` is email-less per EMAIL_LESS_ACTIONS
    (compose-from-scratch with no source email). Edge-case lockdown
    against accidental membership drift."""
    db_path = str(tmp_path / "x.db")
    server = build_mcp_server(db_path=db_path)

    contents = list(await server.read_resource("mailbot://action-types"))
    body = json.loads(contents[0].content)
    entries_by_value = {e["value"]: e for e in body["action_types"]}

    send_new_email = entries_by_value["send_new_email"]
    assert send_new_email["is_email_less"] is True
    assert send_new_email["tier"] == 3
    # Counter-check: send_reply is NOT email-less (it references an existing
    # inbox row).
    assert entries_by_value["send_reply"]["is_email_less"] is False
