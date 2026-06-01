"""Prompt-module registry per Story 2-4 AC-3.

Each prompt module at ``mailbot_api/prompts/<task_type>/<prompt_version>.py``
exports three module-level constants:

  * ``SYSTEM: str`` — the SYSTEM block sent to the model
  * ``USER_TEMPLATE: str`` — a format-string accepting ``content`` keys
  * ``OUTPUT_SCHEMA: type[BaseModel]`` — the Pydantic model the response must validate against

Resolution is dynamic by import path: ``resolve_prompt("coarse_class", "v1")``
imports ``mailbot_api.prompts.coarse_class.v1``. Missing module surfaces as
``PromptResolutionError`` for the Router to convert to a structured
``RouterError(code=PROVIDER_ERROR, ...)``.

Real prompt bodies are owned by Epic 3 (Ingest Pipeline) and Epic 5
(Conversational Control). Story 2-4 ships only a minimal ``coarse_class/v1.py``
stub so the Router is runnable in tests.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass

from pydantic import BaseModel


class PromptResolutionError(Exception):
    """Raised when ``resolve_prompt(task_type, version)`` cannot import the module
    or the module is missing one of the required constants."""


@dataclass(frozen=True)
class PromptModule:
    """The validated triple a prompt module provides."""

    system: str
    user_template: str
    output_schema: type[BaseModel]


def resolve_prompt(task_type: str, prompt_version: str) -> PromptModule:
    """Import ``mailbot_api.prompts.<task_type>.<prompt_version>`` and validate it.

    Validates that the imported module exposes the three required constants
    with the correct types. ``SYSTEM`` and ``USER_TEMPLATE`` must be ``str``;
    ``OUTPUT_SCHEMA`` must be a ``type`` subclass of ``BaseModel``.
    """
    module_path = f"mailbot_api.prompts.{task_type}.{prompt_version}"
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        # Story 2-4 review fix MEDIUM: Python caches failed imports in
        # sys.modules as None, which permanently wedges the router for that
        # task_type until process restart. Pop the negative entry so a
        # corrected module (after a hot-fix + module reload) can be picked up.
        sys.modules.pop(module_path, None)
        raise PromptResolutionError(
            f"prompt module not found: {module_path}"
        ) from exc

    system = getattr(module, "SYSTEM", None)
    user_template = getattr(module, "USER_TEMPLATE", None)
    output_schema = getattr(module, "OUTPUT_SCHEMA", None)

    if not isinstance(system, str):
        raise PromptResolutionError(
            f"{module_path}.SYSTEM must be str; got {type(system).__name__}"
        )
    if not isinstance(user_template, str):
        raise PromptResolutionError(
            f"{module_path}.USER_TEMPLATE must be str; got {type(user_template).__name__}"
        )
    if not (isinstance(output_schema, type) and issubclass(output_schema, BaseModel)):
        raise PromptResolutionError(
            f"{module_path}.OUTPUT_SCHEMA must be a Pydantic BaseModel subclass"
        )

    return PromptModule(
        system=system,
        user_template=user_template,
        output_schema=output_schema,
    )


__all__: list[str] = ["PromptModule", "PromptResolutionError", "resolve_prompt"]
