"""Story 9-7: per-task scoring leaves (objective + subjective).

Submodules:

* ``benchmark.scoring.objective`` — exact-match classification scorer
  (``coarse_class``, ``sensitivity_class``, ``fine_class``) and
  field-level extraction scorer (``action_extraction``). Both produce
  ``benchmark_scores`` rows with ``scorer_model="objective:mechanical"``.
* ``benchmark.scoring.subjective`` — anchor-calibrated auto-eval scorer
  for ``draft_reply`` and ``summary_short``; dispatches via
  ``ask_router(task_type="anchor_calibrated_eval", force_model=<scorer>,
  force=True, caller_origin="benchmark-scorer", email_id=None)`` per
  Rule I. Owns the calibration-MAE check + the cross-evaluator
  Krippendorff α computation.
"""
