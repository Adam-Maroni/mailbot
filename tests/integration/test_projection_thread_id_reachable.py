"""Story 10.5.3 AC-2 (F-10-4-3) — get_thread must be reachable from chat.

Epic 10's walk found `get_thread` unreachable from the chat surface: the verb
works given a `thread_id`, but the agent-visible `EmailProjection` (the list
rows returned by `find_emails`) carried NO `thread_id`, so the model had no way
to discover a thread_id to pass to `get_thread`. The result was
THREAD_NOT_FOUND 2/2 in the live walk.

The fix adds `thread_id` to the projection so a `find_emails` result row
carries the thread_id the model then hands to `get_thread` — closing the
discovery gap. `emails.thread_id` already exists; the projection just never
surfaced it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.find_emails import find_emails
from mailbot_api.verbs.get_thread import get_thread
from mailbot_api.verbs.schemas import EmailProjection, FindEmailsFilter


@pytest.fixture()
async def db_path(tmp_path: Path) -> str:
    db = tmp_path / "proj_thread.db"
    apply_pending_migrations(str(db))
    return str(db)


async def _seed_email(
    db_path: str,
    graph_id: str,
    *,
    thread_id: str | None,
    received_at: str = "2026-07-10T12:00:00Z",
) -> None:
    await execute_write(
        db_path,
        (
            "INSERT INTO emails (graph_id, received_at, from_address, subject, "
            "sensitivity, sensitivity_at, thread_id, change_marker) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            graph_id,
            received_at,
            "alice@example.com",
            "Meeting thread",
            "normal",
            received_at,
            thread_id,
            f"cm-{graph_id}",
        ),
    )


async def _seed_thread(db_path: str, thread_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO threads (id, last_message_at, message_count, thread_continuity_note) "
        "VALUES (?, ?, ?, ?)",
        (thread_id, "2026-07-10T12:00:00Z", 2, "ongoing scheduling thread"),
    )


def test_email_projection_has_thread_id_field() -> None:
    """The projection schema MUST carry a `thread_id` field — without it,
    get_thread is undiscoverable from chat (F-10-4-3)."""
    assert "thread_id" in EmailProjection.model_fields, (
        "EmailProjection has no thread_id — get_thread stays unreachable from "
        "chat (the model can't discover a thread_id from a find_emails row)"
    )


@pytest.mark.asyncio
async def test_find_emails_row_thread_id_round_trips_into_get_thread(db_path: str) -> None:
    """A find_emails result row carries thread_id; feeding that thread_id to
    get_thread returns the thread's projections — the exact chat-path
    round-trip that was broken (F-10-4-3)."""
    await _seed_thread(db_path, "t-100")
    await _seed_email(db_path, "e-1", thread_id="t-100", received_at="2026-07-10T12:00:00Z")
    await _seed_email(db_path, "e-2", thread_id="t-100", received_at="2026-07-10T13:00:00Z")

    found = await find_emails(FindEmailsFilter(), db_path=db_path, limit=25)
    assert found.ok
    assert found.projections
    # Every projection must expose the thread_id the model needs.
    thread_ids = {p.thread_id for p in found.projections}
    assert "t-100" in thread_ids, f"thread_id not surfaced on projections: {thread_ids}"

    # Round-trip: model reads thread_id off a row → calls get_thread.
    discovered = next(p.thread_id for p in found.projections if p.thread_id == "t-100")
    thread = await get_thread(discovered, db_path=db_path)
    assert thread.ok
    assert len(thread.projections) == 2
    # get_thread's own projections carry thread_id too (shared column list).
    assert all(p.thread_id == "t-100" for p in thread.projections)
