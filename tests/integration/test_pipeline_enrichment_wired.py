"""Story 10.5.3 AC-3 (F-10-4-4) — enrichment must run on the ingest path.

Epic 10's walk found enrichment never ran: 0/727 senders, 0/1753 threads had a
cached summary. `enrich_sender` / `enrich_thread` shipped in Story 3-7 with
L2-green tests but had NO call site on the ingest pipeline — so no email ever
triggered them in production.

The fix wires them into `process_email` as a best-effort trailing step (after
the 7 derivation steps): once an email is fully derived, its sender and (if a
multi-message thread) its thread get enriched. Enrichment is Qwen-only (free,
Rule F.1) and cached-forever (Rule A), so wiring it per-email is cost-safe —
the second email from the same sender short-circuits on the cache.

Best-effort contract: an enrichment failure (NULL thread_id, sender with only
confidential emails, single-message thread) MUST NOT fail the pipeline —
`process_email` still returns ok=True.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.ingest.pipeline import ProcessEmailResult, process_email
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse, EmbeddingResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_NOMIC = "nomic-embed-text"


class _FakeAllTasksAdapter:
    """One fake adapter covering every pipeline + enrichment task, routed by
    SYSTEM-block keyword. Qwen serves all classification + enrichment tasks in
    this fixture."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.call_log: list[str] = []

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        s = system.lower()
        self.call_log.append(s[:80])
        if "summarize how an email sender" in s:
            payload: dict[str, Any] = {"summary": "Professional contact, infrequent updates."}
        elif "summarize the continuity of a multi-message email thread" in s:
            payload = {"summary": "Q3 scheduling thread — awaiting confirmation."}
        elif "sensitivity" in s and "normal" in s:
            payload = {"sensitivity": "normal", "confidence": 0.92, "reason": "ordinary"}
        elif "broad kind" in s:
            payload = {"class_coarse": "human", "confidence": 0.9}
        elif "refine the relationship type" in s:
            payload = {"class_fine": "professional", "confidence": 0.8}
        elif "280 characters" in s:
            payload = {"summary": "Confirm Tuesday 2pm."}
        elif "0–100 scale" in s or "0-100 scale" in s:
            payload = {"importance": 55, "signals": ["known_sender"]}
        elif "extract structured action items" in s:
            payload = {"actions": []}
        else:
            raise RuntimeError(f"unscripted system: {system[:80]!r}")
        return AdapterResponse(
            text=json.dumps(payload),
            tokens_in=10,
            tokens_out=6,
            cached_tokens_in=0,
            latency_ms=12,
            raw={"mock": True},
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        vec = [0.1] * 768
        return EmbeddingResponse(vector=vec, dim=len(vec), tokens_in=1, latency_ms=5, raw={"mock": True})


_POLICY_YAML = f"""\
version: "test-enrichment-wired-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  fine_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  summary_short:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 384
    lane: "batch"
    sensitivity: "any"
  importance_scoring:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  action_extraction:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "batch"
    sensitivity: "any"
  embedding:
    model: "{_NOMIC}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 0
    lane: "batch"
    sensitivity: "any"
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
def _clean_state(monkeypatch: Any) -> Any:
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    monkeypatch.setenv("MAILBOT_SKIP_PATTERNS", "1")
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
    register_adapter(_QWEN, _FakeAllTasksAdapter(_QWEN))
    register_adapter(_NOMIC, _FakeAllTasksAdapter(_NOMIC))
    return db_path


async def _seed_sender(db_path: str, sender_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO senders (id, display_name, domain, first_seen_at) VALUES (?, ?, ?, ?)",
        (sender_id, "Alice", "example.com", "2026-06-01T00:00:00Z"),
    )


async def _seed_thread(db_path: str, thread_id: str, message_count: int) -> None:
    await execute_write(
        db_path,
        "INSERT INTO threads (id, last_message_at, message_count) VALUES (?, ?, ?)",
        (thread_id, "2026-07-10T12:00:00Z", message_count),
    )


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    sender_id: str,
    thread_id: str | None,
    body: str,
    received_at: str = "2026-07-10T12:00:00Z",
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, from_address, sender_id, thread_id, subject, body_preview) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (graph_id, received_at, sender_id, sender_id, thread_id, "Scheduling", body),
    )


@pytest.mark.asyncio
async def test_process_email_enriches_sender_and_thread(tmp_path: Path, _clean_state: Any) -> None:
    """After process_email, the email's sender gets a reputation summary and
    its multi-message thread gets a continuity note — enrichment is wired to
    the ingest path (F-10-4-4)."""
    db_path = _setup(tmp_path)
    await _seed_sender(db_path, "alice@example.com")
    await _seed_thread(db_path, "t-1", message_count=2)
    # Two emails in the thread so thread enrichment has material.
    await _seed_email(
        db_path, graph_id="e-0", sender_id="alice@example.com", thread_id="t-1",
        body="earlier message", received_at="2026-07-10T11:00:00Z",
    )
    await _seed_email(
        db_path, graph_id="e-1", sender_id="alice@example.com", thread_id="t-1",
        body="please confirm tuesday 2pm",
    )

    result: ProcessEmailResult = await process_email(email_id="e-1", db_path=db_path)
    assert result.ok is True, f"pipeline failed: {result.error}"

    sender_row = await fetchone(
        db_path,
        "SELECT sender_reputation_summary FROM senders WHERE id = ?",
        ("alice@example.com",),
    )
    assert sender_row is not None and sender_row[0], (
        "sender_reputation_summary not populated — enrichment did not run on ingest"
    )

    thread_row = await fetchone(
        db_path,
        "SELECT thread_continuity_note FROM threads WHERE id = ?",
        ("t-1",),
    )
    assert thread_row is not None and thread_row[0], (
        "thread_continuity_note not populated — thread enrichment did not run on ingest"
    )


@pytest.mark.asyncio
async def test_process_email_ok_when_enrichment_has_no_material(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Best-effort: an email with NO thread_id and a sender-less-than-usable
    enrichment still completes the pipeline (ok=True). Enrichment failure is
    non-fatal."""
    db_path = _setup(tmp_path)
    await _seed_sender(db_path, "bob@example.com")
    # No thread_id → thread enrichment is skipped/fails; must not break pipeline.
    await _seed_email(
        db_path, graph_id="e-solo", sender_id="bob@example.com", thread_id=None,
        body="one-off message",
    )

    result: ProcessEmailResult = await process_email(email_id="e-solo", db_path=db_path)
    assert result.ok is True, f"pipeline failed on enrichment-less email: {result.error}"


@pytest.mark.asyncio
async def test_enrichment_short_circuits_on_second_process_email(
    tmp_path: Path, _clean_state: Any
) -> None:
    """CR-10-5-3 (reviewer): the story claims per-email enrichment is cost-safe
    because a re-run short-circuits on the Rule A cache. Prove it — running
    process_email TWICE for the same sender must dispatch the sender-enrichment
    Qwen call only ONCE (the second run hits the cache), so the trailing step is
    a cheap cache-read on re-derivation, not a repeated billed call."""
    db_path = _setup(tmp_path)
    # Grab the registered qwen adapter so we can count its enrichment calls.
    from mailbot_api.router.registry import get_adapter

    qwen_adapter = get_adapter(_QWEN)
    await _seed_sender(db_path, "carol@example.com")
    await _seed_thread(db_path, "t-2", message_count=2)
    await _seed_email(
        db_path, graph_id="c-0", sender_id="carol@example.com", thread_id="t-2",
        body="first", received_at="2026-07-10T11:00:00Z",
    )
    await _seed_email(
        db_path, graph_id="c-1", sender_id="carol@example.com", thread_id="t-2",
        body="second", received_at="2026-07-10T12:00:00Z",
    )

    def _sender_enrichment_calls() -> int:
        return sum(1 for s in qwen_adapter.call_log if "summarize how an email sender" in s)

    await process_email(email_id="c-1", db_path=db_path)
    after_first = _sender_enrichment_calls()
    assert after_first == 1, f"expected 1 sender-enrichment dispatch, got {after_first}"

    # Second full run of the SAME email — enrichment must short-circuit on cache.
    await process_email(email_id="c-1", db_path=db_path)
    after_second = _sender_enrichment_calls()
    assert after_second == 1, (
        f"sender enrichment re-dispatched on re-run ({after_second} total) — "
        "the cost-safety claim (cache short-circuit) is false"
    )
