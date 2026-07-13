"""Story 10-6-2 (AI-2) AC-2/AC-3 — structural drift tests for the draft-pipeline
reachability contract: the persona MUST dispatch the registered ``draft_reply``
MCP verb when the user asks for a draft, and MUST NOT hand-write the draft inline
in haiku while narrating that ``draft_reply`` "isn't exposed".

Same OFFLINE structural posture as Story 10-5-6's
``test_recognized_phrase_dispatch.py`` and Story 5-5's
``test_hermes_persona_files.py``: these assert the Hermes persona files
(SKILL.md, AGENTS.md) carry the draft-reach dispatch contract plus the explicit
"do not hand-write / narrate-not-exposed" prohibition. They do NOT exercise
Hermes's LLM loader — the runtime proof that the persona deterministically issues
the ``draft_reply`` verb is the Task-5 Adam-hands-on live Discord walk (AC-1/AC-5:
a real "draft a reply" turn producing an Opus ``draft_reply`` ``router_calls``
row, ``model_chosen=claude-opus-*``).

F-10-5-11 (HIGH), 3rd walk it's bitten: across all three Epic 10.5-6 live walks
0 Opus ``draft_reply`` rows were ever created — the persona said "the Router's
draft_reply task isn't directly exposed via MCP" and improvised the draft in
haiku (10-5-6-walk-evidence.md §RESIDUAL). The mailbot_api side is correct
(``draft_reply`` IS MCP-registered, Story 10.5.3, tool count 26); the residual is
persona-reach, which is Hermes-side. This drift test makes a regression of that
contract a red gate.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HERMES_CONFIG = _REPO_ROOT / "hermes-config"
_AGENTS = _HERMES_CONFIG / "AGENTS.md"
_SKILL = _HERMES_CONFIG / "skills" / "mailbot" / "SKILL.md"


# --------------------------------------------------------------------------- #
# SKILL.md — draft_reply is a MUST-issue MCP verb, not an inline improvisation.
# --------------------------------------------------------------------------- #


def test_skill_md_draft_reply_section_mandates_issuing_the_verb() -> None:
    """AC-2: the ``draft_reply`` verb section instructs the persona that a draft
    request MUST dispatch the registered ``draft_reply`` MCP verb — it does not
    leave "how do I draft" to free-form inference (which is how the haiku
    improvisation slips in)."""
    text = _SKILL.read_text(encoding="utf-8")
    # Locate the draft_reply verb section.
    assert "### `draft_reply`" in text, "SKILL.md missing the draft_reply verb section"
    section = text.split("### `draft_reply`", 1)[1].split("\n### ", 1)[0]
    assert "MUST" in section and "draft_reply" in section, (
        "the draft_reply section must state the persona MUST issue the draft_reply "
        "verb on a draft request"
    )


def test_skill_md_forbids_hand_writing_the_draft() -> None:
    """AC-2: the contract explicitly prohibits the F-10-5-11 failure — improvising
    the draft inline in haiku instead of dispatching the real Opus pipeline — and
    names the finding."""
    text = _SKILL.read_text(encoding="utf-8")
    assert "F-10-5-11" in text, (
        "SKILL.md must name F-10-5-11 (the draft-pipeline reachability gap)"
    )
    # The prohibition against hand-writing / improvising the draft.
    assert re.search(r"hand-writ|improvis", text, re.IGNORECASE), (
        "SKILL.md must forbid hand-writing / improvising the draft in place of "
        "dispatching draft_reply"
    )
    # The specific false-narration this closes: 'isn't exposed'.
    assert re.search(r"isn'?t (directly )?exposed", text, re.IGNORECASE), (
        "SKILL.md must name the specific false narration ('draft_reply isn't "
        "exposed via MCP') so a regression to it is a red gate"
    )


def test_skill_md_draft_reply_is_in_the_dispatch_family() -> None:
    """AC-2: draft_reply is grouped with the deterministic dispatch discipline
    (same family as the recognized-phrase control verbs) — a draft request is a
    reliably-recognized dispatch trigger, not a free-form interpretation."""
    text = _SKILL.read_text(encoding="utf-8").lower()
    # The recognized draft-request phrasings the persona must map to the verb.
    assert "draft a reply" in text or "draft the reply" in text, (
        "SKILL.md must name the 'draft a reply' request that maps to draft_reply"
    )


def test_skill_md_turn_structure_uses_the_mcp_verb_not_only_ask_router() -> None:
    """AC-2: the "draft a reply to that" turn structure dispatches the registered
    ``draft_reply`` MCP verb (the single reachable chat call site) — not ONLY the
    ``ask_router(task_type="draft_reply")`` framing, which the persona has
    conflated with the router-internal 'not exposed' note (the F-10-5-11 trap)."""
    text = _SKILL.read_text(encoding="utf-8")
    # The turn-structure walkthrough must reference dispatching the draft_reply
    # MCP verb, so the persona has an unambiguous "call this tool" instruction.
    turn = text.split('draft a reply to that', 1)
    assert len(turn) > 1, "SKILL.md missing the 'draft a reply to that' turn structure"
    turn_body = turn[1].split("### Turn structure 3", 1)[0]
    assert "draft_reply` MCP verb" in turn_body or "`draft_reply` verb" in turn_body, (
        "the 'draft a reply' turn structure must instruct dispatching the "
        "draft_reply MCP verb, not leave it as an ask_router-only framing that "
        "reads as 'router-internal / not exposed'"
    )


# --------------------------------------------------------------------------- #
# AC-3 — the sensitivity gate is preserved (no regression to the reach fix).
# --------------------------------------------------------------------------- #


def test_skill_md_draft_reach_preserves_sensitivity_gate() -> None:
    """AC-3: the draft-reach contract still routes sensitive/confidential drafts
    through the existing sensitivity handshake — the new reach does NOT bypass
    the FR-2.3/F28 gate. The draft_reply verb section keeps the
    confidential-refused / needs-sensitivity-token contract."""
    text = _SKILL.read_text(encoding="utf-8")
    section = text.split("### `draft_reply`", 1)[1].split("\n### ", 1)[0]
    assert "sensitivity gate" in section.lower(), (
        "draft_reply section must keep the sensitivity-gate description (AC-3 "
        "no-regression)"
    )
    assert "confidential" in section.lower() and "confirmation_token" in section, (
        "draft_reply section must keep the confidential-refused + "
        "confirmation_token handshake (AC-3 no-regression)"
    )


def test_agents_md_draft_default_model_note_is_not_a_hand_write_license() -> None:
    """AC-2/AC-3: AGENTS.md Rule N (draft_reply routes to Opus per FR-4.4) must not
    read as license to hand-write a draft in the cheap default model — the draft
    goes through the draft_reply pipeline where the Opus routing + sensitivity gate
    live. The Rule N draft note names draft_reply and its Opus routing."""
    text = _AGENTS.read_text(encoding="utf-8")
    assert "draft_reply" in text, "AGENTS.md must name draft_reply in the cost-rule"
    # Rule N already says draft_reply routes to Opus per FR-4.4; assert that
    # structural note survives (it is the anchor that a draft is NOT a cheap
    # inline haiku improvisation).
    assert re.search(r"draft_reply.{0,80}Opus", text, re.DOTALL), (
        "AGENTS.md Rule N must keep the 'draft_reply routes to Opus' structural "
        "note so a draft request is not treated as a cheap inline improvisation"
    )
