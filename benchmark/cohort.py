"""Story 9.6: cohort_key computation per Adam-decision 2026-06-27 (A5 default).

A cohort_key is a SHA-256[:16] hex digest over the pipe-joined 4-tuple
``(prompt_version, scorer_model, anchors_version, router_policy_version)``.

Pareto plots + DEMOTE/PROMOTE verdicts in Story 9-9 ONLY combine
``benchmark_runs`` rows within the same cohort_key. Cross-cohort comparison
is allowed but flagged in the report's "cross-cohort drift comparison"
section so prompt/scorer/anchor/policy evolution can't silently bias
verdicts.

Pure leaf — no I/O, no config reads, no DB.
"""

from __future__ import annotations

import hashlib

_DELIMITER: str = "|"


def compute_cohort_key(
    prompt_version: str,
    scorer_model: str,
    anchors_version: str,
    router_policy_version: str,
) -> str:
    """Compute a stable cohort_key for the 4-tuple.

    The components are joined by ``|`` and hashed with SHA-256; the first
    16 hex chars are returned. This is enough collision resistance for the
    forecast cohort cardinality (~10s across an epoch) while staying short
    enough to read in a terminal row.

    Empty-string components raise ``ValueError`` (a silent empty string
    would create cohorts that look real but aren't tied to any actual
    pipeline state). The ``|`` delimiter character is also rejected in any
    component to prevent ambiguity (``("a|b", "c")`` and ``("a", "b|c")``
    would otherwise produce the same join).

    Args:
        prompt_version: The dispatched prompt module version (e.g. ``"v3"``).
        scorer_model: The exact Anthropic model id the Story 9-7 scorer
            will use (e.g. ``"claude-opus-4-7-20251220"``); frozen at
            run-start.
        anchors_version: Value from ``evals/anchors/VERSION``; read at
            run-start.
        router_policy_version: ``PolicyTable.version`` value at run-start
            (includes the ``+overrides:<sha256[:8]>`` suffix per Story 9-1
            when user overrides are merged).

    Returns:
        A 16-char lowercase hex SHA-256[:16] digest.

    Raises:
        ValueError: if any component is empty OR contains the pipe
            delimiter character.
    """
    components = (
        prompt_version,
        scorer_model,
        anchors_version,
        router_policy_version,
    )
    names = (
        "prompt_version",
        "scorer_model",
        "anchors_version",
        "router_policy_version",
    )
    for value, name in zip(components, names, strict=True):
        if not value:
            raise ValueError(
                f"cohort_key component {name!r} must be non-empty (got empty string)"
            )
        if _DELIMITER in value:
            raise ValueError(
                f"cohort_key component {name!r} must not contain the {_DELIMITER!r} "
                f"delimiter (got {value!r})"
            )
    joined = _DELIMITER.join(components)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


__all__ = ["compute_cohort_key"]
