"""Story 7-0-f30-f31 — `ProposeActionOut.requires_grant` +
`requires_per_action_confirmation` signal-field unit tests.

AC §4 — parameterized verification that the new boolean fields on
`ProposeActionOut` correctly reflect the registry-derived contract:

  - Tier-1 LOCAL: requires_grant=False, requires_per_action_confirmation=False
  - Tier-2 BATCH: requires_grant=True,  requires_per_action_confirmation=False
  - Tier-3 SEND-family: requires_grant=True, requires_per_action_confirmation=True
  - Tier-3 DELETE (non-SEND): requires_grant=True, requires_per_action_confirmation=False

AC §5 — pragmatic F31 guardrail: the SEND-family per-action-confirmation signal
is the in-band hint Hermes needs to recognize the next "send" user turn as a
confirmation of the existing pending row rather than a fresh propose
(F31 reproduction shape).

Per the Middleware-Real-Bootstrap MailBot reframing: tests use a real on-disk
SQLite via tmp_path with the full migration chain applied.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations


async def _seed_email(db_path: str, *, graph_id: str = "e-1") -> None:
    """Minimal email row with a non-NULL change_marker so Tier-3 propose can
    capture it. Mirror of the helper in test_propose_action.py."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-13T00:00:00Z", "s", "a@b.c", "cm-v1", None),
    )


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


# ---- Tier-1 LOCAL ------------------------------------------------------------


@pytest.mark.parametrize(
    "action_type",
    [
        ActionType.MARK_READ,
        ActionType.MARK_UNREAD,
        ActionType.ADD_LOCAL_CATEGORY,
        ActionType.REMOVE_LOCAL_CATEGORY,
        ActionType.MOVE_TO_TRIAGE_FOLDER,
    ],
)
async def test_tier_1_local_no_grant_no_confirmation(
    tmp_path: Path, action_type: ActionType,
) -> None:
    """Tier-1 LOCAL actions auto-approve per FR-5.1; no grant needed, no
    per-action confirmation needed."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action(
        "e-1", action_type, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 1
    assert out.requires_grant is False
    assert out.requires_per_action_confirmation is False


# ---- Tier-2 BATCH ------------------------------------------------------------


@pytest.mark.parametrize(
    "action_type",
    [
        ActionType.ARCHIVE,
        ActionType.MARK_JUNK,
        ActionType.MOVE_TO_USER_FOLDER,
        ActionType.UNSUBSCRIBE,
        ActionType.MOVE_TO_INBOX,
    ],
)
async def test_tier_2_batch_grant_yes_confirmation_no(
    tmp_path: Path, action_type: ActionType,
) -> None:
    """Tier-2 BATCH actions are grant-gated (FR-5.2) but a single mint_grant
    covers N actions of the same type — no per-action re-confirmation."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action(
        "e-1", action_type, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 2
    assert out.requires_grant is True
    assert out.requires_per_action_confirmation is False


# ---- Tier-3 SEND-family (AC §5 — F31 pragmatic guardrail) --------------------


@pytest.mark.parametrize(
    "action_type",
    [
        ActionType.SEND_REPLY,
        ActionType.SEND_FORWARD,
        ActionType.REPLY_TO_INACTIVE_THREAD,
    ],
)
async def test_send_family_signals_per_action_confirmation(
    tmp_path: Path, action_type: ActionType,
) -> None:
    """AC §5 (F31 pragmatic guardrail) — every SEND-family `propose_action`
    success-return MUST set requires_per_action_confirmation=True AND
    requires_grant=True. This is the in-band signal Hermes consumes to
    recognize the next user-turn "send" as confirming the existing pending
    row (avoiding the F31 duplicate-pending_actions failure mode).

    SEND_NEW_EMAIL is covered separately (email_id=None path)."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action(
        "e-1", action_type, db_path=db_path,
    )
    assert out.ok is True, f"unexpected refusal: {out.error}"
    assert out.tier == 3
    assert out.requires_grant is True
    assert out.requires_per_action_confirmation is True
    # Belt-and-suspenders: status should be cooling_off for SEND-family
    # (Story 4-6 cool-down window is the cancel-affordance — confirms F31
    # contract pre-condition that the existing pending row is the canonical
    # target for the next "send" confirmation turn).
    assert out.status == "cooling_off"


async def test_send_new_email_email_less_path_signals_per_action_confirmation(
    tmp_path: Path,
) -> None:
    """SEND_NEW_EMAIL is the compose-from-scratch path with email_id=None
    (EMAIL_LESS_ACTIONS membership per Story 4-2 CR-1). The signal-field
    contract must hold identically — Hermes needs the same in-band hint."""
    db_path = _setup(tmp_path)
    # No email seeded — SEND_NEW_EMAIL is email-less.
    out = await propose_action(
        None, ActionType.SEND_NEW_EMAIL, db_path=db_path,
    )
    assert out.ok is True, f"unexpected refusal: {out.error}"
    assert out.tier == 3
    assert out.requires_grant is True
    assert out.requires_per_action_confirmation is True
    assert out.status == "cooling_off"


# ---- Tier-3 non-SEND ---------------------------------------------------------


async def test_delete_grant_yes_confirmation_no(tmp_path: Path) -> None:
    """DELETE is Tier-3 non-SEND. Requires a grant (like every Tier-3) but
    does NOT need per-action confirmation (Tier-2/3 grant semantics — the
    sensitivity-token handshake from Story 4-1 CR-2 covers the
    destructive-touch invariant separately)."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action(
        "e-1", ActionType.DELETE, db_path=db_path,
    )
    assert out.ok is True, f"unexpected refusal: {out.error}"
    assert out.tier == 3
    assert out.requires_grant is True
    assert out.requires_per_action_confirmation is False


@pytest.mark.parametrize(
    "action_type",
    [
        ActionType.MODIFY_INBOX_RULE,
        ActionType.MODIFY_OUTLOOK_FILTER,
        ActionType.TOUCH_DELEGATED_MAILBOX,
    ],
)
async def test_tier_3_email_less_admin_grant_yes_confirmation_no(
    tmp_path: Path, action_type: ActionType,
) -> None:
    """Tier-3 admin-style email-less actions: grant-gated but no per-action
    confirmation (they're not in the SEND family). Per propose.py's
    `elif tier == 3` email-less branch, non-SEND email-less Tier-3 actions
    land at `status="pending"` (NOT `pending_grant` — that's Tier-2's
    initial routing). The grant requirement is enforced lazily at drain
    time via the drainer's `is_grant_valid()` check (Story 4-4), not at
    propose-insert time. CR-6 (2026-06-13, sonnet-4-6 review): docstring
    previously claimed `pending_grant` initial status; corrected here."""
    db_path = _setup(tmp_path)
    out = await propose_action(
        None, action_type, db_path=db_path,
    )
    assert out.ok is True, f"unexpected refusal: {out.error}"
    assert out.tier == 3
    assert out.requires_grant is True
    assert out.requires_per_action_confirmation is False


# ---- Refusal path defaults ---------------------------------------------------


async def test_refusal_returns_default_false_signals(tmp_path: Path) -> None:
    """ProposeActionOut on the refusal path (ok=False) returns the new
    fields at their default-False values. The signal is meaningful only on
    success; a refusal carries no in-band recovery contract for these
    specific booleans (the recovery hint lives on
    ProposeActionError.valid_action_types per Story 6-19)."""
    db_path = _setup(tmp_path)
    # Tier-0 refusal — never enters pending_actions.
    out = await propose_action(
        None, ActionType.READ_SQL, db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.requires_grant is False
    assert out.requires_per_action_confirmation is False
