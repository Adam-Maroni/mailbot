"""Unit-style tests for observability/audit.py (Story 2-1).

Per the MailBot Middleware-Real-Bootstrap reframing (Step 2.4.7): tests hit
a real on-disk SQLite (`tmp_path`) with real migrations applied. No mocked
DB layer — that would shortcut exactly the wiring this story is about
(`record_router_call` → `execute_write` → SQLite).

pytest-asyncio asyncio_mode = "auto".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow, record_router_call


def _fresh_db_with_migrations(tmp_path: Path) -> str:
    """Apply every migration through 006_router_calls.sql to a temp DB."""
    db_path = str(tmp_path / "test.db")
    applied = apply_pending_migrations(db_path)
    # Sanity check — 006 must be in the list, otherwise the rest of the test
    # is meaningless (the table won't exist).
    assert any(name.startswith("006_router_calls") for name in applied), (
        f"expected 006_router_calls.sql to apply; got {applied}"
    )
    return db_path


async def test_record_router_call_writes_row_with_all_fields(tmp_path: Path) -> None:
    db_path = _fresh_db_with_migrations(tmp_path)

    row = RouterCallRow(
        ts="2026-06-01T12:34:56Z",
        task_type="coarse_class",
        prompt_version="v1",
        model_chosen="qwen2.5:3b-instruct-q4_K_M",
        model_chosen_reason="policy",
        tokens_in=120,
        tokens_out=45,
        cached_tokens_in=0,
        cost_usd_estimated=0.0,
        latency_ms=812,
        outcome="ok",
        caller_verb="ingest_pipeline",
        caller_origin="verb-ask-router",
        email_id="graph-msg-xyz",
        sensitivity_grant_id=None,
        sensitivity_grant_minted_at=None,
    )

    await record_router_call(row, db_path=db_path)

    fetched = await fetchone(
        db_path,
        "SELECT ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
        "tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
        "outcome, caller_verb, caller_origin, email_id, "
        "sensitivity_grant_id, sensitivity_grant_minted_at "
        "FROM router_calls WHERE task_type = ?",
        ("coarse_class",),
    )
    assert fetched is not None
    (
        ts,
        task_type,
        prompt_version,
        model_chosen,
        model_chosen_reason,
        tokens_in,
        tokens_out,
        cached_tokens_in,
        cost_usd_estimated,
        latency_ms,
        outcome,
        caller_verb,
        caller_origin,
        email_id,
        sensitivity_grant_id,
        sensitivity_grant_minted_at,
    ) = fetched

    assert ts == "2026-06-01T12:34:56Z"
    assert task_type == "coarse_class"
    assert prompt_version == "v1"
    assert model_chosen == "qwen2.5:3b-instruct-q4_K_M"
    assert model_chosen_reason == "policy"
    assert tokens_in == 120
    assert tokens_out == 45
    assert cached_tokens_in == 0
    assert cost_usd_estimated == 0.0
    assert latency_ms == 812
    assert outcome == "ok"
    assert caller_verb == "ingest_pipeline"
    assert caller_origin == "verb-ask-router"
    assert email_id == "graph-msg-xyz"
    assert sensitivity_grant_id is None
    assert sensitivity_grant_minted_at is None


async def test_record_router_call_default_ts_is_utc_z(tmp_path: Path) -> None:
    """Constructing a RouterCallRow without `ts` defaults to a Z-suffixed UTC string."""
    db_path = _fresh_db_with_migrations(tmp_path)
    row = RouterCallRow(
        task_type="sensitivity_class",
        prompt_version="v1",
        model_chosen="qwen2.5:3b-instruct-q4_K_M",
        model_chosen_reason="policy",
        outcome="ok",
    )

    assert row.ts.endswith("Z")
    # ISO-8601 second-precision: 2026-06-01T12:34:56Z is 20 characters.
    assert len(row.ts) == 20

    await record_router_call(row, db_path=db_path)
    fetched = await fetchone(
        db_path,
        "SELECT ts FROM router_calls WHERE task_type = ?",
        ("sensitivity_class",),
    )
    assert fetched is not None
    assert fetched[0] == row.ts  # round-trip with no timezone loss


async def test_record_router_call_caller_origin_defaults_to_unknown(tmp_path: Path) -> None:
    """The placeholder default from AR-D2-2 is `unknown` until Story 2-10."""
    db_path = _fresh_db_with_migrations(tmp_path)
    row = RouterCallRow(
        task_type="summary_short",
        prompt_version="v1",
        model_chosen="claude-haiku-4-5-20251001",
        model_chosen_reason="policy",
        outcome="ok",
    )
    assert row.caller_origin == "unknown"

    await record_router_call(row, db_path=db_path)
    fetched = await fetchone(
        db_path,
        "SELECT caller_origin FROM router_calls WHERE task_type = ?",
        ("summary_short",),
    )
    assert fetched is not None
    assert fetched[0] == "unknown"


async def test_record_router_call_escalated_from_reason_accepted(tmp_path: Path) -> None:
    """The `escalated_from_<X>` parameterized form passes validation."""
    db_path = _fresh_db_with_migrations(tmp_path)
    row = RouterCallRow(
        task_type="draft_reply",
        prompt_version="v1",
        model_chosen="claude-opus-4-7",
        model_chosen_reason="escalated_from_claude-haiku-4-5-20251001",
        outcome="escalated",
    )
    await record_router_call(row, db_path=db_path)
    rows = await fetchall(
        db_path,
        "SELECT model_chosen_reason FROM router_calls WHERE task_type = ?",
        ("draft_reply",),
    )
    assert len(rows) == 1
    assert rows[0][0] == "escalated_from_claude-haiku-4-5-20251001"


@pytest.mark.parametrize(
    "bad_reason",
    [
        "bogus",
        "escalated",  # missing _from_<X> tail
        "ESCALATED_FROM_QWEN",  # uppercase doesn't match the literal set
        "",
    ],
)
def test_router_call_row_rejects_bogus_model_chosen_reason(bad_reason: str) -> None:
    """Pydantic should refuse any reason outside the closed Literal set + escalated_from_ regex."""
    with pytest.raises(ValidationError):
        RouterCallRow(
            task_type="coarse_class",
            prompt_version="v1",
            model_chosen="qwen2.5:3b-instruct-q4_K_M",
            model_chosen_reason=bad_reason,
            outcome="ok",
        )


@pytest.mark.parametrize(
    "bad_outcome",
    ["weird", "OK", "success", "failure", ""],
)
def test_router_call_row_rejects_bogus_outcome(bad_outcome: str) -> None:
    """Outcome is Literal['ok', 'retry_recovered', 'escalated', 'failed']."""
    with pytest.raises(ValidationError):
        RouterCallRow(
            task_type="coarse_class",
            prompt_version="v1",
            model_chosen="qwen2.5:3b-instruct-q4_K_M",
            model_chosen_reason="policy",
            outcome=bad_outcome,
        )


# ---- Story 2-1 review fix R10: ts ISO-8601 format validation ----


@pytest.mark.parametrize(
    "bad_ts",
    [
        "not-a-timestamp",
        "2026-06-01 12:34:56",            # space, no T
        "2026-06-01T12:34:56",            # missing Z
        "2026-06-01T12:34:56+00:00",      # +00:00 instead of Z
        "2026-06-01T12:34:56.123Z",       # fractional seconds
        "20260601T123456Z",               # no dashes
        "",
    ],
)
def test_router_call_row_rejects_malformed_ts(bad_ts: str) -> None:
    """Malformed ts must fail Pydantic validation — `ix_router_calls_ts` depends on it."""
    with pytest.raises(ValidationError):
        RouterCallRow(
            ts=bad_ts,
            task_type="coarse_class",
            prompt_version="v1",
            model_chosen="qwen2.5:3b-instruct-q4_K_M",
            model_chosen_reason="policy",
            outcome="ok",
        )


def test_router_call_row_accepts_default_factory_ts(tmp_path: Path) -> None:
    """The default factory produces a valid ts that passes the format validator."""
    row = RouterCallRow(
        task_type="coarse_class",
        prompt_version="v1",
        model_chosen="qwen2.5:3b-instruct-q4_K_M",
        model_chosen_reason="policy",
        outcome="ok",
    )
    # Default ts should match the validated format.
    assert row.ts.endswith("Z")
    assert len(row.ts) == 20


# ---- Story 2-1 review fix R7: defensive DB-write failure path ----


async def test_record_router_call_swallows_db_failure_without_raising(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A DB write failure must NOT propagate out of record_router_call —
    Story 2-4 will call this in `ask_router`'s finally block; masking the
    original Router error with a secondary audit-write error is forbidden."""
    # Point at a path that cannot be opened (a directory that doesn't exist).
    nonexistent_db = str(tmp_path / "no" / "such" / "directory" / "test.db")

    row = RouterCallRow(
        task_type="coarse_class",
        prompt_version="v1",
        model_chosen="qwen2.5:3b-instruct-q4_K_M",
        model_chosen_reason="policy",
        outcome="ok",
    )

    # MUST NOT raise — the test failing here is the regression we're guarding against.
    import logging as _logging

    with caplog.at_level(_logging.WARNING, logger="mailbot_api.observability.audit"):
        await record_router_call(row, db_path=nonexistent_db)

    # Validate the warning was emitted with the expected event tag.
    assert any(
        "router_calls write failed" in record.message
        and getattr(record, "event", None) == "audit.write.failed"
        for record in caplog.records
    ), f"Expected audit.write.failed warning. Got: {[r.message for r in caplog.records]}"
