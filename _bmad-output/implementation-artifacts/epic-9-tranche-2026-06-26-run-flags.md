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

### Story 9-5 run-mode deviation from A4

The tranche retro § 6 A4 (2026-06-26) envisioned **post-merge solo labeling**: Adam labels the corpus on his host after the story merges. Story 9-5's AC-15 (added 2026-06-27 per Adam-decision before dev pass kickoff) **supersedes** that envisioning with a **live co-pilot session** model: labeling happens during the dev-story conversation as a structured 3-round walkthrough (corpus / reference-slice / anchors) with the agent guiding process (NOT label content per AC-6.5) and CSV worksheets as the Adam-facing surface.

**Why the deviation:**

- Post-merge solo labeling has no agent context — Adam loses the AC-15 step-by-step structure + invariant reminders + reject-loop debugging.
- AC-15 step 15 (anchor `model_output` source mode a/b/c) needs Adam-decision-at-runtime with agent assistance, not solo deliberation.
- Resumability is built into AC-15 § "Resumability" so the time-commitment ambiguity (~2-3h spread across sittings) doesn't trap the agent in one long conversation.

**Cost of the deviation:**

- Story 9-5 becomes **NOT compatible with `/autonomous-epic-run`** — the epic-run loop would start Story 9-6 before AC-15 completes; Story 9-6 (benchmark runner) directly consumes the corpus + anchors AC-15 produces, so a partial-corpus state is a contract violation.
- The story-file run-mode banner at the top documents this restriction; `docs/eval-corpus.md` § 12 documents it for posterity.

**Carry-forward for Epic 9 retro:** consider whether future Adam-in-the-loop labeling stories should adopt AC-15's pattern (CSV-driven worksheets + `_reviewed_*` tick-columns + AC-6.5 stdout sanitization + resumability state file) as a standing template.

### Story 9-5 AC-15 amendment 2026-06-27 (LLM-recommendations mode)

**Contract amendment Adam-decided 2026-06-27 during AC-15 dev pass.**

Original AC-6.5 forbade the agent from: (a) reading `evals/_labeling/*.csv` worksheets directly, (b) proposing `class_coarse` / `class_fine` / `sensitivity` / `summary_short_anchor` / `importance_score` / `actions` / `category` values for any corpus item. Original Dev Notes (story file lines 457-461) required Adam-by-hand labeling on the explicit rationale: *"the scorer in Story 9.7 compares pipeline output against `labels.*` — if `labels.*` IS pipeline output, the scorer is comparing the pipeline to itself."*

**Adam-decision 2026-06-27 amended this** with the explicit verdict "forget about the benchmark, we will move with LLM recommendations." Per that amendment:

- The agent reads the worksheet directly and writes label proposals into all 7 fields (`category`, `class_coarse`, `class_fine`, `sensitivity`, `summary_short_anchor`, `importance_score`, `actions`) via heuristic functions over subject + body content.
- The agent fabricates synthetic 3-turn dialogs for the reference-resolution slice (Round 2) — `expected_resolved_email_ids` points to a single candidate per dialog.
- The agent fabricates `model_output` strings + per-axis scores + rationales for both anchor sets (Round 3, mode (c) — synthetic, no real-spend dispatch).
- `_reviewed_*` is ticked TRUE for every populated label per the AC-6.5 amendment.
- `source_note` documents the LLM-recommendation provenance per row.

**Cost of the amendment:**

- The benchmark Story 9.7 now measures pipeline-LLM-vs-labeler-LLM agreement, NOT pipeline-LLM-vs-Adam-judgment. The original circular-grading concern is restored — the scorer measures whether the routing pipeline's LLMs agree with my LLM, not whether they agree with Adam's judgment. Whatever Story 9.7 reports will reflect LLM consensus, not Adam's ground truth.
- The anchor calibration is similarly LLM-vs-LLM. Story 9.11's anchor stability audit will measure whether a secondary evaluator LLM agrees with the labeler LLM's anchors, again not Adam's judgment.
- Story 9.9's report renderer + sample-size gate are unaffected — they're statistical, not judgment-dependent.

**Why Adam accepted this cost:** the alternative was hand-labeling 113 corpus items + 20 reference-slice dialogs + 40 anchors (~2-3h Adam-wall-clock per AC-15 budget), and Adam explicitly said "forget about the benchmark" during the session.

The amendment is NOT retroactively documented in the story file ACs (the story file remains the source of truth for what was contracted before the amendment); it IS documented here as the Epic 9 retro-input record. Future stories that read the corpus should treat the labels as "LLM-recommended" not "Adam-authored" for any judgment-sensitive analysis.

### Story 9-5 walk-discovered findings (Round 1-3)

Three load-bearing defects surfaced during the AC-15 dev walk:

- **Anonymizer self-match bug (HIGH)** — original template `<email-NNN@example.com>` was itself email-shaped, so `validate --strict` flagged every anonymized email as a PII regex match. Fixed in-session: template changed to `<email-NNN-redacted>` (no `@`, no `.com`) which is regex-immune. `evals/anonymizer.py` + `tests/unit/evals/test_anonymizer.py` updated. Affects existing corpora using the old template (none in production yet — Story 9-5 is the first user). Pre-existing CR pass under sonnet-4-6 did not catch this because the test suite asserted on the old template shape (the regex-flags-its-own-output dynamic only surfaces when the anonymizer runs in production AND `validate --strict` is invoked on the result; the dev tests don't have that combined surface). **Action carry-forward:** add a regression test to `test_corpus_integrity.py` that round-trips a PII-containing string through `anonymize()` then asserts `validate --strict`-equivalent (anonymizer regex over output) finds zero matches.

- **Docker Compose bind-mount file-vs-directory gotcha (MEDIUM)** — `docker-compose.yml` line 95 declares `./evals/email_corpus_v1.jsonl:/app/evals/email_corpus_v1.jsonl:ro`. When the host file doesn't exist at container-start, Compose creates it as an empty DIRECTORY (not a file). When the operator later replaces the directory with a file, Docker's mount layer caches the old type and refuses to start the container with "not a directory" error. Workaround: `docker compose rm -f <service>` to force Docker to re-read the source type. This is the EXACT pattern Story 9.1's `docker-compose.yml` comment for `policy.user-overrides.yaml` warned about — but the warning lives in a comment block on a different line, so I didn't see it preventively. **Action carry-forward:** add the same warning comment block adjacent to the new Story 9-5 bind-mount lines + consider a `setup_vps.sh` step that `touch`-es both corpus + anchor target files before first `docker compose up`.

- **`scripts/_propose_labels.py` / `_propose_reference_slice.py` / `_propose_anchors.py` need `sys.path` injection (LOW)** — same pattern as the pre-existing `scripts/mint_refresh_token.py` gap. The 3 propose-helpers were authored during AC-15 + needed `_PROJECT_ROOT` injection to import from `evals/` (`from evals.corpus_schema import load_corpus`). Fixed in-session for each. **Action carry-forward:** consolidate into the same housekeeping task as the `mint_refresh_token` fix; apply uniformly to all `scripts/*.py` that import from `mailbot_api/` or `evals/`.

- **Anchor file naming inconsistency (LOW)** — production file is `summary_short_anchors.jsonl` (per `_from_csv_anchor` line 1090 = `f"{task}_anchors.jsonl"` with task=`"summary_short"`); but AC-3 spec + `.example` template name (originally) used `summary_anchors.jsonl` (without `_short` infix). I renamed the `.example` from `summary_anchors.jsonl.example` → `summary_short_anchors.jsonl.example` in-session and updated `test_corpus_integrity.py::_anchor_files_present`. The story file AC-3/AC-11 still says `summary_anchors.jsonl` — that's a doc drift to fix in the next retro. **Action carry-forward:** edit AC-3 + AC-11 in `_bmad-output/planning-artifacts/epics.md` (Story 9.5 AC block) to use `summary_short_anchors.jsonl.example` for consistency.

### From Story 9-5 (eval corpus build)

- **AC-15 session discovery → [deferred: separate housekeeping story]** — `scripts/mint_refresh_token.py` does not inject the project root into `sys.path` before its `from mailbot_api.observability.logging import sanitize` import (line 52). The script is uninvokable via `python scripts/mint_refresh_token.py`; works only via `python -m scripts.mint_refresh_token` or `PYTHONPATH=. python scripts/...`. Same pattern that `scripts/build_corpus.py` (Story 9-5) handles correctly with `_PROJECT_ROOT` insertion. Surfaced during Adam's AC-15 OAuth ceremony 2026-06-27. **Action carry-forward:** apply the same `_PROJECT_ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, ...)` pattern to all `scripts/*.py` that import from `mailbot_api/` — file as one-line task in the next epic's housekeeping bucket. Not Story 9-5 scope (the script was pre-existing; Story 9-5 only discovered the bug).
- **CR-F5 LOW → [deferred: known-gap in `list-corpus` default column projection; non-load-bearing]** — `LIST_CORPUS_DEFAULT_COLUMNS` includes `from_display_name` + `received_at` which `_project_corpus_row` reads from `source_note` via regex. `sample --from-db` writes `received_at` into `source_note` but NOT `from_display_name` (which lives in the `_db_provenance` dict only, not in `source_note`). The default `list-corpus` output returns blank for `from_display_name` on real corpus rows. Co-pilot session's primary use case is `id + raw_subject` so the blank column doesn't break AC-15. **Action carry-forward:** when Story 9-5 v2 corpus refresh happens (or whenever `list-corpus` gets revisited), either (a) extend `source_note` in `sample --from-db` to include `from_display_name`, or (b) drop `from_display_name` from the documented defaults. Adding a dedicated `_db_provenance` schema field on `CorpusItem` was considered and rejected — adds schema surface for one tool used only during AC-15.

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
