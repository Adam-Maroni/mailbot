"""Story 6-15 AC-2: persist a freshly-minted Microsoft Graph refresh token
into the `oauth_state` SQLite row without going through `.env` / DELETE /
container restart.

Usage (token from stdin — recommended):

    python scripts/refresh_outlook_oauth.py - < /tmp/new-refresh-token.txt

Usage (token from file):

    python scripts/refresh_outlook_oauth.py --from-file /tmp/new-refresh-token.txt
    # optionally remove the source after a successful persist:
    python scripts/refresh_outlook_oauth.py --from-file /tmp/new-rt.txt --unlink-after-read

The token MUST NOT be passed as a CLI argument (it would land in shell
history + ps). Stdin and `--from-file` are the only accepted channels.

Token-handling discipline (per Story 4-0 capture rubric + Story 5-7 redactor):
  * The token is held in memory only long enough to call exchange_and_persist.
  * Nothing is ever echoed to stdout or logged — the only stdout line on
    success is a structured confirmation containing presence + length +
    rotation_count_after (no value).
  * On error, sanitized_body / error code is rendered; `sanitize()` covers
    the Story 5-7 patterns as defense-in-depth (we already avoid passing the
    token anywhere downstream).

Exit codes:
  0    — success; oauth_state persisted; auto-resume fired if router was paused
  2    — token endpoint rejected the new token (e.g., invalid_grant); the
         old refresh token is still in the row (exchange_and_persist
         transaction-protects the swap by raising before the UPDATE). On a
         fresh-deploy first-run rejection, the row INSERTed for this attempt
         is rolled back (CR-7) so the next worker tick does not read it.
  3    — input validation failure (empty token, missing required env)
  4    — transport error (network, DNS, timeout) — narrow to httpx errors;
         programmer errors no longer collapse to this code (CR-5).
  5    — sqlite3 database error (locked, disk full, migration race) (CR-5)
  130  — KeyboardInterrupt

References:
  * `mailbot_api/sync/oauth.py` — exchange_and_persist (the seam this script reuses)
  * `docs/auth-recovery.md` — the runbook this script collapses to one step
  * `scripts/mint_refresh_token.py` — sibling browser-side mint flow on dev box
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import httpx

from mailbot_api.config import SecretMissing, get_secret
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import OAUTH_STATE_DELETE, OAUTH_STATE_INSERT_SEED
from mailbot_api.observability.logging import configure_logging
from mailbot_api.sync.graph_client import GraphAuthError
from mailbot_api.sync.oauth import (
    OAuthState,
    exchange_and_persist,
    load_oauth_state,
)

_PROVIDER = "microsoft_graph"
_STDIN_SENTINEL = "-"


def _read_token_from_path(path: Path) -> str:
    """Read the refresh token from a file. Trailing whitespace/newline is stripped.

    Empty file → SystemExit(3); the operator presumably hand-edited and saved
    nothing.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(  # noqa: T201
            f"FATAL: cannot read --from-file {path}: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc
    token = raw.strip()
    if not token:
        print(  # noqa: T201
            f"FATAL: --from-file {path} is empty (or whitespace-only)",
            file=sys.stderr,
        )
        raise SystemExit(3)
    return token


def _read_token_from_stdin() -> str:
    """Read the refresh token from stdin. Strips trailing newline."""
    data = sys.stdin.read().strip()
    if not data:
        print(  # noqa: T201
            "FATAL: stdin closed with no token (expected the refresh token "
            "on stdin; pipe it in or use --from-file)",
            file=sys.stderr,
        )
        raise SystemExit(3)
    return data


async def _persist(db_path: str, new_refresh_token: str) -> int:
    """The async core. Returns the process exit code."""
    apply_pending_migrations(db_path)

    # Ensure a row exists. The bootstrap insert is idempotent on conflict-free
    # tables; for re-auth on an existing deploy, the row is already there and
    # we drop into the UPDATE path via exchange_and_persist.
    existing = await load_oauth_state(db_path)
    inserted_for_fresh_deploy = False
    if existing is None:
        await execute_write(db_path, OAUTH_STATE_INSERT_SEED, (_PROVIDER, new_refresh_token))
        inserted_for_fresh_deploy = True
        # Re-read so the in-memory dataclass mirrors the row exactly.
        state = await load_oauth_state(db_path)
        if state is None:  # pragma: no cover — INSERT just succeeded
            print(  # noqa: T201
                "FATAL: oauth_state INSERT succeeded but load returned None",
                file=sys.stderr,
            )
            return 2
    else:
        # The exchange_and_persist call drives the swap with the NEW refresh
        # token. Building a fresh OAuthState dataclass instance (rather than
        # mutating `existing`) keeps the `consecutive_refresh_failures`
        # bookkeeping accurate — the success-path UPDATE will reset it to 0
        # via OAUTH_STATE_UPDATE_AFTER_EXCHANGE.
        state = OAuthState(
            provider=existing.provider,
            refresh_token=new_refresh_token,
            access_token=existing.access_token,
            access_expires_at=existing.access_expires_at,
            last_rotated_at=existing.last_rotated_at,
            rotation_count=existing.rotation_count,
            consecutive_refresh_failures=existing.consecutive_refresh_failures,
        )

    try:
        refreshed = await exchange_and_persist(db_path, state=state)
    except GraphAuthError as exc:
        # Story 6-15 CR-7: on a fresh-deploy INSERT-then-fail, roll back the
        # row so the next worker tick does not read the rejected token. On a
        # re-auth against an existing deploy, the old row stays as-is —
        # exchange_and_persist raised before its UPDATE, so the existing
        # (working) refresh_token is untouched.
        if inserted_for_fresh_deploy:
            try:
                await execute_write(db_path, OAUTH_STATE_DELETE, (_PROVIDER,))
            except sqlite3.OperationalError:
                # Don't mask the original exchange failure with a rollback error.
                pass
        # Sanitized message — code is one of the strings from the Graph
        # identity endpoint (invalid_grant / invalid_request / etc.). NOT
        # the token value.
        print(  # noqa: T201
            f"FATAL: token endpoint rejected the new refresh token: code={exc.code}",
            file=sys.stderr,
        )
        return 2

    # Story 6-15 CR-11: structured confirmation. Never log the token value or
    # its length — length is a weak side-channel that confirms token-format
    # heuristics with no operator value.
    print(  # noqa: T201
        "OK: oauth_state persisted "
        "presence=True "
        f"rotation_count_after={refreshed.rotation_count} "
        f"access_expires_at={refreshed.access_expires_at}",
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Persist a newly-minted Microsoft Graph refresh token into the "
            "oauth_state SQLite row. Run on the VPS host (or inside the "
            "mailbot-api container). The token MUST come from stdin or "
            "--from-file — never as a CLI argument."
        )
    )
    # Story 6-15 CR-4: avoid argparse's mutually-exclusive-group + nargs="?"
    # footgun (bpo-#15112). With the prior pattern, invoking the script with
    # NEITHER `-` nor `--from-file` parsed successfully (positional defaulted
    # to None) and the script hung on a TTY waiting for stdin. Explicit
    # post-parse validation gives a clear error instead.
    parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="Path to a UTF-8 file containing only the refresh token.",
    )
    parser.add_argument(
        "stdin_marker",
        nargs="?",
        default=None,
        choices=[_STDIN_SENTINEL],
        help="Pass '-' as the positional arg to read the token from stdin.",
    )
    parser.add_argument(
        "--unlink-after-read",
        action="store_true",
        help=(
            "When used with --from-file: delete the source file after the "
            "token has been successfully persisted. Useful for one-shot "
            "transfer files."
        ),
    )
    args = parser.parse_args(argv)
    if args.from_file is None and args.stdin_marker != _STDIN_SENTINEL:
        parser.error(
            "exactly one input channel is required: pass '-' to read from "
            "stdin, or --from-file <path>"
        )
    if args.from_file is not None and args.stdin_marker == _STDIN_SENTINEL:
        parser.error("--from-file and '-' (stdin) are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = _parse_args(argv)

    try:
        db_path = get_secret("MAILBOT_DB_PATH")
    except SecretMissing as exc:
        print(  # noqa: T201
            f"FATAL: required secret unset: {exc.name}",
            file=sys.stderr,
        )
        return 2

    # Read the token. Stdin path is preferred for direct pipe use; --from-file
    # is the alternative when the operator already has the value in a file.
    if args.from_file is not None:
        token = _read_token_from_path(args.from_file)
    else:
        token = _read_token_from_stdin()

    try:
        exit_code = asyncio.run(_persist(db_path, token))
    except KeyboardInterrupt:
        print("aborted by operator", file=sys.stderr)  # noqa: T201
        return 130
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        # Story 6-15 CR-5: only transport errors map to exit 4. The previous
        # bare `except Exception` collapsed sqlite3 / ImportError / programmer
        # errors into "FATAL: transport error", which made operators
        # misdiagnose DB locks as network failures. Render only the type so
        # the token cannot leak via str(exc) on a future adapter mishap.
        print(  # noqa: T201
            f"FATAL: transport error: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 4
    except sqlite3.OperationalError as exc:
        # DB-side failure (locked, disk full, migration race). Distinct exit
        # code so the operator does not chase the wrong layer.
        print(  # noqa: T201
            f"FATAL: database error: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 5

    # Optional unlink — only after a successful persist (exit 0). On non-zero
    # exit we keep the file so the operator can retry without remixing tokens.
    if exit_code == 0 and args.from_file is not None and args.unlink_after_read:
        # Story 6-15 CR-6: resolve symlinks so we unlink the canonical token
        # file, not just the link. Operators that stage tokens at a stable
        # path and pass a symlink for the run otherwise leave the real file
        # on disk.
        try:
            real_path = Path(os.path.realpath(args.from_file))
            os.unlink(real_path)
            if real_path != args.from_file.resolve(strict=False):
                # Best-effort: also remove the symlink itself (the file the
                # operator named) so nothing dangling stays behind.
                try:
                    os.unlink(args.from_file)
                except OSError:
                    pass
        except OSError as exc:
            print(  # noqa: T201
                f"WARN: token persisted but --unlink-after-read could not "
                f"remove {args.from_file}: {type(exc).__name__}",
                file=sys.stderr,
            )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
