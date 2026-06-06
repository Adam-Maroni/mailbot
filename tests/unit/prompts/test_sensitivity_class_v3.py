"""Story 6-21 — F27 closure: sensitivity_class v3 prompt-module structural tests.

6 unit tests covering AC-4 tests 1-6: lock the v3 module's STRUCTURAL
invariants (schema re-export, version constant, USER_TEMPLATE byte-stability
vs v2, borderline-cases anti-anchoring content markers, confidence-range
markers, ordering invariant). These do NOT prove qwen2.5:3b will USE the
anti-anchor — that's a model-behavior question only the live walk can
answer (deferred to Story 6-6.5 re-walk per AC-6).
"""

from __future__ import annotations

from mailbot_api.prompts.sensitivity_class import v1, v2, v3


def test_v3_re_exports_v1_sensitivity_class_output_schema() -> None:
    """AC-4.1 — v3.OUTPUT_SCHEMA is THE same v1.SensitivityClassOutput class
    so isinstance() checks across the codebase remain version-agnostic.
    Mirrors v2's re-export pattern (v2.py:38)."""
    assert v3.OUTPUT_SCHEMA is v1.SensitivityClassOutput
    assert v3.SensitivityClassOutput is v1.SensitivityClassOutput


def test_v3_version_constant_is_v3() -> None:
    """AC-4.2 — resolve_prompt's VERSION-equality validator requires
    v3.VERSION == 'v3' to load via mailbot_api.prompts.sensitivity_class.v3.
    """
    assert v3.VERSION == "v3"


def test_v3_user_template_byte_stable_vs_v2() -> None:
    """AC-4.3 — the v2 -> v3 bump is SYSTEM-only. USER_TEMPLATE stays
    byte-identical so callers' templating contracts continue working
    without per-version dispatch."""
    assert v3.USER_TEMPLATE == v2.USER_TEMPLATE


def test_v3_system_includes_borderline_cases_marker() -> None:
    """AC-4.4 — v3.SYSTEM extends v2's body with borderline-case discipline.
    Lightweight content correctness: the borderline marker is present AND
    the v2-required schema enumeration AND cautious-bias paragraph all
    survive the bump."""
    s = v3.SYSTEM
    # New v3 content marker.
    assert "Borderline cases" in s
    # v2 schema enumeration markers (must still be present in v3).
    assert '"sensitivity"' in s
    assert '"confidence"' in s
    assert '"reason"' in s
    # v2 cautious-bias paragraph (must still be present in v3 — NFR-PRIV-1
    # backstop preserved verbatim).
    assert "Cautious bias" in s


def test_v3_system_includes_both_borderline_example_confidences_in_anti_anchor_range() -> None:
    """AC-4.5 — anti-anchoring requires BOTH borderline examples to carry
    confidence in the 0.65-0.75 range. Locks against future refactors that
    might drop one of the examples or shift the confidence values out of
    the anti-anchor range."""
    s = v3.SYSTEM
    # Both confidence values from the spec illustrative examples.
    assert "0.70" in s, "v3 must carry the 0.70 borderline-case example"
    assert "0.65" in s, "v3 must carry the 0.65 borderline-case example"


def test_v3_system_borderline_cases_appear_before_cautious_bias() -> None:
    """AC-4.6 — anti-anchoring discipline requires borderline examples to
    appear BEFORE the cautious-bias paragraph (so qwen reads them while
    constructing its confidence distribution, not after the bias rule has
    set its prior). Locks the ordering invariant."""
    s = v3.SYSTEM
    borderline_idx = s.index("Borderline cases")
    cautious_idx = s.index("Cautious bias")
    assert borderline_idx < cautious_idx, (
        f"borderline cases (idx {borderline_idx}) must precede cautious bias "
        f"paragraph (idx {cautious_idx})"
    )
