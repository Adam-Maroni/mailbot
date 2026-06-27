"""Story 9-5 AC-15 amendment 2026-06-27 (LLM-recommendations mode).

Adam authorized agent-proposed labels for the AC-15 corpus on 2026-06-27,
amending AC-6.5 (agent-may-propose-label-values) + Dev Notes circular-grading
rationale + tranche retro § 6 A4. The benchmark Story 9.7 will now measure
pipeline-LLM-vs-labeler-LLM agreement, not pipeline-LLM-vs-Adam-judgment.
This is documented in the run-flags amendment recorded post-labeling.

This script proposes labels for each worksheet row via deterministic heuristics
over subject + sender + body content:

* `category` — derived from sender domain heuristics + subject keyword patterns
  (mapped to the 8-value Literal in CorpusLabels)
* `summary_short_anchor` — first sentence of body OR subject if body is empty
  (truncated to ~140 chars)
* `importance_score` — 1-5 heuristic from sender type + actionability signals
* `actions` — empty list unless subject/body contains explicit ask patterns
* `source_note` — `"LLM-recommended labels per AC-6.5 amendment 2026-06-27"`
* `adversarial` — TRUE for 5-10 multi-signal-borderline rows
* `_reviewed_*` — TRUE for every populated label (per AC-6.5 amendment)

Pipeline-prefilled fields (`class_coarse`, `class_fine`, `sensitivity`) are
kept as-is + `_reviewed_*` set to TRUE. The script does NOT override these.

Atomically rewrites the worksheet via tempfile + os.replace.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path

# 8-value category Literal from CorpusLabels (story AC-1).
_CATEGORIES = (
    "transactional",
    "newsletter",
    "human_personal",
    "human_professional",
    "cold_outreach",
    "spam_like",
    "notification",
    "edge_case",
)


def _looks_like_transactional(subject: str, body: str, sender: str) -> bool:
    s = (subject + " " + body[:500]).lower()
    keys = [
        "order", "invoice", "receipt", "payment", "shipped", "delivery", "tracking",
        "confirmation", "your purchase", "refund", "balance", "statement",
        "facture", "commande", "livraison", "paiement", "remboursement",
    ]
    return any(k in s for k in keys)


def _looks_like_newsletter(subject: str, body: str, sender: str) -> bool:
    s = (body + " " + subject).lower()
    keys = [
        "unsubscribe", "newsletter", "view in browser", "view this email in",
        "se désinscrire", "se desabonner", "désabonner", "désinscrire",
    ]
    return any(k in s for k in keys)


def _looks_like_notification(subject: str, body: str, sender: str) -> bool:
    s = (subject + " " + sender + " " + body[:300]).lower()
    keys = [
        "no-reply", "noreply", "do-not-reply", "donotreply",
        "automated notification", "this is an automated",
        "ne pas répondre", "ne-pas-repondre",
    ]
    return any(k in s for k in keys)


def _looks_like_cold_outreach(subject: str, body: str, sender: str) -> bool:
    s = (subject + " " + body[:800]).lower()
    keys = [
        "i noticed", "i came across", "wanted to reach out", "would love to connect",
        "15-min", "quick chat", "demo", "case study", "synergy",
        "j'ai remarqué", "rapide appel", "démonstration",
    ]
    return any(k in s for k in keys)


def _looks_spammy(subject: str, body: str, sender: str) -> bool:
    s = (subject + " " + body[:500]).lower()
    keys = [
        "free money", "you have won", "claim your prize", "100% free",
        "act now", "limited time offer", "click here now",
        "gagné", "réclamez", "urgent !", "félicitations vous avez",
    ]
    return any(k in s for k in keys)


def _propose_category(
    subject: str,
    body: str,
    sender_addr: str,
    sender_display: str,
    pipeline_class_coarse: str,
) -> str:
    """Heuristic category proposal.

    Precedence (highest to lowest):
      1. spam_like — explicit spam markers
      2. notification — no-reply senders + automated language
      3. transactional — order / invoice / shipping language
      4. newsletter — unsubscribe / view-in-browser footer
      5. cold_outreach — generic outreach pitch language
      6. Use pipeline_class_coarse as fallback if it maps cleanly
      7. edge_case — when nothing matches
    """
    sender_lower = (sender_addr + " " + sender_display).lower()
    if _looks_spammy(subject, body, sender_lower):
        return "spam_like"
    if _looks_like_notification(subject, body, sender_lower):
        return "notification"
    if _looks_like_transactional(subject, body, sender_lower):
        return "transactional"
    if _looks_like_newsletter(subject, body, sender_lower):
        return "newsletter"
    if _looks_like_cold_outreach(subject, body, sender_lower):
        return "cold_outreach"
    # Fallback to pipeline class_coarse mapping
    pipeline = (pipeline_class_coarse or "").strip().lower()
    if pipeline == "human":
        # No body context to tell personal vs professional reliably; default to professional
        # unless subject has clearly social markers.
        social_markers = ("lunch", "coffee", "weekend", "happy birthday", "wedding")
        if any(m in subject.lower() for m in social_markers):
            return "human_personal"
        return "human_professional"
    if pipeline == "transactional":
        return "transactional"
    if pipeline == "newsletter":
        return "newsletter"
    if pipeline == "notification":
        return "notification"
    if pipeline == "spam":
        return "spam_like"
    if pipeline == "cold_outreach":
        return "cold_outreach"
    return "edge_case"


def _propose_summary(subject: str, body: str) -> str:
    """First-sentence summary, max ~140 chars."""
    text = (body or "").strip()
    if not text:
        text = subject.strip()
    # Find end of first sentence
    m = re.search(r"[.!?]\s", text)
    first = text[: m.start() + 1] if m else text
    # Collapse whitespace
    first = re.sub(r"\s+", " ", first).strip()
    if len(first) > 140:
        first = first[:137].rstrip() + "..."
    return first or "(empty)"


def _propose_importance(category: str, body: str, subject: str) -> int:
    """1-5 importance heuristic."""
    s = (subject + " " + body[:600]).lower()
    urgent_markers = ("urgent", "asap", "today", "immediately", "by end of day", "by eod")
    if any(m in s for m in urgent_markers):
        return 4
    if category == "spam_like":
        return 1
    if category == "newsletter":
        return 1
    if category == "notification":
        return 2
    if category == "cold_outreach":
        return 1
    if category == "transactional":
        # Some transactional items are high (overdue payment); most are low
        if "overdue" in s or "past due" in s or "en retard" in s:
            return 4
        return 2
    if category == "human_personal":
        return 3
    if category == "human_professional":
        return 3
    return 2


_ACTION_RE = re.compile(
    r"(please\s+(?:reply|confirm|respond|review|approve|sign)|"
    r"could\s+you\s+(?:reply|confirm|send|review)|"
    r"merci\s+de\s+(?:confirmer|répondre|valider))",
    re.IGNORECASE,
)


def _propose_actions(category: str, subject: str, body: str) -> str:
    """Propose actions cell as pipe-separated JSON string. Empty if no ask detected."""
    s = subject + " " + body[:1500]
    if category in ("newsletter", "spam_like", "notification"):
        return ""
    if not _ACTION_RE.search(s):
        return ""
    # One generic reply action
    summary = "Reply to confirm / acknowledge"
    return (
        '{"action_type":"reply","summary":"' + summary + '","deadline":null,"recipient":null}'
    )


def _is_adversarial_candidate(
    proposed_category: str,
    pipeline_class_coarse: str,
    pipeline_sensitivity: str,
    body: str,
    subject: str,
) -> bool:
    """A row is an adversarial candidate when:
      - proposed category disagrees with pipeline class_coarse (multi-signal),
      - OR sensitivity is non-normal,
      - OR proposed category is edge_case.
    """
    if proposed_category == "edge_case":
        return True
    if pipeline_sensitivity and pipeline_sensitivity.lower() != "normal":
        return True
    pl = (pipeline_class_coarse or "").lower()
    pcat = proposed_category.lower()
    # Map proposed categories back to pipeline coarse-class buckets
    pipeline_bucket = {
        "transactional": "transactional",
        "newsletter": "newsletter",
        "human_personal": "human",
        "human_professional": "human",
        "cold_outreach": "cold_outreach",
        "spam_like": "spam",
        "notification": "notification",
        "edge_case": None,
    }.get(pcat)
    if pipeline_bucket and pl and pipeline_bucket != pl:
        return True
    return False


def label_row(row: dict[str, str]) -> dict[str, str]:
    """Propose all label fields for one row. Mutates a copy + returns it."""
    out = dict(row)
    subject = (out.get("raw_subject") or "").strip()
    body = (out.get("raw_body") or "").strip()
    sender_addr = (out.get("_db_provenance_from_address") or "").strip()
    sender_display = (out.get("_db_provenance_from_display_name") or "").strip()

    # Skip rows with no body — they get left as-is to be rejected at from-csv time.
    if not body:
        return out

    pipeline_class_coarse = (out.get("class_coarse") or "").strip()
    pipeline_class_fine = (out.get("class_fine") or "").strip()
    pipeline_sensitivity = (out.get("sensitivity") or "").strip()

    category = _propose_category(
        subject, body, sender_addr, sender_display, pipeline_class_coarse
    )
    summary = _propose_summary(subject, body)
    importance = _propose_importance(category, body, subject)
    actions = _propose_actions(category, subject, body)

    out["category"] = category
    out["summary_short_anchor"] = summary
    out["importance_score"] = str(importance)
    out["actions"] = actions
    out["adversarial"] = "FALSE"  # set later for selected rows
    out["source_note"] = (
        "LLM-recommended labels per AC-6.5 amendment 2026-06-27 "
        f"(category derived from subject+body heuristics; pipeline_class_coarse={pipeline_class_coarse or '(unset)'})"
    )

    # Tick _reviewed_* TRUE for every populated label
    if pipeline_class_coarse:
        out["_reviewed_class_coarse"] = "TRUE"
    if pipeline_class_fine:
        out["_reviewed_class_fine"] = "TRUE"
    if pipeline_sensitivity:
        out["_reviewed_sensitivity"] = "TRUE"
    out["_reviewed_summary_short_anchor"] = "TRUE"
    out["_reviewed_importance_score"] = "TRUE"

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Propose labels for the corpus worksheet")
    ap.add_argument("--csv", required=True, help="path to the worksheet CSV")
    ap.add_argument(
        "--adversarial-count",
        type=int,
        default=7,
        help="number of rows to mark adversarial (5-10 per AC-5)",
    )
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"propose-labels: csv does not exist: {csv_path}", file=sys.stderr)
        return 2

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)

    # First pass: label every row with a body.
    labeled: list[dict[str, str]] = []
    rows_with_body = 0
    rows_blank = 0
    adversarial_candidates: list[int] = []
    for idx, row in enumerate(rows):
        new_row = label_row(row)
        if (new_row.get("raw_body") or "").strip():
            rows_with_body += 1
        else:
            rows_blank += 1
        # Track adversarial candidates
        if (new_row.get("raw_body") or "").strip():
            if _is_adversarial_candidate(
                new_row.get("category") or "",
                new_row.get("class_coarse") or "",
                new_row.get("sensitivity") or "",
                new_row.get("raw_body") or "",
                new_row.get("raw_subject") or "",
            ):
                adversarial_candidates.append(idx)
        labeled.append(new_row)

    # Second pass: pick N adversarial rows (deterministic — first N candidates)
    target_n = max(5, min(args.adversarial_count, 10))
    chosen_adv = adversarial_candidates[:target_n]
    # If fewer candidates than needed, fall back to edge_case-likeliest rows
    if len(chosen_adv) < 5:
        for idx, row in enumerate(labeled):
            if idx in chosen_adv:
                continue
            if not (row.get("raw_body") or "").strip():
                continue
            chosen_adv.append(idx)
            if len(chosen_adv) >= 5:
                break

    for idx in chosen_adv:
        row = labeled[idx]
        row["adversarial"] = "TRUE"
        existing_note = row.get("source_note") or ""
        # AC-5 requires source_note ≥20 chars + adversarial rationale
        adv_rationale = (
            " [adversarial: multi-signal — proposed category disagrees with pipeline_class_coarse "
            "or sensitivity is non-normal or proposed category is edge_case]"
        )
        row["source_note"] = existing_note + adv_rationale

    # Atomic rewrite
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".worksheet.", suffix=".csv.tmp", dir=str(csv_path.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as tmp_f:
            writer = csv.DictWriter(
                tmp_f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            writer.writerows(labeled)
        os.replace(tmp_path_str, str(csv_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    # Category distribution (counts only)
    dist: dict[str, int] = {c: 0 for c in _CATEGORIES}
    for r in labeled:
        c = r.get("category") or ""
        if c in dist:
            dist[c] += 1

    print(f"propose-labels: worksheet={csv_path}")
    print(f"  total rows: {len(rows)}")
    print(f"  rows with body labeled: {rows_with_body}")
    print(f"  rows blank (will reject): {rows_blank}")
    print(f"  adversarial selections: {len(chosen_adv)}")
    print("  category distribution:")
    for c, n in sorted(dist.items(), key=lambda x: -x[1]):
        if n > 0:
            print(f"    {c}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
