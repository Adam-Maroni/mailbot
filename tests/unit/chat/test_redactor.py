"""Story 5-7 AC-4 — offline unit tests for the chat-input redactor."""

from __future__ import annotations

import importlib
import logging
import time

import pytest

from mailbot_api.chat.redactor import RedactionKind, RedactionMatch, redact

# Sample credentials shaped to trip each pattern. These are NOT real keys —
# the prefix bytes are correct but the entropy is fixed test text.
_SAMPLE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
_SAMPLE_OPENAI_KEY = "sk-proj-1234567890ABCDEFghijklmnopQR"
_SAMPLE_ANTHROPIC_KEY = "sk-ant-api03-1234567890abcdefghijklmnopQRSTUV"
_SAMPLE_HEX_BLOB = "a" * 64  # 64-char hex — SHA-256 length, above the 40 floor
_SAMPLE_BEARER = "Bearer abcdefghijklmnopqrstuvwxyz12=="  # 28 chars after Bearer
_SAMPLE_SSH = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU\n"
    # 64-char hex inside the body — above the hex_blob 40-char floor, so the
    # SSH-first ordering test (CR-4 fix) actually exercises the
    # SSH-swallows-hex-inside-body scenario.
    "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


# ---- per-pattern positive cases (6 tests) ----


@pytest.mark.parametrize(
    "sample,kind",
    [
        (_SAMPLE_JWT, RedactionKind.JWT),
        (_SAMPLE_OPENAI_KEY, RedactionKind.OPENAI_KEY),
        (_SAMPLE_ANTHROPIC_KEY, RedactionKind.ANTHROPIC_KEY),
        (_SAMPLE_HEX_BLOB, RedactionKind.HEX_BLOB),
        (_SAMPLE_BEARER, RedactionKind.BEARER_TOKEN),
        (_SAMPLE_SSH, RedactionKind.SSH_KEY_FRAGMENT),
    ],
    ids=["jwt", "openai_key", "anthropic_key", "hex_blob", "bearer_token", "ssh_key_fragment"],
)
def test_pattern_positive(sample: str, kind: RedactionKind) -> None:
    """AC-4: each pattern fires on a clear instance; substitution names the kind."""
    redacted, matches = redact(sample)
    assert f"[REDACTED:{kind.value}]" in redacted
    # The original credential bytes are gone (modulo the SSH case where there
    # may be ambient text that isn't a credential).
    if kind is not RedactionKind.SSH_KEY_FRAGMENT:
        assert sample not in redacted
    assert len(matches) >= 1
    assert any(m.kind is kind for m in matches)


# ---- per-pattern negative cases (4 tests) ----


def test_uuid_32_chars_stays_untouched() -> None:
    """AC-4: a 32-char UUID is below the 40-char hex-blob floor."""
    uuid_like = "deadbeef" * 4  # 32 hex chars
    text = f"see id {uuid_like} for details"
    redacted, matches = redact(text)
    assert redacted == text
    assert matches == []


def test_short_bearer_below_floor_stays_untouched() -> None:
    """AC-4: a 19-char Bearer token is below the 20-char floor."""
    text = "Bearer 1234567890abcdefghi"  # 19 chars after Bearer
    redacted, matches = redact(text)
    assert redacted == text
    assert all(m.kind is not RedactionKind.BEARER_TOKEN for m in matches)


def test_two_segment_dot_string_is_not_a_jwt() -> None:
    """AC-4: ``a.b`` (only 1 dot) is not a JWT; JWTs need 3 segments."""
    text = "example.com domain"
    redacted, matches = redact(text)
    assert redacted == text
    assert all(m.kind is not RedactionKind.JWT for m in matches)


def test_bearer_base64_padding_is_fully_redacted() -> None:
    """CR-3 regression: a Bearer token ending in `==` padding must be
    redacted including the padding chars. The original trailing `\\b` left
    the `==` unredacted in the output."""
    text = "header: Bearer abcdefghijklmnopqrstuvwxyz12=="
    redacted, matches = redact(text)
    # The `==` padding must NOT survive in the redacted output.
    assert "==" not in redacted, (
        f"base64 padding leaked into output: {redacted!r}"
    )
    assert any(m.kind is RedactionKind.BEARER_TOKEN for m in matches)


def test_three_segment_short_string_below_jwt_floor_stays_untouched() -> None:
    """CR-6: a 3-segment string that matches the JWT regex but is below the
    30-char length floor must survive untouched. Pins the post-match length
    check in `_sub` (`if _kind is RedactionKind.JWT and len(matched_text) <
    _JWT_MIN_LENGTH: return matched_text`)."""
    text = "tag a.b.cdefghijklm end"  # 3 dot-separated; full match is 15 chars
    redacted, matches = redact(text)
    assert all(m.kind is not RedactionKind.JWT for m in matches)
    assert "[REDACTED:jwt]" not in redacted


def test_lowercase_bearer_stays_untouched() -> None:
    """AC-4: the Bearer pattern is case-sensitive per HTTP standard."""
    text = "bearer 1234567890ABCDEFGHIJKLMN"
    redacted, matches = redact(text)
    assert all(m.kind is not RedactionKind.BEARER_TOKEN for m in matches)
    # The hex-blob may still catch a substring; the assertion is specifically
    # that bearer_token did not.
    assert redacted == text or RedactionKind.HEX_BLOB.value in redacted


# ---- ordering tests ----


def test_anthropic_before_openai_ordering() -> None:
    """AC-4: sk-ant-... must redact as anthropic_key, NOT openai_key."""
    redacted, matches = redact(_SAMPLE_ANTHROPIC_KEY)
    assert "[REDACTED:anthropic_key]" in redacted
    assert "[REDACTED:openai_key]" not in redacted
    assert all(m.kind is RedactionKind.ANTHROPIC_KEY for m in matches)


def test_ssh_first_ordering_swallows_hex_inside_key_body() -> None:
    """AC-4: an SSH private-key block whose body contains hex MUST redact as
    ssh_key_fragment as a single contiguous match — the hex blob pattern must
    NOT also fire inside the now-replaced key body."""
    redacted, matches = redact(_SAMPLE_SSH)
    assert "[REDACTED:ssh_key_fragment]" in redacted
    ssh_matches = [m for m in matches if m.kind is RedactionKind.SSH_KEY_FRAGMENT]
    hex_matches = [m for m in matches if m.kind is RedactionKind.HEX_BLOB]
    assert len(ssh_matches) == 1
    # The hex inside the key body should NOT match — the SSH replacement
    # already turned the original chars into the substitution string.
    assert len(hex_matches) == 0


# ---- mixed content + empty input + position semantics ----


def test_mixed_content_preserves_surrounding_text() -> None:
    """AC-4: text around a credential is preserved verbatim."""
    text = f"My API key is {_SAMPLE_ANTHROPIC_KEY} please rotate it"
    redacted, matches = redact(text)
    assert redacted.startswith("My API key is ")
    assert redacted.endswith(" please rotate it")
    assert "[REDACTED:anthropic_key]" in redacted
    assert len(matches) == 1
    assert matches[0].kind is RedactionKind.ANTHROPIC_KEY


def test_empty_input_returns_empty_tuple() -> None:
    """AC-4: redact('') returns ('', [])."""
    redacted, matches = redact("")
    assert redacted == ""
    assert matches == []


def test_position_indexes_into_original_text() -> None:
    """AC-4: RedactionMatch.position indexes into the ORIGINAL text, not
    the post-redaction text. Separators are whitespace so the word-boundary
    halts the credential match cleanly."""
    text = f"prefix {_SAMPLE_ANTHROPIC_KEY} suffix"
    _, matches = redact(text)
    assert len(matches) == 1
    start, end = matches[0].position
    assert text[start:end] == _SAMPLE_ANTHROPIC_KEY


# ---- performance + logging ----


def test_redaction_under_50ms_on_10kb_input() -> None:
    """AC-5: redacting a 10 KB chat message completes in < 50 ms (Windows +
    pytest overhead inflates the AC's 5ms floor; the test exists to catch
    regex-recompilation regressions, not to pin wall-clock precisely)."""
    # 10 KB of mixed text with one credential embedded.
    chunk = "the quick brown fox jumps over the lazy dog. " * 250
    payload = chunk + _SAMPLE_ANTHROPIC_KEY + " more text"
    # CR-5 fix: real assertion (was `or True` dead code).
    assert len(payload) >= 10 * 1024, (
        f"perf test payload must be >= 10 KB; got {len(payload)}"
    )
    t0 = time.perf_counter()
    redacted, matches = redact(payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50, f"redact took {elapsed_ms:.1f} ms (regex recompile?)"
    assert "[REDACTED:anthropic_key]" in redacted


def test_logging_emits_per_match_event_without_value(caplog) -> None:
    """AC-3: every match emits exactly one INFO log line with event,
    kind, position, prefix — and NEVER the matched value itself."""
    text = f"key: {_SAMPLE_OPENAI_KEY}"
    with caplog.at_level(logging.INFO, logger="mailbot_api.chat.redactor"):
        redacted, matches = redact(text)
    assert len(matches) == 1
    redactor_records = [
        r for r in caplog.records if getattr(r, "event", None) == "chat.redactor.match"
    ]
    assert len(redactor_records) == 1
    rec = redactor_records[0]
    assert getattr(rec, "kind") == RedactionKind.OPENAI_KEY.value
    assert hasattr(rec, "position")
    assert hasattr(rec, "prefix")
    # AC-3: NEVER log the matched value itself.
    for record in caplog.records:
        assert _SAMPLE_OPENAI_KEY not in record.getMessage()
        # Also not in extras as a value (we check the log dict pieces).
        for attr in ("prefix",):
            val = getattr(record, attr, None)
            if val:
                assert _SAMPLE_OPENAI_KEY not in val


# ---- module-load + cache test ----


def test_patterns_compiled_once_at_module_load() -> None:
    """AC-5: re-importing the module does not re-trigger pattern compilation
    in a way that bloats per-call cost. We sanity-check the _PATTERNS tuple is
    a tuple of (kind, compiled regex) pairs at import time."""
    mod = importlib.import_module("mailbot_api.chat.redactor")
    assert isinstance(mod._PATTERNS, tuple)
    assert len(mod._PATTERNS) == 6
    import re as _re_mod

    for kind, pattern in mod._PATTERNS:
        assert isinstance(kind, RedactionKind)
        assert isinstance(pattern, _re_mod.Pattern)


# ---- redaction substitution shape ----


def test_redaction_substitution_format_carries_kind() -> None:
    """AC-1: substitution string is exactly ``[REDACTED:<kind>]``, naming the
    kind so audit logs identify what was caught."""
    redacted, matches = redact(_SAMPLE_HEX_BLOB)
    assert "[REDACTED:hex_blob]" in redacted
    assert matches[0].redaction == "[REDACTED:hex_blob]"


def test_redaction_match_dataclass_is_frozen() -> None:
    """AC-1: RedactionMatch is a frozen dataclass."""
    m = RedactionMatch(
        kind=RedactionKind.JWT, position=(0, 30), redaction="[REDACTED:jwt]"
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        m.kind = RedactionKind.OPENAI_KEY  # type: ignore[misc]
