"""Story 6-8 integration: /spend slash command end-to-end (partial).

The verb side (render_spend_chart), the MCP-tool-registration, and the
SKILL.md documentation are locally testable here. The F6-gated portion —
actual Hermes-side slash-dispatch round-trip from Discord through Hermes's
skill bundle to the MCP /spend tool back to a Discord message attachment —
is deferred to Phase 3.5 (after the F6 MCP /mcp 307→404 redirect fix ships).

Tests in this file:

1. The verb returns a `RenderSpendChartOut` shape (sanity — re-exercises
   the unit-tested boundary at the integration layer).
2. The MCP server registers `render_spend_chart` as a tool with a non-empty
   description.
3. The MCP server has 17 tools after Story 6-8 (validates the count bump).
4. Perf sanity at smaller-than-production scale (1000 rows, <2s budget).

See `_bmad-output/implementation-artifacts/sprint-status.yaml` epic-6 closure
gate annotation for the F6 dependency on the deferred portion.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server
from mailbot_api.verbs.analytics import RenderSpendChartOut, render_spend_chart


def _seed_router_calls(db_path: str, count: int) -> None:
    """Bulk-insert `count` rows packed into the last 30 minutes so all
    periods (today/week/month) see the data on any clock-of-day. Direct
    SQL — tests are outside the boundary scan."""
    now = datetime.now(timezone.utc)
    # Spread `count` rows over the last 30 minutes — fits safely inside the
    # `today` window regardless of when the test runs (worst case: test runs
    # at 00:00:30Z; `now - 30min` lands on 23:30:30Z YESTERDAY, but the
    # window-start computed by the verb is today's 00:00:00Z so the
    # base_ts could fall before it. Mitigate by anchoring near `now` with
    # a short spread.)
    base_ts = now - timedelta(minutes=29)
    spread_seconds = 28 * 60  # 28 minutes of room ahead of base_ts
    step_seconds = max(1, spread_seconds // max(1, count - 1))
    task_types = ["coarse_class", "fine_class", "summary_short", "sensitivity_class"]
    rows = []
    for i in range(count):
        ts = base_ts + timedelta(seconds=i * step_seconds)
        rows.append((
            ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            task_types[i % len(task_types)],
            "v1",
            "qwen2.5:3b",
            "policy",
            100, 50, 0, 0.0001, 1200, "ok",
            None,
            "verb-ask-router",
            None, None, None,
        ))
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO router_calls "
            "(ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
            " tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
            " outcome, caller_verb, caller_origin, email_id, sensitivity_grant_id, sensitivity_grant_minted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


async def test_render_spend_chart_returns_pydantic_shape(tmp_path: Path) -> None:
    """End-to-end: verb returns the documented `RenderSpendChartOut` shape.

    CR MED-3 cousin fix: query `period="week"` for the same clock-safe
    reasoning as the perf test.
    """
    db_path = str(tmp_path / "spend_e2e.db")
    apply_pending_migrations(db_path)
    _seed_router_calls(db_path, 50)

    out = await render_spend_chart("week", db_path=db_path)

    assert isinstance(out, RenderSpendChartOut)
    assert out.mime_type == "image/png"
    assert isinstance(out.image_bytes, bytes)
    assert out.period == "week"
    assert out.task_count > 0
    assert out.total_usd > 0
    assert out.top_task != ""
    # CR HIGH-2: top_task_usd is now exposed for Discord-side summary line.
    assert out.top_task_usd > 0


def test_mcp_server_registers_render_spend_chart(tmp_path: Path) -> None:
    """The MCP server includes `render_spend_chart` after Story 6-8."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    tools = server._tool_manager._tools  # type: ignore[attr-defined]
    assert "render_spend_chart" in tools
    assert tools["render_spend_chart"].description
    assert "PNG" in tools["render_spend_chart"].description


def test_mcp_server_has_22_tools_after_story_6_5(tmp_path: Path) -> None:
    """Story 5-6 → 16; Story 6-8 → 17; Story 6-3 → 19; Story 6-4 → 20;
    Story 6-5 → 22 (compose_digest + finalize_digest_delivery)."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    tools = server._tool_manager._tools  # type: ignore[attr-defined]
    assert len(tools) == 22
    assert "render_spend_chart" in tools


async def test_render_spend_chart_perf_under_2s_at_1000_rows(tmp_path: Path) -> None:
    """Perf sanity at integration-test scale. The AC's 5s budget is at 100k
    rows on the 2-vCPU VPS; at 1000 rows on dev hardware we expect <2s.

    CR MED-3 fix: query `period="week"` instead of `period="today"`. The
    seed spreads rows over the last 29 minutes, which is always inside the
    7-day rolling window — but NOT always inside the today window (rows
    seeded between 00:00 and 00:29 UTC land on yesterday and miss `today`).
    Using `week` makes the assertion safe regardless of clock-of-day AND
    ensures the bar-chart rendering codepath (not the empty-data path)
    actually gets exercised.
    """
    db_path = str(tmp_path / "spend_perf.db")
    apply_pending_migrations(db_path)
    _seed_router_calls(db_path, 1000)

    start = time.perf_counter()
    out = await render_spend_chart("week", db_path=db_path)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"render took {elapsed:.2f}s (>2s budget)"
    assert out.task_count == 4  # 4 distinct task_types in the seed
    # CR HIGH-1 — image_bytes is Base64Bytes; Pydantic keeps raw bytes at the
    # Python layer (only JSON serialization base64-encodes).
    assert out.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_skill_md_documents_render_spend_chart() -> None:
    """Story 6-8 Task 6: SKILL.md (the MailBot verb-surface reference Hermes
    consumes) MUST document `render_spend_chart` so the agent knows how to
    invoke /spend.

    CR LOW-2 fix: anchor SKILL.md path off __file__ so the test is robust to
    cwd changes (pytest sub-invocations, conftest pushd, etc.).
    """
    skill_path = (
        Path(__file__).resolve().parents[2]
        / "hermes-config"
        / "skills"
        / "mailbot"
        / "SKILL.md"
    )
    assert skill_path.exists(), f"SKILL.md missing at {skill_path}"
    text = skill_path.read_text(encoding="utf-8")
    assert "render_spend_chart" in text, (
        "SKILL.md does not document the render_spend_chart verb"
    )
    assert "/spend" in text, (
        "SKILL.md does not document the /spend slash command"
    )
    # CR LOW-2 strengthen: also check the new 4th turn structure.
    assert "Turn structure 4" in text, (
        "SKILL.md does not include the /spend turn structure (4th)"
    )
