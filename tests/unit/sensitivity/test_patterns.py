"""Story 3-3 AC-3 + AC-6: sensitivity pattern loader + override pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mailbot_api.sensitivity.patterns import (
    PatternEntry,
    PatternTable,
    PatternValidationError,
    apply_pattern_override,
    load_patterns,
)


def test_pattern_entry_requires_exactly_one_field() -> None:
    """AC-3: exactly one of regex/sender_domain/keyword must be set."""
    # Zero fields set → ValidationError.
    with pytest.raises(ValidationError):
        PatternEntry()
    # Two fields set → ValidationError.
    with pytest.raises(ValidationError):
        PatternEntry(regex="foo", keyword="bar")
    # All three set → ValidationError.
    with pytest.raises(ValidationError):
        PatternEntry(regex="foo", sender_domain="bar.com", keyword="baz")
    # Exactly one set → OK.
    assert PatternEntry(regex="foo")
    assert PatternEntry(sender_domain="bar.com")
    assert PatternEntry(keyword="baz")


def test_pattern_entry_invalid_regex_fails_at_construction() -> None:
    """AC-3: malformed regex raises at PatternEntry construction time."""
    with pytest.raises(ValidationError):
        PatternEntry(regex="(unclosed")


def test_regex_pattern_matches_against_subject_and_body() -> None:
    """AC-6: regex matches the joined subject+body_preview surface."""
    entry = PatternEntry(regex="(?i)NDA|non-disclosure")
    assert entry.matches(subject="Please sign the NDA", from_address="x@y.com", body_preview="")
    assert entry.matches(
        subject="Hi", from_address="x@y.com", body_preview="please review the non-disclosure agreement"
    )
    assert not entry.matches(subject="Hi", from_address="x@y.com", body_preview="ordinary message")


def test_sender_domain_pattern_matches_case_insensitive() -> None:
    """AC-6: sender_domain matches the lowercased domain part of from_address."""
    entry = PatternEntry(sender_domain="bank.example.com")
    assert entry.matches(subject="", from_address="loan@bank.example.com", body_preview="")
    # Case-insensitive.
    assert entry.matches(subject="", from_address="LOAN@Bank.Example.COM", body_preview="")
    # Mismatch.
    assert not entry.matches(subject="", from_address="x@other.com", body_preview="")
    # Malformed address (no @) → no match.
    assert not entry.matches(subject="", from_address="not-an-email", body_preview="")


def test_keyword_pattern_matches_case_insensitive_substring() -> None:
    """AC-6: keyword does case-insensitive substring match against subject+body_preview."""
    entry = PatternEntry(keyword="Confidential")
    assert entry.matches(subject="STRICTLY CONFIDENTIAL", from_address="x@y.com", body_preview="")
    assert entry.matches(subject="", from_address="x@y.com", body_preview="this message is confidential")
    assert not entry.matches(subject="ordinary", from_address="x@y.com", body_preview="nothing to see")


def test_load_patterns_real_yaml(tmp_path: Path) -> None:
    """AC-3: load_patterns reads a YAML file and returns a validated PatternTable."""
    yaml_path = tmp_path / "patterns.yaml"
    yaml_path.write_text(
        """
version: "test-v0"
force_confidential:
  - {regex: "(?i)password reset"}
  - {sender_domain: "bank.com"}
force_sensitive:
  - {keyword: "confidential"}
""".strip(),
        encoding="utf-8",
    )
    table = load_patterns(yaml_path)
    assert table.version == "test-v0"
    assert len(table.force_confidential) == 2
    assert len(table.force_sensitive) == 1


def test_load_patterns_missing_file_raises() -> None:
    """AC-3: missing file raises PatternValidationError."""
    with pytest.raises(PatternValidationError):
        load_patterns("/nonexistent/path/patterns.yaml")


def test_load_patterns_invalid_yaml_raises(tmp_path: Path) -> None:
    """AC-3: invalid YAML raises PatternValidationError."""
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("not: valid: yaml: at all: [", encoding="utf-8")
    with pytest.raises(PatternValidationError):
        load_patterns(yaml_path)


def _make_table() -> PatternTable:
    return PatternTable(
        version="t",
        force_confidential=[
            PatternEntry(regex="(?i)password reset"),
            PatternEntry(sender_domain="bank.example.com"),
        ],
        force_sensitive=[
            PatternEntry(keyword="confidential"),
            PatternEntry(regex="(?i)NDA"),
        ],
    )


def test_apply_pattern_override_force_confidential_wins() -> None:
    """AC-3: force_confidential always wins, even over classifier='normal'."""
    table = _make_table()
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="Your password reset code",
        from_address="x@y.com",
        body_preview="",
        patterns=table,
    )
    assert final == "confidential"
    assert reason is not None
    assert "force_confidential" in reason
    assert "password reset" in reason


def test_apply_pattern_override_force_sensitive_upgrades_normal() -> None:
    """AC-3: force_sensitive upgrades 'normal' to 'sensitive'."""
    table = _make_table()
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="Please sign the NDA",
        from_address="x@y.com",
        body_preview="",
        patterns=table,
    )
    assert final == "sensitive"
    assert reason is not None
    assert "force_sensitive" in reason


def test_apply_pattern_override_force_sensitive_does_not_downgrade_confidential() -> None:
    """AC-6: force_sensitive NEVER downgrades 'confidential'."""
    table = _make_table()
    final, reason = apply_pattern_override(
        classifier_sensitivity="confidential",
        subject="this is confidential",
        from_address="x@y.com",
        body_preview="",
        patterns=table,
    )
    # Classifier already at confidential; force_sensitive matched but is a no-op.
    assert final == "confidential"
    assert reason is None


def test_apply_pattern_override_no_match_returns_classifier_label() -> None:
    """AC-3: no pattern matches → classifier label stands, reason=None."""
    table = _make_table()
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="Lunch tomorrow?",
        from_address="friend@personal.com",
        body_preview="just checking in",
        patterns=table,
    )
    assert final == "normal"
    assert reason is None


def test_apply_pattern_override_force_confidential_precedence_over_force_sensitive() -> None:
    """AC-3: force_confidential matches first; force_sensitive doesn't get a chance."""
    table = _make_table()
    # Both patterns would match this email; force_confidential's bank.example.com
    # sender_domain wins before force_sensitive's "confidential" keyword runs.
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="confidential review",
        from_address="x@bank.example.com",
        body_preview="",
        patterns=table,
    )
    assert final == "confidential"
    assert reason is not None
    assert "force_confidential" in reason
    assert "bank.example.com" in reason
