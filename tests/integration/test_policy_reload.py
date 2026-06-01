"""Integration tests for the policy.yaml watchfiles hot-reload (Story 2-2 AC-11).

Real on-disk YAML, real watchfiles.awatch, real Pydantic validation —
no mocking of the loader or the watcher. The tests verify:
  * happy-path reload swaps the snapshot
  * validation-failure reload leaves the prior snapshot in place
  * mid-call race: a captured snapshot does NOT change identity when
    the module-level reference is reassigned
  * graceful shutdown via stop_event
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    get_policy,
    load_policy,
    policy_reload_loop,
    set_policy_snapshot,
    snapshot_for_dispatch,
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
"""


def _write_policy(path: Path, version: str) -> None:
    path.write_text(_BASE_POLICY.format(version=version), encoding="utf-8")


def _write_invalid_policy(path: Path) -> None:
    path.write_text("not: a [ valid policy\n", encoding="utf-8")


async def _wait_for_version(expected: str, timeout: float = 5.0) -> None:
    """Poll `get_policy().version` until it matches or timeout."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            current = get_policy().version
        except RuntimeError:
            current = None
        if current == expected:
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(
                f"timeout waiting for policy.version={expected!r}; got {current!r}"
            )
        await asyncio.sleep(0.05)


@pytest.fixture
def _reset_policy_module() -> None:
    """Each test starts with a clean module-level policy state.

    Uses the named test helper ``_reset_policy_snapshot_for_test`` instead of
    a direct attribute write (Story 2-2 review fix LOW) so future concurrency
    guards have a single named call site to update.
    """
    yield
    _reset_policy_snapshot_for_test()


async def test_policy_reload_happy_path_swaps_snapshot(
    tmp_path: Path, _reset_policy_module: None
) -> None:
    path = tmp_path / "policy.yaml"
    _write_policy(path, "v1")
    set_policy_snapshot(load_policy(path))
    assert get_policy().version == "v1"

    stop_event = asyncio.Event()
    task = asyncio.create_task(policy_reload_loop(path, stop_event=stop_event))
    try:
        await asyncio.sleep(0.2)  # let the watcher attach
        _write_policy(path, "v2")
        await _wait_for_version("v2", timeout=5.0)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=5.0)


async def test_policy_reload_validation_failure_keeps_prior_snapshot(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    _reset_policy_module: None,
) -> None:
    path = tmp_path / "policy.yaml"
    _write_policy(path, "v-good")
    set_policy_snapshot(load_policy(path))

    stop_event = asyncio.Event()
    task = asyncio.create_task(policy_reload_loop(path, stop_event=stop_event))
    try:
        await asyncio.sleep(0.2)
        with caplog.at_level(logging.ERROR, logger="mailbot_api.router.policy"):
            _write_invalid_policy(path)
            # Give the watcher a chance to fire and log.
            await asyncio.sleep(1.0)

        # The snapshot must NOT have changed.
        assert get_policy().version == "v-good"
        assert any(
            "policy reload failed" in record.message
            and getattr(record, "event", None) == "policy.reload.failed"
            for record in caplog.records
        ), f"Expected policy.reload.failed; got: {[r.message for r in caplog.records]}"
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=5.0)


async def test_policy_reload_mid_call_race_snapshot_isolation(
    tmp_path: Path, _reset_policy_module: None
) -> None:
    """Architecture D11: a snapshot captured at dispatch time is NOT mutated
    when the module-level reference is rebound."""
    path = tmp_path / "policy.yaml"
    _write_policy(path, "snap-v1")
    set_policy_snapshot(load_policy(path))

    captured = snapshot_for_dispatch()
    assert captured.version == "snap-v1"

    stop_event = asyncio.Event()
    task = asyncio.create_task(policy_reload_loop(path, stop_event=stop_event))
    try:
        await asyncio.sleep(0.2)
        _write_policy(path, "snap-v2")
        await _wait_for_version("snap-v2", timeout=5.0)

        # captured still points at the pre-swap object.
        assert captured.version == "snap-v1", (
            "snapshot captured at dispatch time must not change identity"
        )
        # A subsequent dispatch sees the new version.
        assert snapshot_for_dispatch().version == "snap-v2"
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=5.0)


async def test_policy_reload_loop_stops_cleanly_on_stop_event(
    tmp_path: Path, _reset_policy_module: None
) -> None:
    path = tmp_path / "policy.yaml"
    _write_policy(path, "v1")
    set_policy_snapshot(load_policy(path))

    stop_event = asyncio.Event()
    task = asyncio.create_task(policy_reload_loop(path, stop_event=stop_event))
    await asyncio.sleep(0.2)
    stop_event.set()
    # Task must complete (no zombie).
    await asyncio.wait_for(task, timeout=5.0)
    assert task.done()
    assert not task.cancelled()


def test_get_policy_raises_before_initialization(_reset_policy_module: None) -> None:
    _reset_policy_snapshot_for_test()
    with pytest.raises(RuntimeError, match="policy not loaded"):
        get_policy()
