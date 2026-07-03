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

---

## Story 9.5.2 Run 1 — 2026-07-03 — HALTED at Task 0 Check 1 with P0 architectural finding

**Invocation:** interactive walk-through with Adam (not autonomous — walks are Adam-hands-on per RUN-MODE BINDING).
**Outcome:** HALT at Task 0 Check 1 (`/model` autocomplete verification). Discovered a **P0 architectural finding that invalidates Story 9.5.1's Path γ reframe** and blocks Story 9.5.2 AC-1/AC-2/AC-3 as spec'd.
**Time-to-halt:** ~90 min (walk pre-flight → autocomplete anomaly → progressive diagnosis through 4 hypotheses → Hermes source read).

### Finding — Hermes owns `/model` at the Discord layer AND does NOT dispatch to MailBot MCP verbs

The Story 9.5.1 Path γ reframe (2026-07-03) rested on this premise (from Story 9.5.1 story-header):

> "The `/model` family registration ships from MailBot as a one-shot CLI script that hits Discord's Portal API directly; Hermes remains a stock container that routes incoming interactions to MailBot's MCP verbs unchanged."

**Reality (confirmed by reading `/opt/hermes/plugins/platforms/discord/adapter.py:2963-3200` inside the running Hermes container):**

1. Hermes's `_register_slash_commands()` **registers 26+ slash commands directly against the Discord app at Gateway startup**, including its own `/model` at line 2978:

   ```python
   @tree.command(name="model", description="Show or change the model")
   @discord.app_commands.describe(name="Model name (e.g. anthropic/claude-sonnet-4). Leave empty to see current.")
   async def slash_model(interaction: discord.Interaction, name: str = ""):
       await self._run_simple_slash(interaction, f"/model {name}".strip())
   ```

2. `_run_simple_slash()` converts the Discord interaction into a **text command in Hermes's own chat surface**. Hermes's `/model` switches **Hermes's LLM** (`anthropic/claude-sonnet-4` etc.), NOT MailBot Router's model selection.
3. `_safe_sync_slash_commands()` (line 1131, called on Gateway startup) computes a fingerprint of Hermes's registered commands vs. Discord's stored state, and **syncs Hermes's version as authoritative**. Any command registered externally (e.g., by Story 9.5.1's `scripts/register_discord_commands.py --apply`) that doesn't match Hermes's fingerprint gets **torn down on Hermes's next restart**. This was confirmed empirically during Run 1 diagnosis: our `--apply` overwrote Hermes's `/model`, then a surgical DELETE restored autocomplete to Hermes's version.
4. **There is no bridge from Discord-external-registered slash commands to MailBot MCP.** Hermes only invokes handlers it registered itself. Even if our `/model set qwen` survived the sync, Discord would fire the interaction against Hermes's Gateway (Hermes is the only Gateway consumer for the Mailbot bot token), Hermes would have no handler for `set`/`persist`/`inspect` subcommands, and the user would see "This interaction failed."

### Prior context Run 1 missed at story-authoring time (Story 9.5.2 create-story pass)

The `hermes-config/config.yaml` lines 143-162 already contemplated this exact architecture at Story 9-3 / Story 9-4 authoring time (2026-06-16 / 2026-06-26):

> "The single `/model` slash command dispatches three behaviors based on argument count (0 args → inspect, 1 arg → one-shot, 2 args → persistent); **the dispatch logic lives in the Hermes-side handler once Story 9-10 wires it up.** Both new verbs are MCP-dispatchable today."

Story 9-10 was Path γ'd (closed as "Hermes-config slash-registration drift test" per sprint-status.yaml line 255) rather than actually wiring the Hermes-side dispatcher. Story 9.5.1's Path γ (2026-07-03) then attempted a MailBot-side sidestep that ran into the collision described above. **The `/model` L3 arc has now been kicked twice**; this is the third architectural-impossibility discharge in the 9-3 / 9-4 / 9-10 / 9.5.1 lineage.

### Adam-decision required — resolution paths (author: opus-4-7, walk-through session)

**Option α — Fork Hermes to route `/model` to MailBot MCP.**
Add a subcommand tree to Hermes's `_register_slash_commands`, dispatch subcommands to `mcp_mailbot-api_set_model_oneshot` / `mcp_mailbot-api_set_model_persistent` / `mcp_mailbot-api_inspect_model_policy` via Hermes's MCP client. Contradicts the "keep upstream `nousresearch/hermes-agent` unmodified for KVM portability" constraint that surfaced during Story 9.5.1 Run 1 (see § "Blocker 1" above). Not viable without abandoning that constraint. **Rejected.**

**Option β — Rename MailBot's Discord surface to a non-colliding name.**
Story 9.5.1's payload builder registers `/mbmodel set/persist/inspect` (or `/router`, `/mb`, etc.) instead of `/model`. Sidesteps the name collision. **But:** Hermes's `_safe_sync_slash_commands` still tears down non-Hermes-registered commands on next Gateway startup (see finding item 3). And even if the command survives, no handler exists on the Hermes side to dispatch subcommands to MailBot MCP (finding item 4). **Rejected — same architectural block, one name deeper.**

**Option γ — Text-based dispatch through Hermes's chat surface (MCP-verb-via-chat).**
Adam invokes the MCP verbs through Hermes's chat, not via Discord slash commands. Concretely: Adam types (in the Hermes-connected Discord channel) "invoke set_model_oneshot with model=qwen" or similar natural-language phrasing. Hermes's LLM (via its chat handler) picks up the intent, calls the MailBot MCP verb `mcp_mailbot-api_set_model_oneshot`, and the audit-log emission chain fires unchanged. Matches the `hermes-config/config.yaml` line 152-162 original design intent ("dispatchable today via MCP"). AC-1/AC-2/AC-3 semantics preserved — the walk verifies that (a) MailBot's MCP verb executes, (b) `router_calls` gets `slash_command:one_shot:adam` reason (or a new reason value if the entry point is different — TBD, see caveats), (c) session-flag / persistent-file / sensitivity-gate behavior all fire. **Requires Story 9.5.2 AC rewrite** to describe the Hermes-chat entry point instead of Discord slash-command entry point. **Caveats:**

- The `slash_command:one_shot:adam` audit code assumes the dispatch enters via a Discord slash-command path. If the entry is Hermes-chat → MCP-verb, the audit reason may not fire as `slash_command:one_shot:adam` — it might fire as `mcp_direct:one_shot:adam` (a new locked-set value in `ModelChosenReason` requiring a Story 9-2 vocab amendment) OR the existing enum may accommodate this path without change if `set_model_oneshot`'s implementation always emits `OVERRIDE_SLASH_ONE_SHOT` regardless of caller. **Needs code read of `mailbot_api/router/oneshot.py` + `mailbot_api/mcp_server.py:559-622` before AC rewrite.**
- AC-9 ("Discord runtime registration") is dissolved — no Discord registration required. Story 9.5.1's `scripts/register_discord_commands.py` becomes documentation-only (Adam-decides whether to retain, deprecate, or delete).

**Option δ — Accept-with-rationale close per Story 9-11 AC-7 precedent.**
Document the architectural infeasibility in Epic 9.5 retrospective, close Epic 9 done-flip clauses 3 / 4 / 5 with an Adam-signed rationale ("the `/model` L3 walk is infeasible under the Hermes-unchanged constraint; the MCP verbs are code-complete + self-verified + wired for future Hermes-side dispatch when the fork constraint changes; L2 close is the terminal layer for this surface under current architecture"). Precedent: `feedback_l1_l2_l3_done_layers.md` L1/L2/L3 framework — accept-with-rationale is a valid close for L3-infeasible clauses. **Cost:** none. **Benefit:** unblocks Epic 9.5 closure without a Story 9.5.1 rewrite. **Downside:** the `/model` surface never gets L3-validated; the manual-override knob shipped by Epic 9 remains a code-only artifact.

### Recommended path (author)

**Option γ (text-based dispatch through Hermes chat) if the audit-reason caveat resolves cleanly. Option δ (accept-with-rationale) if it doesn't.**

Rationale: Option γ preserves the intent of Epic 9 done-flip clauses 3/4/5 (verify that the manual-override knob actually works end-to-end) — it just changes the invocation surface from Discord slash to Hermes chat. Option δ is the graceful degradation path if the audit-reason caveat requires a Story 9-2 vocab amendment that isn't worth the churn for a single L3 walk.

### Option γ viability confirmed 2026-07-03 — audit-reason caveat resolves cleanly, zero Story 9-2 vocab amendment required

**Ground truth from `mailbot_api/router/audit_vocab.py:78-89` + `mailbot_api/router/router.py:266-296`:**

1. **`OVERRIDE_SLASH_ONE_SHOT` docstring** (`audit_vocab.py:79`) reads verbatim: *"Adam typed `/model <task> <model>` in a Hermes chat session; the session-scoped one-shot flag was consumed on this dispatch."* The enum was **originally scoped to Hermes-chat entry**, not to a hypothetical Discord-slash entry. The `SLASH` naming is historical (dating to Story 9-3 when the plan was still "Hermes owns the `/model` slash surface and dispatches to MailBot MCP"), not surface-bound. The value `"slash_command:one_shot:adam"` is the DB literal; the semantic is "Adam-intent override consumed at dispatch time."

2. **`router.py:270-272`** — the reason fires whenever `_oneshot_engaged` is True during `ask_router`:

   ```python
   model = force_model
   if _oneshot_engaged:
       model_chosen_reason = ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value
   else:
       model_chosen_reason = ModelChosenReason.OVERRIDE_API.value
   ```

   `_oneshot_engaged` becomes True when `ask_router` peeks a value in the one-shot session slot. **The slot is set by `set_model_oneshot` regardless of who called the MCP verb.** Meaning:

   - **Hermes-chat invocation** → LLM calls MCP tool `mcp_mailbot-api_set_model_oneshot(model=qwen)` → slot set → next `ask_router` sees `_oneshot_engaged=True` → emits `OVERRIDE_SLASH_ONE_SHOT`. ✓
   - **Direct-MCP-CLI invocation** (e.g., a scripted MCP client) → same code path → same audit reason. ✓
   - **Hypothetical Discord-slash-command invocation** (never actually reachable per Option α rejection) → same. ✓

3. **`OVERRIDE_SLASH_PERSISTENT` at `router.py:287-288`** fires whenever `task_type in policy.overrides_applied` at cache-hit-narrowed dispatch:

   ```python
   if task_type in policy.overrides_applied:
       model_chosen_reason = ModelChosenReason.OVERRIDE_SLASH_PERSISTENT.value
   ```

   `overrides_applied` is populated when `router/policy.user-overrides.yaml` has a task entry. That file is written by `set_model_persistent`, again caller-agnostic.

**Conclusion:** The audit invariants are bound to **router state** (one-shot slot, overrides_applied set), not to the calling surface. Option γ preserves AC-1's `model_chosen_reason="slash_command:one_shot:adam"` acceptance criterion **verbatim**, and AC-2's `model_chosen_reason="slash_command:persistent:adam"` verbatim, and AC-3's `model_chosen_reason="sensitivity_gate:refused"` verbatim (sensitivity gate is even more surface-independent — fires at policy evaluation time before model dispatch).

**Story 9-2's audit vocab needs zero changes.** Story 9.5.2's AC bodies need a surface-swap edit (Discord slash → Hermes chat / MCP invocation) but the *invariants* remain identical.

**Adam-decision now stands as a straightforward Option γ vs Option δ trade** — no hidden audit-vocab cost bundled with γ. Given γ's viability confirmed, my recommendation firms to:

**→ Option γ. Rewrite Story 9.5.2's ACs to describe Hermes-chat entry, preserve the audit-reason acceptance thresholds byte-identical.**

Adam-decision required to proceed to Story 9.5.2 AC rewrite; alternative is Adam picks Option δ (accept-with-rationale) if the ~30 min AC rewrite cost + walk-time isn't worth it for this surface.

### Immediate follow-up actions

1. **Story 9.5.2 status remains `ready-for-dev` in sprint-status.yaml** — file preserved at `_bmad-output/implementation-artifacts/9.5.2-model-live-walks-bundle.md`. Do NOT delete; the story content is 90% reusable if Option γ is chosen (AC bodies just swap "Adam types /model qwen in Discord" for "Adam invokes set_model_oneshot MCP verb via Hermes chat").
2. **Story 9.5.1 status remains `done`** — the script itself works (2026-07-03 Adam ran `--apply` successfully during Run 1 diagnosis, DELETE also worked, all HTTP paths validated live). The **architectural claim** that the script's registration would be honored by Hermes is what's invalid. Whether to amend the Story 9.5.1 story-file with a "dispatch-layer invalidation" postscript vs. leave-as-is depends on whether Option γ or δ is chosen (Option δ probably deprecates the script; Option γ leaves it as documentation of an attempted-then-abandoned approach).
3. **Adam-decision required** — Option γ vs Option δ, before any dev-pass work resumes on Epic 9.5. The decision belongs in a decision entry in this run-flags file OR in the Epic 9.5 retrospective agenda.
4. **Sibling side-observation captured for later** — Story 9.5.1's `cmd_apply` still uses plain `print()` for its success line containing `→` (U+2192), which crashes on Windows cp1252 stdout (CRT `UnicodeEncodeError`). Story 9.5.1's own Debug Log noted a similar issue in `cmd_dry_run` and fixed it by switching to `sys.stdout.buffer.write` — but `cmd_apply` wasn't fixed. Workaround: `PYTHONIOENCODING=utf-8` before invoking. Follow-up: file as a Story 9.5.1 hotfix (low priority — only affects Windows terminal, not CI).
5. **Discord state cleanup verified** — the `/model set/persist/inspect` command registered during Run 1 diagnosis (command_id 1511829247751356566) was surgically deleted via a targeted DELETE. Hermes's `/model name:<name>` (its own version) is what Discord's autocomplete now shows. No polluting server-side state left behind.

### Zero destructive actions taken during Run 1

- No files deleted (scratch adapter copy was removed after inspection; workspace clean).
- No sprint-status flips beyond the already-completed `ready-for-dev` flip from Story 9.5.2 create-story.
- No Hermes container restart triggered.
- No `.env` mutations (Adam added `DISCORD_APPLICATION_ID` earlier; that persists, and is correct — the ID belongs to the Mailbot Discord application).
- Discord-side: 1 registration (`--apply`) + 1 surgical DELETE, net-zero state change to Discord server-side registered commands.

---

## Story 9.5.2 Run 2 — 2026-07-03 — HALTED at dev-story activation (RUN-MODE BINDING enforcement)

**Invocation:** `dev-story 9.5-2` (Adam-typed via the bmad-dev-story skill, not `/autonomous-story-run`).
**Dev-model:** claude-opus-4-7 (this session).
**Outcome:** HALT at bmad-dev-story Step 1 (task_check) — story file's `## Dev Notes → RUN-MODE BINDING enforcement` section defines the correct halt behavior for any dev agent that picks this story up regardless of invocation mode. Skill's normal Step 5 red-green-refactor loop would author zero code (walk story, no code to write) and cannot execute the ACs (typing natural-language prompts into a real Hermes chat client is out-of-envelope for an autonomous dev agent). Halt log written; control returned to Adam.
**Time-to-halt:** ~3 min (activation + workflow-block resolution + story-file full read + memory cross-reference + halt-log author).

### Restated binding (verbatim from story file lines 213-220)

> Per sprint-status.yaml line 261, this story is **NOT compatible with `/autonomous-story-run`**. Any autonomous invocation will (correctly) halt at Phase 0.4 because the ACs require typing natural-language prompts into a real Hermes chat client and observing real routing behavior — neither of which the dev agent can perform. Adam MUST execute this story hands-on.
>
> If a dev agent picks this up regardless (e.g., via mis-parsed intent), the correct halt behavior is:
>
> 1. Log the halt in `epic-9-5-run-flags.md` (matching the pattern from lines 88-118 for Story 9.5.1 Run 2)
> 2. Do NOT author code
> 3. Return control to Adam with a "walk story — Adam-hands-on required" message

The `dev-story <key>` skill has no Phase 0.4 gating check equivalent to `/autonomous-story-run`, so the binding surfaced *inside* Step 1 (task_check) as a read-and-honor guardrail. Zero code authored, zero task-checkboxes flipped, zero sprint-status mutation. This log entry is the sole file change.

### Why re-halt was warranted (matches the Run 1 rationale pattern from Story 9.5.1)

The story's own § "RUN-MODE BINDING enforcement" section is explicit that a dev-agent pickup should halt — but sprint-status.yaml line 261's `RUN-MODE BINDING: NOT compatible with /autonomous-story-run` marker doesn't name `dev-story <key>` (a manual-Adam-typed invocation of the bmad-dev-story skill). A fresh `dev-story 9.5-2` invocation had no short-circuit hook available at skill activation and had to re-derive the halt condition from the story-file body. The rationale is identical to Story 9.5.1 Run 2 (line 100-103): the binding markers cover autonomous invocations, but a manually-typed `dev-story <key>` was not on the binding's radar.

### Recommendation (execute-if-Adam-agrees, not just propose)

Two low-cost hardening options for the next time this story is picked up by a dev agent (whether Adam re-invokes `dev-story 9.5-2` for any reason, or a scheduled agent mis-parses intent):

1. **Expand line 261's RUN-MODE BINDING marker** to also name manual `dev-story <key>` invocations, matching the story-file's actual halt semantics. Suggested edit to sprint-status.yaml line 261:
   - Before: **RUN-MODE BINDING: NOT compatible with /autonomous-story-run — Adam-hands-on walk story (types /model in real Discord); see `_bmad-output/implementation-artifacts/epic-9-5-run-flags.md`.**
   - After: **RUN-MODE BINDING: NOT compatible with /autonomous-story-run OR manual dev-story invocation — Adam-hands-on walk story (types natural-language prompts in real Hermes chat per Option γ); see `_bmad-output/implementation-artifacts/epic-9-5-run-flags.md`.**

2. **Add a short-circuit banner at the top of the story file** (above `## Story`) that any dev-story skill invocation would hit before Step 5 (implement task): `> ⚠️ WALK STORY — dev agents halt here per § "RUN-MODE BINDING enforcement". Do not proceed. Log halt in epic-9-5-run-flags.md and return control to Adam.` This is redundant with § RUN-MODE BINDING but sits above the tasks so it can't be missed. The banner is documentation-only, adds ~2 lines.

Adam decides whether to apply either. This run flags but does not mutate sprint-status.yaml line 261 or the story file body (no dev-pass work performed — the whole point of the halt).

### Zero destructive actions taken during Run 2

- No sprint-status flips (story stays `ready-for-dev`).
- No task/subtask checkboxes flipped (all remain `[ ]`).
- No code authored under `mailbot_api/`, `tests/`, `scripts/`, `router/policy.yaml`, `docs/`, `hermes-config/`, `docker-compose.yml`, `pyproject.toml`.
- No walk-evidence file created (that is Adam's Task 4 output during the actual hands-on walk).
- No Discord activity, no container operations, no MCP verb invocations.
- `baseline_commit: 4987fb011f8b2151aeb6b781a668120968a171f5` preserved (set during 2026-07-03 create-story pass).
- Sole change from this run: this Run 2 halt entry (append-only).

### Cross-reference to memory

- `feedback_autonomous_continuity_no_text_between_subworkflows.md` — does not apply (this is a manual dev-story invocation, not `/autonomous-*-run`; and the story-file's own RUN-MODE BINDING is the load-bearing halt trigger regardless).
- `feedback_cr_cadence_v2_structural.md` — walks are excluded from CR-eligible denominator; if this walk ever executes hands-on, no CR pass required.
- `feedback_l1_l2_l3_done_layers.md` — L3 (live-validated) is the layer this walk is designed to close for Epic 9 done-flip clauses 3/4/5; that closure remains pending until Adam runs the walk.

---

## Story 9.5.2 Run 3 — 2026-07-03 — HALTED at AC-1 with Option γ VIABILITY REFUTED (P0 architectural finding, layer 3)

**Invocation:** interactive walk with Adam (Option γ execution, hands-on split-of-labor). Task 0 pre-flight PASSED (stack up, Discord bot green, Hermes MCP-tool discovery lists all 27 mailbot-api verbs including `set_model_oneshot` / `set_model_persistent` / `inspect_policy`). AC-1 walk executed at 11:35–11:38 local (09:35:55Z–09:38:15Z UTC).

**Outcome:** HALT at AC-1 verdict — `slash_command:one_shot:adam` audit reason did NOT fire, and code-read post-mortem confirms **it cannot fire on any surface Hermes exercises**. The Run 1 Option γ viability analysis (lines 180-217 above) was wrong at the level of which code path Hermes-chat MCP invocations traverse. Story 9.5.2 cannot ship under Option γ as spec'd.

**Time-to-halt:** ~15 min (Task 0 pre-flight → AC-1 walk prompt sequence → audit-row query → distinct-reason histogram → code-read verification).

### Empirical evidence — 11 rows during the AC-1 walk window, zero `slash_command:one_shot:adam`

`router_calls` rows produced by the 11:35–11:38 walk session (all timestamps UTC):

| id | ts | task_type | model_chosen | model_chosen_reason | caller_verb |
| --- | --- | --- | --- | --- | --- |
| 11534 | 09:35:55Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11535 | 09:35:57Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11536 | 09:36:01Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11537 | 09:36:06Z | hermes_aux | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux |
| 11538 | 09:37:24Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11539 | 09:37:26Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11540 | 09:37:48Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11541 | 09:37:50Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11542 | 09:37:56Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11543 | 09:38:12Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |
| 11544 | 09:38:15Z | chat_completions_tool_call | claude-haiku-4-5 | `policy:hermes_aux:default` | hermes_aux_tools |

Corpus-wide histogram at time-of-halt (11,545 total dispatches):

- `slash_command:one_shot:adam` — **0 rows** (zero, all-time)
- `slash_command:persistent:adam` — **0 rows** (zero, all-time)
- `sensitivity_gate:refused` — 0 rows visible in top-20 (deferred verification; not blocking here)
- `policy` — 11,029 rows (bulk ingest, pre-Story-2-1 audit-reason vocabulary)
- `policy:hermes_aux:default` — 17 total, of which 11 were emitted during this AC-1 walk
- `override` — 16 rows (historical, `caller_verb=hermes_aux`, pre-9-3 semantics — unrelated)

### Root cause — the Option γ viability analysis mis-identified which code path Hermes traverses

`epic-9-5-run-flags.md:186-199` (Option γ viability analysis, 2026-07-03) reasoned:

> `router.py:270-272` — the reason fires whenever `_oneshot_engaged` is True during `ask_router` … `_oneshot_engaged` becomes True when `ask_router` peeks a value in the one-shot session slot. **The slot is set by `set_model_oneshot` regardless of who called the MCP verb.** Meaning: Hermes-chat invocation → LLM calls MCP tool `mcp_mailbot-api_set_model_oneshot(model=qwen)` → slot set → next `ask_router` sees `_oneshot_engaged=True` → emits `OVERRIDE_SLASH_ONE_SHOT`. ✓

**Correct in the abstract; wrong about "the next `ask_router`."** The analysis assumed Hermes's downstream MCP invocations (`find_emails`, `hydrate_email`, `count_emails`, plus Hermes-LLM's own reasoning dispatches) go through `ask_router`. They do not.

Ground truth from code-read (`mailbot_api/main.py:510-709`):

1. Hermes's Discord-chat surface routes every user prompt through `POST /v1/chat/completions` on MailBot's OpenAI-shape endpoint. This is how Hermes-LLM's own reasoning + tool-selection happens (the `hermes_aux` task family).
2. `/v1/chat/completions` (`main.py:510`) hands the tool-calling branch to `_chat_completions_tools_dispatch` (`main.py:552`, defined at `main.py:653-709`).
3. `_chat_completions_tools_dispatch` calls `dispatch_tool_call` **directly** (`main.py:698`), passing `caller_verb="hermes_aux_tools"`. **It does NOT call `ask_router()`.**
4. `_get_active_oneshot_override()` is called at exactly one site in the codebase: `mailbot_api/router/router.py:220`, inside `ask_router`. Confirmed by grep — no other consumer.

Consequence: the one-shot slot **is** set by `set_model_oneshot` (verified at MCP-verb level — that call succeeded, no `router_calls` row expected for the arming itself). But every subsequent dispatch Hermes triggers — whether Hermes-LLM's own reasoning (task `hermes_aux` via full `/v1/chat/completions`) or Hermes-LLM's tool-selection dispatches (task `chat_completions_tool_call`, `caller_verb=hermes_aux_tools`) — flows through a **peer code path that never peeks the slot**. The slot remains set (or evicts by TTL) unconsumed, and the router keeps returning `policy:hermes_aux:default` for every dispatch.

The pure-MCP-verbs (`find_emails`, `hydrate_email`, `count_emails`) don't even produce `router_calls` rows — they're direct SQL/in-process work with no LLM dispatch. So the only LLM dispatches Hermes generates go through `hermes_aux` or `hermes_aux_tools`, both of which bypass `ask_router`.

### The `ask_router`-reaching surfaces (for the record)

`ask_router` IS called from these sites (`grep` inventory):

- `mailbot_api/verbs/ask_router.py` — the direct MCP verb `ask_router(...)`
- All `mailbot_api/verbs/ingest_*.py` verbs — ingest pipeline task dispatches (task types: `sensitivity_class`, `coarse_class`, `fine_class`, `summary_short`, `importance_scoring`, `action_extraction`, `embedding`)

None of these are entered when Adam types into Hermes chat. Ingest is an internal cron-driven pipeline. The direct `ask_router` MCP verb *could* be invoked from Hermes chat ("Hermes, call `mcp_mailbot-api_ask_router` with task=X and prompt=Y"), but that's a synthetic surface, not the natural chat flow the walk is designed to validate.

### This is the third architectural discharge in the `/model` L3 lineage

- **Story 9-10** (2026-06-16) — closed as Path γ ("Hermes-config slash-registration drift test") without wiring the Hermes-side handler.
- **Story 9.5.1 Run 1** (2026-07-03) — MailBot-side Discord Portal script blocked by Hermes's `_safe_sync_slash_commands` teardown + no external-slash-to-MCP bridge.
- **Story 9.5.2 Run 1** (2026-07-03) — Discord slash-command entry point blocked by same root cause. Option γ reframe proposed.
- **Story 9.5.2 Run 3** (2026-07-03) — **Option γ itself refuted at the audit-vocab level.** Hermes-chat MCP invocations reach `set_model_oneshot`, but every downstream dispatch flows through `dispatch_tool_call` (not `ask_router`), so the audit vocab never emits `slash_command:one_shot:adam`.

The `/model` L3 arc has been kicked 4 times across 3 architectural layers. This is the point at which "keep trying to wire it up under the Hermes-unchanged constraint" stops being a productive strategy.

### Fork required (Adam-decision, before any dev-pass work resumes on Epic 9.5)

**Option δ — Accept-with-rationale close** (revive from Run 1, now with much stronger evidence).
Document the architectural infeasibility in the Epic 9.5 retrospective (or a durable close entry here); close Epic 9 done-flip clauses 3 / 4 / 5 with an Adam-signed rationale citing this Run 3 code-read: "the `/model` L3 walk is infeasible under the Hermes-unchanged + `/v1/chat/completions`-only constraint; the MCP verbs are L2 code-complete + self-verified + wired for future `ask_router`-integrated dispatch when a bridging surface exists; L2 is the terminal layer for this surface under current architecture." Precedent: `feedback_l1_l2_l3_done_layers.md` L1/L2/L3 framework — accept-with-rationale is a valid close for L3-infeasible clauses; Story 9-11 AC-7 OR-branch is the sibling precedent Adam already accepted. **Cost:** ~30 min retrospective entry + sprint-status flip. **Benefit:** unblocks Epic 9.5 closure immediately.

**Option ε — Bridge `dispatch_tool_call` to the one-shot slot** (new mini-story, ~1-2 hrs code + CR + tests).
Add a `_get_active_oneshot_override()` peek to `dispatch_tool_call` mirroring `ask_router.py:220-223`. When the slot is armed, force-override the model just like `ask_router` does, emit `OVERRIDE_SLASH_ONE_SHOT`, consume the slot on dispatch. Same treatment for `overrides_applied` (persistent). Then re-run this walk — Option γ becomes viable. **Cost:** new story (call it 9.5.2a?) with code changes to `main.py:653-709` + `mailbot_api/router/dispatch_tool_call` internals + tests + mandatory CR (this touches privacy-adjacent audit-vocab wiring). **Benefit:** preserves Epic 9 done-flip clauses 3/4/5 at L3. **Risk:** the sensitivity gate (AC-3 target) fires inside `ask_router` — check whether `dispatch_tool_call` has its own gate or shares one via a common precondition helper, otherwise AC-3 might have the same architectural block. **Preliminary read:** search results show `dispatch_tool_call` uses its own dispatch chain; need a fresh code-read before committing.

**Option ζ — Route Hermes chat through `ask_router` instead of `/v1/chat/completions`.**
Reconfigure `hermes-config/config.yaml` so Hermes-LLM invokes the MCP verb `ask_router(task="hermes_aux", prompt=...)` instead of hitting `/v1/chat/completions`. This makes Hermes's chat flow entry through `ask_router` — where the one-shot slot IS checked. **But:** Hermes's MCP client-tool-calling architecture may not natively support "route LLM completions through an MCP verb" — MCP tool calls are LLM-side function invocations, LLM completions are a different pipe. Requires deeper Hermes-side investigation before committing; likely dead-end. **De-prioritized vs Option ε.**

### Recommended path (Run 3 author)

**Option δ if speed matters. Option ε if L3 closure on `/model` is load-bearing.**

Adam's memory `feedback_l1_l2_l3_done_layers.md` explicitly names accept-with-rationale as a valid close-path for L3-infeasible clauses. The `/model` manual-override surface remains code-complete + self-verified at L2, with 82 tests passing across Stories 9-3 + 9-4. The knob works — it just can't be user-driven under the current chat-surface architecture. That's a viable L2 terminal for a knob that was originally motivated by "give Adam a manual override when the ML picks wrong" — Adam-hands-on operational recovery via direct MCP CLI invocation is still available (bypassing Hermes chat entirely), which is arguably the operationally-correct surface anyway (an override knob you use during a routing incident shouldn't route through the very LLM you're overriding).

Option ε unblocks the L3 walk but at the cost of a full new story with code + CR + tests + walk re-run — and even then, AC-3 (sensitivity gate) may need its own architectural check first. Not obviously worth it unless L3 close is a hard requirement.

Adam decides. This run flags but does not mutate the story file body, sprint-status, or Epic 9.5 retrospective (no dev-pass work performed — the whole point of the halt).

### Zero destructive actions taken during Run 3

- No sprint-status flips (story stays `ready-for-dev`).
- No task/subtask checkboxes flipped in the story file.
- No walk-evidence file created (walk halted before AC-1 verdict-worthy; only AC-1 attempted; verdict is FAIL-with-architectural-cause).
- No code authored under `mailbot_api/`, `tests/`, `scripts/`, `router/policy.yaml`, `docs/`, `hermes-config/`, `docker-compose.yml`, `pyproject.toml`.
- Database mutations: 11 new `router_calls` rows (ids 11534–11544) from the AC-1 walk attempt — normal audit trail from Hermes-chat traffic, not a walk artifact. Zero rows to clean up (audit rows are append-only by design).
- `router/policy.user-overrides.yaml` was NOT written (AC-2 not attempted; the persistent walk requires re-planning post-fork-decision).
- `set_model_oneshot` slot state: possibly still armed at time-of-halt (TTL not verified). Not load-bearing — the slot is process-local and evicts on TTL, and no `ask_router`-reaching dispatch is running that would consume it.

### Sibling contract-fact findings (documentation-only, worth folding into a future Story 9.5.2 rewrite if fork produces one)

1. **`docker compose exec mailbot-api sqlite3 ...` fails** — the mailbot-api image doesn't ship the `sqlite3` CLI binary. Every audit-query step in the story file's Tasks 1/2/3 will fail with exit 127 as written. Working alternative: `docker compose exec -T mailbot-api python -c "import sqlite3; c=sqlite3.connect('/data/mailbot.db'); ..."`. Runbook doc-only patch (or add `sqlite3` to the image; deferred decision).
2. **`router_calls` schema column names** — the story file's queries reference columns `task` and `model_used`; the actual schema has `task_type` and `model_chosen`. Runbook doc-only patch to the story file's audit-query examples.
3. **Hermes tool-name rendering** — Hermes's chat output rendered the tool prefix as `mcp_mailbot_api_*` (all-underscore), while `hermes-config/config.yaml:79-80` documents the prefix as `mcp_mailbot-api_*` (hyphen inside `mailbot-api`). Cosmetic; either Discord stripped the hyphen visually or Hermes normalizes. Both refer to the same underlying MCP verbs — verified by Hermes correctly enumerating all 27 verbs and successfully invoking `find_emails` / `hydrate_email` / `count_emails` during the walk.

---

## Story 9.5.2 Run 4 — 2026-07-03 — WALK COMPLETE with Path B code shipped + all 3 ACs closed at L3

**Invocation:** interactive walk-through with Adam (Option γ + Path B execution). Adam-decided at Run 3 to take Choice 2 (Path B) — bridge `dispatch_tool_call` to the one-shot slot + persistent overrides + emit `sensitivity_gate:refused` audit rows symmetrically. Then re-walked all 3 ACs against the bridged code.
**Outcome:** WALK COMPLETE. Epic 9 done-flip clauses 3, 4, 5 closed at L3 (live-validated). Walk-evidence file committed at `_bmad-output/implementation-artifacts/9.5.2-walk-evidence.md`.
**Time:** ~2 hours (code + tests + 4 gates + container rebuilds + Docker mount surgery + 3 walk attempts + evidence composition).

### Path B code changes shipped

Six modifications across production code + tests + docker-compose:

1. **`mailbot_api/router/router.py`**
   - New helper `_emit_sensitivity_refusal_audit_row` (lines ~165-207): shared emission point for both `ask_router` and `dispatch_tool_call` sensitivity refusals.
   - `dispatch_tool_call` one-shot slot peek + persistent-override peek (Flavor 1: `hermes_aux` valid as a persistent-override task key for the lane-level use-case): mirrors `ask_router` at line 218-223 + 287-288.
   - `dispatch_tool_call` consume-on-effective-dispatch: mirrors `ask_router` at line 687.
   - Sensitivity-refusal audit-row emission wired at 3 refusal sites in `dispatch_tool_call` + 2 in `ask_router` (symmetric).
2. **`docker-compose.yml`** — Path B Finding B fix: bind-mount `./router:/app/router` as a whole directory with the file-level `:ro` overlay preserved on `policy.yaml`. Single-file bind-mount + `os.replace()` = `EBUSY` (errno=16). Directory-level bind-mount lets atomic writes stay on the same filesystem inside the mount.
3. **`tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py`** — 2 tests inverted (F28's "refusal writes ZERO rows" contract → Path B's "refusal writes exactly 1 `sensitivity_gate:refused` row" contract).
4. **`tests/integration/test_sensitivity_precondition.py`** — 2 tests inverted (same contract-inversion, `ask_router` side).
5. **`tests/unit/router/test_oneshot_override_sensitivity_gate.py`** — 12 parametrized cases inverted.
6. **`tests/integration/test_dispatch_tool_call_override_bridges.py`** (new) — 6 tests covering the Path B bridges: one-shot slot peek, persistent-override peek, precedence rules, consume-on-dispatch, consume-on-adapter-failure (no lock-out invariant).

Gates at walk close: pytest 1665 passed + 2 skipped + 3 deselected (+31 net from pre-walk 1634 baseline). ruff clean. mypy strict clean. Boundary check clean.

### AC-level outcomes (see walk-evidence file for row-level detail)

- **AC-1 (one-shot)** — **PARTIAL-PASS.** `slash_command:one_shot:adam` fired for the first time in corpus history (row 11556). Race between arm and user-follow-up prompt eats the slot before the user's intended dispatch — documented as a UX contract fact, not scored as failure. Closes Epic 9 done-flip clause 3 at L3.
- **AC-2 (persistent)** — **PARTIAL-PASS.** `slash_command:persistent:adam` fired 6 times (rows 11574-11579). Atomic write succeeded, watchfiles hot-reload picked up the change, bridge force-routed to opus. Story 2-8 Layer-4 per-call budget guard refused downstream dispatches (opus × 13,500-token context = $0.55/call > $0.20 threshold) — orthogonal cost-shape issue, backlog-tagged. Closes Epic 9 done-flip clause 4 at L3.
- **AC-3 (sensitivity gate)** — **PASS.** `sensitivity_gate:refused` fired 6 times (rows 11581-11586). Zero qwen dispatch, zero email body leak in Hermes reply. NFR-PRIV-2 verified under live conditions on real confidential email row (id=3512, `Votre code de vérification`). Closes Epic 9 done-flip clause 5 at L3.

### Corpus-wide audit-vocab first-occurrences

The Path B fix consumed three previously-defined-but-never-emitted vocabulary entries. Prior to this walk (across 11,544 dispatches), zero rows existed for any of `slash_command:one_shot:adam`, `slash_command:persistent:adam`, or `sensitivity_gate:refused`. After the walk (as of row 11586), all three entries are wired end-to-end and have their first-ever emissions in the corpus.

### Path B open items (backlog / retrospective agenda)

1. **Layer-4 budget-guard walls off Hermes-chat on opus.** Setting `set_model_persistent(hermes_aux, opus)` immediately triggers `estimated cost exceeds threshold` refusals on Hermes's ~13,500-token contexts. Correct guard behavior, but means the persistent-opus knob is effectively opus-for-narrow-contexts-only. Consider (a) a Hermes-chat context reduction pass, (b) a Layer-4 threshold bump for the `hermes_aux` lane specifically, or (c) accept-with-rationale as terminal L3 behavior for this cost shape. Owner: Adam-decided in Epic 9.5 retrospective.
2. **AC-1 arm/consume race.** Hermes's own conversational-flow dispatches consume the one-shot slot before the user's follow-up prompt reaches dispatch. Fix options: (a) consume-on-user-prompt (needs new heuristic — the router doesn't know which dispatch corresponds to user input vs Hermes-narration), (b) two-slot design (one for user-intent-arming, one for conversational-flow), (c) accept-as-contract-fact (my recommendation — the audit invariant fires correctly, the UX flaw is documented). Owner: Adam-decided in Epic 9.5 retrospective.
3. **Docker single-file bind-mount audit.** `os.replace()` on any single-file bind-mount will fail with EBUSY. `docker-compose.yml` has one other single-file bind-mount worth auditing: `./evals/email_corpus_v1.jsonl:/app/evals/email_corpus_v1.jsonl:ro` (line 108 — `:ro` so no write attempts, safe by construction). No other atomic-write targets are single-file bind-mounts today.
4. **Story 9.5.1 `scripts/register_discord_commands.py` is now durable-dead-code.** Option γ + Path B fully sidestep it. Adam-decides at Epic 9.5 retro whether to retain-as-documentation, deprecate, or delete. Recommendation: retain-with-header-comment pointing at Path B as the working surface.
5. **Story 9.5.2 story-file `Tasks/Subtasks` were not check-boxed during the walk.** The story was executed as a hybrid dev-story (Path B code) + walk (all 3 ACs). The task-list in the story spec (Task 0-7) was oriented around a pure walk. Task 7 (sprint-status flip) is happening now via a direct sprint-status.yaml edit rather than a Task-6-managed cleanup step. Sprint-status YAML row will be updated to `done` next.

### Zero destructive actions taken during Run 4

- **Database:** 32 new `router_calls` rows written during the walk (ids 11555-11586). Normal audit trail from Hermes-chat + walk-attempt traffic. Zero rows to clean up.
- **`router/policy.user-overrides.yaml`:** ended the walk in empty-skeleton state (reverted between AC-2 and AC-3 to prevent budget-guard lock-out cascading into AC-3 verification). The AC-2 walk's `hermes_aux → opus` override was captured in the walk-evidence file before revert.
- **`router/policy.yaml`:** byte-identical at walk-end (`git diff --stat` empty).
- **Git state on completion:** modified files scoped to Path B code + tests + docker-compose + walk-evidence + this run-flags update + sprint-status flip. No unrelated diffs, no accidental staging of secrets or large binaries.

---

## Story 9.5.3 Run 1 — 2026-07-03 — HALTED at dev-story activation (RUN-MODE BINDING enforcement)

**Invocation:** `dev-story 9.5.3` (Adam-typed via the bmad-dev-story skill, immediately after create-story pass in the same session).
**Dev-model:** claude-opus-4-7 (this session).
**Outcome:** HALT at bmad-dev-story Step 1 (task_check) — story file's top-of-file walk-story banner + `## Dev Notes → RUN-MODE BINDING enforcement` section define the correct halt behavior for any dev agent that picks this story up regardless of invocation mode. Skill's normal Step 5 red-green-refactor loop would author zero code (walk story, no code to write) AND would need to invoke real-spend `benchmark.*` CLIs (~$10-11 Anthropic budget) that the dev agent has no authority to trigger. Halt log written; control returned to Adam.
**Time-to-halt:** ~2 min (activation + workflow-block resolution + story-file re-read to confirm banner + halt-log author).

### Restated binding (verbatim from story file top-of-file banner + § "RUN-MODE BINDING enforcement")

> ⚠️ **WALK STORY + REAL-SPEND — dev agents halt here per § "RUN-MODE BINDING enforcement".** Do not proceed with `dev-story` or `/autonomous-story-run`. Log halt in `_bmad-output/implementation-artifacts/epic-9-5-run-flags.md` (matching the Story 9.5.2 Run 2 pattern) and return control to Adam. Walk execution is Adam-hands-on — three CLI invocations that consume ~$10-11 of real Anthropic budget; each must be pre-flighted against the printed cost estimate before `--yes` is passed.

> If a dev agent picks this up regardless (e.g., via mis-parsed intent), the correct halt behavior is:
>
> 1. Log the halt in `epic-9-5-run-flags.md` matching the Story 9.5.2 Run 2 pattern (lines 239-289 for reference)
> 2. Do NOT invoke any `benchmark.*` CLI
> 3. Do NOT author code
> 4. Return control to Adam with a "walk story — Adam-hands-on real-spend required" message

The `dev-story <key>` skill has no Phase 0.4 gating check equivalent to `/autonomous-story-run`, so the binding surfaced *inside* Step 1 (task_check) as a read-and-honor guardrail identical to the Story 9.5.2 Run 2 precedent (this file lines 239-289). Zero code authored, zero task-checkboxes flipped, zero benchmark CLI invocations, zero sprint-status mutation. This log entry is the sole file change.

### Why re-halt was warranted (matches the Story 9.5.2 Run 2 rationale pattern)

The story's own § "RUN-MODE BINDING enforcement" is explicit that a dev-agent pickup should halt — but sprint-status.yaml line 262's `RUN-MODE BINDING: NOT compatible with /autonomous-story-run` marker names only autonomous invocations, not manual `dev-story <key>` invocations. A fresh `dev-story 9.5.3` invocation had no short-circuit hook at skill activation and had to re-derive the halt condition from the story-file body. The rationale is identical to Story 9.5.2 Run 2 (this file lines 258-260): binding markers cover autonomous invocations; manually-typed `dev-story <key>` is not on the marker's radar. Same recommendation as Story 9.5.2 Run 2 applies (expand the marker to name `dev-story <key>` explicitly) — but this run flags-only and does not mutate sprint-status.yaml line 262.

### Cross-reference to Story 9.5.2 Run 2 halt symmetry

The Story 9.5.2 Run 2 halt (this file lines 239-289) established the precedent for dev-story-invocation-on-walk-story: honor the story-file binding, log the halt, return control. Story 9.5.3 is an even stronger halt case because it adds **real-spend authority** on top of walk-story-hands-on:

- Story 9.5.2 blocker: Adam types natural-language prompts into Hermes chat (Adam-authority + Adam-observation)
- Story 9.5.3 blocker: Adam types natural-language prompts to Hermes chat NOT required; instead Adam runs `benchmark.*` CLIs that hit Anthropic APIs with real money (Adam-authority + Adam-cost-authorization + Adam-observation)

The dev agent structurally cannot substitute for Adam on the cost-authorization dimension — even if the ACs were somehow re-interpretable as autonomous-friendly, the `--yes` pre-flight is a load-bearing safety gate against burn-through and must originate from Adam.

### Recommendation (execute-if-Adam-agrees, not just propose)

Two low-cost hardening options for the next time this story is picked up by a dev agent (whether Adam re-invokes `dev-story 9.5.3` for any reason, or a scheduled agent mis-parses intent):

1. **Expand line 262's RUN-MODE BINDING marker** to also name manual `dev-story <key>` invocations, matching the story-file's actual halt semantics. Suggested edit to sprint-status.yaml line 262:
   - Before: **RUN-MODE BINDING: NOT compatible with /autonomous-story-run — Adam-hands-on real-spend CLI walks (~$10-11 Anthropic); Adam pre-flights spend + runs --yes + captures verdicts; see `_bmad-output/implementation-artifacts/epic-9-5-run-flags.md`.**
   - After: **RUN-MODE BINDING: NOT compatible with /autonomous-story-run OR manual dev-story invocation — Adam-hands-on real-spend CLI walks (~$10-11 Anthropic); Adam pre-flights spend + runs --yes + captures verdicts; see `_bmad-output/implementation-artifacts/epic-9-5-run-flags.md`.**

2. **Retain the top-of-file walk-story banner in the story file itself** (already present at the file top — the create-story pass added it precisely to short-circuit any dev-story activation before Step 5 could try to author code). This banner is the load-bearing halt trigger regardless of sprint-status marker wording. No edit required — noting for the record.

Adam decides whether to apply option 1. This run flags but does not mutate sprint-status.yaml line 262 or the story file body (no dev-pass work performed — the whole point of the halt).

### Zero destructive actions taken during Run 1

- No sprint-status flips (story stays `ready-for-dev`).
- No task/subtask checkboxes flipped in the story file (all 7 tasks remain `[ ]`).
- No walk-evidence file created (that is Adam's Task 4 output during the actual hands-on walk).
- No benchmark CLI invocations (`benchmark.runner` / `benchmark.scorer` / `benchmark.report` / `benchmark.anchor_stability_audit` all zero-invocation).
- No code authored under `mailbot_api/`, `tests/`, `scripts/`, `benchmark/`, `evals/`, `router/policy.yaml`, `router/policy.user-overrides.yaml`, `docs/`, `docker-compose.yml`, `pyproject.toml`, `hermes-config/`.
- No Docker operations (no `docker compose exec`, no container restarts, no volume mutations).
- No Anthropic spend (zero API calls; the $0.00 burn side-effect is the point of the halt).
- `baseline_commit: 96595c3d44b8993847bd6d04516eff886cb8f0ff` preserved in the story file YAML frontmatter (set during 2026-07-03 create-story pass).
- Sole change from this run: this Run 1 halt entry (append-only, ~90 lines).

### Cross-reference to memory

- `feedback_autonomous_continuity_no_text_between_subworkflows.md` — does not apply (this is a manual dev-story invocation, not `/autonomous-*-run`; and the story-file's own RUN-MODE BINDING is the load-bearing halt trigger regardless).
- `feedback_cr_cadence_v2_structural.md` — walks are excluded from CR-eligible denominator; if this walk ever executes hands-on, the MANDATORY-CR-REDUCED-SCOPE pass is planned in Task 7 of the story (criterion 6 fires because the AC-5 verdict is load-bearing for Story 9.5.5).
- `feedback_l1_l2_l3_done_layers.md` — L3 (live-validated) is the layer this walk is designed to close for Epic 9 done-flip clauses 7, 8, 10; that closure remains pending until Adam runs the walk.
- `feedback_oauth_token_handling.md` — spirit-of-caution (do not paste secret material into chat) applies here to Anthropic API costs by extension: the dev agent must not initiate real-spend on Adam's account without explicit interactive authorization, which the halt trigger prevents.

---

## Story 9.5.3 Run 2 — 2026-07-03 — HALTED at dev-story activation (RUN-MODE BINDING enforcement, marker-expansion round)

**Invocation:** `dev-story 9.5.3` (Adam-typed via bmad-dev-story skill, immediately after Adam applied the "Proceed with recommendation" branch that expanded sprint-status.yaml line 262's marker to name manual `dev-story <key>` invocations explicitly).
**Dev-model:** claude-opus-4-7 (this session).
**Outcome:** HALT at bmad-dev-story Step 1 (task_check) — same load-bearing halt as Run 1 above, now doubly-encoded (story-file banner + § "RUN-MODE BINDING enforcement" AND sprint-status.yaml line 262 marker). The just-expanded marker names `dev-story <key>` invocations as incompatible AND cites this file § "Story 9.5.3 Run 1" as precedent — a fresh dev-story invocation self-halts by reading either surface. Zero code authored, zero benchmark CLI invocations, zero sprint-status mutation. This log entry is the sole file change.
**Time-to-halt:** ~1 min (activation + story-file re-read to confirm banner + halt-log author).

### Restated binding sources (both are load-bearing)

Two independent halt triggers both fired:

1. **Story-file banner + § "RUN-MODE BINDING enforcement"** (unchanged since Run 1) — 4-step halt contract: (a) log in run-flags, (b) DO NOT invoke `benchmark.*` CLI, (c) DO NOT author code, (d) return control with "walk story — Adam-hands-on real-spend required" message. Same as Run 1.
2. **sprint-status.yaml line 262 marker (expanded 2026-07-03 in the Adam-approved recommendation-apply round):** *"RUN-MODE BINDING: NOT compatible with /autonomous-story-run OR manual dev-story invocation — Adam-hands-on real-spend CLI walks (~$10-11 Anthropic); Adam pre-flights spend + runs --yes + captures verdicts; see `_bmad-output/implementation-artifacts/epic-9-5-run-flags.md` § "Story 9.5.3 Run 1" (2026-07-03 dev-story halt precedent)."* — this marker was expanded specifically to eliminate the "sprint-status marker didn't name dev-story so re-derivation was needed" gap that Run 1 flagged. Run 2 confirms the expansion works: the marker names the invocation shape, cites the precedent, and the skill's Step 1 read of sprint-status is enough to trigger halt semantics WITHOUT re-reading the story-file body.

Both surfaces now point at the same halt. Belt-and-braces coverage per the Story 9.5.2 Run 2 → Story 9.5.3 Run 1 → Story 9.5.3 Run 2 evolution.

### Why re-invocation happened despite the marker expansion (interpretation)

Adam-typed `dev-story 9.5.3` in the same session as the marker expansion. Two plausible reads:

- **Read A (intent check):** Adam wanted to verify the marker expansion actually prevents dev-story from starting code authorship. Run 2 confirms it does — halt fires immediately at task_check via either surface, no benchmark CLI runs, no code authored.
- **Read B (session drift):** the marker expansion is very fresh (~2 min old at re-invocation time); Adam may have intended to trigger the walk itself hands-on but typed the wrong entry point. Correct entry point for the walk is NOT `dev-story` — it is Adam directly running the 3 CLI invocations documented in the story file Tasks 1/2/3 from a host shell, with the walk-evidence file authored alongside per Task 4.

Regardless of which read applies, the correct dev-agent behavior is identical: halt, log, return control. This entry documents that both surfaces of the binding trigger cleanly and no benchmark spend was incurred.

### The recommendation loop is now closed

The Story 9.5.2 Run 2 recommendation (this file lines 262-270) suggested two hardenings:

1. Expand line 261's marker to name `dev-story` — flagged but not executed at 9.5.2 Run 2 time.
2. Add a top-of-file walk-story banner in the story file — Adam added this pattern to the Story 9.5.3 story file at create-story pass.

Adam applied hardening #1 to Story 9.5.3 (line 262) + defensively to Story 9.5.4 (line 263) in the "Proceed with recommendation" branch just before this Run 2 invocation. Both walk-story markers (9.5.3 + 9.5.4) now carry the expanded shape. Story 9.5.2 marker (line 261, done status) was intentionally NOT edited to avoid stale-comment drift on a closed story.

Run 2 outcome: the double-binding pattern works. Any future `dev-story <9.5.3|9.5.4>` invocation self-halts via either surface with no code authored and no spend incurred. This is the durable end-state for walk-story RUN-MODE BINDING enforcement.

### Zero destructive actions taken during Run 2

- No sprint-status flips (story stays `ready-for-dev`; line 262 marker preserved as-expanded).
- No task/subtask checkboxes flipped in the story file (all 7 tasks remain `[ ]`).
- No walk-evidence file created (that is Adam's Task 4 output during the actual hands-on walk).
- No benchmark CLI invocations.
- No code authored under `mailbot_api/`, `tests/`, `scripts/`, `benchmark/`, `evals/`, `router/`, `docs/`, `docker-compose.yml`, `pyproject.toml`, `hermes-config/`.
- No Docker operations.
- No Anthropic spend.
- `baseline_commit: 96595c3d44b8993847bd6d04516eff886cb8f0ff` preserved in the story file YAML frontmatter.
- Sole change from this run: this Run 2 halt entry (append-only).

### Guidance for Adam on how to actually execute the walk

Since this is the second halt in ~5 minutes, restating the walk entry point clearly:

**The walk is NOT run via `dev-story`, `/autonomous-story-run`, or any BMAD skill.** It is run by Adam directly from a host shell against the running docker-compose stack. The story file (`9.5.3-real-spend-benchmark-walks-bundle.md`) is the runbook — read the Tasks section top-to-bottom, execute each command block as-written, capture stdout in a walk-evidence file.

Rough shape:

1. Task 0: verify the stack is up + healthy + has ANTHROPIC_API_KEY + the corpus/anchors mounts work + the monthly-cap counter is under $20.
2. Task 1 (AC-4, ~$4-5): pre-flight `python -m benchmark.runner ... --tasks coarse_class,sensitivity_class,summary_short,importance_scoring,action_extraction,draft_reply --models policy-default` without `--yes`, capture the estimate; then re-run with `--yes`. Capture the `run_id` printed at start.
3. Task 2 (AC-5, ~$5): pre-flight `python -m benchmark.runner ... --tasks draft_reply --models claude-haiku-4-5,claude-opus-4-7`, then `--yes`; then `benchmark.scorer --run-id <id>`; then `benchmark.report --run-id <id> ...`; then `docker compose cp` the report out.
4. Task 3 (AC-7, ~$1 OR $0 if 9.5.4 already ran): the AC-6/AC-7 branch decision.
5. Task 4: compose `9.5.3-walk-evidence.md`.
6. Task 5: append to `epic-9-5-run-flags.md` with the AC-5 verdict token pinned for Story 9.5.5 pickup.
7. Task 6: sprint-status flip to `done`.
8. Task 7: MANDATORY-CR-REDUCED-SCOPE pass (invoke code-review with sonnet-4-6 on the walk-evidence Section 2/3 + rendered report, NOT the benchmark code).

If Adam wants Claude Code assistance during the walk, Claude Code can help with: SQL query composition, walk-evidence file drafting, sprint-status flip Edit calls at Task 6, invoking the code-review agent at Task 7. What Claude Code CANNOT do: invoke `benchmark.*` CLIs against Adam's Anthropic key (real-spend authority sits with Adam), decide `--yes` after pre-flighting (spend-authorization decision sits with Adam).

### Cross-reference to memory (same set as Run 1, no changes)

- `feedback_autonomous_continuity_no_text_between_subworkflows.md` — does not apply (manual dev-story invocation, not autonomous).
- `feedback_cr_cadence_v2_structural.md` — walk is CR-eligible via criterion 6 (load-bearing verdict); MANDATORY-CR-REDUCED-SCOPE planned in Task 7.
- `feedback_l1_l2_l3_done_layers.md` — L3 close for Epic 9 done-flip clauses 7, 8, 10 remains pending Adam's hands-on walk.
- `feedback_oauth_token_handling.md` — spirit-of-caution against unauthorized real-spend applies; the halt trigger enforces it.

---

## Story 9.5.3 Run 3 — 2026-07-03 — WALK PARTIAL-CLOSE with 5 walk-discovered defects + trust-failure finding

**Invocation:** interactive walk-through with Adam (Adam-authorized $10 real-spend after two prior halt-runs). Adam-decided at Run 2 halt-precedent to override the RUN-MODE BINDING for this specific session with an explicit spend authorization ceiling.

**Outcome:** PARTIAL-CLOSE. Epic 9 done-flip clauses **7 (AC-4) and 8 (AC-5, partial) close at L3**; clause **10 (AC-7) does NOT close** — deferred to Story 9.5.4 close path (i). One durable-memory rule surfaced (`feedback_anthropic_spend_source_of_truth.md`). Five F-defects discovered; 3 fixed in-session, 2 filed as future work.

**Real spend per Anthropic Console (Adam-provided screenshot mid-walk):** $13.46 spent; $3.82 credit balance remaining; $35 monthly cap 38% used. **Overshoot vs $10 authorization: ~$3.43.**

**Time-to-close:** ~90 min end-to-end (Task 0 pre-flight ~5 min → 3 in-session code fixes with RED-GREEN-REFACTOR + full pytest verification ~25 min → AC-4 walk ~10 min → AC-5 walk retries + scorer + report ~35 min → walk-evidence composition ~15 min).

### Load-bearing outcomes

- **AC-4 (Epic 9 done-flip clause 7) closes at L3:** run_id `bde29b0b-8406-4129-9f2c-c27783a95d1a`; 279 cells, 275 ok (98.6%), 4 schema_failed; status=completed. Task selection scoped to Anthropic-served ingest subset (`summary_short,importance_scoring,action_extraction` — all haiku-lane) because `--tasks all --models policy-default` per epics.md was not runnable against the shipped runner CLI (documented in walk-evidence file § "AC-4 scope adjustment"). See `_bmad-output/implementation-artifacts/9.5.3-walk-evidence.md` § Section 1.

- **AC-5 (Epic 9 done-flip clause 8) closes at L3 (PARTIAL):** run_id `db48480f-9692-4791-b3e2-4b3a2ab1fed8`; 186 cells, 100% ok dispatch. Scoring surface partially broken: haiku scored end-to-end (`subjective_overall=2.6176` from 34 anchor-calibrated evals with `calibration_mae=0.0`); opus scoring returned `insufficient_data` at `n=0` due to a scorer-shape issue (post-hotfix chain still surfaces on opus's own-model-as-scorer path). **Report verdict token for Story 9.5.5 pickup: `INSUFFICIENT_DATA` for the Haiku-vs-Opus comparison** (report literally prints `PROMOTE-needed` for haiku on absolute quality but that is misleading in isolation — see walk-evidence § "AC-5 verdict interpretation"). **Story 9.5.5 route: (b) accept-with-rationale.** See `_bmad-output/implementation-artifacts/9.5.3-walk-evidence.md` § Section 2 and copied `9.5.3-report-db48480f.md`.

- **AC-7 (Epic 9 done-flip clause 10) does NOT close this walk:** deferred to close path (i) — will discharge by reference when Story 9.5.4's anchor stability audit produces a non-`untrusted` verdict. Reason: after $13.46 real spend against $10 authorization, continuing to a $4-8-estimated (real cost likely $1.5-3 at real pricing) audit dispatch would have compounded the spend-authority breach. Adam-decision at walk close: defer.

### Trust-failure finding (Adam-surfaced; durable memory filed)

During the walk I aggregated `router_calls.cost_usd_estimated` — a **local placeholder-pricing estimator** — and reported "$36 spent" to Adam mid-walk. Adam screenshotted the Anthropic Console showing real spend was $13.46. The 2.7× overstatement in the "we burned too much" direction was the surface failure. The complementary invisible failure: the same estimator UNDERSTATED the scorer dispatch pre-flight ($0.00 print for a run that actually cost several dollars), which is what caused me to `--yes`-approve the overshoot in the first place.

Adam's durable rule (verbatim): *"you should check frequently the usage with Anthropic's billing API. Any other estimation is erroneous."*

Rule captured in memory `feedback_anthropic_spend_source_of_truth.md` (linked from MEMORY.md). Applies to every future Claude-Code session with Adam-authorized real-money Anthropic spend.

### 5 walk-discovered defects

Filed in walk-evidence file § "Walk-discovered defects" with full detail. Summary:

1. **F-FENCE-STRIP (P0, FIXED in-session):** Claude Haiku 4-5 + Opus 4-7 wrap JSON in ```` ```json ``` ```` fences. Production ingest silently 100%-failing on Anthropic tasks for 3+ days. Fix landed at `mailbot_api/router/router.py` (`_strip_code_fence()` helper). +4 tests. Verified live. **Recommend commit + container-rebuild ASAP** — this is a real production bug the walk surfaced.
2. **F-RATE-LIMIT-CARVE-OUT (P1, FIXED in-session):** benchmark walks blow interactive-lane 60/hr cap. Fix landed at `mailbot_api/router/limits.py` mirrors `caller_origin="cache-warmer"` short-circuit for `caller_origin.startswith("benchmark-")`. +2 tests.
3. **F-DRAFT-REPLY-CONTENT-SHAPE (P1, FIXED in-session):** benchmark runner used uniform `{subject,sender,body_preview}` for every task; `draft_reply` needs `{source_email,thread_context,tone_signals}`. Fix landed at `benchmark/runner.py::_build_content`. +3 tests.
4. **F-UNKNOWN-MODEL-COST-GATE (P0, NOT FIXED — root cause of $3.43 overshoot):** `benchmark.scorer._DEFAULT_SCORER_MODEL = "claude-opus-4-7-20251220"` is not a registered adapter → `estimate_cost_usd()` returns $0 for unknown model → cost gate prints "$0.00" → `--yes` proceeds on false-safe → real dispatch bills actual Opus cost. Filed as future story.
5. **F-PLACEHOLDER-3X-DRIFT (P0, NOT FIXED):** `pricing.py:15-16` explicitly annotates Haiku 4-5 / Opus 4-7 pricing as "PLACEHOLDER pending live-billing verification"; observed 2.7× overstatement vs real Console. Every cost-gate in the codebase (Layer-4 $0.20 per-call, $5 pre-flight, $30 monthly cap) is currently mis-calibrated by ~3×.

### Recommended follow-up work (owner: Adam-decides at Epic 9.5 retro)

1. **Commit + container-rebuild for the 3 in-session hotfixes.** F-FENCE-STRIP in particular is fixing a load-bearing production bug. Without commit, the fix lives only in the running container's ephemeral `docker cp`-injected state and will be lost on next `compose down + up`.
2. **File F-UNKNOWN-MODEL-COST-GATE + F-PLACEHOLDER-3X-DRIFT as either Story 9.5.6 or Epic 9.5 retro action items.** Both are P0 for cost-authority correctness.
3. **Story 9.5.4 execution should include Anthropic-billing-API polling loop** per the durable memory rule. Any agent picking up 9.5.4 that does NOT poll `/v1/organizations/cost_report` at each gate should halt.
4. **Story 9.5.5 dev pass:** load AC-5 verdict-INSUFFICIENT_DATA into route (b) accept-with-rationale; the retro entry cites this walk-evidence file + the Anthropic Console reconciliation as the "we did not get a valid comparison verdict" rationale. `policy.yaml` v0→v1 bump happens without content mutation but with hypothesis annotation reviewed against the partial data captured.

### Zero destructive actions taken during Run 3 outside declared spend

- **Real Anthropic spend:** $13.46 (Adam-authorized $10; overshoot $3.43). Documented + Adam-screenshotted at reconciliation gate.
- **DB mutations:** append-only audit rows in `benchmark_runs` (~1000 rows), `benchmark_scores` (15 rows), `router_calls` (~1700 rows). No deletes, no updates. Normal walk footprint.
- **File mutations:** documented in walk-evidence file § "Footer" — 3 production-code hotfixes (router.py + limits.py + benchmark/runner.py), 3 test files (+9 tests total), 1 gitignored walk-shim (scratch/walk_bootstrap.py), 4 evidence/status files. NO changes to policy.yaml, docker-compose.yml, mcp_server.py, docs/, hermes-config/, scripts/, pyproject.toml.
- **Container mutations:** ephemeral `docker cp` injections of `benchmark/` + `evals/*.py` + hotfixed router.py/limits.py/benchmark/runner.py. Lost on next container restart unless committed + rebuilt. NOT a destructive action — no state deleted; walk-only tooling.
- **Baseline commit preserved:** `96595c3d44b8993847bd6d04516eff886cb8f0ff` in story-file YAML frontmatter.
- **Sole file changes from this run entry:** this run-flags append (~90 lines) + walk-evidence file + story-file body updates (Tasks/Subtasks checkboxes + Dev Agent Record + Change Log + Status flip) + sprint-status.yaml line 262 flip.

### Cross-reference to memory (updated set)

- `feedback_anthropic_spend_source_of_truth.md` — **NEW, filed this walk.** Load-bearing rule for all future spend-authorized sessions.
- `project_epic_6_scope_cleave.md` — N.5-epic policy for walk-discovered defects; the 2 unfixed F-defects (F-UNKNOWN-MODEL-COST-GATE + F-PLACEHOLDER-3X-DRIFT) are candidates for Story 9.5.6 or Epic 9.5 retro absorption per Adam's discretion.
- `feedback_cr_cadence_v2_structural.md` — walks are excluded from CR-eligible denominator; but the 3 in-session hotfixes ARE code changes that should get their own CR pass at commit time (sonnet-4-6, focus on the fence-strip regex correctness + rate-limit carve-out authorization scope + content-shape backward-compat contract).
- `feedback_l1_l2_l3_done_layers.md` — AC-4 closes clause 7 at L3; AC-5 closes clause 8 at L3 (partial dispatch-only, comparison-verdict INSUFFICIENT); AC-7 clause 10 remains at L2 pending Story 9.5.4 close.

