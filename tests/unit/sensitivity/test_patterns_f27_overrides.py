"""Story 6-21 — F27 closure: sensitivity_patterns.yaml override tests for
the two new force_sensitive regexes shipped with prompt v3.

3 unit tests covering AC-4 tests 7-9: validates the two new patterns match
the multi-signal triggers F27 surfaced (family-medical + interpersonal-debt)
AND that they don't over-match unrelated text. Loads the production
`router/sensitivity_patterns.yaml` for the test (not an inline fixture)
so any future edits to the file are caught by these tests.
"""

from __future__ import annotations

from pathlib import Path

from mailbot_api.sensitivity.patterns import (
    apply_pattern_override,
    load_patterns,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PATTERNS_YAML = _REPO_ROOT / "router" / "sensitivity_patterns.yaml"


def test_force_sensitive_treatment_clinic_pattern_matches() -> None:
    """AC-4.7 — family-medical signal "treatment clinic" upgrades a
    normal-classifier verdict to sensitive. F27 fixture case."""
    patterns = load_patterns(_PATTERNS_YAML)
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="Following up on yesterday",
        from_address="friend@example.com",
        body_preview=(
            "My mom's treatment clinic recommended switching specialists; "
            "I'm still figuring out the next step."
        ),
        patterns=patterns,
    )
    assert final == "sensitive"
    assert reason is not None
    assert "force_sensitive" in reason


def test_force_sensitive_owe_money_pattern_matches() -> None:
    """AC-4.8 — interpersonal-debt signal "owe you money" upgrades a
    normal-classifier verdict to sensitive. F27 fixture case."""
    patterns = load_patterns(_PATTERNS_YAML)
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="re: last weekend",
        from_address="friend@example.com",
        body_preview=(
            "By the way, you owe him money still from the rental — "
            "let me know when you can settle it."
        ),
        patterns=patterns,
    )
    assert final == "sensitive"
    assert reason is not None
    assert "force_sensitive" in reason


def test_force_sensitive_owes_conjugated_form_matches() -> None:
    """AC-4.8 (CR-3 extension): the actual CP-B fixture language used the
    conjugated `owes` form, not the bare `owe`. The pattern MUST match
    both. Regression coverage for the F27 root-cause language."""
    patterns = load_patterns(_PATTERNS_YAML)
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="re: last weekend",
        from_address="friend@example.com",
        body_preview=(
            "He owes you money still — wanted to give you a heads up "
            "before you next see him."
        ),
        patterns=patterns,
    )
    assert final == "sensitive"
    assert reason is not None
    assert "force_sensitive" in reason


def test_force_sensitive_outstanding_debt_keyword_matches() -> None:
    """AC-4.8 (CR-3 extension): the CP-B fixture body included the
    `outstanding debt between friends` formulation. The keyword pattern
    MUST cover this case — CR-2 added `outstanding debt` keyword to
    sensitivity_patterns.yaml."""
    patterns = load_patterns(_PATTERNS_YAML)
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="Following up on yesterday",
        from_address="friend@example.com",
        body_preview=(
            "Just want to circle back on the outstanding debt between us "
            "from last quarter — happy to talk through it whenever."
        ),
        patterns=patterns,
    )
    assert final == "sensitive"
    assert reason is not None
    assert "force_sensitive" in reason


def test_force_sensitive_does_not_match_unrelated_text() -> None:
    """AC-4.9 — counter-test: benign text MUST NOT trigger the new patterns.
    Locks against accidental over-matching that would cascade into
    spurious sensitive-classification noise."""
    patterns = load_patterns(_PATTERNS_YAML)
    final, reason = apply_pattern_override(
        classifier_sensitivity="normal",
        subject="Lunch meeting at noon",
        from_address="colleague@example.com",
        body_preview=(
            "Quick reminder we're meeting at noon tomorrow at the cafe "
            "by the office — see you then."
        ),
        patterns=patterns,
    )
    # Classifier label stands; no override fires.
    assert final == "normal"
    assert reason is None
