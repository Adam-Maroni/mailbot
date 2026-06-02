"""Story 4-1 AC-7 — boundary-violation tests for bare action-type literals.

This file exists to satisfy AC-7's explicit file convention. The actual test
implementations live in `tests/unit/test_lint_boundaries.py` (project-wide
convention for `scripts/check_boundaries.py` meta-tests, established by
Stories 1-4, 2-1, 3-1, 3-4). Centralizing all boundary-checker meta-tests in
one module avoids the maintenance burden of three separate subprocess-driving
test files.

CR-6 resolution: code-review surfaced the spec/convention divergence. This
re-import file makes the tests discoverable from the spec'd location without
duplicating the test bodies. If pytest collects this file before the canonical
location it sees no test functions (only the re-imports below) — pytest still
runs the canonical tests from their original file.

Tests covered (canonical location: `tests/unit/test_lint_boundaries.py`):
  - `test_boundary_violations_caught_by_check_boundaries` (parametrized; the
    "violates_bare_action_string_outside_types" entry is the AC-5/AC-7 case)
  - `test_bare_action_string_in_allowlisted_types_path_passes`
  - `test_correct_action_enum_use_does_not_trigger_action_boundary`
  - `test_action_type_docstring_does_not_trigger_action_boundary`
"""

from __future__ import annotations

# Re-import the canonical test functions so they're discoverable from this
# spec'd file path. pytest treats imported test functions as duplicates of
# the originals and does NOT re-run them — this is a discoverability anchor,
# not a parallel execution surface.
from tests.unit.test_lint_boundaries import (  # noqa: F401
    test_action_type_docstring_does_not_trigger_action_boundary,
    test_bare_action_string_in_allowlisted_types_path_passes,
    test_correct_action_enum_use_does_not_trigger_action_boundary,
)
