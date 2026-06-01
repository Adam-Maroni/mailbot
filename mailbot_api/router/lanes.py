"""Two-queue lane scheduler + per-provider concurrency semaphore per Story 2-5.

Architecture §"D10":
  * Two asyncio.Queue instances — interactive (chat-driven) strictly preempts
    batch (ingest-driven) at dequeue time. In-flight dispatches do NOT yield
    priority — preemption is at enqueue/dequeue only.
  * Per-provider concurrency semaphore: 4 concurrent Anthropic; Ollama has no
    semaphore (local serving queues internally).

Scope note for Story 2-5: the queue + worker-pool dispatch architecture is
infrastructure that this story ships, but the actual queue-based dispatch
refactor of `ask_router` is deferred (the rate-limit gate + semaphore wrap
applied inline give us the cost-discipline + 429-protection guarantees
today). When Story 2-9's kill-switch lands, the queue-based dispatch
becomes natural because pause/resume needs the queue surface.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_log = logging.getLogger(__name__)


# Provider classification — extends as adapters land.
_ANTHROPIC_MODEL_PREFIXES: tuple[str, ...] = ("claude-",)
_OLLAMA_MODEL_PREFIXES: tuple[str, ...] = ("qwen", "nomic", "llama", "mistral")


def provider_for_model(model_id: str) -> str:
    """Classify a model id into a provider string used by the semaphore registry.

    Unknown model ids return ``"unknown"`` — they get no semaphore by
    default. Story 2-6 will add Anthropic-specific handling.
    """
    if any(model_id.startswith(p) for p in _ANTHROPIC_MODEL_PREFIXES):
        return "anthropic"
    if any(model_id.startswith(p) for p in _OLLAMA_MODEL_PREFIXES):
        return "ollama"
    return "unknown"


# Per-provider concurrency limits.
_PROVIDER_LIMITS: dict[str, int] = {
    "anthropic": 4,
}

_SEMAPHORE_REGISTRY: dict[str, asyncio.Semaphore] = {}


def _get_or_create_semaphore(provider: str) -> asyncio.Semaphore | None:
    limit = _PROVIDER_LIMITS.get(provider)
    if limit is None:
        return None
    sem = _SEMAPHORE_REGISTRY.get(provider)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _SEMAPHORE_REGISTRY[provider] = sem
    return sem


@asynccontextmanager
async def acquire_provider_slot(model_id: str) -> AsyncIterator[None]:
    """Async context manager that gates the adapter dispatch on the
    per-provider semaphore. Ollama (and unknown) providers pass through
    without blocking.
    """
    provider = provider_for_model(model_id)
    sem = _get_or_create_semaphore(provider)
    if sem is None:
        yield
        return
    async with sem:
        yield


def _reset_semaphore_registry_for_test() -> None:
    """Test-only — clear registered semaphores between tests so each test
    starts with a freshly-counted Semaphore."""
    _SEMAPHORE_REGISTRY.clear()


# ----- Lane queues + scheduler -----

# The queue payload type is intentionally `object` — actual dispatch shim
# lands in a later story; Story 2-5 ships the queue surface so 2-9's
# kill-switch can introspect.
_INTERACTIVE_Q: asyncio.Queue[object] = asyncio.Queue()
_BATCH_Q: asyncio.Queue[object] = asyncio.Queue()


def interactive_queue() -> asyncio.Queue[object]:
    return _INTERACTIVE_Q


def batch_queue() -> asyncio.Queue[object]:
    return _BATCH_Q


class LaneScheduler:
    """Lifecycle wrapper for the two-queue worker pool.

    Story 2-5 ships the lifecycle surface (start / stop with timeout) so the
    FastAPI lifespan has a stable shutdown contract. The worker-pool body
    is a no-op stub — Story 2-9 will populate it when queue-based dispatch
    becomes the primary path.
    """

    def __init__(self, *, pool_size: int = 8) -> None:
        self.pool_size = pool_size
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        for _ in range(self.pool_size):
            self._tasks.append(asyncio.create_task(self._worker_loop()))
        _log.info(
            "lane scheduler started",
            extra={"event": "router.lanes.started", "pool_size": self.pool_size},
        )

    async def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            # Story 2-5 ships the priority-drain shape; payload handling is
            # stubbed. Interactive strictly preempts batch.
            try:
                await asyncio.wait_for(_INTERACTIVE_Q.get(), timeout=0.05)
                continue
            except asyncio.TimeoutError:
                pass
            try:
                await asyncio.wait_for(_BATCH_Q.get(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    async def stop(self, *, timeout: float = 30.0) -> None:
        """Cancel pending queued calls + cancel worker tasks. Per AC-6: any
        queued payloads should be surfaced as RouterError(code=PROVIDER_ERROR,
        message='shutdown', retryable=True). The queue surface ships here;
        wiring lands when queue-based dispatch becomes primary."""
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        _log.info(
            "lane scheduler stopped",
            extra={"event": "router.lanes.stopped"},
        )


__all__ = [
    "LaneScheduler",
    "acquire_provider_slot",
    "batch_queue",
    "interactive_queue",
    "provider_for_model",
]
