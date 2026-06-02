"""count_emails read verb — Story 5-1 AC-5.

Returns the count of emails matching `filter` — no projections, just the count.
Cheap signal for "how many emails match X?" without paying for row reads.
Uses the same WHERE-clause builder as find_emails for filter parity.
"""

from __future__ import annotations

from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import COUNT_EMAILS_SELECT_BASE
from mailbot_api.verbs.find_emails import _build_where_and_params
from mailbot_api.verbs.schemas import (
    CountEmailsOut,
    FindEmailsFilter,
)


async def count_emails(filter: FindEmailsFilter, *, db_path: str) -> CountEmailsOut:
    """Return COUNT(*) of emails matching `filter` (soft-deleted excluded)."""
    where_frag, params = _build_where_and_params(filter)
    sql = f"{COUNT_EMAILS_SELECT_BASE}{where_frag}"
    row = await fetchone(db_path, sql, tuple(params))
    count = int(row[0]) if row is not None else 0
    return CountEmailsOut(ok=True, count=count)


__all__ = ["count_emails"]
