"""Story 9-4 AC-2 + AC-6 — `inspect_policy` verb unit tests.

Verifies the markdown-composition contract:
  - Baseline-only state: no 🔧 prefix anywhere; override_model column is "—"
    for every row; degraded/oneshot lines say "Not active" / "None".
  - One-override state: only the overridden row carries the 🔧 prefix;
    sibling rows stay un-marked.
  - Degraded-mode active: degraded line says "Active".
  - One-shot armed: one-shot line names the model + expires_at.
  - Multi-override state: task_count / override_count reflect the file.

The verb sources the policy snapshot from `snapshot_for_dispatch()`, the
baseline + override models from re-reading the YAML files via the
policy-module helpers, and the degraded + one-shot state from
`get_guard()` + `_get_active_oneshot_override()` respectively. Tests
patch the policy-dir resolver to point at a `tmp_path`-rooted layout.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.router.budget import _reset_guard_for_test, get_guard
from mailbot_api.router.oneshot import (
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
)
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.verbs.router_control import inspect_policy

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


_BASELINE_YAML = f"""\
version: "test-inspect-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state() -> Any:
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_oneshot_override_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_oneshot_override_for_test()


def _setup_policy_dir(
    tmp_path: Path,
    *,
    overrides_yaml: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Write baseline policy.yaml + (optionally) policy.user-overrides.yaml
    under tmp_path and patch `_resolve_policy_dir` to return tmp_path so
    the verb's baseline/override re-readers point at this layout."""
    (tmp_path / "policy.yaml").write_text(_BASELINE_YAML, encoding="utf-8")
    if overrides_yaml is not None:
        (tmp_path / "policy.user-overrides.yaml").write_text(
            overrides_yaml, encoding="utf-8"
        )
    if overrides_yaml is not None:
        set_policy_snapshot(
            load_policy(
                tmp_path / "policy.yaml",
                overrides_path=tmp_path / "policy.user-overrides.yaml",
            )
        )
    else:
        set_policy_snapshot(load_policy(tmp_path / "policy.yaml"))
    monkeypatch.setattr(
        "mailbot_api.verbs.router_control._resolve_policy_dir",
        lambda: tmp_path,
    )
    return tmp_path


async def test_inspect_policy_baseline_only_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-6 baseline-only: no override file, no degraded, no one-shot.
    Every row has override_model='—', no 🔧 prefix, last_changed='—';
    degraded says 'Not active'; one-shot says 'None'."""
    _setup_policy_dir(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    out = await inspect_policy(db_path="unused")
    assert out.task_count == 3
    assert out.override_count == 0
    assert "🔧" not in out.markdown
    # Every per-task row: override_model column is "—".
    # Sanity: count rows that look like task rows.
    for line in out.markdown.split("\n"):
        if line.startswith("| draft_reply") or line.startswith("| coarse_class") or line.startswith("| summary_short"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Columns: task | baseline | override | effective | lane | sensitivity | last_changed
            assert cells[2] == "—", f"baseline row has non-dash override: {line}"
    assert "Current degraded mode state: Not active" in out.markdown
    assert "Active one-shot override: None" in out.markdown


async def test_inspect_policy_one_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-6 one-override: draft_reply overridden to opus. Only that row
    has the 🔧 prefix and a non-dash override_model column."""
    overrides_yaml = f"tasks:\n  draft_reply:\n    model: {_OPUS}\n"
    _setup_policy_dir(tmp_path, overrides_yaml=overrides_yaml, monkeypatch=monkeypatch)
    out = await inspect_policy(db_path="unused")
    assert out.task_count == 3
    assert out.override_count == 1
    assert out.markdown.count("🔧") == 1
    # The 🔧 row is draft_reply, and its override_model is opus.
    draft_row = next(
        line for line in out.markdown.split("\n") if "draft_reply" in line and line.startswith("|")
    )
    cells = [c.strip() for c in draft_row.strip("|").split("|")]
    assert cells[0].startswith("🔧 draft_reply")
    assert cells[1] == _HAIKU  # baseline_model
    assert cells[2] == _OPUS  # override_model
    assert cells[3] == _OPUS  # effective_model


async def test_inspect_policy_degraded_mode_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-6 degraded: when budget guard reports degraded, the line says
    'Active'."""
    _setup_policy_dir(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    # Flip the guard's degraded flag in-memory via the public surface.
    guard = get_guard()
    monkeypatch.setattr(guard, "is_degraded", lambda: True)
    out = await inspect_policy(db_path="unused")
    assert "Current degraded mode state: Active" in out.markdown


async def test_inspect_policy_one_shot_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-6 one-shot: when a one-shot is armed, the line names the
    model + expires_at."""
    _setup_policy_dir(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    override = _set_oneshot_override(model=_OPUS, session_id="adam")
    out = await inspect_policy(db_path="unused")
    assert "Active one-shot override:" in out.markdown
    assert _OPUS in out.markdown
    assert override.expires_at in out.markdown


async def test_inspect_policy_multi_override_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-6 multi-override: 2 overrides → task_count=3, override_count=2,
    exactly two 🔧 prefixes."""
    overrides_yaml = (
        f"tasks:\n  draft_reply:\n    model: {_OPUS}\n"
        f"  coarse_class:\n    model: {_HAIKU}\n"
    )
    _setup_policy_dir(tmp_path, overrides_yaml=overrides_yaml, monkeypatch=monkeypatch)
    out = await inspect_policy(db_path="unused")
    assert out.task_count == 3
    assert out.override_count == 2
    assert out.markdown.count("🔧") == 2


async def test_inspect_policy_markdown_table_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-6 markdown sanity: the output is a well-formed markdown table
    with a header row + separator row + N task rows (N == task_count)."""
    _setup_policy_dir(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    out = await inspect_policy(db_path="unused")
    table_lines = [
        line for line in out.markdown.split("\n") if re.match(r"^\|.*\|$", line)
    ]
    # Expect: 1 header + 1 separator + 3 task rows.
    assert len(table_lines) == 1 + 1 + 3, (
        f"unexpected number of table rows: got {len(table_lines)}"
    )


async def test_inspect_policy_file_path_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-2 inspect: the InspectPolicyOut.file_path field names the
    actual overrides file path (whether or not the file exists)."""
    _setup_policy_dir(tmp_path, overrides_yaml=None, monkeypatch=monkeypatch)
    out = await inspect_policy(db_path="unused")
    assert out.file_path.endswith("policy.user-overrides.yaml")
    assert str(tmp_path) in out.file_path
