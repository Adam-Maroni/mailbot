"""Story 10.5.2 (Epic 10.5 Cluster B) — sensitivity-refusal envelope + builder.

Unit tests for the pure message builder and the typed envelope:
  - the three four-beat message shapes (sensitive / confidential /
    not-yet-classified) match the retro §8.5 spec + offer rules;
  - the not-yet-classified message does NOT suggest `mailbot rederive`
    (guards against re-introducing the F-10-6-3 dead-end until 10-5-4);
  - the envelope carries NO printable Graph email id (F-10-5-6 leak fixed by
    construction — `email_ref` is a one-way display token).
"""

from __future__ import annotations

import pytest

from mailbot_api.router.sensitivity_refusal import (
    SensitivityRefusal,
    build_guidance,
    build_refusal,
    email_ref_for,
)


def test_sensitive_message_offers_yes_escalate() -> None:
    """Sensitive → four-beat prose that offers 'yes, escalate'."""
    msg = build_guidance("sensitive")
    assert "sensitive" in msg.lower()
    assert "yes, escalate" in msg.lower()
    # Four-beat: names the consequence (cloud API) and the expectation window.
    assert "cloud" in msg.lower()
    assert "10 minutes" in msg


def test_confidential_message_offers_no_escalation() -> None:
    """Confidential → NO escalation offered (none exists by design)."""
    msg = build_guidance("confidential")
    assert "confidential" in msg.lower()
    # Must NOT offer the escalation path.
    assert "yes, escalate" not in msg.lower()
    assert "no cloud override" in msg.lower()
    # Points to the working action: read it in Outlook.
    assert "outlook" in msg.lower()


def test_not_classified_message_does_not_suggest_rederive() -> None:
    """Not-yet-classified → does NOT suggest `mailbot rederive` (F-10-6-3
    crashes until 10-5-4). Guards the dead-end from re-entering the prose."""
    msg = build_guidance("not_classified")
    assert "rederive" not in msg.lower()
    # Offers the action that works: wait for the ingest worker.
    assert "worker" in msg.lower() or "shortly" in msg.lower()
    # Does not offer escalation either (there's nothing to escalate yet).
    assert "yes, escalate" not in msg.lower()


def test_email_ref_is_not_the_graph_id() -> None:
    """`email_ref` is a one-way display token — the raw Graph id never appears."""
    graph_id = "AAMkAGI2-super-secret-graph-message-id-0xDEADBEEF"
    ref = email_ref_for(graph_id)
    assert graph_id not in ref
    # Stable + short display shape.
    assert ref.startswith("email #")
    assert email_ref_for(graph_id) == ref  # deterministic


def test_build_refusal_never_stores_graph_id() -> None:
    """The envelope carries the ref, task, classification, guidance — but NOT
    the Graph id in ANY field (F-10-5-6 leak fixed by construction)."""
    graph_id = "AAMkAGI2-super-secret-graph-message-id-0xDEADBEEF"
    env = build_refusal(
        email_id=graph_id,
        task="draft_reply",
        classification="sensitive",
        reason="sensitivity_blocks_api",
    )
    assert isinstance(env, SensitivityRefusal)
    # The raw id must not appear in the serialized envelope at all.
    dumped = env.model_dump_json()
    assert graph_id not in dumped
    assert env.task == "draft_reply"
    assert env.classification == "sensitive"
    assert "yes, escalate" in env.user_facing_guidance.lower()


def test_envelope_is_frozen() -> None:
    """Frozen — every consumer reads by value; mutation raises."""
    env = build_refusal(
        email_id="e1",
        task="summary_short",
        classification="confidential",
        reason="sensitivity_blocks_api",
    )
    with pytest.raises(Exception):  # noqa: B017,PT011 — pydantic frozen ValidationError
        env.task = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("classification", ["sensitive", "confidential", "not_classified"])
def test_all_shapes_carry_no_internal_id_placeholder(classification: str) -> None:
    """None of the three prose shapes contains an id-shaped token or a trace —
    the four-beat contract forbids internal ids and dead-end instructions."""
    msg = build_guidance(classification)  # type: ignore[arg-type]
    assert "AAMk" not in msg  # Graph-id prefix must never appear
    assert "traceback" not in msg.lower()
    assert "502" not in msg
