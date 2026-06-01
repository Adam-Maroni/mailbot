"""Unit tests for mailbot_api/router/lanes.py (Story 2-5)."""

from __future__ import annotations

import asyncio

import pytest

from mailbot_api.router.lanes import (
    LaneScheduler,
    _reset_semaphore_registry_for_test,
    acquire_provider_slot,
    batch_queue,
    interactive_queue,
    provider_for_model,
)


@pytest.fixture(autouse=True)
def _clean_lanes() -> None:
    _reset_semaphore_registry_for_test()
    yield
    _reset_semaphore_registry_for_test()


@pytest.mark.parametrize(
    ("model_id", "expected_provider"),
    [
        ("claude-haiku-4-5-20251001", "anthropic"),
        ("claude-opus-4-7", "anthropic"),
        ("qwen2.5:3b-instruct-q4_K_M", "ollama"),
        ("nomic-embed-text", "ollama"),
        ("llama3.2:3b", "ollama"),
        ("mistral:7b", "ollama"),
        ("some-random-model", "unknown"),
        ("", "unknown"),
    ],
)
def test_provider_for_model(model_id: str, expected_provider: str) -> None:
    assert provider_for_model(model_id) == expected_provider


async def test_acquire_provider_slot_ollama_passes_through() -> None:
    # No semaphore for Ollama — many concurrent acquires should all enter.
    counter = 0

    async def _runner() -> None:
        nonlocal counter
        async with acquire_provider_slot("qwen2.5:3b-instruct-q4_K_M"):
            counter += 1
            await asyncio.sleep(0.01)

    await asyncio.gather(*[_runner() for _ in range(10)])
    assert counter == 10


async def test_acquire_provider_slot_anthropic_capped_at_4() -> None:
    """Story 2-5 AC-3: at most 4 concurrent Anthropic calls in flight."""
    in_flight = 0
    max_observed = 0

    async def _runner() -> None:
        nonlocal in_flight, max_observed
        async with acquire_provider_slot("claude-opus-4-7"):
            in_flight += 1
            max_observed = max(max_observed, in_flight)
            await asyncio.sleep(0.05)
            in_flight -= 1

    await asyncio.gather(*[_runner() for _ in range(12)])
    assert max_observed <= 4, f"observed {max_observed} concurrent Anthropic calls; cap is 4"


async def test_acquire_provider_slot_unknown_passes_through() -> None:
    async with acquire_provider_slot("totally-unknown"):
        pass  # Should not raise / block.


def test_queue_singletons_are_asyncio_queues() -> None:
    assert isinstance(interactive_queue(), asyncio.Queue)
    assert isinstance(batch_queue(), asyncio.Queue)
    # Same instance returned each call.
    assert interactive_queue() is interactive_queue()
    assert batch_queue() is batch_queue()


async def test_lane_scheduler_start_stop_lifecycle() -> None:
    sched = LaneScheduler(pool_size=2)
    await sched.start()
    await asyncio.sleep(0.05)
    await sched.stop(timeout=2.0)
    # No zombie tasks.
    assert all(t.done() for t in sched._tasks)
