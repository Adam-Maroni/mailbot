-- 023_oauth_state_consecutive_failures.sql — Story 6-15 AC-3 source-of-truth.
-- Adds a tally of consecutive refresh failures since the last success so the
-- `mailbot status` `oauth_refresh_failing` alarm can be computed from a single
-- SELECT. The worker_health single-row-per-component shape can't carry the
-- count itself.

ALTER TABLE oauth_state
    ADD COLUMN consecutive_refresh_failures INTEGER NOT NULL DEFAULT 0;
