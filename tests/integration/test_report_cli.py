"""Story 9.9 Task 5 — CLI entry-point tests for ``benchmark.report``.

Tests:
  * argparse rejects missing required flags
  * --thresholds-override accepts JSON and is forwarded to render_report
  * bad run_id (path-traversal) → exit code 1
  * missing db file → exit code 2
  * happy path → exit code 0 + stdout prints output path
"""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from benchmark.db import record_benchmark_run
from benchmark.report import main as report_main
from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from benchmark.scorer_db import record_benchmark_score
from mailbot_api.db.migrations_runner import apply_pending_migrations

_RUN_ID = "test-cli-9-9"
_COHORT_A = "0123456789abcdef"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


@pytest.fixture
def populated_cli_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "mailbot.db"
    apply_pending_migrations(str(db_path))
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
    asyncio.run(
        record_benchmark_run(
            str(db_path),
            BenchmarkRunRow(
                run_id=_RUN_ID,
                corpus_item_id="item-001",
                task_type="coarse_class",
                model=_QWEN,
                prompt_version="v1",
                cohort_key=_COHORT_A,
                output_json='{"label": "ok"}',
                tokens_in=100,
                tokens_out=50,
                cached_tokens_in=0,
                cost_usd=0.0005,
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
    return db_path


class TestReportCLI:
    def test_missing_required_args_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            report_main([])
        assert excinfo.value.code != 0

    def test_happy_path_exits_zero_and_prints_output_path(
        self, populated_cli_db: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "reports"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = report_main(
                [
                    "--run-id",
                    _RUN_ID,
                    "--db-path",
                    str(populated_cli_db),
                    "--output-dir",
                    str(out_dir),
                ]
            )
        assert rc == 0
        printed = buf.getvalue().strip()
        # stdout prints the absolute path of the written report.
        expected = (out_dir / f"{_RUN_ID}.md").resolve()
        assert printed == str(expected)
        assert (out_dir / f"{_RUN_ID}.md").exists()

    def test_unsafe_run_id_exits_one(
        self, populated_cli_db: Path, tmp_path: Path
    ) -> None:
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = report_main(
                [
                    "--run-id",
                    "../etc/passwd",
                    "--db-path",
                    str(populated_cli_db),
                    "--output-dir",
                    str(tmp_path / "reports"),
                ]
            )
        assert rc == 1
        assert "unsafe characters" in err_buf.getvalue()

    def test_missing_db_file_exits_two(self, tmp_path: Path) -> None:
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = report_main(
                [
                    "--run-id",
                    _RUN_ID,
                    "--db-path",
                    str(tmp_path / "nonexistent.db"),
                    "--output-dir",
                    str(tmp_path / "reports"),
                ]
            )
        assert rc == 2
        assert "not found" in err_buf.getvalue()

    def test_thresholds_override_json_accepted(
        self, populated_cli_db: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "reports"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = report_main(
                [
                    "--run-id",
                    _RUN_ID,
                    "--db-path",
                    str(populated_cli_db),
                    "--output-dir",
                    str(out_dir),
                    "--thresholds-override",
                    '{"coarse_class": 0.99}',
                ]
            )
        assert rc == 0
        # Threshold 0.99 > qwen quality 0.85 → PROMOTE-needed in output.
        body = (out_dir / f"{_RUN_ID}.md").read_text(encoding="utf-8")
        assert "PROMOTE-needed" in body

    def test_thresholds_override_invalid_json_exits_one(
        self, populated_cli_db: Path, tmp_path: Path
    ) -> None:
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = report_main(
                [
                    "--run-id",
                    _RUN_ID,
                    "--db-path",
                    str(populated_cli_db),
                    "--output-dir",
                    str(tmp_path / "reports"),
                    "--thresholds-override",
                    "not-valid-json{",
                ]
            )
        assert rc == 1
        assert "JSON" in err_buf.getvalue()

    def test_thresholds_override_non_object_exits_one(
        self, populated_cli_db: Path, tmp_path: Path
    ) -> None:
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = report_main(
                [
                    "--run-id",
                    _RUN_ID,
                    "--db-path",
                    str(populated_cli_db),
                    "--output-dir",
                    str(tmp_path / "reports"),
                    "--thresholds-override",
                    "[1, 2, 3]",  # JSON array, not object
                ]
            )
        assert rc == 1
