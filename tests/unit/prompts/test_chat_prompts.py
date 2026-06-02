"""Story 5-3: parametrized + dedicated tests covering the five new chat-side
prompt modules.

Mirrors the pattern in tests/unit/prompts/test_prompt_modules.py:
  * registry-level resolution invariants (VERSION/SYSTEM/USER_TEMPLATE/OUTPUT_SCHEMA)
  * OUTPUT_SCHEMA round-trip against a known-good payload
  * USER_TEMPLATE format-string accepts the documented placeholders

Plus dedicated tests for prompt-specific invariants:
  * intent_parsing_chat: proposed_filter nested FindEmailsFilter round-trip
  * intent_parsing_chat: unknown intent literal rejected
  * reference_resolution: reasoning > 200 chars rejected
  * draft_reply: defender_warnings defaults to empty list (not None)
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from mailbot_api.prompts import resolve_prompt

_CHAT_TASK_TYPES = (
    "intent_parsing_chat",
    "reference_resolution",
    "draft_reply",
    "tone_style_mirror",
    "multi_turn_refinement",
)


@pytest.mark.parametrize("task_type", _CHAT_TASK_TYPES)
def test_chat_prompt_module_resolves_cleanly(task_type: str) -> None:
    """AC-1 / AC-8: every chat task module loads via the registry as v1."""
    module = resolve_prompt(task_type, "v1")
    assert module.version == "v1"
    assert isinstance(module.system, str) and module.system
    assert isinstance(module.user_template, str) and module.user_template
    assert isinstance(module.output_schema, type)
    assert issubclass(module.output_schema, BaseModel)


_GOOD_PAYLOADS: dict[str, dict] = {
    "intent_parsing_chat": {
        "intent": "find_emails",
        "target_email_ids": [],
        "confidence": 0.92,
        "proposed_filter": {
            "sender_address": "alice@example.com",
            "since": "2026-06-01T00:00:00Z",
        },
    },
    "reference_resolution": {
        "resolved_email_ids": ["graph-id-abc"],
        "reasoning": "most recent thread mentioned in turn N-1; sender matches",
        "confidence": 0.78,
        "ambiguous": False,
    },
    "draft_reply": {
        "draft_body": "Confirmed — Tuesday 2pm works. Adam",
        "suggested_subject": "Re: Friday meeting",
        "tone_signals_used": ["concise", "first_name_basis"],
        "defender_warnings": [],
    },
    "tone_style_mirror": {
        "tone_attributes": ["concise", "no_emoji"],
        "signature_pattern": "Best,\nAdam",
        "salutation_pattern": "Hi {name},",
    },
    "multi_turn_refinement": {
        "refined_draft": "Tuesday 2pm. Adam",
        "changes_summary": "shortened to one line; dropped confirmation phrase",
        "still_needs_clarification": False,
    },
}


@pytest.mark.parametrize("task_type", _CHAT_TASK_TYPES)
def test_chat_prompt_output_schema_round_trips(task_type: str) -> None:
    """AC-8: each chat OUTPUT_SCHEMA accepts the known-good payload cleanly."""
    module = resolve_prompt(task_type, "v1")
    payload = _GOOD_PAYLOADS[task_type]
    instance = module.output_schema(**payload)
    assert isinstance(instance, module.output_schema)
    # Round-trip through model_dump / model_validate to verify symmetry.
    dumped = instance.model_dump()
    reloaded = module.output_schema(**dumped)
    assert reloaded == instance


@pytest.mark.parametrize("task_type", _CHAT_TASK_TYPES)
def test_chat_prompt_output_schema_json_validate_round_trips(task_type: str) -> None:
    """CR-3: also exercise the model_validate_json(json_str) path the Router
    uses when deserializing LLM responses (Pydantic v2 has distinct dict-based
    and JSON-string-based validators). Covers the actual dispatch code path."""
    import json

    module = resolve_prompt(task_type, "v1")
    payload = _GOOD_PAYLOADS[task_type]
    instance = module.output_schema(**payload)
    # model_dump_json -> model_validate_json identity round-trip.
    json_str = instance.model_dump_json()
    assert isinstance(json_str, str)
    # Parse json back to dict, sanity-check it's well-formed JSON.
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    # model_validate_json is the path the Router uses on schema-validation.
    reloaded = module.output_schema.model_validate_json(json_str)
    assert reloaded == instance


_DOCUMENTED_PLACEHOLDERS: dict[str, dict[str, str]] = {
    "intent_parsing_chat": {
        "user_message": "show me unread from sarah",
        "recent_context": "turn N-2: ... turn N-1: ...",
    },
    "reference_resolution": {
        "user_message": "draft a reply to that one",
        "recent_context": "turn N-2: ... turn N-1: ...",
        "candidate_projections": "id=graph-id-abc subject='Friday meeting'",
    },
    "draft_reply": {
        "source_email": "From: sarah\nSubject: Friday meeting\nBody: ...",
        "thread_context": "older messages oldest first ...",
        "tone_signals": "concise, no_emoji, first_name_basis",
    },
    "tone_style_mirror": {
        "recipient_address": "sarah@example.com",
        "prior_emails_sample": "From: adam\nSubject: ...\n\nFrom: adam\nSubject: ...",
    },
    "multi_turn_refinement": {
        "current_draft": "Confirmed -- Tuesday 2pm works. Adam",
        "refinement_instruction": "make it shorter",
    },
}


@pytest.mark.parametrize("task_type", _CHAT_TASK_TYPES)
def test_chat_prompt_user_template_accepts_documented_placeholders(task_type: str) -> None:
    """AC-8: USER_TEMPLATE.format(**documented_kwargs) MUST NOT raise KeyError."""
    module = resolve_prompt(task_type, "v1")
    kwargs = _DOCUMENTED_PLACEHOLDERS[task_type]
    rendered = module.user_template.format(**kwargs)
    assert isinstance(rendered, str)
    # At least one of the documented placeholder values appears in the rendered
    # output (sanity check that the placeholders actually were substituted).
    assert any(v[:20] in rendered for v in kwargs.values() if v)


def test_intent_parsing_chat_proposed_filter_round_trip() -> None:
    """AC-2: proposed_filter nests a FindEmailsFilter; the round-trip must work."""
    from mailbot_api.prompts.intent_parsing_chat.v1 import IntentParsingChatOutput
    from mailbot_api.verbs.schemas import FindEmailsFilter

    payload = {
        "intent": "find_emails",
        "target_email_ids": [],
        "confidence": 0.91,
        "proposed_filter": {
            "sender_domain": "example.com",
            "importance_min": 50.0,
        },
    }
    parsed = IntentParsingChatOutput(**payload)
    assert isinstance(parsed.proposed_filter, FindEmailsFilter)
    assert parsed.proposed_filter.sender_domain == "example.com"
    assert parsed.proposed_filter.importance_min == 50.0


def test_intent_parsing_chat_intent_literal_rejects_unknown() -> None:
    """AC-2: Pydantic rejects an unknown intent value."""
    from mailbot_api.prompts.intent_parsing_chat.v1 import IntentParsingChatOutput

    with pytest.raises(ValidationError):
        IntentParsingChatOutput(
            intent="hack_the_inbox",  # type: ignore[arg-type]
            target_email_ids=[],
            confidence=0.5,
            proposed_filter=None,
        )


def test_reference_resolution_reasoning_max_length() -> None:
    """AC-3: Pydantic rejects a reasoning string > 200 chars."""
    from mailbot_api.prompts.reference_resolution.v1 import ReferenceResolutionOutput

    too_long = "x" * 201
    with pytest.raises(ValidationError):
        ReferenceResolutionOutput(
            resolved_email_ids=["id-1"],
            reasoning=too_long,
            confidence=0.7,
            ambiguous=False,
        )


def test_draft_reply_defender_warnings_default_empty() -> None:
    """AC-4: defender_warnings defaults to [] (not None), since callers iterate over it."""
    from mailbot_api.prompts.draft_reply.v1 import DraftReplyOutput

    out = DraftReplyOutput(
        draft_body="Confirmed.",
        suggested_subject="Re: Friday",
        tone_signals_used=["concise"],
    )
    assert out.defender_warnings == []
    assert isinstance(out.defender_warnings, list)


def test_draft_reply_tone_signals_used_default_empty() -> None:
    """CR-1: tone_signals_used defaults to [] so first-contact drafts (no prior
    tone signals available) don't raise ValidationError when the LLM omits the
    field. Mirrors the defender_warnings discipline."""
    from mailbot_api.prompts.draft_reply.v1 import DraftReplyOutput

    out = DraftReplyOutput(
        draft_body="Confirmed.",
        suggested_subject="Re: Friday",
        # tone_signals_used deliberately omitted — should default to [].
    )
    assert out.tone_signals_used == []
    assert isinstance(out.tone_signals_used, list)
