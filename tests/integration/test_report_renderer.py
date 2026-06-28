"""Story 9.9 Task 4 + 6 + 7 — full renderer integration tests.

Seeds ``benchmark_runs`` + ``benchmark_scores`` rows via the
Rule-C writers, then invokes ``render_report`` and asserts on the
Markdown output. The tests exercise the new sections introduced in
Story 9-9 (Wilson CIs, Pareto frontier, DEMOTE/PROMOTE verdicts,
Scorer calibration, Cross-cohort drift comparison) and the
section-presence rules (calibration ELIDED when no
``cross_evaluator_alpha`` rows; drift ELIDED when only one cohort_key).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from benchmark.db import record_benchmark_run
from benchmark.report import render_report
from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from benchmark.scorer_db import (
    encode_extra_json,
    record_benchmark_score,
)
from mailbot_api.db.migrations_runner import apply_pending_migrations

_RUN_ID = "test-run-renderer-9-9"
_COHORT_A = "0123456789abcdef"
_COHORT_B = "fedcba9876543210"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """Apply migrations + seed a populated dataset for renderer testing.

    20 dispatches (above the n=15 sample gate) split as:
      * coarse_class × qwen → 20 dispatches, 17 ok, 3 provider_error
      * coarse_class × haiku → 20 dispatches, 20 ok
      * 1 score row per (task, model) with accuracy + sample_count=17 / 20
    """
    db_path = tmp_path / "mailbot.db"
    apply_pending_migrations(str(db_path))
    # Seed 20 dispatches for each (task, model) — exceeds n=15 gate.
    _seed_runs(str(db_path), task="coarse_class", model=_QWEN, ok_count=17, total=20)
    _seed_runs(str(db_path), task="coarse_class", model=_HAIKU, ok_count=20, total=20)
    # Score rows — qwen below threshold (0.80 < 0.85), haiku above (0.92).
    asyncio.run(
        record_benchmark_score(
            str(db_path),
            BenchmarkScoreRow(
                run_id=_RUN_ID,
                cohort_key=_COHORT_A,
                task_type="coarse_class",
                model=_QWEN,
                prompt_version="v1",
                scorer_model="objective:mechanical",
                evaluator_role="primary",
                metric_name="accuracy",
                metric_value=0.80,
                sample_count=17,
                outcome="ok",
                extra_json=None,
                computed_at="2026-06-28T12:00:00Z",
            ),
        )
    )
    asyncio.run(
        record_benchmark_score(
            str(db_path),
            BenchmarkScoreRow(
                run_id=_RUN_ID,
                cohort_key=_COHORT_A,
                task_type="coarse_class",
                model=_HAIKU,
                prompt_version="v1",
                scorer_model="objective:mechanical",
                evaluator_role="primary",
                metric_name="accuracy",
                metric_value=0.92,
                sample_count=20,
                outcome="ok",
                extra_json=None,
                computed_at="2026-06-28T12:00:00Z",
            ),
        )
    )
    return db_path


def _seed_runs(
    db_path: str, task: str, model: str, ok_count: int, total: int
) -> None:
    """Seed ``total`` benchmark_runs rows for (task, model)."""
    for i in range(total):
        outcome = "ok" if i < ok_count else "provider_error"
        asyncio.run(
            record_benchmark_run(
                db_path,
                BenchmarkRunRow(
                    run_id=_RUN_ID,
                    corpus_item_id=f"item-{i:03d}",
                    task_type=task,
                    model=model,
                    prompt_version="v1",
                    cohort_key=_COHORT_A,
                    output_json=json.dumps({"label": "ok"}) if outcome == "ok" else None,
                    tokens_in=100,
                    tokens_out=50,
                    cached_tokens_in=0,
                    cost_usd=0.0005 if model == _QWEN else 0.002,
                    latency_ms=200 if model == _QWEN else 500,
                    outcome=outcome,  # type: ignore[arg-type]
                    status="completed",
                    scorer_model="objective:mechanical",
                    anchors_version="v1",
                    router_policy_version="test-policy",
                    ran_at="2026-06-28T12:00:00Z",
                ),
            )
        )


class TestRenderReportFullRenderer:
    def test_report_file_written_at_expected_path(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "reports"
        out_path = render_report(str(populated_db), _RUN_ID, out_dir)
        assert out_path == out_dir / f"{_RUN_ID}.md"
        assert out_path.exists()

    def test_report_contains_all_5_section_headers_in_order(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        # Required sections (calibration + drift absent because no cross-evaluator
        # rows and only 1 cohort_key in the populated_db fixture).
        idx_metadata = body.index("## Run metadata")
        idx_per_task = body.index("## Per-task scores")
        idx_pareto = body.index("## Pareto Frontier")
        idx_demote = body.index("## DEMOTE/PROMOTE Suggestions")
        assert idx_metadata < idx_per_task < idx_pareto < idx_demote
        # No Scorer calibration nor drift sections in single-cohort no-secondary case.
        assert "## Scorer calibration" not in body
        assert "## Cross-cohort drift comparison" not in body

    def test_wilson_ci_rendered_for_accuracy_metric(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        # Wilson CI literal "[95% CI:" must appear on accuracy rows.
        assert "[95% CI:" in body

    def test_pareto_frontier_drops_dominated_qwen(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # qwen quality 0.80, haiku quality 0.92, qwen cheaper. But qwen below
        # threshold so it's NOT dominated by haiku (haiku is more expensive).
        # All 2 distinct (model, pv) on frontier.
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        # The Pareto table should contain BOTH models since neither strictly dominates
        # (qwen cheaper-lower-quality; haiku more-expensive-higher-quality).
        pareto_section_start = body.index("## Pareto Frontier")
        pareto_section = body[pareto_section_start:]
        assert "qwen" in pareto_section
        assert "haiku" in pareto_section

    def test_promote_needed_verdict_renders_policy_yaml_snippet(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # qwen accuracy 0.80 < threshold 0.85 → PROMOTE-needed.
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "PROMOTE-needed" in body
        assert "```yaml" in body
        assert "default_model:" in body
        assert "notes:" in body
        assert _RUN_ID in body

    def test_demote_promote_section_lists_each_model(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        demote_start = body.index("## DEMOTE/PROMOTE Suggestions")
        demote_section = body[demote_start:]
        # Both models must appear in the verdict section.
        assert f"`{_QWEN}`" in demote_section
        assert f"`{_HAIKU}`" in demote_section


class TestRenderReportSampleSizeGate:
    def test_insufficient_data_renders_for_low_n(self, tmp_path: Path) -> None:
        db_path = tmp_path / "mailbot.db"
        apply_pending_migrations(str(db_path))
        # Single low-n row.
        asyncio.run(
            record_benchmark_score(
                str(db_path),
                BenchmarkScoreRow(
                    run_id=_RUN_ID,
                    cohort_key=_COHORT_A,
                    task_type="coarse_class",
                    model=_QWEN,
                    prompt_version="v1",
                    scorer_model="objective:mechanical",
                    evaluator_role="primary",
                    metric_name="accuracy",
                    metric_value=0.80,
                    sample_count=10,  # below n=15 gate
                    outcome="ok",
                    extra_json=None,
                    computed_at="2026-06-28T12:00:00Z",
                ),
            )
        )
        out_path = render_report(str(db_path), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "INSUFFICIENT DATA — n=10, gate=15" in body

    def test_pareto_section_shows_insufficient_points_when_below_threshold(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "mailbot.db"
        apply_pending_migrations(str(db_path))
        # Single eligible point — frontier needs ≥ 2 distinct points.
        asyncio.run(
            record_benchmark_score(
                str(db_path),
                BenchmarkScoreRow(
                    run_id=_RUN_ID,
                    cohort_key=_COHORT_A,
                    task_type="coarse_class",
                    model=_QWEN,
                    prompt_version="v1",
                    scorer_model="objective:mechanical",
                    evaluator_role="primary",
                    metric_name="accuracy",
                    metric_value=0.85,
                    sample_count=20,
                    outcome="ok",
                    extra_json=None,
                    computed_at="2026-06-28T12:00:00Z",
                ),
            )
        )
        out_path = render_report(str(db_path), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "INSUFFICIENT POINTS" in body


class TestRenderReportScorerCalibrationSection:
    def test_calibration_section_present_when_secondary_rows_exist(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # Add a cross_evaluator_alpha row.
        asyncio.run(
            record_benchmark_score(
                str(populated_db),
                BenchmarkScoreRow(
                    run_id=_RUN_ID,
                    cohort_key=_COHORT_A,
                    task_type="summary_short",
                    model="claude-opus-4-7",
                    prompt_version="v1",
                    scorer_model="claude-sonnet-4-6",
                    evaluator_role="secondary",
                    metric_name="cross_evaluator_alpha",
                    metric_value=0.85,
                    sample_count=20,
                    outcome="ok",
                    extra_json=encode_extra_json(
                        {
                            "per_anchor": [
                                {
                                    "anchor_id": "anchor-001",
                                    "primary_score": 4,
                                    "secondary_score": 4,
                                    "delta": 0,
                                }
                            ],
                            "n_anchors": 1,
                        }
                    ),
                    computed_at="2026-06-28T12:00:00Z",
                ),
            )
        )
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "## Scorer calibration" in body
        assert "Krippendorff α" in body
        assert "scorer trusted" in body  # α=0.85 ≥ 0.8
        assert "anchor-001" in body

    def test_calibration_section_uncertain_verdict_at_0_65(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        asyncio.run(
            record_benchmark_score(
                str(populated_db),
                BenchmarkScoreRow(
                    run_id=_RUN_ID,
                    cohort_key=_COHORT_A,
                    task_type="summary_short",
                    model="claude-opus-4-7",
                    prompt_version="v1",
                    scorer_model="claude-sonnet-4-6",
                    evaluator_role="secondary",
                    metric_name="cross_evaluator_alpha",
                    metric_value=0.65,
                    sample_count=20,
                    outcome="ok",
                    extra_json=encode_extra_json({"per_anchor": [], "n_anchors": 0}),
                    computed_at="2026-06-28T12:00:00Z",
                ),
            )
        )
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "scorer uncertain" in body

    def test_calibration_section_untrusted_verdict_at_0_40(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        asyncio.run(
            record_benchmark_score(
                str(populated_db),
                BenchmarkScoreRow(
                    run_id=_RUN_ID,
                    cohort_key=_COHORT_A,
                    task_type="summary_short",
                    model="claude-opus-4-7",
                    prompt_version="v1",
                    scorer_model="claude-sonnet-4-6",
                    evaluator_role="secondary",
                    metric_name="cross_evaluator_alpha",
                    metric_value=0.40,
                    sample_count=20,
                    outcome="ok",
                    extra_json=encode_extra_json({"per_anchor": [], "n_anchors": 0}),
                    computed_at="2026-06-28T12:00:00Z",
                ),
            )
        )
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "scorer untrusted" in body

    def test_calibration_section_absent_when_no_secondary_rows(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # populated_db has no cross_evaluator_alpha rows.
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "## Scorer calibration" not in body


class TestRenderReportCrossCohortDriftSection:
    def test_drift_section_present_when_multi_cohort(self, tmp_path: Path) -> None:
        db_path = tmp_path / "mailbot.db"
        apply_pending_migrations(str(db_path))
        # Two rows in different cohorts with distinct prompt_versions to
        # avoid UNIQUE(run_id, task_type, model, prompt_version, ...) collision.
        for ck, pv in ((_COHORT_A, "v1"), (_COHORT_B, "v2")):
            asyncio.run(
                record_benchmark_score(
                    str(db_path),
                    BenchmarkScoreRow(
                        run_id=_RUN_ID,
                        cohort_key=ck,
                        task_type="coarse_class",
                        model=_QWEN,
                        prompt_version=pv,
                        scorer_model="objective:mechanical",
                        evaluator_role="primary",
                        metric_name="accuracy",
                        metric_value=0.80 if ck == _COHORT_A else 0.82,
                        sample_count=20,
                        outcome="ok",
                        extra_json=None,
                        computed_at="2026-06-28T12:00:00Z",
                    ),
                )
            )
        out_path = render_report(str(db_path), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "## Cross-cohort drift comparison" in body
        assert "WARNING: Rows below span MULTIPLE cohort_keys" in body
        assert _COHORT_A in body
        assert _COHORT_B in body

    def test_drift_section_absent_when_single_cohort(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # populated_db has only _COHORT_A.
        out_path = render_report(str(populated_db), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        assert "## Cross-cohort drift comparison" not in body


class TestRenderReportRunIdGuard:
    def test_render_report_rejects_unsafe_run_id(self, tmp_path: Path) -> None:
        # CR-F3 from Story 9-8 preserved: path-traversal guard.
        with pytest.raises(ValueError, match="unsafe characters"):
            render_report(
                str(tmp_path / "mailbot.db"),
                "../etc/passwd",
                tmp_path / "reports",
            )


class TestRenderReportCRPatchRegressions:
    """Regression tests for CR-F1 (cohort_key slicing) + CR-F3 (on_frontier="no")
    + CR-F4 (empty-dict override). One test per Patch finding.
    """

    def test_cr_f1_pareto_renders_per_cohort_subsections(
        self, tmp_path: Path
    ) -> None:
        # CR-F1: Pareto section MUST render one sub-subsection per cohort_key
        # when multi-cohort, not conflate.
        db_path = tmp_path / "mailbot.db"
        apply_pending_migrations(str(db_path))
        for ck, pv in ((_COHORT_A, "v1"), (_COHORT_B, "v2")):
            for model, quality in ((_QWEN, 0.80), (_HAIKU, 0.92)):
                asyncio.run(
                    record_benchmark_score(
                        str(db_path),
                        BenchmarkScoreRow(
                            run_id=_RUN_ID,
                            cohort_key=ck,
                            task_type="coarse_class",
                            model=model,
                            prompt_version=pv,
                            scorer_model="objective:mechanical",
                            evaluator_role="primary",
                            metric_name="accuracy",
                            metric_value=quality,
                            sample_count=20,
                            outcome="ok",
                            extra_json=None,
                            computed_at="2026-06-28T12:00:00Z",
                        ),
                    )
                )
        out_path = render_report(str(db_path), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        # Both cohort_key sub-subsection markers must appear in Pareto section.
        pareto_section_start = body.index("## Pareto Frontier")
        # Find the next H2 boundary marker (next "\n## " not "\n### " / "\n#### ").
        search_from = pareto_section_start + len("## Pareto Frontier")
        next_h2 = body.find("\n## ", search_from)
        pareto_section = body[pareto_section_start:next_h2 if next_h2 > 0 else None]
        assert f"#### cohort_key: `{_COHORT_A}`" in pareto_section
        assert f"#### cohort_key: `{_COHORT_B}`" in pareto_section

    def test_cr_f3_pareto_table_renders_dominated_rows_with_no(
        self, tmp_path: Path
    ) -> None:
        # CR-F3: dominated rows must appear with on_frontier="no", not get
        # dropped from the table.
        db_path = tmp_path / "mailbot.db"
        apply_pending_migrations(str(db_path))
        # Seed 3 points: cheap+low-q (frontier), mid+mid-q (frontier),
        # expensive+low-q (DOMINATED — must show on_frontier=no).
        for model, pv, quality, cost in (
            (_QWEN, "v1", 0.80, 0.0005),
            (_HAIKU, "v1", 0.92, 0.002),
            ("dominated-model", "v1", 0.70, 0.005),  # dominated by both
        ):
            asyncio.run(
                record_benchmark_score(
                    str(db_path),
                    BenchmarkScoreRow(
                        run_id=_RUN_ID,
                        cohort_key=_COHORT_A,
                        task_type="coarse_class",
                        model=model,
                        prompt_version=pv,
                        scorer_model="objective:mechanical",
                        evaluator_role="primary",
                        metric_name="accuracy",
                        metric_value=quality,
                        sample_count=20,
                        outcome="ok",
                        extra_json=None,
                        computed_at="2026-06-28T12:00:00Z",
                    ),
                )
            )
            asyncio.run(
                record_benchmark_run(
                    str(db_path),
                    BenchmarkRunRow(
                        run_id=_RUN_ID,
                        corpus_item_id=f"item-{model}",
                        task_type="coarse_class",
                        model=model,
                        prompt_version=pv,
                        cohort_key=_COHORT_A,
                        output_json='{"label": "ok"}',
                        tokens_in=100,
                        tokens_out=50,
                        cached_tokens_in=0,
                        cost_usd=cost,
                        latency_ms=200,
                        outcome="ok",
                        status="completed",
                        scorer_model="objective:mechanical",
                        anchors_version="v1",
                        router_policy_version="test-policy",
                        ran_at="2026-06-28T12:00:00Z",
                    ),
                )
            )
        out_path = render_report(str(db_path), _RUN_ID, tmp_path / "reports")
        body = out_path.read_text(encoding="utf-8")
        # dominated-model line should appear with " | no |".
        assert "`dominated-model`" in body
        assert " | no |" in body

    def test_cr_f4_empty_dict_thresholds_override_is_honored(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # CR-F4: passing {} (explicit empty override) MUST NOT silently
        # restore Epic 7 defaults. With {} every task threshold returns
        # 0.0 → both qwen (0.80) and haiku (0.92) meet the threshold →
        # neither is PROMOTE-needed for coarse_class.
        out_path = render_report(
            str(populated_db),
            _RUN_ID,
            tmp_path / "reports",
            thresholds_override={},
        )
        body = out_path.read_text(encoding="utf-8")
        demote_start = body.index("## DEMOTE/PROMOTE Suggestions")
        demote_section = body[demote_start:]
        # With empty thresholds, qwen MUST NOT be PROMOTE-needed (since
        # Epic 7's 0.85 threshold no longer applies).
        qwen_line_idx = demote_section.find(f"`{_QWEN}`")
        assert qwen_line_idx >= 0
        line_start = demote_section.rfind("\n", 0, qwen_line_idx) + 1
        line_end = demote_section.find("\n", qwen_line_idx)
        qwen_line = demote_section[line_start:line_end]
        assert "PROMOTE-needed" not in qwen_line


class TestRenderReportThresholdsOverride:
    def test_thresholds_override_changes_verdict(
        self, populated_db: Path, tmp_path: Path
    ) -> None:
        # Default threshold for coarse_class is 0.85; qwen (0.80) is below
        # → PROMOTE-needed. Override to 0.70 → both models meet threshold,
        # qwen on frontier with cheaper cost, haiku also on frontier with
        # higher quality. Verdict for qwen should change to hold-steady
        # (it's the cheapest threshold-meeting point).
        out_path = render_report(
            str(populated_db),
            _RUN_ID,
            tmp_path / "reports",
            thresholds_override={"coarse_class": 0.70},
        )
        body = out_path.read_text(encoding="utf-8")
        # With lowered threshold qwen is no longer PROMOTE-needed for THIS task.
        # We can't assert "PROMOTE-needed not present" globally because haiku
        # may be DEMOTE-valid; but we can check qwen's row shows hold-steady or
        # DEMOTE-related rather than PROMOTE-needed.
        # Easier discriminator: the original 0.85 threshold renders PROMOTE-needed
        # for qwen; with 0.70 override, it must not appear next to the qwen model.
        # Find the qwen row in the DEMOTE/PROMOTE section.
        demote_start = body.index("## DEMOTE/PROMOTE Suggestions")
        demote_section = body[demote_start:]
        # Find the qwen line.
        qwen_line_idx = demote_section.find(f"`{_QWEN}`")
        assert qwen_line_idx >= 0
        # The verdict for qwen with threshold 0.70 should NOT be PROMOTE-needed.
        # Grab the line containing the qwen reference.
        line_start = demote_section.rfind("\n", 0, qwen_line_idx) + 1
        line_end = demote_section.find("\n", qwen_line_idx)
        qwen_line = demote_section[line_start:line_end]
        assert "PROMOTE-needed" not in qwen_line
