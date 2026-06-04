#!/usr/bin/env python3
"""Story 6-10 — digest-prepare script for the Hermes 08:00 daily digest.

Calls MailBot's ``compose_digest`` MCP tool to fetch the 4-section
payload (unread bucketed by importance + pending Tier-2 batches + queued
important notifications + weekly artifacts) and writes it to a JSON file
the cron job's agent step reads to compose the Qwen-generated intro
paragraph.

Designed as a cron PRE-RUN script (no_agent=False on the cron job): this
script does no LLM work; the agent step that runs after this script
generates the intro via ``ask_router(task_type="daily_digest_intro")``
and posts the assembled message to Discord, then calls
``finalize_digest_delivery`` to flip queued tier='important' rows to
``ok_via_digest`` terminal status.

Empty-payload behavior (per Story 6.5 AC): if every collection is empty,
this script writes the JSON payload with empty arrays — the downstream
agent step is responsible for posting the terse fallback ("Inbox is
clean. Nothing pending. Have a good day.") instead of a blank digest.
This script's job is data fetch only.
"""

from __future__ import annotations

import json
import os
import sys

from _mcp_client import (
    DEFAULT_BASE_URL,
    MCPCallError,
    log_event,
    open_session,
    tool_call,
)

DEFAULT_OUTPUT_PATH = "/opt/data/cron/output/digest-payload.json"


def main() -> int:
    base_url = os.environ.get("MAILBOT_MCP_URL", DEFAULT_BASE_URL)
    # P5: strip whitespace-only env vars (see pull_and_deliver.py same fix).
    api_key = os.environ.get("MAILBOT_ROUTER_KEY", "").strip()
    output_path = os.environ.get("MAILBOT_DIGEST_OUTPUT", DEFAULT_OUTPUT_PATH)

    if not api_key:
        log_event("cron.digest.missing_api_key")
        # Exit non-zero so the cron job's agent step does NOT proceed with
        # a stale or absent payload. The digest is daily, not high-cadence;
        # surfacing the bootstrap-misconfiguration loudly is the right move.
        return 1

    try:
        session_id = open_session(base_url, api_key, "mailbot-cron-digest")
    except MCPCallError as exc:
        log_event("cron.digest.session_open_failed", error=str(exc))
        return 1

    try:
        payload = tool_call(
            base_url, api_key, session_id, "compose_digest", {}
        )
    except MCPCallError as exc:
        log_event("cron.digest.compose_call_failed", error=str(exc))
        return 1

    # Write the payload atomically: write to a tmp file in the same dir,
    # then os.replace() over the target. Prevents the agent step from
    # reading a half-written JSON file if the cron tick is killed mid-write.
    tmp_path = output_path + ".tmp"
    try:
        # P6: a bare filename (e.g., MAILBOT_DIGEST_OUTPUT="digest.json")
        # makes os.path.dirname return "" which makes os.makedirs raise
        # FileNotFoundError. Guard with the walrus so we only call makedirs
        # when there's a real parent directory to create.
        if dirname := os.path.dirname(output_path):
            os.makedirs(dirname, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp_path, output_path)
    except OSError as exc:
        # P4: clean up the .tmp file on any OSError during write/replace.
        # Without this, a partial JSON file is left on disk; a later run
        # whose own write fails could see os.replace install the stale
        # half-written file. suppress FileNotFoundError because the .tmp
        # may not have been created at all (e.g., makedirs failed first).
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        log_event(
            "cron.digest.write_failed", path=output_path, error=str(exc)
        )
        return 1

    log_event(
        "cron.digest.payload_written",
        path=output_path,
        unread_high=len(
            payload.get("unread_by_importance", {}).get("high", [])
        ),
        unread_medium=len(
            payload.get("unread_by_importance", {}).get("medium", [])
        ),
        unread_low=len(
            payload.get("unread_by_importance", {}).get("low", [])
        ),
        pending_tier2_count=len(payload.get("pending_tier2_batches", [])),
        queued_important_count=len(
            payload.get("queued_important_notifications", [])
        ),
    )

    # Hermes's cron-with-agent contract: pre-run script stdout becomes the
    # agent's prompt input. Empty stdout = "script produced no output, skipping
    # AI call" (verified live 2026-06-04 in cron.scheduler logs). So we MUST
    # write the payload to stdout — the file-write above stays as a debugging
    # side-channel, but the agent reads from stdin via the prompt.
    sys.stdout.write(json.dumps(payload, indent=2))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
