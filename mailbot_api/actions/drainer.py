"""pending_actions drainer — Story 4-4.

Continuous-loop coroutine inside the worker process. Each tick:
  1. Read up to 25 pending rows in priority order (tier first, proposed_at next).
  2. Atomic claim per row — conditional flip pending → draining; concurrent
     drainers race-free (rowcount=0 means another drainer beat us).
  3. Per-tier checks (Tier-1 lenient, Tier-2 grant+lenient, Tier-3 grant+strict-ETag).
  4. Write action_history pre_state row (empty for Story 4-4; Story 4-8 fills).
  5. Dispatch via GraphWriteAdapter (Fake for 4-4 happy-path; Story 4-5 ships real).
  6. Terminal status flip (applied / failed / pending_grant if grant missing).

Hybrid sync-conflict policy:
  - AR-D4-1 strict-ETag for Tier-3 (skip when email-less per Story 4-2 CR-2)
  - AR-D4-2 lenient 3-rule for Tier-1/2

Notifications per AR-D5-4:
  - Tier-1 failures → silent log (no notification)
  - Tier-2 failures → important tier (Epic 6 wires the daily digest; here we
    stand in with the same notifications.send_urgent path Story 1-8 ships, but
    log the intended tier as `important` for forward-compat)
  - Tier-3 failures → urgent notification immediately

References:
  - FR-5.1..5.6, AR-D4-1..2, AR-D5-1..4, AR-D13-1
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.authorization import is_grant_valid
from mailbot_api.actions.graph_write import (
    FakeGraphWriteAdapter,
    GraphApplyResult,
    GraphWriteAdapter,
)
from mailbot_api.actions.types import ActionType, is_send_family
from mailbot_api.db.connection import (
    execute_write,
    fetchall,
    fetchone,
)
from mailbot_api.db.queries import (
    ACTION_HISTORY_INSERT,
    EMAIL_MARKER_AND_DELETED_AT_SELECT,
    PENDING_ACTION_CLAIM_DRAINING,
    PENDING_ACTION_MARK_APPLIED,
    PENDING_ACTION_MARK_APPLIED_WITH_GRANT,
    PENDING_ACTION_MARK_FAILED,
    PENDING_ACTION_REVERT_TO_PENDING_GRANT,
    PENDING_ACTIONS_SELECT_DRAINABLE,
    SEND_FAMILY_BUDGET_CONSUMED_TODAY_COUNT,
)
from mailbot_api.notifications import send_urgent

_logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 25
TIER_3_GRANT_WAIT_WINDOW = timedelta(minutes=30)
DEFAULT_TICK_INTERVAL_SECONDS = 2.0

# Story 4-6: hard cap on send-family actions per UTC day. Failed sends count
# too (per AR-D5-2) — the cap protects against retry-bombing as well as
# excessive successful sends.
DAILY_SEND_CAP = 20


class PendingActionRow(BaseModel):
    """Typed projection of the pending_actions row layout."""

    model_config = ConfigDict(frozen=True)

    id: int
    email_id: str | None
    action_type: ActionType
    tier: Literal[1, 2, 3]
    payload: dict[str, Any]
    proposed_at: str
    proposed_by_grant_id: int | None
    change_marker_at_propose: str | None
    status: str
    retry_count: int
    failure_reason: str | None
    terminal_at: str | None
    budget_consumed: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    # Tolerant of "Z" suffix.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_from_db_tuple(t: tuple[Any, ...]) -> PendingActionRow:
    """Construct PendingActionRow from a PENDING_ACTIONS_SELECT_DRAINABLE row."""
    (
        row_id, email_id, action_type_str, tier, payload_json, proposed_at,
        proposed_by_grant_id, change_marker_at_propose, status, retry_count,
        failure_reason, terminal_at, budget_consumed,
    ) = t
    return PendingActionRow(
        id=int(row_id),
        email_id=email_id,
        action_type=ActionType(action_type_str),
        tier=tier,
        payload=json.loads(payload_json) if payload_json else {},
        proposed_at=proposed_at,
        proposed_by_grant_id=proposed_by_grant_id,
        change_marker_at_propose=change_marker_at_propose,
        status=status,
        retry_count=retry_count,
        failure_reason=failure_reason,
        terminal_at=terminal_at,
        budget_consumed=int(budget_consumed),
    )


async def _claim_row(db_path: str, row_id: int) -> bool:
    """Atomic CLAIM: returns True iff we successfully flipped pending→draining."""
    rowcount = await execute_write(db_path, PENDING_ACTION_CLAIM_DRAINING, (row_id,))
    return rowcount == 1


async def _mark_applied(
    db_path: str, row: PendingActionRow, grant_id: int | None = None,
) -> None:
    budget = 1 if is_send_family(row.action_type) else 0
    now_iso = _iso(_utc_now())
    # Tier-2/3 success → also record the grant that authorized this drain.
    # Tier-1 has no grant; pass through MARK_APPLIED untouched.
    if grant_id is not None:
        await execute_write(
            db_path,
            PENDING_ACTION_MARK_APPLIED_WITH_GRANT,
            (now_iso, budget, grant_id, row.id),
        )
    else:
        await execute_write(
            db_path,
            PENDING_ACTION_MARK_APPLIED,
            (now_iso, budget, row.id),
        )
    _logger.info(
        "drainer row applied",
        extra={
            "event": "action.drainer.row.applied",
            "action_id": row.id,
            "action_type": row.action_type.value,
            "tier": row.tier,
        },
    )


async def _mark_failed(
    db_path: str, row: PendingActionRow, reason: str,
) -> None:
    # Per AR-D5-2: failed sends consume budget too — prevents retry-bombing the cap.
    budget = 1 if is_send_family(row.action_type) else 0
    await execute_write(
        db_path,
        PENDING_ACTION_MARK_FAILED,
        (reason, _iso(_utc_now()), budget, row.id),
    )
    _logger.warning(
        "drainer row failed",
        extra={
            "event": "action.drainer.row.failed",
            "action_id": row.id,
            "action_type": row.action_type.value,
            "tier": row.tier,
            "failure_reason": reason,
        },
    )


async def _revert_to_pending_grant(
    db_path: str, row: PendingActionRow, grant_id: int | None,
) -> None:
    """Revert a claimed Tier-2/3 row back to pending_grant when the grant isn't valid yet."""
    await execute_write(
        db_path,
        PENDING_ACTION_REVERT_TO_PENDING_GRANT,
        (grant_id, row.id),
    )
    _logger.info(
        "drainer row pending grant",
        extra={
            "event": "action.drainer.row.pending_grant",
            "action_id": row.id,
            "action_type": row.action_type.value,
            "tier": row.tier,
        },
    )


def _build_pre_state(row: PendingActionRow) -> dict[str, Any]:
    """Construct the pre-state snapshot for action_history.

    Story 4-4 ships an empty dict for every action_type — the emails table
    doesn't carry per-action revert fields (is_read, folder_id, categories).
    Story 4-8 chooses the implementation path (schema migration vs Graph-read
    at revert time) and fills this in.
    """
    return {}


async def _insert_history(db_path: str, row: PendingActionRow) -> None:
    """Write the action_history pre-state row.

    CR-4-4-2: per AC-7 — the action_history row must exist BEFORE the
    Graph dispatch, so that a failed dispatch (or an in-flight crash) still
    leaves an auditable record. The previous implementation wrote history
    only on the success path inside `_write_history_and_apply`; failed and
    adapter-exception paths produced no history row, breaking Story 4-8's
    reverter and contradicting the docstring's own stated intent.
    """
    pre_state_json = json.dumps(_build_pre_state(row))
    await execute_write(
        db_path,
        ACTION_HISTORY_INSERT,
        (row.id, pre_state_json, _iso(_utc_now())),
    )


async def _read_email_marker_and_deleted(
    db_path: str, email_id: str,
) -> tuple[str | None, str | None] | None:
    row = await fetchone(db_path, EMAIL_MARKER_AND_DELETED_AT_SELECT, (email_id,))
    if row is None:
        return None
    return (row[0], row[1])


async def _send_cap_exceeded(db_path: str) -> bool:
    """Story 4-6 AC-4: returns True if the SEND-family budget for today is
    at or above DAILY_SEND_CAP.

    Counts rows where `budget_consumed=1` AND action_type IN (send family)
    AND `terminal_at >= today_midnight_utc`. Successful and failed sends
    both consume budget per AR-D5-2.
    """
    today_midnight = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    row = await fetchone(
        db_path,
        SEND_FAMILY_BUDGET_CONSUMED_TODAY_COUNT,
        (_iso(today_midnight),),
    )
    if row is None:
        return False
    count = int(row[0])
    return count >= DAILY_SEND_CAP


async def _check_tier_1(
    db_path: str, row: PendingActionRow,
) -> str | None:
    """Apply AR-D4-2 lenient 3-rule to a Tier-1 row. Returns a failure reason
    string if the row should be marked failed, OR None if it can proceed to
    dispatch.
    """
    if row.email_id is None:
        # Tier-1 actions in the current type spec are all email-scoped, but
        # be defensive: if an email-less Tier-1 ever lands here, just proceed.
        return None
    marker_info = await _read_email_marker_and_deleted(db_path, row.email_id)
    if marker_info is None:
        # Rule 1 edge: the email row vanished entirely — treat as deleted (silent).
        return "target_deleted"
    _, deleted_at = marker_info
    if deleted_at is not None:
        return "target_deleted"
    return None


async def _check_tier_2(
    db_path: str, row: PendingActionRow,
) -> tuple[str | None, int | None, bool]:
    """Tier-2 check: returns (failure_reason | None, grant_id | None, should_wait).

    - (None, grant_id, False) → proceed to dispatch
    - (reason, None, False) → mark failed
    - (None, None, True) → revert to pending_grant (no valid grant yet)
    """
    ok, grant_id = await is_grant_valid(row.action_type, row.email_id, db_path=db_path)
    if not ok:
        return (None, None, True)
    # Grant valid → apply lenient policy.
    fail = await _check_tier_1(db_path, row)  # same lenient rules as Tier-1
    return (fail, grant_id, False)


async def _check_tier_3(
    db_path: str, row: PendingActionRow,
) -> tuple[str | None, int | None, bool]:
    """Tier-3 check: returns (failure_reason | None, grant_id | None, should_wait).

    Strict ETag enforcement when email_id is set. Email-less Tier-3 actions
    (MODIFY_INBOX_RULE / MODIFY_OUTLOOK_FILTER / TOUCH_DELEGATED_MAILBOX /
    SEND_NEW_EMAIL) skip the ETag check per Story 4-2 CR-2 resolution —
    there's no source email row to compare against.
    """
    ok, grant_id = await is_grant_valid(row.action_type, row.email_id, db_path=db_path)
    if not ok:
        # Grant-wait window: if too much time has elapsed since propose, fail
        # hard with an urgent notification; else revert to pending_grant.
        elapsed = _utc_now() - _parse_iso(row.proposed_at)
        if elapsed > TIER_3_GRANT_WAIT_WINDOW:
            return ("grant_expired_unauthorized", None, False)
        return (None, None, True)

    # ETag check — only for email-scoped Tier-3 rows.
    if row.email_id is not None:
        marker_info = await _read_email_marker_and_deleted(db_path, row.email_id)
        if marker_info is None:
            return ("target_deleted", grant_id, False)
        current_marker, deleted_at = marker_info
        if deleted_at is not None:
            return ("target_deleted", grant_id, False)
        if current_marker != row.change_marker_at_propose:
            _logger.warning(
                "ETag drift",
                extra={
                    "event": "action.drainer.row.etag_drift",
                    "action_id": row.id,
                    "action_type": row.action_type.value,
                    "expected_marker": row.change_marker_at_propose,
                    "current_marker": current_marker,
                },
            )
            return ("state_drift_etag", grant_id, False)
    # Email-less Tier-3 skips ETag check per CR-2 — proceed.
    return (None, grant_id, False)


def _notify_failure(row: PendingActionRow, reason: str) -> None:
    """Tier-banded notification per AR-D5-4.

    Tier-1: silent (log already happened).
    Tier-2: important — Epic 6 wires the daily digest; for now we stand in
            with send_urgent so the operator at least sees the row (and we
            log the intended tier so Epic 6 can re-route).
    Tier-3: urgent.

    CR-4-4-5: every notification emits a structured `intended_notification_tier`
    log field so an Epic 6 migration / shadow-mode observer can programmatically
    detect "this would have been important, not urgent" without text-matching
    the human-readable message.
    """
    if row.tier == 1:
        return
    if row.tier == 2:
        # TODO(epic-6): replace with notifications.send_important; for now
        # surface via urgent so failures don't get silently lost.
        _logger.warning(
            "drainer Tier-2 failure routed to urgent as stand-in",
            extra={
                "event": "action.drainer.notify",
                "action_id": row.id,
                "action_type": row.action_type.value,
                "tier": 2,
                "intended_notification_tier": "important",
                "actual_notification_tier": "urgent",
                "reason": reason,
            },
        )
        send_urgent(
            f"action {row.id} ({row.action_type.value}, Tier 2) failed: {reason} "
            "[intended tier=important; Epic 6 wires the digest]"
        )
        return
    # Tier 3
    _logger.warning(
        "drainer Tier-3 failure routed to urgent",
        extra={
            "event": "action.drainer.notify",
            "action_id": row.id,
            "action_type": row.action_type.value,
            "tier": 3,
            "intended_notification_tier": "urgent",
            "actual_notification_tier": "urgent",
            "reason": reason,
        },
    )
    send_urgent(
        f"action {row.id} ({row.action_type.value}, Tier 3) failed: {reason}"
    )


async def run_tick(
    db_path: str,
    adapter: GraphWriteAdapter | None = None,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """One iteration of the drainer loop. Returns the number of rows processed.

    `adapter` defaults to FakeGraphWriteAdapter when None — useful for tests
    and for Story 4-4 stand-alone execution before Story 4-5 lands the real
    OutlookGraphWriteAdapter.
    """
    if adapter is None:
        adapter = FakeGraphWriteAdapter()
    rows_data = await fetchall(db_path, PENDING_ACTIONS_SELECT_DRAINABLE, (batch_size,))
    # CR-4-4-3: emit prefetch_count at tick.start so the metric name is honest;
    # processed count fires at tick.done after the loop.
    _logger.info(
        "drainer tick start",
        extra={"event": "action.drainer.tick.start", "prefetch_count": len(rows_data)},
    )
    processed = 0
    for tup in rows_data:
        row = _row_from_db_tuple(tup)
        # Atomic CLAIM — if a concurrent drainer beat us, skip.
        if not await _claim_row(db_path, row.id):
            continue
        processed += 1
        # CR-4-4-1: defensive catch-all so an unexpected exception in any of
        # the per-tier checks / history write / send-cap query does not leave
        # the row stuck in `draining` forever. The adapter-level try/except
        # below still handles dispatch exceptions with finer-grained tagging.
        try:
            await _process_claimed_row(db_path, row, adapter)
        except Exception as exc:  # noqa: BLE001 — recovery guard for stuck-draining rows
            _logger.exception(
                "drainer row processing crashed; marking failed to clear claim",
                extra={
                    "event": "action.drainer.row_crash",
                    "action_id": row.id,
                    "action_type": row.action_type.value,
                    "tier": row.tier,
                    "exception_type": type(exc).__name__,
                },
            )
            try:
                await _mark_failed(db_path, row, f"drainer_internal_error:{type(exc).__name__}")
            except Exception:  # noqa: BLE001 — last-resort guard
                _logger.exception(
                    "drainer recovery _mark_failed also crashed — row stuck in draining",
                    extra={"event": "action.drainer.recovery_failed", "action_id": row.id},
                )
    _logger.info(
        "drainer tick done",
        extra={
            "event": "action.drainer.tick.done",
            "prefetch_count": len(rows_data),
            "processed_count": processed,
        },
    )
    return processed


async def _process_claimed_row(
    db_path: str, row: PendingActionRow, adapter: GraphWriteAdapter,
) -> None:
    """Handle a single claimed row through per-tier checks → dispatch → terminal flip."""
    # Per-tier pre-dispatch checks.
    failure: str | None = None
    grant_id: int | None = None

    if row.tier == 1:
        failure = await _check_tier_1(db_path, row)
    elif row.tier == 2:
        failure, grant_id, should_wait = await _check_tier_2(db_path, row)
        if should_wait:
            await _revert_to_pending_grant(db_path, row, grant_id)
            return
    elif row.tier == 3:
        failure, grant_id, should_wait = await _check_tier_3(db_path, row)
        if should_wait:
            await _revert_to_pending_grant(db_path, row, grant_id)
            return
    else:
        # CR-4-4-4: explicit guard for impossible tier values. The
        # `pending_actions.tier` CHECK constraint and PendingActionRow's
        # Literal[1,2,3] type both already exclude this, but a row inserted
        # by a future migration or direct sqlite3 shell command could slip
        # through; defaulting to Tier-3 semantics would silently apply the
        # wrong policy. Fail loud.
        _logger.warning(
            "drainer row has invalid tier value — marking failed",
            extra={
                "event": "action.drainer.invalid_tier",
                "action_id": row.id,
                "action_type": row.action_type.value,
                "tier": row.tier,
            },
        )
        await _mark_failed(db_path, row, f"invalid_tier:{row.tier}")
        _notify_failure(row, f"invalid_tier:{row.tier}")
        return

    if failure is not None:
        await _mark_failed(db_path, row, failure)
        _notify_failure(row, failure)
        return

    # Story 4-6 hard 20-send/day cap. Checked BEFORE dispatch so we never
    # call Graph past the cap. The failed row still consumes budget (per
    # AR-D5-2 + _mark_failed's is_send_family branch) — that's intentional;
    # it prevents retry-bombing from re-attempting the same row 100×.
    if is_send_family(row.action_type) and await _send_cap_exceeded(db_path):
        await _mark_failed(db_path, row, "daily_send_cap_exceeded")
        _notify_failure(row, "daily_send_cap_exceeded")
        return

    # CR-4-4-2: action_history pre-state row MUST exist before dispatch so
    # that failed/exception paths still leave an auditable record (AC-7).
    # Previous implementation wrote history only on the success path inside
    # `_write_history_and_apply`.
    await _insert_history(db_path, row)

    # Dispatch via the adapter — capture both result and any synchronous exception.
    try:
        result: GraphApplyResult = await adapter.apply(row)
    except Exception as exc:  # noqa: BLE001 — adapter contract is "return result"; defend against bugs
        await _mark_failed(db_path, row, f"adapter_exception:{type(exc).__name__}")
        _notify_failure(row, f"adapter_exception:{type(exc).__name__}")
        return

    if result.ok:
        await _mark_applied(db_path, row, grant_id=grant_id)
    else:
        reason = result.error or "unknown_adapter_failure"
        await _mark_failed(db_path, row, reason)
        _notify_failure(row, reason)


async def run_loop(
    db_path: str,
    adapter: GraphWriteAdapter | None = None,
    *,
    interval_seconds: float = DEFAULT_TICK_INTERVAL_SECONDS,
    shutdown_event: Any = None,
) -> None:
    """Continuous drainer loop. Runs `run_tick` every `interval_seconds`.

    `shutdown_event` is an asyncio.Event-like with `.is_set()`; if provided,
    the loop exits cleanly when set. Otherwise runs until cancelled.

    Exceptions inside run_tick are caught + logged + heartbeated — the loop
    never exits on a single-tick failure (per AC-9 worker integration).
    """
    import asyncio

    while True:
        if shutdown_event is not None and shutdown_event.is_set():
            return
        try:
            await run_tick(db_path, adapter)
        except Exception as exc:  # noqa: BLE001 — loop must not exit on tick failures
            _logger.exception(
                "drainer tick crashed",
                extra={
                    "event": "action.drainer.tick.error",
                    "exc_type": type(exc).__name__,
                },
            )
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_TICK_INTERVAL_SECONDS",
    "PendingActionRow",
    "TIER_3_GRANT_WAIT_WINDOW",
    "run_loop",
    "run_tick",
]
