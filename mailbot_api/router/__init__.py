"""Router public API per Story 2-4 AC-7.

Exported functions:
  * ``ask_router`` — primary text-dispatch entry point (Story 2-4)
  * ``dispatch_embedding`` — embeddings sibling (Story 3-4)
  * ``dispatch_tool_call`` — tool-calling sibling (Story 6-9, F11 closure)

Internal helpers (registry, pricing, escalation, policy) are accessible by
full path but not re-exported.
"""

from __future__ import annotations

from mailbot_api.router.router import (
    ask_router,
    dispatch_embedding,
    dispatch_tool_call,
)

__all__ = ["ask_router", "dispatch_embedding", "dispatch_tool_call"]
