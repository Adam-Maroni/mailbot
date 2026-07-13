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
import tomllib
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
    assert "scripts/**/*.py" in pyproject
    # Find the line and verify T201 (or its alias T20) is one of the codes.
    scripts_line = next(line for line in pyproject.splitlines() if "scripts/**/*.py" in line)
    assert ("T201" in scripts_line) or ("T20" in scripts_line)


def test_pyproject_excludes_scratch_from_ruff_scan() -> None:
    """Story 10.6.3 AC-2: the pyproject.toml MUST exclude `scratch` from the ruff
    scan surface via `[tool.ruff] extend-exclude`.

    `scratch/` holds walk/benchmark scaffolding that legitimately prints to
    stdout/stderr (T201). Rather than fix 6 print-sites that would re-appear with
    the next scratch helper (this is the debt's 4th carry), `scratch` is excluded
    wholesale like the other non-product dirs (`_bmad-output`, `.claude`,
    `_eval-outputs`, …). Asserting the config text directly (not running ruff
    against a synthetic tmp tree) is the right way to pin "the exclusion is
    configured", because extend-exclude entries are project-relative.
    """
    # Parse the TOML and assert on the actual [tool.ruff] extend-exclude list
    # membership (not raw substring matching) so a commented-out entry or a
    # same-named key elsewhere in the file can't produce a false pass.
    with (_REPO_ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    ruff_exclude = config["tool"]["ruff"]["extend-exclude"]
    assert "scratch" in ruff_exclude, (
        "`scratch` must be in [tool.ruff] extend-exclude so repo-wide "
        "`ruff check .` stays green regardless of scratch/ print() usage."
    )
    # Story 10.6.3 CR (mypy-symmetry): mirror the exclusion into [tool.mypy]
    # exclude too, so a future repo-wide mypy invocation never trips on the
    # scratch helpers. (mypy is scoped to mailbot_api/ today, but AC-2's
    # durability intent argues for closing the latent gap.)
    mypy_exclude = config["tool"]["mypy"]["exclude"]
    assert "scratch" in mypy_exclude, (
        "`scratch` must be in [tool.mypy] exclude to mirror the ruff "
        "exclusion and keep the durability contract symmetric."
    )


def test_gitignore_ignores_scratch_dir() -> None:
    """Story 10.6.3 AC-3: `scratch/` MUST be git-ignored so walk/benchmark
    scaffolding under it is never accidentally staged. The two existing helpers'
    docstrings already assert scratch is gitignored — this pins that claim true.
    """
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    entries = {line.strip() for line in gitignore.splitlines()}
    assert ("scratch/" in entries) or ("scratch" in entries), (
        "`scratch/` must be listed in .gitignore so scratch scaffolding is "
        "never accidentally staged."
    )


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
        # Story 3-1 AC-4: FR-2.2 idempotency-key formula outside the
        # idempotency.py allowlist. Detection is narrow — fires only when all
        # three of prompt_version, model, task_type appear inside the f-string.
        (
            "violates_idempotency_key_outside_allowlist.py.fixture",
            "mailbot_api/router",
            "FR-2.2 idempotency formula",
        ),
        # Story 3-4 AC-7: embedding-column write outside the embedding.py
        # allowlist. Mirrors the Story 2-1 router_calls writer-monopoly pattern.
        (
            "violates_embedding_write_outside_allowlist.py.fixture",
            "mailbot_api/router",
            "UPDATE emails SET ... embedding",
        ),
        # Story 4-1 AC-5: bare action-type string literals outside the
        # `mailbot_api/actions/types.py` allowlist.
        (
            "violates_bare_action_string_outside_types.py.fixture",
            "mailbot_api/verbs",
            "bare action-type string literal",
        ),
        # Story 6-8 AC-3: matplotlib.pyplot import outside the analytics-verb
        # allowlist (`mailbot_api/verbs/analytics/`).
        (
            "violates_matplotlib_pyplot_outside_analytics.py.fixture",
            "mailbot_api/verbs",
            "matplotlib.pyplot",
        ),
        # Story 6-8 CR-MED-1: indirect `from matplotlib import pyplot` bypass.
        (
            "violates_matplotlib_pyplot_indirect_bypass.py.fixture",
            "mailbot_api/verbs",
            "indirect bypass",
        ),
        # Story 9-6 AC-2 / AC-10: `INSERT INTO benchmark_runs` outside
        # `benchmark/db.py` must fail with a dedicated message pointing at
        # the benchmark_runs writer-monopoly boundary. Mirrors the Story 2-1
        # `INSERT INTO router_calls` enforcement pattern.
        (
            "violates_benchmark_runs_insert_outside_db.py.fixture",
            "benchmark",
            "INSERT INTO benchmark_runs",
        ),
        # Story 9-7 AC-2 / AC-10: `INSERT (OR REPLACE) INTO benchmark_scores`
        # outside `benchmark/scorer_db.py` must fail with a dedicated
        # message pointing at the benchmark_scores writer-monopoly
        # boundary. Mirrors the Story 9-6 benchmark_runs enforcement
        # pattern; the regex covers both the bare INSERT and the
        # INSERT OR REPLACE upsert variant the scorer uses.
        (
            "violates_benchmark_scores_insert_outside_scorer_db.py.fixture",
            "benchmark",
            "INSERT (OR REPLACE) INTO benchmark_scores",
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
    assert expected_substring in output, f"Expected '{expected_substring}' in boundary output: {output}"


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
        f"Expected boundary check to pass when fixture is at the allowlisted path. Got exit={code}, output: {output}"
    )


def test_benchmark_runs_insert_in_allowlisted_db_path_passes(tmp_path: Path) -> None:
    """Story 9-6 AC-2 positive-pass coverage: the same fixture content placed
    at the allowlisted ``benchmark/db.py`` path must produce a clean check
    (exit 0). Mirrors the Story 2-1 router_calls positive-pass test."""
    target_dir = tmp_path / "benchmark"
    _copy_fixture(
        "violates_benchmark_runs_insert_outside_db.py.fixture",
        target_dir,
        "db.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when benchmark_runs fixture is at "
        f"the allowlisted path. Got exit={code}, output: {output}"
    )


def test_benchmark_scores_insert_in_allowlisted_scorer_db_path_passes(tmp_path: Path) -> None:
    """Story 9-7 AC-2 / AC-10 positive-pass coverage: the same fixture content
    placed at the allowlisted ``benchmark/scorer_db.py`` path must produce a
    clean check (exit 0). Mirrors the Story 9-6 benchmark_runs positive-pass
    test."""
    target_dir = tmp_path / "benchmark"
    _copy_fixture(
        "violates_benchmark_scores_insert_outside_scorer_db.py.fixture",
        target_dir,
        "scorer_db.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when benchmark_scores fixture is "
        f"at the allowlisted path. Got exit={code}, output: {output}"
    )


def test_idempotency_key_in_allowlisted_idempotency_path_passes(tmp_path: Path) -> None:
    """Story 3-1 AC-4 positive-pass coverage: the same fixture content placed
    at the allowlisted `mailbot_api/ingest/idempotency.py` path must produce a
    clean check (exit 0)."""
    target_dir = tmp_path / "mailbot_api" / "ingest"
    _copy_fixture(
        "violates_idempotency_key_outside_allowlist.py.fixture",
        target_dir,
        "idempotency.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when idempotency-key fixture is at "
        f"the allowlisted path. Got exit={code}, output: {output}"
    )


def test_embedding_write_in_allowlisted_embedding_path_passes(tmp_path: Path) -> None:
    """Story 3-4 AC-7 positive-pass coverage: the same embedding-write fixture
    content placed AT the allowlisted `mailbot_api/ingest/embedding.py` path
    must produce a clean check (exit 0)."""
    target_dir = tmp_path / "mailbot_api" / "ingest"
    _copy_fixture(
        "violates_embedding_write_outside_allowlist.py.fixture",
        target_dir,
        "embedding.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when embedding-write fixture is at "
        f"the allowlisted path. Got exit={code}, output: {output}"
    )


def test_benign_sha256_use_does_not_trigger_idempotency_boundary(tmp_path: Path) -> None:
    """Story 3-1 AC-4 specificity: generic `hashlib.sha256(...)` use that does
    NOT carry the FR-2.2 formula (prompt_version + model + task_type all
    referenced inside the f-string) must NOT trigger the idempotency boundary
    check, even placed in a non-allowlisted path."""
    target = tmp_path / "mailbot_api" / "verbs"
    _copy_fixture("benign_sha256_use.py.fixture", target, "uses_sha256.py")

    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass for benign sha256 use, but it "
        f"reported violations. Got exit={code}, output: {output}"
    )
    assert "FR-2.2 idempotency formula" not in output, (
        f"Benign sha256 use should not match the FR-2.2 detection: {output}"
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


def test_bare_action_string_in_allowlisted_types_path_passes(tmp_path: Path) -> None:
    """Story 4-1 AC-7 positive-pass coverage: the bare-action-string fixture
    placed AT `mailbot_api/actions/types.py` must NOT trigger the boundary
    rule (the enum legitimately declares these literals)."""
    target_dir = tmp_path / "mailbot_api" / "actions"
    _copy_fixture(
        "violates_bare_action_string_outside_types.py.fixture",
        target_dir,
        "types.py",  # the allowlisted filename
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass when bare-action-string fixture is at "
        f"the allowlisted types.py path. Got exit={code}, output: {output}"
    )


def test_correct_action_enum_use_does_not_trigger_action_boundary(tmp_path: Path) -> None:
    """Story 4-1 AC-7 specificity: a file that uses the ActionType enum
    correctly (no bare action-value literals) must NOT trigger the boundary
    rule, even placed in a non-allowlisted path."""
    target = tmp_path / "mailbot_api" / "verbs"
    _copy_fixture("good_action_enum_use.py.fixture", target, "uses_enum.py")

    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass for correct enum use. "
        f"Got exit={code}, output: {output}"
    )
    assert "bare action-type" not in output, (
        f"Correct enum use must not match the action-type boundary: {output}"
    )


def test_action_type_docstring_does_not_trigger_action_boundary(tmp_path: Path) -> None:
    """Story 4-1 AC-5: a docstring that mentions an action-type value (e.g.,
    a module docstring describing the action surface) must NOT trip the rule.
    The check pre-filters docstring `ast.Constant` nodes."""
    target = tmp_path / "mailbot_api" / "verbs"
    target.mkdir(parents=True, exist_ok=True)
    (target / "doc_only.py").write_text(
        '''"""This module is about delete and send_reply actions.

It does NOT contain any bare-string action-type literal — it only mentions
them in the docstring. Should not trigger Story 4-1's boundary rule.
"""

from __future__ import annotations


def f() -> None:
    """Operate on mark_read events."""
    pass
''',
        encoding="utf-8",
    )
    code, output = _run_boundary_check_on(tmp_path)
    assert code == 0, (
        f"Expected boundary check to pass for docstring-only action mentions. "
        f"Got exit={code}, output: {output}"
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
    assert code != 0, f"Expected f-string bypass to fail boundary check. Got exit={code}, output: {output}"
    assert "INSERT INTO router_calls" in output, f"Expected 'INSERT INTO router_calls' violation in output: {output}"
