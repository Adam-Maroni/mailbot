"""Hermes-aux prompt v1 — Story 2-10 pass-through stub.

Real Hermes uses /v1/chat/completions for auxiliary tasks (title generation,
compression, summarization). Story 2-10 makes the endpoint OpenAI-shape and
routes through ask_router; the prompt module here is a thin pass-through —
the OUTPUT_SCHEMA accepts any text the model returns.

This is intentionally minimal: Hermes-aux tasks are too varied to constrain
with a strict per-call schema. The audit row still captures cost + tokens
+ caller_origin so Rule Ω accounting holds.
"""

from __future__ import annotations

from pydantic import BaseModel

SYSTEM = (
    "You are an auxiliary text-processing model. "
    "Respond with the requested transformation only — no preamble, no commentary."
)

USER_TEMPLATE = "{messages}"


class HermesAuxOutput(BaseModel):
    text: str

    @classmethod
    def model_validate_json(cls, data: str | bytes) -> "HermesAuxOutput":  # type: ignore[override]
        """Accept any string as `text` — Hermes-aux output is free-form."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return cls(text=data)


OUTPUT_SCHEMA: type[BaseModel] = HermesAuxOutput
