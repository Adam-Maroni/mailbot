# Story 9.9: Report renderer — Pareto frontier + DEMOTE/PROMOTE with confidence intervals + sample-size gate

Status: done

baseline_commit: dc04e5d4ac33c35a09a4a8fe6785f7cea3dd11ec

## Story

As Adam,
I want `benchmark/report.py` upgraded from the Story 9-8 stub to a full renderer that produces a per-task report with Wilson-score confidence intervals on accuracy/precision/recall, bootstrap CIs on latency/cost, a Pareto frontier per task that drops cost-quality-dominated models, DEMOTE-valid/DEMOTE-invalid/PROMOTE-needed verdicts with an n≥15 sample-size gate, a cohort_key-keyed primary slice with a separate cross-cohort drift comparison section, and a Scorer-calibration section that surfaces the Story 9-7 cross-evaluator Krippendorff α when present,
So that Epic 9 done-flip clause #4 ("benchmark report renders cleanly for the 5-item canary AND for a full corpus walk if attempted") and clause #11 ("one benchmark-driven routing change OR Adam-signed retro entry") have an evidence-based artifact, and so the next calibration round has a copy-pasteable `policy.yaml` snippet to apply rather than a hand-rolled hypothesis.

## Acceptance Criteria

**Given** Stories 9.5 (corpus), 9.6 (runner + `benchmark_runs` + cohort_key contract), 9.7 (scorer + `benchmark_scores` + cross-evaluator support), and 9.8 (E2E canary join + stub renderer) are all `done`
**When** `benchmark.report.render_report(db_path, run_id, output_dir)` is invoked on a populated `benchmark_scores` set
**Then** the renderer emits a Markdown file at `<output_dir>/<run_id>.md` containing the following named sections, in order: `# Benchmark Report`, `## Run metadata`, `## Per-task scores`, `## Pareto Frontier`, `## DEMOTE/PROMOTE Suggestions`, `## Scorer calibration` (when cross-evaluator data present; ELIDED when absent), `## Cross-cohort drift comparison` (when multiple cohort_keys present; ELIDED when only one cohort_key in the run)
**And** the Story 9-8 stub renderer's CR-F3 path-traversal guard on `run_id` (the `_RUN_ID_SAFE_PATTERN` regex) is preserved verbatim — Story 9-9 is a body-upgrade, not a contract change
**And** the Story 9-8 stub renderer's `benchmark/reports/.gitignore` (single line `*.md`) continues to gate the output directory

**Given** every scored metric carries a `sample_count` field (from migration 025)
**When** the renderer encounters a row whose `sample_count < 15`
**Then** the value cell renders the literal `INSUFFICIENT DATA — n=<count>, gate=15` instead of a numeric value
**And** the DEMOTE/PROMOTE verdict for that (task, model) cell renders `INSUFFICIENT DATA — n=<count>, gate=15` instead of a verdict
**And** the Pareto frontier computation excludes points whose `sample_count < 15` (they are not eligible to dominate or be dominated)

**Given** classification metrics (`accuracy`, `precision_macro`, `recall_macro`) are read from `benchmark_scores`
**When** the renderer formats the per-task table cell for these metrics
**Then** the cell renders `<point_estimate> [95% CI: <lower>–<upper>]` where the bounds are computed via the Wilson score interval at 95% confidence — formula `(p̂ + z²/2n ± z√((p̂(1-p̂) + z²/4n)/n)) / (1 + z²/n)` with `z = 1.96`
**And** the Wilson-CI helper is implemented as a pure-leaf function `wilson_score_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]` (no scipy dependency — matches Story 9-7's pure-numpy Krippendorff α decision because scipy is not installed in this repo)
**And** edge cases are handled cleanly: `trials == 0` returns `(0.0, 1.0)` (maximally uncertain); `successes == 0` returns `(0.0, upper)`; `successes == trials` returns `(lower, 1.0)`

**Given** latency and cost metrics may also be present in the run's `benchmark_runs` joined view (via `read_run_runs` from Story 9-7)
**When** the renderer composes per-(task, model) latency/cost stats
**Then** the renderer reads `latency_ms` + `cost_usd` per `benchmark_runs` row, groups by (task, model), and produces a bootstrap 95% CI using 1000 resamples with replacement — implemented as a pure-leaf `bootstrap_ci(samples: list[float], n_resamples: int = 1000, confidence: float = 0.95, random_seed: int = 42) -> tuple[float, float]`
**And** the bootstrap helper uses a fixed `random_seed=42` so CI bounds are reproducible across re-runs of the renderer (regression test on stability)
**And** rows whose runner-side `outcome != "ok"` are EXCLUDED from latency/cost stats (a 5000ms timeout doesn't reflect the model's healthy-call latency); the excluded count is surfaced in the per-task table as a footnote count

**Given** the per-task table lists every (model, prompt_version) combination scored for that task
**When** the renderer composes the Pareto frontier section
**Then** the frontier algorithm `compute_pareto_frontier(points: list[ParetoPoint]) -> list[ParetoPoint]` drops any point that is dominated — for every (model, prompt_version), a point is dominated if there exists another point with `cost_per_100_calls <= this.cost AND quality >= this.quality AND (strict inequality in at least one dimension)` where `quality` is the task's primary headline metric (accuracy for classification, f1_action_type for extraction, subjective_overall for subjective)
**And** the frontier section renders one Markdown subsection per task (`### Task: <task_name>`) with a frontier table: `| model | prompt_version | cost_per_100_calls | quality | on_frontier |` — non-frontier rows DROPPED from this section (they remain visible in the per-task scores section above)
**And** when fewer than 2 distinct (model, prompt_version) combinations exist for a task, the frontier section for that task renders `INSUFFICIENT POINTS — need ≥2 distinct (model, prompt_version) combinations to compute a frontier, found <N>`

**Given** the renderer computes DEMOTE/PROMOTE suggestions per (task, current_model)
**When** the verdict engine runs on rows passing the sample-size gate (`sample_count >= 15`)
**Then** the verdict is one of four closed-set values: `"DEMOTE-valid"` (the next-cheaper tier meets the per-rubric threshold; safe to demote in v1), `"DEMOTE-invalid"` (the current tier is on the Pareto frontier; demoting would lose quality), `"PROMOTE-needed"` (the current model's accuracy is below the per-rubric threshold), or `"hold-steady"` (current assignment is correct and stable)
**And** the verdict engine is implemented as a pure-leaf function `compute_verdict(task: str, current_model: str, frontier: list[ParetoPoint], current_metrics: ParetoPoint, per_task_thresholds: dict[str, float]) -> VerdictLiteral` with `VerdictLiteral = Literal["DEMOTE-valid", "DEMOTE-invalid", "PROMOTE-needed", "hold-steady", "INSUFFICIENT_DATA"]`
**And** the `per_task_thresholds` mapping has documented defaults: `{"coarse_class": 0.85, "sensitivity_class": 0.90, "fine_class": 0.75, "summary_short": 3.5, "action_extraction": 0.70, "draft_reply": 3.5, "reference_resolution": 0.90}` — these mirror Epic 7 / Story 7.4 thresholds documented in epics.md (FR-4.3 etc.) and are overridable per (task) via an optional `thresholds_override` parameter to `render_report`
**And** when the verdict is `DEMOTE-valid` or `PROMOTE-needed`, the section renders a copy-pasteable `policy.yaml` snippet with the new assignment + `notes: benchmark run_id <run_id>, evidence: <one-line stat>` — this matches the Story 7.4 original AC

**Given** the cohort_key contract from Story 9.6 (frozen `(prompt_version, scorer_model, anchors_version, router_policy_version)`)
**When** the run's `benchmark_scores` rows span multiple distinct `cohort_key` values
**Then** the report's per-task tables + Pareto frontier + DEMOTE/PROMOTE verdicts ONLY combine rows within the same cohort_key
**And** the report appends a `## Cross-cohort drift comparison` section that ENUMERATES each distinct cohort_key, surfaces the headline metric per (task, cohort_key), and prints a warning header: `> WARNING: Rows below span MULTIPLE cohort_keys — prompt/scorer/anchors/policy evolved between rows. Verdicts above DO NOT use these comparisons; this section is informational only.`
**And** when the run has only one cohort_key, the cross-cohort section is OMITTED ENTIRELY (no empty section header)

**Given** Story 9.7's optional `--secondary-evaluator` pathway produces `metric_name="cross_evaluator_alpha"` rows with `evaluator_role="secondary"` and a `extra_json` payload `{"per_anchor": [{anchor_id, primary_score, secondary_score, delta}, ...], "n_anchors": int}`
**When** the renderer detects at least one such row in the run
**Then** the report includes a `## Scorer calibration` section with: the Krippendorff α value, the per-anchor disagreement breakdown table (`| anchor_id | primary_score | secondary_score | delta |`), and the verdict line — `α ≥ 0.8` → `"scorer trusted"`; `0.6 ≤ α < 0.8` → `"scorer uncertain — α<0.8 boundary"`; `α < 0.6` → `"scorer untrusted — blocks routing decisions until reconciled"`
**And** when no `cross_evaluator_alpha` rows are present in the run, the Scorer calibration section is OMITTED ENTIRELY

**Given** the renderer is invoked via the CLI entry point `python -m benchmark.report --run-id <id> --db-path <path> --output-dir <path>`
**When** the CLI parses arguments
**Then** all three flags are required + a `--thresholds-override` flag accepts JSON (e.g., `--thresholds-override '{"coarse_class": 0.90}'`)
**And** the CLI exits with code 0 on success, code 1 on malformed `run_id` (path-traversal guard), code 2 on database access failure
**And** the CLI's stdout prints the absolute path of the written report file on success

**Given** the renderer's load-bearing parts are pure-leaf helpers
**When** the unit-test suite runs
**Then** `wilson_score_interval`, `bootstrap_ci`, `compute_pareto_frontier`, and `compute_verdict` all have ≥3 unit tests each covering: documented edge cases (zero trials, single point, all-dominated, threshold boundary), 1 happy-path golden-value test, and 1 invariant property test (CI symmetry, frontier monotonicity, verdict closed-set)
**And** the integration test `tests/integration/test_report_renderer.py` exercises the renderer end-to-end against seeded `benchmark_runs` + `benchmark_scores` rows, asserting: section ordering, sample-size-gate firing, Pareto exclusion of dominated points, Scorer-calibration section presence/absence by cross-evaluator data, Cross-cohort drift section presence/absence by cohort_key count, copy-pasteable `policy.yaml` snippet rendering

**Given** this story upgrades the Story 9-8 stub into the full renderer
**When** CR cadence is evaluated per the 6 criteria
**Then** criterion 6 (load-bearing orchestrator) fires because the renderer is the verdict-producing surface gating Epic 9 done-flip clause #11 — Run MANDATORY-CR cadence with reviewer `claude-sonnet-4-6`
**And** the CR scope is focused on (a) Wilson-CI math correctness on edge cases (off-by-one in `2n` denominator, `z²` term ordering), (b) Pareto-frontier dominance condition is correct (strict ≥ vs strict >), (c) DEMOTE/PROMOTE verdict thresholds are not silently coerced from policy.yaml at runtime (must be parameter-passed), (d) cohort_key boundary is enforced in the Pareto + DEMOTE/PROMOTE computation, not just in the rendering layer

## Tasks / Subtasks

- [x] **Task 1: Pure-leaf statistical helpers** (AC: Wilson CI, bootstrap CI) — shipped `benchmark/stats.py` with `wilson_score_interval` + `bootstrap_ci`. 18 tests in `tests/unit/benchmark/test_report_stats.py` (Wilson: 10 covering edge cases, golden values 85/100 → (0.7674, 0.9072) + 5/10 → (0.2366, 0.7634), symmetry property, ValueError paths, [0,1] bound property; Bootstrap: 8 covering empty/single/identical-degenerate, deterministic seed=42, different-seeds-differ, mean-containment, ValueError paths). FP-noise fix: explicit snap to 0.0 / 1.0 when successes ∈ {0, trials} since the radius and half-width terms don't cancel cleanly at the boundary.
  - [x] RED: 18 failing tests written
  - [x] GREEN: helpers implemented in `benchmark/stats.py`
  - [x] REFACTOR: inlined `_Z_95` constant + `_z_for_confidence` Acklam approximation for non-95% paths

- [x] **Task 2: Pareto frontier algorithm** (AC: dominance condition, INSUFFICIENT POINTS edge case) — shipped `compute_pareto_frontier` + `ParetoPoint` frozen dataclass in `benchmark/stats.py`. 8 tests in `tests/unit/benchmark/test_report_pareto.py` (empty / single / cheap-winner-drops-loser / 3-non-dominating-all-retained / identical-ties-both-retained / equal-cost-lower-quality-dropped / equal-quality-higher-cost-dropped / output-sorted-by-ascending-cost). Strict-weak dominance: `no_worse AND strictly_better`.
  - [x] RED: 8 failing tests written
  - [x] GREEN: `compute_pareto_frontier` + `ParetoPoint` implemented
  - [x] REFACTOR: `_dominates` extracted as private leaf with comment citing the strict-weak choice

- [x] **Task 3: DEMOTE/PROMOTE verdict engine** (AC: 5-value closed set, threshold-driven, copy-pasteable snippet) — shipped `compute_verdict` + `VerdictLiteral` + `_default_per_task_thresholds()` in new `benchmark/verdict.py`. 8 tests in `tests/unit/benchmark/test_report_verdict.py` (INSUFFICIENT_DATA gate; PROMOTE-needed; DEMOTE-valid; DEMOTE-invalid; hold-steady; per_task_thresholds override; unknown-task → hold-steady defensive; cheaper-with-insufficient-samples does NOT trigger demote — sample-size gate also applies to alternative-side).
  - [x] RED: 8 failing tests written
  - [x] GREEN: `compute_verdict` + `VerdictLiteral` implemented; default thresholds documented per Epic 7 Story 7.4
  - [x] REFACTOR: `_default_per_task_thresholds()` extracted; Epic 7 origin documented in module docstring

- [x] **Task 4: Refactor `benchmark/report.py` to compose the full renderer** (AC: section ordering, cohort_key primary slice, snippet rendering) — shipped full renderer body (~570 lines including helpers). Public `render_report(db_path, run_id, output_dir, thresholds_override=None) -> Path` signature extended with `thresholds_override` kwarg. CR-F3 `_RUN_ID_SAFE_PATTERN` preserved verbatim. Per-section private leaf functions: `_render_task_table`, `_render_pareto_section`, `_render_demote_promote_section`, `_render_scorer_calibration_section`, `_render_cross_cohort_drift_section`. 16 integration tests in `tests/integration/test_report_renderer.py` covering 5-section ordering, Wilson CI literal "[95% CI:", Pareto retention/dropping, PROMOTE-needed policy.yaml snippet, calibration verdicts at α=0.85/0.65/0.40, drift presence with 2 cohorts and absence with 1, thresholds override changes verdict.
  - [x] RED: 16 failing tests written
  - [x] GREEN: full renderer composing all 5 sections (Per-task scores → Pareto → DEMOTE/PROMOTE → Scorer calibration (conditional) → Cross-cohort drift (conditional))
  - [x] REFACTOR: per-section renderers extracted as private leaf functions returning `str | None` (None signals OMISSION)

- [x] **Task 5: CLI entry point** (AC: `python -m benchmark.report ...`) — shipped `main(argv) -> int` + `_build_parser()` + `if __name__ == "__main__"` guard. 7 CLI tests in `tests/integration/test_report_cli.py` covering missing-required → SystemExit, happy path → rc=0 + stdout prints output path, unsafe run_id → rc=1, missing db file → rc=2, --thresholds-override JSON-accepted, --thresholds-override invalid-JSON → rc=1, --thresholds-override non-object → rc=1.
  - [x] RED: 7 failing tests written
  - [x] GREEN: `main(argv) -> int` implemented; argparse exits non-zero on missing required, db-file existence check pre-empts SQLite auto-create
  - [x] REFACTOR: `_build_parser()` extracted per Story 9-6 runner precedent

- [x] **Task 6: Cross-cohort drift section** (folded into Task 4) — `_render_cross_cohort_drift_section(rows)` returns `None` to OMIT when only 1 cohort_key; renders `> WARNING: Rows below span MULTIPLE cohort_keys` header + per-cohort table when ≥ 2.

- [x] **Task 7: Scorer calibration section** (folded into Task 4) — `_render_scorer_calibration_section(rows)` returns `None` to OMIT when no `evaluator_role="secondary"` + `metric_name="cross_evaluator_alpha"` rows; otherwise renders α value + verdict (trusted ≥ 0.8 / uncertain ≥ 0.6 / untrusted < 0.6) + per-anchor breakdown table from `extra_json["per_anchor"]`.

- [x] **Task 8: Boundary-script extension if needed** (AC: gate-coverage criterion 1) — verified no boundary-script changes required. `benchmark/stats.py` and `benchmark/verdict.py` are pure-leaf math + closed-set Literal (no I/O, no env-vars, no SQL). `benchmark/report.py` body grew but remains READ-ONLY via the existing `read_run_scores` + `read_run_runs` helpers; no new INSERT, no raw SQL, no `os.environ` access. `python scripts/check_boundaries.py` EXIT 0 with zero modifications to `scripts/check_boundaries.py`.

- [x] **Task 9: Run the 4 quality gates** — all green at story close.
  - [x] `.venv/Scripts/python.exe -m ruff check .` EXIT 0 ("All checks passed!") after 2 import-sort auto-fixes
  - [x] `.venv/Scripts/python.exe -m mypy --strict mailbot_api/ evals/ benchmark/` EXIT 0 ("Success: no issues found in 146 source files") — exactly +2 vs Story 9-8 close baseline 144 (`benchmark/stats.py` + `benchmark/verdict.py`)
  - [x] `.venv/Scripts/python.exe scripts/check_boundaries.py` EXIT 0
  - [x] `.venv/Scripts/python.exe -m pytest -q` → **1601 passed + 2 skipped + 3 deselected in 243.24s** post-CR (was 1598 at dev-pass close; +3 from CR regression tests for CR-F1/F3/F4) — exactly **+60 net tests** vs Story 9-8 close baseline 1541+2+3 (18 stats + 8 pareto + 8 verdict + 19 renderer + 7 CLI = 60)

## Dev Notes

### Technical requirements

- **Stack:** Python 3.12+ (in-repo `.venv` at `.venv/Scripts/python.exe`); pytest with pytest-asyncio (async test runner); Pydantic v2; numpy 2.4.6 (already wired — Story 9-7 Krippendorff α uses it); **no scipy** (matches Story 9-7's pure-numpy decision; Wilson CI hand-implemented).

- **New files:**
  - `benchmark/stats.py` — pure-leaf statistical helpers (`wilson_score_interval`, `bootstrap_ci`, `compute_pareto_frontier`, `ParetoPoint`)
  - `benchmark/verdict.py` — `compute_verdict`, `VerdictLiteral`, `_default_per_task_thresholds()`
  - `tests/unit/test_report_stats.py` — stats helpers unit tests (≥9 tests)
  - `tests/unit/test_report_pareto.py` — Pareto frontier unit tests (≥6 tests)
  - `tests/unit/test_report_verdict.py` — verdict engine unit tests (≥5 tests)
  - `tests/integration/test_report_renderer.py` — end-to-end renderer tests (≥6 tests covering AC ordering, cohort_key slicing, calibration section, drift section, snippet rendering)
  - `tests/integration/test_report_cli.py` — CLI entry tests (≥5 tests)

- **Modified files:**
  - `benchmark/report.py` — refactored to compose full renderer; preserve `_RUN_ID_SAFE_PATTERN`, `_SAMPLE_SIZE_GATE`, `_INSUFFICIENT_DATA_FMT`, `_insufficient_data`, public `render_report` signature (extended kwarg-only `thresholds_override: dict[str, float] | None = None`); add `main(argv)` CLI entry; add re-exports in `__all__`
  - `benchmark/__init__.py` — extend `__all__` with new exports from `benchmark/stats.py` + `benchmark/verdict.py`

- **No migrations.** This story is read-only against the schema established by migrations 024 (Story 9-6) + 025 (Story 9-7). The renderer SELECTs from `benchmark_runs` + `benchmark_scores` via the existing read helpers — no new SQL.

- **No new dependencies.** Wilson CI is implemented in numpy; bootstrap uses `numpy.random.default_rng(seed=42)`; Markdown is plain string composition. The pure-numpy decision matches Story 9-7's Krippendorff α — scipy is not installed in this repo, and Story 9.9 introducing scipy as a transitive dep is out-of-scope (would require a separate provisioning story).

### Architecture compliance

- **AR-PAT-1 (selective imports):** `benchmark/stats.py` and `benchmark/verdict.py` import only `numpy` + `typing` + standard library. `benchmark/report.py` may import from `benchmark/{schemas, scorer_db, stats, verdict}`. NO direct `sqlite3` import (use `read_run_scores` + `read_run_runs`).
- **Rule C (single-writer boundary):** `benchmark/report.py` remains a READER, not a writer. No new INSERT-allowlist entry needed (matches Story 9-8 boundary posture).
- **Rule I (Router-centric integration coverage):** N/A for this story — the renderer never calls `ask_router`. Integration coverage comes from the runner+scorer that produced the seeded data, plus the Story 9-8 E2E canary which exercises the stub renderer end-to-end.
- **§5.12 cadence — criterion 6 (load-bearing orchestrator):** the verdict engine is the gating surface for Epic 9 done-flip clause #11 (routing change or signed retro entry). Run MANDATORY-CR with reviewer `claude-sonnet-4-6`.

### Statistical math notes

- **Wilson score interval** at 95% confidence (`z = 1.96`) — formula from Wilson 1927; numerically stable for small `n` and extreme `p̂` (0 or 1). NOT the normal-approximation interval (which produces nonsensical bounds outside `[0, 1]` for small `n`). The denominator is `1 + z²/n` — not `1 + z²/(2n)`; the `2n` appears only inside the `±` numerator. Off-by-one on this is the most common implementation bug; tested explicitly in `test_report_stats.py::test_wilson_known_value_85_of_100`.

- **Bootstrap CI** with `numpy.random.default_rng(seed=42)` — 1000 resamples by default, `np.percentile` for the 2.5th and 97.5th percentile. Fixed seed makes the test golden-value-stable.

- **Pareto frontier dominance** uses the strict-weak-dominance definition: point `a` dominates point `b` iff `a.cost <= b.cost AND a.quality >= b.quality AND (a.cost < b.cost OR a.quality > b.quality)`. Ties on both axes → both retained (neither strictly dominates).

### File structure requirements

```text
benchmark/
├── __init__.py              # modified: extend __all__
├── report.py                # MODIFIED: refactored from stub to full renderer + CLI main()
├── stats.py                 # NEW (~120 lines): wilson_score_interval, bootstrap_ci, compute_pareto_frontier, ParetoPoint
├── verdict.py               # NEW (~80 lines): compute_verdict, VerdictLiteral, _default_per_task_thresholds()
└── reports/                 # PRE-EXISTING (Story 9-8) directory
    └── .gitignore           # PRE-EXISTING `*.md`
tests/unit/
├── test_report_stats.py     # NEW (≥9 tests)
├── test_report_pareto.py    # NEW (≥6 tests)
└── test_report_verdict.py   # NEW (≥5 tests)
tests/integration/
├── test_report_renderer.py  # NEW (≥6 tests)
└── test_report_cli.py       # NEW (≥5 tests)
```

### Testing requirements

- **Framework:** pytest + pytest-asyncio (already wired); fixtures from `tests/integration/test_benchmark_e2e_canary.py` may be reused (`_clean_state` pattern) — but the renderer doesn't touch Router state so `_clean_state` is overkill; use a per-test `tmp_path` for the db + `tmp_path / "reports"` for the output dir.
- **Coverage expectations:** ≥31 net tests (9 + 6 + 5 + 6 + 5). Acceptable to add trivial-invariant tests if a discrete property emerges during the dev walk.
- **Hermeticity:** no real API spend, no real Anthropic/Ollama dispatch. The renderer is pure-Python over a SQLite db; tests seed `benchmark_runs` + `benchmark_scores` rows via `record_benchmark_run` + `record_benchmark_score` (the Rule C writers), then invoke `render_report` and assert on the output Markdown.
- **Determinism:** bootstrap CI tests must use `random_seed=42` (the documented default) to make CI bounds reproducible.

### References

- `_bmad-output/planning-artifacts/epics.md` lines 3345–3355 (Story 9.9 spec) + 2926–2962 (inherited Story 7.4 AC text)
- `_bmad-output/implementation-artifacts/9-8-e2e-join-5-item-canary-corpus-runner-scorer-report.md` (Story 9-8 stub renderer this story upgrades)
- `_bmad-output/implementation-artifacts/9-7-scorer-objective-and-subjective-with-anchor-calibrated-auto-eval-and-cross-evaluator-agreement.md` (`cross_evaluator_alpha` row shape + Krippendorff α verdict thresholds — α ≥ 0.8 trusted / 0.6 ≤ α < 0.8 uncertain / α < 0.6 untrusted)
- `_bmad-output/implementation-artifacts/9-6-benchmark-runner-and-benchmark-runs-table-and-cost-confirmation-gate-and-cohort-key.md` (cohort_key 4-tuple contract)
- `benchmark/report.py` (Story 9-8 stub) — the upgrade target
- `benchmark/scorer_db.py` (`read_run_scores`, `read_run_runs`, `extra_json` shape conventions for `cross_evaluator_alpha`)
- `mailbot_api/router/policy.py` (PolicyTable structure — for verdict snippet shape matching)

### Review Findings

- [x] [Review][Decision] CR-F1 (HIGH) — APPLIED Option (a) per-cohort sub-subsections. `_render_pareto_section` and `_render_demote_promote_section` now nest an inner `for ck in cohort_keys` loop inside each task's outer loop. Each (task, cohort_key) cell computes its own Pareto frontier + verdict set; single-cohort runs render one block per task (no extra `#### cohort_key:` header — symmetry with existing per-task layout when only 1 cohort_key exists), multi-cohort runs render one `#### cohort_key: <ck>` sub-subsection per cohort. Regression test `test_cr_f1_pareto_renders_per_cohort_subsections` seeds 2 cohorts × 2 models and asserts both `#### cohort_key:` markers appear in Pareto section.
- [x] [Review][Patch] CR-F2 (MEDIUM) — APPLIED. `_latency_cost_stats` return tuple un-underscored to `(mean_latency, mean_cost, lat_upper, cost_upper)`; `_render_task_table`'s latency/cost summary header expanded to `| model | n_ok | mean_latency_ms [95% CI upper] | mean_cost_usd [95% CI upper] | excluded (outcome≠ok) |` and rows render `f"{mean_latency:.0f} [{lat_upper:.0f}]"` + `f"{mean_cost:.6f} [{cost_upper:.6f}]"`. Bootstrap CI now surfaces to the report. [benchmark/report.py:155-196]
- [x] [Review][Patch] CR-F3 (MEDIUM) — APPLIED. `_render_pareto_section` now iterates `eligible` (all sample-gate-passing points) instead of `frontier`. `frontier_keys` set drives the `on_frontier` cell value, so dominated points render with `on_frontier = "no"` per AC-5 spec. Regression test `test_cr_f3_pareto_table_renders_dominated_rows_with_no` seeds a 3-point dataset where one model is dominated by both others and asserts ``` | no |``` appears.
- [x] [Review][Patch] CR-F4 (LOW) — APPLIED at both sites. `render_report`: `if thresholds_override is None: thresholds = _default_per_task_thresholds(); else: thresholds = thresholds_override`. `compute_verdict` in `benchmark/verdict.py` mirrors. Regression test `test_cr_f4_empty_dict_thresholds_override_is_honored` passes `thresholds_override={}` and asserts qwen (quality 0.80) is NOT PROMOTE-needed since the empty map collapses every task threshold to 0.0.
- [x] [Review][Patch] CR-F5 (LOW) — APPLIED. `_render_cross_cohort_drift_section` disclaimer rewritten to reflect post-CR-F1 cohort-clean verdicts: `"Each verdict in the DEMOTE/PROMOTE section above is scoped to a single cohort_key; this section is informational only and lets you spot drift across cohort boundaries."`
- [x] [Review][Defer] CR-F6 (LOW) — DEFERRED (per pre-review §3 [S3] pre-existing documented acceptance). Inline comment added at `_WILSON_METRICS` distinguishing proper-proportion members (accuracy / precision_macro / recall_macro / ok_rate) from derived-metric members (f1_macro / f1_extraction_*) with a note that the CI on derived metrics is approximate and that a future story may replace with bootstrap CIs. Documented in code, not removed. [benchmark/report.py:73-92]

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — dev model for Phase 2.3 inline walk; claude-sonnet-4-6 — code-review subagent at Phase 2.4 per autonomous-story-run different-model contract.

### Debug Log

- Wilson CI FP-noise edge case: `wilson_score_interval(successes=0, trials=100)` returned `lower ≈ 3.5e-18` instead of exactly 0.0 because the `radius` and `center` terms don't cancel cleanly at the boundary. Snap-to-zero (and snap-to-one for `successes == trials`) added at lines 117-121 of `benchmark/stats.py`.
- `apply_pending_migrations` is synchronous in `mailbot_api/db/migrations_runner.py` (not a coroutine). Initial test fixture wrote `asyncio.run(apply_pending_migrations(...))` and hit `ValueError: a coroutine was expected`. Fixed by removing the `asyncio.run` wrapper.
- UNIQUE(run_id, task_type, model, prompt_version, scorer_model, evaluator_role, metric_name) on `benchmark_scores` does NOT include `cohort_key`. Initial multi-cohort drift test used `(qwen, coarse_class, v1)` across two cohorts → the second INSERT replaced the first via `INSERT OR REPLACE`. Fixed by using `(v1, v2)` distinct prompt_versions per cohort.
- SQLite auto-creates an empty db file on first connect, so a "missing db file" CLI test would hit `OperationalError: no such table: benchmark_scores` instead of `FileNotFoundError`. Pre-empted by adding `Path(args.db_path).is_file()` check in `main()` returning exit code 2.

### Completion Notes List

- AC-1 (5 section headers + ordering + 2 conditional): satisfied via `_render_report_body` composing in order. Tested by `test_report_contains_all_5_section_headers_in_order`.
- AC-1.2 (CR-F3 path-traversal guard preserved verbatim): `_RUN_ID_SAFE_PATTERN` regex unchanged from Story 9-8. Tested by `test_render_report_rejects_unsafe_run_id`.
- AC-2 (sample-size gate `INSUFFICIENT DATA — n=<n>, gate=15`): tested by `test_insufficient_data_renders_for_low_n`.
- AC-2.3 (Pareto excludes n<15 BEFORE frontier computation): `eligible = [p for p in points if p.sample_count >= _SAMPLE_SIZE_GATE]` in `_render_pareto_section`. Tested by `test_pareto_section_shows_insufficient_points_when_below_threshold`.
- AC-3 (Wilson CI rendering with `[95% CI: <lower>–<upper>]`): tested by `test_wilson_ci_rendered_for_accuracy_metric`.
- AC-3.3 (Wilson edge cases: trials=0/successes=0/successes=trials): tested by `TestWilsonScoreInterval` (10 tests).
- AC-4 (bootstrap CI with `random_seed=42` default, outcome≠ok excluded): tested by `TestBootstrapCI` (8 tests) + `test_demote_promote_section_lists_each_model` (excluded count surfaced via `_latency_cost_stats`).
- AC-4.3 (CR-F2): bootstrap CI upper bound surfaced in per-task latency/cost summary table.
- AC-5 (Pareto strict-weak dominance, INSUFFICIENT POINTS edge): tested by `TestComputeParetoFrontier` (8 tests) + integration via `test_pareto_frontier_drops_dominated_qwen` + CR regression `test_cr_f3_pareto_table_renders_dominated_rows_with_no`.
- AC-6 (5-value VerdictLiteral + Epic 7 thresholds + copy-pasteable yaml snippet): tested by `TestComputeVerdict` (8 tests) + `test_promote_needed_verdict_renders_policy_yaml_snippet`.
- AC-7 (cohort_key primary slice — CR-F1 patch): per-cohort sub-subsections in Pareto + DEMOTE/PROMOTE sections enforce the AC-7 cohort boundary. Tested by `test_cr_f1_pareto_renders_per_cohort_subsections`. Single-cohort runs render without the `#### cohort_key:` header (symmetry with prior layout); multi-cohort runs render one per cohort.
- AC-8 (Scorer calibration α verdict thresholds + ELIDED when absent): tested by `TestRenderReportScorerCalibrationSection` (4 tests).
- AC-9 (CLI with 4 flags + 3 exit codes + stdout output path): tested by `TestReportCLI` (7 tests).
- AC-10 (≥3 unit tests per pure-leaf helper + integration): 18 stats + 8 pareto + 8 verdict + 19 renderer + 7 CLI = **60 net tests**.
- AC-11 (criterion 6 fires → MANDATORY-CR sonnet-4-6): dispatched at Step 2.4; 6 findings (5 Patches + 1 Defer); 5/5 actionable Patches applied = **100% applied-rate**.
- CR-F1 HIGH cohort-clean verdict: applied per Option (a) — per-cohort sub-subsections (resolves AC-7 contract).
- CR-F2 MEDIUM bootstrap CI rendering: applied — `_latency_cost_stats` no longer discards the upper bounds; summary table headers extended.
- CR-F3 MEDIUM `on_frontier="no"` dead branch: applied — iterate `eligible` (not `frontier`); dominated points now visible with `no` value.
- CR-F4 LOW empty-dict `or` short-circuit: applied at both `render_report` and `compute_verdict` sites; explicit `if X is None` discriminator.
- CR-F5 LOW drift-section disclaimer: applied — rewritten to reflect post-CR-F1 cohort-clean verdicts.
- CR-F6 LOW Wilson on f1_macro: DEFERRED with code-doc comment at `_WILSON_METRICS` distinguishing proper-proportion members from derived-metric members. Pre-review §3 [S3] disposition preserved.

### File List

- `benchmark/stats.py` — NEW (~213 lines): `wilson_score_interval`, `bootstrap_ci`, `compute_pareto_frontier`, `ParetoPoint`, `_z_for_confidence` (Acklam approximation for non-95% confidence — currently unused but kept for forward-compat).
- `benchmark/verdict.py` — NEW (~128 lines): `compute_verdict`, `VerdictLiteral`, `_default_per_task_thresholds()`.
- `benchmark/report.py` — MODIFIED: refactored from Story 9-8 stub (~170 lines) to full renderer (~660 lines). New: `_format_metric_value_with_ci`, `_group_runs_by_model_task`, `_latency_cost_stats`, `_extract_pareto_points_for_task`, `_render_pareto_section`, `_render_demote_promote_section`, `_render_scorer_calibration_section`, `_render_cross_cohort_drift_section`, `_policy_yaml_snippet`, `_build_parser`, `main(argv)`. Preserved: `_RUN_ID_SAFE_PATTERN`, `_SAMPLE_SIZE_GATE`, `_INSUFFICIENT_DATA_FMT`, `_insufficient_data`. Public `render_report` signature extended with `thresholds_override: dict[str, float] | None = None`.
- `benchmark/__init__.py` — MODIFIED: extended `__all__` with 7 new exports (`ParetoPoint`, `VerdictLiteral`, `bootstrap_ci`, `compute_pareto_frontier`, `compute_verdict`, `wilson_score_interval`).
- `tests/unit/benchmark/test_report_stats.py` — NEW (18 tests).
- `tests/unit/benchmark/test_report_pareto.py` — NEW (8 tests).
- `tests/unit/benchmark/test_report_verdict.py` — NEW (8 tests).
- `tests/integration/test_report_renderer.py` — NEW (19 tests: 16 original + 3 CR regression for CR-F1/F3/F4).
- `tests/integration/test_report_cli.py` — NEW (7 tests).
- `_bmad-output/implementation-artifacts/9-9-...md` — NEW (this story file).
- `_bmad-output/implementation-artifacts/9-9-...pre-review.md` — NEW (Phase 2.3.5 pre-review audit).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED: flipped story 9-9 row backlog→in-progress (will flip to done at Phase 2.4.8 with truncated headline).

### Change Log

- 2026-06-28 — Story 9-9 shipped: full report renderer upgrade of Story 9-8 stub. Wilson CIs + bootstrap CIs + Pareto frontier + DEMOTE/PROMOTE verdict engine + sample-size gate + cohort_key primary slice + Scorer calibration section + Cross-cohort drift comparison. CR sonnet-4-6 5/5 Patches applied + 1 Defer. 4 gates green at 1601+2+3 (+60 net tests vs Story 9-8 baseline 1541+2+3).
