"""URL-heuristic pre-rank to cut 319 → top ~150 before paid scoring."""
import json
import re
from urllib.parse import urlparse

IN = "docs/external/learn-microsoft-azure/.archiver/urls-normalized.json"
OUT = "docs/external/learn-microsoft-azure/.archiver/urls-preranked.json"

# Tier weights for path segments. Higher = more likely a high-value page.
PATH_SIGNALS = [
    # Microsoft Graph — highest value, especially mail/calendar/auth
    (re.compile(r"^/en-us/graph/(?:auth|use-the-api|overview|api-reference|delta|webhooks|subscriptions|tutorials|sdks)", re.I), 90),
    (re.compile(r"^/en-us/graph/(?:outlook|mail|calendar|contacts)", re.I), 100),
    (re.compile(r"^/en-us/graph/", re.I), 60),
    # Entra / AD identity foundations
    (re.compile(r"/active-directory/develop/(?:v2-overview|authentication|access-tokens|id-tokens|refresh-tokens|msal|quickstart|scenario|app-registration|oauth|openid)", re.I), 85),
    (re.compile(r"/active-directory/develop/", re.I), 60),
    (re.compile(r"/active-directory/.*identity-platform", re.I), 80),
    # API Management core
    (re.compile(r"/api-management/api-management-(?:key-concepts|howto-protect|subscriptions|policies)", re.I), 75),
    (re.compile(r"/api-management/", re.I), 50),
    # Logic Apps Outlook connector
    (re.compile(r"/connectors/.*(office365|outlook)", re.I), 85),
    (re.compile(r"/connectors/", re.I), 55),
    # Communication Services email
    (re.compile(r"/communication-services/.*email", re.I), 75),
    (re.compile(r"/communication-services/", re.I), 40),
    # Webhook / subscription / notification
    (re.compile(r"(webhook|subscription|notification)", re.I), 50),
    # Functions HTTP/triggers
    (re.compile(r"/azure-functions/.*(http|trigger|binding)", re.I), 55),
    # Key Vault
    (re.compile(r"/key-vault/", re.I), 35),
]

# Bonus signals
TITLE_HINTS = [
    (re.compile(r"/overview", re.I), 15),
    (re.compile(r"/quickstart", re.I), 20),
    (re.compile(r"/concepts?/", re.I), 10),
    (re.compile(r"/tutorial", re.I), 10),
    (re.compile(r"/how-to-", re.I), 8),
    (re.compile(r"/get-started", re.I), 15),
    (re.compile(r"^/en-us/(azure|graph)/?$", re.I), 30),
]

# Penalties
PENALTIES = [
    (re.compile(r"/troubleshoot/", re.I), -15),
    (re.compile(r"/breaking-changes/", re.I), -25),
    (re.compile(r"/faq", re.I), -10),
    (re.compile(r"/migrate-", re.I), -10),
    (re.compile(r"/previous-versions/", re.I), -30),
    (re.compile(r"/reference/.*-cmdlet", re.I), -20),
    (re.compile(r"-sample$|/samples/", re.I), -10),
    (re.compile(r"/v1/|/v-1/", re.I), -15),  # likely legacy
    # Graph resources that are NOT Outlook/mail/calendar — penalize heavily
    (re.compile(r"/graph/api/resources/(planner|reading|education|team|chat|drive|onenote|todo|booking|industrydata|external|search-|security-|threat|secure|risk|device|admin|sharepoint|list|file|workforceintegration|virtual|insight|term|profile|deviceman|servicePrincipal|directoryRole|approle|contract|domain|orgcontact|organization)", re.I), -60),
    # Graph API operations that are NOT Outlook/mail/calendar
    (re.compile(r"/graph/api/(planner|education|team|chat|drive|onenote|todo|booking|industrydata|external|search-|security-|threat|secure|risk|device|admin|sharepoint|file|workforce|profile|deviceman|servicePrincipal)", re.I), -60),
]

# Strong topical boosts (post-scoring)
TOPICAL_BOOSTS = [
    (re.compile(r"(outlook|/mail|/calendar|/contact|message|mailfolder|event\b|eventseries|/me/|/users/.*/(mail|messages|events|calendars))", re.I), 30),
    (re.compile(r"/graph/(auth|webhooks?|subscriptions?|delta|notifications?|permissions?-reference)", re.I), 25),
]


def score_url(url):
    p = urlparse(url)
    path = p.path
    score = 0
    notes = []
    for pat, w in PATH_SIGNALS:
        if pat.search(path):
            score += w
            notes.append(f"+{w} path")
            break  # only the strongest path signal
    for pat, w in TITLE_HINTS:
        if pat.search(path):
            score += w
            notes.append(f"+{w} hint")
    for pat, w in PENALTIES:
        if pat.search(path):
            score += w
            notes.append(f"{w} penalty")
    for pat, w in TOPICAL_BOOSTS:
        if pat.search(path):
            score += w
            notes.append(f"+{w} topic")
    # Depth penalty: deeply nested pages tend to be auto-generated specifics
    depth = path.strip("/").count("/")
    if depth >= 5:
        score -= (depth - 4) * 5
    return score, notes


def main():
    with open(IN, encoding="utf-8") as f:
        data = json.load(f)
    urls = data["urls"]
    scored = [(score_url(u)[0], u) for u in urls]
    scored.sort(key=lambda t: (-t[0], t[1]))

    # Take top 150
    top = scored[:150]
    out_urls = [u for _, u in top]

    data["preranked_count"] = len(out_urls)
    data["preranked_cutoff_score"] = top[-1][0] if top else 0
    data["urls"] = out_urls
    data["prerank_scores"] = {u: s for s, u in top}

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"preranked {len(urls)} → {len(out_urls)} (cutoff score: {top[-1][0]})")
    print("\nTop 15 by URL heuristic:")
    for s, u in scored[:15]:
        print(f"  [{s:3d}] {u}")
    print("\nBottom of kept set (around the cutoff):")
    for s, u in scored[145:155]:
        marker = "KEEP" if scored.index((s, u)) < 150 else "DROP"
        print(f"  [{s:3d}] {marker} {u}")


if __name__ == "__main__":
    main()
