"""find_emails read verb — Story 5-1 AC-1.

Projection-first filter (Rule J). Returns EmailProjection rows only — bodies
require a separate hydrate_email call. All filter clauses are parameterized
via ? placeholders; the WHERE clause is composed deterministically from the
set FindEmailsFilter fields.

Rule G — the SQL prefix and column list come from mailbot_api/db/queries.py;
this file only assembles the dynamic clauses + LIMIT.
"""

from __future__ import annotations

from typing import Any

from mailbot_api.db.connection import fetchall
from mailbot_api.db.queries import FIND_EMAILS_SELECT_BASE
from mailbot_api.verbs.schemas import (
    EmailProjection,
    FindEmailsFilter,
    FindEmailsOut,
    VerbError,
)

_MAX_LIMIT = 100


def _escape_like(value: str) -> str:
    """Escape SQL LIKE metacharacters (`%`, `_`, `\\`) for safe pattern composition.

    Used by find_emails / count_emails when building `%pattern%` substring matches.
    The escape character is `\\` (matching the ``ESCAPE '\\'`` clause appended to
    every LIKE in this module).
    """
    # Order matters: escape the escape char itself FIRST, then the wildcards.
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_where_and_params(
    f: FindEmailsFilter,
) -> tuple[str, list[Any]]:
    """Return (sql_fragment, params) for the dynamic WHERE clauses.

    sql_fragment starts with `` (empty) or ` AND col = ?`-style strings that
    get appended to FIND_EMAILS_SELECT_BASE. params is a list with one entry
    per `?` in sql_fragment, in the same order.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if f.sender_address is not None:
        clauses.append("from_address = ?")
        params.append(f.sender_address)
    if f.sender_domain is not None:
        # Suffix match on @<domain> — case-insensitive via LOWER on both sides.
        # Escape LIKE metacharacters in the user-supplied domain to prevent
        # wildcard semantics (CR finding 2: `_` in domain would match too broadly).
        domain_escaped = _escape_like(f.sender_domain.lower())
        clauses.append(r"LOWER(from_address) LIKE ? ESCAPE '\'")
        params.append(f"%@{domain_escaped}")
    if f.class_coarse is not None:
        clauses.append("class_coarse = ?")
        params.append(f.class_coarse)
    if f.importance_min is not None:
        clauses.append("importance_score >= ?")
        params.append(f.importance_min)
    if f.since is not None:
        clauses.append("received_at >= ?")
        params.append(f.since)
    if f.until is not None:
        clauses.append("received_at <= ?")
        params.append(f.until)
    if f.query is not None:
        # Substring match on subject + summary_short. The ? placeholders carry
        # the `%pattern%` form — never string-interpolated into the SQL itself.
        # CR finding 1: escape LIKE metacharacters (% / _ / \) in user input so
        # "50% off" doesn't over-match via the interior `%` wildcard.
        clauses.append(r"(subject LIKE ? ESCAPE '\' OR summary_short LIKE ? ESCAPE '\')")
        pattern = f"%{_escape_like(f.query)}%"
        params.append(pattern)
        params.append(pattern)
    if f.unread_only:
        # Story 10.7.7 (AC-1): unread == is_read = 0. NULL rows (synced before
        # migration 029) are excluded by SQLite's three-valued logic — an
        # honest posture (only claim unread when Graph actually said so). No
        # parameter needed: the literal 0 is a fixed constant, not user input.
        clauses.append("is_read = 0")

    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


def row_to_projection(row: tuple[Any, ...]) -> EmailProjection:
    """Map a fetched row to EmailProjection. Column order matches EMAIL_PROJECTION_COLUMNS.

    Public helper — exported for get_thread.py and any future read verb sharing
    the EmailProjection shape (CR finding 4: avoid private-symbol cross-module
    coupling).
    """
    return EmailProjection(
        email_id=row[0],
        received_at=row[1],
        from_address=row[2],
        from_display_name=row[3],
        subject=row[4],
        summary_short=row[5],
        class_coarse=row[6],
        importance_score=row[7],
        sensitivity=row[8],
        has_attachments=bool(row[9]),
        thread_id=row[10],  # Story 10.5.3 (F-10-4-3) — appended to EMAIL_PROJECTION_COLUMNS.
    )


async def find_emails(
    filter: FindEmailsFilter,
    *,
    db_path: str,
    limit: int = 25,
) -> FindEmailsOut:
    """Return up to `limit` email projections matching `filter`.

    Rule J — projection-only fields, no body bytes. Use hydrate_email for full
    body (rate-limited 5/turn).
    """
    if limit > _MAX_LIMIT:
        return FindEmailsOut(
            ok=False,
            error=VerbError(
                code="LIMIT_EXCEEDED",
                message="limit capped at 100 — use repeated queries with the `since` filter if you need more",
            ),
        )
    if limit < 1:
        return FindEmailsOut(
            ok=False,
            error=VerbError(code="LIMIT_INVALID", message="limit must be >= 1"),
        )

    where_frag, params = _build_where_and_params(filter)
    sql = (
        f"{FIND_EMAILS_SELECT_BASE}{where_frag} "
        f"ORDER BY received_at DESC LIMIT ?"
    )
    params.append(limit)
    rows = await fetchall(db_path, sql, tuple(params))
    return FindEmailsOut(ok=True, projections=[row_to_projection(r) for r in rows])


__all__ = ["find_emails", "row_to_projection"]
