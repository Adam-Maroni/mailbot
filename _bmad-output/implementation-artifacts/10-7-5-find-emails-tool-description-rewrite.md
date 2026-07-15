---
baseline_commit: 47b5f752d63a3170275da50ec39b29e8436f1c8b
---
# Story 10.7.5: `find_emails` Tool-Description Rewrite (jargon → natural language)

Status: done

## Story

As the **MailBot maintainer paying $0 for the local tool-calling lane**,
I want **`find_emails`'s MCP tool description (and its sibling read-verb descriptions) rewritten from implementation jargon into natural language that names what the tool does in a user's words ("find / list / show / search unread mail")**,
so that **the local `qwen2.5:3b-instruct-q4_K_M` model reliably selects `find_emails` for an inbox-reading turn instead of chatting or mis-picking a sibling — the PRIMARY, measured, $0 fix for the cost thesis's final gate (Epic 10.7 clause 3 / Epic 10.6 clause 3b).**

## Acceptance Criteria

**AC-1 — `find_emails` description is natural-language, no load-bearing jargon.**
The `_TOOL_DESCRIPTIONS["find_emails"]` string in `mailbot_api/mcp_server.py` is rewritten so it:
- Leads with plain-English action verbs a user would say: **find / list / show / search**.
- Explicitly names the domain object as **the user's own email / inbox / unread mail** (the word "unread" appears), NOT "projections".
- Frames `find_emails` as **the primary tool for reading the inbox**.
- No longer leads with implementation jargon — the phrases "email projections" and "Rule J" no longer appear in the `find_emails` description (they were measured harmful in Story 10.7.0 §4.4: they drove qwen to 0/20 selection + a "chat instead of act" failure).

**AC-2 — Cost-relevant constraint is preserved in plain language.**
The 100-result cap (Story 5.2 AC / epics.md line 1887 "Capped at 100 results") is retained but expressed plainly (e.g. "up to 100 at a time"), so the operational contract is not lost even though the jargon framing is gone. `hydrate_email` is still named as the way to get full bodies.

**AC-3 — Sibling read-verb descriptions swept for the same jargon.**
The four sibling read verbs — `count_emails`, `get_thread`, `hydrate_email`, `get_sender_summary` — have their `_TOOL_DESCRIPTIONS` entries reviewed. The "projections / Rule J" jargon that leads each is rewritten to natural language that names what a user asks for (count / conversation-thread / full-body / who-is-this-sender), while preserving each verb's cost-relevant constraint (5/turn cap on `hydrate_email`, count-only on `count_emails`, confidential-refused on `hydrate_email`). `pull_pending_notifications` (the measured dominant distractor) is out of scope for this story's *rewrite* but MUST NOT be made more attractive.

**AC-4 — The tool-registration contract-test is updated to the new contract, not deleted.**
`tests/integration/test_mcp_server.py::test_list_tools_discoverability` currently asserts `find_emails` description contains `"100"` and `"Rule J"`. The `"Rule J"` assertion on `find_emails` is removed (the jargon it guarded is intentionally gone); the `"100"`-cap assertion is retained or replaced with an equivalent plain-language cap assertion; a new positive assertion is added that the `find_emails` description contains a natural-language reading cue (e.g. `"unread"` and/or `"inbox"`/`"find"`). Sibling-verb assertions (`count_emails`/`get_thread` "Rule J", `hydrate_email` "5"/"turn") are updated consistently with the AC-3 rewrite. The `_EXPECTED_TOOL_COUNT` / 26-tool assertions stay green (no tools added or removed).

**AC-5 — No behavior, schema, or wiring change; description string only.**
The verb functions, `FindEmailsFilter`/`FindEmailsOut` schemas, wrapper registration, and the `wrappers == _TOOL_DESCRIPTIONS` fail-fast assertion are unchanged. This is a model-facing *description* change only. `find_emails` still caps at 100, still returns projection-only rows, still logs to `router_calls`. Full suite stays green.

**AC-6 — temp-0 argument fidelity caveat recorded.**
Per Story 10.7.0 §4.3/§4.4 caveat, this description change is verified by direct-ollama drive (out of scope to re-run live here); the story records that a real-N argument-fidelity re-check on the Hermes path is owed at the epic's live-walk gate (clause 3), and does NOT claim clause 3 discharged. This story is *direct-drive* PRIMARY-fix scope only.

## Tasks / Subtasks

- [x] **Task 1 (AC-4, RED): Encode the new description contract as failing tests.** (AC: 4) — updated `test_list_tools_returns_constraint_phrases`; RED confirmed (jargon `find_emails` desc lacks "unread").
  - [ ] In `tests/integration/test_mcp_server.py::test_list_tools_discoverability`, update the `find_emails` assertions: remove `assert "Rule J" in by_name["find_emails"].description`; add `assert "unread" in by_name["find_emails"].description.lower()` and a natural-language-verb assertion (e.g. `"find"`/`"list"`/`"search"` present); keep/adapt the 100-cap assertion in plain-language form.
  - [ ] Add/adjust sibling assertions consistently with the AC-3 rewrite (drop the now-removed "Rule J" literals on `count_emails`/`get_thread` if they are rewritten out; preserve the `hydrate_email` "5"/"turn" cap assertion — that constraint stays).
  - [ ] Run the test; confirm it FAILS for the right reason (old jargon description still present).

- [x] **Task 2 (AC-1, AC-2, GREEN): Rewrite `find_emails` description to natural language.** (AC: 1, 2) — leads find/list/show/search, names "unread"/"inbox", 100-cap preserved plainly, hydrate_email pointer kept; jargon dropped. Test GREEN.
  - [ ] Edit `_TOOL_DESCRIPTIONS["find_emails"]` in `mailbot_api/mcp_server.py`: lead with find/list/show/search; name "unread mail" / "inbox"; frame as the primary inbox-reading tool; keep the ≤100 cap in plain words + the "use hydrate_email for full bodies" pointer; drop "projections" + "Rule J" as leading jargon. Use the Story 10.7.0 §4.4 `realsurface_betterdesc` rewrite as the reference string (it measured 0/20 → 20/20 at the leaf level).
  - [ ] Re-run the Task-1 test; confirm the `find_emails` assertions now PASS.

- [x] **Task 3 (AC-3, GREEN): Sweep sibling read-verb descriptions.** (AC: 3) — count_emails/get_thread/hydrate_email/get_sender_summary rewritten to natural language, constraints (5/turn, count-only, confidential-refused) preserved; pull_pending_notifications left untouched (10.7.3 scope).
  - [ ] Rewrite `count_emails`, `get_thread`, `hydrate_email`, `get_sender_summary` `_TOOL_DESCRIPTIONS` entries: natural-language lead naming the user-facing intent, preserving each cost-relevant constraint. Do NOT make `pull_pending_notifications` more attractive (leave it or, if touched, de-emphasize "pull/unread" overlap — but a rewrite of the distractor is 10.7.3 scope, so prefer leaving it untouched here).
  - [ ] Re-run the Task-1 sibling assertions; confirm PASS.

- [x] **Task 4 (AC-5, REFACTOR + verify): Confirm no wiring/schema/behavior drift.** (AC: 5)
  - [x] `_EXPECTED_TOOL_COUNT == 26` + `set(wrappers) == set(_TOOL_DESCRIPTIONS)` fail-fast unchanged (only values edited, no keys); `len(by_name) == 26` assertion still green.
  - [x] Grepped `mailbot_api` + `tests` for pinned OLD jargon: only `find_emails.py:116` (verb *docstring*, implementer-facing, overridden by `_TOOL_DESCRIPTIONS` at `add_tool` — AC-5 fenced, left as-is) and `hermes-config/skills/mailbot/SKILL.md:54` (Hermes persona file, not the MCP description — out of scope). No broken contract.
  - [x] 4 gates green: ruff (All checks passed), mypy --strict mailbot_api (no issues, 134 files), full pytest **1941 passed / 3 skipped / 3 deselected** (unchanged vs baseline — contract test updated in place, not added).

- [x] **Task 5 (AC-6): Record the direct-drive scope + owed live re-check.** (AC: 6) — recorded in Completion Notes below.

## Review Findings (bmad-code-review, 2026-07-15, reviewer ≠ dev)

Consolidated from parallel adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) + reviewer direct verification. MANDATORY-CR (pre-review §5.12 criterion 3 + 6). Findings appended as unchecked action items; dev to triage.

- [x] **[HIGH] — FIXED.** Swept the read-verb clause in `FastMCP(instructions=...)` from "projection-first per Rule J" to natural language ("let you find, read, and count the user's emails; use find_emails as the primary tool for reading the inbox") + added a rationale comment. Added contract test `test_server_instructions_read_verbs_natural_language` asserting the jargon is gone and find_emails is named primary. This is a description/instruction-string change (AC-5-compatible); File List extended by these two edits (same two files, no new file). Load-bearing catch — the reviewer is right that leaving it would fight the per-tool fix. **[HIGH] Jargon survives one surface up — `FastMCP(instructions=...)` still names all 5 rewritten read verbs as "projection-first per Rule J", untested, reaches the model every session.** `mailbot_api/mcp_server.py:1263-1276` sets the server-level `instructions=` string (a SECOND model-facing surface, distinct from per-tool `description`) to: *"Read verbs (find_emails, hydrate_email, get_thread, count_emails, get_sender_summary) are projection-first per Rule J."* This re-introduces the EXACT jargon ("projection-first", "Rule J") the spike (10-7-0 §4.4) measured as the load-bearing 0/20 selection defect, naming the identical 5 verbs this story just rewrote. It is delivered to the model as server context on every session alongside the tool list, so the story's own thesis (jargon poisons qwen selection) predicts this partially undoes the per-description fix. It was not identified in the story scope/File List and no test guards it (grep: no assertion on the `instructions=` content). This is not strictly an AC violation (AC-1/AC-3 are scoped to `_TOOL_DESCRIPTIONS`), but it is a live gap in the fix's effectiveness and the most concrete finding of this review. Fix: sweep the read-verb sentence in `instructions=` to natural language (or at minimum drop the "projection-first per Rule J" clause for the read verbs) and add a contract assertion. NOTE: this is a description/instruction-string change consistent with AC-5's "no wiring/behavior" fence — but it exceeds the story's literal File List, so triage as either a same-story extension or a fast-follow.

- [x] **[MEDIUM] — FIXED.** Added `assert "Rule J" not in by_name["get_sender_summary"].description` + `assert "sender" in ...` to `test_list_tools_returns_constraint_phrases`. AC-4 now covers all four siblings consistently. **[MEDIUM] AC-4 gap — `get_sender_summary` rewrite has ZERO contract-test coverage.** `mailbot_api/mcp_server.py:1001-1005` rewrites `get_sender_summary` (drops "Rule J"), but `tests/integration/test_mcp_server.py::test_list_tools_returns_constraint_phrases` adds assertions only for `count_emails` (line ~318-320) and `get_thread` (~321-323). Full-file grep confirms NO `by_name["get_sender_summary"]` assertion anywhere. AC-3 claims all four siblings swept + AC-4 says "sibling-verb assertions updated consistently with the AC-3 rewrite" — not true for `get_sender_summary`: its jargon-removal and purpose-word are unguarded against regression. Fix: add `assert "Rule J" not in by_name["get_sender_summary"].description` + a purpose-word assert (e.g. `"sender"`).

- [x] **[MEDIUM] — FIXED.** Reworded `count_emails` to drop the "unread" collision: now "how many from a sender, how many since a date... return only the number... to actually see or read the emails, use find_emails instead." Removes the shared "unread" noun and adds an explicit find_emails redirect, sharpening the hierarchy. **[MEDIUM] AC-3 / dev-escalation — `count_emails` description duplicates the "unread" trigger token that the test treats as `find_emails`'s distinguishing cue.** `count_emails` new text (`mcp_server.py:997-998`) reads "...how many unread, how many from a sender...", while `find_emails` (`:978-983`) leads on "unread mail" and the test (`test_mcp_server.py:307`) asserts `"unread"` as find_emails's natural-language reading cue. The `count_emails` disambiguator ("without listing them... 'how many' rather than to see") is present, but a noisy turn ("show me my unread") now has keyword overlap on "unread" across both descriptions — a plausible mis-pick vector. This is precisely the dev's own §3/§4 MEDIUM escalation; the stated mitigation scopes by "how many" vs "see" but does NOT acknowledge the shared "unread" noun in the distractor. Neither the fix nor the risk is spike-measured. Fix (optional/judgment): reword the `count_emails` example to avoid the "unread" collision (e.g. "how many are still unopened, how many from a sender"), OR accept-with-rationale and record that the sibling hierarchy is unmeasured pending the clause-3 live walk.

- [x] **[LOW] — ACCEPT/DEFER.** `compose_digest` is Hermes-cron-invoked (`no_agent=True`); an agent never tool-selects it, so its "Rule J" wording cannot poison qwen selection. Correctly out of this story's AC-3 sweep (read-verbs only). Left untouched; noted for a future full jargon sweep if one is ever scoped. **[LOW] Residual "Rule J" in `compose_digest` description (out of AC-3 sweep list).** `mcp_server.py` `_TOOL_DESCRIPTIONS["compose_digest"]` still reads "Cached projections only (Rule J + Rule A); no LLM call." Not in the 4-verb AC-3 sweep and `compose_digest` is Hermes-cron-invoked (`no_agent=True`), so an agent never tool-selects it — plausibly correctly out of scope. Flag only so a future jargon sweep doesn't miss it. ACCEPT-or-defer.

- [x] **[LOW] — ACCEPT (note only).** Persona files (`AGENTS.md`/`SKILL.md`) + their guardian test `test_hermes_persona_files.py:66` are correctly scope-fenced (human-facing persona, not MCP tool descriptions). Recorded as a forward dependency for any later persona-jargon sweep. No change this story. **[LOW] `hermes-config/AGENTS.md` + `SKILL.md` retain "Rule J" jargon; a positive guardian test pins it.** Explicitly scope-fenced by the dev (persona files, not MCP descriptions). `tests/integration/test_hermes_persona_files.py:66` positively asserts `"Rule J — Hydration Discipline"` remains in `AGENTS.md`. Forward dependency: a later story sweeping jargon from the persona files must also update that guardian test. Note only, not a defect in this diff.

- [x] **[LOW] — ACCEPT WITH RATIONALE.** AC-2 (cap "expressed plainly") is satisfied; the reviewer agrees this is a precision note, not a violation. "up to 100 at a time" is defensible because a real re-query path exists (`since` filter). Not adding cursor/pagination language — over-specifying the re-query mechanism to a 3B model risks more confusion than it removes, and the verb's LIMIT_EXCEEDED message already names the `since` path if the model hits the cap. **[LOW] AC-2 — "up to 100 at a time" backing mechanism is a `since`-filtered re-query, not pagination, and the description omits it.** The verb (`mailbot_api/verbs/find_emails.py:121-128`) caps at 100 with message "...use repeated queries with the `since` filter if you need more". So "at a time" is defensible (a real "call again" path exists) but the description never names the `since`-filter re-query, leaving a model to infer a non-existent cursor/pagination. AC-2 (cap "expressed plainly") is satisfied — this is a precision/optional-clarity note, not a violation. Fix (optional): either drop "at a time" or add a one-clause hint that "more" means a narrower/`since`-filtered re-query.

- [x] **AC-1 VERIFIED CLEAN** — `find_emails` leads find/list/show/search, contains "unread", frames as "primary tool for reading the inbox", no "email projections"/"Rule J" (test `"Rule J" not in` / `"projection" not in` asserts pass).
- [x] **AC-2 VERIFIED** — "100" present in `find_emails` desc; hydrate_email pointer retained.
- [x] **AC-3 hydrate_email VERIFIED** — new desc preserves BOTH "5 opens per chat turn" AND "confidential emails are refused"; `pull_pending_notifications` untouched by the diff (scope-fence honored, not made more attractive).
- [x] **AC-5 VERIFIED CLEAN** — `git diff --stat` = only `mcp_server.py` + `test_mcp_server.py`; every non-comment changed line in `mcp_server.py` is inside a `_TOOL_DESCRIPTIONS` string value. No verb/schema/wrapper/fail-fast/`_EXPECTED_TOOL_COUNT` change. Description strings only.
- [x] **AC-6 VERIFIED** — Completion Notes scope this as direct-ollama-drive only; explicitly state clause 3 (live Discord qwen→find_emails turn) + real-N arg-fidelity re-check remain owed; flat-26 still 0/N. No overclaim.
- [x] **Fail-fast + verb enforcement VERIFIED CLEAN** — `assert len(wrappers)==_EXPECTED_TOOL_COUNT` and `set(wrappers)==set(_TOOL_DESCRIPTIONS)` (`mcp_server.py:~1290-1295`) still hold (values-only edit); `_EXPECTED_TOOL_COUNT=26` unchanged. Verb caps independent of wording: `find_emails.py` `_MAX_LIMIT=100`→`LIMIT_EXCEEDED`; `hydrate_email.py` `_HYDRATION_LIMIT_PER_SESSION=5`→`HYDRATE_RATE_LIMITED` + `CONFIDENTIAL_HYDRATION_BLOCKED` all still enforced.
- [x] **No second `_TOOL_DESCRIPTIONS` consumer** — single read site at the `add_tool` loop; no doc-gen / prompt-builder reuse. No stale `_TOOL_DESCRIPTIONS`-string assertions elsewhere in `tests/` (other "Rule J"/"projection" test hits are `EmailProjection` data-shape tests, unrelated).

## Dev Notes

**Technical requirements**
- Stack: Python 3.12, FastMCP tool registration. The load-bearing surface is the module-level `_TOOL_DESCRIPTIONS: dict[str, str]` in `mailbot_api/mcp_server.py` (lines ~968-1114). Each entry is applied at `server.add_tool(wrapper, name=tool_name, description=description)` (line ~1284). This description string is exactly what the model sees on its function list — it IS the model-facing contract (why MANDATORY-CR reviewer ≠ dev applies: a description change is a contract change).
- `$0` change: no new dependency, no migration, no schema, no env var. Pure string edit + test-contract update.

**Architecture compliance**
- Files to touch: `mailbot_api/mcp_server.py` (`_TOOL_DESCRIPTIONS` only) and `tests/integration/test_mcp_server.py` (`test_list_tools_discoverability` assertions). No verb-function, schema, wrapper, or lifespan change.
- The `find_emails` wrapper (`mcp_server.py:270-286`) and `_find_emails` verb (`mailbot_api/verbs/find_emails.py`) are UNCHANGED. The 100-cap is enforced in the verb (LIMIT_EXCEEDED error-as-data), independent of the description wording — so dropping "100/Rule J" *jargon* from the description does not relax the actual cap.
- The `wrappers == _TOOL_DESCRIPTIONS` fail-fast (`:1278`) means every key must stay present; this story edits values, never keys.

**Why this is the fix (Story 10.7.0 §4.4, measured):**
- On the real 5-tool `email_reading` leaf surface, qwen with `find_emails`'s *jargon* description = **0/20** (picked siblings or chatted instead of acting). Swap in the natural-language rewrite → **20/20 with NO system prompt at all** (and the strong/hygiene prompts add nothing on top). "The jargon description was the load-bearing defect, not the prompt." The `pull_pending_notifications` distractor's dominance on the *flat 26-tool* surface is a separate lever owned by 10.7.3 (surface trim) — NOT this story.
- Reference rewrite string: the `realsurface_betterdesc` / `leaf_desc` string from `scratch/qwen_toolcall_spike_107.py` — natural language: "find / list / show / search … unread mail … primary tool for reading the inbox." Keep the ≤100 cap + hydrate_email pointer.

**Testing requirements**
- Framework: pytest; the contract test is `tests/integration/test_mcp_server.py::test_list_tools_discoverability`. It boots a real FastMCP server + client session and asserts on `list_tools()` descriptions — a real integration boundary (satisfies the MailBot Router-contract framing of Step 2.4.7: the MCP tool surface is exercised via a real `build_mcp_server` + connected client, not a mock).
- The 4 gates: ruff, mypy `--strict mailbot_api`, boundary (ruff-covered), full pytest (`-q`, live marker auto-excluded).

**Scope fences**
- Do NOT rewrite `pull_pending_notifications` to be *less* attractive here — that is a de-attractor / surface-trim concern owned by 10.7.3. This story only makes `find_emails` (+ read siblings) *more* correctly attractive.
- Do NOT add a system prompt (10.7.2, DEMOTED/optional) or a rescue parser (10.7.1, defensive). PRIMARY description fix only.
- Do NOT touch temperature or the arg-fidelity path (`models.py:596-628`); temp-0 stays load-bearing.

### References
- `_bmad-output/planning-artifacts/epics.md` § Epic 10.7 Detail (lines 4343-4390) — epic identity, 4-clause done-flip gate, clause 3 = load-bearing.
- `_bmad-output/implementation-artifacts/10-7-0-spike-finding.md` §1, §4.4 (the combined-lever leaf probe proving description-alone = 20/20), §4.3 arg-fidelity caveat.
- `mailbot_api/mcp_server.py:968-1114` (`_TOOL_DESCRIPTIONS`), `:1282-1284` (application), `:270-361` (read-verb wrappers).
- `tests/integration/test_mcp_server.py:285-328` (`test_list_tools_discoverability` — the contract test to update).
- `scratch/10-7-0-tool-descriptions.txt` (the exact jargon strings the spike measured).
- Memory: `feedback_reviewer_model_substitution` (MANDATORY-CR reviewer ≠ dev), `feedback_measure_real_tool_surface_at_every_level` (Story 10.7.0 lesson), `project_local_model_is_safety_net`.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (autonomous-story-run, dev)

### Debug Log References

- Contract test in `tests/integration/test_mcp_server.py` is named `test_list_tools_returns_constraint_phrases` (not `..._discoverability` as the story task text guessed); RED/GREEN run against the correct name.
- The MCP tool description shown to the model comes from `_TOOL_DESCRIPTIONS` applied at `server.add_tool(wrapper, name=..., description=...)` (`mcp_server.py:1282-1284`), which overrides the verb function docstring. Confirmed this is why editing only `_TOOL_DESCRIPTIONS` (not the verb docstrings) is sufficient and correct for a model-facing change.
- Grep for pinned OLD jargon surfaced only `find_emails.py:116` (verb docstring — overridden, AC-5-fenced) and `hermes-config/skills/mailbot/SKILL.md:54` (persona file, not a tool description) — neither is a broken contract.

### Completion Notes List

- **AC-1** ✓ — `_TOOL_DESCRIPTIONS["find_emails"]` rewritten to lead with "Find, list, show, or search the user's emails — the primary tool for reading the inbox, including unread mail." Names "unread"/"inbox", uses plain action verbs, drops "email projections" + "Rule J" jargon.
- **AC-2** ✓ — 100-cap preserved in plain language ("up to 100 at a time"); "call hydrate_email for a full body" pointer retained.
- **AC-3** ✓ — `count_emails`, `get_thread`, `hydrate_email`, `get_sender_summary` swept to natural language; each cost-relevant constraint preserved (5-opens/turn + confidential-refused on hydrate_email; count-only on count_emails). `pull_pending_notifications` deliberately left untouched (de-attractor/surface-trim is 10.7.3 scope; not made more attractive).
- **AC-4** ✓ — `test_list_tools_returns_constraint_phrases` updated to the new contract: removed the `find_emails` "Rule J" assertion, added `"unread"` + natural-verb + `"projection" not in` assertions, kept the "100" cap assertion; sibling "Rule J" literals dropped and replaced with purpose-word assertions (`"count"`, `"thread"`); hydrate_email "5"/"turn" preserved. 26-tool count assertion still green.
- **AC-5** ✓ — description strings only. Verb functions, `FindEmailsFilter`/`FindEmailsOut` schemas, wrappers, and the `wrappers == _TOOL_DESCRIPTIONS` fail-fast unchanged. Full suite unchanged at 1941 passed (contract test edited in place, not added). 4 gates green.
- **Phase 3.5 (2026-07-15)** — PASS WITH FINDINGS. Self-driven CP-1..6 all PASS + a live leaf-selection probe (`scratch/10-7-5-verify-live-leaf.py`) got **12/12** correct on the real qwen with the shipped descriptions (reproduces spike §4.4). Adam-typed Discord walk surfaced **WALK-10-7-5-F1**: qwen emitted `<tool_call>{memory…}</tool_call>` as TEXT (`router_calls id=15022`, `model_chosen=qwen2.5:3b`, `tool_calls_count=0`) — the FORMAT defect (F-10-6-5-W1 #2), reproduced live a 2nd time on the Hermes path. This belongs to **10.7.1 (rescue parser, now CONFIRMED-NEEDED)**, fires upstream of this story's description lever, and does NOT regress 10-7-5. Clause 3 stays OPEN (needs 10.7.1 + 10.7.3 then re-walk). Full detail in story-run-flags.md § "Story 10-7-5 Manual Verification".
- **AC-6** ✓ (scope honesty) — This is the Story 10.7.0 §4.4 **PRIMARY description fix**, measured **0/20 → 20/20** at the 5-tool `email_reading` leaf level via **direct-ollama drive** (`scratch/qwen_toolcall_spike_107.py` `leaf_desc` cell). This story does **NOT** discharge Epic 10.7 clause 3 (a live Discord turn with `model_chosen=qwen2.5:*` AND `tool_calls_count≥1` invoking `find_emails`) — that is the load-bearing Adam-hands-on L3 walk, still owed. A real-N temp-0 **argument-fidelity re-check on the Hermes path** is also owed at that walk (§4.3 caveat: the spike's arg-fidelity was a 3-sample spot-check, not an SLA). The flat-26 surface still fails 0/N (§1) — getting qwen to a *small menu* (surface trim / tree) is 10.7.3's remaining engineering, not this story.

### File List

- `mailbot_api/mcp_server.py` — modified (`_TOOL_DESCRIPTIONS`: rewrote `find_emails` + 4 sibling read-verb descriptions from jargon to natural language + rationale comment; **CR-fix**: swept the read-verb clause in the server-level `FastMCP(instructions=...)` string from "projection-first per Rule J" to natural language + reworded `count_emails` to drop the "unread" collision).
- `tests/integration/test_mcp_server.py` — modified (`test_list_tools_returns_constraint_phrases`: updated the description-contract assertions to the new natural-language contract; **CR-fix**: added `get_sender_summary` assertions + new `test_server_instructions_read_verbs_natural_language` guarding the instructions-string jargon sweep).
- `_bmad-output/implementation-artifacts/10-7-5-find-emails-tool-description-rewrite.md` — added (this story file).
- `_bmad-output/implementation-artifacts/10-7-5-find-emails-tool-description-rewrite.pre-review.md` — added (pre-review self-audit).

### Change Log

- 2026-07-15 — Rewrote `find_emails` (+ 4 sibling read-verb) MCP tool descriptions from implementation jargon to natural language, the Story 10.7.0 §4.4-measured PRIMARY $0 fix for local-qwen tool selection; updated the discoverability contract test to match. No schema/wiring/behavior change; 4 gates green (1941 passed).
- 2026-07-15 (MANDATORY-CR, reviewer sonnet-5 ≠ dev opus-4-8) — 3 actionable findings applied (100%): [HIGH] swept the same read-verb jargon out of the server-level `FastMCP(instructions=...)` string (a 2nd model-facing surface, was untested) + new guard test; [MEDIUM] added `get_sender_summary` contract-test coverage; [MEDIUM] reworded `count_emails` to remove the "unread" trigger collision with `find_emails`. 3 LOW findings ACCEPT/defer (out-of-scope persona files + cron-only `compose_digest` + AC-2 precision note). Suite 1941 → **1942 passed** (+1 new test); ruff+mypy clean.
