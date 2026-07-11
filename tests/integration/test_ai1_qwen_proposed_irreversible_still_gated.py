"""Story AI-1 safety regression — the authorization gate keys on the ACTION's
tier, NEVER on the proposing model.

AI-1 opened the local Qwen model to tool-calling. The load-bearing safety
guarantee is: a qwen-proposed IRREVERSIBLE mailbox action (Tier-2/3 — e.g.
DELETE, SEND_REPLY, ARCHIVE) still requires the existing grant / sensitivity-
token confirmation before it can drain to Microsoft Graph, IDENTICAL to an
opus-proposed one.

The property holds "by construction" today:
  - ``propose_action`` has no ``model`` / ``caller`` / ``proposer`` parameter,
    so the proposing model is not an input to the authorization decision.
  - ``pending_actions`` has no model / caller-identity column, so the drainer
    (which re-derives authorization from ``action_type`` + ``tier`` + the
    grant / sensitivity-token tables) cannot distinguish a qwen-proposed row
    from an opus-proposed one.

These tests turn that construction into an EXPLICIT regression guard: a future
refactor that accidentally threads model-awareness into the propose verb or the
pending_actions schema — and thereby lets the gate vary by proposer — fails
loudly here.

Fixture style mirrors tests/unit/actions/test_propose_action.py (real on-disk
SQLite via tmp_path + full migration chain, NOT a mocked DB).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import (
    ACTION_PROPERTIES,
    ActionType,
    requires_grant,
    tier_for,
)
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations

# ---- fixtures (mirror test_propose_action.py) --------------------------------


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    change_marker: str = "cm-v1",
    deleted_at: str | None = None,
) -> None:
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


def _read_status(db_path: str, action_id: int) -> str:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (action_id,)
        ).fetchone()
    assert row is not None
    return str(row[0])


# Words that would signal the proposing model / caller identity has leaked into
# the authorization surface. ``model_config`` (Pydantic) and payload/params like
# ``change_marker`` are legitimate and must NOT trip this — hence exact-token
# checks against parameter names / column names, not substring scans of source.
_MODEL_IDENTITY_TOKENS = frozenset(
    {"model", "caller", "proposer", "proposed_by_model", "qwen", "opus", "llm"}
)


# ---- 1. behavioural: irreversible action lands in a confirmation-required state


async def test_qwen_proposed_irreversible_action_still_requires_confirmation(
    tmp_path: Path,
) -> None:
    """AI-1 core property (behavioural arm).

    DELETE is the strongest case: Tier-3 AND requires_sensitivity_token=True.
    A proposed DELETE must land in a state that REQUIRES a grant/confirmation
    before drain — it must NOT become auto-drainable. This outcome is derived
    purely from the action type; ``propose_action`` exposes no model input that
    a caller (qwen or opus) could vary to influence it (asserted structurally
    in the sibling tests below), so proving it for one proposer proves it for
    every proposer.

    ARCHIVE (Tier-2) is included as the cheap second irreversible case.
    """
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-del", change_marker="cm-DEL-v1")
    await _seed_email(db_path, graph_id="e-arc", change_marker="cm-ARC-v1")

    # DELETE — Tier-3, irreversible, sensitivity-token-gated.
    assert tier_for(ActionType.DELETE) == 3
    assert requires_grant(ActionType.DELETE) is True
    assert ACTION_PROPERTIES[ActionType.DELETE].requires_sensitivity_token is True
    assert ACTION_PROPERTIES[ActionType.DELETE].reversibility_window_hours is None

    del_out = await propose_action("e-del", ActionType.DELETE, db_path=db_path)
    assert del_out.ok is True
    assert del_out.tier == 3
    # Not auto-drainable: it carries the grant-required signal and its persisted
    # status is a not-yet-authorized state (DELETE skips cooling-off → "pending",
    # which the drainer still refuses without a valid grant).
    assert del_out.requires_grant is True
    assert del_out.status == "pending"
    assert del_out.action_id is not None
    assert _read_status(db_path, del_out.action_id) == "pending"

    # ARCHIVE — Tier-2, irreversible (no auto-revert window), grant-gated.
    assert tier_for(ActionType.ARCHIVE) == 2
    assert requires_grant(ActionType.ARCHIVE) is True
    assert ACTION_PROPERTIES[ActionType.ARCHIVE].reversibility_window_hours is None

    arc_out = await propose_action("e-arc", ActionType.ARCHIVE, db_path=db_path)
    assert arc_out.ok is True
    assert arc_out.tier == 2
    assert arc_out.requires_grant is True
    assert arc_out.status == "pending_grant"  # explicitly awaiting a grant
    assert arc_out.action_id is not None
    assert _read_status(db_path, arc_out.action_id) == "pending_grant"


# ---- 2. structural: the gate CANNOT distinguish qwen from opus ---------------


def test_propose_action_signature_carries_no_model_identity_parameter() -> None:
    """AI-1 property (structural arm — the verb).

    The authorization decision is model-independent because ``propose_action``
    accepts no parameter naming the proposing model / caller identity. If a
    future refactor threads e.g. ``model=`` or ``caller=`` into this signature,
    the gate could begin varying by proposer — this assertion fails first.
    """
    params = set(inspect.signature(propose_action).parameters)
    leaked = params & _MODEL_IDENTITY_TOKENS
    assert leaked == set(), (
        f"propose_action grew a model/caller-identity parameter {leaked!r}; "
        "the authorization gate must key on the action tier only, never on the "
        "proposing model (AI-1 safety property)."
    )


def test_pending_actions_schema_carries_no_model_identity_column(
    tmp_path: Path,
) -> None:
    """AI-1 property (structural arm — the persisted row).

    The drainer re-derives authorization from the ``pending_actions`` row +
    the grant / sensitivity-token tables. If the row carried a proposing-model
    / caller column, a future drainer change could gate on it. Assert no such
    column exists so the drainer physically cannot see who proposed the action.
    """
    db_path = _setup(tmp_path)
    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(pending_actions)")}

    leaked = {
        col
        for col in cols
        for token in _MODEL_IDENTITY_TOKENS
        # exact match or token as a whole underscore-delimited word segment,
        # so legitimate columns like "change_marker_at_propose" don't trip it.
        if col == token or token in col.split("_")
    }
    assert leaked == set(), (
        f"pending_actions grew a model/caller-identity column {leaked!r}; "
        "the drainer must not be able to distinguish a qwen-proposed row from "
        "an opus-proposed one (AI-1 safety property)."
    )
