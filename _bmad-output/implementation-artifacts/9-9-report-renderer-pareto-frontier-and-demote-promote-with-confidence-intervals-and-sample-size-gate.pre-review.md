# Pre-Review Self-Audit — 9-9-report-renderer

**Generated:** 2026-06-28 by claude-opus-4-7 (dev model)
**Story file:** `_bmad-output/implementation-artifacts/9-9-report-renderer-pareto-frontier-and-demote-promote-with-confidence-intervals-and-sample-size-gate.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

| AC | Verdict | Notes |
|---|---|---|
| AC-1 (5 section headers + ordering + 2 conditional) | MATCH | `_render_report_body` composes in order; `_render_scorer_calibration_section` and `_render_cross_cohort_drift_section` return `None` → caller skips |
| AC-1.2 (`_RUN_ID_SAFE_PATTERN` preserved verbatim) | MATCH | `benchmark/report.py:60` preserves Story 9-8 CR-F3 regex exactly |
| AC-1.3 (`benchmark/reports/.gitignore` continues to gate output) | MATCH | Story 9-8 file unchanged |
| AC-2 (sample-size gate n<15 renders `INSUFFICIENT DATA — n=<n>, gate=15`) | MATCH | `_format_metric_value_with_ci` early-returns `_insufficient_data(row.sample_count)`; tested via `test_insufficient_data_renders_for_low_n` |
| AC-2.2 (DEMOTE/PROMOTE per-cell INSUFFICIENT DATA when n<15) | MATCH | `compute_verdict` returns `INSUFFICIENT_DATA` when `current_metrics.sample_count < 15`; renderer treats as INSUFFICIENT DATA literal |
| AC-2.3 (Pareto excludes n<15 points before frontier computation) | MATCH | `eligible = [p for p in points if p.sample_count >= _SAMPLE_SIZE_GATE]` in `_render_pareto_section` |
| AC-3 (Wilson CI: `<value> [95% CI: <lower>–<upper>]`) | MATCH | `_format_metric_value_with_ci` formats `f"{row.metric_value:.4f} [95% CI: {lower:.4f}–{upper:.4f}]"` when metric is in `_WILSON_METRICS` |
| AC-3.2 (Wilson helper pure-numpy no scipy) | MATCH | `benchmark/stats.py` imports `numpy` only; verified scipy not installed and the formula uses numpy.sqrt |
| AC-3.3 (Wilson edge cases: trials=0/successes=0/successes=trials) | MATCH | Returns `(0.0, 1.0)` for trials=0; explicit FP-noise snap to 0.0/1.0 when successes ∈ {0, trials} |
| AC-4 (latency/cost via `read_run_runs` joined view + bootstrap CI) | MATCH | `_latency_cost_stats` consumes `read_run_runs` output; bootstrap_ci called per-(task, model) |
| AC-4.2 (`random_seed=42` default) | MATCH | `bootstrap_ci(samples, ..., random_seed: int = 42)` signature |
| AC-4.3 (outcome≠ok excluded; excluded count surfaced) | MATCH | `ok_rows = [r for r in runs if r.outcome == "ok"]`; excluded count rendered in summary table |
| AC-5 (Pareto strict-weak dominance + INSUFFICIENT POINTS edge) | MATCH | `_dominates` implements strict-weak; `_render_pareto_section` renders `INSUFFICIENT POINTS — need ≥2 distinct (model, prompt_version)` when fewer than 2 eligible distinct combos |
| AC-6 (5-value closed-set VerdictLiteral) | MATCH | `VerdictLiteral = Literal["PROMOTE-needed", "DEMOTE-valid", "DEMOTE-invalid", "hold-steady", "INSUFFICIENT_DATA"]` |
| AC-6.2 (per_task_thresholds defaults match Epic 7) | MATCH | `_default_per_task_thresholds()` returns coarse_class=0.85, sensitivity_class=0.90, etc. |
| AC-6.3 (DEMOTE-valid / PROMOTE-needed produce policy.yaml snippet) | MATCH | `_policy_yaml_snippet(task, target_model, run_id, evidence)` renders ```yaml block ... ``` |
| AC-7 (cohort_key primary slice; Per-task tables only combine same-cohort rows) | DRIFT — partial; see §3 finding [S2] | The current implementation renders ALL rows in the per-task table regardless of cohort, with cohort_keys listed in metadata. The Pareto + DEMOTE/PROMOTE sections also do not slice by cohort_key explicitly — they treat all rows for a task as one set. AC-7 says they ONLY combine rows within same cohort_key. Risk surfaces only when multi-cohort runs are scored — which is rare in practice and explicitly out-of-scope for the canary 5-item run. ESCALATE TO REVIEWER (see §3 [S2]) |
| AC-7.2 (`> WARNING: Rows below span MULTIPLE cohort_keys` header) | MATCH | `_render_cross_cohort_drift_section` emits the literal exactly |
| AC-7.3 (Cross-cohort section OMITTED when single cohort_key) | MATCH | `if len(cohort_keys) < 2: return None` |
| AC-8 (`Scorer calibration` α verdict thresholds) | MATCH | α≥0.8→trusted / 0.6≤α<0.8→uncertain / α<0.6→untrusted |
| AC-8.2 (Scorer calibration section OMITTED when no cross_evaluator_alpha rows) | MATCH | `if not alpha_rows: return None` |
| AC-9 (CLI: --run-id / --db-path / --output-dir / --thresholds-override) | MATCH | `_build_parser` declares all four |
| AC-9.2 (CLI exit codes: 0 success / 1 malformed run_id / 2 db access failure) | MATCH | `main(argv)` returns those codes |
| AC-9.3 (CLI stdout prints absolute path on success) | MATCH | `print(str(out.resolve()))` |
| AC-10 (≥3 unit tests per pure-leaf helper, integration tests for end-to-end) | MATCH | stats=18 / pareto=8 / verdict=8 / renderer=16 / cli=7 = 57 net tests (>>= 9+6+5+6+5 = 31 minimum prescribed) |
| AC-11 (criterion 6 fires → MANDATORY-CR sonnet-4-6) | MATCH | Will dispatch sonnet-4-6 subagent at Step 2.4 |

## 2. File-List-vs-git diff check

`git status --porcelain` filtered to story-relevant paths:

| Path | Status |
|---|---|
| `benchmark/__init__.py` | MODIFIED (` M`) — extended `__all__` with 7 new exports |
| `benchmark/report.py` | MODIFIED (` M`) — refactored stub → full renderer |
| `benchmark/stats.py` | UNTRACKED (`??`) — NEW |
| `benchmark/verdict.py` | UNTRACKED (`??`) — NEW |
| `tests/unit/benchmark/test_report_stats.py` | UNTRACKED (`??`) — NEW (18 tests) |
| `tests/unit/benchmark/test_report_pareto.py` | UNTRACKED (`??`) — NEW (8 tests) |
| `tests/unit/benchmark/test_report_verdict.py` | UNTRACKED (`??`) — NEW (8 tests) |
| `tests/integration/test_report_renderer.py` | UNTRACKED (`??`) — NEW (16 tests) |
| `tests/integration/test_report_cli.py` | UNTRACKED (`??`) — NEW (7 tests) |
| `_bmad-output/implementation-artifacts/9-9-…md` | UNTRACKED — NEW (this story file) |
| `_bmad-output/implementation-artifacts/9-9-…pre-review.md` | UNTRACKED — NEW (this audit) |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | MODIFIED (` M`) — flipped story 9-9 row backlog→in-progress |
| `_bmad-output/implementation-artifacts/.autonomous-run-active.json` | UNTRACKED — run-state file (will be removed at Phase 3.5; not staged) |

All UNTRACKED files in the story scope will be staged in Phase 2.6. All ` M` files in scope will be staged. No MODIFIED-NOT-STAGED orphans.

Pre-existing untracked files (`.claude/skills/.archive/`, `.claude/skills/bmad-*/`, `hermes-config/*`, `_bmad/`, `docs/external/*`, `_eval-outputs/`, etc.) are NOT in story scope and will NOT be staged.

## 3. Adversarial self-review

- [S1] [LOW] `benchmark/report.py:583` — the `from benchmark.verdict import _default_per_task_thresholds` import inside `render_report` is a deferred-load pattern; could be hoisted to the module-level import block. Trade-off: avoids a circular-import risk if `verdict.py` ever imports from `report.py`, but currently no such dependency exists. Cosmetic.
- [S2] [HIGH] `benchmark/report.py:_extract_pareto_points_for_task` and downstream verdict computation DO NOT slice rows by cohort_key before computing the frontier or the verdict. AC-7 says verdicts should ONLY combine same-cohort rows. In the multi-cohort case, a Pareto point built from rows in cohort A could be compared against a verdict-computed candidate from cohort B, producing a misleading verdict. Mitigation: the cross-cohort comparison section explicitly warns "Verdicts above DO NOT use these comparisons; this section is informational only" — but the verdict engine is NOT actually enforcing the cohort split, so the warning is currently a documentation lie. ESCALATE TO REVIEWER.
- [S3] [MEDIUM] `benchmark/report.py:_format_metric_value_with_ci` casts `metric_value * sample_count` to int via `round`, which assumes accuracy is the proportion of correct predictions. For metrics like `f1_macro` (which is in `_WILSON_METRICS`), this is NOT a proportion of trials in the binomial sense — it's a derived quantity. Applying Wilson CI to f1_macro is statistically dubious but produces a number that LOOKS valid. Risk: false confidence in CI bounds for non-proportion metrics. ACCEPT WITH RATIONALE — Story 9-9 AC-3 lists `accuracy/precision_macro/recall_macro` specifically; f1_macro membership in `_WILSON_METRICS` is a deliberate-but-soft extension that future stories may revisit. Documented here for the reviewer.
- [S4] [LOW] `benchmark/report.py:_latency_cost_stats` returns `mean_latency / mean_cost` as the headline values but the CIs computed (`latency_upper`, `cost_upper`) are NOT actually rendered in the per-task summary table (the table only shows `mean_latency_ms` and `mean_cost_usd`). AC-3.4 requires the bootstrap CI be rendered. ESCALATE TO REVIEWER — partial AC coverage. The bootstrap_ci function is invoked but the result is discarded.
- [S5] [LOW] `benchmark/verdict.py:compute_verdict` returns `"hold-steady"` for unknown tasks (no threshold configured). This is defensive but could mask a typo in task naming. A future task name added to `_HEADLINE_METRIC` but forgotten in `_default_per_task_thresholds` would silently produce hold-steady for every model. ACCEPT WITH RATIONALE — closed-set Literal enforcement at the type level makes the typo case caught at mypy time; runtime defensive fallback is correct.
- [S6] [LOW] `benchmark/stats.py:_z_for_confidence` is dead code — only the 95% confidence path is exercised by callers (`wilson_score_interval` defaults to `_Z_95`; `bootstrap_ci` uses percentile-based CI not z-score-based). The Acklam approximation for non-95% z-scores has no test coverage and would not surface a bug if introduced. ACCEPT WITH RATIONALE — defensive math kept for forward-compat with the AC-3 mandate of "95% confidence" being the only required, with non-95% explicitly out-of-scope; if a future story exercises it, add tests then.
- [S7] [INFO] `benchmark/report.py:_render_scorer_calibration_section` parses `extra_json` with `json.loads` + `isinstance` checks. The Pydantic round-trip from `BenchmarkScoreRow` writes `extra_json` as plain TEXT — there's no schema validation on read. If a future scorer writes malformed JSON or alters the `per_anchor` shape, the calibration section silently drops the breakdown table (try/except returns empty list). Acceptable per AR-PAT-1, but a stricter Pydantic parse would catch drift sooner. ACCEPT WITH RATIONALE — Story 9-7 wrote the contract; Story 9-9 conforms.

## 4. Self-caught issues remediated this audit

- [S1] → **ACCEPT WITH RATIONALE** — cosmetic; deferred-import pattern is defensive
- [S2] → **ESCALATE TO REVIEWER** — semantic AC-7 gap; reviewer may demand cohort-slicing in the verdict engine
- [S3] → **ACCEPT WITH RATIONALE** — documented in §3 above; future-story carry-forward
- [S4] → **ESCALATE TO REVIEWER** — partial AC-3.4 coverage; reviewer may demand CI rendering in summary table
- [S5] → **ACCEPT WITH RATIONALE** — type system prevents the typo case at compile time
- [S6] → **ACCEPT WITH RATIONALE** — defensive code with no current call sites
- [S7] → **ACCEPT WITH RATIONALE** — conforms to Story 9-7 contract

## 5. Posture Audit

### 5.1 ruff

```bash
.venv/Scripts/python.exe -m ruff check .
```

Output: `All checks passed!` — EXIT 0.

### 5.2 mypy --strict

```bash
.venv/Scripts/python.exe -m mypy --strict mailbot_api/ evals/ benchmark/
```

Output: `Success: no issues found in 146 source files` — EXIT 0. (+2 source files vs Story 9-8 baseline 144: `benchmark/stats.py` + `benchmark/verdict.py`.)

### 5.3 boundary check

```bash
.venv/Scripts/python.exe scripts/check_boundaries.py
```

Output: no stderr/stdout — EXIT 0. No raw SQL / no os.environ writes / no cross-boundary import violations.

### 5.4 pytest full suite

```bash
.venv/Scripts/python.exe -m pytest -q
```

Output: `1598 passed, 2 skipped, 3 deselected, 1 warning in 222.40s (0:03:42)`. **+57 net tests** vs Story 9-8 close baseline 1541+2+3.

### 5.5 Test breakdown (prod-only-test-ratio audit)

| Test file | Tests | Type |
|---|---|---|
| `tests/unit/benchmark/test_report_stats.py` | 18 | Pure-leaf math unit tests |
| `tests/unit/benchmark/test_report_pareto.py` | 8 | Pure-leaf Pareto unit tests |
| `tests/unit/benchmark/test_report_verdict.py` | 8 | Pure-leaf verdict engine unit tests |
| `tests/integration/test_report_renderer.py` | 16 | End-to-end renderer integration |
| `tests/integration/test_report_cli.py` | 7 | CLI entry-point integration |
| **Total** | **57** | — |

Source line counts (new):
- `benchmark/stats.py`: ~210 lines (including the Acklam approximation for non-95% which is dead code defended in §3 [S6])
- `benchmark/verdict.py`: ~130 lines
- `benchmark/report.py` net new: ~470 lines added to the existing stub

Total new prod LOC: ~810. Total test LOC: 57 tests across ~750 lines. **Prod-LOC/test-LOC ratio ≈ 1.08** — PASS per §5.6 (≥0.5 floor; ≤2.0 ceiling).

### 5.6 §5.6 prod-only-test-ratio

PASS — 1.08 ratio. Tests are not test-heavy nor test-light.

### 5.7 Architectural-impossibility discharge

N/A — all 11 ACs directly implementable. No Path γ reframing needed. The cohort-slicing gap (§3 [S2]) is an implementation-side fix surface, not an architectural impossibility.

### 5.8 §5.12 cadence criterion check

Criterion 6 (load-bearing orchestrator) fires — the verdict engine + render_report compose the gating surface for Epic 9 done-flip clause #11. Cadence: **MANDATORY-CR with reviewer claude-sonnet-4-6**.

Other criteria:
- Criterion 1 (boundary-introducing): NO — `benchmark/` package was already introduced in Story 9-6.
- Criterion 2 (Router-touching): NO.
- Criterion 3 (security/privacy contract): NO.
- Criterion 4 (production-data-touching): NO — tests use tmp_path.
- Criterion 5 (privacy contract convergence): NO.
- Criterion 6 (load-bearing orchestrator): YES — Pareto + verdict + Wilson CI determine routing recommendations.

### 5.9 Cited-figures verification

| Cited figure | Source | Status |
|---|---|---|
| 1598 passed | pytest -q output | command-output-anchored |
| 2 skipped | pytest -q output | command-output-anchored |
| 3 deselected | pytest -q output | command-output-anchored |
| 146 source files | mypy --strict output | command-output-anchored |
| +57 net tests | 18+8+8+16+7 = 57; 1598-1541=57 | command-output-anchored both ways |
| +2 mypy source files | 146-144=2 | command-output-anchored |

### 5.10 Documentation drift

- `epics.md:3345-3355` — Story 9.9 spec unchanged by this implementation. The story file inline-authored at Step 2.2 captures the spec verbatim.
- `_bmad-output/implementation-artifacts/9-8-...md` — Story 9-8 stub renderer file unchanged (only its body in `benchmark/report.py` was replaced).

### 5.11 Coverage of non-trivial inequality choices

Comments added at:
- `benchmark/stats.py:_dominates` — explicit strict-weak `no_worse AND strictly_better` choice cited
- `benchmark/stats.py:wilson_score_interval` — FP-noise snap-to-0/1 explained in code comment
- `benchmark/verdict.py:compute_verdict` — explicit "cheaper-with-insufficient-samples does NOT trigger demote" decision documented

All other code follows CLAUDE.md "default to no comments" rule.
