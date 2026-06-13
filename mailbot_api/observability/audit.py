"""Router audit writer per Story 2-1 and architecture §"Rule W" + Rule C.

The ONLY production-code path that writes to the ``router_calls`` table. The
selective-import boundary checker (``scripts/check_boundaries.py``) refuses
the literal ``INSERT INTO router_calls`` substring in any file outside the
allowlist (this module, ``mailbot_api/db/queries.py``, the migrations
runner, and ``mailbot_api/db/migrations/006_router_calls.sql``).

Row ordering note (Story 2-4 review fix MEDIUM): when Story 2-4's
``ask_router`` escalates on schema-validation failure, the recursive
escalated call's ``finally`` block fires BEFORE the outer call's
``finally``. Result: rows are inserted in REVERSE dispatch order (escalated
tier first, original tier second). Since the 2026-06-02 sub-second-``ts``
fix (Epic 4 retro action item #3), ``ts`` is microsecond-precision so
back-to-back rows from the same call chain are strictly orderable by
``ts``. Queries reconstructing dispatch sequence for escalation analysis
can now ``ORDER BY ts`` reliably; legacy rows written before the fix may
still share a second and should additionally correlate via ``email_id`` +
``task_type`` + ``model_chosen_reason`` (post-9.2: the
``policy:escalation:<from>→<to>`` tag identifies which row was the
escalated leg; pre-9.2 rows used ``escalated_from_<X>``).

Story 2-1 ships the writer in isolation — Story 2-4 will wire it into
``ask_router()`` 's ``finally`` block so a row is recorded even when the
adapter throws. For now, the function is fully testable with a constructed
``RouterCallRow`` against a real (in-memory or temp-file) SQLite database.

Column-order contract: ``RouterCallRow`` field order and the parameter
tuple passed to ``execute_write()`` MUST match the column order in
``queries.ROUTER_CALLS_INSERT`` and the migration. Adding a column means
synchronizing all four sites in one commit.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import is_valid_ts, utc_z_now

_log = logging.getLogger(__name__)

# Story 9.2: ``model_chosen_reason`` accepts ONE of the four shapes defined by
# the ``ModelChosenReason`` enum + helpers in ``mailbot_api/router/audit_vocab.py``:
#   1. Literal enum member value (the eight non-templated members)
#   2. ``policy:<task>:default`` — produced by ``policy_default(task)``
#   3. ``policy:escalation:<from>→<to>`` — produced by ``policy_escalation(...)``
#   4. ``degraded:<from>→<to>`` — produced by ``degraded_mode_demotion(...)``
#
# The pre-9.2 vocabulary (raw ``"policy"`` / ``"override"`` / ``"degraded"`` /
# ``"response_cache_hit"`` / ``"force_override"`` / ``"escalated_from_<X>"``)
# is rejected — old rows in the DB remain readable via SQL but cannot
# round-trip through ``RouterCallRow`` reconstruction (Story 9.2 AC-7
# forward-only contract).
#
# The validator imports lazily from ``mailbot_api.router.audit_vocab``
# because eager import triggers ``mailbot_api/router/__init__.py`` which
# re-exports from ``router.router`` which imports THIS module — circular.
# The lazy import resolves once at first-call time; subsequent calls hit
# Python's module cache and pay no cost.


class RouterCallRow(BaseModel):
    """One row of the ``router_calls`` audit log.

    Field order MUST match ``queries.ROUTER_CALLS_INSERT`` column order — see
    ``_param_tuple`` below.
    """

    ts: str = Field(default_factory=utc_z_now)
    task_type: str
    prompt_version: str
    model_chosen: str
    model_chosen_reason: str
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens_in: int = 0
    cost_usd_estimated: float = 0.0
    latency_ms: int = 0
    outcome: Literal["ok", "retry_recovered", "escalated", "failed"]
    caller_verb: str | None = None
    caller_origin: str = "unknown"
    email_id: str | None = None
    sensitivity_grant_id: str | None = None
    sensitivity_grant_minted_at: str | None = None
    # Story 6-9 (F11 closure) — only populated by dispatch_tool_call.
    # NULL on every non-tools-bearing row. tool_calls_count==0 means tools
    # were offered but the model chose to call none; NULL means the call
    # wasn't tools-bearing at all.
    tool_calls_count: int | None = None
    tool_calls_summary: str | None = None

    @field_validator("model_chosen_reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        """Accept ONE of the four Story 9.2 shapes (see module docstring).

        Pre-9.2 vocabulary is rejected per AC-7's forward-only contract:
        old rows live in SQLite as-is, new construction must use
        ``mailbot_api.router.audit_vocab`` enum + helpers.

        Lazy import: see module docstring for the circular-import rationale.
        """
        from mailbot_api.router.audit_vocab import (
            DEGRADED_RE,
            LITERAL_REASONS,
            POLICY_DEFAULT_RE,
            POLICY_ESCALATION_RE,
        )

        if value in LITERAL_REASONS:
            return value
        if POLICY_DEFAULT_RE.match(value):
            return value
        if POLICY_ESCALATION_RE.match(value):
            return value
        if DEGRADED_RE.match(value):
            return value
        raise ValueError(
            "model_chosen_reason must be one of: "
            "(1) a literal ModelChosenReason enum value, "
            "(2) policy:<task>:default, "
            "(3) policy:escalation:<from>→<to>, "
            "(4) degraded:<from>→<to>. "
            f"See mailbot_api/router/audit_vocab.py. Got: {value!r}"
        )

    @field_validator("ts")
    @classmethod
    def _check_ts_format(cls, value: str) -> str:
        """Reject malformed timestamps before they corrupt `ix_router_calls_ts`.

        Per AR-PAT-3: UTC ISO-8601 with `Z` suffix. Lenient — accepts both
        microsecond-precision (default factory; post-2026-06-02 writes) and
        legacy second-precision (rows written before the sub-second-`ts` fix).
        Explicit callers passing `ts="not-a-timestamp"` would silently break
        ts-ordered queries without this validator (Story 2-1 review fix R10).
        """
        if not is_valid_ts(value):
            raise ValueError(
                "ts must match 'YYYY-MM-DDTHH:MM:SS[.ffffff]Z' format; "
                f"got: {value!r}"
            )
        return value


def _param_tuple(row: RouterCallRow) -> tuple[object, ...]:
    """Build the positional-parameter tuple in the exact column order of
    ``queries.ROUTER_CALLS_INSERT``.

    Keeping this in one place means a column add / reorder only requires
    editing this function plus the SQL constant plus the migration — the
    rest of the codebase passes a ``RouterCallRow`` and never touches order.
    """
    return (
        row.ts,
        row.task_type,
        row.prompt_version,
        row.model_chosen,
        row.model_chosen_reason,
        row.tokens_in,
        row.tokens_out,
        row.cached_tokens_in,
        row.cost_usd_estimated,
        row.latency_ms,
        row.outcome,
        row.caller_verb,
        row.caller_origin,
        row.email_id,
        row.sensitivity_grant_id,
        row.sensitivity_grant_minted_at,
        row.tool_calls_count,
        row.tool_calls_summary,
    )


async def record_router_call(row: RouterCallRow, *, db_path: str) -> None:
    """Append one row to ``router_calls`` via the executor write path.

    The write runs through ``db.connection.execute_write`` (per AR-D8-1), so
    SQLite checkpointing never stalls the FastAPI event loop. The function is
    intentionally fire-and-forget at the call site — Story 2-4 will wrap it
    in ``ask_router`` 's ``finally`` block to guarantee a row even on
    adapter exception.

    Defensive: a DB write failure (disk full, DB locked beyond the busy-timeout,
    schema drift, etc.) is logged-and-swallowed rather than re-raised. Story
    2-4's ``finally`` block must not mask the original Router failure with a
    secondary audit-write failure. Audit-trail loss for a single call is the
    acceptable trade-off — Story 2-9's anomaly detection observes the call
    count from `router_calls` and a missing row will already register as a
    discontinuity. (Story 2-1 review fix R7.)
    """
    try:
        await connection.execute_write(db_path, queries.ROUTER_CALLS_INSERT, _param_tuple(row))
    except Exception as exc:  # noqa: BLE001 — defensive: audit loss is acceptable, mask is not
        _log.warning(
            "router_calls write failed: %s — audit row lost for task_type=%s",
            type(exc).__name__,
            row.task_type,
            extra={"event": "audit.write.failed"},
        )


async def router_calls_by_reason(
    db_path: str,
    reason: object,
    *,
    limit: int = 100,
) -> list[RouterCallRow]:
    """Slice ``router_calls`` by closed-set ``model_chosen_reason`` (Story 9.2 AC-5).

    Accepts either a ``ModelChosenReason`` enum member (literal members only —
    templated members like ``POLICY_DEFAULT`` carry placeholder strings as
    ``.value`` and won't match real rows; pass the concrete templated value
    from the helper instead) OR a raw string (for templated values produced
    by ``policy_default(task)`` / ``policy_escalation(from, to)`` /
    ``degraded_mode_demotion(from, to)``).

    Args:
        db_path: SQLite database path.
        reason: Literal enum member or string-typed reason value.
        limit: Maximum rows to return (ordered by ts DESC).

    Returns:
        ``list[RouterCallRow]`` with the same field order as
        ``RouterCallRow.model_fields`` — i.e., the column order of
        ``queries.ROUTER_CALLS_INSERT`` / ``queries.ROUTER_CALLS_BY_REASON_SELECT``.

    Notes:
        Rows written under the pre-9.2 vocabulary (bare ``"policy"`` /
        ``"override"`` / ``"degraded"`` etc.) cannot round-trip back through
        ``RouterCallRow`` reconstruction — the validator rejects them per
        AC-7's forward-only contract. Story 9.9 callers querying historical
        spans should use raw SQL with ``WHERE model_chosen_reason IN (?, ?)``
        covering both vocabularies, OR call this helper twice with the new
        and old strings and merge the results SQL-side.
    """
    # Lazy import: ModelChosenReason lives in router/audit_vocab; eager
    # import here triggers the same router/__init__ circular cycle that
    # affects the validator (see module docstring).
    from mailbot_api.router.audit_vocab import (
        DEGRADED_RE,
        LITERAL_REASONS,
        POLICY_DEFAULT_RE,
        POLICY_ESCALATION_RE,
        ModelChosenReason,
    )

    reason_str: str
    if isinstance(reason, ModelChosenReason):
        reason_str = reason.value
    elif isinstance(reason, str):
        reason_str = reason
    else:
        raise TypeError(
            f"router_calls_by_reason: reason must be ModelChosenReason or str; "
            f"got {type(reason).__name__}"
        )

    # CR-F6: validate the string matches one of the four post-9.2 shapes.
    # Without this guard, a caller that accidentally passes a pre-9.2 value
    # (e.g., "policy" or "force_override") gets an empty result with no
    # error — silent wrong-result bug. Raise early so the contract is
    # explicit. Pre-9.2 rows in the DB remain SELECTable via raw SQL.
    if (
        reason_str not in LITERAL_REASONS
        and not POLICY_DEFAULT_RE.match(reason_str)
        and not POLICY_ESCALATION_RE.match(reason_str)
        and not DEGRADED_RE.match(reason_str)
    ):
        raise ValueError(
            f"router_calls_by_reason: reason {reason_str!r} does not match any "
            "post-9.2 vocabulary shape. Use a ModelChosenReason enum member "
            "or a helper-produced template string (see audit_vocab.py). "
            "To query pre-9.2 rows, use raw SQL with WHERE model_chosen_reason IN (?, ?)."
        )

    rows = await connection.fetchall(
        db_path, queries.ROUTER_CALLS_BY_REASON_SELECT, (reason_str, limit)
    )
    return [
        RouterCallRow(
            ts=row[0],
            task_type=row[1],
            prompt_version=row[2],
            model_chosen=row[3],
            model_chosen_reason=row[4],
            tokens_in=row[5],
            tokens_out=row[6],
            cached_tokens_in=row[7],
            cost_usd_estimated=row[8],
            latency_ms=row[9],
            outcome=row[10],
            caller_verb=row[11],
            caller_origin=row[12],
            email_id=row[13],
            sensitivity_grant_id=row[14],
            sensitivity_grant_minted_at=row[15],
            tool_calls_count=row[16],
            tool_calls_summary=row[17],
        )
        for row in rows
    ]


__all__: list[str] = ["RouterCallRow", "record_router_call", "router_calls_by_reason"]
