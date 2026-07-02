#!/usr/bin/env python3
"""
Stop hook — refuses to let Claude end the turn while /autonomous-story-run
or /autonomous-epic-run is mid-flight (state file present).

Contract:
  - Reads JSON payload from stdin.
  - If state file `_bmad-output/implementation-artifacts/.autonomous-run-active.json`
    exists AND the current phase is not a terminal phase, AND the assistant's last
    turn produced no tool calls (stop_reason == "end_turn", tool_calls empty),
    block with a reason that tells the orchestrator the exact next tool call.
  - Else exit 0 (allow stop).

Terminal phases (stop allowed):
  - "phase-3.3-final-report"    — Phase 3.3 user-facing text is the FIRST allowed
                                   plain-text emission and may end a turn before
                                   the Phase 3.5 prompt fires on the next turn.
  - "phase-3.5-awaiting-verdict" — manual verification prompt is out; waiting on user.
  - "halt"                       — orchestrator hit a hard gate and emitted a HALT
                                   message intentionally.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

STATE_FILE_REL = "_bmad-output/implementation-artifacts/.autonomous-run-active.json"
TERMINAL_PHASES = {"phase-3.3-final-report", "phase-3.5-awaiting-verdict", "halt"}


def _emit(decision: str | None = None, additional_context: str | None = None) -> None:
    """Write the hook response JSON to stdout and exit 0."""
    payload: dict[str, object] = {}
    if decision is not None:
        payload["decision"] = decision
        payload["reason"] = (
            "Autonomous run is in-flight — turn-end blocked. "
            "See additionalContext for the required next tool call."
        )
    if additional_context is not None:
        payload["hookSpecificOutput"] = {
            "hookEventName": "Stop",
            "additionalContext": additional_context,
        }
    if payload:
        json.dump(payload, sys.stdout)
    sys.exit(0)


def _read_state(cwd: str) -> dict | None:
    state_path = Path(cwd) / STATE_FILE_REL
    if not state_path.is_file():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_nudge(state: dict) -> str:
    story_id = state.get("story_id", "<unknown>")
    phase = state.get("phase", "<unknown>")
    expected = state.get("expected_next_tool", "<unspecified>")
    return (
        f"🛑 AUTONOMOUS-RUN CONTINUITY GUARD\n\n"
        f"Story: {story_id}\n"
        f"Current phase: {phase}\n"
        f"Expected next tool call: {expected}\n\n"
        f"You attempted to end the turn while phase `{phase}` is non-terminal. "
        f"That violates the Continuity Contract (Rule 1 — Silent Transition Table) "
        f"in .claude/skills/autonomous-story-run/SKILL.md. You MUST fire the "
        f"expected next tool call above. If the listed tool is no longer right, "
        f"consult Rule 1's table for the correct call based on what just returned, "
        f"or default to `Read _bmad-output/implementation-artifacts/sprint-status.yaml` "
        f"to re-ground.\n\n"
        f"After firing the next tool call, you MUST Edit the state file at "
        f"{STATE_FILE_REL} to advance `phase` and `expected_next_tool` to the "
        f"new boundary (Rule 1 row). The turn will keep being blocked until "
        f"`phase` reaches a terminal value: phase-3.3-final-report, "
        f"phase-3.5-awaiting-verdict, or halt.\n\n"
        f"Do NOT emit plain text. The orchestrator's voice during Phase 2 is "
        f"silence — tool calls only."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # If we can't parse the payload, never block — fail-open.
        _emit()
        return

    cwd = payload.get("cwd") or os.getcwd()
    state = _read_state(cwd)
    if state is None:
        # No active run — allow stop.
        _emit()
        return

    phase = state.get("phase")
    if phase in TERMINAL_PHASES:
        _emit()
        return

    stop_reason = payload.get("stop_reason")
    # Block any natural turn-end while a non-terminal autonomous run is in-flight.
    # The orchestrator must advance the state file's `phase` to a terminal value
    # (`phase-3.3-final-report`, `phase-3.5-awaiting-verdict`, or `halt`) before
    # the turn is allowed to end. `stop_reason == "tool_use"` is not a real turn
    # end (more tool calls coming), so let it through.
    if stop_reason == "end_turn":
        _emit(decision="block", additional_context=_build_nudge(state))
        return

    _emit()


if __name__ == "__main__":
    main()
