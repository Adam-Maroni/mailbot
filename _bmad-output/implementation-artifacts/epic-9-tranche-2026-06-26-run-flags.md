# Epic 9 Tranche Run Flags — 2026-06-26

**Run scope:** scoped tranche Stories 9-4 + 9-10 (per Adam-confirmed scope at /autonomous-epic-run kickoff 2026-06-26, mirroring the original tranche scope established 2026-06-13: 9-1 / 9-2 / 9-3 / 9-4 / 9-10).

**Run result:** both stories `done`. Epic 9 stays `in-progress` (parked tranche 9-5..9-9, 9-11 unchanged).

**Dev model:** `claude-opus-4-7[1m]`
**Review model:** `claude-sonnet-4-6` (Story 9-4 MANDATORY-CR pass)

---

## Per-story summary

| Story | Status | Tests Δ | Cumulative | CR rounds | Findings | Applied | Rate |
|-------|--------|---------|------------|-----------|----------|---------|------|
| 9-4 | done | +33 | 1370+2+3 | 1 (sonnet-4-6) | 6 (1H+3M+2L) | 4/5 actionable Patches | **80%** |
| 9-10 | done | +7 | 1377+2+3 | 0 (CR skipped per §5.12 GATE-COVERAGE-ELIGIBLE) | 0 reviewer / 5 dev-self-caught | 1 FIX NOW + 2 DOCUMENT + 2 ACCEPT | N/A — gate-coverage cadence |

**Combined tranche delta:** +40 net tests across both stories vs Story 9-3 done-flip baseline (1337 → 1377).

---

## Aggregated `[deferred:*]` items

### From Story 9-4

- **CR-F4 MEDIUM → [deferred: ruff project config enforces split-import style; consolidation requires separate tooling story]** — `mcp_server.py` has multiple `from mailbot_api.verbs.router_control import (...)` blocks (one per symbol) rather than one consolidated block. The reviewer (sonnet-4-6) flagged this as preferred consolidation; ruff's auto-fix immediately reverted the consolidation back to the project-wide single-symbol-per-block style. The fragmentation is the project's preferred formatter shape, not a Story-9-4 introduction. **Action carry-forward:** if Adam wants consolidated imports, file a separate ruff-config tooling story.
- **CR-F6 LOW → [deferred: theoretical fd-leak on Windows; Linux-only deployment makes non-actionable]** — `write_user_overrides_atomic` wraps `tmp_fd` in a `with os.fdopen(...)` context; if `os.fdopen` raised before the context entered (theoretically possible on Windows if the mode string is rejected), `tmp_fd` would leak. POSIX `mkstemp` fd + `"w"` mode makes the failure mode effectively impossible on Linux. **Action carry-forward:** revisit if MailBot ever ships Windows-native support.

### From Story 9-10

- **MEDIUM finding (dev-self-caught) → [accepted-with-rationale: scope expansion to fix pre-existing SKILL.md docs drift]** — Story 9-10's mid-pass surfaced 5 MCP-registered tools mentioned in SKILL.md prose but lacking `### <tool_name>` headings. Fix was to add the 5 missing sections (the principled fix per the fixture's "When NOT to add to exempt list" criteria) rather than ship a known-failing test on already-drifted docs. This is exactly the failure mode Story 9-10 is designed to prevent recurring. **Action carry-forward:** none — the fix is correctly inline with the test introduction.
- **LOW finding (dev-self-caught) → [accepted-with-rationale: safe-by-default exemption-fixture parser]** — `_load_exempt_set()` silently returns empty set on malformed YAML rather than raising. Failure mode is safe-by-default (forward-drift treats all tools as needing SKILL.md entries). **Action carry-forward:** none.

### From Story 9-1-5 (F35 closure)

- **CR-F5 LOW → [deferred: pre-existing risk profile of real-FS integration tests]** — `test_baseline_edit_after_delete_resumes_policy_reloaded` asserts exactly `len(reloaded_events) == 1` after 0.5s hold; on some CI filesystem backends watchfiles fires double-write events on a single write. The existing Story 9-1 baseline tests use `>= 1` for this reason. **Action carry-forward:** if Story 9-1.5's exact-count assertion fails on CI, relax to `>= 1` matching the Story 9-1 baseline pattern.
- **CR-F6 LOW → [deferred: pre-existing risk profile of real-FS integration tests]** — `test_recreating_override_at_runtime_does_not_auto_pickup` asserts `len(swap_events) == 0` after a 2-second hold but does not recheck post-`stop_event.set()`; any late-arriving watchfiles event between the assertion and teardown is invisible. Not a production defect; test-coverage blind-spot. **Action carry-forward:** if test flakes on CI, add a post-stop_event assertion.

---

## UX advisory

**N/A** — project has no graphical frontend per PORTING.md. The equivalent quality gate (real-user walk on Discord-rendered text) is Phase 3.5 manual verification, which itself is **not firing this run** because Epic 9 doesn't enter epic-done state (parked tranche).

---

## Self-grading scorecard

- ☑ **A1** — UI scope check passed for every story (N/A per PORTING.md, applied uniformly)
- ☑ **A2** — end-of-epic dev-env verification (N/A per PORTING.md — no `<dev-env-skill>` configured)
- ☑ **A4** — this `<flags-file>` exists with all `[deferred:*]` items aggregated
- ☑ **A5** — issues-found-vs-applied tracked per story (Story 9-4: 80% applied; Story 9-10: gate-coverage cadence, N/A)
- ☑ **A7** — UX advisory N/A per PORTING.md
- ☑ **B1** — File-List-vs-git gate (Step 2.4.6) passed cleanly for both stories
- ☐ **B2** — Phase 3.5 manual-verification gate — **DOES NOT FIRE THIS RUN** because Epic 9 stays `in-progress` (parked tranche 9-5..9-9, 9-11 unchanged per Adam's 2026-06-13/2026-06-26 scope decision). The autonomous-epic-run skill's Phase 3.5 is end-of-epic-scoped, not end-of-tranche-scoped. The standalone tranche scope means epic-done flip is not reached.

---

## Architectural-impossibility discharges (precedent chain)

This tranche extended the Story 9-3 OQ-2 architectural-impossibility precedent to 2 more stories:

- **Story 9-3 OQ-2 (2026-06-16):** AC-4 `slash_commands` YAML block discharged — SKILL.md docs only + verb MCP-dispatchability.
- **Story 9-4 OQ-1 (2026-06-26):** AC-4 same shape — extended SKILL.md docs only; `hermes-config/config.yaml` OQ-2 comment block extended with Story 9-4 note.
- **Story 9-10 OQ-1 (2026-06-26 — Path γ reframing):** entire original story discharged — reframed as MCP-tool-registry-vs-SKILL.md drift test using the architecturally-correct surface. epics.md AC block annotated.

All 3 discharges follow the same pattern: identify the architectural impossibility (`test_hermes_config_discord_at_top_level_not_under_gateway` forbids `discord.slash_commands` per RECONCILIATION-NOTES §1.4/§1.5); scope-reduce or reframe; annotate epics.md pointing to the story-file discharge.

**Action recommendation for the eventual Epic 9 retro:** consider promoting "OQ-discharge annotation in epics.md" to a standing CR cadence v2 criterion. The pattern emerged 3 times across the tranche.

---

## Permission-prompt summary

No permission log configured on this project — count of mid-run prompts unknown. Subjectively: the run completed without permission-friction-driven derailing. The pre-flight Step 0.0 envelope check at run start identified the relevant command shapes (`rtk git *` / `.venv/Scripts/python.exe *` / `python scripts/check_boundaries.py`) as covered.

---

## Recommendations for next retrospective

1. **Architectural-impossibility discharge precedent — promote to standing criterion.** 3 cases in 4 stories (9-3, 9-4, 9-10) suggests this pattern is now a known shape, not an emergent surprise. CR cadence v2 could include "if a story discharges an AC as architecturally-impossible, verify the discharge is annotated in epics.md before flipping to done."

2. **SKILL.md docs drift was pre-existing.** 5 MCP tools shipped without per-tool `### <tool_name>` headings prior to Story 9-10. Story 9-10's drift test is now the standing sentinel — future verb additions will fire CI before merge.

3. **The Epic 9 tranche scope decision is paying off operationally.** The 5-story tranche (9-1 / 9-2 / 9-3 / 9-4 / 9-10) ships the entire `/model` user-facing surface + the drift sentinel that catches future verb-registration regressions, without needing the parked benchmark tranche's preconditions. Adam's parking decision (2026-06-07 party-mode + 2026-06-13 tranche kickoff + 2026-06-26 tranche close) sequenced this cleanly.

4. **Epic 9 stays in-progress.** The benchmark tranche (9-5..9-9, 9-11) is now the only outstanding work blocking the epic done-flip. The three Adam-decision gates remain: corpus authoring (3-5 hours manual labor), cohort_key composition (15-min decision), real-Anthropic spend authorization ($11-14). When all three resolve, a future /autonomous-epic-run on Epic 9 can drain the remainder.
