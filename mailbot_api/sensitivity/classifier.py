"""Sensitivity classifier wrapper per Story 3-3 AC-1 + AC-2.

The classifier wraps `ask_router(task_type="sensitivity_class", ...)` with
three additional concerns the Router itself cannot enforce:

  1. **FR-2.5 hard safeguard (AC-2)**: per-call assertion that the dispatch-time
     policy snapshot has `policy.tasks["sensitivity_class"].model == _QWEN_MODEL_ID`.
     Refuses to dispatch if policy.yaml ever drifts (the watchfiles hot-reloader
     COULD load a drifted policy between startup and a call). The startup check
     lives in `mailbot_api/sensitivity/__init__.py:assert_qwen_only`.
  2. **NFR-PRIV-1 cautious-bias floor (AC-1)**: if the classifier returns
     `sensitivity="normal"` with `confidence < 0.5`, downgrade to "sensitive"
     and record `floored_to_sensitive=True`.
  3. **Atomic write-back (AC-1)**: a single `execute_write` of sensitivity +
     all 4 companion fields + override_reason. The override_reason is
     populated by `apply_pattern_override` (called from the pipeline; this
     module supports it via the optional `pattern_override_result` arg).

Reference: epics.md lines 1157–1191 (Story 3.3 spec).
"""

from __future__ import annotations

import logging
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    EMAIL_BODY_FOR_SENSITIVITY_SELECT,
    EMAIL_SENSITIVITY_UPDATE,
)
from mailbot_api.observability.timestamps import utc_z_now
from mailbot_api.prompts.sensitivity_class.v1 import SensitivityClassOutput

# Story 6-18 (F24 closure): `SensitivityClassOutput` is imported from v1 as
# the canonical shape — v2 re-exports it. The Pydantic schema is byte-stable
# across versions; only the SYSTEM prompt text differs. Keeping a single
# canonical class lets isinstance() checks remain version-agnostic — Router
# resolves whichever prompt version `policy.yaml` names, and the returned
# `result.output` is the SAME class regardless.
#
# `sensitivity_prompt_v` (the companion column written to `emails`) is
# resolved at call time from the active policy entry — NOT from a module
# constant — so the audit row reflects the version that was ACTUALLY
# dispatched, not whatever version this module happened to import.
from mailbot_api.router.errors import ErrorCode, RouterError
from mailbot_api.router.policy import snapshot_for_dispatch
from mailbot_api.router.router import ask_router

logger = logging.getLogger(__name__)

# FR-2.5 hard-coded enforcement: the ONLY model permitted for sensitivity
# classification. Must match `router/policy.yaml`'s `sensitivity_class.model`
# value. If the project ever changes the Qwen model id, this constant + the
# policy entry + every test fixture change in lockstep.
_QWEN_MODEL_ID: Final[str] = "qwen2.5:3b-instruct-q4_K_M"

# NFR-PRIV-1 cautious-bias floor: if classifier says "normal" with confidence
# below this threshold, downgrade to "sensitive".
_FLOOR_CONFIDENCE: Final[float] = 0.5

# Caller-origin tag for `router_calls.caller_origin` per Story 2-10's caller-origin
# convention. Distinguishes ingest-pipeline sensitivity dispatches from other
# Router callers in cost-attribution dashboards.
_CALLER_ORIGIN: Final[str] = "ingest-pipeline-sensitivity"

# `caller_verb` tag for the same audit row. The "verb" namespace is reserved
# for the verb-API surface in Epic 5; sensitivity dispatches are pipeline-
# internal (not verb-invoked) so we use a synthetic value.
_CALLER_VERB: Final[str] = "ingest.sensitivity"


class SensitivityResult(BaseModel):
    """Return shape of `classify_sensitivity`. Errors-as-data per AR-PAT-4."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    email_id: str
    sensitivity: str | None = None
    confidence: float | None = None
    reason: str | None = None
    model: str | None = None
    floored_to_sensitive: bool = False
    override_reason: str | None = None  # populated by apply_pattern_override at the caller level
    error: RouterError | None = None


def _utc_iso8601_now() -> str:
    """Per AR-PAT-3: UTC ISO-8601 with Z suffix.

    Microsecond-precision since 2026-06-02 (Epic 4 retro action item #3).
    """
    return utc_z_now()


def _read_snapshot_or_error() -> tuple[Any, RouterError | None]:
    """Read the dispatch-time policy snapshot once. Returns (snapshot, None) on
    success or (None, error) on failure.

    Story 6-18 CR-3: factored out of `_assert_qwen_only_per_call` so the caller
    can read the snapshot ONCE and pass it to both the FR-2.5 safeguard AND
    the `sensitivity_prompt_v` audit-row source. Prior code did three
    independent reads (safeguard + prompt-version + router internal) which a
    watchfiles hot-reload between any two could split — the
    `emails.sensitivity_prompt_v` write and the `router_calls.prompt_version`
    write could disagree for the same dispatch.
    """
    try:
        return snapshot_for_dispatch(), None
    except RuntimeError as exc:
        return None, RouterError(
            code=ErrorCode.PROVIDER_ERROR,
            message=f"sensitivity classifier could not read policy snapshot: {exc}",
            retryable=False,
        )


def _assert_qwen_only(snapshot: Any) -> RouterError | None:
    """AC-2 per-call safeguard against a pre-loaded snapshot. Returns
    RouterError on violation, None on pass. Story 6-18 CR-3: refactored from
    `_assert_qwen_only_per_call` to accept a snapshot so the caller can read
    once and pass through — see `_read_snapshot_or_error` for context.
    """
    entry = snapshot.tasks.get("sensitivity_class")
    if entry is None:
        return RouterError(
            code=ErrorCode.PROVIDER_ERROR,
            message="policy.tasks['sensitivity_class'] is missing — FR-2.5 requires the entry",
            retryable=False,
        )
    if entry.model != _QWEN_MODEL_ID:
        logger.critical(
            "FR-2.5 violation",
            extra={
                "event": "sensitivity.fr_2_5_violation",
                "policy_model": entry.model,
                "expected_model": _QWEN_MODEL_ID,
            },
        )
        return RouterError(
            code=ErrorCode.PROVIDER_ERROR,
            message=(
                f"FR-2.5 violation: sensitivity_class policy model is "
                f"{entry.model!r} (expected {_QWEN_MODEL_ID!r}). Sensitivity "
                f"classification must dispatch to Qwen only."
            ),
            retryable=False,
        )
    return None


async def classify_sensitivity(
    email_id: str,
    *,
    db_path: str,
    override_reason: str | None = None,
) -> SensitivityResult:
    """Classify the sensitivity of an email and write the result back atomically.

    Args:
        email_id: the email's `graph_id`.
        db_path: SQLite path.
        override_reason: optional override-reason string (set by the pipeline
            after calling `apply_pattern_override`). Stored in
            `emails.sensitivity_override_reason`.

    Returns a SensitivityResult; on failure, `ok=False` and `error` populated.
    The function NEVER raises — errors-as-data per AR-PAT-4.
    """
    # Story 6-18 CR-3: read the policy snapshot ONCE for this dispatch. Both
    # the FR-2.5 safeguard AND the `sensitivity_prompt_v` audit-row write
    # source from this same snapshot, so a watchfiles hot-reload mid-dispatch
    # cannot split the audit trail between `emails.sensitivity_prompt_v` and
    # `router_calls.prompt_version`. (The router itself reads the snapshot a
    # second time; that's a separate cross-module dispatch and acceptable —
    # what we protect against here is the WRITE-side disagreement within this
    # function's atomic write of the four sensitivity companion columns.)
    snapshot, snapshot_error = _read_snapshot_or_error()
    if snapshot is None:
        assert snapshot_error is not None  # narrow for mypy
        return SensitivityResult(ok=False, email_id=email_id, error=snapshot_error)

    # AC-2 per-call FR-2.5 safeguard against the captured snapshot.
    qwen_error = _assert_qwen_only(snapshot)
    if qwen_error is not None:
        return SensitivityResult(ok=False, email_id=email_id, error=qwen_error)

    sensitivity_prompt_v = snapshot.tasks["sensitivity_class"].prompt_version

    # Read the email body for the prompt's USER_TEMPLATE placeholders.
    row = await fetchone(db_path, EMAIL_BODY_FOR_SENSITIVITY_SELECT, (email_id,))
    if row is None:
        return SensitivityResult(
            ok=False,
            email_id=email_id,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=f"email_id {email_id!r} not found in emails table",
                retryable=False,
            ),
        )
    subject, from_address, body_preview = row

    # Dispatch via the Router. ask_router handles policy resolution, prompt
    # module loading, adapter dispatch, and audit-row writing.
    result = await ask_router(
        task_type="sensitivity_class",
        content={
            "subject": subject or "",
            "sender": from_address or "",
            "body_preview": body_preview or "",
        },
        db_path=db_path,
        caller_origin=_CALLER_ORIGIN,
        caller_verb=_CALLER_VERB,
        email_id=email_id,
    )
    if not result.ok or not isinstance(result.output, SensitivityClassOutput):
        return SensitivityResult(
            ok=False,
            email_id=email_id,
            error=result.error,
            model=result.model_used or None,
        )

    parsed = result.output
    sensitivity = parsed.sensitivity
    confidence = parsed.confidence
    reason = parsed.reason
    floored = False

    # NFR-PRIV-1 cautious-bias floor (AC-1).
    if sensitivity == "normal" and confidence < _FLOOR_CONFIDENCE:
        logger.info(
            "sensitivity floored to sensitive",
            extra={
                "event": "sensitivity.floored",
                "email_id": email_id,
                "original_confidence": confidence,
                "floor_threshold": _FLOOR_CONFIDENCE,
            },
        )
        sensitivity = "sensitive"
        floored = True

    # Atomic write-back of sensitivity + all 4 companions + override_reason.
    await execute_write(
        db_path,
        EMAIL_SENSITIVITY_UPDATE,
        (
            sensitivity,
            sensitivity_prompt_v,
            confidence,
            result.model_used or _QWEN_MODEL_ID,
            _utc_iso8601_now(),
            override_reason,
            email_id,
        ),
    )

    return SensitivityResult(
        ok=True,
        email_id=email_id,
        sensitivity=sensitivity,
        confidence=confidence,
        reason=reason,
        model=result.model_used or _QWEN_MODEL_ID,
        floored_to_sensitive=floored,
        override_reason=override_reason,
    )


__all__ = [
    "SensitivityResult",
    "classify_sensitivity",
]
