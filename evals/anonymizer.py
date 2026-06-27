"""Story 9-5 AC-6: regex-based PII anonymization for production-sampled emails.

The anonymizer replaces 7 PII shapes in a deterministic order with stable
``<token-NNN>`` placeholders. The replacement counters are seeded by the
``seed`` argument so re-runs against the same item are reproducible — same
input + same seed yields byte-identical output.

This module is the single source of truth for the PII contract:
  * ``scripts/build_corpus.py from-csv`` runs the anonymizer on every
    ``raw_body`` before the row is appended to the corpus JSONL.
  * ``tests/unit/evals/test_corpus_integrity.py::test_no_pii_in_committed_corpus``
    imports ``_REGEXES`` and runs them against the gitted canary fixture
    + the .example file to assert zero PII-shape matches survived to PR time.

Architectural choice — regex, NOT LLM-based:
  LLM-based anonymization would mean Adam's real inbox content traverses a
  third-party API. The whole point of the privacy treatment is to keep it
  on-host. Adam's review pass catches false negatives the regex misses
  (sentence-internal "we shipped 5551234567 units" — the test for that
  case documents the accepted false-positive risk).
"""

from __future__ import annotations

import hashlib
import re
from typing import Pattern

# Pattern order matters (AC-6): URLs first so query-string emails inside
# tokenized URLs don't get double-replaced; then email / phone / SSN /
# credit-card / address. SSN is matched BEFORE credit-card because the
# SSN shape ``NNN-NN-NNNN`` would otherwise be partially captured by the
# credit-card-like-digit-run when the body has no hyphens. The dict is
# iterated in insertion order (Python 3.7+ guarantee).
_REGEXES: dict[str, Pattern[str]] = {
    "url_with_tokens": re.compile(
        # URLs with ?token= / ?key= / ?api_key= / ?access_token= / similar
        r"https?://[^\s<>]+\?(?:[^=\s]*(?:token|key|secret|password|auth|sig|signature)"
        r"[^=\s]*=[^\s&<>]+)(?:&[^\s<>]+)?",
        re.IGNORECASE,
    ),
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "ssn": re.compile(
        # ``NNN-NN-NNNN`` — placed BEFORE phone to win the digit-substring race
        # for substrings like ``123-45-6789``; the phone regex's first group
        # is 3 digits + dash so the SSN substring would otherwise partially
        # match. Word-boundary anchors prevent matching inside longer numbers.
        r"\b\d{3}-\d{2}-\d{4}\b"
    ),
    "credit_card": re.compile(
        # ``NNNN-NNNN-NNNN-NNNN`` (also with spaces) OR a no-separator 16-digit run.
        r"\b(?:\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})\b"
    ),
    "phone": re.compile(
        # ``+CC NNN-NNN-NNNN`` / ``(NNN) NNN-NNNN`` / ``NNN-NNN-NNNN`` /
        # ``NNN.NNN.NNNN`` — placed after SSN + credit-card so digit-substring
        # collisions resolve to the more-specific shape.
        r"(?:\+\d{1,3}[\s.-]?)?"
        r"(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}\b"
    ),
    "address": re.compile(
        # ``<number> <Street-name> <Street-type>, <City>, <State?>`` —
        # rough US/CA/FR-shape postal address. Catches the common newsletter
        # footer pattern ``123 Main St, Anytown, CA 12345``. False positives
        # are inevitable; Adam's review pass + the AC-9 `validate --strict`
        # invariant catch what the regex misses.
        r"\b\d{1,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s+"
        r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|"
        r"Way|Pl|Place|Ct|Court|Sq|Square|Pkwy|Parkway|Hwy|Highway|"
        r"Rue|Avenue|Boulevard|Place|Chemin|Allee)"
        r"(?:,\s*[A-Z][A-Za-z]+){1,3}"
        r"(?:\s+[A-Z]{2})?"
        r"(?:\s+\d{5}(?:-\d{4})?)?"
    ),
}


def _deterministic_counter(seed: str | None, kind: str) -> int:
    """Stable starting counter when ``seed`` is provided.

    The counter is reset per ``kind`` — emails start at 001, phones at 001,
    etc. The ``seed`` salts only the visible starting number (we want some
    variation across seeds so anonymized outputs aren't trivially reversible
    by counter-position alone).
    """
    if seed is None:
        return 1
    digest = hashlib.sha256(f"{seed}|{kind}".encode("utf-8")).hexdigest()
    return int(digest[:4], 16) % 900 + 1  # 001-999


def anonymize(raw_text: str, *, seed: str | None = None) -> str:
    """Apply the 7-pattern PII pass.

    Each pattern is applied with a per-kind counter that increments on each
    replacement, producing stable ``<email-001>``, ``<phone-001>``, etc.
    suffixes. When ``seed`` is None the counter starts at 1; when ``seed``
    is provided, the per-kind starting counter is derived from
    ``sha256(seed + kind)`` for deterministic (but non-trivial) ordering.

    Returns the anonymized string. The pattern order is documented in
    ``_REGEXES`` insertion order — DO NOT reorder without re-reviewing the
    SSN-vs-credit-card-vs-phone digit-substring collision logic.
    """
    counters: dict[str, int] = {
        kind: _deterministic_counter(seed, kind) for kind in _REGEXES
    }
    suffix_by_kind: dict[str, str] = {
        "url_with_tokens": "url-with-tokens",
        "email": "email",
        "ssn": "ssn",
        "credit_card": "cc",
        "phone": "phone",
        "address": "address",
    }
    out = raw_text
    for kind, pattern in _REGEXES.items():
        token_prefix = suffix_by_kind[kind]
        # Walk-discovered finding 2026-06-27: the original ``<email-NNN@example.com>``
        # template is itself email-shaped, so the email regex catches its own
        # output → ``validate --strict`` flags every anonymized email as a PII
        # match. Changed to ``<email-NNN-redacted>`` (no ``@`` and no ``.com``)
        # which is regex-immune and still operator-readable.
        template = f"<{token_prefix}-{{n:03d}}-redacted>"

        def _replace(_match: re.Match[str], _kind: str = kind) -> str:
            n = counters[_kind]
            counters[_kind] = n + 1
            return template.format(n=n)

        out = pattern.sub(_replace, out)
    return out


__all__ = ["_REGEXES", "anonymize"]
