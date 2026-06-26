"""Story 9-1.5 integration tests — F35 closure.

Covers the gap that allowed F35 HIGH to escape Story 9-1's integration coverage:
``test_policy_user_overrides_lifespan.py`` used ``tmp_path`` fixtures that
NEVER deleted files mid-test. These tests exercise the delete-mid-lifespan
path so the F35 watchfiles thrash regression is caught at integration time.

Three behaviors verified per AC-5:

* delete-suppression — operator ``rm``'s the override file at runtime; loop
  emits exactly ONE ``policy.user-overrides.swap`` + ONE
  ``policy.user-overrides.absent_at_runtime`` WARNING; subsequent watchfiles
  spurious fires are silently coalesced (zero extra ``policy.reloaded``).
* baseline-edit-resume — after deletion + suppression, mutating the baseline
  ``policy.yaml`` fires exactly ONE ``policy.reloaded`` event with the new
  baseline version and no ``+overrides:`` suffix (AC-3 resume).
* F33-no-auto-pickup-on-recreate — after deletion + suppression, re-creating
  the override file at runtime does NOT pick it up (F33 contract preserved).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from mailbot_api.router.policy import (
    _reset_override_absent_flag_for_test,
    _reset_policy_snapshot_for_test,
    get_policy,
    load_policy,
    policy_reload_loop,
    set_policy_snapshot,
)

_BASE_POLICY = """\
version: "{version}"

tasks:
  coarse_class:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  draft_reply:
    model: "claude-haiku-4-5-20251001"
    prompt_version: "v3"
    escalate: false
    max_tokens_out: 1500
    lane: "interactive"
    sensitivity: "any"
"""


def _write_baseline(path: Path, version: str = "baseline-v1") -> None:
    path.write_text(_BASE_POLICY.format(version=version), encoding="utf-8")


def _write_overrides(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            if predicate():
                return
        except RuntimeError:
            pass
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timeout waiting for predicate {predicate!r}")
        await asyncio.sleep(0.05)


@pytest.fixture
def _reset_policy_module() -> Iterator[None]:
    """F35 closure (Story 9-1.5): also reset the absent-after-applied
    suppression flag between tests since each test arms it via a deletion
    transition and subsequent tests rely on a clean slate.

    CR-F3 (Story 9-1.5, sonnet-4-6): pre-yield setup resets BOTH the
    snapshot and the suppression flag for symmetry with the post-yield
    teardown. Otherwise a stale snapshot from a previously-failing test
    could contaminate test state if pytest reorders tests or runs subsets.
    """
    _reset_policy_snapshot_for_test()
    _reset_override_absent_flag_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_override_absent_flag_for_test()


@pytest.mark.asyncio
async def test_delete_at_runtime_emits_swap_and_absent_warning_then_suppresses(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-1 + AC-2: deletion fires swap + absent_at_runtime WARNING ONCE,
    then suppresses subsequent watchfiles spurious fires.
    """
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path)
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    initial = load_policy(baseline_path, overrides_path=overrides_path)
    set_policy_snapshot(initial)
    assert "+overrides:" in initial.version

    stop_event = asyncio.Event()
    caplog.set_level(logging.DEBUG, logger="mailbot_api.router.policy")
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        # Let the watcher settle before deletion.
        await asyncio.sleep(0.2)
        # rm the override file at runtime — the F35 trigger.
        os.unlink(overrides_path)
        # Wait for the absent_at_runtime warning.
        await _wait_until(
            lambda: any(
                getattr(r, "event", None) == "policy.user-overrides.absent_at_runtime"
                for r in caplog.records
            ),
            timeout=5.0,
        )
        # Hold for 2 seconds — long enough for watchfiles to thrash ~6 times
        # at the observed 310ms cadence per F35 evidence.
        await asyncio.sleep(2.0)
        # AC-1 + AC-2 assertions:
        swap_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.user-overrides.swap"
        ]
        absent_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.user-overrides.absent_at_runtime"
        ]
        reloaded_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.reloaded"
        ]
        assert len(swap_events) == 1, (
            f"expected exactly 1 swap event; got {len(swap_events)}"
        )
        assert len(absent_events) == 1, (
            f"expected exactly 1 absent_at_runtime event; got {len(absent_events)}"
        )
        assert len(reloaded_events) == 0, (
            f"expected ZERO policy.reloaded for the override-side spurious "
            f"fires (F35 closure); got {len(reloaded_events)}"
        )
        # Verify swap event semantics: version_before had +overrides:,
        # version_after lost it.
        swap_event = swap_events[0]
        assert "+overrides:" in swap_event.version_before
        assert "+overrides:" not in swap_event.version_after
        # Verify the absent_at_runtime warning references the F33 restart
        # contract for operator recovery.
        absent_event = absent_events[0]
        assert "restart" in absent_event.getMessage().lower()
        # Verify final in-memory snapshot reflects the swap (baseline-only).
        assert get_policy().version == "baseline-v1"
        assert "+overrides:" not in get_policy().version
        assert get_policy().overrides_applied == frozenset()
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)


@pytest.mark.asyncio
async def test_baseline_edit_after_delete_resumes_policy_reloaded(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-3: after deletion + suppression, mutating baseline policy.yaml
    fires exactly ONE policy.reloaded with the new baseline version (no
    +overrides: suffix).
    """
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path, version="baseline-v1")
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    initial = load_policy(baseline_path, overrides_path=overrides_path)
    set_policy_snapshot(initial)

    stop_event = asyncio.Event()
    caplog.set_level(logging.INFO, logger="mailbot_api.router.policy")
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        await asyncio.sleep(0.2)
        # Delete the override file.
        os.unlink(overrides_path)
        await _wait_until(
            lambda: any(
                getattr(r, "event", None) == "policy.user-overrides.absent_at_runtime"
                for r in caplog.records
            ),
            timeout=5.0,
        )
        # Clear caplog so we only count events triggered by the baseline edit.
        caplog.clear()
        # Now mutate baseline.
        _write_baseline(baseline_path, version="baseline-v2")
        await _wait_until(
            lambda: get_policy().version == "baseline-v2",
            timeout=5.0,
        )
        # Allow a moment for any spurious fires to also process.
        await asyncio.sleep(0.5)
        reloaded_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.reloaded"
        ]
        # Exactly 1 reload event from the baseline change.
        assert len(reloaded_events) == 1, (
            f"expected exactly 1 policy.reloaded after baseline edit; "
            f"got {len(reloaded_events)}"
        )
        assert reloaded_events[0].version == "baseline-v2"
        # Final snapshot: baseline-v2, no +overrides: suffix.
        assert get_policy().version == "baseline-v2"
        assert "+overrides:" not in get_policy().version
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)


@pytest.mark.asyncio
async def test_baseline_edit_with_empty_override_present_resumes(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CR-F4 (Story 9-1.5, sonnet-4-6) — AC-3 resume corner case.

    After deletion + suppression, if an operator creates an EMPTY override
    file (zero-byte) AND edits the baseline simultaneously, the next fire
    returns ``override_status == "empty"`` (not ``"absent"``) per Story 9-1
    CR-F3. The AC-3 resume condition must accept BOTH ``"absent"`` AND
    ``"empty"`` because both are operationally identical for the
    +overrides: suffix surface (no suffix in either case). Without the
    CR-F2 broadening, this scenario would silently drop the baseline edit
    — the suppression flag would stay armed and the real change would
    never emit ``policy.reloaded``.
    """
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path, version="baseline-v1")
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    initial = load_policy(baseline_path, overrides_path=overrides_path)
    set_policy_snapshot(initial)

    stop_event = asyncio.Event()
    caplog.set_level(logging.INFO, logger="mailbot_api.router.policy")
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        await asyncio.sleep(0.2)
        # Delete the override file.
        os.unlink(overrides_path)
        await _wait_until(
            lambda: any(
                getattr(r, "event", None) == "policy.user-overrides.absent_at_runtime"
                for r in caplog.records
            ),
            timeout=5.0,
        )
        # Re-create as EMPTY (zero-byte) override file. Without the watcher
        # restart this would NOT be picked up on strict-Linux per F33; on
        # Windows the directory watch DOES observe it, returning
        # override_status="empty" (not "absent") to the loop.
        _write_overrides(overrides_path, "")
        # Now also mutate the baseline.
        caplog.clear()
        _write_baseline(baseline_path, version="baseline-v2")
        # Wait for the snapshot to reflect the baseline edit.
        await _wait_until(
            lambda: get_policy().version == "baseline-v2",
            timeout=5.0,
        )
        await asyncio.sleep(0.5)
        reloaded_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.reloaded"
        ]
        # AC-3 resume must fire even when override_status is "empty".
        assert len(reloaded_events) >= 1, (
            f"CR-F2 resume must fire on baseline edit even when override "
            f"file is empty (not absent); got {len(reloaded_events)} "
            f"policy.reloaded events"
        )
        # Final snapshot reflects the new baseline, no +overrides: suffix
        # (empty file yields no suffix per Story 9-1 CR-F3).
        assert get_policy().version == "baseline-v2"
        assert "+overrides:" not in get_policy().version
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)


@pytest.mark.asyncio
async def test_recreating_override_at_runtime_does_not_auto_pickup(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-4: after deletion + suppression, re-creating the override file at
    runtime does NOT auto-pickup (F33 contract preserved). No new swap event
    fires from the re-creation.
    """
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path)
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    initial = load_policy(baseline_path, overrides_path=overrides_path)
    set_policy_snapshot(initial)

    stop_event = asyncio.Event()
    caplog.set_level(logging.INFO, logger="mailbot_api.router.policy")
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        await asyncio.sleep(0.2)
        os.unlink(overrides_path)
        await _wait_until(
            lambda: any(
                getattr(r, "event", None) == "policy.user-overrides.absent_at_runtime"
                for r in caplog.records
            ),
            timeout=5.0,
        )
        # After absent_at_runtime fires, re-create the override file at runtime.
        caplog.clear()
        _write_overrides(
            overrides_path,
            "tasks:\n  draft_reply:\n    model: claude-haiku-4-5-20251001\n",
        )
        # Hold for 2 seconds — F33 says the watcher CANNOT pick up the
        # recreated file (the watch descriptor was bound to the now-deleted
        # inode at awatch() call time).
        await asyncio.sleep(2.0)
        swap_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.user-overrides.swap"
        ]
        assert len(swap_events) == 0, (
            f"F33 contract: recreated override file MUST NOT auto-pickup; "
            f"got {len(swap_events)} unexpected swap events"
        )
        # In-memory snapshot still baseline-only (no +overrides: suffix).
        assert "+overrides:" not in get_policy().version
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)
