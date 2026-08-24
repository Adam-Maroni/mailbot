"""Per-call cost gate — the single source of truth for "is this dispatch
affordable, and if not, refuse + announce it".

Story 11.6.1 (re-scoped): the original "one big resolve_and_gate seam" premise
did not survive source-mapping — pause and model-resolution differ per dispatch
path, and the guard chain is non-contiguous (split by the out-of-scope
sensitivity handshake). The ONE genuinely-shared, drift-prone fragment is the
per-call cost check: threshold comparison + the GitHub-#4 `budget.per_call.refused`
log. That policy is consolidated here so `ask_router` and `dispatch_tool_call`
cannot silently drift on what counts as "too expensive" or forget to log a refusal.

Deliberately NOT consolidated (they legitimately differ per caller):
  * token counting — `ask_router` uses prompt/user_msg length; `dispatch_tool_call`
    sums message + tool-schema text. So `estimated_tokens_in` is a caller INPUT.
  * the force bypass — `ask_router` has `force`; `dispatch_tool_call` has none
    (it refuses unconditionally). Callers pass `force`/`force_capable` explicitly;
    the seam never invents a bypass.
  * the result envelope — callers wrap the returned `RouterError` into their own
    `RouterResult` / `ToolCallResult`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mailbot_api.router.budget import PER_CALL_REFUSAL_THRESHOLD_USD
from mailbot_api.router.errors import ErrorCode, RouterError
from mailbot_api.router.pricing import estimate_cost_usd

_logger = logging.getLogger(__name__)


@dataclass
class GateOutcome:
    """Facts from the per-call cost gate. The caller builds its own result type.

    * ``refused`` — True ⇒ stop and return a refusal built from ``error``.
    * ``error`` — the `RouterError` to wrap (non-None iff ``refused``).
    * ``estimated_cost`` — the computed per-call cost (returned either way, so a
      caller may record it on the proceed path if it wants).
    """

    refused: bool
    error: RouterError | None
    estimated_cost: float


def price_and_gate(
    *,
    model: str,
    estimated_tokens_in: int,
    max_tokens_out: int,
    email_id: str | None,
    force: bool = False,
    force_capable: bool = False,
) -> GateOutcome:
    """Compute the per-call cost and refuse if it exceeds the threshold.

    ``force`` (only meaningful when ``force_capable``) bypasses the gate — this
    mirrors `ask_router`'s ``and not force``. `dispatch_tool_call` passes neither
    (``force_capable=False``), so it refuses unconditionally exactly as before.

    ``force_capable`` also controls the refusal message: force-capable callers
    get the "; pass force=True to override" suffix (preserving `ask_router`'s
    original wording); non-force callers get the bare message (preserving
    `dispatch_tool_call`'s). No behaviour change — the two messages are kept
    byte-identical to their pre-consolidation form.
    """
    # strict=False: Router paths price models that policy/registry already vetted;
    # test fixtures also register fake model names here. The strict raise
    # (F-UNKNOWN-MODEL-COST-GATE) is for pre-flight spend gates, not this net.
    estimated_cost = estimate_cost_usd(
        model, estimated_tokens_in, max_tokens_out, strict=False
    )

    over_threshold = estimated_cost > PER_CALL_REFUSAL_THRESHOLD_USD
    bypassed = force_capable and force
    if not (over_threshold and not bypassed):
        return GateOutcome(refused=False, error=None, estimated_cost=estimated_cost)

    # Story 11.5.4 (GitHub #4): the per-call refusal was the one budget guard
    # that refused SILENTLY. Emit a structured line matching the budget.*
    # convention so on-call has something to grep.
    _logger.warning(
        "per-call cost threshold exceeded — refusing dispatch",
        extra={
            "event": "budget.per_call.refused",
            "model": model,
            "estimated_cost_usd": estimated_cost,
            "threshold_usd": PER_CALL_REFUSAL_THRESHOLD_USD,
            "estimated_tokens_in": estimated_tokens_in,
            "email_id": email_id,
        },
    )
    suffix = "; pass force=True to override" if force_capable else ""
    error = RouterError(
        code=ErrorCode.PER_CALL_THRESHOLD_EXCEEDED,
        message=(
            f"estimated cost ${estimated_cost:.4f} exceeds "
            f"per-call threshold ${PER_CALL_REFUSAL_THRESHOLD_USD:.2f}{suffix}"
        ),
        retryable=False,
        model_attempted=[model],
    )
    return GateOutcome(refused=True, error=error, estimated_cost=estimated_cost)
