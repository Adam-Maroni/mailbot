"""Placeholder notification surface for Story 1-8.

`send_urgent(message)` writes a JSONL row to `MAILBOT_LOGS_PATH/notifications_pending.jsonl`.
Epic 5 replaces the body with the Discord-via-Hermes integration. The function
signature stays stable across that refactor.

Why JSONL: each row is one notification; structured for the Epic 5 consumer to
read tail-style; line-delimited so partial writes are always recoverable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mailbot_api.config import get_secret_optional
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)


def _utc_iso8601() -> str:
    return utc_z_now()


def _logs_dir() -> Path:
    """Resolve the notifications-pending log directory.

    Defaults to `/var/log/mailbot` (the docker volume mount); local-dev override
    via MAILBOT_LOGS_PATH env var (e.g., `./logs`).
    """
    raw = get_secret_optional("MAILBOT_LOGS_PATH", "/var/log/mailbot")
    return Path(raw)


def send_urgent(message: str, *, kind: str = "urgent") -> None:
    """Append one notification row to notifications_pending.jsonl.

    Epic 5 will reimplement this to post to Discord via Hermes; the JSONL
    fallback survives as audit trail. The signature is the load-bearing contract.

    Idempotent on filesystem state — caller is responsible for debounce.
    """
    record = {
        "ts": _utc_iso8601(),
        "kind": kind,
        "message": message,
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

    target_dir = _logs_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error(
            "notifications dir create failed",
            extra={
                "event": "notifications.dir.create_failed",
                "error_type": type(exc).__name__,
            },
        )
        return

    target = target_dir / "notifications_pending.jsonl"
    try:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        logger.error(
            "notifications write failed",
            extra={
                "event": "notifications.write.failed",
                "error_type": type(exc).__name__,
            },
        )
        return

    logger.info(
        "notification dispatched",
        extra={
            "event": "notifications.dispatched",
            "kind": kind,
            "target": str(target),
        },
    )
