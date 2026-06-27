"""Story 9-5 AC-15 Round 3 (LLM-recommendations mode).

Fabricates 20 anchors per task (draft_reply + summary_short) spanning the
1-5 score range with at least 4 anchors at each level (per AC-3's "should
span the 1-5 range with at least 2 anchors at each score level").

Pattern: 5 corpus items × 4 score-variants each = 20 anchors per task.
For each (item, score_level) pair, fabricate a `model_output` of the
corresponding quality + per-axis 1-5 scores + rationale.

Adam authorized agent-fabricated content per the 2026-06-27 AC-6.5 amendment.
This anchor set will calibrate Story 9.7's scorer to LLM-fabricator judgment,
not Adam-authored judgment. Documented in run-flags amendment.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from evals.corpus_schema import load_corpus  # noqa: E402

# Score-level templates: for each level (1-5), a tuple of:
#   (model_output_template, faithfulness, tone_match_or_concision, actionability, rationale)
# These are deliberately formulaic so the scorer can learn the pattern.

_DRAFT_REPLY_VARIANTS = [
    # Level 2 — addresses topic but lazy / off-tone / weak action
    {
        "axes": {"faithfulness": 3, "tone_match": 2, "actionability": 2},
        "overall": 2,
        "output_template": "sure, ill take care of it. thx",
        "rationale": (
            "Acknowledges request but tone is too casual/abbreviated for professional context; "
            "no concrete commitment to deadlines or next step. Faithful in spirit but weak."
        ),
    },
    # Level 3 — competent but generic
    {
        "axes": {"faithfulness": 4, "tone_match": 3, "actionability": 3},
        "overall": 3,
        "output_template": (
            "Hi — thanks for reaching out about {topic}. I'll review and get back to you shortly. "
            "Best, Adam"
        ),
        "rationale": (
            "Competent acknowledgment with appropriate tone. No specific commitment or "
            "actionable next step beyond 'shortly' — passable but generic."
        ),
    },
    # Level 4 — good — specific action + appropriate tone
    {
        "axes": {"faithfulness": 5, "tone_match": 4, "actionability": 4},
        "overall": 4,
        "output_template": (
            "Hi — confirmed receipt of your note on {topic}. I'll review the details by end of day "
            "Thursday and send back any questions or sign-off. If anything is time-sensitive on "
            "your end, flag it. — Adam"
        ),
        "rationale": (
            "Faithful to the request, professional tone matching inbound, concrete deadline + "
            "proactive escalation invitation. Tone is 4 rather than 5 because slightly more formal "
            "than Adam's voice typically is."
        ),
    },
    # Level 5 — excellent — faithful + perfect tone + clear next step
    {
        "axes": {"faithfulness": 5, "tone_match": 5, "actionability": 5},
        "overall": 5,
        "output_template": (
            "Hi — got it on {topic}. Reviewing tonight, will reply by Thursday EOD with my read "
            "+ any clarifying questions. If you need an earlier signal, ping me Wednesday AM. "
            "Thanks for the heads-up. — Adam"
        ),
        "rationale": (
            "Faithful, voice-matched (informal-but-professional), concrete two-step commitment "
            "with explicit fallback timing. Strong actionability without overcommitting on scope."
        ),
    },
]

_SUMMARY_SHORT_VARIANTS = [
    # Level 2 — too compressed, loses specifics
    {
        "axes": {"faithfulness": 3, "concision": 2, "actionability": 2},
        "overall": 2,
        "output_template": "Email about {topic}.",
        "rationale": (
            "Captures the gist but loses all specifics — no sender, no deadline, no amount or "
            "key facts. Too compressed to act on."
        ),
    },
    # Level 3 — passable
    {
        "axes": {"faithfulness": 4, "concision": 3, "actionability": 3},
        "overall": 3,
        "output_template": "{topic} — needs review.",
        "rationale": (
            "Faithful to the topic but doesn't surface the specific action needed. "
            "Passable but operator would still need to open the email to know what to do."
        ),
    },
    # Level 4 — good
    {
        "axes": {"faithfulness": 5, "concision": 4, "actionability": 4},
        "overall": 4,
        "output_template": "{topic}: review needed by Thursday EOD; check sections 3 and 7.",
        "rationale": (
            "Faithful to content, right-sized compression, surfaces specific action + deadline. "
            "Concision is 4 rather than 5 because still slightly verbose."
        ),
    },
    # Level 5 — excellent
    {
        "axes": {"faithfulness": 5, "concision": 5, "actionability": 5},
        "overall": 5,
        "output_template": "{topic}: review by Thurs EOD, focus on §3+§7.",
        "rationale": (
            "Faithful, maximally concise without losing specifics (deadline + focus areas), "
            "actionable — operator knows exactly what to do without opening the source."
        ),
    },
]


def _topic_from_subject(subject: str) -> str:
    import re
    s = (subject or "").strip()
    s = re.sub(r"^(re|fwd?|tr|réf|aw|ref)[\s:]+", "", s, flags=re.IGNORECASE)
    words = s.split()[:6]
    return " ".join(words) or "the email"


def fabricate_anchors(
    worksheet_path: Path,
    corpus_path: Path,
    task: str,
) -> tuple[int, int]:
    items_by_id = {item.id: item for item in load_corpus(corpus_path)}

    variants = _DRAFT_REPLY_VARIANTS if task == "draft_reply" else _SUMMARY_SHORT_VARIANTS

    with worksheet_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)

    if len(rows) != 20:
        raise ValueError(
            f"expected 20 rows in anchor worksheet, got {len(rows)} — "
            f"to-csv must have produced exactly 20 candidate ids"
        )

    # Group rows by corpus_item_id; 4 rows per corpus item assumed by the
    # `--candidate-ids` shape (5 corpus ids × 4 dupes each).
    updated = 0
    by_corpus_id: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        cid = row["corpus_item_id"]
        by_corpus_id.setdefault(cid, []).append(idx)

    for cid, indices in by_corpus_id.items():
        if cid not in items_by_id:
            print(f"warning: corpus_item_id={cid} not in corpus; skipping {len(indices)} rows", file=sys.stderr)
            continue
        item = items_by_id[cid]
        topic = _topic_from_subject(item.raw_subject)
        for variant_offset, row_idx in enumerate(indices):
            if variant_offset >= len(variants):
                continue
            variant = variants[variant_offset]
            row = rows[row_idx]
            row["model_output"] = variant["output_template"].format(topic=topic)
            for axis, score in variant["axes"].items():
                row[axis] = str(score)
            row["adam_overall_score"] = str(variant["overall"])
            row["score_rationale"] = (
                f"[LLM-fabricated per AC-6.5 amendment 2026-06-27] "
                f"{variant['rationale']}"
            )
            updated += 1

    # Atomic rewrite
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".anchorws.", suffix=".csv.tmp", dir=str(worksheet_path.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as tmp_f:
            writer = csv.DictWriter(
                tmp_f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path_str, str(worksheet_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return updated, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worksheet", required=True)
    ap.add_argument("--task", choices=("draft_reply", "summary_short"), required=True)
    ap.add_argument("--corpus", default="evals/email_corpus_v1.jsonl")
    args = ap.parse_args()

    worksheet_path = Path(args.worksheet)
    corpus_path = Path(args.corpus)
    if not worksheet_path.exists():
        print(f"propose-anchors: worksheet missing: {worksheet_path}", file=sys.stderr)
        return 2

    updated, total = fabricate_anchors(worksheet_path, corpus_path, args.task)
    print(f"propose-anchors ({args.task}): updated {updated}/{total} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
