"""Story 9-5 AC-6.5 Subtask 8.14: agent-never-sees-raw_body enforcement.

Two load-bearing tests:
  1. ``from-csv --mode corpus`` reject reports MUST NOT echo the offending
     cell's content to stdout/stderr — only column-name + error-class +
     pointer to rejected.csv.
  2. ``list-corpus --columns ...,raw_body`` MUST exit non-zero BEFORE the
     corpus file is opened (mock-friendly defense-in-depth).
"""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.build_corpus as bc

_KNOWN_PII_BODY = "Please send to 123-45-6789 for verification, and call adam@confidential.example.org if needed."


def test_from_csv_rejected_stdout_does_not_echo_raw_body(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-6.5: ``from-csv`` stdout/stderr must surface row-N + column-name +
    error-class, NEVER the cell's value (including raw_body PII).

    Setup: synthesize a CSV row carrying a known-PII raw_body + an
    AC-6.5-violating unreviewed prefilled label. The script rejects the row.
    Assert the PII string does NOT appear in stdout/stderr.
    """
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
                "raw_body": _KNOWN_PII_BODY,
                "category": "transactional",
                "class_coarse": "transactional",
                "_reviewed_class_coarse": "FALSE",  # AC-6.5 violation
                "sensitivity": "normal",
                "_reviewed_sensitivity": "TRUE",
                "adversarial": "FALSE",
                "source_note": "from test",
            }
        )

    corpus = tmp_path / "corpus.jsonl"
    rc = bc.main(
        [
            "from-csv",
            "--mode",
            "corpus",
            "--csv",
            str(csv_path),
            "--corpus",
            str(corpus),
        ]
    )
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    # Row rejected (rc != 0 because at least one row rejected)
    assert rc != 0
    # The hint surfaces (column-name + error-class + pointer)
    assert "_reviewed_class_coarse" in combined
    # CRITICAL: the offending cell's PII string MUST NOT appear in stdout/stderr.
    # The agent reads stdout/stderr; raw_body content lives only in rejected.csv
    # (which the agent does NOT read — it's edited by Adam in his spreadsheet).
    assert "123-45-6789" not in combined
    assert "adam@confidential.example.org" not in combined
    assert _KNOWN_PII_BODY not in combined


def test_list_corpus_raw_body_refusal_before_file_open(tmp_path: Path) -> None:
    """AC-6.5 + AC-9 Subtask 8.10: ``list-corpus --columns ...,raw_body`` MUST
    exit non-zero BEFORE the corpus file is opened.

    Patching ``scripts.build_corpus.load_corpus`` asserts the load was never
    invoked — fail-fast at argparse-validation time.
    """
    corpus_path = tmp_path / "nonexistent-corpus.jsonl"
    with patch("scripts.build_corpus.load_corpus") as mock_load:
        rc = bc.main(
            [
                "list-corpus",
                "--corpus",
                str(corpus_path),
                "--columns",
                "id,raw_subject,raw_body",
            ]
        )
        assert rc == 2
        mock_load.assert_not_called()
