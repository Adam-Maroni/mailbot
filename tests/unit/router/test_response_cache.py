"""Unit tests for mailbot_api/router/response_cache.py (Story 2-7).

CR-3-2-CR-8 guard test (added 2026-06-02, Epic 3 retro action #10): the
`hermes_aux` task MUST NOT have `response_cache_ttl_seconds > 0` in the
production `router/policy.yaml`. Story 3-2's CR-8 found that enabling TTL
on `hermes_aux` triggers a latent double-wrap of the cache result (the
Hermes layer caches its own outputs separately, and the Router layer
would cache them again — the two TTLs interact unpredictably + downstream
consumers parse the doubly-wrapped JSON wrong). The bug is non-triggerable
today because `hermes_aux` has no TTL set; this guard ensures future
edits to `policy.yaml` cannot silently re-enable it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.policy import load_policy
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


# ---------------------------------------------------------------------------
# CR-3-2-CR-8 guard — hermes_aux must NOT enable response_cache_ttl_seconds
# ---------------------------------------------------------------------------


def _production_policy_path() -> Path:
    """Resolve the production router/policy.yaml relative to this test file.

    Layout: <repo>/router/policy.yaml; this file is at
    <repo>/tests/unit/router/test_response_cache.py → up three levels.
    """
    return Path(__file__).resolve().parents[3] / "router" / "policy.yaml"


def test_hermes_aux_has_no_response_cache_ttl_in_production_policy() -> None:
    """CR-3-2-CR-8 / Epic 3 retro action #10 — guard the latent double-wrap.

    If a future `policy.yaml` edit sets `hermes_aux.response_cache_ttl_seconds`
    to a non-zero value, the Router will start caching Hermes-aux pass-through
    responses on top of Hermes's own caching layer. The two TTLs interact
    unpredictably and downstream consumers parse the doubly-wrapped JSON wrong.

    The fix when this test fails is NOT "raise the threshold" — it's "remove
    the response_cache_ttl_seconds line from hermes_aux in policy.yaml" OR fix
    the double-wrap inside `mailbot_api/router/response_cache.py` so caching
    `hermes_aux` becomes safe (the fix is open; see Epic 3 retro action #10).
    """
    policy_path = _production_policy_path()
    assert policy_path.exists(), (
        f"Production policy.yaml not found at {policy_path} — "
        "test resolves the path relative to this file's location; check the layout."
    )
    policy = load_policy(policy_path)
    assert "hermes_aux" in policy.tasks, (
        "hermes_aux task entry is missing from policy.yaml — Story 2-10 added "
        "it specifically so policy.tasks['hermes_aux'] resolves. Restore it "
        "before relying on this guard."
    )
    entry = policy.tasks["hermes_aux"]
    assert entry.response_cache_ttl_seconds == 0, (
        f"hermes_aux has response_cache_ttl_seconds={entry.response_cache_ttl_seconds}; "
        "must be 0 to avoid the latent double-wrap bug (Story 3-2 CR-8). "
        "See Epic 3 retro action #10 + the module docstring for the fix scope."
    )
