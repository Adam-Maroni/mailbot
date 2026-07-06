# Story 10-6 Walk Evidence — Fault-injection walks, all error-table rows

**Session:** 2026-07-06, pure-autonomous run (Adam-authorized pre-flight: run-mode = pure autonomous; risk envelope = pause/degraded/rate/loop trips + container stop/start + simulated rw-DB rows honesty-tagged + sacrificial-folder mailbox micro-mutations).
**Orchestrator/dev model:** claude-fable-5. **Spend contract:** ~$0 (qwen + pre-dispatch refusals; stray Haiku cents only where a recovery proof needs one real cloud dispatch — estimator-recorded per row).
**Baseline commit:** `1a7dbf5` (working tree also carried pre-existing `.claude/settings.json` modification + untracked `scratch/` — neither touched by this story).
**Signature line:** verdicts below are PROPOSED by the walk; Adam signs at Phase 3.5.

## 0. Baselines (Task 0, captured 2026-07-06 pre-injection)

| Field | Value |
| --- | --- |
| Containers | mailbot-api Up 3h (healthy), mailbot-hermes Up 3h, mailbot-ollama Up 3h (healthy) |
| Degraded mode | INACTIVE (`degraded_mode_state`: active=0, exited 2026-07-06T07:54:33Z — the 10-4 pre-run reset) |
| Pause | pause_state: paused=0 (last resumed 2026-07-06T10:12:56Z, 10-5 S6) |
| router_calls watermark W0 | max id **13819** (count 13819) |
| action rows | pending_actions max id **15** (13 applied / 1 cancelled / 1 failed; 0 pending); action_history rowid ≤15, count 14 |
| notifications_outbox watermark | max id **26** |
| oauth_state | provider=microsoft_graph, rotation_count=263, **consecutive_refresh_failures=0**, last_rotated 2026-07-06T16:52:24Z |
| Spend (estimator-only, F-10-3-1 inflation known) | month-to-date $70.6019, today $0.3660 |
| sends today (budget_consumed send-family, UTC) | **1** (10-5 W1b action 15) |
| Sync heartbeat | fresh (2026-07-06T17:09:59Z) |
| Sensitivity population | 63 confidential / 267 sensitive / 1606 normal / **0 unclassified** (R3 requires a staged synthetic subject) |
| Suite baseline | 1708 passed + 2 skipped + 3 deselected (10-5 close) |

**Charter count reconciliation (honest, frozen pre-walk):** the README common-errors table (README:291-308) has **16 data rows** — verified at commits 5c634a7 (rewrite), 4a61545, and HEAD (18 pipe-lines = header + separator + 16). The epic charter says "17". Walked as R1–R16; R1 carries 2 codes and R15 carries 3, so ≥19 distinct code assertions. Filed as INFO finding F-10-6-INFO-1 feeding 10-7's table.

## 1. Frozen case table (Task 1 — frozen BEFORE injection)

Protocol per row: **induce → assert code (Discord and/or `mailbot status`/logs/DB) → apply documented fix → assert recovery**, then restore baseline. Codes are hard-assert; prose soft-assert. `discord-surface: prior-evidence` = code's Discord surfacing rests on named 10-4/10-5 L3 observations, not re-observed this walk.

| Case | README row (line) | Code(s) | Planned inducement | Planned tag |
| --- | --- | --- | --- | --- |
| R1 | :293 sensitive, no token | `sensitivity_blocks_api` / `needs_sensitivity_confirmation` | MCP `ask_router` cloud task (summary_short) on a live `sensitive` email, no token → pre-dispatch refusal, $0 | INDUCED |
| R2 | :294 confidential | `sensitivity_blocks_api` | same on a live `confidential` email | INDUCED |
| R3 | :295 not yet classified | `sensitivity_not_classified` | synthetic email row staged (sensitivity_at NULL) → cloud task refused; fix = documented `mailbot rederive --task=sensitivity_class`; recovery = call passes gate | INDUCED (staged synthetic subject — tagged) |
| R4 | :296 confidential body-read | `CONFIDENTIAL_HYDRATION_BLOCKED` | MCP `hydrate_email` on live confidential email | INDUCED |
| R5 | :297 awaiting grant | status `pending_grant` | MCP `propose_action` ARCHIVE (Tier-2, move-family) on sacrificial low-value email, NO grant → status shows awaiting grant; fix = approve (mint_grant); recovery = drained+applied, then 10-2 revert restores mailbox | INDUCED |
| R6 | :298 per-call refusal | `per_call_threshold_exceeded` | oversized-input cloud task → estimate > $0.20 → pre-dispatch refusal, $0; fix = trim request → re-issue small succeeds | INDUCED |
| R7 | :299 monthly cap | `monthly_budget_exceeded` → `degraded_mode_blocked` | month counter staged to $29.999 via synthetic router_calls row (real rows never mutated) + restart re-seed → one tiny real Haiku call genuinely CROSSES Layer-3 → degraded entered; cloud attempt → blocked; fix = reset path (slash form expected-FAIL per F-10-5-1 → `reset_degraded_mode` + restart, 10-4 precedent); cleanup | SIMULATED (staged counter; real crossing code path) |
| R8 | :300 daily soft warn | `budget.daily.soft_warn` | today counter staged to $1.999 (synthetic row) + restart → tiny real call crosses $2 → single-fire warn log; assert nothing blocked; cleanup | SIMULATED (staged counter; real crossing code path) |
| R9 | :301 rate limited | `rate_limited` | interactive-lane flood (distinct prompts, local qwen, $0) to 60/hr → 61st refused. Run LAST (window pollution). Recovery = documented "wait" honestly PARTIAL (60-min slide not waited out) | INDUCED |
| R10 | :302 loop kill-switch | `loop_detected` | 11 identical qwen dispatches <5min via `/v1/chat/completions` → 11th refused; fix choreography pause→logs→resume (CLI); recovery = distinct prompt flows + window slide | INDUCED |
| R11 | :303 paused | `PAUSED` | `/admin/pause` (server-process, the `mailbot pause` transport) → cloud+local attempts refused; fix = `/resume` slash expected-FAIL (F-10-5-1) → CLI `mailbot resume`; recovery = calls flow | INDUCED |
| R12 | :304 OAuth refresh failing | `oauth_refresh_failing` | EXPENSIVE row per D3 → oauth_state.consecutive_refresh_failures staged to 3 (real refresh token NEVER touched) → `mailbot status` OAUTH warns; documented fix (re-mint) asserted only as far as honestly reachable WITHOUT a real token op — partial by design; counter restored | SIMULATED (explicit D3 expensive-row carve-out) |
| R13 | :305 schema fail | `schema_validation_failed` | corroborate from router_calls history → bounded genuine-induction attempt on a structured qwen task → else EXCLUDED-with-reason (stochastic model output not deterministically inducible without code seams) | decided in-walk |
| R14 | :306 send cap | `daily_send_cap_exceeded` | sends-today staged to ≥20 via synthetic budget_consumed send rows (NEVER 20 real sends) → real proposed+granted send refused at drain, zero dispatch; cleanup | SIMULATED |
| R15a | :307 drift | `target_deleted` | archive proposed+granted on sacrificial email → local soft-delete staged pre-drain (same drainer check the real Outlook-delete path reads) → drain refuses; fix = restore + `mailbot replay <id>` → applied; then revert | SIMULATED (local-DB-staged deletion) |
| R15b | :307 drift | `state_drift_etag` | Tier-3 send_reply proposed+granted on sacrificial email; emails.change_key staged to mismatch marker-at-propose → drain refuses, zero dispatch; restore | SIMULATED |
| R15c | :307 drift | `state_drift_noop` | **pre-walk code-reality finding: code is defined in errors.py:63 but has ZERO raising sites in the codebase** — unreachable by construction; expected FAIL + FILED + README correction | n/a (unreachable) |
| R16 | :308 unknown action | `INVALID_ACTION_TYPE` | MCP `propose_action` with bogus action_type → assert error carries valid list; fix = re-issue canonical → accepted (then cancelled) | INDUCED |

**Sequencing:** R16 → R4 → R1 → R2 → R3 → R6 → R5 → R15a → R15b → R14 → R12 → R13 → R8 → R7 → R11 → R10 → R9 (floods last; restarts grouped in R8/R7; every staging row logs its restore statement before firing).

## 2. Per-row walk blocks

All inducements against the RUNNING server process (MCP streamable-HTTP mount `localhost:8000/mcp/` + `/admin/*` + worker drainer) — never ad-hoc in-process fakes, except where a row's block says otherwise. Walk scaffolding: `scratch/mcp_walk_106.py` (untracked, never staged).

### R16 — `INVALID_ACTION_TYPE` (README:308) — tag: INDUCED — run_id 10-6-r16/2026-07-06

- **Induce:** MCP `propose_action(email_id=<E118 graph id>, action_type="defenestrate_email")` against the running server.
- **Assert:** refusal verbatim `"code": "INVALID_ACTION_TYPE", "message": "unknown action_type 'defenestrate_email'; must be one of ['add_local_category', 'archive', ..., 'write_derived_field']"` — the error **carries the full 23-member valid list** (hard-assert README claim HOLDS), plus a `recovery_action` hint naming `propose_action` with `valid_choices` and pointing at the `mailbot://action-types` MCP resource. This machine-readable recovery payload is exactly what the README's "self-correcting — the agent retries" behavior rides on. Agent-side auto-retry itself is Discord-choreography: `discord-surface: prior-evidence` (10-4/10-5 pattern of agent retry-on-refusal); not re-observed this walk.
- **Fix (documented: "just re-ask"):** re-issued with canonical `archive` → accepted (`ok: true, action_id: 16`).
- **Recovery:** accepted proposal proceeded through the normal pipeline (see R5). **Verdict proposed: PASS.**

### R5 — status `pending_grant` (README:297) — tag: INDUCED — run_id action-16/2026-07-06

- **Subject:** sacrificial low-value email E118 (local id 118, Dropbox newsletter 2026-04-26, sensitivity=normal) — Adam pre-authorized mailbox micro-mutations, blast radius one email.
- **Induce:** MCP `propose_action(archive)` (Tier-2, move-family) with NO grant → `"status": "pending_grant", "requires_grant": true` + `recovery_action` hint naming `mint_grant`.
- **Assert:** `mailbot status` ACTIONS section reads `pending by tier: {'2': 1}` / **`awaiting grant: 1`** — README:297's "`mailbot status` shows 'awaiting grant'" HOLDS verbatim (in-container CLI, wraps GET /admin/status).
- **Fix (documented: approve/grant):** `mint_grant(archive, [E118], expires_at=+180s)` → grant_id 7. Chat-phrase approval ("yes, archive them") is Discord choreography: `discord-surface: prior-evidence` (10-5 W2 walked the chat-side grant mint at L3, incl. F-10-5-8 approval-not-solicited caveat).
- **Recovery:** worker drainer claimed + dispatched REAL Graph archive within seconds (applied 17:23:47Z); `action_history` row 16 captured **populated pre_state** (`source_folder_id` = real Inbox id — 10-2 seam live again). **Verdict proposed: PASS.**
- **Restoration + bonus finding:** `revert_action(16)` refused `ONLY_TIER_1_REVERTIBLE` (tier 2) — consistent with README:368/10-2 limitation (Tier-2 pre_state is audit-only). Mailbox restored via fresh `move_to_inbox` proposal (see R15a, which this restoration doubled as). Note: README:297's Fix cell also documents the lapsed-send re-mint path — not exercised here (10-5 W1 covered send-family grant flow).

### R15a — `target_deleted` (README:307, code 2 of 3) — tag: **INDUCED (genuinely)** — run_id action-17/2026-07-06

- **Context that made this genuine:** R5's applied archive physically moved E118 in Outlook; delta sync then soft-deleted the local row (`deleted_at=17:24:25Z, removed_reason='deleted'`) — 10-1 F5 live. The mailbox REALLY changed underneath the local DB between propose and apply — precisely README:307's cause, no staging needed.
- **Induce:** `propose_action(move_to_inbox)` on E118 (action 17) + `mint_grant` (grant 8) → drainer Tier-2 check → lenient rule read `deleted_at IS NOT NULL` → **`failed / target_deleted`** at 17:25:45Z.
- **Assert:** `pending_actions.failure_reason='target_deleted'` verbatim; notification outbox row 27 (`important/action_escalation`: "action 17 (move_to_inbox, Tier 2) failed: target_deleted") queued for Hermes→Discord delivery — Discord-bound alert layer captured at the outbox seam; `discord-surface: prior-evidence` for final delivery hop (10-4 C8 walked outbox→Discord delivery L3).
- **Fix (documented: "Re-issue the request against the current mailbox state; `mailbot replay <id>` re-queues if the failure was transient"):** `mailbot replay 17` (in-container CLI) → re-queued → drainer refused **`target_deleted` again** (outbox 28). HONEST RESULT: replay does not clear this row — target_deleted from the F5 soft-delete is NOT transient, and a fresh re-issue reads the same local state (same `_check_tier_1` read, deterministic). The Fix cell's replay clause is inert for this sub-case, and "re-issue" only works after the local row is repaired. Only 10-2 revert rows bypass (by design). → **FILED F-10-6-2** + same-commit README correction.
- **Recovery (the working fix):** local soft-delete repaired (rw restore op: `UPDATE emails SET deleted_at=NULL, removed_reason=NULL WHERE id=118` — mirrors 10-2's `local_row_repaired` semantics) → `mailbot replay 17` → drainer applied REAL Graph move_to_inbox (pre_state captured) → **E118 back in Inbox, mailbox as found**. **Verdict proposed: FAIL (code surfaces correctly + recovery achievable, but documented fix does not work as written).**

### R15b — `state_drift_etag` (README:307, code 1 of 3) — tag: SIMULATED (staged marker) — run_id action-18/2026-07-06

- **Subject:** E117 (local id 117, cancer.ca newsletter, normal, never moved — chosen so no F5 soft-delete can race the case).
- **Induce:** `propose_action(send_reply)` (Tier-3, action 18, `status: cooling_off` — 60s Tier-3 cooling-off observed live) captured `change_marker_at_propose` = real marker `…AAj/MUdo`; staged rw mutation `UPDATE emails SET change_marker='…DRIFT-106' WHERE id=117` (restore SQL logged pre-fire) BEFORE minting grant 9 — refusal deterministic before any dispatch was possible. Drainer Tier-3 strict check → **`failed / state_drift_etag`**, `budget_consumed=1` (AR-D5-2: failed send consumes send budget — observed live, sends-today 1→2).
- **Assert:** `pending_actions.failure_reason='state_drift_etag'` verbatim; outbox row 29 `urgent/action_escalation` "action 18 (send_reply, Tier 3) failed: state_drift_etag". Zero Graph dispatch (refusal precedes dispatch in `run_tick`; no action_history row).
- **Fix (documented: re-issue against current state / replay if transient):** asserted STRUCTURALLY, not executed — marker restored, so a re-issue would capture the now-current marker and pass the strict check (deterministic from drainer code path); actually dispatching it would send a REAL reply to a third-party no-reply address — out of blast radius. **Safety note recorded: replay of action 18 after marker restore would PASS the etag check and really send — action 18 must stay `failed`; never replay it.**
- **Restore:** marker restored to `…AAj/MUdo`, verified. **Verdict proposed: PASS (code + refusal + alert verified live; fix asserted structurally within blast-radius limits).**

### R15c — `state_drift_noop` (README:307, code 3 of 3) — tag: n/a — run_id 10-6-r15c/2026-07-06

- **Pre-walk code-reality scan:** `STATE_DRIFT_NOOP = "state_drift_noop"` exists at `errors.py:63` with **ZERO raising sites** anywhere in `mailbot_api/` — `grep -rn state_drift_noop` hits only the enum definition. The code is unreachable by construction; no fault can surface it, no fix can be exercised.
- **Verdict proposed: FAIL** (README hard-asserts a code that cannot occur) → **FILED F-10-6-4** + same-commit README correction.

### R14 — `daily_send_cap_exceeded` (README:306) — tag: SIMULATED (staged counter) — run_id action-37/2026-07-06

- **Induce:** 18 synthetic send-family rows staged (`payload marker 10-6-R14-SYNTHETIC`, `budget_consumed=1`, terminal today; restore SQL logged pre-fire) bringing today's cap count to exactly **20** (2 genuine: 10-5 action 15 send + R15b's failed send — AR-D5-2). Real `propose_action(send_reply)` (action 37) + grant 10 → cooling-off → drainer cap check (which fires BEFORE dispatch by design, drainer.py:609-616) → **`failed / daily_send_cap_exceeded`**, zero dispatch.
- **Assert:** `failure_reason='daily_send_cap_exceeded'` verbatim; outbox 30 `urgent/action_escalation`. Cap arithmetic verified against the production query (`SEND_FAMILY_BUDGET_CONSUMED_TODAY_COUNT`).
- **Fix (documented: "Wait until UTC midnight. No override."):** honest structural assert — no lift verb/env exists on the cap path (`DAILY_SEND_CAP = 20` constant, drainer.py:81); the failed row itself consumed budget (`budget_consumed=1` on action 37, by design). Time-based fix not waited out (UTC midnight ~6.5h away) — mechanism is the day-bounded count query, deterministic.
- **Restore:** 18 synthetic rows deleted (verified count back to 3 — all genuine walk/10-5 rows retained as audit truth). **Verdict proposed: PASS.**

### R4 — `CONFIDENTIAL_HYDRATION_BLOCKED` (README:296) — tag: INDUCED — run_id 10-6-r4/2026-07-06

- **Induce:** MCP `hydrate_email(email_id=<E94 graph id>)` (live confidential email, id 94) against the running server.
- **Assert:** refusal verbatim `"code": "CONFIDENTIAL_HYDRATION_BLOCKED", "message": "confidential emails cannot be hydrated to the agent — only metadata is available"`; `email: null` — zero body egress at the verb boundary.
- **Fix (documented: "Read it in Outlook"):** nothing product-side to exercise — by-design refusal; Outlook remains the read path. **Verdict proposed: PASS.**

### R1 — `sensitivity_blocks_api` / `needs_sensitivity_confirmation` (README:293) — tag: INDUCED — run_id 10-6-r1/2026-07-06 (router_calls 13820+)

- **Channel honesty note:** ask_router is not MCP-exposed; inducement ran the REAL `ask_router` + sensitivity gate + token registry code in-container against the live DB (gate is stateless pre-dispatch; mint+consume in one process mirrors production's server-process semantics). `discord-surface: prior-evidence` (10-5 walked 12 gate refusals L3 from chat).
- **Induce (a):** `ask_router('summary_short', …, email_id=<E4 sensitive>)` no token → **`sensitivity_blocks_api`** — "sensitive email requires per-session confirmation token to escalate to API". Audit row 13820 `outcome=failed, model_chosen_reason=sensitivity_gate:refused`, $0, tokens_in=0.
- **Induce (b):** same call with `confirmation_token='bogus-token-10-6'` → **`needs_sensitivity_confirmation`** — "confirmation token invalid, expired, already consumed, or mismatched (email_id/task_type)". Both README codes surfaced.
- **Fix (documented `/confirm <email_id> <task>` handshake):** literal `/confirm` slash form is unreachable from Discord (F-10-5-1) and its chat choreography is broken-by-construction per FILED F-10-5-7 — NOT re-walked; the token ENGINE the fix rides on was walked: `sensitivity_tokens.mint(email_id, task_type)` → valid token → **gate lifted, real Haiku dispatch ok=True cost $0.000317**.
- **Single-use proof:** immediate re-use of the same token → `needs_sensitivity_confirmation` (consumed).
- **Recovery:** subsequent unrelated calls unaffected (stateless gate). **Verdict proposed: PASS (codes + engine); fix-cell caveat recorded — the documented /confirm choreography itself is already FILED broken (F-10-5-1/7), corroborated not re-filed.**
- Walk-harness noise recorded honestly: two intermediate probe calls failed `prompt render failed: KeyError` (13822-13823, harness content-shape misses, $0) before the content keys were corrected.

### R2 — `sensitivity_blocks_api` confidential (README:294) — tag: INDUCED — run_id 10-6-r2/2026-07-06 (router_calls 13821)

- **Induce:** `ask_router('summary_short', …, email_id=<E94 confidential>)` → **`sensitivity_blocks_api`** — message **"confidential emails admit no API override"** = README:294's quoted surface verbatim. $0, tokens_in=0, audit row 13821 `sensitivity_gate:refused`.
- **Fix (documented: "By design. Nothing to fix."):** confirmed — no override parameter exists on the confidential branch (router.py:419 regardless-of-token). **Verdict proposed: PASS.**

### R6 — `per_call_threshold_exceeded` (README:298) — tag: INDUCED — run_id 10-6-r6/2026-07-06

- **Induce:** `ask_router('summary_short', …)` with ~1.4MB `body_preview` (rendered-prompt estimate is `len//4` chars, router.py:699) → **`per_call_threshold_exceeded`** — "estimated cost $0.3471 exceeds per-call threshold $0.20; pass force=True to override". Refused PRE-dispatch and PRE-cache (Layer 4 fires before cache by design), $0.
- **Fix (documented: confirm-to-force OR trim):** trim path EXECUTED — small re-issue dispatched ok (real Haiku, $0.000372). Force path exists as `force=True` (named in the refusal itself); chat-confirm choreography `discord-surface: prior-evidence`.
- **Interesting negative captured:** the same 1.4MB in `body` (not `body_preview`) dispatched at $0.0004 — the summary_short template only renders subject/sender/body_preview, so oversized fields OUTSIDE the template never hit the estimator. Recorded as observation, not a finding (the gate correctly prices what is actually sent).
- **Verdict proposed: PASS.**

### R3 — `sensitivity_not_classified` (README:295) — tag: INDUCED (staged synthetic subject) — run_id 10-6-r3/2026-07-06

- **Staging:** live mailbox has ZERO unclassified emails (ingest keeps up) — synthetic email row staged (`graph_id='walk-10-6-R3-SYNTH'`, local id 3580, future-dated received_at 2026-07-07 so the documented rederive fix can be scoped to it alone; restore SQL logged pre-fire).
- **Induce:** `ask_router('summary_short', …, email_id='walk-10-6-R3-SYNTH')` → **`sensitivity_not_classified`** — "email sensitivity must be classified before any other Router task" (FR-2.3 invariant live).
- **Fix attempt 1 (documented fallback: `mailbot rederive --task=sensitivity_class --since=2026-07-07 --yes`):** **FAILED — succeeded: 0, failed: 1, error `KeyError: "no adapter registered for model_id='qwen2.5:3b-instruct-q4_K_M'"`.** Root cause read from source: `init_default_adapters()` is called by the FastAPI lifespan (main.py:178) and by `python -m mailbot_api.ingest.pipeline` (pipeline.py:743) but NEVER by the `mailbot rederive` CLI subcommand — every rederive invocation dies on adapter KeyError. The README:295 fix cell's rederive clause is broken as documented. → **FILED F-10-6-3** + same-commit README correction.
- **Fix attempt 2 (documented primary: "Wait a few minutes"):** **WORKS** — the ingest worker picked up the synthetic row on its own and qwen-classified it `normal` at 17:43:20Z (~4 min after staging), $0. Recovery re-probe: gate passed, real Haiku dispatch ok ($0.000318). Bonus live capture: the pipeline pass on this very row produced `retry_recovered` audit rows (13833-13836) — the schema-fail auto-retry chain (R13's fix claim) observed firing on walk-generated traffic.
- **Restore:** synthetic email row deleted + 5 orphan `derivations_idempotency` rows cleaned; verified gone.
- **Verdict proposed: FAIL** (code + primary fix verified, but the fix cell's rederive clause is broken as documented — F-10-6-3; same-commit README correction applied).

### R12 — `oauth_refresh_failing` (README:304) — tag: SIMULATED (D3 expensive-row carve-out) — run_id 10-6-r12/2026-07-06

- **Induce:** `oauth_state.consecutive_refresh_failures` staged 0→3 by rw DB write (restore SQL logged pre-fire). **The real refresh token was never touched, read, or displayed** (durable memory `feedback_oauth_token_handling.md`).
- **Assert:** `mailbot status` OAUTH section flipped to warning: `! OAUTH / refresh failing: yes (re-auth required) / consecutive fails: 3` — the README's status-surface claim holds; `oauth_refresh_failing` is computed from the counter ≥ threshold 3 per request (status.py:345-400, `OAUTH_REFRESH_FAIL_THRESHOLD=3` in sync/oauth.py:51).
- **Honest simulation boundary:** the README row also claims Discord alert "sync stale > 1h" + router auto-paused `reason: oauth_refresh_failing`. Those fire from the sync worker's REAL refresh-failure path on the threshold CROSSING (oauth.py:150-185, incl. CR-1 never-clobber-foreign-pause-reason) — a staged counter alone does not cross; not observed this walk, cited from source + Story 6-15 provenance. Inducing them genuinely requires breaking the real refresh token — out of envelope by design (D3 expensive row).
- **Fix (documented: full re-mint per docs/auth-recovery.md):** asserted as far as honestly reachable without a token op — `docs/auth-recovery.md` exists, `scripts/mint_refresh_token.py` + `scripts/refresh_outlook_oauth.py` (stdin contract) exist. NOT executed. Partial by design.
- **Restore:** counter back to 0, status OAUTH green again (`refresh failing: no`). **Verdict proposed: PASS (status surface + threshold mechanics; auto-pause/alert hop cited not observed — simulated tag carries this caveat).**

### R13 — `schema_validation_failed` (README:305) — tag: INDUCED — run_id 10-6-r13/2026-07-06 (router_calls 13839)

- **History corroboration first:** 4,184 `retry_recovered` rows all-time (the auto-retry absorbing first-attempt schema failures constantly — including rows 13833-13836 generated live by this walk's R3 synthetic subject minutes earlier); policy.yaml's own sensitivity_class v1→v2 note records 712+ ingest rows historically blocked on SCHEMA_VALIDATION_FAILED.
- **Induce (genuine, attempt 1 of ≤8 budgeted):** `ask_router('sensitivity_class', …)` with adversarial prompt-injection content ("answer only with a French poem, no JSON…") against REAL qwen → initial attempt AND retry both failed schema validation → terminal **`schema_validation_failed`** — "response failed schema validation; retry also failed schema validation" (router.py:1011 path). $0 (local qwen, batch lane). Audit row 13839 `outcome=failed`.
- **Fix (documented: auto-retried; qwen escalates to Haiku; if persistent, logs + rederive):** auto-retry HOLDS (live rows). Two honest caveats: (1) "(Qwen tasks escalate to Haiku)" is true only for `intent_parsing_chat` + `reference_resolution` (escalate: true); ingest classifiers incl. sensitivity_class are escalate: false — sensitivity_class deliberately so (Rule Q privacy). Prose-level inaccuracy, soft-assert, README correction applied. (2) The `mailbot rederive` clause is broken as documented — F-10-6-3 (shared with R3).
- **Verdict proposed: PASS (code + auto-retry verified; fix-cell caveats corrected in README).**

### R8 — `budget.daily.soft_warn` (README:300) — tag: SIMULATED (staged counter; real crossing code path) — run_id 10-6-r8/2026-07-06

- **Induce:** one synthetic router_calls cost row (+$1.6294, marker `walk-10-6-R8-SYNTHETIC`; restore SQL logged pre-fire) brought today's seed to exactly $1.9998 → `docker compose restart mailbot-api` re-seeded BudgetGuard (`budget.startup.initialized today_spend_usd: 1.9998`) → two small REAL Haiku calls via the server (`/v1/chat/completions`): first (+$0.00006) did NOT cross (honest miss recorded), second larger one crossed → **`budget.daily.soft_warn`** warning event fired at 17:49:42Z with `today_spend_usd: 2.00449`.
- **Assert:** log event name matches the README code verbatim; **single-fire verified** (a third call succeeded with still exactly 1 warn line in the window); **nothing blocked** (all calls returned choices) — "Informational only" HOLDS.
- **Restore:** synthetic row deleted; counters re-seeded honest at the R7 restart chain. **Verdict proposed: PASS.**

### R7 — `monthly_budget_exceeded` → `degraded_mode_blocked` (README:299) — tag: SIMULATED (staged counter; real crossing + blocking code paths) — run_id 10-6-r7/2026-07-06

- **Why simulation was the ONLY honest route:** BudgetGuard month counter re-seeds from router_calls at startup and Layer-3 entry is CROSSING-only (`prev < 30 ≤ new`, budget.py:126-131). The estimator month sum sits at ~$70.6 — already far above cap (F-10-3-1 corroborated again) — so no genuine call can ever cross this month. Staged one NEGATIVE synthetic row (−$40.612, marker `walk-10-6-R7-SYNTHETIC`; restore SQL logged pre-fire) → month seed exactly $29.999 → restart re-seed.
- **Induce:** one real Haiku call crossed → **`budget.degraded.entered`** — "monthly budget breached — entering degraded mode" ($30.0036 vs cap $30.00); `degraded_mode_state.active=1` persisted 17:50:33Z. The crossing call itself succeeded (entry on post-success accounting, by design).
- **Assert blocked state:** (a) forced-Opus attempt refused: "degraded mode active; force_model=claude-opus-4-7 requires confirmation token" (`DEGRADED_MODE_BLOCKED`, router.py:397 — README's "Opus one-shots in degraded mode trigger an extra confirmation" verbatim behavior); (b) demotion chain LIVE: hermes_aux (policy haiku) served by qwen with audit `model_chosen_reason = degraded:claude-haiku-4-5-20251001→qwen2.5:3b-instruct-q4_K_M` (row 13847) — "everything routes to local Qwen" HOLDS; (c) `mailbot status` BUDGET: `degraded mode: yes`, month 100.0%.
- **Code-reality finding:** **`monthly_budget_exceeded` is defined (errors.py:54) but has ZERO raising sites** — the monthly breach surfaces as the `budget.degraded.entered` log event + degraded-state behavior, never as that error code. README:299's Code cell is half dead-code. → **FILED F-10-6-5** + same-commit README correction.
- **Fix (documented: month rollover or `/budget reset`):** literal `/budget reset` slash form unreachable per FILED F-10-5-1 (prior-evidence, corroborated not re-walked); operator path executed = `reset_degraded_mode` MCP verb (`previously_active: true, "degraded mode exited"`) + restart — the 10-4 pre-run precedent path, now walked end-to-end this session.
- **Recovery + restore:** staging row deleted (month sum honest $70.6156 again), restart re-seeded, `degraded_mode_state.active=0`, real Haiku call flows. **Verdict proposed: PASS (behavior + fix path; Code-cell corrected per F-10-6-5).**

### R11 — `PAUSED` (README:303) — tag: INDUCED — run_id 10-6-r11/2026-07-06

- **Induce:** `mailbot pause` (documented CLI; wraps POST /admin/pause into the SERVER process) → `router paused — reason: manual cli pause`; log event `router.paused`. (CLI reality note: `--reason` flag doesn't exist — reason is fixed "manual cli pause"; README doesn't claim the flag, no finding.)
- **Assert:** chat-lane call refused `{"error": {"type": "router_error", "message": "router paused"}}`; `mailbot status` ROUTER: `paused: yes / since … / reason: manual cli pause` — README's "Check the reason first in mailbot status → ROUTER" surface HOLDS.
- **Code-reality finding:** the refusal's ErrorCode is **`PROVIDER_ERROR`** with message "router paused" (router.py:283-292) — **there is no `PAUSED` error code in errors.py**. README:303's Code cell ("`PAUSED` state") names a state label, not a stable error code; under rule (b) hard-assert the Code cell mismatches the code contract README:289 itself defines. → **FILED F-10-6-6** + same-commit README correction. (Behavioral claims all hold; 10-1 F1/10-5 F-10-5-4 pause-blast-radius corroborated by construction — chat refusals ARE the F1 mechanism.)
- **Fix (documented: `/resume` or `mailbot resume`):** slash form unreachable (F-10-5-1 prior-evidence); **`mailbot resume` executed → "router resumed"** → recovery: calls flow, status paused: no. **Verdict proposed: FAIL on the Code cell / PASS on behavior+fix — net row verdict FAIL (hard-assert rule), fully corrected in README.**

### R10 — `loop_detected` (README:302) — tag: INDUCED — run_id 10-6-r10/2026-07-06

- **Induce:** 12 byte-identical qwen calls through the server (`/v1/chat/completions`, $0): calls 1-10 dispatched, **calls 11-12 refused "prompt hash 3e1c2a64 exceeded loop threshold"** (`LOOP_DETECTED`, >10-in-5-min per limits.py:150-152); log event `router.loop_detected occurrences=12`.
- **Fix (documented: "Stop retrying. /pause, check `mailbot logs --filter level=error`, then /resume"):** executed as chat/CLI equivalents: `mailbot pause` OK → `mailbot logs --filter level=error` — **host-side works but only with `PYTHONIOENCODING=utf-8`** (default Windows cp1252 console crashes with UnicodeDecodeError; in-container it FATALs "docker not found on PATH" — the subcommand shells out to docker, host-side is the intended surface). Windows-host encoding crash → **FILED F-10-6-7** (LOW, host-class-specific). → `mailbot resume` OK.
- **Recovery:** distinct prompt flowed immediately post-resume (window-slide for the same hash not waited out — 5-min slide semantics per limits.py, deterministic).
- **Verdict proposed: PASS (code + choreography; F-10-6-7 filed on the logs step's Windows encoding).**

### R9 — `rate_limited` (README:301) — tag: INDUCED — run_id 10-6-r9/2026-07-06

- **Induce:** distinct-prompt flood on the interactive lane through the server (qwen, $0) — call **45 refused** `"rate limit breached: lane:interactive"` (`LIMIT_INTERACTIVE_PER_HOUR=60`/hr; earlier walk traffic on the lane counted toward the window, so the 60th cumulative — not the 60th of this flood — tripped); log event `router.rate_limited dimension=lane:interactive` at 17:59:52Z.
- **Assert:** breach code + dimension match README:301's "Chat lane: 60 calls/hr". README also documents ingest lane 300/hr + body-reads 5/turn — the interactive lane was the honest cheapest genuine trip; ingest-lane 300 not flooded (disproportionate), body-read-cap covered structurally (5/turn constant, 10-4 C6 walked it at L3). Recorded as scoped-coverage note.
- **Fix (documented: "Wait — the window slides over 60 minutes"):** window-slide is the mechanism (sliding 60-min window, limits.py); post-flood probes succeeded within seconds as older timestamps aged past the window edge — recovery mechanism VERIFIED, full 60-min drain not waited out (honest partial).
- **Anomaly side-effect:** none tripped this flood (below the 3σ hourly threshold for this volume; 10-4/10-5 captured anomaly trips on heavier bursts). **Verdict proposed: PASS.**

## 3. Findings (FILED per N.5, zero fixed)

Per D2/N.5: findings are FILED with evidence, never fixed in this walk. Doc-drift README corrections (rule (a)) are the ONLY edits and are not "fixes" of the underlying defects.

| ID | Sev | Row | Finding | Evidence |
| --- | --- | --- | --- | --- |
| F-10-6-1 | INFO | — | Charter says "17 error rows"; the README table has **16 data rows** (verified at 3 commits). Walked as R1–R16 (17 sub-cases, ≥19 code assertions). Feeds 10-7 verdict-table row count. | §0 reconciliation |
| F-10-6-2 | MEDIUM | R15a | `target_deleted` from a move that soft-deleted the local row is **NOT cleared by the documented `mailbot replay <id>` fix** — replay re-reads the same local soft-delete state and refuses again (deterministic, `_check_tier_1`). Recovery needs local-row repair first (only 10-2 revert rows bypass by design). README:307 fix cell's replay clause is inert for this (common) case. | R15a block; outbox 27+28 |
| F-10-6-3 | HIGH | R3, R13 | `mailbot rederive` **crashes on every invocation** with `KeyError: no adapter registered for 'qwen2.5:3b-instruct-q4_K_M'` — `init_default_adapters()` is called by the FastAPI lifespan + `python -m …pipeline` but never by the `rederive` CLI subcommand. The documented recovery fix in README:295 (and cross-referenced at :305) is broken as written; the actual working recovery is the ingest worker's own "wait a few minutes" pass. | R3 block; rederive run output |
| F-10-6-4 | MEDIUM | R15c | `state_drift_noop` (errors.py:63) has **ZERO raising sites** — unreachable code; README:307 hard-asserts a code that can never surface. | grep across mailbot_api |
| F-10-6-5 | LOW | R7 | `monthly_budget_exceeded` (errors.py:54) has **ZERO raising sites** — the monthly breach surfaces as the `budget.degraded.entered` log + degraded-mode behavior, never that code. README:299 Code cell is half dead-code (`degraded_mode_blocked` IS real). | R7 block; grep |
| F-10-6-6 | LOW | R11 | Paused refusal carries ErrorCode **`PROVIDER_ERROR`** message "router paused", not a `PAUSED` code — README:303's "`PAUSED` state" names a state, and there is no such stable error code (contra README:289's "error codes are stable strings" framing for this row). | R11 block; router.py:283-292 |
| F-10-6-7 | LOW | R10 | `mailbot logs --filter level=error` **crashes on a default Windows console** (`UnicodeDecodeError: cp1252`); needs `PYTHONIOENCODING=utf-8`. Host-class-specific; in-container the subcommand shells to `docker` (absent) and FATALs — the host is the intended surface. | R10 block |

**Corroborated, not re-filed:** F-10-3-1 (estimator month sum ~$70.6 far above the $30 cap — the reason R7 required simulation; the honest-crossing path is unreachable this month); 10-1 F1 / F-10-5-4 (pause blocks chat — R11's refusals ARE that mechanism); 10-1 F5 (move soft-deletes local row — R15a's genuine `target_deleted` rode it); F-10-5-1 (slash-prefix unreachable — R7/R11 fix cells rely on `/budget reset` + `/resume` literals, worked around via verb/CLI).

## 4. Restoration checklist (verified at close)

| Item | Baseline | At close | ✓ |
| --- | --- | --- | --- |
| degraded_mode_state.active | 0 | 0 | ✓ |
| pause_state.paused | 0 | 0 (reason label stale "manual cli pause" — cosmetic, not active) | ✓ |
| oauth_state.consecutive_refresh_failures | 0 | 0 | ✓ |
| synthetic router_calls rows (R7/R8) | 0 | 0 (deleted) | ✓ |
| synthetic pending_actions rows (R14 ×18) | 0 | 0 (deleted) | ✓ |
| synthetic email (R3) + idempotency orphans | absent | deleted (1 email + 5 idempotency) | ✓ |
| E118 sacrificial email | in Inbox, not soft-deleted | in Inbox, deleted_at NULL (archived→restored via R15a real move) | ✓ |
| E117 change_marker (R15b) | …AAj/MUdo | …AAj/MUdo (restored) | ✓ |
| month estimator sum | $70.60 | $70.63 (+$0.03 real walk Haiku, honest) | ✓ |
| open pending actions | 0 | 0 | ✓ |
| containers | 3 healthy | 3 healthy (api restarted ×3 for counter re-seed, all recovered) | ✓ |
| runtime config (policy.user-overrides.yaml etc.) | untouched | untouched | ✓ |

**Retained as audit truth (NOT restored — genuine records):** actions 16/17 (applied archive+restore), 18 (failed etag-drift send), 37 (failed cap send); grants 7-10; 84 `walk-10-6` router_calls rows ($0.0109 estimator-attributable). The two genuinely-failed sends (18, 37) consumed send budget per AR-D5-2 — sends-today 1→3 is real, not synthetic.

**Spend:** $0.0109 estimator-attributable this walk (Haiku recovery micro-calls + R7/R8 crossing calls) — three orders of magnitude under the ~$2-4 that would warrant an Anthropic Console read (10-3 precedent: $0 stories assert against the estimator; Console truth is reserved for real-spend stories per `feedback_anthropic_spend_source_of_truth.md`). Zero Opus.

## 5. Verdict table (feeds Story 10.7)

Per-row PASS = code surfaces as documented AND fix works AND recovers. FAIL = any of those breaks (code corrected in README same-commit).

| Row | Code(s) | Tag | Code surfaces? | Fix works? | Verdict |
| --- | --- | --- | --- | --- | --- |
| R1 | sensitivity_blocks_api / needs_sensitivity_confirmation | INDUCED | ✓ both | token engine ✓ (documented /confirm choreography FILED-broken F-10-5-7, corroborated) | **PASS** |
| R2 | sensitivity_blocks_api (confidential) | INDUCED | ✓ verbatim | by design, nothing to fix | **PASS** |
| R3 | sensitivity_not_classified | INDUCED (synthetic subj) | ✓ | primary "wait" ✓; rederive clause BROKEN (F-10-6-3) | **FAIL** |
| R4 | CONFIDENTIAL_HYDRATION_BLOCKED | INDUCED | ✓ verbatim, zero egress | by design (read in Outlook) | **PASS** |
| R5 | pending_grant (status) | INDUCED | ✓ status verbatim | grant→drain→apply ✓ | **PASS** |
| R6 | per_call_threshold_exceeded | INDUCED | ✓ ($0.3471>$0.20) | trim ✓ + force exists | **PASS** |
| R7 | monthly_budget_exceeded → degraded_mode_blocked | SIMULATED | degraded_mode_blocked ✓; **monthly_budget_exceeded dead-code (F-10-6-5)** | reset verb ✓ | **FAIL** |
| R8 | budget.daily.soft_warn | SIMULATED | ✓ single-fire, non-blocking | informational (nothing to fix) | **PASS** |
| R9 | rate_limited | INDUCED | ✓ lane:interactive | window-slide ✓ (partial wait) | **PASS** |
| R10 | loop_detected | INDUCED | ✓ (>10/5min) | pause→logs→resume ✓ (logs Windows-encoding bug F-10-6-7) | **PASS** |
| R11 | PAUSED | INDUCED | behavior ✓; **code is PROVIDER_ERROR not PAUSED (F-10-6-6)** | resume ✓ | **FAIL** |
| R12 | oauth_refresh_failing | SIMULATED (D3 expensive) | status surface ✓; auto-pause/alert hop cited-not-observed | re-mint partial (token untouched) | **PASS** |
| R13 | schema_validation_failed | INDUCED | ✓ terminal | auto-retry ✓; escalate-to-Haiku prose inaccurate + rederive broken (F-10-6-3) | **PASS** |
| R14 | daily_send_cap_exceeded | SIMULATED | ✓ verbatim, zero dispatch | wait-till-midnight (deterministic) | **PASS** |
| R15a | target_deleted | **INDUCED (genuine)** | ✓ verbatim | replay clause INERT (F-10-6-2); repair+replay works | **FAIL** |
| R15b | state_drift_etag | SIMULATED | ✓ verbatim, zero dispatch | structural (blast-radius safe) | **PASS** |
| R15c | state_drift_noop | n/a | **unreachable (F-10-6-4)** | none possible | **FAIL** |
| R16 | INVALID_ACTION_TYPE | INDUCED | ✓ + valid list + recovery payload | re-issue canonical ✓ | **PASS** |

**Tally: 13 PASS / 5 FAIL / 0 EXCLUDED across 18 verdict rows (16 README rows; R15 = 3 sub-cases R15a/b/c).** The 5 FAIL rows: R3, R7, R11, R15a, R15c. 7 findings FILED (1 HIGH F-10-6-3, 2 MEDIUM F-10-6-2/4, 3 LOW F-10-6-5/6/7, 1 INFO F-10-6-1). Every FAIL is a documentation-contract defect (dead code, broken fix clause, mislabeled code) — zero are product-capability regressions; every error condition that CAN surface, DID surface with a stable code, and every system state recovered.

**Induced-vs-simulated honesty split (D3):** **12 INDUCED** (R1/R2/R4/R5/R6/R9/R10/R11/R13/R16 + R15a genuinely-induced target_deleted + R3 — a real gate refusal on a real-shaped row, only the *subject* synthesized, so tagged "INDUCED (staged synthetic subject)") · **5 SIMULATED** honesty-tagged (R7/R8 staged budget counters, R12 oauth counter, R14 staged send-count, R15b staged marker — each staged a *state*, not just a subject) · R15c n/a (unreachable). No simulated row recorded as induced; R3's synthetic-subject caveat is carried in its own tag rather than counted as a full simulation.

## 6. Proposed AC verdicts (Adam signs at Phase 3.5)

- **AC-1 (per-row protocol): PASS** — all 16 rows induced-or-simulated → code asserted (hard) → documented fix applied → recovery asserted; per-row blocks §2.
- **AC-2 (D3 honesty tagging): PASS** — every row carries an induced-vs-simulated tag; the 5 simulated rows are explicitly tagged with their staging mechanic; R12 (expensive OAuth row) carries the partial-fix + cited-not-observed caveats. No simulated row dressed as induced.
- **AC-3 (verdict table + N.5 + doc-drift): PASS** — §5 names all rows PASS/FAIL (13 PASS / 5 FAIL / 0 EXCLUDED across 18 verdict rows); 7 findings FILED (zero fixed); README corrections applied same-commit for every FAIL (F-10-6-2/3/4/5/6 + R13 prose).
- **AC-4 (CR cadence): PASS** — zero production code touched (README + evidence/tracking only; `scratch/mcp_walk_106.py` is untracked scaffolding). Zero of 6 CR criteria fire → CR skipped per cadence binding.
