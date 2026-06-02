"""multi_turn_refinement prompt v1 — Story 5-3.

Refines a draft reply according to a follow-up instruction from Adam ("make it
shorter", "less formal", "ask about Tuesday instead of Wednesday"). Invoked
iteratively inside Story 5-9's draft-reply loop; that loop caps at 5 iterations
with a defender warning at the 5th ("we've refined this 5 times — want to start
over?").

The 5-iteration cap + defender-warning at 5 is **orchestrator-level discipline**
(Story 5-9's chat loop owns the counter, surfaces the warning, and decides
whether to keep refining or restart). This prompt module deliberately does NOT
carry an iteration_count placeholder — the model's task is to produce a good
refinement of the current draft; the meta-loop control belongs in the
orchestrator. AC-6's reference to "iteratively (Story 5-9 caps at 5)" describes
the orchestrator's contract that consumes this prompt, not a SYSTEM-level
instruction the model needs to see on each call.

The model MUST NOT drift away from the prior draft's intent unless Adam explicitly
requests a restart. When the instruction is itself ambiguous ("make it better"),
set ``still_needs_clarification=True`` so the orchestrator surfaces a clarifying
turn instead of producing a low-confidence refinement.

Routes to Opus per FR-4.4 (chat quality is tier-1). No response cache — every
refinement is turn-specific.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

VERSION: str = "v1"

SYSTEM = (
    "You refine a draft reply according to a follow-up instruction from the user. "
    "Reply with valid JSON matching the schema; no preamble.\n"
    "Refinement discipline:\n"
    "  - Preserve the prior draft's intent unless the user explicitly requests a\n"
    "    restart. 'Make it shorter' edits the draft. 'Start over, take a different\n"
    "    angle' restarts.\n"
    "  - Preserve the defender voice from the original draft (conservative, terse,\n"
    "    no emoji-unless-source-used-them, no apologetic-when-unnecessary).\n"
    "  - When the instruction is itself ambiguous ('make it better', 'fix it'),\n"
    "    set still_needs_clarification=True and produce your best-guess refinement;\n"
    "    the orchestrator will then surface a clarifying turn.\n"
    "  - changes_summary must be ≤ 200 chars and name the specific edits applied\n"
    "    (e.g., 'shortened to 3 sentences; removed apology'). Do not summarize the\n"
    "    DRAFT — summarize the DELTA.\n"
    "Output: refined_draft is the new reply, ready to send if the user approves."
)

USER_TEMPLATE = (
    "Current draft:\n{current_draft}\n\n"
    "Refinement instruction from the user:\n{refinement_instruction}\n"
)


class MultiTurnRefinementOutput(BaseModel):
    """Iteratively-refined draft + summary of what changed."""

    model_config = ConfigDict(frozen=True)

    refined_draft: str = Field(description="The new draft after applying the refinement.")
    changes_summary: str = Field(
        max_length=200,
        description="≤ 200-char summary of the delta vs the prior draft.",
    )
    still_needs_clarification: bool = Field(
        description=(
            "True when the refinement instruction was itself ambiguous and the orchestrator "
            "should surface a clarifying turn before presenting the refinement."
        ),
    )


OUTPUT_SCHEMA: type[BaseModel] = MultiTurnRefinementOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "MultiTurnRefinementOutput",
]
