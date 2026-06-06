"""Story 6-19 — F29 closure: propose_action verb-shim error-time recovery.

5 unit tests covering AC-4 tests 1-5: the `INVALID_ACTION_TYPE` error path
on `mailbot_api/verbs/propose_action.py` carries the canonical 23
ActionType values inline (in the error message) AND as a structured
`valid_action_types` field on `ProposeActionError`, so an agent that
hallucinated a synonym (e.g., `SEND_EMAIL` instead of `send_reply`) can
self-correct in a single turn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.propose_action import propose_action


@pytest.fixture
async def _db_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(db_path: str, *, graph_id: str = "e1") -> None:
    """Seed an email row with the minimum columns needed for propose_action
    to reach its own validation paths (used by AC-4 test 4 to exercise a
    non-INVALID_ACTION_TYPE error code)."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-06-02T00:00:00Z", "s", "x@y.com", "b",
            "normal", "2026-06-02T00:01:00Z", "v1", 0.9, "qwen2.5:3b-instruct-q4_K_M",
        ),
    )


async def test_unknown_action_type_returns_invalid_action_type_code(
    _db_path: str,
) -> None:
    """AC-4.1 — `propose_action(action_type='SEND_EMAIL', ...)` refused with
    INVALID_ACTION_TYPE; offending value embedded in error message."""
    result = await propose_action(
        email_id="e1",
        action_type="SEND_EMAIL",
        db_path=_db_path,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "INVALID_ACTION_TYPE"
    # Forensic clarity — the offending value (the hallucinated string) must
    # appear in the message so a log scrape can correlate.
    assert "SEND_EMAIL" in result.error.message


async def test_invalid_action_type_error_carries_valid_action_types_field(
    _db_path: str,
) -> None:
    """AC-4.2 — the structured `valid_action_types` field carries the
    canonical 23 sorted snake_case values."""
    result = await propose_action(
        email_id="e1",
        action_type="SEND_EMAIL",
        db_path=_db_path,
    )
    assert result.error is not None
    assert result.error.valid_action_types is not None
    assert len(result.error.valid_action_types) == 23
    # Spot-check several known members.
    assert "send_reply" in result.error.valid_action_types
    assert "archive" in result.error.valid_action_types
    assert "delete" in result.error.valid_action_types
    assert "mark_read" in result.error.valid_action_types
    # Deterministic order.
    assert list(result.error.valid_action_types) == sorted(result.error.valid_action_types)
    # Matches the enum.
    assert set(result.error.valid_action_types) == {at.value for at in ActionType}
    # CR-2 (2026-06-06): the field is a tuple (immutable defense-in-depth),
    # not a list — mutation attempts surface as TypeError.
    assert isinstance(result.error.valid_action_types, tuple)


async def test_invalid_action_type_error_message_embeds_full_list(
    _db_path: str,
) -> None:
    """AC-4.3 — agents that read only the message (not the structured field)
    still get the recovery hint inline."""
    result = await propose_action(
        email_id="e1",
        action_type="garbage",
        db_path=_db_path,
    )
    assert result.error is not None
    # Several canonical values appear in the message.
    assert "send_reply" in result.error.message
    assert "archive" in result.error.message
    assert "delete" in result.error.message


async def test_valid_action_types_field_is_none_on_other_error_codes(
    _db_path: str,
) -> None:
    """AC-4.4 — the field is scoped to INVALID_ACTION_TYPE ONLY. Other
    error codes (EMAIL_NOT_FOUND, etc.) MUST NOT carry the hint — the
    contract is "hint relevant to the specific failure mode only"."""
    # Valid action_type but bogus email_id → EMAIL_NOT_FOUND from the
    # actions/propose.py impl (NOT from the verb shim). Use a Tier-3
    # action (`delete`) so the change_marker capture path runs and surfaces
    # EMAIL_NOT_FOUND on the missing row. Tier-1/Tier-2 skip change_marker
    # capture and would silently queue against the nonexistent id.
    result = await propose_action(
        email_id="nonexistent-email-id",
        action_type="delete",
        db_path=_db_path,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "EMAIL_NOT_FOUND"
    # Field absent (None) — the hint is NOT polluted on this error path.
    assert result.error.valid_action_types is None


@pytest.mark.parametrize(
    "bad_action_type",
    [
        # CR-3 (2026-06-06): parametrize list now covers ALL entries in
        # _ACTION_TYPE_SYNONYMS_REJECTED (mcp_server.py) plus the obvious
        # UPPER_SNAKE / kebab-case / camelCase variants. Keeps the test's
        # synonym coverage in sync with the anti-anchor list.
        "SEND_REPLY",       # UPPER_SNAKE enum name (a common foot-gun)
        "send-reply",       # kebab-case variant (in synonyms_rejected)
        "sendReply",        # camelCase variant (in synonyms_rejected)
        "SEND_EMAIL",       # F29's actual hallucination (in synonyms_rejected)
        "send_email",       # lowercase F29 variant (in synonyms_rejected, CR-3)
        "send",             # bare verb (in synonyms_rejected, CR-3)
        "reply",            # bare verb (in synonyms_rejected)
        "delete_email",     # imagined synonym (in synonyms_rejected)
        "trash",            # synonym (in synonyms_rejected)
        "remove",           # synonym (in synonyms_rejected, CR-3)
    ],
)
async def test_known_synonyms_all_rejected(
    bad_action_type: str, _db_path: str,
) -> None:
    """AC-4.5 — parametrized: every known synonym / variant rejects with
    INVALID_ACTION_TYPE + populated valid_action_types. Locks in the
    rejection invariant against future enum drift OR accidental case-
    insensitivity / synonym-acceptance regressions."""
    result = await propose_action(
        email_id="e1",
        action_type=bad_action_type,
        db_path=_db_path,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "INVALID_ACTION_TYPE"
    assert result.error.valid_action_types is not None
    assert len(result.error.valid_action_types) == 23
    assert bad_action_type in result.error.message
    # CR-6 (2026-06-06): explicit not-in assertion — self-documents that
    # the synonym MUST NOT appear in valid_action_types, regardless of
    # how the 23-length guard otherwise constrains the list.
    assert bad_action_type not in result.error.valid_action_types
