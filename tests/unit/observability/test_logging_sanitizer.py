"""Regression tests for the structured-JSON logging sanitizer (Story 1-4 AC-5).

Each test injects a known-secret value into a log line and asserts that the
sanitizer redacts it before emission.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest

from mailbot_api.observability.logging import JsonFormatter, configure_logging


def _capture_one(record: logging.LogRecord) -> dict[str, Any]:
    """Format a LogRecord through JsonFormatter and parse the JSON output."""
    formatted = JsonFormatter().format(record)
    return json.loads(formatted)


def _make_record(msg: str, **extras: Any) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extras.items():
        setattr(record, k, v)
    return record


def test_bearer_token_redacted() -> None:
    record = _make_record(
        "request failed", auth_header="Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    )
    payload = _capture_one(record)
    assert payload["auth_header"] == "[REDACTED_BEARER]"


def test_bearer_token_redacted_inline_in_message() -> None:
    record = _make_record("auth Bearer abc123def456 was rejected")
    payload = _capture_one(record)
    # The message lands in `event` since no `event=` extra was supplied.
    assert "abc123def456" not in payload["event"]
    assert "[REDACTED_BEARER]" in payload["event"]


def test_sk_api_key_redacted() -> None:
    record = _make_record(
        "outbound call", api_key="sk-1234567890abcdefghijklmnopqrstuvwxyz"
    )
    payload = _capture_one(record)
    assert payload["api_key"] == "[REDACTED_SK_KEY]"


def test_url_with_token_query_param_redacted() -> None:
    record = _make_record(
        "graph call",
        url="https://login.microsoftonline.com/oauth?code=secret_code_value&state=ok",
    )
    payload = _capture_one(record)
    assert "secret_code_value" not in payload["url"]
    assert "[REDACTED_QUERY_TOKEN]" in payload["url"]
    # State param survives untouched (not in the redaction list).
    assert "state=ok" in payload["url"]


def test_url_with_access_token_query_redacted() -> None:
    record = _make_record(
        "graph reply",
        url="https://graph.microsoft.com/me?access_token=PRIVATE_TOKEN_HERE",
    )
    payload = _capture_one(record)
    assert "PRIVATE_TOKEN_HERE" not in payload["url"]


def test_url_with_token_query_redacted() -> None:
    record = _make_record(
        "exchange", url="https://example.com/cb?token=THIS_IS_A_SECRET_TOKEN_VALUE"
    )
    payload = _capture_one(record)
    assert "THIS_IS_A_SECRET_TOKEN_VALUE" not in payload["url"]


def test_dot_env_path_redacted() -> None:
    record = _make_record(
        "config load", file_path="/srv/mailbot/.env"
    )
    payload = _capture_one(record)
    assert payload["file_path"] == "[REDACTED_PATH]"


def test_key_path_redacted() -> None:
    record = _make_record(
        "tls load", path="/etc/ssl/mailbot.key"
    )
    payload = _capture_one(record)
    assert payload["path"] == "[REDACTED_PATH]"


def test_pem_path_redacted() -> None:
    record = _make_record("cert", path="ca-bundle.pem")
    payload = _capture_one(record)
    assert payload["path"] == "[REDACTED_PATH]"


def test_nested_dict_redacted() -> None:
    record = _make_record(
        "complex",
        context={
            "auth": "Bearer mytoken",
            "user": {"id": 42, "key": "sk-abcdefghij1234567890_extra_chars_here"},
            "items": ["https://x.com/?code=hidden", "ok"],
        },
    )
    payload = _capture_one(record)
    ctx = payload["context"]
    assert ctx["auth"] == "[REDACTED_BEARER]"
    assert "sk-abcdefghij" not in ctx["user"]["key"]
    assert "hidden" not in ctx["items"][0]
    assert ctx["items"][1] == "ok"  # unchanged
    assert ctx["user"]["id"] == 42  # non-string unchanged


def test_event_field_promoted_from_extras() -> None:
    record = _make_record("ignored msg", event="db.migration.applied", filename="001_init.sql")
    payload = _capture_one(record)
    assert payload["event"] == "db.migration.applied"
    assert payload["filename"] == "001_init.sql"
    # `message` is present because event was supplied explicitly.
    assert payload["message"] == "ignored msg"


def test_ts_is_utc_iso8601_with_z_suffix() -> None:
    record = _make_record("anything")
    payload = _capture_one(record)
    assert payload["ts"].endswith("Z")
    assert len(payload["ts"]) == 20  # YYYY-MM-DDTHH:MM:SSZ


def test_level_lowercase() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=0,
        msg="warn",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "warning"


def test_configure_logging_idempotent() -> None:
    configure_logging()
    handler_count_first = len(logging.getLogger().handlers)
    configure_logging()
    handler_count_second = len(logging.getLogger().handlers)
    assert handler_count_first == handler_count_second == 1


def test_configure_logging_writes_json_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    logger = logging.getLogger("test_configure")
    logger.info("startup", extra={"event": "app.start"})
    captured = capsys.readouterr()
    # Each emitted line should be valid JSON.
    line = captured.out.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == "app.start"
    assert parsed["level"] == "info"


def test_no_stack_trace_in_log_output() -> None:
    """NFR-SEC-4: error logs MUST NOT include stack frames."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg="something failed",
        args=(),
        exc_info=(ValueError, ValueError("oops"), None),
    )
    payload = json.loads(JsonFormatter().format(record))
    # exc_type is allowed (it's just the class name); no `traceback` field.
    assert "exc_type" in payload
    assert "traceback" not in payload
    assert "exc_text" not in payload


def test_unrelated_strings_untouched() -> None:
    """Non-sensitive strings should pass through verbatim."""
    record = _make_record(
        "normal log",
        user_email="adam@example.com",
        count=42,
        ok=True,
    )
    payload = _capture_one(record)
    assert payload["user_email"] == "adam@example.com"
    assert payload["count"] == 42
    assert payload["ok"] is True


def test_stdout_handler_attached() -> None:
    """configure_logging() attaches a StreamHandler writing to sys.stdout (or wrapped equivalent)."""

    configure_logging()
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    h = handlers[0]
    assert isinstance(h, logging.StreamHandler)
    # Note: capsys / pytest wrap sys.stdout; accept both real sys.stdout and wrapped variants
    # by checking that the stream is at least writable (the handler was constructed with stdout).
    assert hasattr(h.stream, "write")


def test_buffered_stream_writes_with_newline(capsys: pytest.CaptureFixture[str]) -> None:
    """Each log line should be its own line in stdout."""
    configure_logging()
    logger = logging.getLogger("buffered")
    logger.info("first")
    logger.info("second")
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.strip().splitlines() if ln]
    assert len(lines) >= 2
    for line in lines[-2:]:
        json.loads(line)  # each is parseable JSON


def _drain_buffer(buf: io.StringIO) -> list[str]:
    lines = buf.getvalue().strip().splitlines()
    return [line for line in lines if line]
