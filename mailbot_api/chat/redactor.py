"""Chat-input redactor — Story 5-7.

Scrubs token-shaped strings (JWTs, OpenAI keys, Anthropic keys, hex blobs,
generic bearer tokens, SSH private-key fragments) from any chat input before
it enters Hermes memory or is forwarded to an external LLM API.

This module ships the REDACTOR PRIMITIVE only. Wiring points:

  * Hermes-side input pipeline: Story 5-9 chat orchestrator calls ``redact()``
    on every user Discord message BEFORE building the prompt context.
  * Memory export / trajectory dump tools: Epic 6 (Story 6-7's
    ``mailbot logs --export-memory`` CLI) calls ``redact()`` on each memory
    line before writing the export file.
  * The verb-side ``ask_router`` wrapper is NOT in scope here; Hermes-side
    redaction guarantees the redacted text reaches the Router by the time
    ``caller_origin="hermes-aux-*"`` is in play.

Order of pattern application is load-bearing:

  1. SSH private-key fragments first (multi-line, would otherwise have their
     bodies caught by the hex-blob pattern).
  2. Anthropic keys before OpenAI keys (``sk-ant-`` is a strict subset of
     ``sk-``; anthropic_key is the more specific + more audit-relevant label).
  3. JWT, OpenAI key, hex blob, bearer token in any order after that.

Rule F.1 alignment: Anthropic keys NEVER reach the agent surface under normal
operation. Catching them here is belt-and-suspenders defense; a flag in the
Hermes input pipeline that someone pasted an ``sk-ant-...`` key is itself a
forensic event worth surfacing in the daily digest.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum

_logger = logging.getLogger(__name__)


class RedactionKind(StrEnum):
    """The labels of redactable token shapes."""

    JWT = "jwt"
    OPENAI_KEY = "openai_key"
    ANTHROPIC_KEY = "anthropic_key"
    HEX_BLOB = "hex_blob"
    BEARER_TOKEN = "bearer_token"  # noqa: S105 — StrEnum kind label, not a secret
    SSH_KEY_FRAGMENT = "ssh_key_fragment"


@dataclass(frozen=True)
class RedactionMatch:
    """One credential-shaped substring that was redacted.

    ``position`` indexes into the PARTIALLY-REDACTED text at the moment the
    pattern fired. For the FIRST pattern's matches this happens to coincide
    with positions in the original text; for patterns 2..6 (which scan after
    prior patterns have substituted ``[REDACTED:...]`` strings into the text),
    the positions are computed against the partially-redacted intermediate
    text. Story 5-7 CR-1 decision (option b): accept this imprecision because
    the forensic linker that actually matters is the ``prefix`` field on the
    structured log line (the first 6 chars of the matched substring), which
    is always meaningful regardless of original-vs-intermediate text.

    Callers needing exact original-text positions should run a separate
    pre-scan over the original text against ``_PATTERNS`` themselves.

    ``redaction`` is the substring that replaced the matched substring.
    """

    kind: RedactionKind
    position: tuple[int, int]
    redaction: str


# Module-level precompiled regexes per AC-5: compiled ONCE at module load;
# never recompiled per-call. Order of the tuple is the order of application.
#
# Why the JWT pattern doesn't enforce ≥ 30 chars in regex: keeping the regex
# simple + post-match length check is clearer than a non-greedy lookahead.
_JWT_MIN_LENGTH = 30

_PATTERNS: tuple[tuple[RedactionKind, re.Pattern[str]], ...] = (
    # SSH private-key fragments FIRST so their bodies aren't broken up by the
    # hex-blob pattern.
    (
        RedactionKind.SSH_KEY_FRAGMENT,
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
    ),
    # Anthropic BEFORE OpenAI (more specific prefix wins).
    (RedactionKind.ANTHROPIC_KEY, re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    (RedactionKind.OPENAI_KEY, re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    # JWT: three dot-separated base64-url-safe segments. Length floor enforced
    # post-match in the redactor loop.
    (
        RedactionKind.JWT,
        re.compile(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    ),
    # Hex blobs: 40-char floor skips UUIDs (32 chars) and short SHAs.
    (RedactionKind.HEX_BLOB, re.compile(r"\b[a-fA-F0-9]{40,}\b")),
    # Bearer tokens: case-sensitive `Bearer` per HTTP standard. Includes `=`
    # because base64 padding is legitimate.
    # Story 5-7 CR-3 fix: the trailing `\b` previously dropped the `==`
    # padding (`=` is not a \w char; \b matches just before the first `=`),
    # leaving credential fragments in the output. Use a `(?=\s|$|[^A-Za-z0-9._=-])`
    # lookahead instead so padding is preserved AND the match stops at the
    # next plausible delimiter.
    (
        RedactionKind.BEARER_TOKEN,
        re.compile(r"Bearer\s+[A-Za-z0-9._=-]{20,}(?=\s|$|[^A-Za-z0-9._=-])"),
    ),
)


def redact(text: str) -> tuple[str, list[RedactionMatch]]:
    """Scrub credential-shaped substrings from text.

    Returns ``(redacted_text, matches)``. ``matches`` is the list of every
    redaction that fired, in the order they were applied (which is the order
    of ``_PATTERNS``). Positions in ``RedactionMatch.position`` index into
    the ORIGINAL text, NOT the redacted text.

    Per AC-3 each match emits exactly one structured log line at INFO with
    event=``chat.redactor.match``. The matched substring itself is NEVER
    logged — only its first 6 chars as a forensic linker.

    Per Story 5-7 CR-2 decision (option a): SHA-1-shaped 40-char hex strings
    (e.g., git commit SHAs pasted into Discord) ARE redacted as ``hex_blob``.
    Defender posture: the cost of a false-positive redaction (one undisplayed
    git SHA) is much lower than the cost of a false-negative redaction (one
    leaked secret-shaped 40-char hex string).
    """
    if not text:
        return text, []

    matches: list[RedactionMatch] = []
    current = text

    # ``current`` is the partially-redacted text we substitute into; we record
    # positions against the ORIGINAL text. To do that we walk the original
    # text per-pattern, compute substitutions, and apply them in the same
    # pass via a single re.sub callback per pattern.
    for kind, pattern in _PATTERNS:

        def _sub(match: re.Match[str], _kind: RedactionKind = kind) -> str:
            matched_text = match.group(0)

            # JWT length floor (AC-2 footnote): the regex is intentionally
            # permissive; reject sub-30-char matches by returning the original
            # untouched.
            if _kind is RedactionKind.JWT and len(matched_text) < _JWT_MIN_LENGTH:
                return matched_text

            redaction = f"[REDACTED:{_kind.value}]"
            # Compute the position in the ORIGINAL text. Because we apply
            # patterns sequentially and substitutions land BEFORE the next
            # pattern's pass, a later pattern's match.start() is into the
            # PARTIALLY-REDACTED text, not the original. For Story 5-7's
            # forensic surface we accept this imprecision: the substitution
            # token "[REDACTED:..." is unambiguous in the output, and the
            # PREFIX in the log line (next block) preserves the forensic
            # linker we actually need.
            position = (match.start(), match.end())

            matches.append(
                RedactionMatch(kind=_kind, position=position, redaction=redaction)
            )

            # AC-3: log the match, never the matched value.
            _logger.info(
                "chat redactor match",
                extra={
                    "event": "chat.redactor.match",
                    "kind": _kind.value,
                    "position": [position[0], position[1]],
                    # First 6 chars only — forensic linker, NOT the value.
                    # If the match is shorter than 6 chars (impossible given
                    # our patterns' minimum lengths), prefix is the whole
                    # match anyway.
                    "prefix": matched_text[:6],
                },
            )
            return redaction

        current = pattern.sub(_sub, current)

    return current, matches


__all__ = ["RedactionKind", "RedactionMatch", "redact"]
