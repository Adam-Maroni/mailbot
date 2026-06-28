"""Story 9-7 AC-8: Krippendorff's α (ordinal data) — pure leaf.

Cross-evaluator agreement coefficient on ordinal 1-5 anchor scores.
Used by ``benchmark/scoring/subjective.py`` to compute the agreement
between the primary evaluator (Opus) and a secondary evaluator (Sonnet
by default) on the 20 hand-anchored items from Story 9-5.

Algorithm: Krippendorff's α with the **ordinal δ² metric** (per
Krippendorff 2018, "Content Analysis: An Introduction to Its Methodology",
section 12.4). The ordinal metric treats the distance between adjacent
score-levels as larger than between non-adjacent levels but with a
non-linear ramp that respects the implicit ordering of ratings.

Reference textbook formulation (transcribed for documentation purposes;
implementation below mirrors this verbatim):

    α = 1 − D_observed / D_expected

    where for a set of N units (rated items) and R raters:
        D_observed = (1 / total_pairable) * Σ_units (1 / (n_u − 1)) *
                     Σ_{c < k} n_uc * n_uk * δ²(c, k)
        D_expected = (1 / (total_pairable * (total_pairable - 1)))
                     * Σ_{c < k} N_c * N_k * δ²(c, k)
        δ²(c, k) for ordinal data = (Σ_{g=c}^{k} N_g − (N_c + N_k) / 2)²

    n_uc = count of raters who rated unit u with value c
    N_c  = total raters who used value c across all units
    total_pairable = Σ_units n_u   [sum of per-unit rater counts; the
        per-unit (n_u − 1) factor is applied INSIDE the unit loop above
        rather than collapsed into total_pairable. CR-F6 (LOW) 2026-06-28:
        the prior docstring stated `total_pairable = Σ_units (n_u * (n_u−1))`
        which is the textbook compact form — algebraically equivalent for
        uniform n_u (the 2-rater production case) but the implementation
        below uses the expanded form (split denominators) to make the
        per-unit `/ (n_u − 1)` explicit. This avoids a real denominator
        bug if a future change extends to 3+ raters with varying
        missing-data patterns where the two forms would diverge.]

α range: [-1.0, 1.0].
  α = 1.0  → perfect agreement
  α = 0.0  → chance (no agreement signal)
  α < 0    → systematic disagreement (worse than chance)

Pure-leaf — no I/O, no config reads, no DB. numpy-only (no scipy /
pyagreement / krippendorff-pip-package; Rule M dependency minimization).

Per-anchor agreement bookkeeping (the {anchor_id, primary_score,
secondary_score, delta} per-anchor breakdown the scorer writes into
``extra_json``) is computed by the caller — this module only returns the
scalar α.
"""

from __future__ import annotations

import numpy as np


def krippendorff_alpha_ordinal(rater_scores: dict[str, list[float | None]]) -> float:
    """Compute Krippendorff's α (ordinal scale) over per-rater score lists.

    Args:
        rater_scores: mapping ``rater_id -> [score_per_item]``. ``None``
            entries indicate the rater did not score that item; missing
            data is handled by treating the unit as unpairable for that
            rater (Krippendorff's "missing data is not the same as
            non-agreement" principle).

    Returns:
        α in [-1.0, 1.0]. Degenerate cases:
          * All raters agree perfectly on every item → 1.0
          * All ratings are identical across raters AND units → 1.0
            (no variability; agreement is trivially perfect)

    Raises:
        ValueError: fewer than 2 raters; rater rows of mismatched length.
    """
    if len(rater_scores) < 2:
        raise ValueError(
            f"Krippendorff α requires ≥ 2 raters; got {len(rater_scores)}"
        )

    lengths = {len(scores) for scores in rater_scores.values()}
    if len(lengths) > 1:
        raise ValueError(
            f"Krippendorff α requires equal-length rater rows; got lengths {sorted(lengths)}"
        )
    n_items = lengths.pop()
    if n_items == 0:
        raise ValueError("Krippendorff α requires ≥ 1 rated item")

    # Build the units × raters matrix; missing data is np.nan.
    rater_ids = sorted(rater_scores.keys())
    matrix = np.full((n_items, len(rater_ids)), np.nan, dtype=np.float64)
    for col, rater_id in enumerate(rater_ids):
        for row, score in enumerate(rater_scores[rater_id]):
            if score is not None:
                matrix[row, col] = float(score)

    # Drop items where < 2 raters scored (unpairable per Krippendorff).
    valid_mask = (~np.isnan(matrix)).sum(axis=1) >= 2
    matrix = matrix[valid_mask]
    if matrix.shape[0] == 0:
        raise ValueError("Krippendorff α requires ≥ 1 item with ≥ 2 ratings")

    # Discover the value-domain (sorted unique non-nan values across all cells).
    flat_finite = matrix[~np.isnan(matrix)]
    values = np.unique(flat_finite)
    if values.size == 1:
        # All ratings identical → perfect agreement (degenerate but informative).
        return 1.0

    # Per-unit value counts: n_uc = # raters who scored unit u with value c.
    # Shape: (n_items_valid, n_values).
    n_uc = np.zeros((matrix.shape[0], values.size), dtype=np.float64)
    for col_idx, val in enumerate(values):
        n_uc[:, col_idx] = (matrix == val).sum(axis=1)

    # Marginal value counts across all units: N_c.
    N_c = n_uc.sum(axis=0)
    # Number of raters who scored each unit (n_u in Krippendorff's notation).
    n_u = n_uc.sum(axis=1)

    # Ordinal δ²(c, k) per Krippendorff 2018 § 12.4:
    #   δ²(c, k) = (Σ_{g=c}^{k} N_g − (N_c + N_k) / 2)²
    # where the summation runs over the SORTED value domain and
    # includes both endpoints. Symmetric: δ²(c, k) = δ²(k, c).
    n_values = values.size
    cumsum_N = np.cumsum(N_c)
    # Σ_{g=c}^{k} N_g = cumsum_N[k] − cumsum_N[c] + N_c[c]   (k ≥ c)
    delta_sq = np.zeros((n_values, n_values), dtype=np.float64)
    for c_idx in range(n_values):
        for k_idx in range(c_idx + 1, n_values):
            sum_g = cumsum_N[k_idx] - cumsum_N[c_idx] + N_c[c_idx]
            term = sum_g - (N_c[c_idx] + N_c[k_idx]) / 2.0
            d2 = term * term
            delta_sq[c_idx, k_idx] = d2
            delta_sq[k_idx, c_idx] = d2

    # Observed disagreement: (1 / total_pairable) * Σ_units Σ_{c < k} n_uc * n_uk * δ²(c, k).
    # total_pairable is the sum over all units of n_u (NOT n_u * (n_u - 1)) —
    # this is the canonical denominator from Krippendorff's reliability paper.
    total_pairable = float(n_u.sum())
    if total_pairable == 0.0:
        raise ValueError("Krippendorff α: zero pairable observations after dropping unscored items")

    # Per-unit disagreement sum.
    observed_disagree = 0.0
    for u_idx in range(matrix.shape[0]):
        n_u_val = n_u[u_idx]
        if n_u_val <= 1:
            continue
        # Σ_{c < k} n_uc * n_uk * δ²(c, k), scaled by 1 / (n_u - 1).
        unit_contrib = 0.0
        for c_idx in range(n_values):
            for k_idx in range(c_idx + 1, n_values):
                unit_contrib += n_uc[u_idx, c_idx] * n_uc[u_idx, k_idx] * delta_sq[c_idx, k_idx]
        observed_disagree += unit_contrib / (n_u_val - 1.0)
    observed_disagree /= total_pairable

    # Expected disagreement: (1 / (total_pairable * (total_pairable - 1)))
    #                       * Σ_{c < k} N_c * N_k * δ²(c, k).
    expected_disagree = 0.0
    for c_idx in range(n_values):
        for k_idx in range(c_idx + 1, n_values):
            expected_disagree += N_c[c_idx] * N_c[k_idx] * delta_sq[c_idx, k_idx]
    denom = total_pairable * (total_pairable - 1.0)
    if denom == 0.0:
        return 1.0
    expected_disagree /= denom

    if expected_disagree == 0.0:
        # No variability across the value domain — perfect agreement.
        return 1.0

    alpha = 1.0 - observed_disagree / expected_disagree
    # Clamp to the formal [-1, 1] range to insulate downstream consumers
    # from floating-point drift at the boundary.
    return float(max(-1.0, min(1.0, alpha)))


__all__ = ["krippendorff_alpha_ordinal"]
