# Pre-Review Self-Audit — 9-8

**Generated:** 2026-06-28 by claude-opus-4-7 (Opus 4.7, 1M context)
**Story file:** `_bmad-output/implementation-artifacts/9-8-e2e-join-5-item-canary-corpus-runner-scorer-report.md`
**Status at audit time:** review (post dev-story, pre code-review)

---

## 1. AC-vs-code drift scan

The ACs in the story file were amended at dev-time vs. the original epics.md AC text (Phase 0 disposition path b + two test-time scope amendments documented in Debug Log). Drift scan is against the **as-shipped story file ACs**, not the original epics.md text.

- **AC-1 (5×2×2=20 cells via runner; --cost-mock + --yes):** `DRIFT — scoped to 5×1×2=10 (objective-only)` — the as-shipped story file explicitly documents the scope reduction in the AC line itself + Debug Log + Task 2 completion note. The test asserts exactly 10 rows. No silent drift; intentional and surfaced.
- **AC-2 (fake adapters via register_adapter, Rule I preserved):** `MATCH` — Test 1 + Test 2 both wire adapters via `register_adapter(_QWEN, ...)` + `register_adapter(_HAIKU, ...)`; no `ask_router` mock. Router runs end-to-end through precondition + lane + audit.
- **AC-3 (scorer produces benchmark_scores rows for same tuples):** `MATCH` — Test 1 asserts `len(scores) > 0`, `task_type == "coarse_class"` present, cohort_key propagates from benchmark_runs.
- **AC-4 (minimal renderer produces benchmark/reports/<run_id>.md):** `MATCH` — `render_report(db_path, run_id, output_dir)` writes `<output_dir>/<run_id>.md`; Test 1 asserts file exists at expected name. Note: tests use `tmp_path/reports/` not `benchmark/reports/` to avoid polluting the repo working tree; the production path is the default when called without `output_dir` override. `benchmark/reports/.gitignore` protects the repo path.
- **AC-5 (Pareto + DEMOTE/PROMOTE INSUFFICIENT DATA literal):** `MATCH` — Test 1 asserts `"INSUFFICIENT DATA" in report_text`, `"gate=15" in report_text`, `"## Pareto Frontier"` + `"## DEMOTE/PROMOTE Suggestions"` headers.
- **AC-6 (cost-mock failure-mid-run + resume):** `DRIFT — switched from "adapter raises after 10" to "--max-items 3 partial state"` — the as-shipped story file's Task 3 completion note documents the rationale (Router's AR-PAT-4 catch-all at `router.py:887` converts adapter `Exception` to `outcome=provider_error` with `status=completed`, so adapter exceptions don't propagate or leave partial-state). The `--max-items 3` approach exercises the **same** resume contract through the official partial-state surface. Test asserts: first invocation = 6 rows, resume = 10 rows total, distinct (item,task,model,pv) tuples = 10 (UNIQUE constraint sanity).
- **AC-7 (CR cadence verdict MANDATORY-CR sonnet-4-6):** `MATCH` — see §5.12 below; criterion 1 fires (new module `benchmark/report.py` under boundary-policed `benchmark/` package). Will dispatch in Step 2.4.

---

## 2. File-List-vs-git diff check

`git status --porcelain` filtered for 9-8-relevant paths:

```text
?? _bmad-output/implementation-artifacts/.autonomous-run-active.json
?? _bmad-output/implementation-artifacts/9-8-e2e-join-5-item-canary-corpus-runner-scorer-report.md
?? benchmark/report.py
?? benchmark/reports/
?? tests/integration/test_benchmark_e2e_canary.py
```

Modified (staged path-only): `benchmark/__init__.py`, `_bmad-output/implementation-artifacts/sprint-status.yaml`.

Cross-reference vs File List:

- `benchmark/report.py` — UNTRACKED + IN FILE LIST ✅ (expected; will stage at Phase 2.6)
- `benchmark/reports/.gitignore` — UNTRACKED + IN FILE LIST ✅ (parent dir `benchmark/reports/` listed as untracked)
- `benchmark/__init__.py` — MODIFIED-NOT-STAGED + IN FILE LIST ✅
- `tests/integration/test_benchmark_e2e_canary.py` — UNTRACKED + IN FILE LIST ✅
- `_bmad-output/implementation-artifacts/9-8-...md` — UNTRACKED + IN FILE LIST ✅
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED + IN FILE LIST ✅
- `_bmad-output/implementation-artifacts/.autonomous-run-active.json` — UNTRACKED + IN FILE LIST ✅ (noted as transient/removed-at-Phase-3.5)

Also present in working tree but NOT in File List (background-unrelated work, will NOT be staged at Phase 2.6):

- `.claude/settings.json` (38/46 diff in settings — outside story scope; Adam's local envelope tuning)
- All `.claude/skills/`, `.claude/hooks/`, etc. — outside story scope; pre-existing untracked

Verdict: **PASS** — story-relevant paths all match between File List and git output; unrelated working-tree state will be excluded from staging at Phase 2.6 per the "carefully selected, NOT `git add -A`" contract.

---

## 3. Adversarial self-review

3-10 self-caught issues. Format: `- [SEVERITY] <file:line> — <one-sentence finding>`.

- **[LOW] benchmark/report.py:1-12** — module docstring claims "Story 9.9 REPLACES this stub with the full renderer" but the upgrade contract isn't expressed structurally (Story 9.9 could replace the body and rename `render_report` and the breakage wouldn't surface until callers fail at import). Mitigation: the `__all__` export and module-level constants (`_SAMPLE_SIZE_GATE`, `_INSUFFICIENT_DATA_FMT`) provide the structural anchor; if Story 9.9 changes the public surface it has to update `benchmark/__init__.py` and the E2E test, which surfaces the break.
- **[LOW] benchmark/report.py:142** — `render_report` calls `asyncio.run(read_run_scores(...))` synchronously. If Story 9.9 wires the renderer into an async caller (FastAPI route, async CLI), `asyncio.run` inside an already-running event loop raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. Current callers (tests + future Story 9.9 standalone CLI) are sync; acceptable for stub scope. Carry-forward note in §4.
- **[LOW] tests/integration/test_benchmark_e2e_canary.py:73-117** — the `_ScriptedAdapter` class duplicates the one in `tests/integration/test_benchmark_runner.py:75-125` rather than importing. Pattern matches Story 9-7 `test_scorer.py:77-107` which also defined its own local `_ScriptedSubjectiveAdapter` rather than importing. Test-helper duplication across `tests/integration/` is a pre-existing repo pattern (see also `_FakeAdapter` in `test_backpressure_e2e.py:46` + `test_pipeline_e2e.py`). Refactoring to a shared `tests/integration/_fakes.py` is a separate tooling story.
- **[INFO] tests/integration/test_benchmark_e2e_canary.py:185-188** — happy-path test reuses the same `_task_responses()` for both qwen + haiku adapters. Both adapters respond with `class_coarse: "newsletter"` on every call, so the scorer's accuracy metric will be (n=1 correct / n=5 = 0.2) — fine for asserting "metric_value populated" but doesn't exercise the differential-model-quality intent of the benchmark. Acceptable for stub-scope (Story 9-9 full-corpus walk is where differential quality lives); the E2E test's purpose is integration-seam coverage, not benchmark quality.
- **[INFO] benchmark/report.py:53-72** — per-task table sorts rows by `(model, metric_name)` not by metric_value. Empty-state rows (sample_count < gate) render the literal in the value column; non-empty rows render `f"{row.metric_value:.4f}"`. Stable sort means deterministic output for snapshot testing; no issue.
- **[LOW] tests/integration/test_benchmark_e2e_canary.py:177** — `monkeypatch.setattr("benchmark.runner._DEFAULT_ANCHORS_DIR", str(anchors_dir))` mirrors the Story 9-6 test pattern (`test_benchmark_runner.py:231-233`). The monkeypatch lives ONLY for the test's duration; no module-global state leak.

---

## 4. Self-caught issues remediated this audit

- **§3 LOW (benchmark/report.py:1-12, structural upgrade contract):** **ACCEPT WITH RATIONALE** — the public-surface anchor via `__all__` is the precedent across all `benchmark/*` modules (cohort, db, schemas, scorer_db). Story 9.9's upgrade path is "replace body, keep signature"; if Story 9.9 also wants to rename, that's an intentional API change requiring callers to be updated and is correctly surfaced as a breaking change.
- **§3 LOW (benchmark/report.py:142, asyncio.run inside async caller):** **ACCEPT WITH RATIONALE + carry-forward** — current callers are all sync. If Story 9.9 grows an async caller, the fix is `async def arender_report(...)` alongside sync `render_report(...)` per the standard "two-name pair" Python pattern. Carry-forward to deferred-work as `[deferred: Story 9.9 — if renderer is called from async context, add async variant]`.
- **§3 LOW (test helper duplication):** **ACCEPT WITH RATIONALE** — pre-existing pattern across 3+ integration test files in the repo. Refactoring to shared `tests/integration/_fakes.py` is a separate tooling story; doing it here would expand scope beyond Story 9-8's E2E surface.
- **§3 INFO (uniform adapter responses don't exercise differential quality):** **ACCEPT WITH RATIONALE** — E2E test's purpose is integration-seam coverage, not benchmark quality discrimination. Differential quality lives in Story 9.9's full-corpus Haiku-vs-Opus comparison (Epic 9 done-flip clause #8).
- **§3 INFO (table sort order):** **ACCEPT** — deterministic; matches stub scope.
- **§3 LOW (monkeypatch scope):** **ACCEPT** — matches Story 9-6 precedent; no module-global leak.

No issue rises to ESCALATE-TO-REVIEWER. Six §3 findings, all dispositioned; no shallow-audit flag.

---

## 5. Posture Audit

### 5.1 Lockfile hygiene

```bash
$ rtk git diff --stat requirements.txt
(no output)
```

Verdict: ✅ PASS — Story 9-8 introduces no new deps; `requirements.txt` untouched.

### 5.2 Cross-doc pair verification

**Cross-doc branch:** N/A — Story 9-8 makes no claims that cross-reference external canonical docs (no docs/* claims). The story DOES cite epics.md line numbers (3089, 3099, 3317–3342) in Dev Notes References — those are read-only line references, not cross-doc claims requiring grep verification.

**5.2.1 schema-touching:** N/A — File List contains no migrations paths (`mailbot_api/db/migrations/*`). Story 9-8 is read-only against schema established by migrations 024 (Story 9-6) + 025 (Story 9-7).

Verdict: ✅ N/A (both branches).

### 5.3 Lifecycle string-uniqueness

N/A — Story added zero i18n keys. MailBot has no graphical frontend per PORTING.md.

### 5.4 Multi-consumer impact scan

`benchmark/__init__.py` modified (added `render_report` export). Consumers of `benchmark.__init__`:

```bash
$ rtk grep -rn "from benchmark import" mailbot_api benchmark tests scripts 2>/dev/null | head -10
```

(no production consumers — `from benchmark import X` not used; everything imports via `from benchmark.<module> import X`)

Verdict: ✅ PASS — the new `render_report` export is additive; no existing consumer of `from benchmark import ...` exists today. The export is for future-Story-9.9 + ad-hoc shell usage convenience.

### 5.5 Screenshot-based perception check

N/A — MailBot has no graphical frontend; no AC uses "visible"/"appears"/"displays" against a UI surface. The "report file exists" AC-4 is filesystem state, not human-perceptible state.

### 5.6 Upstream-contract spec coverage

N/A — Story 9-8 does not consume any upstream-stripped-by-role field. The renderer reads `benchmark_scores` rows which carry the Pydantic schema directly (no role-stripping). The integration test exercises the full producer→consumer chain end-to-end without any role-projection layer.

### 5.7 Module-level mutable container check

Modified `.py` files: `benchmark/__init__.py`, `benchmark/report.py`, `tests/integration/test_benchmark_e2e_canary.py`.

Grep for module-level mutable patterns:

```bash
$ rtk grep -n "^_[A-Z_]* *: *(dict|list|set)" benchmark/report.py tests/integration/test_benchmark_e2e_canary.py 2>/dev/null
```

(no output — `benchmark/report.py` declares only `_SAMPLE_SIZE_GATE: int = 15` and `_INSUFFICIENT_DATA_FMT: str = ...`; both immutable scalars typed implicitly as `int` and `str`. `tests/integration/test_benchmark_e2e_canary.py` declares only string constants `_QWEN`, `_HAIKU`, `_POLICY_YAML_TEMPLATE` — all immutable.)

Verdict: ✅ PASS — no module-level mutable containers introduced. `benchmark/__init__.py` is import-only.

### 5.8 Dev-fixture seed-vs-production-shape parity

`tests/integration/test_benchmark_e2e_canary.py` introduces these test fixtures:

- `_good_coarse_class_response()` — returns an `AdapterResponse` matching the Story 9-6 `_good_coarse_class_response()` shape from `test_benchmark_runner.py:128-136` (cloned verbatim).
- `_POLICY_YAML_TEMPLATE` — minimal policy.yaml matching the Story 9-6 `_POLICY_YAML_TEMPLATE` from `test_benchmark_runner.py:52-72` (subset: only coarse_class + summary_short tasks; matches the producer shape).
- Canary corpus via `shutil.copyfile(Path("evals/fixtures/canary_5.jsonl"), corpus_path)` — pattern 1 (recorded snapshot). The source `evals/fixtures/canary_5.jsonl` was hand-authored in Story 9-5 against the canonical `CorpusItem` Pydantic schema (`evals/corpus_schema.py`) and validated by `evals/_labeling/corpus-index.csv`. The fixture is byte-equal-as-shipped by `shutil.copyfile`; any future Story 9-5 corpus drift fails the test (the test would see different cohort_key or different row count).

Verdict: ✅ PASS — all fixtures are pattern 1 or pattern 2 (cloned from Story 9-6 producer-tests). No pattern 3 shape-faithful synthesis used.

### 5.9 grep-verify-cited-figures

Cites in the story file (Completion Notes + File List + Change Log) that require verification:

- **Cite: "1533 passed + 2 skipped + 3 deselected"** (story file Completion Notes + Task 5).
  - Verification command: `.venv/Scripts/python.exe -m pytest -q` (run at 2026-06-28).
  - Pasted output: `1533 passed, 2 skipped, 3 deselected, 1 warning in 195.79s (0:03:15)`.
  - Verdict: ✅ MATCH.

- **Cite: "+2 net tests vs Story 9-7 close baseline 1531+2+3"** (story file + Task 5).
  - Verification: prior story 9-7 sprint-status row says `1531+2-skipped+3-deselected`; current run reports 1533+2+3 → delta = +2. Story added exactly 2 tests (`test_e2e_canary_happy_path_runner_scorer_report` + `test_e2e_canary_partial_state_then_resume_completes_all_cells`).
  - Verdict: ✅ MATCH.

- **Cite: "144 source files" mypy** (story file Task 5 + Completion Notes).
  - Verification command: `.venv/Scripts/python.exe -m mypy --strict mailbot_api/ evals/ benchmark/`.
  - Pasted output: `Success: no issues found in 144 source files`.
  - Verdict: ✅ MATCH. Also matches the predicted +1 vs Story 9-7 close baseline 143 (Story 9-7 sprint-status row says 143 source files; +1 = `benchmark/report.py`).

- **Cite: "benchmark/report.py ~145 lines"** (story file Completion Notes Task 1 line).
  - Verification: `Bash wc -l benchmark/report.py` — running below.

```bash
$ wc -l benchmark/report.py
156 benchmark/report.py
```

  - Verdict: ⚠️ MINOR DRIFT — actual 156 lines vs cited "~145 lines"; the `~` qualifier makes this an order-of-magnitude approximation under §5.9 legitimate exception. No fix required; the `~` carries the imprecision license.

- **Cite: "epics.md:3089" + "epics.md:3317–3342" + "epics.md:3099"** (story file Dev Notes References).
  - Verification command: re-read epics.md at those offsets (already done at Phase 0).
  - Spot check: epics.md:3089 contains the dep-table row for 9.8 (verified at Phase 0). epics.md:3317 is `### Story 9.8: E2E join — 5-item canary corpus → runner → scorer → report` (verified at Phase 0). epics.md:3099 is `2. 9.8 E2E canary produces valid \`report.json\` on 5-item corpus with all cohort_key fields populated and evaluator model version pinned` (verified at Phase 0).
  - Verdict: ✅ MATCH.

Verdict: ✅ PASS — all cited figures verified, with one trivial `~145` ↔ 156 lines drift covered by the order-of-magnitude exception.

### 5.10 Producer-boundary contract enforcement

**5.10.a typed-column producers:** N/A — Story 9-8 ships a READ-ONLY consumer of `benchmark_scores`. No new producer code, no new typed-column writes, no new third-party JSON ingestion. The `BenchmarkScoreRow` Pydantic boundary (Story 9-7) is the writer's input guard; `benchmark/report.py` reads pre-validated rows.

**5.10.b response-shape allow-list:** N/A — `render_report` returns a `Path` (filesystem path to the rendered file), not an HTTP response. No HTTP boundary, no co-emission audit needed. The file content is intentionally plaintext Markdown for human + Story 9.9 consumption.

**5.10.c producer-boundary input-shape guard:** N/A — no normalizer / extractor / ingestion path introduced.

**5.10.d adjacent-shared-type re-export audit:** N/A — `benchmark/__init__.py` re-exports `render_report` (a function, not a type). No new shared TYPE re-export.

Verdict: ✅ N/A (all 4 sub-checks).

### 5.11 Git-evidence consistency check

**5.11.a File-List-vs-working-tree:** verified inline in §2 above. All 7 declared File List paths appear in git output; no STAGED-NOT-IN-LIST, no IN-LIST-NOT-IN-GIT. Background-unrelated working-tree state (`.claude/settings.json`, `.claude/skills/*` untracked) will be excluded from staging per the Phase 2.6 selective-staging contract.

Verdict: ✅ PASS.

**5.11.b production-only test-to-code ratio:**

```bash
$ rtk git diff --numstat 2>&1 | head -20
38	46	.claude/settings.json
1	1	_bmad-output/implementation-artifacts/sprint-status.yaml
2	0	benchmark/__init__.py
```

Plus untracked-pending-add (will be staged at Phase 2.6):

- `benchmark/report.py` — 156 lines (production)
- `benchmark/reports/.gitignore` — 1 line (docs/infrastructure)
- `tests/integration/test_benchmark_e2e_canary.py` — 333 lines (test)
- `_bmad-output/implementation-artifacts/9-8-...md` — ~120 lines (docs)
- `_bmad-output/implementation-artifacts/9-8-...pre-review.md` — this artifact (~250 lines, docs)

Test-classifier applied:
- `testAdded` = 333 (test_benchmark_e2e_canary.py)
- `docsAdded` = 120 + 250 + 1 = 371 (.md + .md + .gitignore counted as docs/infrastructure)
- `prodAddedExcludingDocs` = 156 (benchmark/report.py) + 2 (benchmark/__init__.py added lines) = 158
- `prodOnlyTestRatio` = 333 / 158 = 2.11

Threshold: 0.3.

Verdict: ✅ PASS — 2.11 ≫ 0.30 (test-to-prod ratio is dominated by the 333-line integration test against 158 prod lines).

**5.11.c no-later-commits-under-attribution:** N/A — single-session dev pass. Story status flipped `backlog → ready-for-dev → in-progress → review` all within the same `/autonomous-story-run` invocation on 2026-06-28. No intervening commits.

Verdict: ✅ N/A.

### 5.12 CR-cadence-mandatory surface classification

Story surface classification:

- **Criterion 1 (boundary-introducing):** YES — new module `benchmark/report.py` under the `benchmark/` package which is itself a boundary-policed package per Story 9-6 / 9-7 precedent (writer-monopoly checks in `scripts/check_boundaries.py:_BENCHMARK_RUNS_INSERT_ALLOW` + `_BENCHMARK_SCORES_INSERT_ALLOW`). The new module is READ-only against `benchmark_scores`, which doesn't introduce a new writer monopoly, but adding the file under a boundary-policed package is itself the boundary-introducing event the criterion calls out. Conservative classification = fires.
- **Criterion 2 (dep-introducing):** NO — no new deps in requirements.txt; verified §5.1.
- **Criterion 3 (dev-self-flagged):** NO — §3 surfaced 6 findings, all ACCEPT WITH RATIONALE or carry-forward; zero ESCALATE-TO-REVIEWER items.
- **Criterion 4 (capstone):** NO — Story 9-8 is mid-Epic-9; remaining stories 9-9 + 9-11. Not the last story in its epic.
- **Criterion 5 (privacy-invariant):** NO — Story 9-8 ships a read-only renderer for benchmark output. No FR-2.3/FR-2.5/FR-5.7 surface, no NFR-PRIV-* requirement, no AR-D12-* rule. The `benchmark_scores` rows it reads are not PII; corpus items were anonymized in Story 9-5.
- **Criterion 6 (load-bearing-orchestrator):** PARTIAL — Story 9.9 will inherit the stub's public surface (path + module export + empty-state literal) as its upgrade target. But Story 9-8 itself is not an integration surface for other epics; it's the E2E join story for Epic 9 done-flip clause #2. Defensive read: the stub IS a primary integration surface for Story 9.9 specifically (the one downstream consumer). Conservative classification = fires.

**Cadence verdict: MANDATORY-CR** (criterion 1 fires unambiguously; criterion 6 fires defensively). CR subagent to dispatch under `claude-sonnet-4-6` at Step 2.4.

---

## Posture Audit summary table

| Check                                                       | Status                                  |
| ----------------------------------------------------------- | --------------------------------------- |
| 5.1 Lockfile hygiene                                        | ✅ PASS                                 |
| 5.2 Cross-doc pair verification                             | ✅ N/A (no cross-doc claims, no migrations) |
| 5.3 Lifecycle string-uniqueness                             | ✅ N/A (no i18n keys; no frontend)      |
| 5.4 Multi-consumer impact scan                              | ✅ PASS (additive export, no consumers today) |
| 5.5 Screenshot-based perception check                       | ✅ N/A (no graphical frontend)          |
| 5.6 Upstream-contract spec coverage                         | ✅ N/A (no role-stripped fields)        |
| 5.7 Module-level mutable container                          | ✅ PASS (only immutable scalars added)  |
| 5.8 Dev-fixture seed-vs-production-shape parity             | ✅ PASS (pattern 1 + cloned-from-producer-tests) |
| 5.9 grep-verify-cited-figures                               | ✅ PASS (5/5 cites verified)            |
| 5.10 Producer-boundary contract enforcement                 | ✅ N/A (read-only consumer, no HTTP)    |
| 5.11 Git-evidence consistency check                         | ✅ PASS (a + b + c)                     |
| 5.12 CR-cadence-mandatory surface classification            | **MANDATORY-CR** (criterion 1 + 6 fire) |
