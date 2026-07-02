"""Build PAGE-GRADING.md from heuristic-scored URLs. Top 100 only."""
import json
from urllib.parse import urlparse

IN = "docs/external/learn-microsoft-azure/.archiver/urls-preranked.json"
OUT_MD = "docs/external/learn-microsoft-azure/PAGE-GRADING.md"
OUT_TOP = "docs/external/learn-microsoft-azure/.archiver/top-selected.json"

# Map heuristic score to tier (rebase 0-100 from heuristic scale)
def tier(raw_score):
    if raw_score >= 100: return "S"
    if raw_score >= 80:  return "A"
    if raw_score >= 60:  return "B"
    if raw_score >= 40:  return "C"
    return "D"

def title_from_url(url):
    p = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return p.replace("-", " ").replace("_", " ").title() or "Index"


def main():
    with open(IN, encoding="utf-8") as f:
        data = json.load(f)

    scores = data["prerank_scores"]
    urls = data["urls"]
    # Sort by score desc, then alpha
    ranked = sorted([(scores[u], u) for u in urls], key=lambda t: (-t[0], t[1]))

    top = ranked[:100]
    selected_urls = [u for _, u in top]

    # Tier counts (over the top-100)
    tier_counts = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    grouped = {"S": [], "A": [], "B": [], "C": [], "D": []}
    for s, u in top:
        t = tier(s)
        tier_counts[t] += 1
        grouped[t].append((s, u))

    excluded_summary = []
    for s, u in ranked[100:]:
        path = urlparse(u).path
        # Build a short pattern (top section)
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            excluded_summary.append(f"/{parts[1]}/{parts[2]}")
        elif len(parts) >= 2:
            excluded_summary.append(f"/{parts[1]}")
    from collections import Counter
    excl_counts = Counter(excluded_summary).most_common(8)
    excl_line = ", ".join(f"{p} ({c})" for p, c in excl_counts) if excl_counts else "none"

    md = []
    md.append("# Microsoft Azure + Graph (API-connectivity scope) — Page Importance Grading\n")
    md.append(f"{len(data['urls'])} pages pre-ranked via URL heuristics from {data['total_after_normalization']} normalized URLs (corpus: Azure root + Microsoft Graph, filtered to API-connectivity / Outlook scope). Top 100 selected for archive.\n")
    md.append("\n**Scoring method:** URL-path heuristics (no per-page preview scrapes). Path structure on `learn.microsoft.com` is strongly predictive of content type, so heuristic scoring is a credit-saving proxy for LLM preview scoring. Scores are relative within this corpus.\n")
    md.append("\n| Tier | Score | Count | Meaning |\n")
    md.append("|------|-------|-------|---------|\n")
    md.append(f"| **S** | 100+   | {tier_counts['S']} | Outlook mail/calendar Graph pages, auth concepts, delta-query overview, Graph tutorials |\n")
    md.append(f"| **A** | 80-99  | {tier_counts['A']} | Core Graph API resources (message, event, mailfolder), identity-platform develop docs, Outlook-specific guides |\n")
    md.append(f"| **B** | 60-79  | {tier_counts['B']} | API Management how-tos, secondary Graph resources, Logic Apps connectors, Functions HTTP triggers |\n")
    md.append(f"| **C** | 40-59  | {tier_counts['C']} | Supporting concepts: Communication Services, Key Vault, webhook plumbing, Entra ID general |\n")
    md.append(f"| **D** | <40    | {tier_counts['D']} | Niche/edge pages — not expected in top-100 |\n")

    for t in ["S", "A", "B", "C", "D"]:
        if not grouped[t]:
            continue
        md.append(f"\n## Tier {t}\n")
        for s, u in grouped[t]:
            path = urlparse(u).path
            title = title_from_url(u)
            md.append(f"- **[{s}]** [{path}]({u}) — {title}\n")

    md.append(f"\n---\n\n**Excluded from archive ({len(ranked)-100} pages dropped from preranked top-150):** {excl_line}\n")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.writelines(md)

    with open(OUT_TOP, "w", encoding="utf-8") as f:
        json.dump({
            "selected": selected_urls,
            "tier_counts": tier_counts,
            "tier_assignment": {u: tier(s) for s, u in top},
            "scores": {u: s for s, u in top},
        }, f, indent=2)

    print(f"wrote {OUT_MD}")
    print(f"tier counts: {tier_counts}")
    print(f"top 5: {selected_urls[:5]}")
    print(f"excluded patterns: {excl_line}")


if __name__ == "__main__":
    main()
