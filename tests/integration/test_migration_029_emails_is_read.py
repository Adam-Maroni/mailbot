"""Story 10.7.7 (AC-1) — migration 029 adds `emails.is_read`, the sync worker
populates it from Graph `isRead`, and `FindEmailsFilter.unread_only` filters on it.

The 10.7.6 clause-3 walk failed with a runaway `find_emails({})` loop because
"find my unread emails" had no backing query — `emails` had no read/unread
column (Graph exposes `isRead`, the sync worker never persisted it). This story
adds the truthful signal so the intent lands on a satisfiable query.

Per the Middleware-Real-Bootstrap MailBot reframing: every test runs against a
real on-disk SQLite (tmp_path) with the real migration chain applied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mailbot_api.db.connection import execute_write, fetchone, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.sync.sync_worker import _upsert_message
from mailbot_api.verbs.find_emails import find_emails
from mailbot_api.verbs.schemas import FindEmailsFilter


def test_unread_only_field_description_documents_capability() -> None:
    """Story 10.7.7: the unread_only field description documents the real filter
    capability (migration 029). An imperative "you MUST set this" phrasing was
    tried + REVERTED (F-10-7-7-W1 walk: Qwen-3B ignores the arg directive), so
    the description is a plain capability statement — it still names the unread
    use, without the disproven prompt-directive framing."""
    desc = (FindEmailsFilter.model_fields["unread_only"].description or "").lower()
    assert "unread" in desc


def test_find_emails_tool_description_mentions_unread_capability() -> None:
    """Story 10.7.7: the find_emails tool description still names unread as a
    filter capability, but the imperative unread_only directive + find_unread_
    emails neutralization were REVERTED (F-10-7-7-W1 walk proved the prompt
    lever doesn't move Qwen-3B's argument-population)."""
    from mailbot_api.mcp_server import _TOOL_DESCRIPTIONS  # noqa: PLC0415

    desc = _TOOL_DESCRIPTIONS["find_emails"].lower()
    assert "unread" in desc
    # The reverted directive/negation must NOT be re-added silently.
    assert "find_unread_emails" not in desc


def test_migration_029_adds_is_read_column(tmp_path: Path) -> None:
    """AC-1: the `is_read` column is present on emails after migration 029."""
    db_path = str(tmp_path / "test.db")
    applied = apply_pending_migrations(db_path)

    assert "029_emails_is_read.sql" in applied
    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)").fetchall()}
    assert "is_read" in cols, "Migration 029 must add emails.is_read"


def test_migration_029_creates_unread_index(tmp_path: Path) -> None:
    """AC-1: the partial index supporting the unread query is created."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    with get_connection(db_path) as conn:
        idx = {row[1] for row in conn.execute("PRAGMA index_list(emails)").fetchall()}
    assert "ix_emails_is_read" in idx


def test_migration_029_is_idempotent(tmp_path: Path) -> None:
    """AC-1: re-running on an already-migrated DB does not re-apply 029."""
    db_path = str(tmp_path / "test.db")
    first = apply_pending_migrations(db_path)
    assert "029_emails_is_read.sql" in first
    assert apply_pending_migrations(db_path) == []


async def _seed(
    db_path: str, *, graph_id: str, is_read: int | None, received_at: str
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, is_read) VALUES (?, ?, ?)",
        (graph_id, received_at, is_read),
    )


async def test_unread_only_filter_returns_only_unread(tmp_path: Path) -> None:
    """AC-1: `unread_only=True` returns is_read=0 rows and excludes read (=1)
    AND unknown (NULL) rows — the honest posture (only claim unread when Graph
    actually said so)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    await _seed(db_path, graph_id="unread-1", is_read=0, received_at="2026-06-03T00:00:00Z")
    await _seed(db_path, graph_id="read-1", is_read=1, received_at="2026-06-02T00:00:00Z")
    await _seed(db_path, graph_id="unknown-1", is_read=None, received_at="2026-06-01T00:00:00Z")

    out = await find_emails(FindEmailsFilter(unread_only=True), db_path=db_path)
    assert out.ok is True
    ids = {p.email_id for p in out.projections}
    assert ids == {"unread-1"}, f"unread_only must return only is_read=0 rows; got {ids}"


async def test_no_unread_filter_returns_all_non_deleted(tmp_path: Path) -> None:
    """AC-1: without unread_only, the read/unread/unknown rows all return
    (existing behavior unchanged — the new field is opt-in)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    await _seed(db_path, graph_id="u", is_read=0, received_at="2026-06-03T00:00:00Z")
    await _seed(db_path, graph_id="r", is_read=1, received_at="2026-06-02T00:00:00Z")
    await _seed(db_path, graph_id="n", is_read=None, received_at="2026-06-01T00:00:00Z")

    out = await find_emails(FindEmailsFilter(), db_path=db_path)
    assert {p.email_id for p in out.projections} == {"u", "r", "n"}


def _graph_message(graph_id: str, *, is_read: Any) -> dict[str, Any]:
    """A minimal Graph message resource. `is_read` may be True/False/omitted
    (pass the sentinel `...` to omit the key entirely)."""
    msg: dict[str, Any] = {
        "id": graph_id,
        "changeKey": f"ck-{graph_id}",
        "conversationId": None,
        "receivedDateTime": "2026-06-01T00:00:00Z",
        "subject": "hi",
        "bodyPreview": "preview",
        "hasAttachments": False,
        "from": {"emailAddress": {"address": "alice@example.com", "name": "Alice"}},
    }
    if is_read is not ...:
        msg["isRead"] = is_read
    return msg


async def test_sync_populates_is_read_from_graph_true(tmp_path: Path) -> None:
    """AC-1: the sync worker persists Graph `isRead=true` as is_read=1."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    await _upsert_message(db_path, _graph_message("g-read", is_read=True))

    row = await fetchone(db_path, "SELECT is_read FROM emails WHERE graph_id = ?", ("g-read",))
    assert row is not None
    assert row[0] == 1


async def test_sync_populates_is_read_from_graph_false(tmp_path: Path) -> None:
    """AC-1: Graph `isRead=false` persists as is_read=0 (the genuinely-unread
    signal the unread_only filter reads)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    await _upsert_message(db_path, _graph_message("g-unread", is_read=False))

    row = await fetchone(db_path, "SELECT is_read FROM emails WHERE graph_id = ?", ("g-unread",))
    assert row is not None
    assert row[0] == 0

    # And it is reachable through the unread_only filter.
    out = await find_emails(FindEmailsFilter(unread_only=True), db_path=db_path)
    assert {p.email_id for p in out.projections} == {"g-unread"}


async def test_sync_persists_null_when_graph_omits_is_read(tmp_path: Path) -> None:
    """AC-1: when Graph omits `isRead` (defensive), persist NULL — never guess.
    A NULL row is NOT surfaced by unread_only."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    await _upsert_message(db_path, _graph_message("g-unknown", is_read=...))

    row = await fetchone(db_path, "SELECT is_read FROM emails WHERE graph_id = ?", ("g-unknown",))
    assert row is not None
    assert row[0] is None

    out = await find_emails(FindEmailsFilter(unread_only=True), db_path=db_path)
    assert out.projections == []
