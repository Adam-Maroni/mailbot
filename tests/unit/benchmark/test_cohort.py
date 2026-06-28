"""Story 9.6 AC-3: unit tests for ``benchmark.cohort.compute_cohort_key``.

Covers:
* determinism — same tuple → same key
* sensitivity to each component — changing any one component changes the key
* pipe-delimiter rejection (collision resistance)
* empty-string rejection
"""

from __future__ import annotations

import hashlib

import pytest

from benchmark.cohort import compute_cohort_key


def test_compute_cohort_key_deterministic() -> None:
    """Same 4-tuple → same 16-char hex digest, every time."""
    k1 = compute_cohort_key("v1", "claude-opus-4-7-20251220", "v1", "policy-v0-2026-06-01")
    k2 = compute_cohort_key("v1", "claude-opus-4-7-20251220", "v1", "policy-v0-2026-06-01")
    assert k1 == k2
    assert len(k1) == 16
    # All-lowercase hex.
    assert all(c in "0123456789abcdef" for c in k1)


def test_compute_cohort_key_matches_explicit_sha256() -> None:
    """Sanity-check the implementation against the expected SHA-256[:16] of the pipe-join."""
    expected = hashlib.sha256(
        b"v1|claude-opus-4-7-20251220|v1|policy-v0-2026-06-01"
    ).hexdigest()[:16]
    actual = compute_cohort_key(
        "v1", "claude-opus-4-7-20251220", "v1", "policy-v0-2026-06-01"
    )
    assert actual == expected


def test_compute_cohort_key_sensitive_to_prompt_version() -> None:
    k1 = compute_cohort_key("v1", "scorer", "anchors-v1", "policy-v0")
    k2 = compute_cohort_key("v2", "scorer", "anchors-v1", "policy-v0")
    assert k1 != k2


def test_compute_cohort_key_sensitive_to_scorer_model() -> None:
    k1 = compute_cohort_key("v1", "scorer-a", "anchors-v1", "policy-v0")
    k2 = compute_cohort_key("v1", "scorer-b", "anchors-v1", "policy-v0")
    assert k1 != k2


def test_compute_cohort_key_sensitive_to_anchors_version() -> None:
    k1 = compute_cohort_key("v1", "scorer", "anchors-v1", "policy-v0")
    k2 = compute_cohort_key("v1", "scorer", "anchors-v2", "policy-v0")
    assert k1 != k2


def test_compute_cohort_key_sensitive_to_router_policy_version() -> None:
    k1 = compute_cohort_key("v1", "scorer", "anchors-v1", "policy-v0")
    k2 = compute_cohort_key("v1", "scorer", "anchors-v1", "policy-v1")
    assert k1 != k2


def test_compute_cohort_key_rejects_pipe_delimiter_in_prompt_version() -> None:
    with pytest.raises(ValueError, match="prompt_version"):
        compute_cohort_key("v1|injected", "scorer", "anchors-v1", "policy-v0")


def test_compute_cohort_key_rejects_pipe_delimiter_in_scorer_model() -> None:
    with pytest.raises(ValueError, match="scorer_model"):
        compute_cohort_key("v1", "scorer|injected", "anchors-v1", "policy-v0")


def test_compute_cohort_key_rejects_pipe_delimiter_in_anchors_version() -> None:
    with pytest.raises(ValueError, match="anchors_version"):
        compute_cohort_key("v1", "scorer", "anchors|injected", "policy-v0")


def test_compute_cohort_key_rejects_pipe_delimiter_in_router_policy_version() -> None:
    with pytest.raises(ValueError, match="router_policy_version"):
        compute_cohort_key("v1", "scorer", "anchors-v1", "policy|injected")


def test_compute_cohort_key_rejects_empty_components() -> None:
    """Empty component → ValueError. Each position tested independently."""
    with pytest.raises(ValueError, match="prompt_version.*non-empty"):
        compute_cohort_key("", "scorer", "anchors-v1", "policy-v0")
    with pytest.raises(ValueError, match="scorer_model.*non-empty"):
        compute_cohort_key("v1", "", "anchors-v1", "policy-v0")
    with pytest.raises(ValueError, match="anchors_version.*non-empty"):
        compute_cohort_key("v1", "scorer", "", "policy-v0")
    with pytest.raises(ValueError, match="router_policy_version.*non-empty"):
        compute_cohort_key("v1", "scorer", "anchors-v1", "")


def test_compute_cohort_key_pipe_collision_resistant() -> None:
    """Pipe-delimiter collision proof: ('a|b', 'c') and ('a', 'b|c') would
    otherwise produce the same join 'a|b|c'. Because we reject ``|`` in
    any component, neither input is reachable; the collision class is
    eliminated by construction."""
    with pytest.raises(ValueError):
        compute_cohort_key("a|b", "c", "anchors-v1", "policy-v0")
    with pytest.raises(ValueError):
        compute_cohort_key("a", "b|c", "anchors-v1", "policy-v0")
