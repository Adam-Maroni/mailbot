"""Structured JSON logging per architecture §AR-PAT-3 and FR-7.3.

- One JSON object per line on stdout (Docker captures it).
- Fields: ts (UTC ISO-8601 Z), level, module, event (dotted namespace), plus context.
- Sanitizer strips token-shaped strings, URLs containing token/code/access_token query
  params, sk-* secrets, and file paths matching .env/.key/.pem.
- No file handlers — Docker stdout is the canonical sink.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

# Sanitizer patterns per AC-4 live in observability/_redaction.py (extracted
# in Story 2-1 review fix R9 — sharing with router/errors.py without
# cross-module private-symbol imports).
from mailbot_api.observability._redaction import (
    BEARER_TOKEN_RE,
    SECRET_FILE_RE,
    SK_KEY_RE,
    URL_TOKEN_QUERY_RE,
)
from mailbot_api.observability.timestamps import utc_z_now


def sanitize(value: Any) -> Any:
    """Recursively sanitize a value for log output.

    Strings get pattern replacements; dicts/lists/tuples recurse; other types pass
    through unchanged (but JSON-encoded later). Public so one-shot scripts in
    ``scripts/`` can reuse the same redaction rules before printing to stderr.
    """
    if isinstance(value, str):
        v = BEARER_TOKEN_RE.sub("[REDACTED_BEARER]", value)
        v = SK_KEY_RE.sub("[REDACTED_SK_KEY]", v)
        v = URL_TOKEN_QUERY_RE.sub(r"\1[REDACTED_QUERY_TOKEN]", v)
        v = SECRET_FILE_RE.sub("[REDACTED_PATH]", v)
        return v
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    return value


def _utc_iso8601() -> str:
    """Return the current UTC time as ISO-8601 with Z suffix (AR-PAT-3).

    Microsecond-precision since 2026-06-02 (Epic 4 retro action item #3) —
    delegates to the shared :func:`mailbot_api.observability.timestamps.utc_z_now`.
    """
    return utc_z_now()


class JsonFormatter(logging.Formatter):
    """Logging formatter that emits one JSON object per line, sanitized.

    Standard `LogRecord` fields land as top-level keys; any extra context passed
    via `logger.info("msg", extra={...})` is merged in.
    """

    # LogRecord built-in attributes we don't re-emit as context. Note: we
    # deliberately do NOT exclude "filename" because callers commonly pass
    # `extra={"filename": "001_init.sql"}` etc. as legitimate context. The
    # cost: if a caller doesn't set it, LogRecord's built-in source filename
    # (e.g., "logging.py") may leak. Acceptable — it's just the caller's
    # __file__, not sensitive.
    _BUILTIN_ATTRS = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "msg",
            "message",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        # Resolve the message (handles %s-formatting + extras).
        message = record.getMessage()

        # Extract any user-supplied extras.
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in self._BUILTIN_ATTRS and not k.startswith("_")
        }

        payload: dict[str, Any] = {
            "ts": _utc_iso8601(),
            "level": record.levelname.lower(),
            "module": record.name,
            "event": extras.pop("event", message),
        }

        # If the message wasn't moved into `event`, preserve it as a `message` field.
        if payload["event"] != message:
            payload["message"] = message

        # Merge sanitized extras.
        for k, v in extras.items():
            payload[k] = v

        # Add exception info if present.
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            # Do NOT include the exc traceback — NFR-SEC-4 mandates no stack frames
            # leak via the logging surface. Sanitized error message only.

        sanitized = sanitize(payload)
        return json.dumps(sanitized, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger writing to stdout.

    Idempotent — calling multiple times replaces the handler (test helpers rely on this).
    """
    root = logging.getLogger()
    root.setLevel(level)
    # Remove any pre-existing handlers (idempotent setup).
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
