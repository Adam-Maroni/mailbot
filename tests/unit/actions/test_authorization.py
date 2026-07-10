"""Story 4-3 — mint_grant + is_grant_valid + revoke_grant unit tests.

Real on-disk SQLite via tmp_path + the full migration chain. No mocks.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.authorization import (
    MAX_BATCH_SIZE,
    is_grant_valid,
    mint_grant,
    revoke_grant,
)
from mailbot_api.actions.types import ActionType
from mailbot_api.actions.user_confirmation import record_grant_confirmation
from mailbot_api.db.connection import get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.mint_grant import mint_grant as mint_grant_shim


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _confirm(db_path: str, action_type: ActionType) -> None:
    """Story 10.5.2: seed the user-gated confirmation that mint_grant now
    requires (F-10-5-8). The boundary creates this on a real user 'yes'; tests
    that exercise a SUCCESSFUL mint seed it explicitly."""
    await record_grant_confirmation(db_path, action_type=action_type.value, email_ids=[])


# Story 10.5.2 (F-10-5-8): mint_grant now requires a user-gated confirmation.
# These Story-4-3-era tests predate that gate and exercise the mint as a
# structural operation. Patch `mint_grant` in this module so every call first
# seeds a fresh single-use confirmation for its action_type — preserving each
# test's original intent (they are NOT testing the confirmation gate; the
# dedicated gate tests live in test_mint_requires_user_confirmation.py).
@pytest.fixture(autouse=True)
def _auto_confirm_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    import mailbot_api.actions.authorization as _authz

    _real_mint = _authz.mint_grant

    async def _mint_with_confirmation(action_type, email_ids, expires_at, *, db_path):  # type: ignore[no-untyped-def]
        # Seed a confirmation for THIS action_type immediately before minting so
        # the structural refusal tests (past/window/batch/tier) still refuse on
        # their own gate (which fires before the confirmation consume).
        await record_grant_confirmation(
            db_path, action_type=action_type.value, email_ids=list(email_ids),
        )
        return await _real_mint(action_type, email_ids, expires_at, db_path=db_path)

    monkeypatch.setattr(_authz, "mint_grant", _mint_with_confirmation)
    # The names imported at module top bind to the original; rebind them too.
    monkeypatch.setattr(
        "tests.unit.actions.test_authorization.mint_grant", _mint_with_confirmation
    )


def _hours_from_now(n: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=n)


# ---- mint_grant happy path ----------------------------------------------------


async def test_mint_grant_happy_path_returns_grant_id(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant(
        ActionType.DELETE,
        ["e-1", "e-2", "e-3"],
        _hours_from_now(1),
        db_path=db_path,
    )
    assert out.ok is True
    assert out.grant_id is not None
    assert out.email_count == 3
    assert out.expires_at is not None
    assert out.expires_at.endswith("Z")
    assert out.error is None
    # Verify the row landed correctly.
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT action_type, email_ids, expires_at, revoked_at "
            "FROM action_grants WHERE id = ?",
            (out.grant_id,),
        ).fetchone()
    assert row[0] == "delete"
    assert json.loads(row[1]) == ["e-1", "e-2", "e-3"]
    assert row[2].endswith("Z")
    assert row[3] is None


# ---- mint_grant refusals ------------------------------------------------------


async def test_mint_grant_expires_at_in_past_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant(
        ActionType.DELETE,
        ["e-1"],
        _hours_from_now(-1),
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "EXPIRES_AT_IN_PAST"


async def test_mint_grant_window_too_large_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant(
        ActionType.DELETE,
        ["e-1"],
        _hours_from_now(25),
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "GRANT_WINDOW_TOO_LARGE"


async def test_mint_grant_batch_too_large_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    too_many = [f"e-{i}" for i in range(MAX_BATCH_SIZE + 1)]
    out = await mint_grant(
        ActionType.DELETE,
        too_many,
        _hours_from_now(1),
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "BATCH_TOO_LARGE"


async def test_mint_grant_for_tier_0_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant(
        ActionType.READ_SQL,
        ["e-1"],
        _hours_from_now(1),
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "GRANT_NOT_NEEDED"


async def test_mint_grant_for_tier_1_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant(
        ActionType.MARK_READ,
        ["e-1"],
        _hours_from_now(1),
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "GRANT_NOT_NEEDED"


# ---- mint_grant verb shim -----------------------------------------------------


async def test_mint_grant_shim_invalid_action_type_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant_shim(
        "fake_action", ["e-1"], _hours_from_now(1).isoformat(),
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "INVALID_ACTION_TYPE"


async def test_mint_grant_shim_invalid_iso8601_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await mint_grant_shim(
        "delete", ["e-1"], "not-a-date",
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    # Treated as "in past" — closest existing code.
    assert out.error.code == "EXPIRES_AT_IN_PAST"


# ---- is_grant_valid -----------------------------------------------------------


async def test_is_grant_valid_happy_path(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    mint_out = await mint_grant(
        ActionType.DELETE, ["e-1", "e-2"], _hours_from_now(1), db_path=db_path,
    )
    assert mint_out.ok
    ok, gid = await is_grant_valid(ActionType.DELETE, "e-1", db_path=db_path)
    assert ok is True
    assert gid == mint_out.grant_id


async def test_is_grant_valid_email_not_in_list(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await mint_grant(
        ActionType.DELETE, ["e-1", "e-2"], _hours_from_now(1), db_path=db_path,
    )
    ok, gid = await is_grant_valid(ActionType.DELETE, "e-99", db_path=db_path)
    assert ok is False
    assert gid is None


async def test_is_grant_valid_wrong_action_type(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    ok, gid = await is_grant_valid(ActionType.SEND_REPLY, "e-1", db_path=db_path)
    assert ok is False
    assert gid is None


async def test_is_grant_valid_expired_grant(tmp_path: Path) -> None:
    """Insert an already-expired grant directly + verify is_grant_valid refuses."""
    db_path = _setup(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    minted = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO action_grants (action_type, email_ids, expires_at, minted_at) "
            "VALUES (?, ?, ?, ?)",
            ("delete", json.dumps(["e-1"]), past, minted),
        )
        conn.commit()
    ok, gid = await is_grant_valid(ActionType.DELETE, "e-1", db_path=db_path)
    assert ok is False
    assert gid is None


async def test_is_grant_valid_revoked_grant(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    mint_out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    revoke_out = await revoke_grant(mint_out.grant_id, db_path=db_path)
    assert revoke_out.ok
    ok, gid = await is_grant_valid(ActionType.DELETE, "e-1", db_path=db_path)
    assert ok is False
    assert gid is None


async def test_is_grant_valid_email_less_grant_matches_any(tmp_path: Path) -> None:
    """An action_grants row with email_ids=[] (email-less grant for actions
    like MODIFY_INBOX_RULE) matches any target email_id (including None)."""
    db_path = _setup(tmp_path)
    mint_out = await mint_grant(
        ActionType.MODIFY_INBOX_RULE, [], _hours_from_now(1), db_path=db_path,
    )
    assert mint_out.ok
    ok, gid = await is_grant_valid(ActionType.MODIFY_INBOX_RULE, None, db_path=db_path)
    assert ok is True
    assert gid == mint_out.grant_id
    ok2, gid2 = await is_grant_valid(ActionType.MODIFY_INBOX_RULE, "any-eid", db_path=db_path)
    assert ok2 is True
    assert gid2 == mint_out.grant_id


async def test_is_grant_valid_tier_1_returns_false(tmp_path: Path) -> None:
    """Defensive: Tier-1 calls return (False, None) even if a grant somehow exists."""
    db_path = _setup(tmp_path)
    ok, gid = await is_grant_valid(ActionType.MARK_READ, "e-1", db_path=db_path)
    assert ok is False
    assert gid is None


# ---- revoke_grant -------------------------------------------------------------


async def test_revoke_grant_happy_path(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    mint_out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    out = await revoke_grant(mint_out.grant_id, db_path=db_path)
    assert out.ok is True
    assert out.grant_id == mint_out.grant_id
    assert out.revoked_at is not None
    assert out.revoked_at.endswith("Z")


async def test_revoke_grant_nonexistent_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await revoke_grant(99999, db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "GRANT_NOT_FOUND"


async def test_revoke_grant_already_revoked_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    mint_out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    first = await revoke_grant(mint_out.grant_id, db_path=db_path)
    assert first.ok
    second = await revoke_grant(mint_out.grant_id, db_path=db_path)
    assert second.ok is False
    assert second.error.code == "GRANT_NOT_FOUND"


# ---- log lines ----------------------------------------------------------------


async def test_action_grant_minted_log_line_emitted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = _setup(tmp_path)
    with caplog.at_level(logging.INFO, logger="mailbot_api.actions.authorization"):
        out = await mint_grant(
            ActionType.DELETE, ["e-1", "e-2"], _hours_from_now(1), db_path=db_path,
        )
    assert out.ok
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "action.grant.minted")
    assert rec.grant_id == out.grant_id
    assert rec.action_type == "delete"
    assert rec.email_count == 2


async def test_action_grant_revoked_log_line_emitted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = _setup(tmp_path)
    mint_out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    with caplog.at_level(logging.INFO, logger="mailbot_api.actions.authorization"):
        await revoke_grant(mint_out.grant_id, db_path=db_path)
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "action.grant.revoked")
    assert rec.grant_id == mint_out.grant_id


# ---- Story 6-13: pending_grant -> pending promotion on mint_grant (F22) ------


async def _seed_pending_grant_row(
    db_path: str,
    *,
    action_type: str,
    email_id: str | None = "e-1",
    tier: int = 2,
) -> int:
    """Direct INSERT of a pending_actions row in status='pending_grant'.

    Mirrors what `_revert_to_pending_grant` (drainer) writes when a Tier-2/3
    row finds no valid grant at drain time. Returns the row id.

    CR-2 (Story 6-13 reviewer): we deliberately seed `proposed_by_grant_id=NULL`
    even though production rows reach `pending_grant` via the drainer's
    `PENDING_ACTION_REVERT_TO_PENDING_GRANT` query which always writes a
    non-NULL grant_id. This is safe for the promotion-path tests because the
    `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` UPDATE filters by `status` +
    `action_type` only and never reads `proposed_by_grant_id`. If a future
    consumer (e.g. revoke_grant cascade) reads that column from a promoted
    row, this helper should be extended to accept an optional grant_id.
    """
    from mailbot_api.db.connection import execute_insert_returning_id

    proposed_at = _hours_from_now(0).isoformat().replace("+00:00", "Z")
    return await execute_insert_returning_id(
        db_path,
        "INSERT INTO pending_actions (email_id, action_type, tier, payload, "
        "proposed_at, status) VALUES (?, ?, ?, ?, ?, ?)",
        (email_id, action_type, tier, "{}", proposed_at, "pending_grant"),
    )


def _read_pending_status(db_path: str, action_id: int) -> str:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (action_id,),
        ).fetchone()
    return row[0]


async def test_mint_grant_promotes_matching_pending_grant_row(tmp_path: Path) -> None:
    """AC-3 first bullet: mint_grant flips a seeded pending_grant row with
    matching action_type to pending."""
    db_path = _setup(tmp_path)
    action_id = await _seed_pending_grant_row(db_path, action_type="delete")
    assert _read_pending_status(db_path, action_id) == "pending_grant"

    out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert out.ok is True

    assert _read_pending_status(db_path, action_id) == "pending"


async def test_mint_grant_does_not_promote_different_action_type(
    tmp_path: Path,
) -> None:
    """AC-3 second bullet (counter-test): mint_grant of SEND_REPLY does NOT
    promote a seeded pending_grant row whose action_type is DELETE.

    This test is the load-bearing one — without the `AND action_type = ?`
    filter in PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE, a broad sweep would
    flip every pending_grant row regardless of type. is_grant_valid() at
    drain time re-checks email_id membership, but action_type mismatch
    must be filtered at the SQL boundary."""
    db_path = _setup(tmp_path)
    delete_action_id = await _seed_pending_grant_row(
        db_path, action_type="delete",
    )
    assert _read_pending_status(db_path, delete_action_id) == "pending_grant"

    out = await mint_grant(
        ActionType.SEND_REPLY, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert out.ok is True

    # Different action_type must NOT promote.
    assert _read_pending_status(db_path, delete_action_id) == "pending_grant"


async def test_mint_grant_promotes_multiple_matching_rows(tmp_path: Path) -> None:
    """Broad sweep: a single mint_grant promotes ALL pending_grant rows of
    that action_type, regardless of email_id (is_grant_valid does the
    email_id membership re-check at drain time)."""
    db_path = _setup(tmp_path)
    a1 = await _seed_pending_grant_row(db_path, action_type="delete", email_id="e-1")
    a2 = await _seed_pending_grant_row(db_path, action_type="delete", email_id="e-2")
    a3 = await _seed_pending_grant_row(db_path, action_type="delete", email_id="e-99")

    out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert out.ok is True

    # All three promoted, even e-99 which is NOT in the grant's email_ids list.
    # The is_grant_valid re-check at drain time will revert e-99 back to
    # pending_grant on the drainer's next tick (the broad-sweep contract) —
    # PROVIDED the grant-wait window has not elapsed. For Tier-3 rows past
    # TIER_3_GRANT_WAIT_WINDOW the drainer marks them `failed` instead of
    # reverting (drainer.py:330-332). This test is instantaneous so the
    # window concern does not apply here; the Tier-3 grant-expiry path is
    # covered by Story 4-4's existing `test_tier_3_delete_grant_expired_*`.
    assert _read_pending_status(db_path, a1) == "pending"
    assert _read_pending_status(db_path, a2) == "pending"
    assert _read_pending_status(db_path, a3) == "pending"


async def test_mint_grant_promotion_log_includes_count(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-1: the side-effect MUST log `pending_grant_promoted=N` in the
    structured `action.grant.minted` log line."""
    db_path = _setup(tmp_path)
    await _seed_pending_grant_row(db_path, action_type="delete", email_id="e-1")
    await _seed_pending_grant_row(db_path, action_type="delete", email_id="e-2")

    with caplog.at_level(logging.INFO, logger="mailbot_api.actions.authorization"):
        out = await mint_grant(
            ActionType.DELETE, ["e-1", "e-2"], _hours_from_now(1), db_path=db_path,
        )
    assert out.ok is True
    rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "action.grant.minted"
    )
    assert rec.pending_grant_promoted == 2


async def test_mint_grant_promotion_zero_when_no_pending_grant_rows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """The side-effect is safe when no pending_grant rows exist — the
    structured log records pending_grant_promoted=0."""
    db_path = _setup(tmp_path)

    with caplog.at_level(logging.INFO, logger="mailbot_api.actions.authorization"):
        out = await mint_grant(
            ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
        )
    assert out.ok is True
    rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "action.grant.minted"
    )
    assert rec.pending_grant_promoted == 0


async def test_mint_grant_promotion_skips_pending_and_applied_rows(
    tmp_path: Path,
) -> None:
    """The promotion query filters on `status = 'pending_grant'` — rows
    already in pending / applied / failed / cancelled MUST NOT be touched."""
    db_path = _setup(tmp_path)
    pending_id = await execute_insert_returning_id_helper(
        db_path, "delete", "pending",
    )
    applied_id = await execute_insert_returning_id_helper(
        db_path, "delete", "applied",
    )
    pending_grant_id = await _seed_pending_grant_row(db_path, action_type="delete")

    out = await mint_grant(
        ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert out.ok is True

    assert _read_pending_status(db_path, pending_id) == "pending"
    assert _read_pending_status(db_path, applied_id) == "applied"
    assert _read_pending_status(db_path, pending_grant_id) == "pending"


async def execute_insert_returning_id_helper(
    db_path: str, action_type: str, status: str,
) -> int:
    """Helper: insert a pending_actions row with arbitrary status."""
    from mailbot_api.db.connection import execute_insert_returning_id

    proposed_at = _hours_from_now(0).isoformat().replace("+00:00", "Z")
    return await execute_insert_returning_id(
        db_path,
        "INSERT INTO pending_actions (email_id, action_type, tier, payload, "
        "proposed_at, status) VALUES (?, ?, ?, ?, ?, ?)",
        ("e-1", action_type, 2, "{}", proposed_at, status),
    )


async def test_mint_grant_atomicity_rollback_on_promotion_failure(
    tmp_path: Path,
) -> None:
    """CR-1 (Story 6-13 reviewer): the grant INSERT and the pending_grant→
    pending promotion MUST commit atomically. If the promotion query fails
    after the INSERT succeeds, the entire transaction MUST roll back —
    no orphan grant row in action_grants, no half-applied state.

    Trigger: pass a deliberately-invalid promotion query (referencing a
    non-existent column) to the batch helper. SQLite raises OperationalError
    after the INSERT half has executed but before commit, exercising the
    rollback path."""
    from mailbot_api.db.connection import execute_insert_and_write
    from mailbot_api.db.queries import ACTION_GRANT_INSERT

    db_path = _setup(tmp_path)
    # Seed a pending_grant row so the promotion would otherwise UPDATE 1 row.
    await _seed_pending_grant_row(db_path, action_type="delete")

    now = datetime.now(timezone.utc)
    expires_iso = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    minted_iso = now.isoformat().replace("+00:00", "Z")

    invalid_update = (
        "UPDATE pending_actions SET status = 'pending' "
        "WHERE nonexistent_column = ?"
    )

    import sqlite3 as _sqlite3

    with pytest.raises(_sqlite3.OperationalError):
        await execute_insert_and_write(
            db_path,
            ACTION_GRANT_INSERT,
            ("delete", json.dumps(["e-1"]), expires_iso, minted_iso),
            invalid_update,
            ("delete",),
        )

    # Atomicity assertion: no grant row should exist (rolled back).
    with get_connection(db_path) as conn:
        grants = conn.execute("SELECT COUNT(*) FROM action_grants").fetchone()
        assert grants[0] == 0, (
            f"action_grants row leaked despite promotion failure — "
            f"transaction not atomic. Got {grants[0]} rows."
        )
    # And the pending_grant row stays in pending_grant (not promoted).
    with get_connection(db_path) as conn:
        statuses = conn.execute(
            "SELECT status FROM pending_actions WHERE status = 'pending_grant'",
        ).fetchall()
        assert len(statuses) == 1, (
            f"pending_grant row was promoted despite rollback — expected 1, got {len(statuses)}"
        )
