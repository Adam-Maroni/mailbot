"""Pipeline orchestrator per Story 3-5.

Single-email end-to-end derivation following the FR-2.3 fixed ordering:

    sensitivity_class
        → coarse_class
        → (fine_class if class_coarse == "human")
        → summary_short
        → importance_scoring
        → action_extraction
        → embedding

Each step is idempotent (re-runs short-circuit via `derivations_idempotency`
keyed by sha256(body|prompt_v|model|task_type) — see Story 3-1's
`compute_idempotency_key`). On any step returning ok=False, the pipeline
ABORTS the remaining steps but the email row carries whatever finished
before the failure (partial derivation is permitted per epic spec).

CLI: `python -m mailbot_api.ingest.pipeline --email-id <id> [--db-path <path>]`
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    DERIVATIONS_IDEMPOTENCY_SELECT,
    DERIVATIONS_IDEMPOTENCY_UPSERT,
    EMAIL_ACTION_EXTRACTION_UPDATE,
    EMAIL_BODY_FOR_SENSITIVITY_SELECT,
    EMAIL_CLASS_COARSE_SELECT,
    EMAIL_CLASS_COARSE_UPDATE,
    EMAIL_CLASS_FINE_UPDATE,
    EMAIL_IMPORTANCE_SCORE_UPDATE,
    EMAIL_SENSITIVITY_DETAIL_SELECT,
    EMAIL_SENSITIVITY_OVERRIDE_REWRITE,
    EMAIL_SUMMARY_SHORT_UPDATE,
)
from mailbot_api.ingest.embedding import EmbedEmailResult, embed_email, read_embedding
from mailbot_api.ingest.idempotency import compute_idempotency_key
from mailbot_api.observability.logging import sanitize as _sanitize_log_value
from mailbot_api.observability.timestamps import utc_z_now
from mailbot_api.router import ask_router
from mailbot_api.router.errors import ErrorCode, RouterError, RouterResult
from mailbot_api.router.policy import snapshot_for_dispatch
from mailbot_api.sensitivity import (
    SensitivityResult,
    apply_pattern_override,
    classify_sensitivity,
    get_patterns,
)

logger = logging.getLogger(__name__)


# Sensitivity is the gate; embedding lives on its own writer-monopoly path.
# These are the 5 "ask_router-dispatched, idempotency-tracked" tasks.
_ROUTER_TASKS_IN_ORDER: Final[tuple[str, ...]] = (
    "coarse_class",
    "fine_class",  # conditional — only when class_coarse == "human"
    "summary_short",
    "importance_scoring",
    "action_extraction",
)

# Mapping from task_type → (UPDATE query, field_extractor_fn).
# field_extractor_fn takes the Pydantic OUTPUT_SCHEMA instance and returns
# the (value, confidence) pair to write into the derived column. For
# action_extraction the value is JSON-serialized; the helper handles that.

_TASK_UPDATE_QUERIES: Final[dict[str, str]] = {
    "coarse_class": EMAIL_CLASS_COARSE_UPDATE,
    "fine_class": EMAIL_CLASS_FINE_UPDATE,
    "summary_short": EMAIL_SUMMARY_SHORT_UPDATE,
    "importance_scoring": EMAIL_IMPORTANCE_SCORE_UPDATE,
    "action_extraction": EMAIL_ACTION_EXTRACTION_UPDATE,
}


def _utc_iso8601_now() -> str:
    return utc_z_now()


class ProcessEmailResult(BaseModel):
    """Return shape of `process_email`. AR-PAT-4 errors-as-data."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    email_id: str
    # CR-3-5-4: Pydantic v2 wraps these in default_factory internally so the
    # bare `= []` form is safe, but the project convention (RouterError, etc.)
    # uses `Field(default_factory=list)` explicitly to avoid the shared-mutable-
    # default trap if this pattern is copied into a non-Pydantic dataclass.
    steps_run: list[str] = Field(default_factory=list)
    steps_skipped: list[str] = Field(default_factory=list)  # idempotency short-circuits
    steps_inapplicable: list[str] = Field(default_factory=list)  # fine_class on non-human
    steps_blocked_by_sensitivity: list[str] = Field(default_factory=list)  # SENSITIVITY_BLOCKS_API
    failed_at: str | None = None
    partial_due_to_sensitivity: bool = False
    # CR-3-5-5: propagate the inner RouterError.retryable upward so the batch
    # caller (run_batch) can distinguish transient (rate-limited, paused) from
    # terminal failures and let backpressure re-enqueue them.
    retryable: bool = False
    error: RouterError | None = None


def _extract_value_and_confidence(task_type: str, output: BaseModel) -> tuple[Any, float | None]:
    """Return (value_to_store, confidence) for a given task's Pydantic output."""
    if task_type == "coarse_class":
        return (output.class_coarse, output.confidence)  # type: ignore[attr-defined]
    if task_type == "fine_class":
        return (output.class_fine, output.confidence)  # type: ignore[attr-defined]
    if task_type == "summary_short":
        return (output.summary, None)  # type: ignore[attr-defined]
    if task_type == "importance_scoring":
        return (output.importance, None)  # type: ignore[attr-defined]
    if task_type == "action_extraction":
        return (output.model_dump_json(), None)
    raise ValueError(f"unknown task_type for value extraction: {task_type!r}")


async def _idempotency_check(*, db_path: str, email_id: str, task_type: str, key: str) -> bool:
    """Return True if the (email_id, task_type) row already has this key."""
    row = await fetchone(db_path, DERIVATIONS_IDEMPOTENCY_SELECT, (email_id, task_type))
    return row is not None and row[0] == key


async def record_idempotency(*, db_path: str, email_id: str, task_type: str, key: str) -> None:
    """Upsert the derivations_idempotency row for this email-task pair."""
    await execute_write(
        db_path,
        DERIVATIONS_IDEMPOTENCY_UPSERT,
        (email_id, task_type, key, _utc_iso8601_now()),
    )


async def _run_router_step(
    *,
    db_path: str,
    email_id: str,
    task_type: str,
    body_preview: str,
    subject: str,
    sender: str,
    caller_origin: str,
) -> tuple[RouterResult, str, str]:
    """Dispatch one ask_router step.

    Returns (result, prompt_version, model) for the dispatch — the caller
    needs prompt_version + model to compute the idempotency key.
    """
    policy = snapshot_for_dispatch()
    entry = policy.tasks.get(task_type)
    if entry is None:
        return (
            RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.PROVIDER_ERROR,
                    message=f"task_type {task_type!r} not in policy",
                    retryable=False,
                ),
            ),
            "",
            "",
        )
    result = await ask_router(
        task_type=task_type,
        content={
            "subject": subject or "",
            "sender": sender or "",
            "body_preview": body_preview or "",
        },
        db_path=db_path,
        email_id=email_id,
        caller_origin=caller_origin,
        caller_verb=f"ingest.{task_type}",
    )
    return (result, entry.prompt_version, entry.model)


async def apply_derived_field_write(
    *,
    db_path: str,
    email_id: str,
    task_type: str,
    output: BaseModel,
    model: str,
    prompt_version: str,
) -> None:
    """Atomically write the derived value + 4 companions for one step."""
    value, confidence = _extract_value_and_confidence(task_type, output)
    query = _TASK_UPDATE_QUERIES[task_type]
    await execute_write(
        db_path,
        query,
        (value, prompt_version, confidence, model, _utc_iso8601_now(), email_id),
    )


def _is_sensitivity_blocks_api(result: RouterResult) -> bool:
    return result.error is not None and result.error.code == ErrorCode.SENSITIVITY_BLOCKS_API


async def _run_sensitivity_step(*, db_path: str, email_id: str) -> tuple[SensitivityResult, bool]:
    """Run sensitivity classification + pattern override.

    Returns (final_result, was_skipped). The "was_skipped" flag is True when
    sensitivity_at was already populated and we short-circuited the classifier.
    """
    # If sensitivity_at is already populated, short-circuit. We re-read the
    # final sensitivity value so the caller can act on it.
    row = await fetchone(db_path, EMAIL_SENSITIVITY_DETAIL_SELECT, (email_id,))
    if row is not None and row[1] is not None:
        sensitivity, _at, conf, model = row
        return (
            SensitivityResult(
                ok=True,
                email_id=email_id,
                sensitivity=sensitivity,
                confidence=conf,
                model=model,
                floored_to_sensitive=False,
            ),
            True,
        )

    # Run the raw classifier.
    classifier_result = await classify_sensitivity(email_id, db_path=db_path)
    if not classifier_result.ok or classifier_result.sensitivity is None:
        return (classifier_result, False)

    # Apply pattern override (may upgrade normal → sensitive or → confidential).
    body_row = await fetchone(db_path, EMAIL_BODY_FOR_SENSITIVITY_SELECT, (email_id,))
    if body_row is None:
        # CR-3-5-3: narrow race — classifier just wrote a row but a concurrent
        # soft-delete removed it before the override pass. Classifier result
        # stands (no upgrade applied). Log so the silent skip is observable;
        # privacy is not compromised (override could only have upgraded, never
        # downgraded), but a force_confidential rule that should have fired is
        # silently missed.
        logger.warning(
            "sensitivity override skipped — body row vanished between classify and override",
            extra={
                "event": "ingest.sensitivity.override_skip_missing_row",
                "email_id": email_id,
            },
        )
        return (classifier_result, False)
    subject, from_address, body_preview = body_row

    try:
        patterns = get_patterns()
    except RuntimeError:
        # Patterns not loaded (e.g., MAILBOT_SKIP_PATTERNS=1 in tests).
        # Skip override pass; the classifier result stands.
        return (classifier_result, False)

    final_sensitivity, override_reason = apply_pattern_override(
        classifier_sensitivity=classifier_result.sensitivity,
        subject=subject or "",
        from_address=from_address or "",
        body_preview=body_preview or "",
        patterns=patterns,
    )

    if override_reason is not None:
        # Re-write the sensitivity + override_reason only. Companions from the
        # classifier run (prompt_v, conf, model, at) stay intact.
        await execute_write(
            db_path,
            EMAIL_SENSITIVITY_OVERRIDE_REWRITE,
            (final_sensitivity, override_reason, email_id),
        )
        logger.info(
            "sensitivity overridden by pattern",
            extra={
                "event": "ingest.sensitivity.overridden",
                "email_id": email_id,
                "from_classifier": classifier_result.sensitivity,
                "to_final": final_sensitivity,
                "override_reason": override_reason,
            },
        )
        # Patch the classifier result so the caller sees the final value.
        classifier_result = SensitivityResult(
            ok=True,
            email_id=email_id,
            sensitivity=final_sensitivity,
            confidence=classifier_result.confidence,
            reason=classifier_result.reason,
            model=classifier_result.model,
            floored_to_sensitive=classifier_result.floored_to_sensitive,
            override_reason=override_reason,
        )

    return (classifier_result, False)


async def process_email(
    *,
    email_id: str,
    db_path: str,
    caller_origin: str = "ingest-pipeline",
) -> ProcessEmailResult:
    """Orchestrate the 7-step ingest pipeline for a single email.

    Errors-as-data: never raises; populates ProcessEmailResult.error on failure.
    """
    result = ProcessEmailResult(ok=False, email_id=email_id)

    # Read the email body once. Subsequent steps reuse this.
    body_row = await fetchone(db_path, EMAIL_BODY_FOR_SENSITIVITY_SELECT, (email_id,))
    if body_row is None:
        result.error = RouterError(
            code=ErrorCode.PROVIDER_ERROR,
            message=f"email_id {email_id!r} not found",
            retryable=False,
        )
        result.failed_at = "preflight"
        return result
    subject, from_address, body_preview = body_row
    body_preview = body_preview or ""

    # ----- Step 1: sensitivity_class -----
    sensitivity_result, was_skipped = await _run_sensitivity_step(db_path=db_path, email_id=email_id)
    if not sensitivity_result.ok:
        result.failed_at = "sensitivity_class"
        result.error = sensitivity_result.error
        # CR-3-5-5: propagate retryable from the inner RouterError so
        # run_batch can let backpressure re-enqueue transient failures.
        result.retryable = bool(sensitivity_result.error and sensitivity_result.error.retryable)
        logger.warning(
            "pipeline step failed",
            extra={
                "event": "ingest.step.failed",
                "email_id": email_id,
                "task_type": "sensitivity_class",
                "error_code": (sensitivity_result.error.code.value if sensitivity_result.error else "unknown"),
                # Story 6-11 F17: surface the underlying error string. Defense-in-depth
                # re-sanitization: most RouterError.message values are already sanitized at
                # router.py PROVIDER_ERROR construction sites, but classifier.py:97-101 (and
                # siblings) build messages via raw f-string from a caught RuntimeError and do
                # NOT pass through sanitize_error. NFR-SEC-4 requires every exception-derived
                # log field to flow through redaction; this wrapper enforces that contract at
                # the pipeline boundary regardless of upstream behavior.
                "error_message": (
                    _sanitize_log_value(sensitivity_result.error.message)
                    if sensitivity_result.error
                    else "no error object"
                ),
            },
        )
        return result
    if was_skipped:
        result.steps_skipped.append("sensitivity_class")
    else:
        result.steps_run.append("sensitivity_class")

    # ----- Steps 2-6: ask_router-dispatched tasks (with conditional fine_class) -----
    class_coarse_value: str | None = None  # populated by step 2 to gate step 3
    coarse_class_blocked_by_sensitivity = False  # CR-3-5-1 marker
    for task_type in _ROUTER_TASKS_IN_ORDER:
        # Conditional gate: fine_class only when class_coarse == "human".
        # CR-3-5-1: if coarse_class itself was blocked by the sensitivity gate
        # (possible under a future policy that puts coarse_class on Haiku/Opus),
        # `class_coarse_value` stays None — we cannot decide applicability for
        # fine_class. Attribute it to sensitivity-blocked rather than
        # inapplicable so the result accurately reflects WHY it was skipped.
        if task_type == "fine_class" and class_coarse_value != "human":
            if coarse_class_blocked_by_sensitivity:
                result.steps_blocked_by_sensitivity.append(task_type)
                result.partial_due_to_sensitivity = True
            else:
                result.steps_inapplicable.append(task_type)
            continue

        # Resolve policy entry up-front so we can compute the idempotency key.
        policy_snapshot = snapshot_for_dispatch()
        entry = policy_snapshot.tasks.get(task_type)
        if entry is None:
            result.failed_at = task_type
            result.error = RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=f"task_type {task_type!r} not in policy",
                retryable=False,
            )
            return result

        key = compute_idempotency_key(
            body=body_preview,
            prompt_version=entry.prompt_version,
            model=entry.model,
            task_type=task_type,
        )
        if await _idempotency_check(db_path=db_path, email_id=email_id, task_type=task_type, key=key):
            result.steps_skipped.append(task_type)
            # Even though we skipped, we need class_coarse for the fine_class
            # gate decision — read it from the row directly.
            if task_type == "coarse_class":
                cc_row = await fetchone(db_path, EMAIL_CLASS_COARSE_SELECT, (email_id,))
                class_coarse_value = cc_row[0] if cc_row else None
            continue

        # Dispatch.
        rr, prompt_version, model = await _run_router_step(
            db_path=db_path,
            email_id=email_id,
            task_type=task_type,
            body_preview=body_preview,
            subject=subject or "",
            sender=from_address or "",
            caller_origin=caller_origin,
        )

        # Sensitivity-blocks-API: continue pipeline, flag for partial completion.
        if _is_sensitivity_blocks_api(rr):
            result.steps_blocked_by_sensitivity.append(task_type)
            result.partial_due_to_sensitivity = True
            # CR-3-5-1: mark coarse_class as blocked so the fine_class gate
            # downstream attributes its skip to sensitivity, not "inapplicable".
            if task_type == "coarse_class":
                coarse_class_blocked_by_sensitivity = True
            logger.info(
                "pipeline step skipped due to sensitivity",
                extra={
                    "event": "ingest.step.skipped_sensitive",
                    "email_id": email_id,
                    "task_type": task_type,
                },
            )
            continue

        if not rr.ok or rr.output is None:
            result.failed_at = task_type
            result.error = rr.error
            # CR-3-5-5: see ProcessEmailResult.retryable. Transient errors
            # (RATE_LIMITED, router-paused PROVIDER_ERROR) carry retryable=True
            # so run_batch can leave the email in the unprocessed queue (its
            # sensitivity_at IS set, so it won't actually re-enqueue — see the
            # `failed_at != "sensitivity_class"` lane in run_batch).
            result.retryable = bool(rr.error and rr.error.retryable)
            logger.warning(
                "pipeline step failed",
                extra={
                    "event": "ingest.step.failed",
                    "email_id": email_id,
                    "task_type": task_type,
                    "error_code": (rr.error.code.value if rr.error else "unknown"),
                    "retryable": result.retryable,
                },
            )
            return result

        # Write the derived field atomically.
        await apply_derived_field_write(
            db_path=db_path,
            email_id=email_id,
            task_type=task_type,
            output=rr.output,
            model=model,
            prompt_version=prompt_version,
        )
        await record_idempotency(db_path=db_path, email_id=email_id, task_type=task_type, key=key)
        result.steps_run.append(task_type)

        # Capture class_coarse for the fine_class gate.
        if task_type == "coarse_class":
            class_coarse_value = rr.output.class_coarse  # type: ignore[attr-defined]

    # ----- Step 7: embedding -----
    existing_embedding = await read_embedding(db_path=db_path, email_id=email_id)
    if existing_embedding is not None:
        result.steps_skipped.append("embedding")
    else:
        embed_result: EmbedEmailResult = await embed_email(
            db_path=db_path,
            email_id=email_id,
            caller_origin=f"{caller_origin}-embedding",
        )
        if not embed_result.ok:
            result.failed_at = "embedding"
            result.error = embed_result.error
            logger.warning(
                "pipeline step failed",
                extra={
                    "event": "ingest.step.failed",
                    "email_id": email_id,
                    "task_type": "embedding",
                    "error_code": (embed_result.error.code.value if embed_result.error else "unknown"),
                },
            )
            return result
        # Record idempotency for embedding too (cross-task consistency).
        # The embedding key uses the same formula but its policy entry's
        # prompt_version is the sentinel "v1".
        # CR-3-5-8: hard-fail when the embedding entry is missing. The earlier
        # router-task loop already rejects missing entries with PROVIDER_ERROR
        # (see line ~376); a silent skip here would have left a gap in
        # derivations_idempotency that breaks the cross-task consistency claim
        # in migration 013's comment. If embedding should be disabled, remove
        # it from _ROUTER_TASKS_IN_ORDER + this block rather than relying on
        # policy.yaml absence.
        policy_snapshot = snapshot_for_dispatch()
        entry = policy_snapshot.tasks.get("embedding")
        if entry is None:
            result.failed_at = "embedding"
            result.error = RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="task_type 'embedding' not in policy",
                retryable=False,
            )
            return result
        embedding_key = compute_idempotency_key(
            body=body_preview,
            prompt_version=entry.prompt_version,
            model=entry.model,
            task_type="embedding",
        )
        await record_idempotency(
            db_path=db_path,
            email_id=email_id,
            task_type="embedding",
            key=embedding_key,
        )
        result.steps_run.append("embedding")

    result.ok = True
    return result


# ---------------------------------------------------------------------------
# Story 3-6 — bulk batch drain helpers.
# ---------------------------------------------------------------------------


class RunBatchResult(BaseModel):
    """Aggregate result of `run_batch` (Story 3-6 AC-2)."""

    processed: int
    succeeded: int
    failed: int
    partial_due_to_sensitivity: int
    # CR-3-5-5: count emails whose pipeline failed with a retryable error so
    # operators can distinguish "permanently broken" from "should be retried".
    retryable_failed: int = 0
    email_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


async def run_batch(
    *,
    db_path: str,
    caller_origin: str = "ingest-pipeline-batch",
    batch_size: int | None = None,
) -> RunBatchResult:
    """Drain up to BATCH_SIZE unprocessed emails sequentially (Story 3-6 AC-2).

    Sequential within the batch — concurrency comes from the Router's worker
    pool (Story 2-5), not from per-email parallelism. Records a `worker_health`
    row at the end ("ingest_pipeline" component).
    """
    # Lazy imports to avoid the backpressure → pipeline circular surface.
    from mailbot_api.db.connection import fetchall
    from mailbot_api.db.queries import (
        EMAIL_UNPROCESSED_BATCH_SELECT,
        WORKER_HEALTH_UPSERT,
    )
    from mailbot_api.ingest.backpressure import BATCH_SIZE

    size = batch_size if batch_size is not None else BATCH_SIZE
    rows = await fetchall(db_path, EMAIL_UNPROCESSED_BATCH_SELECT, (size,))
    email_ids = [r[0] for r in rows]

    succeeded = 0
    failed = 0
    retryable_failed = 0
    partial_sensitive = 0
    errors: list[str] = []
    last_error: str | None = None

    try:
        for email_id in email_ids:
            r = await process_email(
                email_id=email_id, db_path=db_path, caller_origin=caller_origin
            )
            if r.ok:
                succeeded += 1
                if r.partial_due_to_sensitivity:
                    partial_sensitive += 1
            else:
                failed += 1
                # CR-3-5-5: a retryable failure (rate-limit / pause) is
                # bookkept separately so operators can distinguish "needs
                # operator attention" from "queue is throttled". The email
                # itself: if the failure was at sensitivity_class, the row
                # still has sensitivity_at IS NULL → backpressure re-enqueues
                # on the next batch. Failures at later steps leave
                # sensitivity_at populated, so the email won't be re-picked
                # automatically — surfaced via the count for now; a future
                # story can extend with a "retry queue" if needed.
                if r.retryable:
                    retryable_failed += 1
                msg = f"{email_id}: {r.failed_at} ({r.error.code.value if r.error else 'unknown'})"
                errors.append(msg)
                last_error = msg

        outcome = "ok"
        worker_error = last_error  # may be None if all succeeded
    except Exception as exc:  # noqa: BLE001 — defensive; process_email is errors-as-data, this is a guard
        outcome = "failed"
        worker_error = f"run_batch escape: {type(exc).__name__}: {exc}"
        # Re-raise after we record the health row.
        await execute_write(
            db_path,
            WORKER_HEALTH_UPSERT,
            ("ingest_pipeline", _utc_iso8601_now(), outcome, worker_error),
        )
        raise

    await execute_write(
        db_path,
        WORKER_HEALTH_UPSERT,
        ("ingest_pipeline", _utc_iso8601_now(), outcome, worker_error),
    )

    return RunBatchResult(
        processed=len(email_ids),
        succeeded=succeeded,
        failed=failed,
        partial_due_to_sensitivity=partial_sensitive,
        retryable_failed=retryable_failed,
        email_ids=email_ids,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI: python -m mailbot_api.ingest.pipeline --email-id <id> [--db-path <p>]
# ---------------------------------------------------------------------------


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mailbot_api.ingest.pipeline",
        description="Run the ingest pipeline end-to-end on a single email.",
    )
    parser.add_argument("--email-id", required=True, help="The email's graph_id.")
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite path. Defaults to $MAILBOT_DB_PATH.",
    )
    return parser


async def _cli_async_main(args: argparse.Namespace) -> int:
    db_path = args.db_path
    if db_path is None:
        from mailbot_api.config import get_secret_optional

        db_path = get_secret_optional("MAILBOT_DB_PATH", "")
        if not db_path:
            print(  # noqa: T201 — CLI output is the only consumer of this branch
                json.dumps({"ok": False, "error": "MAILBOT_DB_PATH unset and --db-path not provided"})
            )
            return 2

    # Story 4-0 Finding 4: the FastAPI lifespan normally loads policy + patterns
    # snapshots and registers adapters before any ask_router / pipeline call.
    # The CLI bypasses the lifespan, so we must mirror that init here or every
    # `process_email` call fails immediately at sensitivity_class.
    await init_pipeline_runtime(db_path)

    result = await process_email(email_id=args.email_id, db_path=db_path)
    print(result.model_dump_json(indent=2))  # noqa: T201 — CLI prints to stdout
    return 0 if result.ok else 1


async def init_pipeline_runtime(db_path: str) -> None:
    """Initialize the module-level runtime that process_email depends on.

    Mirrors mailbot_api/main.py lifespan() ordering: policy first, then
    sensitivity patterns, then adapters, then budget guard, then pause state.
    Apply pending migrations to make sure the DB schema is current for the
    invoking process (lifespan does this; CLI + worker must too).

    Story 6-11 (F17 closure): promoted from `_cli_init_runtime` to a public
    helper. The worker process (`mailbot_api/worker.py`) was added by Story 6-6
    as a third interpreter that runs ingest ticks, but Story 6-6 missed wiring
    this init — so `classify_sensitivity` failed every tick with
    `provider_error: policy not loaded` because the per-process module
    snapshots were empty. Three call sites now share this exact body: api
    lifespan (open-coded, retains test-flag branches), CLI (`_cli_async_main`),
    and worker (`_worker_main`).

    Honors MAILBOT_SKIP_POLICY=1 and MAILBOT_SKIP_PATTERNS=1 (mirrors the api
    lifespan in `main.py`) so test boots that don't need the sensitivity gate
    can still drive ingest-adjacent code. Production env never sets these.
    """
    from pathlib import Path

    from mailbot_api.config import get_secret_optional
    from mailbot_api.db.migrations_runner import apply_pending_migrations
    from mailbot_api.router.budget import get_guard
    from mailbot_api.router.pause import get_pause_state
    from mailbot_api.router.policy import load_policy, set_policy_snapshot, snapshot_for_dispatch
    from mailbot_api.router.registry import init_default_adapters
    from mailbot_api.sensitivity import assert_qwen_only, load_patterns
    from mailbot_api.sensitivity.patterns import (
        set_patterns_snapshot as _set_sensitivity_patterns,
    )

    skip_policy = get_secret_optional("MAILBOT_SKIP_POLICY", "0") == "1"
    skip_patterns = get_secret_optional("MAILBOT_SKIP_PATTERNS", "0") == "1"

    apply_pending_migrations(db_path)

    if not skip_policy:
        policy_path = Path(get_secret_optional("MAILBOT_POLICY_PATH", "/app/router/policy.yaml"))
        set_policy_snapshot(load_policy(policy_path))
        # CR-3-5-7: mirror the FastAPI lifespan's FR-2.5 startup check. The
        # per-call safeguard in classifier.py would catch a drifted policy at
        # first dispatch, but the CLI's job is fail-fast at init — same shape
        # as the lifespan at main.py.
        assert_qwen_only(snapshot_for_dispatch())

        if not skip_patterns:
            patterns_path = Path(
                get_secret_optional("MAILBOT_PATTERNS_PATH", "/app/router/sensitivity_patterns.yaml")
            )
            _set_sensitivity_patterns(load_patterns(patterns_path))

        init_default_adapters()

    await get_guard().initialize(db_path)
    await get_pause_state().initialize(db_path)


def main() -> int:
    args = _build_cli_parser().parse_args()
    return asyncio.run(_cli_async_main(args))


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "ProcessEmailResult",
    "RunBatchResult",
    "apply_derived_field_write",
    "init_pipeline_runtime",
    "process_email",
    "record_idempotency",
    "run_batch",
]
