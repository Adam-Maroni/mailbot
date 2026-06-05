"""Story 6-13 — F22 closure integration test.

Drives the full lifecycle that F22 was discovered against during Story 6-6.5's
third-pass walk:

    propose -> drainer_revert_to_pending_grant -> mint_grant
            -> drainer_claim -> dispatch -> applied

Real on-disk SQLite + full migration chain + FakeGraphWriteAdapter (mock
transport at the Graph boundary — the integration-test seam ends BELOW the
HTTP boundary per Step 2.4.7's MailBot reframing for the Router contract;
adapter-level fakes are the standard tool here, mirroring Story 4-4's drainer
integration tests).

The lifecycle asserts the F22 closure: without the mint_grant side-effect,
the row would stay in pending_grant indefinitely after mint_grant fires
(PENDING_ACTIONS_SELECT_DRAINABLE filters on status='pending' only).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.authorization import mint_grant
from mailbot_api.actions.drainer import run_tick
from mailbot_api.actions.graph_write import FakeGraphWriteAdapter
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Apply migrations + redirect notification log dir to tmp_path.

    CR-6 (Story 6-13 reviewer): the unit test `_setup(tmp_path)` in
    test_authorization.py does NOT take monkeypatch because the unit tests
    never exercise the urgent-notification path (no drainer involved). This
    integration test drives the full drainer lifecycle including potential
    notification fires for Tier-3 failure paths, so MAILBOT_LOGS_PATH must
    be redirected away from the developer machine's default logs directory.
    """
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    return db_path


async def _seed_email(db_path: str, *, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com",
         "cm-v1", None),
    )


def _read_status(db_path: str, action_id: int) -> str:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (action_id,),
        ).fetchone()
    return row[0]


def _hours_from_now(n: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=n)


async def test_full_lifecycle_pending_grant_promotion_on_mint_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3 third bullet: full propose -> drainer_revert_to_pending_grant ->
    mint_grant -> drainer_claim -> dispatch flow.

    Status transitions asserted at each beat:
        pending -> pending_grant (drainer revert; no grant exists yet)
        pending_grant -> pending (mint_grant side-effect; F22 closure)
        pending -> applied (drainer claim + dispatch via FakeGraphWriteAdapter)

    DELETE (Tier-3) is used because it skips cooling_off and goes directly to
    'pending' on propose — keeps the lifecycle linear without needing to mock
    the cooling-off ticker.
    """
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")

    # 1. Propose: DELETE lands directly in 'pending' (no cooling_off for Tier-3).
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    assert _read_status(db_path, out.action_id) == "pending"

    # 2. Drainer tick: no valid grant exists -> revert to pending_grant.
    await run_tick(db_path, FakeGraphWriteAdapter())
    assert _read_status(db_path, out.action_id) == "pending_grant"

    # 3. Drainer fires again BEFORE mint_grant -> row stays in pending_grant
    #    (regression guard: PENDING_ACTIONS_SELECT_DRAINABLE filters on
    #    status='pending' only, so the drainer can't pick this row up).
    await run_tick(db_path, FakeGraphWriteAdapter())
    assert _read_status(db_path, out.action_id) == "pending_grant"

    # 4. mint_grant fires -> F22 side-effect promotes the pending_grant row
    #    back to 'pending'. THIS IS THE FIX UNDER TEST.
    grant_out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert grant_out.ok is True
    assert _read_status(db_path, out.action_id) == "pending"

    # 5. Drainer tick: grant is now valid, row claimed and dispatched.
    await run_tick(db_path, FakeGraphWriteAdapter())
    assert _read_status(db_path, out.action_id) == "applied"


async def test_full_lifecycle_mint_grant_does_not_disturb_unrelated_action_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counter-test (cross-cutting): minting a SEND_REPLY grant must NOT
    promote a DELETE pending_grant row. The DELETE row stays stuck until a
    DELETE grant is minted — which is the correct defender-bias behavior."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")

    # Propose DELETE + drain -> pending_grant.
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    await run_tick(db_path, FakeGraphWriteAdapter())
    assert _read_status(db_path, out.action_id) == "pending_grant"

    # Mint a SEND_REPLY grant — wrong action_type, must NOT promote.
    grant_out = await mint_grant(
        ActionType.SEND_REPLY, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert grant_out.ok is True
    assert _read_status(db_path, out.action_id) == "pending_grant"

    # Now mint the correct DELETE grant — must promote.
    grant_out2 = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert grant_out2.ok is True
    assert _read_status(db_path, out.action_id) == "pending"
