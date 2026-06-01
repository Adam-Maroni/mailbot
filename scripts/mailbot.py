"""Operator CLI host. Stories 1-7 + 3-8 ship the subcommands. Epic 6 ships the
full surface (status, logs, pause/resume, replay, revert).

Usage:
    python scripts/mailbot.py sync-now
    python scripts/mailbot.py rederive --task=coarse_class --since=2026-04-01
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date as date_type

from mailbot_api.config import SecretMissing, get_secret, get_secret_optional
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.logging import configure_logging
from mailbot_api.router.policy import (
    PolicyValidationError,
    load_policy,
    set_policy_snapshot,
)
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


def _load_policy_for_cli() -> None:
    """Load policy.yaml into the module-level snapshot (mirrors lifespan)."""
    from pathlib import Path

    policy_path = Path(get_secret_optional("MAILBOT_POLICY_PATH", "/app/router/policy.yaml"))
    try:
        policy = load_policy(policy_path)
    except PolicyValidationError as exc:
        print(  # noqa: T201
            f"FATAL: policy.yaml failed to load: {exc.details}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    set_policy_snapshot(policy)


async def _cmd_rederive(
    *,
    task: str,
    since: date_type,
    prompt_version: str | None,
    yes: bool,
    db_path_arg: str | None,
) -> int:
    """Story 3-8 AC-1..7: targeted re-derivation."""
    from mailbot_api.ingest.rederive import (
        VALID_RE_DERIVATION_TASKS,
        execute_rederive,
        plan_rederive,
    )

    if task not in VALID_RE_DERIVATION_TASKS:
        print(  # noqa: T201
            f"FATAL: --task={task!r} is not valid. "
            f"Expected one of: {sorted(VALID_RE_DERIVATION_TASKS)}",
            file=sys.stderr,
        )
        return 2

    if db_path_arg is not None:
        db_path = db_path_arg
    else:
        try:
            db_path = get_secret("MAILBOT_DB_PATH")
        except SecretMissing as exc:
            print(  # noqa: T201
                f"FATAL: required secret unset: {exc.name}. "
                f"Set MAILBOT_DB_PATH or pass --db-path.",
                file=sys.stderr,
            )
            return 2

    # Load policy for plan_rederive's snapshot_for_dispatch call.
    _load_policy_for_cli()

    plan = await plan_rederive(
        task=task, since=since, prompt_version=prompt_version, db_path=db_path
    )

    # AC-4 sensitivity precondition gate.
    if plan.blocked_by_sensitivity_count > 0:
        print(  # noqa: T201
            f"REFUSED: {plan.blocked_by_sensitivity_count} rows are unclassified "
            f"for sensitivity — re-derivation requires sensitivity to have run first."
        )
        return 1

    if plan.count == 0:
        print(  # noqa: T201
            f"No rows need re-derivation for task={task!r} "
            f"prompt_version={plan.prompt_version!r} since={plan.since_iso}. "
            f"Nothing to do."
        )
        return 0

    # Show plan summary.
    if task == "sensitivity_class":
        # AC-5: prominent warning.
        print(  # noqa: T201
            f"WARNING: Re-deriving sensitivity will clear all downstream "
            f"derivations for {plan.count} rows."
        )
    print(  # noqa: T201
        f"\nPlan:\n"
        f"  task:                 {plan.task}\n"
        f"  since:                {plan.since_iso}\n"
        f"  prompt_version:       {plan.prompt_version}\n"
        f"  model:                {plan.model}\n"
        f"  rows to re-derive:    {plan.count}\n"
        f"  est. cost (USD):      ${plan.cost_usd_estimated:.4f}\n"
        f"  est. wall-clock:      ~{plan.est_wall_clock_seconds:.0f}s"
    )

    # AC-6 confirmation prompt.
    if not yes:
        print("Proceed? [y/N] (30s timeout → no): ", end="", flush=True)  # noqa: T201
        try:
            # 30-second timeout via asyncio.wait_for around a sync stdin read.
            user_input = await asyncio.wait_for(
                asyncio.to_thread(sys.stdin.readline), timeout=30.0
            )
        except asyncio.TimeoutError:
            print("\n(timeout — exiting without changes)")  # noqa: T201
            return 0
        if user_input.strip().lower() != "y":
            print("(no — exiting without changes)")  # noqa: T201
            return 0

    # AC-3 dispatch.
    result = await execute_rederive(plan=plan, db_path=db_path)

    print(  # noqa: T201
        f"\nResult:\n"
        f"  processed:  {result.processed}\n"
        f"  succeeded:  {result.succeeded}\n"
        f"  failed:     {result.failed}\n"
        f"  aborted:    {result.aborted}"
    )
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")  # noqa: T201
        for e in result.errors[:10]:
            print(f"  - {e}")  # noqa: T201
        if len(result.errors) > 10:
            print(f"  ... ({len(result.errors) - 10} more)")  # noqa: T201

    return 0 if result.failed == 0 and not result.aborted else 1


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="mailbot", description="MailBot operator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync-now", help="Run one delta-sync iteration")

    rederive = sub.add_parser(
        "rederive",
        help="Re-derive a single ingest task on rows since DATE (FR-2.6)",
    )
    rederive.add_argument("--task", required=True, help="Task to re-derive")
    rederive.add_argument(
        "--since",
        required=True,
        type=lambda s: date_type.fromisoformat(s),
        help="YYYY-MM-DD cutoff (received_at >= since)",
    )
    rederive.add_argument(
        "--prompt-v",
        dest="prompt_v",
        default=None,
        help="Override the policy.tasks[task].prompt_version target",
    )
    rederive.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt (CI / scripted use)",
    )
    rederive.add_argument(
        "--db-path",
        dest="db_path",
        default=None,
        help="SQLite path. Defaults to $MAILBOT_DB_PATH.",
    )

    args = parser.parse_args()

    if args.cmd == "sync-now":
        return asyncio.run(_cmd_sync_now())
    if args.cmd == "rederive":
        return asyncio.run(
            _cmd_rederive(
                task=args.task,
                since=args.since,
                prompt_version=args.prompt_v,
                yes=args.yes,
                db_path_arg=args.db_path,
            )
        )
    return 2


if __name__ == "__main__":
    sys.exit(main())
