"""Targeted re-derivation orchestrator per Story 3-8.

`mailbot rederive --task=<task> --since=<date>` re-runs a single ingest task
on selected rows when Adam bumps a prompt version OR wants to re-evaluate
after a model refresh. FR-2.6 calibration-driven re-derivation as a
deliberate, scoped, evidence-backed operation.

Two public functions:

  * `plan_rederive(*, task, since, prompt_version, db_path)` — resolves the
    target prompt_version, queries rows needing re-derivation, returns a
    RederivePlan with the count + cost estimate + selected email_ids.
  * `execute_rederive(*, plan, db_path, caller_origin)` — dispatches the
    re-derivation sequentially, handling sensitivity's downstream-clear,
    embedding's Story-3-4-specific path, and KeyboardInterrupt.

Sensitivity precondition (AC-4): non-sensitivity tasks refuse if any selected
row has `sensitivity_at IS NULL` — re-derivation requires sensitivity already
classified per FR-2.3.

Sensitivity re-derivation (AC-5): clears ALL downstream derived fields +
derivations_idempotency rows for each email_id BEFORE the re-derivation runs.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict

from mailbot_api.db.connection import execute_write, fetchall
from mailbot_api.db.queries import (
    DERIVATIONS_IDEMPOTENCY_DELETE_FOR_EMAIL,
    EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS,
    EMAIL_EMBEDDING_CLEAR,
    EMAILS_NEEDING_REDERIVATION_ACTION_EXTRACTION,
    EMAILS_NEEDING_REDERIVATION_COARSE_CLASS,
    EMAILS_NEEDING_REDERIVATION_EMBEDDING,
    EMAILS_NEEDING_REDERIVATION_FINE_CLASS,
    EMAILS_NEEDING_REDERIVATION_IMPORTANCE_SCORING,
    EMAILS_NEEDING_REDERIVATION_SENSITIVITY,
    EMAILS_NEEDING_REDERIVATION_SUMMARY_SHORT,
    EMAILS_REDERIVATION_UNCLASSIFIED_COUNT,
)
from mailbot_api.ingest.embedding import embed_email
from mailbot_api.ingest.idempotency import compute_idempotency_key
from mailbot_api.ingest.pipeline import (
    apply_derived_field_write,
    record_idempotency,
)
from mailbot_api.observability.timestamps import utc_z_now
from mailbot_api.router import ask_router
from mailbot_api.router.policy import snapshot_for_dispatch
from mailbot_api.router.pricing import estimate_cost_usd
from mailbot_api.sensitivity import classify_sensitivity

logger = logging.getLogger(__name__)


# Map task → query selecting rows needing re-derivation. The `embedding` task
# has the same shape but reads `embedding_at` + `embedding_prompt_v` instead
# of `<task>_at` + `<task>_prompt_v`.
_REDERIVATION_QUERY_BY_TASK: Final[dict[str, str]] = {
    "sensitivity_class": EMAILS_NEEDING_REDERIVATION_SENSITIVITY,
    "coarse_class": EMAILS_NEEDING_REDERIVATION_COARSE_CLASS,
    "fine_class": EMAILS_NEEDING_REDERIVATION_FINE_CLASS,
    "summary_short": EMAILS_NEEDING_REDERIVATION_SUMMARY_SHORT,
    "importance_scoring": EMAILS_NEEDING_REDERIVATION_IMPORTANCE_SCORING,
    "action_extraction": EMAILS_NEEDING_REDERIVATION_ACTION_EXTRACTION,
    "embedding": EMAILS_NEEDING_REDERIVATION_EMBEDDING,
}

VALID_RE_DERIVATION_TASKS: Final[tuple[str, ...]] = tuple(_REDERIVATION_QUERY_BY_TASK.keys())

# Rough upper-bound cost estimate inputs per row.
_EST_TOKENS_IN_PER_ROW: Final[int] = 200
_EST_TOKENS_OUT_PER_ROW: Final[int] = 100
_EST_WALL_CLOCK_SECONDS_PER_ROW: Final[float] = 1.0


class RederivePlan(BaseModel):
    """The plan returned by `plan_rederive`. Shown to the user before confirm."""

    task: str
    since_iso: str  # YYYY-MM-DD
    prompt_version: str
    model: str
    count: int
    blocked_by_sensitivity_count: int = 0
    cost_usd_estimated: float = 0.0
    est_wall_clock_seconds: float = 0.0
    email_ids: list[str] = []


class RederiveResult(BaseModel):
    """The outcome of `execute_rederive`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: str
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    aborted: bool = False
    errors: list[str] = []


def _utc_iso8601_now() -> str:
    return utc_z_now()


async def plan_rederive(
    *,
    task: str,
    since: date,
    prompt_version: str | None,
    db_path: str,
) -> RederivePlan:
    """Build the re-derivation plan without dispatching anything yet.

    Returns RederivePlan with `count`, `email_ids`, cost + time estimates.
    The `blocked_by_sensitivity_count` field is non-zero when the task is
    non-sensitivity AND any selected row has sensitivity_at IS NULL — the
    CLI should refuse to proceed in that case.
    """
    if task not in _REDERIVATION_QUERY_BY_TASK:
        raise ValueError(
            f"unknown task {task!r}; expected one of {sorted(VALID_RE_DERIVATION_TASKS)}"
        )

    # Resolve effective prompt_version + model from policy snapshot.
    policy = snapshot_for_dispatch()
    entry = policy.tasks.get(task)
    if entry is None:
        raise RuntimeError(
            f"task {task!r} not in policy.tasks — add a policy entry first"
        )
    effective_prompt_version = prompt_version or entry.prompt_version
    model = entry.model

    # Query rows needing re-derivation.
    query = _REDERIVATION_QUERY_BY_TASK[task]
    since_iso = since.isoformat()
    rows = await fetchall(db_path, query, (since_iso, effective_prompt_version))
    email_ids = [r[0] for r in rows]
    count = len(email_ids)

    # AC-4 sensitivity precondition for non-sensitivity tasks.
    blocked_count = 0
    if task != "sensitivity_class" and email_ids:
        placeholders = ",".join("?" * len(email_ids))
        unclassified_query = EMAILS_REDERIVATION_UNCLASSIFIED_COUNT.format(
            placeholders=placeholders
        )
        unclassified_row = await fetchall(db_path, unclassified_query, tuple(email_ids))
        blocked_count = int(unclassified_row[0][0]) if unclassified_row else 0

    # Cost estimate.
    cost_estimate = estimate_cost_usd(
        model,
        tokens_in=_EST_TOKENS_IN_PER_ROW * count,
        tokens_out=_EST_TOKENS_OUT_PER_ROW * count,
        cached_tokens_in=0,
    )
    wall_clock_estimate = count * _EST_WALL_CLOCK_SECONDS_PER_ROW

    return RederivePlan(
        task=task,
        since_iso=since_iso,
        prompt_version=effective_prompt_version,
        model=model,
        count=count,
        blocked_by_sensitivity_count=blocked_count,
        cost_usd_estimated=cost_estimate,
        est_wall_clock_seconds=wall_clock_estimate,
        email_ids=email_ids,
    )


async def _clear_downstream_for_email(*, db_path: str, email_id: str) -> None:
    """AC-5: clear all downstream derived fields + idempotency rows for one email."""
    await execute_write(db_path, EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS, (email_id,))
    await execute_write(db_path, DERIVATIONS_IDEMPOTENCY_DELETE_FOR_EMAIL, (email_id,))


async def _rederive_one_sensitivity(*, email_id: str, db_path: str) -> tuple[bool, str | None]:
    """Re-derive sensitivity for one email. Clears downstream FIRST.

    Returns (succeeded, error_message).
    """
    await _clear_downstream_for_email(db_path=db_path, email_id=email_id)
    result = await classify_sensitivity(email_id, db_path=db_path)
    if result.ok:
        return (True, None)
    return (False, result.error.message if result.error else "unknown error")


async def _rederive_one_embedding(
    *, email_id: str, db_path: str, caller_origin: str
) -> tuple[bool, str | None]:
    """Re-derive embedding for one email via embed_email."""
    # Clear the existing embedding so embed_email's read_embedding != None
    # short-circuit doesn't fire.
    await execute_write(db_path, EMAIL_EMBEDDING_CLEAR, (email_id,))
    result = await embed_email(
        db_path=db_path, email_id=email_id, caller_origin=caller_origin
    )
    if result.ok:
        return (True, None)
    return (False, result.error.message if result.error else "unknown error")


def _extract_body_preview_for_key(rows: list[tuple[str, str, str, str | None]]) -> dict[str, str]:
    """Build email_id → body_preview map for idempotency key computation."""
    return {r[0]: (r[3] or "") for r in rows}


async def _rederive_one_ask_router(
    *,
    email_id: str,
    task: str,
    prompt_version: str,
    model: str,
    body_preview: str,
    db_path: str,
    caller_origin: str,
) -> tuple[bool, str | None]:
    """Re-derive via ask_router for one of the 5 ask_router-dispatched tasks."""
    # Re-fetch subject + from_address so the prompt's USER_TEMPLATE placeholders are populated.
    # Use the existing EMAIL_BODY_FOR_SENSITIVITY_SELECT query (returns subject + from + body_preview).
    from mailbot_api.db.connection import fetchone
    from mailbot_api.db.queries import EMAIL_BODY_FOR_SENSITIVITY_SELECT

    body_row = await fetchone(db_path, EMAIL_BODY_FOR_SENSITIVITY_SELECT, (email_id,))
    if body_row is None:
        return (False, f"email {email_id!r} not found")
    subject, from_address, body_preview_fresh = body_row

    rr = await ask_router(
        task_type=task,
        content={
            "subject": subject or "",
            "sender": from_address or "",
            "body_preview": body_preview_fresh or "",
        },
        db_path=db_path,
        email_id=email_id,
        caller_origin=caller_origin,
        caller_verb=f"rederive.{task}",
    )
    if not rr.ok or rr.output is None:
        return (False, rr.error.message if rr.error else "unknown error")

    # Write the derived field + idempotency row.
    await apply_derived_field_write(
        db_path=db_path,
        email_id=email_id,
        task_type=task,
        output=rr.output,
        model=model,
        prompt_version=prompt_version,
    )
    key = compute_idempotency_key(
        body=body_preview_fresh or "",
        prompt_version=prompt_version,
        model=model,
        task_type=task,
    )
    await record_idempotency(
        db_path=db_path, email_id=email_id, task_type=task, key=key
    )
    return (True, None)


async def execute_rederive(
    *,
    plan: RederivePlan,
    db_path: str,
    caller_origin: str = "cli-rederive",
    progress_every: int = 50,
) -> RederiveResult:
    """Run the re-derivation per plan.

    Sequential per-row. Catches KeyboardInterrupt and returns aborted=True.
    Errors-as-data per row — single failures don't abort the whole run.
    """
    result = RederiveResult(task=plan.task)

    try:
        for idx, email_id in enumerate(plan.email_ids, start=1):
            if plan.task == "sensitivity_class":
                ok, err = await _rederive_one_sensitivity(
                    email_id=email_id, db_path=db_path
                )
            elif plan.task == "embedding":
                ok, err = await _rederive_one_embedding(
                    email_id=email_id, db_path=db_path, caller_origin=caller_origin
                )
            else:
                ok, err = await _rederive_one_ask_router(
                    email_id=email_id,
                    task=plan.task,
                    prompt_version=plan.prompt_version,
                    model=plan.model,
                    body_preview="",  # re-fetched inside helper
                    db_path=db_path,
                    caller_origin=caller_origin,
                )
            result.processed += 1
            if ok:
                result.succeeded += 1
            else:
                result.failed += 1
                if err is not None:
                    result.errors.append(f"{email_id}: {err}")

            if idx % progress_every == 0:
                logger.info(
                    "rederive progress",
                    extra={
                        "event": "rederive.progress",
                        "task": plan.task,
                        "processed": idx,
                        "total": plan.count,
                    },
                )
    except KeyboardInterrupt:
        result.aborted = True
        logger.warning(
            "rederive aborted by KeyboardInterrupt",
            extra={
                "event": "rederive.aborted",
                "task": plan.task,
                "processed": result.processed,
                "total": plan.count,
            },
        )

    return result


__all__ = [
    "VALID_RE_DERIVATION_TASKS",
    "RederivePlan",
    "RederiveResult",
    "execute_rederive",
    "plan_rederive",
]
