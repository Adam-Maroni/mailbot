---
name: autonomous-epic-run
description: Autonomously run an entire BMAD epic from start to finish — pick the epic in progress (or the latest planned), then loop create-story → dev-story → code-review (with a different model than the dev agent) through every story until the epic is fully implemented. Use this skill whenever the user types "/autonomous-epic-run", asks to "run the epic autonomously", "finish the current epic without me", "loop through the remaining stories", or wants hands-off execution of a BMAD epic. Stops before the retrospective. Stages changes but never commits. Pushes through errors and flags them at the end.
---

# Autonomous Epic Run — Hands-Off BMAD Epic Executor

This skill runs an entire BMAD epic end-to-end without human intervention. It selects the target epic, loops through every remaining story — `create-story` → `dev-story` → `code-review` (under a different model than dev) → optional dev-environment verification — and only stops once every story in the epic is `done`. **It never runs the retrospective**, and it never commits; it stages changes and hands control back to the user.

## Prerequisites

This skill assumes the target project uses BMAD (the bmm module specifically). It invokes `bmad:bmm:workflows:create-story`, `bmad:bmm:workflows:dev-story`, and `bmad:bmm:workflows:code-review` as sub-workflows, and reads/writes `sprint-status.yaml` plus story files under a BMAD output directory. If those don't exist on the target project, this skill won't work — port the BMAD framework first, or this is the wrong tool.

Beyond BMAD, the skill assumes a few project conventions. Some are required, some can be reconfigured at the call site. See `PORTING.md` for the full target-project checklist.

## Why This Exists

Epic execution is a highly mechanical loop: look at sprint-status, ask SM for the next story, let Dev implement it, have a second model review it, apply the fixes, verify, move on. Running this manually for a 5–10 story epic is tedious and error-prone. The steps are already encoded in BMAD workflows — this skill is the orchestrator that chains them without pausing to ask the user between each one.

**Cadence contract:** the code-review subagent dispatch is the orchestrator's primary defense against the "ship-it-and-flag-for-retro" pattern that Epic 3 + Epic 4 retros documented. The cadence is set at Step 2.3.5 via §5.12 of the pre-review artifact (CR-cadence-mandatory surface classification), and Step 2.4 honors that verdict. **`MANDATORY-CR` is non-negotiable** — operational pressure cannot downgrade it (Adam-decided, Epic 4 retro action item #1, option A, 2026-06-02). If context budget cannot support the dispatch, the orchestrator HALTs and surfaces to the user; it does NOT silently skip.

## Project Conventions Referenced By This Skill

The skill refers to several paths and commands that are project-configurable. The defaults below match a typical BMAD setup; override them at the call site if your project differs.

| Reference                             | Default                                                  | What it is                                                            |
| ------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------- |
| `<bmad-output>/`                      | `_bmad-output/`                                          | Root of BMAD planning + implementation artifacts                      |
| `<sprint-status>`                     | `<bmad-output>/implementation-artifacts/sprint-status.yaml` | YAML index of every epic + story + status                          |
| `<epics-file>`                        | `<bmad-output>/planning-artifacts/epics.md`              | Canonical epic + story planning doc                                   |
| `<story-file>`                        | `<bmad-output>/implementation-artifacts/{story-id}.md`   | Per-story file with ACs, Dev Notes, File List, Completion Notes       |
| `<flags-file>`                        | `<bmad-output>/implementation-artifacts/epic-run-flags.md` | End-of-epic flag aggregation                                        |
| `<permission-log>`                    | `<bmad-output>/implementation-artifacts/permission-requests.log` | Auto-populated by hook (if installed); optional               |
| `<settings-file>`                     | `.claude/settings.json`                                  | Claude Code permission envelope                                       |
| `<dev-env-skill>`                     | Project-specific (e.g., `/debug-vista-manager` or `/debug-dev-env`) | Optional skill that verifies the dev environment starts cleanly |

If a path differs on your project, replace it wherever it appears below. If a referenced skill or file doesn't exist (e.g., no `<dev-env-skill>`), the relevant step is skipped — see Step 2.5 and Step 3.0.

## Operating Contract: Stay Inside the Permission Envelope

**This is a hard constraint, not a suggestion.** The user chose "autonomous" — if the skill causes permission prompts mid-run, it has failed. Plan every command, tool call, and workflow step around the permissions already granted in `<settings-file>`.

**The full envelope reference lives at [references/permission-envelope.md](references/permission-envelope.md)** — load it at Step 0.0 and any time a prompt happens. The short version is below.

### Permission Hygiene — top friction sources to actively avoid

These are the command shapes that empirically prompt during runs across many projects. The agent must _actively avoid_ these shapes — they are not safety nets to lean on, they are bugs to refuse.

| ❌ Don't do this                       | ✅ Do this instead                                                              | Why                                                                          |
| -------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `cd <subdir> && <test-cmd>`            | `<test-cmd> --rootDir=<subdir>` or your package manager's filter flag           | Permission matching does not unwrap compounds; `cd` prefix breaks every glob |
| `cd packages/api && npx jest`          | `npx jest --rootDir=packages/api` or your monorepo's `--filter` equivalent      | Same compound-exec gotcha                                                    |
| `tail -50 file.md`                     | `Read` tool with `offset` + `limit`                                             | `tail` triggers a Bash prompt; `Read` is always allowed                      |
| `head -100 file.md`                    | `Read` tool                                                                     | Same                                                                         |
| `cat file.md \| grep foo`              | `Grep` tool with `path: file.md`                                                | Pipe + grep both prompt; `Grep` is always allowed                            |
| `find . -name '*.ts'`                  | `Glob` tool with pattern `**/*.ts`                                              | `find` prompts; `Glob` is always allowed                                     |
| `ls <dir>`                             | `Glob` tool — bare `ls` is often not allowed; `Bash(ls -la *)` may be           | Project-specific allow-list policy varies                                    |
| `git commit -m "$(cat <<'EOF' …`       | Skill never commits. If a commit is needed, the run is over — surface to user   | This skill stages, never commits                                             |
| `node -e "complex script"` mid-run     | Write a `.mjs` file under a temp dir and `node <path>` it                       | Inline `node -e` quoting often escapes any `Bash(node -e *)` rule            |

If the agent finds itself reaching for one of the ❌ shapes, **stop and pick the ✅ alternative instead**. This is not a soft suggestion — it is the difference between an autonomous run and a 30-prompt slog.

### The five envelope rules

1. **Never run compound `cd … && …` commands.** Use package-manager filter flags, `--rootDir=<path>` equivalents, or `git -C <path>` instead.
2. **Prefer Read / Grep / Glob / Edit / Write tools over Bash.** They bypass permission rules entirely.
3. **Bare `ls` may or may not be allowed.** Use `Glob` for directory listings.
4. **If a required command isn't in the envelope:** find an allowed alternative, decompose into tool calls, or surface the gap ONCE up front. Never just take the prompt.
5. **Pre-flight before Phase 1.** Step 0.0 reads `<settings-file>` and verifies coverage.

Pass this contract through to every subagent: _"Stay inside the `<settings-file>` permission envelope — do not run commands that will prompt. Prefer tool-native filter flags over `cd X && <cmd>`."_

### Step 0.0 — Permission envelope pre-flight

Read `<settings-file>` and confirm coverage for the command shapes the run will need: test runners, lint/build, git operations, file listing, monorepo filter-exec compound shapes, and any dev-environment verification skill prerequisites. The full pre-flight checklist is at [references/permission-envelope.md](references/permission-envelope.md).

If anything is missing, surface ONCE with a single permission request before Phase 1. Do not start the main loop until the envelope is confirmed clean.

### Step 0.0b — Permission request log (optional, auto-populated if hook is installed)

If the project has a `PreToolUse` hook that logs permission-denying commands (e.g., to `<permission-log>`), the run benefits from a written feedback loop — every command that misses the allow-list lands in the log before the user sees the prompt. The agent doesn't have to log manually — but Phase 3.3's final report should cite the log if it was written to during the run.

If no such hook is installed, this step is N/A and Phase 3.3's final report says "no permission log configured" rather than citing one.

Full mechanics + format are at [references/permission-envelope.md](references/permission-envelope.md).

## Phase 0 — Target Epic Selection & Pre-Flight

### Step 0.1 — Pick the target epic

Read `<sprint-status>`.

**Pick the target epic using this priority:**

1. **An epic in progress** — any `epic-N` whose value is `in-progress`. If multiple, pick the lowest-numbered one.
2. **Otherwise, the latest planned** — the highest-numbered epic whose value is `backlog` (skip `done` and skip retrospective keys).

If no epic satisfies either condition, halt and report: "No epic to run — the latest epic is already `done`. Create a new one first." This is one of two hard-halt conditions in the skill (the other is in Step 0.2).

Record:

- The epic number (integer or decimal, e.g., `27`, `22.5`)
- The full ordered list of that epic's story keys
- The retrospective key (e.g., `epic-28-retrospective`) — **excluded** from the execution loop

**Story ordering:** Use the order they appear in `<sprint-status>` (top-to-bottom within the epic's block). That order is canonical — `create-story` and `dev-story` pick up the next `backlog` / `ready-for-dev` story **globally across the whole file**, so upstream orphan stories from other epics would be picked up first. That's why Step 0.2 exists.

### Step 0.2 — Pre-flight: no upstream orphan stories

Before starting the loop, scan every epic _earlier_ than the target. None should contain stories in `backlog` or `ready-for-dev` — those are orphans that `create-story` would grab before reaching the target epic, silently derailing the run.

If any orphans exist, halt and report: "Epic {M} has unresolved story {story-id} in status {status}. Clean up before running autonomously — `create-story` picks globally and would route around the target epic." This is the second hard-halt condition.

If the target epic itself has stories already `ready-for-dev`, `in-progress`, `review`, or `done`, that's normal — this skill is designed to resume. Continue.

### Step 0.3 — Announce

Report the target epic and the story list to the user in one line: "Target epic-{N}: {total-count} stories, {remaining-count} remaining. Running blocker scan…"

### Step 0.4 — Blocker Scan (mandatory, gating)

**Why this exists:** mid-run halts are the failure mode autonomous skills must avoid; the fix is to forecast every blocker before the main loop runs so the user resolves them once, upfront. A common case: a UI-only story whose mockup was never produced — predictable from `<epics-file>` the moment the epic was selected.

**For each unstarted story** (`backlog`, `ready-for-dev`, or `in-progress`) in the target epic:

1. **Locate the story's authoritative AC source.** Prefer the story file at `<story-file>` if it exists; otherwise fall back to the epic's section in `<epics-file>`. Read the Acceptance Criteria and Dev Notes sections.

2. **UI-gate check.** Regex-match the ACs (case-insensitive) against UI nouns: `popover`, `button`, `slider`, `spinner`, `badge`, `column`, `layout`, `card`, `toolbar`, `modal`, `dialog`, `page`, `dropdown`, `menu`, `tab`, `panel`, `header`, `footer`, `sidebar`, `chart`, `tooltip`, `banner`, `form`, `field`, `input`, `checkbox`, `radio`, `toast`, `icon`, `empty state`, `loading state`, `error state`. If any match, the story may have UI ACs. Then **apply the no-frontend carve-out**:
   - If PORTING.md's path-placeholder table marks `<frontend-src>` as N/A (this project has no graphical frontend — e.g., MailBot, where Discord is the UI and the Discord client is owned by an external container), **suppress the UI-gate flag entirely**: write `UI-gate N/A — project has no graphical frontend per PORTING.md; UI nouns in ACs refer to Discord-rendered text, owned by an external container` and move on. Do NOT proceed to mockup verification — it cannot succeed and produces noise.
   - Otherwise (project has a real frontend), determine mockup presence:
     - Read the story file's `### Design Mockup` section. If it names a specific file path, verify the file exists.
     - If the Design Mockup field is `N/A`, `TBD`, blank, or a placeholder, do a content-based search: `Glob **/*.html`, then `Grep` the hits for the story's key nouns. If a plausible mockup is found but not referenced in the story file, list it as a candidate for the user to confirm.
     - If no mockup is referenced AND none found by content search, flag `BLOCKED(mockup-missing)`.
     - **Do not hard-code a single canonical mockup location.** Mockups can live anywhere.

3. **External-dep gate.** From the story's Dev Notes:
   - **ORM models** named as new (Prisma/TypeORM/SQLAlchemy/etc.): `Grep` the current schema file — if the model is absent AND the story doesn't say "new migration in this story", flag `BLOCKED(missing-orm-model)`.
   - **Env vars** referenced: check the project's `.env.example` (or equivalent). If missing, flag `WARNING(env-var-not-documented)`.
   - **External API contracts** referenced: confirm they exist.

4. **Cross-story-dep gate.** Parse any `Depends on:` line from the story block in `<epics-file>`. Note the dependency graph in the report — informational, not a blocker.

5. **Model-contract gate.** Confirm the review model selected in Phase 1 can be spawned (the `Agent` tool must accept the `model` parameter). If not, flag `BLOCKED(model-contract-violation)` — non-bypassable.

**Output: a single consolidated readiness report**, formatted as a markdown table, printed to the user BEFORE Phase 1:

```
Pre-flight readiness report for epic-{N} ({K} unstarted stories)

Story  | UI? | Mockup         | External deps        | Dep chain | Status
-------|-----|----------------|----------------------|-----------|----------
N-3    | Yes | MISSING        | —                    | ← N-1     | BLOCKED
N-4    | Yes | MISSING        | —                    | ← N-1     | BLOCKED
N-5    | No  | —              | NewModel OK          | ← N-1     | READY
N-6    | No  | — (UAT story)  | —                    | ← N-1..5  | SEQUENCED

2 blockers. Resolve before I proceed:
- N-3 needs an approved UI mockup
- N-4 needs an approved UI mockup

Options:
(a) You'll provide mockups and re-invoke /autonomous-epic-run — I stop now
(b) Skip the 2 blocked stories and run the ready set only
(c) Hand off to a UX agent for mockup design first — I stop

Zero permission prompts expected during the run itself.
```

**Gating rule:** if any story is `BLOCKED`, **stop the run** and wait for user resolution. Do not enter Phase 1.

**If zero blockers:** print "Pre-flight clean — 0 blockers, {K} stories ready. Starting main loop." and proceed.

## Phase 1 — Determine Dev vs Review Models

The core invariant: **the code reviewer must use a different model than the developer.**

Read the model currently powering this session (the `You are powered by the model named ...` line — e.g., `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5`). This becomes the **dev model**. For the **review model**:

| Dev model running now | Review model to use                                                   |
| --------------------- | --------------------------------------------------------------------- |
| `claude-opus-4-7`     | `claude-sonnet-4-6`                                                   |
| `claude-sonnet-4-6`   | `claude-opus-4-7`                                                     |
| `claude-haiku-4-5`    | `claude-opus-4-7`                                                     |
| anything else         | `claude-opus-4-7` (safe default — most skilled at adversarial review) |

**How to invoke code review with a different model:** use the `Agent` tool with the `model` parameter set to the review model. The review subagent runs in an isolated context, so it loads fresh and grades independently.

Record both model IDs.

### Phase 1.5 — Activate `#yolo` mode for sub-workflows during the loop

BMAD sub-workflows (`create-story`, `dev-story`, `code-review`, `sprint-planning`) are governed by `_bmad/core/tasks/workflow.xml`. By default, that engine pauses after every `template-output` section asking "Continue to next step? (y/n/edit)". For 5 stories × ~10 template checkpoints × 3 workflows each, that's ~150 prompts — death-by-a-thousand-prompts in an autonomous run.

`workflow.xml` defines a **`#yolo` execution mode** explicitly for this case: _"Skip all confirmations and elicitation, minimize prompts and try to produce all of the workflow automatically by simulating the remaining discussions with a simulated expert user."_

**Before invoking the first sub-workflow, declare `#yolo` mode for sub-workflows used during the loop.** When invoking a BMAD skill, include a preamble like: _"Proceed in `#yolo` mode per the autonomous-epic-run contract — no interactive prompts, make sensible defaults, simulate expert-user responses, produce the full artifact without pausing."_

**`#yolo` mode SCOPE — critical:**

`#yolo` applies ONLY to the four sub-workflows used by this skill's main loop: `create-story`, `dev-story`, `code-review`, `sprint-planning`. It does **NOT** apply to:

- **`retrospective`** — always interactive, even after autonomous epic completion. The retro is a discussion between the user and the agent; `#yolo` would silently skip the back-and-forth that makes the retro valuable.
- **Any sub-workflow invoked AFTER the autonomous run finishes**, in any later session. `#yolo` is scoped to the lifetime of this skill's main loop, not the broader Claude Code session.

**Termination of `#yolo`:** at the end of Phase 3 (after the final report is emitted), explicitly note in chat output: _"`#yolo` mode is now off. Any subsequent BMAD workflow invocation — including the retrospective — runs interactively by default."_ This is the structural fix for the bug where retros silently inherited `#yolo` from a prior autonomous run.

Trade-off acknowledged: `#yolo` trades intermediate review for end-to-end throughput **during the loop**. Every story still gets reviewed by a different-model adversarial reviewer at Step 2.4 — that's the real quality gate.

## Phase 2 — Main Execution Loop

### Loop Continuity Contract — read before every sub-workflow returns

**Why this exists:** the most common stall pattern is the orchestrator emitting a polished "Story X done — returning control" message to the user, and the run effectively ending there. Even a one-line progress marker between sub-workflow invocations ends the turn — when the assistant's only action after a sub-workflow returns is plain text (even one line), Claude treats that text as the response and the run stalls.

**The shape of the loop is `while`, not "step 1 → step 2 → step 3":**

```text
while (any story in target epic is not `done`) {
  Step 2.1  re-read sprint-status.yaml
  Step 2.2/2.3/2.4  invoke the next sub-workflow per status
  Step 2.3.5 / 2.4.4 / 2.4.5 / 2.4.6 / 2.4.7 / 2.4.8  apply the gates
  Step 2.5  conditional dev-env verification
  Step 2.6  selective stage
  // CONTINUE — do NOT break, do NOT address the user, loop to top
}
// only after the while-loop exits do we enter Phase 3
```

**Four rules that govern the orchestrator (this skill, the parent agent) between sub-workflow invocations:**

1. **Sub-workflow returning is NEVER a stopping condition. The next assistant action MUST be a tool call.** When `bmad:bmm:workflows:create-story`, `bmad:bmm:workflows:dev-story`, or `bmad:bmm:workflows:code-review` returns, the very next thing the orchestrator emits must be a tool invocation — specifically `Read` on `<sprint-status>` (Step 2.1). Not a sentence of text. Not a one-line marker. Not a "✓ Story X done" acknowledgment. **Plain assistant text following a sub-workflow return ends the turn — that is the mechanism the run stops by.** Treat the sub-workflow's return as a token in your reasoning, not a signal to address the user. The only mid-loop exits are the hard-halts in the Error Handling Summary table.

2. **Do NOT emit ANY user-facing text between sub-workflow invocations.** Between a sub-workflow returning and the next sub-workflow invocation (or the loop terminating), the orchestrator emits zero plain-text messages. All assistant output during the loop is either (a) tool calls (`Read`, `Skill`, `Agent`, `Edit`, `Bash`, etc.) or (b) gate-failure HALT messages from the Error Handling Summary table. The user sees no story-by-story narration during the run; the full story-by-story rollup lands at Phase 3.3.

   Sub-skills will produce rich completion reports of their own ("Story X-Y — implementation complete · all N ACs · Status: review"). Consume those internally — read the words to inform the gate checks at 2.3.5 / 2.4.4 / 2.4.5 / 2.4.6 / 2.4.7 / 2.4.8 and the eventual Phase 3.3 final report. Do not re-emit them. Do not summarize them. Do not echo even a one-line acknowledgment. The user gets exactly ONE message during the loop's lifetime: the Phase 3.3 final report (plus the Phase 3.5 manual-verification prompt, which is a separate architectural beat).

   If the impulse arises to write _anything_ — even "Story X-1 created · status=ready-for-dev" — between two sub-workflow calls, that is the bug this contract exists to prevent. The fix is mechanical: invoke the next tool instead.

3. **The `#yolo` contract from Phase 1.5 is a sub-workflow contract; this contract is the parent-agent equivalent.** `#yolo` keeps sub-workflows from prompting the user; the Loop Continuity Contract keeps the orchestrator from prompting the user — including by accident, via a one-line status update that Claude's turn-handling treats as a response. Both must hold simultaneously for the run to actually be autonomous. If either leaks, the run silently degrades into one-story-at-a-time.

4. **Inline-execution corollary.** Rules 1-3 talk about "sub-workflow returning" as the trigger event. But the orchestrator may also run a sub-workflow's instructions _inline_ — walking through `dev-story` Steps 1 → 9.5 itself, calling Edit/Bash/Read directly to satisfy each step, never delegating to a subagent that would `return` a tool result. In that case there is no return event. The trap: when the orchestrator finishes the inline workflow's terminal step (e.g., dev-story Step 9.5 flips story status to `review`), it _feels_ like the workflow is done — same psychological cue as a real return — and the urge to write a one-line wrap-up is identical. **Same fix: the moment the inline workflow's terminal step completes, the next assistant action is a tool call, not text.** Specifically: after dev-story Step 9.5 flips status to review, the very next tool call is the `Agent` invocation that spawns the Step 2.4 code-reviewer for the same story (or `Read sprint-status.yaml` if you're choosing to re-read state first). NOT a wrap-up sentence. The inline-execution path is just as exposed as the delegated path; the fix is the same.

**Self-check at every workflow boundary:** before any assistant output following EITHER (a) a sub-workflow `Skill`/`Agent` returning OR (b) the orchestrator finishing a sub-workflow's instructions inline, ask: _"Is my next action a tool call, or am I about to write text? If text — even one informative line — I am about to end the turn and break the loop. The next action must be a tool call."_ Apply this self-check especially aggressively at moments that _feel_ like natural pause points: status flips, gate completions, "phase 1 done, moving to phase 2," "all ACs satisfied." Those feelings are the bug surface.

Repeat until every story in the target epic is `done`:

### Step 2.1 — Re-read sprint status

Always re-read `<sprint-status>` at the top of the loop. Do not cache — workflows mutate the file.

| Status          | Action                                 |
| --------------- | -------------------------------------- |
| `done`          | Skip, go to next story                 |
| `backlog`       | Call **Step 2.2 — Create Story**       |
| `ready-for-dev` | Call **Step 2.3 — Dev Story**          |
| `in-progress`   | Call **Step 2.3 — Dev Story** (resume) |
| `review`        | Call **Step 2.4 — Code Review**        |

If every story is `done`, exit the loop and go to **Phase 3 — Wrap Up**.

### Step 2.2 — Create Story

Invoke `bmad:bmm:workflows:create-story` via the `Skill` tool with this preamble (verbatim — do not paraphrase, the `#yolo` + Loop Continuity directives are load-bearing):

> _"Proceed in `#yolo` mode per the autonomous-epic-run contract — no interactive prompts, simulate expert-user responses, produce the full artifact without pausing. When you finish, return tersely: just the new story key and status. The orchestrator (autonomous-epic-run) is mid-loop and will keep iterating; do not address the user, do not write a 'returning control' message, do not produce a story-complete summary — those belong to the orchestrator's end-of-epic report at Phase 3.3."_

After it returns, the next assistant action **must be a tool call** — specifically the `Read` on `<sprint-status>` from Step 2.1. Do not emit a progress marker, an acknowledgment, or any other plain-text message. Per the Loop Continuity Contract above, plain-text output here ends the turn and stalls the run. This rule is mechanical, not stylistic: even a sentence as short as `→ Story X-2 created · status=ready-for-dev` is enough to break the loop.

**Sanity check:** if the picked story is not from the target epic (orphan slipped past Phase 0), flag CRITICAL in `<flags-file>` and halt — sprint state corruption risk.

### Step 2.3 — Dev Story (dev model = this session)

Invoke `bmad:bmm:workflows:dev-story` via the `Skill` tool with this preamble (verbatim):

> _"Proceed in `#yolo` mode per the autonomous-epic-run contract — implement every task and AC, run tests, mark `review`, update Dev Agent Record, do not pause for confirmation. When you finish, return tersely: story key, final status, and a one-sentence headline (under 30 words). Do NOT produce a per-AC table, a 'what shipped' section, a files-changed listing, or a 'returning control to the orchestrator' message — those re-emit through the parent agent and look like a turn-end to the user, breaking the autonomous loop. The orchestrator already has the story file and `git status` and will assemble the full report at Phase 3.3."_

This implements the next `ready-for-dev` story in this session, runs tests, and marks it `review`. After it returns, the next assistant action **must be a tool call** that begins Step 2.3.5 — for example, `Read` on the story file at `<story-file>` to verify the file list and ACs before generating the pre-review artifact. Do not emit a progress marker, an acknowledgment of the dev sub-skill's return, or any other plain-text message between dev-story returning and the first 2.3.5 tool call. Per the Loop Continuity Contract, plain-text output here ends the turn — the run will appear to "stall after dev-story finishes" exactly because that text was emitted.

### Step 2.3.5 — Pre-Review Self-Audit Gate

**Why this exists:** soft "should self-review" commitments produce zero audits in practice. This step is a hard refuse-to-proceed gate that folds in three previously-soft commitments: self-adversarial review, AC-vs-code spec audit, and an early branch of the File-List-vs-git check.

**Where this fires:** AFTER `dev-story` (Step 2.3) returns and BEFORE the code-review subagent (Step 2.4) is spawned.

**Hard contract:** the gate refuses to proceed to Step 2.4 if the artifact is missing or empty. There is no `[deferred]` escape hatch.

**The artifact:** `<bmad-output>/implementation-artifacts/{story-id}.pre-review.md` — sibling to the story file.

**Required structure (all five sections mandatory):**

```markdown
# Pre-Review Self-Audit — {story-id}

**Generated:** {YYYY-MM-DD HH:MM} by {dev-model-id}
**Story file:** {relative path}
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

For each AC: write one line `AC-N: <verdict>` where verdict is `MATCH` | `DRIFT — <what drifted>` | `N/A — <why>`. If any drift, update the AC text in the story file BEFORE this audit completes.

## 2. File-List-vs-git diff check

Run `git status --porcelain` and cross-reference against the story's `### File List`. For each path in File List: `TRACKED` | `UNTRACKED — <path>` | `MODIFIED-NOT-STAGED — <path>`. Fix any UNTRACKED before this audit completes.

## 3. Adversarial self-review

3-10 self-caught issues with severity. Format: `- [SEVERITY] <file:line> — <one-sentence finding>`. ZERO issues is suspect — flag in section 4.

## 4. Self-caught issues remediated this audit

For each issue from section 3: **FIX NOW** | **ESCALATE TO REVIEWER** | **ACCEPT WITH RATIONALE**. If section 3 was empty, write `Audit was shallow — re-run with harsher self-criticism.` and re-run.

## 5. Posture Audit

12 named checks (5.1 lockfile / 5.2 cross-doc / 5.3 lifecycle-string / 5.4 multi-consumer / 5.5 screenshot-perception / 5.6 upstream-contract / 5.7 module-mutable-state / 5.8 dev-fixture seed-vs-production-shape parity / 5.9 grep-verify-cited-figures / 5.10 producer-boundary contract / 5.11 git-evidence consistency / **5.12 CR-cadence-mandatory surface classification**). Each requires runnable command + actual output OR explicit `N/A — <justification>` — EXCEPT §5.12, which ALWAYS runs and produces a binary verdict `MANDATORY-CR` or `GATE-COVERAGE-ELIGIBLE` consumed by Step 2.4.

**Full check definitions, anti-patterns, and required output formats are at [references/posture-audit.md](references/posture-audit.md).** Load that file when generating section 5.
```

**Why the 12th check matters at THIS gate, not later:** §5.12 (CR-cadence-mandatory surface classification) is the structural binding that closes the Epic 4 retro action item #2 failure mode — "the orchestrator decided under context pressure to skip CR on a load-bearing-orchestrator / privacy-invariant story." The classification is recorded into the pre-review artifact BEFORE Step 2.4 evaluates whether to dispatch CR; the artifact is the contract, not the orchestrator's runtime memory. The Adam-decided rule (Epic 4 retro 2026-06-02, action item #1, option A): once §5.12 records `MANDATORY-CR`, Step 2.4 MUST dispatch the CR subagent; if context is genuinely insufficient to support the dispatch, the orchestrator HALTs and surfaces the gap to the user — it does NOT silently downgrade to gate-coverage-only.

**Refuse-to-proceed enforcement:**

1. Before spawning Step 2.4, check that `{story-id}.pre-review.md` exists
2. Verify all five sections are present (`## 1.` through `## 5.`)
3. Verify section 3 has at least one severity-tagged bullet (or the explicit shallow-audit re-run)
4. Verify section 4 has dispositions for every section 3 issue
5. Verify section 5 has all 12 sub-sections (5.1–5.12) with command output OR N/A justifications (5.12 has NO N/A path; its verdict is always `MANDATORY-CR` or `GATE-COVERAGE-ELIGIBLE`), plus the summary table
6. If ANY check fails, HALT and emit:

```
🛑 Pre-Review Self-Audit gate (Step 2.3.5) — story {story-id} cannot proceed to code-review.

Reason: {missing file | section N missing | section 3 empty | section 4 incomplete | section 5 incomplete: <which> | section 5 missing command output for <which>}

Required: pre-review artifact with all 5 sections per template + 11 Posture Audit sub-sections per references/posture-audit.md.

Do not spawn the code-review subagent until this artifact is complete.
```

7. Do NOT spawn Step 2.4. Do NOT advance sprint-status. The dev model produces the artifact, then the loop retries the gate.

**Why hard refuse, not loud-fail:** loud-fail variants produce zero audits in practice. Hard refuse is the only mechanism shape that survives contact with autonomous execution.

### Step 2.4 — Code Review (review model, different from dev)

**Cadence binding — Adam-decided in Epic 4 retro 2026-06-02, action item #1 (option A):**

1. Read the pre-review artifact's §5.12 verdict (the line `Cadence verdict: MANDATORY-CR` or `Cadence verdict: GATE-COVERAGE-ELIGIBLE`).
2. If the verdict is **`MANDATORY-CR`**: dispatch the CR subagent below. **No escape hatch.** Context pressure / token budget / "the four gates are green and the dev was thorough" are NOT valid reasons to downgrade. If the dispatch genuinely cannot proceed (e.g., the Agent tool errors, the review model is unavailable), HALT the run and surface to the user with the §5.12 evidence — do NOT silently skip and mark `done`.
3. If the verdict is **`GATE-COVERAGE-ELIGIBLE`**: CR subagent dispatch is OPTIONAL. The orchestrator MAY skip Step 2.4 entirely if context budget warrants — write the gate-coverage-only rationale into the story's Completion Notes (template: `Gate-coverage-only cadence per §5.12 GATE-COVERAGE-ELIGIBLE verdict — no criterion fires. Surface is <mechanical CRUD on already-CR-cleared boundary | prompt-module shim | schema-only migration | pure-doc>.`). Skipping is recorded; the four green gates ARE the evidence for `done`.

**Anti-pattern (the Epic 3 + 4 retro failure mode this binding closes):** a `MANDATORY-CR` story shipped under gate-coverage-only cadence because "the orchestrator weighed remaining context budget and decided to skip." Operational pressure does NOT override the §5.12 verdict. If you observe yourself reaching for this rationalization mid-run, STOP and HALT — the gap goes to the user, not to a silent downgrade.

**If the verdict is MANDATORY-CR (or the orchestrator chooses to dispatch on a GATE-COVERAGE-ELIGIBLE story for safety):** spawn the code review as a subagent under the **review model** from Phase 1:

```
Invoke: Agent tool with:
- subagent_type: "general-purpose"
- model: "<review-model-id-from-phase-1>"
- description: "Code review for {story-id}"
- prompt: "Run the BMAD code-review workflow for the current story in review status.
  Invoke the Skill tool with skill='bmad:bmm:workflows:code-review' in #yolo mode
  (no interactive prompts, simulate expert-user). The workflow will find 3-10 issues
  and append them as unchecked action items to the story's Tasks/Subtasks section.
  Do NOT fix the issues yourself — the goal is just to produce the review. Return
  tersely as a tool result the parent will consume: (a) story ID reviewed,
  (b) count of issues found, (c) one-sentence headline of biggest concern. Under
  80 words. Do not produce a per-issue table, a markdown report, or any
  user-facing framing — the parent orchestrator is mid-loop and will assemble
  the final report at Phase 3.3."
```

When the subagent returns, the story has fresh unchecked action items. The next assistant action **must be a tool call** that begins triaging those items — typically `Read` on the story file to inspect the appended action items, then `Edit` to apply fixes. Do not emit a progress marker, an acknowledgment of how many issues the reviewer found, or any other plain-text message between code-review returning and the first triage tool call. After fixes are applied and (if any non-trivial fixes happened) the review loop has run, proceed directly into Steps 2.4.4 → 2.4.8 via tool calls and then back to Step 2.1's `Read sprint-status.yaml`. Per the Loop Continuity Contract, plain-text output here ends the turn — this is the most common stall point because review-issues-found feels like a natural moment to summarize.

#### Applying the review's action items

After the review subagent returns:

**(a) Triage and apply fixes — use your judgment.**

- **Apply now** if it's a clear win: security, correctness, missing test coverage, broken type, violated project rule, accessibility / i18n gap. Fix it, check the box, add a one-line note.
- **Skip and document** if it's subjective: stylistic, speculative refactor, "consider extracting…". Leave the box unchecked and add `[deferred: reason]`.

Never ignore security or correctness items.

**(b) Re-verify after fixes.** If any non-trivial fixes were applied, re-run the review. Two rounds max — past that, log it and keep moving (infinite review loops are a known failure mode).

### Step 2.4.4 — Dev Agent Record Completeness Gate

**Before marking a story `done`**, verify the story file's Dev Agent Record:

1. `### Agent Model Used` — must name a model
2. `### Completion Notes List` — must have at least one bullet per completed task
3. `### File List` — must list every file. If documentation-only: `None — documentation story, no source files modified.`
4. The story's `Status:` header line must be `done` in the file itself (not just sprint-status.yaml).

If any field is blank: fill it from evidence (grep, git status, code reading). Do NOT skip or write `[deferred]`.

**Why the File List matters:** Step 2.4.6 (File-List-vs-git) and Step 2.6 (selective staging) both parse it. An empty File List makes both silently pass while staging nothing — a double failure.

### Step 2.4.5 — UI-Scope Pre-Flight Check

**Project-level exemption (check first):** if PORTING.md's path-placeholder table marks `<frontend-src>` as N/A (the project has no graphical frontend), **this entire gate is N/A**. Write `Step 2.4.5 N/A — project has no graphical frontend per PORTING.md; UI ACs satisfied by non-graphical surfaces (Discord-rendered text, CLI output, prompt modules)` to `<flags-file>` and skip to Step 2.4.6. The gate's silent-UI-scope-cut detection assumes a stack with React/Vue/Svelte components; without that stack it cannot fire correctly.

Otherwise (project has a graphical frontend), before marking a story `done`, scan its ACs for UI nouns (`popover`, `button`, `slider`, `badge`, `column`, `layout`, `card`, `toolbar`, `modal`, `dialog`, `page`, `dropdown`, `menu`, `tab`, `panel`, `header`, `footer`, `sidebar`, `chart`, `tooltip`, `banner`, `form`, `field`, `input`, `checkbox`, `radio`).

If any AC contains a UI noun AND the File List has zero UI source files (no `.tsx` / `.vue` / `.svelte` / framework-specific component extensions, or only test files), this is a **silent UI scope cut**:

1. Do NOT mark `done`
2. Add CRITICAL flag to `<flags-file>`: "Story X-Y has UI ACs but no UI source files in File List. Suspected silent UI scope cut. Reopen and complete UI before marking done."
3. Set status back to `in-progress` and loop back to Step 2.3

**Exception:** Documentation-only stories where AC mentions UI descriptively ("document the toolbar architecture"). Bias toward reopening.

### Step 2.4.6 — File-List-vs-git cross-check gate

Before marking `done` (after 2.4.5 passes):

1. Parse `### File List` from the story file
2. Skip directory paths (trailing `/`), `(deleted)`/`(removed)` annotations, and commentary
3. For each remaining path: `git ls-files --error-unmatch "<path>"` from repo root
4. If any path exits non-zero, the file is **untracked** — HALT

On HALT:

```
🛑 File-List-vs-git gate — story {story-id} has {N} untracked files:
- path/to/file-a.ts
- path/to/file-b.tsx

Story NOT marked done. Resolve one of:
(a) `git add` the listed files, then retry
(b) Remove them from the story's File List if they shouldn't be tracked
(c) Cancel the autonomous run
```

Do NOT advance sprint-status. Do NOT stage. Wait for user resolution, then retry.

**Dry-run scenarios** at [dry-run-scenarios.md](dry-run-scenarios.md) walk a synthetic untracked-file HALT and a clean pass-through.

### Step 2.4.7 — Middleware-Real-Bootstrap Gate

**Why this exists:** module-level HTTP-client mocks (`axios`, `fetch`, `httpx`, `requests`) and over-mocked test scaffolds create a false integration boundary. Unit tests pass on mocked clients while the real wiring (auth headers, error filters, validation, the project's domain-specific request gateway) is broken. Integration tests hitting the real wiring catch wiring-level bugs that thousands of unit tests miss.

**After Step 2.4 passes, before marking `done`:** scan File List for any pattern below. **Stack adapters are listed per language** — apply the one that matches the project's architecture. (For MailBot, see "MailBot-specific reframing" below — the gate is reframed around the Router contract rather than HTTP wiring.)

- **NestJS/TypeScript backend:** new/modified controller with `@Post` / `@Put` / `@Patch` / `@Delete` decorators
- **FastAPI/Python backend:** new/modified route with `@app.post` / `@app.put` / `@app.patch` / `@app.delete` decorators, OR an `APIRouter` instance with the same decorators (`@router.post`, etc.)
- **Express/Koa backend:** new/modified route registered via `app.post(...)` / `router.put(...)` / similar
- **Django/Rails/Flask backend:** new/modified view function handling a state-changing method (POST/PUT/PATCH/DELETE)
- **Frontend hook/function calling state-changing API**: new/modified frontend code doing `axios.post/put/patch/delete`, `fetch(..., { method: 'POST'|... })`, or your project's typed-API-client equivalent for create/update/delete/upload

**If either pattern is present, verify AT LEAST ONE of:**

1. **Backend integration test** — a test that boots the real HTTP server / app instance WITH the real auth + error-handling middleware wired up, hitting via an HTTP client, asserting against the actual response shape your error filter produces. Stack examples:
   - **NestJS:** `Test.createTestingModule` + supertest, asserting against the project's `HttpExceptionFilter` output shape (e.g., RFC 7807 `.detail` not raw `.message`)
   - **FastAPI:** `from fastapi.testclient import TestClient` (or `httpx.AsyncClient(app=app)` for async) + the real app object including all `app.include_router` calls and `app.add_middleware` registrations, asserting against the actual response body
   - **Django:** `django.test.Client` with the real URL conf
   - **Flask:** `app.test_client()` with all blueprints registered
2. **Frontend hook uses your project's typed API client** — not bare `axios`/`fetch`. The typed client routes through the shared HTTP layer with CSRF interceptor / auth / error normalization
3. **End-to-end test** (Playwright/Cypress/etc.) exercising the loop

**NOT satisfied by:** unit tests mocking the HTTP client, controller/view unit tests with mock-function request objects, "unit tests green" alone, "auth flag set in bare client" alone.

**MailBot-specific reframing (no graphical frontend, Router as the integration boundary):**

For MailBot specifically, the HTTP-client mock framing degrades — there is no graphical frontend, and most state changes flow through the **Router contract** (`mailbot_api/router/router.py`'s `ask_router(...)` orchestration), not through HTTP endpoints. When PORTING.md marks `<frontend-src>` as N/A AND the touched file is under `mailbot_api/`, apply this reframing:

- **In scope:** any new/modified verb (`mailbot_api/verbs/*.py`), any new/modified `ask_router` call site, any new/modified state-changing operation against the SQLite DB (writes through `mailbot_api/db/queries.py`), any new/modified action drainer or sync worker logic.
- **Verification options (need at least one):**
  1. **Router-real integration test** — test boots a real `ask_router(...)` call against either real Ollama or a fake `ModelAdapter` registered at the adapter boundary (NOT mocking `router.py` itself). The test asserts against the actual `RouterResult` / `RouterError` shape, including precondition errors (e.g., `sensitivity_not_classified`), budget guard errors, and lane-routing behavior.
  2. **DB-real integration test** — test runs against a real SQLite database (in-memory `:memory:` or a temp file) with the real schema migrations applied, exercising the verb / drainer / worker end-to-end. NOT a mocked `queries.py`.
  3. **HTTP-real integration test for `mailbot_api/main.py` endpoints** — `TestClient(app)` exercising `/v1/chat/completions`, `/v1/embeddings`, `/health`, `/v1/health` with the real app including the real Router and real DB connection.
- **NOT satisfied by:** mocking `ask_router`, mocking `queries.py`, mocking `OllamaAdapter` / `AnthropicAdapter` above the adapter boundary, or unit-testing a verb in isolation from its DB and Router dependencies.

**Action if gate fails:**

- Do NOT mark `done`
- CRITICAL flag in `<flags-file>`: "Story X-Y ships {endpoint / verb / Router call site} but no integration test / typed-client routing / E2E test. Middleware-Real-Bootstrap Gate failed."
- Set status to `in-progress` and loop back to Step 2.3

**Exemptions:** read-only GETs with no auth/CSRF requirements (rare), pure-function stories, markdown/config-only. For the MailBot reframing: pure read-only verbs that touch only `SELECT` queries AND don't trigger Router calls (e.g., `count_emails`) — but bias toward DB-real testing even for reads, because the SQLite WAL + executor-write pattern is wiring-sensitive.

### Step 2.4.8 — Verbose-Row Truncation Gate

**Why this exists:** without an explicit truncation contract, sprint-status rows accrete a paragraph at every state transition. Sprint-status's job is to be the _index_ of sprint health, not the _content_. Story files are the canonical content home.

**Where this fires:** AFTER all `done`-gates (2.4.4 → 2.4.7) pass and BEFORE flipping the row to `done`.

**Hard contract (when flipping to `done`):**

1. Capture verbose narrative from the in-progress row
2. Append to `## Completion Notes` in the story file with a `### {YYYY-MM-DD} — {phase}` header
3. Replace the sprint-status row with a 1-2 sentence headline + pointer to the story file's completion notes

**Templates (sprint-status row shape, completion-notes section shape, refuse-to-proceed enforcement) are at [references/completion-notes-templates.md](references/completion-notes-templates.md).** Load that file when flipping a story to `done`.

**Apply going forward only.** Existing rows in the target project retain historical bloat as audit trail — do NOT retroactively rewrite. The first row using the new pattern is the next `done`-flip after this gate ships.

### Step 2.5 — Environment Verification (per story, conditional)

After marking a story `done`, if the File List includes any source file (`.ts`, `.tsx`, `.js`, `.jsx`, schema files, config, migrations, tests, seed scripts):

If the target project defines a dev-environment verification skill (e.g., `/debug-vista-manager`, `/debug-dev-env`, or similar — record the name in `PORTING.md`), invoke it via the `Skill` tool. The skill should verify that the dev environment (database, backend, frontend, etc.) boots cleanly with the new code.

Skip for pure-documentation stories. If `<dev-env-skill>` fails: read whichever log file the skill writes, attempt one fix, then flag and continue.

If no dev-env skill exists on the target project, this step is N/A — note that in `<flags-file>`.

**Per-story dev-env verification is optional in autonomous mode** — to save time you may defer to end-of-epic (Step 3.0). If you defer, **track it as deferred in `<flags-file>`** so end-of-epic verification runs unconditionally.

### Step 2.6 — Stage changes (carefully selected, NOT `git add -A`)

**Do NOT run `git add -A`.** The working tree often contains unrelated work-in-progress, artifacts from prior runs, scratch files. Staging everything pollutes the user's commit surface.

Instead:

1. **Start from the story's File List** — every recorded file is in scope
2. **Add obvious story artifacts** — the story `.md`, mockup files referenced, `<flags-file>` updates
3. **Add expected side-effects** — DB migrations if schema changed, all locale files if i18n changed, regenerated lockfiles only if the story explicitly mentions them
4. **Scan `git status --porcelain` for story-adjacent files the File List missed** — new test fixture in same `__tests__/`, snapshot co-located with a modified component. Inspect: "would a reviewer expect this file in the commit for this story?" If unclear, skip and flag in `<flags-file>`
5. **Do NOT stage** anything under workspace/scratch directories (`tmp/`, `logs/`, `.playwright-mcp/`, skill workspaces, unrelated `<bmad-output>/` entries, or pre-existing untracked work)

Stage with explicit paths: `git add path1 path2 path3`. Avoid wildcards unless tightly scoped.

After staging, run `git status` and sanity-check: "Changes to be committed" should read like a clean changelog for just this story. If not, unstage strays and re-stage.

**Never `git commit`. Never `git push`.** Staging with tight scope is the whole point.

Then loop back to Step 2.1.

## Phase 3 — Wrap Up

Once every story in the target epic is `done`:

### Step 3.0 — Mandatory end-of-epic environment verification

If the target project defines `<dev-env-skill>`, run it unconditionally — even if it ran per-story. This is the single non-skippable environment gate.

If it fails: attempt one fix, then if still failing record CRITICAL in `<flags-file>` and continue. Do NOT halt.

**Bypass:** only via explicit user request before the run started, recorded as `--skip-dev-env` in `<flags-file>`.

If no `<dev-env-skill>` is configured, this step is N/A — note in `<flags-file>`.

### Step 3.1 — UX advisory subagent for UI-only feature epics (optional gate)

**Project-level short-circuit (check first):** if PORTING.md's path-placeholder table marks `<frontend-src>` as N/A (the project has no graphical frontend), **this step is N/A unconditionally**. Write `UX advisory: N/A — project has no graphical frontend per PORTING.md` to `<flags-file>` and continue to Step 3.2. The advisory subagent assumes a graphical UI surface to react to (information density, mental-model alignment, click-through workflow friction); without one, the spawn produces noise rather than signal. For projects where the UI is conversational text (Discord, CLI, etc.), the equivalent quality gate happens at Phase 3.5 manual verification — a real user walks the actual flow.

Otherwise (project has a graphical frontend AND a designated UX/persona advisory subagent configured in `PORTING.md`), spawn it for UI-only feature epics — i.e., the epic touched UI source files in any story's File List. The advisory's output gets inlined into the terminal-UAT story's `## UX Advisory Output` section AND appended to `<flags-file>` under `## UX Advisory` BEFORE the epic-close `done` flip.

If no advisory persona is configured, this step is N/A — skip and continue.

```
Invoke: Agent tool with:
- subagent_type: "general-purpose"
- model: "<review-model-id-from-phase-1>"
- description: "UX advisory for epic-{N}"
- prompt: "Act as <project-defined persona — a representative end user of the product>.
  Review the UI changes shipped in epic-{N} based on the story files in
  <bmad-output>/implementation-artifacts/{N}-*.md. Focus on: discoverability,
  information density, mental-model alignment, and end-user workflow friction.
  Produce a non-blocking advisory paragraph (under 200 words). This is not a
  blocker — it's a UX read on what shipped. Format: 'UX advisory: ...'"
```

**Gate check before flipping epic to `done`** (when configured): the terminal-UAT story's `## UX Advisory Output` section MUST contain ≥1 non-empty bullet OR an explicit "UX advisory SKIPPED — carve-out at kickoff: {reason}" line. If neither present, block the epic-done flip and re-spawn.

### Step 3.2 — End-of-epic self-grading checklist

Print a scorecard. Any unchecked → flag in `<flags-file>`:

```
Epic-{N} self-grading scorecard
☐/☑ A1 — UI scope check passed for every story
☐/☑ A2 — end-of-epic dev-env verification ran (or N/A)
☐/☑ A4 — <flags-file> exists with all [deferred:*] aggregated
☐/☑ A5 — issues-found-vs-applied tracked per story (target: ≥70% applied)
☐/☑ A7 — UX advisory invoked (UI epic) or N/A (non-UI / not configured)
☐/☑ B1 — File-List-vs-git gate passed cleanly for every story
☐/☑ B2 — Phase 3.5 manual-verification gate (always unchecked on first render; checked retroactively after user posts PASS/FAIL)
```

### Step 3.3 — Mark epic done and finalize

1. **Mark the epic `done`** in `<sprint-status>`. Leave the `epic-{N}-retrospective` key as-is (`optional`) — the user runs that **interactively, manually, in a future session**. The retrospective is NOT part of this skill.

2. **Always create `<flags-file>`** (mandatory output even if no flags raised — write a "no flags raised" file rather than skipping). Must include:
   - Per-story summary table: story-id, status, tests, review rounds, issues-found, issues-applied, applied-rate% (warn if <70%)
   - Aggregated `[deferred:*]` items pulled from each story's Completion Notes
   - UX advisory (Step 3.1) if applicable
   - Self-grading scorecard (Step 3.2)
   - Recommendations for next retrospective

3. **Produce a final report to the user**, as chat output, covering:
   - Epic number and story count completed
   - Dev model and review model used
   - Per-story: one-line summary
   - Flags from `<flags-file>`
   - Files staged (count, not full list)
   - Reminder: **"Automated tests + code review are not browser UAT. Run end-to-end verification manually before release."**
   - Reminder: **"Code complete ≠ epic complete. Manual verification recommended."**
   - **Reminder (strong): "`#yolo` mode is now OFF. The retrospective is ALWAYS interactive — even after autonomous epic completion. Invoke `/bmad:bmm:workflows:retrospective` manually when ready and engage in the dialogue with the SM agent. Do NOT pass `#yolo` to the retro under any circumstance."**
   - Reminder: **"Nothing committed — review `git status` and commit when ready."**
   - **Permission-prompt summary** (always included when a permission log is configured):
     - If `<permission-log>` was written during the run: "`{N}` permission prompts occurred — top 3 recurring shapes: <X>, <Y>, <Z>. Review `<permission-log>` and extend `<settings-file>` before the next run."
     - If no prompts: "Zero permission prompts during the run — envelope was sufficient."
     - If no permission log is configured on the target: "No permission log configured — count of mid-run prompts unknown."

### Phase 3.5 — Manual Verification Hard Gate (Shape 2)

**Why this exists:** even 30 minutes of browser verification at the end of an epic routinely finds bugs that thousands of unit tests, lint, i18n parity, code review, and dev-env verification all miss. "Automated checks pass" is not equivalent to "feature works for the user."

#### Three-layer verification model

End-of-epic verification operates on three architecturally distinct layers. The autonomous-epic-run skill is responsible for Layer 1 unconditionally; Layer 2 is gated by surface category; Layer 3 is non-blocking advisory.

- **Layer 1 — Automated checks.** Unit + integration tests + lint + i18n parity + build + dev-env verification (Step 3.0 when configured). The skill runs all of these inside the loop and at end-of-epic. PASS at Layer 1 means the artifact compiles, tests green-path, and the dev environment boots cleanly. It does NOT mean the feature works for the user.

- **Layer 2 — Real-user verification on real-domain data — MANDATORY for pipeline-output surfaces.** The user opens the app, walks the UAT checklist on real-domain data (or production-shape seeds), and posts a verdict. This layer catches what unit tests cannot see: rendering deltas, microcopy alignment, click-through workflows, real-data shape mismatches.

  **Mandatory triggers:** any surface that consumes pipeline output (data scraping, enrichment, signal extraction, projection-heavy UIs, anywhere fixture seeds may diverge from real producer output). NOT optional. NOT batchable to end-of-epic for any fixture seed that has not yet had a real-user verification on real-domain data since the fixture was authored — irrespective of which agent authored the fixture and which agent wrote the test. The gate triggers on **fixture-without-real-data-verification** as the load-bearing condition, not on agent identity.

  **Carve-out — when Layer 2 may legitimately be deferred or skipped:** ONLY for backend-only epics (no UI source files in any story File List), AND only with an explicit user call recorded in `<flags-file>`. The carve-out exists for genuinely non-user-visible work (e.g., schema migrations with no UI surface, observability hardening). It does NOT apply to pipeline-output surfaces — those remain MANDATORY regardless of whether the story added new UI files (a backend-only fix to a projection consumed by an existing UI surface still surfaces user-visible behavior changes).

- **Layer 3 — UX advisory (non-blocking).** Spawned at Step 3.1 when configured. Produces a short advisory paragraph from a representative end-user perspective. Non-blocking by design; findings route to next quality-epic carry-forward, not to the verdict.

**When this runs:** after Step 3.3 would normally mark the epic `done`, and before the final report. **The epic stays `in-progress` until this gate resolves** — do not flip to `done` until the user posts a verdict.

**What the gate does:**

1. Locate the epic's final UAT story (typical naming convention: `{N}-{last}-uat-checklist-generation-and-execution`). **Fallback when no UAT story exists** (pure hardening / skill-only epics): synthesize a minimal checklist from each story's top-level ACs — one line per story's primary user-facing AC, prefixed with the story ID. Emit with a prefix line "⚠ No UAT story found for epic-{N} — using synthesized checklist (degraded mode)."

2. Extract AC-level checklist from the UAT story — each `**Given** ... **When** ... **Then** ...` becomes one checkpoint.

3. Emit the prompt:

```
🖐️ MANUAL VERIFICATION REQUIRED — epic-{N}

Open the app at <project local URL — e.g., http://localhost:3000> and walk these {N} checkpoints from Story {X-N} UAT:

  1. [AC-1] ...
  2. [AC-2] ...

Respond with one of:
  PASS                  — everything works, proceed to close epic
  PASS WITH FINDINGS    — mostly works; I'll list findings below
  FAIL                  — at least one checkpoint is broken, epic stays in-progress
```

4. **Wait for the user's response.** This is the only explicit mid-invocation prompt the skill issues at end-of-epic.
5. Record the verdict + findings under `## Manual Verification` in `<flags-file>`.
6. Behavior by verdict:
   - **PASS** → flip `epic-{N}: in-progress` → `done`. Emit final report.
   - **PASS WITH FINDINGS** → epic closes; note findings in final report; recommend they route to next quality-epic carry-forward.
   - **FAIL** → leave epic `in-progress`. Emit short report listing failing checkpoints.

**Extraction algorithm:**

1. Read the UAT story file. Locate `## Acceptance Criteria`; extract until next `## ` heading.
2. Split on `**Given**` (or bare `Given` at line start). Each chunk is a potential checkpoint.
3. If a chunk has `**Then**` (or `Then`), the whole chunk collapses into ONE checkpoint: `[AC-{n}] <summary derived from Then>`.
4. If the AC section is a flat bullet list (no Gherkin), use each bullet verbatim.
5. Hard cap at 25 checkpoints; if more, append "N additional checkpoints not shown — see `{uat-story-file}`".

See [dry-run-scenarios.md](dry-run-scenarios.md) Scenario 4 for a worked mixed-format example.

**Scope:** the ONLY mid-invocation prompt the skill issues after the main loop starts. The "No human prompts mid-loop" principle holds during the loop; Phase 3.5 is end-of-epic, architecturally distinct.

**Future evolution:** drive automated browser testing (Playwright/Cypress MCP) against the same UAT checklist, produce PASS/FAIL auto-report + screenshots, then still fire the real-user spot-check on 1–2 high-risk items.

## Core Principles

**Forecast before, push through during, flag at end.** Phase 0.4's Blocker Scan catches predictable blockers before the loop. The user resolves those upfront. Then the loop runs clean: it does NOT halt on test failures, environment failures, non-converging reviews, or newly-discovered missing deps — those are flagged in `<flags-file>` and the loop continues. Mid-loop halts only on: (a) no epic to run, (b) sprint-status integrity issue (`create-story` picks wrong epic), (c) a blocker the scan couldn't have anticipated.

**Sub-workflows returning is not a stopping condition.** When `create-story`, `dev-story`, or `code-review` returns, the orchestrator's next action is `Read sprint-status.yaml` and continue — not write a status summary, not ask the user to confirm, not "return control to the orchestrator" framing (the orchestrator IS this skill). See the Loop Continuity Contract at the top of Phase 2.

**Different model for review is non-negotiable.** If you can't get a different model (e.g., the `Agent` tool rejects the model parameter), halt — don't fall back to self-review.

**Stage, never commit.** `git add` is fine. `git commit`, `git push`, `git commit --amend` are forbidden in this skill.

**Re-read sprint-status every iteration.** Workflows mutate the file. Caching causes skipped or duplicated work.

**Review judgment is a real responsibility.** Fix what matters, document what you deferred, never skip security or correctness.

**The retrospective is always interactive.** Even after autonomous epic completion. The retro is the agent + user discussing what happened, what to keep, what to change. `#yolo` mode is scoped to the four loop sub-workflows ONLY — it does NOT apply to the retro.

## What This Skill Does NOT Do

- **No retrospective.** Stops before it. The user runs it manually, **interactively**, in a future session.
- **No commits.** Only `git add`.
- **No epic planning.** If there's no epic to run, it exits — does not create one.
- **No model auto-fallback.** If the different-model requirement can't be met, it halts.
- **No human prompts mid-loop.** Only prompts: (a) Phase 0.4 if Blocker Scan finds blockers, (b) Phase 3.5 end-of-epic manual verification. Both are architecturally outside the per-story loop.
- **No mid-loop user-facing text — at all.** The orchestrator does NOT emit per-story "what shipped" tables, per-AC breakdowns, files-changed listings, "returning control to the orchestrator" framing, OR single-line progress markers between iterations. Mid-loop output is restricted to (a) tool calls and (b) the explicit HALT messages defined in the Error Handling Summary table. The full report lands at Phase 3.3. See the Loop Continuity Contract at the top of Phase 2.
- **No `#yolo` propagation past the main loop.** Phase 1.5 activates `#yolo` for sub-workflows used IN the loop; Phase 3.3 explicitly deactivates it before handing back to the user.

## Permission Envelope

Required permissions in `<settings-file>` — full envelope reference at [references/permission-envelope.md](references/permission-envelope.md). The skill expects coverage for at minimum:

- Git operations: `git status*`, `git add *`, `git log *`, `git diff *`, `git stash *`, `git ls-files *`, `git init`, `git config*`
- Test runners and build: whatever your project uses. Stack examples:
  - **JS/TS:** `pnpm test`, `npm test`, `pnpm lint`, `pnpm build`
  - **Python:** `python -m pytest *`, `pytest *`, `ruff *`, `mypy *`, `pyright *`
  - **Rust:** `cargo test`, `cargo check`, `cargo clippy`
  - **Go:** `go test ./...`, `go build`, `go vet`
- Monorepo filter-exec compound shapes if applicable (e.g., `pnpm --filter * exec npx jest *`). For Python projects with `pip + venv` (no workspace tool), this is N/A.
- Container tooling if your project is containerized: `docker compose *`, `docker ps`, `docker logs *`, `docker exec *`, `curl localhost:*`
- Any `<dev-env-skill>` prerequisites (see PORTING.md)

If any command shape prompts during a run, add it after the run via the project's permission-management workflow (e.g., `/update-config`, `/fewer-permission-prompts`, or by manually editing `<settings-file>`).

## Error Handling Summary

| Condition                                                  | Action                                                                                |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| No epic in progress, no backlog epic                       | **HALT** — nothing to do                                                              |
| Upstream orphan story exists in earlier epic (pre-flight)  | **HALT** — would derail the run                                                       |
| Cannot spawn subagent with different model for code review | **HALT** — skill's core contract violated                                             |
| `create-story` picks story from wrong epic mid-run         | **HALT + CRITICAL flag** — sprint state corruption risk                               |
| `dev-story` tests fail                                     | Attempt fix; if 2 retries fail → flag and move on                                     |
| `dev-story` implementation genuinely stuck                 | Flag, mark `review` with `[blocked]` note, move on                                    |
| File-List-vs-git gate finds untracked files (Step 2.4.6)   | **HALT** — wait for user `git add` or File List correction                            |
| Phase 3.5 manual-verification gate fires                   | **HALT** — epic stays `in-progress` until user posts PASS / PASS WITH FINDINGS / FAIL |
| Code-review loop doesn't converge in 2 rounds              | Flag, mark `done`, move on                                                            |
| Dev-env verification fails                                 | One fix attempt, then flag, move on                                                   |
| UAT-style story with FAIL gate                             | Flag CRITICAL, mark `done`, move on                                                   |
| External dep missing (mockup, API key, seed data)          | Flag, mark `done` with `[external-dep]` note, move on                                 |

All flags land in `<flags-file>` — one bullet per flag, with story ID, severity (CRITICAL / WARNING / INFO), and reason.

## Resuming After Interruption

This skill is idempotent and resumable. All state lives in `<sprint-status>` plus the story files. If the run is interrupted, just invoke `/autonomous-epic-run` again:

- Phase 0 picks the same target epic (now `in-progress`)
- Phase 2.1 re-reads status, skips already-`done` stories, picks up the first non-done one
- If a story was mid-way through dev, `dev-story` continues where it left off
- If a story was in `review` with unchecked reviewer items, Step 2.4's fix-and-verify branch picks them up

No extra flags or checkpoints needed.

## Walk-Evidence Convention

When the orchestrator (or a story's Phase 3.5 step) executes an automated browser-testing walk (Playwright MCP, Cypress MCP, etc.) to substitute for or supplement a real-user Layer 2 verification, all captured artifacts (PNG screenshots, CSV downloads, JSON dumps, console logs) MUST land in a story-scoped evidence sub-folder, NOT at repo root or in tool-default scratch dirs:

- **Target location:** `<bmad-output>/implementation-artifacts/<story-id>-uat-evidence/`
  - Example: `<bmad-output>/implementation-artifacts/50-4-uat-evidence/`
- **Inline requirement:** the story's `## Phase 3.5 evidence` section (or `## Completion Notes` if no dedicated subsection) MUST inline ≥1 most-diagnostic screenshot per AC verdict using markdown image syntax: `![alt text](<story-id>-uat-evidence/<file>.png)`. Cross-link CSV exports / log dumps via `[file label](path)` link syntax.
- **Replay-only artifacts** (not inlined but kept for audit trail) stay in the same sub-folder; their presence is documented in the story's `### File List` WALK EVIDENCE sub-section.
- **Selective staging:** the sub-folder + artifacts are explicit `git add` entries in the story's commit; never `git add -A` to scoop them up.

**Why this convention:** audit-trail recoverability. Repo-root artifacts are at risk of `git clean` / accidental deletion / discoverability decay; story-scoped sub-folders co-locate evidence with the AC verdicts that consumed them, surviving across initiative archives.

## Disposition-Story Pattern

The orchestrator occasionally encounters stories whose **planned scope has been overtaken by events** between create-story and dev-story phases — typically because a prior story (or a same-epic predecessor) shipped the same fix, OR because the story's original framing dissolves under investigation (the actual scope is bigger / smaller / different shape than the spec assumed). The Disposition-Story Pattern is the orchestrator's stable default for these cases. **Do not re-discover already-shipped work. Do not silently re-frame the story without an honest disposition trail.**

### When the pattern applies

- **Supersession:** investigation at dev-pass kickoff shows the architectural intent of the story is already realized by a prior commit (a same-epic predecessor, a followup story closed pre-epic, or an emergency fix during retro). The right action is to close the story as `done` with a "superseded-by-<commit>" disposition note, NOT to re-implement.
- **Ratification (docs-only):** the story's scope is a ratification artifact — a sign-off cell flip, an APPROVED-PENDING-XYZ template fill, a docs changelog entry. Zero source-code changes; the deliverable is text-level alignment.
- **Verification-only (terminal UAT):** the story is a Phase 3.5 walk + sign-off checkpoint with no expected source-code changes. The "implementation" is the walk evidence + verdict capture.

### Discipline rules for the orchestrator

1. **Detect at dev-pass kickoff investigation step.** If investigation surfaces "this fix is already shipped" OR "this story's scope is text/walk only with no source-code expected," surface as an Open Question honest-rescope GATE STORY in the story file. Do NOT proceed to AC checking as if the story were a normal feature ship.
2. **Open Questions document the path choice.** Enumerate Path (a) re-discover-and-reimplement vs Path (c) close-superseded-by-X vs Path (e) verification-only automated walk vs Path (custom). Default = the path that minimizes scope spill-over while preserving honest disposition.
3. **Selective staging stays explicit.** Even for docs-only stories, `git add <path>` allow-lists; never `git add -A` to scoop up unrelated changes. Typical staged file count: 2-6 (story file + pre-review + sprint-status + 1-3 docs touches).
4. **Dev-env verification SKIPPED per Step 9.5 docs-only carve-out** is the right call when zero source-code changes. Sanity baseline from the predecessor story stays the contract; new tests are not expected.
5. **Pre-review self-audit still required.** Even a docs-only / supersession story gets a `<story-id>.pre-review.md` artifact with the §5 Posture Audit — most sections will be N/A but the pre-review forcing function holds.
6. **Cross-story finding ratchet.** If supersession discovers the load-bearing fix lives in a non-existent or insufficient successor, file the new followup row in sprint-status as part of the disposition — don't lose the architectural debt.

### Why this matters for autonomous loops

Without this pattern, autonomous-epic-run loops will either: (a) re-implement already-shipped work, producing scope-creep commits with confusing diffs; or (b) silently mark stories `done` without explanation, breaking auditability. The pattern preserves loop velocity AND audit-trail integrity by giving the orchestrator a named, honest, replicable default for "overtaken by events" cases.