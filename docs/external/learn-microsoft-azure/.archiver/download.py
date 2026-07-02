"""Download approved URLs as Markdown via Firecrawl scrape, parallel."""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

TOP = "docs/external/learn-microsoft-azure/.archiver/top-selected.json"
OUT_DIR = "docs/external/learn-microsoft-azure/pages"
FAIL_FILE = "docs/external/learn-microsoft-azure/.archiver/failures.json"
TITLES_FILE = "docs/external/learn-microsoft-azure/.archiver/titles.json"

CONCURRENCY = 6


def url_to_path(url):
    """Mirror URL structure under pages/. Drop locale prefix."""
    p = urlparse(url)
    path = p.path
    # Strip leading /en-us/
    path = re.sub(r"^/en-us/", "/", path)
    path = path.strip("/")
    if not path:
        return os.path.join(OUT_DIR, "index.md")
    # Path ending in / means section index
    parts = path.split("/")
    if url.endswith("/"):
        return os.path.join(OUT_DIR, *parts, "index.md")
    # Last segment becomes a .md file
    parts[-1] = parts[-1] + ".md"
    if p.query:
        # Tutorial-step variants: tutorials/azure-functions?tutorial-step=3 → azure-functions__step-3.md
        q = re.sub(r"[^a-z0-9-]+", "-", p.query.lower()).strip("-")
        parts[-1] = parts[-1].replace(".md", f"__{q}.md")
    return os.path.join(OUT_DIR, *parts)


def scrape_one(url):
    target = url_to_path(url)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        return url, target, "skip-exists", None
    try:
        # firecrawl scrape <url> --format markdown -o <path>
        # Windows: must use shell=True so .cmd shim resolves; quote args defensively.
        cmd = f'firecrawl scrape "{url}" --format markdown --only-main-content -o "{target}"'
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0 or not os.path.exists(target):
            return url, target, "fail", (result.stderr or result.stdout or "no output")[-400:]
        # Sanity: empty file = failure
        if os.path.getsize(target) < 100:
            return url, target, "fail", f"output too small ({os.path.getsize(target)} bytes)"
        return url, target, "ok", None
    except subprocess.TimeoutExpired:
        return url, target, "fail", "timeout 180s"
    except Exception as e:
        return url, target, "fail", str(e)[-400:]


def main():
    with open(TOP, encoding="utf-8") as f:
        data = json.load(f)
    urls = data["selected"]
    print(f"downloading {len(urls)} URLs with concurrency={CONCURRENCY}")

    failures = []
    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(scrape_one, u): u for u in urls}
        for fut in as_completed(futures):
            url, path, status, err = fut.result()
            done += 1
            results.append((url, path, status, err))
            if status == "fail":
                failures.append({"url": url, "target": path, "error": err})
                print(f"[{done}/{len(urls)}] FAIL {url}: {(err or '')[:120]}")
            else:
                print(f"[{done}/{len(urls)}] {status.upper()} {url}")

    if failures:
        with open(FAIL_FILE, "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=2)
        print(f"\n{len(failures)} failures written to {FAIL_FILE}")
    else:
        print("\nall downloads succeeded")

    # Extract titles from h1 of downloaded files for SITE-MAP
    titles = {}
    for url, path, status, _ in results:
        if status in ("ok", "skip-exists") and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    head = f.read(8000)
                m = re.search(r"^#\s+(.+?)$", head, re.M)
                if m:
                    titles[url] = m.group(1).strip()
            except Exception:
                pass
    with open(TITLES_FILE, "w", encoding="utf-8") as f:
        json.dump(titles, f, indent=2)
    print(f"extracted {len(titles)} titles")


if __name__ == "__main__":
    main()
