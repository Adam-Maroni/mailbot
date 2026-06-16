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
import logging
import re
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import EMAIL_SENSITIVITY_SELECT
from mailbot_api.observability.audit import RouterCallRow, record_router_call
from mailbot_api.prompts import PromptResolutionError, resolve_prompt
from mailbot_api.router.audit_vocab import (
    ModelChosenReason,
    degraded_mode_demotion,
    policy_default,
    policy_escalation,
)
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
from mailbot_api.router.oneshot import (
    _consume_oneshot_override,
    _get_active_oneshot_override,
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

_logger = logging.getLogger(__name__)

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
        _logger.warning(
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
    sensitivity_grant_id: str | None = None,
    sensitivity_grant_minted_at: str | None = None,
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
        sensitivity_grant_id=sensitivity_grant_id,
        sensitivity_grant_minted_at=sensitivity_grant_minted_at,
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
    confirmation_token: str | None = None,
) -> RouterResult:
    """The single agent-facing LLM entry point. See module docstring.

    Story 2-8 additions:
      * ``force`` — bypass Layer 4 per-call refusal threshold ($0.20).
        Logged with ``model_chosen_reason=ModelChosenReason.OVERRIDE_API`` on
        dispatch (Story 9.2 vocabulary; pre-9.2 distinguished force=True as
        "force_override" but the audit row no longer separates them).
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

    # Story 9-3 — `/model <model>` one-shot override peek.
    # AC-2: if `force_model is None`, lift the active override into
    # `force_model` for the remainder of this call. PEEK only — do NOT
    # consume yet. Consume happens at the effective-dispatch site after
    # all gates pass (sensitivity / budget / degraded). Gate-refused paths
    # leave the override armed within its TTL per AC-3.
    # If `force_model is not None` was passed explicitly by the API caller,
    # the explicit value wins and the one-shot stays armed for the next call.
    _oneshot_engaged: bool = False
    if force_model is None:
        _oneshot_active = _get_active_oneshot_override()
        if _oneshot_active is not None:
            force_model = _oneshot_active.model
            _oneshot_engaged = True

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
    # Story 9.2: force_override and override (force=True vs force=False with
    # force_model set) both collapse to OVERRIDE_API per AC-1's vocabulary
    # consolidation. The `force` boolean still gates degraded-mode behavior
    # below — only the audit string is unified.
    # Story 9-3: if the one-shot peek lifted an override into force_model
    # (`_oneshot_engaged`), the audit reason is OVERRIDE_SLASH_ONE_SHOT
    # instead of OVERRIDE_API — distinguishes Adam's chat-side `/model`
    # intent from a direct API force_model from a non-chat caller.
    if force_model is not None:
        model = force_model
        if _oneshot_engaged:
            model_chosen_reason = ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value
        else:
            model_chosen_reason = ModelChosenReason.OVERRIDE_API.value
    else:
        model = policy_entry.model
        model_chosen_reason = policy_default(task_type)

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
            model_chosen_reason = degraded_mode_demotion(from_model=model, to_model=demoted)
            model = demoted

    # Story 3-3 AC-5: FR-2.3 hard invariant — sensitivity precondition layer.
    # Story 4-7: extended with confirmation_token handshake for sensitive emails.
    #
    # Applies to every email-scoped Router call EXCEPT sensitivity_class itself
    # (which IS the gate). Ad-hoc Router calls with email_id=None bypass the gate.
    #
    # Token-handshake semantics (Story 4-7):
    #   - sensitive + API-bound model + no token → SENSITIVITY_BLOCKS_API (handshake required)
    #   - sensitive + API-bound model + invalid/expired/consumed token → NEEDS_SENSITIVITY_CONFIRMATION
    #   - sensitive + API-bound model + valid token → consume → dispatch + populate grant_id on router_calls
    #   - confidential + API-bound model → SENSITIVITY_BLOCKS_API regardless of token (NFR-PRIV-2)
    #
    # No router_calls row is written when the gate refuses — the precondition
    # is a routing-side decision, not a dispatch outcome. On consume-success,
    # the grant_id is captured into `_sensitivity_grant_id` and threaded
    # through to `record_router_call` so the audit row carries it.
    _sensitivity_grant_id: str | None = None
    _sensitivity_grant_minted_at: str | None = None
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
        if sensitivity_value == "confidential" and _API_BOUND_MODEL_RE.match(model) is not None:
            # Per NFR-PRIV-2: confidential admits no override even with a token.
            return RouterResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.SENSITIVITY_BLOCKS_API,
                    message="confidential emails admit no API override",
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
        if sensitivity_value == "sensitive" and _API_BOUND_MODEL_RE.match(model) is not None:
            # Token handshake — Story 4-7.
            if confirmation_token is None:
                return RouterResult(
                    ok=False,
                    error=RouterError(
                        code=ErrorCode.SENSITIVITY_BLOCKS_API,
                        message="sensitive email requires per-session confirmation token to escalate to API",
                        retryable=False,
                        model_attempted=[model],
                    ),
                    model_used=model,
                )
            from mailbot_api.actions.sensitivity_tokens import consume as _consume_token  # noqa: PLC0415
            # CR-4-7-3(a): defensive wrap so any future change to consume() that
            # makes it raise (e.g., a DB-backed registry) doesn't leak the
            # confirmation_token value into a traceback. The exception type and
            # message are logged WITHOUT the token value; the caller gets
            # NEEDS_SENSITIVITY_CONFIRMATION as if the token were invalid.
            try:
                consume_result = _consume_token(confirmation_token, email_id, task_type)
            except Exception as exc:  # noqa: BLE001 — guard against token-in-traceback
                _logger.exception(
                    "sensitivity token consume crashed; refusing dispatch",
                    extra={
                        "event": "sensitivity.token.consume_crash",
                        "email_id": email_id,
                        "task_type": task_type,
                        "exception_type": type(exc).__name__,
                    },
                )
                consume_result = None
            if consume_result is None:
                return RouterResult(
                    ok=False,
                    error=RouterError(
                        code=ErrorCode.NEEDS_SENSITIVITY_CONFIRMATION,
                        message=(
                            "confirmation token invalid, expired, already "
                            "consumed, or mismatched (email_id/task_type)"
                        ),
                        retryable=False,
                        model_attempted=[model],
                    ),
                    model_used=model,
                )
            # CR-4-7-6: consume() returns (grant_id, minted_at) so the audit
            # row records the real mint time (not consume time, which could
            # drift up to 10 minutes — the TTL window).
            grant_id, minted_at = consume_result
            _sensitivity_grant_id = grant_id
            _sensitivity_grant_minted_at = minted_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        elif sensitivity_value == "normal" and confirmation_token is not None:
            # CR-4-7-5: a token passed for a normal email is unexpected.
            # The call is valid (no token needed), but the agent's behavior
            # is worth observing — either the agent is confused about the
            # email's sensitivity, or sensitivity was reclassified mid-flow.
            # Do NOT log the token value itself.
            _logger.warning(
                "confirmation_token passed for normal email; ignoring",
                extra={
                    "event": "sensitivity.token.unexpected",
                    "email_id": email_id,
                    "task_type": task_type,
                    "sensitivity": sensitivity_value,
                },
            )

    # Story 9-3 — consume happens INSIDE _dispatch_with_failure_chain
    # after the $0.20 per-call budget gate. Sensitivity / degraded gates
    # fire ABOVE this point (in ask_router), so they leave the override
    # armed automatically. Budget gate fires INSIDE the dispatch chain;
    # the `_oneshot_engaged` flag is threaded through so the dispatch
    # chain can do the consume itself once all its gates pass.
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
        sensitivity_grant_id=_sensitivity_grant_id,
        sensitivity_grant_minted_at=_sensitivity_grant_minted_at,
        _oneshot_engaged=_oneshot_engaged,
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
    sensitivity_grant_id: str | None = None,
    sensitivity_grant_minted_at: str | None = None,
    _oneshot_engaged: bool = False,
) -> RouterResult:
    """Inner dispatch + failure chain. Recursive on escalation.

    Story 9-3: `_oneshot_engaged` indicates that the outer `ask_router`
    lifted a one-shot override into `force_model`. The consume happens
    inside this function AFTER the $0.20 per-call budget gate so that
    PER_CALL_THRESHOLD_EXCEEDED refusals leave the override armed within
    its TTL per AC-3.
    """

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

        # Story 9-3 — consume the one-shot override now that ALL gates
        # (sensitivity in ask_router, budget here) have passed. From this
        # point forward the dispatch is committed: cache lookup, adapter
        # call, failure chain. AC-3 invariant satisfied: any gate-refused
        # path above leaves the override armed within its TTL.
        if _oneshot_engaged:
            _consume_oneshot_override()

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
                # Story 9-3 CR-F1: when the one-shot override is engaged AND
                # we hit the response cache, Adam's `/model` intent must NOT
                # be hidden behind CACHE_HIT in the audit log. Preserve the
                # OVERRIDE_SLASH_ONE_SHOT reason so the row reflects WHY the
                # dispatch happened (Adam's override), not HOW it was
                # served (cache). The override IS consumed even on cache
                # hit — a cache-hit IS actual use of Adam's intent.
                if not _oneshot_engaged:
                    model_chosen_reason = ModelChosenReason.CACHE_HIT.value
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
                # CR-4-7-1: forward the sensitivity-grant audit columns so
                # the escalated leg's router_calls row is forensically linked
                # to the original token consume. Without this, a sensitive-email
                # dispatch that escalates leaves the escalated row's
                # sensitivity_grant_id NULL — breaking the "which API calls
                # were made for sensitive email X" forensic query.
                # Story 9-3 CR-F7: `_oneshot_engaged` is intentionally NOT
                # forwarded to the recursive escalated call. Reasoning:
                # the outer call already consumed the override at this point
                # in the call stack (consume site is BEFORE the failure
                # chain reaches escalation). The escalated leg's row
                # should carry `policy:escalation:<from>→<to>` (the
                # routing-decision reason for THIS row), NOT the original
                # OVERRIDE_SLASH_ONE_SHOT. Forwarding `_oneshot_engaged=True`
                # here would (a) cause a double-consume attempt on the
                # already-cleared slot (a no-op but logic-misleading) AND
                # (b) overwrite the policy:escalation reason in the
                # cache-hit branch. Default to False is correct.
                escalated = await _dispatch_with_failure_chain(
                    task_type=task_type,
                    prompt=prompt,
                    policy_entry=escalated_policy_entry,
                    content=content,
                    model=next_model,
                    model_chosen_reason=policy_escalation(from_model=model, to_model=next_model),
                    db_path=db_path,
                    caller_origin=caller_origin,
                    caller_verb=caller_verb,
                    email_id=email_id,
                    sensitivity_grant_id=sensitivity_grant_id,
                    sensitivity_grant_minted_at=sensitivity_grant_minted_at,
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
            sensitivity_grant_id=sensitivity_grant_id,
            sensitivity_grant_minted_at=sensitivity_grant_minted_at,
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
            model_chosen_reason=policy_default("embedding"),
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
            model_chosen_reason=policy_default("embedding"),
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
            model_chosen_reason=policy_default("embedding"),
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
        model_chosen_reason=policy_default("embedding"),
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


# ---------------------------------------------------------------------------
# Story 6-9 (F11 closure) — dispatch_tool_call sibling.
#
# Tool-calling sibling of ask_router. Carries the OpenAI-shape messages +
# tools through to the adapter's call_with_tools method and returns an
# OpenAI-shape ToolCallResult. Shares the sensitivity-precondition, pause,
# budget-guard, and audit primitives with ask_router but owns its own
# dispatch path:
#   * No schema-validation retry leg (tool-call responses don't have schema
#     failure semantics)
#   * No escalation chain (tool support is per-adapter; escalation to a
#     non-tool-supporting model is meaningless)
#   * No response cache (tool args may carry per-email state)
#
# See 6-9-design-decision.md for the full design rationale.
# ---------------------------------------------------------------------------


_TOOL_CALL_TASK_TYPE = "chat_completions_tool_call"
_TOOL_CALL_PROMPT_VERSION = "v1"


def _resolve_email_ids_from_messages(messages: list[dict[str, Any]]) -> set[str]:
    """Story 6-20 (F28 closure) — resolve the union of email_ids referenced
    anywhere in a chat-completions request payload, by walking:

      (a) every assistant-role message's ``tool_calls[].function.arguments``
          (a JSON string per OpenAI spec), AND
      (b) every tool-role message's ``content`` (a JSON string when the
          tool result is dict-shaped, as produced by MCP verbs).

    Collects every value at a ``"email_id"`` key at any nesting depth.
    Returns a deduped set; iteration of nested dicts/lists is exhaustive.

    Malformed JSON in either source is silently skipped — a structured
    DEBUG log fires so the caller-side bug is recoverable, but the
    sensitivity gate's concern is solely whether we MISSED an email_id
    reference. The downstream tool-dispatch will surface the malformed
    argument as its own error.

    Pure function (no DB I/O). Tested via the AC-5 unit tests in
    ``tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py``.
    """
    found: set[str] = set()

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "email_id" and isinstance(v, str):
                    found.add(v)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for idx, m in enumerate(messages):
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "assistant":
            tool_calls = m.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                continue
            for tc_idx, tc in enumerate(tool_calls):
                # Accept either dict shape (post-_chat_completions_tools_dispatch
                # model_dump) OR Pydantic model shape (defensive — direct
                # callers may pass models).
                if isinstance(tc, dict):
                    fn = tc.get("function")
                    args_str = fn.get("arguments") if isinstance(fn, dict) else None
                else:
                    fn = getattr(tc, "function", None)
                    args_str = getattr(fn, "arguments", None) if fn is not None else None
                if not isinstance(args_str, str):
                    continue
                try:
                    _walk(json.loads(args_str))
                except (json.JSONDecodeError, ValueError) as exc:
                    _logger.debug(
                        "dispatch_tool_call arg parse failed",
                        extra={
                            "event": "dispatch_tool_call.arg_parse_failed",
                            "message_index": idx,
                            "tool_call_index": tc_idx,
                            "exception_type": type(exc).__name__,
                        },
                    )
        elif role == "tool":
            content = m.get("content")
            if not isinstance(content, str):
                continue
            try:
                _walk(json.loads(content))
            except (json.JSONDecodeError, ValueError) as exc:
                _logger.debug(
                    "dispatch_tool_call tool-result parse failed",
                    extra={
                        "event": "dispatch_tool_call.arg_parse_failed",
                        "message_index": idx,
                        "exception_type": type(exc).__name__,
                    },
                )
    return found


def _redact_tool_args_for_audit(arguments_json: str) -> str:
    """Apply the same redaction rules as `sanitize_error` to a tool-call
    arguments JSON string before persisting to the audit row.

    Tool arguments can contain email subject/body fragments, OAuth tokens
    (if the agent confuses scopes), or other sensitive payload. Pipe
    through the shared redactor before write.
    """
    from mailbot_api.observability._redaction import (  # noqa: PLC0415
        BEARER_TOKEN_RE,
        SECRET_FILE_RE,
        SK_KEY_RE,
        URL_TOKEN_QUERY_RE,
    )
    redacted = BEARER_TOKEN_RE.sub("[REDACTED_BEARER]", arguments_json)
    redacted = SK_KEY_RE.sub("[REDACTED_SK_KEY]", redacted)
    redacted = URL_TOKEN_QUERY_RE.sub(r"\1[REDACTED_QUERY_TOKEN]", redacted)
    redacted = SECRET_FILE_RE.sub("[REDACTED_PATH]", redacted)
    return redacted


def _build_tool_calls_summary(tool_calls: list[Any]) -> str:
    """Compact JSON summary of dispatched tool_calls for the audit row.

    Shape: `[{"name": "<tool>", "input_redacted": "<redacted args JSON>"}, ...]`
    """
    summary = [
        {
            "name": tc.function.name,
            "input_redacted": _redact_tool_args_for_audit(tc.function.arguments),
        }
        for tc in tool_calls
    ]
    return json.dumps(summary, separators=(",", ":"))


async def dispatch_tool_call(
    *,
    messages: list[dict[str, Any]],
    tools: list[Any],  # list[ChatCompletionToolDef] — quoted to avoid forward ref
    tool_choice: Any = None,
    model: str,
    is_force_override: bool = False,
    max_tokens_out: int = 1024,
    temperature: float = 0.0,
    db_path: str,
    caller_origin: str = "unknown-external",
    caller_verb: str | None = None,
    email_id: str | None = None,
    confirmation_token: str | None = None,
) -> Any:  # ToolCallResult — quoted to avoid circular import at module load
    """Story 6-9 (F11 closure) — OpenAI-shape tool-call dispatcher.

    The tool-calling sibling of `ask_router`. Translates the OpenAI-shape
    `messages` + `tools` to the adapter, dispatches via the adapter's
    `call_with_tools` method, and returns an OpenAI-shape `ToolCallResult`
    carrying any `tool_calls` the model produced.

    Honors:
      * Pause kill-switch (Story 2-9)
      * Sensitivity precondition (Story 3-3, Story 4-7, Story 6-20) —
        gating on the UNION of (a) the legacy `email_id` parameter and
        (b) every `email_id` resolved from `messages` (assistant
        `tool_calls[].function.arguments` JSON + tool-role `content` JSON,
        at any nesting depth). Iteration order is `sorted(audit_ids)` so
        refusal messages and audit-row sequences are deterministic.

        Single-token v1 contract (Story 6-20): the supplied
        `confirmation_token` consumes against the FIRST sensitive
        email_id in sorted order; any subsequent sensitive id falls
        through to `SENSITIVITY_BLOCKS_API`. Multi-token shape
        (`confirmation_tokens: list[str]`) is the deferred v2 expansion.
        `confidential` admits NO override even with a token (NFR-PRIV-2).
      * Budget guard (Story 2-8) — per-call refusal threshold + degraded-mode
        demotion. NOTE: degraded mode demotes to qwen, which doesn't support
        tools — the call will surface as `tools_unsupported` after demotion.
        This is intentional: degraded mode is a cost-shedding safety net,
        not a feature-preservation layer.
      * Audit row (Story 2-1) — populated with `tool_calls_count` +
        redacted `tool_calls_summary` for forensic queries

    Does NOT apply (vs. `ask_router`):
      * Schema-validation retry leg
      * Escalation chain
      * Response cache (tool args may carry per-email state)
    """
    from mailbot_api.router.errors import (  # noqa: PLC0415
        ErrorCode,
        RouterError,
        ToolCallResult,
        sanitize_error,
    )

    # ---- Pause kill-switch ----
    if get_pause_state().is_paused():
        return ToolCallResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="router paused",
                retryable=True,
            ),
        )

    # ---- Policy snapshot ----
    try:
        policy: PolicyTable = snapshot_for_dispatch()
    except RuntimeError as exc:
        return ToolCallResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=sanitize_error(exc),
                retryable=False,
            ),
        )

    # Tool-call dispatch doesn't tie to a prompt module — it has its own
    # synthetic task_type for audit purposes. But it DOES need a lane for
    # rate-limit / semaphore accounting; we synthesize one from the
    # hermes_aux policy entry (the closest sibling — both Anthropic-bound,
    # both Hermes-driven, both external-facing).
    policy_entry = policy.tasks.get("hermes_aux")
    if policy_entry is None:
        return ToolCallResult(
            ok=False,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="task_type 'hermes_aux' not in policy (used as the lane proxy for tool-call dispatch)",
                retryable=False,
            ),
        )

    # CR-2 (Story 6-9 review 2026-06-04): default to policy so policy-
    # resolved dispatches don't pollute cost-attribution queries that filter
    # by reason. Only flip to OVERRIDE_API when the endpoint signaled this is
    # an explicit user override (via is_force_override=True).
    # Story 9.2: vocabulary migrated to closed-set enum (see audit_vocab.py).
    model_chosen_reason: str = (
        ModelChosenReason.OVERRIDE_API.value
        if is_force_override
        else policy_default("hermes_aux")
    )

    # ---- Story 2-8 Layer 3 — degraded mode gate ----
    guard = get_guard()
    if guard.is_degraded():
        # CR-4 (Story 6-9 review 2026-06-04): only block opus when it was
        # explicitly user-forced. A policy-resolved opus (unlikely today but
        # possible if hermes_aux policy flips) should be demoted like any
        # other model rather than refused — matches ask_router semantics.
        if model == "claude-opus-4-7" and is_force_override:
            return ToolCallResult(
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
            model_chosen_reason = degraded_mode_demotion(from_model=model, to_model=demoted)
            model = demoted

    # ---- Story 3-3 + 4-7 sensitivity precondition (Story 6-20 strictest-placement) ----
    #
    # Story 6-20 (F28 closure, Adam-decided option A + strictest-placement
    # 2026-06-06): gate the union of (a) the legacy ``email_id`` parameter
    # and (b) every email_id referenced anywhere in the chat-completions
    # request payload (assistant tool_calls arguments + tool-role content).
    # The Hermes inline-drafting path doesn't pass email_id as a parameter
    # but DOES land sensitive bodies via tool_result content — F28's
    # PRIVACY INVARIANT VIOLATION was the gate firing only on the parameter.
    #
    # Iteration order: ``sorted(audit_ids)`` so multi-id refusal messages
    # are deterministic across test runs and audit-trail diffs.
    #
    # Token consume binds to the FIRST sensitive id encountered in sorted
    # order; multi-token handshakes for N-sensitive-id refs are explicitly
    # DEFERRED (file a follow-up if Hermes patterns demand it). Story 4-7's
    # single-string ``confirmation_token`` shape is preserved verbatim.
    #
    # Defense-in-depth: ``ask_router``'s precondition layer (Story 4-7)
    # stays UNCHANGED; this is the upstream gate for Hermes-driven chat
    # completions, not a replacement for the agent-tool gate.
    _sensitivity_grant_id: str | None = None
    _sensitivity_grant_minted_at: str | None = None
    _audit_ids: set[str] = set()
    if email_id is not None:
        _audit_ids.add(email_id)
    _audit_ids |= _resolve_email_ids_from_messages(messages)
    if _audit_ids:
        _consumed_for_eid: str | None = None
        for eid in sorted(_audit_ids):
            sensitivity_row = await fetchone(db_path, EMAIL_SENSITIVITY_SELECT, (eid,))
            if sensitivity_row is None or sensitivity_row[1] is None:
                # Carry email_id in the error message ONLY when the call
                # actually references multiple ids OR the id was discovered
                # via message resolution (caller may not know which id
                # tripped the gate). The legacy single-id-param path
                # preserves the original message verbatim for backwards
                # compatibility with Story 6-9's audit conventions.
                if eid == email_id and len(_audit_ids) == 1:
                    msg = "email sensitivity must be classified before any other Router task"
                else:
                    msg = (
                        f"email {eid!r} sensitivity must be classified before "
                        "any other Router task"
                    )
                return ToolCallResult(
                    ok=False,
                    error=RouterError(
                        code=ErrorCode.SENSITIVITY_NOT_CLASSIFIED,
                        message=msg,
                        retryable=False,
                    ),
                )
            sensitivity_value, _ = sensitivity_row
            if sensitivity_value == "confidential" and _API_BOUND_MODEL_RE.match(model) is not None:
                # NFR-PRIV-2: confidential admits no override even with a
                # token. Refuse unconditionally regardless of whether
                # confirmation_token was supplied — token does NOT unlock
                # confidential. Message includes the offending id so the
                # multi-id caller can act.
                if eid == email_id and len(_audit_ids) == 1:
                    msg = "confidential emails admit no API override"
                else:
                    msg = f"confidential email {eid!r} admits no API override"
                return ToolCallResult(
                    ok=False,
                    error=RouterError(
                        code=ErrorCode.SENSITIVITY_BLOCKS_API,
                        message=msg,
                        retryable=False,
                        model_attempted=[model],
                    ),
                    model_used=model,
                )
            if sensitivity_value == "sensitive" and _API_BOUND_MODEL_RE.match(model) is not None:
                # Token-consume contract (Story 6-20 single-token v1):
                # the supplied confirmation_token (if any) consumes against
                # the FIRST sensitive id encountered in sorted order. Any
                # subsequent sensitive id falls through to SENSITIVITY_BLOCKS_API
                # because the agent didn't supply a second token. The deferred
                # multi-token handshake (list[str]) is the future expansion.
                if confirmation_token is None or _consumed_for_eid is not None:
                    if eid == email_id and len(_audit_ids) == 1:
                        msg = (
                            "sensitive email requires per-session confirmation "
                            "token to escalate to API"
                        )
                    else:
                        msg = (
                            f"sensitive email {eid!r} requires per-session "
                            "confirmation token to escalate to API"
                        )
                    return ToolCallResult(
                        ok=False,
                        error=RouterError(
                            code=ErrorCode.SENSITIVITY_BLOCKS_API,
                            message=msg,
                            retryable=False,
                            model_attempted=[model],
                        ),
                        model_used=model,
                    )
                # Defensive wrap around consume() — see CR-4-7-3(a): any
                # future DB-backed registry that raises mid-consume must not
                # leak the token value into a traceback. The exception type
                # and email_id/task_type are logged; the token value is not.
                from mailbot_api.actions.sensitivity_tokens import (  # noqa: PLC0415
                    consume as _consume_token,
                )
                try:
                    consume_result = _consume_token(confirmation_token, eid, _TOOL_CALL_TASK_TYPE)
                except Exception as exc:  # noqa: BLE001 — guard against token-in-traceback
                    # CR-6-20-1 (2026-06-06, sonnet-4-6 review): use _logger.error
                    # WITHOUT exc_info so a future DB-backed registry that embeds
                    # the token value in its exception message does NOT leak it
                    # via the captured traceback. The `exception_type` field in
                    # `extra` is the load-bearing diagnostic; that survives.
                    _logger.error(
                        "sensitivity token consume crashed; refusing dispatch",
                        extra={
                            "event": "sensitivity.token.consume_crash",
                            "email_id": eid,
                            "task_type": _TOOL_CALL_TASK_TYPE,
                            "exception_type": type(exc).__name__,
                        },
                    )
                    consume_result = None
                if consume_result is None:
                    return ToolCallResult(
                        ok=False,
                        error=RouterError(
                            code=ErrorCode.NEEDS_SENSITIVITY_CONFIRMATION,
                            message=(
                                "confirmation token invalid, expired, already "
                                "consumed, or mismatched (email_id/task_type)"
                            ),
                            retryable=False,
                            model_attempted=[model],
                        ),
                        model_used=model,
                    )
                grant_id, minted_at = consume_result
                _sensitivity_grant_id = grant_id
                _sensitivity_grant_minted_at = minted_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                _consumed_for_eid = eid
            elif sensitivity_value == "normal" and confirmation_token is not None:
                # CR-4-7-5: a token passed for a normal email is unexpected.
                # The call is valid (no token needed for this id), but the
                # agent's behavior is worth observing. Do NOT log the token
                # value itself. Note: the token may have been intended for a
                # DIFFERENT sensitive id in the same audit_ids set; we log
                # per-occurrence so the operator can correlate.
                _logger.warning(
                    "confirmation_token passed; referenced email is normal",
                    extra={
                        "event": "sensitivity.token.unexpected",
                        "email_id": eid,
                        "task_type": _TOOL_CALL_TASK_TYPE,
                        "sensitivity": sensitivity_value,
                    },
                )

    # ---- Dispatch ----
    tokens_in = 0
    tokens_out = 0
    cached_tokens_in = 0
    cost_usd = 0.0
    latency_ms = 0
    outcome: str = "failed"
    # CR-3 (Story 6-9 review 2026-06-04): initialize tool_calls_count=0
    # so a tools-bearing call that fails the adapter dispatch still records
    # `tool_calls_count=0` (NOT NULL). Per design §4: NULL means "not a
    # tools-bearing call"; 0 means "tools were attempted". This preserves
    # the forensic distinction for `WHERE tool_calls_count IS NOT NULL`
    # queries identifying all tools-bearing dispatch attempts.
    tool_calls_count: int | None = 0
    tool_calls_summary: str | None = None
    result: ToolCallResult

    try:
        # Resolve the adapter.
        try:
            adapter = get_adapter(model)
        except KeyError as exc:
            result = ToolCallResult(
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

        # Rate-limit gate (per Story 2-5 + Story 6-2).
        breach_dim = enforce_rate_limit(policy_entry.lane, model_chosen_reason, caller_origin)
        if breach_dim is not None:
            result = ToolCallResult(
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

        # Per-call refusal threshold (Story 2-8 Layer 4).
        # Rough estimate: joined message text + tool schemas.
        msg_text_total = sum(
            len(str(m.get("content", ""))) for m in messages if isinstance(m, dict)
        )
        tool_text_total = sum(
            len(t.function.description) + len(json.dumps(t.function.parameters))
            for t in tools
        )
        estimated_tokens_in = (msg_text_total + tool_text_total) // 4
        estimated_cost = estimate_cost_usd(model, estimated_tokens_in, max_tokens_out)
        if estimated_cost > PER_CALL_REFUSAL_THRESHOLD_USD:
            result = ToolCallResult(
                ok=False,
                error=RouterError(
                    code=ErrorCode.PER_CALL_THRESHOLD_EXCEEDED,
                    message=(
                        f"estimated cost ${estimated_cost:.4f} exceeds "
                        f"per-call threshold ${PER_CALL_REFUSAL_THRESHOLD_USD:.2f}"
                    ),
                    retryable=False,
                    model_attempted=[model],
                ),
                model_used=model,
            )
            return result

        # System prompt: concatenate ALL system messages with "\n\n"
        # (CR-6 Story 6-9 review 2026-06-04: Hermes's main inference path
        # carries SOUL.md + AGENTS.md + SKILL.md as separate system blocks;
        # silently keeping only the first would lose the rest). A None
        # content field on a system-role message is coerced to "" to keep
        # the concatenation safe — Pydantic admits `content=None` on
        # assistant messages, but a system message with `content=None`
        # is a client bug we silently tolerate.
        system_parts: list[str] = []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "system":
                content = m.get("content")
                if isinstance(content, str):
                    system_parts.append(content)
                # else content is None or non-string — silently skip; the
                # validator already kept this message in the list, just
                # don't contribute to system_text.
        system_text = "\n\n".join(system_parts)
        # Filter system-role messages from the messages list — Anthropic
        # carries system as a separate top-level field, not in messages.
        non_system_messages = [
            m for m in messages
            if not (isinstance(m, dict) and m.get("role") == "system")
        ]

        # Adapter dispatch via tool-calling protocol method.
        try:
            async with acquire_provider_slot(model):
                tool_response = await adapter.call_with_tools(
                    system=system_text,
                    messages=non_system_messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    max_tokens_out=max_tokens_out,
                    temperature=temperature,
                )
        except AdapterTimeout as exc:
            outcome = "failed"
            result = ToolCallResult(
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
            result = ToolCallResult(
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

        tokens_in = tool_response.tokens_in
        tokens_out = tool_response.tokens_out
        cached_tokens_in = tool_response.cached_tokens_in
        latency_ms = tool_response.latency_ms
        cost_usd = estimate_cost_usd(model, tokens_in, tokens_out, cached_tokens_in)

        tool_calls_count = len(tool_response.tool_calls)
        tool_calls_summary = _build_tool_calls_summary(tool_response.tool_calls) if tool_response.tool_calls else None

        outcome = "ok"
        result = ToolCallResult(
            ok=True,
            text=tool_response.text or None,
            tool_calls=tool_response.tool_calls or None,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cached_tokens_in,
            model_used=model,
            finish_reason=tool_response.finish_reason,
        )
        await guard.add_spend(db_path, cost_usd)
        return result

    except Exception as exc:  # noqa: BLE001 — AR-PAT-4 boundary catch-all
        outcome = "failed"
        result = ToolCallResult(
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
        # Audit row.
        row = RouterCallRow(
            task_type=_TOOL_CALL_TASK_TYPE,
            prompt_version=_TOOL_CALL_PROMPT_VERSION,
            model_chosen=model,
            model_chosen_reason=model_chosen_reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cached_tokens_in,
            cost_usd_estimated=cost_usd,
            latency_ms=latency_ms,
            outcome=cast(Literal["ok", "retry_recovered", "escalated", "failed"], outcome),
            caller_verb=caller_verb,
            caller_origin=caller_origin,
            email_id=email_id,
            sensitivity_grant_id=_sensitivity_grant_id,
            sensitivity_grant_minted_at=_sensitivity_grant_minted_at,
            tool_calls_count=tool_calls_count,
            tool_calls_summary=tool_calls_summary,
        )
        await record_router_call(row, db_path=db_path)


__all__ = [
    "EmbeddingDispatchResult",
    "ask_router",
    "dispatch_embedding",
    "dispatch_tool_call",
]
