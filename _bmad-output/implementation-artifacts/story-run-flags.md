# Story-Run Flags — `/autonomous-story-run` per-invocation log

This file collects flags raised by `autonomous-story-run` runs. One block per invocation.

## Story 1-10 — 2026-06-01

**Headline:** 4 sync-correctness patches shipped (ImmutableId Prefer header, changeKey-first extraction with @odata.etag fallback, @removed.reason capture, 410+syncStateNotFound full-resync recovery with debounced urgent notification). 7 code-review issues found and applied including 1 HIGH-severity production correctness bug.

**Dev model:** claude-opus-4-7 (inline execution, no sub-skill delegation)
**Review model:** claude-sonnet-4-6 (Agent tool subagent)

**Review rounds run:** 1. Issues found: 7. Issues applied: 7. Apply rate: 100% (≥70% threshold ✓).

**Aggregated [deferred:*] items:** none.

**Gate verdicts:**

- 2.3.5 (Pre-Review Self-Audit) — PASS (all 5 sections; §3 surfaced 7 self-caught issues with dispositions; §5 posture audit 11/11 with one §5.9 cited-figure correction applied)
- 2.4 (Code Review) — PASS (7 issues, all applied; biggest find: HIGH-severity nested-vs-flat error.code mismatch that would have silently broken AC-5 against real Graph)
- 2.4.4 (Dev Agent Record completeness) — PASS (model named, completion notes 1+ bullet per AC, File List populated, story-file Status=done)
- 2.4.5 (UI scope) — N/A (no graphical frontend per PORTING.md)
- 2.4.6 (File-List-vs-git) — PASS (all 9 File List entries `git ls-files` clean after staging migration 005)
- 2.4.7 (Middleware-Real-Bootstrap, MailBot reframing) — PASS (DB-real integration tests via real SQLite + `apply_pending_migrations`; httpx.MockTransport mocks the Graph network seam not the Router/queries)
- 2.4.8 (Verbose-row truncation) — PASS (sprint-status row collapsed to one-line headline; full narrative in `## Completion Notes` block in story file)

**Step 2.5 dev-env verification:** N/A — no `<dev-env-skill>` configured for MailBot. (Future evolution: a `/debug-mailbot-stack` skill that boots docker compose, hits `/health`, validates the worker is heartbeating to `worker_health`, would land here.)

**Pre-flight reconciliations performed (informational, not flags):**

- `epic-1: done` → `in-progress` (story 1-10 was backlog inside a done epic; this would have halted at Step 0.2)
- `1-10: backlog` → `ready-for-dev` → `review` → `done` (story file was authored but row not updated)

**Permission-prompt summary:** No permission log configured on this project. Count of mid-run prompts unknown. (One PowerShell command — `ls "C:/Users/Adam/.claude/plugins/cache/skill-creator/..."` — failed with a shell escape error and required manual recovery, but this was an earlier skill-creator-related issue, not a 1-10 dev-flow prompt.)

**Notable patterns surfaced for the next retro / process improvement:**

- The HIGH-severity code-review find (nested error.code) was a textbook case of the Middleware-Real-Bootstrap gate's value: unit tests passing on a synthetic fixture shape silently failed to validate the real Graph error envelope. The dev model's pre-review audit (§5.6 upstream-contract) cited the archived docs but did not cross-check the test fixture shape against the docs' actual error envelope examples. **Process suggestion:** §5.6 should require pasting one real-Graph error-body example (from the archived docs) alongside the test fixture for any error-path test.
- Sprint-status drift (epic-1 done + child story backlog) was caught at Step 0.2; the skill correctly halted and surfaced the right fix to the user. **No skill change needed.** Confirms the integrity gate's design.

## Story 1-10 Manual Verification — 2026-06-01

**Verdict:** PASS WITH FINDINGS

**Findings:**

- Checkpoints 1–7 (live Graph behavior: Prefer header on /me + delta, changeKey semantics, removed_reason capture, 410 + 404+syncStateNotFound recovery, debounce) all require real `OUTLOOK_*` env vars on a dev host. No such configuration available on the current host.
- Checkpoint 8 (no duplicate `graph_id` rows in live DB) vacuously passed — no live SQLite DB exists yet (./mailbot.db not found; only mypy caches present). Integration test `test_handles_duplicate_message_in_single_delta_page` is the meaningful evidence for AC-6 until the real worker runs.

**Disposition:** Story 1-10 stays `done`. The 7 deferred checkpoints fold into a single real-tenant smoke session that should also exercise Story 1-5's and Story 1-9's deferred smokes (both have identical "no `OUTLOOK_*` env vars on dev host" carry-overs). When that session runs, all three stories' Phase 3.5 checkpoints are walked together; any failures spawn follow-up bug-fix stories rather than reopening 1-10.

**Recommended carry-forward:** add a "real-tenant smoke for Stories 1-5/1-9/1-10" item to the epic-2 retrospective intake (or as a discrete story 1-11 if the smoke surfaces enough work). Do NOT block epic-1 closure on it — the pattern is consistent with how 1-9 was closed.

---

## Story 5-2 — 2026-06-02 13:15

**Headline:** MCP server (FastMCP 1.27.2) exposes 11 verbs (5 read + 6 write) under `/mcp` mounted on the uvicorn FastAPI app via per-lifespan Starlette `Mount`; verb-import isolation + FastMCP-dependency localization boundary rules added (Story 5-1 AC-8 deferred check now done). 714 tests, all 4 gates green.

**Dev model:** claude-opus-4-7 (1M context) — this autonomous-story-run session.
**Review model:** claude-sonnet-4-6 — Phase 2.4 subagent.

**Review rounds:** 1. Issues found: 7. Issues applied: 7. Apply rate: 100% (≥70% threshold ✓).

**Aggregated `[deferred:*]` items:** none.

**Gate verdicts:**

- 2.3.5 (Pre-Review Self-Audit) — PASS (all 5 sections + 11 Posture Audit sub-sections; §5.12 cadence MANDATORY-CR — 5 of 6 criteria fire; CR subagent dispatch non-skippable per Epic 4 retro action #1)
- 2.4 (Code Review) — PASS (7/7 findings applied; biggest find: HIGH session_id logging gap — 10 of 11 wrappers were emitting `session_id=null` in structured logs; fix added `ctx: Context[Any, Any, Any]` to remaining wrappers)
- 2.4.4 (Dev Agent Record completeness) — PASS (model named, completion notes ≥ 1 bullet per task, File List populated, story Status=review)
- 2.4.5 (UI scope) — N/A (no graphical frontend per PORTING.md; backend-only story)
- 2.4.6 (File-List-vs-git) — PASS (all 7 File List paths in `git status`; 4 new untracked + 3 modified; no orphans; no story-adjacent untracked outside the File List)
- 2.4.7 (Middleware-Real-Bootstrap, MailBot reframing) — PASS (new `POST /mcp/*` HTTP surface covered by `tests/integration/test_mcp_server.py` exercising full FastAPI lifespan + real verbs + real SQLite via in-memory MCP transport)
- 2.4.8 (Verbose-row truncation) — DEFERRED (story currently at `review`; truncation runs at the `review → done` flip after Phase 3.5 PASS)

**Step 2.5 dev-env verification:** PASS — full lifespan via `TestClient(app)` against tmp SQLite + real policy.yaml + real patterns.yaml; `/health` 200; `/mcp/mcp` is live, allocates session ID, returns 421 only because TestClient's `Host: testserver` trips FastMCP's localhost DNS-rebinding protection (expected; will not fire under Docker DNS in production).

**Permission-prompt summary:** No permission log configured. Zero permission prompts observed during the run.

**Notable patterns surfaced for the next retro / process improvement:**

- The HIGH session_id logging gap was caught BY the code-review subagent — exactly the pattern §5.12 MANDATORY-CR cadence is designed to surface. The dev pass's self-audit §3 listed 8 items but missed this one (the `None` placeholders looked like cosmetic boilerplate, not a spec violation). Confirms the value of dispatching CR for boundary-introducing + load-bearing-orchestrator stories regardless of dev confidence.
- The Pattern-A → per-lifespan mount pivot in `main.py` is a reusable lesson: FastMCP's `StreamableHTTPSessionManager` binds to the construction-time event loop. Any future module that uses an anyio-task-group-based session manager will need the same treatment. **Process suggestion:** if Story 5-4 (Hermes container config) or any subsequent story mounts a similar transport, reference this story's main.py pattern.
- Boundary checker's indirect-import bypass (CR-5: `from mailbot_api import verbs`) was a real gap that the dev pass missed in §4 ESCALATE. Sonnet 4.6 found it in seconds. **Process suggestion:** when adding a new boundary rule on a module path, always check BOTH `from X.Y import ...` and `from X import Y` shapes.

---

## Story 5-2 Manual Verification — 2026-06-02 13:20

**Verdict:** PASS

**Walker:** Claude (this autonomous-story-run session, on user request "Walk those points yourself").

**Checkpoints walked end-to-end against the live HTTP MCP transport (real uvicorn on :18000, real FastAPI lifespan, real SQLite tmp DB seeded with normal + confidential rows, real `streamablehttp_client` MCP client):**

1. **AC-1 — 11 verbs registered with correct names + constraint hints.** PASS. `await server.list_tools()` returned exactly the 11 expected names; forbidden set (ask_router / cost_breakdown / reset_degraded_mode / pause_router / resume_router / reset_hydration_count) overlap was empty. Constraint hints verified in descriptions: find_emails carries "100" + "Rule J"; hydrate_email carries "5" + "turn"; mint_sensitivity_token carries "10-min"; revert_action carries "Tier-1".
2. **AC-2/AC-3 — Tool schemas omit db_path / session_id / ctx.** PASS. Iterated all 11 tools' `inputSchema.properties`; zero leaks. Examples: `hydrate_email` exposes only `email_id`; `find_emails` exposes only `filter` + `limit`. FastMCP's Context-parameter suppression works as documented.
3. **AC-4 — Per-turn hydration cap + 30s reset over live MCP transport.** PASS. 5 successive `hydrate_email` calls succeeded; 6th returned `HYDRATE_RATE_LIMITED` as data (not protocol error); advancing the mcp_server-module clock 31s, the 7th call succeeded (counter reset). Server logs confirmed `mcp.tool.ok` + `mcp.tool.error_as_data` events firing with non-null session_id values (CR-1 HIGH fix verified live).
4. **AC-5 — /mcp reachable from live uvicorn FastAPI.** PASS. Booted uvicorn on `127.0.0.1:18000` against tmp DB + real `router/policy.yaml` + real `router/sensitivity_patterns.yaml`. Connected via real HTTP transport `streamablehttp_client('http://127.0.0.1:18000/mcp/mcp/')`. Listed 11 tools over the wire, received MCP session id `7eae02859f944526a44717b9b0ef4bb8`, and round-tripped `find_emails(sender_address="live@example.com")` returning the seeded `live-mid-1` row.
5. **AC-8 / Privacy — confidential gates over live MCP.** PASS. Seeded an email with `sensitivity="confidential"` and `body_preview="SECRET PAYLOAD do not leak"`. (a) `hydrate_email("conf-mid-1")` returned `ok=False`, `error.code="CONFIDENTIAL_HYDRATION_BLOCKED"`, `email=None`; full-response JSON scanned for `"SECRET PAYLOAD"` substring — **not present** (body bytes never crossed the wire). (b) `mint_sensitivity_token("conf-mid-1", "summary_short")` returned `ok=False`, `error.code="SENSITIVITY_BLOCKS_API"`, `token=None`. Both refusals are structured error-as-data per AR-PAT-4, not protocol errors.

**Disposition:** Story 5-2 flipped review → done. Verbose row in sprint-status.yaml truncated to one-line headline per Step 2.4.8; full narrative preserved in this flags-file block + story file Completion Notes.

---

## Story 6-6.5 — 2026-06-04 14:20 (path (a) verification-only walk)

**Headline:** Section A PASS (10/10 agent-side wiring checks green); Section B QUEUED for Adam (OUTLOOK_CLIENT_SECRET + OUTLOOK_USER_EMAIL gated per Epic 6 retro A3+A6).

**Trigger:** `/autonomous-story-run 6-6-5` with explicit path (a) verification-only walk disposition (Phase 0 surfaced disposition-story gate; Adam confirmed (a)).

**Dev model:** claude-opus-4-7 (1M context).
**Review model:** claude-sonnet-4-6 (dispatch pending — see below).
**Review rounds:** 1 round queued; not yet dispatched.

**Gate verdicts:**

- 2.3.5 (pre-review self-audit) — PENDING
- 2.4.4 (Dev Agent Record completeness) — PENDING
- 2.4.5 (UI-scope pre-flight) — N/A (no graphical frontend on MailBot)
- 2.4.6 (File-List-vs-git untracked check) — PENDING
- 2.4.7 (middleware-real-bootstrap) — N/A (no code changes; pure walk-record + doc updates)
- 2.4.8 (verbose-row truncation) — PENDING
- Step 2.5 (dev-env verification) — N/A (no code changes; stack already verified live during Section A)

**Aggregated [deferred:*] items:** none from this story; Story 4-0 deferred CPs (drainer e2e, real Graph write-back, 20-send/day cap live) close to ADAM-Section-B-CLOSED disposition pending Adam's Section B walk.

**Story-doc drift findings filed inline (NON-BLOCKING):**

- **F16-A (DOC-DRIFT)**: Story 6-6.5 Task 1 references `tests/integration/test_draft_reply_capstone*.py`; actual filename is `test_draft_reply_orchestrator.py`. 14/14 tests passed when running the correct filename.
- **F16-B (DOC-DRIFT)**: Story 6-6.5 Task 3 SQL references column `sensitivity_class`; actual column is `sensitivity` (also `sensitivity_at` for timestamp). Corrected query used inline; 1622 emails in DB, 4 classified (2 normal + 2 sensitive + 0 confidential).

Neither warrants a follow-up story. Corrected commands are recorded in `epic-6-run-flags.md § Story 6-6.5 walk record` so the next runner uses them.

**Permission-prompt summary:** No permission log configured on the target. Zero prompts observed during Section A.


## Story 6-6.5 — 2026-06-04 14:55 (Section B partial walk, post-prereq fulfillment)

**Trigger:** continuation of the same `/autonomous-story-run 6-6-5` session — Adam answered the Phase 3.5 manual-verification prompt with "I will now proceed to complying to Prerequisites before walking Section B" and asked the agent to walk through interactively.

**Outcome:** Section B PARTIAL — 2 prereqs captured + 1 prereq blocked by new finding F17 + CP-D agent-surrogate PASS + CP-A/B/C BLOCKED-by-F17.

**New flags:**

- **F17 (CRITICAL, BLOCKING-Section-B-CP-A/B/C)** — Ingest pipeline `sensitivity_class` step stuck on bare `error_code=provider_error` since 2026-06-01 21:02 UTC; 1618-email unclassified backlog. Router/Ollama/budget all healthy; bug exits before reaching `ask_router`. Most likely cause: SecretMissing per `mailbot_api/config.py:18` (a required env var read by the classifier path only). Filed as new **Story 6-11** in backlog with 5-task investigation plan. See `epic-6-run-flags.md § F17`.
- **F18 (INFO, NON-BLOCKING, story-doc drift)** — Story 6-6.5 Task 7 references failure_reason `BUDGET_CAP_HIT`; actual code constant is `daily_send_cap_exceeded` at `mailbot_api/actions/drainer.py:516`. Same shape as F16-A + F16-B. No code impact.

**CP-D agent-surrogate evidence (PASS):**

- 20 same-day `terminal_at=_iso(now)` send_reply rows with `budget_consumed=1` → `_send_cap_exceeded() = True` ✅
- 19 same-day rows → `_send_cap_exceeded() = False` ✅
- 25 yesterday-`terminal_at` rows → `_send_cap_exceeded() = False` ✅ (UTC midnight rollover)
- `DAILY_SEND_CAP=20`, send-family enum confirmed, failure path at `drainer.py:515-517` runs `_mark_failed(row, "daily_send_cap_exceeded")` BEFORE Graph dispatch.

**Final disposition:** Story 6-6.5 stays `ready-for-walk`. Section A PASS (locked). Section B verdict: PARTIAL-PASS (CP-D agent-surrogate) + BLOCKED-by-F17 (CP-A/B/C live walk). Re-walks once Story 6-11 closes.

**Permission-prompt summary:** No permission log configured on the target. Zero prompts observed during the partial walk.

## Story 6-13 — 2026-06-05

**Headline:** F22 closure shipped — `mint_grant` `pending_grant`→`pending` promotion now atomic via new `execute_insert_and_write` helper; 7 new unit tests (6 promotion + 1 atomicity rollback regression) + 2 integration tests + AC-4 symmetric-demotion audit (hypothesis CONFIRMED).

**Dev model:** claude-opus-4-7 (inline execution, no sub-skill delegation)
**Review model:** claude-sonnet-4-6 (Agent tool subagent)

**Review rounds run:** 1. Issues found: 6 (1 MED, 3 LOW, 2 INFO). Issues applied: 6. Apply rate: 100% (≥70% threshold ✓).

**Aggregated [deferred:*] items:** none.

**Gate verdicts:**

- 2.3.5 (Pre-Review Self-Audit) — PASS (all 5 sections; §3 surfaced 5 self-caught issues — 1 escalated to reviewer for second opinion; §5 posture audit 11/11 with one §5.9 minor-drift breakdown correction applied — Task 5 +6+2 not +5+2+1)
- 2.4 (Code Review) — PASS (6 issues, 6 applied; biggest find: CR-1 MED non-atomic INSERT+UPDATE seam between ACTION_GRANT_INSERT and PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE — closed via new `execute_insert_and_write` async helper batching both writes in a single BEGIN IMMEDIATE / COMMIT envelope + regression test asserting rollback symmetry)
- 2.4.4 (Dev Agent Record completeness) — PASS (model named: Dev claude-opus-4-7 + Reviewer claude-sonnet-4-6; completion notes 1+ bullet per task; File List 7 entries; story-file Status=done after gate 2.4.8 flip)
- 2.4.5 (UI-scope pre-flight) — N/A — project has no graphical frontend per PORTING.md; UI ACs N/A per Story 6-13 (backend-only seam, no user-visible surface).
- 2.4.6 (File-List-vs-git cross-check) — PASS (4 modified + 2 new files in story scope, all in File List; `git ls-files --error-unmatch` exits 0 for all File List entries post-staging)
- 2.4.7 (Middleware-Real-Bootstrap) — PASS (Router-real reframing for MailBot: `mint_grant` is a state-changing write on `action_grants` + `pending_actions`; integration test exercises real SQLite + real schema + real drainer + FakeGraphWriteAdapter at the Graph boundary — no `is_grant_valid` / `execute_write` mocking; satisfies MailBot's Router-as-integration-boundary contract)
- 2.4.8 (Verbose-row truncation) — PASS (sprint-status.yaml row replaced with 1-2-sentence headline + pointer; full Completion Notes live in story file)

**Step 2.5 dev-env verification:** PASS — all 4 quality gates green (ruff / mypy --strict 122 files / boundary / pytest 1079+2 skipped). No separate dev-env skill invocation needed — gates are the dev-env health check on this codebase.

**Permission-prompt summary:** No permission log configured. Zero prompts observed during the full run.

### Story 6-13 Manual Verification

**Verdict:** PASS (autonomous self-verification per user instruction "run the manual verification yourself").

**Checkpoints walked:** 7/7. All PASS.

- AC-1 (`mint_grant` invokes promotion + structured-log `pending_grant_promoted=N`): verified at `authorization.py:170-176` (call site) + `:184-194` (log site) + `:192` (log field).
- AC-2 (query filters by `action_type` only, not `email_id`): verified at `queries.py:804-807` — SQL `UPDATE pending_actions SET status = 'pending' WHERE status = 'pending_grant' AND action_type = ?` (single `?` placeholder, no email_id predicate).
- AC-3a (matching-type promotion unit test): `test_mint_grant_promotes_matching_pending_grant_row` PASSED.
- AC-3b (counter-test: different action_type does NOT promote): `test_mint_grant_does_not_promote_different_action_type` PASSED.
- AC-3c (full propose→drainer→mint→drain→applied lifecycle): both `test_full_lifecycle_pending_grant_promotion_on_mint_grant` + `test_full_lifecycle_mint_grant_does_not_disturb_unrelated_action_type` PASSED.
- AC-4 (symmetric-demotion audit paragraph): verified at story file lines 86-98 — hypothesis CONFIRMED, 3 drainer-code citations support the conclusion.
- AC-5 (MANDATORY-CR per §5.12): verified — `### Code Review Action Items (sonnet-4-6, 2026-06-05)` section has 6/6 CR findings marked `[x]` APPLIED (100% apply rate); `## Senior Developer Review (AI)` section populated.

**Findings:** none.

**Verification limitation noted:** automated self-verification confirms code-and-test correctness. It does NOT substitute for live exercise of `mint_grant` against a real running MailBot instance (which would require Outlook OAuth + a real Tier-2/3 propose event arriving via the Graph delta sync). The cross-store contract (`action_grants` INSERT triggers `pending_actions` UPDATE atomically) is proven end-to-end via the integration test against real SQLite + the real drainer + FakeGraphWriteAdapter at the Graph boundary, satisfying Step 2.4.7's MailBot reframing.

