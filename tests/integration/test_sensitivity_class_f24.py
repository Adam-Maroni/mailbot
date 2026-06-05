"""Story 6-18 F24 regression tests: sensitivity_class qwen call must succeed when
the model emits valid JSON with all three required fields and must continue to
fail when `confidence` is dropped.

Background: F24 root cause was prompt-side drift — `sensitivity_class/v1.py`'s
SYSTEM block instructed "Reply with valid JSON matching the schema" but never
enumerated the required field names. qwen2.5:3b-instruct-q4_K_M deterministically
returned `{"sensitivity": "...", "reason": "..."}` (no `confidence`), Pydantic's
`SensitivityClassOutput.model_validate_json` rejected every call, and the
ingest pipeline blocked 712+ emails (no escalation per FR-2.5 / Rule Q
local-only). Same defect class as F21 (Story 6-14 closure for Haiku
summary_short). Story 6-18 ships `v2.py` with schema fields explicitly named.

The tests below lock the fix in three layers:

  (1) **Structural**: assert `sensitivity_class` v2 SYSTEM contains the
      enumerated field names ("sensitivity", "confidence", "reason"). Prevents
      future authors from accidentally removing them.
  (2) **Router happy path (AC-3.b)**: a JSON response with all three fields
      yields `outcome="ok"` on the first leg (no retry consumed).
  (3) **Router F24-shape counter-test (AC-3.a)**: a response missing
      `confidence` (the F24 production failure shape) on BOTH legs yields
      `outcome="failed"` with `SCHEMA_VALIDATION_FAILED` and writes the audit
      row. Locks in the failure path so a future author cannot silently relax
      the Pydantic validator.

AC-3.c bonus (live roundtrip against real Ollama) is gated `pytest.mark.live`
and only fires in environments that opt in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_QWEN_MODEL_ID = "qwen2.5:3b-instruct-q4_K_M"


class _FakeQwenAdapter:
    """Scripted adapter — yields each response in `responses` per call."""

    def __init__(self, responses: list[str]) -> None:
        self.model_id = _QWEN_MODEL_ID
        self.responses = list(responses)
        self.call_log: list[dict[str, Any]] = []

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        self.call_log.append({"system": system, "user": user})
        if not self.responses:
            raise RuntimeError("FakeQwenAdapter exhausted")
        text = self.responses.pop(0)
        return AdapterResponse(
            text=text,
            tokens_in=20,
            tokens_out=10,
            cached_tokens_in=0,
            latency_ms=33,
            raw={"mock": True},
        )


_POLICY_YAML = f"""\
version: "test-sensitivity-class-f24-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN_MODEL_ID}"
    prompt_version: "v2"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state():
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


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


def _content() -> dict[str, str]:
    return {
        "subject": "Re: Tuesday review",
        "sender": "sarah@example.com",
        "body_preview": "Moving the meeting from Friday 3pm to Tuesday 2pm. Let me know.",
    }


# ---------- Layer 1: structural lock-in (no router needed) ----------


def test_sensitivity_class_v2_system_enumerates_required_fields() -> None:
    """F24 structural regression: v2 SYSTEM must name `sensitivity`,
    `confidence`, and `reason` as required output fields.

    Pre-v2, the SYSTEM only said "Reply with valid JSON matching the schema" —
    qwen2.5:3b had no signal that `confidence` was required and deterministically
    dropped it. Story 6-18 closed F24 by enumerating field names in the prompt.
    This test locks the contract so a future edit that strips the field
    enumeration is caught at test time, not after a week of blocked ingest.
    """
    from mailbot_api.prompts.sensitivity_class.v2 import SYSTEM, VERSION

    assert VERSION == "v2"
    # All three required field names must appear in the SYSTEM block.
    assert '"sensitivity"' in SYSTEM, (
        "v2 SYSTEM must enumerate `sensitivity` as a required output field — "
        "without explicit naming, qwen2.5:3b can drop fields and trigger F24."
    )
    assert '"confidence"' in SYSTEM, (
        "v2 SYSTEM must enumerate `confidence` as a required output field — "
        "this is the specific field qwen2.5:3b dropped pre-v2, causing F24."
    )
    assert '"reason"' in SYSTEM, (
        "v2 SYSTEM must enumerate `reason` as a required output field."
    )
    # Cautious-bias preservation (NFR-PRIV-1) must survive the v1 -> v2 bump.
    assert "Cautious bias" in SYSTEM, (
        "v2 SYSTEM must preserve the NFR-PRIV-1 cautious-bias instruction "
        "verbatim from v1 — first line of defense before Story 3-3's "
        "confidence-downgrade wrapper."
    )

    # CR-4: lock in the AC-1 resolver linkage. The above asserts the v2 module
    # directly; this asserts that `resolve_prompt("sensitivity_class", "v2")`
    # also returns it via the registry path the Router uses. Catches the case
    # where the file exists but the resolver's VERSION-equality guard rejects
    # it (accidental v1 content copy-paste into v2.py).
    from mailbot_api.prompts import resolve_prompt

    module = resolve_prompt("sensitivity_class", "v2")
    assert module.version == "v2"
    assert module.system is SYSTEM  # same string object — resolver loaded THIS module


# ---------- Layer 2: router happy path (AC-3.b positive) ----------


async def test_sensitivity_class_with_all_three_fields_yields_outcome_ok(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-3.b: a qwen response shaped as `{"sensitivity", "confidence", "reason"}`
    (which the v2 SYSTEM prompt instructs) succeeds on the first leg.

    Locks the canonical post-fix behavior: well-instructed qwen produces all
    three required fields; the router accepts cleanly; one adapter call
    consumed, no retry leg.
    """
    db_path = _setup(tmp_path)
    adapter = _FakeQwenAdapter(
        [json.dumps({"sensitivity": "normal", "confidence": 0.92, "reason": "Routine meeting confirmation."})]
    )
    register_adapter(_QWEN_MODEL_ID, adapter)

    result = await ask_router(
        task_type="sensitivity_class",
        content=_content(),
        db_path=db_path,
    )

    assert result.ok is True, f"expected ok=True, got error={result.error}"
    assert result.output is not None
    # Lock content extraction — empty-string `reason` would satisfy the
    # max_length=200 constraint but would not be a real classification.
    assert result.output.sensitivity == "normal"  # type: ignore[attr-defined]
    assert result.output.confidence == 0.92  # type: ignore[attr-defined]
    assert result.output.reason == "Routine meeting confirmation."  # type: ignore[attr-defined]
    # Exactly one adapter call — no retry leg consumed (JSON parsed cleanly).
    assert len(adapter.call_log) == 1

    row = await fetchone(db_path, "SELECT outcome, model_chosen FROM router_calls", ())
    assert row == ("ok", _QWEN_MODEL_ID)


# ---------- Layer 3: F24-shape counter-test (AC-3.a) ----------


async def test_sensitivity_class_without_confidence_field_still_fails_with_schema_validation_error(
    tmp_path: Path, _clean_state: Any
) -> None:
    """F24 reproducer (counter-test): if a model emits the F24 production
    failure shape (sensitivity + reason, missing confidence) on BOTH legs, the
    router MUST yield `outcome="failed"` with `SCHEMA_VALIDATION_FAILED` and
    write the audit row. This locks in two contracts:

      (a) The router's `model_validate_json` boundary is not silently weakened
          to accept partial responses (which would mask future F24-shape
          regressions and silently let half-classified emails through the
          privacy gate).
      (b) The retry leg's stricter-JSON prefix is still applied — visible as
          the schema reminder appearing in `adapter.call_log[1]`'s user message.

    This is the canonical F24 failure trace: every qwen sensitivity_class call
    against the v1 prompt produced exactly this shape, outcome=failed, both
    legs consumed (~5 tokens each since qwen is local — no API billing, but
    the ingest pipeline blocked indefinitely with no escalation per FR-2.5 /
    Rule Q local-only).
    """
    db_path = _setup(tmp_path)
    # Both legs return the F24 production shape — missing `confidence`.
    f24_shape = json.dumps({"sensitivity": "normal", "reason": "L'email concerne des applications Microsoft."})
    adapter = _FakeQwenAdapter([f24_shape, f24_shape])
    register_adapter(_QWEN_MODEL_ID, adapter)

    result = await ask_router(
        task_type="sensitivity_class",
        content=_content(),
        db_path=db_path,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SCHEMA_VALIDATION_FAILED
    # Both legs fired — first leg parses to dict-without-confidence, fails
    # Pydantic; retry leg with stricter prefix also returns same shape, also
    # fails. Router records failed and gives up (no escalation per policy).
    assert len(adapter.call_log) == 2

    # The retry leg's user message contains the stricter "valid JSON" reminder.
    # (We don't pin the exact substring — that would be brittle across router
    # internals — but we assert it differs from the first leg's user message
    # to prove the retry path actually fired.)
    assert adapter.call_log[0]["user"] != adapter.call_log[1]["user"]

    # Audit row written with failed outcome. The error code (SCHEMA_VALIDATION_FAILED)
    # is carried on the RouterResult.error returned to the caller, asserted above —
    # router_calls does not persist a dedicated error_code column (errors-as-data
    # surface is the RouterResult only; the audit row records the outcome string).
    row = await fetchone(
        db_path,
        "SELECT outcome, model_chosen FROM router_calls",
        (),
    )
    assert row is not None
    assert row[0] == "failed"
    assert row[1] == _QWEN_MODEL_ID


# ---------- Layer 4 (bonus, AC-3.c): live roundtrip ----------


@pytest.mark.live
async def test_sensitivity_class_v2_real_qwen_returns_all_three_fields(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-3.c bonus: a real-Ollama roundtrip proves the v2 prompt actually
    elicits all three fields from qwen2.5:3b-instruct-q4_K_M.

    Gated `pytest.mark.live` (only fires when `-m live` is passed). Requires
    an Ollama container reachable at `OLLAMA_BASE_URL` (defaults to
    `http://localhost:11434` or `http://ollama:11434` per the project's
    `OllamaAdapter` defaults) with the qwen model pulled.

    Pre-v2 this same test would have failed with SCHEMA_VALIDATION_FAILED
    (the F24 production trace); post-v2 it should succeed with the canonical
    three-field JSON.
    """
    import os

    from mailbot_api.router.adapters.ollama import OllamaAdapter

    db_path = _setup(tmp_path)
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    adapter = OllamaAdapter(model_id=_QWEN_MODEL_ID, base_url=base_url)
    register_adapter(_QWEN_MODEL_ID, adapter)

    result = await ask_router(
        task_type="sensitivity_class",
        content={
            "subject": "Microsoft account security alert",
            "sender": "account-security-noreply@accountprotection.microsoft.com",
            "body_preview": "Sign-in attempt detected from Paris, France. If this was you, no action needed.",
        },
        db_path=db_path,
    )

    assert result.ok is True, f"expected ok=True, got error={result.error}"
    assert result.output is not None
    assert result.output.sensitivity in ("normal", "sensitive", "confidential")  # type: ignore[attr-defined]
    assert 0.0 <= result.output.confidence <= 1.0  # type: ignore[attr-defined]
    assert 0 < len(result.output.reason) <= 200  # type: ignore[attr-defined]
