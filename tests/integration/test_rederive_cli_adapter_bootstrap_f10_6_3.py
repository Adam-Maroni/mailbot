"""Story 10.5.4 Task 1 (AC-1, F-10-6-3): the `rederive` CLI subcommand must
bootstrap the adapter registry before dispatching.

The bug (Epic 10 fault-injection walk, retro §7): `mailbot rederive` crashed on
EVERY invocation with `KeyError: no adapter registered for
'qwen2.5:3b-instruct-q4_K_M'`. `_cmd_rederive` called only `_load_policy_for_cli()`
— it loaded the policy snapshot but NEVER registered adapters. The FastAPI
lifespan (`main.py`) and the pipeline CLI (`pipeline.py:_cli_async_main`) both
call `init_pipeline_runtime` which registers adapters; the rederive CLI did not.
So the documented recovery fix at README:295/:305 was dead.

This is the same bug CLASS as F17 (Story 6-11: worker process forgot to init the
runtime) — see `test_worker_pipeline_runtime_init.py`. This test guards the
rederive CLI's own init path against re-introduction by driving `_cmd_rederive`
with an EMPTY registry (the production condition) and asserting it runs to
completion with a real `router_calls` insert and NO KeyError.

Middleware-Real-Bootstrap (architecture §2.4.7 / §2.4.7 MailBot reframing): the
Router, DB, and CLI init path are all REAL; only the SDK boundary (the Ollama
adapter) is a scripted fake, registered by overriding `init_default_adapters`'
Ollama construction so no real Ollama server is contacted.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchall
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
)
from mailbot_api.router.registry import (
    _reset_registry_for_test,
    register_adapter,
)

_QWEN = "qwen2.5:3b-instruct-q4_K_M"


@pytest.fixture
def _clean_state():
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


class _FakeQwenAdapter:
    model_id = _QWEN

    def __init__(self) -> None:
        self.calls = 0

    async def call(self, system, user, max_tokens_out, temperature=0.0):
        self.calls += 1
        return AdapterResponse(
            text=json.dumps({"class_coarse": "newsletter", "confidence": 0.9}),
            tokens_in=5,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=10,
            raw={},
        )

    async def embed(self, text):
        raise RuntimeError("no embed")


def _point_env_at_repo_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH",
        str(repo_root / "router" / "sensitivity_patterns.yaml"),
    )


async def _seed_classified_email_needing_coarse(db_path: str, *, graph_id: str) -> None:
    """An email with sensitivity classified but no coarse_class → selected for coarse rederive."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-05-15T00:00:00Z", "s", "x@y.com", "body",
            "normal", "2026-05-01T00:00:00Z", "v1", 0.9, _QWEN,
        ),
    )


async def test_cmd_rederive_bootstraps_adapters_and_dispatches_no_keyerror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: Any,
) -> None:
    """AC-1 / F-10-6-3: `_cmd_rederive` must register adapters via its init path
    so the first `ask_router` dispatch does NOT raise `KeyError: no adapter
    registered`. Pre-fix this raised because `_cmd_rederive` never registered
    adapters. Post-fix (init_pipeline_runtime) the registry is populated.

    We register the fake Qwen adapter by patching the registry's default-adapter
    constructor so `init_default_adapters` (called inside init_pipeline_runtime)
    installs OUR fake instead of a real Ollama client — the registry is
    genuinely populated by the CLI's own init path, not pre-seeded by the test.
    """
    from scripts import mailbot as cli

    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    _point_env_at_repo_yaml(monkeypatch)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    # Skip the real Ollama registration; register a fake for every model id the
    # policy pins. `init_default_adapters` is what `_cmd_rederive` must now call
    # (via init_pipeline_runtime) — we patch it to install fakes so the CLI's
    # init path populates the registry without a live Ollama server.
    fake = _FakeQwenAdapter()

    def _fake_init_default_adapters() -> None:
        register_adapter(_QWEN, fake)

    monkeypatch.setattr(
        "mailbot_api.router.registry.init_default_adapters",
        _fake_init_default_adapters,
    )

    await _seed_classified_email_needing_coarse(db_path, graph_id="redr-1")

    # Drive the CLI subcommand end-to-end. Pre-fix: KeyError at first dispatch.
    exit_code = await cli._cmd_rederive(
        task="coarse_class",
        since=date(2026, 4, 1),
        prompt_version=None,
        yes=True,  # skip the interactive confirm
        db_path_arg=db_path,
    )

    # No crash → clean exit (0 = all rows succeeded).
    assert exit_code == 0
    assert fake.calls >= 1, "the fake Qwen adapter was never dispatched — init path did not register it"

    # A real router_calls row landed (dispatch actually happened through the Router).
    rows = await fetchall(
        db_path,
        "SELECT task_type, caller_origin FROM router_calls WHERE task_type = 'coarse_class'",
        (),
    )
    assert rows == [("coarse_class", "cli-rederive")]

    # The coarse_class value was written.
    written = await fetchall(
        db_path,
        "SELECT class_coarse FROM emails WHERE graph_id = 'redr-1'",
        (),
    )
    assert written == [("newsletter",)]
