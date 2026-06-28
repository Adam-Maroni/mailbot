# Epic 9 — Run Flags

**Epic:** Manual Model Control & Benchmark Harness (created 2026-06-07 via party-mode roundtable scope cleave)
**Run cadence:** Tranche-scoped (Adam-decision 2026-06-13)
**Current status:** Epic 9 `in-progress` — only Story 9-1 done; all other stories still `backlog`

---

## Run history

### Run 1 — 2026-06-13 — scoped tranche (option a), Story 9-1 only

**Trigger:** `/autonomous-epic-run epic 7` → Phase 0 surfaced Epic 7-blocks-on-Epic-9 sequencing per sprint-status.yaml comment lines 197-205 → Adam picked option (a) "run Epic 9 instead" → Phase 0.4 Blocker Scan surfaced 3 hard blockers in the benchmark sub-tranche (9-5 corpus Adam-labor, 9-6 cohort_key decision, 9-8 fixture recording authz) → Adam picked option (b) "ship 9-1+9-2+9-3+9-4+9-10 /model surface tranche" → after Story 9-1 done-gates passed, scope re-shrunk to option (a) "ship 9-1 standalone" per budget honesty halt.

**Final scope shipped:** Story 9-1 only.

**Models:**

- Dev: `claude-opus-4-7` (1M context, this session inline execution)
- Reviewer (Story 9-1): `claude-sonnet-4-6` per dev-vs-review different-model invariant

**`#yolo` mode:** activated for the per-story sub-workflows during the main loop; deactivated at Phase 3 close per Phase 1.5 contract. Does NOT propagate to the retrospective (interactive-only per N.5-epic policy).

---

## Per-story summary

| Story | Status | Tests | Review rounds | Issues found | Issues applied | Applied rate | CR cadence |
|---|---|---|---|---|---|---|---|
| 9-1 | done | +32 net (vs +6 plan) | 1 | 7 | 5 | 71% | MANDATORY-CR (sonnet-4-6) |
| 9-2 | backlog | — | — | — | — | — | MANDATORY-CR (scoped out of Run 1 — Adam-decided budget halt) |
| 9-3 | backlog | — | — | — | — | — | MANDATORY-CR |
| 9-4 | backlog | — | — | — | — | — | MANDATORY-CR |
| 9-5 | backlog | — | — | — | — | — | — (3-5h Adam-labor hand-labeling blocker) |
| 9-6 | backlog | — | — | — | — | — | MANDATORY-CR (blocked on cohort_key Adam-decision) |
| 9-7 | backlog | — | — | — | — | — | MANDATORY-CR |
| 9-8 | backlog | — | — | — | — | — | gate-coverage-eligible (~$0.50 real-API recording blocker) |
| 9-9 | backlog | — | — | — | — | — | medium-CR |
| 9-10 | backlog | — | — | — | — | — | gate-coverage-eligible |
| 9-11 | backlog | — | — | — | — | — | reduced-scope MANDATORY-CR (blocked on OpenRouter creds + ~$1-3 spend authz) |

**Applied-rate target:** ≥70% per Epic 3 retro precedent. **Run 1 actual: 71% on the one MANDATORY-CR story dispatched.** Held the cadence v2 100% applied-rate streak for the actionable bucket (5/5 PATCH-tagged; 2 DEFER with rationale).

---

## `[deferred:*]` items aggregated

### From Story 9-1

- **[deferred:CR-F4 spurious-reload-event]** — content-identical rewrites of the override file produce a `policy.reloaded` audit event despite no semantic change. Real-world impact negligible (operationally rare). Acceptable observability noise.
- **[deferred:CR-F7 bind-mount-RW-permissions]** — UID alignment between host-side `touch`ed override file and the mailbot container user is unverified. Deferred to Story 9-4 (owns the write path via `os.replace()`).

---

## Findings

### F32 — Production `sensitivity_patterns.yaml` bind-mount latent gap (NEW, MEDIUM)

**Discovered during:** Story 9-1 AC-7 implementation (docker-compose bind-mount fix).
**Surface:** `router/sensitivity_patterns.yaml` is loaded by `mailbot_api/main.py` lifespan from `/app/router/sensitivity_patterns.yaml` (Story 3-3 AC-3). The Dockerfile does NOT `COPY router/` into the image, and the base `docker-compose.yml` did NOT bind-mount it either — only `docker-compose.override.yml` (dev mode) provided the file. Same latent class as the `policy.yaml` gap closed in Story 9-1.
**Severity:** MEDIUM — blocks first production CP-1 deploy if not addressed. Not a runtime correctness bug while dev-mode override is in effect, but the production stack would fail at startup with `sensitivity_patterns.yaml: file not found`.
**Closure shape:** add `./router/sensitivity_patterns.yaml:/app/router/sensitivity_patterns.yaml:ro` to `docker-compose.yml` `mailbot-api.volumes`. Small change. Filed as a follow-up — out of Story 9-1 scope per CLAUDE.md "Don't add features beyond what the task requires."
**Suggested home:** Could ride into Story 9-2's docker-compose touch OR ship as a one-off pre-Epic-9-done patch. Adam-decision.

### F35 — Watchfiles thrash on runtime file DELETION (NEW, HIGH — discovered during Phase 3.5)

**RESOLVED — Story 9-1.5 — `<commit-hash-pending-commit>`** — closed via detect-and-stop-watching branch in `mailbot_api/router/policy.py::policy_reload_loop` per run-flags Option 1. Suppression flag `_override_absent_after_applied` is armed on the first absent-after-applied transition; subsequent watchfiles spurious fires (both `override_status=="absent"` thrash AND platform-specific `override_status=="applied"` re-creation pickup on Windows) are silently coalesced until either the operator restarts mailbot-api (process restart implicitly clears the flag) OR the baseline `policy.yaml` is edited (AC-3 resume contract). Three new integration tests in `tests/integration/test_policy_overrides_delete_at_runtime.py` exercise the delete path that Story 9-1's `tmp_path` fixtures missed. AC-4 F33 contract preservation verified on Windows where ReadDirectoryChangesW DOES observe the recreated file but the suppression flag holds the loop in "ignore override side" mode uniformly across platforms.

**Discovered during:** Story 9-1 Phase 3.5 manual verification (orchestrator-driven live walk).
**Surface:** When `router/policy.user-overrides.yaml` is DELETED at runtime while mailbot-api is running, `watchfiles.awatch` enters a thrash state. The semantic transition fires correctly ONCE (`policy.user-overrides.swap` event with `version_before="<baseline>+overrides:<hash>"` → `version_after="<baseline>"` per the CR-F1 patch), but then watchfiles continues firing change events at ~310ms cadence because the watch descriptor was bound to a now-nonexistent path. Each fire triggers `load_policy_with_status` → status="absent" → falls through to the baseline-only reload branch → emits `policy.reloaded`. **Log spam continues indefinitely until mailbot-api is restarted.**
**Live evidence:** Phase 3.5 Checkpoint 6 (file deletion test). After `rm router/policy.user-overrides.yaml`, the log shows ~60+ `policy.reloaded` events in ~20 seconds (every ~310ms) all emitting the identical baseline version `policy-v0-2026-06-01`. No semantic state change after the first event.
**Severity:** HIGH — production-impacting log spam if Adam ever `rm`'s the override file. Audit log becomes useless during the thrash window. Could mask real `policy.reloaded` events from baseline policy.yaml edits.
**Closure shape (deferred to follow-up story):** the integration tests covered the create-then-mutate-then-malform path but NOT the delete path because the integration test fixture used `tmp_path` which never deletes files mid-test. Three options for Story 9-2 or a dedicated 9-1.5 hotfix:
  1. **Detect-then-stop-watching** — after seeing the first `status="absent"` event when previously we had overrides, remove the override path from the watch set + emit a one-shot warning that hot-reload-from-create requires restart (matches F33's documented limitation).
  2. **Coalesce reloads** — track the last-emitted version + only emit `policy.reloaded` when version actually changes (deduplicates the spam at log layer; still wastes CPU on the load_policy_with_status call per fire).
  3. **Migrate to directory-watch** — watch `router/` directory instead of two specific files; detect creation + deletion + modification uniformly. Bigger refactor.
  Option 1 is the most surgical. Option 3 is the architecturally correct long-term fix.
**Workaround for now:** **don't `rm` the override file at runtime** — operationally, `/model persistent` (Story 9-4) doesn't delete the file; it atomically rewrites it. The delete path is only triggered by direct operator `rm`. Documented limitation; not exercised by Story 9-4's intended flow.

### F33 — Watchfiles cannot watch non-existent paths (UPSTREAM CONTRACT, INFO)

**Discovered during:** Story 9-1 integration testing.
**Surface:** `watchfiles.awatch(*paths, ...)` raises `FileNotFoundError` if ANY of the watched paths does not exist at watcher-start time. Documented online behavior, not a bug — but the Story 9-1 Dev Notes incorrectly assumed watchfiles 0.21+ gracefully handled non-existent paths.
**Impact:** When `router/policy.user-overrides.yaml` is absent at lifespan start, `policy_reload_loop` watches only the baseline. If Adam creates the override file at runtime (e.g., via first `/model persistent` call in Story 9-4), the hot-reload does NOT pick it up — mailbot-api must restart to extend the watch set.
**Closure:** documented in `docs/policy-overrides.md` "Hot-reload contract limitation — file-must-exist-at-startup" section. Story 9-4 owns the create-flow restart-requirement surfacing. Bootstrap recommendation in design doc: `touch router/policy.user-overrides.yaml` in `setup_vps.sh` (or equivalent) so the file always exists from day one.

### F34 — AC-2 contract restoration caught at MANDATORY-CR (CRITICAL but caught pre-merge)

**Discovered during:** Story 9-1 MANDATORY-CR pass (F1 finding from sonnet-4-6 reviewer).
**Surface:** Initial Story 9-1 dev pass swapped to baseline-only snapshot when override file became malformed at runtime. AC-2 explicitly required "the running policy is NOT swapped" — the prior merged snapshot should survive.
**Closure (CR-F1 patch):** new `load_policy_with_status()` returns `(PolicyTable, OverrideLoadStatus)` with status discriminated as `"applied" | "absent" | "empty" | "parse_failed"`. `policy_reload_loop` checks `status == "parse_failed"` and refuses the swap. Integration test rewritten to assert the prior merged snapshot survives malformed-override mutation.
**Why it matters going forward:** validates the MANDATORY-CR cadence v2 mechanism — a CRITICAL contract violation in load-bearing single-point-of-truth code was caught by adversarial cross-model review BEFORE the story flipped done. Adds to the cadence-v2 streak (Epic 3-4-5-6-6.5 + this story = 5+ consecutive epics).

---

## Carry-forward to retrospective

When Epic 9 eventually retrospectives:

1. **Cohort_key Adam-decision** — sprint-status comment 228-231 + epic spec 3072 say "15-minute Adam-decision gates Story 9-6 migration." Still pending. Adam to confirm: `(prompt_v, scorer_model, anchors_v, router_policy_v)` — or amend.
2. **Story 9-5 corpus Adam-labor** — 3-5h hand-labeling effort (100 emails + 20 reference slice + 20 anchors + 5-10 adversarial items per Round 5 maturity-bar). Cannot be autonomously generated.
3. **Story 9-8 cost-mock fixture recording** — ~$0.50 real-API spend authorization to record Anthropic responses for the canary E2E test. Adam-spend gate.
4. **Story 9-11 secondary-evaluator credentials** — OPENROUTER_API_KEY OR Sonnet API access for the Krippendorff α cross-evaluator audit. ~$1-3 real spend.
5. **`policy.yaml` v0→v1 bump (done-flip clause 11)** — requires either one benchmark-driven routing change OR Adam-signed retro entry stating "policy.yaml reviewed against benchmark output, no changes warranted, here's why." Load-bearing.
6. **Audit-row vocabulary shape change (Story 9-2 surface)** — the spec moves from flat strings (`"policy"`) to parameterized strings (`"policy:<task>:default"`). Discuss backward-compat for existing `router_calls` rows + the Story 9-9 report-generator query layer.
7. **Bin-mount UID alignment** (CR-F7 deferred) — Story 9-4 owns the write path; production deploy needs UID-aligned `touch` of the override file.

---

## Self-grading scorecard

| Check | Result |
|---|---|
| A1 — UI scope check passed for every story | N/A (no graphical frontend per PORTING.md `<frontend-src>` carve-out) |
| A2 — end-of-epic dev-env verification ran | N/A (no `<dev-env-skill>` configured per PORTING.md) |
| A4 — `<flags-file>` exists with all [deferred:*] aggregated | ☑ (this file) |
| A5 — issues-found-vs-applied tracked per story (target ≥70%) | ☑ (Story 9-1 = 71%) |
| A7 — UX advisory invoked (UI epic) or N/A | N/A unconditionally per PORTING.md |
| B1 — File-List-vs-git gate passed cleanly for every story | ☑ (Story 9-1 passed Step 2.4.6 — all tracked / all new-files-exist) |
| B2 — Phase 3.5 manual-verification gate | ☑ (orchestrator-driven live walk completed; PASS WITH FINDINGS — see verdict below) |

---

## Phase 3.5 manual-verification verdict — Story 9-1 surface

**Verdict:** PASS WITH FINDINGS

**Live walk against running `mailbot-api` container (production-shape docker-compose):**

- ✅ **Checkpoint 1 — Baseline bind-mount works in production-shape compose.** Container started cleanly; `event="policy.startup.loaded"` with `policy_path=/app/router/policy.yaml`, `overrides_path=/app/router/policy.user-overrides.yaml`, `overrides_present=false`, version=`policy-v0-2026-06-01` (no suffix). Bind-mount fix in AC-7 confirmed live.
- ✅ **Checkpoint 2 — Empty companion file produces no-suffix version.** After `touch router/policy.user-overrides.yaml` + restart: `overrides_present=true` but version still `policy-v0-2026-06-01` (no `+overrides:` suffix). CR-F3 patch confirmed live (zero-byte = empty = no suffix).
- ✅ **Checkpoint 3 — Single-field override applies + carries version suffix.** After writing `tasks.draft_reply.model: claude-opus-4-7`: startup logged version=`policy-v0-2026-06-01+overrides:0fbc3c39`. SHA-256 truncation confirmed live.
- ✅ **Checkpoint 4 — Hot-reload swap on valid edit.** Mutated override to `claude-haiku-4-5-20251001` without restart: `event="policy.user-overrides.swap"` fired ~10s later with `version_before="...0fbc3c39"` → `version_after="...599d656f"`. Different SHA = different content. Real watchfiles + real Pydantic + real on-disk YAML.
- ✅ **Checkpoint 5 — Malformed override at runtime does NOT swap prior merged snapshot.** Mutated to `::: not yaml :::`: `event="policy.user-overrides.parse_failed"` fired at ERROR; **no subsequent `policy.user-overrides.swap` event**. The prior merged snapshot (`+overrides:599d656f`) survived. CR-F1 patch (AC-2 contract restoration) confirmed live. Subsequent recovery (restoring valid YAML) correctly fell into the "no semantic change" branch and emitted `policy.reloaded` instead of a redundant swap.
- ⚠ **Checkpoint 6 — Create-from-absent flow requires restart.** Not executed live (would require 3 restarts to walk fully); F33 documented limitation; integration test `test_hot_reload_picks_up_overrides_mutation` validates the "watcher must see file at start" contract via the `tmp_path` fixture.

**NEW FINDING discovered during walk:** F35 HIGH — watchfiles thrash on runtime file DELETION. When the override file is `rm`'d at runtime, the semantic transition fires correctly ONCE (`policy.user-overrides.swap` with `version_after` losing the suffix per CR-F1), but watchfiles then continues firing change events at ~310ms cadence indefinitely against the nonexistent path, flooding the audit log with `policy.reloaded` events. Stopped only by restarting mailbot-api. **Filed above as F35.** Workaround: don't `rm` the override file at runtime — operationally, `/model persistent` (Story 9-4) rewrites the file atomically; it never deletes. The delete path is only triggered by direct operator `rm`. Closure deferred to Story 9-2 or 9-1.5 hotfix.

**Net:** the load-bearing contract (companion-file merge + version-suffix + hot-reload + no-swap-on-parse-fail) works correctly under live conditions. The F35 edge case is an upstream-watchfiles-behavior corner that integration tests didn't catch because `tmp_path` fixtures don't exercise mid-test file deletion. Documented, work-aroundable, scoped to a follow-up.

---

## Permission-prompt summary

No `<permission-log>` hook is installed on this project (PORTING.md confirms). Mid-loop permission-prompt count is therefore unknown by automated count. From qualitative observation during Run 1: zero permission prompts encountered during the entire Story 9-1 sequence (all Bash commands stayed inside `.claude/settings.json` envelope — pytest, ruff, mypy, git ls-files, git add, git status, python via venv path, rtk-prefixed commands per global RTK Golden Rule).

**Envelope health: clean for the surfaces touched in this run.**

---

## Run 3 — 2026-06-27 — benchmark tranche kickoff (`/autonomous-epic-run epic 9`)

**Trigger:** Adam invoked `/autonomous-epic-run epic 9` 2026-06-27. Phase 0.4 surfaced 4 of 5 remaining stories blocked on A5 (cohort_key Adam-decision) + A6 (~$11-14 real-Anthropic spend). Adam picked option (a) "authorize both and proceed."

### A5 authorization — cohort_key 4-tuple locked

**Adam-decision 2026-06-27:** lock cohort_key to the epics.md § Epic 9 Detail spec line 3072 default 4-tuple:

```text
cohort_key = (prompt_v, scorer_model, anchors_v, router_policy_v)
```

No amendment. This becomes the migration's frozen column shape for Story 9-6. Changing it later requires a migration revision.

### A6 authorization — real-Anthropic spend cap ($14 hard ceiling)

**Adam-decision 2026-06-27:** authorize $14 total spend across the benchmark tranche, split per-line-item:

| Line item | Story | Estimate |
| --- | --- | --- |
| Cost-cap unit test | 9-6 | $0 |
| Haiku-vs-Opus on `draft_reply` | 9-7 | ~$5 |
| Cross-evaluator on 20 anchors (Krippendorff alpha) | 9-7 | ~$1-3 |
| Full 100-item corpus walk on production routing | 9-8 | ~$4-5 |
| Anchor-drift baseline persistence | 9-11 | ~$1 |

**Enforcement (Adam-decision 2026-06-27 — Q1=a):** per-line-item halt-and-surface. When a story's cumulative real-Anthropic spend approaches its line item, the next dispatch that would cross the line halts the run and surfaces the spend snapshot to Adam for explicit Y/N continuation. Never silently exceed a line item.

### Q2 — Krippendorff α fallback (Adam-decision 2026-06-27)

**Adam-decision 2026-06-27 — Q2=a:** if the cross-evaluator agreement coefficient comes back below the done-flip clause 9 threshold (α < 0.6), halt the run and surface the α value to Adam. Do NOT auto-file a stub recalibration story; do NOT treat α as advisory. The benchmark numbers downstream of the agreement gate are unreliable if α < 0.6, and the gate exists precisely to force the disagreement into Adam's attention before any DEMOTE/PROMOTE verdict ships.

### Story 9-5 LLM-recommended corpus propagation (acknowledged)

The benchmark tranche consumes the Story 9-5 corpus built under the 2026-06-27 AC-15 amendment (LLM-recommended labels, not Adam-authored). Per the tranche retro § "Story 9-5 AC-15 amendment 2026-06-27": Story 9-7 measures pipeline-LLM-vs-labeler-LLM agreement, not pipeline-LLM-vs-Adam-judgment. Story 9-9 DEMOTE/PROMOTE verdicts will reflect LLM consensus. Re-anchoring procedure documented in `docs/eval-corpus.md § 9`.

### Done-flip gate (11 clauses) — reactivated

All 11 clauses from sprint-status.yaml lines 232-244 fire at end of run:

1. Stories 9-1..9-11 status=done — pending Run 3
2. 9-8 E2E canary produces valid `report.json` — pending 9-8
3. `/model` one-shot live-verified (audit shows `slash_command:one_shot:adam`) — deferred to Phase 3.5
4. `/model` persistent live-verified — deferred to Phase 3.5
5. Sensitivity gate regression (`/model qwen --once` on confidential email refused) — deferred to Phase 3.5
6. Benchmark cost-cap test passes — covered by 9-6 unit test
7. Full 100-item corpus live walk — A6 authorized
8. Haiku-vs-Opus on `draft_reply` — A6 authorized
9. Krippendorff α reported (BLOCKS if α < 0.6) — Q2 enforcement above
10. Anchor-drift baseline persisted to `evals/anchor_baselines/v1.json` — covered by 9-11
11. `policy.yaml` v0 → v1 bump (benchmark-driven routing change OR Adam-signed retro entry) — if no routing change warranted, surface for Adam retro-entry sign-off; do NOT auto-bump

### Models

- Dev: `claude-opus-4-7` (this session)
- Reviewer: `claude-sonnet-4-6` per dev-vs-review different-model invariant

### `#yolo` mode

Activated for the per-story sub-workflows (create-story, dev-story, code-review) during the main loop. Deactivated at Phase 3 close per Phase 1.5 contract. Does NOT propagate to the retrospective or to Phase 3.5 manual verification.

### Phase 0.2 orphan-scan mitigation (Adam-decision 2026-06-27)

**Found at Phase 0.2:** Epic 7's `7-5` / `7-6` / `7-7` are `backlog` and sit at sprint-status.yaml lines 207-209 — lexically before Epic 9's `9-6` / `9-7` / `9-8` / `9-9` / `9-11` (lines 251-256). `bmad:bmm:workflows:create-story` with no arg scans top-to-bottom and would pick `7-5` instead of `9-6`.

**Why technically a false positive:** Epic 7 is sequenced AFTER Epic 9 per the 2026-06-07 party-mode roundtable scope cleave (sprint-status.yaml lines 197-205). The 7-5/7-6/7-7 backlog state is correct — they're waiting on Epic 9 outputs.

**Mitigation (Adam-decision 2026-06-27, option a):** pass explicit `story_path` to every `create-story` invocation in the Run 3 loop. Order: `9-6` → `9-7` → `9-8` → `9-9` → `9-11`. Sidesteps the top-down scan; no sprint-status reordering needed.

**Carry-forward for Epic 9 full retro:** Epic-7-dependent-block lexical-vs-architectural mismatch is a process learning. Consider either (i) reordering sprint-status.yaml when an epic is scope-cleaved to depend on a later epic, or (ii) extending Phase 0.2 spec to recognize the architectural-sequencing carve-out shape directly.

### Run 3 scope-cleave (Adam-decision 2026-06-27, options a then x)

**Mid-Phase-2 scope-cleave** before entering the create-story loop. Original Run 3 scope: 5 stories (9-6, 9-7, 9-8, 9-9, 9-11). Adam-decision sequence:

1. **First cleave (option a):** 9-6 + 9-8 + 9-9 this run; 9-7 + 9-11 deferred. Reasoning: 9-7 + 9-11 are research-shaped (anchor calibration, cross-evaluator alpha verdict) with real-Anthropic spend; benefit from focused single-story passes.
2. **Second cleave (option x):** further narrowed to **9-6 only** this run; 9-8 + 9-9 also deferred. Reasoning: 9-6 alone is a heavy MANDATORY-CR story (migration 024 + new benchmark/ package + cost gate + cohort_key + ~500-800 LOC + +20-40 net tests). Combined with Phase 0 token-spend on Adam-decision surfaces, the residual context budget cannot reliably carry 3 heavy stories. Single-story focused passes for 9-8 + 9-9 preserve coherence.

**Final Run 3 scope: 9-6 only.**

| Story | This run? | Reason |
| --- | --- | --- |
| 9-6 (runner + migration + cost gate + cohort_key) | Yes | Mechanical infrastructure; $0 dev-time spend; no Anthropic dispatch |
| 9-7 (scorer + cross-evaluator Krippendorff alpha) | **Deferred** to dedicated /autonomous-story-run | Research-shaped; real-spend (~$5 Haiku-vs-Opus + ~$1-3 cross-evaluator) |
| 9-8 (E2E canary corpus → runner → scorer → report) | **Deferred** to dedicated /autonomous-story-run | Pairs naturally with 9-7 real-Anthropic dispatch for httpx.MockTransport fixture recording |
| 9-9 (report renderer + Pareto + DEMOTE/PROMOTE + CIs + sample-size gate) | **Deferred** to dedicated /autonomous-story-run | Pure compute; cleanest with 9-7 + 9-8 outputs already on disk |
| 9-11 (anchor stability audit + alpha verdict) | **Deferred** to dedicated /autonomous-story-run | One-shot research-shaped measurement; alpha verdict can halt entire run |

**Epic 9 done-flip:** stays gated after this run on Stories 9-7 + 9-8 + 9-9 + 9-11 plus all 11 clauses of the done-flip gate (sprint-status lines 232-244). Epic 9 status remains `in-progress` after Run 3 closes.

**Reactivation guidance:** /autonomous-story-run 9-7 → /autonomous-story-run 9-8 → /autonomous-story-run 9-9 → /autonomous-story-run 9-11 → Adam invokes full Epic 9 retrospective.

### Run 3 close (2026-06-28)

**Final scope shipped:** Story 9-6 only (per scope-cleave option x above).

#### Per-story summary table

| Story | Status | Tests delta | Review rounds | Issues found | Issues applied | Applied-rate | CR cadence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 9-6 | done | +20 net (1450 → 1470) | 1 | 7 (6 Patch + 1 Defer) | 6 actionable Patches | 100% (6/6) | MANDATORY-CR (sonnet-4-6, §5.12 criterion 1 + 6 fire) |

#### Aggregated `[deferred:*]` items

- **CR-F7 LOW Defer (Story 9-6):** AC-9 Test 6 (SIGINT simulation) not implemented — Windows SIGINT-in-asyncio brittleness; revisit on Linux CI follow-up. Manual code review of `_run_dispatch_loop` covers the path. Carry-forward to next Epic 9 full retro.
- **Pre-review §3 MEDIUM ACCEPT WITH RATIONALE (Story 9-6):** `read_completed_cells` set-membership loses status information — `--resume` skips ANY-status cells, no flag to re-run aborted ones. Operator-recoverable via manual SQL. Carry-forward to deferred-work.md for a future "re-run aborted cells" flag.
- **Pre-review §3 MEDIUM ACCEPT WITH RATIONALE (Story 9-6):** SIGINT race window between `record_benchmark_run` and next iteration. Worst case: one cell marked `completed` instead of `interrupted`. Doesn't break resume semantics. No action.

#### Biggest CR catch this run

**CR-F1 HIGH** caught a dead test: the dev pass's Test 4 (`test_runner_aborts_on_monthly_budget_exceeded`) used a non-existent `BudgetGuard.month_spent_usd` attribute (correct name is `this_month_spend_usd`) AND mapped to the never-emitted `MONTHLY_BUDGET_EXCEEDED` error code. The conditional `if exit_code == 2:` masked the failure. The dev-pass's pre-review §1 verdict was MATCH, missing the dead-test pattern. The CR-reviewer's parallel-adversarial-layer caught it on first pass. Patch consolidated CR-F1+F4 into a single real test exercising the production `DEGRADED_MODE_BLOCKED` path via `_degraded_mode_active=True` + `force_model="claude-opus-4-7"`.

#### Architectural-impossibility discharges (precedent chain — none new this run)

Story 9-6 introduced no architectural-impossibility discharges. Precedent chain remains at 4 stories (9-3 OQ-2 + 9-4 OQ-1 + 9-5 AC-15 amendment + 9-10 OQ-1 Path γ).

#### Phase 3.5 manual verification gate

**DOES NOT FIRE this run.** Epic 9 stays `in-progress` per the Run 3 scope-cleave (9-7 + 9-8 + 9-9 + 9-11 deferred). Phase 3.5 is end-of-epic-scoped per autonomous-epic-run cadence, not end-of-tranche-scoped. Will fire on the eventual Epic 9 done-flip after Stories 9-7 + 9-8 + 9-9 + 9-11 ship.

#### UX advisory

**N/A** — project has no graphical frontend per PORTING.md.

#### Self-grading scorecard

- ☑ **A1** — UI scope check passed (N/A per PORTING.md, applied uniformly)
- ☑ **A2** — end-of-epic dev-env verification N/A per PORTING.md
- ☑ **A4** — this `<flags-file>` (epic-9-run-flags.md) updated with all `[deferred:*]` items + per-story summary
- ☑ **A5** — issues-found-vs-applied tracked: Story 9-6 6/6 actionable Patches applied = 100% (well above ≥70% threshold)
- ☑ **A7** — UX advisory N/A per PORTING.md
- ☑ **B1** — File-List-vs-git gate (Step 2.4.6) PASSED after staging (17 files; story-scoped; no scope creep beyond pyproject.toml self-caught in §2)
- ☐ **B2** — Phase 3.5 manual-verification gate — **DOES NOT FIRE** (Epic 9 stays in-progress)

#### Recommendations for next retrospective (Epic 9 full retro)

When the benchmark tranche (9-7 + 9-8 + 9-9 + 9-11) ships and Epic 9 reaches done-flip, the full Epic 9 retro should consolidate this Run 3 with the benchmark-tranche findings. Items to consolidate:

1. **AC-7 amendment pattern** (Story 9-6 `email_id=None` + `force=True`) — both are amendments discovered at integration-test time, not at design time. Worth documenting as a recurring pattern for benchmark-shaped stories that dispatch against synthetic data vs production data.
2. **CR-F1 dead-test catch** — the pattern where a test passes because the test asserts on a typo'd attribute path that doesn't trigger the actual code path. Suggests a pre-review §3 self-audit check: "for every test asserting on a guard's mutated state, paste the attribute path's `Grep` verification."
3. **CR-F2 dormant-code-path pattern** — `MONTHLY_BUDGET_EXCEEDED` defined in errors.py but never emitted by production router. Worth a future tooling story: lint check for unused `ErrorCode` enum members against `grep "ErrorCode\.X"` in production code.
4. **Per-line-item halt-and-surface (Q1=a)** — not exercised this run (Story 9-6 line-item budget = $0). The mechanism will first fire in Story 9-7's Haiku-vs-Opus walk; should evaluate effectiveness then.
5. **Krippendorff α halt-and-surface (Q2=a)** — won't fire until Story 9-11. Document evaluation criteria upfront.
