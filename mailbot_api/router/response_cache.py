"""SQL-backed response cache per Story 2-7.

Keyed on ``sha256(model|temperature|system|user)`` so identical Router calls
return the cached result without re-dispatching. Per-task TTL is stored on
the row (from ``policy.tasks[task_type].response_cache_ttl_seconds``).

Hit semantics: a hit increments ``hit_count`` and returns a ``RouterResult``
with ``cost_usd=0``, ``cached_tokens_in=0``, and ``model_used``
=``"<original>+response_cache"`` so downstream cost-rollup queries can
pattern-match cache-hit rows separately from real dispatches.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now


def compute_cache_key(
    model: str,
    temperature: float,
    system: str,
    user: str,
    tools_hash: str = "",
) -> str:
    """Stable sha256 hex digest used as the response-cache primary key.

    Story 6-9 (F11 closure 2026-06-04): `tools_hash` was added defensively.
    Existing call sites pass nothing (empty string) — and crucially, the
    digest formula does NOT include the trailing `|{tools_hash}` separator
    when `tools_hash` is empty, so existing production cache rows (written
    with the pre-Story-6-9 4-arg form) continue to hit. When
    `dispatch_tool_call` later wires up its own caching (currently
    disabled per 6-9 design doc §6), it MUST pass a non-empty stable hash
    of the tools list to prevent a tools-bearing cache entry from being
    returned to a tools-free call.
    """
    if tools_hash:
        payload = f"{model}|{temperature}|{system}|{user}|{tools_hash}"
    else:
        payload = f"{model}|{temperature}|{system}|{user}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_z_iso8601(value: str) -> datetime:
    # Lenient: accepts both microsecond-precision (post-2026-06-02) and
    # legacy second-precision timestamps via fromisoformat.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def lookup(db_path: str, cache_key: str) -> dict[str, object] | None:
    """Return the cached row dict if it exists AND is unexpired, else None.

    A non-None return increments ``hit_count`` on the row. Callers receive
    the deserialized ``result_json`` and the original ``cost_usd``.
    """
    row = await connection.fetchone(db_path, queries.RESPONSE_CACHE_SELECT, (cache_key,))
    if row is None:
        return None

    result_json, cost_usd, cached_at, ttl_seconds, hit_count = row
    cached_dt = _parse_z_iso8601(cached_at)
    now = datetime.now(timezone.utc)
    age_seconds = (now - cached_dt).total_seconds()
    if age_seconds > ttl_seconds:
        return None

    # Bump hit_count atomically. We do not gate on the row existing because
    # the SELECT just confirmed it, and concurrent expiry doesn't change
    # the correctness of returning what we read.
    await connection.execute_write(
        db_path, queries.RESPONSE_CACHE_INCREMENT_HIT, (cache_key,)
    )

    return {
        "result_json": result_json,
        "cost_usd": cost_usd,
        "cached_at": cached_at,
        "ttl_seconds": ttl_seconds,
        "hit_count": hit_count + 1,
    }


async def insert(
    db_path: str,
    *,
    cache_key: str,
    task_type: str,
    model: str,
    result_json: str,
    cost_usd: float,
    ttl_seconds: int,
) -> None:
    """Upsert a row into ``response_cache``. ``hit_count`` is reset to 0 on
    overwrite — a re-caching represents a fresh start for hit accounting.
    """
    cached_at = utc_z_now()
    await connection.execute_write(
        db_path,
        queries.RESPONSE_CACHE_INSERT,
        (cache_key, task_type, model, result_json, cost_usd, cached_at, ttl_seconds),
    )


def serialize_router_output(output_model_json: str) -> str:
    """Round-trip the output JSON through json.loads/dumps so we don't store
    unsanitized provider strings. The Pydantic model already validated it,
    but a normalized form is friendlier for downstream raw-SQL inspection.
    """
    return json.dumps(json.loads(output_model_json), separators=(",", ":"))


__all__ = [
    "compute_cache_key",
    "insert",
    "lookup",
    "serialize_router_output",
]
