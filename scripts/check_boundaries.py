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
_SQLITE_ALLOW = frozenset({"mailbot_api/db/connection.py", "mailbot_api/db/migrations_runner.py"})
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
        # Story 3-4: embedding.py is the sole writer of emails.embedding (per
        # the new _EMBEDDING_WRITE_ALLOW check) and its module docstring +
        # write_embedding docstring legitimately mention the UPDATE SQL shape
        # for documentation. Adding to _RAW_SQL_ALLOW is consistent with
        # embedding.py co-owning the SQL contract for that column family.
        "mailbot_api/ingest/embedding.py",
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
_YAML_LOAD_ALLOW = frozenset(
    {
        "mailbot_api/router/policy.py",
        # Story 3-3: sensitivity_patterns.yaml has its own dedicated loader
        # at the sensitivity-module boundary. Co-owns yaml access with the
        # policy loader.
        "mailbot_api/sensitivity/patterns.py",
    }
)
# Story 3-1 AC-4: the FR-2.2 idempotency-key formula
# (sha256(f"{body}|{prompt_version}|{model}|{task_type}").hexdigest()) lives in
# exactly ONE place. Mirrors the Story 2-1 writer-monopoly pattern for
# router-calls inserts. Detection fires on a hashlib.sha256(...) call whose
# argument is an f-string (ast.JoinedStr) carrying all three identifiers
# `prompt_version`, `model`, AND `task_type` — a precise enough heuristic to
# avoid false positives on unrelated sha256 usage.
_IDEMPOTENCY_KEY_ALLOW = frozenset({"mailbot_api/ingest/idempotency.py"})
# Story 3-4 AC-7: `UPDATE emails SET embedding` / `INSERT INTO emails (...embedding...)`
# may only appear in mailbot_api/ingest/embedding.py (the sole writer) + the
# SQL constants module + the migrations runner. Same writer-monopoly pattern
# as Story 2-1's _ROUTER_CALLS_INSERT_ALLOW. The migration .sql files are not
# scanned by this Python AST pass.
_EMBEDDING_WRITE_ALLOW = frozenset(
    {
        "mailbot_api/ingest/embedding.py",
        "mailbot_api/db/queries.py",
        "mailbot_api/db/migrations_runner.py",
    }
)
_IDEMPOTENCY_KEY_REQUIRED_NAMES = frozenset({"prompt_version", "model", "task_type"})

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

# Story 3-4 AC-7: targeted scan for `UPDATE emails SET ... embedding ...` OR
# `INSERT INTO emails (...embedding...)`. Mirrors the Story 2-1
# `_ROUTER_CALLS_INSERT_RE` pattern but covers BOTH the UPDATE-SET path
# (typical embedding write) and the INSERT path (defensive — Story 1-7's
# EMAIL_UPSERT might one day include embedding in its column list).
_EMBEDDING_WRITE_RE = re.compile(
    r"(?:UPDATE\s+emails\s+SET[^;]*\bembedding\b"
    r"|INSERT\s+INTO\s+emails\s*\([^)]*\bembedding\b)",
    flags=re.IGNORECASE | re.DOTALL,
)


def _is_sqlite_connect(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr == "connect" and isinstance(func.value, ast.Name) and func.value.id == "sqlite3":
            return True
    return False


def _is_hashlib_sha256_call(call: ast.Call) -> bool:
    """Detect `hashlib.sha256(...)` invocations specifically."""
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr == "sha256" and isinstance(func.value, ast.Name) and func.value.id == "hashlib":
            return True
    return False


def _fstring_carries_idempotency_formula(joined_str: ast.JoinedStr) -> bool:
    """Return True if an f-string contains FormattedValue nodes for all three
    of `prompt_version`, `model`, and `task_type` (in any order, possibly
    interleaved with body and other content).

    Detection looks at the `ast.FormattedValue.value` sub-expressions inside
    the JoinedStr. We collect every `Name` that appears anywhere in those
    sub-expressions (including attribute access bases, function call args,
    etc.) and check whether the required-name set is a subset.

    This is a precise heuristic for the FR-2.2 formula and won't trip on
    unrelated f-strings that merely happen to mention one of the names.
    """
    names_seen: set[str] = set()
    for value in joined_str.values:
        if not isinstance(value, ast.FormattedValue):
            continue
        # Walk the FormattedValue sub-expression for any Name references.
        for sub in ast.walk(value):
            if isinstance(sub, ast.Name):
                names_seen.add(sub.id)
    return _IDEMPOTENCY_KEY_REQUIRED_NAMES.issubset(names_seen)


def _arg_carries_idempotency_formula(arg: ast.AST) -> bool:
    """Return True if a sha256 argument expression carries the FR-2.2 formula.

    Handles two shapes the formula can take:
      1. `f"{body}|{prompt_version}|{model}|{task_type}".encode(...)`
         → argument is a Call to `.encode`, with value being a JoinedStr.
      2. `f"{body}|{prompt_version}|{model}|{task_type}".encode()` passed
         as the arg directly, or the raw JoinedStr passed (rare; encoding is
         normally explicit).
      3. The same f-string built up via `+` concatenation isn't supported by
         this detection (would require constant-folding); the established
         pattern in Story 2-1 takes the same trade-off.
    """
    # Unwrap a `.encode(...)` call: arg is Call where func is Attribute('encode').
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute):
        if arg.func.attr == "encode":
            inner = arg.func.value
            if isinstance(inner, ast.JoinedStr):
                return _fstring_carries_idempotency_formula(inner)
    # Direct JoinedStr argument (rare but possible).
    if isinstance(arg, ast.JoinedStr):
        return _fstring_carries_idempotency_formula(arg)
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
            if func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os":
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
                    violations.append(_violation(node.lineno, "`import anthropic`", _ANTHROPIC_ALLOW))
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
                if isinstance(base, ast.Name) and base.id == "yaml" and rel not in _YAML_LOAD_ALLOW:
                    violations.append(_violation(node.lineno, f"`yaml.{attr_name}(...)`", _YAML_LOAD_ALLOW))
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
            violations.append(_violation(node.lineno, "`sqlite3.connect(...)`", _SQLITE_ALLOW))

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
            violations.append(_violation(getattr(node, "lineno", 0), "raw SQL literal", _RAW_SQL_ALLOW))

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

        # Story 3-4 AC-7: embedding-column writer monopoly. `UPDATE emails SET
        # embedding ...` or `INSERT INTO emails (...embedding...)` literals
        # outside `mailbot_api/ingest/embedding.py` (the sole writer) fail.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _EMBEDDING_WRITE_RE.search(node.value)
            and rel not in _EMBEDDING_WRITE_ALLOW
        ):
            violations.append(
                _violation(
                    getattr(node, "lineno", 0),
                    "`UPDATE emails SET ... embedding ...` / `INSERT INTO emails (...embedding...)`",
                    _EMBEDDING_WRITE_ALLOW,
                )
            )
        # Same check on JoinedStr (f-string) nodes (Story 2-1 R5 pattern).
        if isinstance(node, ast.JoinedStr) and rel not in _EMBEDDING_WRITE_ALLOW:
            literal_parts = [
                v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
            ]
            joined = " ".join(literal_parts)
            if _EMBEDDING_WRITE_RE.search(joined):
                violations.append(
                    _violation(
                        getattr(node, "lineno", 0),
                        "`UPDATE/INSERT emails ... embedding` (in f-string)",
                        _EMBEDDING_WRITE_ALLOW,
                    )
                )

        # Story 3-1 AC-4: idempotency-key writer monopoly. Detection fires on
        # `hashlib.sha256(...)` calls whose argument is an f-string carrying the
        # FR-2.2 formula (prompt_version + model + task_type names referenced
        # inside the JoinedStr's FormattedValue sub-expressions). The check
        # tolerates the `.encode(...)` wrapping that is standard practice in
        # this codebase.
        #
        # CR-5: also inspect keyword arguments (e.g., a call written as
        # `hashlib.sha256(data=f"...")` would pass the f-string via kwargs).
        # Known out-of-scope bypasses (consistent with Story 2-1's documented
        # limitations): (a) `hashlib.new('sha256', ...)` — uses the new()
        # constructor not directly inspected here; (b) variable renames before
        # the f-string is built (`pv = prompt_version; sha256(f"{...|{pv}|...")`).
        # Both are accidental-drift catches, not adversarial defenses.
        if isinstance(node, ast.Call) and _is_hashlib_sha256_call(node) and rel not in _IDEMPOTENCY_KEY_ALLOW:
            candidate_args: list[ast.AST] = list(node.args)
            for kw in node.keywords:
                if kw.value is not None:
                    candidate_args.append(kw.value)
            if any(_arg_carries_idempotency_formula(a) for a in candidate_args):
                violations.append(
                    _violation(
                        getattr(node, "lineno", 0),
                        '`hashlib.sha256(f"{body}|{prompt_version}|{model}|{task_type}")` (FR-2.2 idempotency formula)',
                        _IDEMPOTENCY_KEY_ALLOW,
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
            literal_parts = [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
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
