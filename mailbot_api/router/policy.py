"""Per-task routing policy schema, loader, and hot-reload per Story 2-2.

Architecture §"D11: policy.yaml reload semantics" is the contract:
  * validation-or-no-swap on every reload
  * mid-call race acceptable — each `ask_router` call captures the
    `PolicyTable` instance at dispatch time and the call's lifecycle uses
    that snapshot regardless of subsequent reloads.

Story 9-1 extension: companion-file user-overrides pattern.
  * Baseline `router/policy.yaml` ships in-image / bind-mounted read-only
    (source-of-truth, gitted).
  * Companion `router/policy.user-overrides.yaml` is bind-mounted read-write
    (operator-state, gitignored, written by Story 9-4 set_model_persistent).
  * Merge happens at load time via _merge_user_overrides with shallow-leaf
    semantics — override leaves (per-field) replace baseline leaves; absent
    fields keep baseline; unknown tasks logged + discarded.
  * The post-merge PolicyTable.version carries a "+overrides:<sha256[:8]>"
    suffix when overrides are applied, so Story 9-6 benchmark_runs.cohort_key
    can distinguish baseline-only runs from override-augmented runs.
  * Malformed overrides are non-fatal: log ERROR, continue with baseline,
    do NOT swap (validation-or-no-swap symmetric across both files).

Public API:
  * ``PolicyEntry`` — Pydantic model for a single task's routing decision
  * ``PolicyTable`` — Pydantic model with the full task table + a version string
  * ``UserOverridesEntry`` — Pydantic model for a single task's per-field override
    (every field Optional; mirrors PolicyEntry fields)  [Story 9-1]
  * ``UserOverridesTable`` — Pydantic model wrapping {tasks: dict}  [Story 9-1]
  * ``PolicyValidationError`` — raised by ``load_policy`` on baseline failures
  * ``load_policy(path, *, overrides_path=None)`` — pure function: reads +
    validates baseline + (if path given AND file exists) overrides; returns
    the post-merge PolicyTable. Malformed overrides are logged + ignored.
  * ``get_policy()`` / ``set_policy_snapshot()`` — module-level snapshot accessors
  * ``snapshot_for_dispatch()`` — semantic alias for ``get_policy()`` used by
    Story 2-4's ``ask_router`` to make the dispatch-time-capture intent explicit
  * ``policy_reload_loop(path, *, overrides_path=None, stop_event)`` —
    watchfiles-driven reloader; watches BOTH files when overrides_path given.

This module is the ONLY place YAML parsing happens against ``policy.yaml`` AND
``policy.user-overrides.yaml``. ``scripts/check_boundaries.py`` enforces this
via a ``yaml.safe_load`` / ``yaml.load`` allowlist.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from watchfiles import awatch

from mailbot_api.router.errors import sanitize_error

# CR-F1 (Story 9-1, sonnet-4-6): override-load status enum surfaces to
# policy_reload_loop so it can honor AC-2's "no swap on malformed override"
# discipline. Values:
#   "applied"      — overrides file existed and was successfully merged
#   "absent"       — overrides file does not exist (no swap discrimination)
#   "empty"        — overrides file existed but yielded zero applied fields
#                    (zero-byte, tasks: {}, or all-None entries); treated
#                    identically to "absent" for version-suffix purposes
#                    per CR-F3 (Story 9-1 AC-6 "empty or absent → no suffix").
#   "parse_failed" — overrides file existed but YAML/schema/IO failed; the
#                    reload loop MUST refuse the swap to preserve the prior
#                    merged snapshot per AC-2.
OverrideLoadStatus = Literal["applied", "absent", "empty", "parse_failed"]

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

    Story 9-4 AC-2: ``overrides_applied`` carries per-task provenance — the
    set of task names whose merged entry differs from baseline due to
    ``policy.user-overrides.yaml`` shallow-leaf merging. The router uses
    this to emit ``ModelChosenReason.OVERRIDE_SLASH_PERSISTENT`` instead of
    ``policy_default(task)`` for overridden tasks. Empty frozenset on
    baseline-only snapshots; populated only when an override file applied
    at least one field. Pydantic stores it as a frozenset — immutable +
    hashable, matches the snapshot semantic of "captured at dispatch time,
    never mutated mid-call."
    """

    model_config = ConfigDict(extra="forbid")

    tasks: dict[str, PolicyEntry] = Field(min_length=1)
    version: str
    overrides_applied: frozenset[str] = Field(default_factory=frozenset)


class UserOverridesEntry(BaseModel):
    """Story 9-1: per-field override for a single task entry.

    Every field is Optional[T] = None. The merge function applies only the
    fields that the override caller actually set (per Pydantic's
    ``model_dump(exclude_none=True)`` semantics). Fields left as None are
    treated as "not specified" and the baseline value is preserved.

    ``extra="forbid"`` defends against typos in operator-edited override
    files — e.g., ``modle: claude-haiku-4-5`` would raise rather than
    silently no-op.
    """

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    prompt_version: str | None = None
    escalate: bool | None = None
    max_tokens_out: int | None = None
    lane: Literal["interactive", "batch"] | None = None
    sensitivity: Literal["normal", "sensitive", "confidential", "any"] | None = None
    notes: str | None = None
    demotion_hypothesis: str | None = None
    promotion_hypothesis: str | None = None
    response_cache_ttl_seconds: int | None = None
    cache_warm: bool | None = None


class UserOverridesTable(BaseModel):
    """Story 9-1: the full user-overrides file shape.

    ``tasks`` defaults to an empty dict so an empty/skeleton overrides file
    (``tasks: {}`` or just ``{}``) parses without error and produces a
    merged result identical to the baseline.

    ``version`` is optional and ignored by the merge — the post-merge
    effective version is derived in ``_compute_merged_version`` from the
    baseline version + the SHA-256 of the overrides file contents.
    """

    model_config = ConfigDict(extra="forbid")

    tasks: dict[str, UserOverridesEntry] = Field(default_factory=dict)
    version: str | None = None


class PolicyValidationError(Exception):
    """Raised by ``load_policy`` for baseline-policy failure shapes only.

    Story 9-1: overrides-file failures are NON-fatal — they are logged and
    the baseline policy is returned. Only baseline failures (missing file,
    malformed YAML, schema violation) raise this exception. The
    ``details`` attribute carries the sanitized human-readable description.
    """

    def __init__(self, details: str) -> None:
        super().__init__(details)
        self.details = details

    def __str__(self) -> str:
        return f"PolicyValidationError: {self.details}"


def _compute_overrides_hash(text: str) -> str:
    """Story 9-1 AC-6: SHA-256 first-8-hex-chars of the overrides file content.

    Content-addressed so whitespace-only edits DO change the hash (that is a
    feature — they may correspond to operator-intentional re-saves). 32-bit
    truncation is operationally acceptable; collision probability is
    negligible across the cadence at which an operator hand-edits this file.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _compute_merged_version(baseline_version: str, overrides_text: str | None) -> str:
    """Story 9-1 AC-6: derive the post-merge effective version string.

    * ``overrides_text is None`` (overrides file absent OR empty after merge):
      return ``baseline_version`` unchanged. No ``+overrides:`` suffix.
    * Otherwise: return ``f"{baseline_version}+overrides:{hash[:8]}"``.

    The result flows into ``router_calls`` audit rows (via the snapshot's
    ``version`` field) and into Story 9-6's ``benchmark_runs.cohort_key``
    so override-augmented runs are distinguishable from baseline runs.
    """
    if overrides_text is None:
        return baseline_version
    return f"{baseline_version}+overrides:{_compute_overrides_hash(overrides_text)}"


def _merge_user_overrides(
    baseline: PolicyTable, overrides: UserOverridesTable
) -> tuple[dict[str, PolicyEntry], int, frozenset[str]]:
    """Story 9-1: apply shallow-leaf user overrides to the baseline policy.

    **Shallow-leaf semantics — four contract points:**

    1. **Override leaves replace baseline leaves (per-field, NOT per-task-block).**
       If overrides specify ``tasks.draft_reply.model``, only that single
       field is replaced; other ``draft_reply`` fields keep their baseline
       values.

    2. **Unknown tasks are dropped with a warning.** An override on a task
       key not present in the baseline is logged as
       ``event="policy.user-overrides.unknown_task"`` and discarded. This is
       defensive — it protects against typos that would otherwise create
       phantom task entries the rest of the system cannot route through.

    3. **None/absent fields in override = baseline preserved.** Pydantic's
       ``model_dump(exclude_none=True)`` is the source-of-truth for "which
       fields did the override actually set." An explicit ``model: null`` in
       YAML is treated as "not specified," not as "set the model to None."

    4. **The merge is total.** Every baseline task survives unless explicitly
       overridden. There is no negation primitive — overrides cannot DELETE a
       task. (This is deliberate: Adam-decision deferred to Epic-9 retro if a
       use case emerges.)

    **Examples:**

    Single-field override::

        baseline.tasks["draft_reply"] = PolicyEntry(
            model="claude-haiku-4-5", prompt_version="v3", escalate=False, ...
        )
        overrides.tasks["draft_reply"] = UserOverridesEntry(model="claude-opus-4-7")
        # result.tasks["draft_reply"]:
        #   PolicyEntry(model="claude-opus-4-7", prompt_version="v3", escalate=False, ...)
        #   ^^^ only model changed; prompt_version + escalate + all other fields preserved

    Multi-field override::

        baseline.tasks["coarse_class"] = PolicyEntry(
            model="qwen2.5:3b", prompt_version="v1", lane="batch", ...
        )
        overrides.tasks["coarse_class"] = UserOverridesEntry(
            model="claude-haiku-4-5", lane="interactive"
        )
        # result.tasks["coarse_class"]:
        #   PolicyEntry(model="claude-haiku-4-5", prompt_version="v1", lane="interactive", ...)
        #   ^^^ model + lane both changed; prompt_version preserved
    """
    merged_tasks: dict[str, PolicyEntry] = dict(baseline.tasks)
    applied_field_count = 0
    overridden_task_names: set[str] = set()
    for task_key, override_entry in overrides.tasks.items():
        if task_key not in baseline.tasks:
            _log.warning(
                "user override targets unknown task; discarding",
                extra={
                    "event": "policy.user-overrides.unknown_task",
                    "task_key": task_key,
                },
            )
            continue
        # exclude_none=True is the contract: only fields the override
        # actually set get applied. Pydantic's model_copy(update={...})
        # produces a new PolicyEntry instance — original untouched.
        override_fields = override_entry.model_dump(exclude_none=True)
        if not override_fields:
            # An override entry with all fields None — treat as no-op.
            # Still log at DEBUG so operators see the touch.
            _log.debug(
                "user override targets task with no fields set; no-op",
                extra={
                    "event": "policy.user-overrides.empty_entry",
                    "task_key": task_key,
                },
            )
            continue
        merged_tasks[task_key] = baseline.tasks[task_key].model_copy(update=override_fields)
        applied_field_count += len(override_fields)
        # Story 9-4 AC-2: per-task provenance. Only tasks where at least
        # one field was effectively applied (passed the not-None +
        # known-task gates) appear here. Tasks dropped as unknown or
        # all-None do NOT appear, so the set reflects "what observers see
        # as effectively-overridden" — consistent with applied_field_count.
        overridden_task_names.add(task_key)
    # CR-F6 (Story 9-1, sonnet-4-6): return the raw task dict + the
    # applied-field count. The caller (load_policy) is responsible for
    # composing the final PolicyTable with the correct version-suffix
    # — this function does not know whether the overrides file existed
    # vs was empty. applied_field_count is the count of override fields
    # actually merged (CR-F3 uses it to suppress +overrides: suffix when
    # the override file is operationally empty).
    # Story 9-4 AC-2: also return the per-task provenance frozenset so the
    # snapshot can answer "is this task overridden?" at audit-emit time
    # without re-running the merge.
    return merged_tasks, applied_field_count, frozenset(overridden_task_names)


# ---------------------------------------------------------------------------
# Story 9-4: helpers for set_model_persistent (verbs/router_control.py).
#
# Co-located with the existing YAML readers so the `yaml.safe_load` /
# `yaml.safe_dump` calls remain inside the Story-2-2 AC-12 + Story-9-1
# boundary: the policy module is the ONLY place where router policy YAML
# is parsed or written. Verbs reach into these helpers rather than
# importing `yaml` directly. The boundary checker enforces this via the
# `_YAML_LOAD_ALLOW` frozenset.
# ---------------------------------------------------------------------------


class UserOverridesWriteError(Exception):
    """Raised by ``write_user_overrides_atomic`` on any failure path
    (parent missing, target not writable, atomic-replace failure). The
    ``set_model_persistent`` verb maps this to an actionable error message
    in ``SetModelPersistentOut.error`` per Story 9-4 OQ-3."""

    def __init__(self, details: str) -> None:
        super().__init__(details)
        self.details = details


def read_user_overrides_raw(path: Path) -> dict[str, Any]:
    """Story 9-4: read the current `policy.user-overrides.yaml` content as
    a Python dict, normalizing edge cases for the verb's read-modify-write
    cycle.

    Contract:
    * Missing file → returns ``{"tasks": {}}`` (caller's first write will
      create the file; the file-existence pre-check is the caller's job
      because OQ-3 requires it to refuse first-write when watchfiles can't
      pick up a newly-appeared file).
    * Zero-byte / comments-only file → returns ``{"tasks": {}}``.
    * Top-level not a mapping → raises ``UserOverridesWriteError`` (the
      verb should not silently overwrite a list/scalar).
    * Schema-invalid mapping (unknown fields, wrong types) is NOT validated
      here — that's ``UserOverridesTable.model_validate``'s job at LOAD
      time. The verb reads the raw dict, mutates it, and writes it back;
      validation happens on the next hot-reload via ``load_policy_with_status``.
    """
    if not path.exists():
        return {"tasks": {}}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UserOverridesWriteError(
            f"read failed for {path}: {sanitize_error(exc)}"
        ) from exc
    if not text.strip():
        return {"tasks": {}}
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise UserOverridesWriteError(
            f"YAML parse failed for {path}: {sanitize_error(exc)}"
        ) from exc
    if raw is None:
        return {"tasks": {}}
    if not isinstance(raw, dict):
        raise UserOverridesWriteError(
            f"top-level must be a mapping; got {type(raw).__name__}"
        )
    raw.setdefault("tasks", {})
    if not isinstance(raw["tasks"], dict):
        raise UserOverridesWriteError(
            f"'tasks' must be a mapping; got {type(raw['tasks']).__name__}"
        )
    return raw


def write_user_overrides_atomic(path: Path, data: dict[str, Any]) -> str:
    """Story 9-4 AC-1: atomic write to `policy.user-overrides.yaml`.

    Contract:
    * ``data`` must be the post-mutation dict (caller is responsible for
      the read-modify-update cycle via ``read_user_overrides_raw``).
    * The write is atomic via the standard tempfile + fsync + os.replace
      idiom. The tempfile is created in ``path.parent`` so ``os.replace``
      stays on the same filesystem (atomic by POSIX).
    * On any I/O failure during the write, the tempfile is removed and
      ``UserOverridesWriteError`` is raised. The original target file is
      left in its pre-call state (the whole point of atomic write).
    * The parent directory must exist; if not, raises. The verb's OQ-3
      pre-flight will have already confirmed the file is writable, which
      implicitly confirms the parent exists.

    Returns the SHA-256 first-8-hex of the new file content (for the
    audit-log emission in ``set_model_persistent``).
    """
    if not path.parent.exists():
        raise UserOverridesWriteError(
            f"parent directory does not exist: {path.parent}"
        )
    new_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".policy.user-overrides.",
        suffix=".yaml.tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(new_text)
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
        except OSError as exc:
            raise UserOverridesWriteError(
                f"tempfile write failed: {sanitize_error(exc)}"
            ) from exc
        try:
            os.replace(tmp_path_str, str(path))
        except OSError as exc:
            raise UserOverridesWriteError(
                f"atomic replace failed: {sanitize_error(exc)}"
            ) from exc
    except UserOverridesWriteError:
        # Best-effort tempfile cleanup. If unlink itself fails (rare), let
        # the verb's structured log surface the original error — leaking
        # a tmpfile is recoverable; double-raising obscures the cause.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return _compute_overrides_hash(new_text)


def load_policy(path: Path, *, overrides_path: Path | None = None) -> PolicyTable:
    """Read + validate baseline ``policy.yaml`` + optional companion overrides.

    Convenience wrapper: returns only the ``PolicyTable``. Callers that need
    to discriminate "override applied" vs "override parse failed" vs
    "override absent" (e.g., ``policy_reload_loop``) should use
    ``load_policy_with_status`` instead and honor the AC-2 "no swap on
    parse_failed" discipline.

    **Story 9-1 contract:**

    * Baseline: required. Any failure (missing file, malformed YAML, schema
      violation) raises ``PolicyValidationError`` — same behavior as
      pre-Story-9-1.
    * Overrides: optional. If ``overrides_path`` is None, the loader looks
      for ``policy.user-overrides.yaml`` next to the baseline. If neither
      explicit-path nor default-path resolves to an existing file, the
      baseline is returned unchanged (version has no ``+overrides:`` suffix).
    * Malformed overrides: NON-fatal at this layer. Logged as
      ``policy.user-overrides.parse_failed`` with sanitized details; baseline
      is returned unchanged. The reload loop uses ``load_policy_with_status``
      to detect this case and skip the swap per AR-D11-1.

    All baseline failure shapes converge on ``PolicyValidationError``.
    Pydantic validation errors get their JSON-shaped error list stringified
    and run through ``sanitize_error`` so any secret accidentally pasted into
    the YAML cannot leak via the failure log.
    """
    table, _status = load_policy_with_status(path, overrides_path=overrides_path)
    return table


def load_policy_with_status(
    path: Path, *, overrides_path: Path | None = None
) -> tuple[PolicyTable, OverrideLoadStatus]:
    """Story 9-1 CR-F1: load policy + return the override-load status.

    Returns ``(table, status)`` where status is one of:

    * ``"applied"``    — overrides file existed and at least one field was
                        merged; ``table.version`` carries ``+overrides:`` suffix
    * ``"absent"``     — overrides file does not exist; ``table`` is baseline
    * ``"empty"``      — overrides file existed but yielded zero merged
                        fields (zero-byte, ``tasks: {}``, unknown-task-only,
                        or all-None entries); per CR-F3 the version has NO
                        suffix because the file is operationally indistinguishable
                        from absent for cohort_key purposes
    * ``"parse_failed"`` — overrides file existed but YAML/schema/IO failed;
                        ``table`` is baseline-only; ``policy_reload_loop``
                        MUST refuse the swap to preserve the prior merged
                        snapshot per AC-2

    Baseline failures still raise ``PolicyValidationError`` unchanged.
    """
    # ----- BASELINE LOAD (same as pre-Story-9-1) -----
    try:
        baseline_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyValidationError(f"policy file not found: {path}") from exc
    except OSError as exc:
        raise PolicyValidationError(
            sanitize_error(exc) + f" (path={path})"
        ) from exc

    try:
        baseline_raw = yaml.safe_load(baseline_text)
    except yaml.YAMLError as exc:
        raise PolicyValidationError(
            "YAML parse failed: " + sanitize_error(exc)
        ) from exc

    if not isinstance(baseline_raw, dict):
        raise PolicyValidationError(
            f"policy.yaml top-level must be a mapping; got {type(baseline_raw).__name__}"
        )

    try:
        baseline = PolicyTable.model_validate(baseline_raw)
    except ValidationError as exc:
        raise PolicyValidationError(sanitize_error(exc)) from exc

    # ----- OVERRIDES LOAD (Story 9-1) -----
    # Resolve overrides_path: explicit argument > sibling default > none.
    resolved_overrides_path: Path | None
    if overrides_path is not None:
        resolved_overrides_path = overrides_path
    else:
        sibling = path.parent / "policy.user-overrides.yaml"
        resolved_overrides_path = sibling if sibling.exists() else None

    if resolved_overrides_path is None or not resolved_overrides_path.exists():
        return baseline, "absent"

    # Read + parse + validate. On any failure: log + return (baseline, "parse_failed").
    try:
        overrides_text = resolved_overrides_path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.error(
            "user-overrides file read failed; falling back to baseline",
            extra={
                "event": "policy.user-overrides.parse_failed",
                "path": str(resolved_overrides_path),
                "details": sanitize_error(exc),
            },
        )
        return baseline, "parse_failed"

    try:
        overrides_raw = yaml.safe_load(overrides_text)
    except yaml.YAMLError as exc:
        _log.error(
            "user-overrides YAML parse failed; falling back to baseline",
            extra={
                "event": "policy.user-overrides.parse_failed",
                "path": str(resolved_overrides_path),
                "details": sanitize_error(exc),
            },
        )
        return baseline, "parse_failed"

    if overrides_raw is None:
        # Empty file (zero bytes or comments-only). Per CR-F3 + AC-6:
        # empty file is operationally indistinguishable from absent file
        # for the version-suffix surface. Return baseline + "empty".
        return baseline, "empty"

    if not isinstance(overrides_raw, dict):
        _log.error(
            "user-overrides top-level must be a mapping; falling back to baseline",
            extra={
                "event": "policy.user-overrides.parse_failed",
                "path": str(resolved_overrides_path),
                "details": f"top-level must be mapping; got {type(overrides_raw).__name__}",
            },
        )
        return baseline, "parse_failed"

    try:
        overrides = UserOverridesTable.model_validate(overrides_raw)
    except ValidationError as exc:
        _log.error(
            "user-overrides schema validation failed; falling back to baseline",
            extra={
                "event": "policy.user-overrides.parse_failed",
                "path": str(resolved_overrides_path),
                "details": sanitize_error(exc),
            },
        )
        return baseline, "parse_failed"

    # Merge. CR-F6: receive (merged_tasks, applied_field_count, overrides_applied) directly.
    # Story 9-4 AC-2: third return element is the per-task provenance set.
    merged_tasks, applied_field_count, overrides_applied = _merge_user_overrides(
        baseline, overrides
    )

    if applied_field_count == 0:
        # CR-F3 (Story 9-1 AC-6): `tasks: {}`, unknown-task-only, or
        # all-None entries yield zero applied fields → version has NO
        # +overrides: suffix (operationally indistinguishable from absent
        # for the cohort_key surface). Baseline carries overrides_applied
        # = frozenset() by default; no provenance to propagate.
        return baseline, "empty"

    merged_version = _compute_merged_version(baseline.version, overrides_text)
    return (
        PolicyTable(
            tasks=merged_tasks,
            version=merged_version,
            overrides_applied=overrides_applied,
        ),
        "applied",
    )


_policy: PolicyTable | None = None

# F35 closure (Story 9-1.5): once the override file transitions from
# "present + applied" to "absent at runtime" via direct operator `rm`, the
# watchfiles descriptor keeps firing change events at ~310ms cadence against
# the nonexistent path. This flag tracks "we've already emitted the
# absent_at_runtime warning + announced the transition; subsequent fires
# against the still-absent path are spurious and must be silently coalesced
# until either the baseline version changes (operator edited policy.yaml,
# AC-3 resume contract) OR the watcher is restarted (F33 contract — there is
# no auto-pickup of recreated override file at runtime).
_override_absent_after_applied: bool = False


def _reset_override_absent_flag_for_test() -> None:
    """Test-only helper to clear the F35 suppression flag between tests."""
    global _override_absent_after_applied  # noqa: PLW0603
    _override_absent_after_applied = False


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


def _version_has_overrides_suffix(version: str) -> bool:
    """Story 9-1: detect whether a version string carries the override suffix."""
    return "+overrides:" in version


async def policy_reload_loop(
    path: Path,
    *,
    overrides_path: Path | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Watch baseline + (optional) overrides files; reload on either changing.

    Story 9-1 extension: ``awatch`` is called with BOTH paths when
    ``overrides_path`` is provided. The watcher fires on ANY change to
    EITHER file; the reloader re-reads the merged view from scratch each
    time (no per-file delta tracking — simpler + more robust to
    multi-file edits).

    Log event taxonomy:
      * ``policy.reloaded`` — baseline-only change OR override change that
        produced no semantic-version change vs prior snapshot
        (preserves pre-Story-9-1 log emit for Story 2-2 callers).
      * ``policy.user-overrides.swap`` — overrides-file content changed and
        the merged effective version's ``+overrides:`` suffix changed
        (i.e., the operator-visible override surface materially shifted).
      * ``policy.reload.failed`` — baseline ``PolicyValidationError``;
        DO NOT swap. Previous snapshot stays.
      * ``policy.user-overrides.parse_failed`` — emitted INSIDE ``load_policy``
        for override-file errors. The watcher does not re-emit; it just
        sees the returned baseline-only table and swaps it in (if the
        baseline itself was valid).
      * ``policy.reload.loop.error`` — defensive catch-all for non-
        ``PolicyValidationError`` exceptions during load.
    """
    # watchfiles.awatch raises FileNotFoundError on any non-existent path,
    # so we filter to files that actually exist at watcher-start time. If
    # the overrides file appears later (e.g., Story 9-4 set_model_persistent
    # creating it for the first time), the operator restarts mailbot-api to
    # pick up the new watch set. This is acceptable because:
    #   * Story 9-4 owns the create-flow and can warn operators of the
    #     restart requirement in the verb's response.
    #   * The lifespan-restart cadence is acceptable for an operator-driven
    #     one-time configuration step.
    #   * Story 9-1 still picks up MUTATIONS to a pre-existing overrides
    #     file (the common case once Adam has at least one override).
    # CR-F1 (Story 9-1.5, sonnet-4-6): function-top global declaration for
    # symmetry with set_policy_snapshot's `global _policy` pattern. The flag
    # is touched in two distinct branches below (suppression-coalesce + AC-3
    # resume-clear + absent_at_runtime arm); declaring once at function scope
    # is cleaner than three inline `global` statements.
    global _override_absent_after_applied  # noqa: PLW0603

    watch_paths: tuple[str, ...]
    paths_to_watch: list[str] = [str(path)]
    if overrides_path is not None and overrides_path.exists():
        paths_to_watch.append(str(overrides_path))
    watch_paths = tuple(paths_to_watch)

    async for _changes in awatch(*watch_paths, stop_event=stop_event):
        try:
            new_table, override_status = load_policy_with_status(
                path, overrides_path=overrides_path
            )
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

        # CR-F1 (Story 9-1, sonnet-4-6): AC-2 "no swap on malformed override"
        # — when the override side parse-failed, the baseline-only table is
        # returned, but the watcher MUST refuse the swap so the prior merged
        # snapshot stays in place. The parse_failed event was already logged
        # inside load_policy_with_status; no additional log here.
        if override_status == "parse_failed":
            continue

        # Compare to previous snapshot to choose the right event.
        prev_version = _policy.version if _policy is not None else ""
        new_version = new_table.version
        prev_had_overrides = _version_has_overrides_suffix(prev_version)
        new_has_overrides = _version_has_overrides_suffix(new_version)

        # F35 closure (Story 9-1.5): spurious-fire suppression + F33
        # contract preservation. Once we've announced the absent-after-
        # applied transition:
        #   (a) subsequent fires returning override_status=="absent" with
        #       prev_version==new_version are watchfiles thrashing against
        #       the deleted path — suppress silently (the F35 flood).
        #   (b) fires returning override_status=="applied" (the operator
        #       recreated the override file at runtime) MUST also be
        #       suppressed: F33 says the watcher cannot reliably observe a
        #       recreated file; on platforms where it does (Windows
        #       ReadDirectoryChangesW), AC-4 mandates we still ignore the
        #       re-creation so the contract holds uniformly across
        #       platforms. Operators must restart mailbot-api to re-arm.
        # AC-3 resume contract: clear the flag when the baseline version
        # changes between fires (operator edited policy.yaml).
        # CR-F2 (Story 9-1.5, sonnet-4-6): the resume condition must also
        # fire when override_status == "empty" — load_policy_with_status
        # returns "empty" (not "absent") when an operator creates an empty
        # override file (zero-byte, comments-only, tasks: {}, or all-None
        # entries). If we only checked "absent", a simultaneous create-
        # empty-override + edit-baseline would leave the suppression flag
        # armed and silently drop the baseline change. Both shapes are
        # operationally indistinguishable for the suppression surface per
        # Story 9-1 CR-F3 (no +overrides: suffix in either case).
        if _override_absent_after_applied:
            # AC-3: baseline change wakes us back up.
            baseline_changed = (
                override_status in ("absent", "empty")
                and prev_version != new_version
            )
            if baseline_changed:
                _override_absent_after_applied = False
            else:
                # Both (a) absent-spurious and (b) recreated-file fires
                # are silently coalesced. No log emission.
                continue

        if new_has_overrides or prev_had_overrides:
            # Either we just gained overrides, lost overrides, or the
            # overrides hash changed — all three are "operator-visible
            # override surface shifted." Emit the dedicated event.
            if prev_version != new_version:
                set_policy_snapshot(new_table)
                _log.info(
                    "policy user-overrides swap",
                    extra={
                        "event": "policy.user-overrides.swap",
                        "baseline_path": str(path),
                        "overrides_path": (
                            str(overrides_path) if overrides_path is not None else None
                        ),
                        "version_before": prev_version,
                        "version_after": new_version,
                    },
                )
                # F35 closure (Story 9-1.5): detect the absent-after-applied
                # transition — operator `rm`'d the override file at runtime.
                # Emit the one-shot WARNING that names the F33 restart
                # requirement (the watchfiles descriptor was bound to the
                # now-deleted path; auto-pickup of a recreated file is not
                # possible per the documented F33 contract). Then arm the
                # suppression flag so subsequent spurious fires against the
                # nonexistent path are silently coalesced per AC-2.
                # set_policy_snapshot has already cleared the flag IF the
                # new snapshot still carried +overrides: — that's not this
                # branch (we're here because the override surface lost the
                # suffix). So setting the flag here is unconditional.
                if prev_had_overrides and not new_has_overrides and override_status == "absent":
                    _override_absent_after_applied = True
                    _log.warning(
                        "override file deleted at runtime; subsequent edits "
                        "will require mailbot-api restart to re-arm watcher "
                        "(watchfiles cannot watch newly-appeared paths per "
                        "F33 upstream contract)",
                        extra={
                            "event": "policy.user-overrides.absent_at_runtime",
                            "baseline_path": str(path),
                            "overrides_path": (
                                str(overrides_path)
                                if overrides_path is not None
                                else None
                            ),
                            "baseline_version": new_version,
                        },
                    )
                continue
            # Versions identical despite override-suffix presence — could
            # happen if the watcher fired spuriously (e.g., file touched
            # but content unchanged). Emit the standard reload event and
            # still swap (the comparison is cheap; the swap is idempotent).
            set_policy_snapshot(new_table)
            _log.info(
                "policy reloaded",
                extra={"event": "policy.reloaded", "version": new_version},
            )
            continue

        # Neither pre nor post has overrides → baseline-only reload path.
        set_policy_snapshot(new_table)
        _log.info(
            "policy reloaded",
            extra={"event": "policy.reloaded", "version": new_version},
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
    "OverrideLoadStatus",
    "PolicyEntry",
    "PolicyTable",
    "PolicyValidationError",
    "UserOverridesEntry",
    "UserOverridesTable",
    "UserOverridesWriteError",
    "_reset_override_absent_flag_for_test",
    "_reset_policy_snapshot_for_test",
    "get_policy",
    "load_policy",
    "load_policy_with_status",
    "policy_reload_loop",
    "read_user_overrides_raw",
    "set_policy_snapshot",
    "snapshot_for_dispatch",
    "write_user_overrides_atomic",
]
