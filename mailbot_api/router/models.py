"""Model adapters per Story 2-3 (Ollama) and Story 2-6 (Anthropic, TBD).

Architecture Rule I + F.1: the ONLY file in the project allowed to import
``ollama`` or ``anthropic``. Enforced by ``scripts/check_boundaries.py``.

Public API:
  * ``AdapterResponse`` — normalized Pydantic shape returned by every adapter
  * ``ModelAdapter`` — Protocol that ``OllamaAdapter`` + ``AnthropicAdapter`` satisfy
  * ``AdapterError`` / ``AdapterTimeout`` / ``AdapterProviderError`` — exception hierarchy
  * ``OllamaAdapter`` — concrete adapter for local Ollama serving

Story 2-3 ships only the Ollama leg + the shared shapes. Story 2-4 will dispatch
through these adapters via the ``ModelAdapter`` Protocol. Story 2-6 will add
the Anthropic concrete class.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Literal, Protocol

import anthropic
import ollama
from pydantic import BaseModel, ConfigDict

from mailbot_api.observability._redaction import (
    BEARER_TOKEN_RE,
    SECRET_FILE_RE,
    SK_KEY_RE,
    URL_TOKEN_QUERY_RE,
)
from mailbot_api.router.errors import (
    ChatCompletionToolChoice,
    ChatCompletionToolChoiceObject,
    ChatCompletionToolDef,
    OpenAIToolCall,
    OpenAIToolCallFunction,
    sanitize_error,
)

_log = logging.getLogger(__name__)


def _sanitize_text(raw: str) -> str:
    """Redact secrets from a raw string for logging (Story 10-7-1).

    ``sanitize_error`` only accepts a ``BaseException``; the declined-block log
    records qwen's raw emitted text (a ``str``), so apply the same shared
    redaction regexes (``observability._redaction``) in the same order — Bearer
    tokens, ``sk-`` keys, URL query tokens, secret file paths — and collapse
    newlines to a single line. Mirrors ``sanitize_error``'s redaction body.
    """
    out = BEARER_TOKEN_RE.sub("[REDACTED_BEARER]", raw)
    out = SK_KEY_RE.sub("[REDACTED_SK_KEY]", out)
    out = URL_TOKEN_QUERY_RE.sub(r"\1[REDACTED_QUERY_TOKEN]", out)
    out = SECRET_FILE_RE.sub("[REDACTED_PATH]", out)
    return out.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "; ")

# Story 10-7-1: Qwen 2.5 3B on the Hermes chat-template path sometimes emits a
# tool call as a literal `<tool_call>{…}</tool_call>` text block inside
# message.content instead of the structured message.tool_calls array (the call
# is chosen but silently no-ops, tool_calls_count=0).
_TOOL_CALL_OPEN = "<tool_call>"
_TOOL_CALL_CLOSE = "</tool_call>"


def _extract_first_tool_call_block(text: str) -> str | None:
    """Return the FIRST ``<tool_call>…</tool_call>`` block (opener+inner+closer,
    inclusive) via a linear string scan, or ``None`` if there is no complete
    block.

    Story 10-7-1 CR (F3/F4): a regex ``<tool_call>\\s*(.*?)\\s*</tool_call>``
    with DOTALL backtracks quadratically on many unclosed ``<tool_call>``
    prefixes (measured ~64s on 20k prefixes) — a ReDoS on a live path fed by an
    unpredictable local 3B model. ``str.find`` is linear and cannot backtrack.
    We take the FIRST opener and the FIRST closer after it (single-call
    semantics). A stray ``</tool_call>`` substring inside a JSON string value
    still truncates the block early → the inner JSON fails to parse → STRICT
    decline (the safe direction), same as the regex approach but without the
    catastrophic-backtracking cost.
    """
    open_idx = text.find(_TOOL_CALL_OPEN)
    if open_idx == -1:
        return None
    inner_start = open_idx + len(_TOOL_CALL_OPEN)
    close_idx = text.find(_TOOL_CALL_CLOSE, inner_start)
    if close_idx == -1:
        return None
    return text[open_idx : close_idx + len(_TOOL_CALL_CLOSE)]


def _reject_json_constant(_token: str) -> object:
    """``json.loads`` ``parse_constant`` hook (Story 10-7-1 CR F5).

    Python's ``json`` accepts the non-standard tokens ``NaN`` / ``Infinity`` /
    ``-Infinity`` by default. For the STRICT rescue those are malformed values
    (they would re-serialize into a non-JSON-standard ``arguments`` string and
    contradict the wrong-shaped-call-declines intent), so raise to force a
    decline.
    """
    raise ValueError("non-standard JSON constant rejected by strict rescue")


def _strict_json_object(raw: str) -> dict[str, Any] | None:
    """Parse ``raw`` as a JSON object, STRICTLY. Returns the dict, or ``None`` if
    it is not valid standard JSON, not an object, or contains
    ``NaN``/``Infinity`` (CR F5). Never raises (AR-PAT-4)."""
    try:
        obj = json.loads(raw, parse_constant=_reject_json_constant)
    except (TypeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _rescue_text_tool_call(text: str) -> OpenAIToolCall | None:
    """Story 10-7-1 — STRICT rescue of a `<tool_call>`-as-text block.

    When qwen emits its tool call as literal text in ``message.content`` rather
    than the structured ``message.tool_calls`` array, promote the FIRST
    well-formed ``<tool_call>{…}</tool_call>`` block to a real ``OpenAIToolCall``
    that is byte-shape-identical to a natively-structured one (so everything
    downstream — ``router.py`` ``tool_calls_count``, the drain/gate pipeline — is
    unchanged).

    STRICT tolerance (Adam architectural decision 2026-07-15): promote ONLY a
    clean call — a non-empty ``name`` and either a dict ``arguments`` (or a JSON
    string that parses to a dict) or NO ``arguments`` key at all (→ empty args).
    A malformed block — stray sibling keys instead of a proper ``arguments``
    object (the real walk shape ``{"name":"memory","action":"add",…}``) — is
    NOT promoted. Fabricating an ad-hoc ``arguments`` object from a
    half-hallucinated block would push ambiguous 3B output *toward* action
    through propose→grant→drain, the wrong failure direction for the local
    safety-net lane. A wrong-shaped call is worse than no call; selection is
    10.7.3's job, not this parser's.

    Returns the promoted ``OpenAIToolCall`` on success, or ``None`` when there is
    no block or the block is malformed. Never raises across the adapter boundary
    (AR-PAT-4: errors-as-data). The caller is responsible for logging the
    promote/decline telemetry.
    """
    block = _extract_first_tool_call_block(text)
    if block is None:
        return None
    inner = block[len(_TOOL_CALL_OPEN) : -len(_TOOL_CALL_CLOSE)]
    obj = _strict_json_object(inner)
    if obj is None:
        return None

    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        return None  # a call with no tool name is meaningless — decline

    if "arguments" in obj:
        arg_input = obj["arguments"]
        # Some emitters nest arguments as a JSON STRING rather than a dict.
        if isinstance(arg_input, str):
            arg_input = _strict_json_object(arg_input)
            if arg_input is None:
                return None
        if not isinstance(arg_input, dict):
            return None  # arguments present but not an object — decline
    else:
        # No `arguments` KEY at all. This branch is where the walk's malformed
        # shape lands: `{"name":"memory","action":"add","target":"user",
        # "content":"unread_emails"}` has no `arguments` key, so its extra
        # top-level keys (`action`/`target`/`content`) are `stray` and it is
        # STRICTLY declined rather than fabricated into an arguments object.
        # (CR F8: this is NOT the arguments-present path — a block WITH an
        # `arguments` key never reaches here; it is validated above.) A bare
        # `{"name": ...}` with no stray keys promotes with empty args.
        stray = {k for k in obj if k != "name"}
        if stray:
            return None
        arg_input = {}

    try:
        args_json = json.dumps(arg_input, separators=(",", ":"))
    except (TypeError, ValueError):
        return None

    return OpenAIToolCall(
        id="call_0",
        type="function",
        function=OpenAIToolCallFunction(name=name, arguments=args_json),
    )


class AdapterResponse(BaseModel):
    """Normalized shape returned by every adapter's ``call`` method."""

    model_config = ConfigDict(extra="forbid")

    text: str
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    latency_ms: int
    raw: dict[str, Any]


class ToolCallAdapterResponse(BaseModel):
    """Story 6-9 (F11 closure) — adapter response for tool-bearing calls.

    Parallels `AdapterResponse` but carries:
      * `text` — optional accompanying assistant text (Anthropic CAN return
        both text + tool_use blocks in one response). Empty string when only
        tool_use blocks are present.
      * `tool_calls` — list of OpenAI-shape tool_calls translated from
        Anthropic's tool_use content blocks. Empty list when the model
        chose to produce text only.
      * `finish_reason` — `"tool_calls"` when any tool_use block present;
        `"length"` when truncated by max_tokens; `"stop"` otherwise.

    Adapters that don't support tool-calling raise `AdapterProviderError`
    with `sanitized_message="tools_unsupported"` rather than returning an
    empty-tool_calls response — silent drop would mask the gap.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    tool_calls: list[OpenAIToolCall]
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    latency_ms: int
    finish_reason: Literal["stop", "tool_calls", "length"]
    raw: dict[str, Any]


class EmbeddingResponse(BaseModel):
    """Normalized shape returned by ``OllamaAdapter.embed`` (Story 3-4).

    Parallels ``AdapterResponse`` but tailored to embeddings:
      * ``vector`` is the raw float list returned by the embedding API.
      * ``dim`` is the embedding dimensionality; ``len(vector) == dim`` is
        invariant-checked at the adapter boundary.
      * No ``text`` / ``tokens_out`` — embedding output is a vector, not a string.
      * No ``cached_tokens_in`` — Ollama's embedding API does not return cache stats.
    """

    model_config = ConfigDict(extra="forbid")

    vector: list[float]
    dim: int
    tokens_in: int
    latency_ms: int
    raw: dict[str, Any]


# Story 3-4: embeddings are faster than chat completions; the spec mandates
# a separate, shorter timeout so a slow embedding call doesn't borrow the
# chat-side 30s budget. Only used by ``OllamaAdapter.embed``.
_EMBEDDING_TIMEOUT_SECONDS: float = 15.0


class AdapterError(Exception):
    """Base class for all adapter-side failures."""


class AdapterTimeout(AdapterError):
    """Raised when the adapter's hard timeout fires (FR-3.4)."""

    def __init__(self, model_id: str, timeout_seconds: float) -> None:
        super().__init__(f"adapter timeout: model_id={model_id} timeout_seconds={timeout_seconds}")
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds


class AdapterProviderError(AdapterError):
    """Raised when any non-timeout exception occurs inside the adapter.

    Any provider-side failure (HTTP error, JSON parse, model-not-found, etc.)
    converges here. ``sanitized_message`` is the already-redacted string ready
    for Router-level error reporting; the raw exception never crosses this boundary.
    """

    def __init__(self, model_id: str, sanitized_message: str) -> None:
        super().__init__(f"adapter provider error: model_id={model_id} message={sanitized_message}")
        self.model_id = model_id
        self.sanitized_message = sanitized_message


class ModelAdapter(Protocol):
    """The uniform interface ``ask_router`` uses to call any supported LLM the
    same way, regardless of provider.

    Each concrete adapter (``OllamaAdapter`` for local Qwen, ``AnthropicAdapter``
    for Claude Haiku/Opus) hides its provider's specific API behind this shared
    protocol and returns the same normalized ``AdapterResponse``. This keeps
    ``ask_router`` provider-agnostic: it never has to know how any individual
    model's API works. (Note: "OpenAI" names elsewhere in this module — e.g.
    ``OpenAIToolCall`` — refer to the OpenAI-compatible *wire format* that Ollama
    emits, not an OpenAI provider; there is no OpenAI adapter. See
    ``docs/CONCEPTS.md``.)

    Story 2-4's ``ask_router`` dispatches against this protocol — no runtime
    inheritance required, so Pydantic-bearing adapter classes don't need to
    fight a metaclass with an ABC.

    Story 6-9 (F11 closure): ``call_with_tools`` is the tool-calling sibling.
    Adapters that don't support tool-calling MUST raise
    ``AdapterProviderError(sanitized_message="tools_unsupported")`` rather
    than silently dropping tools — silent drop is how F11 originally hid.
    """

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse: ...

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ChatCompletionToolDef],
        tool_choice: ChatCompletionToolChoice | None = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse: ...


# ---------------------------------------------------------------------------
# Story 6-9 (F11 closure) — OpenAI ↔ Anthropic translation helpers.
#
# Pure functions, no I/O. Tested via unit tests that pass canned shapes
# through the helpers and assert the translated output.
# ---------------------------------------------------------------------------


def _translate_tools_openai_to_anthropic(
    tools: list[ChatCompletionToolDef],
) -> list[dict[str, Any]]:
    """OpenAI `tools=[{"type":"function","function":{...}}]` →
    Anthropic `tools=[{"name","description","input_schema"}]`."""
    return [
        {
            "name": t.function.name,
            "description": t.function.description,
            "input_schema": t.function.parameters or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


def _translate_tools_openai_to_ollama(
    tools: list[ChatCompletionToolDef],
) -> list[dict[str, Any]]:
    """OpenAI `tools=[{"type":"function","function":{...}}]` → Ollama tools.

    Story AI-1: Ollama's Python SDK (`/api/chat`) accepts OpenAI-compatible
    tool dicts verbatim — `{"type":"function","function":{name,description,
    parameters}}`. This helper reconstructs that shape from the parsed
    `ChatCompletionToolDef` Pydantic models so the SDK sees a plain dict it
    can serialize (mirrors `_translate_tools_openai_to_anthropic` above).
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t.function.name,
                "description": t.function.description,
                "parameters": t.function.parameters or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def _translate_messages_openai_to_ollama(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """OpenAI messages history → Ollama `/api/chat` messages.

    Story AI-1 (CR-3, multi-turn correlation). Most OpenAI message shapes pass
    to Ollama's `/api/chat` verbatim (user/assistant/system text, and assistant
    messages carrying an OpenAI-shape `tool_calls` array). The ONE shape that
    needs translation is the tool-RESULT message:

      * OpenAI: `{"role": "tool", "tool_call_id": "<id>", "content": "..."}`
      * Ollama: `{"role": "tool", "tool_name": "<fn name>", "content": "..."}`

    Ollama correlates a tool result to the call by function NAME (`tool_name`),
    not by the OpenAI `tool_call_id`. To recover the name we walk the history
    once, building an id → function-name map from every assistant `tool_calls`
    entry, then rewrite each `role:"tool"` message to carry `tool_name`
    (dropping the meaningless-to-Ollama `tool_call_id`). If an id can't be
    resolved (e.g. a tool result with no preceding assistant tool_call in the
    supplied window), we fall back to any `name` already on the message, else
    omit `tool_name` — Ollama then matches positionally, which is the best we
    can do without the name and matches single-turn behavior.

    Story AI-1 Phase 2 (10-6-1): a SECOND translation is needed for assistant
    messages that ECHO a prior `tool_calls` array (multi-turn history). OpenAI's
    wire shape stores `function.arguments` as a JSON STRING, but Ollama's
    `Message.ToolCall` model requires `arguments` to be a DICT — passing the
    string through raises a pydantic ValidationError inside the ollama library
    (`Input should be a valid dictionary ... input_type=str`). This path became
    REACHED only when AI-1 Phase 2 routed default chat tool-calls to the local
    lane; before that qwen refused all tool-calls at the capability gate so no
    multi-turn echo ever reached this translator. We convert each assistant
    tool_call's arguments string → dict (json-decoded); a value that is already
    a dict, or a string that isn't valid JSON, is left unchanged (the latter is
    a caller/model bug the Ollama layer surfaces on its own — the translator
    must not raise mid-history).

    Non-tool, non-tool_call messages are passed through unchanged (a shallow
    copy is made only for the messages we rewrite; other dicts are forwarded by
    reference, same as the pre-AI-1 pass-through).
    """
    # Pass 1: id → function name, harvested from assistant tool_calls.
    id_to_name: dict[str, str] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        tcs = msg.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            call_id = tc.get("id")
            fn = tc.get("function")
            if isinstance(call_id, str) and isinstance(fn, dict):
                name = fn.get("name")
                if isinstance(name, str) and name:
                    id_to_name[call_id] = name

    # Pass 2: rewrite tool-result messages (role:"tool") AND assistant messages
    # echoing a tool_calls array (arguments string → dict); pass everything else
    # through by reference.
    out: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool":
            translated = dict(msg)
            call_id = translated.pop("tool_call_id", None)
            resolved = None
            if isinstance(call_id, str):
                resolved = id_to_name.get(call_id)
            if resolved is None:
                # Fall back to an explicit name already on the message, if any.
                existing = translated.get("tool_name") or translated.get("name")
                if isinstance(existing, str) and existing:
                    resolved = existing
            if resolved is not None:
                translated["tool_name"] = resolved
            out.append(translated)
        elif (
            isinstance(msg, dict)
            and msg.get("role") == "assistant"
            and isinstance(msg.get("tool_calls"), list)
        ):
            out.append(_ollama_assistant_tool_calls_args_to_dict(msg))
        else:
            out.append(msg)
    return out


def _ollama_assistant_tool_calls_args_to_dict(msg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an assistant message whose `tool_calls[].function.
    arguments` JSON strings have been decoded to dicts (Ollama's required
    shape). A value that is already a dict is left as-is. A string is
    substituted ONLY when it decodes to a JSON OBJECT (dict); a string that is
    not valid JSON, or that decodes to a non-object (scalar/list — e.g. `'42'`,
    `'[1,2]'`, `'"x"'`), is left UNCHANGED so the Ollama layer surfaces its own
    typed error rather than this translator fabricating a still-invalid
    non-dict `arguments`. (CR — the decode guard must reject valid-JSON-but-
    non-object, not just syntactically-invalid JSON.)

    Copies only the mutated sub-structures — a fresh `tool_calls` list plus a
    shallow copy (`dict(...)`) of each rewritten call and its `function` dict —
    so the caller's original message dicts are never aliased or mutated. The
    decoded `arguments` object is a freshly-allocated value from `json.loads`,
    not shared with the caller.
    """
    tool_calls = msg.get("tool_calls")
    if not isinstance(tool_calls, list):
        return msg
    new_tool_calls: list[Any] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            new_tool_calls.append(tc)
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            new_tool_calls.append(tc)
            continue
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                decoded = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                # Malformed args — leave as-is; the Ollama layer surfaces its
                # own error rather than the translator raising mid-history.
                new_tool_calls.append(tc)
                continue
            if not isinstance(decoded, dict):
                # Valid JSON that is NOT an object (scalar/list). Ollama requires
                # a dict; leaving the original string in place lets the ollama
                # validator raise its own diagnostic rather than us forwarding a
                # differently-but-still-invalid shape. Same disposition as the
                # malformed-JSON branch above.
                new_tool_calls.append(tc)
                continue
            new_fn = dict(fn)
            new_fn["arguments"] = decoded
            new_tc = dict(tc)
            new_tc["function"] = new_fn
            new_tool_calls.append(new_tc)
        else:
            # Already a dict (or absent) — pass the call through unchanged.
            new_tool_calls.append(tc)
    new_msg = dict(msg)
    new_msg["tool_calls"] = new_tool_calls
    return new_msg


_OMIT_TOOL_CHOICE = object()
"""Sentinel returned by `_translate_tool_choice_openai_to_anthropic` to signal
that the caller should OMIT the tool_choice field from the Anthropic request
entirely (vs. passing an explicit `{"type":"auto"}` value). CR-8 (Story 6-9
review): tool_choice is part of Anthropic's cached prefix per Rule M; sending
an explicit value when the caller passed None subtly varies the cache key.
Omitting matches Anthropic's documented default."""


def _translate_tool_choice_openai_to_anthropic(
    tool_choice: ChatCompletionToolChoice | None,
) -> dict[str, Any] | None | object:
    """OpenAI tool_choice → Anthropic tool_choice.

    Return values:
      * dict — explicit Anthropic tool_choice to send
      * None — `"none"` semantics; caller omits both tools and tool_choice
      * `_OMIT_TOOL_CHOICE` — caller omits tool_choice but keeps tools
        (CR-8: caller passed None → Anthropic's documented default is auto;
        omitting matches that default without varying the cached prefix)
    """
    if tool_choice is None:
        return _OMIT_TOOL_CHOICE
    if tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "required":
        return {"type": "any"}
    if tool_choice == "none":
        return None
    if isinstance(tool_choice, ChatCompletionToolChoiceObject):
        return {"type": "tool", "name": tool_choice.function.name}
    # Defensive — Pydantic should have caught any other shape at parse time.
    raise ValueError(f"unrecognized tool_choice: {tool_choice!r}")


def _translate_messages_openai_to_anthropic(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """OpenAI messages history → Anthropic messages.

    Handles three message shapes:
      * `{"role": "user", "content": "..."}` → pass-through
      * `{"role": "assistant", "content": "...", "tool_calls": [...]}`
        → `{"role": "assistant", "content": [<text block?>, <tool_use blocks>]}`
      * `{"role": "tool", "tool_call_id": "...", "content": "..."}`
        → `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}`

    Per §3.4 of 6-9-design-decision.md, tool-result messages travel as
    `user`-role content blocks on the Anthropic side. Adjacent assistant +
    tool messages preserve their relative order.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            tool_use_id = msg.get("tool_call_id", "")
            content = msg.get("content", "")
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": content,
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and msg.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            text = msg.get("content")
            if isinstance(text, str) and text:
                blocks.append({"type": "text", "text": text})
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    parsed_args = json.loads(fn.get("arguments", "{}"))
                except (TypeError, json.JSONDecodeError):
                    parsed_args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": parsed_args,
                    }
                )
            out.append({"role": "assistant", "content": blocks})
            continue
        # Plain user / assistant text — pass-through.
        out.append(
            {"role": role or "user", "content": msg.get("content", "")}
        )
    return out


def _translate_response_anthropic_to_openai_tool_calls(
    content_blocks: list[dict[str, Any]],
) -> tuple[str, list[OpenAIToolCall]]:
    """Anthropic response content → (joined_text, openai_tool_calls).

    Walks the Anthropic content blocks once, separating `text` blocks
    (joined into one string) from `tool_use` blocks (translated to
    OpenAI's `tool_calls` shape with JSON-stringified arguments).
    """
    text_parts: list[str] = []
    tool_calls: list[OpenAIToolCall] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text_parts.append(str(block.get("text", "")))
        elif btype == "tool_use":
            arg_input = block.get("input") or {}
            try:
                args_json = json.dumps(arg_input, separators=(",", ":"))
            except (TypeError, ValueError):
                args_json = "{}"
            tool_calls.append(
                OpenAIToolCall(
                    id=str(block.get("id", "")),
                    type="function",
                    function=OpenAIToolCallFunction(
                        name=str(block.get("name", "")),
                        arguments=args_json,
                    ),
                )
            )
    return "".join(text_parts), tool_calls


class OllamaAdapter:
    """Concrete adapter for local Ollama serving (Qwen 2.5 3B Q4_K_M).

    Construction is side-effect-free (no network); the first network call
    happens on ``call(...)``. The ``ollama.AsyncClient`` is constructed
    eagerly in ``__init__`` because it carries no network state until the
    first request — making it eager simplifies testability (one place to
    monkeypatch).
    """

    def __init__(
        self,
        model_id: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        keep_alive: int | str = -1,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        # Story 10-6-4 (F-10-6-1-W1): keep_alive controls Ollama's model-residency
        # window. Default -1 = never evict, which pins qwen resident AND preserves
        # the prompt KV-cache across turns. Without it, the 5-min idle eviction
        # discards the cache → the next full-context tool-call turn re-ingests
        # ~1658 tokens (~19s cold on CPU) and crosses the timeout. Passed as a
        # top-level `chat()` kwarg (sibling of `options`), not inside options.
        self.keep_alive = keep_alive
        self._client = ollama.AsyncClient(host=base_url)

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        options = {"num_predict": max_tokens_out, "temperature": temperature}

        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.chat(
                    model=self.model_id,
                    messages=messages,
                    options=options,
                    keep_alive=self.keep_alive,  # Story 10-6-4: prompt-cache preservation
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary: convert everything
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        # ollama's response is a ChatResponse model; convert to a plain dict
        # so AdapterResponse.raw doesn't pin the public shape to an external
        # Pydantic class that may change between SDK releases.
        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        message = raw_dict.get("message") or {}
        text = message.get("content", "") if isinstance(message, dict) else ""

        tokens_in = int(raw_dict.get("prompt_eval_count") or 0)
        tokens_out = int(raw_dict.get("eval_count") or 0)

        return AdapterResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=0,
            latency_ms=int(latency_ms),
            raw=raw_dict,
        )

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ChatCompletionToolDef],
        tool_choice: ChatCompletionToolChoice | None = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse:
        """Story AI-1 — Ollama tool-call surface (real implementation).

        Qwen 2.5 3B (`qwen2.5:3b-instruct-q4_K_M`) DOES expose OpenAI-shape
        tool-calling via Ollama's native `/api/chat` `tools` parameter. The
        prior `tools_unsupported` write-off (Story 6-9) was stale: the AI-1
        live probe (2026-07-11, `AI-1-local-tool-caller-verify-or-restore.md`)
        proved 6/6 exact argument fidelity at temperature 0 on both the native
        and OpenAI-compat surfaces — including long Graph-style ids.

        Temperature 0 is LOAD-BEARING for argument fidelity on this 3B/Q4
        model: the same probe saw default (non-zero) temperature corrupt a
        tool-call argument (`ABC123` → `ABC132`, a digit transposition) while
        temp 0 was 6/6 exact. The signature defaults `temperature=0.0`; we
        pass it straight through and callers should not raise it for
        write-bearing tool calls.

        `messages` arrive in OpenAI shape (roles + content, plus tool /
        tool_call blocks) — Ollama's `/api/chat` accepts most of those dicts
        directly, so we prepend the system message (F14 guard: only when
        non-empty) and forward the caller's list. The ONE exception (Story
        AI-1 CR-3) is the tool-RESULT message: OpenAI keys it by
        `tool_call_id`, Ollama by `tool_name`, so
        `_translate_messages_openai_to_ollama` rewrites those for multi-turn
        correlation. See that helper's docstring for the fallback behavior.

        When `tool_choice == "none"` the tools list is omitted entirely — same
        contract as the Anthropic adapter and OpenAI's "disable tools" meaning.
        For any other tool_choice (auto / required / a specific function) we
        pass the tools and let the model choose: Ollama's `/api/chat` has no
        server-side tool_choice knob, so we CANNOT hard-force "required" or a
        specific function. This is a known limitation surfaced here rather than
        silently honored; the Router decides what to do with zero tool_calls
        (we do NOT raise `tools_unsupported` — the capability exists).
        """
        # F14 guard (mirrors AnthropicAdapter.call_with_tools): only prepend a
        # system message when the caller supplied non-whitespace system text.
        ollama_messages: list[dict[str, Any]] = []
        if system and system.strip():
            ollama_messages.append({"role": "system", "content": system})
        # Story AI-1 (CR-3): translate OpenAI-shape tool-RESULT messages
        # (`role:"tool"`, keyed by `tool_call_id`) to Ollama's shape (keyed by
        # `tool_name`) so multi-turn tool rounds correlate. Non-tool messages
        # pass through unchanged.
        ollama_messages.extend(_translate_messages_openai_to_ollama(messages))

        # Temperature 0 is load-bearing for argument fidelity (see docstring).
        # Story 10-6-4 (AC-4): do NOT set `num_ctx` here. The F-10-6-1-W1
        # diagnosis measured it irrelevant to the ~19s cold-ingest latency
        # (forcing num_ctx=8192 changed ingest by ~0); the real lever is
        # keep_alive (prompt-cache preservation), applied below. A future dev
        # tempted to add num_ctx should read that diagnosis first.
        options: dict[str, Any] = {
            "num_predict": max_tokens_out,
            "temperature": temperature,
        }

        chat_kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": ollama_messages,
            "options": options,
            # Story 10-6-4: keep_alive is a top-level chat() kwarg (sibling of
            # options) — pins the model + preserves the prompt cache across the
            # chained tool-calls within a turn (calls 2..N cache-hit at ~4s).
            "keep_alive": self.keep_alive,
        }
        # tool_choice == "none" ⇒ omit tools entirely (disable tool use).
        if tool_choice != "none":
            chat_kwargs["tools"] = _translate_tools_openai_to_ollama(tools)

        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.chat(**chat_kwargs),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary: convert everything
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        message = raw_dict.get("message") or {}
        if not isinstance(message, dict):
            message = {}
        text = message.get("content") or ""
        if not isinstance(text, str):
            text = ""

        # Ollama native /api/chat returns tool_calls as
        # [{"function": {"name": ..., "arguments": <dict>}}]. Note arguments is
        # a DICT here; OpenAIToolCallFunction.arguments is a JSON STRING, so we
        # json.dumps it (mirrors the Anthropic tool_use translation). Ollama
        # does not supply a call id, so we synthesize one per index.
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls: list[OpenAIToolCall] = []
        if isinstance(raw_tool_calls, list):
            for i, tc in enumerate(raw_tool_calls):
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                if not isinstance(fn, dict):
                    fn = {}
                arg_input = fn.get("arguments") or {}
                try:
                    args_json = json.dumps(arg_input, separators=(",", ":"))
                except (TypeError, ValueError):
                    args_json = "{}"
                call_id = tc.get("id") or f"call_{i}"
                tool_calls.append(
                    OpenAIToolCall(
                        id=str(call_id),
                        type="function",
                        function=OpenAIToolCallFunction(
                            name=str(fn.get("name", "")),
                            arguments=args_json,
                        ),
                    )
                )

        # Story 10-7-1: fallback ONLY when the structured array yielded nothing.
        # Structured calls always win (AC-4) — content is not scanned when they
        # are present. When empty, attempt a STRICT rescue of a
        # `<tool_call>`-as-text block that qwen emitted in message.content.
        if not tool_calls and text and _TOOL_CALL_OPEN in text:
            block = _extract_first_tool_call_block(text)
            rescued = _rescue_text_tool_call(text)
            if rescued is not None:
                tool_calls.append(rescued)
                # CR F2: strip the promoted block from `.text` so a rescued turn
                # is shape-identical to a natively-structured one (whose `.text`
                # is prose, not raw `<tool_call>` markup). `tool_calls` is
                # authoritative for dispatch; `.text` becomes the residual prose.
                if block is not None:
                    text = text.replace(block, "", 1).strip()
                _log.info(
                    "rescued text-emitted tool call",
                    extra={
                        "event": "tool_call.rescue.promoted",
                        "tool_name": rescued.function.name,
                        "source": "message.content",
                    },
                )
            else:
                # CR F7: log the matched block (sanitized), not the whole
                # content — a long prose response would otherwise truncate the
                # actual offending block out of the 500-char window. Fall back to
                # the full text only when no complete block was found.
                _log.warning(
                    "malformed <tool_call> block declined, not promoted",
                    extra={
                        "event": "tool_call.rescue.declined",
                        "raw_block": _sanitize_text(block if block is not None else text)[:500],
                    },
                )

        tokens_in = int(raw_dict.get("prompt_eval_count") or 0)
        tokens_out = int(raw_dict.get("eval_count") or 0)

        # finish_reason: tool_calls win; otherwise honor a truncation signal
        # from Ollama's done_reason ("length"), else "stop".
        done_reason = raw_dict.get("done_reason") or ""
        finish_reason: Literal["stop", "tool_calls", "length"]
        if tool_calls:
            finish_reason = "tool_calls"
        elif done_reason == "length":
            finish_reason = "length"
        else:
            finish_reason = "stop"

        return ToolCallAdapterResponse(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=0,
            latency_ms=int(latency_ms),
            finish_reason=finish_reason,
            raw=raw_dict,
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        """Generate an embedding for ``text`` via Ollama's embeddings API (Story 3-4).

        Used by ``mailbot_api/ingest/embedding.py`` (the sole writer of the
        ``emails.embedding`` BLOB column). Uses a separate, shorter timeout
        (``_EMBEDDING_TIMEOUT_SECONDS = 15.0``) than the chat path because
        embeddings are typically much faster than chat completions — the
        instance ``timeout_seconds`` (chat budget, ~120s) is deliberately NOT
        used here.

        Story 10-6-4 (CR F1): ``keep_alive`` IS honored here — the ingest
        pipeline calls ``embed`` once per email, so pinning nomic resident
        (keep_alive=-1) avoids a per-email cold model-load, exactly the
        residency benefit the registry wires onto this adapter. (Before this
        fix ``embed`` passed neither field, so the nomic ``keep_alive`` was
        dead config — the false-symmetry the reviewer caught.)

        Defensive contract: ``len(vector) == dim`` is asserted at the adapter
        boundary — a misbehaving Ollama can't corrupt downstream consumers
        with mismatched shapes.
        """
        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.embeddings(
                    model=self.model_id,
                    prompt=text,
                    keep_alive=self.keep_alive,
                ),
                timeout=_EMBEDDING_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=_EMBEDDING_TIMEOUT_SECONDS,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        # Ollama's embeddings response carries the vector under the
        # ``embedding`` key. Convert to plain list of floats for the
        # ``EmbeddingResponse`` wire shape.
        vector_raw = raw_dict.get("embedding") or []
        if not isinstance(vector_raw, list):
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=(
                    f"ollama embeddings response 'embedding' field is not a list; "
                    f"got {type(vector_raw).__name__}"
                ),
            )
        try:
            vector = [float(v) for v in vector_raw]
        except (TypeError, ValueError) as exc:
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        dim = len(vector)
        if dim == 0:
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message="ollama embeddings response returned an empty vector",
            )

        # Ollama doesn't return token counts on the embed path; surface 0
        # (callers don't gate on this).
        tokens_in = int(raw_dict.get("prompt_eval_count") or 0)

        return EmbeddingResponse(
            vector=vector,
            dim=dim,
            tokens_in=tokens_in,
            latency_ms=int(latency_ms),
            raw=raw_dict,
        )


class AnthropicAdapter:
    """Adapter for Claude Haiku 4.5 + Opus 4.7 with Rule M ephemeral cache.

    Per FR-3.6 and architecture Rule M: every call tags the SYSTEM block with
    ``cache_control={"type": "ephemeral"}`` so Anthropic's 5-minute prompt cache
    is a primary cost lever from day one. Cache hits surface in the response's
    ``usage.cache_read_input_tokens`` field and propagate to
    ``AdapterResponse.cached_tokens_in`` for accurate cost accounting.

    The adapter is intentionally constructor-injectable for tests — pass a
    pre-configured ``anthropic.AsyncClient`` with an ``httpx.MockTransport``
    to exercise cold/warm cache scenarios without a live API.
    """

    def __init__(
        self,
        model_id: str,
        api_key: str | None = None,
        client: anthropic.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        if client is not None:
            self._client = client
        else:
            # Lazy + permits a test environment without a live API key.
            self._client = anthropic.AsyncClient(api_key=api_key or "test-placeholder-key")

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        from anthropic.types import MessageParam, TextBlockParam

        start_ns = time.monotonic_ns()
        # Rule M: SYSTEM block carries cache_control: ephemeral on every call.
        system_blocks: list[TextBlockParam] = [
            TextBlockParam(
                type="text",
                text=system,
                cache_control={"type": "ephemeral"},
            )
        ]
        messages: list[MessageParam] = [
            MessageParam(role="user", content=user),
        ]

        # F19 (Story 6-6.5 walk, 2026-06-04): Anthropic deprecated `temperature`
        # on `claude-opus-4-7` (reasoning model); passing it returns HTTP 400.
        # Omit on Opus 4.7; keep on Haiku and other models that still accept it.
        request_kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": max_tokens_out,
            "system": system_blocks,
            "messages": messages,
        }
        if self.model_id != "claude-opus-4-7":
            request_kwargs["temperature"] = temperature

        try:
            response = await asyncio.wait_for(
                self._client.messages.create(**request_kwargs),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        # Extract assistant text from content blocks.
        content_blocks = raw_dict.get("content") or []
        text_parts = [
            cb.get("text", "")
            for cb in content_blocks
            if isinstance(cb, dict) and cb.get("type") == "text"
        ]
        text = "".join(text_parts)

        usage = raw_dict.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)

        return AdapterResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cache_read + cache_creation,
            latency_ms=int(latency_ms),
            raw=raw_dict,
        )

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ChatCompletionToolDef],
        tool_choice: ChatCompletionToolChoice | None = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse:
        """Story 6-9 (F11 closure) — Anthropic tool-call surface.

        Translates the OpenAI-shape `messages` + `tools` into Anthropic's
        Messages API shape, dispatches with Rule M ephemeral cache on the
        system block, and translates the response content blocks back to
        OpenAI's `tool_calls` shape via the module-level translation
        helpers.

        When `tool_choice="none"`, the tools list is omitted entirely —
        Anthropic has no "force no tools" knob, and the contract matches
        OpenAI's behavior of disabling tool use for that call.
        """
        from anthropic.types import TextBlockParam

        anthropic_messages = _translate_messages_openai_to_anthropic(messages)
        anthropic_tool_choice = _translate_tool_choice_openai_to_anthropic(tool_choice)

        # F14 (Story 6-9 CP-2 walk attempt #4, 2026-06-04): Anthropic rejects
        # `cache_control: ephemeral` on empty text blocks with
        # `"system.0: cache_control cannot be set for empty text blocks"`.
        # When the caller passes no system message (or only whitespace), skip
        # the system block entirely rather than emit an empty cached block.
        system_blocks: list[TextBlockParam] = []
        if system and system.strip():
            system_blocks.append(
                TextBlockParam(
                    type="text",
                    text=system,
                    cache_control={"type": "ephemeral"},
                )
            )

        # Build the request kwargs. tools is omitted entirely when
        # tool_choice == "none" — see docstring + design doc §3.2.
        # F14: system field omitted entirely when no non-empty system text.
        # F19 (Story 6-6.5 walk, 2026-06-04): `temperature` deprecated on
        # claude-opus-4-7 (reasoning model); omit on Opus 4.7, keep on Haiku.
        request_kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": max_tokens_out,
            "messages": anthropic_messages,
        }
        if self.model_id != "claude-opus-4-7":
            request_kwargs["temperature"] = temperature
        if system_blocks:
            request_kwargs["system"] = system_blocks
        if tool_choice != "none":
            request_kwargs["tools"] = _translate_tools_openai_to_anthropic(tools)
            # CR-8 (Story 6-9 review): include tool_choice only when the
            # caller asked for one. Passing an explicit `{"type":"auto"}`
            # when the caller defaulted to None subtly varies Rule M's
            # cached prefix; omitting hits Anthropic's documented default.
            if (
                anthropic_tool_choice is not None
                and anthropic_tool_choice is not _OMIT_TOOL_CHOICE
            ):
                request_kwargs["tool_choice"] = anthropic_tool_choice

        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(**request_kwargs),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        content_blocks = raw_dict.get("content") or []
        text, tool_calls = _translate_response_anthropic_to_openai_tool_calls(
            content_blocks if isinstance(content_blocks, list) else []
        )

        usage = raw_dict.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)

        # Map Anthropic's stop_reason to OpenAI's finish_reason.
        # Anthropic uses: end_turn, max_tokens, stop_sequence, tool_use.
        # Per §3.3 of design doc: any tool_use block present ⇒ "tool_calls".
        stop_reason = raw_dict.get("stop_reason") or ""
        finish_reason: Literal["stop", "tool_calls", "length"]
        if tool_calls:
            finish_reason = "tool_calls"
        elif stop_reason == "max_tokens":
            finish_reason = "length"
        else:
            finish_reason = "stop"

        return ToolCallAdapterResponse(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cache_read + cache_creation,
            latency_ms=int(latency_ms),
            finish_reason=finish_reason,
            raw=raw_dict,
        )


__all__ = [
    "AdapterError",
    "AdapterProviderError",
    "AdapterResponse",
    "AdapterTimeout",
    "AnthropicAdapter",
    "EmbeddingResponse",
    "ModelAdapter",
    "OllamaAdapter",
    "ToolCallAdapterResponse",
]
