"""Story 3-4 AC-2, AC-3: write_embedding + read_embedding unit tests.

Uses real SQLite (tmp_path) + real migrations — Middleware-Real-Bootstrap
discipline per MailBot reframing.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import EMAIL_EMBEDDING_SELECT
from mailbot_api.ingest.embedding import read_embedding, write_embedding


async def _seed_email(db_path: str, graph_id: str = "seed-1") -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at) VALUES (?, ?)",
        (graph_id, "2026-06-01T00:00:00Z"),
    )


async def test_write_embedding_populates_blob_and_companions(tmp_path: Path) -> None:
    """AC-2: write_embedding writes blob + dtype + shape + prompt_v + model + at."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    vector = np.array([0.1, 0.2, 0.3, 0.4], dtype="<f4")
    await write_embedding(
        db_path=db_path, email_id="seed-1", vector=vector, model_id="nomic-embed-text"
    )

    row = await fetchone(db_path, EMAIL_EMBEDDING_SELECT, ("seed-1",))
    assert row is not None
    blob, dtype, shape_json = row
    assert blob is not None
    assert dtype == "<f4"
    assert json.loads(shape_json) == [4]
    # Bytes match the W-5 serialization exactly.
    assert blob == vector.astype("<f4").tobytes()


async def test_write_embedding_rejects_non_1d_vector(tmp_path: Path) -> None:
    """AC-2: ValueError on vector.ndim != 1 (caller bug)."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    vector_2d = np.array([[0.1, 0.2], [0.3, 0.4]], dtype="<f4")
    with pytest.raises(ValueError, match="1-D vector"):
        await write_embedding(
            db_path=db_path, email_id="seed-1", vector=vector_2d, model_id="x"
        )


async def test_write_embedding_rejects_empty_vector(tmp_path: Path) -> None:
    """AC-2: ValueError on empty vector (caller bug)."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    vector_empty = np.array([], dtype="<f4")
    with pytest.raises(ValueError, match="empty vector"):
        await write_embedding(
            db_path=db_path, email_id="seed-1", vector=vector_empty, model_id="x"
        )


async def test_read_embedding_roundtrip_preserves_all_values(tmp_path: Path) -> None:
    """AC-3: round-trip is byte-exact for the W-5 little-endian float32 contract."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    original = np.array([0.0, 1.0, -1.0, 0.5, 0.123456], dtype="<f4")
    await write_embedding(
        db_path=db_path, email_id="seed-1", vector=original, model_id="x"
    )

    roundtrip = await read_embedding(db_path=db_path, email_id="seed-1")
    assert roundtrip is not None
    assert np.array_equal(roundtrip, original)
    assert roundtrip.dtype == np.dtype("<f4")


async def test_read_embedding_returns_none_when_unwritten(tmp_path: Path) -> None:
    """AC-3: read_embedding returns None when the blob is NULL."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    # No write — blob is NULL.
    result = await read_embedding(db_path=db_path, email_id="seed-1")
    assert result is None


async def test_read_embedding_returns_none_when_email_missing(tmp_path: Path) -> None:
    """AC-3: missing email row also returns None (caller distinguishes nothing-yet vs not-found)."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    # No seed.

    result = await read_embedding(db_path=db_path, email_id="nope")
    assert result is None


async def test_write_embedding_cross_architecture_portability(tmp_path: Path) -> None:
    """AC-3: written blob bytes match the W-5 contract byte-for-byte.

    Catches accidental big-endian dtype or native-byte-order writes that
    would silently produce different bytes on a different host arch.
    """
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    vec = np.asarray([1.0, 2.0, 3.0], dtype="<f4")
    await write_embedding(
        db_path=db_path, email_id="seed-1", vector=vec, model_id="x"
    )

    row = await fetchone(db_path, EMAIL_EMBEDDING_SELECT, ("seed-1",))
    assert row is not None
    blob, _, _ = row
    # Canonical W-5 bytes.
    expected = np.asarray([1.0, 2.0, 3.0], dtype="<f4").tobytes()
    assert blob == expected, "W-5 byte-exact contract violated"


async def test_read_embedding_raises_on_partial_corruption(tmp_path: Path) -> None:
    """AC-3 defensive: blob present but dtype/shape NULL is unrecoverable corruption."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await _seed_email(db_path)

    # Manually corrupt: write blob without companions via direct SQL.
    # NOTE: this is a hostile fixture — production code path (write_embedding)
    # writes atomically so this shape can't arise via normal means.
    bad_blob = b"\x00" * 12  # 3 floats worth of zero bytes
    await execute_write(
        db_path,
        "UPDATE emails SET embedding = ? WHERE graph_id = ?",
        (bad_blob, "seed-1"),
    )

    with pytest.raises(ValueError, match="corrupted embedding row"):
        await read_embedding(db_path=db_path, email_id="seed-1")
