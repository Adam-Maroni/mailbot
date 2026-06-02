"""In-memory sensitivity-token registry — Story 4-7.

Per AR-D12-1: the registry is process-local and dies on worker restart by
design — forcing operator re-confirmation. The audit trail lives on
`router_calls.sensitivity_grant_id` so the consume event survives.

CR-4-7-10 (2026-06-02 retroactive CR): the "dies on restart" property is a
security invariant — tokens must not survive process restarts. This module
backs the registry with a module-level Python dict (`_REGISTRY`) initialized
empty on import. Any refactor that introduces persistence (SQLite, Redis,
file-backed cache) violates AR-D12-1 and must be rejected at review time.

Public API:
  - mint(email_id, task_type) → SensitivityToken
  - consume(token_value, email_id, task_type) → tuple[grant_id, minted_at_iso] | None
    (single-use; returns the original mint timestamp so the audit row records
    real mint time, not consume time — CR-4-7-6)
  - sweep() — removes expired tokens (called inline at the top of every
    mint() so the registry self-cleans without needing worker wiring —
    CR-4-7-2)
  - _clear_registry_for_tests() — wipes state between tests

Tokens are cryptographic randoms (secrets.token_urlsafe(32) — 256 bits of
randomness). The grant_id is sha256(token)[:16] = 64-bit truncation of a
sha256 digest of a 256-bit random; grant_id uniqueness is sha256
preimage-bounded (not birthday-bounded), since each grant_id is
deterministically derived from a 256-bit cryptographic random. Collision
risk is negligible (CR-4-7-8).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict

_logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(minutes=10)


class SensitivityToken(BaseModel):
    model_config = ConfigDict(frozen=True)
    token_value: str
    email_id: str
    task_type: str
    expires_at: datetime
    minted_at: datetime
    grant_id: str


# Module-level registry. Per AR-D12-1: process-local, dies on restart.
# Mutable by design — `consume` flips a token to "consumed" by removing it
# (frozen Pydantic means we delete-and-omit rather than mutate-in-place).
_REGISTRY: dict[str, SensitivityToken] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_for_grant_id(token_value: str) -> str:
    return hashlib.sha256(token_value.encode("utf-8")).hexdigest()[:16]


def mint(email_id: str, task_type: str) -> SensitivityToken:
    """Mint a fresh sensitivity token for (email_id, task_type). 10-min TTL.

    CR-4-7-2: sweep expired tokens inline at the top of every mint so the
    registry self-cleans without needing worker-side scheduling. Mint rate
    is human-paced (one per confirmation prompt), so the per-mint sweep
    cost is amortized across rare operations.
    """
    sweep()  # inline self-cleaning per CR-4-7-2
    token_value = secrets.token_urlsafe(32)
    now = _utc_now()
    token = SensitivityToken(
        token_value=token_value,
        email_id=email_id,
        task_type=task_type,
        expires_at=now + TOKEN_TTL,
        minted_at=now,
        grant_id=_hash_for_grant_id(token_value),
    )
    _REGISTRY[token_value] = token
    return token


def consume(
    token_value: str, email_id: str, task_type: str
) -> tuple[str, datetime] | None:
    """Consume a token. Returns (grant_id, minted_at) if (token, email_id,
    task_type) match an unexpired unconsumed entry; returns None otherwise.

    CR-4-7-6: the return tuple now includes the original `minted_at` so the
    caller can record real mint time on the audit row rather than approximating
    with consume time. Previously the router used `utc_z_now()` at consume,
    drifting up to 10 minutes from the real mint timestamp for tokens consumed
    near TTL expiry.

    "Consumed" is modeled by removing the entry from the registry — frozen
    Pydantic precludes mutating .consumed on the model itself, and removal is
    the semantically cleaner signal anyway (the registry only ever contains
    live tokens).
    """
    token = _REGISTRY.get(token_value)
    if token is None:
        return None
    if token.email_id != email_id or token.task_type != task_type:
        return None
    if token.expires_at <= _utc_now():
        # Expired — remove + refuse.
        del _REGISTRY[token_value]
        return None
    minted_at = token.minted_at
    grant_id = token.grant_id
    del _REGISTRY[token_value]
    return (grant_id, minted_at)


def sweep() -> int:
    """Remove expired tokens. Returns the count removed.

    Call periodically from the worker (e.g., once per minute) to keep the
    registry bounded. Tokens are typically tiny but a long-lived process
    with high mint volume could otherwise drift.
    """
    now = _utc_now()
    expired = [tv for tv, t in _REGISTRY.items() if t.expires_at <= now]
    for tv in expired:
        del _REGISTRY[tv]
    return len(expired)


def _clear_registry_for_tests() -> None:
    """Test-only: wipe the registry so each test starts clean."""
    _REGISTRY.clear()


def _registry_size_for_tests() -> int:
    """Test-only: introspect the registry size."""
    return len(_REGISTRY)


__all__ = [
    "TOKEN_TTL",
    "SensitivityToken",
    "consume",
    "mint",
    "sweep",
]
