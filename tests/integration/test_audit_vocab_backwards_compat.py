"""Integration test for Story 9.2 AC-7: forward-only vocabulary contract.

Pre-9.2 ``router_calls`` rows carry the OLD vocabulary:
    ``"policy"``, ``"override"``, ``"degraded"``, ``"response_cache_hit"``,
    ``"force_override"``, ``"escalated_from_<X>"``

Post-9.2:
- Old rows REMAIN readable via raw SQL (no migration touches them)
- New row construction via ``RouterCallRow(model_chosen_reason=...)`` REJECTS
  the old vocab (validator only accepts the four AC-2 shapes)
- The Story 9.9 report renderer's WHERE clause must cover BOTH vocabularies
  via ``WHERE model_chosen_reason IN (?, ?)`` until the old values are retired

This test exercises that contract end-to-end against a real SQLite database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mailbot_api.db import connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow


@pytest.mark.asyncio
async def test_old_vocab_row_survives_raw_sql_insert_but_cannot_round_trip(
    tmp_path: Path,
) -> None:
    """An old-vocab row INSERTed via raw SQL is readable via SELECT (the column
    is still ``TEXT``; no schema migration changed that), but reconstructing
    a ``RouterCallRow`` from its values raises ``ValidationError``.
    """
    db_path = str(tmp_path / "backwards_compat.db")
    apply_pending_migrations(db_path)

    # Simulate a pre-9.2 audit row via raw SQL (NOT via record_router_call,
    # which uses the new validator). This mirrors what's already in production
    # SQLite from Epics 2–8.
    insert_sql = (
        "INSERT INTO router_calls ("
        "  ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
        "  tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, "
        "  latency_ms, outcome, caller_verb, caller_origin, email_id, "
        "  sensitivity_grant_id, sensitivity_grant_minted_at, "
        "  tool_calls_count, tool_calls_summary"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    old_vocab_row = (
        "2026-05-01T12:00:00.000000Z",  # ts
        "draft_reply",                   # task_type
        "v1",                            # prompt_version
        "claude-haiku-4-5-20251001",     # model_chosen
        "policy",                        # model_chosen_reason — OLD vocabulary
        100,                             # tokens_in
        50,                              # tokens_out
        0,                               # cached_tokens_in
        0.001,                           # cost_usd_estimated
        500,                             # latency_ms
        "ok",                            # outcome
        None,                            # caller_verb
        "unknown",                       # caller_origin
        None,                            # email_id
        None,                            # sensitivity_grant_id
        None,                            # sensitivity_grant_minted_at
        None,                            # tool_calls_count
        None,                            # tool_calls_summary
    )
    await connection.execute_write(db_path, insert_sql, old_vocab_row)

    # Read the row back via raw SQL — must succeed.
    select_sql = (
        "SELECT model_chosen_reason, task_type FROM router_calls "
        "WHERE task_type = ?"
    )
    row = await connection.fetchone(db_path, select_sql, ("draft_reply",))
    assert row is not None
    assert row[0] == "policy"
    assert row[1] == "draft_reply"

    # Reconstructing a RouterCallRow from the same value MUST fail —
    # the validator rejects the pre-9.2 vocabulary per AC-7's forward-only
    # contract.
    with pytest.raises(ValidationError, match="model_chosen_reason"):
        RouterCallRow(
            ts="2026-05-01T12:00:00.000000Z",
            task_type="draft_reply",
            prompt_version="v1",
            model_chosen="claude-haiku-4-5-20251001",
            model_chosen_reason="policy",  # old vocab
            outcome="ok",
        )


@pytest.mark.asyncio
async def test_old_escalated_from_value_survives_raw_but_blocks_reconstruction(
    tmp_path: Path,
) -> None:
    """The pre-9.2 ``escalated_from_<X>`` regex is rejected by the new
    validator. Old rows in SQLite stay readable; new construction fails.
    """
    db_path = str(tmp_path / "backwards_compat_escalated.db")
    apply_pending_migrations(db_path)

    insert_sql = (
        "INSERT INTO router_calls ("
        "  ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
        "  tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, "
        "  latency_ms, outcome, caller_verb, caller_origin, email_id, "
        "  sensitivity_grant_id, sensitivity_grant_minted_at, "
        "  tool_calls_count, tool_calls_summary"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    await connection.execute_write(
        db_path,
        insert_sql,
        (
            "2026-05-01T12:00:00.000000Z",
            "draft_reply",
            "v1",
            "claude-opus-4-7",
            "escalated_from_claude-haiku-4-5-20251001",  # OLD vocabulary
            100,
            50,
            0,
            0.05,
            800,
            "escalated",
            None,
            "unknown",
            None,
            None,
            None,
            None,
            None,
        ),
    )

    select_sql = "SELECT model_chosen_reason FROM router_calls WHERE task_type = ?"
    row = await connection.fetchone(db_path, select_sql, ("draft_reply",))
    assert row is not None
    assert row[0] == "escalated_from_claude-haiku-4-5-20251001"

    # New construction with the old value is rejected.
    with pytest.raises(ValidationError, match="model_chosen_reason"):
        RouterCallRow(
            ts="2026-05-01T12:00:00.000000Z",
            task_type="draft_reply",
            prompt_version="v1",
            model_chosen="claude-opus-4-7",
            model_chosen_reason="escalated_from_claude-haiku-4-5-20251001",
            outcome="escalated",
        )


@pytest.mark.asyncio
async def test_mixed_vocab_table_in_clause_query(tmp_path: Path) -> None:
    """Story 9.9's report-renderer pattern: a single ``WHERE IN (?, ?)`` query
    can cover BOTH old and new vocabulary for the same semantic category
    (here: "policy" old + "policy:draft_reply:default" new).
    """
    from mailbot_api.observability.audit import record_router_call

    db_path = str(tmp_path / "mixed_vocab.db")
    apply_pending_migrations(db_path)

    # Insert one OLD-vocab row via raw SQL.
    insert_sql = (
        "INSERT INTO router_calls ("
        "  ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
        "  tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, "
        "  latency_ms, outcome, caller_verb, caller_origin, email_id, "
        "  sensitivity_grant_id, sensitivity_grant_minted_at, "
        "  tool_calls_count, tool_calls_summary"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    await connection.execute_write(
        db_path,
        insert_sql,
        (
            "2026-05-01T12:00:00.000000Z",
            "draft_reply",
            "v1",
            "claude-haiku-4-5-20251001",
            "policy",  # old
            100, 50, 0, 0.001, 500, "ok",
            None, "unknown", None, None, None, None, None,
        ),
    )

    # Insert one NEW-vocab row via the production writer.
    new_row = RouterCallRow(
        ts="2026-06-13T12:00:00.000000Z",
        task_type="draft_reply",
        prompt_version="v1",
        model_chosen="claude-haiku-4-5-20251001",
        model_chosen_reason="policy:draft_reply:default",  # new
        tokens_in=120,
        tokens_out=55,
        outcome="ok",
    )
    await record_router_call(new_row, db_path=db_path)

    # Single IN-clause query returns BOTH rows.
    in_clause_sql = (
        "SELECT model_chosen_reason FROM router_calls "
        "WHERE model_chosen_reason IN (?, ?) ORDER BY ts"
    )
    rows = await connection.fetchall(
        db_path, in_clause_sql, ("policy", "policy:draft_reply:default")
    )
    assert len(rows) == 2
    assert rows[0][0] == "policy"
    assert rows[1][0] == "policy:draft_reply:default"
