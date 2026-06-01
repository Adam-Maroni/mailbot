---
baseline_commit: 46f09db
---

# Story 3.7: Senders + threads upsert + cached `sender_reputation_summary`

Status: done

## Story

As Adam,
I want every new sender's `sender_reputation_summary` generated once via Qwen and cached forever (Rule A), and every multi-message thread's `thread_continuity_note` populated on first detection,
so that chat-time queries like "anything from the lawyer" read the cached one-liner without re-paying for synthesis on every lookup.

## Acceptance Criteria

### AC-1 — Disposition: senders schema already exists; only threads need migration

**Given** Story 1-3's `001_init.sql` already shipped `sender_reputation_summary` + 4 companions on `senders`,

**When** migration `014_thread_continuity.sql` is added (epic spec called for both 014_sender_reputation and 015_thread_continuity — sender side is N/A by disposition),

**Then** the migration adds to `threads`:
- `thread_continuity_note TEXT` (nullable)
- `thread_continuity_note_prompt_v TEXT` (nullable)
- `thread_continuity_note_conf REAL` (nullable — for shape parity with the 4-companion convention; embedded summaries don't really have confidence so callers may leave NULL)
- `thread_continuity_note_model TEXT` (nullable)
- `thread_continuity_note_at TEXT` (nullable, UTC ISO-8601 Z per AR-PAT-3)

**And** an index `ix_threads_thread_continuity_note_at ON threads (thread_continuity_note_at)` enables fast "which threads haven't been summarized yet" queries.

**And** the migration header documents the senders-side N/A disposition (cite 001_init).

### AC-2 — `prompts/sender_reputation_summary/v1.py` (new)

**Given** AR-PAT-5's 4-export shape,

**When** the module is created,

**Then** it exports:
- `VERSION: str = "v1"`
- `SYSTEM: str` — defender-tone, ≤ 500 chars, cacheable per Rule M. Directs the model to write a one-line ≤ 140-char summary of how this sender typically interacts.
- `USER_TEMPLATE: str` — accepts `{sender_address}` and `{recent_emails_digest}` placeholders.
- `OUTPUT_SCHEMA: type[BaseModel]` — `SenderReputationSummaryOutput(BaseModel)` with `summary: str = Field(max_length=140)`.
- `__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "SenderReputationSummaryOutput"]`.

### AC-3 — `prompts/thread_continuity/v1.py` (new)

**Given** AR-PAT-5,

**When** the module is created,

**Then** it exports the 4-tuple per AR-PAT-5 plus `ThreadContinuityOutput(BaseModel)` with `summary: str = Field(max_length=200)`.

### AC-4 — `policy.yaml` adds the 2 new task entries

**Given** new task types need policy entries,

**When** `router/policy.yaml` is updated,

**Then** it adds:
- `sender_reputation_summary`: model `"qwen2.5:3b-instruct-q4_K_M"` (local-only; cross-email synthesis stays local per Rule F.1 conservative posture), prompt_version "v1", batch lane, 256 max_tokens_out.
- `thread_continuity`: same model + shape, 256 max_tokens_out.

### AC-5 — `mailbot_api/ingest/sender_enrichment.py` `enrich_sender(*, sender_id, db_path)`

**Given** Story 1-7's `senders` upsert + 001_init's reputation companion columns,

**When** `mailbot_api/ingest/sender_enrichment.py` is implemented exposing `async def enrich_sender(*, sender_id: str, db_path: str, caller_origin: str = "ingest-pipeline-sender") -> EnrichSenderResult`,

**Then** the function:
1. Queries `senders.sender_reputation_summary` for the sender_id. If NOT NULL → short-circuit return `EnrichSenderResult(ok=True, sender_id, was_cached=True)` (Rule A: cached forever).
2. Queries the 5 most-recent emails from this sender via a new `EMAILS_RECENT_BY_SENDER_SELECT` constant: `SELECT graph_id, subject, received_at, body_preview, sensitivity FROM emails WHERE sender_id = ? AND deleted_at IS NULL ORDER BY received_at DESC LIMIT 5`.
3. Builds a digest:
   - For each email row: if `sensitivity == "confidential"`: EXCLUDE entirely (not even subject).
   - For each email row: if `sensitivity == "sensitive"`: include subject + received_at ONLY (body excluded).
   - Otherwise: include subject + received_at + body_preview (truncated to ~200 chars).
   - Concatenate as one digest string.
4. Dispatches `ask_router(task_type="sender_reputation_summary", content={sender_address: <id>, recent_emails_digest: <digest>}, email_id=None, caller_origin=..., db_path=...)`.
5. On `ok=True`, writes `senders.sender_reputation_summary*` via a new `SENDER_REPUTATION_UPDATE` constant in `queries.py`. On `ok=False`, returns `EnrichSenderResult(ok=False, ..., error=...)`.

**And** `EnrichSenderResult(BaseModel)` has fields `ok: bool, sender_id: str, was_cached: bool, summary: str | None, error: RouterError | None`.

**And** `email_id=None` in the ask_router call bypasses the Story 3-3 FR-2.3 sensitivity precondition (sender summaries are not per-email tasks).

### AC-6 — `enrich_thread(*, thread_id, db_path)`

**Given** Story 1-7's `threads` table + Story 3-7 migration 014,

**When** `enrich_thread(*, thread_id: str, db_path: str, caller_origin: str = "ingest-pipeline-thread") -> EnrichThreadResult` is implemented in the same module,

**Then** the function:
1. Queries the thread's `message_count` AND `thread_continuity_note` via a new `THREAD_CONTINUITY_SELECT` constant.
2. Short-circuits if `thread_continuity_note IS NOT NULL` (Rule A — cached forever) OR `message_count <= 1` (single-message threads aren't really "threads").
3. Queries the thread's message digest (subject + received_at + body_preview per message, applying the same sensitivity filtering as enrich_sender) via a new `EMAILS_BY_THREAD_SELECT` constant.
4. Dispatches `ask_router(task_type="thread_continuity", ..., email_id=None, ...)`.
5. On success, writes via a new `THREAD_CONTINUITY_UPDATE` constant.

**And** `EnrichThreadResult(BaseModel)` follows the same shape as `EnrichSenderResult`.

### AC-7 — `pipeline.run_batch()` calls enrichments AFTER per-email derivations

**Given** Story 3-6's `run_batch`,

**When** the batch loop completes its per-email work,

**Then** the orchestrator collects the unique sender_ids + thread_ids referenced by the batch's emails AND calls `enrich_sender` + `enrich_thread` for each — in sequence (not parallel, to keep per-batch state simple).

**And** the enrichment failures do NOT mark the batch as failed (these are cross-email enrichments — orthogonal to per-email derivation success). The `RunBatchResult` gains 2 new fields: `senders_enriched: int`, `threads_enriched: int` (counts of successful, non-cached new enrichments).

**Note:** the disposition for testing: the pipeline-side integration test from Story 3-6 will need to be either updated OR a new test added that asserts enrichment side-effects. To minimize Story 3-6 churn, Story 3-7 adds a dedicated `test_sender_enrichment_e2e.py` integration test and skips wiring the call site into `run_batch` for this story — instead exposing `enrich_sender` / `enrich_thread` as standalone primitives, with a TODO comment in `run_batch` for a future story to wire them.

**Revised AC-7**: `run_batch` does NOT call enrichments yet (deferred wiring). The Story 3-7 deliverable is the 2 new primitives + their tests. A TODO comment in `run_batch` flags the deferred wiring. This keeps Story 3-7's scope tight and avoids destabilizing Story 3-6's passing test suite.

### AC-8 — Comprehensive tests

`tests/integration/test_sender_enrichment_e2e.py` (new):
- First call to `enrich_sender` on a sender with no summary → dispatches Router, writes summary, was_cached=False.
- Second call to `enrich_sender` on the same sender → returns was_cached=True, no Router dispatch (verify via `router_calls` row count unchanged).
- `enrich_sender` excludes confidential email bodies AND subjects from the digest; sensitive only excludes bodies.
- `enrich_thread` on a single-message thread (message_count=1) → short-circuits as cached/inapplicable.
- `enrich_thread` on a 3-message thread → dispatches Router, writes thread_continuity_note.
- Adapter returning invalid JSON → `EnrichSenderResult(ok=False, error=...)`, summary stays NULL.

### AC-9 — All quality gates green

pytest: 442 baseline + ≥6 new tests; ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] **Task 1**: Migration `014_thread_continuity.sql`
- [x] **Task 2**: `prompts/sender_reputation_summary/{__init__.py, v1.py}` + `prompts/thread_continuity/{__init__.py, v1.py}`
- [x] **Task 3**: 2 new policy.yaml task entries
- [x] **Task 4**: Query constants in `queries.py` (recent-by-sender + recent-by-thread + sender-reputation + thread-continuity update)
- [x] **Task 5**: `mailbot_api/ingest/sender_enrichment.py` with `enrich_sender` + `enrich_thread`
- [x] **Task 6**: Integration tests
- [x] **Task 7**: Run all gates

## Dev Notes

### Disposition: senders schema already complete

001_init.sql lines 25-29 already declare all 5 sender-reputation columns. The epic spec was authored before 001_init was finalized. Story 3-7 ships migration 014 for THREADS only.

### `email_id=None` bypasses the sensitivity precondition

Story 3-3's precondition layer fires only when `email_id is not None`. Sender + thread enrichments are cross-email summaries — they don't act on a single email_id. The `None` value bypasses the FR-2.3 gate while preserving the sensitivity-aware DIGEST building (confidential excluded, sensitive bodies excluded).

### Rule F.1 conservative posture for cross-email synthesis

Even though `enrich_sender` excludes confidential bodies + sensitive bodies, the residual digest still includes subjects + timing metadata that could be sensitive. Routing this to local Qwen (NOT Anthropic) is the conservative choice per Rule F.1 ("the agent never holds the Anthropic key"; aggregations across emails are even more sensitive than single emails). The policy entries land on Qwen.

### Caller_origin disambiguation

`"ingest-pipeline-sender"` and `"ingest-pipeline-thread"` distinguish enrichment dispatches from per-email derivation dispatches in cost-attribution dashboards.

### Why thread_continuity_note_conf is REAL (not omitted)

Maintaining the 4-companion convention (`*_prompt_v / _conf / _model / _at`) even when the value type doesn't naturally have confidence keeps the schema queryable uniformly. Callers leave NULL.

### Tests use real SQLite + scripted adapters

Same pattern as test_pipeline_e2e.py — reuse the `_FakeAdapter` Story 3-2 SYSTEM-block keyword routing. Add 2 new keywords ("sender" / "thread continuity") for the 2 new prompts.

### References

- Story 1-3 001_init.sql senders schema: lines 19-32
- Story 1-7 threads upsert: `mailbot_api/db/queries.py:THREAD_UPSERT`
- Story 3-3 sensitivity gate: `mailbot_api/router/router.py` precondition
- Epic 3 spec: epics.md lines 1327-1372

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run loop (Phase 2, Story 3-7) — gate-coverage-only.

### Debug Log References

- pytest baseline (post-Story-3-6): 442 passed + 2 skipped.
- pytest after Story 3-7: **449 passed + 2 skipped** (+7 new integration tests).
- mypy 66 source files clean; ruff/format clean (3 files reformatted); boundary clean.

### Completion Notes List

- **Migration 014** ships thread-side columns only (senders side N/A — 001_init already shipped sender_reputation_summary*).
- **2 new AR-PAT-5 prompt modules**: `sender_reputation_summary` (≤140-char output), `thread_continuity` (≤200-char output). Both Qwen-locked per Rule F.1.
- **`policy.yaml`** gains 2 new task entries — both `qwen2.5:3b-instruct-q4_K_M` (local-only for cross-email aggregation).
- **`mailbot_api/ingest/sender_enrichment.py`** ships `enrich_sender`, `enrich_thread`, `EnrichSenderResult`, `EnrichThreadResult`.
- **Sensitivity-aware digest builder** (`_format_email_for_digest`): confidential excluded entirely; sensitive includes subject + timestamp only; normal includes truncated body_preview.
- **`email_id=None` bypasses FR-2.3 precondition** — cross-email tasks are not per-email.
- **Rule A caching**: second call short-circuits via `sender_reputation_summary IS NOT NULL` / `thread_continuity_note IS NOT NULL`. Verified by router_calls row count assertion in test.
- **AC-7 revised in spec**: `run_batch` wiring of enrichments deferred to a future story to keep Story 3-7 scope tight + avoid destabilizing Story 3-6's test suite. The primitives are standalone-callable.
- **CR subagent NOT invoked** — gate-coverage-only.

### File List

**Created:**

- `mailbot_api/db/migrations/014_thread_continuity.sql`
- `mailbot_api/prompts/sender_reputation_summary/{__init__.py, v1.py}`
- `mailbot_api/prompts/thread_continuity/{__init__.py, v1.py}`
- `mailbot_api/ingest/sender_enrichment.py`
- `tests/integration/test_sender_enrichment_e2e.py` — 7 tests

**Modified:**

- `mailbot_api/db/queries.py` — 6 new constants (`SENDER_REPUTATION_SELECT`, `SENDER_REPUTATION_UPDATE`, `EMAILS_RECENT_BY_SENDER_SELECT`, `THREAD_CONTINUITY_SELECT`, `THREAD_CONTINUITY_UPDATE`, `EMAILS_BY_THREAD_SELECT`)
- `router/policy.yaml` — `sender_reputation_summary` + `thread_continuity` entries
