"""Unit tests for Story 9-1: policy.user-overrides.yaml shallow-leaf merge.

Covers the seven AC-4 cases (empty, single-field, full-task, unknown-task,
malformed, extra-forbid, null-as-absent) plus AC-6 version-suffix
computation + AC-2 malformed-non-fatal behavior + AC-1 unknown-task
warning emit.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mailbot_api.router.policy import (
    PolicyEntry,
    PolicyTable,
    PolicyValidationError,
    UserOverridesEntry,
    UserOverridesTable,
    _compute_merged_version,
    _compute_overrides_hash,
    _merge_user_overrides,
    load_policy,
    load_policy_with_status,
)

_BASELINE_YAML = """\
version: "baseline-v1"

tasks:
  coarse_class:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  draft_reply:
    model: "claude-haiku-4-5-20251001"
    prompt_version: "v3"
    escalate: false
    max_tokens_out: 1500
    lane: "interactive"
    sensitivity: "any"
"""


def _write_baseline(tmp_path: Path) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(_BASELINE_YAML, encoding="utf-8")
    return p


def _write_overrides(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "policy.user-overrides.yaml"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# AC-4 case 1: Empty overrides file produces baseline unchanged (modulo version
# suffix per AC-6).
# ---------------------------------------------------------------------------


def test_empty_overrides_file_returns_baseline_no_suffix(tmp_path: Path) -> None:
    """CR-F3 (Story 9-1, sonnet-4-6): `tasks: {}` (file exists but applies
    zero fields) is operationally indistinguishable from absent for the
    cohort_key surface. Per AC-6 "empty or absent → no suffix", the
    version field carries NO +overrides: suffix.
    """
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(tmp_path, "tasks: {}\n")
    table = load_policy(baseline_path)
    # Zero applied fields → no suffix.
    assert table.version == "baseline-v1"
    assert "+overrides:" not in table.version
    # Tasks identical to baseline.
    assert table.tasks["coarse_class"].model == "qwen2.5:3b-instruct-q4_K_M"
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"


def test_truly_empty_overrides_file_returns_baseline_no_suffix(tmp_path: Path) -> None:
    """A literally-empty file (zero bytes, yaml.safe_load → None) is treated
    as absent per the implementation. No +overrides: suffix.
    """
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(tmp_path, "")
    table = load_policy(baseline_path)
    assert table.version == "baseline-v1"
    assert "+overrides:" not in table.version


# ---------------------------------------------------------------------------
# AC-4 case 2: Single-field override on one task — only that field changes.
# ---------------------------------------------------------------------------


def test_single_field_override_preserves_other_fields(tmp_path: Path) -> None:
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(
        tmp_path,
        """\
tasks:
  draft_reply:
    model: "claude-opus-4-7"
""",
    )
    table = load_policy(baseline_path)
    assert table.tasks["draft_reply"].model == "claude-opus-4-7"
    # All other draft_reply fields untouched.
    assert table.tasks["draft_reply"].prompt_version == "v3"
    assert table.tasks["draft_reply"].max_tokens_out == 1500
    assert table.tasks["draft_reply"].lane == "interactive"
    # Other tasks untouched.
    assert table.tasks["coarse_class"].model == "qwen2.5:3b-instruct-q4_K_M"
    # Version carries the override-suffix.
    assert table.version.startswith("baseline-v1+overrides:")


# ---------------------------------------------------------------------------
# AC-4 case 3: Full-task override — every field replaced.
# ---------------------------------------------------------------------------


def test_full_task_override_replaces_all_specified_fields(tmp_path: Path) -> None:
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(
        tmp_path,
        """\
tasks:
  coarse_class:
    model: "claude-haiku-4-5-20251001"
    prompt_version: "v9"
    escalate: true
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "normal"
""",
    )
    table = load_policy(baseline_path)
    cc = table.tasks["coarse_class"]
    assert cc.model == "claude-haiku-4-5-20251001"
    assert cc.prompt_version == "v9"
    assert cc.escalate is True
    assert cc.max_tokens_out == 512
    assert cc.lane == "interactive"
    assert cc.sensitivity == "normal"
    # Other task untouched.
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"
    assert table.tasks["draft_reply"].prompt_version == "v3"


# ---------------------------------------------------------------------------
# AC-4 case 4: Unknown-task override → WARNING + discard.
# ---------------------------------------------------------------------------


def test_unknown_task_override_logs_warning_and_discards(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(
        tmp_path,
        """\
tasks:
  this_task_does_not_exist:
    model: "claude-opus-4-7"
""",
    )
    caplog.set_level(logging.WARNING, logger="mailbot_api.router.policy")
    table = load_policy(baseline_path)
    # Unknown task absent from merged result.
    assert "this_task_does_not_exist" not in table.tasks
    # Baseline tasks present + unchanged.
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"
    # CR-F3: unknown-task-only file applies zero fields → no suffix.
    assert table.version == "baseline-v1"
    # Warning event emitted.
    unknown_records = [
        r for r in caplog.records
        if getattr(r, "event", None) == "policy.user-overrides.unknown_task"
    ]
    assert len(unknown_records) == 1
    assert getattr(unknown_records[0], "task_key", None) == "this_task_does_not_exist"


# ---------------------------------------------------------------------------
# AC-4 case 5 + AC-2: Malformed override → ERROR + return baseline (no raise).
# ---------------------------------------------------------------------------


def test_malformed_overrides_yaml_returns_baseline(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(tmp_path, "::: not yaml :::\n- random\n  : nope")
    caplog.set_level(logging.ERROR, logger="mailbot_api.router.policy")
    table = load_policy(baseline_path)
    # Baseline returned despite malformed override.
    assert table.version == "baseline-v1"
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"
    parse_failed = [
        r for r in caplog.records
        if getattr(r, "event", None) == "policy.user-overrides.parse_failed"
    ]
    assert len(parse_failed) == 1


def test_malformed_overrides_top_level_non_mapping_returns_baseline(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(tmp_path, "- not a mapping\n- but a list\n")
    caplog.set_level(logging.ERROR, logger="mailbot_api.router.policy")
    table = load_policy(baseline_path)
    assert table.version == "baseline-v1"
    parse_failed = [
        r for r in caplog.records
        if getattr(r, "event", None) == "policy.user-overrides.parse_failed"
    ]
    assert len(parse_failed) == 1


def test_overrides_wrong_field_type_returns_baseline(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An override that specifies the wrong type (e.g., model: 42) fails
    Pydantic validation → ERROR + baseline returned.
    """
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(
        tmp_path,
        """\
tasks:
  draft_reply:
    model: 42
""",
    )
    caplog.set_level(logging.ERROR, logger="mailbot_api.router.policy")
    table = load_policy(baseline_path)
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"
    parse_failed = [
        r for r in caplog.records
        if getattr(r, "event", None) == "policy.user-overrides.parse_failed"
    ]
    assert len(parse_failed) == 1


# ---------------------------------------------------------------------------
# AC-4 case 6: extra="forbid" — unknown field in override raises (returns
# baseline per AC-2 non-fatal contract).
# ---------------------------------------------------------------------------


def test_unknown_field_in_override_returns_baseline(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    baseline_path = _write_baseline(tmp_path)
    _write_overrides(
        tmp_path,
        """\
tasks:
  draft_reply:
    modle: "claude-opus-4-7"
""",
    )
    caplog.set_level(logging.ERROR, logger="mailbot_api.router.policy")
    table = load_policy(baseline_path)
    # Baseline preserved.
    assert table.tasks["draft_reply"].model == "claude-haiku-4-5-20251001"
    parse_failed = [
        r for r in caplog.records
        if getattr(r, "event", None) == "policy.user-overrides.parse_failed"
    ]
    assert len(parse_failed) == 1


# ---------------------------------------------------------------------------
# AC-4 case 7: explicit null in override = treated as "not specified".
# ---------------------------------------------------------------------------


def test_null_in_override_preserves_baseline_field() -> None:
    """Pydantic's UserOverridesEntry treats `model: null` as None → not in
    model_dump(exclude_none=True). Direct Python-level test of the merge
    function (not the loader) so we can construct the override explicitly.
    """
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(tasks={"draft_reply": UserOverridesEntry(model=None)})
    merged_tasks, applied_count, _overrides_applied = _merge_user_overrides(baseline, overrides)
    # model stays baseline value despite explicit-None override.
    assert merged_tasks["draft_reply"].model == "claude-haiku-4-5-20251001"
    # CR-F6: None override = zero applied fields.
    assert applied_count == 0


# ---------------------------------------------------------------------------
# AC-6: Version-suffix derivation.
# ---------------------------------------------------------------------------


def test_compute_merged_version_no_overrides() -> None:
    assert _compute_merged_version("v1", None) == "v1"


def test_compute_merged_version_with_overrides_appends_suffix() -> None:
    result = _compute_merged_version("v1", "tasks:\n  draft_reply:\n    model: opus\n")
    assert result.startswith("v1+overrides:")
    # Suffix is exactly 8 hex chars.
    suffix = result.split("+overrides:")[1]
    assert len(suffix) == 8
    assert all(c in "0123456789abcdef" for c in suffix)


def test_overrides_hash_determinism() -> None:
    """Same content → same hash."""
    text = "tasks:\n  draft_reply:\n    model: opus\n"
    assert _compute_overrides_hash(text) == _compute_overrides_hash(text)


def test_overrides_hash_whitespace_change_differs() -> None:
    """Whitespace edits DO change the hash (operationally desired per AC-6)."""
    a = "tasks:\n  draft_reply:\n    model: opus\n"
    b = "tasks:\n  draft_reply:\n    model: opus\n\n"  # trailing newline
    assert _compute_overrides_hash(a) != _compute_overrides_hash(b)


# ---------------------------------------------------------------------------
# Backward-compat: load_policy(path) without overrides_path AND no sibling
# overrides file returns baseline unchanged (no +overrides: suffix).
# ---------------------------------------------------------------------------


def test_load_policy_no_overrides_arg_no_sibling_file_returns_baseline(
    tmp_path: Path,
) -> None:
    baseline_path = _write_baseline(tmp_path)
    # No overrides file exists in tmp_path.
    table = load_policy(baseline_path)
    assert table.version == "baseline-v1"
    assert "+overrides:" not in table.version


def test_load_policy_explicit_overrides_path_takes_precedence(
    tmp_path: Path,
) -> None:
    """An explicit overrides_path argument is honored even if no sibling
    default exists.
    """
    baseline_path = _write_baseline(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "custom.yaml"
    elsewhere.parent.mkdir()
    elsewhere.write_text(
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
        encoding="utf-8",
    )
    table = load_policy(baseline_path, overrides_path=elsewhere)
    assert table.tasks["draft_reply"].model == "claude-opus-4-7"
    assert "+overrides:" in table.version


def test_load_policy_explicit_overrides_path_absent_returns_baseline(
    tmp_path: Path,
) -> None:
    """An explicit overrides_path pointing to a non-existent file is
    benign — no error, baseline returned.
    """
    baseline_path = _write_baseline(tmp_path)
    nonexistent = tmp_path / "elsewhere" / "missing.yaml"
    table = load_policy(baseline_path, overrides_path=nonexistent)
    assert table.version == "baseline-v1"
    assert "+overrides:" not in table.version


# ---------------------------------------------------------------------------
# Baseline failures still raise (Story 9-1 only relaxes overrides failures).
# ---------------------------------------------------------------------------


def test_malformed_baseline_still_raises(tmp_path: Path) -> None:
    """Story 9-1 does NOT relax baseline-failure handling — baseline
    failures still raise PolicyValidationError.
    """
    p = tmp_path / "policy.yaml"
    p.write_text("::: not yaml :::", encoding="utf-8")
    with pytest.raises(PolicyValidationError):
        load_policy(p)


def test_baseline_file_not_found_still_raises(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-file.yaml"
    with pytest.raises(PolicyValidationError):
        load_policy(missing)


# ---------------------------------------------------------------------------
# CR-F1 (Story 9-1, sonnet-4-6): load_policy_with_status returns
# discriminated status for the reload-loop swap-or-no-swap decision.
# ---------------------------------------------------------------------------


def test_load_policy_with_status_absent(tmp_path: Path) -> None:
    """No override file → status='absent'."""
    from mailbot_api.router.policy import load_policy_with_status

    baseline_path = _write_baseline(tmp_path)
    table, status = load_policy_with_status(baseline_path)
    assert status == "absent"
    assert table.version == "baseline-v1"


def test_load_policy_with_status_empty(tmp_path: Path) -> None:
    """tasks: {} (zero applied fields) → status='empty'."""
    from mailbot_api.router.policy import load_policy_with_status

    baseline_path = _write_baseline(tmp_path)
    _write_overrides(tmp_path, "tasks: {}\n")
    table, status = load_policy_with_status(baseline_path)
    assert status == "empty"
    assert table.version == "baseline-v1"


def test_load_policy_with_status_applied(tmp_path: Path) -> None:
    """Single-field override → status='applied'."""
    from mailbot_api.router.policy import load_policy_with_status

    baseline_path = _write_baseline(tmp_path)
    _write_overrides(
        tmp_path,
        "tasks:\n  draft_reply:\n    model: claude-opus-4-7\n",
    )
    table, status = load_policy_with_status(baseline_path)
    assert status == "applied"
    assert table.version.startswith("baseline-v1+overrides:")
    assert table.tasks["draft_reply"].model == "claude-opus-4-7"


def test_load_policy_with_status_parse_failed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed override YAML → status='parse_failed' + baseline returned."""
    from mailbot_api.router.policy import load_policy_with_status

    baseline_path = _write_baseline(tmp_path)
    _write_overrides(tmp_path, "::: not yaml :::\n")
    caplog.set_level(logging.ERROR, logger="mailbot_api.router.policy")
    table, status = load_policy_with_status(baseline_path)
    assert status == "parse_failed"
    assert table.version == "baseline-v1"


# ---------------------------------------------------------------------------
# CR-F6 (Story 9-1, sonnet-4-6): _merge_user_overrides returns
# (dict[str, PolicyEntry], applied_field_count) — not a PolicyTable.
# ---------------------------------------------------------------------------


def test_merge_user_overrides_returns_dict_and_count() -> None:
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={"draft_reply": UserOverridesEntry(model="claude-opus-4-7")}
    )
    merged_tasks, applied_count, _overrides_applied = _merge_user_overrides(baseline, overrides)
    assert isinstance(merged_tasks, dict)
    assert merged_tasks["draft_reply"].model == "claude-opus-4-7"
    assert applied_count == 1


def test_merge_user_overrides_applied_count_zero_for_unknown_task() -> None:
    """Unknown task → discarded → applied_count == 0."""
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={"unknown_task": UserOverridesEntry(model="claude-opus-4-7")}
    )
    merged_tasks, applied_count, _overrides_applied = _merge_user_overrides(baseline, overrides)
    assert applied_count == 0
    assert "unknown_task" not in merged_tasks
    assert merged_tasks["draft_reply"].model == "claude-haiku-4-5-20251001"


def test_merge_user_overrides_counts_multiple_fields() -> None:
    """Multi-field override → applied_count == number of fields."""
    baseline = PolicyTable(
        tasks={
            "coarse_class": PolicyEntry(
                model="qwen2.5:3b-instruct-q4_K_M",
                prompt_version="v1",
                escalate=False,
                lane="batch",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={
            "coarse_class": UserOverridesEntry(
                model="claude-haiku-4-5-20251001",
                lane="interactive",
                max_tokens_out=512,
            )
        }
    )
    merged_tasks, applied_count, _overrides_applied = _merge_user_overrides(baseline, overrides)
    assert applied_count == 3


# ---------------------------------------------------------------------------
# Story 9-4 AC-2: per-task provenance tests for the new `overrides_applied`
# frozenset returned by _merge_user_overrides (3rd tuple element) and stored
# on PolicyTable for the router to consume at audit-emit time.
# ---------------------------------------------------------------------------


def test_overrides_applied_single_task_present() -> None:
    """Story 9-4: a task with an applied field appears in the provenance set."""
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            ),
            "coarse_class": PolicyEntry(
                model="qwen2.5:3b-instruct-q4_K_M",
                prompt_version="v1",
                escalate=False,
                lane="batch",
                sensitivity="any",
            ),
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={"draft_reply": UserOverridesEntry(model="claude-opus-4-7")}
    )
    _merged, _count, overrides_applied = _merge_user_overrides(baseline, overrides)
    assert isinstance(overrides_applied, frozenset)
    assert overrides_applied == frozenset({"draft_reply"})
    assert "coarse_class" not in overrides_applied  # AC-3 isolation


def test_overrides_applied_unknown_task_excluded() -> None:
    """Story 9-4: an unknown-task override is NOT in the provenance set
    (mirrors the applied_count == 0 contract from Story 9-1)."""
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={"phantom_task": UserOverridesEntry(model="claude-opus-4-7")}
    )
    _merged, _count, overrides_applied = _merge_user_overrides(baseline, overrides)
    assert overrides_applied == frozenset()


def test_overrides_applied_all_none_excluded() -> None:
    """Story 9-4: an all-None override entry yields zero applied fields AND
    is NOT in the provenance set — consistent with applied_count semantics."""
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={"draft_reply": UserOverridesEntry(model=None)}
    )
    _merged, _count, overrides_applied = _merge_user_overrides(baseline, overrides)
    assert overrides_applied == frozenset()


def test_overrides_applied_multi_task() -> None:
    """Story 9-4: multiple tasks with applied fields all appear."""
    baseline = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            ),
            "coarse_class": PolicyEntry(
                model="qwen2.5:3b-instruct-q4_K_M",
                prompt_version="v1",
                escalate=False,
                lane="batch",
                sensitivity="any",
            ),
            "summary_short": PolicyEntry(
                model="qwen2.5:3b-instruct-q4_K_M",
                prompt_version="v1",
                escalate=False,
                lane="batch",
                sensitivity="any",
            ),
        },
        version="b-v1",
    )
    overrides = UserOverridesTable(
        tasks={
            "draft_reply": UserOverridesEntry(model="claude-opus-4-7"),
            "coarse_class": UserOverridesEntry(model="claude-haiku-4-5-20251001"),
        }
    )
    _merged, _count, overrides_applied = _merge_user_overrides(baseline, overrides)
    assert overrides_applied == frozenset({"draft_reply", "coarse_class"})
    assert "summary_short" not in overrides_applied


def test_policy_table_overrides_applied_default_empty() -> None:
    """Story 9-4: PolicyTable without an explicit overrides_applied gets
    frozenset() — backward-compat for Story 9-1's PolicyTable callers."""
    table = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-haiku-4-5-20251001",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1",
    )
    assert table.overrides_applied == frozenset()


def test_policy_table_overrides_applied_explicit() -> None:
    """Story 9-4: PolicyTable with explicit overrides_applied stores the set."""
    table = PolicyTable(
        tasks={
            "draft_reply": PolicyEntry(
                model="claude-opus-4-7",
                prompt_version="v3",
                escalate=False,
                lane="interactive",
                sensitivity="any",
            )
        },
        version="b-v1+overrides:abc12345",
        overrides_applied=frozenset({"draft_reply"}),
    )
    assert table.overrides_applied == frozenset({"draft_reply"})


def test_load_policy_with_status_applied_carries_provenance(tmp_path: Path) -> None:
    """Story 9-4: load_policy_with_status returns a PolicyTable whose
    overrides_applied frozenset reflects the merged-in tasks."""
    baseline_path = tmp_path / "policy.yaml"
    baseline_path.write_text(
        """tasks:
  draft_reply:
    model: claude-haiku-4-5-20251001
    prompt_version: v3
    escalate: false
    lane: interactive
    sensitivity: any
  coarse_class:
    model: qwen2.5:3b-instruct-q4_K_M
    prompt_version: v1
    escalate: false
    lane: batch
    sensitivity: any
version: b-v1
""",
        encoding="utf-8",
    )
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    overrides_path.write_text(
        """tasks:
  draft_reply:
    model: claude-opus-4-7
""",
        encoding="utf-8",
    )
    table, status = load_policy_with_status(baseline_path, overrides_path=overrides_path)
    assert status == "applied"
    assert table.overrides_applied == frozenset({"draft_reply"})
    assert table.tasks["draft_reply"].model == "claude-opus-4-7"
    assert table.tasks["coarse_class"].model == "qwen2.5:3b-instruct-q4_K_M"


def test_load_policy_with_status_baseline_only_empty_provenance(tmp_path: Path) -> None:
    """Story 9-4: when no overrides file is present, the returned PolicyTable
    has overrides_applied=frozenset()."""
    baseline_path = tmp_path / "policy.yaml"
    baseline_path.write_text(
        """tasks:
  draft_reply:
    model: claude-haiku-4-5-20251001
    prompt_version: v3
    escalate: false
    lane: interactive
    sensitivity: any
version: b-v1
""",
        encoding="utf-8",
    )
    table, status = load_policy_with_status(baseline_path)
    assert status == "absent"
    assert table.overrides_applied == frozenset()
