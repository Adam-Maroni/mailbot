"""Selective-import boundary checker per architecture §AR-PAT-1.

Ruff doesn't natively support "ban this import in all files EXCEPT this allowlist",
so we implement that check here as a lightweight AST scan. The script is
invoked from `make lint` after `ruff check` passes.

Bans enforced:
  - `import ollama` / `from ollama` outside `mailbot_api/router/models.py`
  - `import anthropic` / `from anthropic` outside `mailbot_api/router/models.py`
  - `import sqlite3` / `from sqlite3` / `sqlite3.connect(...)` outside
    `mailbot_api/db/connection.py` and `mailbot_api/db/migrations_runner.py`
  - `os.environ[...]` / `os.environ.get(...)` outside `mailbot_api/config.py`
  - Raw SQL literals (string with SELECT/INSERT/UPDATE/DELETE keywords + table name)
    outside `mailbot_api/db/queries.py` AND `mailbot_api/db/migrations_runner.py`
  - `INSERT INTO router_calls` literal (Story 2-1 AC-6 — Rule C audit-writer
    boundary) outside `mailbot_api/observability/audit.py` AND
    `mailbot_api/db/queries.py` AND `mailbot_api/db/migrations_runner.py`.
    The migration file itself is `.sql`, not scanned by this Python AST pass.

Output: one line per violation, non-zero exit code on any violation.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Allowlists (paths are project-relative, POSIX-style).
_OLLAMA_ALLOW = frozenset({"mailbot_api/router/models.py"})
_ANTHROPIC_ALLOW = frozenset({"mailbot_api/router/models.py"})
_SQLITE_ALLOW = frozenset(
    {"mailbot_api/db/connection.py", "mailbot_api/db/migrations_runner.py"}
)
_OS_ENVIRON_ALLOW = frozenset({"mailbot_api/config.py"})
_RAW_SQL_ALLOW = frozenset(
    {
        "mailbot_api/db/queries.py",
        "mailbot_api/db/migrations_runner.py",
        # Story 2-1 / review fix R8 + R5 consequence: audit.py legitimately
        # references router-calls SQL in its module docstring (column-order
        # contract documentation), and the AC-8 allowlist-passes-clean test
        # for INSERT INTO router_calls places fixture content here. Adding to
        # the raw-SQL allowlist is consistent with audit.py's role as the
        # audit-writer boundary owner — it co-owns the SQL contract.
        "mailbot_api/observability/audit.py",
    }
)
# Story 2-1 AC-6: `INSERT INTO router_calls` may only appear in the audit
# writer module, the SQL constants module, the migrations runner, or the
# migration file itself. The migration is .sql, not scanned here.
_ROUTER_CALLS_INSERT_ALLOW = frozenset(
    {
        "mailbot_api/observability/audit.py",
        "mailbot_api/db/queries.py",
        "mailbot_api/db/migrations_runner.py",
    }
)
# Story 2-2 AC-12: `yaml.safe_load` / `yaml.load` may only appear in the
# policy loader. Downstream consumers go through get_policy() /
# snapshot_for_dispatch() — no per-module YAML reparse.
_YAML_LOAD_ALLOW = frozenset({"mailbot_api/router/policy.py"})

# Raw-SQL heuristic: SQL verb followed by an identifier-shaped token. Tightened
# from a bare verb match to reduce false positives on docstrings that mention
# the word "UPDATE" / "INSERT" without an accompanying identifier.
# Pattern: VERB <whitespace> identifier-like-token (letters/digits/underscores/asterisk).
_RAW_SQL_RE = re.compile(
    r"\b(?:SELECT\s+[\w*]"
    r"|INSERT\s+INTO\s+\w"
    r"|UPDATE\s+\w+\s+SET"
    r"|DELETE\s+FROM\s+\w"
    r"|CREATE\s+TABLE\s+\w"
    r"|CREATE\s+INDEX\s+\w"
    r"|ALTER\s+TABLE\s+\w"
    r"|DROP\s+TABLE\s+\w"
    r")",
    flags=re.IGNORECASE,
)

# Story 2-1 AC-6: targeted scan for the literal `INSERT INTO router_calls`
# (case-insensitive, whitespace-flexible) — fires on the table name even when
# the broader _RAW_SQL_RE would also fire from the allowlisted queries module.
# The check runs in addition to the raw-SQL scan; both must allowlist the file
# for it to pass cleanly.
_ROUTER_CALLS_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+router_calls\b",
    flags=re.IGNORECASE,
)


def _is_sqlite_connect(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr == "connect" and isinstance(func.value, ast.Name) and func.value.id == "sqlite3":
            return True
    return False


def _is_os_environ_access(node: ast.AST) -> bool:
    """Detect `os.environ[...]`, `os.environ.get(...)`, `os.getenv(...)`, `from os import environ` use."""
    # os.environ[...]
    if isinstance(node, ast.Subscript):
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "environ"
            and isinstance(value.value, ast.Name)
            and value.value.id == "os"
        ):
            return True
    # os.environ.get(...) or os.getenv(...)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            # os.environ.get(...)
            if (
                func.attr == "get"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "environ"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
            ):
                return True
            # os.getenv(...)
            if (
                func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                return True
    return False


def check_file(path: Path, repo_root: Path) -> list[str]:
    """Return list of violation strings for one source file."""
    rel = path.relative_to(repo_root).as_posix()
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        violations.append(f"{rel}: syntax error — cannot check boundaries")
        return violations

    def _violation(line: int, pattern: str, allow: frozenset[str]) -> str:
        return f"{rel}:{line}: BOUNDARY: {pattern} is forbidden outside {sorted(allow)}"

    for node in ast.walk(tree):
        # Import bans.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name == "ollama" and rel not in _OLLAMA_ALLOW:
                    violations.append(_violation(node.lineno, "`import ollama`", _OLLAMA_ALLOW))
                if root_name == "anthropic" and rel not in _ANTHROPIC_ALLOW:
                    violations.append(
                        _violation(node.lineno, "`import anthropic`", _ANTHROPIC_ALLOW)
                    )
                if root_name == "sqlite3" and rel not in _SQLITE_ALLOW:
                    violations.append(_violation(node.lineno, "`import sqlite3`", _SQLITE_ALLOW))

        # Story 2-2 AC-12: `yaml.safe_load(...)` / `yaml.load(...)` calls.
        # Detection on Call → Attribute (`yaml.safe_load(...)`); imports of
        # `yaml.safe_load` as a bare name are permitted by exception (the
        # policy loader is the only module that does this).
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in ("safe_load", "load"):
                base = node.func.value
                if (
                    isinstance(base, ast.Name)
                    and base.id == "yaml"
                    and rel not in _YAML_LOAD_ALLOW
                ):
                    violations.append(
                        _violation(node.lineno, f"`yaml.{attr_name}(...)`", _YAML_LOAD_ALLOW)
                    )
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod == "ollama" and rel not in _OLLAMA_ALLOW:
                violations.append(_violation(node.lineno, "`from ollama`", _OLLAMA_ALLOW))
            if mod == "anthropic" and rel not in _ANTHROPIC_ALLOW:
                violations.append(_violation(node.lineno, "`from anthropic`", _ANTHROPIC_ALLOW))
            if mod == "sqlite3" and rel not in _SQLITE_ALLOW:
                violations.append(_violation(node.lineno, "`from sqlite3`", _SQLITE_ALLOW))
            # Story 2-2 review fix LOW: `from yaml import safe_load`
            # bare-name bypass — the bare `safe_load(x)` call after such an
            # import won't be caught by the `yaml.safe_load(...)` attribute
            # detection below. Catch the import itself.
            if mod == "yaml" and rel not in _YAML_LOAD_ALLOW:
                for alias in node.names:
                    if alias.name in ("safe_load", "load"):
                        violations.append(
                            _violation(
                                node.lineno,
                                f"`from yaml import {alias.name}`",
                                _YAML_LOAD_ALLOW,
                            )
                        )

        # sqlite3.connect(...) calls.
        if isinstance(node, ast.Call) and _is_sqlite_connect(node) and rel not in _SQLITE_ALLOW:
            violations.append(
                _violation(node.lineno, "`sqlite3.connect(...)`", _SQLITE_ALLOW)
            )

        # os.environ access.
        if _is_os_environ_access(node) and rel not in _OS_ENVIRON_ALLOW:
            violations.append(
                _violation(
                    getattr(node, "lineno", 0),
                    "`os.environ`/`os.getenv`",
                    _OS_ENVIRON_ALLOW,
                )
            )

        # Raw SQL literals.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _RAW_SQL_RE.search(node.value)
            and rel not in _RAW_SQL_ALLOW
        ):
            violations.append(
                _violation(
                    getattr(node, "lineno", 0), "raw SQL literal", _RAW_SQL_ALLOW
                )
            )

        # Story 2-1 AC-6: `INSERT INTO router_calls` outside the audit-writer
        # allowlist. Dedicated check (separate from raw-SQL) so the violation
        # message points at the right boundary.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _ROUTER_CALLS_INSERT_RE.search(node.value)
            and rel not in _ROUTER_CALLS_INSERT_ALLOW
        ):
            violations.append(
                _violation(
                    getattr(node, "lineno", 0),
                    "`INSERT INTO router_calls`",
                    _ROUTER_CALLS_INSERT_ALLOW,
                )
            )

        # Story 2-1 review fix R5: f-strings (ast.JoinedStr) can construct the
        # forbidden literal at runtime — e.g.,
        # `f"INSERT INTO router_calls ({col}) VALUES (?)"`. Walk the f-string's
        # constant fragments and concatenate them; if the joined fragment
        # matches `_ROUTER_CALLS_INSERT_RE`, the f-string was clearly hand-built
        # to bypass the constant scan. We only fail on the dedicated
        # router_calls check here (not the broad raw-SQL check) because the
        # raw-SQL check is meant as a docstring-tolerant heuristic; the
        # router_calls table is the load-bearing audit boundary that justifies
        # the stricter walk.
        if isinstance(node, ast.JoinedStr) and rel not in _ROUTER_CALLS_INSERT_ALLOW:
            literal_parts = [
                v.value
                for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            ]
            joined = " ".join(literal_parts)
            if _ROUTER_CALLS_INSERT_RE.search(joined):
                violations.append(
                    _violation(
                        getattr(node, "lineno", 0),
                        "`INSERT INTO router_calls` (in f-string)",
                        _ROUTER_CALLS_INSERT_ALLOW,
                    )
                )

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    # Scan mailbot_api/ only (production code). Tests get explicit fixture-based linting.
    target_dirs = [repo_root / "mailbot_api"]

    all_violations: list[str] = []
    for target in target_dirs:
        if not target.exists():
            continue
        for py_file in target.rglob("*.py"):
            all_violations.extend(check_file(py_file, repo_root))

    if all_violations:
        for v in all_violations:
            print(v)  # noqa: T201 — this script is in scripts/, T20 allows print here
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
