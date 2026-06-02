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
from mailbot_api.db.connection import get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.mint_grant import mint_grant as mint_grant_shim


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


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
