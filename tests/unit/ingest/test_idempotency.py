"""Unit tests for `mailbot_api/ingest/idempotency.py`.

Story 3-1 AC-5: nine scenarios covering determinism, per-field sensitivity,
cross-interpreter stability, Unicode handling, empty inputs, and hex format.
"""

from __future__ import annotations

import re

from mailbot_api.ingest.idempotency import compute_idempotency_key

# Golden value: hardcoded SHA-256 hex for a fixed quadruple. The pre-computed
# value below was generated via:
#   python -c "import hashlib; print(hashlib.sha256(
#       b'hello world|v1|qwen2.5:3b-instruct-q4_K_M|coarse_class'
#   ).hexdigest())"
# If this assertion ever fails, the formula has changed and downstream
# idempotency rows become invalid — STOP and reconcile with the data layer.
_GOLDEN_BODY = "hello world"
_GOLDEN_PROMPT_V = "v1"
_GOLDEN_MODEL = "qwen2.5:3b-instruct-q4_K_M"
_GOLDEN_TASK = "coarse_class"
_GOLDEN_HEX = "edf960560ef1044c7d4fe2bc94aca9de0cc99071f637a1366e284292c464364d"


def test_golden_value_locks_formula() -> None:
    """AC-5 §6: cross-interpreter stability — the golden hex value is locked.

    Any change to the formula (delimiters, order, encoding) invalidates this
    assertion. That is intentional: an accidental refactor that shifts the key
    formula would silently break every cached derivation row. The test catches
    it before the row goes out of sync.
    """
    assert (
        compute_idempotency_key(
            body=_GOLDEN_BODY,
            prompt_version=_GOLDEN_PROMPT_V,
            model=_GOLDEN_MODEL,
            task_type=_GOLDEN_TASK,
        )
        == _GOLDEN_HEX
    )


def test_deterministic_for_identical_inputs() -> None:
    """AC-5 §1: identical inputs always produce identical keys."""
    args = ("body text", "v1", "qwen", "task")
    assert compute_idempotency_key(*args) == compute_idempotency_key(*args)


def test_body_sensitivity() -> None:
    """AC-5 §2: changing the body changes the key."""
    k1 = compute_idempotency_key("body A", "v1", "qwen", "task")
    k2 = compute_idempotency_key("body B", "v1", "qwen", "task")
    assert k1 != k2


def test_body_single_char_change_changes_key() -> None:
    """AC-5 §2 stricter: a one-character body diff changes the key."""
    k1 = compute_idempotency_key("hello world", "v1", "qwen", "task")
    k2 = compute_idempotency_key("hello worle", "v1", "qwen", "task")
    assert k1 != k2


def test_prompt_version_sensitivity() -> None:
    """AC-5 §3: changing the prompt_version changes the key."""
    k1 = compute_idempotency_key("body", "v1", "qwen", "task")
    k2 = compute_idempotency_key("body", "v2", "qwen", "task")
    assert k1 != k2


def test_model_sensitivity() -> None:
    """AC-5 §4: changing the model changes the key."""
    k_qwen = compute_idempotency_key("body", "v1", "qwen2.5:3b-instruct-q4_K_M", "task")
    k_haiku = compute_idempotency_key("body", "v1", "claude-haiku-4-5-20251001", "task")
    assert k_qwen != k_haiku


def test_task_type_sensitivity() -> None:
    """AC-5 §5: changing the task_type changes the key."""
    k1 = compute_idempotency_key("body", "v1", "qwen", "coarse_class")
    k2 = compute_idempotency_key("body", "v1", "qwen", "sensitivity_class")
    assert k1 != k2


def test_unicode_body_is_handled() -> None:
    """AC-5 §7: a non-ASCII body hashes successfully and deterministically.

    Verifies the explicit `.encode("utf-8")` in the helper — without it,
    a body with non-ASCII chars could raise UnicodeEncodeError on platforms
    whose default sys.getdefaultencoding() differs.
    """
    body = "café 🚀 résumé"
    k1 = compute_idempotency_key(body, "v1", "qwen", "task")
    k2 = compute_idempotency_key(body, "v1", "qwen", "task")
    assert k1 == k2
    assert re.fullmatch(r"[0-9a-f]{64}", k1) is not None


def test_empty_inputs_are_permissive() -> None:
    """AC-5 §8: empty argument strings are accepted and yield a stable hex.

    The helper is permissive — call-site validation is the caller's job.
    Empty quadruple still produces a 64-char hex deterministically.
    """
    k1 = compute_idempotency_key("", "", "", "")
    k2 = compute_idempotency_key("", "", "", "")
    assert k1 == k2
    assert re.fullmatch(r"[0-9a-f]{64}", k1) is not None


def test_pipe_in_body_produces_collision_with_different_field_split() -> None:
    """CR-4: document the accepted body-pipe collision behavior.

    A body containing `|` admits a hash collision against a different
    `(body, prompt_version)` split — both quadruples feed the SAME string
    `"x|y|z|a|t"` to sha256. The docstring documents this as an accepted
    trade-off (body content is not adversarial; prompt_version/model/task_type
    are snake_case identifiers that never contain `|`).

    This test EXISTS to document the behavior — if this assertion ever
    starts failing, someone has changed the formula (e.g., added a body-length
    prefix, switched to a different delimiter) and the docstring claims +
    accepted trade-off rationale need to be re-validated.
    """
    k1 = compute_idempotency_key("x|y", "z", "a", "t")
    k2 = compute_idempotency_key("x", "y|z", "a", "t")
    assert k1 == k2, (
        "Body-pipe collision behavior changed — verify the docstring's "
        "'accepted trade-off' framing still holds and update if not."
    )


def test_hex_format() -> None:
    """AC-5 §9: the return value is exactly 64 lowercase hex chars."""
    k = compute_idempotency_key("the quick brown fox", "v1", "qwen", "summary_short")
    assert re.fullmatch(r"[0-9a-f]{64}", k) is not None
