"""Unit tests for mailbot_api/router/response_cache.py (Story 2-7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.response_cache import (
    compute_cache_key,
    insert,
    lookup,
)


def test_compute_cache_key_is_deterministic() -> None:
    a = compute_cache_key("qwen", 0.0, "sys", "user")
    b = compute_cache_key("qwen", 0.0, "sys", "user")
    assert a == b


@pytest.mark.parametrize(
    ("a_args", "b_args"),
    [
        (("m1", 0.0, "s", "u"), ("m2", 0.0, "s", "u")),
        (("m", 0.0, "s", "u"), ("m", 0.5, "s", "u")),
        (("m", 0.0, "s1", "u"), ("m", 0.0, "s2", "u")),
        (("m", 0.0, "s", "u1"), ("m", 0.0, "s", "u2")),
    ],
)
def test_compute_cache_key_changes_on_any_input(
    a_args: tuple[str, float, str, str], b_args: tuple[str, float, str, str]
) -> None:
    assert compute_cache_key(*a_args) != compute_cache_key(*b_args)


async def test_lookup_miss_returns_none(tmp_path: Path) -> None:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    assert await lookup(db_path, "nonexistent-key") is None


async def test_insert_then_lookup_hit(tmp_path: Path) -> None:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    # Story 3-2: coarse_class output uses field name `class_coarse` with 6 labels.
    payload = json.dumps({"class_coarse": "newsletter", "confidence": 0.9})
    await insert(
        db_path,
        cache_key="key-1",
        task_type="coarse_class",
        model="claude-haiku-4-5-20251001",
        result_json=payload,
        cost_usd=0.0012,
        ttl_seconds=300,
    )
    row = await lookup(db_path, "key-1")
    assert row is not None
    assert row["result_json"] == payload
    assert row["ttl_seconds"] == 300


async def test_lookup_increments_hit_count(tmp_path: Path) -> None:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    # Story 3-2: "spam" is now "spam_like" in the 6-label taxonomy.
    payload = json.dumps({"class_coarse": "spam_like", "confidence": 0.99})
    await insert(
        db_path,
        cache_key="key-2",
        task_type="coarse_class",
        model="qwen2.5:3b-instruct-q4_K_M",
        result_json=payload,
        cost_usd=0.0,
        ttl_seconds=300,
    )
    first = await lookup(db_path, "key-2")
    second = await lookup(db_path, "key-2")
    third = await lookup(db_path, "key-2")
    assert first is not None and first["hit_count"] == 1
    assert second is not None and second["hit_count"] == 2
    assert third is not None and third["hit_count"] == 3


async def test_lookup_expired_returns_none(tmp_path: Path) -> None:
    """TTL=0 stored means the very next lookup is past-expiry."""
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    await insert(
        db_path,
        cache_key="key-3",
        task_type="coarse_class",
        model="qwen",
        result_json="{}",
        cost_usd=0.0,
        ttl_seconds=0,
    )
    # With TTL=0 and age>0, lookup returns None.
    import asyncio

    await asyncio.sleep(1.1)
    assert await lookup(db_path, "key-3") is None
