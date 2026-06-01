"""Story 3-7 AC-8: sender + thread enrichment integration tests.

Real SQLite + scripted adapter pattern matching test_pipeline_e2e.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.ingest.sender_enrichment import enrich_sender, enrich_thread
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_QWEN = "qwen2.5:3b-instruct-q4_K_M"


class _FakeQwenAdapter:
    """Routes by SYSTEM-block keyword to either sender or thread payload."""

    def __init__(
        self,
        sender_payload: dict[str, Any] | None = None,
        thread_payload: dict[str, Any] | None = None,
        *,
        raise_on_sender: BaseException | None = None,
    ) -> None:
        self.model_id = _QWEN
        self._sender_payload = sender_payload or {"summary": "Professional contact, infrequent updates."}
        self._thread_payload = thread_payload or {"summary": "Q3 budget review — awaiting CFO sign-off."}
        self._raise_on_sender = raise_on_sender
        self.call_log: list[str] = []

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        self.call_log.append(system[:80])
        if "summarize how an email sender" in system.lower():
            if self._raise_on_sender is not None:
                raise self._raise_on_sender
            payload = self._sender_payload
        elif "summarize the continuity of a multi-message email thread" in system.lower():
            payload = self._thread_payload
        else:
            raise RuntimeError(f"unscripted system: {system[:80]!r}")
        return AdapterResponse(
            text=json.dumps(payload),
            tokens_in=10,
            tokens_out=8,
            cached_tokens_in=0,
            latency_ms=15,
            raw={"mock": True},
        )

    async def embed(self, text: str) -> Any:
        raise RuntimeError("_FakeQwenAdapter has no embed method")


_POLICY_YAML = f"""\
version: "test-enrichment-v1"

tasks:
  sender_reputation_summary:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  thread_continuity:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state():
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


async def _seed_sender(db_path: str, sender_id: str = "alice@example.com") -> None:
    await execute_write(
        db_path,
        "INSERT INTO senders (id, display_name, domain, first_seen_at) VALUES (?, ?, ?, ?)",
        (sender_id, "Alice", "example.com", "2026-06-01T00:00:00Z"),
    )


async def _seed_email_from_sender(
    db_path: str,
    *,
    graph_id: str,
    sender_id: str,
    subject: str,
    body: str,
    sensitivity: str | None = None,
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, sender_id, subject, body_preview, sensitivity) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-01T00:00:00Z", sender_id, subject, body, sensitivity),
    )


async def test_enrich_sender_first_call_dispatches_and_caches(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: first call generates and writes the summary; was_cached=False."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeQwenAdapter())
    await _seed_sender(db_path)
    await _seed_email_from_sender(db_path, graph_id="e-1", sender_id="alice@example.com", subject="Hi", body="Lunch?")

    result = await enrich_sender(sender_id="alice@example.com", db_path=db_path)

    assert result.ok is True
    assert result.was_cached is False
    assert result.summary == "Professional contact, infrequent updates."

    row = await fetchone(
        db_path,
        "SELECT sender_reputation_summary, sender_reputation_summary_prompt_v, sender_reputation_summary_at "
        "FROM senders WHERE id = ?",
        ("alice@example.com",),
    )
    assert row is not None
    assert row[0] == "Professional contact, infrequent updates."
    assert row[1] == "v1"
    assert row[2]  # at timestamp populated


async def test_enrich_sender_second_call_short_circuits(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: a second call returns was_cached=True with no Router dispatch."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeQwenAdapter())
    await _seed_sender(db_path)
    await _seed_email_from_sender(db_path, graph_id="e-1", sender_id="alice@example.com", subject="Hi", body="ok")

    first = await enrich_sender(sender_id="alice@example.com", db_path=db_path)
    assert first.was_cached is False

    second = await enrich_sender(sender_id="alice@example.com", db_path=db_path)
    assert second.ok is True
    assert second.was_cached is True
    assert second.summary == first.summary

    # Only ONE router_calls row (from the first call).
    rows = await fetchall(db_path, "SELECT id FROM router_calls", ())
    assert len(rows) == 1


async def test_enrich_sender_excludes_confidential_from_digest(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: confidential emails are excluded entirely (no body, no subject)."""
    db_path = _setup(tmp_path)

    captured_users: list[str] = []

    class _CaptureAdapter:
        model_id = _QWEN

        async def call(self, system, user, max_tokens_out, temperature=0.0):
            captured_users.append(user)
            return AdapterResponse(
                text=json.dumps({"summary": "Mixed correspondence."}),
                tokens_in=5,
                tokens_out=5,
                cached_tokens_in=0,
                latency_ms=10,
                raw={},
            )

        async def embed(self, text: str):
            raise RuntimeError("no embed")

    register_adapter(_QWEN, _CaptureAdapter())
    await _seed_sender(db_path)
    # 3 emails: confidential, sensitive, normal.
    await _seed_email_from_sender(
        db_path,
        graph_id="conf-1",
        sender_id="alice@example.com",
        subject="SUPER SECRET CONFIDENTIAL",
        body="CONFIDENTIAL_BODY_MARKER_xyz",
        sensitivity="confidential",
    )
    await _seed_email_from_sender(
        db_path,
        graph_id="sens-1",
        sender_id="alice@example.com",
        subject="Private chat",
        body="SENSITIVE_BODY_MARKER_xyz",
        sensitivity="sensitive",
    )
    await _seed_email_from_sender(
        db_path,
        graph_id="norm-1",
        sender_id="alice@example.com",
        subject="Lunch?",
        body="NORMAL_BODY_MARKER_xyz",
        sensitivity="normal",
    )

    await enrich_sender(sender_id="alice@example.com", db_path=db_path)
    assert len(captured_users) == 1
    sent_user = captured_users[0]
    # Confidential subject + body MUST be absent.
    assert "SUPER SECRET CONFIDENTIAL" not in sent_user
    assert "CONFIDENTIAL_BODY_MARKER_xyz" not in sent_user
    # Sensitive subject is present, body is NOT.
    assert "Private chat" in sent_user
    assert "SENSITIVE_BODY_MARKER_xyz" not in sent_user
    # Normal: full body present.
    assert "NORMAL_BODY_MARKER_xyz" in sent_user


async def test_enrich_sender_no_emails_returns_error(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5 defensive: sender with no emails returns ok=False."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeQwenAdapter())
    await _seed_sender(db_path)
    # No emails seeded.

    result = await enrich_sender(sender_id="alice@example.com", db_path=db_path)
    assert result.ok is False
    assert result.error is not None


async def test_enrich_thread_single_message_short_circuits(tmp_path: Path, _clean_state: Any) -> None:
    """AC-6: a thread with message_count <= 1 is treated as cached/inapplicable."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeQwenAdapter())
    await execute_write(
        db_path,
        "INSERT INTO threads (id, subject_normalized, last_message_at, message_count) VALUES (?, ?, ?, ?)",
        ("t-1", "subject", "2026-06-01T00:00:00Z", 1),
    )

    result = await enrich_thread(thread_id="t-1", db_path=db_path)
    assert result.ok is True
    assert result.was_cached is True


async def test_enrich_thread_multi_message_dispatches(tmp_path: Path, _clean_state: Any) -> None:
    """AC-6: multi-message thread runs the Router and writes the note."""
    db_path = _setup(tmp_path)
    register_adapter(_QWEN, _FakeQwenAdapter())
    await execute_write(
        db_path,
        "INSERT INTO threads (id, subject_normalized, last_message_at, message_count) VALUES (?, ?, ?, ?)",
        ("t-1", "Q3 budget", "2026-06-01T00:00:00Z", 3),
    )
    # 3 messages on the thread.
    for i in range(3):
        await execute_write(
            db_path,
            "INSERT INTO emails (graph_id, received_at, thread_id, subject, body_preview) VALUES (?, ?, ?, ?, ?)",
            (f"m-{i}", f"2026-06-0{i + 1}T00:00:00Z", "t-1", f"Subject {i}", f"Body {i}"),
        )

    result = await enrich_thread(thread_id="t-1", db_path=db_path)
    assert result.ok is True
    assert result.was_cached is False
    assert result.summary == "Q3 budget review — awaiting CFO sign-off."

    row = await fetchone(
        db_path,
        "SELECT thread_continuity_note, thread_continuity_note_prompt_v FROM threads WHERE id = ?",
        ("t-1",),
    )
    assert row is not None
    assert row[0] == "Q3 budget review — awaiting CFO sign-off."
    assert row[1] == "v1"


async def test_enrich_sender_router_failure_returns_error(tmp_path: Path, _clean_state: Any) -> None:
    """AC-8: adapter exception → ok=False, summary stays NULL."""
    db_path = _setup(tmp_path)
    register_adapter(
        _QWEN,
        _FakeQwenAdapter(raise_on_sender=RuntimeError("kaboom")),
    )
    await _seed_sender(db_path)
    await _seed_email_from_sender(db_path, graph_id="e-1", sender_id="alice@example.com", subject="s", body="b")

    result = await enrich_sender(sender_id="alice@example.com", db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR

    row = await fetchone(
        db_path,
        "SELECT sender_reputation_summary FROM senders WHERE id = ?",
        ("alice@example.com",),
    )
    assert row is not None
    assert row[0] is None
