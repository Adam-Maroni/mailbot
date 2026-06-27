"""Story 9-5 AC-15 Round 2 (LLM-recommendations mode).

Fabricates synthetic 3-turn dialogs for the 20 reference-resolution-slice
items. Each dialog has the shape:

  user (turn 0):  generic conversational opener about a topic
  agent (turn 1): brief acknowledgment / clarifying question
  user (turn 2):  references the target email by shorthand
                  (e.g., "the one from <sender> about <topic>")

`expected_resolved_email_ids` is populated with the single target corpus id
(per AC-4: list of ids the agent SHOULD resolve to).

Adam authorized agent-fabricated content per the 2026-06-27 AC-6.5 amendment;
documented in scripts/_propose_labels.py header + run-flags amendment.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from evals.corpus_schema import load_corpus  # noqa: E402


def _short_topic(subject: str, body: str) -> str:
    """Extract a 3-6-word topic phrase from the subject (preferred) or body opener."""
    s = (subject or "").strip()
    # Strip common reply/forward prefixes
    s = re.sub(r"^(re|fwd?|tr|réf|aw|ref)[\s:]+", "", s, flags=re.IGNORECASE)
    # Take first ~6 words
    words = s.split()
    if not words:
        # Fall back to body opener
        b = (body or "").strip().split()
        words = b[:6] if b else ["that item"]
    # Drop trailing punctuation
    topic = " ".join(words[:6]).strip(" -:!?.,")
    return topic.lower() or "that item"


def _sender_shorthand(sender_display: str, sender_addr: str, category: str) -> str:
    """Produce a short sender reference suitable for "the one from X" phrasing."""
    d = (sender_display or "").strip()
    if d and not d.lower().startswith(("no-reply", "noreply", "do-not-reply")):
        # Take first name if possible
        parts = d.split()
        return parts[0] if parts else d
    # No clean display name → use domain
    if sender_addr and "@" in sender_addr:
        domain = sender_addr.split("@", 1)[1].split(".")[0]
        return domain
    # Fall back to category language
    return {
        "newsletter": "that newsletter",
        "notification": "that notification",
        "transactional": "that order",
        "edge_case": "that thing",
        "human_professional": "that colleague",
        "human_personal": "that friend",
        "cold_outreach": "that salesperson",
        "spam_like": "that spam",
    }.get(category, "that person")


def fabricate_dialog(
    corpus_item_id: str,
    raw_subject: str,
    raw_body: str,
    sender_display: str,
    sender_addr: str,
    category: str,
) -> tuple[str, str, str]:
    """Return (turn0_user, turn1_agent, turn2_user)."""
    topic = _short_topic(raw_subject, raw_body)
    sender = _sender_shorthand(sender_display, sender_addr, category)

    turn0 = "Quick question — I need to follow up on some emails I got recently."
    turn1 = "Sure, which one are you thinking about?"
    turn2 = f"The one from {sender} about {topic} — can you pull it up for me?"
    return turn0, turn1, turn2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--worksheet",
        required=True,
        help="reference-slice worksheet CSV produced by `to-csv --mode reference-slice`",
    )
    ap.add_argument(
        "--corpus",
        default="evals/email_corpus_v1.jsonl",
        help="path to the corpus JSONL (for sender + body lookup)",
    )
    args = ap.parse_args()

    worksheet_path = Path(args.worksheet)
    if not worksheet_path.exists():
        print(f"propose-reference-slice: worksheet missing: {worksheet_path}", file=sys.stderr)
        return 2

    corpus_path = Path(args.corpus)
    items_by_id = {item.id: item for item in load_corpus(corpus_path)}

    with worksheet_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)

    updated = 0
    skipped = 0
    for row in rows:
        cid = (row.get("corpus_item_id") or "").strip()
        if not cid or cid not in items_by_id:
            skipped += 1
            continue
        item = items_by_id[cid]
        # source_note from the labeling pass contains the from-address shorthand.
        # We don't have a direct sender field on CorpusItem; reconstruct from source_note.
        # Format: "sampled from emails.id=X, graph_id=Y, received_at=Z, seed=...
        #          LLM-recommended labels per AC-6.5 amendment 2026-06-27
        #          (category derived from subject+body heuristics; pipeline_class_coarse=...)"
        # No sender_display in source_note. We'll use category-based fallback +
        # the body's "From" header lines if present.
        body = item.raw_body or ""
        sender_display = ""
        sender_addr = ""
        # Try to scan first ~500 chars of body for a "From:" header (Outlook quoted text)
        m = re.search(r"^\s*From:\s*(.+?)(?:\s*<(.+?)>)?\s*$", body[:500], re.MULTILINE | re.IGNORECASE)
        if m:
            sender_display = (m.group(1) or "").strip()
            sender_addr = (m.group(2) or "").strip()
        t0, t1, t2 = fabricate_dialog(
            cid, item.raw_subject, body, sender_display, sender_addr, item.category
        )
        row["turn0_user_content"] = t0
        row["turn1_agent_content"] = t1
        row["turn2_user_content"] = t2
        row["expected_resolved_email_ids"] = cid
        row["_force"] = "FALSE"
        updated += 1

    # Atomic rewrite
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".refslice.", suffix=".csv.tmp", dir=str(worksheet_path.parent)
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

    print(f"propose-reference-slice: updated {updated} rows, skipped {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
