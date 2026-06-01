"""One-shot smoke script to verify the Microsoft Graph OAuth pipeline (Story 1-5 AC-2).

Reads OUTLOOK_* env vars (via mailbot_api.config.get_secret), exchanges the
refresh token, and calls /me. Prints the displayName + userPrincipalName via
the structured logger. Exits 0 on success, non-zero on auth failure.

Usage:
    # Locally:
    python scripts/check_graph_auth.py

    # Inside the docker stack:
    docker compose exec mailbot-api python scripts/check_graph_auth.py
"""

from __future__ import annotations

import sys

from mailbot_api.config import SecretMissing
from mailbot_api.observability.logging import configure_logging
from mailbot_api.sync.graph_client import GraphAuthError, GraphClient


def main() -> int:
    configure_logging()
    try:
        client = GraphClient()
    except SecretMissing as exc:
        print(  # noqa: T201 — scripts/ may print
            f"FATAL: required secret unset: {exc.name}. "
            f"Set OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_REFRESH_TOKEN "
            f"in your .env (see .env.example). OUTLOOK_CLIENT_SECRET is only "
            f"required for confidential clients (Web platform).",
            file=sys.stderr,
        )
        return 2

    try:
        me = client.me()
    except GraphAuthError as exc:
        print(  # noqa: T201
            f"FATAL: Graph auth failed — code={exc.code} message={exc.message}",
            file=sys.stderr,
        )
        return 1

    # Print summary line — full details land in the structured logger.
    print(  # noqa: T201
        f"OK: signed in as {me.get('displayName')!r} ({me.get('userPrincipalName')!r})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
