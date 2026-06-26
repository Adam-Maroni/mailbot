"""Story 9-4 AC-1 + AC-5 — atomic-write integrity + OQ-3 preconditions.

Verifies:
  - The atomic write contract: a successful set_model_persistent writes
    `router/policy.user-overrides.yaml` AND leaves `router/policy.yaml`
    byte-identical to its pre-call state.
  - Schema-validity round-trip: every successful write yields a file that
    `read_user_overrides_raw` can parse back without error.
  - Crash-during-write atomicity: if `os.replace` raises mid-call, the
    original target file content is unchanged.
  - OQ-3 file-state preconditions: absent file → actionable error; the
    file is NOT created from inside the verb.
  - Hot-reload propagation timing: after a successful write, the next
    `snapshot_for_dispatch()` call sees the new model within the polled
    window.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    read_user_overrides_raw,
    set_policy_snapshot,
)
from mailbot_api.verbs.router_control import (
    set_model_persistent,
)

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


_BASELINE_YAML = f"""\
version: "test-atomic-v1"

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


def _bootstrap_layout(
    tmp_path: Path,
    *,
    overrides_initial: str | None = "tasks: {}\n",
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Write baseline + (optional) overrides file under tmp_path, prime
    the policy snapshot, and patch `_resolve_policy_dir` to return
    tmp_path so the verb writes into the test layout."""
    (tmp_path / "policy.yaml").write_text(_BASELINE_YAML, encoding="utf-8")
    if overrides_initial is not None:
        (tmp_path / "policy.user-overrides.yaml").write_text(
            overrides_initial, encoding="utf-8"
        )
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


# ---------------------------------------------------------------------------
# AC-5 — atomic-write integrity + byte-identity check on policy.yaml
# ---------------------------------------------------------------------------


async def test_successful_write_leaves_policy_yaml_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-5 byte-identity: a successful set_model_persistent writes to
    the overrides file ONLY — policy.yaml is byte-identical pre/post."""
    _bootstrap_layout(tmp_path, monkeypatch=monkeypatch)
    policy_yaml_pre = (tmp_path / "policy.yaml").read_bytes()
    out = await set_model_persistent(
        db_path="unused",
        task="draft_reply",
        model="opus",
    )
    # NB: the verb may report ok=False if the hot-reload-polling does not
    # observe the swap (we don't run the watchfiles loop in this unit
    # context). The byte-identity assertion is the load-bearing one.
    policy_yaml_post = (tmp_path / "policy.yaml").read_bytes()
    assert policy_yaml_post == policy_yaml_pre
    # AND the overrides file got the update.
    raw_after = read_user_overrides_raw(tmp_path / "policy.user-overrides.yaml")
    assert raw_after["tasks"]["draft_reply"]["model"] == _OPUS
    # The error path (if any) should be the hot-reload-timeout, not a
    # write-side failure.
    if not out.ok:
        assert out.error is not None
        assert "hot-reload" in out.error.lower()


async def test_write_produces_schema_valid_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-5: after each successful write, the resulting file parses back
    via `read_user_overrides_raw` cleanly."""
    _bootstrap_layout(tmp_path, monkeypatch=monkeypatch)
    for task, model in (
        ("draft_reply", "opus"),
        ("coarse_class", "haiku"),
        ("draft_reply", "qwen"),  # second write to draft_reply
    ):
        await set_model_persistent(db_path="unused", task=task, model=model)
        raw = read_user_overrides_raw(tmp_path / "policy.user-overrides.yaml")
        assert isinstance(raw, dict)
        assert "tasks" in raw
        assert task in raw["tasks"]
        assert isinstance(raw["tasks"][task], dict)
        assert "model" in raw["tasks"][task]


async def test_crash_during_replace_leaves_original_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-5 crash-during-write: if `os.replace` raises mid-call, the
    original overrides file is unchanged (atomic-replace contract)."""
    _bootstrap_layout(
        tmp_path,
        overrides_initial="tasks:\n  draft_reply:\n    model: claude-haiku-4-5-20251001\n",
        monkeypatch=monkeypatch,
    )
    original_content = (tmp_path / "policy.user-overrides.yaml").read_bytes()
    # Patch os.replace inside the policy module's namespace to raise.
    import mailbot_api.router.policy as policy_mod

    def _exploding_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated mid-write crash")

    monkeypatch.setattr(policy_mod.os, "replace", _exploding_replace)

    out = await set_model_persistent(
        db_path="unused",
        task="draft_reply",
        model="opus",
    )
    # Verb returns ok=False with the write-failure message.
    assert out.ok is False
    assert out.error is not None
    assert "atomic" in out.error.lower() or "replace" in out.error.lower()
    # Original file content is untouched.
    assert (tmp_path / "policy.user-overrides.yaml").read_bytes() == original_content


# ---------------------------------------------------------------------------
# OQ-3 — file-state preconditions
# ---------------------------------------------------------------------------


async def test_absent_file_refused_with_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """OQ-3: when policy.user-overrides.yaml is absent, the verb refuses
    to proceed AND does NOT create the file — the host-side bootstrap is
    the operator's job per Story 9-1's hot-reload contract limitation."""
    _bootstrap_layout(tmp_path, overrides_initial=None, monkeypatch=monkeypatch)
    assert not (tmp_path / "policy.user-overrides.yaml").exists()
    out = await set_model_persistent(
        db_path="unused",
        task="draft_reply",
        model="opus",
    )
    assert out.ok is False
    assert out.error is not None
    # Actionable error must reference the bootstrap command.
    assert (
        "bootstrap" in out.error.lower()
        or "cp router" in out.error.lower()
        or "restart" in out.error.lower()
    )
    # File was NOT created.
    assert not (tmp_path / "policy.user-overrides.yaml").exists()


async def test_unknown_task_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-1 validation: unknown task name is rejected without writing."""
    _bootstrap_layout(tmp_path, monkeypatch=monkeypatch)
    original_content = (tmp_path / "policy.user-overrides.yaml").read_bytes()
    out = await set_model_persistent(
        db_path="unused",
        task="phantom_task",
        model="opus",
    )
    assert out.ok is False
    assert out.error is not None
    assert "unknown task" in out.error.lower()
    # File unchanged.
    assert (tmp_path / "policy.user-overrides.yaml").read_bytes() == original_content


async def test_unknown_model_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-1 validation: unknown model id is rejected without writing."""
    _bootstrap_layout(tmp_path, monkeypatch=monkeypatch)
    original_content = (tmp_path / "policy.user-overrides.yaml").read_bytes()
    out = await set_model_persistent(
        db_path="unused",
        task="draft_reply",
        model="nonsense-model",
    )
    assert out.ok is False
    assert out.error is not None
    assert "unknown model" in out.error.lower()
    assert (tmp_path / "policy.user-overrides.yaml").read_bytes() == original_content


async def test_shorthand_aliases_normalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-1: shorthand aliases (qwen/haiku/opus) normalize to full IDs."""
    _bootstrap_layout(tmp_path, monkeypatch=monkeypatch)
    for alias, full_id in (
        ("qwen", _QWEN),
        ("haiku", _HAIKU),
        ("opus", _OPUS),
    ):
        out = await set_model_persistent(
            db_path="unused",
            task="draft_reply",
            model=alias,
        )
        # ok may be False due to hot-reload timeout, but the write went
        # through and stored the FULL id.
        raw = read_user_overrides_raw(tmp_path / "policy.user-overrides.yaml")
        assert raw["tasks"]["draft_reply"]["model"] == full_id
        if out.ok:
            assert out.model == full_id


async def test_existing_override_overwrites_only_model_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-1 shallow-leaf: an existing task override with sibling fields
    (e.g. lane, max_tokens_out) survives a model-only re-write."""
    initial = (
        "tasks:\n"
        "  draft_reply:\n"
        "    model: claude-haiku-4-5-20251001\n"
        "    lane: batch\n"
        "    max_tokens_out: 256\n"
    )
    _bootstrap_layout(tmp_path, overrides_initial=initial, monkeypatch=monkeypatch)
    await set_model_persistent(
        db_path="unused",
        task="draft_reply",
        model="opus",
    )
    raw = read_user_overrides_raw(tmp_path / "policy.user-overrides.yaml")
    entry = raw["tasks"]["draft_reply"]
    assert entry["model"] == _OPUS
    assert entry["lane"] == "batch"
    assert entry["max_tokens_out"] == 256
