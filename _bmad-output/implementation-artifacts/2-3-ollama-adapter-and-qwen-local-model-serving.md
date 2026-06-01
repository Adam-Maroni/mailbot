---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.3: Ollama adapter + Qwen local-model serving

Status: done

## Story

As Adam,
I want a thin `OllamaAdapter` in `mailbot_api/router/models.py` that calls Qwen 2.5 3B (Q4_K_M) via the `ollama` Python client and returns a normalized response shape,
So that the local-LLM leg works in isolation before being plumbed into the Router's failure chain.

## Context

Story 2-1 shipped the audit + error shapes; 2-2 shipped the policy schema + hot-reload. Story 2-3 ships the **first concrete adapter** — Ollama. The adapter is **not** wired into `ask_router` yet (Story 2-4 does that); 2-3 ships it in isolation with a `ModelAdapter` Protocol + the concrete `OllamaAdapter` + `AdapterResponse` Pydantic shape + `AdapterTimeout` / `AdapterProviderError` exception types. The single allowed `import ollama` boundary (architecture Rule I, F.1) is enforced by `scripts/check_boundaries.py` (Story 1-4 already wired this).

The real-Qwen latency AC (p95 ≤ 5s over 20 sequential calls) requires a real Ollama container with `qwen2.5:3b-instruct-q4_K_M` pre-pulled. That's Phase 3.5 manual-verification material per project conventions; this story's tests use httpx-mocked transport via `ollama.AsyncClient`'s internal httpx client.

## Acceptance Criteria

**AC-1 (`AdapterResponse` Pydantic shape).** `mailbot_api/router/models.py` (NEW FILE) defines:

- `class AdapterResponse(BaseModel)` with fields:
  - `text: str` — the assistant-message content
  - `tokens_in: int`
  - `tokens_out: int`
  - `cached_tokens_in: int` — always 0 for Ollama
  - `latency_ms: int`
  - `raw: dict[str, Any]` — provider raw payload for debugging
- `model_config = ConfigDict(arbitrary_types_allowed=False, extra="forbid")` — `raw` is a plain `dict`, so no arbitrary-types needed.

**AC-2 (`ModelAdapter` Protocol).** `models.py` also defines:

- `class ModelAdapter(Protocol)` with `async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse: ...`
- This Protocol is the interface Story 2-4's `ask_router` dispatches against. Both `OllamaAdapter` (this story) and the future `AnthropicAdapter` (Story 2-6) implement it.

**AC-3 (`AdapterTimeout` and `AdapterProviderError`).** `models.py` defines:

- `class AdapterError(Exception)` — base class.
- `class AdapterTimeout(AdapterError)` — raised when the adapter's hard timeout fires. Carries `model_id: str` and `timeout_seconds: float` attributes.
- `class AdapterProviderError(AdapterError)` — raised for any other provider-side failure. Carries `model_id: str` and `sanitized_message: str` attributes.

Per architecture: any non-timeout adapter exception MUST be caught and re-raised as `AdapterProviderError(sanitize_error(...))` — raw provider exceptions never cross the adapter boundary.

**AC-4 (`OllamaAdapter` class).** `models.py` defines:

- `class OllamaAdapter:` with `__init__(self, model_id: str, base_url: str, timeout_seconds: float = 30.0)` per FR-3.4 local-call timeout default.
- Stores `model_id`, `base_url`, `timeout_seconds`; constructs an `ollama.AsyncClient(host=base_url)` (or equivalent) lazily on first call so adapter construction is side-effect-free (no network on `__init__`).
- `async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse`:
  - Builds the chat request: `messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]`.
  - Passes `options={"num_predict": max_tokens_out, "temperature": temperature}` (Ollama's max-output is `num_predict`).
  - Wraps the call in `asyncio.wait_for(..., timeout=self.timeout_seconds)`. On `asyncio.TimeoutError` → `AdapterTimeout(model_id=..., timeout_seconds=...)`.
  - On any other `Exception` → `AdapterProviderError(model_id=..., sanitized_message=sanitize_error(exc))`.
  - On success: extracts `text` from the response's `message.content`, derives `tokens_in` / `tokens_out` from `prompt_eval_count` / `eval_count`, measures elapsed `latency_ms` via `time.monotonic_ns()`, returns the `AdapterResponse`.

**AC-5 (boundary enforcement).** `scripts/check_boundaries.py` already permits `import ollama` only in `mailbot_api/router/models.py` (Story 1-4 / boundary `_OLLAMA_ALLOW`). This story uses the existing allowlist — no boundary check changes needed.

**AC-6 (unit tests — happy path).** `tests/unit/router/test_ollama_adapter.py` (NEW FILE) covers:

- Happy-path: monkeypatch `ollama.AsyncClient` to return a canned `ChatResponse`-shaped dict; assert `AdapterResponse` fields populated correctly.
- Token-counting: assert `tokens_in == prompt_eval_count` and `tokens_out == eval_count` from the mocked response.
- `cached_tokens_in == 0` always.
- `latency_ms > 0` after a brief sleep in the mock.

**AC-7 (unit tests — timeout).** `tests/unit/router/test_ollama_adapter.py` covers:

- Timeout: mock `AsyncClient.chat` to take longer than `timeout_seconds=0.1`; assert `AdapterTimeout` raised with `model_id` and `timeout_seconds` attributes preserved.

**AC-8 (unit tests — error wrapping).** `tests/unit/router/test_ollama_adapter.py` covers:

- Provider error: mock `AsyncClient.chat` to raise `ollama.ResponseError("upstream 500")`; assert `AdapterProviderError` raised; raw exception's message is sanitized (any secrets stripped per `sanitize_error`).
- Generic exception: mock to raise `RuntimeError("boom")`; assert `AdapterProviderError`.

**AC-9 (integration test gated as opt-in).** Per the original AC, no required integration test against a real Ollama container. `tests/integration/test_ollama_adapter_real.py` (NEW FILE) is gated behind an env var `MAILBOT_RUN_REAL_OLLAMA=1` (uses `pytest.skip` if unset) and exercises the latency AC + the "Reply with OK" smoke test. It's the canonical Phase 3.5 verification artifact.

**AC-10 (`docker-compose.yml` ollama model pre-pull).** Verify that Story 1-2's Docker stack pre-pulls `qwen2.5:3b-instruct-q4_K_M` and `nomic-embed-text` either via a post-start script or a one-shot job. If not present, add a `model_warmup` service that runs `ollama pull qwen2.5:3b-instruct-q4_K_M && ollama pull nomic-embed-text` against the ollama container. If already present, leave as-is and note in Dev Notes.

**AC-11 (all gates green).** ruff / mypy --strict / boundary / pytest — all clean. Baseline 194 → +N for the new unit tests.

## Tasks / Subtasks

- [x] **Task 1** — Implement `mailbot_api/router/models.py` shapes + exceptions (AC: #1, #2, #3)
- [x] **Task 2** — Implement `OllamaAdapter` class (AC: #4)
- [x] **Task 3** — Unit tests: happy path + token counting + latency (AC: #6)
- [x] **Task 4** — Unit tests: timeout (AC: #7)
- [x] **Task 5** — Unit tests: error wrapping (AC: #8)
- [x] **Task 6** — Integration test scaffold (gated, opt-in) (AC: #9)
- [x] **Task 7** — Docker model-warmup (AC: #10)
- [x] **Task 8** — All gates green (AC: #11)

## Dev Notes

### Why a `ModelAdapter` Protocol and not a `BaseAdapter` ABC

Architecture line 843 names "`ModelAdapter` base, OllamaAdapter, AnthropicAdapter" — but Python `Protocol` is structurally typed and matches "duck-typed adapter interface" more cleanly than a runtime-inherited ABC. Story 2-6's `AnthropicAdapter` will implement the same `call(...)` signature and `isinstance` checks aren't needed (Story 2-4 dispatches via the protocol type only). Using Protocol avoids the metaclass conflict with Pydantic v2's `BaseModel` that often arises with ABC + Pydantic mixing.

### `ollama.AsyncClient` lifecycle

Constructing it is side-effect-free (no network); the first network call happens on `chat(...)`. The client supports a `timeout` constructor parameter, but the project preference per Story 2-1's `sanitize_error` discipline is to use `asyncio.wait_for(..., timeout=...)` — this gives a single, predictable failure type (`asyncio.TimeoutError`) regardless of which layer raised. `ollama.AsyncClient`'s internal timeout could fire as `httpx.ReadTimeout` or similar, which we'd have to catch separately.

### `time.monotonic_ns()` for `latency_ms`

`time.monotonic()` is fine but returns float seconds; nanoseconds + integer division by 1_000_000 avoids any float-precision wobble at sub-millisecond latencies. Consistent with Story 1-3's pragma-aware timing pattern.

### `raw: dict[str, Any]` — typing pragmatism

The Ollama response is a `ChatResponse` Pydantic model in their SDK. We could carry it forward typed, but storing it as `dict[str, Any]` via `.model_dump()` (or `dict(response)` if it's a TypedDict) avoids tying `AdapterResponse`'s public API to an external Pydantic class that could change between Ollama SDK releases. The cost is mypy `Any` propagation — bounded inside `models.py`.

### Files being touched / created

**Created:** `mailbot_api/router/models.py`, `tests/unit/router/test_ollama_adapter.py`, `tests/integration/test_ollama_adapter_real.py`
**Updated:** `docker-compose.yml` (if model warmup not yet present)

### References

- [Source: epics.md#Story 2.3]
- [Source: architecture.md line 843 (ModelAdapter base)]
- [Source: architecture.md FR-3.4 timeout discipline]
- [Source: mailbot_api/router/errors.py:sanitize_error] for the provider-error wrapping

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

### Completion Notes List

- **No code review subagent** spawned for 2-3 — gate-coverage strategy (per epic-1 story 1-4 pattern). Story scope is narrowly scoped (one adapter + Pydantic shape + exception hierarchy + protocol) with comprehensive mock-based unit coverage and the boundary check enforcing the Rule I `import ollama` allowlist. Subagent spawn would add latency without surfacing issues the gates can't catch.
- **`AdapterResponse.cached_tokens_in` always 0 for Ollama** — Ollama has no equivalent to Anthropic's `cache_read_input_tokens`. Story 2-6's `AnthropicAdapter` will be the first adapter where this field carries real values.
- **`ModelAdapter` is a `Protocol`, not an ABC** — structural typing avoids the Pydantic-v2-`BaseModel` + ABC metaclass conflict pattern. Story 2-4's `ask_router` will dispatch by Protocol type only.
- **Opt-in real-Ollama tests are skipped by default** — gated by `MAILBOT_RUN_REAL_OLLAMA=1`. Phase 3.5 verification material per PORTING.md. Test count: 9 unit tests (all green) + 2 opt-in skipped.
- **docker-compose model warmup added** — new `ollama_model_warmup` one-shot service pulls `qwen2.5:3b-instruct-q4_K_M` and `nomic-embed-text` against the `ollama` container once it's healthy. Idempotent (`ollama pull` is no-op on a model already in the volume).
- **No boundary check changes** — Story 1-4's `_OLLAMA_ALLOW` already permits `import ollama` only in `mailbot_api/router/models.py`.
- **203 passed + 2 skipped** (194 baseline → 203, +9 unit tests; +2 opt-in real-Ollama skipped). All gates green.

### File List

**Created:**

- `mailbot_api/router/models.py` — `AdapterResponse` / `ModelAdapter` Protocol / `AdapterError`+`AdapterTimeout`+`AdapterProviderError` / `OllamaAdapter`
- `tests/unit/router/test_ollama_adapter.py` — 9 mock-based unit tests
- `tests/integration/test_ollama_adapter_real.py` — 2 opt-in (env-gated) real-Ollama tests

**Updated:**

- `docker-compose.yml` — added `ollama_model_warmup` one-shot service
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 2-3 → done

## Change Log

- 2026-06-01 (claude-opus-4-7, autonomous-epic-run) — Story 2-3 implemented: OllamaAdapter + ModelAdapter Protocol + AdapterResponse Pydantic shape + AdapterError exception hierarchy + docker-compose model warmup. 203 tests pass (+9 unit, +2 opt-in skipped); all gates green.

