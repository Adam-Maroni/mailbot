# autonomous-epic-run — Dry-Run Scenarios

Walkable scenarios for manually auditing the skill's gating behavior without a real autonomous run. Each scenario describes a setup, the expected skill behavior, and how to verify.

**Purpose:** these scenarios serve as documentation when evaluating whether a skill change preserves the gates, and as a sanity check before invoking the skill on a new project for the first time.

---

## Scenario 1 — File-List-vs-git gate HALTs on untracked file

**Setup:**

1. Create a synthetic new file somewhere the skill would plausibly touch during a story: `<frontend-src>/components/__synthetic_untracked__.tsx`
2. Do NOT run `git add` on it — leave it untracked.
3. Open a story file at `<bmad-output>/implementation-artifacts/99-9-synthetic-story.md` (or any story that is currently `in-progress`) and ensure its File List section includes the synthetic path.

**Expected skill behavior at Step 2.4.6:**

- Skill parses the File List and finds `<frontend-src>/components/__synthetic_untracked__.tsx`
- Runs `git ls-files --error-unmatch <frontend-src>/components/__synthetic_untracked__.tsx`
- Command exits non-zero with message like `error: pathspec '...' did not match any file(s) known to git`
- Skill HALTs the loop with the message template:

  ```
  🛑 File-List-vs-git gate — story 99-9 has 1 untracked files:
    - <frontend-src>/components/__synthetic_untracked__.tsx

  Story NOT marked done. Resolve one of:
    (a) `git add` the listed files, then retry
    (b) Remove them from the story's File List if they shouldn't be tracked
    (c) Cancel the autonomous run
  ```

- Sprint-status is NOT touched; story stays in `review` (or whatever its current status is)
- No staging happens in Step 2.6

**Verification:**

- After user runs `git add <frontend-src>/components/__synthetic_untracked__.tsx` and re-invokes the skill, the re-check passes and the story flows through.
- Cleanup: `rm <frontend-src>/components/__synthetic_untracked__.tsx` and `git rm --cached` if already staged.

---

## Scenario 2 — File-List-vs-git gate passes on clean File List

**Setup:**

1. A story whose File List lists only files that are either tracked (green in `git status`) OR staged for commit (in the index).
2. Story is in `review` status, all review items applied or deferred.

**Expected skill behavior:**

- Skill parses File List, runs `git ls-files --error-unmatch <path>` for each path
- Every path exits zero (tracked + known to git)
- Gate passes silently — no halt, no log output beyond a standard "Step 2.4.6 — passed" breadcrumb
- Skill proceeds to Step 2.5 (Environment Verification) and beyond

**Verification:**

- Run `git ls-files <path>` manually for each File List entry; all should print the path back (exit 0)
- Skill should complete the story without surfacing the gate

---

## Scenario 3 — Canonical autonomous-run command sequence (permission envelope sanity check)

**Purpose:** a manual checklist the user can walk before a real autonomous run to predict whether the tightened permission envelope will cause spurious re-prompts. Each command below should execute without a permission prompt under the current `<settings-file>`.

**Table to fill in for your project.** Replace the example commands with whatever your test runner / build tool / monorepo tool actually uses. The right-hand "Allowed by" column should be filled with the matching glob rule in `<settings-file>` — if any cell ends up blank, that's an envelope gap to extend before the autonomous run starts.

| #   | Command                                                                                | Purpose in the skill   | Allowed by settings.json rule                              |
| --- | -------------------------------------------------------------------------------------- | ---------------------- | ---------------------------------------------------------- |
| 1   | `git status`                                                                           | Step 2.1, 2.6          | `git status*`                                              |
| 2   | `git diff --cached`                                                                    | Step 2.6               | `git diff *`                                               |
| 3   | `git add <path-to-modified-file>`                                                      | Step 2.6               | `git add *`                                                |
| 4   | `git log --oneline -5`                                                                 | Phase 1 story intel    | `git log *`                                                |
| 5   | `git stash`                                                                            | Rare mid-story cleanup | `git stash *`                                              |
| 6   | `git ls-files --error-unmatch <path>`                                                  | Step 2.4.6             | `git ls-files *`                                           |
| 7   | `<your-test-runner>`                                                                   | Step 2.3               | _(fill in)_                                                |
| 8   | `<your-lint-command>`                                                                  | Step 2.3               | _(fill in)_                                                |
| 9   | `<your-build-command>`                                                                 | Step 2.3, 2.5          | _(fill in)_                                                |
| 10  | `<workspace-filtered-test-runner>` if monorepo                                         | Step 2.3               | _(fill in)_                                                |
| 11  | `<workspace-filtered-orm-migration-cli>` if applicable                                 | schema stories         | _(fill in — likely the compound-exec gotcha shape)_        |
| 12  | `<workspace-filtered-unit-test-cli>` if applicable                                     | Step 2.3               | _(fill in)_                                                |
| 13  | `<your-dev-env-skill prerequisites — docker/curl/etc.>`                                | Phase 3.0              | _(fill in)_                                                |

**Walkthrough instructions:**

Before invoking the skill for the first time on a new project, run these commands one-by-one from the shell Claude is observing. None should prompt. If any does, that's an envelope gap — add the shape to `<settings-file>` or document the acceptance in `references/permission-envelope.md`.

---

## Scenario 4 — Phase 3.5 Gherkin AC extraction (mixed-format example)

**Purpose:** walk the concrete extraction algorithm (SKILL.md Phase 3.5 "Extraction algorithm") against a realistic UAT story structure. Run this if the algorithm produces unexpected checkpoints for a future epic.

**Input (excerpt from a hypothetical UAT story):**

```markdown
## Acceptance Criteria

**Given** the user opens the entity list page
**When** they click "Add new entity"
**Then** the discovery dialog opens within one animation frame
**And** the search input has immediate keyboard focus

**Given** the user types a query string
**When** results return
**Then** dedup badges render for each result
**And** no 404s appear in the network tab

**Given** all UAT preconditions pass
**When** the gate decision is made
**Then** the checklist covers:

- Typing any entity name → dedup badges render without 404s
- Opening the dialog → focus lands on input
- Running `<your-cli-tool> report:search-gaps` → markdown written
```

**Expected extraction (per algorithm):**

1. Split on `**Given**` — three chunks found.
2. Chunk 1: `**Given** … **When** … **Then** opens within one animation frame **And** input has immediate keyboard focus` → one checkpoint: `[AC-1] Discovery dialog opens within one animation frame, input focused`
3. Chunk 2: `**Given** … **When** … **Then** dedup badges render … **And** no 404s` → one checkpoint: `[AC-2] Dedup badges render for each result, no 404s`
4. Chunk 3: `**Given** … **When** … **Then** the checklist covers: (bullet list)` → the flat bullet list rule kicks in; extract 3 additional checkpoints: `[AC-3a] Typing any entity → dedup badges render without 404s`, `[AC-3b] Opening the dialog → focus lands on input`, `[AC-3c] Running <your-cli-tool> report:search-gaps → markdown written`

**Total: 5 checkpoints from this UAT story.** Under the 25-cap, so all rendered.

**Edge cases covered:**

- Bold-markdown `**Given**` vs plain `Given` — algorithm matches both
- `**And**` subsequent lines collapse into the parent checkpoint
- Flat bullet list mixed with Gherkin — both extracted
- Empty lines between Gherkin blocks — ignored during split

**If the algorithm produces different output:** check the 25-cap, check whether `**Given**` is at line start (required), check whether the ACs live under `## Acceptance Criteria` exactly (required).

---

## Notes

- These scenarios are not automated — they're human-walkable mocks of skill behavior. The skill runs within Claude Code's tool invocation loop, which is not trivially mockable from test code.
- If a future skill change alters gate semantics (e.g. tightening the File-List parser), update this file to match.
- Once you've exercised these scenarios on a new project and confirmed the gates fire as expected, you can safely invoke the skill on a real epic.