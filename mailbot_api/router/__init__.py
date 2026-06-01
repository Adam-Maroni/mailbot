"""Router public API per Story 2-4 AC-7.

The ONLY exported function is ``ask_router``. Internal helpers (registry,
pricing, escalation, policy) are accessible by full path but not re-exported.
"""

from __future__ import annotations

from mailbot_api.router.router import ask_router

__all__ = ["ask_router"]
