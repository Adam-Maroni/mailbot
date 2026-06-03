"""Operator CLI host. Stories 1-7 + 3-8 + 4-5 + 4-8 + 6-1 + 6-2 ship the
subcommands. Epic 6 ships the full surface (status, logs, pause/resume,
replay, revert).

Usage:
    python scripts/mailbot.py sync-now
    python scripts/mailbot.py rederive --task=coarse_class --since=2026-04-01
    python scripts/mailbot.py replay 42
    python scripts/mailbot.py revert 42
    python scripts/mailbot.py status                       # Story 6-1
    python scripts/mailbot.py status --base-url http://mailbot-api:8000
    python scripts/mailbot.py pause [reason]               # Story 6-2
    python scripts/mailbot.py resume                       # Story 6-2
    python scripts/mailbot.py logs --tail 200 \\
        --filter event=sync.failed --filter level=error    # Story 6-2
    python scripts/mailbot.py logs -f                      # follow mode
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

    # Story 4-5: re-queue a terminal-failed pending_actions row.
    replay = sub.add_parser(
        "replay",
        help="Re-queue a failed pending_actions row for re-drain (Story 4-5)",
    )
    replay.add_argument("action_id", type=int, help="pending_actions.id to replay")
    replay.add_argument(
        "--db-path",
        dest="db_path",
        default=None,
        help="SQLite path. Defaults to $MAILBOT_DB_PATH.",
    )

    # Story 4-8: revert an applied Tier-1 action within 24h.
    revert = sub.add_parser(
        "revert",
        help="Revert an applied Tier-1 pending_actions row within 24h (Story 4-8)",
    )
    revert.add_argument("action_id", type=int, help="pending_actions.id to revert")
    revert.add_argument(
        "--db-path",
        dest="db_path",
        default=None,
        help="SQLite path. Defaults to $MAILBOT_DB_PATH.",
    )

    # Story 6-1: operator status board.
    status_parser = sub.add_parser(
        "status",
        help="Print the operator status board (Story 6-1)",
    )
    status_parser.add_argument(
        "--base-url",
        dest="base_url",
        default="http://localhost:8000",
        help="mailbot-api base URL. Defaults to http://localhost:8000.",
    )

    # Story 6-2: pause / resume / logs subcommands.
    pause_parser = sub.add_parser(
        "pause",
        help="Pause the Router (Story 6-2; wraps Story 2-9 pause_router)",
    )
    pause_parser.add_argument(
        "reason",
        nargs="?",
        default="manual cli pause",
        help="Optional reason string. Defaults to 'manual cli pause'.",
    )
    pause_parser.add_argument(
        "--base-url",
        dest="base_url",
        default="http://localhost:8000",
        help="mailbot-api base URL. Defaults to http://localhost:8000.",
    )

    resume_parser = sub.add_parser(
        "resume",
        help="Resume the Router (Story 6-2; wraps Story 2-9 resume_router)",
    )
    resume_parser.add_argument(
        "--base-url",
        dest="base_url",
        default="http://localhost:8000",
        help="mailbot-api base URL. Defaults to http://localhost:8000.",
    )

    logs_parser = sub.add_parser(
        "logs",
        help="Tail / filter docker-compose logs (Story 6-2)",
    )
    logs_parser.add_argument(
        "--tail",
        dest="tail",
        type=int,
        default=200,
        help="Lines to tail from docker compose logs (default 200).",
    )
    logs_parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        help=(
            "Filter JSON log lines by field=value. Repeatable. "
            "Supported fields: event, level. Multiple values OR within a "
            "field; multiple fields AND across fields. Non-JSON lines "
            "always pass through. Example: --filter event=sync.failed "
            "--filter level=error"
        ),
    )
    logs_parser.add_argument(
        "-f",
        "--follow",
        dest="follow",
        action="store_true",
        help="Stream logs in real time (like docker compose logs -f).",
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
    if args.cmd == "replay":
        return asyncio.run(
            _cmd_replay(action_id=args.action_id, db_path_arg=args.db_path)
        )
    if args.cmd == "revert":
        return asyncio.run(
            _cmd_revert(action_id=args.action_id, db_path_arg=args.db_path)
        )
    if args.cmd == "status":
        return _cmd_status(base_url=args.base_url)
    if args.cmd == "pause":
        return _cmd_pause(reason=args.reason, base_url=args.base_url)
    if args.cmd == "resume":
        return _cmd_resume(base_url=args.base_url)
    if args.cmd == "logs":
        return _cmd_logs(tail=args.tail, filters=args.filters, follow=args.follow)
    return 2


def _cmd_status(*, base_url: str) -> int:
    """Render the operator status board (Story 6-1).

    Synchronous (uses `httpx.Client`) — the subcommand wraps a single GET
    against /admin/status and renders the JSON response. Exit codes:
      0  — clean (no section in warning state)
      1  — at least one section is in warning state
      2  — mailbot-api unreachable, missing env, or other transport failure
    """
    import httpx  # local import: keep CLI module's top-level imports lean

    router_key = get_secret_optional("MAILBOT_ROUTER_KEY")
    if not router_key:
        print(  # noqa: T201
            "FATAL: MAILBOT_ROUTER_KEY required for status (Story 2-10 bearer)",
            file=sys.stderr,
        )
        return 2

    url = f"{base_url.rstrip('/')}/admin/status"
    headers = {"Authorization": f"Bearer {router_key}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
        print(  # noqa: T201
            f"! STATUS: mailbot-api unreachable ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return 2

    if resp.status_code == 401:
        print("! STATUS: 401 — check MAILBOT_ROUTER_KEY", file=sys.stderr)  # noqa: T201
        return 2
    if resp.status_code != 200:
        print(  # noqa: T201
            f"! STATUS: HTTP {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return 2

    report = resp.json()
    warnings = _render_status_report(report)
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) — exit 1")  # noqa: T201
        return 1
    print("\nOK (no warnings — exit 0)")  # noqa: T201
    return 0


def _render_status_report(report: dict[str, object]) -> list[str]:
    """Pretty-print the status report grouped by section. Returns the list
    of section names that raised a warning.

    Section verdict rules (see story Dev Notes for the canonical list):
      sync          — sync_health_alarm True
      ingest        — backpressure_active True
      actions       — failed_in_last_24h > 0
      budget        — degraded_mode_active OR month_usd > 0.8 * month_cap_usd
      cache         — cache_hit_rate_7d < 0.3 AND not the empty-DB case (skip if 0.0 and no calls happened)
      errors        — last_5_router_errors non-empty
      hermes_aux    — drift_alarm True
      containers    — any value != "ok"
    """
    warnings: list[str] = []

    def section_header(name: str, *, warn: bool) -> None:
        marker = "! " if warn else ""
        print(f"\n{marker}{name.upper()}")  # noqa: T201
        if warn:
            warnings.append(name)

    def _as_dict(value: object) -> dict[str, object]:
        # CR-8 (Story 6-1 review 2026-06-03): runtime guard instead of bare
        # `assert isinstance(...)` — asserts are stripped under `python -O`,
        # which would turn malformed JSON into an AttributeError on the
        # subsequent `.get()`. Return {} on type mismatch so rendering
        # degrades gracefully rather than crashing.
        return value if isinstance(value, dict) else {}

    def _as_int(value: object, default: int = 0) -> int:
        # Type-narrowing coerce for `dict[str, object]`.get() values.
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    def _as_float(value: object, default: float = 0.0) -> float:
        # Type-narrowing coerce for `dict[str, object]`.get() values.
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return default
        return default

    # CR-4 (Story 6-1 review 2026-06-03): import the daily soft-warn constant
    # so the rendered output stays in lockstep with router/budget.py instead
    # of hard-coding "$2.00".
    from mailbot_api.router.budget import DAILY_SOFT_WARN_USD

    sync = _as_dict(report.get("sync"))
    sync_warn = bool(sync.get("sync_health_alarm"))
    section_header("sync", warn=sync_warn)
    print(f"  last_heartbeat_at: {sync.get('last_heartbeat_at')}")  # noqa: T201
    print(f"  last_outcome:      {sync.get('last_outcome')}")  # noqa: T201
    minutes = sync.get("minutes_since_last_ok")
    minutes_str = f"{minutes:.1f}" if isinstance(minutes, (int, float)) else "n/a"
    print(f"  minutes_since:     {minutes_str}")  # noqa: T201

    ingest = _as_dict(report.get("ingest"))
    ingest_warn = bool(ingest.get("backpressure_active"))
    section_header("ingest", warn=ingest_warn)
    print(f"  last_heartbeat_at: {ingest.get('last_heartbeat_at')}")  # noqa: T201
    print(f"  unprocessed:       {ingest.get('unprocessed_count')}")  # noqa: T201
    print(  # noqa: T201
        f"  backpressure:      {'yes' if ingest_warn else 'no'}",
    )

    actions = _as_dict(report.get("actions"))
    failed_24h = _as_int(actions.get("failed_in_last_24h"))
    actions_warn = failed_24h > 0
    section_header("actions", warn=actions_warn)
    print(f"  pending by tier:   {actions.get('pending_count_by_tier')}")  # noqa: T201
    print(f"  awaiting grant:    {actions.get('awaiting_grant_count')}")  # noqa: T201
    print(f"  failed (24h):      {failed_24h}")  # noqa: T201

    budget = _as_dict(report.get("budget"))
    today_usd = _as_float(budget.get("today_usd"))
    month_usd = _as_float(budget.get("month_usd"))
    month_cap_usd = _as_float(budget.get("month_cap_usd"), default=30.0)
    daily_warn_fired = bool(budget.get("daily_warn_fired_today"))
    degraded = bool(budget.get("degraded_mode_active"))
    # CR-5 (Story 6-1 review 2026-06-03): include daily_warn_fired_today in
    # the budget warning verdict — Dev Notes implicitly expected the daily
    # soft-warn fire to surface as a section-level warning, but the
    # original verdict only fired on degraded mode OR > 80% of monthly cap.
    budget_warn = degraded or daily_warn_fired or (month_usd > 0.8 * month_cap_usd)
    section_header("budget", warn=budget_warn)
    print(  # noqa: T201
        f"  today:             ${today_usd:.4f} / ${DAILY_SOFT_WARN_USD:.2f} daily-warn"
        f"{' (fired)' if daily_warn_fired else ''}",
    )
    pct = (month_usd / month_cap_usd * 100.0) if month_cap_usd > 0 else 0.0
    pct_marker = " (warning)" if pct > 80.0 else ""
    print(  # noqa: T201
        f"  month:             ${month_usd:.4f} / ${month_cap_usd:.2f} cap "
        f"({pct:.1f}%){pct_marker}",
    )
    print(f"  degraded mode:     {'yes' if degraded else 'no'}")  # noqa: T201

    cache = _as_dict(report.get("cache"))
    rate = _as_float(cache.get("cache_hit_rate_7d"))
    cache_warn = rate < 0.3 and rate > 0.0  # 0.0 = no calls; not a warning
    section_header("cache", warn=cache_warn)
    print(f"  hit rate (7d):     {rate * 100.0:.1f}%")  # noqa: T201

    errors = _as_dict(report.get("errors"))
    error_rows_raw = errors.get("last_5_router_errors") or []
    error_rows = error_rows_raw if isinstance(error_rows_raw, list) else []
    # CR-6 (Story 6-1 review 2026-06-03): time-scope the errors warning to
    # the last 1h per Dev Notes. The underlying query returns up to 5 errors
    # of any age; the verdict filters to recent ones. If ALL 5 are older
    # than 1h, the section renders but does NOT trigger a warning marker.
    from datetime import datetime, timedelta, timezone
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_error_count = 0
    for err_raw in error_rows:
        if not isinstance(err_raw, dict):
            continue
        ts_str = err_raw.get("ts")
        if not isinstance(ts_str, str):
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts >= one_hour_ago:
            recent_error_count += 1
    errors_warn = recent_error_count > 0
    section_header("errors", warn=errors_warn)
    if not error_rows:
        print("  (none in last 5 router_calls)")  # noqa: T201
    else:
        for err_raw in error_rows:
            err = err_raw if isinstance(err_raw, dict) else {}
            print(  # noqa: T201
                f"  id={err.get('router_call_id')} "
                f"ts={err.get('ts')} "
                f"task={err.get('task_type')} "
                f"model={err.get('model_chosen')} "
                f"outcome={err.get('outcome')} "
                f"origin={err.get('caller_origin')}",
            )

    hermes_aux = _as_dict(report.get("hermes_aux"))
    drift = bool(hermes_aux.get("drift_alarm"))
    section_header("hermes-aux", warn=drift)
    print(f"  last 24h count:    {hermes_aux.get('last_24h_count')}")  # noqa: T201
    print(f"  drift alarm:       {'yes' if drift else 'no'}")  # noqa: T201

    # Story 6-2: ROUTER section — pause-state visibility in the status board.
    router = _as_dict(report.get("router"))
    paused = bool(router.get("paused"))
    section_header("router", warn=paused)
    if paused:
        print("  paused:            yes")  # noqa: T201
        print(f"  since:             {router.get('paused_at')}")  # noqa: T201
        print(f"  reason:            {router.get('reason')}")  # noqa: T201
    else:
        print("  paused:            no")  # noqa: T201

    container = _as_dict(report.get("container_health"))
    container_warn = any(
        v != "ok" for v in container.values() if isinstance(v, str)
    )
    section_header("containers", warn=container_warn)
    for service in ("mailbot_api", "mailbot_hermes", "ollama"):
        display = service.replace("_", "-")
        print(f"  {display:18} {container.get(service)}")  # noqa: T201

    return warnings


def _cmd_pause(*, reason: str, base_url: str) -> int:
    """Story 6-2: POST /admin/pause with bearer auth + reason body."""
    import httpx

    router_key = get_secret_optional("MAILBOT_ROUTER_KEY")
    if not router_key:
        print(  # noqa: T201
            "FATAL: MAILBOT_ROUTER_KEY required for pause (Story 2-10 bearer)",
            file=sys.stderr,
        )
        return 2

    url = f"{base_url.rstrip('/')}/admin/pause"
    headers = {"Authorization": f"Bearer {router_key}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, headers=headers, json={"reason": reason})
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
        print(  # noqa: T201
            f"FATAL: mailbot-api unreachable ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return 2

    if resp.status_code == 401:
        print("FATAL: 401 — check MAILBOT_ROUTER_KEY", file=sys.stderr)  # noqa: T201
        return 2
    if resp.status_code != 200:
        print(  # noqa: T201
            f"FATAL: HTTP {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return 2

    body = resp.json()
    print(body.get("message", "router paused"))  # noqa: T201
    return 0


def _cmd_resume(*, base_url: str) -> int:
    """Story 6-2: POST /admin/resume with bearer auth (no body)."""
    import httpx

    router_key = get_secret_optional("MAILBOT_ROUTER_KEY")
    if not router_key:
        print(  # noqa: T201
            "FATAL: MAILBOT_ROUTER_KEY required for resume (Story 2-10 bearer)",
            file=sys.stderr,
        )
        return 2

    url = f"{base_url.rstrip('/')}/admin/resume"
    headers = {"Authorization": f"Bearer {router_key}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
        print(  # noqa: T201
            f"FATAL: mailbot-api unreachable ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return 2

    if resp.status_code == 401:
        print("FATAL: 401 — check MAILBOT_ROUTER_KEY", file=sys.stderr)  # noqa: T201
        return 2
    if resp.status_code != 200:
        print(  # noqa: T201
            f"FATAL: HTTP {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return 2

    body = resp.json()
    print(body.get("message", "router resumed"))  # noqa: T201
    return 0


def _parse_logs_filters(raw_filters: list[str]) -> dict[str, list[str]]:
    """Parse `--filter field=value` arguments into a `{field: [values]}` dict.

    Repeated filters of the same field accumulate values (OR within field).
    Different fields AND together at filter-application time.
    Raises ValueError on malformed input.
    """
    result: dict[str, list[str]] = {}
    for raw in raw_filters:
        if "=" not in raw:
            raise ValueError(
                f"malformed --filter {raw!r}: expected field=value"
            )
        field, _, value = raw.partition("=")
        field = field.strip()
        value = value.strip()
        if not field or not value:
            raise ValueError(
                f"malformed --filter {raw!r}: field and value must be non-empty"
            )
        result.setdefault(field, []).append(value)
    return result


def _filter_log_line(
    line: str, filters: dict[str, list[str]]
) -> str | None:
    """Pure helper for `mailbot logs` filter application.

    Returns the line if it should be printed; None if filtered out.

    Rules per Story 6-2 Dev Notes:
      - Empty filters dict -> pass everything.
      - Non-JSON lines -> ALWAYS pass (subprocess errors, boot lines, etc.
        should never be hidden by filter misuse).
      - JSON line missing a filtered field -> drop.
      - JSON line where field value not in allowed list -> drop.
      - JSON line where every required field has a matching value -> pass.
    """
    if not filters:
        return line
    import json as _json

    try:
        parsed = _json.loads(line)
    except (ValueError, TypeError):
        # Non-JSON line — always pass per AC.
        return line
    if not isinstance(parsed, dict):
        return line
    for field, allowed in filters.items():
        actual = parsed.get(field)
        if actual is None or str(actual) not in allowed:
            return None
    return line


def _build_logs_argv(*, tail: int, follow: bool) -> list[str]:
    """Construct the `docker compose logs ...` argv list. Pure function for
    testability — does NOT actually spawn the subprocess."""
    argv = ["docker", "compose", "logs"]
    if follow:
        argv.append("-f")
    argv.extend(["--tail", str(tail), "mailbot-api", "mailbot-hermes", "ollama"])
    return argv


def _cmd_logs(*, tail: int, filters: list[str], follow: bool) -> int:
    """Story 6-2: `mailbot logs` — tail + filter docker-compose logs.

    Spawns `docker compose logs` as a subprocess and applies the filter
    rules per line. Non-JSON lines pass unconditionally. Ctrl-C during
    follow mode terminates the subprocess cleanly.
    """
    import subprocess  # noqa: S404 — docker compose is the documented surface

    try:
        parsed_filters = _parse_logs_filters(filters)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)  # noqa: T201
        return 2

    argv = _build_logs_argv(tail=tail, follow=follow)
    try:
        proc = subprocess.Popen(  # noqa: S603 — argv is constructed; not shell
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,  # line-buffered
            text=True,
        )
    except FileNotFoundError:
        print(  # noqa: T201
            "FATAL: `docker` not found on PATH — install Docker Engine",
            file=sys.stderr,
        )
        return 2

    try:
        assert proc.stdout is not None  # noqa: S101 — PIPE invariant
        for line in proc.stdout:
            # CR-4 (Story 6-2 review 2026-06-03): strip BOTH \r and \n so
            # Windows-hosted Docker (which can emit CRLF) doesn't turn every
            # structured JSON log line into a `}\r` parse failure → silently
            # treated as non-JSON pass-through → filters bypassed entirely.
            line = line.rstrip("\r\n")
            keep = _filter_log_line(line, parsed_filters)
            if keep is not None:
                print(keep)  # noqa: T201
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0

    # CR-6 (Story 6-2 review 2026-06-03): bounded wait on the normal exit
    # path so a stalled stdout pipe drain (rare but possible with buffered
    # writes in the subprocess) doesn't hang the CLI indefinitely.
    try:
        proc.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        return 2
    return 0 if proc.returncode == 0 else 2


async def _cmd_revert(*, action_id: int, db_path_arg: str | None) -> int:
    """Revert an applied Tier-1 pending_actions row within 24h (Story 4-8)."""
    from mailbot_api.actions.reverter import revert_action

    db_path = db_path_arg or get_secret_optional("MAILBOT_DB_PATH")
    if not db_path:
        print("FATAL: --db-path or $MAILBOT_DB_PATH required", file=sys.stderr)  # noqa: T201
        return 2

    result = await revert_action(action_id, db_path=db_path)
    if result.ok:
        print(  # noqa: T201
            f"action {action_id} reverted; revert_action_id={result.revert_action_id} "
            "queued for drain",
        )
        return 0
    assert result.error is not None
    print(f"REFUSED: {result.error.code}: {result.error.message}", file=sys.stderr)  # noqa: T201
    return 2


async def _cmd_replay(*, action_id: int, db_path_arg: str | None) -> int:
    """Re-queue a failed pending_actions row (Story 4-5)."""
    from mailbot_api.actions.replay import replay_action

    db_path = db_path_arg or get_secret_optional("MAILBOT_DB_PATH")
    if not db_path:
        print("FATAL: --db-path or $MAILBOT_DB_PATH required", file=sys.stderr)  # noqa: T201
        return 2

    result = await replay_action(action_id, db_path=db_path)
    if result.ok:
        print(f"action {action_id} re-queued for drain")  # noqa: T201
        return 0
    assert result.error is not None
    print(f"REFUSED: {result.error.code}: {result.error.message}", file=sys.stderr)  # noqa: T201
    return 2


if __name__ == "__main__":
    sys.exit(main())
