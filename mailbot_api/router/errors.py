"""Stable error codes + structured Router result/error shapes per Story 2-1.

The Router contract is **errors-as-data** (architecture §"Errors as data" +
AR-PAT-4): every call returns a ``RouterResult`` Pydantic model. Successes
carry the parsed prompt output and cost telemetry; failures carry a
``RouterError`` with a stable ``ErrorCode`` enum value. Exceptions never
cross the Router boundary into the agent / verbs / Hermes — they are caught
at the boundary and converted to ``RouterError`` instances via
``sanitize_error()``.

Adding a new code requires updating downstream consumers (the verb shim,
prompt modules, observability dashboards, eval rubric). Check architecture
§AR-PAT-3 before extending the enum.

Boundary: this module is import-safe from any caller. It does not touch the
DB, the network, ``ollama``, or ``anthropic`` — Router state and adapter
access live in sibling modules (``router.py``, ``models.py``, etc.) that
will be wired up in Stories 2-2 through 2-10.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Shared redaction regex constants live in observability/_redaction.py — a
# leaf module with no internal dependencies. `observability/logging.py` and
# this module both import from it (Story 2-1 review fix R9 — was previously
# a private-symbol import from logging.py, which was brittle).
from mailbot_api.observability._redaction import (
    BEARER_TOKEN_RE,
    SECRET_FILE_RE,
    SK_KEY_RE,
    URL_TOKEN_QUERY_RE,
)

# Story 10.5.2: the sensitivity-refusal envelope carried on RouterError.
# sensitivity_refusal.py is a leaf module (pydantic + hashlib only; no DB /
# network / errors.py import) so this does not create a cycle.
from mailbot_api.router.sensitivity_refusal import SensitivityRefusal


class ErrorCode(str, Enum):
    """Stable, lowercase, snake_case error codes for the Router contract.

    Inheriting from ``str`` means each member is its own ``.value`` for JSON
    serialization and SQL writes — downstream tooling keys on the string form
    (e.g., ``router_calls.outcome`` joined against a code lookup, eval-report
    filters, dashboards).
    """

    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    PER_CALL_THRESHOLD_EXCEEDED = "per_call_threshold_exceeded"
    PROVIDER_ERROR = "provider_error"
    MONTHLY_BUDGET_EXCEEDED = "monthly_budget_exceeded"
    DEGRADED_MODE_BLOCKED = "degraded_mode_blocked"
    LOOP_DETECTED = "loop_detected"
    SENSITIVITY_BLOCKS_API = "sensitivity_blocks_api"
    NEEDS_SENSITIVITY_CONFIRMATION = "needs_sensitivity_confirmation"
    SENSITIVITY_NOT_CLASSIFIED = "sensitivity_not_classified"
    RATE_LIMITED = "rate_limited"
    STATE_DRIFT_ETAG = "state_drift_etag"
    TARGET_DELETED = "target_deleted"
    STATE_DRIFT_NOOP = "state_drift_noop"
    # Story 10.5.5 (AC-2, F-10-3-2): a tool-call request resolved/demoted to a
    # model that cannot serve tools (qwen under degraded mode). The router
    # refuses cleanly with this stable code INSTEAD of dispatching a doomed call
    # to `OllamaAdapter.call_with_tools` (which raises opaque `tools_unsupported`,
    # the 18/18-fail root cause). The caller gets a recoverable, typed refusal.
    TOOL_CALLS_UNAVAILABLE_DEGRADED = "tool_calls_unavailable_degraded"


class RouterError(BaseModel):
    """Structured failure payload carried on ``RouterResult.error`` when ok=False."""

    code: ErrorCode
    message: str
    model_attempted: list[str] = Field(default_factory=list)
    retryable: bool
    # Story 10.5.2 (Epic 10.5 Cluster B, B7): sensitivity refusals carry a
    # typed envelope so the chat boundary can render the four-beat graceful
    # message (and NOT leak the Graph email id) instead of a raw HTTP-502.
    # Optional + additive — every non-sensitivity error leaves it None, so the
    # existing RouterError contract is unchanged. See router/sensitivity_refusal.py.
    refusal_envelope: SensitivityRefusal | None = None


class RouterResult(BaseModel):
    """The canonical return value of every Router call.

    Invariants enforced at instantiation:
      * ``ok=True``  ⇒ ``error is None``
      * ``ok=False`` ⇒ ``error is not None``

    The ``output`` field is intentionally a polymorphic ``BaseModel`` — each
    prompt module defines its own ``OUTPUT_SCHEMA`` Pydantic class and that
    instance lands here on success. ``arbitrary_types_allowed`` is required
    so Pydantic v2 admits the polymorphic shape at class-definition time.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    output: BaseModel | None = None
    error: RouterError | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens_in: int = 0
    model_used: str = ""

    @model_validator(mode="after")
    def _check_ok_error_consistency(self) -> RouterResult:
        if self.ok and self.error is not None:
            raise ValueError("RouterResult.ok=True requires error to be None")
        if not self.ok and self.error is None:
            raise ValueError("RouterResult.ok=False requires error to be populated")
        return self


# ---------------------------------------------------------------------------
# Story 6-9 (F11 closure) — OpenAI-shape tool-calling contract.
#
# These shapes are the Router public contract for the dispatch_tool_call
# sibling of ask_router. They mirror OpenAI's tool-calling API so Hermes's
# main-inference path (which assembles OpenAI tools=[...] requests to expose
# MCP tools) can flow through /v1/chat/completions and receive a tool_calls
# response.
#
# The Anthropic-side translation is encapsulated entirely inside
# AnthropicAdapter.call_with_tools (router/models.py) — these shapes never
# leak Anthropic-side field names.
# ---------------------------------------------------------------------------


class ChatCompletionFunctionDef(BaseModel):
    """The `function` sub-object of an OpenAI tool definition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    # `parameters` is JSON Schema; we accept arbitrary dict — translation to
    # Anthropic `input_schema` is a field-rename (see adapter).
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionToolDef(BaseModel):
    """OpenAI tool-definition shape: `{"type":"function","function":{...}}`."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["function"]
    function: ChatCompletionFunctionDef


class ChatCompletionToolChoiceFunction(BaseModel):
    """`{"type":"function","function":{"name":"X"}}` choice form."""

    model_config = ConfigDict(extra="forbid")

    name: str


class ChatCompletionToolChoiceObject(BaseModel):
    """Object-form tool_choice: `{"type":"function","function":{"name":"X"}}`."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["function"]
    function: ChatCompletionToolChoiceFunction


# OpenAI's tool_choice union: literal string ("auto"/"none"/"required") OR
# object selecting a specific function.
ChatCompletionToolChoice = (
    Literal["auto", "none", "required"] | ChatCompletionToolChoiceObject
)


class OpenAIToolCallFunction(BaseModel):
    """The `function` sub-object on an assistant tool_call.

    `arguments` is a JSON STRING (per OpenAI's wire shape), not a dict.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: str


class OpenAIToolCall(BaseModel):
    """One element of `message.tool_calls` on an assistant response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["function"]
    function: OpenAIToolCallFunction


class ToolCallResult(BaseModel):
    """Return shape of `dispatch_tool_call` (Story 6-9 F11 closure).

    Parallel to `RouterResult` but tailored to tool-call dispatch:
      * No `output: BaseModel` — tool-call responses don't have a prompt
        OUTPUT_SCHEMA; the OpenAI-shape `tool_calls` IS the structured output.
      * `text` carries the optional accompanying assistant text (Anthropic
        can return both text + tool_use blocks in one response).
      * `finish_reason` is `"tool_calls"` when any tool_use block present.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    text: str | None = None
    tool_calls: list[OpenAIToolCall] | None = None
    error: RouterError | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens_in: int = 0
    model_used: str = ""
    finish_reason: Literal["stop", "tool_calls", "length"] = "stop"

    @model_validator(mode="after")
    def _check_ok_error_consistency(self) -> ToolCallResult:
        if self.ok and self.error is not None:
            raise ValueError("ToolCallResult.ok=True requires error to be None")
        if not self.ok and self.error is None:
            raise ValueError("ToolCallResult.ok=False requires error to be populated")
        return self


def sanitize_error(exc: BaseException) -> str:
    """Return a single-line, secret-redacted string for ``RouterError.message``.

    Input contract: the caller passes a raw ``Exception`` instance. The function
    extracts ``type(exc).__name__ + ": " + str(exc)``; it does NOT accept a
    pre-formatted traceback string (no caller in the system passes one). If you
    need to redact a formatted traceback, call ``observability.logging.sanitize``
    on the formatted string instead.

    Redactions (shared with ``observability.logging.sanitize`` via
    ``observability._redaction``):
      * Bearer tokens → ``[REDACTED_BEARER]``
      * ``sk-…`` keys → ``[REDACTED_SK_KEY]``
      * URL query-param values for ``token`` / ``code`` / ``access_token`` /
        ``refresh_token`` / ``api_key`` / ``key`` / ``secret`` → key preserved,
        value replaced with ``[REDACTED_QUERY_TOKEN]``
      * File paths matching ``.env`` / ``.key`` / ``.pem`` / ``.p12`` / ``.pfx``
        → ``[REDACTED_PATH]``

    Any embedded newlines (rare but possible — e.g., a multi-line ``str(exc)``
    on a custom exception type) collapse to one line, joined with ``"; "``.

    Defensive: if the exception's ``__str__`` itself raises (a valid edge case
    for badly-implemented custom exception types), the function returns a safe
    fallback string rather than propagating — error-formatting must never make
    the error worse.
    """

    try:
        body = str(exc)
    except Exception:  # noqa: BLE001 — defensive fallback per Story 2-1 review fix R4
        body = "<unprintable exception>"
    raw = f"{type(exc).__name__}: {body}"
    # Apply the redaction rules in the same order as observability.logging.sanitize.
    raw = BEARER_TOKEN_RE.sub("[REDACTED_BEARER]", raw)
    raw = SK_KEY_RE.sub("[REDACTED_SK_KEY]", raw)
    raw = URL_TOKEN_QUERY_RE.sub(r"\1[REDACTED_QUERY_TOKEN]", raw)
    raw = SECRET_FILE_RE.sub("[REDACTED_PATH]", raw)
    # Single-line collapse: replace any newlines (incl. CR) with "; ".
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "; ")
    return raw.strip()


__all__: list[str] = [
    "ChatCompletionFunctionDef",
    "ChatCompletionToolChoice",
    "ChatCompletionToolChoiceFunction",
    "ChatCompletionToolChoiceObject",
    "ChatCompletionToolDef",
    "ErrorCode",
    "OpenAIToolCall",
    "OpenAIToolCallFunction",
    "RouterError",
    "RouterResult",
    "ToolCallResult",
    "sanitize_error",
]
