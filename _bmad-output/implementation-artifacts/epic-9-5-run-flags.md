# Epic 9.5 Run Flags — Live Validation & policy.yaml v0→v1 Bump

**Epic:** 9.5 — Live Validation & policy.yaml v0→v1 Bump
**Status at file creation:** backlog (all 5 stories backlog)
**File created:** 2026-07-02 by /autonomous-epic-run 9.5 Phase 0.4 halt

---

## /autonomous-epic-run 9.5 Run 1 — 2026-07-02 — HALTED at Phase 0.4 blocker scan

**Invocation:** `/autonomous-epic-run 9.5`
**Dev-model:** claude-opus-4-7
**Review-model (would-have-been):** claude-sonnet-4-6
**Outcome:** HALT before Phase 1 — Phase 0.4 gating rule fired.
**Time-to-halt:** ~5 min (Phase 0 pre-flight + orphan-decision + blocker scan).

### Phase 0.2 orphan-scan decision (durable Adam-decision)

Epic 7 has 3 backlog stories (7-5, 7-6, 7-7) that lexically precede Epic 9.5 stories in `sprint-status.yaml`. Per SKILL.md Phase 0.2 letter-of-the-law, this would HALT the run because `bmad:bmm:workflows:create-story` picks the next backlog story globally and would grab 7-5 first.

**Adam-decided 2026-07-02:** sidestep via explicit `story_path=9.5.X` passed to create-story (recommended option). Epic 7 orphans are architecturally-correct downstream (sequences AFTER Epic 9/9.5 → CP-1), not a real ordering violation. This mirrors the 2026-06-27 precedent from `epic-9-run-flags.md § Run 3` for Story 9-6.

**Durable rule for future Epic 9.5 story runs:** any `/autonomous-story-run 9.5.X` invocation MUST pass `story_path=9.5.X` explicitly to create-story to sidestep the Epic 7 orphan lineup. Do NOT reorder sprint-status.yaml — audit-trail ordering is preserved.

### Phase 0.4 blocker findings — 5/5 stories BLOCKED

| Story | Type | Autonomous-safe? | Blocker |
|---|---|---|---|
| 9.5.1 | Implementation (Hermes Discord Portal API) | **NO** — cross-repo | Target repo lives outside MailBot workspace |
| 9.5.2 | Walk (Discord live) | **NO** — Adam-hands-on | Adam types `/model` in real Discord + captures verdicts |
| 9.5.3 | Walk (real-spend CLI, ~$10-11) | **NO** — Adam-hands-on | Adam pre-flights spend + runs `--yes` + captures verdicts |
| 9.5.4 | Walk (real-spend CLI, ~$1-3) | **NO** — Adam-hands-on | Adam pre-flights spend + branch-decides on α<0.6 path |
| 9.5.5 | Implementation gated by 9.5.3+9.5.4 verdicts | **Partially** — dep-chain locked | Cannot start until walks land AND their verdicts exist |

### Blocker 1: Story 9.5.1 — cross-repo (Hermes source not in workspace)

Per epics.md § "Story 9.5.1" ACs line 3529-3532:
> "Given the registration is a Hermes-side change, not a mailbot-api change / When the implementation lands / Then the code lives in the Hermes repository per the existing mailbot-api ↔ Hermes split (mailbot-api ships the MCP verbs; Hermes is the user-facing surface) / And mailbot-api's `policy.yaml`, `mcp_server.py`, and the Epic 9 `/model` verbs are UNCHANGED by this story."

**Workspace scan result:** sibling directories in `c:\Users\Adam\Desktop\GitWorkspace\` at run time are `MailBot`, `Vistai.ai_lovable`, `TicketPack`, `ANTLR4-Training`, `BashPowershellTraining`, `CppProjectTemplate`, `HackerRank`, `PersonnalProfileCard`, `React_tutorial`, `dockertmp`, `groovy_traning`, `time-tracker`. **No `hermes/` repo present.** Per PORTING.md line 77, `nousresearch/hermes-agent` is a Docker image; the Hermes source lives in Adam's private fork elsewhere. dev-story cannot author code in a repo it cannot see.

**Additional blocker (secondary):** 3 unresolved OQs per epics.md line 3523 require Adam-decision AT KICKOFF — (a) startup-vs-dynamic slash registration, (b) single-slash-with-subcommands vs three-separate slash entries, (c) testing surface for external-API integration.

### Blockers 2-4: Stories 9.5.2, 9.5.3, 9.5.4 — walk stories, Adam-hands-on required

The Epic 9 retrospective explicitly named this pattern at `epic-9-retro-2026-06-29.md` line 140:
> "autonomous-epic-run / autonomous-story-run cadence makes the L3 gap structural — Phase 3.5 walks only fire on epic done-flip, not on story close. Tranche-close (no Phase 3.5) → Epic-close-on-Option-A (Phase 3.5 also doesn't fire) means a 12-story epic shipped without a single live walk for 10 of the 12 stories."

Epic 9.5 IS the L3 tranche — the whole POINT is Adam-observable real-world verification. 3 of 5 stories are Phase-3.5-shaped walks requiring:
- **9.5.2:** Adam types `/model qwen` in Discord for a non-sensitive prompt (AC-1), `/model draft_reply opus` (AC-2), `/model qwen --once` on confidential email that must be refused (AC-3), captures 3 walk-evidence entries in `9-5-2-walk-evidence.md`
- **9.5.3:** Adam pre-flights ~$10-11 Anthropic spend, runs `python -m benchmark.runner --corpus … --yes` (bypasses $5 cost gate), then `--tasks draft_reply --models claude-haiku-4-5,claude-opus-4-7 --yes` (Haiku-vs-Opus 200-cell run), then `python -m benchmark.anchor_stability_audit … --yes` (baseline write), captures verdicts in `9-5-3-walk-evidence.md`
- **9.5.4:** Adam pre-flights ~$1-3 spend, runs `benchmark.anchor_stability_audit … --secondary-evaluator claude-haiku-4-5 --yes` (Krippendorff α on 20 anchors), then branch-decides on α<0.6 (reconciliation-vs-accept-with-rationale), captures verdict in `9-5-4-walk-evidence.md`

None of these are autonomous-executable. Precedent: Story 9-5 was flagged `RUN-MODE BINDING: NOT compatible with /autonomous-epic-run` in sprint-status.yaml line 250 because AC-15 required Adam co-pilot labeling; the walk stories here are the same shape at higher intensity.

### Blocker 5: Story 9.5.5 — dep-chain locked to walk verdicts

Per epics.md § "Story 9.5.5" AC line 3683-3689 and dep table line 3456, 9.5.5 depends on:
- AC-5 verdict from 9.5.3 (Haiku-vs-Opus PROMOTE-needed / DEMOTE-invalid / hold-steady / INSUFFICIENT_DATA / DEMOTE-valid)
- α verdict from 9.5.4 (must be α≥0.6 OR accept-with-rationale to gate v0→v1 bump)

**BUT:** 9.5.5 IS autonomous-safe once the walks land — the implementation is a policy.yaml edit + regression test + version-bump documentation. That's the /autonomous-story-run 9.5.5 target once verdicts are captured.

### Adam-decided resolution — 2026-07-02 (option d)

Adam handles manually:
- **9.5.1** in the Hermes repo (outside MailBot workspace, Adam-only-access)
- **9.5.2** as 3 live Discord walks against a running Hermes + mailbot-api stack
- **9.5.3** as 3 real-spend CLI walks (~$10-11 total Anthropic budget)
- **9.5.4** as 1 real-spend CLI walk (~$1-3) + branch-decision on α outcome

Then re-invokes `/autonomous-story-run 9.5.5` for the policy.yaml v0→v1 bump implementation once the walk evidence files (`9-5-3-walk-evidence.md`, `9-5-4-walk-evidence.md`) are on disk with the verdicts captured. Per Phase 0.2 durable rule above, that invocation MUST pass `story_path=9.5.5` explicitly to create-story to sidestep the Epic 7 orphan lineup.

### Zero permission prompts occurred during pre-flight

Envelope was sufficient for the surfaces touched (Read of settings.json + sprint-status.yaml + PORTING.md + epics.md, Grep, Glob, ls of workspace root, ls of `_bmad-output/implementation-artifacts/`, and this Write). No mid-run permission prompt drift to record.

### Recommendations for the Epic 9.5 retrospective

1. **Codify the "walk-heavy epic" incompatibility in SKILL.md.** Epic 9.5 is the second data point (after Story 9-5 AC-15) where the autonomous-epic-run skill correctly halts at Phase 0.4 because the epic's ACs are structurally Adam-hands-on. Worth adding a Phase 0.4 sub-check: "if ≥50% of stories are walk-shaped (grep AC bodies for `Adam runs`, `Adam types`, `Adam pre-flights`, `walk evidence`), halt with the recommendation to use /autonomous-story-run individually on the non-walk stories."

2. **Consider marking Epic 9.5 stories with `RUN-MODE BINDING: NOT compatible with /autonomous-epic-run`** in sprint-status.yaml for 9.5.2/9.5.3/9.5.4 (matching the Story 9-5 precedent). This makes the incompatibility visible without needing to re-derive it at every future autonomous-run invocation. 9.5.5 stays autonomous-safe (dep-locked but implementable).

3. **The Phase 0.2 sidestep pattern is now used twice** (Epic 9 Run 3 for Story 9-6, and this run for Epic 9.5). Worth codifying in SKILL.md as a first-class carve-out rather than an every-run ad-hoc Adam-decision — likely as: "if the target epic's `epic-N` row appears strictly after backlog stories from earlier epics that are architecturally-downstream (per epics.md sequencing header), sidestep via explicit story_path rather than halt."

---

## /autonomous-story-run 9.5.1 Run 1 — 2026-07-02 — HALTED at Phase 0.4 blocker scan

**Invocation:** `/autonomous-story-run 9.5.1` (user typed `9.5-1`; interpreted as `9.5.1` per the dot-notation naming convention Adam-decided 2026-07-02, sprint-status.yaml line 259).
**Dev-model:** claude-opus-4-7 (this session)
**Review-model (would-have-been):** claude-sonnet-4-6
**Outcome:** HALT before Phase 1 — Phase 0.4 gating rule fired (same blocker as Run 1 above at epic scope).
**Time-to-halt:** ~3 min (permission-envelope pre-flight + sprint-status lookup + epics.md read + workspace scan + prior-halt cross-reference).

### Restated blocker (same as Run 1 § "Blocker 1")

Story 9.5.1 requires source-code changes in the Hermes repository, which is **not present in the workspace** (`c:\Users\Adam\Desktop\GitWorkspace\` sibling scan returned identical result to Run 1 — no `hermes/` sibling). Per epics.md § "Story 9.5.1" ACs line 3529-3532, mailbot-api's `policy.yaml`, `mcp_server.py`, and the Epic 9 `/model` verbs must remain byte-identical — meaning there is no in-repo surface this dev pass could legitimately touch.

### Why re-halt was warranted (not a mistake to re-invoke)

The Run 1 halt entry did not update `sprint-status.yaml` line 260 with `RUN-MODE BINDING: NOT compatible with /autonomous-story-run` — recommendation §2 above proposed but did not execute the change. So a fresh `/autonomous-story-run 9.5.1` invocation had no in-file marker to short-circuit against and had to re-derive the blocker.

### Recommendation upgrade (execute now, not just propose)

The Epic 9.5 retrospective (`epic-9-5-retrospective: optional` in sprint-status.yaml line 265) will fire *after* the epic done-flips — and cannot back-mark story rows for future autonomous invocations. The right time to add the `RUN-MODE BINDING:` markers is now, at Adam's discretion. Suggested edits:

- Line 260 (`9.5.1`): append `**RUN-MODE BINDING: NOT compatible with /autonomous-story-run — cross-repo (Hermes source outside MailBot workspace); Adam-only-access; see epic-9-5-run-flags.md.**`
- Line 261 (`9.5.2`): append `**RUN-MODE BINDING: NOT compatible with /autonomous-story-run — Adam-hands-on walk story (types /model in real Discord); see epic-9-5-run-flags.md.**`
- Line 262 (`9.5.3`): append `**RUN-MODE BINDING: NOT compatible with /autonomous-story-run — Adam-hands-on real-spend CLI walks (~$10-11 Anthropic); see epic-9-5-run-flags.md.**`
- Line 263 (`9.5.4`): append `**RUN-MODE BINDING: NOT compatible with /autonomous-story-run — Adam-hands-on real-spend CLI walk (~$1-3) + branch-decision on α outcome; see epic-9-5-run-flags.md.**`
- Line 264 (`9.5.5`): leave unchanged — autonomous-safe once 9.5.3/9.5.4 verdicts land.

Adam decides whether to apply. This run flags but does not mutate sprint-status.yaml (no dev-pass work performed).

### Zero permission prompts occurred during pre-flight (Run 2)

Same envelope coverage as Run 1. Read of settings.json + sprint-status.yaml + PORTING.md + epics.md + prior epic-9-5-run-flags.md, Grep, Glob, `rtk ls`, and this Edit. No mid-run permission-prompt drift to record.
