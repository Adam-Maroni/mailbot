"""Router kill-switch verbs per Story 2-9 (`/pause` and `/resume`).

Epic 5 wires the slash-command UI; this story implements the verb-side
handlers + the Pydantic shapes they return.

Story 6-4 extension: ``resume_router`` ALSO lifts the urgent-only
notification posture (set via ``notifications.posture.set_urgent_only``).
``/resume`` is the de-facto "talk to me" signal that the urgent-only
auto-recovery rule needs; auto-lift on any-slash-command-dispatch lands
when Hermes-side instrumentation is real.

Story 9-3 extension: ``set_model_oneshot`` adds the ``/model <model>``
session-scoped one-shot override surface. OQ-1 Option B (Adam-decided
2026-06-14): the override is stored in a module-level single-slot global,
NOT a session-keyed dict. The session_id from ctx is captured for audit
trail visibility but does NOT key the lookup. This matches MailBot's
single-user deployment reality; multi-user would require introducing a
session-keyed dict + plumbing session_id through the
``/v1/chat/completions`` HTTP endpoint (see story 9-3 OQ-1 for the full
decision trail).
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from mailbot_api.notifications.posture import lift_urgent_only
from mailbot_api.router.oneshot import (
    OneShotOverride,
    _consume_oneshot_override,
    _get_active_oneshot_override,
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
)
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


# ---------------------------------------------------------------------------
# Story 9-3 — `/model <model>` one-shot dispatch verb
# ---------------------------------------------------------------------------
#
# The override-slot storage lives in `mailbot_api.router.oneshot` (router-
# internal, NOT a verb) so that `mailbot_api/router/router.py` can reach
# into it without violating Story 5-2 AC-7's verb-import isolation
# boundary. The verb (this file) is the SETTER; the router consumes.
#
# OQ-1 Option B: single-slot global per-process per Adam-decision 2026-06-14.
# The imports at the top of this file re-export the helpers from
# `router.oneshot` for tests + the MCP wrapper layer to continue importing
# them from here without touching the new module path.

_MODEL_ALIASES: Final[dict[str, str]] = {
    "qwen": "qwen2.5:3b-instruct-q4_K_M",
    "haiku": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-7",
}

_ALLOWED_FULL_MODEL_IDS: Final[frozenset[str]] = frozenset(_MODEL_ALIASES.values())


class SetModelOneShotOut(BaseModel):
    ok: bool
    model: str | None = None
    expires_at: str | None = None
    session_id: str | None = None
    error: str | None = None


def _normalize_model_id(model: str) -> str | None:
    """Return the full model ID for a shorthand alias or a known full ID.
    Returns None if the input is neither a registered alias nor a known
    full ID."""
    if model in _MODEL_ALIASES:
        return _MODEL_ALIASES[model]
    if model in _ALLOWED_FULL_MODEL_IDS:
        return model
    return None


async def set_model_oneshot(
    *,
    db_path: str,  # noqa: ARG001 — unused (no DB writes); kept for verb-signature parity
    model: str,
    session_id: str | None = None,
) -> SetModelOneShotOut:
    """Set a one-shot model override that the next ``ask_router`` call
    consumes (within the 5-min TTL).

    Per OQ-1 Option B: the override is stored in a module-level global in
    ``mailbot_api.router.oneshot``, not keyed by ``session_id``.
    ``session_id`` is captured for audit trail visibility only.
    """
    normalized = _normalize_model_id(model)
    if normalized is None:
        allowed = sorted(
            set(_MODEL_ALIASES.keys()) | _ALLOWED_FULL_MODEL_IDS
        )
        return SetModelOneShotOut(
            ok=False,
            model=None,
            error=(
                f"unknown model: {model!r}; allowed (aliases + full IDs): "
                + ", ".join(allowed)
            ),
        )
    override = _set_oneshot_override(
        model=normalized,
        session_id=session_id,
    )
    return SetModelOneShotOut(
        ok=True,
        model=normalized,
        expires_at=override.expires_at,
        session_id=session_id,
    )


__all__ = [
    "OneShotOverride",
    "PauseOut",
    "ResumeOut",
    "SetModelOneShotOut",
    "_consume_oneshot_override",
    "_get_active_oneshot_override",
    "_reset_oneshot_override_for_test",
    "_set_oneshot_override",
    "pause_router",
    "resume_router",
    "set_model_oneshot",
]
