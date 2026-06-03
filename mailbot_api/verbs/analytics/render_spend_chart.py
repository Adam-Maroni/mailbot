"""``render_spend_chart`` verb — Story 6-8 (`/spend [period]` analytics).

Reads ``router_calls`` via ``db/queries.py.ROUTER_CALLS_BY_TASK_SINCE`` (raw
SQL — no pandas, per AR-BOOT-2 deferral), groups cost by ``task_type`` over the
period, and renders a horizontal bar chart at 1200×800 px @ 100 DPI via
matplotlib's ``Agg`` backend.

Window computed in Python — ``period`` maps to ``_period_window_start(period)``;
SQL filter is ``ts >= ?``. No new SQL constant added (the Story 2-10
``ROUTER_CALLS_BY_TASK_SINCE`` is reused).

Per AR-ANALYTICS-2: PNG bytes are returned via ``BytesIO`` — never written to
disk. ``plt.close(fig)`` follows every ``fig.savefig`` so the agg renderer
cache doesn't leak in the long-running worker process.

Module-load discipline (CRITICAL ordering):

  ``import matplotlib; matplotlib.use("Agg")`` MUST run BEFORE
  ``import matplotlib.pyplot as plt``. Once pyplot imports, the backend is
  resolved; calling ``use()`` afterward warns and is ignored.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import base64

import matplotlib.pyplot as plt  # noqa: E402 — Agg backend MUST be set first
import matplotlib.ticker as mticker  # noqa: E402
from pydantic import BaseModel, field_serializer

from mailbot_api.db import connection, queries
from mailbot_api.router.budget import MONTHLY_HARD_CAP_USD

_Period = Literal["today", "week", "month"]


class RenderSpendChartOut(BaseModel):
    """Result of ``render_spend_chart(period)``.

    ``image_bytes`` is the PNG payload (1200×800 @ 100 DPI). ``top_task`` is
    the highest-spending ``task_type`` over the period, or ``""`` when the
    period had no spend. ``top_task_usd`` is the cost of ``top_task`` (0.0
    when ``task_count == 0``) so Discord-side dispatchers can render the
    documented summary line `"$X.XX spent {period}. Top task: {top_task}
    (${Y.YY}). Cap: $30."` from this shape alone — no sibling MCP call to
    ``cost_breakdown`` required (which also matters because ``cost_breakdown``
    does not support ``period="week"``).

    CR HIGH-1 fix: ``image_bytes`` carries raw ``bytes`` at the Python layer
    and a ``field_serializer`` base64-encodes them at JSON-serialization
    time. A bare ``bytes`` field with no serializer would crash
    ``pydantic_core.to_json`` with a non-UTF-8 sequence error on every real
    ``/spend`` invocation (PNG magic bytes ``\\x89PNG`` are non-UTF-8).
    Pydantic's ``Base64Bytes`` was the reviewer's first suggestion but it
    DECODES on input (assumes raw bytes ARE base64-encoded already), which
    inverts the semantics — we want raw-in, base64-out.
    """

    mime_type: Literal["image/png"] = "image/png"
    image_bytes: bytes
    period: str
    total_usd: float
    task_count: int
    top_task: str
    top_task_usd: float = 0.0

    @field_serializer("image_bytes", when_used="json")
    def _serialize_image_bytes_to_b64(self, value: bytes) -> str:
        """Base64-encode the raw PNG bytes for JSON transport (MCP wire).

        ``when_used="json"`` keeps Python-side consumers receiving raw bytes
        from ``model_dump(mode="python")`` and direct attribute access;
        only ``model_dump_json()`` / ``model_dump(mode="json")`` triggers
        the base64 step that FastMCP's transport layer requires.
        """
        return base64.b64encode(value).decode("ascii")


def _period_window_start(period: _Period) -> str:
    """ISO-8601 UTC timestamp marking the start of the window.

    ``today`` → today's 00:00:00 UTC.
    ``week``  → 7 days ago at the current UTC time (rolling window).
    ``month`` → first-of-month at 00:00:00 UTC.

    Raises ``ValueError`` for any other input (defensive; the ``Literal``
    annotation enforces this at type-check time but MCP-decoded JSON at
    runtime needs an explicit guard — pattern matches Story 2-10 ``cost.py``
    + Story 5-6 CR-2 fix).
    """
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.strftime("%Y-%m-%dT00:00:00Z")
    if period == "week":
        seven_days_ago = now - timedelta(days=7)
        return seven_days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    if period == "month":
        return now.strftime("%Y-%m-01T00:00:00Z")
    raise ValueError(
        f"render_spend_chart: invalid period {period!r}; "
        "expected 'today', 'week', or 'month'"
    )


def _period_label(period: _Period) -> str:
    if period == "today":
        return "Today"
    if period == "week":
        return "Last 7 Days"
    if period == "month":
        return "This Month"
    raise ValueError(f"render_spend_chart: invalid period {period!r}")


def _render_empty_png() -> bytes:
    """Render a 1200×800 chart with a single 'no spend' label.

    Skips the bar-chart path entirely; just lays down a centered message so
    the Discord-side dispatcher always has a valid PNG to attach (defensive
    against the empty-data crash path).
    """
    fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
    try:
        ax.text(
            0.5,
            0.5,
            "No spend recorded for this period",
            ha="center",
            va="center",
            fontsize=24,
        )
        ax.set_axis_off()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        return buf.getvalue()
    finally:
        plt.close(fig)


def _render_bar_chart_png(
    *,
    period: _Period,
    rows_desc: list[tuple[str, float]],
    total_usd: float,
) -> bytes:
    """Horizontal bar chart at 1200×800 px @ 100 DPI.

    ``rows_desc`` is sorted descending by cost; after ``invert_yaxis()`` the
    highest-cost task lands at the top of the chart.
    """
    task_types = [row[0] for row in rows_desc]
    costs = [row[1] for row in rows_desc]

    fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
    try:
        ax.barh(task_types, costs)
        ax.invert_yaxis()  # highest-cost at top
        ax.set_xlabel("Cost (USD)")
        # AR-ANALYTICS-1 defense-in-depth: chart labels SHOULD pass through the
        # Story 5-7 chat-input redactor before being baked into the PNG.
        # Currently deferred (Story 6-8 CR LOW-3) because task_type values are
        # project-internal policy.yaml enum strings — not user input. Wire in
        # when a future analytics verb introduces user-derived text on labels
        # (e.g., sender-address labels on a per-sender chart).
        ax.set_title(
            f"Spend by Task — {_period_label(period)} (${total_usd:.2f} total)"
        )
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))

        if period == "month":
            # Defender-toned subtitle noting the monthly cap.
            ax.text(
                0.5,
                1.02,
                f"${total_usd:.2f} of ${MONTHLY_HARD_CAP_USD:.0f} month cap",
                transform=ax.transAxes,
                ha="center",
                va="bottom",
                fontsize=10,
                style="italic",
            )

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        return buf.getvalue()
    finally:
        plt.close(fig)


async def render_spend_chart(
    period: _Period, *, db_path: str
) -> RenderSpendChartOut:
    """Render a per-task cost chart for the period and return as PNG bytes.

    Reads ``router_calls`` raw via ``ROUTER_CALLS_BY_TASK_SINCE`` (Story 2-10
    SQL constant). Sort is performed in Python after the SQL ``GROUP BY``
    (SQLite's GROUP BY does not guarantee ordering).
    """
    since = _period_window_start(period)

    per_task_rows = await connection.fetchall(
        db_path, queries.ROUTER_CALLS_BY_TASK_SINCE, (since,)
    )

    # Coerce SQL row tuples to (task_type: str, cost: float) and drop empty
    # task_types defensively (router_calls.task_type is NOT NULL per Story
    # 2-1 schema, but a NULL row would crash the bar-label rendering).
    rows = [
        (str(row[0]), float(row[1]))
        for row in per_task_rows
        if row[0] is not None
    ]
    rows.sort(key=lambda r: r[1], reverse=True)

    total_usd = sum(cost for _, cost in rows)
    task_count = len(rows)
    top_task = rows[0][0] if rows else ""
    top_task_usd = rows[0][1] if rows else 0.0

    if task_count == 0:
        image_bytes = _render_empty_png()
    else:
        image_bytes = _render_bar_chart_png(
            period=period, rows_desc=rows, total_usd=total_usd
        )

    return RenderSpendChartOut(
        mime_type="image/png",
        image_bytes=image_bytes,
        period=period,
        total_usd=total_usd,
        task_count=task_count,
        top_task=top_task,
        top_task_usd=top_task_usd,
    )


__all__ = ["RenderSpendChartOut", "render_spend_chart"]
