"""Idempotency-key helper for the ingest pipeline.

Per FR-2.2 and Rule K (architecture.md "Idempotency & caching"), every per-email
derived-field write keys its idempotency on the quadruple
`(body, prompt_version, model, task_type)`. The key is `sha256(...)` hex digest.

This module is the SOLE definer of the formula — `scripts/check_boundaries.py`
enforces a writer-monopoly boundary (mirroring the Story 2-1 pattern for the
router-calls audit-row writer in `mailbot_api/observability/audit.py`). Any
other module that computes a key by constructing an f-string containing
`prompt_version`, `model`, AND `task_type` fed into `hashlib.sha256(...)`
fails the boundary check.

Story 3-1 ships only this helper. Story 3-5's `pipeline.py` is the first
consumer.

References:
  - FR-2.2: PRD §"F2 Ingest Pipeline" (idempotency keyed on sha256(body)+prompt_v+model+task)
  - Rule K: architecture.md §"Idempotency & caching"
  - Story 3-1: _bmad-output/implementation-artifacts/3-1-derived-field-schema-...md
"""

from __future__ import annotations

import hashlib

__all__ = ["compute_idempotency_key"]


def compute_idempotency_key(
    body: str,
    prompt_version: str,
    model: str,
    task_type: str,
) -> str:
    """Compute the FR-2.2 idempotency key for one derived-field write.

    The key is `sha256(f"{body}|{prompt_version}|{model}|{task_type}".encode("utf-8")).hexdigest()`.

    Pipe-delimiters separate the four inputs. This guards against collisions
    between boundary-adjacent values for **trusted-shape inputs only** —
    `prompt_version`, `model`, and `task_type` are snake_case identifiers
    that never contain `|`. **Body pipes are NOT guarded** (see Notes below):
    a body containing `|` admits a hash collision against a different
    `(body, prompt_version)` split. This is an accepted trade-off — email
    bodies are not adversarially controlled in this system and are
    sufficiently long+unique that the collision risk is purely theoretical.
    Inputs are UTF-8 encoded before hashing — this means Unicode bodies hash
    deterministically across platforms regardless of locale or default
    encoding.

    Args:
        body: the raw email body (or other deriveable content). May contain
            arbitrary UTF-8 including pipes — see "body-pipe collision" in
            Notes for the accepted trade-off.
        prompt_version: the prompt module version string, e.g. "v1". MUST
            NOT contain `|` (snake_case identifier — caller-enforced).
        model: the resolved model id at dispatch time, e.g.
            "qwen2.5:3b-instruct-q4_K_M" or "claude-haiku-4-5-20251001".
            MUST NOT contain `|`.
        task_type: the task identifier from `policy.yaml`, e.g.
            "coarse_class" / "sensitivity_class" / "summary_short". MUST NOT
            contain `|`.

    Returns:
        A 64-character lowercase hex digest.

    Notes:
        - **Body-pipe collision (accepted)**: `compute_idempotency_key("x|y", "z", "a", "t")`
          and `compute_idempotency_key("x", "y|z", "a", "t")` produce the SAME
          key because both feed `"x|y|z|a|t"` to sha256. This is exercised by
          `test_pipe_in_body_produces_collision_with_different_field_split`
          and documents the design choice — body content is not adversarial,
          and `prompt_version`/`model`/`task_type` never contain pipes in
          practice.
        - The helper is permissive: empty strings are accepted and produce a
          stable hex. Validation at call sites is the caller's responsibility.
        - The helper does NOT depend on `hash()` (which is randomized per
          interpreter unless PYTHONHASHSEED is fixed). Output is stable across
          processes and Python versions.
    """
    return hashlib.sha256(f"{body}|{prompt_version}|{model}|{task_type}".encode("utf-8")).hexdigest()
