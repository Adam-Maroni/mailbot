"""Story 10-5-6 AC-4 — structural drift tests for the slash→plain-NL charter
rewrite and the deterministic recognized-phrase control-verb dispatch contract.

These are OFFLINE structural tests (same posture as Story 5-5's
``test_hermes_persona_files.py``): they assert that the README no longer
presents a slash-command invocation surface, and that the Hermes persona files
carry the recognized-phrase control-verb contract plus the explicit
"do not narrate a control action without issuing the verb" prohibition. They do
NOT exercise Hermes's LLM loader — the runtime proof that the persona
deterministically issues the verb is the Task-5 Adam-hands-on Discord walk
(F-10-5-6-W1 "use qwen" + F-10-5-2-W2 "yes, escalate").

Rationale: these persona-contract + charter-doc surfaces regress silently — a
future edit could re-introduce the ``/command`` metaphor (which F-10-5-1 proved
is architecturally unreachable: Discord/Hermes own the ``/`` prefix) or drop the
recognized-phrase contract. The drift test makes the regression a red gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HERMES_CONFIG = _REPO_ROOT / "hermes-config"
_AGENTS = _HERMES_CONFIG / "AGENTS.md"
_SKILL = _HERMES_CONFIG / "skills" / "mailbot" / "SKILL.md"
_README = _REPO_ROOT / "README.md"

# The control verbs whose invocation touches the mailbox or the kill-switch and
# therefore MUST dispatch via an exact-match recognized phrase, not free-form
# LLM interpretation (retro §8.7 two-tier constraint).
_RECOGNIZED_CONTROL_VERBS = (
    "cancel_action",
    "pause_router",
    "resume_router",
    "mint_sensitivity_token",
    "set_model_oneshot",
)

# Slash-invocation verb STEMS that F-10-5-1 proved unreachable. These must NOT
# appear as the documented way to invoke a MailBot intent. Matched with BOTH a
# start-boundary (the '/' must begin a token — preceded by start-of-line,
# whitespace, backtick, or an opening delimiter like ( " ' , ) AND an
# end-boundary after the verb (a word boundary). The start-boundary excludes
# legitimate slash-separated prose ("abort/pause/confirm", "Pause/resume the
# Router" — there the '/' is preceded by a word char). The end-boundary excludes
# false positives ("/pauseless", "/resumes", "/spendthrift") while still catching
# every real invocation regardless of the trailing char ("/cancel 14", "`/pause`",
# "(/resume)", "/confirm.", '"/spend"', "the /model qwen override").
#
# NOTE: 'model' IS included — F-10-5-6-W1 (the "use qwen" / model-override bug)
# is a central motivating case of this story, so a reintroduced "/model qwen"
# invocation MUST be a red gate. The permitted carve-out — native Discord
# "/model opens Hermes's own UI" as an *explanation* — is matched too, so any
# such explanatory mention is asserted separately (see
# test_readme_model_slash_is_explanation_only) rather than blanket-forbidden.
_DEAD_SLASH_INVOCATIONS = (
    "cancel",
    "confirm",
    "pause",
    "resume",
    "budget reset",
    "mute",
    "unmute",  # distinct from 'mute': '/unmute' has '/u', not '/m' (CR HIGH — SKILL.md:492)
    "cost",
    "spend",
    "model",
)

# Verbs whose native-Hermes '/model'-opens-its-own-UI mention is an allowed
# *explanation* (not a MailBot invocation). For these, a bare "/verb" is only an
# offender when it is NOT part of the explanatory carve-out.
_EXPLANATION_ONLY_SLASH = {"model"}


def _dead_slash_offenders(name: str, text: str) -> list[str]:
    """Return a list of dead slash-invocation offenders found in ``text``.

    A slash-invocation is ``/verb`` where the '/' begins a token (preceded by
    start-of-string, whitespace, backtick, or an opening delimiter) AND ``verb``
    ends on a word boundary. This ignores slash-separated prose word lists
    (``abort/pause/confirm`` — '/' preceded by a word char) and stem-prefix
    false positives (``/pauseless`` — no word boundary after 'pause').

    For verbs in ``_EXPLANATION_ONLY_SLASH`` (currently just 'model'), a match is
    only an offender when the surrounding line is NOT the permitted "native
    Hermes /model opens its own UI" explanation — so the honest architectural
    note about why plain NL is used does not trip the sweep.
    """
    offenders: list[str] = []
    for verb in _DEAD_SLASH_INVOCATIONS:
        # (?<![\w/]) — '/' not glued to a word char or another '/' (excludes
        #              "abort/pause" and "//pause"); r"\b" after — verb ends on
        #              a word boundary (excludes "/pauseless").
        pattern = r"(?<![\w/])/" + re.escape(verb) + r"\b"
        for m in re.finditer(pattern, text, re.MULTILINE):
            if verb in _EXPLANATION_ONLY_SLASH:
                line = text[text.rfind("\n", 0, m.start()) + 1 :
                            (text.find("\n", m.end()) + 1 or len(text) + 1) - 1]
                if re.search(r"Hermes|own (UI|picker|model-config)|opens", line):
                    continue  # permitted explanatory carve-out
            offenders.append(f"{name}: '/{verb}'")
            break
    return offenders


# --------------------------------------------------------------------------- #
# README — the slash-command invocation surface is gone (AC-1).
# --------------------------------------------------------------------------- #


def test_readme_has_no_slash_command_invocation_section() -> None:
    """AC-1: the '## Slash commands' section is removed and the interim
    'type these WITHOUT the leading `/`' honesty note (a documented workaround)
    is superseded — plain NL is now the actual contract."""
    text = _README.read_text(encoding="utf-8")
    assert "## Slash commands" not in text, (
        "README still has the '## Slash commands' heading — F-10-5-1 proved the "
        "whole slash surface is unreachable; it must be a plain-NL section"
    )
    assert "WITHOUT the leading" not in text, (
        "README still carries the interim slash-workaround honesty note; "
        "10-5-6 supersedes it — plain NL is the contract, not a workaround"
    )


def test_readme_documents_plain_nl_intents_section() -> None:
    """AC-1: the replacement plain-NL intents section exists."""
    text = _README.read_text(encoding="utf-8")
    assert "## Talking to MailBot" in text, (
        "README missing the plain-NL '## Talking to MailBot' intents section "
        "that replaces the dead slash table"
    )


def test_readme_write_examples_use_plain_nl_cancel() -> None:
    """AC-1: the write-family examples no longer instruct the '/cancel' form."""
    text = _README.read_text(encoding="utf-8")
    assert "/cancel " not in text, (
        "README still shows a '/cancel <id>' invocation — must be plain-NL "
        "'cancel <id>' (F-10-5-1: the slash form never reaches the agent)"
    )


# --------------------------------------------------------------------------- #
# SKILL.md — recognized-phrase control-verb dispatch contract (AC-2).
# --------------------------------------------------------------------------- #


def test_skill_md_has_recognized_phrase_control_verb_section() -> None:
    """AC-2: SKILL.md documents a deterministic recognized-phrase control-verb
    dispatch section (replacing the dead '## Slash-command verbs' section)."""
    text = _SKILL.read_text(encoding="utf-8")
    assert "Control-verb dispatch" in text, (
        "SKILL.md missing the 'Control-verb dispatch' recognized-phrase section"
    )
    assert "recognized phrase" in text.lower(), (
        "SKILL.md must describe the exact-match recognized-phrase contract"
    )
    assert "## Slash-command verbs" not in text, (
        "SKILL.md still has the dead '## Slash-command verbs' section heading"
    )


@pytest.mark.parametrize("verb", _RECOGNIZED_CONTROL_VERBS)
def test_skill_md_maps_each_control_verb(verb: str) -> None:
    """AC-2: each mailbox/kill-switch control verb is named in the contract."""
    text = _SKILL.read_text(encoding="utf-8")
    assert verb in text, f"SKILL.md control-verb contract missing {verb}"


def test_skill_md_forbids_narrating_without_the_verb() -> None:
    """AC-2: the contract explicitly prohibits the false-narration failure
    (narrating a control outcome without issuing the tool call) and names the
    two inherited motivating findings."""
    text = _SKILL.read_text(encoding="utf-8")
    # The prohibition itself.
    assert "without issuing the verb" in text, (
        "SKILL.md must forbid narrating a control action without issuing the verb"
    )
    # The two inherited motivating findings, named.
    assert "F-10-5-6-W1" in text, (
        "SKILL.md must name F-10-5-6-W1 ('use qwen' narrated-not-dispatched)"
    )
    assert "F-10-5-2-W2" in text, (
        "SKILL.md must name F-10-5-2-W2 ('yes, escalate' re-parrots refusal)"
    )


def test_skill_md_recognizes_the_two_inherited_phrases() -> None:
    """AC-2: the recognized-phrase set includes the two live-proven failures —
    'use qwen' → set_model_oneshot and 'yes, escalate' → the escalation mint."""
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "use qwen" in text, "SKILL.md missing 'use qwen' recognized phrase"
    assert "yes, escalate" in text, (
        "SKILL.md missing 'yes, escalate' recognized phrase"
    )


# --------------------------------------------------------------------------- #
# AGENTS.md — plain-NL tier flows + discoverability tie-in (AC-2, AC-3).
# --------------------------------------------------------------------------- #


def test_agents_md_tier_flows_use_plain_nl() -> None:
    """AC-2: the Tier-2/Tier-3 flow prose no longer instructs '/cancel' /
    '/confirm' slash forms."""
    text = _AGENTS.read_text(encoding="utf-8")
    assert "/cancel" not in text, (
        "AGENTS.md still cites '/cancel' in a tier flow — must be plain NL"
    )
    assert "/confirm" not in text, (
        "AGENTS.md still cites '/confirm' in a tier flow — must be plain NL"
    )


def test_agents_md_documents_user_facing_guidance_discoverability() -> None:
    """AC-3: AGENTS.md documents that user_facing_guidance (Rule S /
    RecoveryAction) is the discoverability surface that carries the exact
    working phrase — replacing the dead slash table."""
    text = _AGENTS.read_text(encoding="utf-8")
    assert "user_facing_guidance" in text, (
        "AGENTS.md must document user_facing_guidance as the discoverability "
        "surface for the exact working phrase (AC-3)"
    )


# --------------------------------------------------------------------------- #
# Cross-file — no dead slash invocation anywhere in the persona files (AC-2).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("verb", ["cancel", "confirm", "pause", "resume", "model"])
def test_persona_files_carry_no_control_verb_slash_invocation(verb: str) -> None:
    """AC-2: the load-bearing control-verb slash invocations (incl. the
    model-override family — F-10-5-6-W1) are gone from both persona files
    (token-boundary match — prose word lists are not invocations)."""
    for pf in (_SKILL, _AGENTS):
        offenders = _dead_slash_offenders(pf.name, pf.read_text(encoding="utf-8"))
        assert f"{pf.name}: '/{verb}'" not in offenders, (
            f"{pf.name} still contains dead slash invocation '/{verb}'"
        )


def test_dead_slash_invocations_gone_from_readme_and_persona() -> None:
    """AC-1/AC-2: sweep — none of the dead slash-invocation forms survive in the
    README or the persona files (native Hermes '/model'-opens-its-own-UI as an
    *explanation* is allowed and is not in this list; slash-separated prose word
    lists are not invocations)."""
    surfaces = {
        "README.md": _README.read_text(encoding="utf-8"),
        "SKILL.md": _SKILL.read_text(encoding="utf-8"),
        "AGENTS.md": _AGENTS.read_text(encoding="utf-8"),
    }
    offenders: list[str] = []
    for name, text in surfaces.items():
        offenders.extend(_dead_slash_offenders(name, text))
    assert not offenders, (
        "dead slash-invocation forms still present (F-10-5-1 unreachable): "
        + ", ".join(offenders)
    )


def test_no_regression_of_slash_word_in_prose_is_acceptable() -> None:
    """Guard: the word 'slash' may still appear in *explanatory* prose (why we
    dropped it), but only alongside the architectural reason. This keeps the
    honest F-10-5-1 explanation while forbidding the invocation surface."""
    readme = _README.read_text(encoding="utf-8")
    if "slash" in readme.lower():
        # If 'slash' appears, it must be explaining the Hermes-owns-/ reason,
        # not presenting an invocation table.
        assert re.search(r"Hermes|reserved|owns the `?/`?", readme), (
            "README mentions 'slash' without the architectural explanation — "
            "either remove it or keep the F-10-5-1 reason alongside"
        )


def test_readme_model_slash_is_explanation_only() -> None:
    """AC-1 carve-out (CR): any '/model' surviving in the README must be the
    permitted 'native Hermes /model opens its own UI' EXPLANATION, never a
    documented MailBot invocation. The matcher's explanation-carve-out means a
    genuine '/model qwen' invocation WOULD be flagged; this test locks the
    carve-out to the honest-explanation shape."""
    readme = _README.read_text(encoding="utf-8")
    # No '/model' offender should survive the sweep (explanation carve-out aside).
    assert not _dead_slash_offenders("README.md", readme), (
        "README carries a dead slash invocation the sweep flagged"
    )
    # Every literal '/model' occurrence must sit on an explanatory line.
    for m in re.finditer(r"(?<![\w/])/model\b", readme):
        line_start = readme.rfind("\n", 0, m.start()) + 1
        line_end = readme.find("\n", m.end())
        line = readme[line_start : line_end if line_end != -1 else len(readme)]
        assert re.search(r"Hermes|own (UI|picker|model-config)|opens", line), (
            f"README '/model' not on an explanatory line: {line.strip()!r}"
        )


def test_dead_slash_matcher_catches_all_trailing_delimiters() -> None:
    """CR fix (Blind/Edge Hunter): the matcher must catch a real invocation
    regardless of the char after the verb — space, backtick, period, quote,
    paren, or end-of-line — closing the false-NEGATIVE hole."""
    for trailing in (" 14", "`", ".", '"', ")", ""):
        text = f"type /cancel{trailing}"
        assert _dead_slash_offenders("t", text), (
            f"matcher missed a real invocation with trailing {trailing!r}"
        )
    # Backtick-wrapped and delimiter-prefixed forms are caught too.
    for text in ("say `/pause` to stop", "use (/resume) here", 'the "/spend" cmd'):
        assert _dead_slash_offenders("t", text), f"matcher missed: {text!r}"


def test_dead_slash_matcher_ignores_prose_and_stem_prefixes() -> None:
    """CR fix (Blind Hunter): the matcher must NOT flag slash-separated prose
    word lists or stem-prefix words, closing the false-POSITIVE hole."""
    # Prose word lists — '/' preceded by a word char.
    for text in ("abort/pause/confirm", "Pause/resume the Router", "read/write"):
        assert not _dead_slash_offenders("t", text), (
            f"matcher false-flagged prose: {text!r}"
        )
    # Stem-prefix words — verb not on a word boundary.
    for text in ("the /pauseless mode", "check /resumes", "/spendthrift ways"):
        assert not _dead_slash_offenders("t", text), (
            f"matcher false-flagged a stem-prefix word: {text!r}"
        )


def test_dead_slash_matcher_flags_reintroduced_model_invocation() -> None:
    """CR fix (all 3 layers): a reintroduced '/model qwen' or '/model <task>
    <model>' MailBot invocation MUST be caught — this is F-10-5-6-W1's family,
    the story's own motivating bug. The explanatory carve-out must NOT hide it."""
    for text in ("type /model qwen", "use /model draft_reply opus", "`/model`"):
        assert _dead_slash_offenders("t", text), (
            f"matcher missed a reintroduced model-override invocation: {text!r}"
        )
    # The permitted explanation is NOT flagged.
    explanation = "native /model opens Hermes's own model-config UI instead"
    assert not _dead_slash_offenders("t", explanation), (
        "matcher wrongly flagged the permitted native-Hermes /model explanation"
    )


def test_dead_slash_matcher_distinguishes_unmute_from_mute() -> None:
    """CR HIGH (SKILL.md:492): '/unmute' is a distinct invocation from '/mute'
    ('/u' vs '/m'); the sweep must catch a reintroduced '/unmute <category>'."""
    assert _dead_slash_offenders("t", "Slash command: /unmute <category>"), (
        "matcher missed a reintroduced '/unmute' invocation"
    )
    # And '/mute' is still caught independently.
    assert _dead_slash_offenders("t", "type /mute newsletter"), (
        "matcher missed '/mute'"
    )
