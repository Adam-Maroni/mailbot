---
baseline_commit: TBD-at-dev-start
---

# Story 10.7.8: Get qwen to actually invoke `find_emails` with the right args — small correctly-named menu + the `unread_only` argument-population gap

Status: backlog

## Story

**As** the MailBot operator (Adam) relying on the $0 local qwen lane to answer "find my unread emails" on Discord,
**I want** qwen to reliably (a) SELECT the real `find_emails` verb from a small, correctly-named menu (not mis-pick `memory`/`pull_pending_notifications`, hallucinate `email_search`, or mis-bind to the Hermes `turn`/`find_unread_emails` primitive) AND (b) POPULATE the `unread_only: true` argument so the turn returns genuinely-unread mail,
**so that** the clause-3 walk finally produces a usable unread reply at $0 — discharging Epic 10.6 clause 3b (the founding cost thesis's final gate) that Stories 10.7.6 and 10.7.7 each advanced but left OPEN.

## Context & why this story exists (read before implementing)

This is the **clause-3 sequel to 10.7.7**, consolidating three residuals that all block the SAME goal — a faithful qwen→`find_emails(unread_only=true)` Discord turn — but that each prior story proved were outside its own scope:

- **F-10-7-7-W1 (from 10.7.7, the newest + most decisive): Qwen-3B ARGUMENT-population ceiling.** 10.7.7 shipped the runaway guard (proven live) + a real `unread_only` filter capability (migration 029, `is_read` from Graph). But across THREE live walks qwen called `find_emails` with args **`{}`** — empty, `unread_only` never set — and a guard-fire arg-diagnostic (`repeated_args_redacted="{}"`) proved three model-facing description/prompt edits moved it **ZERO**. The 10.7.5 description lever moves tool SELECTION but does NOT move ARGUMENT-population for Qwen-3B. Those prompt edits were REVERTED (bloat degrades a 3B/Q4 context). See `10-7-7-walk-evidence.md` + `story-run-flags.md § 10-7-7 Manual Verification (walks #2 + #3)`.
- **F-10-7-3-R1 (from 10.7.3): per-verb mailbot-api surface scoping is NOT achievable via `platform_toolsets`.** The `hermes-config/config.yaml` allow-list is toolset-granularity (keep/drop whole toolsets); `pull_pending_notifications` (the spike's dominant flat-26 attractor) is registered INSIDE the single `mailbot-api` MCP server, so it can't be dropped without dropping all 26 email verbs including `find_emails`. Getting qwen to a genuinely small email-only menu needs a **mailbot_api-side per-platform verb filter** OR a **hierarchical/tree tool-selection** design (spike §4.2/§6). This is the IN-REPO half.
- **F-10-7-6-R1 (from 10.7.6): the `turn`/`find_unread_emails` mis-binding is a Hermes-side (out-of-repo) primitive.** On an earlier walk qwen derived the correct intent (`{"action":"find_unread_emails"}`) but bound it to the Hermes `turn` control primitive, not the `find_emails` MCP verb. `turn`/`find_unread_emails` are presented by the Hermes agent harness itself (not a configurable toolset, not a mailbot_api verb) — a Hermes-side registration/binding fix. This is the OUT-OF-REPO half.

**The measure-first framing (mirrors the 10.7.0 spike discipline):** these three residuals name three candidate fixes at different layers. This story must NOT blindly implement all three — it opens by **measuring which layer is load-bearing NOW** (the surface has changed since each residual was filed: `messaging` + `memory` toolset states, the reverted 10.7.7 prompts). Task 1 is a live characterization: run the real Discord walk (or the `hermes tools list` resolver + a direct `/v1/chat/completions` probe) and record qwen's ACTUAL failure — which verb it picks, with which args — then pick the cheapest lever that moves it.

**The three candidate levers (Task 1 chooses; do not pre-commit):**

1. **Small correctly-named menu (in-repo, F-10-7-3-R1):** a mailbot_api-side per-platform verb filter so the Discord chat surface exposes a SMALL email-only menu (e.g. `find_emails`, `hydrate_email`, `get_thread`, `count_emails`, `get_sender_summary`) instead of all 26 verbs — removing the `pull_pending_notifications`/notification/digest/cron attractors that the toolset allow-list can't reach. The spike (§4.2 top-split 20/20) suggests a small menu is the SELECTION fix. Does NOT by itself fix the `unread_only` ARG gap.
2. **The unread ARG gap (the F-10-7-7-W1 core):** since prompting won't make Qwen-3B populate `unread_only`, options are (a) a **bigger/better local tool-calling model** that still runs $0 (larger Qwen or a fn-calling-tuned local — the 10.7.4 contingency, re-fires here if a ceiling is confirmed AND the small menu doesn't recover it), OR (b) a **Hermes-side `find_unread_emails`→`find_emails(unread_only=true)` binding** (F-10-7-6-R1) so qwen's natural `find_unread_emails` intent lands on the real verb WITH the arg pre-set — sidestepping the arg-population wall entirely by moving `unread_only` out of the model's hands.
3. **Hermes-side intent binding (out-of-repo, F-10-7-6-R1):** stop offering `turn` as an action-bearing tool on the Discord email surface, and/or bind `find_unread`-style intents to `find_emails`. This is the cleanest fix for BOTH the mis-binding AND the arg gap (option 2b) but lives in `hermes-config`/the Hermes harness, not `mailbot_api`.

**Honest boundary:** option 3 (and possibly option 2a's model swap) may be genuinely out of the `mailbot_api` package. This story's IN-REPO deliverable is the per-platform verb filter (lever 1) + whichever of lever 2 is in-repo; any Hermes-harness change is a companion `hermes-config` deliverable or a filed residual if it can't be done here. The done-gate is the live walk producing a usable unread reply — the same discipline as 10.7.6/10.7.7.

## Acceptance Criteria

**AC-1 — Characterize the CURRENT failure live (measure-first gate).** Before any fix, run the real "find my unread emails" surface (Discord walk OR `hermes tools list --platform discord` + a direct `/v1/chat/completions` tool-call probe on a FRESH Hermes session) and record: which tool qwen selects, with which exact args, and where it fails (wrong verb / hallucinated verb / `turn` mis-bind / right verb + empty args / right verb + `unread_only` but no result render). Pin the finding in Dev Notes. This determines which lever(s) Tasks 2-4 implement — do NOT implement a lever AC-1 doesn't justify.

**AC-2 — Small correctly-named email menu on the Discord chat surface (in-repo, F-10-7-3-R1).** A mailbot_api-side per-platform verb filter exposes a SMALL email-read menu on the chat/Discord surface (the read verbs, NOT the 26-verb flat surface — no `pull_pending_notifications`, no cron/digest/notification verbs). Config/registration-driven + drift-tested. Must NOT drop verbs the chat surface legitimately needs (`find_emails`, `hydrate_email`, `get_thread`, `count_emails`, `get_sender_summary`, plus the operator-control verbs already reachable). Verified against the live resolver, not just offline gates (the 10.7.3 CR lesson: run `hermes tools list`).

**AC-3 — The `unread_only` argument lands (the F-10-7-7-W1 core).** For a "find my unread emails" turn, the dispatched `find_emails` call carries `unread_only: true` — achieved by whichever lever AC-1 justifies: a Hermes-side `find_unread_emails`→`find_emails(unread_only=true)` binding (preferred if in-config reach), OR a bigger local model that populates the arg, OR (last resort, documented) a mailbot_api-side inference at the dispatch seam that sets `unread_only` when the user's latest message is an unread request AND the model sent an empty/no-unread find_emails filter. If the chosen lever is out-of-repo, ship the in-repo half + file the residual precisely (do NOT over-claim a fix, per the 10.7.6 discipline).

**AC-4 — No regression of 10.7.7's runaway guard or unread capability.** The `NO_PROGRESS` turn-termination guard, the `unread_only` filter (migration 029), and the guard arg-diagnostic all still pass their tests. This story adds selection/argument fidelity ON TOP of 10.7.7's fail-closed floor; it must not weaken the guard or the $0-fail-closed invariant. The runaway guard remains the backstop (a worst case stays a bounded $0 stop, never a 26-min loop).

**AC-5 — No selection regression from prior trims.** 10.7.6's `memory` drop + 10.7.3's `messaging` drop stay intact; the offline drift gates from both still pass. If AC-2's per-verb filter changes the surface, the existing `test_hermes_config.py` gates are updated coherently (not weakened).

**AC-6 — Offline tests for every in-repo code path.** The per-platform verb filter, any dispatch-seam arg-inference, and any registration change are covered by offline unit/integration tests (real SQLite where DB touched; no Docker/Discord/Anthropic). Cost-thesis + safety invariants re-verified: $0 on the guard path unchanged; sensitivity/grant gates untouched.

**AC-7 — Clause-3 live walk PASSES (Adam-hands-on, L3, $0) — the done-gate.** A real Discord "find my unread emails" turn produces a **usable unread-emails reply rendered in Discord**, backed by `router_calls` with `model_chosen=qwen2.5:*` (or the chosen $0 local model) AND `find_emails` invoked WITH `unread_only:true` (verified in `tool_calls_summary` or the guard arg-diagnostic), bounded calls, NO paid escalation, no 502, sane wall-clock. **Read the Discord reply, not just router rows** (the 10.7.6/10.7.7 durable lesson). This is the load-bearing clause-3 gate = Epic 10.6 clause 3b. NOT done until Adam signs. On FAIL: record the new dominant defect, re-open.

## Tasks / Subtasks

- [ ] **Task 1 (AC-1): Characterize the current failure live (measure-first).** On a FRESH Hermes session (restart hermes; restart mailbot-api if code changed), run "find my unread emails" and capture qwen's actual pick + args from `router_calls` + the guard `repeated_args_redacted` log + `hermes tools list --platform discord`. Record the exact failure mode + which lever(s) it justifies. HALT-and-decide gate: pick the cheapest lever that AC-1 evidence supports before writing fix code.
- [ ] **Task 2 (AC-2): Implement the small correctly-named email menu (per-platform verb filter).** Add a mailbot_api-side per-platform (chat/Discord) verb-exposure filter to the MCP server so only the email-read menu surfaces on the chat surface. Drift-test the exposed set; verify against the live resolver. (Scope: this is the in-repo F-10-7-3-R1 lever.)
- [ ] **Task 3 (AC-3): Close the `unread_only` argument gap.** Per AC-1's chosen lever: implement the Hermes-side `find_unread_emails`→`find_emails(unread_only=true)` binding (hermes-config companion) OR evaluate/swap a bigger $0 local model OR (last resort) a documented mailbot_api dispatch-seam arg-inference. Whichever is in-repo, test it; whichever is out-of-repo, ship the in-repo half + file the residual precisely.
- [ ] **Task 4 (AC-4, AC-5): Regression guard.** Re-run 10.7.7's guard/unread/arg-diagnostic tests + 10.7.6/10.7.3 drift gates; confirm green. Update `test_hermes_config.py` coherently if AC-2 changed the surface.
- [ ] **Task 5 (AC-6): Full offline test pass + invariant tests.** All in-repo paths covered; $0-on-guard-fire + sensitivity/grant gates asserted untouched.
- [ ] **Task 6 (all offline ACs): Run the 4 gates** — ruff, mypy, boundary checker, pytest full suite. Record counts.
- [ ] **Task 7 (AC-7): Clause-3 live walk (Adam-hands-on, HALT-and-hand-off).** After offline gates green + hermes/mailbot-api restarted + `is_read` seeded (full re-sync if needed), Adam sends "find my unread emails". PASS = usable unread reply rendered + `find_emails(unread_only=true)` invoked + $0 local + no 502. **Read the Discord reply.** Record in `10-7-8-walk-evidence.md`. On FAIL: record new dominant defect, re-open. *(NOT autonomous-run compatible — dev agents HALT here.)*

## Dev Notes

### Root-cause evidence (from the 10.7.7 walks, grep/log-confirmed 2026-07-20)
- **F-10-7-7-W1 decisive log:** guard-fire `repeated_args_redacted="{}"` — qwen sends `find_emails({})`, `unread_only` never set; 3 prompt/description edits moved it zero (REVERTED). `find_emails` never reached the MCP verb across any walk (only `pull_pending_notifications` cron executes); the guard intercepts the repeated tool-call INTENTION at the `/v1/chat/completions` dispatch seam (`router.py` `_max_repeated_tool_invocation` / `dispatch_tool_call`).
- **Chat tool list is Hermes-supplied:** `main.py:856` `tools=request.tools` — mailbot_api does NOT curate the chat surface today; the per-platform filter (AC-2) is new mailbot_api work OR a hermes-config lever.
- **F-10-7-3-R1 boundary:** `hermes-config/config.yaml` `platform_toolsets.discord` is toolset-granularity (config lines ~207-220); `pull_pending_notifications` is intra-`mailbot-api`-MCP (`mcp_server.py`, `_EXPECTED_TOOL_COUNT=26`), untrimmable by the allow-list.
- **F-10-7-6-R1 boundary:** `turn`/`find_unread_emails` are Hermes harness primitives (not toolsets, not mailbot_api verbs — grep-verified absent from `mailbot_api/`); config lines ~191-205.

### Architecture compliance
- MCP verb-surface changes go through `mailbot_api/mcp_server.py` (the 26-verb registration). A per-platform filter is a new registration/exposure lever — keep the FULL verb set available to non-chat callers (cron/worker), filter only the chat/Discord surface.
- Any hermes-config change is a companion deliverable in `hermes-config/config.yaml` (in-repo config, NOT the `mailbot_api` package) — mirror the 10.7.3/10.7.6 drift-test + live-resolver-verify pattern.
- Runaway guard (10.7.7) + sensitivity/grant gates stay exactly as-is (AC-4).

### Files likely to touch
- `mailbot_api/mcp_server.py` — per-platform verb-exposure filter (AC-2).
- `hermes-config/config.yaml` — possible `find_unread_emails` binding / `turn` de-listing (AC-3, companion; out-of-`mailbot_api` but in-repo).
- `mailbot_api/router/router.py` OR `main.py` — last-resort dispatch-seam `unread_only` inference IF AC-1 justifies it (AC-3).
- `tests/integration/test_hermes_config.py` + new tests for the per-platform filter + arg lever.
- `_bmad-output/implementation-artifacts/10-7-8-walk-evidence.md` (new, at walk time).

### Testing requirements
- Offline unit/integration only for the diff (real SQLite where DB touched). Live proof is AC-7's walk (READ THE DISCORD REPLY).
- **MANDATORY-CR** reviewer ≠ dev (tool-surface + dispatch seam + possible cross-repo config = load-bearing). Probe: does the small menu keep every chat-needed verb? does the arg lever actually set `unread_only` (or is it over-claimed)? does the guard/unread capability survive?
- Run `docker exec mailbot-hermes hermes tools list --platform discord` against any config change (the 10.7.3 CR lesson: verify the live resolver, don't infer).

### Run-mode note
Tasks 1-6 are dev-story / autonomous-run compatible (Task 1 has a HALT-and-decide gate for lever selection). **Task 7 (clause-3 walk) is Adam-hands-on and NOT autonomous compatible** — a dev agent HALTS and logs.

### References
- `_bmad-output/implementation-artifacts/10-7-7-walk-evidence.md` — the 3 walks + the F-10-7-7-W1 argument-population-ceiling verdict + the guard arg-diagnostic.
- `_bmad-output/implementation-artifacts/story-run-flags.md` § 10-7-7 Manual Verification (walks #1-#3), § Residual F-10-7-6-R1, § Residual F-10-7-3-R1.
- `hermes-config/config.yaml` (the toolset boundary + prior-trim context, lines ~123-240), `mailbot_api/mcp_server.py` (26-verb registration), `mailbot_api/router/router.py` (guard + dispatch seam), `mailbot_api/main.py:856` (Hermes-supplied tools).
- Memory: `project_10_7_7_turn_termination_guard`, `project_clause3_walk_failed_runaway_loop`, `project_local_model_is_safety_net`, `project_reached_not_equal_usable`, `feedback_live_walk_load_bearing_clause_early`, `feedback_measure_real_tool_surface_at_every_level`, `project_qwen_management_epic_spawned`, `project_qwen_cpu_toolcall_latency`, `feedback_reviewer_model_substitution`.

## Dev Agent Record

### Agent Model Used
_(to be filled by the dev agent)_

### Debug Log References
_(to be filled)_

### Completion Notes List
_(to be filled)_

### File List
_(to be filled)_

### Change Log
- 2026-07-20 — Story DRAFTED (backlog, spec-only) as the clause-3 sequel to 10.7.7, consolidating F-10-7-7-W1 (Qwen-3B argument-population ceiling), F-10-7-3-R1 (per-verb surface scoping / small menu), and F-10-7-6-R1 (Hermes-side find_unread_emails/turn binding). Measure-first (AC-1 characterization gate picks the cheapest lever). In-repo deliverable = per-platform verb filter + whichever arg lever is in-repo; out-of-repo Hermes-harness work filed as residual. Done-gate is the live walk producing a usable unread reply. NOT autonomous compatible (Task 7 halts).
