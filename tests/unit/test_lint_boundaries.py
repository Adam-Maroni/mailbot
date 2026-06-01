"""Meta-tests: assert each lint-violations fixture actually triggers its
expected rule when checked.

Two kinds of checks:
  1. ruff-enforced rules (T201 print, DTZ003 utcnow): copy fixture to a temp dir
     under a representative path and run ruff against it.
  2. boundary-checker-enforced rules (ollama/anthropic/sqlite3/os.environ/raw SQL):
     copy fixture into a temp mailbot_api/-shaped tree and run scripts/check_boundaries.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "lint_violations"


def _copy_fixture(fixture_name: str, dest_dir: Path, dest_filename: str) -> Path:
    """Copy a .fixture file to a .py file at dest_dir/dest_filename."""
    src = _FIXTURE_DIR / fixture_name
    dest = dest_dir / dest_filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def _run_ruff_on(target_dir: Path) -> tuple[int, str]:
    """Run ruff check against target_dir using the project's pyproject.toml settings."""
    result = subprocess.run(  # noqa: S603 — controlled subprocess for meta-test
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(_REPO_ROOT / "pyproject.toml"),
            str(target_dir),
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    return result.returncode, result.stdout + result.stderr


def _run_boundary_check_on(repo_root: Path) -> tuple[int, str]:
    """Run scripts/check_boundaries.py against a synthetic repo root."""
    # Patch the script's repo_root by passing it as CWD. The script computes
    # repo_root = Path(__file__).resolve().parent.parent — to test against an
    # arbitrary tree, copy the script + a tree shape into a tmp dir.
    script_src = _REPO_ROOT / "scripts" / "check_boundaries.py"
    script_dst = repo_root / "scripts" / "check_boundaries.py"
    script_dst.parent.mkdir(parents=True, exist_ok=True)
    script_dst.write_text(script_src.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(  # noqa: S603 — controlled subprocess for meta-test
        [sys.executable, str(script_dst)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    return result.returncode, result.stdout + result.stderr


def test_print_in_non_scripts_triggers_t201(tmp_path: Path) -> None:
    """T201 should fire when print() is used outside scripts/."""
    target = tmp_path / "mailbot_api"
    _copy_fixture("violates_print.py.fixture", target, "uses_print.py")
    code, output = _run_ruff_on(target)
    assert code != 0
    assert "T201" in output


def test_pyproject_per_file_ignores_scripts_for_t201() -> None:
    """The pyproject.toml MUST grant scripts/ a T201 exemption.

    Why not run ruff against a tmp_path/scripts/ tree: per-file-ignores in
    pyproject.toml are project-relative globs (`scripts/**/*.py`), so a synthetic
    tmp_path/scripts path doesn't match. Verifying the config text directly is
    the right way to assert "the exemption is configured."
    """
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'scripts/**/*.py' in pyproject
    # Find the line and verify T201 (or its alias T20) is one of the codes.
    scripts_line = next(
        line for line in pyproject.splitlines() if 'scripts/**/*.py' in line
    )
    assert ("T201" in scripts_line) or ("T20" in scripts_line)


def test_utcnow_triggers_dtz003(tmp_path: Path) -> None:
    """DTZ003 should fire on datetime.utcnow() per AR-PAT-3."""
    target = tmp_path / "mailbot_api"
    _copy_fixture("violates_utcnow.py.fixture", target, "uses_utcnow.py")
    code, output = _run_ruff_on(target)
    assert code != 0
    assert "DTZ" in output  # DTZ001-007 family


@pytest.mark.parametrize(
    "fixture_name,placement_subdir,expected_substring",
    [
        (
            "violates_ollama_outside_router.py.fixture",
            "mailbot_api/verbs",
            "import ollama",
        ),
        (
            "violates_anthropic_outside_router.py.fixture",
            "mailbot_api/verbs",
            "from anthropic",
        ),
        (
            "violates_sqlite_outside_db.py.fixture",
            "mailbot_api/verbs",
            "sqlite3",
        ),
        (
            "violates_os_environ_outside_config.py.fixture",
            "mailbot_api/verbs",
            "os.environ",
        ),
        (
            "violates_raw_sql_outside_db_queries.py.fixture",
            "mailbot_api/verbs",
            "raw SQL literal",
        ),
        # Story 2-1 AC-6: `INSERT INTO router_calls` outside audit.py /
        # queries.py / migrations_runner.py must fail with a dedicated message
        # pointing at the router_calls boundary.
        (
            "violates_router_calls_insert_outside_audit.py.fixture",
            "mailbot_api/verbs",
            "INSERT INTO router_calls",
        ),
        # Story 2-2 AC-12: yaml.safe_load outside the policy loader.
        (
            "violates_yaml_load_outside_policy.py.fixture",
            "mailbot_api/verbs",
            "yaml.safe_load",
        ),
        # Story 2-2 review fix LOW: `from yaml import safe_load` bypass.
        (
            "violates_yaml_from_import_bypass.py.fixture",
            "mailbot_api/verbs",
            "from yaml import safe_load",
        ),
    ],
)
def test_boundary_violations_caught_by_check_boundaries(
    tmp_path: Path, fixture_name: str, placement_subdir: str, expected_substring: str
) -> None:
    """Each boundary fixture, placed in a non-allowlisted path, must produce a
    BOUNDARY: violation when scripts/check_boundaries.py runs."""
    target = tmp_path / placement_subdir
    _copy_fixture(fixture_name, target, "violation.py")

    code, output = _run_boundary_check_on(tmp_path)
    assert code != 0, f"Expected boundary check to fail, got success. Output: {output}"
    assert "BOUNDARY:" in output, f"Expected 'BOUNDARY:' in output: {output}"
    assert expected_substring in output, (
        f"Expected '{expected_substring}' in boundary output: {output}"
    )


def test_router_calls_insert_in_allowlisted_audit_path_passes(tmp_path: Path) -> None:
    """Story 2-1 AC-8 + review fix R8: the same fixture content placed AT the
    allowlisted audit-writer path must produce a clean check (exit 0)."""
    target_dir = tmp_path / "mailbot_api" / "observability"
    _copy_fixture(
        "violates_router_calls_insert_outside_audit.py.fixture",
        target_dir,
        "audit.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when fixture is at the allowlisted "
        f"path. Got exit={code}, output: {output}"
    )


def test_yaml_safe_load_in_allowlisted_policy_path_passes(tmp_path: Path) -> None:
    """Story 2-2 review fix LOW: positive-pass coverage for the yaml allowlist.

    The same yaml-violation fixture placed at the allowlisted policy.py path
    must produce a clean check (exit 0)."""
    target_dir = tmp_path / "mailbot_api" / "router"
    _copy_fixture(
        "violates_yaml_load_outside_policy.py.fixture",
        target_dir,
        "policy.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when yaml fixture is at the "
        f"allowlisted policy path. Got exit={code}, output: {output}"
    )


def test_router_calls_insert_f_string_caught_by_check_boundaries(tmp_path: Path) -> None:
    """Story 2-1 review fix R5: an f-string that constructs the forbidden
    literal at runtime should also fail the boundary check, not just plain
    string constants."""
    target = tmp_path / "mailbot_api" / "verbs"
    target.mkdir(parents=True, exist_ok=True)
    (target / "fstring_bypass.py").write_text(
        '''"""Try to bypass the boundary via f-string concatenation."""

table = "router_calls"
SQL = f"INSERT INTO {table} (ts) VALUES (?)"

# This still tries the literal form via f-string fragment concat — should fail.
ALSO_SQL = f"INSERT INTO router_calls ({\'ts\'}) VALUES (?)"
''',
        encoding="utf-8",
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code != 0, (
        f"Expected f-string bypass to fail boundary check. Got exit={code}, "
        f"output: {output}"
    )
    assert "INSERT INTO router_calls" in output, (
        f"Expected 'INSERT INTO router_calls' violation in output: {output}"
    )
