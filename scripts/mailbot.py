"""Minimal operator CLI (Story 1-7). Epic 6 ships the full `mailbot` CLI surface
(status, logs, pause/resume, replay, revert). This story ships just `sync-now`
because Story 1-7 AC-7 requires it.

Usage:
    python scripts/mailbot.py sync-now
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from mailbot_api.config import SecretMissing, get_secret
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.logging import configure_logging
from mailbot_api.sync.graph_client import GraphAuthError
from mailbot_api.sync.sync_worker import run_once


async def _cmd_sync_now() -> int:
    try:
        db_path = get_secret("MAILBOT_DB_PATH")
    except SecretMissing as exc:
        print(  # noqa: T201
            f"FATAL: required secret unset: {exc.name}",
            file=sys.stderr,
        )
        return 2

    # Apply migrations defensively — the worker assumes the schema is present.
    apply_pending_migrations(db_path)

    try:
        result = await run_once(db_path)
    except SecretMissing as exc:
        print(  # noqa: T201
            f"FATAL: required secret unset: {exc.name}. Set OUTLOOK_CLIENT_ID, "
            f"OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID, OUTLOOK_REFRESH_TOKEN in your "
            f".env (see .env.example).",
            file=sys.stderr,
        )
        return 2
    except GraphAuthError as exc:
        print(  # noqa: T201
            f"FATAL: Graph auth failed — code={exc.code} message={exc.message}",
            file=sys.stderr,
        )
        return 1

    print(  # noqa: T201
        f"OK: messages_seen={result.messages_seen} "
        f"messages_upserted={result.messages_upserted} "
        f"messages_soft_deleted={result.messages_soft_deleted} "
        f"duration_ms={result.duration_ms}"
    )
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="mailbot", description="MailBot operator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync-now", help="Run one delta-sync iteration")
    args = parser.parse_args()

    if args.cmd == "sync-now":
        return asyncio.run(_cmd_sync_now())
    return 2


if __name__ == "__main__":
    sys.exit(main())
