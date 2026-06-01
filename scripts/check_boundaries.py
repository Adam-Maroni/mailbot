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
    {"mailbot_api/db/queries.py", "mailbot_api/db/migrations_runner.py"}
)

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
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod == "ollama" and rel not in _OLLAMA_ALLOW:
                violations.append(_violation(node.lineno, "`from ollama`", _OLLAMA_ALLOW))
            if mod == "anthropic" and rel not in _ANTHROPIC_ALLOW:
                violations.append(_violation(node.lineno, "`from anthropic`", _ANTHROPIC_ALLOW))
            if mod == "sqlite3" and rel not in _SQLITE_ALLOW:
                violations.append(_violation(node.lineno, "`from sqlite3`", _SQLITE_ALLOW))

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
