---
baseline_commit: 7864de4
---

# Story 10.5.3: Never-wired capabilities — draft pipeline, enrichment, digest intro, thread_id

Status: done

## Story

As Adam,
I want the shipped-but-dead capabilities either wired to a real production trigger or their non-wiring honestly re-documented — starting with the flagship Opus draft pipeline getting a live chat call site,
So that "MailBot drafts replies" stops being an L2-green illusion and becomes a thing a user can actually do from chat, and the charter stops promising capabilities that never fire.

## Cluster & Findings

**Cluster C — must-fix (charter credibility).** Epic 10's walk (retro §5.3) found a "never-wired" capability class that shipped across three epics with L2-green tests but zero production call sites. Findings:

- **F-10-5-11 HIGH** — Opus draft pipeline has **0 chat call sites** (the flagship capability; largest gap). `handle_draft_reply` (`mailbot_api/chat/orchestrator.py`) is fully built + tested but is not registered as a chat-reachable tool, so `draft_reply` produces zero `router_calls` chat rows ever.
- **F-10-4-3 HIGH** — `get_thread` unreachable from chat because `EmailProjection` carries no `thread_id`. The verb itself works given a `thread_id`; the model has no way to discover one from `find_emails` list rows.
- **F-10-4-4 HIGH** — enrichment never runs: 0/727 senders, 0/1753 threads. `enrich_sender` / `enrich_thread` (`mailbot_api/ingest/sender_enrichment.py`) have no call site on the ingest path.
- **F-10-4-6 HIGH** — `daily_digest_intro` zero rows all-time. The persona-voiced Qwen intro call is documented as Hermes-side (`compose_digest.py` docstring), but never fires.

See `10-4-walk-evidence.md` + `10-5-walk-evidence.md`.

## Run-Mode Binding

**HYBRID (2026-07-10) — dev-codeable wiring is autonomous; AC-1's live draft walk is Adam-hands-on.**

Tasks 1-6 (wiring + tests + MANDATORY-CR) ARE `/autonomous-story-run` / `dev-story` compatible. **Task 7 — the live draft walk (small real Opus spend, Console-sourced per `feedback_anthropic_spend_source_of_truth.md`) — is Adam-hands-on.** Dev agents HALT at Task 7, flip to `review`, and log to `epic-10-5-run-flags.md`. This follows the 10-5-1 / 10-5-2 precedent (dev pass autonomous, live-walk HALT to Adam at Phase 3.5).

AC-1's *code-reachability* (draft tool registered + `handle_draft_reply` invoked from `dispatch_tool_call` → real `router_calls` chat row on a fake/local adapter in an integration test) IS provable autonomously and is the dev-pass deliverable. The *real-Opus* confirmation is the Adam-hands-on walk clause.

## Acceptance Criteria

**AC-1 (F-10-5-11 — Opus draft pipeline has 0 chat call sites):**
**Given** the draft orchestrator (`handle_draft_reply`) is built but not chat-reachable
**When** a user asks the bot to draft a reply from chat
**Then** the draft orchestrator is reachable from the chat path — a `draft_reply` tool is registered on the chat surface (`_build_tools` / MCP tool registry) and dispatched via `dispatch_tool_call`, so `draft_reply` produces real `router_calls` chat rows — proven at code-L3 by an integration test (real DB + registered tool + fake/local adapter routing to a real `router_calls` insert), and verified by a live draft walk (small real Opus spend, recorded against pre-flight estimate, Console-sourced) at Phase 3.5 / Task 7 (Adam-hands-on)

**AC-2 (F-10-4-3 — get_thread unreachable; EmailProjection has no thread_id):**
**Given** `EmailProjection` (the agent-visible list row from `find_emails` / `get_thread`) has no `thread_id`
**When** the projection is built
**Then** `thread_id` is present on `EmailProjection` so `get_thread` is reachable from chat (the model can read a `thread_id` off a `find_emails` row and pass it to `get_thread`) — implemented by adding `thread_id` to `EMAIL_PROJECTION_COLUMNS` + the `EmailProjection` schema + `row_to_projection`; **OR**, if the projection change is judged out of must-fix scope at dev time, the README stops claiming `get_thread` works and the limitation is documented honestly. The chosen path is recorded either way.

**AC-3 (F-10-4-4 enrichment 0/727,0/1753 + F-10-4-6 daily_digest_intro 0 rows):**
**Given** enrichment never runs and `daily_digest_intro` has zero rows all-time
**When** the fix lands
**Then** each capability is wired to its production trigger (enrichment runs on the ingest path; digest intro fires on the digest cron) **OR** its non-wiring is honestly re-documented as a limitation — no capability remains silently shipped-dead with the README implying it works. For any capability whose trigger is Hermes-side (outside `mailbot_api`), the disposition is honest re-documentation + a filed follow-up, NOT a fabricated mailbot_api fix; the boundary is recorded.

**AC-4 (CR cadence):**
**Given** this story touches the chat-orchestration + projection seam
**When** CR cadence is evaluated per the 6 criteria
**Then** criterion 6 (load-bearing) fires → **MANDATORY-CR per §5.12**, full scope, reviewer model ≠ dev model

## Tasks / Subtasks

- [x] **Task 1 — Register `draft_reply` as a chat-reachable tool (AC-1).** DONE. RED (`tests/integration/test_draft_reply_chat_reachable.py`, 2 tests): tool absent → "Unknown tool: draft_reply". GREEN: registered `draft_reply` in `_build_wrappers` + handlers dict + `_TOOL_DESCRIPTIONS`; bumped `_EXPECTED_TOOL_COUNT` 25→26; imported `handle_draft_reply`/`DraftReplyRequest`. Wrapper is thin (maps chat kwargs → `DraftReplyRequest` → serialized `DraftReplyOutcome` dict; `router_error` dumped via Pydantic). The RED test proves a REAL `router_calls` row for `task_type='draft_reply'` lands with a non-qwen Opus model via a registered fake adapter (NO monkeypatched ask_router — kills the L2-green illusion). Sensitivity gate + confirmation_token contract preserved (orchestrator owns it). Pause interaction: `draft_reply` reaches Opus only via `ask_router`, which reads the authoritative pause row (Story 10.5.1) → a paused router refuses the dispatch; no `_tool_on_pause_allowlist` entry needed (allowlist is `dispatch_tool_call`-scoped, a different surface). Updated 4 count/coverage assertions (test_mcp_server ×2, test_mcp_server_extended_tools, SKILL.md frontmatter 25→26 + new `### draft_reply` heading). 37 tests green.

- [x] **Task 2 — Add `thread_id` to `EmailProjection` (AC-2).** DONE — **implement path chosen** (not re-doc; the change was small, self-contained, and `emails.thread_id` already exists). RED (`tests/integration/test_projection_thread_id_reachable.py`, 2 tests): `EmailProjection` had no `thread_id` → AttributeError. GREEN: appended `thread_id` LAST to `EMAIL_PROJECTION_COLUMNS` (`db/queries.py` — single constant feeds both `FIND_EMAILS_SELECT_BASE` and `GET_THREAD_PROJECTION_SELECT`, so both projection SELECTs stay byte-parallel); added the field to `EmailProjection` (`verbs/schemas.py`, default None); mapped `row[10]` in `row_to_projection` (`verbs/find_emails.py`). Round-trip proven: a `find_emails` row's `thread_id` feeds `get_thread` → thread projections returned. No regressions (140 verb+MCP tests green; default-None keeps existing `EmailProjection(...)` construction sites valid).

- [x] **Task 3 — Wire enrichment to the ingest path (AC-3, F-10-4-4).** DONE — **wire path chosen** (enrichment is Qwen-only per Rule F.1 = free, and cached-forever per Rule A = one-time per sender/thread → per-email firing is cost-safe; the second email from a sender/thread short-circuits on cache). RED (`tests/integration/test_pipeline_enrichment_wired.py`, 2 tests): sender_reputation_summary NULL after `process_email` → enrichment never ran. GREEN: added `_run_enrichment_step` as a trailing (post-embedding, pre-`result.ok=True`) BEST-EFFORT step in `process_email` — reads the email's `sender_id`+`thread_id` (new `EMAIL_SENDER_THREAD_SELECT`), fires `enrich_sender` + (if thread_id present) `enrich_thread`, and swallows every failure (NULL thread_id, single-message thread, confidential-only sender, Router refusal, or missing adapter) with a log line — enrichment is NOT a pipeline correctness gate, so `result.ok` is unaffected. Verified: existing pipeline e2e tests (which register NO enrichment adapter) stay green because the missing-adapter crash is swallowed (23 pipeline/enrichment/backpressure tests green). Non-wiring re-doc NOT needed — enrichment now runs.

- [x] **Task 4 — `daily_digest_intro` disposition (AC-3, F-10-4-6).** DONE — **honest re-documentation** (boundary-honest, NO fabricated mailbot_api fix). Confirmed the intro's ONLY call site is the Hermes cron-with-agent step: `hermes-config/scripts/digest_prepare.py:12` documents it, but the script only calls `compose_digest` (deliberately LLM-free per Rule J/A) + writes the payload; the agent step that would issue `ask_router(daily_digest_intro)` never fires → zero rows all-time. There is NO mailbot_api call site to add (fabricating one violates the compose_digest-is-LLM-free contract). Verified zero `daily_digest_intro`/`DailyDigestIntro` call sites in `mailbot_api/` outside the prompt module. Disposition: README limitations bullet (line 382) re-documented honestly (intro is Hermes-runtime-issued); Hermes-side follow-up filed in `epic-10-5-run-flags.md` § Story 10-5-3 (same class as F-10-5-2-W2). Boundary recorded.

- [x] **Task 5 — Dev Agent Record + gates.** DONE. Dev Agent Record filled below. Gates: ruff clean (2 auto-fixed import-sort in new test files); mypy --strict clean (131 files); boundaries clean (via ruff — new SQL in queries.py, no raw SQL outside it); pytest full suite (see Completion Notes for count). Net test delta: +6 (3 new test files: draft_reply chat-reachable ×2, thread_id projection ×2, enrichment-wired ×2).

- [x] **Task 6 — MANDATORY-CR (AC-4).** DONE. Reviewer sonnet-5 ≠ dev opus-4-8, 1 round. 14 adversarial findings + an independent source-verification pass (confirmed sensitivity-gate/pause/token/projection-mapping/crash-handling all clean, 0 bugs). Triage: 3 APPLIED (added confidential-refused + sensitive-no-token tests through the NEW MCP wrapper — closes the "privacy claim tested only at orchestrator level not new call site" gap; added enrichment cache-short-circuit test proving the cost-safety claim; refactored the two duplicated sender/thread enrichment blocks into one `_best_effort` runner). Rest dispositioned in Review Findings below. Gates re-green post-fix: ruff/mypy-strict(131)/boundaries clean; +9 net tests now (draft_reply 4, thread_id 2, enrichment 3).

## Review Findings — CR2026-07-10 (sonnet-5 ≠ opus-4-8)

Independent source-verification agent confirmed (0 bugs): sensitivity gate refuses confidential before any ask_router call at the new wrapper; pause gate covered via ask_router's authoritative pause row (draft_reply not in `_PAUSE_ALLOWED_TASK_TYPES`); confirmation-token single-use enforcement inherited unchanged; EMAIL_PROJECTION_COLUMNS positional mapping clean (thread_id row[10], both SELECTs parallel, other construction sites use kwargs); wrapper `except/log/raise` only catches genuine crashes (orchestrator models all expected states as returns).

**APPLIED (3):**
- CR-1 (test gap — sensitivity refusal at new call site): FIX NOW — added `test_draft_reply_confidential_refused_through_wrapper_no_router_call` (asserts 0 router_calls rows) + `test_draft_reply_sensitive_without_token_needs_confirmation` (None-default token path, not the "" sentinel). Privacy invariant now tested at the NEW surface, not only inherited.
- CR-2 (enrichment cost-safety asserted-not-tested): FIX NOW — added `test_enrichment_short_circuits_on_second_process_email` (2× process_email → sender-enrichment dispatched exactly once; second run cache-hits).
- CR-3 (enrichment try/except duplication): FIX NOW — collapsed both branches into one `_best_effort(kind, target_id, coro)` runner; can't drift.

**REJECTED / ACCEPT-WITH-RATIONALE:**
- draft_reply idempotency/rate-limit: router lane + rate-limiter + budget guard already apply to `ask_router("draft_reply")`; no other write-tool has per-tool dedup. Out of scope.
- tone_signals_blob prompt-injection: orchestrator docstring pins caller-side `redact()`; tone_blob is pre-existing orchestrator contract, unchanged by this story. Not a new vector.
- row[10] IndexError / column drift: the SELECT column list IS the tuple shape (sqlite guarantees arity); verification agent confirmed no drift. Reject.
- magic-number 26 across 4 files: pre-existing project pattern (every tool story touches these count sites); single-source-of-truth refactor is a separate cleanup, out of scope.
- crash stack-trace leak: verification agent confirmed the wrapper matches all sibling wrappers' identical `except/log/raise`; MCP framework translates. Consistent, not a regression.
- caller_origin validation / BLE001 breadth / EMAIL_SENDER_THREAD_SELECT reuse / README clarity nit: minor; documented, no change.

**DEFERRED (1):**
- CR-D1 (no paused-draft integration regression test): the pause gate on draft_reply is verified by source-reading + covered indirectly by `ask_router`'s own pause tests + `test_dispatch_tool_call_pause_allowlist.py`. A dedicated paused-`draft_reply`-refusal integration test is a nice-to-have but needs the pause-state harness wired into this test module; deferred (recorded in deferred-work rationale here, not `deferred-work.md`, as it's a test-coverage nicety not a shipped-behavior gap). If a future refactor changes `dispatch_tool_call` allowlist scoping, the existing ask_router pause tests still catch the class.

- [ ] **Task 7 — Live draft walk (Adam-hands-on, HALT).** Small real Opus spend. Ask the bot to draft a reply from chat; confirm `draft_reply` produces a real `router_calls` chat row with a non-qwen model; record spend against pre-flight estimate, Console-sourced per `feedback_anthropic_spend_source_of_truth.md`. Dev agents HALT here → flip to `review` → log to `epic-10-5-run-flags.md`.

## Dev Notes

### Technical requirements

- Python 3.12, async SQLite (aiosqlite) via `mailbot_api/db/connection.py` (`fetchone`/`fetchall`/`execute_write`).
- Router surface: `ask_router` (schema-validated task dispatch) + `dispatch_tool_call` (OpenAI-shape tool-call dispatcher, `router/router.py:1666`). The chat model reaches verbs through tools registered in the MCP tool registry (`mcp_server.py:854-888`) and described in `_TOOL_DESCRIPTIONS` (`:896`).
- `draft_reply` is Opus-bound per FR-4.4 / policy.yaml. The orchestrator (`chat/orchestrator.py`) already dispatches `ask_router(task_type="draft_reply", ...)`, which is why wiring it produces real `router_calls` rows once the tool is reachable.

### Architecture compliance / fix loci (verified against source at authoring)

- **AC-1 locus:** the draft orchestrator `handle_draft_reply` at `mailbot_api/chat/orchestrator.py:142` is fully built (sensitivity gate + tone + draft + accept_draft → propose SEND_REPLY). The gap is purely that no tool named `draft_reply` exists in the registry, so the chat model can never emit that tool call. Register it + map args. The 12 files that reference `orchestrator`/`handle_draft_reply` are module-internal/tests, NOT chat call sites — confirming F-10-5-11.
- **AC-2 locus:** `EMAIL_PROJECTION_COLUMNS` (`db/queries.py:992`) is the single shared column list for `FIND_EMAILS_SELECT_BASE` (:1003) + `GET_THREAD_PROJECTION_SELECT` (:1022). `EmailProjection` (`verbs/schemas.py:52`) lacks `thread_id`; `row_to_projection` (`verbs/find_emails.py`) maps positionally. `emails.thread_id` column exists (hydrate `HYDRATE_EMAIL_SELECT` selects it, row[19]). Adding `thread_id` at the end of the column list + schema + mapper is minimal and keeps the two SELECTs parallel.
- **AC-3 enrichment locus:** `enrich_sender` / `enrich_thread` live in `mailbot_api/ingest/sender_enrichment.py` with Rule A caching + cross-email sensitivity-aware filtering, but have NO call site in `ingest/pipeline.py`. Trigger-wiring vs re-doc is a dev-time judgment on cost/backpressure safety.
- **AC-3 digest locus:** `daily_digest_intro` prompt module (`prompts/daily_digest_intro/v1.py`) is consumed Hermes-side per `compose_digest.py:5` ("Hermes's cron-with-agent job... makes ONE Qwen call for a persona-voiced intro"). Zero rows all-time (F-10-4-6) most likely means the Hermes-side cron intro call never fires — a Hermes-runtime wiring issue OUTSIDE `mailbot_api`. Honest re-documentation + a filed Hermes-side follow-up is the boundary-honest disposition (mirrors 10-5-2's AC-2 skill-file boundary-honesty).

### Testing requirements

- pytest; live-marked tests auto-deselected via `addopts`. Baseline: **1781 collected** (3 deselected). Aim for net-positive coverage on the two code-side ACs (AC-1 tool registration + `router_calls` chat-row assertion; AC-2 `thread_id` round-trip).
- AC-1 code-L3: prove `draft_reply` produces a `router_calls` row through the tool path using a real DB + fake/local adapter — do NOT mock `ask_router` (that would reproduce the L2-green illusion this story exists to kill). This is the Step 2.4.7 Router-real-integration requirement.

### References

- `epics.md` § "Story 10.5.3" (lines ~4139-4163) — AC source of truth.
- `sprint-status.yaml` 10-5-3 row — Cluster C findings + finalization.
- `10-4-walk-evidence.md` / `10-5-walk-evidence.md` — F-10-4-3/4/6 + F-10-5-11 evidence.
- `epic-10-retro-2026-07-07.md` §5.3 — never-wired capability class.
- 10-5-1 / 10-5-2 stories — HYBRID run-mode precedent (dev autonomous, live-walk HALT).
- `feedback_anthropic_spend_source_of_truth.md` — spend truth from Console, never local placeholders.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev pass, autonomous-story-run). Review model: claude-sonnet-5 (MANDATORY-CR, Task 6).

### Debug Log References

- AC-1 fix locus was NOT the orchestrator (already complete) but the tool registry: the chat model reaches verbs only through MCP-registered tools, so registering `draft_reply` is the mailbot_api-side chat call site (Hermes discovers via MCP → offers as OpenAI tools). Confirmed `dispatch_tool_call`'s `tools` come from `request.tools` (`main.py:772`) which Hermes builds from MCP discovery.
- AC-1 test deliberately does NOT monkeypatch `ask_router` — it registers a fake Opus adapter under `claude-opus-4-7` (draft_reply's policy model) so a REAL `router_calls` row lands. Monkeypatching ask_router is the exact L2-green illusion (per existing `test_draft_reply_orchestrator.py`) this story exists to kill.
- AC-3 enrichment: `enrich_sender` keys on `emails.sender_id` (NOT `from_address`); pipeline reads both `sender_id`+`thread_id` via new `EMAIL_SENDER_THREAD_SELECT`. Best-effort by construction — the missing-adapter crash is swallowed, which is why the 23 existing pipeline/enrichment/backpressure tests (no enrichment adapter registered) stay green.
- AC-3 digest (F-10-4-6): boundary-honest. The `daily_digest_intro` intro is issued by the Hermes cron-agent step (`digest_prepare.py:12` docstring), not mailbot_api; `compose_digest` is deliberately LLM-free. Zero mailbot_api call sites → honest re-doc + Hermes-side follow-up, not a fabricated fix.

### Completion Notes List

- **AC-1 (F-10-5-11)** — Opus draft pipeline now reachable from chat. Registered `draft_reply` as MCP tool #26 (`mcp_server.py`: import + `_build_wrappers` wrapper + handlers dict + `_TOOL_DESCRIPTIONS` + `_EXPECTED_TOOL_COUNT` 25→26). The wrapper is thin — maps chat kwargs → `DraftReplyRequest` → serialized `DraftReplyOutcome` dict. Proven at code-L3: a real `router_calls` row for `task_type='draft_reply'` with a non-qwen Opus model via a registered fake adapter (NOT monkeypatched ask_router). Sensitivity gate + confirmation_token contract preserved. Live real-Opus confirmation deferred to Task 7 (Adam-hands-on).
- **AC-2 (F-10-4-3)** — `get_thread` now reachable from chat (implement path chosen). Added `thread_id` to `EMAIL_PROJECTION_COLUMNS` (shared by find_emails + get_thread SELECTs), `EmailProjection` (default None), and `row_to_projection` (row[10]). `find_emails` rows carry the thread_id the model passes to `get_thread`; round-trip proven.
- **AC-3 enrichment (F-10-4-4)** — wired to ingest (wire path chosen; Qwen-free + cached = cost-safe). `_run_enrichment_step` fires `enrich_sender`+`enrich_thread` as a best-effort trailing step in `process_email`. Non-fatal by construction. Historical 727-sender/1753-thread backfill fills lazily on each sender/thread's next email.
- **AC-3 digest (F-10-4-6)** — boundary-honest re-documentation (Hermes-side gap, not a mailbot_api fix). README limitations updated; Hermes follow-up filed in `epic-10-5-run-flags.md`.
- **AC-4** — MANDATORY-CR, Task 6 (sonnet-5 ≠ opus-4-8).
- **Gates (post-CR):** ruff clean, mypy --strict clean (131 files), boundaries clean, pytest **1788 passed / 2 skipped / 3 deselected** (+9 net vs 1779 baseline: draft_reply 4, thread_id 2, enrichment 3). No regressions.
- **MANDATORY-CR (Task 6):** sonnet-5 ≠ opus-4-8, 1 round, 3 findings applied (2 test-coverage additions at the new call site + 1 duplication refactor), rest rejected/deferred with rationale. See Review Findings.
- **Status: review (NOT done).** HYBRID run-mode — dev + CR + gates autonomous-complete; AC-1's live-Opus draft walk (Task 7) is Adam-hands-on and AC verdicts are Adam-signed at Phase 3.5, per the 10-5-1/10-5-2 precedent. Done-flip waits on Adam.
- **Nothing committed.** Staged only.

### File List

Source (mailbot_api):
- `mailbot_api/mcp_server.py` — registered `draft_reply` tool (import, wrapper, handlers dict, description, count 25→26).
- `mailbot_api/db/queries.py` — appended `thread_id` to `EMAIL_PROJECTION_COLUMNS`; added `EMAIL_SENDER_THREAD_SELECT`.
- `mailbot_api/verbs/schemas.py` — added `thread_id` field to `EmailProjection`.
- `mailbot_api/verbs/find_emails.py` — mapped `thread_id` (row[10]) in `row_to_projection`.
- `mailbot_api/ingest/pipeline.py` — added `_run_enrichment_step` (best-effort trailing enrichment) + import.

Tests (new):
- `tests/integration/test_draft_reply_chat_reachable.py` — AC-1 (tool registered + real router_calls row).
- `tests/integration/test_projection_thread_id_reachable.py` — AC-2 (thread_id round-trip find_emails→get_thread).
- `tests/integration/test_pipeline_enrichment_wired.py` — AC-3 enrichment (fires on ingest + best-effort).

Tests (count-assertion updates for the +1 tool):
- `tests/integration/test_mcp_server.py` — 25→26 (2 assertions + expected-name set).
- `tests/integration/test_mcp_server_extended_tools.py` — 25→26.
- `tests/integration/test_spend_chart_command.py` — 25→26.

Docs:
- `hermes-config/skills/mailbot/SKILL.md` — new `### draft_reply` heading + frontmatter count 25→26.
- `README.md` — limitations updated honestly (AC-2/AC-3 fixes; F-10-4-6 Hermes-side re-doc; F-10-5-11 draft-wired).
- `_bmad-output/implementation-artifacts/epic-10-5-run-flags.md` — Story 10-5-3 section + F-10-4-6 Hermes follow-up.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 10-5-3 row flip (backlog→ready-for-dev→…).

### Change Log

- 2026-07-10 — Story 10.5.3 dev pass: wired the flagship Opus draft pipeline to chat (`draft_reply` MCP tool, F-10-5-11), made `get_thread` reachable via `thread_id` on `EmailProjection` (F-10-4-3), wired sender/thread enrichment to the ingest path (F-10-4-4), and boundary-honestly re-documented the Hermes-side `daily_digest_intro` gap (F-10-4-6). +6 net tests; all gates green.
