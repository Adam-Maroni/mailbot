"""Story 9-5 AC-15 helper — fetches full message bodies via Microsoft Graph.

INVOKED INSIDE the ``mailbot-api`` container (which has OUTLOOK_REFRESH_TOKEN
+ the rotated-in-memory token state). The host-side ``scripts/build_corpus.py
fetch-bodies`` subcommand pipes a JSONL list of ``{corpus_id, graph_id}`` rows
to this script's stdin via ``docker exec -i``; this script writes a JSONL list
of ``{corpus_id, body, content_type, error?}`` rows to stdout.

The host script then reads stdout, converts HTML→text if needed, and writes
``raw_body`` cells into the worksheet CSV. Body content flows
Graph → container Python → docker stdout pipe → host script → CSV file.
NEVER through the conversation transcript (AC-6.5 invariant preserved).

Failure modes are reported per-row as ``{corpus_id, error}`` so the host
side can decide which rows to leave blank for Adam to handle manually.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import httpx

from mailbot_api.sync.graph_client import GraphAuthError, GraphClient

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def fetch_one(client: httpx.Client, token: str, graph_id: str) -> dict[str, Any]:
    """GET /me/messages/{graph_id}?$select=body,bodyPreview,subject.

    Returns ``{"body": str, "content_type": str}`` on success.
    Raises on Graph error so the caller emits an error row.
    """
    url = f"{_GRAPH_BASE}/me/messages/{graph_id}?$select=body,bodyPreview"
    resp = client.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"graph_get_failed status={resp.status_code}"
        )
    data = resp.json()
    body_obj = data.get("body") or {}
    return {
        "body": body_obj.get("content") or "",
        "content_type": body_obj.get("contentType") or "text",
    }


def main() -> int:
    rows = [json.loads(line) for line in sys.stdin if line.strip()]
    if not rows:
        print(
            json.dumps({"error": "no_input_rows"}),
            file=sys.stderr,
        )
        return 2

    try:
        gc = GraphClient()
        token = gc._access_token()
    except GraphAuthError as exc:
        print(
            json.dumps({"error": f"auth_failed: {exc}"}),
            file=sys.stderr,
        )
        return 1

    with httpx.Client(timeout=30) as client:
        for row in rows:
            corpus_id = row["corpus_id"]
            graph_id = row["graph_id"]
            try:
                result = fetch_one(client, token, graph_id)
                sys.stdout.write(
                    json.dumps(
                        {
                            "corpus_id": corpus_id,
                            "body": result["body"],
                            "content_type": result["content_type"],
                        }
                    )
                    + "\n"
                )
                sys.stdout.flush()
            except Exception as exc:
                sys.stdout.write(
                    json.dumps(
                        {
                            "corpus_id": corpus_id,
                            "error": str(exc),
                        }
                    )
                    + "\n"
                )
                sys.stdout.flush()
            # Gentle pacing — Graph rate-limits at ~10k req / 10 min per app,
            # so 120 reqs in a tight loop is well under the cap, but a tiny
            # sleep keeps us friendly.
            time.sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
