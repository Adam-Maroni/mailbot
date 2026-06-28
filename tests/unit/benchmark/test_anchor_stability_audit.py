"""Story 9-11: anchor stability audit CLI unit tests.

Six scenarios (per Story file Task 5):
  5.1  ``_classify_alpha`` thresholds (trusted / uncertain / untrusted /
       negative α).
  5.2  ``_compose_baseline`` produces deterministic per-anchor ordering
       (sorted by anchor_id; same input → byte-identical JSON).
  5.3  CLI happy-path with FakeAdapter-scripted scores writes the
       canonical output path; α matches hand-computed value.
  5.4  CLI on `untrusted` α writes the FAILED-CALIBRATION path NOT the
       canonical path; exits 2; stderr contains per-anchor table.
  5.5  Re-running the audit within 24h triggers Story 2-7 response cache
       hits (assert via call_count diff — second invocation issues 0 new
       dispatches; AC-7).
  5.6  Cost-gate at $5 threshold honors `--yes` bypass.

FakeAdapter pattern at the adapter boundary preserves Rule I coverage
(Router precondition layer + sensitivity gate + cache + audit write all
run end-to-end).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchmark.anchor_baselines import PerAnchorScore
from benchmark.anchor_stability_audit import (
    _classify_alpha,
    _compose_baseline,
    _failed_calibration_path,
    _serialize_baseline,
    main,
)
from evals.corpus_schema import AnchorItem
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter


@pytest.fixture(autouse=True)
def _clean_router_state(tmp_path: Path) -> Iterator[None]:
    """Reset all module-level Router state before + after each test."""
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_semaphore_registry_for_test()
    _reset_loop_detector_for_test()
    _reset_rate_limiter_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()
    # Load the production policy so anchor_calibrated_eval task is registered.
    policy = load_policy(Path("router/policy.yaml"))
    set_policy_snapshot(policy)
    yield
    _reset_policy_snapshot_for_test()
    _reset_guard_for_test()
    _reset_semaphore_registry_for_test()
    _reset_loop_detector_for_test()
    _reset_rate_limiter_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()


def _adapter_response(text: str, tokens_out: int = 20) -> AdapterResponse:
    return AdapterResponse(
        text=text,
        tokens_in=100,
        tokens_out=tokens_out,
        cached_tokens_in=0,
        latency_ms=5,
        raw={},
    )


class _ScriptedEvaluatorAdapter:
    """Adapter that returns a constant overall_score per call.

    Used to script primary + secondary evaluator behavior for the audit.
    """

    def __init__(
        self,
        overall_score: int,
        per_axis_scores: dict[str, int],
        model_id: str,
    ) -> None:
        self.overall_score = overall_score
        self.per_axis_scores = per_axis_scores
        self.model_id = model_id
        self.call_log: list[dict[str, Any]] = []

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        self.call_log.append(
            {
                "system": system,
                "user": user,
                "max_tokens_out": max_tokens_out,
                "temperature": temperature,
            }
        )
        body = json.dumps(
            {
                "overall_score": self.overall_score,
                "per_axis_scores": self.per_axis_scores,
            }
        )
        return _adapter_response(body)


def _anchor(idx: int, adam_overall: int, task: str = "draft_reply") -> AnchorItem:
    axes = (
        {"faithfulness": adam_overall, "tone_match": adam_overall, "actionability": adam_overall}
        if task == "draft_reply"
        else {"faithfulness": adam_overall, "concision": adam_overall, "actionability": adam_overall}
    )
    return AnchorItem.model_validate(
        {
            "id": f"anchor-{task}-{idx:03d}",
            "task": task,
            "corpus_item_id": None,
            "input_email_subject": f"Subject {idx}",
            "input_email_body": f"Body of email {idx}.",
            "model_output": json.dumps({"reply": f"Reply for anchor {idx}"}),
            "adam_score_axes": axes,
            "adam_overall_score": adam_overall,
            "score_rationale": f"Rationale for anchor {idx}",
        }
    )


def _write_anchors_dir(
    anchors_root: Path,
    *,
    summary_short: list[AnchorItem],
    draft_reply: list[AnchorItem],
    version: str = "v1",
) -> None:
    anchors_root.mkdir(parents=True, exist_ok=True)
    (anchors_root / "VERSION").write_text(version + "\n", encoding="utf-8")
    with (anchors_root / "summary_short_anchors.jsonl").open("w", encoding="utf-8") as fh:
        for a in summary_short:
            fh.write(json.dumps(a.model_dump()) + "\n")
    with (anchors_root / "draft_reply_anchors.jsonl").open("w", encoding="utf-8") as fh:
        for a in draft_reply:
            fh.write(json.dumps(a.model_dump()) + "\n")


# Scenario 5.1 — verdict-threshold boundaries
@pytest.mark.parametrize(
    "alpha,expected",
    [
        (1.0, "trusted"),
        (0.8, "trusted"),  # exactly at boundary → trusted
        (0.7999, "uncertain"),  # just below trusted
        (0.6, "uncertain"),  # exactly at lower boundary → uncertain
        (0.5999, "untrusted"),  # just below uncertain
        (0.0, "untrusted"),
        (-0.5, "untrusted"),
        (-1.0, "untrusted"),
    ],
)
def test_classify_alpha_thresholds(alpha: float, expected: str) -> None:
    assert _classify_alpha(alpha) == expected


# Scenario 5.2 — deterministic per-anchor ordering
def test_compose_baseline_per_anchor_sorted_by_id() -> None:
    rows = [
        PerAnchorScore(
            anchor_id="anchor-draft_reply-005",
            task="draft_reply",
            primary_score=3,
            secondary_score=3,
            delta=0,
        ),
        PerAnchorScore(
            anchor_id="anchor-draft_reply-001",
            task="draft_reply",
            primary_score=4,
            secondary_score=2,
            delta=2,
        ),
        PerAnchorScore(
            anchor_id="anchor-summary_short-002",
            task="summary_short",
            primary_score=5,
            secondary_score=4,
            delta=1,
        ),
    ]
    snap1 = _compose_baseline(
        primary_evaluator="opus",
        secondary_evaluator="sonnet",
        anchors_version="v1",
        per_anchor_scores=rows,
        alpha=0.85,
        verdict="trusted",
        baseline_date="2026-06-28",
    )
    ids_in_order = [r.anchor_id for r in snap1.per_anchor_scores]
    assert ids_in_order == sorted(ids_in_order)
    # Byte-identical re-serialize even when input list ordering differs.
    rows_reversed = list(reversed(rows))
    snap2 = _compose_baseline(
        primary_evaluator="opus",
        secondary_evaluator="sonnet",
        anchors_version="v1",
        per_anchor_scores=rows_reversed,
        alpha=0.85,
        verdict="trusted",
        baseline_date="2026-06-28",
    )
    assert _serialize_baseline(snap1) == _serialize_baseline(snap2)


# Scenario 5.3 — CLI happy-path writes canonical baseline file
def test_cli_happy_path_writes_canonical_baseline(tmp_path: Path) -> None:
    """Both evaluators agree perfectly → α = 1.0 → trusted → canonical path."""
    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(i + 1, adam_overall=3, task="summary_short") for i in range(3)]
    draft = [_anchor(i + 1, adam_overall=4, task="draft_reply") for i in range(3)]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)

    primary = _ScriptedEvaluatorAdapter(
        overall_score=4,
        per_axis_scores={"faithfulness": 4, "tone_match": 4, "actionability": 4},
        model_id="claude-opus-4-7",
    )
    secondary = _ScriptedEvaluatorAdapter(
        overall_score=4,
        per_axis_scores={"faithfulness": 4, "tone_match": 4, "actionability": 4},
        model_id="claude-sonnet-4-5",
    )
    register_adapter("claude-opus-4-7", primary)
    register_adapter("claude-sonnet-4-5", secondary)

    output = tmp_path / "anchor_baselines" / "v1.json"
    exit_code = main(
        [
            "--evaluators",
            "primary,secondary",
            "--primary-model",
            "claude-opus-4-7",
            "--secondary-model",
            "claude-sonnet-4-5",
            "--output",
            str(output),
            "--db-path",
            db_path,
            "--anchors-dir",
            str(anchors_dir),
            "--tasks",
            "summary_short,draft_reply",
            "--yes",
            "--cost-mock",
        ]
    )
    assert exit_code == 0
    assert output.is_file()
    failed = _failed_calibration_path(output)
    assert not failed.exists(), "trusted verdict should NOT write FAILED-CALIBRATION sibling"

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["verdict"] == "trusted"
    # All anchors agree perfectly so α = 1.0 (degenerate-but-perfect case).
    assert payload["krippendorff_alpha"] == 1.0
    assert payload["primary_evaluator"] == "claude-opus-4-7"
    assert payload["secondary_evaluator"] == "claude-sonnet-4-5"
    assert payload["anchors_version"] == "v1"
    assert len(payload["per_anchor_scores"]) == 6  # 3 + 3 paired


# Scenario 5.4 — CLI on untrusted α writes FAILED-CALIBRATION + exits 2
def test_cli_untrusted_writes_failed_calibration_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Primary returns 5, secondary returns 1 on all anchors → α near -1 → untrusted."""
    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    # Need enough anchors for the ordinal α to be meaningfully negative;
    # use 5 per task → 10 paired.
    summary = [_anchor(i + 1, adam_overall=3, task="summary_short") for i in range(5)]
    draft = [_anchor(i + 1, adam_overall=3, task="draft_reply") for i in range(5)]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)

    primary = _ScriptedEvaluatorAdapter(
        overall_score=5,
        per_axis_scores={"faithfulness": 5, "tone_match": 5, "actionability": 5},
        model_id="claude-opus-4-7",
    )
    secondary = _ScriptedEvaluatorAdapter(
        overall_score=1,
        per_axis_scores={"faithfulness": 1, "tone_match": 1, "actionability": 1},
        model_id="claude-sonnet-4-5",
    )
    register_adapter("claude-opus-4-7", primary)
    register_adapter("claude-sonnet-4-5", secondary)

    output = tmp_path / "anchor_baselines" / "v1.json"
    exit_code = main(
        [
            "--evaluators",
            "primary,secondary",
            "--primary-model",
            "claude-opus-4-7",
            "--secondary-model",
            "claude-sonnet-4-5",
            "--output",
            str(output),
            "--db-path",
            db_path,
            "--anchors-dir",
            str(anchors_dir),
            "--tasks",
            "summary_short,draft_reply",
            "--yes",
            "--cost-mock",
        ]
    )
    assert exit_code == 2
    assert not output.exists(), "untrusted verdict must NOT write canonical baseline"
    fail = _failed_calibration_path(output)
    assert fail.is_file()
    payload = json.loads(fail.read_text(encoding="utf-8"))
    assert payload["verdict"] == "untrusted"

    captured = capsys.readouterr()
    # Per-anchor table goes to stderr in tab-separated form.
    assert "anchor_id\ttask\tprimary\tsecondary\tdelta" in captured.err
    # delta = abs(5 - 1) = 4 for every anchor.
    assert "\t4" in captured.err


# Scenario 5.5 — re-running within 24h triggers Story 2-7 response cache reuse
def test_cli_rerun_within_24h_reuses_response_cache(tmp_path: Path) -> None:
    """Re-running the audit a second time issues 0 new adapter calls."""
    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(i + 1, adam_overall=3, task="summary_short") for i in range(2)]
    draft = [_anchor(i + 1, adam_overall=3, task="draft_reply") for i in range(2)]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)

    primary = _ScriptedEvaluatorAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7",
    )
    secondary = _ScriptedEvaluatorAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-sonnet-4-5",
    )
    register_adapter("claude-opus-4-7", primary)
    register_adapter("claude-sonnet-4-5", secondary)

    output = tmp_path / "anchor_baselines" / "v1.json"
    argv = [
        "--evaluators",
        "primary,secondary",
        "--primary-model",
        "claude-opus-4-7",
        "--secondary-model",
        "claude-sonnet-4-5",
        "--output",
        str(output),
        "--db-path",
        db_path,
        "--anchors-dir",
        str(anchors_dir),
        "--tasks",
        "summary_short,draft_reply",
        "--yes",
        "--cost-mock",
    ]

    assert main(argv) == 0
    first_run_primary_calls = len(primary.call_log)
    first_run_secondary_calls = len(secondary.call_log)
    # 4 anchors (2 per task) × 2 evaluators = 8 dispatches.
    assert first_run_primary_calls == 4
    assert first_run_secondary_calls == 4

    # Second run within 24h — Story 2-7 response cache should short-circuit
    # every dispatch (caller key = task_type + prompt_version + content
    # hash + model — identical input).
    assert main(argv) == 0
    assert len(primary.call_log) == first_run_primary_calls
    assert len(secondary.call_log) == first_run_secondary_calls


# Scenario 5.6 — cost-gate honors --yes
def test_cli_cost_gate_yes_bypasses_confirmation(tmp_path: Path) -> None:
    """--yes bypasses the cost gate without prompting (no EOFError raised)."""
    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(i + 1, adam_overall=3, task="summary_short") for i in range(1)]
    draft = [_anchor(i + 1, adam_overall=3, task="draft_reply") for i in range(1)]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)
    primary = _ScriptedEvaluatorAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7",
    )
    secondary = _ScriptedEvaluatorAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-sonnet-4-5",
    )
    register_adapter("claude-opus-4-7", primary)
    register_adapter("claude-sonnet-4-5", secondary)
    output = tmp_path / "anchor_baselines" / "v1.json"

    # Run with --yes; should NOT raise EOFError or hang on input().
    exit_code = main(
        [
            "--evaluators",
            "primary,secondary",
            "--primary-model",
            "claude-opus-4-7",
            "--secondary-model",
            "claude-sonnet-4-5",
            "--output",
            str(output),
            "--db-path",
            db_path,
            "--anchors-dir",
            str(anchors_dir),
            "--tasks",
            "summary_short,draft_reply",
            "--yes",
            "--cost-mock",
        ]
    )
    assert exit_code == 0


# Scenario 5.6b (CR-F4 LOW) — cost-gate ACTUALLY fires above threshold;
# --yes short-circuits _confirm_proceed even when the gate trips.
def test_cli_cost_gate_yes_bypasses_above_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkey-patch the cost threshold to 0.0 so the gate ALWAYS trips.

    Then with `--yes`, the bypass path must short-circuit `_confirm_proceed`
    without prompting (no EOFError raised in non-TTY) and the audit must
    complete normally (exit 0). Without `--yes`, the prior 5.6 test covers
    the under-threshold case where the gate never fires.

    Closes CR-F4: prior 5.6 with n_anchors_per_task=1 + n_tasks=2 estimated
    a tiny cost well below $5, so `_confirm_proceed` was never called and
    the --yes bypass path was implicitly untested.
    """
    import benchmark.anchor_stability_audit as audit_mod

    # Force gate to trip on ANY positive cost estimate.
    monkeypatch.setattr(audit_mod, "_COST_GATE_THRESHOLD_USD", 0.0)

    # Make _confirm_proceed raise if --yes does NOT short-circuit it.
    # Use a sentinel exception distinguishable from EOFError so the test
    # asserts the bypass took the right path.
    class _ShouldNotPrompt(Exception):
        pass

    def _boom(_prompt: str) -> bool:
        raise _ShouldNotPrompt("--yes failed to bypass _confirm_proceed")

    monkeypatch.setattr(audit_mod, "_confirm_proceed", _boom)

    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(i + 1, adam_overall=3, task="summary_short") for i in range(2)]
    draft = [_anchor(i + 1, adam_overall=3, task="draft_reply") for i in range(2)]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)
    primary = _ScriptedEvaluatorAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-opus-4-7",
    )
    secondary = _ScriptedEvaluatorAdapter(
        overall_score=3,
        per_axis_scores={"faithfulness": 3, "tone_match": 3, "actionability": 3},
        model_id="claude-sonnet-4-5",
    )
    register_adapter("claude-opus-4-7", primary)
    register_adapter("claude-sonnet-4-5", secondary)

    output = tmp_path / "anchor_baselines" / "v1.json"
    exit_code = main(
        [
            "--evaluators",
            "primary,secondary",
            "--primary-model",
            "claude-opus-4-7",
            "--secondary-model",
            "claude-sonnet-4-5",
            "--output",
            str(output),
            "--db-path",
            db_path,
            "--anchors-dir",
            str(anchors_dir),
            "--tasks",
            "summary_short,draft_reply",
            "--yes",
            "--cost-mock",
        ]
    )
    # --yes bypassed the gate cleanly; _confirm_proceed was NOT called
    # (else _ShouldNotPrompt would have propagated as SystemExit/CalledError
    # from asyncio.run). Exit 0 confirms the audit finished.
    assert exit_code == 0
    assert output.is_file()


# Scenario 5.6c (CR-F3 MEDIUM) — cost-gate user-declines returns exit 1
# (NOT 0) so CI can distinguish "user aborted" from "baseline written".
def test_cli_cost_gate_user_decline_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """User declines the cost-gate prompt → exit code 1 (not 0).

    Closes CR-F3: the prior code returned 0 on decline, which is a false
    success signal for any CI pipeline checking for baseline creation.
    """
    import benchmark.anchor_stability_audit as audit_mod

    monkeypatch.setattr(audit_mod, "_COST_GATE_THRESHOLD_USD", 0.0)
    # User declines (returns False) — should yield exit 1.
    monkeypatch.setattr(audit_mod, "_confirm_proceed", lambda _prompt: False)

    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(1, adam_overall=3, task="summary_short")]
    draft = [_anchor(1, adam_overall=3, task="draft_reply")]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)
    # No adapter registration needed — should bail BEFORE dispatch.
    output = tmp_path / "anchor_baselines" / "v1.json"
    exit_code = main(
        [
            "--evaluators",
            "primary,secondary",
            "--primary-model",
            "claude-opus-4-7",
            "--secondary-model",
            "claude-sonnet-4-5",
            "--output",
            str(output),
            "--db-path",
            db_path,
            "--anchors-dir",
            str(anchors_dir),
            "--tasks",
            "summary_short,draft_reply",
            "--cost-mock",
            # NOTE: no --yes flag so the cost gate fires and decline-path is taken.
        ]
    )
    assert exit_code == 1
    assert not output.is_file(), "decline path must NOT write canonical baseline"


# Scenario 5.6d (CR-F1 HIGH) — zero-pairs guard: when every dispatch fails,
# audit exits 2 WITHOUT raising Pydantic ValidationError and WITHOUT writing
# the FAILED-CALIBRATION sibling (no valid payload to persist).
def test_cli_zero_pairs_exits_2_without_crash(tmp_path: Path) -> None:
    """All dispatches fail (adapter returns malformed body) → exit 2, no file."""
    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(i + 1, adam_overall=3, task="summary_short") for i in range(2)]
    draft = [_anchor(i + 1, adam_overall=3, task="draft_reply") for i in range(2)]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)

    # Adapter that returns non-JSON garbage → SubjectiveAutoEvalOutput
    # validation fails → _dispatch_eval returns None → calibration skips
    # the anchor → all_pairs stays empty.
    class _BrokenAdapter:
        def __init__(self, model_id: str) -> None:
            self.model_id = model_id
            self.call_log: list[dict[str, Any]] = []

        async def call(
            self,
            system: str,
            user: str,
            max_tokens_out: int,
            temperature: float = 0.0,
        ) -> AdapterResponse:
            self.call_log.append({"system": system, "user": user})
            return _adapter_response("not-a-json-blob")

    register_adapter("claude-opus-4-7", _BrokenAdapter("claude-opus-4-7"))
    register_adapter("claude-sonnet-4-5", _BrokenAdapter("claude-sonnet-4-5"))

    output = tmp_path / "anchor_baselines" / "v1.json"
    exit_code = main(
        [
            "--evaluators",
            "primary,secondary",
            "--primary-model",
            "claude-opus-4-7",
            "--secondary-model",
            "claude-sonnet-4-5",
            "--output",
            str(output),
            "--db-path",
            db_path,
            "--anchors-dir",
            str(anchors_dir),
            "--tasks",
            "summary_short,draft_reply",
            "--yes",
            "--cost-mock",
        ]
    )
    assert exit_code == 2
    assert not output.is_file()
    fail = _failed_calibration_path(output)
    assert not fail.is_file(), "zero-pairs branch must NOT write FAILED-CALIBRATION either"


# Bonus — --evaluators that omits 'secondary' is rejected with SystemExit
def test_cli_rejects_evaluators_without_secondary(tmp_path: Path) -> None:
    """--evaluators primary alone is meaningless for cross-evaluator α."""
    db_path = str(tmp_path / "audit.db")
    apply_pending_migrations(db_path)
    anchors_dir = tmp_path / "anchors"
    summary = [_anchor(1, adam_overall=3, task="summary_short")]
    draft = [_anchor(1, adam_overall=3, task="draft_reply")]
    _write_anchors_dir(anchors_dir, summary_short=summary, draft_reply=draft)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--evaluators",
                "primary",
                "--output",
                str(tmp_path / "out.json"),
                "--db-path",
                db_path,
                "--anchors-dir",
                str(anchors_dir),
                "--yes",
            ]
        )
    assert "primary" in str(exc.value) and "secondary" in str(exc.value)


# Bonus — _failed_calibration_path derives sibling correctly
def test_failed_calibration_path_derives_sibling() -> None:
    p = Path("evals/anchor_baselines/v1.json")
    assert _failed_calibration_path(p) == Path(
        "evals/anchor_baselines/v1-FAILED-CALIBRATION.json"
    )
    p2 = Path("/abs/path/v2.json")
    assert _failed_calibration_path(p2) == Path(
        "/abs/path/v2-FAILED-CALIBRATION.json"
    )
