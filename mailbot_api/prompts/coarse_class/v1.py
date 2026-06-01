"""Coarse-class prompt v1 — Story 2-4 minimal stub.

Real prompt body lands in Epic 3 Story 3-2 (uniform AR-PAT-5 structure).
This stub exists so Story 2-4's Router orchestration is end-to-end runnable
in tests and a developer can exercise `ask_router("coarse_class", ...)`
against a fake adapter.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SYSTEM = (
    "You classify the kind of email a message is. "
    "Reply with valid JSON matching the schema. Do not include any prose."
)

USER_TEMPLATE = (
    "Subject: {subject}\n"
    "From: {sender}\n"
    "Body preview: {body_preview}\n\n"
    "Classify as one of: newsletter, transactional, personal, promotional, spam."
)


class CoarseClassOutput(BaseModel):
    label: Literal["newsletter", "transactional", "personal", "promotional", "spam"]
    confidence: float


OUTPUT_SCHEMA: type[BaseModel] = CoarseClassOutput
