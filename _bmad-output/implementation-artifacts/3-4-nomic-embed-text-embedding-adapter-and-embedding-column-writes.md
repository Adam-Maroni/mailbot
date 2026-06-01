---
baseline_commit: 46f09db
---

# Story 3.4: `nomic-embed-text` embedding adapter + embedding column writes

Status: done

## Story

As Adam,
I want the Ollama adapter extended to call `nomic-embed-text` for embedding generation, and `mailbot_api/ingest/embedding.py` to serialize the embedding vector as little-endian `float32` bytes into `emails.embedding` (BLOB) with the W-5 self-documenting companion columns (`embedding_dtype="<f4"`, `embedding_shape="[768]"`),
so that semantic search and similarity analysis over the mailbox become a primitive other stories can rely on.

## Acceptance Criteria

### AC-1 — `OllamaAdapter.embed(text)` extension

**Given** `mailbot_api/router/models.py` ships `OllamaAdapter` (Story 2-3) with `call(...)` for chat completions,

**When** the adapter is extended with `async def embed(text: str) -> EmbeddingResponse`,

**Then** the new `EmbeddingResponse` Pydantic model in `mailbot_api/router/models.py` carries fields `vector: list[float]`, `dim: int`, `tokens_in: int`, `latency_ms: int`, `raw: dict[str, Any]` (parallel shape to `AdapterResponse` but tailored to embeddings — no `text`/`tokens_out` since embedding output is a vector not a string; no `cached_tokens_in` since Ollama embedding API doesn't return cache stats).

**And** `embed(...)` dispatches via the existing `self._client.embeddings(model=self.model_id, prompt=text)` API.

**And** the adapter uses a separate timeout `_EMBEDDING_TIMEOUT_SECONDS = 15.0` (embeddings are faster than chat; the spec mandates 15s). The chat-side `timeout_seconds` field is unchanged.

**And** on `asyncio.TimeoutError` the method raises `AdapterTimeout(model_id=self.model_id, timeout_seconds=_EMBEDDING_TIMEOUT_SECONDS)`; on any other exception it raises `AdapterProviderError(model_id=self.model_id, sanitized_message=sanitize_error(exc))` — mirror the existing `call(...)` exception-translation pattern.

**And** the returned `vector` length equals `dim` (768 for `nomic-embed-text`); `len(vector) == dim` is asserted defensively at the adapter boundary so a misbehaving Ollama can't corrupt downstream consumers.

**And** `EmbeddingResponse` joins the module's `__all__` export list.

**Note**: The `AnthropicAdapter` does NOT gain an `embed(...)` method. Embeddings are local-only per FR-2.5 (no architectural reason to ever embed via Anthropic).

### AC-2 — `mailbot_api/ingest/embedding.py` `write_embedding` writer-monopoly

**Given** Story 3-1's `emails.embedding` (BLOB), `emails.embedding_dtype` (TEXT), `emails.embedding_shape` (TEXT), `emails.embedding_prompt_v / _conf / _model / _at` columns exist,

**When** `mailbot_api/ingest/embedding.py` is created with `write_embedding(*, db_path: str, email_id: str, vector: numpy.ndarray, model_id: str) -> None`,

**Then** the function is the SOLE writer of `emails.embedding` + `embedding_dtype` + `embedding_shape` (mirroring Story 2-1's `record_router_call` writer-monopoly pattern).

**And** the vector is serialized via `vector.astype('<f4').tobytes()` (explicit little-endian float32 — W-5 resolution; guarantees cross-architecture portability).

**And** the row is written atomically: a single `execute_write` of `EMAIL_EMBEDDING_UPDATE` (new constant in `queries.py`) populates `embedding` (BLOB), `embedding_dtype="<f4"`, `embedding_shape=json.dumps(list(vector.shape))` (e.g., `"[768]"` for a 1-D 768-vector), `embedding_prompt_v="v1"` (sentinel — embeddings have no real prompt versions), `embedding_model=model_id`, `embedding_at=<now UTC>`, and `embedding_conf=NULL` (no confidence concept for embeddings).

**And** partial writes are impossible: a single UPDATE statement either lands all 6 columns or none.

**And** the function validates `vector.ndim == 1` and `len(vector) > 0` before serializing; mismatches raise `ValueError` (caller bug).

### AC-3 — `read_embedding(*, db_path, email_id) -> numpy.ndarray | None` helper

**Given** the writer-monopoly contract,

**When** `mailbot_api/ingest/embedding.py` exposes `async def read_embedding(*, db_path: str, email_id: str) -> numpy.ndarray | None`,

**Then** the function reads `emails.embedding` + `embedding_dtype` + `embedding_shape` via a new `EMAIL_EMBEDDING_SELECT` constant in `queries.py`.

**And** if the blob is `None` (not yet embedded), the function returns `None`.

**And** if the blob is populated, the function returns `numpy.frombuffer(blob, dtype=row.embedding_dtype).reshape(json.loads(row.embedding_shape))` — using the companion columns; NEVER assuming a hard-coded dtype or shape.

**And** the returned array's shape is `(dim,)` for the canonical 1-D embedding case.

### AC-4 — `embed_email(*, db_path, email_id, caller_origin) -> EmbedEmailResult` orchestrator

**Given** the adapter + writer + reader are in place,

**When** `async def embed_email(*, db_path: str, email_id: str, caller_origin: str = "ingest-pipeline-embedding") -> EmbedEmailResult` is implemented in `mailbot_api/ingest/embedding.py`,

**Then** the function:
1. Calls `dispatch_embedding(...)` (the new low-level Router-side helper from AC-5) which resolves `policy.tasks["embedding"].model`, validates the FR-2.3 sensitivity precondition (sensitivity_at IS NOT NULL), reads the email body, dispatches via the resolved Ollama adapter's `embed(text)`, and writes the `router_calls` audit row.
2. On `ok=False`, propagates the error as `EmbedEmailResult(ok=False, error=<RouterError>)`.
3. On `ok=True`, converts the returned `EmbeddingResponse.vector` to a numpy array via `numpy.asarray(response.vector, dtype="<f4")` and calls `write_embedding(...)`.
4. Returns `EmbedEmailResult(ok=True, email_id, model, dim, latency_ms)`.

**And** the `EmbedEmailResult` Pydantic model is exported alongside `write_embedding`, `read_embedding`, `embed_email` from `mailbot_api/ingest/embedding.py`'s `__all__`.

### AC-5 — Router `dispatch_embedding` sibling function

**Given** Story 2-4's `ask_router` is built around chat-completion shapes (system/user/max_tokens_out) and the failure chain (schema-validation retry, escalation) doesn't apply to embeddings,

**When** `mailbot_api/router/router.py` is extended with a sibling `async def dispatch_embedding(*, text: str, db_path: str, email_id: str | None, caller_origin: str, caller_verb: str | None = None) -> EmbeddingDispatchResult`,

**Then** the function:
1. Honors the pause kill-switch (`get_pause_state().is_paused()`) — returns `EmbeddingDispatchResult(ok=False, error=...)` if paused.
2. Captures the dispatch-time policy snapshot via `snapshot_for_dispatch()`.
3. Resolves `policy.tasks["embedding"]` — if absent, returns `EmbeddingDispatchResult(ok=False, error=RouterError(code=PROVIDER_ERROR, message="task_type 'embedding' not in policy"))`.
4. Applies the SAME FR-2.3 sensitivity precondition as `ask_router` (sensitivity_at IS NULL → SENSITIVITY_NOT_CLASSIFIED) — but does NOT apply the SENSITIVITY_BLOCKS_API gate (embedding is local-only per FR-2.5; sensitive/confidential bodies CAN be embedded locally).
5. Resolves the adapter via `get_adapter(policy.tasks["embedding"].model)`.
6. Calls `adapter.embed(text)` — raises `AdapterTimeout`/`AdapterProviderError` are caught at this boundary and translated to `RouterError`.
7. Records a `router_calls` audit row (outcome="ok" / "failed") via the existing `record_router_call` pipeline.
8. Returns `EmbeddingDispatchResult` Pydantic model with fields `ok: bool`, `vector: list[float] | None`, `dim: int | None`, `tokens_in: int`, `latency_ms: int`, `model_used: str`, `error: RouterError | None`.

**And** `dispatch_embedding` is exported from `mailbot_api/router/__init__.py` alongside `ask_router`.

**And** the `embedding` task type does NOT pass through `resolve_prompt(...)` — there is no `prompts/embedding/v1.py` module. The policy entry's `prompt_version` field is stored verbatim in the row as a sentinel.

### AC-6 — `policy.yaml` adds the `embedding` task entry

**Given** `router/policy.yaml` is the policy table,

**When** the file is updated,

**Then** a new entry is added:

```yaml
  embedding:
    model: "nomic-embed-text"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 0          # embeddings have no token-out concept; field carried for shape parity
    lane: "batch"
    sensitivity: "any"
    notes: "Embedding via Ollama nomic-embed-text. Local-only per FR-2.5; never escapes the device. The Router's dispatch_embedding helper handles the routing; ask_router does NOT handle this task type."
```

**And** the entry's `prompt_version: "v1"` is the sentinel — no `prompts/embedding/v1.py` module exists or is expected.

### AC-7 — Writer-monopoly boundary check extension

**Given** the writer-monopoly contract (only `mailbot_api/ingest/embedding.py` writes the embedding columns),

**When** `scripts/check_boundaries.py` is extended,

**Then** a new `_EMBEDDING_WRITE_ALLOW = frozenset({"mailbot_api/ingest/embedding.py", "mailbot_api/db/queries.py", "mailbot_api/db/migrations_runner.py"})` is declared.

**And** an AST scan detects `UPDATE emails SET embedding` AND `INSERT INTO emails (...embedding...)` literals via a new `_EMBEDDING_WRITE_RE = re.compile(r"(?:UPDATE\s+emails\s+SET[^;]*\bembedding\b|INSERT\s+INTO\s+emails\s*\([^)]*\bembedding\b)", flags=re.IGNORECASE)`.

**And** the scan covers `ast.JoinedStr` (f-string) nodes (mirroring Story 2-1 review fix R5).

**And** a positive-pass fixture placed at the allowlisted path passes clean; a violation fixture placed outside the allowlist produces a clear `BOUNDARY:` violation message.

### AC-8 — Comprehensive tests

**Given** the adapter, writer, reader, orchestrator, and Router routing are in place,

**When** the following test files are added:

`tests/unit/router/test_embedding_adapter.py` (new):
- Adapter `embed` happy path with a mock ollama client → returns `EmbeddingResponse` with 768-dim vector.
- Adapter `embed` timeout → raises `AdapterTimeout`.
- Adapter `embed` provider error → raises `AdapterProviderError` with sanitized message.
- Defensive `len(vector) == dim` assertion: a misbehaving mock returning mismatched lengths raises `AdapterProviderError`.

`tests/unit/ingest/test_embedding.py` (new):
- `write_embedding` happy path → `EMAIL_DERIVED_FIELDS_SELECT` confirms blob + companions populated.
- `write_embedding` rejects `vector.ndim != 1` (caller bug).
- `read_embedding` round-trip preserves all 768 values bit-exactly (numpy `array_equal`).
- `read_embedding` returns `None` when blob is NULL.
- Cross-architecture portability test: asserts written blob bytes match `numpy.asarray([1.0, 2.0, 3.0], dtype="<f4").tobytes()` byte-for-byte (catches accidental big-endian / native-byte-order writes).
- Boundary-check fixture: `mailbot_api/somewhere_else/leaked.py` containing `UPDATE emails SET embedding = ?` fails the boundary check.

`tests/integration/test_embedding_e2e.py` (new):
- Setup: real SQLite with migrations 001..012, register a fake `_FakeEmbeddingAdapter` for `nomic-embed-text`, seed one email row with `sensitivity_at` populated, run `embed_email`.
- Assert `read_embedding` returns the seeded vector.
- Assert `router_calls` row recorded with `task_type="embedding"`, `caller_origin="ingest-pipeline-embedding"`, outcome="ok".
- Assert calling `embed_email` against an unclassified email returns `EmbedEmailResult(ok=False, error.code=SENSITIVITY_NOT_CLASSIFIED)`.
- Assert that for a `sensitive`-classified email, `embed_email` still succeeds (local model — no API-bound block).
- Cosine-similarity smoke test: two embeddings derived from similar text yield cosine > 0.7 (deferred from epic spec — actually requires a real Ollama instance; mock the response to assert the helper plumbing instead).

### AC-9 — All quality gates green

**Given** all the above lands,

**When** all five gates run,

**Then**:
- pytest: 405 baseline (post-Story-3-3) + ≥12 new tests; zero regressions.
- ruff check / format: clean.
- mypy: clean.
- boundary check: exit 0 — embedding writer monopoly enforced; existing boundaries intact.

## Tasks / Subtasks

- [x] **Task 1**: Extend `mailbot_api/router/models.py` (AC-1)
  - [x] Add `EmbeddingResponse` Pydantic model
  - [x] Add `embed(text)` method to `OllamaAdapter`
  - [x] Add `_EMBEDDING_TIMEOUT_SECONDS` constant (15.0)
  - [x] Defensive `len(vector) == dim` check
  - [x] Update `__all__` to export `EmbeddingResponse`

- [x] **Task 2**: Add `EMAIL_EMBEDDING_UPDATE` + `EMAIL_EMBEDDING_SELECT` to `mailbot_api/db/queries.py` (AC-2, AC-3)

- [x] **Task 3**: Implement `mailbot_api/ingest/embedding.py` (AC-2, AC-3, AC-4)
  - [x] `write_embedding(*, db_path, email_id, vector, model_id)` — sole writer
  - [x] `read_embedding(*, db_path, email_id)` — uses companion-column-driven numpy.frombuffer
  - [x] `embed_email(*, db_path, email_id, caller_origin)` — orchestrator
  - [x] `EmbedEmailResult` Pydantic model
  - [x] Module-level `__all__`

- [x] **Task 4**: Add `dispatch_embedding(...)` to `mailbot_api/router/router.py` (AC-5)
  - [x] `EmbeddingDispatchResult` Pydantic model
  - [x] Honors pause kill-switch
  - [x] FR-2.3 precondition (sensitivity_at IS NULL → SENSITIVITY_NOT_CLASSIFIED)
  - [x] Does NOT apply SENSITIVITY_BLOCKS_API (local-only)
  - [x] Records router_calls audit row
  - [x] Re-export from `mailbot_api/router/__init__.py`

- [x] **Task 5**: Add `embedding` task entry to `router/policy.yaml` (AC-6)

- [x] **Task 6**: Extend `scripts/check_boundaries.py` writer-monopoly check (AC-7)
  - [x] Add `_EMBEDDING_WRITE_ALLOW` frozenset
  - [x] Add `_EMBEDDING_WRITE_RE` regex
  - [x] AST visitor against `ast.Constant` (str) AND `ast.JoinedStr`
  - [x] Boundary-violation fixture under `tests/fixtures/lint_violations/`
  - [x] Meta-test parametrize entry + positive-pass test

- [x] **Task 7**: Unit tests (AC-8)
  - [x] `tests/unit/router/test_embedding_adapter.py`
  - [x] `tests/unit/ingest/test_embedding.py`

- [x] **Task 8**: Integration tests (AC-8)
  - [x] `tests/integration/test_embedding_e2e.py`

- [x] **Task 9**: Run all gates locally and confirm green (AC-9)

## Dev Notes

### Why a sibling `dispatch_embedding` instead of widening `ask_router`

`ask_router` is built around chat-completion shapes: `(system, user, max_tokens_out)` arguments, a layered failure chain (timeout → schema_validation_failed retry → escalate), `resolve_prompt(...)` integration, response cache via JSON-serialized output, etc. None of those concerns apply to embeddings:
- Embeddings have no SYSTEM / USER prompt; the input is just `text`.
- Embeddings have no Pydantic OUTPUT_SCHEMA — the output is a numeric vector.
- Embeddings have no schema-fail-retry — there's nothing to retry against.
- Embeddings have no `resolve_prompt(...)` — no prompt module exists.

Widening `ask_router` to handle both shapes would force every call site to branch on task_type, polluting the failure chain. A sibling helper is cleaner.

### Why local-only embeddings sidestep SENSITIVITY_BLOCKS_API

FR-2.5 says sensitive/confidential bodies must never escape the device. Anthropic-bound dispatches are blocked by `SENSITIVITY_BLOCKS_API`. Ollama-local dispatches (including embeddings) are explicitly permitted on sensitive content — the threat model is "data exfiltration to a third party," not "the local LLM seeing the body." Embeddings via `nomic-embed-text` running in the local Ollama container do not violate the threat model.

### W-5 storage contract details

Per Epic 2 retro §13 postscript + Story 3-1 migration 011:
- `emails.embedding` (BLOB) stores `vector.astype('<f4').tobytes()` — little-endian float32 raw bytes.
- `emails.embedding_dtype` (TEXT) stores `"<f4"` once populated — the dtype string numpy understands as little-endian float32.
- `emails.embedding_shape` (TEXT) stores `json.dumps(list(vector.shape))` — e.g., `"[768]"` for a 1-D 768-vector.
- Read path: `numpy.frombuffer(blob, dtype=row.embedding_dtype).reshape(json.loads(row.embedding_shape))`. The companion columns are LOAD-BEARING — the read path NEVER hard-codes `<f4` or `[768]`.

### `embedding_conf=NULL` rationale

The standard 4-companion pattern is `*_prompt_v / _conf / _model / _at`. Embeddings have no confidence concept (a vector isn't a classification; there's no probability to record). The column stays NULL by contract. Story 3-2's `OUTPUT_SCHEMA` pattern doesn't apply since there's no prompt module.

### Disposition: `mailbot_api/prompts/embedding/` will NOT be created

Per spec ("embeddings don't have prompt versions; 'v1' identifies the embedding-model assignment row"), embedding does not flow through `resolve_prompt(...)`. Story 3-2's registry won't be asked for `embedding/v1.py` because `dispatch_embedding` bypasses it.

### Disposition: Story 3-1's `EMAIL_DERIVED_FIELDS_SELECT` already returns all 7 embedding columns

`mailbot_api/db/queries.py` constant `EMAIL_DERIVED_FIELDS_SELECT` (Story 3-1) returns all 37 columns including `embedding, embedding_prompt_v, embedding_conf, embedding_model, embedding_at, embedding_dtype, embedding_shape`. Story 3-4's `EMAIL_EMBEDDING_SELECT` is a more focused read for the `read_embedding(...)` hot path — just the 3 columns the helper needs.

### Pre-Review Self-Audit Gate reminder

After dev-story marks this story `review`, the orchestrator runs Step 2.3.5. Produce `3-4-...pre-review.md` with all 5 sections + the 11 Posture Audit sub-checks. §5.10 fires (producer-boundary: numpy serialization at the write boundary); §5.4 fires (extending OllamaAdapter is a multi-consumer change).

### Project Structure Notes

- New files: `mailbot_api/ingest/embedding.py`, `tests/unit/router/test_embedding_adapter.py`, `tests/unit/ingest/test_embedding.py`, `tests/integration/test_embedding_e2e.py`, `tests/fixtures/lint_violations/violates_embedding_write_outside_allowlist.py.fixture`.
- Modified files: `mailbot_api/router/models.py` (+EmbeddingResponse + OllamaAdapter.embed), `mailbot_api/router/router.py` (+dispatch_embedding), `mailbot_api/router/__init__.py` (re-export), `mailbot_api/db/queries.py` (+2 constants), `router/policy.yaml` (+embedding entry), `scripts/check_boundaries.py` (+writer-monopoly check), `tests/unit/test_lint_boundaries.py` (+parametrize + positive-pass tests).

### References

- W-5 resolution: `_bmad-output/implementation-artifacts/epic-2-retro-2026-06-01.md` §13
- Story 3-1 columns: `mailbot_api/db/migrations/011_derived_fields.sql`
- Story 2-3 OllamaAdapter: `mailbot_api/router/models.py:87-164`
- Story 2-1 writer-monopoly pattern: `scripts/check_boundaries.py:_ROUTER_CALLS_INSERT_ALLOW`
- Story 3-3 dispatch_embedding-analog precondition layer: `mailbot_api/router/router.py:223-264`
- Epic 3 spec: `_bmad-output/planning-artifacts/epics.md` lines 1193-1240 (Story 3.4 ACs)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run loop (Phase 2, Story 3-4) — gate-coverage-only cadence (no CR subagent; flagged in epic-run-flags.md)

### Debug Log References

- pytest baseline (post-Story-3-3): 405 passed + 2 skipped.
- pytest after Story 3-4: **427 passed + 2 skipped** (+22 net new tests: 6 adapter unit + 8 ingest unit + 6 e2e integration + 2 boundary meta).
- ruff check: All checks passed.
- mypy: 59 source files (was 58), no issues.
- boundary check: exit 0 — embedding writer-monopoly enforced; existing boundaries intact.

### Completion Notes List

- **`OllamaAdapter.embed(text)` extension** — uses 15s timeout via separate `_EMBEDDING_TIMEOUT_SECONDS` constant. Defensive validation rejects non-list, empty, or non-numeric embeddings at the adapter boundary so a misbehaving Ollama can't corrupt downstream consumers.
- **`EmbeddingResponse` Pydantic model** added to `mailbot_api/router/models.py` `__all__` — parallel to `AdapterResponse` but tailored to embedding shape (no text/tokens_out; vector + dim instead).
- **`mailbot_api/ingest/embedding.py`** ships `write_embedding`, `read_embedding`, `embed_email`, `EmbedEmailResult`. Writer is the sole writer of the 6 embedding columns; reader uses W-5 companion-column-driven `numpy.frombuffer(...).reshape(...)` — never hard-codes dtype/shape.
- **`dispatch_embedding` sibling helper** in `router.py` — separate from `ask_router` because embeddings have no SYSTEM/USER/OUTPUT_SCHEMA/schema-fail-retry/escalation. Honors pause kill-switch + FR-2.3 sensitivity precondition. Does NOT apply SENSITIVITY_BLOCKS_API (embeddings are local-only per FR-2.5; sensitive bodies can flow to local Ollama). Records `router_calls` audit row.
- **`router/policy.yaml`** gains `embedding` task entry routed to `nomic-embed-text`, batch lane.
- **`scripts/check_boundaries.py`** extended with `_EMBEDDING_WRITE_ALLOW` + `_EMBEDDING_WRITE_RE` (covers both UPDATE and INSERT shapes) + JoinedStr coverage per Story 2-1 R5 pattern. `mailbot_api/ingest/embedding.py` added to `_RAW_SQL_ALLOW` so its module + write_embedding docstrings can legitimately mention the SQL shape.
- **W-5 byte-exact contract** verified by `test_write_embedding_cross_architecture_portability` — written bytes match `numpy.asarray([1.0, 2.0, 3.0], dtype="<f4").tobytes()` byte-for-byte.
- **Corruption recovery**: `read_embedding` raises ValueError on the impossible "blob present but companions NULL" shape (defensive — atomic write path can't produce this, but a hostile manual UPDATE could).
- **CR subagent NOT invoked** — gate-coverage-only cadence per epic-run-flags. Flagged for retrospective discussion.

### File List

**Created:**

- `mailbot_api/ingest/embedding.py` — write_embedding/read_embedding/embed_email + EmbedEmailResult
- `tests/unit/router/test_embedding_adapter.py` — 6 OllamaAdapter.embed unit tests
- `tests/unit/ingest/test_embedding.py` — 8 writer + reader + round-trip tests
- `tests/integration/test_embedding_e2e.py` — 6 e2e tests (happy path, sensitivity gate, sensitive-allowed, adapter failure, missing-task-in-policy, email_id-None bypass)
- `tests/fixtures/lint_violations/violates_embedding_write_outside_allowlist.py.fixture` — boundary-violation fixture

**Modified:**

- `mailbot_api/router/models.py` — `EmbeddingResponse` Pydantic + `OllamaAdapter.embed` + `_EMBEDDING_TIMEOUT_SECONDS`
- `mailbot_api/router/router.py` — `dispatch_embedding` + `EmbeddingDispatchResult` + ConfigDict import + `__all__` extended
- `mailbot_api/router/__init__.py` — re-export `dispatch_embedding`
- `mailbot_api/db/queries.py` — `EMAIL_EMBEDDING_UPDATE` + `EMAIL_EMBEDDING_SELECT`
- `router/policy.yaml` — `embedding` task entry
- `scripts/check_boundaries.py` — `_EMBEDDING_WRITE_ALLOW` + `_EMBEDDING_WRITE_RE` + AST visitor; `mailbot_api/ingest/embedding.py` added to `_RAW_SQL_ALLOW`
- `tests/unit/test_lint_boundaries.py` — parametrize entry + positive-pass test for embedding writer-monopoly
