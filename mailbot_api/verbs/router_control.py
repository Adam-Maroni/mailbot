"""Router kill-switch verbs per Story 2-9 (`/pause` and `/resume`).

Epic 5 wires the slash-command UI; this story implements the verb-side
handlers + the Pydantic shapes they return.

Story 6-4 extension: ``resume_router`` ALSO lifts the urgent-only
notification posture (set via ``notifications.posture.set_urgent_only``).
``/resume`` is the de-facto "talk to me" signal that the urgent-only
auto-recovery rule needs; auto-lift on any-slash-command-dispatch lands
when Hermes-side instrumentation is real.
"""

from __future__ import annotations

from pydantic import BaseModel

from mailbot_api.notifications.posture import lift_urgent_only
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
    posture_lifted: bool = False


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
    # Story 6-4: /resume also lifts urgent-only posture. Returns True iff
    # the posture WAS active before this call.
    posture_lifted = await lift_urgent_only(db_path=db_path)
    msg_parts = []
    if previously:
        msg_parts.append("router resumed")
    else:
        msg_parts.append("router was not paused")
    if posture_lifted:
        msg_parts.append(
            "lifted urgent-only posture — resuming normal notifications"
        )
    return ResumeOut(
        ok=True,
        previously_paused=previously,
        message="; ".join(msg_parts),
        posture_lifted=posture_lifted,
    )


__all__ = ["PauseOut", "ResumeOut", "pause_router", "resume_router"]
