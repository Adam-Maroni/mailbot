"""Sensitivity pattern loader + override pipeline per Story 3-3 AC-3.

User-configurable forcing rules in `router/sensitivity_patterns.yaml`:

  - `force_confidential`: highest precedence; ALWAYS wins (even over the
    classifier's own "confidential" label — sticky upward).
  - `force_sensitive`:    fires AFTER force_confidential; upgrades "normal"
    to "sensitive" but NEVER downgrades.

Pattern shapes (exactly ONE per entry):
  - `regex` (Python re.search pattern; use (?i) for case-insensitive)
  - `sender_domain` (lowercased domain part of From; exact match)
  - `keyword` (case-insensitive substring against subject + body_preview)

Regex patterns are compiled ONCE at PatternTable construction time via a
model_validator — malformed regex raises Pydantic ValidationError at startup,
not at first-match time.

This module is the SOLE consumer of `yaml.safe_load` for sensitivity patterns
(see `scripts/check_boundaries.py` _YAML_LOAD_ALLOW for the boundary).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

__all__ = [
    "PatternEntry",
    "PatternTable",
    "PatternValidationError",
    "apply_pattern_override",
    "get_patterns",
    "load_patterns",
    "set_patterns_snapshot",
]


# Module-level snapshot, populated at lifespan startup via set_patterns_snapshot.
# Single-reference atomic swap (same pattern as policy.py's set_policy_snapshot).
_PATTERN_SNAPSHOT: PatternTable | None = None


def set_patterns_snapshot(snapshot: PatternTable) -> None:
    """Replace the module-level patterns snapshot atomically.

    Called from `mailbot_api/main.py`'s FastAPI lifespan after `load_patterns`
    succeeds. The single-reference swap guarantees in-flight readers see either
    the previous or new snapshot — never a torn read.
    """
    global _PATTERN_SNAPSHOT  # noqa: PLW0603 — singleton snapshot, same idiom as policy.py
    _PATTERN_SNAPSHOT = snapshot


def get_patterns() -> PatternTable:
    """Return the current patterns snapshot.

    Raises `RuntimeError` if the snapshot has not been initialized yet
    (the caller should always have run through the lifespan first).
    """
    if _PATTERN_SNAPSHOT is None:
        raise RuntimeError(
            "sensitivity patterns snapshot is not initialized; "
            "call set_patterns_snapshot(load_patterns(...)) from lifespan first"
        )
    return _PATTERN_SNAPSHOT


class PatternValidationError(ValueError):
    """Raised when sensitivity_patterns.yaml fails to validate."""


class PatternEntry(BaseModel):
    """A single pattern entry — exactly ONE of regex/sender_domain/keyword is set."""

    regex: str | None = None
    sender_domain: str | None = None
    keyword: str | None = None

    # `compiled_regex` is a runtime-only cached re.Pattern; not a wire field.
    _compiled_regex: re.Pattern[str] | None = PrivateAttr(default=None)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _exactly_one_field(self) -> PatternEntry:
        present = [f for f in ("regex", "sender_domain", "keyword") if getattr(self, f) is not None]
        if len(present) != 1:
            raise ValueError(f"PatternEntry requires exactly one of regex/sender_domain/keyword; got {present}")
        if self.regex is not None:
            try:
                # Cache the compiled pattern for fast per-call matching.
                object.__setattr__(self, "_compiled_regex", re.compile(self.regex))
            except re.error as exc:
                raise ValueError(
                    f"PatternEntry.regex is not a valid regular expression: {self.regex!r} ({exc})"
                ) from exc
        return self

    def matches(self, *, subject: str, from_address: str, body_preview: str) -> bool:
        """Apply this pattern against the three input surfaces.

        - regex: re.search against (subject + "\\n" + body_preview)
        - sender_domain: lowercased domain part of from_address (text after '@')
        - keyword: case-insensitive substring against (subject + "\\n" + body_preview)
        """
        if self._compiled_regex is not None:
            haystack = f"{subject}\n{body_preview}"
            return self._compiled_regex.search(haystack) is not None
        if self.sender_domain is not None:
            if "@" not in from_address:
                return False
            domain = from_address.rsplit("@", 1)[1].lower()
            return domain == self.sender_domain.lower()
        if self.keyword is not None:
            haystack = f"{subject}\n{body_preview}".lower()
            return self.keyword.lower() in haystack
        return False

    def describe(self) -> str:
        """One-line audit description of WHICH rule fired (for the override_reason column)."""
        if self.regex is not None:
            return f"regex {self.regex!r}"
        if self.sender_domain is not None:
            return f"sender_domain {self.sender_domain!r}"
        return f"keyword {self.keyword!r}"


class PatternTable(BaseModel):
    """The full pattern table parsed from `sensitivity_patterns.yaml`."""

    version: str
    force_confidential: list[PatternEntry]
    force_sensitive: list[PatternEntry]

    model_config = ConfigDict(extra="forbid")


def load_patterns(yaml_path: str | Path) -> PatternTable:
    """Parse `sensitivity_patterns.yaml` into a validated PatternTable.

    Raises `PatternValidationError` on any failure — file missing, YAML parse
    error, or Pydantic validation error. Callers catch this and exit cleanly
    rather than starting up with a partial / invalid pattern table.
    """
    path = Path(yaml_path)
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise PatternValidationError(f"sensitivity_patterns.yaml not found at {path}") from exc
    except yaml.YAMLError as exc:
        raise PatternValidationError(f"sensitivity_patterns.yaml YAML parse error: {exc}") from exc

    if not isinstance(raw, dict):
        raise PatternValidationError(f"sensitivity_patterns.yaml top-level must be a mapping; got {type(raw).__name__}")
    try:
        return PatternTable.model_validate(raw)
    except Exception as exc:
        raise PatternValidationError(f"sensitivity_patterns.yaml validation failed: {exc}") from exc


# `final_sensitivity` ranking: "confidential" > "sensitive" > "normal".
_SENSITIVITY_RANK: Final[dict[str, int]] = {"normal": 0, "sensitive": 1, "confidential": 2}


def _rank(label: str) -> int:
    """Return the rank for a sensitivity label, or -1 for unknown labels.

    CR-3-3-6: a bare `_SENSITIVITY_RANK[label]` lookup raises KeyError on any
    label outside the known set. AR-PAT-4 (errors-as-data) requires this
    function never raise. Unknown labels are treated as below-normal so that
    a `force_sensitive` rule still upgrades them — fail-safe direction for a
    privacy invariant.
    """
    return _SENSITIVITY_RANK.get(label, -1)


def apply_pattern_override(
    *,
    classifier_sensitivity: str,
    subject: str,
    from_address: str,
    body_preview: str,
    patterns: PatternTable,
) -> tuple[str, str | None]:
    """Apply the pattern-override pipeline to a classifier result.

    Returns (final_sensitivity, override_reason).
    override_reason is None when no override fired (classifier stands).

    Precedence:
      1. force_confidential rules ALWAYS upgrade (or sustain) "confidential".
      2. force_sensitive rules upgrade "normal" -> "sensitive" but NEVER
         downgrade "confidential" or "sensitive".
      3. No match → classifier label stands, override_reason=None.

    Signature note (CR-3-3-8): the story-spec AC-3 listed
    `(email_id, classifier_result: SensitivityResult, ...)`. The shipped
    signature takes `classifier_sensitivity: str` (the only field consumed)
    and drops `email_id` (caller has it; never used here). The change avoided
    a circular import via `SensitivityResult`. Behaviour is unchanged.
    """
    # Force-confidential pass.
    for entry in patterns.force_confidential:
        if entry.matches(subject=subject, from_address=from_address, body_preview=body_preview):
            reason = f"pattern_override: force_confidential {entry.describe()}"
            return ("confidential", reason)

    # Force-sensitive pass. Only fires if classifier said "normal" — downgrades
    # forbidden per epic spec ("downgrades from `confidential` are never applied").
    # CR-3-3-1: the no-op case (classifier already ≥sensitive) MUST `continue`
    # rather than `return` — otherwise a later force_sensitive rule that DOES
    # match the email is silently skipped on already-sensitive inputs. The
    # upgrade case returns early (no later rule can do anything additional).
    for entry in patterns.force_sensitive:
        if entry.matches(subject=subject, from_address=from_address, body_preview=body_preview):
            if _rank(classifier_sensitivity) < _SENSITIVITY_RANK["sensitive"]:
                reason = f"pattern_override: force_sensitive {entry.describe()}"
                return ("sensitive", reason)
            # Classifier already at "sensitive" or higher — pattern is a no-op.
            # Keep scanning so all force_sensitive rules are evaluated.
            continue

    # No match at all (or only no-op matches above).
    return (classifier_sensitivity, None)
