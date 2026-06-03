"""Analytics verbs surface — Story 6-8 + AR-ANALYTICS-1.

Per **AR-ANALYTICS-1** (architecture inventory):

  ``mailbot-api`` ships with ``numpy`` and ``matplotlib`` for tabular analysis
  and chart rendering over the local mailbox + ``router_calls``. These libraries
  are **not alternatives to the verb API or the Router**: any analysis that hits
  the LLM still goes through ``ask_router``; any raw email body still goes
  through ``hydrate_email`` (Rule J); any chart that needs LLM-derived data
  reads cached derived-field columns (Rule A) — never re-derives. New
  "analytics verbs" live in ``mailbot_api/verbs/analytics/`` and return either
  structured Pydantic models OR a ``(bytes, mime_type)`` tuple for chart PNGs.
  Charts posted to Discord by Hermes are subject to the same chat-input
  redactor (FR-4.7) on any inline text labels rendered onto the image.
  ``pandas`` is explicitly deferred until a future story justifies it (most
  tabular shaping is cleaner as raw SQL).

Per **AR-ANALYTICS-2**: matplotlib's ``Agg`` non-interactive backend
(``matplotlib.use("Agg")``) — no GUI dependencies. PNGs returned as bytes
(never written to disk on ``mailbot-api``); Hermes posts them as Discord
attachments. Standard chart dimensions: 1200×800 px @ 100 DPI.

Future analytics verbs added here MUST:

1. Use ``matplotlib.use("Agg")`` BEFORE any ``matplotlib.pyplot`` import.
2. Be on the ``_MATPLOTLIB_PYPLOT_ALLOW`` allowlist in
   ``scripts/check_boundaries.py`` (the only modules allowed to import
   ``matplotlib.pyplot``).
3. Return ``bytes`` directly — never write PNGs to disk.
4. Call ``plt.close(fig)`` after every ``fig.savefig`` to release the agg
   renderer cache (long-running worker process memory hygiene).
"""

from __future__ import annotations

from mailbot_api.verbs.analytics.render_spend_chart import (
    RenderSpendChartOut,
    render_spend_chart,
)

__all__ = ["RenderSpendChartOut", "render_spend_chart"]
