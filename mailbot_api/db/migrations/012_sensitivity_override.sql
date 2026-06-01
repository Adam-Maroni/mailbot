-- 012_sensitivity_override.sql — Story 3-3 AC-4.
--
-- Adds `emails.sensitivity_override_reason` (TEXT, nullable) populated only
-- when `apply_pattern_override` in `mailbot_api/sensitivity/patterns.py`
-- promotes the classifier's sensitivity label. The column carries the
-- override-trigger reason as a free-text audit string (e.g.,
-- "pattern_override: force_confidential regex 'password reset confirmation'").
--
-- Append-only per AR-D14-1. No data backfill — pre-existing rows have
-- sensitivity_override_reason=NULL, which is semantically correct (the
-- override only fires from Story 3-3 forward).
--
-- Reference: _bmad-output/implementation-artifacts/3-3-...md AC-4.

PRAGMA foreign_keys = ON;

ALTER TABLE emails ADD COLUMN sensitivity_override_reason TEXT;
