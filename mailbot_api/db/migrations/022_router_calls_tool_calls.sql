-- 022_router_calls_tool_calls.sql — Story 6-9 (F11 closure)
--
-- Adds two NULL-able columns to router_calls so dispatch_tool_call's audit
-- row can record per-call tool-use metadata for forensic + cost-attribution
-- queries:
--
--   * tool_calls_count    — INTEGER NULL. Count of tool_use blocks in the
--                           response. 0 = tools were offered but model chose
--                           not to call any; NULL = call wasn't tools-bearing.
--   * tool_calls_summary  — TEXT NULL. Compact JSON of per-tool-call
--                           metadata: [{"name","input_redacted"}, ...].
--                           Story 5-7's redactor pipeline is applied before
--                           write. NULL on non-tools calls.
--
-- Existing rows backfill to NULL (NULL-able + no default => column is added
-- with NULL for all pre-existing rows).
--
-- Column-order contract still load-bearing: queries.ROUTER_CALLS_INSERT,
-- observability/audit._param_tuple, and RouterCallRow field-order MUST be
-- updated in the same commit. The boundary checker still gates direct
-- INSERT INTO router_calls.

PRAGMA foreign_keys = ON;

ALTER TABLE router_calls
    ADD COLUMN tool_calls_count INTEGER NULL;

ALTER TABLE router_calls
    ADD COLUMN tool_calls_summary TEXT NULL;
