---
baseline_commit: ccdaf31a4c1b9eb6910931c4cddc60479f4c0093
---

# Story 10.7.4: Swap the Local Tool-Calling Model — DISPOSITION: CLOSE (contingency did not fire)

Status: done

<!-- Note: this is a DISPOSITION story per the autonomous-story-run Disposition-Story Pattern.
     10.7.4 was filed as a CONTINGENCY: it fires ONLY if the 10.7.0 characterization spike
     found a Qwen-3B ceiling that the harness-fix stories could not overcome. The spike found
     NO ceiling and the harness fixes shipped. This story records that evidence-backed close.
     Adam-decided disposition (2026-07-17): "Close as superseded (verification-only)." -->

## Story

As the MailBot maintainer,
I want the contingent "swap the local tool-calling model" story closed on the evidence that its firing precondition (a proven Qwen-3B ceiling) never materialized,
so that Epic 10.7's done-flip gate (clause 2 — "all spike-selected fix stories status=done") can be discharged without carrying a stale, unlicensed model-swap on the roster or building the wrong thing.

## Acceptance Criteria

1. **The firing precondition is documented as unmet.** The story file records that 10.7.4's trigger — "fires ONLY if 10.7.0 finds a 3B ceiling" (epics.md:4373) — is provably false against the 10.7.0 spike finding: no ceiling at coarse (§4.2, 20/20) or leaf (§4.4, 20/20), with the fire-list explicitly stating "10.7.4 (model swap) — CLOSE. No ceiling at coarse OR leaf. Nothing licenses a swap." (10-7-0-spike-finding.md:111).

2. **The superseding harness fixes are verified done.** The story confirms that the stories the spike selected in place of a model swap are all `done` in sprint-status.yaml: 10-7-5 (find_emails description rewrite — the PRIMARY fix, 0/20→20/20 leaf), 10-7-3 (surface trim), 10-7-1 (rescue parser, defensive), 10-7-2 (system prompt, defensive). No open harness-fix work remains that a model swap would be a fallback for.

3. **No source code is changed.** The disposition is verification-only. No adapter, registry, policy, model-id, or cost-thesis-affecting code is touched. The File List is documentation-only (this story file + its pre-review artifact + flags-file). Confirmed via `git status --porcelain` showing no `mailbot_api/` source deltas attributable to this story.

4. **The cost thesis and the reversible fallback are preserved, not spent.** The story records that the contingency remains *available* as a documented fallback if — and only if — a real-Hermes-path regression re-surfaces a ceiling that 10-7-5 + 10-7-3 cannot fix (sprint-status:377). Closing it now does not delete the escape hatch; it declines to fire it absent evidence. The founding $0-local cost thesis (`project_local_model_is_safety_net`) is untouched.

5. **The sprint-status row is flipped to `done` with a superseded-by rationale**, citing 10-7-0 (no ceiling) + 10-7-5/10-7-3/10-7-1/10-7-2 (harness fixes shipped) as the supersession chain, and noting the fallback-availability carve-out from AC-4.

## Tasks / Subtasks

- [x] Task 1: Verify the firing precondition is unmet (AC: 1) — VERIFIED: spike §4.2 coarse 20/20, §4.4 leaf 20/20 (leaf_desc + leaf_desc_strong both 20/20), fire-list item 4 (line 111) reads "10.7.4 (model swap) — CLOSE. No ceiling at coarse OR leaf. Nothing licenses a swap." epics.md:4373 confirms CONTINGENT framing. Verdict: precondition NOT met.
  - [x] Read 10-7-0-spike-finding.md §4.2 (coarse 20/20), §4.4 (leaf 20/20), and the FINAL fire-list line for 10.7.4.
  - [x] Read epics.md:4373 to confirm the story was filed as CONTINGENT on a 3B ceiling.
  - [x] Record the verdict: precondition NOT met.
- [x] Task 2: Verify the superseding harness-fix stories are done (AC: 2) — VERIFIED via grep of sprint-status.yaml: 10-7-5 (:373 done), 10-7-1 (:374 done), 10-7-2 (:375 done), 10-7-3 (:376 done). All four `done`.
  - [x] Grep sprint-status.yaml for 10-7-5 / 10-7-3 / 10-7-1 / 10-7-2 status; confirm all `done`.
  - [x] Record each supersession pointer.
- [x] Task 3: Confirm no source code is in scope (AC: 3) — VERIFIED: `git status --porcelain` shows only this story file (??) + sprint-status.yaml (M) attributable to this story; no `mailbot_api/` deltas. (settings.json + 10-7-0-spike-finding.md M's are pre-existing, unrelated.)
  - [x] Run `git status --porcelain`; confirm no `mailbot_api/` source deltas attributable to this story.
  - [x] Record the documentation-only File List.
- [x] Task 4: Record the cost-thesis + reversible-fallback preservation (AC: 4) — RECORDED: fallback stays available per sprint-status:377 carve-out; cost thesis $0-intact per spike §5 + `project_local_model_is_safety_net`.
  - [x] Note the fallback-availability carve-out (sprint-status:377) and cost-thesis intactness (spike-finding §5).
- [x] Task 5: Flip sprint-status row to done with superseded-by rationale (AC: 5) — done at Step 2.4.8 (gates first).
  - [x] Edit sprint-status.yaml row with the supersession chain + fallback carve-out.

## Review Findings — CR2026-07-17 (reviewer sonnet-5 ≠ dev opus-4-8)

- [x] [LOW] File List overclaims `story-run-flags.md` as "new/appended" for this story's run (File List entry, line ~106) — `git status --porcelain` shows this file has zero pending changes and is not untracked; `git log` confirms its most recent content is already committed at `ccdaf31` (this story's own `baseline_commit`) and its tail contains no 10-7-4 entry. No append actually happened. AC-3's "documentation-only File List" claim is therefore inaccurate in one entry (harmless — doesn't affect the disposition's substance — but should be corrected or the append performed before `done`). **APPLIED (dev 2026-07-17):** File List entry re-worded to "to be appended at Step 3.3 — not yet written at pre-review time"; the flags-file append genuinely happens at Step 3.3 of this run, so the entry stays (accurate at run-completion) but no longer claims a past-tense append. AC-3's substance (no `mailbot_api/` source code) is unaffected.
- [ ] [INFO — no action required, recorded for audit trail] [ACCEPTED — no change] The sprint-status.yaml comment on the **10-7-0** row (line 372) still reads "DO-NOT-CLOSE 10.7.4 (3B ceiling not ruled out)" — this is the spike's §4 mid-run recommendation, since superseded by the spike doc's own §4.4 "FINAL fire-list (supersedes §4 + §4.2 + §4.3)" verdict ("10.7.4 — CLOSE"), which 10-7-4 correctly cites. The stale comment on the *sibling* 10-7-0 row is pre-existing (not introduced by this story) and does not misstate 10-7-4's own row, but a reader skimming only tracker comments (not the full spike doc) could see the two rows appear to conflict. **DEV DISPOSITION: ACCEPT / no change** — BMAD sprint-status inline comments are append-only point-in-time history (never amended); the 10-7-0 row is not in this story's scope, and this story's own 10-7-4 row + the spike doc §4.4 carry the authoritative CLOSE verdict. Left as an intentional historical log entry per BMAD convention.

**Adversarial disposition-test summary:** The four brief-specified verification points all survive scrutiny. (1) Firing-precondition-unmet claim is TRUE and faithfully cited — the spike doc's §4.4 section is explicitly self-labeled as superseding its own earlier §4 "DO NOT CLOSE" recommendation ("FINAL fire-list (supersedes §4 + §4.2 + §4.3)"), so citing only §4.4 is legitimate sequential-supersession, not evidence-shopping. (2) All four superseding siblings (10-7-5/10-7-1/10-7-2/10-7-3) are verified `done` in sprint-status.yaml (lines 373-376). (3) The story does NOT claim Epic 10.7 done-flip clause 3 (live Discord walk) — Dev Notes explicitly disclaim it ("Clause 3 ... is load-bearing and is owed at the epic live walk. This disposition does NOT claim clause 3."), verified against epics.md:4387's clause-3 text. (4) The fallback carve-out (fires only on a real-Hermes-path regression 10-7-5+10-7-3 can't cover) is faithfully preserved from sprint-status:377 and does not delete the escape hatch. No blocking findings; one LOW file-list correction.

## Dev Notes

**Disposition type:** verification-only close (Disposition-Story Pattern, autonomous-story-run SKILL.md). No product code expected; most Posture-Audit sub-sections will be N/A with justification, but the forcing function (pre-review self-audit + MANDATORY-CR on the disposition record) still holds per the pattern.

**Why this is not a HALT:** the skill's Branch-A authoring HALT fires only when epics.md has *no section* for the story-id. Epics.md HAS a section (§ Epic 10.7 Detail, story row 10.7.4 at epics.md:4373) — it explicitly defines 10.7.4 as contingent. So requirements exist; they simply resolve to "do not fire, close." Authoring a disposition record from that section is the correct inline action.

**Evidence chain (the whole basis for the close):**

- 10.7.4 filing intent (contingent): epics.md:4373 — "*(CONTINGENT — fires only if 10.7.0 finds a 3B ceiling)*".
- Spike verdict (no ceiling): 10-7-0-spike-finding.md §4.2 (coarse 20/20), §4.4 table (leaf_desc 20/20, leaf_desc_strong 20/20), and §4.4 FINAL fire-list item 4 (line 111): "10.7.4 (model swap) — CLOSE. No ceiling at coarse OR leaf. Nothing licenses a swap."
- Spike §4 headline (line 68): "10.7.4 (model swap) drops toward unlikely — keep open only as a fallback, no longer co-equal."
- Superseding fixes done: sprint-status.yaml rows 10-7-5 / 10-7-3 / 10-7-1 / 10-7-2 (all `done`, 2026-07-15/16).
- Fallback carve-out: sprint-status.yaml:377 — "Contingency fires ONLY if a real-Hermes-path regression re-surfaces a ceiling that 10-7-5 + 10-7-3 cannot fix."
- Cost thesis intact: 10-7-0-spike-finding.md §5 ("Cost thesis intact — $0"); memory `project_local_model_is_safety_net`.

**Done-flip clause it services:** Epic 10.7 done-flip clause 2 ("All spike-selected fix stories … status=done"). The spike *deselected* the model swap; closing 10.7.4 as superseded is the correct way to make clause 2 fully accounted-for. Clause 3 (a live Discord qwen→find_emails turn) is load-bearing and is owed at the epic live walk — this disposition does NOT claim clause 3.

### Project Structure Notes

- No source-tree changes. Artifacts live under `_bmad-output/implementation-artifacts/` only.
- No conflicts with unified project structure — documentation-only.

### References

- [Source: _bmad-output/implementation-artifacts/10-7-0-spike-finding.md#4.4] — leaf 20/20, fire-list "10.7.4 — CLOSE".
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-10.7-Detail] — 10.7.4 contingent framing (epics.md:4373).
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — 10-7-4 row (:377) + sibling done rows (:373-:376).
- [Source: memory/project_local_model_is_safety_net.md] — reversible-fallback / cost-thesis discipline.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev), via autonomous-story-run. Disposition decided by Adam 2026-07-17 ("Close as superseded (verification-only)").

### Debug Log References

- This is a DISPOSITION story (verification-only close), not a code story. The dev pass is evidence verification, not RED/GREEN/REFACTOR. No source files touched.
- Firing-precondition check: 10.7.4 was filed CONTINGENT on 10.7.0 finding a Qwen-3B ceiling (epics.md:4373). The spike found NO ceiling — coarse 20/20 (§4.2), leaf 20/20 (§4.4, both leaf_desc and leaf_desc_strong), and the FINAL fire-list (line 111) reads verbatim: "10.7.4 (model swap) — CLOSE. No ceiling at coarse OR leaf. Nothing licenses a swap." Precondition NOT met.
- Supersession check: the spike's selected fixes are all shipped — 10-7-5 (find_emails desc rewrite, the PRIMARY 0/20→20/20 lever), 10-7-3 (surface trim), 10-7-1 (rescue parser, defensive), 10-7-2 (system prompt, defensive) — all `done` in sprint-status.yaml (:373-:376).
- Source-scope check: `git status --porcelain` showed no `mailbot_api/` deltas attributable to this story; only the story file + sprint-status row.
- Gates run as a baseline sanity check (no `.py` changed): ruff `All checks passed!`; pytest `1972 passed, 3 skipped, 3 deselected` — unchanged vs the 10-7-3 baseline (1972), confirming zero regression.

### Completion Notes List

- **AC-1 (precondition unmet):** Recorded with primary-source citations — spike §4.2/§4.4 (no ceiling) + fire-list line 111 (explicit "CLOSE") + epics.md:4373 (contingent framing). Satisfied.
- **AC-2 (superseding fixes done):** 10-7-5/10-7-3/10-7-1/10-7-2 all confirmed `done` via grep. Satisfied.
- **AC-3 (no source code):** `git status --porcelain` confirms documentation-only footprint; no adapter/registry/policy/model-id change. Satisfied.
- **AC-4 (cost thesis + reversible fallback preserved):** Fallback stays available per the sprint-status:377 carve-out (fires only on a real-Hermes-path regression re-surfacing a ceiling that 10-7-5+10-7-3 can't fix); $0-local cost thesis intact (spike §5 + `project_local_model_is_safety_net`). Recorded, not spent. Satisfied.
- **AC-5 (row flipped with superseded-by rationale):** Done at Step 2.4.8 with the supersession chain + fallback carve-out in the row comment. Satisfied.

### File List

- `_bmad-output/implementation-artifacts/10-7-4-swap-local-tool-calling-model.md` (new — this disposition story)
- `_bmad-output/implementation-artifacts/10-7-4.pre-review.md` (new — pre-review self-audit artifact)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — 10-7-4 row backlog → in-progress → done)
- `_bmad-output/implementation-artifacts/story-run-flags.md` (to be appended at Step 3.3 — end-of-run flag report; not yet written at pre-review time, per CR2026-07-17 LOW finding #1)

No source files modified — documentation/disposition story, no `mailbot_api/` changes.

### Change Log

- 2026-07-17 — Closed 10.7.4 (swap local tool-calling model) as SUPERSEDED (contingency did not fire): 10.7.0 spike found no Qwen-3B ceiling and the harness-fix siblings shipped. Verification-only; no source code. Fallback remains documented and available.

## Completion Notes

### 2026-07-17 — disposition (verification-only close)

10.7.4 was a contingency that fires only on a proven Qwen-3B ceiling. The 10.7.0 characterization spike found no ceiling at any choice level (coarse 20/20, leaf 20/20; "the description IS the fix"), and its selected harness fixes (10-7-5 primary + 10-7-3 + 10-7-1 + 10-7-2) are all done. Nothing licenses a model swap. Closed as superseded on Adam's decision; the swap stays available as a documented reversible fallback only if a real-Hermes-path regression re-surfaces a ceiling those fixes can't cover. Cost thesis ($0-local) untouched. Gates green (ruff clean, pytest 1972, unchanged). Services Epic 10.7 done-flip clause 2; does NOT claim clause 3 (live Discord qwen→find_emails turn, owed at epic walk).
