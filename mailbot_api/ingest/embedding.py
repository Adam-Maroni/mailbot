"""Embedding writer-monopoly + reader + orchestrator (Story 3-4).

This module is the SOLE writer of the ``emails.embedding`` (BLOB),
``emails.embedding_dtype`` (TEXT), and ``emails.embedding_shape`` (TEXT)
columns. Enforced by ``scripts/check_boundaries.py`` (Story 3-4 AC-7).

Public API:
  * ``write_embedding(*, db_path, email_id, vector, model_id)`` — atomic write
    of the 6 embedding columns. Vector serialized as little-endian float32
    raw bytes per the W-5 contract (Epic 2 retro §13).
  * ``read_embedding(*, db_path, email_id) -> numpy.ndarray | None`` — reads
    the blob using the companion-column dtype/shape, never hard-coded.
  * ``embed_email(*, db_path, email_id, caller_origin) -> EmbedEmailResult`` —
    higher-level orchestrator: dispatches via ``router.dispatch_embedding``,
    converts the returned vector to numpy, calls ``write_embedding``.

Sensitivity gate: ``dispatch_embedding`` enforces the FR-2.3 precondition
(sensitivity_at IS NULL → SENSITIVITY_NOT_CLASSIFIED). It does NOT enforce
SENSITIVITY_BLOCKS_API because embeddings are local-only per FR-2.5.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Final

import numpy as np
from pydantic import BaseModel, ConfigDict

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    EMAIL_BODY_FOR_SENSITIVITY_SELECT,
    EMAIL_EMBEDDING_SELECT,
    EMAIL_EMBEDDING_UPDATE,
)
from mailbot_api.router.errors import ErrorCode, RouterError
from mailbot_api.router.router import dispatch_embedding

__all__ = [
    "EmbedEmailResult",
    "embed_email",
    "read_embedding",
    "write_embedding",
]

# W-5 contract sentinel — little-endian float32 dtype string numpy understands.
_DTYPE_LITTLE_ENDIAN_F32: Final[str] = "<f4"

# Sentinel prompt-version for embeddings. Embeddings have no actual prompt
# modules; the value is stored verbatim so SQL queries that aggregate
# `embedding_prompt_v` see a stable identifier rather than NULL.
_EMBEDDING_PROMPT_V_SENTINEL: Final[str] = "v1"


def _utc_iso8601_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EmbedEmailResult(BaseModel):
    """Return shape of ``embed_email``. Errors-as-data per AR-PAT-4."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    email_id: str
    model: str | None = None
    dim: int | None = None
    latency_ms: int | None = None
    error: RouterError | None = None


async def write_embedding(
    *,
    db_path: str,
    email_id: str,
    vector: np.ndarray,
    model_id: str,
) -> None:
    """Persist the vector + W-5 companion columns atomically.

    The ONLY callers of this function should be ``mailbot_api/ingest/embedding.py``
    itself (i.e., ``embed_email``) and tests. The
    ``scripts/check_boundaries.py`` writer-monopoly check enforces this by
    detecting ``UPDATE emails SET ... embedding ...`` literals outside the
    allowlisted path.

    Raises:
        ValueError: if ``vector.ndim != 1`` or ``vector.size == 0`` (caller bug).
    """
    if vector.ndim != 1:
        raise ValueError(
            f"write_embedding expects a 1-D vector; got ndim={vector.ndim} shape={vector.shape}"
        )
    if vector.size == 0:
        raise ValueError("write_embedding refuses to write an empty vector")

    # Serialize per W-5: explicit little-endian float32, NEVER native byte order.
    blob = vector.astype(_DTYPE_LITTLE_ENDIAN_F32).tobytes()
    shape_json = json.dumps(list(vector.shape))

    await execute_write(
        db_path,
        EMAIL_EMBEDDING_UPDATE,
        (
            blob,
            _DTYPE_LITTLE_ENDIAN_F32,
            shape_json,
            _EMBEDDING_PROMPT_V_SENTINEL,
            model_id,
            _utc_iso8601_now(),
            email_id,
        ),
    )


async def read_embedding(*, db_path: str, email_id: str) -> np.ndarray | None:
    """Read the embedding back as a numpy array, OR ``None`` if not yet written.

    Uses the W-5 companion columns to drive the deserialize path — never
    hard-codes the dtype or shape. If the blob is populated but the
    companions are NULL (corrupted partial write), raises ``ValueError``.
    """
    row = await fetchone(db_path, EMAIL_EMBEDDING_SELECT, (email_id,))
    if row is None:
        return None
    blob, dtype, shape_json = row
    if blob is None:
        return None
    if dtype is None or shape_json is None:
        raise ValueError(
            f"corrupted embedding row for email_id={email_id!r}: blob present "
            f"but dtype/shape companions are NULL (dtype={dtype!r}, shape={shape_json!r})"
        )
    shape = tuple(json.loads(shape_json))
    return np.frombuffer(blob, dtype=dtype).reshape(shape)


async def embed_email(
    *,
    db_path: str,
    email_id: str,
    caller_origin: str = "ingest-pipeline-embedding",
) -> EmbedEmailResult:
    """Higher-level orchestrator: dispatch + serialize + write.

    Reads the email body via ``EMAIL_BODY_FOR_SENSITIVITY_SELECT`` (a
    cross-section read that returns subject + from_address + body_preview;
    the embedding only needs body_preview, but reusing the existing constant
    keeps the SQL surface small).

    The ``dispatch_embedding`` helper handles the FR-2.3 sensitivity precondition,
    policy lookup, adapter resolution, and ``router_calls`` audit-row write.

    Returns ``EmbedEmailResult.ok=False`` with a populated ``.error`` on any
    failure path; NEVER raises (errors-as-data per AR-PAT-4).
    """
    row = await fetchone(db_path, EMAIL_BODY_FOR_SENSITIVITY_SELECT, (email_id,))
    if row is None:
        return EmbedEmailResult(
            ok=False,
            email_id=email_id,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=f"email_id {email_id!r} not found in emails table",
                retryable=False,
            ),
        )
    _subject, _from_address, body_preview = row

    dispatch = await dispatch_embedding(
        text=body_preview or "",
        db_path=db_path,
        email_id=email_id,
        caller_origin=caller_origin,
    )
    if not dispatch.ok or dispatch.vector is None:
        return EmbedEmailResult(
            ok=False,
            email_id=email_id,
            model=dispatch.model_used or None,
            error=dispatch.error,
        )

    vector = np.asarray(dispatch.vector, dtype=_DTYPE_LITTLE_ENDIAN_F32)
    await write_embedding(
        db_path=db_path,
        email_id=email_id,
        vector=vector,
        model_id=dispatch.model_used,
    )

    return EmbedEmailResult(
        ok=True,
        email_id=email_id,
        model=dispatch.model_used,
        dim=dispatch.dim,
        latency_ms=dispatch.latency_ms,
    )
