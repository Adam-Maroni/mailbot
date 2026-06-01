"""Unit tests for mailbot_api/router/cache_warmer.py (Story 2-7)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.router.cache_warmer import CacheWarmer
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)


def _write_policy(tmp_path: Path, *, warm_for_coarse: bool) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(
        f"""version: "warmer-test"

tasks:
  coarse_class:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
    cache_warm: {str(warm_for_coarse).lower()}
  summary_short:
    model: "claude-haiku-4-5-20251001"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
    cache_warm: false
""",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def _clean_policy() -> None:
    yield
    _reset_policy_snapshot_for_test()


async def test_cache_warmer_probes_warm_flagged_task(
    tmp_path: Path, _clean_policy: None
) -> None:
    set_policy_snapshot(load_policy(_write_policy(tmp_path, warm_for_coarse=True)))
    probes: list[dict[str, Any]] = []

    async def _fake_ask_router(task_type: str, content: dict[str, Any], **kwargs: Any) -> None:
        probes.append({"task_type": task_type, "content": content, **kwargs})

    warmer = CacheWarmer(
        db_path=str(tmp_path / "db.sqlite"),
        warm_interval_seconds=0.1,
        ask_router_fn=_fake_ask_router,
    )
    await warmer.start()
    await asyncio.sleep(0.3)
    await warmer.stop(timeout=1.0)

    assert any(p["task_type"] == "coarse_class" for p in probes)
    # summary_short was NOT warm-flagged.
    assert not any(p["task_type"] == "summary_short" for p in probes)
    # Probe carries cache-warmer caller_origin.
    assert all(p["caller_origin"] == "cache-warmer" for p in probes)


async def test_cache_warmer_skips_when_no_warm_flagged_tasks(
    tmp_path: Path, _clean_policy: None
) -> None:
    set_policy_snapshot(load_policy(_write_policy(tmp_path, warm_for_coarse=False)))
    probes: list[dict[str, Any]] = []

    async def _fake_ask_router(task_type: str, content: dict[str, Any], **kwargs: Any) -> None:
        probes.append({"task_type": task_type, **kwargs})

    warmer = CacheWarmer(
        db_path=str(tmp_path / "db.sqlite"),
        warm_interval_seconds=0.1,
        ask_router_fn=_fake_ask_router,
    )
    await warmer.start()
    await asyncio.sleep(0.3)
    await warmer.stop(timeout=1.0)

    assert probes == []


async def test_cache_warmer_logs_and_continues_on_probe_failure(
    tmp_path: Path,
    _clean_policy: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    set_policy_snapshot(load_policy(_write_policy(tmp_path, warm_for_coarse=True)))

    async def _failing_ask_router(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    warmer = CacheWarmer(
        db_path=str(tmp_path / "db.sqlite"),
        warm_interval_seconds=0.1,
        ask_router_fn=_failing_ask_router,
    )
    with caplog.at_level(logging.INFO, logger="mailbot_api.router.cache_warmer"):
        await warmer.start()
        await asyncio.sleep(0.2)
        await warmer.stop(timeout=1.0)

    assert any(
        getattr(r, "event", None) == "cache_warmer.failed"
        and getattr(r, "task_type", None) == "coarse_class"
        for r in caplog.records
    )


async def test_cache_warmer_stop_is_idempotent(tmp_path: Path, _clean_policy: None) -> None:
    set_policy_snapshot(load_policy(_write_policy(tmp_path, warm_for_coarse=False)))

    async def _noop(*args: Any, **kwargs: Any) -> None:
        pass

    warmer = CacheWarmer(
        db_path=str(tmp_path / "db.sqlite"),
        warm_interval_seconds=10.0,
        ask_router_fn=_noop,
    )
    await warmer.start()
    await warmer.stop(timeout=1.0)
    # Second stop is a no-op.
    await warmer.stop(timeout=1.0)
