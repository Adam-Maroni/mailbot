"""Closed-set vocabulary for ``router_calls.model_chosen_reason`` (Story 9.2).

Every Router callsite that writes a ``RouterCallRow`` MUST source the
``model_chosen_reason`` value from this module — either the enum member's
``.value`` (for literal members) or one of the three helper functions
(for templated members). The selective-import boundary checker
(``scripts/check_boundaries.py`` rule ``forbid_raw_model_chosen_reason_strings``)
refuses any raw string literal matching this module's stable prefixes
outside the allowlist (``audit_vocab.py`` itself + ``audit.py`` for
validator documentation).

Contract — ten literal members, three templated members (13 total):

Literal members (``.value`` is the exact string written to the DB):
    OVERRIDE_API                       "override:api:force_model"
    OVERRIDE_SLASH_ONE_SHOT            "slash_command:one_shot:adam"
    OVERRIDE_SLASH_PERSISTENT          "slash_command:persistent:adam"
    FALLBACK_TIMEOUT                   "fallback:timeout"
    FALLBACK_BUDGET_REFUSAL_RETRY      "fallback:budget_refusal_retry"
    BENCHMARK_FORCE_MODEL              "benchmark:force_model"
    CACHE_HIT                          "cache:response_cache_hit"
    SENSITIVITY_GATE_REFUSED           "sensitivity_gate:refused"
    SENSITIVITY_GATE_NORMAL            "sensitivity_gate:normal"
    PAUSE_GATE_REFUSED                 "pause_gate:refused"

Templated members (``.value`` is the TEMPLATE; helpers produce the actual write):
    POLICY_DEFAULT                     "policy:<task>:default"
        -> use ``policy_default(task)``
    POLICY_ESCALATION                  "policy:escalation:<from>→<to>"
        -> use ``policy_escalation(from_model, to_model)``
    DEGRADED_MODE_DEMOTION             "degraded:<from>→<to>"
        -> use ``degraded_mode_demotion(from_model, to_model)``

Adding a new routing-decision kind requires adding an enum member here AND
updating the audit validator's accepted-shape list in
``mailbot_api/observability/audit.py``. Raw strings outside this module
are forbidden by the boundary checker.

Migration note (Story 9.2 AC-7): pre-9.2 ``router_calls`` rows carry the
OLD vocabulary (``"policy"``, ``"override"``, ``"degraded"``,
``"response_cache_hit"``, ``"force_override"``, ``"escalated_from_<X>"``).
Old rows stay readable via SQL but cannot round-trip through
``RouterCallRow`` reconstruction — the contract is forward-only. The
Story 9.9 report renderer must accept BOTH vocabularies via SQL ``IN (?, ?)``
until the old values are retired.
"""

from __future__ import annotations

import re
from enum import Enum


class ModelChosenReason(str, Enum):
    """Closed-set values for ``router_calls.model_chosen_reason``.

    String-backed so ``member.value`` is the stable wire string AND
    ``member == "override:api:force_model"`` comparison works.

    For the three TEMPLATED members (``POLICY_DEFAULT``,
    ``POLICY_ESCALATION``, ``DEGRADED_MODE_DEMOTION``), the ``.value`` is
    the documentation template with placeholders — NOT what gets written
    to the DB. Use the corresponding module-level helper function to
    produce the concrete write value with runtime substitutions.
    """

    # ---- Literal members (write .value directly) ------------------------

    OVERRIDE_API = "override:api:force_model"
    """API caller passed ``force_model=...`` (regardless of ``force`` flag).

    The ``force`` boolean still gates degraded-mode behavior (see
    ``router.py``), but the audit vocabulary unifies both branches because
    the routing-analytics distinction between "force=True" and "force=False"
    is internal-only — observers slicing ``router_calls`` care that the
    model came from an API override, not which boolean flag was set.
    """

    OVERRIDE_SLASH_ONE_SHOT = "slash_command:one_shot:adam"
    """Adam typed ``/model <task> <model>`` in a Hermes chat session;
    the session-scoped one-shot flag was consumed on this dispatch.

    Consumed by Story 9.3.
    """

    OVERRIDE_SLASH_PERSISTENT = "slash_command:persistent:adam"
    """Adam typed ``/model <task> <model>`` to write the persistent
    override file ``router/policy.user-overrides.yaml``. Subsequent
    dispatches use the new policy until Adam reverts.

    Consumed by Story 9.4.
    """

    FALLBACK_TIMEOUT = "fallback:timeout"
    """The previously-attempted model timed out; this row records the
    fallback dispatch with a different (typically lower-tier) model.

    NOT YET WIRED (CR-F7): the existing ``router.py:_dispatch_with_failure_chain``
    AdapterTimeout path records the row with whatever ``model_chosen_reason``
    was set BEFORE the exception (typically the policy_default for the
    task). A future story will wire ``FALLBACK_TIMEOUT`` into the timeout
    handler so the audit row carries the explicit fallback intent. Reserved
    for future wiring; consuming story TBD.
    """

    FALLBACK_BUDGET_REFUSAL_RETRY = "fallback:budget_refusal_retry"
    """The previously-attempted model returned a budget-refusal sentinel;
    this row records the retry under a different model.

    NOT YET WIRED (CR-F7): the budget-refusal retry path does not yet
    emit this reason. Reserved for future wiring; consuming story TBD.
    """

    BENCHMARK_FORCE_MODEL = "benchmark:force_model"
    """Benchmark runner forced a specific model for the comparison cohort.

    Consumed by Story 9.6.
    """

    CACHE_HIT = "cache:response_cache_hit"
    """Dispatch was satisfied from ``response_cache`` — no adapter call
    was made. ``cost_usd_estimated == 0`` and ``tokens_in == 0``
    typically accompany this reason."""

    SENSITIVITY_GATE_REFUSED = "sensitivity_gate:refused"
    """The sensitivity gate refused the dispatch (confidential email
    without confirmation token, or sensitive email under API model with
    no handshake)."""

    SENSITIVITY_GATE_NORMAL = "sensitivity_gate:normal"
    """The sensitivity gate validated a confirmation token and allowed
    the dispatch to proceed for a sensitive email."""

    PAUSE_GATE_REFUSED = "pause_gate:refused"
    """Story 10.5.1 (AC-4, F3) — the pause kill-switch refused a dispatch or a
    drainer tick/row because the system was paused. Previously paused refusals
    (router-dispatch 502s AND drainer skips) left NO audit row, so a
    paused-window incident was not reconstructable from ``router_calls``.
    Emitted with ``outcome="failed"``, zero tokens/cost — no adapter call
    happened. Mirrors ``SENSITIVITY_GATE_REFUSED``'s refusal-audit shape."""

    # ---- Templated members (use helpers; .value is documentation only) --

    POLICY_DEFAULT = "policy:<task>:default"
    """Default model picked from ``policy.yaml`` for this ``task_type``.

    DO NOT write ``.value`` directly. Use ``policy_default(task)``.
    """

    POLICY_ESCALATION = "policy:escalation:<from>→<to>"
    """``policy_entry.escalate=True`` triggered a next-tier dispatch.

    DO NOT write ``.value`` directly. Use ``policy_escalation(from, to)``.
    """

    DEGRADED_MODE_DEMOTION = "degraded:<from>→<to>"
    """Degraded-mode demoted the dispatch to a lower-tier model.

    DO NOT write ``.value`` directly. Use ``degraded_mode_demotion(from, to)``.
    """


def policy_default(task: str) -> str:
    """Produce the audit string for a policy-default dispatch.

    Args:
        task: The ``task_type`` from the dispatch (e.g., ``"draft_reply"``).

    Returns:
        ``"policy:<task>:default"`` with the task name substituted.

    Raises:
        ValueError: If ``task`` is empty or whitespace-only (CR-F4: real
            task_type values are snake_case identifiers; an all-whitespace
            string would pass `POLICY_DEFAULT_RE` but is semantically
            nonsense and indicates a caller bug).
    """
    if not task or not task.strip():
        raise ValueError("policy_default: task must be a non-empty, non-whitespace string")
    return f"policy:{task}:default"


def policy_escalation(from_model: str, to_model: str) -> str:
    """Produce the audit string for a policy-driven escalation dispatch.

    Args:
        from_model: The model that was originally picked but escalated away from.
        to_model: The escalated-to model that actually dispatched.

    Returns:
        ``"policy:escalation:<from>→<to>"`` with model IDs substituted.

    Raises:
        ValueError: If either arm is empty or whitespace-only (CR-F4).
    """
    if not from_model or not from_model.strip():
        raise ValueError("policy_escalation: from_model must be a non-empty, non-whitespace string")
    if not to_model or not to_model.strip():
        raise ValueError("policy_escalation: to_model must be a non-empty, non-whitespace string")
    return f"policy:escalation:{from_model}→{to_model}"


def degraded_mode_demotion(from_model: str, to_model: str) -> str:
    """Produce the audit string for a degraded-mode demotion dispatch.

    Args:
        from_model: The model that was picked by policy before degraded
            mode demoted it.
        to_model: The demoted-to model that actually dispatched.

    Returns:
        ``"degraded:<from>→<to>"`` with model IDs substituted.

    Raises:
        ValueError: If either arm is empty or whitespace-only (CR-F4).
    """
    if not from_model or not from_model.strip():
        raise ValueError("degraded_mode_demotion: from_model must be a non-empty, non-whitespace string")
    if not to_model or not to_model.strip():
        raise ValueError("degraded_mode_demotion: to_model must be a non-empty, non-whitespace string")
    return f"degraded:{from_model}→{to_model}"


# ---- Validator support (co-located so audit.py imports a leaf module) -------

# Audit-validator-facing constants. ``audit.py`` consumes these to check
# incoming ``model_chosen_reason`` strings against the four accepted shapes.
# Co-locating with the enum/helpers avoids a circular import (``audit.py`` is
# imported by ``router.router`` which is imported by ``router/__init__.py``;
# putting the enum inside ``router/`` means importing from ``router.foo`` runs
# the package ``__init__`` — so we keep this module a pure leaf and provide
# the validator inputs from here).

LITERAL_REASONS: frozenset[str] = frozenset(
    member.value
    for member in ModelChosenReason
    if "<" not in member.value  # templates carry placeholder brackets
)
"""Literal enum-member values accepted by the audit validator verbatim."""

_MODEL_ID_RE_FRAGMENT = r"[\w.:\-]+"
"""Character class for model identifiers — accepts Ollama IDs with colons
(e.g., ``qwen2.5:3b-instruct-q4_K_M``) and dotted-hyphenated Anthropic IDs."""

POLICY_DEFAULT_RE = re.compile(r"^policy:[^:]+:default$")
"""Matches strings produced by ``policy_default(task)``."""

POLICY_ESCALATION_RE = re.compile(
    rf"^policy:escalation:{_MODEL_ID_RE_FRAGMENT}→{_MODEL_ID_RE_FRAGMENT}$"
)
"""Matches strings produced by ``policy_escalation(from_model, to_model)``."""

DEGRADED_RE = re.compile(rf"^degraded:{_MODEL_ID_RE_FRAGMENT}→{_MODEL_ID_RE_FRAGMENT}$")
"""Matches strings produced by ``degraded_mode_demotion(from_model, to_model)``."""


__all__: list[str] = [
    "ModelChosenReason",
    "policy_default",
    "policy_escalation",
    "degraded_mode_demotion",
    "LITERAL_REASONS",
    "POLICY_DEFAULT_RE",
    "POLICY_ESCALATION_RE",
    "DEGRADED_RE",
]
