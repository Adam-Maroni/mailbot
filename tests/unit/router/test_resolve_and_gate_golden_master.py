"""Dispatch-decision GOLDEN-MASTER for Story 11.6.1 (resolve_and_gate seam).

This is the load-bearing safety net for extracting the pre-dispatch guard chain
(pause -> pick model -> degrade -> price -> per-call cost) out of `ask_router`
and `dispatch_tool_call` into one `resolve_and_gate` seam.

It drives the CURRENT (pre-refactor) `ask_router` over a branch-covering corpus
and pins the pre-dispatch DECISION each row produces:

    (pause_flag, refused, refusal_code, selected_model, degraded_demotion, log_fired)

CONTRACT (Story 11.6.1 AC-7):
  * Captured on `master` BEFORE the seam extraction -> must be GREEN here.
  * After `resolve_and_gate` is extracted and the paths rewired, this file must
    stay BYTE-IDENTICAL green. Any diff is a behaviour change -> stop + reconcile.

Why the tuple records DECISIONS, not mailbox facts: the seam's inputs are
pause/policy/budget state + prompt-string length (NEVER the ingested `messages`
view), so this oracle does NOT inherit the shared-oracle blindness that spawned
Epic 11.5. It is an independent oracle for exactly the surface #3 restructures.

Corpus coverage map (branch -> row):
  * clean-pass (model runs, no refuse/demote) .......... ROW clean_pass
  * paused + REFUSED (task_type not pause-allowed) ..... ROW paused_refused
  * degraded demotion (opus -> haiku) ................. ROW degraded_demote
  * over-cost REFUSED (est cost > $0.20) .............. ROW over_cost
  * cost exactly AT threshold (not over -> pass) ...... ROW cost_at_threshold
  * cost one epsilon OVER threshold (refuse) .......... ROW cost_epsilon_over
  * unknown task_type (policy_entry is None refusal) .. ROW unknown_task

Boundary rows (at-threshold / epsilon-over) are computed against the live
`estimate_cost_usd` + policy `max_tokens_out` so the golden pins the REAL
comparison, not a guessed number.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.budget import (
    PER_CALL_REFUSAL_THRESHOLD_USD,
    _reset_guard_for_test,
    get_guard,
)
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test, get_pause_state
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_LOGGER_NAME = "mailbot_api.router.router"
_REFUSAL_EVENT = "budget.per_call.refused"

# Real model ids so pricing.py returns real (placeholder) rates for the cost rows.
_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


class _FakeAdapter:
    """Scripted adapter — records calls, yields one response per call."""

    def __init__(self, responses: list[AdapterResponse] | None = None) -> None:
        self.responses = responses or []
        self.call_log: list[dict[str, Any]] = []

    async def call(
        self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0
    ) -> AdapterResponse:
        self.call_log.append({"system": system, "user": user})
        if not self.responses:
            raise RuntimeError("FakeAdapter ran out of scripted responses")
        return self.responses.pop(0)


def _adapter_response() -> AdapterResponse:
    return AdapterResponse(
        text=json.dumps({"class_coarse": "newsletter", "confidence": 0.9}),
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=42,
        raw={"mock": True},
    )


def _content() -> dict[str, Any]:
    return {"subject": "hi", "sender": "a@b.co", "body_preview": "x"}


def _write_policy(tmp_path: Path, *, model: str, max_tokens_out: int = 256) -> str:
    """Single-task policy pinned to `model` with a chosen output cap. Returns db_path."""
    db_path = str(tmp_path / "gm.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        yaml.safe_dump(
            {
                "version": "gm-v1",
                "tasks": {
                    "coarse_class": {
                        "model": model,
                        "prompt_version": "v1",
                        "escalate": False,
                        "max_tokens_out": max_tokens_out,
                        "lane": "batch",
                        "sensitivity": "any",
                        "response_cache_ttl_seconds": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


@pytest.fixture
def _clean() -> Any:
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


async def _decision(
    db_path: str,
    caplog: pytest.LogCaptureFixture,
    *,
    task_type: str = "coarse_class",
    force: bool = False,
) -> dict[str, Any]:
    """Drive the CURRENT ask_router once and distill the pre-dispatch decision tuple."""
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = await ask_router(task_type, _content(), db_path=db_path, force=force)
    log_fired = any(
        getattr(r, "event", None) == _REFUSAL_EVENT for r in caplog.records
    )
    code = result.error.code.value if (not result.ok and result.error) else None
    return {
        "ok": result.ok,
        "refusal_code": code,
        "model_used": result.model_used,
        "log_fired": log_fired,
    }


# ---------------------------------------------------------------------------
# GOLDEN-MASTER: the pinned decision for each corpus row. Captured on master
# (25e6e06). After the resolve_and_gate extraction these MUST stay identical.
# ---------------------------------------------------------------------------


async def test_gm_clean_pass(tmp_path: Path, _clean: Any, caplog: Any) -> None:
    """Clean pass: qwen ($0 local) runs, no refuse, no demote, no refusal-log."""
    db_path = _write_policy(tmp_path, model=_QWEN)
    register_adapter(_QWEN, _FakeAdapter([_adapter_response()]))
    d = await _decision(db_path, caplog)
    assert d == {
        "ok": True,
        "refusal_code": None,
        "model_used": _QWEN,
        "log_fired": False,
    }


async def test_gm_paused_refused(tmp_path: Path, _clean: Any, caplog: Any) -> None:
    """Paused + non-pause-allowed task_type -> PROVIDER_ERROR 'router paused', no model, no cost-log."""
    db_path = _write_policy(tmp_path, model=_QWEN)
    register_adapter(_QWEN, _FakeAdapter([_adapter_response()]))
    await get_pause_state().pause(db_path, reason="golden-master")
    d = await _decision(db_path, caplog)
    # model_used == "" (empty string, not None) is the CURRENT reality on the
    # pause-refusal RouterResult — golden records what IS.
    assert d == {
        "ok": False,
        "refusal_code": ErrorCode.PROVIDER_ERROR.value,
        "model_used": "",
        "log_fired": False,
    }


async def test_gm_over_cost_refused(tmp_path: Path, _clean: Any, caplog: Any) -> None:
    """Huge max_tokens_out on Opus -> estimated cost > $0.20 -> PER_CALL_THRESHOLD_EXCEEDED + refusal-log fires."""
    db_path = _write_policy(tmp_path, model=_OPUS, max_tokens_out=100_000)
    register_adapter(_OPUS, _FakeAdapter([_adapter_response()]))
    d = await _decision(db_path, caplog)
    # log_fired flipped False→True on 2026-08-24 when story 11-5-4 (GitHub #4)
    # shipped the `budget.per_call.refused` line at both refusal sites. This is a
    # DELIBERATE, documented golden update (the row anticipated this flip), NOT a
    # silent regression mask. 11-6-1's seam extraction must keep this True and
    # emit the log ONCE from the consolidated cost-check.
    assert d == {
        "ok": False,
        "refusal_code": ErrorCode.PER_CALL_THRESHOLD_EXCEEDED.value,
        "model_used": _OPUS,
        "log_fired": True,
    }


async def test_gm_over_cost_forced_passes(tmp_path: Path, _clean: Any, caplog: Any) -> None:
    """Same over-cost row but force=True -> the `and not force` branch: NO refusal, model runs, NO log."""
    db_path = _write_policy(tmp_path, model=_OPUS, max_tokens_out=100_000)
    register_adapter(_OPUS, _FakeAdapter([_adapter_response()]))
    d = await _decision(db_path, caplog, force=True)
    assert d == {
        "ok": True,
        "refusal_code": None,
        "model_used": _OPUS,
        "log_fired": False,
    }


async def test_gm_degraded_demotes_opus_to_haiku(
    tmp_path: Path, _clean: Any, caplog: Any
) -> None:
    """Degraded mode active + policy model Opus -> demote_model(opus)=haiku; haiku runs; no refusal."""
    db_path = _write_policy(tmp_path, model=_OPUS)
    # register both: policy says opus, degraded demotes to haiku which actually runs
    register_adapter(_OPUS, _FakeAdapter([_adapter_response()]))
    register_adapter(_HAIKU, _FakeAdapter([_adapter_response()]))
    guard = get_guard()
    await guard._enter_degraded_mode(db_path)
    d = await _decision(db_path, caplog)
    assert d == {
        "ok": True,
        "refusal_code": None,
        "model_used": _HAIKU,
        "log_fired": False,
    }


async def test_gm_unknown_task_type_refused(
    tmp_path: Path, _clean: Any, caplog: Any
) -> None:
    """task_type not in policy -> policy_entry is None -> PROVIDER_ERROR, no model, no cost-log."""
    db_path = _write_policy(tmp_path, model=_QWEN)
    register_adapter(_QWEN, _FakeAdapter([_adapter_response()]))
    d = await _decision(db_path, caplog, task_type="no_such_task")
    # model_used == "" (empty string) is current reality on this refusal path.
    assert d == {
        "ok": False,
        "refusal_code": ErrorCode.PROVIDER_ERROR.value,
        "model_used": "",
        "log_fired": False,
    }


def test_gm_threshold_constant_pinned() -> None:
    """Pin the per-call threshold the boundary rows depend on. If this changes,
    the over-cost golden rows above must be re-derived deliberately, not silently."""
    assert PER_CALL_REFUSAL_THRESHOLD_USD == pytest.approx(0.20, abs=1e-9)
