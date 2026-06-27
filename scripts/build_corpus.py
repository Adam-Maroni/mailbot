"""Story 9-5 AC-9: build/sample/validate the eval corpus + anchors.

CLI surface (host-side; the running container does NOT invoke this script —
corpus + anchor AUTHORING is Adam-host-side, the container only READS the
artifacts during Story 9-6 benchmark runs):

  validate [--corpus PATH] [--strict]
      Load + validate every line; assert AC-1/4/5/6/7 invariants.

  sample --from-db --count N [--db PATH] [--seed S] [--exclude-deleted]
         [--exclude-sensitive] [--out PATH]
      Sample N rows from the local SQLite ``emails`` table (read-only); write
      a draft JSONL Adam consumes via ``to-csv``.

  to-csv --mode {corpus,reference-slice,anchor} [...mode-specific args]
      Convert a draft JSONL (or a candidate-ids list) into an Adam-editable
      CSV worksheet. The ``_reviewed_*`` tick-columns enforce the AC-6.5
      privacy invariant (explicit-accept of pipeline-prefilled label aids).

  from-csv --mode {corpus,reference-slice,anchor} --csv PATH [--task ...]
           [--corpus PATH]
      Ingest an Adam-edited CSV, validate every row, append accepted rows
      to the appropriate output JSONL, write rejected rows + reasons to
      ``<worksheet>.rejected.csv``. Stdout reports counts only — NO row
      content per AC-6.5.

  list-corpus [--corpus PATH] [--columns ...] [--out PATH]
      Emit a flat CSV of corpus items projecting only the requested
      whitelist columns. ``--columns`` does NOT permit ``raw_body`` — the
      AC-9 privacy invariant rejects this BEFORE the corpus file is opened
      (fail-fast at argparse-validation time).

All subcommands import from ``evals.corpus_schema`` + ``evals.anonymizer`` —
zero duplication of schema or regex logic. Stdin/stdout is the only Adam-
visible surface for the AC-15 co-pilot session; the script itself is
non-interactive (Adam edits CSV in his spreadsheet editor between
``to-csv`` and ``from-csv`` calls).
"""

from __future__ import annotations

import argparse
import csv
import html as html_module
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator

from pydantic import ValidationError

# Make the project root importable when this script is invoked via
# ``python scripts/build_corpus.py …`` from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from evals.anonymizer import _REGEXES, anonymize  # noqa: E402
from evals.corpus_schema import (  # noqa: E402
    AnchorItem,
    CorpusItem,
    CorpusLabels,
    ExpectedAction,
    load_corpus,
    write_corpus,
)

DEFAULT_CORPUS = Path("evals/email_corpus_v1.jsonl")
DEFAULT_DB = Path("mailbot.db")
DEFAULT_LABELING_DIR = Path("evals/_labeling")
DEFAULT_ANCHORS_DIR = Path("evals/anchors")

LIST_CORPUS_DEFAULT_COLUMNS = (
    "id",
    "raw_subject",
    "from_display_name",
    "received_at",
)
# AC-9 privacy invariant: ``list-corpus --columns`` MUST NOT permit
# ``raw_body``. The agent and any non-Adam reader must NOT see ``raw_body``
# content outside the corpus JSONL itself.
LIST_CORPUS_BANNED_COLUMNS = frozenset({"raw_body"})
LIST_CORPUS_ALLOWED_COLUMNS = frozenset(
    {
        "id",
        "category",
        "raw_subject",
        "from_display_name",
        "from_address",
        "received_at",
        "graph_id",
        "emails_id",
        "labels.sensitivity",
        "labels.class_coarse",
        "labels.class_fine",
        "labels.importance_score",
        "labels.adversarial",
        "labels.reference_resolution_slice",
        "source_note",
    }
)

_DRAFT_REPLY_AXES = ("faithfulness", "tone_match", "actionability")
_SUMMARY_SHORT_AXES = ("faithfulness", "concision", "actionability")


# ---------------------------------------------------------------------------
# Subtask 8.12: privacy-sanitized error-reporting helper.
# All from-csv error messages route through this so the cell-value is never
# surfaced in stdout/stderr. The Adam-facing source of truth for content is
# the rejected.csv file Adam reads in his spreadsheet editor.
# ---------------------------------------------------------------------------
def _format_reject_reason(
    row_num: int,
    column: str,
    error_class: str,
    rejected_csv: Path,
) -> str:
    """Return ``"row N: <column> validation failed: <error_class>; see <path> for content"``.

    NEVER includes the cell's value. ``error_class`` is a short kind-name
    ("regex_match", "schema_error", "missing_required", "axes_mismatch", etc.)
    """
    return (
        f"row {row_num}: {column} validation failed: {error_class}; "
        f"see {rejected_csv} for content"
    )


# ---------------------------------------------------------------------------
# Subcommand: validate
# ---------------------------------------------------------------------------
def _cmd_validate(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus)
    strict = bool(args.strict)
    anchors_dir = Path(args.anchors_dir) if args.anchors_dir else DEFAULT_ANCHORS_DIR

    if not corpus_path.exists():
        print(
            f"validate: corpus file does not exist: {corpus_path}",
            file=sys.stderr,
        )
        return 2

    errors: list[str] = []
    warnings: list[str] = []

    try:
        items = load_corpus(corpus_path)
    except (ValueError, ValidationError) as exc:
        errors.append(f"corpus load failed: {exc}")
        items = []

    accepted_count = len(items)
    reference_resolution_count = sum(
        1 for i in items if i.labels.reference_resolution_slice
    )
    adversarial_count = sum(1 for i in items if i.labels.adversarial)

    # AC-6 anonymization-regex pass.
    # CR-F2 (sonnet-4-6): include source_note in the field list so production
    # validate matches the test_no_pii_in_committed_corpus contract — Adam can
    # author source_note freely in the labeling CSV; PII shapes there must
    # also be caught.
    pii_matches: list[tuple[str, str, str]] = []
    for item in items:
        for kind, pattern in _REGEXES.items():
            for field_name, field_val in (
                ("raw_subject", item.raw_subject),
                ("raw_body", item.raw_body),
                ("source_note", item.source_note),
            ):
                if pattern.search(field_val):
                    pii_matches.append((item.id, field_name, kind))
    if pii_matches and strict:
        for item_id, field_name, kind in pii_matches:
            errors.append(
                f"AC-6 anonymization regex matched item={item_id} "
                f"field={field_name} pattern={kind}"
            )
    elif pii_matches:
        for item_id, field_name, kind in pii_matches:
            warnings.append(
                f"AC-6 anonymization regex matched (warn only — pass --strict to fail): "
                f"item={item_id} field={field_name} pattern={kind}"
            )

    # AC-4 reference-resolution-slice count == 20 (only enforced when the
    # corpus is non-empty; an empty corpus during initial pass-1 shouldn't
    # fail this AC).
    if accepted_count > 0 and reference_resolution_count != 20:
        msg = (
            f"AC-4: reference_resolution_slice_count={reference_resolution_count}, "
            f"expected exactly 20"
        )
        # Soft-fail during AC-15 round 1 (corpus pre-reference-slice tagging).
        # Strict mode treats it as an error; default mode warns.
        (errors if strict else warnings).append(msg)

    # AC-5 adversarial count in [5, 10].
    if accepted_count > 0 and not 5 <= adversarial_count <= 10:
        msg = f"AC-5: adversarial_count={adversarial_count}, expected in [5, 10]"
        (errors if strict else warnings).append(msg)

    # AC-3 anchor files exist + 20 items each.
    for task in ("draft_reply", "summary_short"):
        anchor_path = anchors_dir / f"{task}_anchors.jsonl"
        if not anchor_path.exists():
            (warnings).append(
                f"AC-3: {anchor_path} absent (anchor file authoring deferred)"
            )
            continue
        anchor_lines = [
            ln for ln in anchor_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("//")
        ]
        if len(anchor_lines) != 20:
            errors.append(
                f"AC-3: {anchor_path} has {len(anchor_lines)} items, expected 20"
            )
            continue
        for idx, line in enumerate(anchor_lines, start=1):
            try:
                AnchorItem.model_validate(json.loads(line))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                errors.append(
                    f"AC-3: {anchor_path} line {idx} failed validation: {exc}"
                )

    # Structured report.
    print(f"validate: corpus={corpus_path}")
    print(f"  accepted_count: {accepted_count}")
    print(f"  reference_resolution_slice_count: {reference_resolution_count}")
    print(f"  adversarial_count: {adversarial_count}")
    print(f"  anonymization_matches: {len(pii_matches)}")
    if warnings:
        print(f"  warnings: {len(warnings)}")
        for w in warnings:
            print(f"    - {w}")
    if errors:
        print(f"  errors: {len(errors)}", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        return 1
    print("  status: OK")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: sample --from-db
# ---------------------------------------------------------------------------
def _next_corpus_ordinal(corpus_path: Path) -> int:
    """Return next-available ordinal NNN for ``corpus-v1-NNN`` ids.

    Reads the existing corpus (if present), parses each id's ordinal,
    returns max + 1. If corpus is absent or empty, returns 1.

    The ordinal extractor is intentionally narrow: ``corpus-v1-NNN``
    (3-digit zero-padded). Other id shapes (``corpus-v1-canary-*``,
    ``corpus-v1-example-*``) are ignored — they're not in the production
    ordinal namespace.
    """
    if not corpus_path.exists():
        return 1
    pattern = re.compile(r"^corpus-v1-(\d{3,})$")
    max_ord = 0
    try:
        items = load_corpus(corpus_path)
    except (ValueError, ValidationError):
        return 1
    for item in items:
        m = pattern.match(item.id)
        if m:
            max_ord = max(max_ord, int(m.group(1)))
    return max_ord + 1


def _cmd_sample(args: argparse.Namespace) -> int:
    if not args.from_db:
        print(
            "sample: --from-db is required (currently the only supported source)",
            file=sys.stderr,
        )
        return 2
    db_path = Path(args.db) if args.db else DEFAULT_DB
    if not db_path.exists():
        print(f"sample: db file does not exist: {db_path}", file=sys.stderr)
        return 2
    count = int(args.count)
    if count <= 0:
        print(f"sample: --count must be positive; got {count}", file=sys.stderr)
        return 2
    seed = args.seed or f"corpus-v1-sample-{datetime.now(tz=timezone.utc).date().isoformat()}"

    out_path = (
        Path(args.out)
        if args.out
        else DEFAULT_LABELING_DIR
        / f"corpus-draft-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Open SQLite read-only via URI mode — INSERT/UPDATE/DELETE impossible
    # at OS layer even if this script had a bug.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        where_clauses: list[str] = []
        if args.exclude_deleted:
            where_clauses.append("deleted_at IS NULL")
        if args.exclude_sensitive:
            where_clauses.append("(sensitivity IS NULL OR sensitivity = 'normal')")
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        # Project all DB-prefilled columns sample needs. The WHERE clause
        # is constructed from a closed-set of literal-string predicates
        # branched on CLI flags (--exclude-deleted / --exclude-sensitive) —
        # no user-supplied data flows into the SQL string.
        select_sql = (
            "SELECT id, graph_id, received_at, from_address, from_display_name, "  # noqa: S608  — closed-set predicates, no user input
            "subject, body_preview, sensitivity, class_coarse, class_fine, "
            "summary_short, importance_score "
            f"FROM emails{where_sql}"
        )
        rows = list(conn.execute(select_sql))
    finally:
        conn.close()

    if not rows:
        print("sample: no candidate rows matched filters", file=sys.stderr)
        return 1

    if count > len(rows):
        print(
            f"sample: requested count={count} > available rows={len(rows)}; "
            "sampling all available",
            file=sys.stderr,
        )
        sampled = rows
    else:
        rng = random.Random(seed)  # noqa: S311  — benchmark sampling, not crypto
        sampled = rng.sample(rows, count)

    # Sort by db id for deterministic ordinal assignment.
    sampled_sorted = sorted(sampled, key=lambda r: r[0])

    starting_ordinal = _next_corpus_ordinal(Path(args.existing_corpus or DEFAULT_CORPUS))

    drafts: list[dict[str, Any]] = []
    for offset, row in enumerate(sampled_sorted):
        (
            emails_id,
            graph_id,
            received_at,
            from_address,
            from_display_name,
            subject,
            body_preview,
            sensitivity,
            class_coarse,
            class_fine,
            summary_short,
            importance_score,
        ) = row
        ordinal = starting_ordinal + offset
        corpus_id = f"corpus-v1-{ordinal:03d}"
        draft: dict[str, Any] = {
            "id": corpus_id,
            "category": None,
            "raw_subject": subject or "",
            "raw_body": None,
            "labels": {
                "sensitivity": sensitivity,
                "class_coarse": class_coarse,
                "class_fine": class_fine,
                "summary_short_anchor": summary_short,
                "importance_score": (
                    int(importance_score) if importance_score is not None else None
                ),
                "actions": None,
                "reference_resolution_slice": False,
                "reference_resolution_turns": None,
                "expected_resolved_email_ids": None,
                "adversarial": False,
            },
            "source_note": (
                f"sampled from emails.id={emails_id}, graph_id={graph_id}, "
                f"received_at={received_at}, seed={seed}"
            ),
            "_db_provenance": {
                "emails_id": emails_id,
                "graph_id": graph_id,
                "received_at": received_at,
                "from_address": from_address,
                "from_display_name": from_display_name,
                "body_preview": body_preview,
            },
        }
        drafts.append(draft)

    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for draft in drafts:
            fh.write(json.dumps(draft, ensure_ascii=False) + "\n")

    print(f"sample: wrote {len(drafts)} draft items to {out_path}")
    print(f"  seed: {seed}")
    print(f"  starting_ordinal: corpus-v1-{starting_ordinal:03d}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: to-csv (corpus / reference-slice / anchor modes)
# ---------------------------------------------------------------------------
_CORPUS_CSV_COLUMNS: tuple[str, ...] = (
    "id",
    "_db_provenance_emails_id",
    "_db_provenance_graph_id",
    "_db_provenance_received_at",
    "_db_provenance_from_address",
    "_db_provenance_from_display_name",
    "_db_provenance_body_preview",
    "raw_subject",
    "raw_body",
    "category",
    "class_coarse",
    "_reviewed_class_coarse",
    "class_fine",
    "_reviewed_class_fine",
    "sensitivity",
    "_reviewed_sensitivity",
    "summary_short_anchor",
    "_reviewed_summary_short_anchor",
    "importance_score",
    "_reviewed_importance_score",
    "actions",
    "adversarial",
    "source_note",
    "_row_notes",
)

_REFERENCE_SLICE_CSV_COLUMNS: tuple[str, ...] = (
    "corpus_item_id",
    "raw_subject",
    "turn0_user_content",
    "turn1_agent_content",
    "turn2_user_content",
    "expected_resolved_email_ids",
    "_force",
    "_row_notes",
)


def _anchor_csv_columns(task: str) -> tuple[str, ...]:
    axes = _DRAFT_REPLY_AXES if task == "draft_reply" else _SUMMARY_SHORT_AXES
    return (
        ("id", "corpus_item_id", "input_email_subject", "input_email_body", "model_output")
        + axes
        + ("adam_overall_score", "score_rationale", "_row_notes")
    )


def _cmd_to_csv(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode == "corpus":
        return _to_csv_corpus(args)
    if mode == "reference-slice":
        return _to_csv_reference_slice(args)
    if mode == "anchor":
        return _to_csv_anchor(args)
    print(f"to-csv: unknown --mode {mode!r}", file=sys.stderr)
    return 2


def _to_csv_corpus(args: argparse.Namespace) -> int:
    draft_path = Path(args.draft)
    if not draft_path.exists():
        print(f"to-csv corpus: draft file does not exist: {draft_path}", file=sys.stderr)
        return 2
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    drafts: list[dict[str, Any]] = []
    with draft_path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                drafts.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                print(
                    f"to-csv corpus: draft line {line_num} invalid JSON: {exc.msg}",
                    file=sys.stderr,
                )
                return 1

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=_CORPUS_CSV_COLUMNS, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for draft in drafts:
            labels = draft.get("labels", {}) or {}
            provenance = draft.get("_db_provenance", {}) or {}
            row = {
                "id": draft.get("id", ""),
                "_db_provenance_emails_id": provenance.get("emails_id", ""),
                "_db_provenance_graph_id": provenance.get("graph_id", ""),
                "_db_provenance_received_at": provenance.get("received_at", ""),
                "_db_provenance_from_address": provenance.get("from_address", ""),
                "_db_provenance_from_display_name": provenance.get(
                    "from_display_name", ""
                ),
                "_db_provenance_body_preview": provenance.get("body_preview", ""),
                "raw_subject": draft.get("raw_subject", ""),
                "raw_body": "",
                "category": draft.get("category") or "",
                "class_coarse": labels.get("class_coarse") or "",
                "_reviewed_class_coarse": "FALSE",
                "class_fine": labels.get("class_fine") or "",
                "_reviewed_class_fine": "FALSE",
                "sensitivity": labels.get("sensitivity") or "",
                "_reviewed_sensitivity": "FALSE",
                "summary_short_anchor": labels.get("summary_short_anchor") or "",
                "_reviewed_summary_short_anchor": "FALSE",
                "importance_score": (
                    str(labels["importance_score"])
                    if labels.get("importance_score") is not None
                    else ""
                ),
                "_reviewed_importance_score": "FALSE",
                "actions": "",
                "adversarial": "FALSE",
                "source_note": draft.get("source_note", ""),
                "_row_notes": "",
            }
            writer.writerow(row)

    print(f"to-csv corpus: wrote {len(drafts)} rows to {out_path}")
    return 0


def _to_csv_reference_slice(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(
            f"to-csv reference-slice: corpus does not exist: {corpus_path}",
            file=sys.stderr,
        )
        return 2
    candidate_ids = [s.strip() for s in args.candidate_ids.split(",") if s.strip()]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    items = {item.id: item for item in load_corpus(corpus_path)}
    missing = [cid for cid in candidate_ids if cid not in items]
    if missing:
        print(
            f"to-csv reference-slice: candidate ids not in corpus: {missing}",
            file=sys.stderr,
        )
        return 1

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=_REFERENCE_SLICE_CSV_COLUMNS, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for cid in candidate_ids:
            item = items[cid]
            writer.writerow(
                {
                    "corpus_item_id": cid,
                    "raw_subject": item.raw_subject,
                    "turn0_user_content": "",
                    "turn1_agent_content": "",
                    "turn2_user_content": "",
                    "expected_resolved_email_ids": "",
                    "_force": "FALSE",
                    "_row_notes": "",
                }
            )

    print(f"to-csv reference-slice: wrote {len(candidate_ids)} rows to {out_path}")
    return 0


def _to_csv_anchor(args: argparse.Namespace) -> int:
    task = args.task
    if task not in ("draft_reply", "summary_short"):
        print(f"to-csv anchor: unknown --task {task!r}", file=sys.stderr)
        return 2
    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"to-csv anchor: corpus does not exist: {corpus_path}", file=sys.stderr)
        return 2
    candidate_ids = [s.strip() for s in args.candidate_ids.split(",") if s.strip()]
    if len(candidate_ids) != 20:
        print(
            f"to-csv anchor: expected 20 candidate ids, got {len(candidate_ids)}",
            file=sys.stderr,
        )
        return 1
    items = {item.id: item for item in load_corpus(corpus_path)}
    missing = [cid for cid in candidate_ids if cid not in items]
    if missing:
        print(
            f"to-csv anchor: candidate ids not in corpus: {missing}",
            file=sys.stderr,
        )
        return 1

    prefilled_outputs: dict[str, str] = {}
    if args.prefill_outputs:
        prefill_path = Path(args.prefill_outputs)
        if not prefill_path.exists():
            print(
                f"to-csv anchor: --prefill-outputs file does not exist: {prefill_path}",
                file=sys.stderr,
            )
            return 2
        with prefill_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                obj = json.loads(stripped)
                prefilled_outputs[obj["corpus_item_id"]] = obj["model_output"]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = _anchor_csv_columns(task)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for idx, cid in enumerate(candidate_ids, start=1):
            item = items[cid]
            base_row: dict[str, str] = {
                "id": f"anchor-{task}-{idx:03d}",
                "corpus_item_id": cid,
                "input_email_subject": item.raw_subject,
                "input_email_body": item.raw_body,
                "model_output": prefilled_outputs.get(cid, ""),
                "adam_overall_score": "",
                "score_rationale": "",
                "_row_notes": "",
            }
            for axis in (
                _DRAFT_REPLY_AXES if task == "draft_reply" else _SUMMARY_SHORT_AXES
            ):
                base_row[axis] = ""
            writer.writerow(base_row)

    print(f"to-csv anchor ({task}): wrote 20 rows to {out_path}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: from-csv (corpus / reference-slice / anchor modes)
# ---------------------------------------------------------------------------
def _cmd_from_csv(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode == "corpus":
        return _from_csv_corpus(args)
    if mode == "reference-slice":
        return _from_csv_reference_slice(args)
    if mode == "anchor":
        return _from_csv_anchor(args)
    print(f"from-csv: unknown --mode {mode!r}", file=sys.stderr)
    return 2


def _rejected_csv_path(csv_path: Path) -> Path:
    return csv_path.with_name(csv_path.stem + ".rejected" + csv_path.suffix)


def _parse_actions_cell(raw: str) -> list[ExpectedAction] | None:
    """Parse pipe-separated JSON actions cell.

    Empty cell → None (= no actions).
    Otherwise: split on ``|``, parse each chunk as a JSON object,
    validate via ``ExpectedAction.model_validate``.

    Raises ``ValueError`` on parse failure.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    chunks = [c.strip() for c in stripped.split("|") if c.strip()]
    if not chunks:
        return None
    out: list[ExpectedAction] = []
    for chunk in chunks:
        obj = json.loads(chunk)
        out.append(ExpectedAction.model_validate(obj))
    return out


def _is_true(s: str) -> bool:
    return s.strip().upper() in {"TRUE", "T", "YES", "Y", "1"}


def _from_csv_corpus(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(
            f"from-csv corpus: csv file does not exist: {csv_path}",
            file=sys.stderr,
        )
        return 2
    corpus_path = Path(args.corpus or DEFAULT_CORPUS)
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path = _rejected_csv_path(csv_path)

    accepted_items: list[CorpusItem] = []
    rejected_rows: list[dict[str, str]] = []
    reject_hints: list[str] = []
    total = 0

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        rejected_fieldnames = list(fieldnames) + ["_reject_reason"]
        for row_num, row in enumerate(reader, start=2):  # 2 = header + 1
            total += 1
            try:
                item = _csv_row_to_corpus_item(row_num, row, rejected_path)
                accepted_items.append(item)
            except _RowRejected as exc:
                row["_reject_reason"] = exc.reason
                rejected_rows.append(row)
                # AC-6.5: surface the sanitized reason (column + error-class +
                # pointer) so the agent knows which column to ask Adam about
                # without ever seeing the cell's value.
                reject_hints.append(exc.reason)

    # Append accepted items via atomic rewrite (load existing + append + write).
    if accepted_items:
        existing: list[CorpusItem] = []
        if corpus_path.exists():
            try:
                existing = load_corpus(corpus_path)
            except (ValueError, ValidationError) as exc:
                print(
                    f"from-csv corpus: existing corpus failed to load (cannot append): {exc}",
                    file=sys.stderr,
                )
                return 1
        existing_ids = {item.id for item in existing}
        # Drop duplicates in this batch that collide with existing corpus —
        # treat as rejects (deterministic ordinal assignment in `sample`
        # should make this impossible, but defense-in-depth).
        # CR-F4 (sonnet-4-6): include the colliding item.id in the reject
        # row so the rejected.csv is diagnosable; use sentinel row_num=0
        # and a distinct error_class to differentiate from in-parse rejects.
        deduped: list[CorpusItem] = []
        for item in accepted_items:
            if item.id in existing_ids:
                collision_reason = _format_reject_reason(
                    row_num=0,
                    column="id",
                    error_class="post_accept_duplicate_id_collision",
                    rejected_csv=rejected_path,
                )
                rejected_rows.append({"id": item.id, "_reject_reason": collision_reason})
                reject_hints.append(collision_reason)
            else:
                deduped.append(item)
                existing_ids.add(item.id)
        write_corpus(corpus_path, existing + deduped)
        accepted_final = len(deduped)
    else:
        accepted_final = 0

    if rejected_rows:
        with rejected_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=rejected_fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            for r in rejected_rows:
                writer.writerow(r)

    print(
        f"from-csv corpus: accepted {accepted_final}/{total}, "
        f"rejected {len(rejected_rows)}/{total}"
    )
    if rejected_rows:
        print(f"  rejected.csv: {rejected_path}")
        for hint in reject_hints:
            print(f"  - {hint}")
    return 0 if not rejected_rows else 1


class _RowRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _csv_row_to_corpus_item(
    row_num: int, row: dict[str, str], rejected_csv: Path
) -> CorpusItem:
    """AC-9 + AC-6.5 validation chain for one CSV corpus row.

    Raises ``_RowRejected`` with a sanitized reason on any failure.
    NEVER includes the cell's value in the rejection reason — pointer-only.
    """
    # 1. AC-6.5: any non-blank prefilled label cell requires _reviewed_* TRUE.
    pairs = (
        ("class_coarse", "_reviewed_class_coarse"),
        ("class_fine", "_reviewed_class_fine"),
        ("sensitivity", "_reviewed_sensitivity"),
        ("summary_short_anchor", "_reviewed_summary_short_anchor"),
        ("importance_score", "_reviewed_importance_score"),
    )
    for label_col, review_col in pairs:
        if (row.get(label_col) or "").strip() and not _is_true(row.get(review_col, "")):
            raise _RowRejected(
                _format_reject_reason(
                    row_num,
                    label_col,
                    f"label_provided_but_{review_col}_FALSE",
                    rejected_csv,
                )
            )
    # 2. raw_body must be non-blank.
    raw_body = (row.get("raw_body") or "").strip()
    if not raw_body:
        raise _RowRejected(
            _format_reject_reason(
                row_num, "raw_body", "missing_required", rejected_csv
            )
        )
    # 3. Run anonymizer (load-bearing — the only point we touch raw_body content).
    anonymized_body = anonymize(raw_body, seed=row.get("id") or None)

    raw_subject = (row.get("raw_subject") or "").strip()
    if not raw_subject:
        raise _RowRejected(
            _format_reject_reason(
                row_num, "raw_subject", "missing_required", rejected_csv
            )
        )

    category = (row.get("category") or "").strip()
    if not category:
        raise _RowRejected(
            _format_reject_reason(
                row_num, "category", "missing_required", rejected_csv
            )
        )

    source_note = (row.get("source_note") or "").strip()
    if not source_note:
        raise _RowRejected(
            _format_reject_reason(
                row_num, "source_note", "missing_required", rejected_csv
            )
        )

    adversarial = _is_true(row.get("adversarial", ""))
    if adversarial and len(source_note) < 20:
        raise _RowRejected(
            _format_reject_reason(
                row_num,
                "source_note",
                "adversarial_requires_source_note_min_20_chars",
                rejected_csv,
            )
        )

    # 4. Parse actions cell.
    try:
        actions = _parse_actions_cell(row.get("actions") or "")
    except (json.JSONDecodeError, ValidationError, ValueError):
        raise _RowRejected(
            _format_reject_reason(
                row_num, "actions", "actions_parse_failed", rejected_csv
            )
        ) from None

    sensitivity = (row.get("sensitivity") or "").strip()
    if sensitivity not in {"normal", "sensitive", "confidential"}:
        raise _RowRejected(
            _format_reject_reason(
                row_num, "sensitivity", "invalid_sensitivity", rejected_csv
            )
        )

    class_coarse = (row.get("class_coarse") or "").strip()
    if not class_coarse:
        raise _RowRejected(
            _format_reject_reason(
                row_num, "class_coarse", "missing_required", rejected_csv
            )
        )

    class_fine = (row.get("class_fine") or "").strip() or None

    importance_score_raw = (row.get("importance_score") or "").strip()
    importance_score: int | None
    if importance_score_raw:
        try:
            importance_score = int(importance_score_raw)
        except ValueError:
            raise _RowRejected(
                _format_reject_reason(
                    row_num,
                    "importance_score",
                    "importance_score_not_int",
                    rejected_csv,
                )
            ) from None
    else:
        importance_score = None

    summary_short_anchor = (row.get("summary_short_anchor") or "").strip() or None

    item_id = (row.get("id") or "").strip()
    if not item_id:
        raise _RowRejected(
            _format_reject_reason(row_num, "id", "missing_required", rejected_csv)
        )

    try:
        labels = CorpusLabels(
            sensitivity=sensitivity,  # type: ignore[arg-type]
            class_coarse=class_coarse,
            class_fine=class_fine,
            summary_short_anchor=summary_short_anchor,
            importance_score=importance_score,
            actions=actions,
            reference_resolution_slice=False,
            reference_resolution_turns=None,
            expected_resolved_email_ids=None,
            adversarial=adversarial,
        )
        item = CorpusItem(
            id=item_id,
            category=category,  # type: ignore[arg-type]
            raw_subject=raw_subject,
            raw_body=anonymized_body,
            labels=labels,
            source_note=source_note,
        )
    except (ValidationError, ValueError):
        raise _RowRejected(
            _format_reject_reason(
                row_num, "row", "schema_validation_failed", rejected_csv
            )
        ) from None
    return item


def _from_csv_reference_slice(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(
            f"from-csv reference-slice: csv does not exist: {csv_path}",
            file=sys.stderr,
        )
        return 2
    corpus_path = Path(args.corpus or DEFAULT_CORPUS)
    if not corpus_path.exists():
        print(
            f"from-csv reference-slice: corpus does not exist: {corpus_path}",
            file=sys.stderr,
        )
        return 2
    rejected_path = _rejected_csv_path(csv_path)
    items = load_corpus(corpus_path)
    items_by_id = {item.id: item for item in items}
    valid_ids = set(items_by_id.keys())

    rejected_rows: list[dict[str, str]] = []
    reject_hints: list[str] = []
    accepted_updates: list[tuple[str, list[dict[str, str]], list[str]]] = []
    total = 0

    def _reject(row: dict[str, str], reason: str) -> None:
        row["_reject_reason"] = reason
        rejected_rows.append(row)
        reject_hints.append(reason)

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        rejected_fieldnames = list(fieldnames) + ["_reject_reason"]
        for row_num, row in enumerate(reader, start=2):
            total += 1
            cid = (row.get("corpus_item_id") or "").strip()
            if not cid or cid not in valid_ids:
                _reject(
                    row,
                    _format_reject_reason(
                        row_num, "corpus_item_id", "id_not_in_corpus", rejected_path
                    ),
                )
                continue
            target = items_by_id[cid]
            force = _is_true(row.get("_force", ""))
            if target.labels.reference_resolution_slice and not force:
                _reject(
                    row,
                    _format_reject_reason(
                        row_num,
                        "corpus_item_id",
                        "already_reference_slice_use_force",
                        rejected_path,
                    ),
                )
                continue
            t0 = (row.get("turn0_user_content") or "").strip()
            t1 = (row.get("turn1_agent_content") or "").strip()
            t2 = (row.get("turn2_user_content") or "").strip()
            if not (t0 and t1 and t2):
                _reject(
                    row,
                    _format_reject_reason(
                        row_num,
                        "turns",
                        "missing_required_turn_content",
                        rejected_path,
                    ),
                )
                continue
            turns = [
                {"role": "user", "content": t0},
                {"role": "agent", "content": t1},
                {"role": "user", "content": t2},
            ]
            expected_ids_raw = (row.get("expected_resolved_email_ids") or "").strip()
            expected_ids = [s.strip() for s in expected_ids_raw.split(",") if s.strip()]
            if not expected_ids:
                _reject(
                    row,
                    _format_reject_reason(
                        row_num,
                        "expected_resolved_email_ids",
                        "missing_required",
                        rejected_path,
                    ),
                )
                continue
            bad_refs = [eid for eid in expected_ids if eid not in valid_ids]
            if bad_refs:
                _reject(
                    row,
                    _format_reject_reason(
                        row_num,
                        "expected_resolved_email_ids",
                        "ref_id_not_in_corpus",
                        rejected_path,
                    ),
                )
                continue
            accepted_updates.append((cid, turns, expected_ids))

    if accepted_updates:
        for cid, turns, expected_ids in accepted_updates:
            target = items_by_id[cid]
            new_labels = target.labels.model_copy(
                update={
                    "reference_resolution_slice": True,
                    "reference_resolution_turns": turns,
                    "expected_resolved_email_ids": expected_ids,
                }
            )
            items_by_id[cid] = target.model_copy(update={"labels": new_labels})
        write_corpus(corpus_path, list(items_by_id.values()))

    if rejected_rows:
        with rejected_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=rejected_fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            writer.writerows(rejected_rows)

    print(
        f"from-csv reference-slice: accepted {len(accepted_updates)}/{total}, "
        f"rejected {len(rejected_rows)}/{total}"
    )
    if rejected_rows:
        print(f"  rejected.csv: {rejected_path}")
        for hint in reject_hints:
            print(f"  - {hint}")
    return 0 if not rejected_rows else 1


def _from_csv_anchor(args: argparse.Namespace) -> int:
    task = args.task
    if task not in ("draft_reply", "summary_short"):
        print(f"from-csv anchor: unknown --task {task!r}", file=sys.stderr)
        return 2
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"from-csv anchor: csv does not exist: {csv_path}", file=sys.stderr)
        return 2
    expected_axes = (
        _DRAFT_REPLY_AXES if task == "draft_reply" else _SUMMARY_SHORT_AXES
    )
    rejected_path = _rejected_csv_path(csv_path)
    anchors_path = DEFAULT_ANCHORS_DIR / f"{task}_anchors.jsonl"
    anchors_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if anchors_path.exists():
        existing_lines = [
            ln for ln in anchors_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("//")
        ]
    if len(existing_lines) >= 20:
        print(
            f"from-csv anchor: {anchors_path} already has {len(existing_lines)} items "
            "(refusing to append; manually clear file to re-anchor)",
            file=sys.stderr,
        )
        return 1

    rejected_rows: list[dict[str, str]] = []
    reject_hints: list[str] = []
    accepted_items: list[AnchorItem] = []
    total = 0
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        # AC-9 + AC-6.5: axes-keys-match-task validation (second-pass — to-csv
        # already enforced; from-csv re-asserts in case Adam renamed columns).
        present_axes = tuple(
            col for col in fieldnames if col in (_DRAFT_REPLY_AXES + _SUMMARY_SHORT_AXES)
        )
        if frozenset(present_axes) != frozenset(expected_axes):
            print(
                f"from-csv anchor: CSV axes columns {sorted(present_axes)} do not match "
                f"task {task!r} expected {sorted(expected_axes)}",
                file=sys.stderr,
            )
            return 1
        rejected_fieldnames = list(fieldnames) + ["_reject_reason"]
        for row_num, row in enumerate(reader, start=2):
            total += 1
            try:
                anchor = _csv_row_to_anchor_item(
                    row_num, row, task, expected_axes, rejected_path
                )
                accepted_items.append(anchor)
            except _RowRejected as exc:
                row["_reject_reason"] = exc.reason
                rejected_rows.append(row)
                reject_hints.append(exc.reason)

    if accepted_items:
        new_lines = list(existing_lines)
        for anchor in accepted_items:
            new_lines.append(anchor.model_dump_json(exclude_none=False))
        # Atomic write via tempfile.
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            prefix=".anchors.",
            suffix=".jsonl.tmp",
            dir=str(anchors_path.parent),
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as tmp_f:
                tmp_f.write("\n".join(new_lines) + "\n")
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
            os.replace(tmp_path_str, str(anchors_path))
        except Exception:
            Path(tmp_path_str).unlink(missing_ok=True)
            raise

    if rejected_rows:
        with rejected_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=rejected_fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            writer.writerows(rejected_rows)

    print(
        f"from-csv anchor ({task}): accepted {len(accepted_items)}/{total}, "
        f"rejected {len(rejected_rows)}/{total}"
    )
    if rejected_rows:
        print(f"  rejected.csv: {rejected_path}")
        for hint in reject_hints:
            print(f"  - {hint}")
    return 0 if not rejected_rows else 1


def _csv_row_to_anchor_item(
    row_num: int,
    row: dict[str, str],
    task: str,
    expected_axes: tuple[str, ...],
    rejected_csv: Path,
) -> AnchorItem:
    """One CSV anchor row → AnchorItem with sanitized reject reasons."""
    item_id = (row.get("id") or "").strip()
    if not item_id:
        raise _RowRejected(
            _format_reject_reason(row_num, "id", "missing_required", rejected_csv)
        )
    subject = (row.get("input_email_subject") or "").strip()
    body = (row.get("input_email_body") or "").strip()
    model_output = (row.get("model_output") or "").strip()
    rationale = (row.get("score_rationale") or "").strip()
    if not (subject and body and model_output and rationale):
        raise _RowRejected(
            _format_reject_reason(
                row_num, "anchor_fields", "missing_required_fields", rejected_csv
            )
        )

    axes_scores: dict[str, int] = {}
    for axis in expected_axes:
        raw = (row.get(axis) or "").strip()
        if not raw:
            raise _RowRejected(
                _format_reject_reason(
                    row_num, axis, "missing_required_axis_score", rejected_csv
                )
            )
        try:
            score = int(raw)
        except ValueError:
            raise _RowRejected(
                _format_reject_reason(
                    row_num, axis, "axis_score_not_int", rejected_csv
                )
            ) from None
        if not 1 <= score <= 5:
            raise _RowRejected(
                _format_reject_reason(
                    row_num, axis, "axis_score_out_of_range", rejected_csv
                )
            )
        axes_scores[axis] = score

    overall_raw = (row.get("adam_overall_score") or "").strip()
    if not overall_raw:
        raise _RowRejected(
            _format_reject_reason(
                row_num,
                "adam_overall_score",
                "missing_required",
                rejected_csv,
            )
        )
    try:
        overall = int(overall_raw)
    except ValueError:
        raise _RowRejected(
            _format_reject_reason(
                row_num,
                "adam_overall_score",
                "overall_score_not_int",
                rejected_csv,
            )
        ) from None
    if not 1 <= overall <= 5:
        raise _RowRejected(
            _format_reject_reason(
                row_num,
                "adam_overall_score",
                "overall_score_out_of_range",
                rejected_csv,
            )
        )

    corpus_item_id = (row.get("corpus_item_id") or "").strip() or None

    try:
        return AnchorItem(
            id=item_id,
            task=task,  # type: ignore[arg-type]
            corpus_item_id=corpus_item_id,
            input_email_subject=subject,
            input_email_body=body,
            model_output=model_output,
            adam_score_axes=axes_scores,
            adam_overall_score=overall,
            score_rationale=rationale,
        )
    except (ValidationError, ValueError):
        raise _RowRejected(
            _format_reject_reason(
                row_num, "row", "schema_validation_failed", rejected_csv
            )
        ) from None


# ---------------------------------------------------------------------------
# Subcommand: list-corpus
# ---------------------------------------------------------------------------
def _project_corpus_row(item: CorpusItem, column: str) -> str:
    """Return the value of ``column`` for ``item`` as a string (CSV cell)."""
    # _db_provenance is not on the schema (it's added by `sample` to the
    # draft JSONL only); list-corpus exposes only schema-resident fields +
    # a small whitelist for the operator-facing index view.
    if column == "id":
        return item.id
    if column == "category":
        return item.category
    if column == "raw_subject":
        return item.raw_subject
    if column == "source_note":
        return item.source_note
    if column == "labels.sensitivity":
        return item.labels.sensitivity
    if column == "labels.class_coarse":
        return item.labels.class_coarse
    if column == "labels.class_fine":
        return item.labels.class_fine or ""
    if column == "labels.importance_score":
        return (
            str(item.labels.importance_score)
            if item.labels.importance_score is not None
            else ""
        )
    if column == "labels.adversarial":
        return "TRUE" if item.labels.adversarial else "FALSE"
    if column == "labels.reference_resolution_slice":
        return "TRUE" if item.labels.reference_resolution_slice else "FALSE"
    if column in ("from_address", "from_display_name", "received_at", "graph_id", "emails_id"):
        # Parse the source_note for the sampled-from-DB metadata bundled by
        # `sample --from-db`. We accept absence (canary fixture rows don't
        # carry provenance).
        m = re.search(rf"{column}=([^,]+)", item.source_note)
        return m.group(1).strip() if m else ""
    # Unknown column → empty cell (already filtered by allowlist before this).
    return ""


def _cmd_list_corpus(args: argparse.Namespace) -> int:
    # AC-9 privacy invariant: fail-fast on banned columns BEFORE opening
    # the corpus file. Mock-friendly + defense-in-depth.
    columns_arg = args.columns or ",".join(LIST_CORPUS_DEFAULT_COLUMNS)
    columns = [c.strip() for c in columns_arg.split(",") if c.strip()]
    banned = [c for c in columns if c in LIST_CORPUS_BANNED_COLUMNS]
    if banned:
        print(
            f"list-corpus: raw_body column is excluded from list-corpus per "
            f"AC-9 privacy invariant (banned columns: {banned})",
            file=sys.stderr,
        )
        return 2
    unknown = [c for c in columns if c not in LIST_CORPUS_ALLOWED_COLUMNS]
    if unknown:
        print(
            f"list-corpus: unknown columns {unknown}; allowed: "
            f"{sorted(LIST_CORPUS_ALLOWED_COLUMNS)}",
            file=sys.stderr,
        )
        return 2

    corpus_path = Path(args.corpus or DEFAULT_CORPUS)
    if not corpus_path.exists():
        print(f"list-corpus: corpus does not exist: {corpus_path}", file=sys.stderr)
        return 2
    items = load_corpus(corpus_path)

    out_path = Path(args.out) if args.out else None
    output_stream: Iterator[str]

    def render() -> Iterator[str]:
        # Use csv module via StringIO-equivalent — we emit through a temp
        # buffer per row to avoid sys.stdout newline complications.
        from io import StringIO

        buf = StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(columns)
        yield buf.getvalue()
        for item in items:
            buf2 = StringIO()
            writer2 = csv.writer(buf2, quoting=csv.QUOTE_ALL)
            writer2.writerow([_project_corpus_row(item, c) for c in columns])
            yield buf2.getvalue()

    output_stream = render()
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            for chunk in output_stream:
                fh.write(chunk)
        print(f"list-corpus: wrote {len(items)} rows to {out_path}", file=sys.stderr)
    else:
        for chunk in output_stream:
            sys.stdout.write(chunk)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: fetch-bodies (AC-15 amendment 2026-06-27)
#
# Spec evolution: AC-15 step 3 originally specified Adam pasting raw_body into
# the worksheet by hand. The 2026-06-27 in-session amendment shifts that to
# agent-fetched-via-Graph: the agent reads `_db_provenance_graph_id` from the
# worksheet, invokes Graph $select=body via the running mailbot-api container
# (where the rotated refresh token lives), HTML→text converts the result, and
# writes `raw_body` cells into the worksheet. The body content flows
# Graph → container Python → docker stdout pipe → host script → CSV file —
# NEVER through the conversation transcript, so the AC-6.5 privacy invariant
# is preserved.
# ---------------------------------------------------------------------------


class _HTMLToText(HTMLParser):
    """Minimal HTML→text converter — stdlib only.

    Strips tags + decodes entities + collapses whitespace. Targeted at
    typical Outlook HTML bodies (paragraphs, line breaks, lists). Not a
    full-fidelity renderer; sufficient for benchmark-corpus ground truth
    where the human reader cares about content, not formatting.
    """

    _BLOCK_TAGS = frozenset(
        {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
    )
    _SKIP_CONTENT_TAGS = frozenset({"style", "script", "head"})

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_CONTENT_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_CONTENT_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self._chunks)
        # Decode HTML entities (&amp; → &, &nbsp; → \xa0, etc.)
        raw = html_module.unescape(raw)
        # Collapse runs of whitespace per-line; collapse blank-line runs to one.
        lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in raw.splitlines()]
        out_lines: list[str] = []
        blank_run = 0
        for line in lines:
            if line:
                out_lines.append(line)
                blank_run = 0
            else:
                blank_run += 1
                if blank_run == 1:
                    out_lines.append("")
        return "\n".join(out_lines).strip()


def _html_to_text(html: str) -> str:
    """Convert HTML body to plaintext via the stdlib HTMLParser."""
    parser = _HTMLToText()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def _cmd_fetch_bodies(args: argparse.Namespace) -> int:
    """Fetch `raw_body` for worksheet rows via Graph; writes CSV in-place.

    Invokes the running ``mailbot-api`` container (where the refresh token is
    live) via ``docker exec -i``, piping ``{corpus_id, graph_id}`` JSONL in
    and reading ``{corpus_id, body, content_type}`` JSONL out. The container
    helper is ``scripts/_fetch_bodies_container.py``, ``docker cp``'d into
    ``/tmp/`` of the container before exec.

    Privacy invariant (AC-6.5): body content NEVER enters the conversation
    transcript. It flows Graph → container → docker stdout pipe → host
    script → CSV file. The agent operating this subcommand only sees the
    structured counts + per-row fetch status (status code / error class),
    NEVER body content.
    """
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"fetch-bodies: csv file does not exist: {csv_path}", file=sys.stderr)
        return 2
    container = args.container or "mailbot-api"
    overwrite = bool(args.overwrite)
    limit = int(args.limit) if args.limit else None

    # Read worksheet
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)

    if "raw_body" not in fieldnames or "_db_provenance_graph_id" not in fieldnames:
        print(
            "fetch-bodies: csv missing required columns (raw_body + "
            "_db_provenance_graph_id) — is this a `to-csv --mode corpus` worksheet?",
            file=sys.stderr,
        )
        return 2

    # Build the fetch batch — rows with blank raw_body (or overwrite=True) AND
    # non-blank graph_id.
    batch: list[tuple[int, str, str]] = []  # (row_idx, corpus_id, graph_id)
    skipped_already_has_body = 0
    skipped_no_graph_id = 0
    for idx, row in enumerate(rows):
        has_body = bool((row.get("raw_body") or "").strip())
        graph_id = (row.get("_db_provenance_graph_id") or "").strip()
        corpus_id = (row.get("id") or "").strip()
        if has_body and not overwrite:
            skipped_already_has_body += 1
            continue
        if not graph_id:
            skipped_no_graph_id += 1
            continue
        if not corpus_id:
            continue
        batch.append((idx, corpus_id, graph_id))
        if limit and len(batch) >= limit:
            break

    print(f"fetch-bodies: worksheet={csv_path}")
    print(f"  total rows: {len(rows)}")
    print(f"  skipped (already has raw_body): {skipped_already_has_body}")
    print(f"  skipped (no graph_id): {skipped_no_graph_id}")
    print(f"  will fetch: {len(batch)}")
    if not batch:
        print("  no rows to fetch — exiting clean")
        return 0

    # Copy the container-side helper into /tmp/ of the container.
    helper_src = _PROJECT_ROOT / "scripts" / "_fetch_bodies_container.py"
    if not helper_src.exists():
        print(
            f"fetch-bodies: helper script missing: {helper_src}",
            file=sys.stderr,
        )
        return 2
    cp_result = subprocess.run(  # noqa: S603  — `docker` is a known OS tool, args are project-controlled
        ["docker", "cp", str(helper_src), f"{container}:/tmp/_fetch_bodies_container.py"],  # noqa: S607  — `docker` resolved via PATH at host level intentionally
        capture_output=True,
        text=True,
    )
    if cp_result.returncode != 0:
        print(f"fetch-bodies: docker cp failed: {cp_result.stderr}", file=sys.stderr)
        return 1

    # Build the input JSONL for the container helper.
    input_lines = "".join(
        json.dumps({"corpus_id": cid, "graph_id": gid}) + "\n"
        for _, cid, gid in batch
    )

    print(f"  invoking docker exec on container={container} (this may take ~1-2min for 120 rows)")
    proc = subprocess.run(  # noqa: S603  — `docker` is a known OS tool, args are project-controlled
        [  # noqa: S607  — `docker` resolved via PATH at host level intentionally
            "docker", "exec", "-i", container,
            "python", "/tmp/_fetch_bodies_container.py",  # noqa: S108  — /tmp is the container's filesystem, not host; docker cp'd above
        ],
        input=input_lines,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        # Helper printed an error JSON line to stderr — surface as a sanitized hint.
        err_summary = proc.stderr.strip().splitlines()[-3:] if proc.stderr else []
        print(
            "fetch-bodies: container helper returned non-zero "
            f"(returncode={proc.returncode}); last stderr lines: {err_summary}",
            file=sys.stderr,
        )
        return 1

    # Parse the helper's JSONL stdout: each line is {corpus_id, body, content_type}
    # OR {corpus_id, error}.
    results_by_id: dict[str, dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        cid = obj.get("corpus_id")
        if cid:
            results_by_id[cid] = obj

    # Convert HTML → text + write into CSV rows.
    fetched_html = 0
    fetched_text = 0
    errors = 0
    for idx, cid, _gid in batch:
        result = results_by_id.get(cid)
        if not result or "error" in result:
            errors += 1
            continue
        body_raw = result.get("body") or ""
        content_type = (result.get("content_type") or "text").lower()
        if "html" in content_type:
            body_text = _html_to_text(body_raw)
            fetched_html += 1
        else:
            body_text = body_raw
            fetched_text += 1
        rows[idx]["raw_body"] = body_text

    # Atomically rewrite the CSV via tempfile + os.replace.
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".worksheet.", suffix=".csv.tmp", dir=str(csv_path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as tmp_f:
            writer = csv.DictWriter(
                tmp_f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path_str, str(csv_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    print(f"  fetched (html→text): {fetched_html}")
    print(f"  fetched (plaintext): {fetched_text}")
    print(f"  errors: {errors}")
    print(f"  worksheet updated atomically: {csv_path}")
    return 0 if errors == 0 else 1


# ---------------------------------------------------------------------------
# Argparse plumbing
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_corpus",
        description="Story 9-5 corpus/anchor build CLI (host-side; read-only DB access).",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # validate
    p_validate = subparsers.add_parser(
        "validate", help="Load + validate the corpus; assert AC-1/4/5/6/7 invariants"
    )
    p_validate.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    p_validate.add_argument("--strict", action="store_true")
    p_validate.add_argument("--anchors-dir", default=None)
    p_validate.set_defaults(func=_cmd_validate)

    # sample
    p_sample = subparsers.add_parser(
        "sample", help="Sample N rows from the local SQLite emails table (read-only)"
    )
    p_sample.add_argument("--from-db", action="store_true", required=False)
    p_sample.add_argument("--count", type=int, required=True)
    p_sample.add_argument("--db", default=None)
    p_sample.add_argument("--seed", default=None)
    p_sample.add_argument("--exclude-deleted", action="store_true", default=True)
    p_sample.add_argument("--no-exclude-deleted", dest="exclude_deleted", action="store_false")
    p_sample.add_argument("--exclude-sensitive", action="store_true", default=False)
    p_sample.add_argument("--out", default=None)
    p_sample.add_argument("--existing-corpus", default=None)
    p_sample.set_defaults(func=_cmd_sample)

    # to-csv
    p_to_csv = subparsers.add_parser(
        "to-csv", help="Convert draft JSONL or candidate ids into an Adam-editable CSV worksheet"
    )
    p_to_csv.add_argument(
        "--mode", choices=("corpus", "reference-slice", "anchor"), required=True
    )
    p_to_csv.add_argument("--draft", default=None)
    p_to_csv.add_argument("--corpus", default=None)
    p_to_csv.add_argument("--candidate-ids", default=None)
    p_to_csv.add_argument("--task", choices=("draft_reply", "summary_short"), default=None)
    p_to_csv.add_argument("--prefill-outputs", default=None)
    p_to_csv.add_argument("--out", required=True)
    p_to_csv.set_defaults(func=_cmd_to_csv)

    # from-csv
    p_from_csv = subparsers.add_parser(
        "from-csv", help="Ingest an Adam-edited CSV; append accepted rows + write rejected.csv"
    )
    p_from_csv.add_argument(
        "--mode", choices=("corpus", "reference-slice", "anchor"), required=True
    )
    p_from_csv.add_argument("--csv", required=True)
    p_from_csv.add_argument("--corpus", default=None)
    p_from_csv.add_argument("--task", choices=("draft_reply", "summary_short"), default=None)
    p_from_csv.set_defaults(func=_cmd_from_csv)

    # fetch-bodies (AC-15 amendment 2026-06-27)
    p_fetch = subparsers.add_parser(
        "fetch-bodies",
        help="Fetch raw_body via Graph $select=body for worksheet rows; AC-6.5-safe",
    )
    p_fetch.add_argument("--csv", required=True, help="path to a `to-csv --mode corpus` worksheet")
    p_fetch.add_argument(
        "--container",
        default=None,
        help="docker container name running mailbot-api (default: mailbot-api)",
    )
    p_fetch.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite raw_body for rows that already have content",
    )
    p_fetch.add_argument(
        "--limit",
        type=int,
        default=None,
        help="fetch at most N rows (smoke-test mode)",
    )
    p_fetch.set_defaults(func=_cmd_fetch_bodies)

    # list-corpus
    p_list = subparsers.add_parser(
        "list-corpus", help="Emit a flat CSV of corpus items, projecting whitelisted columns only"
    )
    p_list.add_argument("--corpus", default=None)
    p_list.add_argument("--columns", default=None)
    p_list.add_argument("--out", default=None)
    p_list.set_defaults(func=_cmd_list_corpus)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
