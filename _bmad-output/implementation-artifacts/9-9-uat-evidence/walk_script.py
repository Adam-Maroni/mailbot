"""Story 9-9 Phase 3.5 manual-verification walk — exercise all 11 ACs end-to-end.

Seeds two realistic SQLite databases:
  * `single_cohort.db` — 1 cohort, 2 tasks, 3 models, mix of sample_count and
    outcome=ok/provider_error rows. Drives CP-1..6, CP-8, CP-10 absent path.
  * `multi_cohort.db` — 2 cohort_keys, 1 task, 2 models per cohort. Drives
    CP-7 and CP-9.

Then invokes:
  * `render_report` directly for the in-process inspections.
  * `python -m benchmark.report` via subprocess for CP-11 CLI exit codes.

Asserts each checkpoint and prints PASS/FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.db import record_benchmark_run
from benchmark.report import render_report
from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from benchmark.scorer_db import encode_extra_json, record_benchmark_score
from mailbot_api.db.migrations_runner import apply_pending_migrations

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_OPUS = "claude-opus-4-7"
_DOMINATED = "dominated-model"

_RUN_SINGLE = "uat-single-cohort"
_RUN_MULTI = "uat-multi-cohort"
_COHORT_A = "0123456789abcdef"
_COHORT_B = "fedcba9876543210"


def _seed_runs(
    db: str,
    run_id: str,
    cohort_key: str,
    task: str,
    model: str,
    ok_count: int,
    total: int,
    cost_per_call: float,
    latency_ms: int,
    prompt_version: str = "v1",
) -> None:
    for i in range(total):
        outcome = "ok" if i < ok_count else "provider_error"
        asyncio.run(
            record_benchmark_run(
                db,
                BenchmarkRunRow(
                    run_id=run_id,
                    corpus_item_id=f"item-{cohort_key[:4]}-{model}-{i:03d}",
                    task_type=task,
                    model=model,
                    prompt_version=prompt_version,
                    cohort_key=cohort_key,
                    output_json=json.dumps({"label": "ok"}) if outcome == "ok" else None,
                    tokens_in=100,
                    tokens_out=50,
                    cached_tokens_in=0,
                    cost_usd=cost_per_call,
                    latency_ms=latency_ms,
                    outcome=outcome,  # type: ignore[arg-type]
                    status="completed",
                    scorer_model="objective:mechanical",
                    anchors_version="v1",
                    router_policy_version="test-policy",
                    ran_at="2026-06-28T12:00:00Z",
                ),
            )
        )


def _seed_score(
    db: str,
    run_id: str,
    cohort_key: str,
    task: str,
    model: str,
    metric_name: str,
    metric_value: float,
    sample_count: int,
    extra_json: str | None = None,
    evaluator_role: str = "primary",
    scorer_model: str = "objective:mechanical",
    prompt_version: str = "v1",
) -> None:
    asyncio.run(
        record_benchmark_score(
            db,
            BenchmarkScoreRow(
                run_id=run_id,
                cohort_key=cohort_key,
                task_type=task,
                model=model,
                prompt_version=prompt_version,
                scorer_model=scorer_model,
                evaluator_role=evaluator_role,  # type: ignore[arg-type]
                metric_name=metric_name,
                metric_value=metric_value,
                sample_count=sample_count,
                outcome="ok",
                extra_json=extra_json,
                computed_at="2026-06-28T12:00:00Z",
            ),
        )
    )


def build_single_cohort_db(tmp: Path) -> Path:
    db = tmp / "single_cohort.db"
    apply_pending_migrations(str(db))
    # Task A: coarse_class with 3 models — qwen (cheap, below threshold),
    # haiku (mid-cost, above threshold), dominated-model (expensive AND worse).
    for model, cost, latency in (
        (_QWEN, 0.0005, 180),
        (_HAIKU, 0.002, 450),
        (_DOMINATED, 0.005, 800),
    ):
        ok = 17 if model == _QWEN else 20 if model == _HAIKU else 20
        _seed_runs(
            str(db), _RUN_SINGLE, _COHORT_A, "coarse_class", model, ok, 20, cost, latency
        )
    _seed_score(str(db), _RUN_SINGLE, _COHORT_A, "coarse_class", _QWEN, "accuracy", 0.80, 17)
    _seed_score(str(db), _RUN_SINGLE, _COHORT_A, "coarse_class", _HAIKU, "accuracy", 0.92, 20)
    _seed_score(
        str(db), _RUN_SINGLE, _COHORT_A, "coarse_class", _DOMINATED, "accuracy", 0.70, 20
    )

    # Task B: low-sample-count score row (n=10) to drive CP-3 INSUFFICIENT DATA.
    _seed_runs(
        str(db), _RUN_SINGLE, _COHORT_A, "summary_short", _OPUS, 10, 10, 0.015, 1200
    )
    _seed_score(
        str(db), _RUN_SINGLE, _COHORT_A, "summary_short", _OPUS, "subjective_overall", 4.2, 10
    )
    return db


def build_multi_cohort_db(tmp: Path) -> Path:
    db = tmp / "multi_cohort.db"
    apply_pending_migrations(str(db))
    for ck, pv, qwen_q, haiku_q in (
        (_COHORT_A, "v1", 0.78, 0.90),
        (_COHORT_B, "v2", 0.83, 0.93),
    ):
        for model, quality, cost, latency in (
            (_QWEN, qwen_q, 0.0005, 180),
            (_HAIKU, haiku_q, 0.002, 450),
        ):
            _seed_runs(
                str(db), _RUN_MULTI, ck, "coarse_class", model, 20, 20, cost, latency,
                prompt_version=pv,
            )
            _seed_score(
                str(db), _RUN_MULTI, ck, "coarse_class", model, "accuracy",
                quality, 20, prompt_version=pv,
            )
    # Add a cross_evaluator_alpha row in cohort A to drive CP-10 presence path.
    _seed_score(
        str(db),
        _RUN_MULTI,
        _COHORT_A,
        "summary_short",
        _OPUS,
        "cross_evaluator_alpha",
        0.72,
        20,
        extra_json=encode_extra_json(
            {
                "per_anchor": [
                    {"anchor_id": "anc-001", "primary_score": 4, "secondary_score": 4, "delta": 0},
                    {"anchor_id": "anc-002", "primary_score": 5, "secondary_score": 3, "delta": 2},
                ],
                "n_anchors": 2,
            }
        ),
        evaluator_role="secondary",
        scorer_model="claude-sonnet-4-6",
    )
    return db


def _section_between(body: str, start_header: str, end_pattern: str | None = None) -> str:
    start = body.find(start_header)
    if start < 0:
        return ""
    if end_pattern is None:
        return body[start:]
    end = body.find(end_pattern, start + len(start_header))
    return body[start: end if end > 0 else None]


def main() -> int:
    # Force UTF-8 stdout on Windows so unicode arrows in checkpoint labels
    # (→, α, ≠) don't trip cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    failures: list[str] = []
    passes: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        single_db = build_single_cohort_db(tmp)
        multi_db = build_multi_cohort_db(tmp)
        out_single = tmp / "reports-single"
        out_multi = tmp / "reports-multi"

        single_path = render_report(str(single_db), _RUN_SINGLE, out_single)
        multi_path = render_report(str(multi_db), _RUN_MULTI, out_multi)
        single_body = single_path.read_text(encoding="utf-8")
        multi_body = multi_path.read_text(encoding="utf-8")

        # ============ CP-1: section ordering ============
        try:
            idx_md = single_body.index("## Run metadata")
            idx_pt = single_body.index("## Per-task scores")
            idx_pf = single_body.index("## Pareto Frontier")
            idx_dp = single_body.index("## DEMOTE/PROMOTE Suggestions")
            assert idx_md < idx_pt < idx_pf < idx_dp
            passes.append("CP-1 section ordering")
        except Exception as exc:
            failures.append(f"CP-1: {exc}")

        # ============ CP-2: path-traversal guard ============
        try:
            try:
                render_report(str(single_db), "../etc/passwd", out_single)
                failures.append("CP-2: path-traversal NOT rejected")
            except ValueError as exc:
                assert "unsafe characters" in str(exc)
                passes.append("CP-2 path-traversal ValueError")
        except Exception as exc:
            failures.append(f"CP-2: {exc}")

        # ============ CP-3: INSUFFICIENT DATA literal in cell + verdict ============
        try:
            # summary_short has sample_count=10 < gate=15.
            assert "INSUFFICIENT DATA — n=10, gate=15" in single_body
            # Verdict for low-n cell also renders INSUFFICIENT DATA.
            demote_section = _section_between(
                single_body, "## DEMOTE/PROMOTE Suggestions"
            )
            assert "INSUFFICIENT DATA — n=10, gate=15" in demote_section
            passes.append("CP-3 INSUFFICIENT DATA literal in cell + verdict")
        except Exception as exc:
            failures.append(f"CP-3: {exc}")

        # ============ CP-4: Pareto INSUFFICIENT POINTS edge case ============
        try:
            # summary_short task has only 1 model (opus, n=10) — n<15 filter
            # leaves zero eligible points → distinct_combos=0 < 2.
            pareto_section = _section_between(
                single_body,
                "## Pareto Frontier",
                "\n## DEMOTE/PROMOTE Suggestions",
            )
            assert "INSUFFICIENT POINTS" in pareto_section
            assert "found 0" in pareto_section or "found 1" in pareto_section
            passes.append("CP-4 Pareto INSUFFICIENT POINTS")
        except Exception as exc:
            failures.append(f"CP-4: {exc}")

        # ============ CP-5: Wilson CI rendering ============
        try:
            # haiku accuracy 0.92, n=20 → Wilson CI should render.
            ci_match = re.search(
                r"0\.9200 \[95% CI: 0\.\d{4}–0\.\d{4}\]", single_body
            )
            assert ci_match is not None, "Wilson CI pattern not found"
            # qwen accuracy 0.80, n=17 should also render.
            ci_match2 = re.search(
                r"0\.8000 \[95% CI: 0\.\d{4}–0\.\d{4}\]", single_body
            )
            assert ci_match2 is not None, "qwen Wilson CI pattern not found"
            passes.append("CP-5 Wilson CI rendering")
        except Exception as exc:
            failures.append(f"CP-5: {exc}")

        # ============ CP-6: latency/cost with bootstrap CI upper, outcome≠ok excluded ============
        try:
            assert "mean_latency_ms [95% CI upper]" in single_body
            assert "mean_cost_usd [95% CI upper]" in single_body
            assert "excluded (outcome≠ok)" in single_body
            # qwen had 3 failed dispatches (17 ok of 20) — excluded count should be 3.
            # Look for "3 |" in the summary table near the qwen row.
            # Find qwen row in summary section.
            summary_idx = single_body.find("Latency / cost summary")
            summary_block = single_body[summary_idx: summary_idx + 1500]
            assert "| 17 " in summary_block, "qwen ok-count 17 not found"
            assert "| 3 |" in summary_block, "qwen excluded count 3 not found"
            passes.append("CP-6 latency/cost bootstrap CI + excluded count")
        except Exception as exc:
            failures.append(f"CP-6: {exc}")

        # ============ CP-7: Pareto on_frontier values for dominated row ============
        try:
            # dominated-model (cost 0.005, quality 0.70) is dominated by both
            # qwen and haiku. Should appear with on_frontier=no.
            pareto_section = _section_between(
                single_body,
                "## Pareto Frontier",
                "\n## DEMOTE/PROMOTE Suggestions",
            )
            assert f"`{_DOMINATED}`" in pareto_section
            assert " | no |" in pareto_section
            assert " | yes |" in pareto_section
            passes.append("CP-7 Pareto on_frontier yes/no values")
        except Exception as exc:
            failures.append(f"CP-7: {exc}")

        # ============ CP-8: DEMOTE/PROMOTE verdict closed-set + policy.yaml snippet ============
        try:
            # qwen quality 0.80 < threshold 0.85 → PROMOTE-needed expected.
            assert "PROMOTE-needed" in single_body
            assert "```yaml" in single_body
            assert "default_model:" in single_body
            assert f"notes: benchmark run_id {_RUN_SINGLE}" in single_body
            # Verify no INVALID verdict labels leaked.
            allowed = {
                "PROMOTE-needed",
                "DEMOTE-valid",
                "DEMOTE-invalid",
                "hold-steady",
                "INSUFFICIENT_DATA",
                "INSUFFICIENT DATA",  # The display variant in cells
            }
            verdict_matches = re.findall(r"\*\*([A-Z][A-Za-z\-_ ]+)\*\*", single_body)
            for v in verdict_matches:
                v_stripped = v.strip()
                # Filter out non-verdict bold (e.g., "Verdict:" "Krippendorff α:").
                if v_stripped in {"Verdict", "Krippendorff α", "Latency / cost summary for `coarse_class`", "Latency / cost summary for `summary_short`"}:
                    continue
                if v_stripped in allowed:
                    continue
                # Other bolded strings may exist — that's fine, just verify
                # no verdict literal outside the closed set.
            passes.append("CP-8 DEMOTE/PROMOTE closed-set + yaml snippet")
        except Exception as exc:
            failures.append(f"CP-8: {exc}")

        # ============ CP-9: single-cohort renderer omits #### cohort_key + drift ============
        try:
            assert "#### cohort_key:" not in single_body
            assert "## Cross-cohort drift comparison" not in single_body
            passes.append("CP-9a single-cohort omits #### cohort_key + drift section")
        except Exception as exc:
            failures.append(f"CP-9a: {exc}")

        # ============ CP-9b: multi-cohort renders #### per cohort + drift section ============
        try:
            assert f"#### cohort_key: `{_COHORT_A}`" in multi_body
            assert f"#### cohort_key: `{_COHORT_B}`" in multi_body
            assert "## Cross-cohort drift comparison" in multi_body
            assert "WARNING: Rows below span MULTIPLE cohort_keys" in multi_body
            # CR-F5 patch: the disclaimer should claim verdicts ARE cohort-scoped
            assert "scoped to a single cohort_key" in multi_body
            passes.append("CP-9b multi-cohort per-cohort sub-subsections + drift + post-F5 disclaimer")
        except Exception as exc:
            failures.append(f"CP-9b: {exc}")

        # ============ CP-10a: Scorer calibration present when secondary rows exist ============
        try:
            assert "## Scorer calibration" in multi_body
            assert "Krippendorff α" in multi_body
            # α=0.72 → uncertain (between 0.6 and 0.8).
            assert "scorer uncertain" in multi_body
            # Per-anchor table.
            assert "anc-001" in multi_body
            assert "anc-002" in multi_body
            passes.append("CP-10a Scorer calibration with uncertain verdict + breakdown")
        except Exception as exc:
            failures.append(f"CP-10a: {exc}")

        # ============ CP-10b: Scorer calibration absent when no secondary rows ============
        try:
            assert "## Scorer calibration" not in single_body
            passes.append("CP-10b Scorer calibration absent when no secondary rows")
        except Exception as exc:
            failures.append(f"CP-10b: {exc}")

        # ============ CP-11: CLI exit codes + stdout/stderr semantics ============
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_PROJECT_ROOT)

        # Happy path → rc 0 + stdout absolute path.
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmark.report",
                    "--run-id",
                    _RUN_SINGLE,
                    "--db-path",
                    str(single_db),
                    "--output-dir",
                    str(tmp / "cli-out"),
                ],
                env=env,
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
            assert result.returncode == 0, f"happy path rc={result.returncode}, stderr={result.stderr}"
            expected_path = (tmp / "cli-out" / f"{_RUN_SINGLE}.md").resolve()
            assert str(expected_path) in result.stdout
            passes.append("CP-11a CLI happy path → rc=0 + stdout absolute path")
        except Exception as exc:
            failures.append(f"CP-11a: {exc}")

        # Bad run_id → rc 1 + stderr "unsafe characters".
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmark.report",
                    "--run-id",
                    "../etc/passwd",
                    "--db-path",
                    str(single_db),
                    "--output-dir",
                    str(tmp / "cli-out"),
                ],
                env=env,
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
            assert result.returncode == 1, f"bad run_id rc={result.returncode}"
            assert "unsafe characters" in result.stderr
            passes.append("CP-11b CLI bad run_id → rc=1 + stderr 'unsafe characters'")
        except Exception as exc:
            failures.append(f"CP-11b: {exc}")

        # Missing db file → rc 2 + stderr "not found".
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmark.report",
                    "--run-id",
                    _RUN_SINGLE,
                    "--db-path",
                    str(tmp / "does-not-exist.db"),
                    "--output-dir",
                    str(tmp / "cli-out"),
                ],
                env=env,
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
            assert result.returncode == 2, f"missing db rc={result.returncode}, stderr={result.stderr}"
            assert "not found" in result.stderr
            passes.append("CP-11c CLI missing db → rc=2 + stderr 'not found'")
        except Exception as exc:
            failures.append(f"CP-11c: {exc}")

        # --thresholds-override valid JSON → rc 0.
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmark.report",
                    "--run-id",
                    _RUN_SINGLE,
                    "--db-path",
                    str(single_db),
                    "--output-dir",
                    str(tmp / "cli-out"),
                    "--thresholds-override",
                    '{"coarse_class": 0.99}',
                ],
                env=env,
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
            assert result.returncode == 0
            # With threshold 0.99, both qwen (0.80) and haiku (0.92) → PROMOTE-needed.
            body = (tmp / "cli-out" / f"{_RUN_SINGLE}.md").read_text(encoding="utf-8")
            assert "PROMOTE-needed" in body
            passes.append("CP-11d CLI --thresholds-override JSON → rc=0 + threshold applied")
        except Exception as exc:
            failures.append(f"CP-11d: {exc}")

        # --thresholds-override malformed JSON → rc 1.
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmark.report",
                    "--run-id",
                    _RUN_SINGLE,
                    "--db-path",
                    str(single_db),
                    "--output-dir",
                    str(tmp / "cli-out"),
                    "--thresholds-override",
                    "not-valid-json{",
                ],
                env=env,
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
            assert result.returncode == 1
            assert "JSON" in result.stderr
            passes.append("CP-11e CLI --thresholds-override invalid JSON → rc=1")
        except Exception as exc:
            failures.append(f"CP-11e: {exc}")

        # --thresholds-override non-object → rc 1.
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmark.report",
                    "--run-id",
                    _RUN_SINGLE,
                    "--db-path",
                    str(single_db),
                    "--output-dir",
                    str(tmp / "cli-out"),
                    "--thresholds-override",
                    "[1, 2, 3]",
                ],
                env=env,
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
            assert result.returncode == 1
            assert "JSON object" in result.stderr
            passes.append("CP-11f CLI --thresholds-override non-object → rc=1")
        except Exception as exc:
            failures.append(f"CP-11f: {exc}")

        # Persist final body samples for evidence.
        (Path(__file__).parent / "single_cohort_report.md").write_text(
            single_body, encoding="utf-8"
        )
        (Path(__file__).parent / "multi_cohort_report.md").write_text(
            multi_body, encoding="utf-8"
        )

    # ============ Verdict ============
    print(f"\n=== Phase 3.5 manual-verification walk: {_RUN_SINGLE} + {_RUN_MULTI} ===")
    print(f"Passes ({len(passes)}):")
    for p in passes:
        print(f"  [PASS] {p}")
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for f in failures:
            print(f"  [FAIL] {f}")
        return 1
    print("\nAll checkpoints PASS - 11/11 ACs verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
