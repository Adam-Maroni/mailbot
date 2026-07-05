"""Story 4-2 — propose_action unit tests.

Per the Middleware-Real-Bootstrap MailBot reframing: tests use a real on-disk
SQLite via tmp_path with the full migration chain applied, NOT a mocked DB.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pytest

from mailbot_api.actions.propose import (
    propose_action,
)
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.propose_action import propose_action as propose_action_shim

# ---- shared fixtures ----------------------------------------------------------

async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    change_marker: str = "cm-v1",
    deleted_at: str | None = None,
) -> None:
    """Minimal INSERT into emails — only the columns 4-2 reads."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com",
         change_marker, deleted_at),
    )


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


def _read_row(db_path: str, action_id: int) -> tuple:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, email_id, action_type, tier, payload, status, "
            "change_marker_at_propose, retry_count, budget_consumed "
            "FROM pending_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
    assert row is not None
    return row


# ---- AC-7 §2: Tier-0 refusal --------------------------------------------------


async def test_tier_0_action_refused_at_verb_boundary(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await propose_action(
        None, ActionType.READ_SQL, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "TIER_0_NOT_QUEUEABLE"
    assert out.tier == 0
    assert out.action_id is None


# ---- AC-7 §3: tier-promotion guard --------------------------------------------


async def test_tier_promotion_payload_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action(
        "e-1", ActionType.MARK_READ, payload={"tier": 0}, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "TIER_PROMOTION_ATTEMPT"


# ---- Story 10-2: reserved revert marker key ------------------------------------


async def test_reserved_revert_marker_payload_key_refused(tmp_path: Path) -> None:
    """Story 10-2: `revert_of_action_id` is reserved for the reverter — it
    makes the drainer bypass the lenient target_deleted gate, so an agent
    must not be able to set it via propose_action (the reverter inserts
    directly via PENDING_ACTION_INSERT and is unaffected)."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "f-1", "revert_of_action_id": 7},
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "INVALID_PAYLOAD"
    assert "revert_of_action_id" in out.error.message


# ---- AC-11: invalid action_type via shim --------------------------------------


async def test_invalid_action_type_string_refused_by_verb_shim(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await propose_action_shim(
        "e-1", "fake_action_type_xyz", db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "INVALID_ACTION_TYPE"
    assert "fake_action_type_xyz" in out.error.message


# ---- AC-8: email-scope validation ---------------------------------------------


async def test_email_scoped_action_without_email_id_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await propose_action(
        None, ActionType.MARK_READ, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "INVALID_PAYLOAD"


async def test_email_less_action_without_email_id_accepted(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await propose_action(
        None,
        ActionType.MODIFY_INBOX_RULE,
        payload={"rule": "auto-archive newsletters"},
        db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 3
    assert out.status == "pending"
    assert out.action_id is not None
    row = _read_row(db_path, out.action_id)
    assert row[1] is None  # email_id IS NULL
    assert row[6] is None  # change_marker_at_propose IS NULL (no email to capture from)


async def test_send_new_email_without_email_id_accepted(tmp_path: Path) -> None:
    """CR-1 (4-2 review): SEND_NEW_EMAIL is compose-from-scratch — accepts
    email_id=None and goes through the SEND-family cooling-off branch even
    without a source email."""
    db_path = _setup(tmp_path)
    out = await propose_action(
        None,
        ActionType.SEND_NEW_EMAIL,
        payload={"to": ["new@example.com"], "subject": "Hi", "body": "..."},
        db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 3
    assert out.status == "cooling_off"  # SEND family → cooling_off even when email-less
    assert out.action_id is not None
    row = _read_row(db_path, out.action_id)
    assert row[1] is None
    assert row[6] is None  # no change_marker (no source email)


# ---- AC-7 §5-§8: per-tier happy paths -----------------------------------------


async def test_tier_1_mark_read_happy_path(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action(
        "e-1", ActionType.MARK_READ, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 1
    assert out.status == "pending"
    row = _read_row(db_path, out.action_id)
    assert row[2] == "mark_read"
    assert row[3] == 1
    assert row[5] == "pending"
    assert row[6] is None  # no change_marker for Tier 1


async def test_tier_2_archive_happy_path(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action(
        "e-1", ActionType.ARCHIVE, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 2
    assert out.status == "pending_grant"
    row = _read_row(db_path, out.action_id)
    assert row[5] == "pending_grant"
    assert row[6] is None  # no change_marker for Tier 2


async def test_tier_3_delete_happy_path_captures_change_marker(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-del", change_marker="cm-DEL-v1")
    out = await propose_action(
        "e-del", ActionType.DELETE, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 3
    assert out.status == "pending"  # DELETE skips cooling-off
    row = _read_row(db_path, out.action_id)
    assert row[6] == "cm-DEL-v1"  # change_marker captured


async def test_tier_3_send_reply_happy_path_goes_to_cooling_off(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-snd", change_marker="cm-SND-v7")
    out = await propose_action(
        "e-snd",
        ActionType.SEND_REPLY,
        payload={"body": "Thanks, I'll get back to you.", "to": ["bob@example.com"]},
        db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 3
    assert out.status == "cooling_off"  # SEND family routes here
    row = _read_row(db_path, out.action_id)
    assert row[6] == "cm-SND-v7"


# ---- AC-7 §5: email-not-found / email-deleted ---------------------------------


async def test_tier_3_send_against_unknown_email_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await propose_action(
        "nonexistent-eid", ActionType.SEND_REPLY, payload={"body": "x"}, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "EMAIL_NOT_FOUND"


async def test_tier_3_against_never_synced_email_refused(tmp_path: Path) -> None:
    """CR-5 (4-2 review): row exists in emails but change_marker IS NULL
    (sync worker hasn't recorded a changeKey yet) → distinct
    EMAIL_NEVER_SYNCED error so the operator can disambiguate from missing-row.
    """
    db_path = _setup(tmp_path)
    # Insert a row with change_marker explicitly NULL (None passed through).
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, NULL, NULL)",
        ("e-never-synced", "2026-06-02T00:00:00Z", "Subject", "alice@example.com"),
    )
    out = await propose_action(
        "e-never-synced", ActionType.DELETE, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "EMAIL_NEVER_SYNCED"
    assert "NULL change_marker" in out.error.message


async def test_tier_3_against_soft_deleted_email_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(
        db_path,
        graph_id="e-dead",
        change_marker="cm-v1",
        deleted_at="2026-06-01T00:00:00Z",
    )
    out = await propose_action(
        "e-dead", ActionType.DELETE, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "EMAIL_DELETED"


# ---- AC-7 §9: payload serialization round-trip --------------------------------


async def test_payload_serialization_round_trips(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-v1")
    payload = {"body": "Hi Alice", "to": ["alice@example.com"], "extra_int": 42}
    out = await propose_action(
        "e-1", ActionType.SEND_REPLY, payload=payload, db_path=db_path,
    )
    assert out.ok is True
    row = _read_row(db_path, out.action_id)
    payload_json = row[4]
    deserialized = json.loads(payload_json)
    assert deserialized == payload


# ---- AC-9: structured logging -------------------------------------------------


async def test_action_proposed_log_line_emitted_with_safe_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-log", change_marker="cm-v1")
    with caplog.at_level(logging.INFO, logger="mailbot_api.actions.propose"):
        out = await propose_action(
            "e-log",
            ActionType.SEND_REPLY,
            payload={"body": "SECRET-CONTENT-SHOULD-NOT-LOG", "to": ["x@y.com"]},
            db_path=db_path,
        )
    assert out.ok is True
    proposed_records = [r for r in caplog.records if getattr(r, "event", None) == "action.proposed"]
    assert len(proposed_records) == 1
    rec = proposed_records[0]
    assert rec.action_id == out.action_id  # type: ignore[attr-defined]
    assert rec.action_type == "send_reply"  # type: ignore[attr-defined]
    assert rec.tier == 3  # type: ignore[attr-defined]
    assert rec.status == "cooling_off"  # type: ignore[attr-defined]
    assert rec.email_id == "e-log"  # type: ignore[attr-defined]
    # Critically: the body content must NOT appear anywhere in the log record.
    assert "SECRET-CONTENT-SHOULD-NOT-LOG" not in str(rec.__dict__)
    assert "SECRET-CONTENT-SHOULD-NOT-LOG" not in rec.getMessage()


async def test_action_propose_refused_log_line_emitted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = _setup(tmp_path)
    with caplog.at_level(logging.WARNING, logger="mailbot_api.actions.propose"):
        out = await propose_action(None, ActionType.READ_SQL, db_path=db_path)
    assert out.ok is False
    refused_records = [
        r for r in caplog.records if getattr(r, "event", None) == "action.propose.refused"
    ]
    assert len(refused_records) == 1
    rec = refused_records[0]
    assert rec.code == "TIER_0_NOT_QUEUEABLE"  # type: ignore[attr-defined]
    assert rec.action_type == "read_sql"  # type: ignore[attr-defined]
    assert rec.tier_attempted == 0  # type: ignore[attr-defined]


# ---- AC-12 schema CHECK constraint reachable from direct SQL ------------------


def test_check_constraint_on_action_type_blocks_direct_insert(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_actions (action_type, tier, payload, proposed_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                ("bogus_action", 1, "{}", "2026-06-02T00:00:00Z", "pending"),
            )
