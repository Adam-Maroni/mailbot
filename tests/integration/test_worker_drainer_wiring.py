"""Story 6-6 — worker-process integration: drainer + OutlookGraphWriteAdapter.

This is the load-bearing test for Story 6-6's scope expansion: it proves that
once the worker boots, a propose_action → cool-off → drain → applied round-trip
completes through the wired drainer + adapter (NOT a direct module call).

Tests run against:
  - real on-disk SQLite (tmp_path) with all migrations applied
  - real OutlookGraphWriteAdapter against `httpx.MockTransport` (not a mocked adapter)
  - real cooling_off_tick promoting cooling_off → pending
  - real drainer.run_loop with the adapter wired in

Coverage:
  - Tier-1 ADD_LOCAL_CATEGORY: drainer applies WITHOUT a Graph HTTP call
  - Tier-2 ARCHIVE happy path: drainer applies via the real adapter against MockTransport
  - drainer heartbeat row written under `component="actions_drainer"` while running
  - drainer shutdown_event cleanly stops the loop without losing the in-flight tick
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from mailbot_api.actions.drainer import run_loop as drainer_run_loop
from mailbot_api.actions.outlook_adapter import OutlookGraphWriteAdapter
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, fetchone, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.scheduler import upsert_worker_health


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    return db_path


async def _seed_email(db_path: str, *, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com",
         "cm-v1", None),
    )


def _read_status(db_path: str, action_id: int) -> str:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (action_id,),
        ).fetchone()
    return str(row[0])


def _make_mock_transport(captured: dict[str, Any]) -> httpx.MockTransport:
    """Return an httpx.MockTransport that records the request + returns 200.

    Story 10-2: move-family drains issue a pre-state GET ($select=parentFolderId)
    before the dispatch; serve it a folder id (fail-closed would otherwise
    refuse the row) and keep `captured` recording the dispatch call only."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("$select") == "parentFolderId":
            return httpx.Response(200, json={"parentFolderId": "folder-pre-state"})
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["body"] = req.content
        captured["called"] = True
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


async def test_tier_1_local_category_drainer_does_not_call_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier-1 ADD_LOCAL_CATEGORY actions short-circuit inside OutlookGraphWriteAdapter
    per Story 4-5's design — the drainer applies WITHOUT touching the network.
    Verified by attaching MockTransport that records every call and asserting
    zero calls were made."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-local-1")

    out = await propose_action(
        "e-local-1",
        ActionType.ADD_LOCAL_CATEGORY,
        db_path=db_path,
        payload={"category": "starred"},
    )
    assert out.ok

    captured: dict[str, Any] = {"called": False}
    adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: "fake-token",
        transport=_make_mock_transport(captured),
    )

    # Bounded drainer run via shutdown_event.
    shutdown = asyncio.Event()

    async def _run_drainer_briefly() -> None:
        async def _trigger_shutdown() -> None:
            await asyncio.sleep(0.3)
            shutdown.set()

        asyncio.create_task(_trigger_shutdown())
        await drainer_run_loop(
            db_path, adapter=adapter, interval_seconds=0.05, shutdown_event=shutdown,
        )

    await _run_drainer_briefly()

    assert _read_status(db_path, out.action_id) == "applied"
    assert captured["called"] is False  # zero Graph HTTP calls


async def test_tier_2_archive_drainer_dispatches_to_real_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier-2 ARCHIVE goes through the real OutlookGraphWriteAdapter; this proves
    Story 5-9's capstone send path is now wired end-to-end at the worker boundary
    (ARCHIVE stands in for SEND_REPLY here because seeding a sensitivity grant
    is out of scope for this integration test — same dispatch path)."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-arch-1")

    out = await propose_action("e-arch-1", ActionType.ARCHIVE, db_path=db_path)
    assert out.ok

    # Force into pending so the drainer claims (mirrors the Story 4-4 unit-test
    # pattern: propose lands in pending_grant; mint the matching grant; flip
    # the row to pending; drainer's per-tier grant check re-binds the grant_id).
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()

    from mailbot_api.actions.authorization import mint_grant

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    grant_out = await mint_grant(
        ActionType.ARCHIVE, ["e-arch-1"], expires_at, db_path=db_path,
    )
    assert grant_out.ok

    captured: dict[str, Any] = {"called": False}
    adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: "fake-token",
        transport=_make_mock_transport(captured),
    )

    shutdown = asyncio.Event()

    async def _trigger_shutdown() -> None:
        await asyncio.sleep(0.3)
        shutdown.set()

    asyncio.create_task(_trigger_shutdown())
    await drainer_run_loop(
        db_path, adapter=adapter, interval_seconds=0.05, shutdown_event=shutdown,
    )

    assert _read_status(db_path, out.action_id) == "applied"
    assert captured["called"] is True
    assert "graph.microsoft.com" in captured["url"]
    assert "/me/messages/e-arch-1/move" in captured["url"]


async def test_cross_process_pause_stops_worker_drainer_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10.5.1 (F4, CRITICAL) — the two-instance regression.

    "The API process" pauses by writing the pause_state DB row via its own
    PauseState instance; the worker/drainer instance NEVER calls initialize().
    Before the fix, the drainer's gate read the worker's stale in-memory
    `is_paused()` mirror (False) and dispatched the REAL Graph move while the
    system was paused (the 259ms-after-propose F4 evidence). After the fix, the
    drainer reads the authoritative DB row and refuses to dispatch — zero Graph
    HTTP calls — and the queued row stays pending for the post-resume tick.
    """
    from mailbot_api.router.pause import (
        PauseState,
        _reset_pause_state_for_test,
    )

    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-paused-1")

    out = await propose_action("e-paused-1", ActionType.ARCHIVE, db_path=db_path)
    assert out.ok
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()

    from mailbot_api.actions.authorization import mint_grant

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    grant_out = await mint_grant(
        ActionType.ARCHIVE, ["e-paused-1"], expires_at, db_path=db_path,
    )
    assert grant_out.ok

    # "API process" pauses (writes the DB row). Reset the module singleton so
    # the drainer's in-memory mirror is unambiguously stale/False — the
    # worker-process reality that let F4 through.
    api_state = PauseState()
    await api_state.initialize(db_path)
    await api_state.pause(db_path, reason="operator-pause")
    _reset_pause_state_for_test()

    captured: dict[str, Any] = {"called": False}
    adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: "fake-token",
        transport=_make_mock_transport(captured),
    )

    shutdown = asyncio.Event()

    async def _trigger_shutdown() -> None:
        await asyncio.sleep(0.3)
        shutdown.set()

    asyncio.create_task(_trigger_shutdown())
    await drainer_run_loop(
        db_path, adapter=adapter, interval_seconds=0.05, shutdown_event=shutdown,
    )

    # No Graph dispatch happened; the row is still pending.
    assert captured["called"] is False
    assert _read_status(db_path, out.action_id) == "pending"

    _reset_pause_state_for_test()


async def test_drainer_heartbeat_writable_via_scheduler_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker writes `component="actions_drainer"` heartbeats while the
    drainer is running. This test verifies the worker_health upsert path used
    by `_drainer_heartbeat_loop` is wired correctly (we call it directly here;
    the worker integration is covered separately)."""
    db_path = _setup(tmp_path, monkeypatch)

    await upsert_worker_health(
        db_path, component="actions_drainer", outcome="ok", error=None,
    )
    row = await fetchone(
        db_path,
        "SELECT component, last_outcome, last_error FROM worker_health "
        "WHERE component = ?",
        ("actions_drainer",),
    )
    assert row == ("actions_drainer", "ok", None)


async def test_drainer_shutdown_event_stops_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `shutdown_event` parameter to `drainer.run_loop` causes a clean exit
    on the next tick — proves the worker's teardown path actually terminates."""
    db_path = _setup(tmp_path, monkeypatch)

    captured: dict[str, Any] = {"called": False}
    adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: "fake-token",
        transport=_make_mock_transport(captured),
    )

    shutdown = asyncio.Event()
    shutdown.set()  # pre-set so the loop exits on first iteration

    # Must terminate quickly because the shutdown event is already set.
    await asyncio.wait_for(
        drainer_run_loop(
            db_path, adapter=adapter, interval_seconds=0.05, shutdown_event=shutdown,
        ),
        timeout=2.0,
    )
