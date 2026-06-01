"""Single read site for environment variables and secrets per AR-PAT-1 Rule F.

`os.environ` access anywhere else in `mailbot_api/` is forbidden — ruff rule + the
boundary-check script (`scripts/check_boundaries.py`) both flag violations.

Why: keeps the secrets read surface trivially auditable. Swapping `.env` for a
vault later is localized to this file (NFR-SEC-5).
"""

from __future__ import annotations

import os


class SecretMissing(RuntimeError):
    """Raised when a required environment variable is unset.

    The agent process surfaces this as a `RouterError(code="provider_error",
    message="secret missing: <name>")` at the verb boundary — never the raw
    exception (NFR-SEC-4).
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"Required secret is unset: {name}")
        self.name = name


def get_secret(name: str) -> str:
    """Read a required secret from the environment.

    Raises SecretMissing if the env var is unset or empty.
    """
    value = os.environ.get(name, "")
    if not value:
        raise SecretMissing(name)
    return value


def get_secret_optional(name: str, default: str = "") -> str:
    """Read an optional env var, returning default if unset/empty.

    Use for non-secret config that has a sensible fallback (e.g., a port number
    that defaults to 8000). For actual secrets, always use `get_secret`.
    """
    return os.environ.get(name, default) or default
