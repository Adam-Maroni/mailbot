"""Story 6-1: `mailbot status` assembler.

Composes the operator status board read by `mailbot status` (via the
`GET /admin/status` HTTP endpoint, see `mailbot_api/main.py`). All section
reads run in parallel via `asyncio.gather` so the total wall-clock budget
is bounded by the slowest section (< 1s on 100k `router_calls` rows
per the AC perf budget).

Sections:
  * sync — worker_health[sync] + staleness alarm
  * ingest — unprocessed-email count + backpressure flag
  * actions — pending_actions counts (by tier, awaiting-grant, failed-24h)
  * budget — today/month spend via verbs.cost.cost_breakdown
  * cache — 7-day cache-hit ratio
  * errors — last 5 failed/retry_recovered router_calls
  * hermes_aux — last-24h hermes-aux call count + simple drift heuristic
  * router — Story 6-2 pause-state visibility
  * oauth — Story 6-15: refresh-token lifecycle + oauth_refresh_failing alarm
  * container_health — mailbot-api (self) + ollama (HTTP probe) + mailbot-hermes (log-tail)

Hermes-aux drift fire-once semantics (Epic 2 retro C17) are DEFERRED to
Story 6-3's notification dispatcher — this CLI surfaces the current
stateless flag, not a fire-once episode marker.

Container health for mailbot-hermes uses the log-tail fallback (Option B
per Story 6-1 Dev Notes): if `/var/log/mailbot/mailbot-hermes.log` exists
and was written within the last 5 minutes, mark `ok`; older or missing
marks `degraded`/`unknown`. This is a known gap from Story 6-0's F3/F4/F5
carry-forward (Hermes does not expose a documented /health endpoint).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from mailbot_api.db import connection, queries
from mailbot_api.ingest.backpressure import BACKPRESSURE_THRESHOLD, count_unprocessed
from mailbot_api.router.budget import DAILY_SOFT_WARN_USD, MONTHLY_HARD_CAP_USD
from mailbot_api.sync.oauth import OAUTH_REFRESH_FAIL_THRESHOLD
from mailbot_api.worker import STALE_THRESHOLD_MINUTES, minutes_since, read_sync_health

logger = logging.getLogger(__name__)

# Simple, threshold-based drift heuristic per Story 6-1 Dev Notes Path 1.
# Fire-once semantics are Story 6-3's responsibility.
HERMES_AUX_DRIFT_THRESHOLD_24H = 100

# Container-health log-tail fallback for mailbot-hermes (see module docstring).
HERMES_LOG_PATH = Path("/var/log/mailbot/mailbot-hermes.log")
HERMES_LOG_STALE_THRESHOLD_SECONDS = 300  # 5 minutes

# HTTP probe constants.
OLLAMA_PROBE_URL = "http://ollama:11434/api/tags"
OLLAMA_PROBE_TIMEOUT_SECONDS = 1.0


ContainerStatus = Literal["ok", "degraded", "down", "unknown"]


class SyncStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    last_heartbeat_at: str | None
    last_outcome: str | None
    minutes_since_last_ok: float | None
    sync_health_alarm: bool


class IngestStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    unprocessed_count: int
    backpressure_active: bool
    last_heartbeat_at: str | None
    last_outcome: str | None


class ActionsStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    pending_count_by_tier: dict[int, int]
    awaiting_grant_count: int
    failed_in_last_24h: int


class BudgetStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    today_usd: float
    month_usd: float
    month_cap_usd: float
    degraded_mode_active: bool
    daily_warn_fired_today: bool


class CacheStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    cache_hit_rate_7d: float


class RouterErrorSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    router_call_id: int
    ts: str
    task_type: str
    model_chosen: str
    outcome: str
    caller_origin: str | None


class ErrorsStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    last_5_router_errors: list[RouterErrorSummary]


class HermesAuxStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    last_24h_count: int
    drift_alarm: bool


class ContainerHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    mailbot_api: ContainerStatus
    mailbot_hermes: ContainerStatus
    ollama: ContainerStatus


class RouterStatus(BaseModel):
    """Story 6-2: Router pause-state surface in the status board."""

    model_config = ConfigDict(frozen=True)

    paused: bool
    reason: str | None
    paused_at: str | None


class OAuthStatus(BaseModel):
    """Story 6-15: Outlook OAuth refresh-token health surface."""

    model_config = ConfigDict(frozen=True)

    last_rotated_at: str | None
    rotation_count: int
    consecutive_refresh_failures: int
    oauth_refresh_failing: bool
    access_token_expires_at: str | None
    # Minutes since the cached access token expired. None when the token is
    # still inside its validity window or when no token has been seeded yet.
    access_token_stale_minutes: float | None


class StatusReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    container_health: ContainerHealth
    sync: SyncStatus
    ingest: IngestStatus
    actions: ActionsStatus
    budget: BudgetStatus
    cache: CacheStatus
    errors: ErrorsStatus
    hermes_aux: HermesAuxStatus
    router: RouterStatus
    oauth: OAuthStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_microseconds_z(dt: datetime) -> str:
    """Microsecond-precision UTC ISO-8601 with `Z` suffix — matches `utc_z_now()` shape."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def _read_sync(db_path: str) -> SyncStatus:
    last_heartbeat_at, last_outcome, _last_error = await read_sync_health(db_path)
    if last_heartbeat_at is None or last_outcome is None:
        return SyncStatus(
            last_heartbeat_at=None,
            last_outcome=None,
            minutes_since_last_ok=None,
            sync_health_alarm=False,
        )
    # CR-7 (Story 6-1 review 2026-06-03): populate minutes_since_last_ok
    # unconditionally with elapsed-time-since-last-heartbeat. The original
    # None-on-failure shape gave the operator zero staleness signal at the
    # exact moment they needed it most. Reserve None ONLY for the
    # no-heartbeat-yet case (handled above).
    elapsed = minutes_since(last_heartbeat_at)
    alarm = last_outcome != "ok" or elapsed > STALE_THRESHOLD_MINUTES
    return SyncStatus(
        last_heartbeat_at=last_heartbeat_at,
        last_outcome=last_outcome,
        minutes_since_last_ok=elapsed,
        sync_health_alarm=alarm,
    )


async def _read_ingest(db_path: str) -> IngestStatus:
    unprocessed = await count_unprocessed(db_path)
    backpressure = unprocessed > BACKPRESSURE_THRESHOLD
    ingest_hb = await connection.fetchone(
        db_path, queries.WORKER_HEALTH_SELECT, ("ingest_pipeline",)
    )
    if ingest_hb is None:
        return IngestStatus(
            unprocessed_count=unprocessed,
            backpressure_active=backpressure,
            last_heartbeat_at=None,
            last_outcome=None,
        )
    # WORKER_HEALTH_SELECT returns (component, last_heartbeat_at, last_outcome, last_error)
    return IngestStatus(
        unprocessed_count=unprocessed,
        backpressure_active=backpressure,
        last_heartbeat_at=str(ingest_hb[1]) if ingest_hb[1] is not None else None,
        last_outcome=str(ingest_hb[2]) if ingest_hb[2] is not None else None,
    )


async def _read_actions(db_path: str) -> ActionsStatus:
    tier_rows = await connection.fetchall(
        db_path, queries.PENDING_ACTIONS_COUNT_BY_TIER, ()
    )
    pending_by_tier: dict[int, int] = {int(row[0]): int(row[1]) for row in tier_rows}
    awaiting_row = await connection.fetchone(
        db_path, queries.PENDING_ACTIONS_AWAITING_GRANT_COUNT, ()
    )
    awaiting = int(awaiting_row[0]) if awaiting_row else 0
    since_24h = _iso_microseconds_z(_utc_now() - timedelta(hours=24))
    failed_row = await connection.fetchone(
        db_path, queries.PENDING_ACTIONS_FAILED_LAST_24H, (since_24h,)
    )
    failed_24h = int(failed_row[0]) if failed_row else 0
    return ActionsStatus(
        pending_count_by_tier=pending_by_tier,
        awaiting_grant_count=awaiting,
        failed_in_last_24h=failed_24h,
    )


async def _read_budget(db_path: str) -> BudgetStatus:
    """Reads router_calls totals directly (NOT via verbs.cost.cost_breakdown —
    boundary check forbids verbs imports from observability/). Same SQL
    constant the verb uses; same math."""
    now = _utc_now()
    today_iso = now.strftime("%Y-%m-%dT00:00:00Z")
    month_iso = now.strftime("%Y-%m-01T00:00:00Z")
    today_row = await connection.fetchone(
        db_path, queries.ROUTER_CALLS_TOTALS_SINCE, (today_iso,)
    )
    month_row = await connection.fetchone(
        db_path, queries.ROUTER_CALLS_TOTALS_SINCE, (month_iso,)
    )
    # ROUTER_CALLS_TOTALS_SINCE returns (count, sum_cost_usd, sum_cached_in, sum_in).
    today_usd = float(today_row[1]) if today_row else 0.0
    month_usd = float(month_row[1]) if month_row else 0.0
    degraded_row = await connection.fetchone(
        db_path, queries.DEGRADED_MODE_SELECT, ()
    )
    degraded = bool(degraded_row[0]) if degraded_row else False
    return BudgetStatus(
        today_usd=today_usd,
        month_usd=month_usd,
        month_cap_usd=MONTHLY_HARD_CAP_USD,
        degraded_mode_active=degraded,
        daily_warn_fired_today=today_usd >= DAILY_SOFT_WARN_USD,
    )


async def _read_cache(db_path: str) -> CacheStatus:
    since_7d = _iso_microseconds_z(_utc_now() - timedelta(days=7))
    row = await connection.fetchone(
        db_path, queries.ROUTER_CALLS_CACHE_HIT_RATE_LAST_7D, (since_7d,)
    )
    if row is None:
        return CacheStatus(cache_hit_rate_7d=0.0)
    sum_cached = int(row[0])
    sum_in = int(row[1])
    ratio = (sum_cached / sum_in) if sum_in > 0 else 0.0
    return CacheStatus(cache_hit_rate_7d=ratio)


async def _read_errors(db_path: str) -> ErrorsStatus:
    rows = await connection.fetchall(
        db_path, queries.ROUTER_CALLS_LAST_N_ERRORS, (5,)
    )
    summaries = [
        RouterErrorSummary(
            router_call_id=int(row[0]),
            ts=str(row[1]),
            task_type=str(row[2]),
            model_chosen=str(row[3]),
            outcome=str(row[4]),
            caller_origin=str(row[5]) if row[5] is not None else None,
        )
        for row in rows
    ]
    return ErrorsStatus(last_5_router_errors=summaries)


async def _read_router(db_path: str) -> RouterStatus:
    """Story 6-2: read pause_state for the status board.

    Reuses Story 2-9's PAUSE_STATE_SELECT (returns `(paused, reason, paused_at,
    resumed_at)`) — we only surface the first three. Empty row → not paused
    (the pause_state table is seeded with `(id=1, paused=0)` per migration 010).

    CR-3 (Story 6-2 review 2026-06-03): Story 2-9's `PAUSE_STATE_RESUME` only
    flips `paused=0` — it does NOT clear `reason` or `paused_at` (so the
    audit trail of "last pause episode" survives in the DB). For the
    status board's read, that would surface stale `reason`/`paused_at` to
    the operator after a resume. Null them out at the read boundary when
    `paused=False` so the status view doesn't lie. The DB still carries the
    last-pause-episode trail for forensics.
    """
    row = await connection.fetchone(db_path, queries.PAUSE_STATE_SELECT, ())
    if row is None:
        return RouterStatus(paused=False, reason=None, paused_at=None)
    paused = bool(row[0])
    if not paused:
        return RouterStatus(paused=False, reason=None, paused_at=None)
    return RouterStatus(
        paused=True,
        reason=str(row[1]) if row[1] is not None else None,
        paused_at=str(row[2]) if row[2] is not None else None,
    )


async def _read_oauth(db_path: str) -> OAuthStatus:
    """Story 6-15: Outlook OAuth refresh-token surface.

    Reads the single-row `oauth_state` table for the microsoft_graph provider.
    The `oauth_refresh_failing` flag is computed from
    `consecutive_refresh_failures` (bumped by `mailbot_api/sync/oauth.py`'s
    `exchange_and_persist` failure paths, reset to 0 on success). Threshold:
    `OAUTH_REFRESH_FAIL_THRESHOLD` (default 3).

    No row yet → all-zero status with no alarm. The bootstrap seed flow
    (Story 1-6) inserts the row on the first sync iteration, so this branch
    is only reachable on a fresh deploy that has never run sync.

    Story 6-15 CR-8: if migration 023 (the one that introduces
    `consecutive_refresh_failures`) has not yet applied — e.g., a healthcheck
    races `apply_pending_migrations` during boot, or a test imports the
    reader without running migrations — the read raises a sqlite3
    `OperationalError: no such column`. Returning the all-zero status keeps
    the status board responsive instead of taking down `/admin/status`. We
    do not import sqlite3 directly (boundary rule reserves that to
    db/connection.py + db/migrations_runner.py); detection by error-message
    substring is sufficient since the message text is stable across the
    library versions we ship.
    """
    try:
        row = await connection.fetchone(
            db_path, queries.OAUTH_STATE_STATUS_SELECT, ("microsoft_graph",)
        )
    except Exception as exc:  # noqa: BLE001 — narrowed below
        if "no such column" not in str(exc).lower():
            raise
        logger.warning(
            "oauth status read failed pre-migration — treating as all-zero",
            extra={"event": "status.oauth.pre_migration", "error": str(exc)[:200]},
        )
        return OAuthStatus(
            last_rotated_at=None,
            rotation_count=0,
            consecutive_refresh_failures=0,
            oauth_refresh_failing=False,
            access_token_expires_at=None,
            access_token_stale_minutes=None,
        )
    if row is None:
        return OAuthStatus(
            last_rotated_at=None,
            rotation_count=0,
            consecutive_refresh_failures=0,
            oauth_refresh_failing=False,
            access_token_expires_at=None,
            access_token_stale_minutes=None,
        )
    access_expires_at = row[0]
    last_rotated_at = row[1]
    rotation_count = int(row[2])
    consecutive_failures = int(row[3])
    stale_minutes: float | None = None
    if access_expires_at:
        try:
            expiry = datetime.fromisoformat(access_expires_at.replace("Z", "+00:00"))
        except ValueError:
            expiry = None
        if expiry is not None:
            elapsed = _utc_now() - expiry
            if elapsed > timedelta(0):
                stale_minutes = elapsed.total_seconds() / 60.0
    return OAuthStatus(
        last_rotated_at=last_rotated_at,
        rotation_count=rotation_count,
        consecutive_refresh_failures=consecutive_failures,
        oauth_refresh_failing=consecutive_failures >= OAUTH_REFRESH_FAIL_THRESHOLD,
        access_token_expires_at=access_expires_at,
        access_token_stale_minutes=stale_minutes,
    )


async def _read_hermes_aux(db_path: str) -> HermesAuxStatus:
    """Path 1 (Story 6-1 Dev Notes): stateless threshold-based drift flag.

    Epic 2 retro C17 carry-forward (fire-once episode semantics) is deferred
    to Story 6-3's notification dispatcher — the status CLI surfaces the
    current state, not the episode boundary."""
    since_24h = _iso_microseconds_z(_utc_now() - timedelta(hours=24))
    row = await connection.fetchone(
        db_path, queries.ROUTER_CALLS_HERMES_AUX_COUNT_LAST_24H, (since_24h,)
    )
    count = int(row[0]) if row else 0
    drift = count > HERMES_AUX_DRIFT_THRESHOLD_24H
    return HermesAuxStatus(last_24h_count=count, drift_alarm=drift)


async def _probe_ollama() -> ContainerStatus:
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(OLLAMA_PROBE_URL)
            if 200 <= resp.status_code < 300:
                return "ok"
            if 500 <= resp.status_code < 600:
                return "degraded"
            return "degraded"
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError):
        return "down"
    except Exception:  # noqa: BLE001 — probe must NEVER crash the assembler
        logger.exception("ollama probe failed unexpectedly")
        return "unknown"


def _probe_hermes_from_log() -> ContainerStatus:
    """Option B log-tail fallback per Story 6-1 Dev Notes.

    Hermes does NOT expose a documented /health endpoint (Story 6-0 F3/F4/F5
    carry-forward). We treat "log file written within last 5 minutes" as ok.
    Older marks degraded; missing marks unknown.
    """
    try:
        if not HERMES_LOG_PATH.exists():
            return "unknown"
        mtime = HERMES_LOG_PATH.stat().st_mtime
        age_seconds = _utc_now().timestamp() - mtime
        if age_seconds <= HERMES_LOG_STALE_THRESHOLD_SECONDS:
            return "ok"
        return "degraded"
    except OSError:
        return "unknown"


async def _read_container_health() -> ContainerHealth:
    # mailbot-api is self — we ARE this process, by definition `ok` here.
    ollama_status = await _probe_ollama()
    # CR-2 (Story 6-1 review 2026-06-03): asyncio.get_event_loop() is deprecated
    # in 3.10+. Use get_running_loop() — we ARE inside an active loop here.
    hermes_status = await asyncio.get_running_loop().run_in_executor(
        None, _probe_hermes_from_log
    )
    return ContainerHealth(
        mailbot_api="ok",
        mailbot_hermes=hermes_status,
        ollama=ollama_status,
    )


async def assemble_status(db_path: str) -> StatusReport:
    """Compose the full operator status board.

    Section reads run in parallel via `asyncio.create_task` + per-task `await`
    so the total wall-clock budget is bounded by the slowest section. Per AC
    perf budget, this should complete in < 1s wall-clock on 100k router_calls.

    Why `create_task` + per-task `await` and not `asyncio.gather`:
    `asyncio.gather(*Awaitable[T1], *Awaitable[T2], ...)` is typed as
    `tuple[T1 | T2 | ..., ...]` under mypy's stubs — the heterogeneous return
    types collapse to their common ancestor (BaseModel here), which makes
    every `StatusReport(...)` keyword argument fail strict typing with
    `incompatible type "BaseModel"`. `create_task` returns a concretely-typed
    `asyncio.Task[T]` per section so `await task` preserves the section's
    concrete return type. Same parallelism semantics; different typing path.

    Note that this trades gather's first-exception-propagation for the
    sequential await order — if `_read_sync` raises, downstream tasks
    continue to completion and only get awaited (and discarded) after the
    exception unwinds. Acceptable for status board reads (every section is
    independent + read-only).
    """
    container_t = asyncio.create_task(_read_container_health())
    sync_t = asyncio.create_task(_read_sync(db_path))
    ingest_t = asyncio.create_task(_read_ingest(db_path))
    actions_t = asyncio.create_task(_read_actions(db_path))
    budget_t = asyncio.create_task(_read_budget(db_path))
    cache_t = asyncio.create_task(_read_cache(db_path))
    errors_t = asyncio.create_task(_read_errors(db_path))
    hermes_aux_t = asyncio.create_task(_read_hermes_aux(db_path))
    router_t = asyncio.create_task(_read_router(db_path))
    oauth_t = asyncio.create_task(_read_oauth(db_path))

    return StatusReport(
        container_health=await container_t,
        sync=await sync_t,
        ingest=await ingest_t,
        actions=await actions_t,
        budget=await budget_t,
        cache=await cache_t,
        errors=await errors_t,
        hermes_aux=await hermes_aux_t,
        router=await router_t,
        oauth=await oauth_t,
    )


__all__ = [
    "ActionsStatus",
    "BudgetStatus",
    "CacheStatus",
    "ContainerHealth",
    "ContainerStatus",
    "ErrorsStatus",
    "HERMES_AUX_DRIFT_THRESHOLD_24H",
    "HermesAuxStatus",
    "IngestStatus",
    "OAUTH_REFRESH_FAIL_THRESHOLD",
    "OAuthStatus",
    "RouterErrorSummary",
    "RouterStatus",
    "StatusReport",
    "SyncStatus",
    "assemble_status",
]
