"""Unit tests for mailbot_api/router/errors.py (Story 2-1).

Covers:
- ErrorCode enum membership + value contract (AC-2)
- RouterError code-rejection invariant (AC-3)
- RouterResult (ok, error) consistency invariant (AC-3)
- sanitize_error redaction rules (AC-4)
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from mailbot_api.router.errors import (
    ErrorCode,
    RouterError,
    RouterResult,
    sanitize_error,
)

# ---- AC-2: ErrorCode enum membership ----

_EXPECTED_ERROR_CODES = {
    "SCHEMA_VALIDATION_FAILED": "schema_validation_failed",
    "TIMEOUT": "timeout",
    "BUDGET_EXCEEDED": "budget_exceeded",
    "PER_CALL_THRESHOLD_EXCEEDED": "per_call_threshold_exceeded",
    "PROVIDER_ERROR": "provider_error",
    "MONTHLY_BUDGET_EXCEEDED": "monthly_budget_exceeded",
    "DEGRADED_MODE_BLOCKED": "degraded_mode_blocked",
    "LOOP_DETECTED": "loop_detected",
    "SENSITIVITY_BLOCKS_API": "sensitivity_blocks_api",
    "NEEDS_SENSITIVITY_CONFIRMATION": "needs_sensitivity_confirmation",
    "SENSITIVITY_NOT_CLASSIFIED": "sensitivity_not_classified",
    "RATE_LIMITED": "rate_limited",
    "STATE_DRIFT_ETAG": "state_drift_etag",
    "TARGET_DELETED": "target_deleted",
    "STATE_DRIFT_NOOP": "state_drift_noop",
}


def test_error_code_has_exactly_15_members() -> None:
    members = {m.name for m in ErrorCode}
    assert members == set(_EXPECTED_ERROR_CODES.keys()), (
        f"ErrorCode membership drift detected. "
        f"Missing: {set(_EXPECTED_ERROR_CODES) - members}. "
        f"Extra: {members - set(_EXPECTED_ERROR_CODES)}."
    )


@pytest.mark.parametrize(("name", "expected_value"), list(_EXPECTED_ERROR_CODES.items()))
def test_error_code_value_is_lowercase_snake_case(name: str, expected_value: str) -> None:
    assert ErrorCode[name].value == expected_value


def test_error_code_is_str_subclass() -> None:
    """`str`-backed Enum so values serialize cleanly to JSON / SQL."""
    assert issubclass(ErrorCode, str)
    assert ErrorCode.TIMEOUT == "timeout"  # equality with raw string


# ---- AC-3: RouterError ----


def test_router_error_accepts_valid_code() -> None:
    err = RouterError(code=ErrorCode.TIMEOUT, message="boom", retryable=False)
    assert err.code is ErrorCode.TIMEOUT
    assert err.model_attempted == []


def test_router_error_rejects_free_string_code() -> None:
    with pytest.raises(ValidationError):
        RouterError(code="not_a_real_code", message="boom", retryable=False)  # type: ignore[arg-type]


def test_router_error_accepts_string_form_of_enum_value() -> None:
    """str-backed Enum: passing the .value should coerce to the enum member."""
    err = RouterError(code="timeout", message="boom", retryable=False)  # type: ignore[arg-type]
    assert err.code is ErrorCode.TIMEOUT


def test_router_error_model_attempted_defaults_to_empty_list() -> None:
    err = RouterError(code=ErrorCode.PROVIDER_ERROR, message="x", retryable=True)
    assert err.model_attempted == []


# ---- AC-3: RouterResult (ok, error) consistency ----


class _SampleOutput(BaseModel):
    label: str


def test_router_result_ok_with_output_succeeds() -> None:
    r = RouterResult(ok=True, output=_SampleOutput(label="x"), model_used="qwen")
    assert r.ok is True
    assert r.error is None
    assert isinstance(r.output, _SampleOutput)
    assert r.output.label == "x"


def test_router_result_failure_with_error_succeeds() -> None:
    err = RouterError(code=ErrorCode.TIMEOUT, message="t/o", retryable=False)
    r = RouterResult(ok=False, error=err, model_used="qwen")
    assert r.ok is False
    assert r.error is err
    assert r.output is None


def test_router_result_ok_true_with_error_raises() -> None:
    err = RouterError(code=ErrorCode.TIMEOUT, message="t/o", retryable=False)
    with pytest.raises(ValidationError):
        RouterResult(ok=True, error=err)


def test_router_result_ok_false_without_error_raises() -> None:
    with pytest.raises(ValidationError):
        RouterResult(ok=False, error=None)


def test_router_result_defaults_zero_cost_zero_latency() -> None:
    r = RouterResult(ok=True, output=_SampleOutput(label="x"))
    assert r.cost_usd == 0.0
    assert r.latency_ms == 0
    assert r.tokens_in == 0
    assert r.tokens_out == 0
    assert r.cached_tokens_in == 0
    assert r.model_used == ""


# ---- AC-4: sanitize_error ----


def test_sanitize_error_redacts_bearer_token() -> None:
    exc = RuntimeError("auth failed with Bearer eyJhbGciOiJIUzI1NiJ9.xyz.abc on /me")
    msg = sanitize_error(exc)
    assert "Bearer eyJ" not in msg
    assert "[REDACTED_BEARER]" in msg
    # Exception type prefix is preserved.
    assert msg.startswith("RuntimeError:")


def test_sanitize_error_redacts_sk_key() -> None:
    exc = RuntimeError("apikey sk-AbCdEfGh1234567890abcdefghIJ was rejected")
    msg = sanitize_error(exc)
    assert "sk-AbCd" not in msg
    assert "[REDACTED_SK_KEY]" in msg


def test_sanitize_error_redacts_url_query_token() -> None:
    exc = RuntimeError(
        "GET https://api.example.com/oauth?access_token=secret123&user=adam failed"
    )
    msg = sanitize_error(exc)
    assert "secret123" not in msg
    assert "access_token=[REDACTED_QUERY_TOKEN]" in msg


def test_sanitize_error_redacts_secret_file_paths() -> None:
    exc = RuntimeError("cannot read /etc/secrets/anthropic.env at startup")
    msg = sanitize_error(exc)
    assert "/etc/secrets/anthropic.env" not in msg
    assert "[REDACTED_PATH]" in msg


def test_sanitize_error_collapses_to_single_line() -> None:
    exc = RuntimeError("line1\nline2\r\nline3")
    msg = sanitize_error(exc)
    assert "\n" not in msg
    assert "\r" not in msg
    assert "line1" in msg
    assert "line2" in msg
    assert "line3" in msg
    # Lines should be joined with "; " separator.
    assert "; " in msg


def test_sanitize_error_preserves_exception_type_in_message() -> None:
    exc = ValueError("just a value error")
    assert sanitize_error(exc).startswith("ValueError:")


def test_sanitize_error_returns_stripped_string() -> None:
    """No leading/trailing whitespace in the redacted message."""
    exc = RuntimeError("   surrounded by space   ")
    msg = sanitize_error(exc)
    assert msg == msg.strip()


# ---- Story 2-1 review fix R2: extended URL query-param keys per AC-4 ----


@pytest.mark.parametrize(
    "key",
    ["token", "code", "access_token", "refresh_token", "api_key", "key", "secret"],
)
def test_sanitize_error_redacts_all_ac4_url_query_keys(key: str) -> None:
    exc = RuntimeError(f"GET https://api.example.com/x?{key}=very_secret_value rejected")
    msg = sanitize_error(exc)
    assert "very_secret_value" not in msg, (
        f"key={key} value leaked through: {msg!r}"
    )
    assert "[REDACTED_QUERY_TOKEN]" in msg


# ---- Story 2-1 review fix R3: extended secret-file extensions per AC-4 ----


@pytest.mark.parametrize(
    "ext",
    ["env", "key", "pem", "p12", "pfx"],
)
def test_sanitize_error_redacts_all_ac4_secret_file_extensions(ext: str) -> None:
    exc = RuntimeError(f"cannot read /etc/secrets/credentials.{ext} at startup")
    msg = sanitize_error(exc)
    assert f"credentials.{ext}" not in msg, (
        f"ext=.{ext} path leaked through: {msg!r}"
    )
    assert "[REDACTED_PATH]" in msg


# ---- Story 2-1 review fix R4: defensive str(exc) path ----


class _ExcWithBrokenStr(RuntimeError):
    """Custom exception whose __str__ raises — sanitize_error must NOT propagate."""

    def __str__(self) -> str:  # pragma: no cover — intentionally raises
        raise ValueError("intentionally broken __str__")


def test_sanitize_error_handles_exception_with_broken_str_method() -> None:
    """The function MUST return a fallback string, not re-raise."""
    exc = _ExcWithBrokenStr()
    msg = sanitize_error(exc)
    # Type name is preserved; body falls back to the sentinel.
    assert msg.startswith("_ExcWithBrokenStr:")
    assert "<unprintable exception>" in msg
