---
baseline_commit: 1a7dbf569d75017cc72518aed3736da57c09fd1f
---

# Story 10.6: Fault-injection walks — all 17 error-table rows

Status: done

<!--
Walk story, Epic 10 README-as-charter UAT. NOT an implementation story: it produces fault-
injection walk evidence (per-row induce → assert code → apply documented fix → assert
recovery) + same-commit README error-table corrections per doc-drift rule (a) where a
documented fix fails, and defect FILINGS per N.5 — not code. Any injection harness scaffolding
is test scaffolding under scratch/, never production code (AC-4).

RUN-MODE DECISION RECORD (this session, 2026-07-06): no RUN-MODE BINDING existed on 10-6.
Phase 0.4 blocker scan surfaced (1) run-mode and (2) fault-injection risk envelope. Adam chose
**PURE AUTONOMOUS**: the orchestrator (dev model) induces every fault server-side and asserts
codes via `mailbot status` / logs / DB / read-only Discord REST; rows whose Discord surfacing
is not re-observed are honesty-tagged with the 10-4/10-5 evidence they lean on. Adam
authorized the FULL risk envelope: (a) pause/degraded/rate/loop trips, (b) container
stop/start, (c) simulated rows via rw DB writes — every one honesty-tagged **simulated** per
D3, baseline restored after, (d) real mailbox micro-mutations via the sacrificial
MailBot-UAT-10-1 folder + one low-value email, mailbox left as found.

D3 HONESTY CONTRACT (hard): every row verdict carries an **induced vs simulated** tag.
"Induced" = the real fault condition genuinely occurred (e.g., router actually paused, loop
detector actually tripped by 11 real dispatches). "Simulated" = the condition was staged
harness-assisted (e.g., synthetic router_calls cost rows to cross the $30 cap, oauth
consecutive_failures set by DB write). NO simulated row may be recorded as induced. A row that
can be neither induced nor defensibly simulated gets EXCLUDED-with-reason — never a fabricated
verdict.

CHARTER COUNT RECONCILIATION (honest, frozen pre-walk): the README common-errors table has
**16 data rows** (README:293-308) and has had 16 since the 2026-07-04 rewrite (verified via
git show 5c634a7/4a61545/HEAD — 18 pipe-lines = header + separator + 16 rows). The epic
charter says "17". Row R15 (README:307) carries THREE codes (state_drift_etag /
target_deleted / state_drift_noop) and R1 (README:293) carries two; walked as sub-cases the
protocol covers ≥19 distinct code assertions across 16 rows. The 16-vs-17 discrepancy is
recorded as an INFO finding feeding 10-7's table — scope is "ALL rows of the table as it
exists" per D3's no-cherry-picking intent.

Scope fence (N.5 policy): findings are FILED with evidence, never fixed here. The ONLY
non-evidence file this story edits is README.md (doc-drift rule (a) — an explicit AC: rows
whose documented fix does NOT work get a same-commit README correction). Any code/config/
prompt change escalates CR per §5.12.

KNOWN-BROKEN FIX SURFACE (from FILED findings, frozen pre-walk): F-10-5-1 — the literal slash
forms named in the table's Fix column (`/pause`, `/resume`, `/confirm`, `/budget reset`) are
unreachable from Discord (Hermes owns the `/` prefix). Per doc-drift rule (b) command names
are hard-assert: a Fix cell whose literal command cannot be executed as documented is a FAIL
on the fix step (corroborating F-10-5-1, not re-filing it), with the chat-equivalent/CLI
fallback recorded as the honest working fix + a same-commit README correction.
-->

## Story

As Adam,
I want each of the documented common-error rows induced (or honestly-tagged simulated) against the live local stack, asserting that the documented stable error code surfaces in Discord/status, that the documented fix works, and that the system recovers,
So that the error table stops being aspirational documentation and becomes a verified troubleshooting contract.

## Acceptance Criteria

**AC-1 — Per-row fault-injection protocol**
**Given** the README common-errors table (16 rows as it exists; charter's "17" reconciled honestly)
**When** each fault-injection case fires
**Then** the per-row protocol is: induce the condition → assert the documented stable error code surfaces in Discord and/or `mailbot status` → apply the documented fix → assert recovery
**And** error codes are hard-assert per doc-drift rule (b); surrounding prose is soft-assert

**AC-2 — D3 honesty tagging**
**Given** D3's honesty requirement
**When** any of the ~4 expensive rows (e.g., OAuth expiry mid-batch) is exercised harness-assisted rather than genuinely induced
**Then** the walk evidence for that row is explicitly honesty-tagged **induced-vs-simulated** — no simulated row may be recorded as induced

**AC-3 — Complete verdict table + N.5 filings + doc-drift**
**Given** the per-row outcomes
**When** the story closes
**Then** all rows carry a named PASS / FAIL / EXCLUDED-with-reason verdict in `10-6-walk-evidence.md`, feeding Story 10.7's table, and any row whose documented fix does NOT work produces a FILED defect per N.5 policy (plus a same-commit README correction per doc-drift rule (a))

**AC-4 — CR cadence**
**Given** this is a walk story (the injection harness, if any, is test scaffolding, not production code)
**When** CR cadence is evaluated per the 6 criteria
**Then** zero criteria fire → CR skipped per cadence binding; escalate per §5.12 if any production code is touched

### AC interpretation pins (code-reality; read before executing)

- **The 16 rows, frozen as cases R1–R16 (README:293-308):** R1 sensitive-no-token (`sensitivity_blocks_api`/`needs_sensitivity_confirmation`), R2 confidential (`sensitivity_blocks_api`), R3 unclassified (`sensitivity_not_classified`), R4 confidential body-read (`CONFIDENTIAL_HYDRATION_BLOCKED`), R5 awaiting grant (status `pending_grant`), R6 per-call refusal (`per_call_threshold_exceeded`), R7 monthly cap (`monthly_budget_exceeded` → `degraded_mode_blocked`), R8 daily soft warn (`budget.daily.soft_warn`), R9 rate limit (`rate_limited`), R10 loop kill-switch (`loop_detected`), R11 paused (`PAUSED` state), R12 OAuth refresh failing (`oauth_refresh_failing`), R13 schema fail (`schema_validation_failed`), R14 send cap (`daily_send_cap_exceeded`), R15 mailbox drift (`state_drift_etag`/`target_deleted`/`state_drift_noop` — 3 sub-cases), R16 unknown action (`INVALID_ACTION_TYPE`).
- **Assertion surface per AC-1 is "Discord and/or `mailbot status`"** — the "and/or" is load-bearing under the pure-autonomous run mode. Primary assertion = the layer where the code contractually surfaces (`mailbot status` ERRORS/ROUTER/OAUTH rows, structured logs, router_calls.outcome, refusal payloads returned by the verb/Router seam). Discord-side surfacing is re-observed read-only where traffic exists (Discord REST fetch, bot token, never displayed — 10-5 precedent), else the row's evidence cites the 10-4/10-5 L3 observation of the same code and is tagged `discord-surface: prior-evidence`.
- **Planned induced-vs-simulated split (frozen; walk may upgrade a simulated row to induced, never downgrade silently):** genuinely INDUCED expected — R1, R2, R3 (if an unclassified email exists or a synthetic email row is used → then tagged simulated-subject), R4, R5, R6 (oversized-estimate call refused pre-spend, $0), R9 (body-read-cap variant and/or chat-lane flood on local qwen), R10 (11 identical qwen dispatches), R11 (real pause), R16 (bogus action_type via propose seam). SIMULATED expected (rw-DB staging, honesty-tagged) — R7 (synthetic cost rows cross the $30 Layer-3 crossing), R8 (synthetic rows cross $2 daily), R12 (oauth_state consecutive_failures ≥3 by DB write; the REAL refresh token is never touched — durable memory `feedback_oauth_token_handling.md`), R14 (sends-today counter staged; never 20 real sends), R15 sub-cases as reachable (target_deleted may be genuinely induced via the sacrificial email per 10-2 precedent; etag/noop staged if Graph-side staging is disproportionate). R13 (schema fail) is stochastic-model-output — protocol: first check for naturally-occurring rows to corroborate, then attempt a bounded genuine induction; if neither lands defensibly, EXCLUDED-with-reason or simulated-with-tag. Final tags recorded per row in evidence.
- **Recovery step is part of every row:** after fix-assert, baseline is restored and verified (synthetic rows deleted, degraded reset via `reset_degraded_mode` + restart — proven 10-4 path, pause off, containers healthy, mailbox as found, overrides untouched). The walk ends with a full restoration checklist block in evidence.
- **Fix-step reality under F-10-5-1:** literal slash fixes are expected-FAIL (hard-assert on command names); chat-equivalent or CLI fallback is executed as the honest fix and the README Fix cell corrected same-commit. This corroborates F-10-5-1; new fix-path defects beyond it are FILED per N.5.
- **Known landmines (frozen from 10-1/10-2/10-3/10-4/10-5 evidence):** 10-1 F4 — pause does NOT gate the worker drainer (never rely on pause for containment; containment = sacrificial subject only); 10-1 F1 — pause kills Hermes chat (R11 assertion via status/CLI, resume via CLI fallback); F-10-3-2/10-4-C8 — degraded mode blocks Hermes tool-calls (R7 window kept short, digest slot timing checked before tripping); 10-2 F5 bypass + local_row_repaired are expected behavior on revert rows, not findings; anomaly-detector trips from flood traffic (R9/R10) are expected side-effects, captured not filed; transient Anthropic 529s are known noise (F-10-4-2).
- **Spend contract: ~$0.** All inductions route to local qwen or are refused pre-dispatch; no Opus anywhere; possible stray Haiku cents only if R13's genuine-induction attempt uses a live cloud escalation (bounded ≤ a few calls, estimator-recorded; Console read not required for a ~$0 story — 10-3 precedent — unless the estimator shows unexpected cloud dispatches, in which case honesty rules escalate to a Console read at Phase 3.5).
- **run_id convention:** rows produce no chat turns → `run_id 10-6-rN/2026-07-06` backed by router_calls id ranges / action ids / log line refs (10-4/10-5 convention). Action-bearing rows (R5, R14, R15) also cite `action-N`.
- **Verdict vocabulary:** PASS / FAIL / EXCLUDED-with-reason per row (10.7 table contract), PASS / PARTIAL-PASS / FAIL per AC, proposed by the walk and signed at Phase 3.5.

## Tasks / Subtasks

- [x] **Task 0 — Preconditions + baseline capture (BLOCKING)** (AC: 1, 2)
  - [x] 0.1 `docker ps` all three containers healthy; `/health` ok; sync heartbeat fresh; degraded OFF, pause OFF, 0 pending actions (verified at pre-flight — re-verify at walk start) — all green, evidence §0
  - [x] 0.2 Baselines into evidence header: W0=13819, actions max 15, outbox 26, oauth failures 0, sends-today 1, estimator month $70.60/today $0.366 — evidence §0
  - [x] 0.3 Inducement seams read + pinned: budget.py crossing-only Layer 2/3 (in-memory, seeded from router_calls at startup — month counter $70.60 already ABOVE cap → genuine crossing impossible this month, corroborates F-10-3-1; staging plan uses seed-below-cap synthetic row + restart); limits.py 60/hr interactive + >10-in-5min loop (per-process → induction MUST go through the running server via /v1/chat/completions + /mcp mount, never ad-hoc docker-exec python); drainer.py send-cap counts budget_consumed=1 send-family terminal today, target_deleted reads LOCAL soft-delete state, state_drift_etag = Tier-3 marker mismatch; **state_drift_noop defined errors.py:63 with ZERO raising sites — unreachable, pre-walk finding**; status.py OAUTH computes oauth_refresh_failing from DB counter ≥3 per request (DB staging will surface); /mcp streamable-HTTP mount is auth-free in-container; ARCHIVE is Tier-2 + MOVE_FAMILY (revertible per 10-2)
  - [x] 0.4 Subjects: 267 sensitive (e.g., id 4/5/10) + 63 confidential (id 94/95/96) live; 0 unclassified → R3 stages a synthetic subject (tagged); sacrificial low-value email designated at R5 execution time
- [x] **Task 1 — Case-table freeze** (AC: 1, 2)
  - [x] 1.1 Frozen case table R1-R16 (17 sub-cases, ≥19 code assertions) written to evidence §1 BEFORE injection, incl. per-row induced-vs-simulated plan + sequencing (floods last, restarts grouped)
- [x] **Task 2 — Cheap genuine inductions, no persistent state (R1, R2, R3, R4, R6, R16)** (AC: 1)
  - [x] 2.1 R1/R2/R4: sensitivity refusals + hydration block on real classified emails ($0, refusals only); zero body egress cross-checked in router_calls
  - [x] 2.2 R3: unclassified-email refusal; fix = targeted rederive; recovery = classified + call succeeds
  - [x] 2.3 R6: oversized-estimate cloud call refused pre-spend; fix = trim request (re-issue small) → succeeds on qwen/refusal lifted
  - [x] 2.4 R16: bogus action_type at the propose seam; assert error carries the valid-list; fix = re-issue canonical → accepted
- [x] **Task 3 — State-trip inductions with restoration (R11, R10, R9)** (AC: 1)
  - [x] 3.1 R11: pause (verb/CLI) → assert PAUSED refusal + status ROUTER reason → fix per README (slash expected-FAIL → CLI `mailbot resume`) → recovery: calls flow
  - [x] 3.2 R10: 11 identical qwen dispatches in <5min → `loop_detected` → fix choreography per README (pause, logs check, resume — chat/CLI equivalents) → recovery: distinct prompt flows
  - [x] 3.3 R9: body-read-cap variant (5/turn, ~30s reset) and/or chat-lane 60/hr flood on qwen — pick the honest cheapest that genuinely trips `rate_limited`; recovery = window slide (bounded wait) honestly recorded; anomaly-detector side-effects captured
- [x] **Task 4 — Simulated rows via rw-DB staging, honesty-tagged, baseline-restored (R7, R8, R12, R14)** (AC: 1, 2)
  - [x] 4.1 R7: synthetic cost rows cross $30 → next cloud attempt refused `monthly_budget_exceeded`/`degraded_mode_blocked` → fix = budget reset path (slash expected-FAIL → `reset_degraded_mode` verb + restart, 10-4 precedent) → recovery verified → synthetic rows deleted, degraded re-verified OFF
  - [x] 4.2 R8: synthetic rows cross $2 daily → soft-warn fires once (outbox/log) → informational-only asserted (nothing blocked) → rows deleted
  - [x] 4.3 R12 (EXPENSIVE row, simulated): oauth_state consecutive_failures ≥3 by DB write → assert status OAUTH warns + auto-pause choreography per README:304 → fix per docs/auth-recovery.md asserted as far as honestly reachable WITHOUT touching the real token (mint/persist steps NOT run — documented-fix verification is partial by design, tagged) → restore counter, verify OAuth healthy
  - [x] 4.4 R14: sends-today staged ≥20 → propose real send (Adam-owned recipient) → drain refuses `daily_send_cap_exceeded` → assert; staged rows removed; the proposed send cancelled — no real dispatch
- [x] **Task 5 — Drift + stochastic rows (R5, R15, R13)** (AC: 1, 2)
  - [x] 5.1 R5: Tier-2/move-family propose on sacrificial subject without grant → status `pending_grant` asserted → fix = mint grant (chat-equivalent/verb) → drained + applied → reverted via 10-2 revert path; mailbox as found
  - [x] 5.2 R15: `target_deleted` genuinely induced per 10-2 precedent (sacrificial subject); `state_drift_etag` / `state_drift_noop` staged or EXCLUDED-with-reason if staging is disproportionate — per-sub-case tags; `mailbot replay <id>` fix asserted where applicable
  - [x] 5.3 R13: corroborate from history → bounded genuine-induction attempt → else simulated-with-tag or EXCLUDED-with-reason; escalation choreography (qwen→Haiku) asserted from audit rows
- [x] **Task 6 — README doc-drift rule (a) edits** (AC: 3)
  - [x] 6.1 Error-table Fix cells corrected where the documented fix FAILED (slash-form fallout + anything new); corrected rows tagged `<!-- verified 10-6, run_id ... -->`; PASS rows tagged; EXCLUDED rows untouched + honest note if warranted
- [x] **Task 7 — Findings FILED per N.5** (AC: 3)
  - [x] 7.1 F-10-6-N findings table in evidence, mirrored to `epic-10-run-flags.md`; zero fixes shipped; 16-vs-17 charter count filed as INFO
- [x] **Task 8 — Compose `10-6-walk-evidence.md`** (AC: 1, 2, 3)
  - [x] 8.1 Session header, frozen case table, per-row blocks (induce/assert/fix/recover + induced-vs-simulated tag + provenance), restoration checklist, findings table, verdict table (all rows named PASS/FAIL/EXCLUDED-with-reason), per-AC proposed verdicts
- [x] **Task 9 — CR determination, run-flags, gates, sprint flip, stage (never commit)** (AC: 4)
  - [x] 9.1 CR-cadence determination recorded (expect zero criteria — zero production code)
  - [x] 9.2 Append § "Story 10-6 Run 1" to `epic-10-run-flags.md`; flag report to `story-run-flags.md`
  - [x] 9.3 Gates: ruff/mypy/boundaries/pytest expected byte-identical to baseline (docs+evidence only)
  - [x] 9.4 sprint-status flip `review`; explicit-path staging; `done` on signed verdicts; nothing committed

## Dev Notes

### Live-DB access pattern (unchanged from 10-3/10-4/10-5)

`MSYS_NO_PATHCONV=1 docker exec mailbot-api python -c "import sqlite3; sqlite3.connect('file:/data/mailbot.db?mode=ro', uri=True)"` — image has no sqlite3 CLI; rw staging uses the same seam WITHOUT `mode=ro`, each write paired with its restoration statement recorded in evidence BEFORE execution (stage/restore symmetry).

### Restoration contract (hard)

Every rw staging action logs `(staged_sql, restore_sql)` to evidence before firing. End-of-walk restoration checklist re-verifies: degraded OFF, pause OFF, oauth_state counters at baseline, synthetic router_calls/action rows deleted, pending actions drained-or-cancelled to baseline 0, sacrificial email back in place (10-2 revert or manual note), containers healthy, suite-relevant runtime files untouched.

### Container stop/start (authorized, use sparingly)

Authorized by Adam but only needed if a row's honest inducement demands it (e.g., provider-unreachable variants). Not a frozen case — any use is recorded with health-recovery assertion.

### Project Structure Notes

Files this story may touch — and ONLY these: `README.md` (error-table corrections, doc-drift rule (a) — explicit AC), `_bmad-output/implementation-artifacts/10-6-walk-evidence.md` (new), `epic-10-run-flags.md` (append), `sprint-status.yaml` (flips), this story file, `story-run-flags.md` (run report), optional throwaway scaffolding under `scratch/` (untracked, never staged). ZERO changes under `mailbot_api/`, `scripts/`, `router/`, `hermes-config/`, `docker/`, `tests/`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Epic 10 Detail" (D3, doc-drift rules, N.5 fence) + § "Story 10.6"] — ACs verbatim
- [Source: README.md:287-308] — the error table under injection; :362-372 limitations context
- [Source: mailbot_api/router/errors.py + router/budget.py + sync/oauth.py + actions/drainer.py + verbs/hydrate_email.py + observability/status.py + db/migrations/023_oauth_state_consecutive_failures.sql] — inducement seams (pinned in Task 0.3)
- [Source: 10-1/10-2/10-4/10-5 walk-evidence + epic-10-run-flags.md] — F1/F4 pause landmines, target_deleted precedent, slash-prefix fix fallout (F-10-5-1), degraded reset path, run_id + sanitization conventions
- [Source: memory feedback_oauth_token_handling.md, project_epic_6_scope_cleave.md (N.5), ops_msys_path_mangling_docker_exec.md] — durable rules binding this walk

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — inline create-story + autonomous fault-injection walk orchestration + evidence + README doc-drift, pure-autonomous `autonomous story run 10-6` session 2026-07-06 (Adam pre-flight decision: pure autonomous, full risk envelope). No human turns during Phase 2; Adam signs verdicts at Phase 3.5.

### Debug Log References

- `10-6-walk-evidence.md` (frozen case table R1-R16, 17 per-row blocks with induce/assert/fix/recover + induced-vs-simulated tags + provenance, restoration checklist, findings table F-10-6-1..7, verdict table, per-AC verdicts)
- `epic-10-run-flags.md` § "Story 10-6 Run 1"
- `scratch/mcp_walk_106.py` — untracked MCP walk-driver scaffolding (never staged)

### Completion Notes List

- **AC-1 (per-row protocol): PASS** — 16 README error rows induced-or-simulated, R15's 3 codes walked as R15a/b/c → 18 verdict rows total; each: induce → hard-assert code (Discord/status/logs/DB/router_calls) → apply documented fix → assert recovery. §2 per-row blocks.
- **AC-2 (D3 honesty tagging): PASS** — every row induced-vs-simulated tagged; 5 SIMULATED rows carry their staging mechanic explicitly (R3 synthetic subject, R7/R8 staged counters, R12 oauth counter, R14 send-count, R15b marker); R12 (expensive OAuth row per D3) carries partial-fix + cited-not-observed caveats. No simulated row recorded as induced.
- **AC-3 (verdict table + N.5 + doc-drift): PASS** — §5 names all rows PASS/FAIL (13 PASS / 5 FAIL / 0 EXCLUDED across 18 verdict rows; 16 README rows, R15=3 sub-cases); 7 findings FILED zero fixed; README error-table corrected same-commit for every FAIL (F-10-6-2/3/4/5/6 + R13 prose) + 10 verified-10-6 PASS tags.
- **AC-4 (CR cadence): PASS** — zero production code touched (README + evidence/tracking only; `scratch/mcp_walk_106.py` untracked, never staged). Zero of 6 CR criteria fire → CR skipped per cadence binding.
- **Findings F-10-6-1..7 FILED per N.5, zero fixed:** F-10-6-3 HIGH (`mailbot rederive` crashes every invocation — no adapter bootstrap in the CLI subcommand); F-10-6-2 MEDIUM (`mailbot replay` inert for move-induced `target_deleted`); F-10-6-4 MEDIUM (`state_drift_noop` unreachable dead code); F-10-6-5 LOW (`monthly_budget_exceeded` unreachable dead code); F-10-6-6 LOW (paused refusal is `provider_error`, no `PAUSED` code); F-10-6-7 LOW (`mailbot logs` crashes on Windows cp1252 console); F-10-6-1 INFO (charter said 17 rows, table has 16). Every FAIL is a doc-contract defect; zero product-capability regressions.
- **Spend: $0.0109 estimator-attributable** (Haiku recovery micro-calls + R7/R8 crossing calls), zero Opus — three orders under the Console-read threshold (10-3 $0-story precedent). F-10-3-1 estimator inflation corroborated again (month ~$70 forced R7 simulation).
- **Restoration verified:** degraded OFF, pause OFF, oauth counter 0, all synthetic rows deleted, sacrificial email E118 back in Inbox, E117 marker restored, no open pending actions, 3 containers healthy (api restarted ×3 for counter re-seed, all recovered).
- Gates at close: ruff clean on tracked tree (6 pre-existing T201 in untracked `scratch/`, same residual class as 10-1..10-5), mypy --strict clean (129 files), boundaries exit 0, pytest **1708 passed + 2 skipped + 3 deselected in 215.66s** — byte-identical to baseline (docs+evidence only).

### File List

None — documentation/walk story, no source files modified. Artifacts:

- `README.md` (§"Common errors" table: 6 FAIL rows corrected + 10 PASS rows verified-tagged + intro note, doc-drift rule (a))
- `_bmad-output/implementation-artifacts/10-6-fault-injection-walks-all-17-error-table-rows.md` (this file)
- `_bmad-output/implementation-artifacts/10-6-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (§ Story 10-6 Run 1 appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- `_bmad-output/implementation-artifacts/story-run-flags.md` (run report)
- `scratch/mcp_walk_106.py` — untracked MCP walk-driver scaffolding; NOT staged, never part of the source tree

### Change Log

- 2026-07-06 — All 16 README common-error rows fault-injected against the live local stack (pure-autonomous, full risk envelope): 13 PASS / 5 FAIL / 0 EXCLUDED across 18 verdict rows; 7 findings FILED per N.5 (1 HIGH broken rederive CLI); README error-table made evidence-real (6 FAIL-row corrections + 10 verified tags); every FAIL a doc-contract defect, zero product regressions; baseline fully restored; zero code changes; $0.0109 estimator spend, zero Opus.
