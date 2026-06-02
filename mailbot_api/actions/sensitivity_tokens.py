"""In-memory sensitivity-token registry — Story 4-7.

Per AR-D12-1: the registry is process-local and dies on worker restart by
design — forcing operator re-confirmation. The audit trail lives on
`router_calls.sensitivity_grant_id` so the consume event survives.

Public API:
  - mint(email_id, task_type) → SensitivityToken
  - consume(token_value, email_id, task_type) → grant_id | None (single-use)
  - sweep() — removes expired tokens (call periodically; bounded dict hygiene)
  - _clear_registry_for_tests() — wipes state between tests

Tokens are cryptographic randoms (secrets.token_urlsafe(32)). The grant_id
returned to callers is sha256(token)[:16] — short enough to log, long enough
to uniquely identify across plausible mint rates.
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
    """Mint a fresh sensitivity token for (email_id, task_type). 10-min TTL."""
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


def consume(token_value: str, email_id: str, task_type: str) -> str | None:
    """Consume a token. Returns grant_id if (token, email_id, task_type) match
    an unexpired unconsumed entry; returns None otherwise.

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
    grant_id = token.grant_id
    del _REGISTRY[token_value]
    return grant_id


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
