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
tier first, original tier second). ``ts`` is second-precision so the two
rows often share the same timestamp. Queries reconstructing dispatch
sequence from this table should NOT order by ``id`` or ``ts`` alone for
escalation analysis — instead correlate via ``email_id`` + ``task_type`` +
``model_chosen_reason`` (the ``escalated_from_<X>`` tag identifies which
row was the escalated leg). A future story may add a ``parent_call_id``
column if richer dispatch-chain reconstruction becomes load-bearing.

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
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from mailbot_api.db import connection, queries

_log = logging.getLogger(__name__)

# UTC ISO-8601 with Z suffix, second precision (matches the format produced by
# `_utc_z_now` below and by Story 1-4's logging timestamp format).
_TS_FORMAT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Closed-set ``model_chosen_reason`` values that downstream Epic-2 stories produce.
# Adding a value here ALSO requires updating any consumer that filter-greps on
# the reason — see architecture §AR-PAT-3 + Dev Notes "Why we enumerate all
# model_chosen_reason values now" in the Story 2-1 file.
_REASON_LITERALS = frozenset(
    {
        "policy",
        "override",
        "degraded",
        "response_cache_hit",
        "force_override",
    }
)
# Story 2-4: model ids can contain colons (e.g., "qwen2.5:3b-instruct-q4_K_M"),
# so the escalated_from_<X> regex must accept them too. The character class
# matches everything reasonable in an Ollama/Anthropic model id.
_ESCALATED_FROM_RE = re.compile(r"^escalated_from_[\w.:\-]+$")


def _utc_z_now() -> str:
    """UTC ISO-8601 with Z suffix (AR-PAT-3 — matches ``observability.logging`` format)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RouterCallRow(BaseModel):
    """One row of the ``router_calls`` audit log.

    Field order MUST match ``queries.ROUTER_CALLS_INSERT`` column order — see
    ``_param_tuple`` below.
    """

    ts: str = Field(default_factory=_utc_z_now)
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

    @field_validator("model_chosen_reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        if value in _REASON_LITERALS or _ESCALATED_FROM_RE.match(value):
            return value
        valid_literals = ", ".join(sorted(_REASON_LITERALS))
        raise ValueError(
            f"model_chosen_reason must be one of {{{valid_literals}}} "
            "or match 'escalated_from_<X>'"
        )

    @field_validator("ts")
    @classmethod
    def _check_ts_format(cls, value: str) -> str:
        """Reject malformed timestamps before they corrupt `ix_router_calls_ts`.

        Per AR-PAT-3: UTC ISO-8601 with `Z` suffix, second precision
        (`YYYY-MM-DDTHH:MM:SSZ`). The default factory always produces this
        shape; explicit callers passing `ts="not-a-timestamp"` would silently
        break ts-ordered queries without this validator (Story 2-1 review fix R10).
        """
        if not _TS_FORMAT_RE.match(value):
            raise ValueError(
                f"ts must match 'YYYY-MM-DDTHH:MM:SSZ' format; got: {value!r}"
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


__all__: list[str] = ["RouterCallRow", "record_router_call"]
