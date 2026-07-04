"""Story 9.5.5: policy.yaml v0→v1 bump — regression tests (AC-4 + AC-5).

AC-4 — the v1 file is load-bearing config:
  1. ``load_policy()`` succeeds on the repo's REAL ``router/policy.yaml``
     (not a fixture — the whole point is guarding the shipped file).
  2. The version field reads as the v1 value ``policy-v1-2026-07-04``
     (cohort_key composition depends on it per Story 9-6's
     ``router_policy_version`` 4-tuple component).
  3. Story 9-4 user-overrides still merge cleanly via shallow-leaf
     semantics on top of v1 (``+overrides:<sha256[:8]>`` suffix appears;
     non-overridden leaves + non-overridden tasks preserved).

Route-(b) no-change guard (AC-3): the v0→v1 bump is a version-bump-only
edit — ``draft_reply`` stays on Opus and its ``demotion_hypothesis`` is
retained, per the INSUFFICIENT_DATA verdict on
``benchmark_runs.run_id=db48480f-9692-4791-b3e2-4b3a2ab1fed8``
(9.5.3-walk-evidence.md § "AC-5 verdict interpretation").

AC-5 — cohort_key propagation: a corpus item pushed through the real
``benchmark.runner`` path (E2E canary pattern from
``test_benchmark_e2e_canary.py``, scripted adapter, ``--cost-mock``, $0
spend) records ``router_policy_version=policy-v1-2026-07-04`` and a
``cohort_key`` recomputable from the row's own frozen components; a
"historical" run recorded under the v0 version value remains queryable
alongside the v1 rows (distinct cohort_key, no invalidation).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchmark.cohort import compute_cohort_key
from benchmark.runner import main as runner_main
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
    PolicyTable,
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_REPO_POLICY_PATH = Path("router/policy.yaml")
_V0_VERSION: str = "policy-v0-2026-06-01"
_V1_VERSION: str = "policy-v1-2026-07-04"
_QWEN: str = "qwen2.5:3b-instruct-q4_K_M"
_COST_MOCK_ENV: str = "BENCHMARK_COST_MOCK"


# ---------- AC-4: load_policy on the real v1 file ----------


def test_load_policy_succeeds_on_repo_policy_yaml() -> None:
    """AC-4 (1): the shipped router/policy.yaml validates end-to-end."""
    table = load_policy(_REPO_POLICY_PATH)
    assert isinstance(table, PolicyTable)
    assert "draft_reply" in table.tasks
    assert "coarse_class" in table.tasks


def test_version_field_reads_as_v1() -> None:
    """AC-4 (2): PolicyTable.version carries the v1 value verbatim.

    cohort_key composition (Story 9-6) consumes this string as the
    ``router_policy_version`` component — an unexpected value here would
    silently fork every future benchmark cohort.
    """
    table = load_policy(_REPO_POLICY_PATH)
    assert table.version == _V1_VERSION


def test_v1_bump_did_not_change_routing() -> None:
    """Route-(b) guard: v0→v1 is a version-bump-only edit.

    Per the INSUFFICIENT_DATA verdict (opus scoring n=0 — no valid
    Haiku-vs-Opus comparison), draft_reply keeps Opus and the demotion
    hypothesis is retained (augmented, never removed) for v2 re-review.
    """
    table = load_policy(_REPO_POLICY_PATH)
    draft_reply = table.tasks["draft_reply"]
    assert draft_reply.model == "claude-opus-4-7"
    assert draft_reply.demotion_hypothesis is not None
    # The other two Opus cells were NOT covered by the 9.5.3 run — their
    # routing AND hypotheses must survive the bump untouched (CR-F1: model
    # pins added so a silent model swap on the un-benchmarked cells fails
    # this guard just as loudly as one on draft_reply).
    assert table.tasks["tone_style_mirror"].model == "claude-opus-4-7"
    assert table.tasks["tone_style_mirror"].demotion_hypothesis is not None
    assert table.tasks["multi_turn_refinement"].model == "claude-opus-4-7"
    assert table.tasks["multi_turn_refinement"].demotion_hypothesis is not None


def test_user_overrides_merge_cleanly_on_v1(tmp_path: Path) -> None:
    """AC-4 (3): Story 9-4 shallow-leaf overrides merge on top of v1."""
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    overrides_path.write_text(
        "tasks:\n  draft_reply:\n    max_tokens_out: 1200\n",
        encoding="utf-8",
    )
    merged = load_policy(_REPO_POLICY_PATH, overrides_path=overrides_path)

    # Merged effective version = v1 baseline + overrides suffix (Story 9-1 AC-6).
    assert merged.version.startswith(f"{_V1_VERSION}+overrides:"), merged.version

    # Overridden leaf applied; sibling leaves on the same task preserved.
    assert merged.tasks["draft_reply"].max_tokens_out == 1200
    assert merged.tasks["draft_reply"].model == "claude-opus-4-7"
    assert merged.tasks["draft_reply"].lane == "interactive"

    # Non-overridden tasks byte-identical to the baseline.
    baseline = load_policy(_REPO_POLICY_PATH)
    assert merged.tasks["coarse_class"] == baseline.tasks["coarse_class"]


# ---------- AC-5: cohort_key propagation through benchmark.runner ----------


class _ScriptedAdapter:
    """Minimal scripted adapter (Story 9-6/9-7/9-8 pattern)."""

    def __init__(self, text: str, model_id: str) -> None:
        self.text = text
        self.model_id = model_id

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        return AdapterResponse(
            text=self.text,
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=42,
            raw={"mock": True},
        )


@pytest.fixture
def _clean_state() -> Iterator[None]:
    """Reset module-level singletons + BENCHMARK_COST_MOCK (9-8 pattern)."""
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    os.environ.pop(_COST_MOCK_ENV, None)
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    os.environ.pop(_COST_MOCK_ENV, None)


def _fetchall(db_path: str, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db_path)
    try:
        return list(conn.execute(query, params).fetchall())
    finally:
        conn.close()


def _run_canary_once(
    run_id: str, corpus_path: Path, db_path: str
) -> None:
    """Dispatch the 5-item canary through the real runner ($0, cost-mock)."""
    rc = runner_main(
        [
            "--run-id", run_id,
            "--corpus", str(corpus_path),
            "--db-path", db_path,
            "--tasks", "coarse_class",
            "--models", _QWEN,
            "--cost-mock",
            "--yes",
        ]
    )
    assert rc == 0, f"runner exit code expected 0; got {rc}"
    # The runner sets the env var itself on --cost-mock; clear it so the
    # next invocation makes its own explicit choice (CR-F2 precedent, 9-8).
    os.environ.pop(_COST_MOCK_ENV, None)


def test_cohort_key_uses_v1_component_and_v0_rows_stay_queryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """AC-5: post-v1 runs carry the v1 cohort component; v0 rows survive.

    Sequence mirrors history: a "historical" run fires under a policy
    snapshot whose version is the v0 value (all other components equal),
    then the real repo v1 policy is loaded and a second run fires. The
    two runs land distinct cohort_keys in the SAME table, and the v0
    rows remain fully queryable after the v1 run — the bump invalidates
    nothing (Story 9-9's cross-cohort drift section handles the split).
    """
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)

    corpus_path = tmp_path / "canary_5.jsonl"
    shutil.copyfile(Path("evals/fixtures/canary_5.jsonl"), corpus_path)

    anchors_dir = tmp_path / "anchors"
    anchors_dir.mkdir()
    (anchors_dir / "VERSION").write_text("anchors-v9-5-5-test", encoding="utf-8")
    monkeypatch.setattr("benchmark.runner._DEFAULT_ANCHORS_DIR", str(anchors_dir))

    register_adapter(
        _QWEN,
        _ScriptedAdapter(
            text='{"class_coarse": "newsletter", "confidence": 0.9}',
            model_id=_QWEN,
        ),
    )

    repo_table = load_policy(_REPO_POLICY_PATH)

    # Historical run — identical policy except the version component is v0.
    set_policy_snapshot(repo_table.model_copy(update={"version": _V0_VERSION}))
    _run_canary_once("policy-v0-historical", corpus_path, db_path)

    # Post-bump run — the real repo v1 policy, verbatim.
    set_policy_snapshot(repo_table)
    _run_canary_once("policy-v1-cohort-e2e", corpus_path, db_path)

    v1_rows = _fetchall(
        db_path,
        "SELECT prompt_version, scorer_model, anchors_version, "
        "router_policy_version, cohort_key, outcome "
        "FROM benchmark_runs WHERE run_id = ?",
        ("policy-v1-cohort-e2e",),
    )
    assert len(v1_rows) == 5, f"expected 5 v1 rows; got {len(v1_rows)}"
    for prompt_version, scorer_model, anchors_version, rpv, cohort_key, outcome in v1_rows:
        assert outcome == "ok"
        # The frozen component IS the v1 policy version…
        assert rpv == _V1_VERSION
        # …and the stored cohort_key is recomputable from the row's own
        # frozen 4-tuple (Story 9-6 contract, now with the v1 component).
        assert cohort_key == compute_cohort_key(
            prompt_version=prompt_version,
            scorer_model=scorer_model,
            anchors_version=anchors_version,
            router_policy_version=rpv,
        )

    # Historical v0 rows: distinct cohort, still fully queryable post-v1.
    v0_rows = _fetchall(
        db_path,
        "SELECT router_policy_version, cohort_key "
        "FROM benchmark_runs WHERE run_id = ?",
        ("policy-v0-historical",),
    )
    assert len(v0_rows) == 5, f"expected 5 historical v0 rows; got {len(v0_rows)}"
    assert all(rpv == _V0_VERSION for rpv, _ in v0_rows)

    v0_cohorts = {ck for _, ck in v0_rows}
    v1_cohorts = {row[4] for row in v1_rows}
    assert len(v0_cohorts) == 1 and len(v1_cohorts) == 1
    assert v0_cohorts.isdisjoint(v1_cohorts), (
        "v0 and v1 runs must land in DIFFERENT cohorts — the version bump "
        "is exactly a one-component cohort_key change"
    )

    # Query by the OLD cohort_key still returns the historical rows.
    by_old_cohort = _fetchall(
        db_path,
        "SELECT COUNT(*) FROM benchmark_runs WHERE cohort_key = ?",
        (next(iter(v0_cohorts)),),
    )
    assert by_old_cohort[0][0] == 5
