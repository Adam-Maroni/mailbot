"""Story 4-7 — sensitivity-token registry + mint verb unit tests.

The registry is module-level state; each test calls `_clear_registry_for_tests`
in a fixture-style autouse to keep tests isolated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions import sensitivity_tokens as st
from mailbot_api.actions.sensitivity_tokens import (
    TOKEN_TTL,
    _clear_registry_for_tests,
    _registry_size_for_tests,
    consume,
    mint,
    sweep,
)
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.mint_sensitivity_token import mint_sensitivity_token


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    _clear_registry_for_tests()


# ---- registry primitives -----------------------------------------------------


def test_mint_returns_token_with_correct_shape() -> None:
    token = mint("e-1", "draft_reply")
    assert len(token.token_value) >= 32
    assert token.email_id == "e-1"
    assert token.task_type == "draft_reply"
    assert len(token.grant_id) == 16
    assert all(c in "0123456789abcdef" for c in token.grant_id)
    assert token.expires_at > datetime.now(timezone.utc)
    assert token.expires_at - token.minted_at == TOKEN_TTL


def test_consume_with_matching_args_returns_grant_id_and_removes_entry() -> None:
    token = mint("e-1", "draft_reply")
    assert _registry_size_for_tests() == 1
    grant_id = consume(token.token_value, "e-1", "draft_reply")
    assert grant_id == token.grant_id
    assert _registry_size_for_tests() == 0


def test_consume_with_mismatched_email_id_returns_none() -> None:
    token = mint("e-1", "draft_reply")
    grant_id = consume(token.token_value, "e-2", "draft_reply")
    assert grant_id is None
    # Token NOT removed on mismatch — operator can still try the correct (email, task).
    assert _registry_size_for_tests() == 1


def test_consume_with_mismatched_task_type_returns_none() -> None:
    token = mint("e-1", "draft_reply")
    grant_id = consume(token.token_value, "e-1", "wrong_task")
    assert grant_id is None
    assert _registry_size_for_tests() == 1


def test_consume_second_call_returns_none_single_use_semantics() -> None:
    token = mint("e-1", "draft_reply")
    first = consume(token.token_value, "e-1", "draft_reply")
    second = consume(token.token_value, "e-1", "draft_reply")
    assert first is not None
    assert second is None


def test_consume_after_expiry_returns_none() -> None:
    """Patch the registry clock to put the token in the past."""
    token = mint("e-1", "draft_reply")
    # Reach into the registry and rewrite the token to be expired. Frozen
    # model means we replace the entry.
    expired = st.SensitivityToken(
        token_value=token.token_value,
        email_id=token.email_id,
        task_type=token.task_type,
        expires_at=token.minted_at - timedelta(seconds=1),
        minted_at=token.minted_at,
        grant_id=token.grant_id,
    )
    st._REGISTRY[token.token_value] = expired
    grant_id = consume(token.token_value, "e-1", "draft_reply")
    assert grant_id is None
    # Expired entries are removed on the consume attempt.
    assert _registry_size_for_tests() == 0


def test_consume_unknown_token_returns_none() -> None:
    grant_id = consume("not-a-real-token", "e-1", "draft_reply")
    assert grant_id is None


def test_sweep_removes_only_expired() -> None:
    t1 = mint("e-1", "draft_reply")
    t2 = mint("e-2", "summary_short")
    # Manually expire t1.
    st._REGISTRY[t1.token_value] = st.SensitivityToken(
        token_value=t1.token_value,
        email_id=t1.email_id,
        task_type=t1.task_type,
        expires_at=t1.minted_at - timedelta(seconds=1),
        minted_at=t1.minted_at,
        grant_id=t1.grant_id,
    )
    removed = sweep()
    assert removed == 1
    assert _registry_size_for_tests() == 1
    # t2 still consumable.
    grant_id = consume(t2.token_value, "e-2", "summary_short")
    assert grant_id == t2.grant_id


def test_mint_produces_distinct_tokens_and_distinct_grant_ids() -> None:
    t1 = mint("e-1", "draft_reply")
    t2 = mint("e-1", "draft_reply")
    assert t1.token_value != t2.token_value
    assert t1.grant_id != t2.grant_id


# ---- mint_sensitivity_token verb ---------------------------------------------


def _setup_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email_with_sensitivity(
    db_path: str, *, graph_id: str, sensitivity: str | None,
) -> None:
    sensitivity_at = "2026-06-02T00:00:00Z" if sensitivity is not None else None
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "sensitivity, sensitivity_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com",
         sensitivity, sensitivity_at),
    )


async def test_mint_verb_refuses_for_confidential(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email_with_sensitivity(db_path, graph_id="e-conf", sensitivity="confidential")
    out = await mint_sensitivity_token("e-conf", "draft_reply", db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "SENSITIVITY_BLOCKS_API"


async def test_mint_verb_refuses_for_normal(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email_with_sensitivity(db_path, graph_id="e-norm", sensitivity="normal")
    out = await mint_sensitivity_token("e-norm", "draft_reply", db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "EMAIL_NOT_SENSITIVE"


async def test_mint_verb_succeeds_for_sensitive(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email_with_sensitivity(db_path, graph_id="e-sens", sensitivity="sensitive")
    out = await mint_sensitivity_token("e-sens", "draft_reply", db_path=db_path)
    assert out.ok is True
    assert out.token is not None
    assert out.grant_id is not None
    assert len(out.grant_id) == 16
    assert out.expires_at is not None
    assert out.expires_at.endswith("Z")


async def test_mint_verb_refuses_for_missing_email(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    out = await mint_sensitivity_token("nonexistent", "draft_reply", db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "EMAIL_NOT_FOUND"


async def test_mint_log_line_carries_grant_id_not_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email_with_sensitivity(db_path, graph_id="e-log", sensitivity="sensitive")
    with caplog.at_level(logging.INFO, logger="mailbot_api.verbs.mint_sensitivity_token"):
        out = await mint_sensitivity_token("e-log", "draft_reply", db_path=db_path)
    assert out.ok
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "sensitivity.token.minted")
    assert rec.grant_id == out.grant_id  # type: ignore[attr-defined]
    # The token value must NEVER appear in the log record.
    assert out.token not in str(rec.__dict__)
    assert out.token not in rec.getMessage()
