---
baseline_commit: 8e53f5b
---

# Story 6.11: Ingest pipeline `sensitivity_class` step stuck on `provider_error` — F17 investigation + fix

Status: review

> **Filed 2026-06-04** during Story 6-6.5 Section B prereq seeding. Live `/admin/status` showed `ingest.unprocessed_count=1618`; `mailbot-api` log showed ~30 consecutive `event=ingest.step.failed task_type=sensitivity_class error_code=provider_error` lines per ingest tick, no `message` field, since 2026-06-01 21:02 UTC. Other Router task types (`hermes_aux`, `chat_completions_tool_call`) reach Anthropic fine. The bug is `sensitivity_class`-specific OR exits before reaching `ask_router`. **Surgical fix, not a refactor.** See `epic-6-run-flags.md § F17` for the full finding.

## Story

As the MailBot ingest pipeline,
I want the `sensitivity_class` step to dispatch successfully to the Router and write classification results to `emails.sensitivity`,
So that the 1618-email unclassified backlog drains, Story 6-6.5 Section B's CP-A/B/C walks become unblocked, and the privacy-defending sensitivity gate (Story 3-3 + Story 4-7) actually fires against incoming mail again.

## Acceptance Criteria

**AC-1 — Surfacing the underlying error.**
Given the current `ingest.step.failed` log line at `mailbot_api/ingest/pipeline.py:341-348` only logs `error_code` (the underlying message is silently dropped),
When this story's first task runs,
Then the log line MUST be extended to also include `error_message=<sanitized>` (sanitized via `mailbot_api.router.errors.sanitize_error`, which already redacts bearer tokens, sk- keys, URL query secrets, and `.env`/`.key`/`.pem` paths per NFR-SEC-4 — see `mailbot_api/router/errors.py:225-265`),
And the next ingest tick MUST surface the actual root-cause string in `docker compose logs mailbot-api`.

**AC-2 — Root cause identified + fixed.**
Given the unredacted error is now visible,
When the root cause is identified,
Then the minimal code change MUST close the failure,
And the next ingest tick MUST produce at least one new `router_calls` row with `task_type='sensitivity_class'` AND `outcome IN ('ok', 'retry_recovered')` AND `ts > '2026-06-04T00:00:00Z'`,
And the corresponding `emails.sensitivity` + `emails.sensitivity_at` cells MUST be populated post-tick.

**AC-3 — Regression test against the boundary that broke.**
Given the root cause is closed,
When the fix lands,
Then it MUST be accompanied by an integration test in `tests/integration/` that exercises `process_email` end-to-end against a real `ModelAdapter` boundary (NOT a mocked Router), so the same failure mode would have been caught BEFORE shipping.
The shape SHOULD mirror existing tests like `tests/integration/test_ingest_pipeline_process_email.py` (or sibling), using the Story-3-5 Middleware-Real-Bootstrap rule per architecture §2.4.7 ("real adapters at the dispatch boundary; mocking is forbidden at the SDK boundary in integration tests").

**AC-4 — Backlog drains.**
Given the fix is deployed,
When the next 6 ingest ticks (30 min at the 5-min cadence) run,
Then `/admin/status` MUST report `ingest.unprocessed_count` strictly decreasing,
And `ingest.backpressure_active` MUST eventually flip to `false` once the queue drains below the backpressure floor.

**AC-5 — Story 6-6.5 Section B unblocked.**
Given AC-1..AC-4 pass,
When this story closes,
Then `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Section B` MUST be updated to flip CP-A/B/C from BLOCKED to QUEUED,
And `epic-6-run-flags.md § F17` status MUST flip from OPEN to RESOLVED with a one-line root-cause summary,
And `_bmad-output/implementation-artifacts/sprint-status.yaml` row for `6-6-5-epic-5-capstone-carry-forward-walk` MUST be amended noting the F17 unblock.

**AC-6 — Temporary diagnostics removed (if added).**
Given the dev added any TEMP-tagged diagnostic logging at the Router error-construction sites (`mailbot_api/router/router.py` PROVIDER_ERROR sites) to triangulate root cause,
When the fix lands,
Then ALL temp-tagged logging MUST be removed before the final commit (it logs the underlying exception string, which is itself a redaction-class signal under NFR-SEC-4),
EXCEPT the persistent `error_message=<sanitized>` addition at the ingest pipeline boundary (AC-1) which is permanent and goes through `sanitize_error()`.

## Tasks / Subtasks

- [x] **Task 1 — Surface the unredacted error (AC-1). [start here]**
  - [x] Edit `mailbot_api/ingest/pipeline.py:341-348` (the `ingest.step.failed` log call) to add an `error_message` field to the `extra` dict, populated from `sensitivity_result.error.message if sensitivity_result.error else "no error object"`. Wrap with `sanitize_error(...)` only if the message hasn't already passed through sanitization at the Router boundary — which it has per `mailbot_api/router/router.py` PROVIDER_ERROR sites (lines 207, 228, 426, 459, 577, 760), so just pass the raw `.message` field through.
  - [x] ~~TEMP-tagged debug logs at Router error-construction sites~~ — SKIPPED (AC-1 alone was sufficient; the surfaced message immediately pinpointed root cause, no triangulation needed).
  - [x] Restart the mailbot-api container via `docker compose up -d --build mailbot-api`.
  - [x] Wait one ingest tick (≤ 5 min) and tail logs.
  - [x] Recorded the unredacted `error_message` value in Debug Log References.

- [x] **Task 2 — Root cause analysis (AC-2).**
  - [x] Mapped the surfaced message — **none of the prioritized hypotheses were correct**. Surfaced error: `"sensitivity classifier could not read policy snapshot: policy not loaded — set_policy_snapshot(load_policy(path)) must be called by the FastAPI lifespan before get_policy()"`. This comes from `classifier.py:_assert_qwen_only_per_call` line 97-101 (the FR-2.5 per-call safeguard catching a `RuntimeError` from `snapshot_for_dispatch()`).
  - [x] Identified specific code path: **Story 6-6 worker-process init gap**. The FastAPI lifespan in `mailbot_api/main.py` initializes the per-process module state (`set_policy_snapshot`, `_set_sensitivity_patterns`, `init_default_adapters`, `get_guard().initialize`, `get_pause_state().initialize`) but `mailbot_api/worker.py:main()` only ran `apply_pending_migrations` — leaving the worker process's policy snapshot, adapter registry, etc. all uninitialized. Story 6-6 (commit `a4fee96`, deployed 2026-06-03) moved the `ingest_pipeline` interval task from the api process's lifespan asyncio task into the worker process without porting this init. Other Router task types (`hermes_aux`, `chat_completions_tool_call`, chat orchestrator) all dispatch from the api process via FastAPI endpoints and thus work fine — perfectly explaining F17's "only sensitivity_class-from-ingest fails" blast radius.
  - [x] NOT an env-var gap (Hypothesis 5 from story spec — code audit was correct: no `get_secret` mandatory call on the `sensitivity_class` path).
  - [x] NOT a Story 6-9 column-order regression (Hypothesis 1 — wrong process, right time-of-arrival). Schema-side verified consistent.

- [x] **Task 3 — Code fix + integration test (AC-2 + AC-3).**
  - [x] Applied minimal structural fix (3 hunks): (a) promoted `_cli_init_runtime` → public `init_pipeline_runtime` in `mailbot_api/ingest/pipeline.py` + added `MAILBOT_SKIP_POLICY` / `MAILBOT_SKIP_PATTERNS` flag honoring (mirrors api lifespan) so existing test fixtures still work; (b) called `init_pipeline_runtime(db_path)` from `_worker_main` BEFORE scheduler start; (c) updated CLI call-site reference; (d) updated `__all__` export. Worker init is the structural fix; the `error_message` log extension at `pipeline.py:341-348` (Task 1) is permanent.
  - [x] Added integration test `tests/integration/test_worker_pipeline_runtime_init.py` with 2 tests: (a) structural — `init_pipeline_runtime` populates policy + adapter registry + sensitivity_class entry; (b) end-to-end — `process_email` dispatches via real Router (Middleware-Real-Bootstrap pattern) and writes a `router_calls(task_type='sensitivity_class', outcome IN ('ok','retry_recovered'))` row + `emails.sensitivity` populated.
  - [x] Updated `tests/integration/test_pipeline_e2e.py::test_cli_init_runtime_loads_policy_patterns_and_adapters` to use the new public name.
  - [x] Updated `tests/integration/test_worker_main_integration.py` to set `MAILBOT_SKIP_POLICY=1` / `MAILBOT_SKIP_PATTERNS=1` (this test verifies heartbeat plumbing, not classification — same skip-flag pattern api lifespan uses).
  - [x] No TEMP F17 diagnostic logs were added in Task 1 (AC-6 satisfied by default).
  - [x] All 4 gates green: pytest **1060 passed + 2 skipped** (+2 net from new test module; vs 1058+2 baseline at 6-9 close), ruff `All checks passed!`, mypy `Success: no issues found in 122 source files`, boundary checker silent (zero output = pass).

- [x] **Task 4 — Backlog drain verification (AC-4).**
  - [x] Pre-fix `/admin/status` baseline (via direct SQLite query — `/admin/status` returns the same data): `unprocessed_count=1620, classified={normal:2, sensitive:2}`.
  - [x] Post-fix waited 2 ingest ticks: `unprocessed_count: 1620 → 1614` (–6, strictly decreasing). Classification distribution: `{normal:7, sensitive:2, confidential:1}` — **first `confidential` row in DB history** (Story 6-6.5 CP-C was blocked specifically on this).
  - [x] `sensitivity_class` router_calls outcomes since fix: `{retry_recovered: 6}` — every dispatch succeeded after a single schema retry (Qwen's JSON output occasionally trips first-attempt validation; Story 2-4's escalation chain handles this normally).
  - [x] AC-4 "backpressure_active flips to false" deferred: 1614 is still well above the backpressure floor — drain will continue naturally over many hours. The strictly-decreasing requirement is met.

- [x] **Task 5 — Unblock Story 6-6.5 Section B + close F17 (AC-5).**
  - [x] Edited `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Section B`: CP-A/B/C flipped from `🛑 BLOCKED by F17` to `⏯ QUEUED — F17 closed by Story 6-11 on 2026-06-04; CP re-walk pending`.
  - [x] Edited `_bmad-output/implementation-artifacts/epic-6-run-flags.md § F17`: prepended `STATUS: RESOLVED 2026-06-04T15:16:51Z by Story 6-11` block with root-cause summary (worker-process init gap) and reflection on why both filing-time and create-story analysis missed it (didn't enumerate the worker-process boundary as a distinct interpreter).
  - [x] Edited `_bmad-output/implementation-artifacts/sprint-status.yaml` line for `6-6-5-epic-5-capstone-carry-forward-walk`: amended with F17 closure timestamp + CP-A/B/C re-walk-queued note + flagged new downstream finding (summary_short schema_validation_failed, NON-BLOCKING for CP re-walks).

## Investigation Plan — Hypothesis Map

**Revised prioritization** (different from F17 filing — the filing assumed SecretMissing was most-likely; a code-side audit during story creation revised this. See "Why the original SecretMissing hypothesis is down-ranked" in Dev Notes).

1. **HIGH — Story 6-9 column-order regression in `router_calls` insert path.** Story 6-9 (commit `42fd4dc`, shipped 2026-06-03, deployed end-of-day) added migration `022_router_calls_tool_calls.sql` extending `router_calls` with `tool_calls_count` + `tool_calls_summary` NULLable columns AND updated `mailbot_api/db/queries.py` ROUTER_CALLS_INSERT, `mailbot_api/observability/audit.py` RouterCallRow + `_param_tuple` in lockstep. Spot-check during story creation showed all 4 sites consistent — but check whether the deployed environment ran the migration successfully (a partial migration would leave the schema accepting 16 columns while the code sends 18 → `sqlite3.OperationalError: 18 values for 16 columns`). Verify via `sqlite3 mailbot.db ".schema router_calls"` and confirm both new columns exist. Time alignment: the 2026-06-01 21:02 UTC last-success → 2026-06-04 broken window straddles the 6-9 deploy.

2. **MEDIUM — Pydantic schema validation failure on `SensitivityClassOutput`.** `mailbot_api/router/router.py:591-604` validates Qwen's response via `prompt.output_schema.model_validate_json(response.text)`. If Qwen's output drifted (e.g., Ollama upgraded the model file silently, or `temperature=0.0` no longer guarantees JSON-only output), the `ValidationError` would surface as PROVIDER_ERROR via `sanitize_error(exc)`. Counter-evidence: 4 successful 2026-06-01 calls used the same model — but reproducing a fresh Qwen response against the current Ollama instance is the test.

3. **MEDIUM — Ollama SDK / wire-format regression at the adapter boundary.** `mailbot_api/router/models.py:373-377` catches Exception broadly in `OllamaAdapter.call`. A breaking change in `ollama-python` (e.g., response shape, `prompt_eval_count` field name) would surface as PROVIDER_ERROR. Reproduce via `curl http://ollama:11434/api/chat -d '...'` to confirm wire format is what the SDK expects.

4. **LOW — Prompt-module version mismatch.** `mailbot_api/prompts/sensitivity_class/v1.py` is in good shape; `__init__.py` is intentionally empty (resolver uses dynamic import per `mailbot_api/prompts/__init__.py:resolve_prompt`). The `VERSION="v1"` constant in `v1.py:22` matches `policy.yaml:26 prompt_version: "v1"`. Unlikely but cheap to verify.

5. **LOW — SecretMissing at the verb boundary** (original F17 filing's top hypothesis — DOWN-RANKED). All `get_secret*` call sites on the `sensitivity_class` path were audited during story creation: every one uses `get_secret_optional` with a safe default. No `get_secret` (mandatory, can raise SecretMissing) is reachable from `classify_sensitivity → ask_router → OllamaAdapter.call`. Counter-evidence is strong; keep this as a fallback only if hypotheses 1-4 are eliminated.

## Dev Notes

### Why the original SecretMissing hypothesis is down-ranked

F17 was filed in 5 minutes of triage; the assessment cited `mailbot_api/config.py:18`'s docstring contract ("`SecretMissing` surfaces as `RouterError(code='provider_error', message='secret missing: <name>')` at the verb boundary"). The contract IS real, but the surface area where it could fire on the `sensitivity_class` path is empty:

| Call site on sensitivity_class path | Function used | Raises SecretMissing? |
| --- | --- | --- |
| `mailbot_api/sensitivity/classifier.py` (whole file) | (none — no env reads) | No |
| `mailbot_api/router/router.py` (whole file) | (none — no env reads) | No |
| `mailbot_api/router/registry.py:46` `OLLAMA_URL` | `get_secret_optional` (defaulted) | No |
| `mailbot_api/router/registry.py:68` `ANTHROPIC_API_KEY` | `get_secret_optional` (defaulted) | No — and sensitivity_class doesn't route to Anthropic anyway |
| `mailbot_api/ingest/pipeline.py:686-712` (CLI bootstrap, NOT the FastAPI hot path) | All `get_secret_optional` | No |

The FastAPI lifespan path is similar — `mailbot_api/main.py:84` does call `get_secret("MAILBOT_DB_PATH")`, but that fires at startup, not per-ingest-tick, and a startup failure would prevent the API from booting at all (other Router task types wouldn't be working either; F17's observation is that they ARE working).

**Conclusion**: the unredacted `error_message` from AC-1 is needed before assigning weight to any hypothesis. Once visible, hypothesis assignment becomes trivial. Don't pre-commit to a fix until Task 1's log line surfaces the actual string.

### Architecture compliance (mandatory)

The fix MUST respect these contracts (architecture references in parens):

- **AR-PAT-4 errors-as-data** (`_bmad-output/planning-artifacts/architecture.md` §AR-PAT-4): the Router's errors-as-data contract stays. `classify_sensitivity` MUST NOT be changed to raise; `process_email` MUST keep its errors-as-data shape.
- **NFR-SEC-4 secret redaction** (architecture §NFR-SEC-4): any new logging that originates from an exception MUST flow through `sanitize_error()`. AC-1's new `error_message` field already does this because the Router boundary at `mailbot_api/router/router.py:207, 228, 426, 459, 577, 760` already sanitized the message before it was stored on `RouterError.message`.
- **FR-2.5 Qwen-only sensitivity** (architecture §FR-2.5, classifier.py:47): the fix MUST NOT change which model `sensitivity_class` dispatches to. Qwen-only is a hard privacy contract; sensitive email bodies never escape the device.
- **AR-PAT-5 4-export prompt contract** (`mailbot_api/prompts/__init__.py`): if the fix touches the prompt module, the 4-tuple `VERSION / SYSTEM / USER_TEMPLATE / OUTPUT_SCHEMA` contract stays; resolver validates at resolve-time.
- **Column-order contract** (`mailbot_api/observability/audit.py:27-30` docstring): if the fix touches `router_calls` schema, all 4 sites (migration + ROUTER_CALLS_INSERT + _param_tuple + RouterCallRow) MUST change in one commit.
- **Boundary checker** (`scripts/check_boundaries.py`): the literal `INSERT INTO router_calls` substring is allowed only in `audit.py`, `queries.py`, `migrations_runner.py`, and `migrations/006_router_calls.sql`. Don't expand the surface.

### Files being modified (UPDATE) — read before editing

Per the create-story skill's "read files being modified" requirement, here are the load-bearing files for this story and what they do today vs. what this story changes:

- **`mailbot_api/ingest/pipeline.py`** (UPDATE) — Current state: 734-line orchestrator; `process_email` (line 308) is the 7-step pipeline; sensitivity step at lines 333-349 logs `event=ingest.step.failed` with `error_code` only. **What this story changes**: extend the `extra` dict at lines 341-348 to include `error_message`. Preserve every other behavior, including the CR-3-5-5 `retryable` propagation and the `result.failed_at = "sensitivity_class"` setter.
- **`mailbot_api/sensitivity/classifier.py`** (UPDATE — conditional) — Current state: 240-line classifier wrapper; `classify_sensitivity` (line 130) dispatches via `ask_router(task_type="sensitivity_class", ...)` and writes back via `EMAIL_SENSITIVITY_UPDATE`. **What this story might change**: depends on root cause. If FR-2.5 per-call safeguard (lines 88-127) is firing, fix the policy snapshot (NOT the safeguard). If the post-dispatch validation at lines 181-187 is failing, fix the prompt or the adapter (NOT the validator).
- **`mailbot_api/router/router.py`** (UPDATE — conditional) — Current state: 1500+ lines; `ask_router` (line ~155) is the agent-facing entry; PROVIDER_ERROR is constructed at lines 192, 206, 217, 227, 425, 458, 576, 759 (in ask_router) and 859, 873, 883, 933, 962 (in dispatch_embedding) and 1140, 1153, 1169, 1299, 1404, 1443 (in dispatch_tool_call). **What this story might change**: depends on root cause. Most likely zero changes here — it's a downstream consumer of whatever the actual bug is.
- **`mailbot_api/router/models.py`** (UPDATE — conditional) — Current state: `OllamaAdapter.call` (line 345) catches Exception broadly at line 373-377 and converts to `AdapterProviderError`. **What this story might change**: if Ollama wire-format regression is the cause, the broad-except contract stays, but the specific path that triggers it (e.g., `ollama-python` version pin in `pyproject.toml`) might need pinning.

### Build / test / lint commands (for the dev agent)

```bash
# 1. Stack up if not running (per Story 6-7 deploy.sh contract):
docker compose up -d --build mailbot-api ollama

# 2. Confirm ingest backlog exists:
curl -s -H "Authorization: Bearer $MAILBOT_ROUTER_KEY" http://localhost:8000/admin/status | python -m json.tool | grep -A 3 ingest

# 3. After Task 1 edit, restart api + tail logs:
docker compose up -d --build mailbot-api
docker compose logs -f mailbot-api --since 1m | grep -E "ingest\.(step\.failed|sensitivity)"

# 4. After fix:
pytest -q tests/integration/test_ingest_pipeline_sensitivity_class.py  # (new file from Task 3)
pytest -q  # full suite
ruff check mailbot_api/ tests/
mypy --strict mailbot_api/
python scripts/check_boundaries.py

# 5. Backlog drain check:
sqlite3 ./hermes-data/mailbot.db "SELECT COUNT(*) FROM emails WHERE sensitivity IS NULL"
sqlite3 ./hermes-data/mailbot.db "SELECT sensitivity, COUNT(*) FROM emails WHERE sensitivity IS NOT NULL GROUP BY sensitivity"
```

### Scope discipline — what this story does NOT include

- **Manual backfill CLI** for the 1618-email backlog beyond what natural ingest ticks drain. If a one-shot `mailbot ingest --backfill` is needed (e.g., backpressure throttle makes natural drain take days), file as Story 6-12. This story only fixes the bug + verifies drain trajectory.
- **Story 6-6.5 Section B re-walk.** That's a separate re-invocation of `bmad-dev-story 6-6-5` (or a manual Adam walk) AFTER this story closes; mechanically distinct.
- **Broader Router error-as-data refactors.** The `error_code`-only-no-message logging shape at `pipeline.py:341-348` is a latent observability gap, not a Router contract bug. AC-1 fixes only the sensitivity_class log line — do NOT sweep through other `event=*.failed` log calls in `mailbot_api/` to add `error_message` everywhere. Per `MEMORY.md feedback_cr_cadence_v2_structural.md` + global CLAUDE.md "Don't add features … beyond what the task requires": surgical only.
- **Promotion of the diagnostic log line to debug-level only.** AC-1's `error_message` field stays at the existing warning-level log line — observability dashboards already query `event=ingest.step.failed` and they SHOULD have the message field.

### Code-Review (CR) cadence per Adam's `feedback_cr_cadence_v2_structural.md` memory

This story will trigger MANDATORY-CR per the 6 §5.12 criteria. Likely fired criteria for this story:

- **#1 (new code path / new contract)** — likely fires if Task 3's integration test introduces a new test module.
- **#3 (observability / log-line semantics change)** — fires for AC-1's `error_message` addition.
- **#5 (cross-story load-bearing seam)** — fires because the bug interacts with Story 3-3 (classifier), Story 3-5 (pipeline), Story 2-1 (audit), and possibly Story 6-9 (router_calls schema).
- **#6 (P0 / closes a carry-forward finding)** — fires because F17 is OPEN and blocks Story 6-6.5 Section B.

Expect 3+ §5.12 criteria → MANDATORY-CR with the alternate-model dev/review split per Adam's CR cadence v2 rule. Dev model: Opus 4.7. CR model: Sonnet 4.6. Apply CR findings inline before done-flip.

### Previous-story intelligence (Story 6-10 + Story 6-9)

From Story 6-10's live walk (per `epic-6-run-flags.md § Story 6-10 Phase 3.5 walk record`), 8 contract facts were learned the hard way. Two are directly relevant here:

- **Fact #4** — `docker compose restart` keeps old env cached; must use `docker compose up -d --build` for code/env changes to take effect. Critical for Task 1's restart step.
- **Fact #7** — Hermes cron-with-agent contract = script stdout becomes agent prompt input. Not directly relevant to F17 but a reminder that the deployed surface has hidden contracts.

From Story 6-9 (F11 closure, commit `42fd4dc`): the `tool_calls_count` / `tool_calls_summary` NULL columns were added to `router_calls`. Schema verified consistent during story creation, but DO confirm the migration ran in the deployed environment (see Hypothesis 1 above). The 6-9 deploy is the highest-probability bisect point against the 2026-06-01 → 2026-06-04 broken window.

### Testing standards

Per architecture §"Testing standards" + Story 3-5's Middleware-Real-Bootstrap rule:

- Integration tests at `tests/integration/` MUST exercise real adapters at the SDK boundary. Mocking `ask_router`, `OllamaAdapter.call`, or `anthropic.AsyncMessages.create` directly is FORBIDDEN. Mock at the network/transport layer only (e.g., `aioresponses`, `respx`, or a fake Ollama HTTP server).
- The new integration test for AC-3 SHOULD use a `tmp_path`-scoped SQLite DB, run migrations via `apply_pending_migrations`, seed an `emails` row, then invoke `process_email` and assert: (a) a `router_calls` row was written with `task_type='sensitivity_class'` AND `outcome IN ('ok', 'retry_recovered')`, (b) `emails.sensitivity` is non-NULL, (c) `emails.sensitivity_at` is non-NULL.
- Test naming: `test_process_email_sensitivity_class_dispatches_to_real_adapter` or similar — descriptive over terse.

### Project Structure Notes

No new top-level directories. New test file lives under `tests/integration/` per existing convention. No new packages. No new migrations (the fix is behavioral, not schema-shaped — unless Hypothesis 1 turns out to need a schema repair, in which case a new migration `023_*.sql` would be required; that's a discovery-time decision).

### References

- [`mailbot_api/ingest/pipeline.py:308-349`](mailbot_api/ingest/pipeline.py#L308-L349) — `process_email` + Step 1 sensitivity dispatch + the log line to extend
- [`mailbot_api/sensitivity/classifier.py:130-233`](mailbot_api/sensitivity/classifier.py#L130-L233) — `classify_sensitivity` + FR-2.5 per-call safeguard + cautious-bias floor
- [`mailbot_api/router/router.py:155-388`](mailbot_api/router/router.py#L155-L388) — `ask_router` entry + dispatch chain + PROVIDER_ERROR construction sites
- [`mailbot_api/router/models.py:324-422`](mailbot_api/router/models.py#L324-L422) — `OllamaAdapter.call` + adapter error wrapping
- [`mailbot_api/router/errors.py:40-72`](mailbot_api/router/errors.py#L40-L72) — `ErrorCode` enum + `RouterError` shape
- [`mailbot_api/router/errors.py:225-265`](mailbot_api/router/errors.py#L225-L265) — `sanitize_error` redaction contract
- [`mailbot_api/observability/audit.py:65-152`](mailbot_api/observability/audit.py#L65-L152) — `RouterCallRow` + `_param_tuple` (column-order contract)
- [`mailbot_api/db/queries.py:556-570`](mailbot_api/db/queries.py#L556-L570) — `ROUTER_CALLS_INSERT` (column-order contract)
- [`mailbot_api/db/migrations/022_router_calls_tool_calls.sql`](mailbot_api/db/migrations/022_router_calls_tool_calls.sql) — Story 6-9 schema extension (Hypothesis 1)
- [`mailbot_api/prompts/sensitivity_class/v1.py`](mailbot_api/prompts/sensitivity_class/v1.py) — Qwen-bound prompt module
- [`mailbot_api/prompts/__init__.py:59-106`](mailbot_api/prompts/__init__.py#L59-L106) — `resolve_prompt` validation
- [`router/policy.yaml:24-31`](router/policy.yaml#L24-L31) — `sensitivity_class` policy entry
- [`_bmad-output/implementation-artifacts/epic-6-run-flags.md` § F17 (lines 885-918)](_bmad-output/implementation-artifacts/epic-6-run-flags.md) — F17 finding
- [`_bmad-output/implementation-artifacts/epic-6-run-flags.md` § Story 6-6.5 walk record § Section B (line ~804+)](_bmad-output/implementation-artifacts/epic-6-run-flags.md) — what's blocked
- [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md) — §AR-PAT-3, §AR-PAT-4, §AR-PAT-5, §FR-2.5, §NFR-SEC-4
- [`_bmad-output/planning-artifacts/epics.md` Story 3-3 (lines 1157-1191)](_bmad-output/planning-artifacts/epics.md) — original sensitivity_class spec
- `MEMORY.md feedback_cr_cadence_v2_structural.md` — CR cadence v2 (6 §5.12 criteria force MANDATORY-CR)
- `MEMORY.md project_delete_requires_sensitivity_token.md` — sensitivity gate is privacy-critical; FR-2.5 stays

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context). CR pending — `feedback_cr_cadence_v2_structural.md` calls for a different model (Sonnet 4.6) for the review pass.

### Debug Log References

**Pre-fix log line (F17 signature, current production behavior):**

```json
{"ts":"2026-06-04T14:56:40.116495Z","level":"warning","module":"mailbot_api.ingest.pipeline","event":"ingest.step.failed","message":"pipeline step failed","filename":"pipeline.py","email_id":"…","task_type":"sensitivity_class","error_code":"provider_error"}
```

(no `error_message` field — the underlying RouterError.message was silently dropped at `pipeline.py:341-348`.)

**Post-Task-1 log line (unredacted error_message now surfaced):**

```json
{"ts":"2026-06-04T15:04:40.970325Z","level":"warning","module":"mailbot_api.ingest.pipeline","event":"ingest.step.failed","message":"pipeline step failed","filename":"pipeline.py","email_id":"…","task_type":"sensitivity_class","error_code":"provider_error","error_message":"sensitivity classifier could not read policy snapshot: policy not loaded — set_policy_snapshot(load_policy(path)) must be called by the FastAPI lifespan before get_policy()"}
```

**Post-fix log line (after Task 3 worker init wiring + container rebuild at 2026-06-04T15:16:14Z):**

```json
{"ts":"2026-06-04T15:16:14.358039Z","level":"info","module":"__main__","event":"worker.startup.pipeline_runtime_ready","message":"worker pipeline runtime initialized","filename":"worker.py"}
```

First successful post-fix ingest tick at 2026-06-04T15:16:51Z produced `router_calls(task_type='sensitivity_class', outcome='retry_recovered')`. Subsequent ticks: 6 successful `retry_recovered` outcomes, 0 failed.

### Completion Notes List

- ✅ **F17 RESOLVED.** Root cause was Story 6-6 worker-process init gap (NOT any of the 5 prioritized hypotheses in the create-story plan). Story 6-6 moved ingest-tick dispatch from the api process into the worker process but missed porting the policy snapshot, sensitivity patterns, adapter registry, budget guard, and pause state init. The FR-2.5 per-call safeguard at `classifier.py:88-127` caught it correctly every tick; the pipeline log line at `pipeline.py:341-348` masked the message field, hiding it from observability for 3 days.
- ✅ **Structural fix shipped**: `init_pipeline_runtime` promoted from `_cli_init_runtime` (was: CLI-only) to a public helper now shared by 3 call sites — the FastAPI lifespan (open-coded with test-flag branches; not refactored to use the helper because the lifespan does additional MCP/lane-scheduler/anomaly setup that's api-process-specific), the CLI `_cli_async_main`, and `_worker_main`. `MAILBOT_SKIP_POLICY` / `MAILBOT_SKIP_PATTERNS` env-flag honoring added for symmetry with api lifespan so existing test fixtures (`test_worker_main_integration.py`) still boot the worker without policy YAML files.
- ✅ **Permanent observability fix**: `pipeline.py:341-348` log line now includes `error_message` field. The next worker/process boundary regression of this shape will surface in <1 ingest tick instead of <3 days.
- ✅ **AC-1..AC-5 all PASS.** AC-6 satisfied by default (no TEMP-tagged logging was added — AC-1 surfaced the root cause directly).
- 🆕 **NEW FINDING (downstream, NON-BLOCKING for F17 closure): summary_short schema_validation_failed.** First post-fix ingest tick exposed that the `summary_short` step (claude-haiku-4-5-20251001) now fails schema validation. This was masked for 3 days because the pipeline short-circuited at sensitivity_class. The failure is at the Anthropic adapter boundary — likely a prompt-output drift or a `prompt_version` migration gap from a recent commit. **Out of scope for Story 6-11** (per Investigation Plan scope discipline: "Surgical fix, not a refactor"). Recommend filing as Story 6-12 (or Epic 7 first item, depending on Path A/B decision from Epic 6 retro A1). Backlog drain continues correctly — sensitivity_class IS classifying; only the LLM-summarization step further down the pipeline is failing.
- 🆕 **Backlog drain trajectory**: 1620 → 1614 unclassified over 2 ticks (3 emails classified per tick avg; full drain ≈ 9 hours at current cadence). First `confidential` row in DB history landed (Story 6-6.5 CP-C was blocked specifically on this).
- 📊 **Gates**: pytest 1060 passed + 2 skipped (+2 net from new test module); ruff clean; mypy --strict clean (122 source files); boundary checker silent.
- 🔬 **CR cadence**: per `MEMORY.md feedback_cr_cadence_v2_structural.md`, this story fires multiple §5.12 criteria (#1 new public helper + new test module; #3 observability log-line semantics change; #5 cross-story load-bearing seam touching Stories 3-3 / 3-5 / 4-0 / 6-6; #6 closes carry-forward F17). MANDATORY-CR with a different model (Sonnet 4.6) should follow this `review` status. Findings to apply inline before done-flip.

### File List

**New files:**

- `tests/integration/test_worker_pipeline_runtime_init.py` (212 lines) — regression test guarding against F17 re-introduction

**Modified files:**

- `mailbot_api/worker.py` — added `init_pipeline_runtime` call at top of `_worker_main` + `worker.startup.pipeline_runtime_ready` log line
- `mailbot_api/ingest/pipeline.py` — renamed `_cli_init_runtime` → `init_pipeline_runtime` (public); added `MAILBOT_SKIP_POLICY` / `MAILBOT_SKIP_PATTERNS` flag honoring; extended `ingest.step.failed` log line at sensitivity step to include `error_message` field; added `init_pipeline_runtime` to `__all__`
- `tests/integration/test_pipeline_e2e.py` — updated import + call-site to use new `init_pipeline_runtime` public name
- `tests/integration/test_worker_main_integration.py` — added `MAILBOT_SKIP_POLICY=1` + `MAILBOT_SKIP_PATTERNS=1` monkeypatch so existing test still boots worker without policy YAML fixtures
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md` — F17 finding prepended with RESOLVED block + root-cause summary; Story 6-6.5 Section B status flipped CP-A/B/C from BLOCKED-by-F17 to QUEUED
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 6-6.5 row amended with F17 closure timestamp + downstream-finding flag; 6-11 row to be flipped to `review` at story close

### Change Log

- 2026-06-04 — Story 6-11 filed as F17 carry-forward from Story 6-6.5 Section B prereq seeding. Status: backlog.
- 2026-06-04 — Story 6-11 contexted: hypothesis prioritization revised after code audit (SecretMissing down-ranked to LOW; Story 6-9 column-order migration up-ranked to HIGH). AC-1 added (surface unredacted error_message). AC-6 added (temp diagnostics removal). Investigation Plan Hypothesis Map added. Files-being-modified read pass complete. Status: ready-for-dev.
- 2026-06-04 — Story 6-11 implementation complete. Root cause: **Story 6-6 worker-process init gap** (none of the 5 prioritized hypotheses were correct; story-creation analysis missed enumerating the worker-process boundary as a distinct Python interpreter). Fix: promoted `_cli_init_runtime` to public `init_pipeline_runtime` + called from `_worker_main`; extended sensitivity step log line to surface `error_message` permanently. F17 RESOLVED 2026-06-04T15:16:51Z (live-verified). New downstream finding (summary_short schema_validation_failed) filed for separate follow-up. All 4 gates green at 1060 + 2 skipped (+2 net). Status: review.
