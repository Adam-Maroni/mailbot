"""Router kill-switch verbs per Story 2-9 (`/pause` and `/resume`).

Epic 5 wires the slash-command UI; this story implements the verb-side
handlers + the Pydantic shapes they return.
"""

from __future__ import annotations

from pydantic import BaseModel

from mailbot_api.router.pause import get_pause_state


class PauseOut(BaseModel):
    ok: bool
    previously_paused: bool
    reason: str
    message: str


class ResumeOut(BaseModel):
    ok: bool
    previously_paused: bool
    message: str


async def pause_router(*, db_path: str, reason: str) -> PauseOut:
    state = get_pause_state()
    previously = state.is_paused()
    await state.pause(db_path, reason=reason)
    return PauseOut(
        ok=True,
        previously_paused=previously,
        reason=reason,
        message=(
            f"router paused — reason: {reason}"
            if not previously
            else f"router was already paused — reason updated to: {reason}"
        ),
    )


async def resume_router(*, db_path: str) -> ResumeOut:
    state = get_pause_state()
    previously = state.is_paused()
    await state.resume(db_path)
    return ResumeOut(
        ok=True,
        previously_paused=previously,
        message=(
            "router resumed" if previously else "router was not paused"
        ),
    )


__all__ = ["PauseOut", "ResumeOut", "pause_router", "resume_router"]
