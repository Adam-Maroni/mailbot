"""Per-task routing policy schema, loader, and hot-reload per Story 2-2.

Architecture §"D11: policy.yaml reload semantics" is the contract:
  * validation-or-no-swap on every reload
  * mid-call race acceptable — each `ask_router` call captures the
    `PolicyTable` instance at dispatch time and the call's lifecycle uses
    that snapshot regardless of subsequent reloads.

Public API:
  * ``PolicyEntry`` — Pydantic model for a single task's routing decision
  * ``PolicyTable`` — Pydantic model with the full task table + a version string
  * ``PolicyValidationError`` — raised by ``load_policy`` on any failure shape
  * ``load_policy(path)`` — pure function: reads + validates, returns a table
  * ``get_policy()`` / ``set_policy_snapshot()`` — module-level snapshot accessors
  * ``snapshot_for_dispatch()`` — semantic alias for ``get_policy()`` used by
    Story 2-4's ``ask_router`` to make the dispatch-time-capture intent explicit
  * ``policy_reload_loop(path, *, stop_event)`` — watchfiles-driven reloader
    for the FastAPI lifespan to schedule as a task

This module is the ONLY place YAML parsing happens against ``policy.yaml``.
``scripts/check_boundaries.py`` enforces this via a new ``yaml.safe_load`` /
``yaml.load`` allowlist (Story 2-2 AC-12).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from watchfiles import awatch

from mailbot_api.router.errors import sanitize_error

_log = logging.getLogger(__name__)


class PolicyEntry(BaseModel):
    """One row of ``policy.yaml#tasks`` — the routing decision for a single task type."""

    model_config = ConfigDict(extra="forbid")

    model: str
    prompt_version: str
    escalate: bool
    max_tokens_out: int = Field(default=4000)
    lane: Literal["interactive", "batch"]
    sensitivity: Literal["normal", "sensitive", "confidential", "any"]
    notes: str | None = None
    demotion_hypothesis: str | None = None
    promotion_hypothesis: str | None = None
    # Story 2-7 additions:
    #   response_cache_ttl_seconds — 0 disables caching for this task (default);
    #     >0 caches successful results for that many seconds keyed on
    #     hash(model|temperature|system|user).
    #   cache_warm — if true, the cache warmer issues a probe call every 4 min
    #     to keep Anthropic's ephemeral 5-min cache warm on the SYSTEM block.
    response_cache_ttl_seconds: int = 0
    cache_warm: bool = False


class PolicyTable(BaseModel):
    """The full policy snapshot: every per-task decision plus an opaque version.

    Story 2-2 review fix MEDIUM: ``tasks`` enforces ``min_length=1`` so an
    operator-shipped ``tasks: {}`` fails validation rather than silently
    breaking every Router lookup at first dispatch.
    """

    model_config = ConfigDict(extra="forbid")

    tasks: dict[str, PolicyEntry] = Field(min_length=1)
    version: str


class PolicyValidationError(Exception):
    """Raised by ``load_policy`` for any failure shape — missing file, bad YAML,
    Pydantic validation, etc. The ``details`` attribute carries the
    sanitized human-readable description.
    """

    def __init__(self, details: str) -> None:
        super().__init__(details)
        self.details = details

    def __str__(self) -> str:
        return f"PolicyValidationError: {self.details}"


def load_policy(path: Path) -> PolicyTable:
    """Read + validate ``policy.yaml``. Pure (no module-level state mutation).

    All failure shapes converge on ``PolicyValidationError`` with a sanitized
    ``details`` string. Pydantic validation errors get their JSON-shaped
    error list stringified and run through ``sanitize_error`` so any secret
    accidentally pasted into ``policy.yaml`` cannot leak via the failure log.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyValidationError(f"policy file not found: {path}") from exc
    except OSError as exc:
        raise PolicyValidationError(
            sanitize_error(exc) + f" (path={path})"
        ) from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyValidationError(
            "YAML parse failed: " + sanitize_error(exc)
        ) from exc

    if not isinstance(raw, dict):
        raise PolicyValidationError(
            f"policy.yaml top-level must be a mapping; got {type(raw).__name__}"
        )

    try:
        return PolicyTable.model_validate(raw)
    except ValidationError as exc:
        raise PolicyValidationError(sanitize_error(exc)) from exc


_policy: PolicyTable | None = None


def get_policy() -> PolicyTable:
    """Return the current policy snapshot.

    Raises ``RuntimeError`` if the snapshot has not been initialized — this
    can only happen via a programmer error (calling before the FastAPI
    lifespan ran the initial ``load_policy`` + ``set_policy_snapshot``).
    """
    if _policy is None:
        raise RuntimeError(
            "policy not loaded — set_policy_snapshot(load_policy(path)) must "
            "be called by the FastAPI lifespan before get_policy()"
        )
    return _policy


def set_policy_snapshot(table: PolicyTable) -> None:
    """Atomically replace the module-level policy reference.

    Python's GIL guarantees single-name rebinding is atomic; concurrent
    readers via ``get_policy()`` see either the old or new snapshot, never
    a torn read. No lock required. The previous snapshot stays valid for
    any in-flight call that already captured it via ``snapshot_for_dispatch``
    — that is the architecture D11 race-acceptable contract.
    """
    global _policy  # noqa: PLW0603 — module-level singleton swap is the contract
    _policy = table


def snapshot_for_dispatch() -> PolicyTable:
    """Semantic alias for ``get_policy()`` used by Story 2-4's ``ask_router``.

    The name documents the intent: the caller captures the snapshot ONCE at
    dispatch time and passes the returned ``PolicyTable`` instance through
    the entire call's lifecycle. Subsequent reloads do not affect this
    captured instance — only the module-level reference is replaced.
    """
    return get_policy()


async def policy_reload_loop(
    path: Path,
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Watch ``policy.yaml`` and atomically swap the snapshot on each valid edit.

    On every change event yielded by ``watchfiles.awatch``:
      * Successful ``load_policy`` → ``set_policy_snapshot`` + log
        ``event="policy.reloaded"`` with the new version.
      * ``PolicyValidationError`` → log ``event="policy.reload.failed"``
        with the sanitized ``details``; DO NOT swap. The previous snapshot
        stays in place.

    The watcher exits cleanly when ``stop_event`` is set by the lifespan
    shutdown branch.
    """
    async for _changes in awatch(str(path), stop_event=stop_event):
        try:
            new_table = load_policy(path)
        except PolicyValidationError as exc:
            _log.error(
                "policy reload failed",
                extra={"event": "policy.reload.failed", "details": exc.details},
            )
            continue
        except Exception as exc:  # noqa: BLE001 — review fix MEDIUM: defensive
            # Any non-PolicyValidationError exception during load (e.g., disk
            # I/O failure, sanitize_error crash, OS-level encoding error)
            # should NOT kill the watcher silently. Log + continue keeps the
            # prior snapshot in place and lets the next change retry.
            _log.error(
                "policy reload loop error",
                extra={
                    "event": "policy.reload.loop.error",
                    "exc_type": type(exc).__name__,
                },
            )
            continue
        set_policy_snapshot(new_table)
        _log.info(
            "policy reloaded",
            extra={"event": "policy.reloaded", "version": new_table.version},
        )


def _reset_policy_snapshot_for_test() -> None:
    """Test-only helper: clear the module-level snapshot to its initial state.

    Exposed (vs leaving callers to write ``policy_mod._policy = None`` directly)
    so test isolation has a single named call site that future contributors
    can rename or wrap with a lock if concurrency guards are added (Story 2-2
    review fix LOW). The leading underscore signals test-only intent — do NOT
    call from production code.
    """
    global _policy  # noqa: PLW0603 — test isolation contract
    _policy = None


__all__ = [
    "PolicyEntry",
    "PolicyTable",
    "PolicyValidationError",
    "_reset_policy_snapshot_for_test",
    "get_policy",
    "load_policy",
    "policy_reload_loop",
    "set_policy_snapshot",
    "snapshot_for_dispatch",
]
