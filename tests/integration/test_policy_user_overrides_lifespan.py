"""Integration tests for Story 9-1: policy.user-overrides.yaml hot-reload
+ lifespan behavior.

Real on-disk YAML, real watchfiles.awatch, real Pydantic validation. The
tests verify:
  * lifespan with absent override file → baseline version, no suffix
  * lifespan with present override file → merged version with +overrides: suffix
  * hot-reload: mutate override file → new snapshot reflects change within timeout
  * hot-reload: malformed override file → previous merged snapshot stays
  * graceful shutdown via stop_event
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from mailbot_api.router.policy import (
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
    """Poll a predicate until it returns truthy or timeout."""
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
    """Each test starts (and ends) with a clean module-level policy state.

    CR-F5 (Story 9-1, sonnet-4-6): fixed return annotation from `-> None`
    to `-> Iterator[None]` since the fixture uses `yield`. The pattern
    mirrors `tests/integration/test_policy_reload.py` from Story 2-2.
    """
    yield
    _reset_policy_snapshot_for_test()


# ---------------------------------------------------------------------------
# Lifespan-shape tests: synchronous load_policy() emulating what main.py does.
# ---------------------------------------------------------------------------


def test_lifespan_with_absent_overrides_file_no_suffix(tmp_path: Path) -> None:
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"  # not created
    _write_baseline(baseline_path)

    table = load_policy(baseline_path, overrides_path=overrides_path)
    assert table.version == "baseline-v1"
    assert "+overrides:" not in table.version
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"


def test_lifespan_with_populated_overrides_file_has_suffix(tmp_path: Path) -> None:
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path)
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    table = load_policy(baseline_path, overrides_path=overrides_path)
    assert table.version.startswith("baseline-v1+overrides:")
    assert table.tasks["draft_reply"].model == "claude-opus-4-7"
    # Other fields preserved.
    assert table.tasks["draft_reply"].prompt_version == "v3"
    assert table.tasks["coarse_class"].model == "qwen2.5:3b-instruct-q4_K_M"


# ---------------------------------------------------------------------------
# Hot-reload tests via policy_reload_loop with real awatch.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hot_reload_picks_up_overrides_mutation(
    tmp_path: Path, _reset_policy_module: Iterator[None]
) -> None:
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path)
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    initial = load_policy(baseline_path, overrides_path=overrides_path)
    set_policy_snapshot(initial)
    assert get_policy().tasks["draft_reply"].model == "claude-opus-4-7"

    stop_event = asyncio.Event()
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        # Mutate the override file.
        await asyncio.sleep(0.1)  # let the watcher settle
        _write_overrides(
            overrides_path,
            "tasks:\n  draft_reply:\n    model: claude-haiku-4-5-20251001\n",
        )
        # Poll until the snapshot reflects the change.
        await _wait_until(
            lambda: get_policy().tasks["draft_reply"].model == "claude-haiku-4-5-20251001",
            timeout=5.0,
        )
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)


@pytest.mark.asyncio
async def test_hot_reload_malformed_overrides_preserves_prior_snapshot(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CR-F1 (Story 9-1, sonnet-4-6) — AC-2 corrected contract.

    Malformed override file on reload → policy_reload_loop logs
    `policy.user-overrides.parse_failed` (inside load_policy_with_status)
    AND REFUSES the swap. The previous merged snapshot stays in place
    per AC-2 "the running policy is NOT swapped" + AR-D11-1
    validation-or-no-swap.

    Rationale: operator-edited garbage shouldn't silently swap us off
    the last-known-good merged state. The audit log surfaces the failure;
    Adam fixes the file; the next valid edit hot-reloads.
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
    assert initial.version.startswith("baseline-v1+overrides:")
    initial_version = initial.version
    initial_draft_model = initial.tasks["draft_reply"].model
    assert initial_draft_model == "claude-opus-4-7"

    stop_event = asyncio.Event()
    caplog.set_level(logging.ERROR, logger="mailbot_api.router.policy")
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        await asyncio.sleep(0.1)
        # Mutate to malformed YAML.
        _write_overrides(overrides_path, "::: not yaml :::\n")
        # Wait for the parse_failed event (the watcher saw the change).
        await _wait_until(
            lambda: any(
                getattr(r, "event", None) == "policy.user-overrides.parse_failed"
                for r in caplog.records
            ),
            timeout=5.0,
        )
        # Allow one more event loop tick so any swap (if it would happen)
        # propagates. Then assert NO swap happened.
        await asyncio.sleep(0.2)
        # Prior merged snapshot still in place — version unchanged.
        assert get_policy().version == initial_version
        # draft_reply still reflects the override (claude-opus-4-7), not
        # the baseline (claude-haiku-4-5-20251001).
        assert get_policy().tasks["draft_reply"].model == initial_draft_model
        # parse_failed event WAS emitted.
        parse_failed = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.user-overrides.parse_failed"
        ]
        assert len(parse_failed) >= 1
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)


@pytest.mark.asyncio
async def test_hot_reload_emits_swap_event_when_overrides_change(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the override file already exists and its content changes
    materially (hash differs), the watcher emits policy.user-overrides.swap.

    Contract limitation (Story 9-1, documented in policy.py docstring):
    if the override file does NOT exist at watcher-start time, watchfiles
    cannot watch it. The operator must restart mailbot-api after creating
    the file the first time. Story 9-4 owns the create-flow and is
    responsible for surfacing the restart requirement.
    """
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    _write_baseline(baseline_path)
    # Override file MUST exist at watcher-start for it to be watched.
    _write_overrides(
        overrides_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )

    initial = load_policy(baseline_path, overrides_path=overrides_path)
    set_policy_snapshot(initial)
    initial_version = initial.version
    assert "+overrides:" in initial_version

    stop_event = asyncio.Event()
    caplog.set_level(logging.INFO, logger="mailbot_api.router.policy")
    watcher = asyncio.create_task(
        policy_reload_loop(
            baseline_path, overrides_path=overrides_path, stop_event=stop_event
        )
    )
    try:
        await asyncio.sleep(0.1)
        # Mutate the existing override file — hash will differ.
        _write_overrides(
            overrides_path,
            "tasks:\n  draft_reply:\n    model: claude-haiku-4-5-20251001\n",
        )
        # Wait for the swap (new version differs from initial).
        await _wait_until(
            lambda: get_policy().version != initial_version
            and "+overrides:" in get_policy().version,
            timeout=5.0,
        )
        swap_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.user-overrides.swap"
        ]
        assert len(swap_events) >= 1
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)


@pytest.mark.asyncio
async def test_hot_reload_baseline_only_change_emits_reloaded_event(
    tmp_path: Path,
    _reset_policy_module: Iterator[None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No overrides file; baseline change → standard policy.reloaded event
    (backward-compat with Story 2-2 callers).
    """
    baseline_path = tmp_path / "policy.yaml"
    overrides_path = tmp_path / "policy.user-overrides.yaml"  # never created
    _write_baseline(baseline_path, version="baseline-v1")

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
        await asyncio.sleep(0.1)
        _write_baseline(baseline_path, version="baseline-v2")
        await _wait_until(
            lambda: get_policy().version == "baseline-v2",
            timeout=5.0,
        )
        reloaded_events = [
            r for r in caplog.records
            if getattr(r, "event", None) == "policy.reloaded"
        ]
        assert len(reloaded_events) >= 1
    finally:
        stop_event.set()
        await asyncio.wait_for(watcher, timeout=3.0)
