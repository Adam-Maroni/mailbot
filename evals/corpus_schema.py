"""Story 9-5: corpus + anchor Pydantic schema + JSONL helpers.

This module is the primary integration surface every benchmark-tranche story
(9-6 runner, 9-7 scorer, 9-8 E2E canary, 9-11 anchor stability audit) reads.
It defines the shape of ``evals/email_corpus_v1.jsonl`` items, the anchor
items under ``evals/anchors/*.jsonl``, and the load/write helpers.

Public API (re-exported via ``__all__``):
  * ``ExpectedAction``      — Pydantic model for a single ``CorpusLabels.actions`` entry
  * ``CorpusLabels``        — Pydantic model for ``CorpusItem.labels``
  * ``CorpusItem``          — Pydantic model for one JSONL row of the corpus
  * ``AnchorItem``          — Pydantic model for one JSONL row of an anchor file
  * ``load_corpus(path)``   — JSONL reader; ``ValueError`` on first parse failure
  * ``write_corpus(path)``  — atomic JSONL writer (tempfile + ``os.replace``)
  * ``read_anchors_version(dir)`` — small VERSION-file reader for cohort_key
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

_DRAFT_REPLY_AXES: frozenset[str] = frozenset(
    {"faithfulness", "tone_match", "actionability"}
)
_SUMMARY_SHORT_AXES: frozenset[str] = frozenset(
    {"faithfulness", "concision", "actionability"}
)

CategoryLiteral = Literal[
    "transactional",
    "newsletter",
    "human_personal",
    "human_professional",
    "cold_outreach",
    "spam_like",
    "notification",
    "edge_case",
]

SensitivityLiteral = Literal["normal", "sensitive", "confidential"]

TaskLiteral = Literal["draft_reply", "summary_short"]


class ExpectedAction(BaseModel):
    """One row of ``CorpusLabels.actions`` — Adam-labeled expected action."""

    model_config = ConfigDict(extra="forbid")

    action_type: str
    summary: str
    deadline: str | None = None
    recipient: str | None = None


class CorpusLabels(BaseModel):
    """Adam-labeled ground truth for a single ``CorpusItem``.

    Cross-field invariants (AC-1 + AC-4):
      * ``reference_resolution_slice=True`` requires ``reference_resolution_turns``
        AND ``expected_resolved_email_ids`` both non-None and non-empty.
      * ``reference_resolution_slice=False`` requires both fields to be None.
    """

    model_config = ConfigDict(extra="forbid")

    sensitivity: SensitivityLiteral
    class_coarse: str
    class_fine: str | None = None
    summary_short_anchor: str | None = None
    importance_score: int | None = None
    actions: list[ExpectedAction] | None = None
    reference_resolution_slice: bool = False
    reference_resolution_turns: list[dict[str, str]] | None = None
    expected_resolved_email_ids: list[str] | None = None
    adversarial: bool = False

    @model_validator(mode="after")
    def _validate_reference_resolution_invariant(self) -> CorpusLabels:
        if self.importance_score is not None and not 1 <= self.importance_score <= 5:
            raise ValueError(
                f"importance_score must be in range 1-5; got {self.importance_score}"
            )
        if self.reference_resolution_slice:
            if not self.reference_resolution_turns:
                raise ValueError(
                    "reference_resolution_slice=True requires non-empty "
                    "reference_resolution_turns"
                )
            if not self.expected_resolved_email_ids:
                raise ValueError(
                    "reference_resolution_slice=True requires non-empty "
                    "expected_resolved_email_ids"
                )
        else:
            if self.reference_resolution_turns is not None:
                raise ValueError(
                    "reference_resolution_turns must be None when "
                    "reference_resolution_slice=False"
                )
            if self.expected_resolved_email_ids is not None:
                raise ValueError(
                    "expected_resolved_email_ids must be None when "
                    "reference_resolution_slice=False"
                )
        return self


class CorpusItem(BaseModel):
    """One JSONL row of ``evals/email_corpus_v1.jsonl`` / ``evals/fixtures/canary_5.jsonl``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: CategoryLiteral
    raw_subject: str
    raw_body: str
    labels: CorpusLabels
    source_note: str

    @model_validator(mode="after")
    def _validate_non_empty_strings(self) -> CorpusItem:
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.raw_subject:
            raise ValueError("raw_subject must be ≥ 1 char")
        if not self.raw_body:
            raise ValueError("raw_body must be ≥ 1 char (post-anonymization)")
        if not self.source_note:
            raise ValueError("source_note must be ≥ 1 char")
        return self


class AnchorItem(BaseModel):
    """One JSONL row of ``evals/anchors/<task>_anchors.jsonl`` (AC-3).

    20 per task (HARD contract — Story 9.7 secondary-evaluator path + Story
    9.11 anchor stability audit both assume n=20).

    Cross-field invariants:
      * Every axis-score AND ``adam_overall_score`` must be in range 1-5.
      * Axes-keys must match the task:
        - ``draft_reply``    → ``{faithfulness, tone_match, actionability}``
        - ``summary_short``  → ``{faithfulness, concision, actionability}``
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    task: TaskLiteral
    corpus_item_id: str | None = None
    input_email_subject: str
    input_email_body: str
    model_output: str
    adam_score_axes: dict[str, int]
    adam_overall_score: int
    score_rationale: str

    @model_validator(mode="after")
    def _validate_scores_and_axes(self) -> AnchorItem:
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.input_email_subject:
            raise ValueError("input_email_subject must be non-empty")
        if not self.input_email_body:
            raise ValueError("input_email_body must be non-empty")
        if not self.model_output:
            raise ValueError("model_output must be non-empty")
        if not self.score_rationale:
            raise ValueError("score_rationale must be non-empty")
        if not 1 <= self.adam_overall_score <= 5:
            raise ValueError(
                f"adam_overall_score must be in range 1-5; got {self.adam_overall_score}"
            )
        expected_axes = (
            _DRAFT_REPLY_AXES if self.task == "draft_reply" else _SUMMARY_SHORT_AXES
        )
        actual_axes = frozenset(self.adam_score_axes.keys())
        if actual_axes != expected_axes:
            raise ValueError(
                f"adam_score_axes keys for task={self.task!r} must be "
                f"{sorted(expected_axes)}; got {sorted(actual_axes)}"
            )
        for axis_name, axis_score in self.adam_score_axes.items():
            if not 1 <= axis_score <= 5:
                raise ValueError(
                    f"adam_score_axes[{axis_name!r}] must be in range 1-5; "
                    f"got {axis_score}"
                )
        return self


def load_corpus(path: Path) -> list[CorpusItem]:
    """Read a JSONL file of ``CorpusItem`` rows; no silent skips on parse failure.

    Each non-blank line is parsed as a JSON object then validated as a
    ``CorpusItem``. The first malformed line raises ``ValueError`` with the
    line number (1-indexed). Blank lines are skipped silently — same convention
    as ``json.loads`` over JSONL.

    Raises ``FileNotFoundError`` if ``path`` does not exist.
    """
    items: list[CorpusItem] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            # JSONL-with-comments: `//`-prefixed lines are skipped so the
            # `.example` files can carry an explanatory header. Story 9-5
            # Subtask 6.1 documents this convention in docs/eval-corpus.md
            # § 2. The convention applies to ALL ``load_corpus`` callers
            # (including the gitted canary fixture + the production
            # corpus); the production corpus does not use it in practice.
            if stripped.startswith("//"):
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}: line {line_num}: invalid JSON: {exc.msg}"
                ) from exc
            try:
                items.append(CorpusItem.model_validate(row))
            except Exception as exc:
                raise ValueError(
                    f"{path}: line {line_num}: schema validation failed: {exc}"
                ) from exc
    return items


def write_corpus(path: Path, items: list[CorpusItem]) -> None:
    """Atomic JSONL write of ``items`` to ``path``.

    Mirrors the tempfile + ``os.replace`` primitive Story 9.4 established in
    ``mailbot_api/router/policy.py::write_user_overrides_atomic``. Parameterized
    for corpus JSONL: each row is a single ``model_dump_json(exclude_none=False)``
    line terminated with ``\\n``.

    The parent directory MUST exist. On any I/O failure, the tempfile is
    removed and the original target file is left in its pre-call state.
    """
    if not path.parent.exists():
        raise FileNotFoundError(
            f"parent directory does not exist: {path.parent}"
        )
    payload = "".join(
        item.model_dump_json(exclude_none=False) + "\n" for item in items
    )
    # CR-F1 (sonnet-4-6): flat try/except matching Story 9.4's
    # write_user_overrides_atomic pattern — single cleanup path, no nested
    # double-unlink risk.
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".corpus.",
        suffix=".jsonl.tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as tmp_f:
            tmp_f.write(payload)
            tmp_f.flush()
            os.fsync(tmp_f.fileno())
        os.replace(tmp_path_str, str(path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def read_anchors_version(anchors_dir: Path = Path("evals/anchors")) -> str:
    """Read + strip the contents of ``<anchors_dir>/VERSION``.

    Story 9.6's runner consumes this at startup to populate
    ``benchmark_runs.cohort_key``. Fail-loud: ``FileNotFoundError`` if absent
    (silently using ``"unknown"`` would create cohorts that look comparable
    but aren't).
    """
    version_path = anchors_dir / "VERSION"
    if not version_path.exists():
        raise FileNotFoundError(
            f"anchors VERSION file not found at {version_path}; "
            "Story 9-5 AC-13 requires this file for cohort_key population"
        )
    return version_path.read_text(encoding="utf-8").strip()


__all__ = [
    "AnchorItem",
    "CorpusItem",
    "CorpusLabels",
    "ExpectedAction",
    "load_corpus",
    "read_anchors_version",
    "write_corpus",
]
