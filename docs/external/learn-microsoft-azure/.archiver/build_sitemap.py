"""Build SITE-MAP.md from downloaded pages."""
import json
import os
import re
from collections import defaultdict
from urllib.parse import urlparse

TOP = "docs/external/learn-microsoft-azure/.archiver/top-selected.json"
TITLES = "docs/external/learn-microsoft-azure/.archiver/titles.json"
FAIL = "docs/external/learn-microsoft-azure/.archiver/failures.json"
OUT = "docs/external/learn-microsoft-azure/SITE-MAP.md"
PAGES_DIR = "docs/external/learn-microsoft-azure/pages"


def url_to_relpath(url):
    p = urlparse(url)
    path = re.sub(r"^/en-us/", "/", p.path).strip("/")
    if not path:
        return "index.md"
    parts = path.split("/")
    if url.endswith("/"):
        return "/".join(parts + ["index.md"])
    parts[-1] = parts[-1] + ".md"
    if p.query:
        q = re.sub(r"[^a-z0-9-]+", "-", p.query.lower()).strip("-")
        parts[-1] = parts[-1].replace(".md", f"__{q}.md")
    return "/".join(parts)


def extract_h1(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read(20000)
    except Exception:
        return None
    # Microsoft Learn pages have chrome before the real H1. Skip nav junk.
    # Real article H1 usually appears after "Table of contents" / "Reading mode" / "Print" block.
    # Strategy: find all H1s, prefer one after first 30 lines, or the longest one.
    h1s = re.findall(r"^#\s+(.+?)$", content, re.M)
    h1s = [h.strip() for h in h1s if h.strip() and not h.startswith("Table of") and "Ask Learn" not in h]
    if not h1s:
        return None
    # Return first non-junk H1
    for h in h1s:
        if len(h) > 5 and "Reading mode" not in h:
            return h
    return h1s[0]


def main():
    with open(TOP, encoding="utf-8") as f:
        sel = json.load(f)
    selected = sel["selected"]
    tier_assignment = sel["tier_assignment"]

    failed_urls = set()
    if os.path.exists(FAIL):
        with open(FAIL, encoding="utf-8") as f:
            failed_urls = {item["url"] for item in json.load(f)}

    # Group by top-level section
    groups = defaultdict(list)
    n_archived = 0
    for url in selected:
        if url in failed_urls:
            continue
        relpath = url_to_relpath(url)
        full = os.path.join(PAGES_DIR, *relpath.split("/"))
        if not os.path.exists(full):
            continue
        n_archived += 1
        title = extract_h1(full)
        if not title:
            # Derive from URL
            last = relpath.rsplit("/", 1)[-1].replace(".md", "").replace("-", " ")
            title = last.title()
        # Section key
        parts = relpath.split("/")
        if parts[0] in ("graph",):
            section = "graph"
            sub = parts[1] if len(parts) > 2 else "(root)"
            key = f"graph / {sub}"
        elif parts[0] == "azure":
            section = "azure"
            sub = parts[1] if len(parts) > 2 else "(root)"
            key = f"azure / {sub}"
        else:
            key = parts[0]
        groups[key].append({
            "url": url,
            "path": relpath,
            "title": title,
            "tier": tier_assignment.get(url, "?"),
        })

    md = []
    md.append("# Microsoft Azure + Graph (API-connectivity / Outlook scope) — Site Cartography\n\n")
    md.append(f"Cartography of `learn.microsoft.com/en-us/azure/` + `/en-us/graph/` filtered to API-connectivity and Outlook surfaces. {n_archived} of 100 selected pages archived locally as Markdown.\n\n")
    md.append("Scope: Microsoft Graph (Outlook mail, calendar, events), Microsoft identity platform / Entra ID, Azure API Management, Logic Apps Outlook connectors, Functions HTTP triggers, Communication Services email, Key Vault, webhook plumbing.\n\n")
    md.append("- Local markdown lives under [pages/](pages/) — paths mirror the URL structure (locale `/en-us/` stripped)\n")
    md.append("- `[online]` links point back to the original page on `learn.microsoft.com`\n")
    md.append("- Tier letters (S/A/B) reflect content importance — see [PAGE-GRADING.md](PAGE-GRADING.md)\n\n")
    md.append("---\n\n")

    for key in sorted(groups.keys()):
        md.append(f"### {key}\n\n")
        for item in sorted(groups[key], key=lambda x: x["path"]):
            md.append(f"- **[{item['tier']}]** [{item['path']}](pages/{item['path']}) — {item['title']} · [online]({item['url']})\n")
        md.append("\n")

    if failed_urls:
        md.append("---\n\n## Failed downloads\n\n")
        for u in sorted(failed_urls):
            md.append(f"- [online]({u})\n")
        md.append("\n")

    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(md)

    print(f"wrote {OUT}")
    print(f"archived: {n_archived}/100")
    print(f"failed: {len(failed_urls)}")
    print(f"sections: {len(groups)}")


if __name__ == "__main__":
    main()
