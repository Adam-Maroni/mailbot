"""Prompt-module registry per Story 2-4 AC-3, extended in Story 3-2 to enforce
the AR-PAT-5 4-export shape.

Each prompt module at ``mailbot_api/prompts/<task_type>/<prompt_version>.py``
exports FOUR module-level constants:

  * ``VERSION: str`` — the prompt-module version string, e.g. ``"v1"``. Story 3-2:
    the registry verifies ``VERSION == requested prompt_version``; this catches
    accidental copy-paste of v1 content into a v2 file at startup, not at
    first-call time.
  * ``SYSTEM: str`` — the SYSTEM block sent to the model. Stable across calls so
    Anthropic ephemeral prompt cache (Rule M) hits.
  * ``USER_TEMPLATE: str`` — a format-string accepting ``content`` keys
  * ``OUTPUT_SCHEMA: type[BaseModel]`` — the Pydantic model the response must
    validate against

Resolution is dynamic by import path: ``resolve_prompt("coarse_class", "v1")``
imports ``mailbot_api.prompts.coarse_class.v1``. Missing module surfaces as
``PromptResolutionError`` for the Router to convert to a structured
``RouterError(code=PROVIDER_ERROR, ...)``.

Story 3-2 owns the real prompt bodies for ingest tasks (sensitivity_class,
coarse_class, fine_class, summary_short, importance_scoring, action_extraction).
Story 2-4 shipped a minimal ``coarse_class/v1.py`` stub that Story 3-2 replaces
with the spec-conformant 6-label module. Story 2-10's ``hermes_aux/v1.py`` was
patched in Story 3-2 to add ``VERSION = "v1"`` per the new 4-export contract.
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
    """The validated 4-tuple a prompt module provides.

    Story 3-2: ``version`` field added to mirror the module's ``VERSION``
    constant. Useful when the Router needs to record the prompt version that
    was actually used (e.g., for the derived-field companion
    ``<X>_prompt_v`` columns).
    """

    version: str
    system: str
    user_template: str
    output_schema: type[BaseModel]


def resolve_prompt(task_type: str, prompt_version: str) -> PromptModule:
    """Import ``mailbot_api.prompts.<task_type>.<prompt_version>`` and validate it.

    Validates that the imported module exposes the four required constants
    with the correct types:

      * ``VERSION`` must be a non-empty ``str`` and MUST equal ``prompt_version``.
      * ``SYSTEM`` and ``USER_TEMPLATE`` must be ``str``.
      * ``OUTPUT_SCHEMA`` must be a ``type`` subclass of ``BaseModel``.

    Story 3-2 added the ``VERSION`` validation; the equality check guards against
    accidental copy-paste of v1 content into a v2 directory.
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
        raise PromptResolutionError(f"prompt module not found: {module_path}") from exc

    version = getattr(module, "VERSION", None)
    system = getattr(module, "SYSTEM", None)
    user_template = getattr(module, "USER_TEMPLATE", None)
    output_schema = getattr(module, "OUTPUT_SCHEMA", None)

    if not isinstance(version, str) or not version:
        raise PromptResolutionError(f"{module_path}.VERSION must be a non-empty str; got {type(version).__name__}")
    if version != prompt_version:
        raise PromptResolutionError(f"{module_path}.VERSION='{version}' != requested '{prompt_version}'")
    if not isinstance(system, str) or not system:
        raise PromptResolutionError(f"{module_path}.SYSTEM must be a non-empty str; got {type(system).__name__}")
    if not isinstance(user_template, str) or not user_template:
        raise PromptResolutionError(
            f"{module_path}.USER_TEMPLATE must be a non-empty str; got {type(user_template).__name__}"
        )
    if not (isinstance(output_schema, type) and issubclass(output_schema, BaseModel)):
        raise PromptResolutionError(f"{module_path}.OUTPUT_SCHEMA must be a Pydantic BaseModel subclass")

    return PromptModule(
        version=version,
        system=system,
        user_template=user_template,
        output_schema=output_schema,
    )


__all__: list[str] = ["PromptModule", "PromptResolutionError", "resolve_prompt"]
