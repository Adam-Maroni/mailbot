"""Normalize + filter Azure/Graph URL maps to API-connectivity/Outlook scope."""
import json
import re
from urllib.parse import urlparse, urldefrag

AZURE_RAW = "docs/external/learn-microsoft-azure/.archiver/azure-raw.json"
GRAPH_RAW = "docs/external/learn-microsoft-azure/.archiver/graph-raw.json"
OUT = "docs/external/learn-microsoft-azure/.archiver/urls-normalized.json"

# Patterns to drop (changelog noise, locale mirrors, asset URLs).
DROP_PATH_PATTERNS = [
    re.compile(r"/release-notes/", re.I),
    re.compile(r"/whats-new", re.I),
    re.compile(r"/changelog", re.I),
    re.compile(r"/releases?(?:/|$)", re.I),
    re.compile(r"/news/", re.I),
    re.compile(r"/sprint-\d+", re.I),
    re.compile(r"\.(png|jpg|jpeg|svg|css|js|woff2?|ico|gif|webp)$", re.I),
]

# In-scope topic keywords: API connectivity, identity/auth, Outlook/mail/Graph.
SCOPE_PATTERNS = [
    # Microsoft Graph (all of /graph/ is in scope by default)
    re.compile(r"^/en-us/graph/", re.I),
    # Identity/auth (Entra ID, AAD, OAuth, app registration, MSAL)
    re.compile(r"/azure/active-directory/", re.I),
    re.compile(r"/azure/active-directory-b2c/", re.I),
    re.compile(r"/active-directory/develop/", re.I),
    re.compile(r"/azure/aad-b2c/", re.I),
    # Auth/token/identity in path
    re.compile(r"/azure/.*(oauth|openid|saml|token|msal|identity|app-registration|authentication|authorization|service-principal|managed-identit)", re.I),
    # API Management gateway
    re.compile(r"/azure/api-management/", re.I),
    # Outlook / mail / calendar / Graph mail endpoints
    re.compile(r"(outlook|exchange|mail|calendar|contacts)", re.I),
    # Communication Services email
    re.compile(r"/azure/communication-services/", re.I),
    # Logic Apps + Functions (connectors for Outlook live here)
    re.compile(r"/azure/connectors/", re.I),
    re.compile(r"/azure/logic-apps/", re.I),
    re.compile(r"/azure/azure-functions/.*(http|trigger|binding|api|auth)", re.I),
    # Event Grid / Event Hubs (webhook + notification surface for Graph)
    re.compile(r"/azure/event-grid/", re.I),
    re.compile(r"/azure/event-hubs/", re.I),
    # Key Vault (token/secret storage)
    re.compile(r"/azure/key-vault/", re.I),
    # Webhook / subscription concepts
    re.compile(r"(webhook|subscription|notification)", re.I),
]

# Anti-scope: even if it matches scope, drop these (Azure marketing / unrelated services).
HARD_DROP = [
    re.compile(r"/azure/machine-learning/", re.I),
    re.compile(r"/azure/databricks/", re.I),
    re.compile(r"/azure/synapse-analytics/", re.I),
    re.compile(r"/azure/hdinsight/", re.I),
    re.compile(r"/azure/cosmos-db/", re.I),
    re.compile(r"/azure/azure-sql/", re.I),
    re.compile(r"/azure/postgresql/", re.I),
    re.compile(r"/azure/mysql/", re.I),
    re.compile(r"/azure/site-recovery/", re.I),
    re.compile(r"/azure/backup/", re.I),
    re.compile(r"/azure/storage-mover/", re.I),
    re.compile(r"/azure/iot-", re.I),
    re.compile(r"/azure/vpn-gateway/", re.I),
    re.compile(r"/azure/expressroute/", re.I),
    re.compile(r"/azure/firewall/", re.I),
    re.compile(r"/azure/ddos-protection/", re.I),
    re.compile(r"/azure/bastion/", re.I),
    re.compile(r"/azure/devops/", re.I),
    re.compile(r"/azure/defender-for-", re.I),
    re.compile(r"/azure/sentinel/", re.I),
    re.compile(r"/azure/governance/", re.I),
    re.compile(r"/azure/policy/", re.I),
    re.compile(r"/azure/cost-management", re.I),
    re.compile(r"/azure/azure-monitor/reference/", re.I),
    re.compile(r"/azure/azure-monitor/.*\bmetrics\b", re.I),
    re.compile(r"/azure/foundry", re.I),
    re.compile(r"/azure/ai-services/(?!.*identity)", re.I),
    # Non-EN locales (paranoia — shouldn't appear since we asked for /en-us/)
    re.compile(r"/(zh-(cn|tw|hans|hant)|ja-jp|ko-kr|fr-fr|de-de|es-es|pt-br|it-it|ru-ru|nl-nl)/", re.I),
]


def load_urls(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and line.strip().startswith("http")]


def normalize(url):
    """Strip fragment, drop common tracking query params."""
    url, _ = urldefrag(url)
    # Strip ?tabs= / ?view= / ?pivots= / ?tool= / ?session_ref= variants (treat canonical)
    if "?" in url:
        base, qs = url.split("?", 1)
        keep = []
        for pair in qs.split("&"):
            if "=" not in pair:
                continue
            k = pair.split("=", 1)[0].lower()
            # Drop noisy variants; keep nothing
            if k in {"tabs", "view", "pivots", "tool", "session_ref", "context", "product", "wt.mc_id", "ocid"}:
                continue
            keep.append(pair)
        url = base + ("?" + "&".join(keep) if keep else "")
    return url


def in_scope(url):
    p = urlparse(url)
    path = p.path
    full = p.path + ("?" + p.query if p.query else "")

    # Hard structural drops
    for pat in DROP_PATH_PATTERNS:
        if pat.search(full):
            return False, "structural-drop"
    for pat in HARD_DROP:
        if pat.search(path):
            return False, "hard-drop"

    # Must match at least one scope pattern
    for pat in SCOPE_PATTERNS:
        if pat.search(path):
            return True, "scope-match"
    return False, "out-of-scope"


def main():
    azure = load_urls(AZURE_RAW)
    graph = load_urls(GRAPH_RAW)
    all_raw = azure + graph
    print(f"raw azure: {len(azure)}, raw graph: {len(graph)}, total: {len(all_raw)}")

    seen = set()
    kept = []
    reasons = {"structural-drop": 0, "hard-drop": 0, "out-of-scope": 0}
    for url in all_raw:
        nurl = normalize(url)
        if nurl in seen:
            continue
        seen.add(nurl)
        ok, reason = in_scope(nurl)
        if ok:
            kept.append(nurl)
        else:
            reasons[reason] = reasons.get(reason, 0) + 1

    kept.sort()
    print(f"after normalize+dedup: {len(seen)}, kept in scope: {len(kept)}")
    print(f"dropped: {reasons}")

    out = {
        "root_urls": [
            "https://learn.microsoft.com/en-us/azure/",
            "https://learn.microsoft.com/en-us/graph/",
        ],
        "site_name": "learn-microsoft-azure",
        "mapped_at": "2026-06-01",
        "source": "firecrawl-map",
        "scope_filter": "API connectivity / Outlook / Microsoft Graph",
        "total_raw": len(all_raw),
        "total_after_normalization": len(seen),
        "total_after_scope_filter": len(kept),
        "normalization_notes": [
            "Stripped fragments",
            "Stripped tabs/view/pivots/tool/session_ref/context/product/tracking query params",
            "Dropped changelog/release-notes/sprint paths",
            "Dropped non-API-related Azure services (ML, DBs, VPN, firewall, backup, etc.)",
            "Kept only paths matching Graph, identity/auth, API Mgmt, Outlook/mail, connectors, webhooks",
        ],
        "drop_reasons": reasons,
        "urls": kept,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUT}")

    # Sample
    print("\nfirst 20 kept:")
    for u in kept[:20]:
        print(f"  {u}")


if __name__ == "__main__":
    main()
