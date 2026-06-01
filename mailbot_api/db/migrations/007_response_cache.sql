-- 007_response_cache.sql — SQL-backed response cache per Story 2-7.
--
-- Keyed on sha256(model|temperature|system|user). Per-task TTL is stored on
-- the row so a policy.yaml edit can change TTL without re-priming the cache.
--
-- Numbering: epic spec said 006; Story 2-1 took 006_router_calls.sql.
--
-- Single writer/reader: mailbot_api/router/response_cache.py (Rule C).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS response_cache (
    cache_key TEXT PRIMARY KEY,         -- sha256 hex of model|temperature|system|user
    task_type TEXT NOT NULL,
    model TEXT NOT NULL,
    result_json TEXT NOT NULL,          -- serialized RouterResult.output (Pydantic .model_dump_json())
    cost_usd REAL NOT NULL DEFAULT 0,   -- original dispatch cost (for accounting if reissued)
    cached_at TEXT NOT NULL,            -- UTC ISO-8601 with Z
    ttl_seconds INTEGER NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_response_cache_task_type_cached_at
    ON response_cache (task_type, cached_at);
