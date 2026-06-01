"""Shared secret-redaction regex constants per Story 2-1 code-review fix R9.

Originally the constants lived as private (`_`-prefixed) names in
``observability/logging.py``. Story 2-1's ``router/errors.py`` imported them
across the module boundary, which created a brittle coupling: a rename in
``logging.py`` would silently break ``errors.py`` at runtime (mypy + ruff
don't flag cross-module private imports).

Centralizing here makes the contract explicit. Both ``logging.JsonFormatter``
and ``router.errors.sanitize_error`` import from this leaf module — no
import cycle risk because this module has no internal dependencies.

Patterns enforced (per Story 2-1 AC-4 + Story 1-4 AC-5):
- ``Bearer <token>`` → ``[REDACTED_BEARER]``
- ``sk-…`` keys (Anthropic-style) → ``[REDACTED_SK_KEY]``
- URL query-param values for ``token`` / ``code`` / ``access_token`` /
  ``refresh_token`` / ``api_key`` / ``key`` / ``secret`` (Story 2-1 R2 fix
  extended the original 3-key set to the AC-4 full 6-key set; AC-4 explicit
  list also includes ``code``, retained) → key preserved, value redacted.
- File paths matching ``.env`` / ``.key`` / ``.pem`` / ``.p12`` / ``.pfx``
  (Story 2-1 R3 fix added the two cert extensions per AC-4) → redacted.
"""

from __future__ import annotations

import re

BEARER_TOKEN_RE = re.compile(r"Bearer\s+[A-Za-z0-9._-]+")

SK_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")

# AC-4 query-param key set: token, code, access_token, refresh_token, api_key,
# key, secret. The pattern captures `https?://host/path?...key=` up to the next
# `&` or whitespace so the substitution keeps the key visible.
URL_TOKEN_QUERY_RE = re.compile(
    r"(https?://[^\s?]+\?[^\s]*?"
    r"(?:token|code|access_token|refresh_token|api_key|key|secret)=)[^&\s]+",
    flags=re.IGNORECASE,
)

# Secret-file extension set: env, key, pem, p12, pfx (last two added per Story
# 2-1 R3 fix — client-cert files are secret-sensitive per AC-4).
SECRET_FILE_RE = re.compile(
    r"[/\\]?[\w/.\\-]+\.(?:env|key|pem|p12|pfx)\b",
    flags=re.IGNORECASE,
)


__all__ = [
    "BEARER_TOKEN_RE",
    "SECRET_FILE_RE",
    "SK_KEY_RE",
    "URL_TOKEN_QUERY_RE",
]
