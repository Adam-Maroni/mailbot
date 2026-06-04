"""Story 6-10 — minimal stdlib-only MCP client for cron scripts.

Shared by `pull_and_deliver.py` and `digest_prepare.py`. Both are
``no_agent=True`` cron jobs running inside the Hermes container; the
container has Python 3 but we avoid third-party deps to keep the cron
surface portable to any Hermes deployment.

Transport: MCP streamable-HTTP over ``http://mailbot-api:8000/mcp/``
(Story 6-6.6 closed the trailing-slash routing; Story 6-6.7 closed the
transport-security allow-list). Bearer auth via ``MAILBOT_ROUTER_KEY``.

Session model: FastMCP requires `initialize` first; subsequent
`tools/call` requests carry the `Mcp-Session-Id` header echoed from the
initialize response.
"""

from __future__ import annotations

import json
import sys
import uuid
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

DEFAULT_BASE_URL = "http://mailbot-api:8000/mcp/"
HTTP_TIMEOUT_SECONDS = 15
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPCallError(RuntimeError):
    """Surfaces any non-success outcome from the MCP transport layer.

    Distinct from JSON-RPC `error` payloads (those are caught and
    re-raised with the error.message preserved) — `MCPCallError` covers
    transport failures (timeout, 4xx/5xx, bad framing) so the caller
    can distinguish "downstream verb failed" from "MCP server unreachable".
    """


def log_event(event: str, **fields: Any) -> None:
    """Emit one structured log line to stderr.

    Stderr is the operational telemetry channel; stdout is what Hermes's
    cron delivery posts to Discord, so any non-message output must go to
    stderr to keep the cron-message output clean.
    """
    record = {"event": event, **fields}
    sys.stderr.write(json.dumps(record) + "\n")
    sys.stderr.flush()


def mcp_call(
    base_url: str,
    api_key: str,
    method: str,
    params: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Issue one JSON-RPC call over MCP streamable-HTTP.

    Returns ``(result_dict, response_session_id)``. The session id flows
    from the server's ``Mcp-Session-Id`` response header on the initialize
    call; subsequent calls echo it back via the request header.
    """
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": str(uuid.uuid4()),
    }
    if params is not None:
        payload["params"] = params
    body = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {api_key}",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    # Defensive scheme check: a misconfigured `MAILBOT_MCP_URL` (e.g.,
    # `file:///etc/passwd` from a botched env-var-edit) must NOT be
    # opened by urlopen. Restrict to HTTP/HTTPS — this is the only set
    # MailBot's MCP transport ever uses.
    if not base_url.lower().startswith(("http://", "https://")):
        raise MCPCallError(
            f"refusing to open non-http URL: {base_url!r}"
        )

    # S310 noqa: the scheme is guarded above to http(s) only; this is
    # the MCP-transport call site, fundamentally an HTTP client.
    req = urllib_request.Request(  # noqa: S310
        base_url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib_request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            response_session_id = resp.headers.get("Mcp-Session-Id")
            raw = resp.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        raise MCPCallError(
            f"MCP HTTP error {exc.code} on method={method}: {exc.reason}"
        ) from exc
    except urllib_error.URLError as exc:
        raise MCPCallError(
            f"MCP transport error on method={method}: {exc}"
        ) from exc
    # P7: socket.timeout is a subclass of OSError (since Python 3.3) but
    # NOT of urllib.error.URLError on older interpreters and not on all
    # urlopen code paths. Catching plain OSError here covers timeout +
    # ConnectionResetError + similar mid-read socket failures the URLError
    # handler can miss, surfacing them as MCPCallError so the caller's
    # cron-tick error path runs.
    except OSError as exc:
        raise MCPCallError(
            f"MCP socket error on method={method}: {exc}"
        ) from exc

    # P3: streamable-HTTP may return SSE-framed JSON with multiple events
    # per response (e.g., a progress notification followed by the result,
    # or a ping followed by the result). Walk every `data:` line, try to
    # parse each as JSON, and pick the frame that carries `id` matching
    # our request. Fall back to the last parseable data frame. This is
    # more robust than the original "first data: line wins" loop which
    # silently mis-read multi-event streams.
    if raw.startswith("event:"):
        request_id = payload["id"]
        matched_data: str | None = None
        last_parseable: str | None = None
        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            data_text = line[len("data:") :].strip()
            if not data_text:
                continue
            try:
                candidate = json.loads(data_text)
            except json.JSONDecodeError:
                continue
            last_parseable = data_text
            if isinstance(candidate, dict) and candidate.get("id") == request_id:
                matched_data = data_text
                break
        if matched_data is not None:
            raw = matched_data
        elif last_parseable is not None:
            raw = last_parseable
        else:
            raise MCPCallError(
                f"SSE response on method={method} contained no parseable data frame"
            )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPCallError(
            f"MCP response not JSON on method={method}: {raw!r}"
        ) from exc

    if "error" in parsed:
        err = parsed["error"]
        raise MCPCallError(
            f"MCP JSON-RPC error on method={method}: "
            f"code={err.get('code')} message={err.get('message')!r}"
        )

    result = parsed.get("result", {})
    if not isinstance(result, dict):
        raise MCPCallError(
            f"MCP result not a dict on method={method}: "
            f"{type(result).__name__}"
        )
    return result, response_session_id


def open_session(base_url: str, api_key: str, client_name: str) -> str:
    """Initialize an MCP session and return its session id.

    FastMCP requires a session id on every tool call after the handshake.
    The id flows back on the ``Mcp-Session-Id`` response header.
    """
    _, session_id = mcp_call(
        base_url,
        api_key,
        "initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": "0.1.0"},
        },
    )
    if not session_id:
        raise MCPCallError(
            "MCP initialize succeeded but no Mcp-Session-Id header returned"
        )
    return session_id


def tool_call(
    base_url: str,
    api_key: str,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Invoke an MCP tool and return the structured result payload.

    FastMCP-2.x ships ``result.structuredContent`` for typed outputs —
    that's our primary path. Fall back to parsing ``content[0].text`` as
    JSON if ``structuredContent`` is absent (older FastMCP or wire-shape
    variance during transport upgrades).
    """
    result, _ = mcp_call(
        base_url,
        api_key,
        "tools/call",
        params={"name": tool_name, "arguments": arguments},
        session_id=session_id,
    )
    if "structuredContent" in result:
        structured = result["structuredContent"]
        if isinstance(structured, dict):
            return structured
    content = result.get("content", [])
    if content and isinstance(content, list):
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            text = first.get("text", "")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise MCPCallError(
                    f"tool {tool_name!r} text content not JSON: {text!r}"
                ) from exc
            if isinstance(parsed, dict):
                return parsed
    raise MCPCallError(
        f"tool {tool_name!r} returned no usable content; "
        f"result keys: {list(result)}"
    )
