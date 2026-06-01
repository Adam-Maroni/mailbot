"""Core Router orchestration per Story 2-4.

``ask_router`` is the single agent-facing LLM entry point. Every Router call
in the system flows through here. The function implements the layered
failure chain (timeout → schema validation → single retry with stricter
prompt → escalate-to-next-tier or return structured error) and guarantees a
``router_calls`` audit row via the ``finally`` block — even on uncaught
exceptions.

Story 2-4 ships this in isolation. Story 2-5 will wrap dispatch in lane
queues; Story 2-7 will wrap it in response-cache lookup; Story 2-8 will gate
it with the budget guard; Story 2-9 will gate it with the kill-switch.
Each later story bolts onto a specific seam declared here.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import EMAIL_SENSITIVITY_SELECT
from mailbot_api.observability.audit import RouterCallRow, record_router_call
from mailbot_api.prompts import PromptResolutionError, resolve_prompt
from mailbot_api.router.budget import (
    PER_CALL_REFUSAL_THRESHOLD_USD,
    demote_model,
    get_guard,
)
from mailbot_api.router.errors import (
    ErrorCode,
    RouterError,
    RouterResult,
    sanitize_error,
)
from mailbot_api.router.escalation import next_tier
from mailbot_api.router.lanes import acquire_provider_slot
from mailbot_api.router.limits import enforce_rate_limit, get_loop_detector
from mailbot_api.router.models import (
    AdapterProviderError,
    AdapterResponse,
    AdapterTimeout,
)
from mailbot_api.router.pause import get_pause_state
from mailbot_api.router.policy import PolicyTable, snapshot_for_dispatch
from mailbot_api.router.pricing import estimate_cost_usd
from mailbot_api.router.registry import get_adapter
from mailbot_api.router.response_cache import (
    compute_cache_key,
)
from mailbot_api.router.response_cache import (
    insert as response_cache_insert,
)
from mailbot_api.router.response_cache import (
    lookup as response_cache_lookup,
)

_STRICTER_PROMPT_PREFIX = (
    "Your previous reply was not valid JSON matching the schema. "
    "Reply only with valid JSON matching this schema: {schema_dump}\n\n"
)

# Story 3-3 AC-5: API-bound model detection for the precondition layer.
# Matches the Anthropic model id prefix family (haiku / opus / sonnet variants).
# Local-only models (Qwen `qwen2.5:*`, `nomic-embed-text`) do NOT match — they
# are exempt from the SENSITIVITY_BLOCKS_API gate because sensitive bodies CAN
# flow to local LLMs per FR-2.5.
_API_BOUND_MODEL_RE = re.compile(r"^claude-(haiku|opus|sonnet)\b")


def _stricter_user_template(original: str, output_schema: type[BaseModel]) -> str:
    schema_dump = json.dumps(output_schema.model_json_schema(), separators=(",", ":"))
    return _STRICTER_PROMPT_PREFIX.format(schema_dump=schema_dump) + original


async def _maybe_cache_result(
    *,
    db_path: str,
    policy_entry: Any,
    cache_key: str,
    task_type: str,
    model: str,
    parsed: BaseModel,
    cost_usd: float,
) -> None:
    """Story 2-7: write a successful result to response_cache iff caching
    is enabled for this task (TTL > 0). Failures are swallowed — a cache
    write failure must not bubble out and clobber a successful Router call.
    """
    ttl = int(getattr(policy_entry, "response_cache_ttl_seconds", 0))
    if ttl <= 0:
        return
    try:
        await response_cache_insert(
            db_path,
            cache_key=cache_key,
            task_type=task_type,
            model=model,
            result_json=parsed.model_dump_json(),
            cost_usd=cost_usd,
            ttl_seconds=ttl,
        )
    except Exception as exc:  # noqa: BLE001 — cache loss acceptable, masking is not
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "response cache insert failed",
            extra={"event": "response_cache.insert.failed", "exc_type": type(exc).__name__},
        )


async def _record(
    *,
    db_path: str,
    task_type: str,
    prompt_version: str,
    model_chosen: str,
    model_chosen_reason: str,
    tokens_in: int,
    tokens_out: int,
    cached_tokens_in: int,
    cost_usd_estimated: float,
    latency_ms: int,
    outcome: str,
    caller_verb: str | None,
    caller_origin: str,
    email_id: str | None,
) -> None:
    row = RouterCallRow(
        task_type=task_type,
        prompt_version=prompt_version,
        model_chosen=model_chosen,
        model_chosen_reason=model_chosen_reason,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cached_tokens_in=cached_tokens_in,
        cost_usd_estimated=cost_usd_estimated,
        latency_ms=latency_ms,
        outcome=cast(Literal["ok", "retry_recovered", "escalated", "failed"], outcome),
        caller_verb=caller_verb,
        caller_origin=caller_origin,
        email_id=email_id,
    )
    await record_router_call(row, db_path=db_path)


async def ask_router(
    task_type: str,
    content: dict[str, Any],
    *,
    db_path: str,
    force_model: str | None = None,
    max_cost_usd: float | None = None,  # noqa: ARG001 — wired in Story 2-9 anomaly hooks
    force: bool = False,
    caller_origin: str = "unknown-internal",
    caller_verb: str | None = None,
    email_id: str | None = None,
) -> RouterResult:
    """The single agent-facing LLM entry point. See module docstring.

    Story 2-8 additions:
      * ``force`` — bypass Layer 4 per-call refusal threshold ($0.20).
        Logged with ``model_chosen_reason="force_override"`` on dispatch.
      * Degraded mode (Layer 3) demotes opus→haiku→qwen on every call.
      * ``force_model="claude-opus-4-7"`` in degraded mode returns
        DEGRADED_MODE_BLOCKED unless a future confirmation-token flow lifts
        it (Epic 5 wires that).

    Story 2-9 additions:
      * Pause kill-switch — if ``get_pause_state().is_paused()``, return
        ``RouterError(code=PROVIDER_ERROR, message="router paused",
        retryable=True)`` immediately. In-flight calls finish normally.
      * Loop detector — same prompt hash > 10x in 5 min returns
        ``RouterError(code=LOOP_DETECTED)``.
    """

    # Story 2-9: kill-switch. Pause check fires first so a paused router
    # short-circuits ALL incoming calls before any other work.
    if get_pause_state().is_paused():
        return RouterResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="router paused",
                retryable=True,
            ),
        )

    # Capture the dispatch-time policy snapshot per AR-D11-2 race semantics.
    try:
        policy: PolicyTable = snapshot_for_dispatch()
    except RuntimeError as exc:
        # Policy not loaded — programmer error, but surface as structured data.
        return RouterResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=sanitize_error(exc),
                retryable=False,
            ),
        )

    policy_entry = policy.tasks.get(task_type)
    if policy_entry is None:
        msg = f"task_type not in policy: {task_type}"
        return RouterResult(
            ok=False,
            error=RouterError(code=ErrorCode.PROVIDER_ERROR, message=msg, retryable=False),
        )

    # Resolve prompt module.
    try:
        prompt = resolve_prompt(task_type, policy_entry.prompt_version)
    except PromptResolutionError as exc:
        return RouterResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=sanitize_error(exc),
                retryable=False,
            ),
        )

    # Resolve model.
    if force_model is not None:
        model = force_model
        model_chosen_reason = "force_override" if force else "override"
    else:
        model = policy_entry.model
        model_chosen_reason = "policy"

    # Story 2-8 Layer 3 — degraded mode gate.
    guard = get_guard()
    if guard.is_degraded():
        if force_model == "claude-opus-4-7":
            # Block force-opus in degraded mode without a confirmation token.
            # Token mint flow lands in Epic 5; for now the error path is what's tested.
            return RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.DEGRADED_MODE_BLOCKED,
                    message="degraded mode active; force_model=claude-opus-4-7 requires confirmation token",
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
        demoted = demote_model(model)
        if demoted != model:
            model = demoted
            model_chosen_reason = "degraded"

    # Story 3-3 AC-5: FR-2.3 hard invariant — sensitivity precondition layer.
    # Applies to every email-scoped Router call EXCEPT sensitivity_class itself
    # (which IS the gate). Ad-hoc Router calls with email_id=None (Hermes-aux
    # compression, cache-warmer, sender-reputation, etc.) bypass the gate.
    #
    # No router_calls row is written when the gate refuses — the precondition
    # is a routing-side decision, not a dispatch outcome. The audit table
    # captures actual provider interaction.
    #
    # TODO Epic 4: accept a `confirmation_token` kwarg and validate it here so
    # the SENSITIVITY_BLOCKS_API path admits Adam-confirmed sensitive-to-API
    # dispatches. Stub for now — every API-bound sensitive/confidential email
    # without a token refuses unconditionally.
    if task_type != "sensitivity_class" and email_id is not None:
        sensitivity_row = await fetchone(db_path, EMAIL_SENSITIVITY_SELECT, (email_id,))
        if sensitivity_row is None or sensitivity_row[1] is None:
            # Either the email row is missing entirely OR sensitivity_at is NULL.
            # In both cases the FR-2.3 invariant blocks dispatch.
            return RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.SENSITIVITY_NOT_CLASSIFIED,
                    message="email sensitivity must be classified before any other Router task",
                    retryable=False,
                ),
            )
        sensitivity_value, _sensitivity_at = sensitivity_row
        if sensitivity_value in ("sensitive", "confidential") and _API_BOUND_MODEL_RE.match(model) is not None:
            return RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.SENSITIVITY_BLOCKS_API,
                    message="email sensitivity blocks API dispatch; needs confirmation token",
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )

    return await _dispatch_with_failure_chain(
        task_type=task_type,
        prompt=prompt,
        policy_entry=policy_entry,
        content=content,
        model=model,
        model_chosen_reason=model_chosen_reason,
        db_path=db_path,
        caller_origin=caller_origin,
        caller_verb=caller_verb,
        email_id=email_id,
        force=force,
    )


async def _dispatch_with_failure_chain(
    *,
    task_type: str,
    prompt: Any,
    policy_entry: Any,
    content: dict[str, Any],
    model: str,
    model_chosen_reason: str,
    db_path: str,
    caller_origin: str,
    caller_verb: str | None,
    email_id: str | None,
    force: bool = False,
) -> RouterResult:
    """Inner dispatch + failure chain. Recursive on escalation."""

    tokens_in = 0
    tokens_out = 0
    cached_tokens_in = 0
    cost_usd = 0.0
    latency_ms = 0
    outcome: str = "failed"
    result: RouterResult

    try:
        # Resolve the adapter.
        try:
            adapter = get_adapter(model)
        except KeyError as exc:
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.PROVIDER_ERROR,
                    message=sanitize_error(exc),
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        # Story 2-5 rate-limit gate (before adapter dispatch, after resolution):
        # an exhausted lane or escalations bucket fails fast with RATE_LIMITED.
        # The audit row still records via the outer `finally` so observability
        # can correlate the breach with the calling task_type.
        breach_dim = enforce_rate_limit(policy_entry.lane, model_chosen_reason, caller_origin)
        if breach_dim is not None:
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.RATE_LIMITED,
                    message=f"rate limit breached: {breach_dim}",
                    retryable=True,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        try:
            user_msg = prompt.user_template.format(**content)
        except (KeyError, ValueError) as exc:
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.PROVIDER_ERROR,
                    message=f"prompt render failed: {sanitize_error(exc)}",
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        # ----- Story 2-9 loop detector -----
        # Same prompt hash > 10x in 5 min returns LOOP_DETECTED before any
        # adapter dispatch. Uses the same cache-key hash since it represents
        # the call's input identity. The check still records the timestamp
        # so the window count remains accurate for future calls.
        loop_hash_key = compute_cache_key(model, 0.0, prompt.system, user_msg)
        if get_loop_detector().check_and_record(loop_hash_key):
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.LOOP_DETECTED,
                    message=f"prompt hash {loop_hash_key[:8]} exceeded loop threshold",
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        # ----- Story 2-8 Layer 4 — per-call refusal threshold -----
        # Estimate based on rendered user_msg + max_tokens_out. Uses a rough
        # token-count proxy of len(text) // 4 (correct within ±25% for
        # English; sufficient for the $0.20 gate which is itself a coarse
        # safety net). Layer 4 always fires BEFORE the cache check so a
        # rogue caller can't trigger the cache-write path with an
        # ultra-expensive call.
        estimated_tokens_in = (len(prompt.system) + len(user_msg)) // 4
        estimated_cost = estimate_cost_usd(model, estimated_tokens_in, policy_entry.max_tokens_out)
        if estimated_cost > PER_CALL_REFUSAL_THRESHOLD_USD and not force:
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.PER_CALL_THRESHOLD_EXCEEDED,
                    message=(
                        f"estimated cost ${estimated_cost:.4f} exceeds "
                        f"per-call threshold ${PER_CALL_REFUSAL_THRESHOLD_USD:.2f}; "
                        f"pass force=True to override"
                    ),
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        # ----- Story 2-7: response cache lookup -----
        # The lookup runs unconditionally — if a row exists and is within
        # its stored TTL, return the cached result. Insertion is gated on
        # policy_entry.response_cache_ttl_seconds > 0, so unconfigured
        # tasks never produce cache entries; configured tasks see hits
        # bound by the stored ttl_seconds value.
        cache_key = compute_cache_key(model, 0.0, prompt.system, user_msg)
        cached = await response_cache_lookup(db_path, cache_key)
        if cached is not None:
            try:
                parsed_cached = prompt.output_schema.model_validate_json(str(cached["result_json"]))
            except (ValidationError, ValueError):
                # Cached payload no longer validates (schema rev?) — treat
                # as cache miss; the live dispatch will re-cache.
                parsed_cached = None
            if parsed_cached is not None:
                outcome = "ok"
                model_chosen_reason = "response_cache_hit"
                # cost_usd stays 0 on the audit row even though the original
                # dispatch cost money — the row reflects THIS call's cost.
                result = RouterResult(
                    ok=True,
                    output=parsed_cached,
                    cost_usd=0.0,
                    latency_ms=0,
                    tokens_in=0,
                    tokens_out=0,
                    cached_tokens_in=0,
                    model_used=f"{model}+response_cache",
                )
                return result

        # ----- First-attempt dispatch -----
        try:
            # Story 2-5: per-provider concurrency semaphore. Anthropic capped
            # at 4 concurrent; Ollama passes through (local server queues).
            async with acquire_provider_slot(model):
                response: AdapterResponse = await adapter.call(
                    system=prompt.system,
                    user=user_msg,
                    max_tokens_out=policy_entry.max_tokens_out,
                    temperature=0.0,
                )
        except AdapterTimeout as exc:
            tokens_in = tokens_out = cached_tokens_in = 0
            cost_usd = 0.0
            latency_ms = 0
            outcome = "failed"
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.TIMEOUT,
                    message=sanitize_error(exc),
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result
        except AdapterProviderError as exc:
            outcome = "failed"
            result = RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.PROVIDER_ERROR,
                    message=exc.sanitized_message,
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        tokens_in = response.tokens_in
        tokens_out = response.tokens_out
        cached_tokens_in = response.cached_tokens_in
        latency_ms = response.latency_ms
        cost_usd = estimate_cost_usd(model, tokens_in, tokens_out, cached_tokens_in)

        # Try schema validation.
        try:
            parsed = prompt.output_schema.model_validate_json(response.text)
            outcome = "ok"
            result = RouterResult(
                ok=True,
                output=parsed,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cached_tokens_in=cached_tokens_in,
                model_used=model,
            )
            # Story 2-7: cache successful first-attempt result.
            await _maybe_cache_result(
                db_path=db_path,
                policy_entry=policy_entry,
                cache_key=cache_key,
                task_type=task_type,
                model=model,
                parsed=parsed,
                cost_usd=cost_usd,
            )
            # Story 2-8: add to budget guard spend counters.
            await get_guard().add_spend(db_path, cost_usd)
            return result
        except (ValidationError, ValueError):
            pass  # fall through to retry

        # ----- Retry with stricter prompt -----
        stricter_user = _stricter_user_template(user_msg, prompt.output_schema)
        try:
            async with acquire_provider_slot(model):
                retry_response: AdapterResponse = await adapter.call(
                    system=prompt.system,
                    user=stricter_user,
                    max_tokens_out=policy_entry.max_tokens_out,
                    temperature=0.0,
                )
        except (AdapterTimeout, AdapterProviderError) as exc:
            # Retry-leg adapter failure → fall through to escalation/failure.
            retry_response = None  # type: ignore[assignment]
            retry_exc: BaseException | None = exc
        else:
            retry_exc = None

        if retry_exc is None and retry_response is not None:
            tokens_in += retry_response.tokens_in
            tokens_out += retry_response.tokens_out
            cached_tokens_in += retry_response.cached_tokens_in
            latency_ms += retry_response.latency_ms
            cost_usd += estimate_cost_usd(
                model,
                retry_response.tokens_in,
                retry_response.tokens_out,
                retry_response.cached_tokens_in,
            )
            try:
                parsed = prompt.output_schema.model_validate_json(retry_response.text)
                outcome = "retry_recovered"
                result = RouterResult(
                    ok=True,
                    output=parsed,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cached_tokens_in=cached_tokens_in,
                    model_used=model,
                )
                # Story 2-7: cache successful retry-leg result.
                await _maybe_cache_result(
                    db_path=db_path,
                    policy_entry=policy_entry,
                    cache_key=cache_key,
                    task_type=task_type,
                    model=model,
                    parsed=parsed,
                    cost_usd=cost_usd,
                )
                # Story 2-8: add to budget guard spend counters.
                await get_guard().add_spend(db_path, cost_usd)
                return result
            except (ValidationError, ValueError):
                pass

        # ----- Escalation -----
        if policy_entry.escalate:
            next_model = next_tier(model)
            if next_model is not None:
                # Recurse — note: a recursive call records its own row in its
                # own finally block. Combined with this call's row, the audit
                # log shows both attempts.
                #
                # Story 2-4 review fix HIGH: cap escalation depth at 1 hop.
                # We construct a shallow clone of the policy entry with
                # `escalate=False` so the recursive call's schema-validation
                # failure terminates at SCHEMA_VALIDATION_FAILED rather than
                # chaining qwen→haiku→opus and tripling costs.
                escalated_policy_entry = policy_entry.model_copy(update={"escalate": False})
                escalated = await _dispatch_with_failure_chain(
                    task_type=task_type,
                    prompt=prompt,
                    policy_entry=escalated_policy_entry,
                    content=content,
                    model=next_model,
                    model_chosen_reason=f"escalated_from_{model}",
                    db_path=db_path,
                    caller_origin=caller_origin,
                    caller_verb=caller_verb,
                    email_id=email_id,
                )
                if escalated.ok:
                    outcome = "escalated"
                    # Our own audit row reflects the failed first attempt;
                    # the escalated row is recorded by the recursive call.
                    result = escalated
                    return result
                # Escalation also failed.
                outcome = "failed"
                result = RouterResult(
                    ok=False,
                    error=RouterError(
                        code=ErrorCode.SCHEMA_VALIDATION_FAILED,
                        message="retry + escalation both failed schema validation",
                        retryable=False,
                        model_attempted=[model, next_model],
                    ),
                    model_used=model,
                )
                return result

        # ----- No escalation, or no next tier -----
        outcome = "failed"
        # Story 2-4 review fix MEDIUM: surface the retry-leg exception when
        # the retry path failed for an adapter reason rather than a second
        # schema validation. Without this, callers can't distinguish a
        # double-validation-fail from a retry-timeout.
        if retry_exc is not None:
            retry_failure_note = f"; retry leg raised {type(retry_exc).__name__}: {sanitize_error(retry_exc)}"
        else:
            retry_failure_note = "; retry also failed schema validation"
        result = RouterResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.SCHEMA_VALIDATION_FAILED,
                message=f"response failed schema validation{retry_failure_note}",
                retryable=False,
                model_attempted=[model],
            ),
            model_used=model,
        )
        return result

    except Exception as exc:  # noqa: BLE001 — AR-PAT-4 boundary catch-all
        outcome = "failed"
        result = RouterResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=sanitize_error(exc),
                retryable=False,
                model_attempted=[model],
            ),
            model_used=model,
        )
        return result
    finally:
        # Story 2-1 audit-loss-acceptable contract: record_router_call
        # swallows DB failures internally so this finally block is safe.
        await _record(
            db_path=db_path,
            task_type=task_type,
            prompt_version=policy_entry.prompt_version,
            model_chosen=model,
            model_chosen_reason=model_chosen_reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cached_tokens_in,
            cost_usd_estimated=cost_usd,
            latency_ms=latency_ms,
            outcome=outcome,
            caller_verb=caller_verb,
            caller_origin=caller_origin,
            email_id=email_id,
        )


# ---------------------------------------------------------------------------
# Story 3-4 — dispatch_embedding sibling helper.
# ---------------------------------------------------------------------------


class EmbeddingDispatchResult(BaseModel):
    """Return shape of ``dispatch_embedding`` (Story 3-4 AC-5).

    Parallel to ``RouterResult`` but tailored to embedding dispatch:
      * No ``output: BaseModel`` — embeddings don't have prompt OUTPUT_SCHEMAs.
      * Carries the raw vector + dim instead.
      * Carries cost telemetry (latency, tokens_in) but no cost_usd because
        local Ollama embedding cost is $0.00.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    vector: list[float] | None = None
    dim: int | None = None
    tokens_in: int = 0
    latency_ms: int = 0
    model_used: str = ""
    error: RouterError | None = None


# Sentinel: dispatch_embedding skips the schema-fail-retry path entirely.
# This outcome string flows into ``router_calls.outcome`` for embedding rows.
_EMBEDDING_OUTCOME_OK = "ok"
_EMBEDDING_OUTCOME_FAILED = "failed"


async def dispatch_embedding(
    *,
    text: str,
    db_path: str,
    email_id: str | None,
    caller_origin: str = "ingest-pipeline-embedding",
    caller_verb: str | None = None,
) -> EmbeddingDispatchResult:
    """Embedding-side sibling of ``ask_router`` (Story 3-4 AC-5).

    Why a sibling instead of widening ``ask_router``: embeddings have a
    different shape (no system/user prompt, no OUTPUT_SCHEMA, no schema-fail-
    retry, no escalation). Conflating them would pollute the chat-side
    failure chain. See story Dev Notes "Why a sibling dispatch_embedding".

    Honors:
      * Pause kill-switch (Story 2-9)
      * Policy snapshot lookup (Story 2-2)
      * FR-2.3 sensitivity precondition (Story 3-3) — sensitivity_at IS NULL
        on an email-scoped call → SENSITIVITY_NOT_CLASSIFIED.

    Does NOT apply:
      * SENSITIVITY_BLOCKS_API — embeddings are local-only per FR-2.5.
      * Budget guard / degraded mode — Ollama cost is $0.00; the guard is
        an Anthropic-side concern.
      * Lane scheduling / rate limits — embeddings use the batch lane via
        policy; per-call rate limiting is the Anthropic-side concern.
      * Schema-fail-retry / escalation — there is no schema.

    Writes a ``router_calls`` audit row at the end (success or failure).
    Errors-as-data per AR-PAT-4: never raises.
    """
    # Pause kill-switch.
    if get_pause_state().is_paused():
        return EmbeddingDispatchResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="router paused",
                retryable=True,
            ),
        )

    # Policy snapshot.
    try:
        policy: PolicyTable = snapshot_for_dispatch()
    except RuntimeError as exc:
        return EmbeddingDispatchResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=sanitize_error(exc),
                retryable=False,
            ),
        )

    policy_entry = policy.tasks.get("embedding")
    if policy_entry is None:
        return EmbeddingDispatchResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="task_type 'embedding' not in policy",
                retryable=False,
            ),
        )

    model = policy_entry.model
    prompt_version = policy_entry.prompt_version  # sentinel "v1"

    # FR-2.3 sensitivity precondition — only fires when an email_id is provided.
    # Note: dispatch_embedding does NOT apply SENSITIVITY_BLOCKS_API (the model
    # is local Ollama; FR-2.5 permits sensitive bodies to flow to local LLMs).
    if email_id is not None:
        sensitivity_row = await fetchone(db_path, EMAIL_SENSITIVITY_SELECT, (email_id,))
        if sensitivity_row is None or sensitivity_row[1] is None:
            return EmbeddingDispatchResult(
                ok=False,
                model_used=model,
                error=RouterError(
                    code=ErrorCode.SENSITIVITY_NOT_CLASSIFIED,
                    message="email sensitivity must be classified before any other Router task",
                    retryable=False,
                ),
            )

    # Resolve the adapter.
    try:
        adapter = get_adapter(model)
    except KeyError as exc:
        # Audit row + return error.
        await _record(
            db_path=db_path,
            task_type="embedding",
            prompt_version=prompt_version,
            model_chosen=model,
            model_chosen_reason="policy",
            tokens_in=0,
            tokens_out=0,
            cached_tokens_in=0,
            cost_usd_estimated=0.0,
            latency_ms=0,
            outcome=_EMBEDDING_OUTCOME_FAILED,
            caller_verb=caller_verb,
            caller_origin=caller_origin,
            email_id=email_id,
        )
        return EmbeddingDispatchResult(
            ok=False,
            model_used=model,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=sanitize_error(exc),
                retryable=False,
            ),
        )

    # Dispatch via adapter.embed. The adapter raises AdapterTimeout /
    # AdapterProviderError; we catch and translate at this boundary.
    embed = getattr(adapter, "embed", None)
    if embed is None or not callable(embed):
        await _record(
            db_path=db_path,
            task_type="embedding",
            prompt_version=prompt_version,
            model_chosen=model,
            model_chosen_reason="policy",
            tokens_in=0,
            tokens_out=0,
            cached_tokens_in=0,
            cost_usd_estimated=0.0,
            latency_ms=0,
            outcome=_EMBEDDING_OUTCOME_FAILED,
            caller_verb=caller_verb,
            caller_origin=caller_origin,
            email_id=email_id,
        )
        return EmbeddingDispatchResult(
            ok=False,
            model_used=model,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=(
                    f"adapter for model={model!r} does not expose an "
                    f"embed(text) method — adapter is not an embedding adapter"
                ),
                retryable=False,
            ),
        )

    try:
        embedding_response = await embed(text)
    except (AdapterTimeout, AdapterProviderError) as exc:
        code = ErrorCode.TIMEOUT if isinstance(exc, AdapterTimeout) else ErrorCode.PROVIDER_ERROR
        await _record(
            db_path=db_path,
            task_type="embedding",
            prompt_version=prompt_version,
            model_chosen=model,
            model_chosen_reason="policy",
            tokens_in=0,
            tokens_out=0,
            cached_tokens_in=0,
            cost_usd_estimated=0.0,
            latency_ms=0,
            outcome=_EMBEDDING_OUTCOME_FAILED,
            caller_verb=caller_verb,
            caller_origin=caller_origin,
            email_id=email_id,
        )
        return EmbeddingDispatchResult(
            ok=False,
            model_used=model,
            error=RouterError(
                code=code,
                message=sanitize_error(exc),
                retryable=False,
                model_attempted=[model],
            ),
        )

    # Success path. Embedding cost is $0.00 (local Ollama).
    await _record(
        db_path=db_path,
        task_type="embedding",
        prompt_version=prompt_version,
        model_chosen=model,
        model_chosen_reason="policy",
        tokens_in=embedding_response.tokens_in,
        tokens_out=0,
        cached_tokens_in=0,
        cost_usd_estimated=0.0,
        latency_ms=embedding_response.latency_ms,
        outcome=_EMBEDDING_OUTCOME_OK,
        caller_verb=caller_verb,
        caller_origin=caller_origin,
        email_id=email_id,
    )

    return EmbeddingDispatchResult(
        ok=True,
        vector=embedding_response.vector,
        dim=embedding_response.dim,
        tokens_in=embedding_response.tokens_in,
        latency_ms=embedding_response.latency_ms,
        model_used=model,
    )


__all__ = ["EmbeddingDispatchResult", "ask_router", "dispatch_embedding"]
