"""Verb shim re-exporting `ask_router` per Story 2-4 AC-6.

Story 2-10 will extend this with OpenAI-shape adaptation for the
``/v1/chat/completions`` endpoint. For Story 2-4 it's a thin pass-through —
the agent-facing surface IS the Router function itself.
"""

from __future__ import annotations

from mailbot_api.router import ask_router

__all__ = ["ask_router"]
