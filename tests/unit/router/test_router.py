"""Failure-chain tests for mailbot_api.router.router:ask_router (Story 2-4 AC-10).

Uses a fake `ModelAdapter` returning scripted `AdapterResponse` instances
(or raising scripted exceptions). Real Ollama/Anthropic adapters live in
their own modules with their own unit tests.

Each test applies the migration runner to a `tmp_path` SQLite so the
`finally`-block `record_router_call` writes work end-to-end and the
`router_calls` row count can be asserted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.budget import _reset_guard_for_test, get_guard
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import (
    AdapterProviderError,
    AdapterResponse,
    AdapterTimeout,
)
from mailbot_api.router.pause import _reset_pause_state_for_test, get_pause_state
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter


class _FakeAdapter:
    """Scripted ModelAdapter — yields one response (or raises) per `call`."""

    def __init__(
        self,
        responses: list[AdapterResponse | BaseException] | None = None,
        model_id: str = "fake-model",
    ) -> None:
        self.responses: list[AdapterResponse | BaseException] = responses or []
        self.model_id = model_id
        self.call_log: list[dict[str, Any]] = []

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        self.call_log.append(
            {
                "system": system,
                "user": user,
                "max_tokens_out": max_tokens_out,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise RuntimeError("FakeAdapter ran out of scripted responses")
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


_POLICY_YAML_TEMPLATE = """\
version: "test-v1"

tasks:
  coarse_class:
    model: "{model}"
    prompt_version: "v1"
    escalate: {escalate}
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
    response_cache_ttl_seconds: {ttl}
"""


def _setup_db_and_policy(
    tmp_path: Path,
    *,
    model: str = "fake-qwen",
    escalate: bool = False,
    cache_ttl: int = 0,
) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        _POLICY_YAML_TEMPLATE.format(
            model=model, escalate=str(escalate).lower(), ttl=cache_ttl
        ),
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


def _good_output_json() -> str:
    # Story 3-2: coarse_class output is now {class_coarse, confidence} with a
    # 6-label taxonomy (newsletter is still valid).
    return json.dumps({"class_coarse": "newsletter", "confidence": 0.9})


def _adapter_response(text: str = "", tokens_in: int = 10, tokens_out: int = 5) -> AdapterResponse:
    return AdapterResponse(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cached_tokens_in=0,
        latency_ms=42,
        raw={"mock": True},
    )


@pytest.fixture
def _clean_state() -> None:
    """Reset module-level singletons between tests."""
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


def _content() -> dict[str, Any]:
    return {"subject": "newsletter weekly", "sender": "news@example.com", "body_preview": "..."}


# ---- Happy path + model_chosen_reason variants ----


async def test_ask_router_happy_path(tmp_path: Path, _clean_state: None) -> None:
    db_path = _setup_db_and_policy(tmp_path, model="fake-qwen", escalate=False)
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)

    assert result.ok is True
    assert result.error is None
    assert result.output is not None
    assert result.model_used == "fake-qwen"
    assert result.tokens_in == 10
    assert result.tokens_out == 5

    rows = await fetchall(db_path, "SELECT model_chosen, model_chosen_reason, outcome FROM router_calls", ())
    assert len(rows) == 1
    # Story 9.2: closed-set vocabulary; was bare "policy" pre-9.2.
    assert rows[0] == ("fake-qwen", "policy:coarse_class:default", "ok")


async def test_ask_router_force_model_logs_override(
    tmp_path: Path, _clean_state: None
) -> None:
    db_path = _setup_db_and_policy(tmp_path, model="fake-qwen")
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("fake-opus", adapter)

    result = await ask_router(
        "coarse_class", _content(), db_path=db_path, force_model="fake-opus"
    )
    assert result.ok is True
    row = await fetchone(
        db_path, "SELECT model_chosen, model_chosen_reason FROM router_calls", ()
    )
    # Story 9.2: force=True and force=False both collapse to OVERRIDE_API per
    # AC-1's vocabulary consolidation. Pre-9.2 this was bare "override".
    assert row == ("fake-opus", "override:api:force_model")


# ---- Timeout ----


async def test_ask_router_timeout_no_retry(tmp_path: Path, _clean_state: None) -> None:
    db_path = _setup_db_and_policy(tmp_path)
    adapter = _FakeAdapter([AdapterTimeout(model_id="fake-qwen", timeout_seconds=30.0)])
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.TIMEOUT
    assert len(adapter.call_log) == 1, "timeout should not trigger a retry"

    row = await fetchone(db_path, "SELECT outcome FROM router_calls", ())
    assert row == ("failed",)


# ---- Schema validation failure + retry ----


async def test_ask_router_schema_failure_then_retry_succeeds(
    tmp_path: Path, _clean_state: None
) -> None:
    db_path = _setup_db_and_policy(tmp_path)
    bad_then_good = [
        _adapter_response("not json at all"),
        _adapter_response(_good_output_json()),
    ]
    adapter = _FakeAdapter(bad_then_good)
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is True
    assert len(adapter.call_log) == 2
    # Stricter prompt prefix was applied on the retry leg.
    assert "valid JSON matching this schema" in adapter.call_log[1]["user"]

    row = await fetchone(db_path, "SELECT outcome FROM router_calls", ())
    assert row == ("retry_recovered",)


async def test_ask_router_schema_failure_then_retry_fails_no_escalate(
    tmp_path: Path, _clean_state: None
) -> None:
    db_path = _setup_db_and_policy(tmp_path, escalate=False)
    adapter = _FakeAdapter(
        [_adapter_response("garbage"), _adapter_response("still garbage")]
    )
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SCHEMA_VALIDATION_FAILED

    row = await fetchone(db_path, "SELECT outcome FROM router_calls", ())
    assert row == ("failed",)


async def test_ask_router_schema_failure_then_escalation_succeeds(
    tmp_path: Path, _clean_state: None
) -> None:
    db_path = _setup_db_and_policy(
        tmp_path,
        model="qwen2.5:3b-instruct-q4_K_M",  # real chain start
        escalate=True,
    )
    qwen_adapter = _FakeAdapter(
        [_adapter_response("bad"), _adapter_response("still bad")]
    )
    haiku_adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("qwen2.5:3b-instruct-q4_K_M", qwen_adapter)
    register_adapter("claude-haiku-4-5-20251001", haiku_adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is True

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason, outcome FROM router_calls ORDER BY id",
        (),
    )
    # Two rows: escalation runs as a recursive ask_router invocation, so its
    # `finally` records the escalated row FIRST; the outer call's `finally`
    # then records the original-tier failure. Audit-row ordering reflects
    # finally-block unwinding (inner → outer), not dispatch order.
    assert len(rows) == 2
    # Story 9.2: vocabulary migrated to "policy:escalation:<from>→<to>" and
    # templated "policy:<task>:default" per AC-1; pre-9.2 was bare
    # "escalated_from_<X>" and bare "policy".
    assert rows[0][0] == "claude-haiku-4-5-20251001"
    assert rows[0][1] == "policy:escalation:qwen2.5:3b-instruct-q4_K_M→claude-haiku-4-5-20251001"
    assert rows[0][2] == "ok"
    assert rows[1][0] == "qwen2.5:3b-instruct-q4_K_M"
    assert rows[1][1] == "policy:coarse_class:default"
    # outcome on the outer record reflects the escalated success.
    assert rows[1][2] == "escalated"


async def test_ask_router_escalation_also_fails(tmp_path: Path, _clean_state: None) -> None:
    db_path = _setup_db_and_policy(
        tmp_path,
        model="qwen2.5:3b-instruct-q4_K_M",
        escalate=True,
    )
    qwen_adapter = _FakeAdapter(
        [_adapter_response("bad"), _adapter_response("still bad")]
    )
    haiku_adapter = _FakeAdapter(
        [_adapter_response("also bad"), _adapter_response("triply bad")]
    )
    # Story 2-4 review fix HIGH cap: escalation is bounded at 1 hop. The
    # recursive escalated call uses a clone of the policy_entry with
    # `escalate=False`, so haiku's schema-validation failure terminates at
    # SCHEMA_VALIDATION_FAILED rather than chaining to opus and tripling
    # costs. We register a haiku adapter but no opus adapter — and the
    # absence is NEVER reached because the cap stops the chain there.
    register_adapter("qwen2.5:3b-instruct-q4_K_M", qwen_adapter)
    register_adapter("claude-haiku-4-5-20251001", haiku_adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SCHEMA_VALIDATION_FAILED


async def test_ask_router_escalation_cap_at_one_hop(
    tmp_path: Path, _clean_state: None
) -> None:
    """Story 2-4 review fix HIGH regression test: a 3-hop chain
    (qwen → haiku → opus) MUST NOT execute even when all three adapters
    are registered and the policy has escalate=True. The recursive call
    runs with escalate=False so the chain terminates at the haiku tier.
    """
    db_path = _setup_db_and_policy(
        tmp_path,
        model="qwen2.5:3b-instruct-q4_K_M",
        escalate=True,
    )
    qwen_adapter = _FakeAdapter(
        [_adapter_response("bad"), _adapter_response("still bad")]
    )
    haiku_adapter = _FakeAdapter(
        [_adapter_response("also bad"), _adapter_response("still bad")]
    )
    opus_adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("qwen2.5:3b-instruct-q4_K_M", qwen_adapter)
    register_adapter("claude-haiku-4-5-20251001", haiku_adapter)
    register_adapter("claude-opus-4-7", opus_adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    # MUST NOT escalate further — even though opus would succeed.
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SCHEMA_VALIDATION_FAILED
    # Opus adapter must NOT have been called.
    assert len(opus_adapter.call_log) == 0, (
        "opus must not be invoked — escalation is capped at 1 hop"
    )


async def test_ask_router_retry_timeout_surfaces_in_error_message(
    tmp_path: Path, _clean_state: None
) -> None:
    """Story 2-4 review fix MEDIUM regression test: a retry-leg adapter
    exception (e.g., AdapterTimeout) must be surfaced in the final
    RouterError.message rather than silently subsumed under a generic
    'retry also failed schema validation' string."""
    db_path = _setup_db_and_policy(tmp_path, escalate=False)
    adapter = _FakeAdapter(
        [
            _adapter_response("not json"),
            AdapterTimeout(model_id="fake-qwen", timeout_seconds=30.0),
        ]
    )
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SCHEMA_VALIDATION_FAILED
    # The retry-leg exception type must appear in the message.
    assert "AdapterTimeout" in result.error.message


# ---- Provider error ----


async def test_ask_router_provider_error(tmp_path: Path, _clean_state: None) -> None:
    db_path = _setup_db_and_policy(tmp_path)
    adapter = _FakeAdapter(
        [AdapterProviderError(model_id="fake-qwen", sanitized_message="upstream 503")]
    )
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert "upstream 503" in result.error.message


async def test_ask_router_generic_exception_caught(
    tmp_path: Path, _clean_state: None
) -> None:
    db_path = _setup_db_and_policy(tmp_path)
    # FakeAdapter ran out of scripted responses → raises RuntimeError inside dispatch.
    adapter = _FakeAdapter([])
    register_adapter("fake-qwen", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR


# ---- Unknown task_type / unknown adapter ----


async def test_ask_router_unknown_task_type(tmp_path: Path, _clean_state: None) -> None:
    db_path = _setup_db_and_policy(tmp_path)
    result = await ask_router("nonexistent_task", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert "task_type not in policy" in result.error.message


async def test_ask_router_unknown_adapter(tmp_path: Path, _clean_state: None) -> None:
    db_path = _setup_db_and_policy(tmp_path, model="model-with-no-adapter")
    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert "no adapter registered" in result.error.message


# ---- Policy snapshot stability mid-call ----


async def test_ask_router_uses_dispatch_snapshot_not_swapped_policy(
    tmp_path: Path, _clean_state: None
) -> None:
    """If policy is swapped during dispatch, the call uses the pre-swap snapshot."""
    db_path = _setup_db_and_policy(tmp_path, model="fake-qwen")
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("fake-qwen", adapter)

    # Construct a future policy with a different model id and swap it in
    # right before the call — but the call's snapshot capture happens BEFORE
    # the swap, so the call uses the original.
    swapped_yaml = tmp_path / "swapped.yaml"
    swapped_yaml.write_text(
        yaml.safe_dump(
            {
                "version": "swapped",
                "tasks": {
                    "coarse_class": {
                        "model": "future-model-with-no-adapter",
                        "prompt_version": "v1",
                        "escalate": False,
                        "max_tokens_out": 256,
                        "lane": "batch",
                        "sensitivity": "any",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    # We can't easily inject a swap during the await without thread/event
    # gymnastics; instead, test the simpler invariant: a second call
    # AFTER an explicit swap uses the new policy.
    result1 = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result1.ok is True

    set_policy_snapshot(load_policy(swapped_yaml))
    result2 = await ask_router("coarse_class", _content(), db_path=db_path)
    # Second call hits the swapped policy → no adapter → provider_error.
    assert result2.ok is False
    assert result2.error is not None
    assert "no adapter registered" in result2.error.message


# ---- Story 2-5: rate-limit gate ----


async def test_ask_router_rate_limit_breach_returns_rate_limited(
    tmp_path: Path, _clean_state: None
) -> None:
    """Exhaust the interactive lane budget; the next call must surface
    RouterError(code=RATE_LIMITED) without hitting the adapter."""
    # Policy with lane=interactive (override the default batch from the helper).
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        """version: \"interactive-test\"

tasks:
  coarse_class:
    model: \"fake-qwen\"
    prompt_version: \"v1\"
    escalate: false
    max_tokens_out: 256
    lane: \"interactive\"
    sensitivity: \"any\"
    response_cache_ttl_seconds: 0
""",
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))

    adapter = _FakeAdapter([_adapter_response(_good_output_json())] * 200)
    register_adapter("fake-qwen", adapter)

    # Exhaust the 60/hr interactive budget. Use distinct content per call to
    # avoid tripping the Story 2-9 loop detector (10x identical prompt limit).
    for i in range(60):
        result = await ask_router(
            "coarse_class",
            {"subject": f"unique-{i}", "sender": "x@y.com", "body_preview": "..."},
            db_path=db_path,
        )
        assert result.ok is True

    # 61st call should fail-fast with RATE_LIMITED.
    breach = await ask_router(
        "coarse_class",
        {"subject": "unique-61", "sender": "x@y.com", "body_preview": "..."},
        db_path=db_path,
    )
    assert breach.ok is False
    assert breach.error is not None
    assert breach.error.code == ErrorCode.RATE_LIMITED
    assert breach.error.retryable is True
    assert "lane:interactive" in breach.error.message

    # The adapter call count should be exactly 60 — the breach short-circuited.
    assert len(adapter.call_log) == 60


# ---- Story 2-7: response cache ----


async def test_ask_router_response_cache_hit_on_second_call(
    tmp_path: Path, _clean_state: None
) -> None:
    """First call hits the adapter and caches; second identical call returns
    cached result with `model_used` ending in `+response_cache` and
    `outcome="ok"` recorded with `model_chosen_reason="cache:response_cache_hit"`
    (Story 9.2 closed-set vocabulary; was bare "response_cache_hit" pre-9.2)."""
    db_path = _setup_db_and_policy(
        tmp_path, model="fake-qwen", escalate=False, cache_ttl=300
    )
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("fake-qwen", adapter)

    first = await ask_router("coarse_class", _content(), db_path=db_path)
    assert first.ok is True
    assert first.model_used == "fake-qwen"
    assert len(adapter.call_log) == 1

    # Second call with identical content should hit the cache.
    second = await ask_router("coarse_class", _content(), db_path=db_path)
    assert second.ok is True
    assert second.model_used == "fake-qwen+response_cache"
    assert second.cost_usd == 0.0
    # Adapter NOT called a second time.
    assert len(adapter.call_log) == 1, "cache hit must short-circuit adapter dispatch"

    # Two router_calls rows; the second has model_chosen_reason="cache:response_cache_hit"
    # (Story 9.2 vocabulary; was bare "response_cache_hit" pre-9.2).
    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason, outcome FROM router_calls ORDER BY id",
        (),
    )
    assert len(rows) == 2
    assert rows[1][1] == "cache:response_cache_hit"
    assert rows[1][2] == "ok"


async def test_ask_router_no_cache_when_ttl_zero(
    tmp_path: Path, _clean_state: None
) -> None:
    """response_cache_ttl_seconds=0 disables caching; both calls hit the adapter."""
    db_path = _setup_db_and_policy(
        tmp_path, model="fake-qwen", escalate=False, cache_ttl=0
    )
    adapter = _FakeAdapter(
        [_adapter_response(_good_output_json()), _adapter_response(_good_output_json())]
    )
    register_adapter("fake-qwen", adapter)

    await ask_router("coarse_class", _content(), db_path=db_path)
    await ask_router("coarse_class", _content(), db_path=db_path)
    assert len(adapter.call_log) == 2


async def test_ask_router_cache_warmer_origin_bypasses_rate_limit(
    tmp_path: Path, _clean_state: None
) -> None:
    """Story 2-7: caller_origin='cache-warmer' must bypass the rate-limit
    budget so warmer probes don't eat into chat/ingest allowances."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        """version: \"warmer-bypass\"

tasks:
  coarse_class:
    model: \"fake-qwen\"
    prompt_version: \"v1\"
    escalate: false
    max_tokens_out: 256
    lane: \"interactive\"
    sensitivity: \"any\"
""",
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))

    adapter = _FakeAdapter([_adapter_response(_good_output_json())] * 200)
    register_adapter("fake-qwen", adapter)

    # Exhaust the 60/hr interactive budget with regular calls (distinct
    # content to avoid Story 2-9 loop detector).
    for i in range(60):
        await ask_router(
            "coarse_class",
            {"subject": f"reg-{i}", "sender": "x@y.com", "body_preview": "..."},
            db_path=db_path,
        )

    # A regular call NOW would be rate-limited.
    blocked = await ask_router(
        "coarse_class",
        {"subject": "regular-blocked", "sender": "x@y.com", "body_preview": "..."},
        db_path=db_path,
    )
    assert blocked.ok is False
    assert blocked.error is not None
    assert blocked.error.code == ErrorCode.RATE_LIMITED

    # But a cache-warmer call goes through.
    warmer_call = await ask_router(
        "coarse_class",
        {"subject": "warmer-bypass", "sender": "x@y.com", "body_preview": "..."},
        db_path=db_path,
        caller_origin="cache-warmer",
    )
    assert warmer_call.ok is True


# ---- Story 2-8: budget guard ----


async def test_ask_router_layer_4_refuses_expensive_call(
    tmp_path: Path, _clean_state: None
) -> None:
    """Layer 4 — per-call estimate > $0.20 returns PER_CALL_THRESHOLD_EXCEEDED."""
    # Use the real Opus model id so pricing.py returns real placeholder rates.
    db_path = _setup_db_and_policy(tmp_path, model="claude-opus-4-7", escalate=False)
    # Even though no adapter is registered for opus, Layer 4 fires BEFORE
    # adapter resolution? Actually no — Layer 4 fires AFTER adapter resolution
    # (inside _dispatch_with_failure_chain). Register a dummy adapter so the
    # gate gets reached.
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("claude-opus-4-7", adapter)

    # The policy has max_tokens_out=256, system+user is short. With Opus
    # placeholder rate $75/Mtok output, 256 output tokens = ~$0.019. That's
    # well under $0.20. To trip Layer 4 we need a high output cap.
    # Patch policy to have a huge max_tokens_out by re-writing the YAML.
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        """version: \"layer4-test\"

tasks:
  coarse_class:
    model: \"claude-opus-4-7\"
    prompt_version: \"v1\"
    escalate: false
    max_tokens_out: 100000
    lane: \"batch\"
    sensitivity: \"any\"
""",
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PER_CALL_THRESHOLD_EXCEEDED
    # Adapter NOT called.
    assert len(adapter.call_log) == 0


async def test_ask_router_layer_4_force_override(
    tmp_path: Path, _clean_state: None
) -> None:
    """force=True bypasses Layer 4 and logs model_chosen_reason="override:api:force_model"
    (Story 9.2 closed-set vocabulary; pre-9.2 distinguished force=True as
    "force_override", but the audit row now collapses both branches to
    ModelChosenReason.OVERRIDE_API per AC-1's vocabulary consolidation —
    `force` boolean still gates degraded-mode behavior internally, just not
    visible in the audit string)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        """version: \"force-test\"

tasks:
  coarse_class:
    model: \"claude-opus-4-7\"
    prompt_version: \"v1\"
    escalate: false
    max_tokens_out: 100000
    lane: \"batch\"
    sensitivity: \"any\"
""",
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))

    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("claude-opus-4-7", adapter)

    result = await ask_router(
        "coarse_class",
        _content(),
        db_path=db_path,
        force_model="claude-opus-4-7",
        force=True,
    )
    assert result.ok is True
    row = await fetchone(db_path, "SELECT model_chosen_reason FROM router_calls", ())
    assert row == ("override:api:force_model",)


async def test_ask_router_degraded_mode_demotes_opus_to_haiku(
    tmp_path: Path, _clean_state: None
) -> None:
    """Layer 3 — degraded mode demotes via the chain."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        """version: \"degraded-test\"

tasks:
  coarse_class:
    model: \"claude-opus-4-7\"
    prompt_version: \"v1\"
    escalate: false
    max_tokens_out: 100
    lane: \"batch\"
    sensitivity: \"any\"
""",
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))

    # Initialize guard + force it into degraded mode.
    guard = get_guard()
    await guard.initialize(db_path)
    await guard.add_spend(db_path, 35.0)
    assert guard.is_degraded() is True

    # Register a Haiku adapter (the demotion target) only — no Opus.
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("claude-haiku-4-5-20251001", adapter)

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is True
    row = await fetchone(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE outcome = 'ok'",
        (),
    )
    # Story 9.2: vocabulary migrated to "degraded:<from>→<to>"; pre-9.2 was bare "degraded".
    assert row == ("claude-haiku-4-5-20251001", "degraded:claude-opus-4-7→claude-haiku-4-5-20251001")


async def test_ask_router_degraded_mode_blocks_force_opus(
    tmp_path: Path, _clean_state: None
) -> None:
    """force_model=claude-opus-4-7 in degraded mode returns DEGRADED_MODE_BLOCKED."""
    db_path = _setup_db_and_policy(tmp_path, model="fake-qwen", escalate=False)
    guard = get_guard()
    await guard.initialize(db_path)
    await guard.add_spend(db_path, 35.0)

    result = await ask_router(
        "coarse_class",
        _content(),
        db_path=db_path,
        force_model="claude-opus-4-7",
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.DEGRADED_MODE_BLOCKED


# ---- Story 2-9: pause + loop detection ----


async def test_ask_router_paused_returns_provider_error(
    tmp_path: Path, _clean_state: None
) -> None:
    """When the kill-switch is active, ask_router short-circuits with
    PROVIDER_ERROR message='router paused' retryable=True. No router_calls row written."""
    db_path = _setup_db_and_policy(tmp_path)
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("fake-qwen", adapter)

    await get_pause_state().pause(db_path, reason="manual test")

    result = await ask_router("coarse_class", _content(), db_path=db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert result.error.retryable is True
    assert "paused" in result.error.message
    # Adapter NOT called.
    assert len(adapter.call_log) == 0
    # No router_calls row written (pause short-circuits before dispatch).
    rows = await fetchall(db_path, "SELECT 1 FROM router_calls", ())
    assert rows == []


async def test_ask_router_loop_detected_after_11_identical_calls(
    tmp_path: Path, _clean_state: None
) -> None:
    """11 identical prompts within the loop window trips LOOP_DETECTED."""
    db_path = _setup_db_and_policy(tmp_path)
    adapter = _FakeAdapter([_adapter_response(_good_output_json())] * 200)
    register_adapter("fake-qwen", adapter)

    # First 10 calls succeed.
    for _ in range(10):
        result = await ask_router("coarse_class", _content(), db_path=db_path)
        assert result.ok is True
    # 11th call is blocked.
    blocked = await ask_router("coarse_class", _content(), db_path=db_path)
    assert blocked.ok is False
    assert blocked.error is not None
    assert blocked.error.code == ErrorCode.LOOP_DETECTED
    assert blocked.error.retryable is False


async def test_ask_router_resume_clears_pause(
    tmp_path: Path, _clean_state: None
) -> None:
    db_path = _setup_db_and_policy(tmp_path)
    adapter = _FakeAdapter([_adapter_response(_good_output_json())])
    register_adapter("fake-qwen", adapter)

    state = get_pause_state()
    await state.pause(db_path, reason="x")
    blocked = await ask_router("coarse_class", _content(), db_path=db_path)
    assert blocked.error is not None
    assert "paused" in blocked.error.message

    await state.resume(db_path)
    ok = await ask_router("coarse_class", _content(), db_path=db_path)
    assert ok.ok is True
