"""Router kill-switch verbs per Story 2-9 (`/pause` and `/resume`).

Epic 5 wires the slash-command UI; this story implements the verb-side
handlers + the Pydantic shapes they return.

Story 6-4 extension: ``resume_router`` ALSO lifts the urgent-only
notification posture (set via ``notifications.posture.set_urgent_only``).
``/resume`` is the de-facto "talk to me" signal that the urgent-only
auto-recovery rule needs; auto-lift on any-slash-command-dispatch lands
when Hermes-side instrumentation is real.

Story 9-3 extension: ``set_model_oneshot`` adds the ``/model <model>``
session-scoped one-shot override surface. OQ-1 Option B (Adam-decided
2026-06-14): the override is stored in a module-level single-slot global,
NOT a session-keyed dict. The session_id from ctx is captured for audit
trail visibility but does NOT key the lookup. This matches MailBot's
single-user deployment reality; multi-user would require introducing a
session-keyed dict + plumbing session_id through the
``/v1/chat/completions`` HTTP endpoint (see story 9-3 OQ-1 for the full
decision trail).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from mailbot_api.config import get_secret_optional
from mailbot_api.notifications.posture import lift_urgent_only
from mailbot_api.router.budget import get_guard
from mailbot_api.router.oneshot import (
    OneShotOverride,
    _consume_oneshot_override,
    _get_active_oneshot_override,
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
)
from mailbot_api.router.pause import get_pause_state
from mailbot_api.router.policy import (
    UserOverridesWriteError,
    read_user_overrides_raw,
    snapshot_for_dispatch,
    write_user_overrides_atomic,
)

_log = logging.getLogger(__name__)


class PauseOut(BaseModel):
    ok: bool
    previously_paused: bool
    reason: str
    message: str


class ResumeOut(BaseModel):
    ok: bool
    previously_paused: bool
    message: str
    posture_lifted: bool = False


async def pause_router(*, db_path: str, reason: str) -> PauseOut:
    state = get_pause_state()
    previously = state.is_paused()
    await state.pause(db_path, reason=reason)
    return PauseOut(
        ok=True,
        previously_paused=previously,
        reason=reason,
        message=(
            f"router paused — reason: {reason}"
            if not previously
            else f"router was already paused — reason updated to: {reason}"
        ),
    )


async def resume_router(*, db_path: str) -> ResumeOut:
    state = get_pause_state()
    previously = state.is_paused()
    await state.resume(db_path)
    # Story 6-4: /resume also lifts urgent-only posture. Returns True iff
    # the posture WAS active before this call.
    posture_lifted = await lift_urgent_only(db_path=db_path)
    msg_parts = []
    if previously:
        msg_parts.append("router resumed")
    else:
        msg_parts.append("router was not paused")
    if posture_lifted:
        msg_parts.append(
            "lifted urgent-only posture — resuming normal notifications"
        )
    return ResumeOut(
        ok=True,
        previously_paused=previously,
        message="; ".join(msg_parts),
        posture_lifted=posture_lifted,
    )


# ---------------------------------------------------------------------------
# Story 9-3 — `/model <model>` one-shot dispatch verb
# ---------------------------------------------------------------------------
#
# The override-slot storage lives in `mailbot_api.router.oneshot` (router-
# internal, NOT a verb) so that `mailbot_api/router/router.py` can reach
# into it without violating Story 5-2 AC-7's verb-import isolation
# boundary. The verb (this file) is the SETTER; the router consumes.
#
# OQ-1 Option B: single-slot global per-process per Adam-decision 2026-06-14.
# The imports at the top of this file re-export the helpers from
# `router.oneshot` for tests + the MCP wrapper layer to continue importing
# them from here without touching the new module path.

_MODEL_ALIASES: Final[dict[str, str]] = {
    "qwen": "qwen2.5:3b-instruct-q4_K_M",
    "haiku": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-7",
}

_ALLOWED_FULL_MODEL_IDS: Final[frozenset[str]] = frozenset(_MODEL_ALIASES.values())


class SetModelOneShotOut(BaseModel):
    ok: bool
    model: str | None = None
    expires_at: str | None = None
    session_id: str | None = None
    error: str | None = None


def _normalize_model_id(model: str) -> str | None:
    """Return the full model ID for a shorthand alias or a known full ID.
    Returns None if the input is neither a registered alias nor a known
    full ID."""
    if model in _MODEL_ALIASES:
        return _MODEL_ALIASES[model]
    if model in _ALLOWED_FULL_MODEL_IDS:
        return model
    return None


async def set_model_oneshot(
    *,
    db_path: str,  # noqa: ARG001 — unused (no DB writes); kept for verb-signature parity
    model: str,
    session_id: str | None = None,
) -> SetModelOneShotOut:
    """Set a one-shot model override that the next ``ask_router`` call
    consumes (within the 5-min TTL).

    Per OQ-1 Option B: the override is stored in a module-level global in
    ``mailbot_api.router.oneshot``, not keyed by ``session_id``.
    ``session_id`` is captured for audit trail visibility only.
    """
    normalized = _normalize_model_id(model)
    if normalized is None:
        allowed = sorted(
            set(_MODEL_ALIASES.keys()) | _ALLOWED_FULL_MODEL_IDS
        )
        return SetModelOneShotOut(
            ok=False,
            model=None,
            error=(
                f"unknown model: {model!r}; allowed (aliases + full IDs): "
                + ", ".join(allowed)
            ),
        )
    override = _set_oneshot_override(
        model=normalized,
        session_id=session_id,
    )
    return SetModelOneShotOut(
        ok=True,
        model=normalized,
        expires_at=override.expires_at,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Story 9-4 — `/model <task> <model>` persistent override verb
#                                + `/model` inspect verb
# ---------------------------------------------------------------------------
#
# set_model_persistent writes to router/policy.user-overrides.yaml atomically
# (Story 9-1 companion file). The Story 9-1 watchfiles loop picks up the
# mutation and swaps in a new merged PolicyTable within ~1s; the verb polls
# for the swap and returns the observed propagation time. Validation lives
# at three layers: (a) verb input validation (task name + model id), (b)
# OQ-3 file-state preconditions (exists + writable; refuse-with-actionable-
# error if the watcher can't pick up a newly-appeared file per Story 9-1's
# hot-reload contract limitation), (c) post-write YAML re-parse on the next
# hot-reload via UserOverridesTable.model_validate (any schema regression
# is logged as policy.user-overrides.parse_failed at ERROR but does NOT
# undo the verb's write — Adam can re-issue to fix).
#
# inspect_policy renders the merged effective policy as a markdown table.
# Baseline values are sourced from router/policy.yaml; override values
# from router/policy.user-overrides.yaml when policy.overrides_applied
# is populated. Multi-state composition: degraded-mode + active one-shot
# lines appended below the per-task table for the "what is the router
# doing right now" view.


_USER_OVERRIDES_FILENAME: Final[str] = "policy.user-overrides.yaml"
_POLICY_FILENAME: Final[str] = "policy.yaml"
_PERSISTENT_HOT_RELOAD_TIMEOUT_S: Final[float] = 2.0
_PERSISTENT_HOT_RELOAD_POLL_S: Final[float] = 0.1


def _resolve_policy_dir() -> Path:
    """Resolve the router/ directory holding policy.yaml + the overrides
    companion. Mirrors mailbot_api/main.py's lifespan resolution: prefer
    the MAILBOT_POLICY_PATH env var if set; otherwise fall back to the
    repo-conventional ``router/policy.yaml`` relative to the project root.

    Returns the DIRECTORY containing the files (so both filenames can
    be appended). Falls back to ``Path("router").resolve()`` if the
    env var is unset — matches Story 9-1's docker-compose bind-mount
    target.

    Env-var read goes through ``mailbot_api.config.get_secret_optional``
    per Rule F (single env-read site; verbs/* are not allowlisted for
    direct ``os.environ`` access).
    """
    env_policy_path = get_secret_optional("MAILBOT_POLICY_PATH", default="").strip()
    if env_policy_path:
        return Path(env_policy_path).resolve().parent
    return Path("router").resolve()


def _persistent_error(error: str) -> SetModelPersistentOut:  # noqa: F821 — forward ref defined below
    """Helper for OQ-3 actionable-error paths."""
    return SetModelPersistentOut(
        ok=False,
        task=None,
        model=None,
        file_path=None,
        effective_after_reload_ms=None,
        error=error,
    )


class SetModelPersistentOut(BaseModel):
    """Story 9-4 AC-1 response shape for ``set_model_persistent``."""

    ok: bool
    task: str | None = None
    model: str | None = None
    file_path: str | None = None
    effective_after_reload_ms: int | None = None
    error: str | None = None


async def set_model_persistent(
    *,
    db_path: str,  # noqa: ARG001 — unused (no DB writes); kept for verb-signature parity
    task: str,
    model: str,
    session_id: str | None = None,
) -> SetModelPersistentOut:
    """Story 9-4 AC-1: persistent per-task model override.

    Validates inputs against the current `snapshot_for_dispatch()` task
    set + the Story 9-3 `_MODEL_ALIASES` model set, then atomically writes
    `router/policy.user-overrides.yaml` and polls for hot-reload pickup.

    OQ-3: the verb REFUSES to proceed if the target file is absent or
    read-only — first-write must be host-side bootstrap because
    watchfiles cannot watch a file that did not exist at watcher-start
    time (Story 9-1 hot-reload contract limitation).

    ``session_id`` is captured for structured-log audit visibility only
    (single-user reality per Story 9-3 OQ-1).
    """
    # ---- (1) Validate task name against current policy snapshot ----
    try:
        snapshot = snapshot_for_dispatch()
    except RuntimeError as exc:
        return _persistent_error(
            f"policy snapshot not loaded; cannot validate task name ({exc})"
        )
    known_tasks = sorted(snapshot.tasks.keys())
    if task not in snapshot.tasks:
        return _persistent_error(
            f"unknown task: {task!r}; known tasks: " + ", ".join(known_tasks)
        )

    # ---- (2) Validate model id (reuse Story 9-3's _normalize_model_id) ----
    normalized_model = _normalize_model_id(model)
    if normalized_model is None:
        allowed = sorted(set(_MODEL_ALIASES.keys()) | _ALLOWED_FULL_MODEL_IDS)
        return _persistent_error(
            f"unknown model: {model!r}; allowed (aliases + full IDs): "
            + ", ".join(allowed)
        )

    # ---- (3) OQ-3 file-state preconditions ----
    policy_dir = _resolve_policy_dir()
    overrides_path = policy_dir / _USER_OVERRIDES_FILENAME
    if not overrides_path.exists():
        return _persistent_error(
            f"{overrides_path} is not bind-mounted as a writable file. "
            f"Run the host-side bootstrap: "
            f"'cp router/policy.user-overrides.yaml.example "
            f"router/policy.user-overrides.yaml && "
            f"docker compose restart mailbot-api', then re-issue this command. "
            f"Reason: watchfiles cannot watch a file that did not exist at "
            f"watcher-start time (Story 9-1 hot-reload contract limitation, "
            f"see docs/policy-overrides.md)."
        )
    if not os.access(overrides_path, os.W_OK):
        return _persistent_error(
            f"{overrides_path} exists but is not writable. Verify "
            f"docker-compose.yml mounts it RW (no ':ro' suffix) and that "
            f"host file permissions allow the mailbot container user to "
            f"write (Story 9-1 F7 carry-forward)."
        )

    # ---- (4) Capture pre-write state for audit + reload-poll ----
    version_before = snapshot.version
    baseline_model = snapshot.tasks[task].model
    try:
        overrides_data = read_user_overrides_raw(overrides_path)
    except UserOverridesWriteError as exc:
        return _persistent_error(
            f"cannot read current overrides file: {exc.details}. "
            f"Inspect the file manually before re-issuing."
        )
    prev_overridden_model: str | None = None
    tasks_dict = overrides_data["tasks"]
    if task in tasks_dict and isinstance(tasks_dict[task], dict):
        prev_overridden_model = tasks_dict[task].get("model")
    elif task in tasks_dict and tasks_dict[task] is None:
        # Existing entry that's None — treat as absent for read purposes,
        # but ensure we replace it with a dict-shaped entry below.
        tasks_dict[task] = {}

    # ---- (5) Apply the shallow-leaf update ----
    entry = tasks_dict.setdefault(task, {})
    if not isinstance(entry, dict):
        # Defensive: an operator-edited file may have shaped tasks[T] as a
        # scalar. Refuse to silently coerce; surface so Adam can inspect.
        return _persistent_error(
            f"current overrides file has tasks.{task} as a non-mapping "
            f"({type(entry).__name__}). Edit the file manually to fix the "
            f"shape before re-issuing this command."
        )
    entry["model"] = normalized_model

    # ---- (6) Atomic write ----
    try:
        new_sha8 = write_user_overrides_atomic(overrides_path, overrides_data)
    except UserOverridesWriteError as exc:
        return _persistent_error(
            f"atomic write failed: {exc.details}. The original "
            f"{overrides_path.name} is unchanged (atomic-replace contract)."
        )

    # ---- (7) Structured-log audit emit ----
    _log.info(
        "persistent model override applied",
        extra={
            "event": "policy.user-overrides.set_persistent",
            "task": task,
            "model": normalized_model,
            "prev_model_baseline": baseline_model,
            "prev_model_overridden": prev_overridden_model,
            "file_sha8_after_write": new_sha8,
            "session_id": session_id,
        },
    )

    # ---- (8) Poll for hot-reload pickup ----
    t0 = time.perf_counter()
    elapsed_ms = 0
    reload_observed = False
    while (time.perf_counter() - t0) < _PERSISTENT_HOT_RELOAD_TIMEOUT_S:
        await asyncio.sleep(_PERSISTENT_HOT_RELOAD_POLL_S)
        current_version = snapshot_for_dispatch().version
        if current_version != version_before:
            reload_observed = True
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            break
    if not reload_observed:
        return SetModelPersistentOut(
            ok=False,
            task=task,
            model=normalized_model,
            file_path=str(overrides_path),
            effective_after_reload_ms=None,
            error=(
                "hot-reload not observed within "
                f"{int(_PERSISTENT_HOT_RELOAD_TIMEOUT_S * 1000)}ms. "
                f"The file WAS written successfully; either the watcher is "
                f"misconfigured (check docker-compose bind-mount + watchfiles "
                f"startup logs) or a manual mailbot-api restart is required."
            ),
        )

    return SetModelPersistentOut(
        ok=True,
        task=task,
        model=normalized_model,
        file_path=str(overrides_path),
        effective_after_reload_ms=elapsed_ms,
        error=None,
    )


# ---------------------------------------------------------------------------
# Story 9-4 — `/model` (no args) inspect verb
# ---------------------------------------------------------------------------


class InspectPolicyOut(BaseModel):
    """Story 9-4 AC-2 response shape for ``inspect_policy``."""

    markdown: str
    task_count: int
    override_count: int
    file_path: str


def _format_iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _read_baseline_models() -> dict[str, str]:
    """Source baseline `policy_entry.model` per task by reading
    router/policy.yaml directly (NOT the merged snapshot — we need the
    pre-merge value to populate the inspect table's baseline column).

    Goes through the policy-module helper to stay inside the YAML-load
    boundary. Returns ``{task_name: model_id}``; on failure returns
    ``{}`` and the inspect verb's caller renders baseline rows with
    ``"?"`` placeholders rather than crashing.
    """
    policy_path = _resolve_policy_dir() / _POLICY_FILENAME
    try:
        raw = read_user_overrides_raw(policy_path)  # accepts both schema shapes
    except UserOverridesWriteError:
        return {}
    out: dict[str, str] = {}
    for task_name, entry in raw.get("tasks", {}).items():
        if isinstance(entry, dict):
            model_val = entry.get("model")
            if isinstance(model_val, str):
                out[task_name] = model_val
    return out


def _read_override_models() -> dict[str, str]:
    """Source override `model` field per task from policy.user-overrides.yaml.
    Returns ``{task_name: override_model_id}`` only for tasks where the
    override file specifies a `model` field (matches the per-task provenance
    set from ``policy.overrides_applied`` for the model-field case)."""
    overrides_path = _resolve_policy_dir() / _USER_OVERRIDES_FILENAME
    try:
        raw = read_user_overrides_raw(overrides_path)
    except UserOverridesWriteError:
        return {}
    out: dict[str, str] = {}
    for task_name, entry in raw.get("tasks", {}).items():
        if isinstance(entry, dict):
            model_val = entry.get("model")
            if isinstance(model_val, str):
                out[task_name] = model_val
    return out


async def inspect_policy(
    *,
    db_path: str,  # noqa: ARG001 — status report; degraded read stays in-memory (Story 10.5.1 scope)
    session_id: str | None = None,  # noqa: ARG001 — single-user; audit-only
) -> InspectPolicyOut:
    """Story 9-4 AC-2: render the current effective policy as a markdown
    table for Discord display via Hermes.

    Composes three layers:
      (a) Per-task table (baseline_model | override_model | effective_model
          | lane | sensitivity | last_changed). Overridden rows prefix the
          task name with 🔧.
      (b) Degraded-mode line (from get_guard().is_degraded()).
      (c) Active one-shot override line (from _get_active_oneshot_override()).
    """
    try:
        snapshot = snapshot_for_dispatch()
    except RuntimeError as exc:
        return InspectPolicyOut(
            markdown=f"⚠️ policy snapshot not loaded: {exc}",
            task_count=0,
            override_count=0,
            file_path=str(_resolve_policy_dir() / _USER_OVERRIDES_FILENAME),
        )

    overrides_path = _resolve_policy_dir() / _USER_OVERRIDES_FILENAME
    baseline_models = _read_baseline_models()
    override_models = _read_override_models()
    overridden_set = snapshot.overrides_applied

    # last_changed = file-level mtime (per-task mtime is out of scope for v1).
    last_changed_str: str = "—"
    if overrides_path.exists():
        try:
            last_changed_str = _format_iso_utc(overrides_path.stat().st_mtime)
        except OSError:
            last_changed_str = "—"

    rows: list[str] = []
    header = (
        "| task | baseline_model | override_model | effective_model | lane | "
        "sensitivity | last_changed |"
    )
    sep = "|---|---|---|---|---|---|---|"
    rows.append(header)
    rows.append(sep)
    for task_name in sorted(snapshot.tasks.keys()):
        entry = snapshot.tasks[task_name]
        is_overridden = task_name in overridden_set
        prefix = "🔧 " if is_overridden else ""
        baseline_m = baseline_models.get(task_name, "?")
        override_m = override_models.get(task_name, "—") if is_overridden else "—"
        last_ch = last_changed_str if is_overridden else "—"
        rows.append(
            f"| {prefix}{task_name} | {baseline_m} | {override_m} | "
            f"{entry.model} | {entry.lane} | {entry.sensitivity} | {last_ch} |"
        )

    # Degraded-mode + one-shot lines.
    # Story 10.5.1 scope note: AC-2 makes the DISPATCH-GOVERNING degraded reads
    # authoritative (the two router.py gates). `inspect_policy` is a pure status
    # REPORT — it does not govern any mailbox write — so it keeps the in-memory
    # `is_degraded()` read. Making a report read fail-closed would LIE ("Active")
    # on a transient DB-read error, which is worse for an operator than a
    # momentarily-stale mirror. The authoritative cross-process degraded read
    # lives where it changes a dispatch decision, not on the display path.
    degraded_line = (
        "Current degraded mode state: "
        + ("Active" if get_guard().is_degraded() else "Not active")
    )
    active_oneshot = _get_active_oneshot_override()
    if active_oneshot is None:
        one_shot_line = "Active one-shot override: None"
    else:
        one_shot_line = (
            f"Active one-shot override: model={active_oneshot.model}, "
            f"expires_at={active_oneshot.expires_at}"
        )

    markdown_body = "\n".join(rows) + "\n\n" + degraded_line + "\n" + one_shot_line

    return InspectPolicyOut(
        markdown=markdown_body,
        task_count=len(snapshot.tasks),
        override_count=len(overridden_set),
        file_path=str(overrides_path),
    )


__all__ = [
    "InspectPolicyOut",
    "OneShotOverride",
    "PauseOut",
    "ResumeOut",
    "SetModelOneShotOut",
    "SetModelPersistentOut",
    "UserOverridesWriteError",
    "_consume_oneshot_override",
    "_get_active_oneshot_override",
    "_reset_oneshot_override_for_test",
    "_set_oneshot_override",
    "inspect_policy",
    "pause_router",
    "resume_router",
    "set_model_oneshot",
    "set_model_persistent",
]
