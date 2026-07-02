"""Strip Microsoft Learn chrome from downloaded pages.

Header chrome: everything before the first article H1.
Body chrome:   `[Section titled: ...](...)` anchor lines (duplicate the H2 below).
Footer chrome: everything from `## Feedback` (or `## Additional resources`) onward.
Also strips: 'Feedback', 'Summarize this article for me', 'Expand table' UI labels.
"""
import os
import re
from pathlib import Path

PAGES_DIR = Path("docs/external/learn-microsoft-azure/pages")


HEADER_JUNK_PATTERNS = [
    "Table of contents Exit editor mode",
    "Ask LearnAsk Learn",
    "Reading modeTable of contents",
    "Copy MarkdownPrint",
    "Add to CollectionsAdd to plan",
]

# Footer terminator headings — strip from these onward.
FOOTER_HEADINGS = [
    re.compile(r"^##\s+Feedback\s*$", re.M),
    re.compile(r"^##\s+Additional resources\s*$", re.M),
]

# Body-noise lines (exact or regex).
SECTION_ANCHOR_RE = re.compile(r"^\[Section titled:[^\]]+\]\([^)]+\)\s*$", re.M)
NOISE_LINES_EXACT = {
    "Feedback",
    "Summarize this article for me",
    "Expand table",
    "Note",
}
# Lines that match these patterns are also dropped.
NOISE_PATTERNS = [
    re.compile(r"^Access to this page requires authorization\..*$", re.M),
    re.compile(r"^- Last updated on \d{1,2}/\d{1,2}/\d{4}\s*$", re.M),
    re.compile(r"^Ask Learn is an AI assistant.*$", re.M),
    re.compile(r"^Please sign in to use Ask Learn\.\s*$", re.M),
    re.compile(r"^\[Sign in\]\([^)]+\)\s*$", re.M),
]


def clean(text: str) -> tuple[str, dict]:
    stats = {"before_lines": text.count("\n") + 1}

    # 1. Drop header chrome: everything before the first ATX H1 that looks like a real title
    #    (skip H1 'Table of contents' etc., though we already cull them above).
    lines = text.splitlines()
    article_start = None
    for i, line in enumerate(lines):
        m = re.match(r"^#\s+(.+)$", line)
        if not m:
            continue
        title = m.group(1).strip()
        if title in HEADER_JUNK_PATTERNS or title in NOISE_LINES_EXACT:
            continue
        if title.startswith("Table of") or title == "Reading mode":
            continue
        article_start = i
        break
    if article_start is not None:
        lines = lines[article_start:]
    text = "\n".join(lines)

    # 2. Drop footer: everything from first footer heading match onward
    cut = len(text)
    for pat in FOOTER_HEADINGS:
        m = pat.search(text)
        if m:
            cut = min(cut, m.start())
    text = text[:cut].rstrip() + "\n"

    # 3. Drop `[Section titled: ...]` anchor lines
    text = SECTION_ANCHOR_RE.sub("", text)

    # 4. Drop noise patterns
    for pat in NOISE_PATTERNS:
        text = pat.sub("", text)

    # 5. Drop exact-match noise lines
    out_lines = []
    for line in text.splitlines():
        if line.strip() in NOISE_LINES_EXACT:
            continue
        out_lines.append(line)
    text = "\n".join(out_lines)

    # 6. Collapse runs of 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    stats["after_lines"] = text.count("\n") + 1
    stats["removed_lines"] = stats["before_lines"] - stats["after_lines"]
    return text.strip() + "\n", stats


def main():
    files = sorted(PAGES_DIR.rglob("*.md"))
    print(f"cleaning {len(files)} files...")
    total_before = 0
    total_after = 0
    skipped = 0
    for f in files:
        raw = f.read_text(encoding="utf-8")
        cleaned, stats = clean(raw)
        # Sanity: cleaned must still have the article H1
        if not re.search(r"^#\s+\w", cleaned, re.M):
            print(f"  SKIP (no H1 after clean): {f.relative_to(PAGES_DIR)}")
            skipped += 1
            continue
        if len(cleaned) < 200:
            print(f"  SKIP (too small after clean: {len(cleaned)}B): {f.relative_to(PAGES_DIR)}")
            skipped += 1
            continue
        f.write_text(cleaned, encoding="utf-8")
        total_before += len(raw)
        total_after += len(cleaned)
    print(f"done. {len(files)-skipped} cleaned, {skipped} skipped")
    if total_before:
        print(f"size: {total_before:,} -> {total_after:,} bytes ({100*(total_before-total_after)/total_before:.1f}% reduction)")


if __name__ == "__main__":
    main()
