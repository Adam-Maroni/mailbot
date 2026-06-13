"""Story 7-0-prep AC §3 — DELETE-via-handshake smoke integration tests.

Disposition story: Story 4-1 CR-2 (DELETE requires_sensitivity_token=True) shipped
2026-06-02 in commit e4dac69 (Adam-authored on Epic 4 retro day). This smoke
test ships 4 days late as the closure trail — forward-looking insurance that
documents the DELETE-via-handshake contract Hermes-side flow will consume.

The 3 tests cover:
  1. `mailbot://action-types` MCP resource exposes DELETE with
     `requires_sensitivity_token=True` so Hermes can discover the handshake
     requirement before proposing a DELETE on a sensitive email.
  2. `mint_sensitivity_token(email_id, task_type="delete")` succeeds for a
     sensitive email — the verb is task-type-agnostic and accepts arbitrary
     task_type strings, mint→consume pattern is identical to SEND_REPLY.
  3. `mint_sensitivity_token(email_id, task_type="delete")` refuses for a
     CONFIDENTIAL email with `SENSITIVITY_BLOCKS_API` per NFR-PRIV-2 —
     confidential admits no override regardless of task_type.

This test does NOT exercise the full mint→propose_action(DELETE)→drainer→
Outlook Graph DELETE end-to-end flow; that surface is covered transitively
by the drainer + adapter coverage. The smoke scope is bounded to the
discoverability contract + the verb's task-type-agnostic mint shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server
from mailbot_api.verbs.mint_sensitivity_token import mint_sensitivity_token

_QWEN = "qwen2.5:3b-instruct-q4_K_M"


@pytest.fixture
def _clean_state():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


async def _seed_email(
    db_path: str, *, graph_id: str, sensitivity: str,
) -> None:
    """Mirror of the seed helper in test_router_sensitivity_handshake.py to keep
    fixture shape parity (5.8 self-audit gate). Inserts the minimal email row
    with the sensitivity classification + audit metadata the
    `EMAIL_SENSITIVITY_SELECT` query reads."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-06-13T00:00:00Z", "s", "x@y.com", "b",
            sensitivity, "2026-06-13T00:01:00Z", "v1", 0.9, _QWEN,
        ),
    )


@pytest.mark.asyncio
async def test_mcp_action_types_resource_exposes_delete_requires_sensitivity_token(
    tmp_path: Path,
) -> None:
    """AC §3 test 1 — `mailbot://action-types` carries DELETE entry with
    `requires_sensitivity_token=True`. This is the discoverability contract
    Hermes-side flow consults before proposing a DELETE on a sensitive email
    (parity with the SEND_REPLY discoverability path tested in
    test_mcp_server_action_types_resource.py::test_action_types_resource_includes_send_reply_with_correct_metadata)."""
    db_path = str(tmp_path / "x.db")
    server = build_mcp_server(db_path=db_path)

    contents = list(await server.read_resource("mailbot://action-types"))
    body: dict[str, Any] = json.loads(contents[0].content)
    entries_by_value = {e["value"]: e for e in body["action_types"]}

    delete_entry = entries_by_value[ActionType.DELETE.value]
    assert delete_entry["tier"] == 3
    assert delete_entry["requires_sensitivity_token"] is True, (
        "DELETE must surface requires_sensitivity_token=True per Adam's Epic 4 "
        "retro decision (2026-06-02, Story 4-1 CR-2, commit e4dac69). This is "
        "the discoverability contract for Hermes-side flow."
    )
    # DELETE is not a SEND-family action — counter-check against accidental
    # membership drift.
    assert delete_entry["is_send_family"] is False
    assert delete_entry["is_email_less"] is False


@pytest.mark.asyncio
async def test_mint_sensitivity_token_succeeds_for_delete_task_on_sensitive_email(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC §3 test 2 — the mint verb is task-type-agnostic; `task_type="delete"`
    on a sensitive email mints a usable token + grant_id identical in shape to
    the SEND_REPLY path tested in test_router_sensitivity_handshake.py. This
    documents the contractual support shape for a future Hermes-side flow that
    proposes DELETE on a sensitive email + must consume a handshake token."""
    db_path = str(tmp_path / "x.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path, graph_id="e-sens-del", sensitivity="sensitive")

    mint_out = await mint_sensitivity_token(
        "e-sens-del", "delete", db_path=db_path,
    )
    assert mint_out.ok is True, (
        f"mint_sensitivity_token(task_type='delete') unexpectedly refused: "
        f"{mint_out.error}"
    )
    assert mint_out.token is not None
    assert mint_out.expires_at is not None and mint_out.expires_at.endswith("Z")
    assert mint_out.grant_id is not None
    assert mint_out.error is None


@pytest.mark.asyncio
async def test_mint_sensitivity_token_refuses_delete_task_on_confidential_email(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC §3 test 3 — NFR-PRIV-2: confidential admits no override regardless
    of task_type. Even with the "DELETE belt-and-suspenders" intent, the
    confidential gate fires first. Counter-test guarding against any future
    refactor that would special-case task_type='delete' as a confidential
    override path."""
    db_path = str(tmp_path / "x.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path, graph_id="e-conf-del", sensitivity="confidential")

    mint_out = await mint_sensitivity_token(
        "e-conf-del", "delete", db_path=db_path,
    )
    assert mint_out.ok is False
    assert mint_out.token is None
    assert mint_out.grant_id is None
    assert mint_out.error is not None
    assert mint_out.error.code == "SENSITIVITY_BLOCKS_API"
    assert "confidential" in mint_out.error.message.lower()
