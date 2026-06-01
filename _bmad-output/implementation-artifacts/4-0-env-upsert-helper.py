"""Story 4-0 .env upsert helper — used by the dev-story walkthrough.

Single source of truth for `.env` writes during the credential-capture walk.
Implements AC-2's requirements:
  - atomic write (temp file + rename)
  - upsert semantics (replace ^KEY=... in place, or append)
  - quoting rule (single-quote iff value contains '#' or whitespace)
  - fail-fast if .env is not gitignored

Usage:
    python _bmad-output/implementation-artifacts/4-0-env-upsert-helper.py KEY1=val1 [KEY2=val2 ...]

Prints (to stdout) one line per write:
    SET KEY1 (len=N, last4=XXXX, action=created|updated)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"


def _verify_env_gitignored() -> None:
    if not GITIGNORE_PATH.exists():
        raise SystemExit("FATAL: .gitignore not found at repo root")
    contents = GITIGNORE_PATH.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in contents.splitlines()]
    if ".env" not in lines:
        raise SystemExit("FATAL: '.env' is not in .gitignore — refusing to write")


def _quote_if_needed(value: str) -> str:
    if "#" in value or any(c.isspace() for c in value):
        # Single-quote (no escape for embedded single-quotes — KISS; if a value
        # needs that, the operator handles it directly per Story 4-0 protocol).
        return f"'{value}'"
    return value


def _last4(value: str) -> str:
    return value[-4:] if len(value) >= 4 else value


def _upsert_one(lines: list[str], key: str, value: str) -> tuple[list[str], str]:
    """Return (new_lines, action) where action is 'created' or 'updated'."""
    quoted = _quote_if_needed(value)
    new_line = f"{key}={quoted}"
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = new_line
            return lines, "updated"
    lines.append(new_line)
    return lines, "created"


def _atomic_write(path: Path, content: str) -> None:
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".env.tmp.", dir=str(path.parent), text=False
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
        # Atomic on POSIX; on Windows, os.replace overwrites.
        os.replace(str(tmp_path), str(path))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def main(argv: list[str]) -> int:
    _verify_env_gitignored()

    if not argv:
        print("usage: 4-0-env-upsert-helper.py KEY1=val1 [KEY2=val2 ...]", file=sys.stderr)
        return 2

    if ENV_PATH.exists():
        existing = ENV_PATH.read_text(encoding="utf-8").splitlines()
    else:
        existing = []

    lines = list(existing)
    results: list[tuple[str, str, int, str]] = []  # (key, action, length, last4)

    for arg in argv:
        if "=" not in arg:
            print(f"FATAL: argument missing '=': {arg!r}", file=sys.stderr)
            return 2
        key, _, value = arg.partition("=")
        if not key:
            print(f"FATAL: empty key in argument: {arg!r}", file=sys.stderr)
            return 2
        lines, action = _upsert_one(lines, key, value)
        results.append((key, action, len(value), _last4(value)))

    # Ensure trailing newline (POSIX text-file convention).
    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"

    _atomic_write(ENV_PATH, content)

    for key, action, length, last4 in results:
        print(f"SET {key} (len={length}, last4={last4}, action={action})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
