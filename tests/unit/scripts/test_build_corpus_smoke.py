"""Story 9-5 AC-9 Subtask 8.13: scripts/build_corpus.py smoke tests."""

from __future__ import annotations

import csv
import json
import sqlite3
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.build_corpus as bc

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CANARY = _PROJECT_ROOT / "evals" / "fixtures" / "canary_5.jsonl"


def _run(*argv: str) -> int:
    return bc.main(list(argv))


# ---------------------------------------------------------------------------
# (a) validate on canary fixture
# ---------------------------------------------------------------------------
def test_validate_canary_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run("validate", "--corpus", str(_CANARY))
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "accepted_count: 5" in captured.out
    assert "anonymization_matches: 0" in captured.out


# ---------------------------------------------------------------------------
# (b) sample --from-db deterministic
# ---------------------------------------------------------------------------
def _make_synthetic_db(db_path: Path, n: int = 10) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL UNIQUE,
                received_at TEXT NOT NULL,
                from_address TEXT,
                from_display_name TEXT,
                subject TEXT,
                body_preview TEXT,
                deleted_at TEXT,
                sensitivity TEXT,
                class_coarse TEXT,
                class_fine TEXT,
                summary_short TEXT,
                importance_score REAL
            );
            """
        )
        for i in range(n):
            conn.execute(
                "INSERT INTO emails (graph_id, received_at, from_address, "
                "from_display_name, subject, body_preview, sensitivity, "
                "class_coarse, summary_short, importance_score) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"graph-{i:03d}",
                    f"2026-06-{(i % 28) + 1:02d}T12:00:00Z",
                    f"sender{i}@example.com",
                    f"Sender {i}",
                    f"Subject {i}",
                    f"Body preview {i}",
                    "normal",
                    "transactional" if i % 2 == 0 else "newsletter",
                    f"Short summary {i}",
                    3.0,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_sample_from_db_deterministic(tmp_path: Path) -> None:
    db = tmp_path / "mailbot.db"
    _make_synthetic_db(db, n=10)
    out1 = tmp_path / "draft1.jsonl"
    out2 = tmp_path / "draft2.jsonl"
    rc1 = _run(
        "sample",
        "--from-db",
        "--count",
        "3",
        "--db",
        str(db),
        "--seed",
        "test-seed",
        "--out",
        str(out1),
    )
    rc2 = _run(
        "sample",
        "--from-db",
        "--count",
        "3",
        "--db",
        str(db),
        "--seed",
        "test-seed",
        "--out",
        str(out2),
    )
    assert rc1 == 0
    assert rc2 == 0
    lines1 = [
        json.loads(ln)
        for ln in out1.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    lines2 = [
        json.loads(ln)
        for ln in out2.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(lines1) == 3
    assert len(lines2) == 3
    # Same seed → same graph_ids
    g1 = sorted(r["_db_provenance"]["graph_id"] for r in lines1)
    g2 = sorted(r["_db_provenance"]["graph_id"] for r in lines2)
    assert g1 == g2


def test_sample_from_db_different_seed_different_rows(tmp_path: Path) -> None:
    db = tmp_path / "mailbot.db"
    _make_synthetic_db(db, n=10)
    out1 = tmp_path / "a.jsonl"
    out2 = tmp_path / "b.jsonl"
    _run(
        "sample", "--from-db", "--count", "3", "--db", str(db),
        "--seed", "seed-A", "--out", str(out1),
    )
    _run(
        "sample", "--from-db", "--count", "3", "--db", str(db),
        "--seed", "seed-B", "--out", str(out2),
    )
    lines1 = [json.loads(ln) for ln in out1.read_text(encoding="utf-8").splitlines() if ln.strip()]
    lines2 = [json.loads(ln) for ln in out2.read_text(encoding="utf-8").splitlines() if ln.strip()]
    g1 = sorted(r["_db_provenance"]["graph_id"] for r in lines1)
    g2 = sorted(r["_db_provenance"]["graph_id"] for r in lines2)
    # With 10 rows and seed entropy, different seeds should produce different samples
    # with overwhelming probability. (Tiny non-zero collision chance acknowledged.)
    assert g1 != g2


# ---------------------------------------------------------------------------
# (c) to-csv corpus round-trip
# ---------------------------------------------------------------------------
def test_to_csv_corpus_round_trip(tmp_path: Path) -> None:
    draft = tmp_path / "draft.jsonl"
    draft.write_text(
        json.dumps(
            {
                "id": "corpus-v1-001",
                "category": None,
                "raw_subject": "Test subject",
                "raw_body": None,
                "labels": {
                    "sensitivity": "normal",
                    "class_coarse": "transactional",
                    "class_fine": None,
                    "summary_short_anchor": "Test summary",
                    "importance_score": 3,
                    "actions": None,
                    "reference_resolution_slice": False,
                    "reference_resolution_turns": None,
                    "expected_resolved_email_ids": None,
                    "adversarial": False,
                },
                "source_note": "sampled from emails.id=1, graph_id=g-001, seed=test",
                "_db_provenance": {
                    "emails_id": 1,
                    "graph_id": "g-001",
                    "received_at": "2026-06-01T12:00:00Z",
                    "from_address": "a@b.example.com",
                    "from_display_name": "A B",
                    "body_preview": "preview...",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_csv = tmp_path / "worksheet.csv"
    rc = _run("to-csv", "--mode", "corpus", "--draft", str(draft), "--out", str(out_csv))
    assert rc == 0
    text = out_csv.read_text(encoding="utf-8")
    reader = csv.DictReader(StringIO(text))
    rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    # Column-order check (a representative selection — exhaustive would be brittle)
    assert "_reviewed_class_coarse" in (reader.fieldnames or [])
    assert "_reviewed_sensitivity" in (reader.fieldnames or [])
    assert "_reviewed_summary_short_anchor" in (reader.fieldnames or [])
    assert "raw_body" in (reader.fieldnames or [])
    # Prefill correctness
    assert row["class_coarse"] == "transactional"
    assert row["sensitivity"] == "normal"
    assert row["summary_short_anchor"] == "Test summary"
    assert row["importance_score"] == "3"
    # raw_body is BLANK in the CSV (Adam pastes)
    assert row["raw_body"] == ""
    # _reviewed_* defaults FALSE
    assert row["_reviewed_class_coarse"] == "FALSE"


# ---------------------------------------------------------------------------
# (d) from-csv corpus rejects non-blank label with _reviewed=FALSE
# ---------------------------------------------------------------------------
def test_from_csv_corpus_rejects_unreviewed_label(tmp_path: Path) -> None:
    csv_path = tmp_path / "worksheet.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=bc._CORPUS_CSV_COLUMNS, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerow(
            {col: "" for col in bc._CORPUS_CSV_COLUMNS}
            | {
                "id": "corpus-v1-001",
                "raw_subject": "Subj",
                "raw_body": "Body content here.",
                "category": "transactional",
                "class_coarse": "transactional",
                "_reviewed_class_coarse": "FALSE",  # <- the bug
                "sensitivity": "normal",
                "_reviewed_sensitivity": "TRUE",
                "adversarial": "FALSE",
                "source_note": "from test",
            }
        )
    corpus = tmp_path / "corpus.jsonl"
    rc = _run("from-csv", "--mode", "corpus", "--csv", str(csv_path), "--corpus", str(corpus))
    assert rc == 1
    rejected = csv_path.with_name(csv_path.stem + ".rejected" + csv_path.suffix)
    assert rejected.exists()
    rejected_text = rejected.read_text(encoding="utf-8")
    assert "_reviewed_class_coarse_FALSE" in rejected_text


# ---------------------------------------------------------------------------
# (e) from-csv anchor with wrong axes-keys rejected
# ---------------------------------------------------------------------------
def test_from_csv_anchor_axes_keys_mismatch(tmp_path: Path) -> None:
    csv_path = tmp_path / "anchor.csv"
    # draft_reply task expects {faithfulness, tone_match, actionability}.
    # Substituting `concision` for `tone_match` should cause from-csv to refuse.
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "corpus_item_id",
                "input_email_subject",
                "input_email_body",
                "model_output",
                "faithfulness",
                "concision",  # <-- wrong for draft_reply
                "actionability",
                "adam_overall_score",
                "score_rationale",
                "_row_notes",
            ],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "anchor-draft_reply-001",
                "corpus_item_id": "",
                "input_email_subject": "s",
                "input_email_body": "b",
                "model_output": "m",
                "faithfulness": "3",
                "concision": "3",
                "actionability": "3",
                "adam_overall_score": "3",
                "score_rationale": "r",
                "_row_notes": "",
            }
        )
    rc = _run(
        "from-csv",
        "--mode",
        "anchor",
        "--csv",
        str(csv_path),
        "--task",
        "draft_reply",
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# (f) from-csv reference-slice refuses already-slice item without _force
# ---------------------------------------------------------------------------
def test_from_csv_reference_slice_refuses_already_slice_without_force(
    tmp_path: Path,
) -> None:
    # Build a tiny corpus that already has an item marked reference-slice=True.
    from evals.corpus_schema import CorpusItem, CorpusLabels, write_corpus

    corpus_path = tmp_path / "corpus.jsonl"
    items = [
        CorpusItem(
            id="corpus-v1-001",
            category="transactional",
            raw_subject="s",
            raw_body="b",
            labels=CorpusLabels(
                sensitivity="normal",
                class_coarse="transactional",
                reference_resolution_slice=True,
                reference_resolution_turns=[
                    {"role": "user", "content": "u0"},
                    {"role": "agent", "content": "a1"},
                    {"role": "user", "content": "u2"},
                ],
                expected_resolved_email_ids=["corpus-v1-002"],
            ),
            source_note="n",
        ),
        CorpusItem(
            id="corpus-v1-002",
            category="newsletter",
            raw_subject="s",
            raw_body="b",
            labels=CorpusLabels(sensitivity="normal", class_coarse="newsletter"),
            source_note="n",
        ),
    ]
    write_corpus(corpus_path, items)

    csv_path = tmp_path / "ref.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "corpus_item_id",
                "raw_subject",
                "turn0_user_content",
                "turn1_agent_content",
                "turn2_user_content",
                "expected_resolved_email_ids",
                "_force",
                "_row_notes",
            ],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerow(
            {
                "corpus_item_id": "corpus-v1-001",
                "raw_subject": "s",
                "turn0_user_content": "new u0",
                "turn1_agent_content": "new a1",
                "turn2_user_content": "new u2",
                "expected_resolved_email_ids": "corpus-v1-002",
                "_force": "FALSE",  # <-- refuses without _force=TRUE
                "_row_notes": "",
            }
        )

    rc = _run(
        "from-csv",
        "--mode",
        "reference-slice",
        "--csv",
        str(csv_path),
        "--corpus",
        str(corpus_path),
    )
    assert rc == 1
    rejected = csv_path.with_name(csv_path.stem + ".rejected" + csv_path.suffix)
    assert rejected.exists()
    assert "already_reference_slice_use_force" in rejected.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (g) list-corpus rejects raw_body column BEFORE opening the corpus file
# ---------------------------------------------------------------------------
def test_list_corpus_raw_body_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    # Mock load_corpus to assert it's never called.
    with patch("scripts.build_corpus.load_corpus") as mock_load:
        rc = _run("list-corpus", "--corpus", str(corpus_path), "--columns", "id,raw_body")
        assert rc == 2
        mock_load.assert_not_called()
    err = capsys.readouterr().err
    assert "AC-9 privacy invariant" in err
    assert "raw_body" in err
