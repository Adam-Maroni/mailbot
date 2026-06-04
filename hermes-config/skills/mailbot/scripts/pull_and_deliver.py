#!/usr/bin/env python3
"""Story 6-10 — pull-and-deliver script for the Hermes cron pull loop.

Calls MailBot's `pull_pending_notifications` MCP tool, formats each
returned row for Discord, and acks each row via `ack_notification` MCP
tool. The cron job runs `no_agent=True` — no LLM call, pure HTTP +
JSON-RPC plumbing. Stdout is what Hermes's cron delivery posts to
Discord.

Schema-reality reframe (per 6-10-design-decision.md §3): mailbot-api is
the source of truth for the pending queue; Hermes is the thin transport.
Single-attempt-per-tick (§4 Q4): ack as ok immediately after formatting;
if the cron's downstream delivery to Discord fails, the cron job's own
retry policy handles it.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from _mcp_client import (
    DEFAULT_BASE_URL,
    MCPCallError,
    log_event,
    open_session,
    tool_call,
)

DEFAULT_PULL_LIMIT = 10


def format_for_discord(notification: dict[str, Any]) -> str:
    """Render one notification row as a Discord-ready line.

    Story 6-3's `category` is load-bearing for Story 6-4's anti-fatigue
    (mute / dedup / quiet-hours), but it's also useful context for the
    operator reading the alert. Format: `[category] message`.
    """
    category = notification.get("category", "unknown")
    message = notification.get("message", "(empty)")
    return f"[{category}] {message}"


def main() -> int:
    base_url = os.environ.get("MAILBOT_MCP_URL", DEFAULT_BASE_URL)
    # P5: a whitespace-only env var (e.g., `MAILBOT_ROUTER_KEY="   "` from a
    # botched shell-quoting) passes a bare truthiness check; strip first so
    # the missing-key event fires instead of sending a Bearer of spaces.
    api_key = os.environ.get("MAILBOT_ROUTER_KEY", "").strip()
    if not api_key:
        log_event("cron.pull.missing_api_key")
        # Exit 0 — cron retries on next tick. Missing env vars during
        # bootstrap shouldn't crash the cron job into a back-off state.
        return 0

    try:
        limit = int(os.environ.get("MAILBOT_PULL_LIMIT", str(DEFAULT_PULL_LIMIT)))
    except ValueError:
        limit = DEFAULT_PULL_LIMIT

    try:
        session_id = open_session(base_url, api_key, "mailbot-cron-pull")
    except MCPCallError as exc:
        log_event("cron.pull.session_open_failed", error=str(exc))
        return 0

    try:
        pull_result = tool_call(
            base_url,
            api_key,
            session_id,
            "pull_pending_notifications",
            {"limit": limit},
        )
    except MCPCallError as exc:
        log_event("cron.pull.pull_call_failed", error=str(exc))
        return 0

    notifications = pull_result.get("notifications", [])
    if not isinstance(notifications, list):
        log_event("cron.pull.unexpected_shape", payload_keys=list(pull_result))
        return 0

    if not notifications:
        # Empty tick — per design-decision §4 Q2, stay silent (no log).
        return 0

    # P1: stdout must flush BEFORE we ack any row. Sequence:
    #   1. format every claimed row into a stdout line,
    #   2. flush stdout (this is what Hermes's cron delivery posts to Discord),
    #   3. THEN ack each row.
    # If the process dies between (2) and (3), the row stays `delivering` and
    # Story 6-3's recovery sweep flips it back to `pending` for re-pull —
    # at-least-once delivery preserved. The previous ack-inside-the-format-loop
    # ordering risked silent loss (acked but Discord write never happened).
    delivered: list[tuple[int, str]] = []
    for notification in notifications:
        if not isinstance(notification, dict):
            continue
        notification_id = notification.get("id")
        # P8: `bool` is a subclass of `int` in Python. A malformed server
        # response with `id: true` would slip past a bare isinstance(int)
        # check and we'd ack notification_id=1 (silently corrupting state).
        if not isinstance(notification_id, int) or isinstance(notification_id, bool):
            continue
        delivered.append((notification_id, format_for_discord(notification)))

    # Stdout is what Hermes's cron delivery posts to Discord. Flush BEFORE acks.
    if delivered:
        sys.stdout.write("\n".join(line for _, line in delivered))
        sys.stdout.write("\n")
        sys.stdout.flush()

    # P2: inspect the ack response. The verb returns `ok=False` when the row
    # wasn't in `delivering` state at ack time (recovery sweep flipped it
    # back to `pending`, or another puller claimed it). That's the race-loss
    # signal Story 6-3 CR HIGH-2 surfaced — emit the documented event.
    for notification_id, _ in delivered:
        try:
            ack_result = tool_call(
                base_url,
                api_key,
                session_id,
                "ack_notification",
                {
                    "notification_id": notification_id,
                    "delivery_status": "ok",
                },
            )
        except MCPCallError as exc:
            log_event(
                "cron.pull.ack_failed",
                notification_id=notification_id,
                error=str(exc),
            )
            continue

        if not ack_result.get("ok", False):
            log_event(
                "notification.ack.race_loss",
                notification_id=notification_id,
                final_status=ack_result.get("final_status"),
                error=ack_result.get("error"),
            )

    log_event(
        "cron.pull.delivered",
        count=len(delivered),
        ids=[nid for nid, _ in delivered],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
