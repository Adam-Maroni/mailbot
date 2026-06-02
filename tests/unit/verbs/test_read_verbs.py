"""Story 5-1 — read-side verb tests.

Per the Middleware-Real-Bootstrap MailBot reframing: every test uses a real
on-disk SQLite via tmp_path with the full migration chain applied, NOT a
mocked DB. Coverage matrix per AC-9.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.count_emails import count_emails
from mailbot_api.verbs.find_emails import find_emails
from mailbot_api.verbs.get_sender_summary import get_sender_summary
from mailbot_api.verbs.get_thread import get_thread
from mailbot_api.verbs.hydrate_email import (
    _SESSION_HYDRATION_COUNTS,
    hydrate_email,
    reset_hydration_count,
)
from mailbot_api.verbs.schemas import FindEmailsFilter

# ---- fixtures -----------------------------------------------------------------


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    received_at: str = "2026-06-01T12:00:00Z",
    from_address: str | None = "alice@example.com",
    from_display_name: str | None = "Alice",
    subject: str | None = "hello",
    body_preview: str | None = "body preview text",
    summary_short: str | None = None,
    class_coarse: str | None = "human",
    class_fine: str | None = None,
    importance_score: float | None = 50.0,
    sensitivity: str | None = "normal",
    sensitivity_at: str | None = "2026-06-01T12:00:01Z",
    action_extraction: str | None = None,
    has_attachments: int = 0,
    thread_id: str | None = None,
    deleted_at: str | None = None,
) -> None:
    """Insert one emails row. Only fields the read verbs touch."""
    await execute_write(
        db_path,
        (
            "INSERT INTO emails ("
            "graph_id, received_at, from_address, from_display_name, subject, "
            "body_preview, summary_short, summary_short_at, class_coarse, class_coarse_at, "
            "class_fine, class_fine_at, importance_score, importance_score_at, "
            "sensitivity, sensitivity_at, action_extraction, action_extraction_at, "
            "has_attachments, thread_id, deleted_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            graph_id,
            received_at,
            from_address,
            from_display_name,
            subject,
            body_preview,
            summary_short,
            "2026-06-01T12:00:02Z" if summary_short is not None else None,
            class_coarse,
            "2026-06-01T12:00:03Z" if class_coarse is not None else None,
            class_fine,
            "2026-06-01T12:00:04Z" if class_fine is not None else None,
            importance_score,
            "2026-06-01T12:00:05Z" if importance_score is not None else None,
            sensitivity,
            sensitivity_at,
            action_extraction,
            "2026-06-01T12:00:06Z" if action_extraction is not None else None,
            has_attachments,
            thread_id,
            deleted_at,
        ),
    )


async def _seed_thread(db_path: str, *, thread_id: str, continuity_note: str | None = None) -> None:
    """Insert one threads row."""
    await execute_write(
        db_path,
        "INSERT INTO threads (id, last_message_at, message_count, thread_continuity_note) "
        "VALUES (?, ?, ?, ?)",
        (thread_id, "2026-06-01T12:00:00Z", 0, continuity_note),
    )


async def _seed_sender(
    db_path: str,
    *,
    address_lower: str,
    display_name: str | None = None,
    reputation: str | None = None,
) -> None:
    """Insert one senders row. senders.id is the lowercased email address."""
    await execute_write(
        db_path,
        "INSERT INTO senders (id, display_name, first_seen_at, sender_reputation_summary) "
        "VALUES (?, ?, ?, ?)",
        (address_lower, display_name, "2026-06-01T00:00:00Z", reputation),
    )


@pytest.fixture(autouse=True)
def _clear_hydration_state() -> Iterator[None]:
    """Hydration counter is module-level — clear between tests (setup + teardown)."""
    _SESSION_HYDRATION_COUNTS.clear()
    yield
    _SESSION_HYDRATION_COUNTS.clear()


# ---- find_emails --------------------------------------------------------------


async def test_find_emails_empty_db(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await find_emails(FindEmailsFilter(), db_path=db_path)
    assert out.ok is True
    assert out.projections == []


async def test_find_emails_one_row(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    out = await find_emails(FindEmailsFilter(), db_path=db_path)
    assert out.ok is True
    assert len(out.projections) == 1
    p = out.projections[0]
    assert p.email_id == "e-1"
    assert p.from_address == "alice@example.com"
    assert p.subject == "hello"
    assert p.class_coarse == "human"
    assert p.importance_score == 50.0
    assert p.sensitivity == "normal"
    assert p.has_attachments is False


async def test_find_emails_filter_by_sender_address(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", from_address="alice@example.com")
    await _seed_email(db_path, graph_id="e-2", from_address="bob@other.com")
    out = await find_emails(
        FindEmailsFilter(sender_address="alice@example.com"), db_path=db_path,
    )
    assert out.ok is True
    assert len(out.projections) == 1
    assert out.projections[0].email_id == "e-1"


async def test_find_emails_filter_by_sender_domain(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", from_address="alice@example.com")
    await _seed_email(db_path, graph_id="e-2", from_address="bob@OTHER.COM")
    out = await find_emails(
        FindEmailsFilter(sender_domain="other.com"), db_path=db_path,
    )
    assert out.ok is True
    assert len(out.projections) == 1
    assert out.projections[0].email_id == "e-2"


async def test_find_emails_filter_by_class_coarse(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", class_coarse="human")
    await _seed_email(db_path, graph_id="e-2", class_coarse="automated")
    out = await find_emails(FindEmailsFilter(class_coarse="automated"), db_path=db_path)
    assert out.ok is True
    assert len(out.projections) == 1
    assert out.projections[0].email_id == "e-2"


async def test_find_emails_filter_by_importance_min(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", importance_score=20.0)
    await _seed_email(db_path, graph_id="e-2", importance_score=80.0)
    out = await find_emails(FindEmailsFilter(importance_min=50.0), db_path=db_path)
    assert out.ok is True
    assert len(out.projections) == 1
    assert out.projections[0].email_id == "e-2"


async def test_find_emails_filter_by_since_until(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", received_at="2026-05-01T00:00:00Z")
    await _seed_email(db_path, graph_id="e-2", received_at="2026-06-01T00:00:00Z")
    await _seed_email(db_path, graph_id="e-3", received_at="2026-07-01T00:00:00Z")
    out = await find_emails(
        FindEmailsFilter(since="2026-05-15T00:00:00Z", until="2026-06-15T00:00:00Z"),
        db_path=db_path,
    )
    assert out.ok is True
    assert {p.email_id for p in out.projections} == {"e-2"}


async def test_find_emails_filter_by_query_substring(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", subject="invoice due", summary_short=None)
    await _seed_email(db_path, graph_id="e-2", subject="newsletter", summary_short="invoice mentioned")
    await _seed_email(db_path, graph_id="e-3", subject="random", summary_short="nothing")
    out = await find_emails(FindEmailsFilter(query="invoice"), db_path=db_path)
    assert out.ok is True
    assert {p.email_id for p in out.projections} == {"e-1", "e-2"}


async def test_find_emails_query_like_metachars_escaped(tmp_path: Path) -> None:
    """CR finding 1: `query` must escape % and _ so they don't act as wildcards."""
    db_path = _setup(tmp_path)
    # subject contains literal "50% off" — the `%` should be matched literally.
    await _seed_email(db_path, graph_id="e-1", subject="50% off everything", summary_short=None)
    await _seed_email(db_path, graph_id="e-2", subject="50 cents off", summary_short=None)
    # Search for "50%" — must match e-1 (literal `%`) and NOT e-2 (no `%` char).
    out = await find_emails(FindEmailsFilter(query="50%"), db_path=db_path)
    assert out.ok is True
    assert {p.email_id for p in out.projections} == {"e-1"}


async def test_find_emails_sender_domain_underscore_escaped(tmp_path: Path) -> None:
    """CR finding 2: `sender_domain` underscore must be literal, not LIKE wildcard."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", from_address="alice@ex_mple.com")
    await _seed_email(db_path, graph_id="e-2", from_address="alice@example.com")
    # `ex_mple.com` — the `_` must be literal, NOT match `example.com`.
    out = await find_emails(FindEmailsFilter(sender_domain="ex_mple.com"), db_path=db_path)
    assert out.ok is True
    assert {p.email_id for p in out.projections} == {"e-1"}


async def test_find_emails_query_sql_injection_safe(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    # Injection attempt: if not parameterized, this would either drop the table
    # or error. With ? placeholders, it's just a literal substring search.
    out = await find_emails(
        FindEmailsFilter(query="'; DROP TABLE emails; --"), db_path=db_path,
    )
    assert out.ok is True
    assert out.projections == []  # no match for that literal substring
    # And the table still exists:
    out2 = await find_emails(FindEmailsFilter(), db_path=db_path)
    assert out2.ok is True
    assert len(out2.projections) == 1


async def test_find_emails_limit_over_100_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await find_emails(FindEmailsFilter(), db_path=db_path, limit=101)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "LIMIT_EXCEEDED"


async def test_find_emails_limit_under_1_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await find_emails(FindEmailsFilter(), db_path=db_path, limit=0)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "LIMIT_INVALID"


async def test_find_emails_excludes_soft_deleted(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    await _seed_email(db_path, graph_id="e-2", deleted_at="2026-06-01T13:00:00Z")
    out = await find_emails(FindEmailsFilter(), db_path=db_path)
    assert out.ok is True
    assert {p.email_id for p in out.projections} == {"e-1"}


async def test_find_emails_order_by_received_at_desc(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-old", received_at="2026-01-01T00:00:00Z")
    await _seed_email(db_path, graph_id="e-new", received_at="2026-06-01T00:00:00Z")
    out = await find_emails(FindEmailsFilter(), db_path=db_path)
    assert out.ok is True
    assert [p.email_id for p in out.projections] == ["e-new", "e-old"]


async def test_find_emails_projection_has_no_body_field(tmp_path: Path) -> None:
    """Rule J: EmailProjection must never carry body_preview / body_text."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", body_preview="SECRET BODY")
    out = await find_emails(FindEmailsFilter(), db_path=db_path)
    p = out.projections[0]
    # Serialize the projection and verify no body field surfaces.
    dumped = p.model_dump()
    assert "body_preview" not in dumped
    assert "body_text" not in dumped
    assert "body_html" not in dumped
    assert "SECRET BODY" not in str(dumped)


# ---- hydrate_email ------------------------------------------------------------


async def test_hydrate_email_normal_returns_full(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_thread(db_path, thread_id="t-1")
    await _seed_email(db_path, graph_id="e-1", body_preview="hi there", thread_id="t-1")
    out = await hydrate_email("e-1", db_path=db_path, session_id="s")
    assert out.ok is True
    assert out.email is not None
    assert out.email.email_id == "e-1"
    assert out.email.body_preview == "hi there"
    assert out.email.thread_id == "t-1"


async def test_hydrate_email_confidential_blocked(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", sensitivity="confidential")
    out = await hydrate_email("e-1", db_path=db_path, session_id="s")
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "CONFIDENTIAL_HYDRATION_BLOCKED"


async def test_hydrate_email_not_found(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await hydrate_email("does-not-exist", db_path=db_path, session_id="s")
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "HYDRATE_EMAIL_NOT_FOUND"


async def test_hydrate_email_soft_deleted(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", deleted_at="2026-06-01T13:00:00Z")
    out = await hydrate_email("e-1", db_path=db_path, session_id="s")
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "HYDRATE_EMAIL_DELETED"


async def test_hydrate_email_not_classified(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", sensitivity=None, sensitivity_at=None)
    out = await hydrate_email("e-1", db_path=db_path, session_id="s")
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "HYDRATE_NOT_CLASSIFIED"


async def test_hydrate_email_confidential_with_null_at_returns_blocked(tmp_path: Path) -> None:
    """CR finding 5: corrupt-state row (sensitivity='confidential' but sensitivity_at IS NULL)
    must surface CONFIDENTIAL_HYDRATION_BLOCKED, NOT HYDRATE_NOT_CLASSIFIED. Body is refused
    in both, but the correct refusal code carries the right privacy signal to the agent."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", sensitivity="confidential", sensitivity_at=None)
    out = await hydrate_email("e-1", db_path=db_path, session_id="s")
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "CONFIDENTIAL_HYDRATION_BLOCKED"


async def test_hydrate_email_rate_limited_at_6th(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    for i in range(1, 7):
        await _seed_email(db_path, graph_id=f"e-{i}")
    for i in range(1, 6):
        out = await hydrate_email(f"e-{i}", db_path=db_path, session_id="s")
        assert out.ok is True
    out = await hydrate_email("e-6", db_path=db_path, session_id="s")
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "HYDRATE_RATE_LIMITED"


async def test_hydrate_email_sessions_isolated(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    for i in range(1, 7):
        await _seed_email(db_path, graph_id=f"e-{i}")
    # Session A exhausts its 5.
    for i in range(1, 6):
        await hydrate_email(f"e-{i}", db_path=db_path, session_id="A")
    # Session B starts fresh.
    out = await hydrate_email("e-6", db_path=db_path, session_id="B")
    assert out.ok is True


async def test_hydrate_email_reset_clears_counter(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    for i in range(1, 7):
        await _seed_email(db_path, graph_id=f"e-{i}")
    for i in range(1, 6):
        await hydrate_email(f"e-{i}", db_path=db_path, session_id="s")
    reset_hydration_count("s")
    out = await hydrate_email("e-6", db_path=db_path, session_id="s")
    assert out.ok is True


async def test_hydrate_email_not_found_does_not_charge_counter(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    for _ in range(10):
        out = await hydrate_email("nope", db_path=db_path, session_id="s")
        assert out.error is not None
        assert out.error.code == "HYDRATE_EMAIL_NOT_FOUND"
    assert _SESSION_HYDRATION_COUNTS.get("s", 0) == 0


async def test_hydrate_email_confidential_does_not_charge_counter(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", sensitivity="confidential")
    for _ in range(10):
        out = await hydrate_email("e-1", db_path=db_path, session_id="s")
        assert out.error is not None
        assert out.error.code == "CONFIDENTIAL_HYDRATION_BLOCKED"
    assert _SESSION_HYDRATION_COUNTS.get("s", 0) == 0


# ---- get_thread ---------------------------------------------------------------


async def test_get_thread_returns_ordered_projections(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_thread(db_path, thread_id="t-1", continuity_note="ongoing convo")
    await _seed_email(db_path, graph_id="e-2", thread_id="t-1", received_at="2026-06-02T00:00:00Z")
    await _seed_email(db_path, graph_id="e-1", thread_id="t-1", received_at="2026-06-01T00:00:00Z")
    out = await get_thread("t-1", db_path=db_path)
    assert out.ok is True
    assert [p.email_id for p in out.projections] == ["e-1", "e-2"]  # ASC
    assert out.thread_continuity_note == "ongoing convo"
    assert out.message_count == 2


async def test_get_thread_unknown_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await get_thread("nope", db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "THREAD_NOT_FOUND"


async def test_get_thread_excludes_soft_deleted(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_thread(db_path, thread_id="t-1")
    await _seed_email(db_path, graph_id="e-1", thread_id="t-1")
    await _seed_email(db_path, graph_id="e-2", thread_id="t-1", deleted_at="2026-06-01T13:00:00Z")
    out = await get_thread("t-1", db_path=db_path)
    assert out.ok is True
    assert [p.email_id for p in out.projections] == ["e-1"]
    assert out.message_count == 1


# ---- count_emails -------------------------------------------------------------


async def test_count_emails_returns_int(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    await _seed_email(db_path, graph_id="e-2")
    out = await count_emails(FindEmailsFilter(), db_path=db_path)
    assert out.ok is True
    assert out.count == 2


async def test_count_emails_respects_filter(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1", class_coarse="human")
    await _seed_email(db_path, graph_id="e-2", class_coarse="automated")
    out = await count_emails(FindEmailsFilter(class_coarse="human"), db_path=db_path)
    assert out.count == 1


async def test_count_emails_excludes_soft_deleted(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    await _seed_email(db_path, graph_id="e-2", deleted_at="2026-06-01T13:00:00Z")
    out = await count_emails(FindEmailsFilter(), db_path=db_path)
    assert out.count == 1


async def test_count_emails_query_sql_injection_safe(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="e-1")
    out = await count_emails(
        FindEmailsFilter(query="'; DROP TABLE emails; --"), db_path=db_path,
    )
    assert out.ok is True
    assert out.count == 0
    out2 = await count_emails(FindEmailsFilter(), db_path=db_path)
    assert out2.count == 1


# ---- get_sender_summary -------------------------------------------------------


async def test_get_sender_summary_known(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_sender(
        db_path,
        address_lower="alice@example.com",
        display_name="Alice",
        reputation="known correspondent",
    )
    await _seed_email(db_path, graph_id="e-1", from_address="alice@example.com",
                      received_at="2026-05-01T00:00:00Z")
    await _seed_email(db_path, graph_id="e-2", from_address="alice@example.com",
                      received_at="2026-06-01T00:00:00Z")
    out = await get_sender_summary("Alice@Example.COM", db_path=db_path)
    assert out.ok is True
    assert out.sender is not None
    assert out.sender.sender_address == "alice@example.com"
    assert out.sender.display_name == "Alice"
    assert out.sender.message_count == 2
    assert out.sender.last_seen_at == "2026-06-01T00:00:00Z"
    assert out.sender.sender_reputation_summary == "known correspondent"


async def test_get_sender_summary_unknown_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await get_sender_summary("nobody@nowhere.com", db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "SENDER_NOT_FOUND"


async def test_get_sender_summary_aggregates_mixed_case(tmp_path: Path) -> None:
    """CR finding 3: emails with mixed-case from_address must aggregate correctly."""
    db_path = _setup(tmp_path)
    await _seed_sender(db_path, address_lower="alice@example.com", display_name="Alice")
    # Sync captured the address with original casing — common Graph behavior.
    await _seed_email(db_path, graph_id="e-1", from_address="Alice@Example.COM",
                      received_at="2026-06-01T00:00:00Z")
    await _seed_email(db_path, graph_id="e-2", from_address="ALICE@example.com",
                      received_at="2026-06-02T00:00:00Z")
    out = await get_sender_summary("alice@example.com", db_path=db_path)
    assert out.ok is True
    assert out.sender is not None
    # Both case-variant rows should aggregate despite from_address casing.
    assert out.sender.message_count == 2
    assert out.sender.last_seen_at == "2026-06-02T00:00:00Z"


async def test_get_sender_summary_no_emails(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_sender(db_path, address_lower="alice@example.com", display_name="Alice")
    out = await get_sender_summary("alice@example.com", db_path=db_path)
    assert out.ok is True
    assert out.sender is not None
    assert out.sender.message_count == 0
    assert out.sender.last_seen_at is None
