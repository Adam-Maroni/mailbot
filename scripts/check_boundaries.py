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
  - Bare action-type string literals (Story 4-1 AC-5 — FR-5.6 enforcement at
    lint time). `propose_action("delete", ...)` and similar bypass attempts
    are caught — callers must use `ActionType.DELETE` from
    `mailbot_api/actions/types.py`. Only `mailbot_api/actions/types.py`
    (where the enum is defined) is allowlisted; the `tests/` tree is
    inherently outside this script's scan (we only scan `mailbot_api/`).
  - Story 5-2 AC-7: `from mailbot_api.verbs.*` outside `mailbot_api/verbs/`
    and `mailbot_api/mcp_server.py`. Verbs are the agent-facing surface;
    internal callers should reach the underlying business logic directly
    (e.g., `mailbot_api/actions/propose.py`, not
    `mailbot_api/verbs/propose_action.py`).
  - Story 5-2 AC-7: `from mcp.server.fastmcp` outside `mailbot_api/mcp_server.py`.
    Keeps the FastMCP dependency localized to the MCP server module.
  - Story 6-8 AC-3: `import matplotlib.pyplot` / `from matplotlib.pyplot`
    outside `mailbot_api/verbs/analytics/`. Bare `import matplotlib` is
    permitted (analytics verbs need `matplotlib.use("Agg")` BEFORE the pyplot
    import); only the pyplot gateway is locked down. AR-ANALYTICS-1 +
    AR-ANALYTICS-2 — chart rendering is owned by analytics verbs returning
    `(bytes, mime_type)` shapes.

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
_OS_ENVIRON_ALLOW = frozenset(
    {
        "mailbot_api/config.py",
        # Story 9-6: benchmark/runner.py is a CLI entry (python -m benchmark.runner)
        # that legitimately reads MAILBOT_DB_PATH at startup (same pattern as
        # mailbot_api/ingest/pipeline.py's CLI path uses via get_secret_optional)
        # AND sets BENCHMARK_COST_MOCK=1 as a runtime contract with Story 9-8's
        # adapter layer (env-var carrier for the --cost-mock flag).
        "benchmark/runner.py",
        # Story 9-7: benchmark/scorer.py is a CLI entry (python -m benchmark.scorer)
        # that legitimately reads MAILBOT_DB_PATH at startup AND sets
        # BENCHMARK_COST_MOCK=1 as the env-var carrier for Story 9-8 — same
        # CLI shape and contract as the runner above.
        "benchmark/scorer.py",
        # Story 9-11: benchmark/anchor_stability_audit.py is a CLI entry
        # (python -m benchmark.anchor_stability_audit) that legitimately
        # reads MAILBOT_DB_PATH at startup AND sets BENCHMARK_COST_MOCK=1
        # for the adapter layer — same CLI contract as the runner + scorer
        # above. Produces no DB rows (writes baseline JSON file only) so
        # no new _*_INSERT_ALLOW allowlist is needed.
        "benchmark/anchor_stability_audit.py",
    }
)
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
        # Story 9-6: benchmark/db.py is the sole writer of benchmark_runs (per
        # the new _BENCHMARK_RUNS_INSERT_ALLOW check) and co-owns the SQL
        # contract — same pattern as audit.py + embedding.py above.
        "benchmark/db.py",
        # Story 9-7: benchmark/scorer_db.py is the sole writer of
        # benchmark_scores (per the new _BENCHMARK_SCORES_INSERT_ALLOW
        # check) and co-owns the SQL contract for the benchmark_runs READ
        # side too (read_run_runs SELECT) — same pattern as benchmark/db.py.
        "benchmark/scorer_db.py",
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
# Story 9-6 AC-2 / AC-10: `INSERT INTO benchmark_runs` may only appear in
# `benchmark/db.py` (the single writer per Rule C, same pattern as Story 2-1's
# router_calls monopoly). The migration file is .sql and not AST-scanned.
_BENCHMARK_RUNS_INSERT_ALLOW = frozenset(
    {
        "benchmark/db.py",
    }
)
# Story 9-7 AC-2 / AC-10: `INSERT INTO benchmark_scores` (and the
# `INSERT OR REPLACE INTO benchmark_scores` upsert variant the scorer uses
# for the AC-1 7-column UNIQUE re-scoring idempotency) may only appear in
# `benchmark/scorer_db.py`. Same writer-monopoly pattern as Story 9-6's
# benchmark_runs + Story 2-1's router_calls. The migration file is .sql
# and not AST-scanned.
_BENCHMARK_SCORES_INSERT_ALLOW = frozenset(
    {
        "benchmark/scorer_db.py",
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

# Story 4-1 AC-5: bare-string action-type literals are banned outside the
# canonical type module. The set covers Tier 1/2/3 — the user-visible action
# surface where FR-5.6 (agent cannot promote tier) actually matters. Tier 0
# values (`ask_router`, `read_sql`, etc.) are NOT in this set because they
# collide with Python symbol names like the `ask_router` function — the
# boundary risk there is zero (Tier-0 verbs never enter pending_actions per
# Story 4-2 AC), and including them would generate noise on every `__all__`
# list. `tests/unit/actions/test_types.py` asserts this set equals the
# Tier-1/2/3 subset of ActionType so drift fails the regression suite.
_ACTION_TYPE_STRING_LITERAL_ALLOW = frozenset(
    {
        "mailbot_api/actions/types.py",
        # Story 4-5: outlook_adapter.py uses Microsoft Graph well-known-folder
        # names ("archive", "inbox") that incidentally collide with
        # ActionType.ARCHIVE.value / MOVE_TO_INBOX context. The collision is
        # semantic — these are Graph folder identifiers, not bare action-type
        # literals. Adding to the allowlist accepts that trade-off.
        "mailbot_api/actions/outlook_adapter.py",
    }
)
# Story 5-2 AC-7: verb-import isolation. Only the verbs package itself + the
# MCP server module may import `mailbot_api.verbs.<verb_name>` symbols. This
# is the boundary that keeps internal callers from sneaking through the
# agent-facing surface — production code should reach the underlying logic
# (e.g., mailbot_api.actions.propose, mailbot_api.actions.cancel) directly.
# Tests are not scanned by this script.
_VERBS_IMPORT_ALLOW = frozenset(
    {
        # The verbs package itself can re-export across sibling modules.
        "mailbot_api/verbs/__init__.py",
        "mailbot_api/verbs/find_emails.py",
        "mailbot_api/verbs/hydrate_email.py",
        "mailbot_api/verbs/get_thread.py",
        "mailbot_api/verbs/count_emails.py",
        "mailbot_api/verbs/get_sender_summary.py",
        "mailbot_api/verbs/schemas.py",
        "mailbot_api/verbs/ask_router.py",
        "mailbot_api/verbs/propose_action.py",
        "mailbot_api/verbs/mint_grant.py",
        "mailbot_api/verbs/revoke_grant.py",
        "mailbot_api/verbs/cancel_action.py",
        "mailbot_api/verbs/revert_action.py",
        "mailbot_api/verbs/mint_sensitivity_token.py",
        "mailbot_api/verbs/budget_admin.py",
        "mailbot_api/verbs/router_control.py",
        "mailbot_api/verbs/cost.py",
        # Story 5-6: notification mute write-side; reads from
        # notification_mutes happen in Epic 6's dispatcher.
        "mailbot_api/verbs/mute_category.py",
        # Story 6-8: analytics surface — render_spend_chart is the first
        # analytics verb. Both the package __init__ (re-export) and the
        # render module itself live inside the verbs package; they re-import
        # each other for ergonomic `from mailbot_api.verbs.analytics import
        # render_spend_chart` consumers (the MCP server).
        "mailbot_api/verbs/analytics/__init__.py",
        "mailbot_api/verbs/analytics/render_spend_chart.py",
        # Story 6-3: notification dispatcher verbs — pull/ack ride the same
        # MCP surface F6 closure unblocked. Hermes polls pull every ~10s.
        "mailbot_api/verbs/pull_pending_notifications.py",
        "mailbot_api/verbs/ack_notification.py",
        # Story 6-4: /unmute companion to Story 5-6's /mute. Clears
        # notification_mutes rows by category.
        "mailbot_api/verbs/unmute_category.py",
        # Story 6-5: daily digest verbs — compose reads cached projections,
        # finalize sweeps queued important rows to ok_via_digest terminal.
        "mailbot_api/verbs/compose_digest.py",
        "mailbot_api/verbs/finalize_digest_delivery.py",
        # Story 5-8: reference-resolution orchestrator. Consumes EmailProjection
        # from verbs.schemas to type the candidate_projections context field;
        # itself an agent-facing surface (chat surface) so the verb-import
        # boundary's intent (only agent-facing modules consume) is preserved.
        "mailbot_api/chat/reference.py",
        # Story 5-9: draft-reply chat orchestrator. Consumes propose_action verb
        # to fire SEND_REPLY into the pending_actions queue; the chat surface IS
        # the agent-facing module by Rule P.
        "mailbot_api/chat/orchestrator.py",
        # Story 5-2: mcp_server.py legitimately consumes every verb to register
        # them as MCP tools — it IS the agent-facing surface.
        "mailbot_api/mcp_server.py",
        # Story 5-3: intent_parsing_chat's OUTPUT_SCHEMA nests FindEmailsFilter
        # so the agent's intent-parse turn can carry a parsed filter forward
        # to find_emails / count_emails. The prompt module IS the agent-facing
        # schema for that turn; reaching `verbs.schemas.FindEmailsFilter`
        # rather than duplicating the model preserves the single-source-of-truth.
        "mailbot_api/prompts/intent_parsing_chat/v1.py",
    }
)
# Story 5-2 AC-7: FastMCP import isolation. Only mcp_server.py may import
# from `mcp.server.fastmcp`. The MCP SDK is a heavy dependency we keep
# localized; tests live under tests/ and are not scanned.
_FASTMCP_IMPORT_ALLOW = frozenset({"mailbot_api/mcp_server.py"})
# Story 6-8 AC-3: matplotlib.pyplot import isolation. Only analytics verbs
# may reach for pyplot — the chart rendering surface is locked to
# `mailbot_api/verbs/analytics/`. `import matplotlib` (without `.pyplot`) is
# permitted everywhere — analytics verbs need `matplotlib.use("Agg")` BEFORE
# the pyplot import, and future analytics modules may need `matplotlib.figure`
# or `matplotlib.transforms` directly. Only the pyplot module is the gateway
# we're locking down.
_MATPLOTLIB_PYPLOT_ALLOW = frozenset(
    {
        "mailbot_api/verbs/analytics/render_spend_chart.py",
    }
)
# Story 9.2 AC-4: ``model_chosen_reason`` raw-string writes are banned outside
# the canonical vocabulary module + audit writer. The enum + helpers in
# ``mailbot_api/router/audit_vocab.py`` are the single source of truth for
# the closed-set values; ``mailbot_api/observability/audit.py`` legitimately
# references them in its validator and docstring; all other modules MUST go
# through the enum / helper indirection.
_MODEL_CHOSEN_REASON_LITERAL_ALLOW = frozenset(
    {
        "mailbot_api/router/audit_vocab.py",
        "mailbot_api/observability/audit.py",
    }
)
# Story 9.2 AC-4: any string literal whose content matches one of these
# stable prefixes is treated as a raw model_chosen_reason write attempt.
# Case-sensitive (the enum values are lowercase + colons).
_MODEL_CHOSEN_REASON_PREFIX_RE = re.compile(
    r"^(policy|override|fallback|degraded|benchmark|cache|sensitivity_gate|"
    r"slash_command|escalated_from):?"
)

_ACTION_TYPE_VALUES = frozenset(
    {
        # Tier 1
        "mark_read",
        "mark_unread",
        "add_local_category",
        "remove_local_category",
        "move_to_triage_folder",
        # Tier 2
        "archive",
        "mark_junk",
        "move_to_user_folder",
        "unsubscribe",
        "move_to_inbox",
        # Tier 3
        "delete",
        "send_reply",
        "send_new_email",
        "send_forward",
        "reply_to_inactive_thread",
        "modify_inbox_rule",
        "modify_outlook_filter",
        "touch_delegated_mailbox",
    }
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

# Story 2-1 AC-6: targeted scan for the literal `INSERT INTO router_calls`
# (case-insensitive, whitespace-flexible) — fires on the table name even when
# the broader _RAW_SQL_RE would also fire from the allowlisted queries module.
# The check runs in addition to the raw-SQL scan; both must allowlist the file
# for it to pass cleanly.
_ROUTER_CALLS_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+router_calls\b",
    flags=re.IGNORECASE,
)

# Story 9-6 AC-2: targeted scan for the literal `INSERT INTO benchmark_runs`
# (case-insensitive, whitespace-flexible). Mirrors the Story 2-1
# `_ROUTER_CALLS_INSERT_RE` pattern; only `benchmark/db.py` is allowed to
# emit this literal.
_BENCHMARK_RUNS_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+benchmark_runs\b",
    flags=re.IGNORECASE,
)

# Story 9-7 AC-2 / AC-10: targeted scan for `INSERT INTO benchmark_scores`
# AND `INSERT OR REPLACE INTO benchmark_scores` (the scorer uses upsert
# semantics so the OR REPLACE branch must also be caught). Mirrors the
# Story 9-6 `_BENCHMARK_RUNS_INSERT_RE` pattern; only
# `benchmark/scorer_db.py` is allowed to emit either literal.
_BENCHMARK_SCORES_INSERT_RE = re.compile(
    r"INSERT(?:\s+OR\s+REPLACE)?\s+INTO\s+benchmark_scores\b",
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


def _collect_docstring_node_ids(tree: ast.AST) -> set[int]:
    """Return the `id()` of every `ast.Constant` node that serves as a docstring.

    A docstring is the first statement of a Module / FunctionDef / AsyncFunctionDef
    / ClassDef body when that statement is `ast.Expr(value=ast.Constant(value=str))`.
    Used by the action-type-literal scan (Story 4-1 AC-5) to avoid flagging
    docstrings that happen to contain action-type-like words.
    """
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                expr_value = body[0].value
                if isinstance(expr_value, ast.Constant) and isinstance(expr_value.value, str):
                    docstring_ids.add(id(expr_value))
    return docstring_ids


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

    # Pre-collect docstring node ids so the action-type-literal scan doesn't
    # false-positive on a docstring that mentions an action name. Other scans
    # (raw SQL, router_calls insert, etc.) are also tolerant to docstrings by
    # being heuristic — only the precise action-value equality check needs
    # this defense because module docstrings legitimately discuss actions.
    docstring_node_ids = _collect_docstring_node_ids(tree)

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
                # Story 5-2 AC-7: bare `import mailbot_api.verbs[.xxx]` bypass.
                if (
                    alias.name == "mailbot_api.verbs"
                    or alias.name.startswith("mailbot_api.verbs.")
                ) and rel not in _VERBS_IMPORT_ALLOW:
                    violations.append(
                        _violation(
                            node.lineno,
                            f"`import {alias.name}`",
                            _VERBS_IMPORT_ALLOW,
                        )
                    )
                # Story 5-2 AC-7: bare `import mcp.server.fastmcp[.xxx]` bypass.
                if (
                    alias.name == "mcp.server.fastmcp"
                    or alias.name.startswith("mcp.server.fastmcp.")
                ) and rel not in _FASTMCP_IMPORT_ALLOW:
                    violations.append(
                        _violation(
                            node.lineno,
                            f"`import {alias.name}`",
                            _FASTMCP_IMPORT_ALLOW,
                        )
                    )
                # Story 6-8 AC-3: `import matplotlib.pyplot[.xxx]` outside the
                # analytics-verb allowlist. Bare `import matplotlib` is permitted
                # (analytics verbs need it for the `matplotlib.use("Agg")` call
                # at module-load time, BEFORE the pyplot import).
                if (
                    alias.name == "matplotlib.pyplot"
                    or alias.name.startswith("matplotlib.pyplot.")
                ) and rel not in _MATPLOTLIB_PYPLOT_ALLOW:
                    violations.append(
                        _violation(
                            node.lineno,
                            f"`import {alias.name}`",
                            _MATPLOTLIB_PYPLOT_ALLOW,
                        )
                    )

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
            full_mod = node.module or ""
            if mod == "ollama" and rel not in _OLLAMA_ALLOW:
                violations.append(_violation(node.lineno, "`from ollama`", _OLLAMA_ALLOW))
            if mod == "anthropic" and rel not in _ANTHROPIC_ALLOW:
                violations.append(_violation(node.lineno, "`from anthropic`", _ANTHROPIC_ALLOW))
            if mod == "sqlite3" and rel not in _SQLITE_ALLOW:
                violations.append(_violation(node.lineno, "`from sqlite3`", _SQLITE_ALLOW))
            # Story 5-2 AC-7: ban `from mailbot_api.verbs.*` outside the
            # verbs package + mcp_server.py. The bare `from mailbot_api.verbs
            # import ...` form is also banned (modules outside the allowlist
            # have no business reaching the agent-facing surface).
            if (
                full_mod == "mailbot_api.verbs"
                or full_mod.startswith("mailbot_api.verbs.")
            ) and rel not in _VERBS_IMPORT_ALLOW:
                violations.append(
                    _violation(
                        node.lineno,
                        f"`from {full_mod} import ...`",
                        _VERBS_IMPORT_ALLOW,
                    )
                )
            # Story 5-2 AC-7 (CR-5 closure): indirect-import bypass —
            # `from mailbot_api import verbs` then `verbs.find_emails()`.
            # node.module is "mailbot_api", aliased name is "verbs"; the
            # primary check above doesn't fire because module != "mailbot_api.verbs".
            if full_mod == "mailbot_api" and rel not in _VERBS_IMPORT_ALLOW:
                for alias in node.names:
                    if alias.name == "verbs":
                        violations.append(
                            _violation(
                                node.lineno,
                                "`from mailbot_api import verbs` (indirect bypass)",
                                _VERBS_IMPORT_ALLOW,
                            )
                        )
            # Story 5-2 AC-7: ban `from mcp.server.fastmcp` outside mcp_server.py.
            if (
                full_mod == "mcp.server.fastmcp"
                or full_mod.startswith("mcp.server.fastmcp.")
            ) and rel not in _FASTMCP_IMPORT_ALLOW:
                violations.append(
                    _violation(
                        node.lineno,
                        f"`from {full_mod} import ...`",
                        _FASTMCP_IMPORT_ALLOW,
                    )
                )
            # Story 6-8 AC-3: `from matplotlib.pyplot import ...` outside the
            # analytics-verb allowlist.
            if (
                full_mod == "matplotlib.pyplot"
                or full_mod.startswith("matplotlib.pyplot.")
            ) and rel not in _MATPLOTLIB_PYPLOT_ALLOW:
                violations.append(
                    _violation(
                        node.lineno,
                        f"`from {full_mod} import ...`",
                        _MATPLOTLIB_PYPLOT_ALLOW,
                    )
                )
            # Story 6-8 CR-MED-1: indirect-import bypass —
            # `from matplotlib import pyplot [as plt]`. Mirrors the Story 5-2
            # CR-5 closure for the verbs boundary (`from mailbot_api import
            # verbs`). Without this guard, any module could write
            # `from matplotlib import pyplot as plt` and reach into pyplot
            # without firing the primary check above.
            if full_mod == "matplotlib" and rel not in _MATPLOTLIB_PYPLOT_ALLOW:
                for alias in node.names:
                    if alias.name == "pyplot":
                        violations.append(
                            _violation(
                                node.lineno,
                                "`from matplotlib import pyplot` (indirect bypass)",
                                _MATPLOTLIB_PYPLOT_ALLOW,
                            )
                        )
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

        # Story 9-6 AC-2 / AC-10: `INSERT INTO benchmark_runs` outside
        # `benchmark/db.py`. Same shape as the router_calls check above.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _BENCHMARK_RUNS_INSERT_RE.search(node.value)
            and rel not in _BENCHMARK_RUNS_INSERT_ALLOW
        ):
            violations.append(
                _violation(
                    getattr(node, "lineno", 0),
                    "`INSERT INTO benchmark_runs`",
                    _BENCHMARK_RUNS_INSERT_ALLOW,
                )
            )

        # Story 9-7 AC-2 / AC-10: `INSERT INTO benchmark_scores` (or
        # `INSERT OR REPLACE INTO benchmark_scores`) outside
        # `benchmark/scorer_db.py`. Same shape as the benchmark_runs check
        # above; the upsert variant is covered by the regex.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _BENCHMARK_SCORES_INSERT_RE.search(node.value)
            and rel not in _BENCHMARK_SCORES_INSERT_ALLOW
        ):
            violations.append(
                _violation(
                    getattr(node, "lineno", 0),
                    "`INSERT (OR REPLACE) INTO benchmark_scores`",
                    _BENCHMARK_SCORES_INSERT_ALLOW,
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

        # Story 9.2 AC-4: model_chosen_reason raw-string writes outside the
        # audit_vocab module + audit writer. Catches three shapes:
        #   1. keyword arg `model_chosen_reason="<prefix>:..."` inside a Call
        #   2. bare assignment `model_chosen_reason = "<prefix>:..."`
        #   3. annotated assignment `model_chosen_reason: str = "<prefix>:..."`
        # The check only fires on Constant(str) values — Attribute references
        # (`ModelChosenReason.OVERRIDE_API.value`), Call expressions
        # (`policy_default(...)`), conditional expressions, and Field
        # declarations all pass.
        if isinstance(node, ast.keyword) and node.arg == "model_chosen_reason":
            if (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and _MODEL_CHOSEN_REASON_PREFIX_RE.match(node.value.value)
                and rel not in _MODEL_CHOSEN_REASON_LITERAL_ALLOW
            ):
                violations.append(
                    _violation(
                        getattr(node.value, "lineno", 0),
                        "raw model_chosen_reason kwarg literal — use ModelChosenReason enum or audit_vocab helpers",
                        _MODEL_CHOSEN_REASON_LITERAL_ALLOW,
                    )
                )
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "model_chosen_reason"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and _MODEL_CHOSEN_REASON_PREFIX_RE.match(node.value.value)
                    and rel not in _MODEL_CHOSEN_REASON_LITERAL_ALLOW
                ):
                    violations.append(
                        _violation(
                            getattr(node, "lineno", 0),
                            (
                                "raw model_chosen_reason assignment literal — "
                                "use ModelChosenReason enum or audit_vocab helpers"
                            ),
                            _MODEL_CHOSEN_REASON_LITERAL_ALLOW,
                        )
                    )
        if isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "model_chosen_reason"
                and node.value is not None
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and _MODEL_CHOSEN_REASON_PREFIX_RE.match(node.value.value)
                and rel not in _MODEL_CHOSEN_REASON_LITERAL_ALLOW
            ):
                violations.append(
                    _violation(
                        getattr(node, "lineno", 0),
                        (
                            "raw model_chosen_reason annotated-assignment literal — "
                            "use ModelChosenReason enum or audit_vocab helpers"
                        ),
                        _MODEL_CHOSEN_REASON_LITERAL_ALLOW,
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

        # Story 4-1 AC-5: bare-string action-type literals are banned outside
        # `mailbot_api/actions/types.py`. Fires only when the literal value is
        # EXACTLY one of the 23 ActionType values — action values are specific
        # enough (`send_reply`, `reply_to_inactive_thread`, `mark_junk`, etc.)
        # that incidental collisions are rare. Docstrings are pre-filtered via
        # `docstring_node_ids` so module/class/function docstrings discussing
        # actions don't false-positive.
        #
        # Tolerated by design:
        #   - The `mailbot_api/actions/types.py` allowlist (the enum DEFINES
        #     these literals).
        #   - Docstrings anywhere (filtered above).
        #   - F-strings with `{action_type.value}` (no bare constant literal
        #     to flag — the value is computed).
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in _ACTION_TYPE_VALUES
            and rel not in _ACTION_TYPE_STRING_LITERAL_ALLOW
            and id(node) not in docstring_node_ids
        ):
            violations.append(
                f"{rel}:{getattr(node, 'lineno', 0)}: BOUNDARY: "
                f'bare action-type string literal "{node.value}" — use '
                f"ActionType.{node.value.upper()} from "
                f"mailbot_api.actions.types is forbidden outside "
                f"{sorted(_ACTION_TYPE_STRING_LITERAL_ALLOW)}"
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

        # Story 9-6 AC-2: f-string-built `INSERT INTO benchmark_runs` mirror
        # of the router_calls f-string walk above.
        if isinstance(node, ast.JoinedStr) and rel not in _BENCHMARK_RUNS_INSERT_ALLOW:
            literal_parts = [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            joined = " ".join(literal_parts)
            if _BENCHMARK_RUNS_INSERT_RE.search(joined):
                violations.append(
                    _violation(
                        getattr(node, "lineno", 0),
                        "`INSERT INTO benchmark_runs` (in f-string)",
                        _BENCHMARK_RUNS_INSERT_ALLOW,
                    )
                )

        # Story 9-7 AC-2: f-string-built `INSERT INTO benchmark_scores` (or
        # `INSERT OR REPLACE INTO`) mirror of the benchmark_runs f-string
        # walk above.
        if isinstance(node, ast.JoinedStr) and rel not in _BENCHMARK_SCORES_INSERT_ALLOW:
            literal_parts = [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            joined = " ".join(literal_parts)
            if _BENCHMARK_SCORES_INSERT_RE.search(joined):
                violations.append(
                    _violation(
                        getattr(node, "lineno", 0),
                        "`INSERT (OR REPLACE) INTO benchmark_scores` (in f-string)",
                        _BENCHMARK_SCORES_INSERT_ALLOW,
                    )
                )

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    # Scan mailbot_api/ (production code) + benchmark/ (Story 9-6 — extends
    # scan surface so the benchmark_runs writer-monopoly check fires on the
    # benchmark package). Tests get explicit fixture-based linting.
    target_dirs = [repo_root / "mailbot_api", repo_root / "benchmark"]

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
