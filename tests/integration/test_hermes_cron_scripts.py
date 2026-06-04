"""Story 6-10 — regression tests for the Hermes cron scripts.

The scripts (`pull_and_deliver.py`, `digest_prepare.py`) live in
`hermes-config/skills/mailbot/scripts/` and run inside the Hermes
container as cron jobs. They're stdlib-only Python and invoke MCP tools
on mailbot-api via JSON-RPC over the streamable-HTTP transport.

End-to-end testing against a real Hermes container is operator-side
Phase 3.5 work. These tests cover the offline contract:

  1. Both scripts import cleanly (no syntax errors, no missing deps).
  2. `pull_and_deliver.main()` behavior across the three branches:
     - missing API key → no-op exit 0
     - empty notifications list → silent exit 0 (no Discord stdout)
     - non-empty list → formatted stdout per row + one ack per row
  3. `digest_prepare.main()` behavior:
     - missing API key → exit 1 (loud, daily job shouldn't proceed)
     - compose_digest payload written atomically to disk
  4. Format invariants: `_format_for_discord` carries category +
     message; ack arguments shaped correctly.

The MCP transport itself is mocked at the `_mcp_client` boundary —
those are unit-scope concerns covered by `tests/integration/test_mcp_*`.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "hermes-config" / "skills" / "mailbot" / "scripts"


def _load_script_module(name: str) -> Any:
    """Load one of the cron-script modules.

    The scripts use a sibling import (`from _mcp_client import ...`),
    which only works when the scripts directory is on `sys.path`. We
    prepend it (idempotently) and use importlib so each test gets a
    fresh module if monkeypatching is needed.
    """
    scripts_dir_str = str(_SCRIPTS_DIR)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)

    # Drop any cached version so monkeypatch.setattr survives across tests.
    for cached in [name, "_mcp_client"]:
        if cached in sys.modules:
            del sys.modules[cached]

    spec = importlib.util.spec_from_file_location(
        name, _SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Import smoke — the cheapest possible regression guard.
# ---------------------------------------------------------------------------


def test_pull_and_deliver_imports_cleanly() -> None:
    """The script module must import without ImportError or SyntaxError.

    Guards against accidental dependency-on-third-party-libs (the script
    is stdlib-only by design — Hermes container has no guarantee of
    `requests`/`httpx`/etc.).
    """
    module = _load_script_module("pull_and_deliver")
    assert hasattr(module, "main")
    assert callable(module.main)


def test_digest_prepare_imports_cleanly() -> None:
    module = _load_script_module("digest_prepare")
    assert hasattr(module, "main")
    assert callable(module.main)


def test_mcp_client_imports_cleanly() -> None:
    module = importlib.import_module("_mcp_client")
    assert hasattr(module, "mcp_call")
    assert hasattr(module, "open_session")
    assert hasattr(module, "tool_call")
    assert hasattr(module, "MCPCallError")
    assert hasattr(module, "DEFAULT_BASE_URL")


# ---------------------------------------------------------------------------
# pull_and_deliver — branch coverage.
# ---------------------------------------------------------------------------


def test_pull_missing_api_key_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without ``MAILBOT_ROUTER_KEY`` the cron tick is a no-op.

    Per design-decision §4 + the script's docstring: cron retries on the
    next tick. Crashing on a missing env var during bootstrap is the
    wrong move — fail soft, emit a structured log line, exit 0.
    """
    monkeypatch.delenv("MAILBOT_ROUTER_KEY", raising=False)
    module = _load_script_module("pull_and_deliver")

    rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    # Stdout MUST be empty — anything on stdout becomes a Discord message.
    assert captured.out == ""
    # Stderr should have a structured failure event.
    assert "cron.pull.missing_api_key" in captured.err


def test_pull_empty_returns_silent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Per §4 Q2: an empty tick emits no log line and no Discord output."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")

    # Patch the shared MCP client surface (loaded via the script's
    # `from _mcp_client import ...`).
    with patch.object(module, "open_session", return_value="sess-xyz"), patch.object(
        module, "tool_call", return_value={"notifications": [], "count": 0}
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out == ""
    # No "cron.pull.delivered" log because nothing was delivered.
    assert "cron.pull.delivered" not in captured.err


def test_pull_nonempty_formats_and_acks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two pending notifications → two formatted lines on stdout + two
    ack calls. Verifies the ack call's argument shape matches Story 6-3's
    ``ack_notification(notification_id, delivery_status)`` contract.
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")

    pull_payload = {
        "notifications": [
            {
                "id": 101,
                "tier": "urgent",
                "category": "health",
                "message": "sync alarm fired",
                "enqueued_at": "2026-06-04T10:00:00.000000Z",
                "attempt_count": 1,
            },
            {
                "id": 102,
                "tier": "urgent",
                "category": "router_anomaly",
                "message": "model usage spike",
                "enqueued_at": "2026-06-04T10:00:05.000000Z",
                "attempt_count": 1,
            },
        ],
        "count": 2,
    }

    tool_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_tool_call(
        _base: str,
        _key: str,
        _sess: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        tool_calls.append((tool_name, arguments))
        if tool_name == "pull_pending_notifications":
            return pull_payload
        if tool_name == "ack_notification":
            return {
                "ok": True,
                "final_status": "ok",
                "notification_id": arguments["notification_id"],
            }
        raise AssertionError(f"unexpected tool {tool_name!r}")

    with patch.object(module, "open_session", return_value="sess-xyz"), patch.object(
        module, "tool_call", side_effect=fake_tool_call
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    # Stdout = the cron delivery payload Hermes posts to Discord.
    stdout_lines = [line for line in captured.out.splitlines() if line]
    assert stdout_lines == [
        "[health] sync alarm fired",
        "[router_anomaly] model usage spike",
    ]

    # One pull + two acks.
    assert [name for name, _ in tool_calls] == [
        "pull_pending_notifications",
        "ack_notification",
        "ack_notification",
    ]
    # Both acks carry the right id + ok status.
    ack_args = [args for name, args in tool_calls if name == "ack_notification"]
    assert ack_args == [
        {"notification_id": 101, "delivery_status": "ok"},
        {"notification_id": 102, "delivery_status": "ok"},
    ]
    # Delivered log line carries the count.
    assert "cron.pull.delivered" in captured.err


def test_pull_session_open_failure_is_soft(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the MCP session handshake fails, exit 0 (cron retries on next
    tick). Surface the failure on stderr so the operator can investigate
    via the cron `output/` capture."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")

    from _mcp_client import MCPCallError  # noqa: PLC0415  - test-scoped

    with patch.object(
        module, "open_session", side_effect=MCPCallError("transport boom")
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out == ""
    assert "cron.pull.session_open_failed" in captured.err
    assert "transport boom" in captured.err


def test_pull_format_carries_category_and_message() -> None:
    """`format_for_discord` invariant: category + message both present."""
    module = _load_script_module("pull_and_deliver")
    line = module.format_for_discord(
        {"category": "health", "message": "test alert"}
    )
    assert line == "[health] test alert"

    # Missing fields fall through to defensible defaults (the verb
    # validates these, but a malformed-server response shouldn't crash).
    line_empty = module.format_for_discord({})
    assert "unknown" in line_empty


# ---------------------------------------------------------------------------
# P10 / P11 — ordering + race-loss + ack-failure-mid-batch (CR-applied)
# ---------------------------------------------------------------------------


def test_pull_stdout_flushes_before_any_ack(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1 fix: stdout must flush BEFORE any ack call lands.

    The previous ordering (ack inside the format loop) created a silent-loss
    window where a process death between ack and stdout write would lose a
    notification permanently. The new ordering writes stdout for ALL claimed
    rows first, THEN issues acks — so a death mid-ack leaves rows in
    `delivering` for Story 6-3's recovery sweep to revert.

    We assert ordering by tracking call sequence: the FIRST tool call must
    be `pull_pending_notifications`, then NO `ack_notification` until after
    we've recorded the stdout-flush moment.
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")

    pull_payload = {
        "notifications": [
            {
                "id": 201,
                "tier": "urgent",
                "category": "sync",
                "message": "first",
                "enqueued_at": "2026-06-04T10:00:00.000000Z",
                "attempt_count": 1,
            },
            {
                "id": 202,
                "tier": "urgent",
                "category": "sync",
                "message": "second",
                "enqueued_at": "2026-06-04T10:00:01.000000Z",
                "attempt_count": 1,
            },
        ],
        "count": 2,
    }

    call_log: list[str] = []

    # Wrap stdout.flush so we know exactly when it landed in the call order.
    original_flush = sys.stdout.flush

    def traced_flush() -> None:
        call_log.append("stdout.flush")
        original_flush()

    def fake_tool_call(
        _base: str,
        _key: str,
        _sess: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        call_log.append(f"tool:{tool_name}")
        if tool_name == "pull_pending_notifications":
            return pull_payload
        if tool_name == "ack_notification":
            return {
                "ok": True,
                "final_status": "ok",
                "notification_id": arguments["notification_id"],
            }
        raise AssertionError(f"unexpected tool {tool_name!r}")

    with patch.object(module, "open_session", return_value="sess-xyz"), patch.object(
        module, "tool_call", side_effect=fake_tool_call
    ), patch.object(sys.stdout, "flush", side_effect=traced_flush):
        rc = module.main()

    assert rc == 0
    # Sequence assertion: pull → stdout.flush → ack → ack. No ack BEFORE flush.
    pull_index = call_log.index("tool:pull_pending_notifications")
    flush_index = call_log.index("stdout.flush")
    first_ack_index = next(
        i for i, ev in enumerate(call_log) if ev == "tool:ack_notification"
    )
    assert pull_index < flush_index < first_ack_index, (
        f"ordering violated: {call_log!r} — expected pull < flush < first ack"
    )


def test_pull_ack_race_loss_emits_observability_log(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P2 fix + AC: when `ack_notification` returns ``ok=False`` (meaning a
    recovery sweep flipped the row back to ``pending`` between pull and ack,
    OR another puller claimed the row), the script MUST emit
    ``notification.ack.race_loss`` per Story 6-3 CR HIGH-2 observability rule.
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")

    pull_payload = {
        "notifications": [
            {
                "id": 301,
                "tier": "urgent",
                "category": "health",
                "message": "racey alert",
                "enqueued_at": "2026-06-04T10:00:00.000000Z",
                "attempt_count": 1,
            },
        ],
        "count": 1,
    }

    def fake_tool_call(
        _base: str,
        _key: str,
        _sess: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "pull_pending_notifications":
            return pull_payload
        if tool_name == "ack_notification":
            # Race-loss signal: ok=False + final_status reflects the actual
            # current row state (recovery sweep already flipped to pending).
            return {
                "ok": False,
                "final_status": "pending",
                "notification_id": arguments["notification_id"],
                "error": None,
            }
        raise AssertionError(f"unexpected tool {tool_name!r}")

    with patch.object(module, "open_session", return_value="sess-xyz"), patch.object(
        module, "tool_call", side_effect=fake_tool_call
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    # Discord still gets the line (we already wrote it; pull cycle commits).
    assert "[health] racey alert" in captured.out

    # The race-loss event MUST be in the stderr log.
    race_log_lines = [
        line for line in captured.err.splitlines() if "notification.ack.race_loss" in line
    ]
    assert race_log_lines, (
        f"expected notification.ack.race_loss log entry, "
        f"got stderr: {captured.err!r}"
    )
    # Parse the race-loss log and verify the structured fields.
    parsed = json.loads(race_log_lines[0])
    assert parsed["event"] == "notification.ack.race_loss"
    assert parsed["notification_id"] == 301
    assert parsed["final_status"] == "pending"


def test_pull_ack_failure_mid_batch_still_delivers_all_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P10: first ack succeeds, second ack raises MCPCallError. Stdout MUST
    still contain BOTH lines (we flushed before any ack), and stderr MUST
    contain ``cron.pull.ack_failed`` for the failed row only. The first
    row's success is silent.
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")
    from _mcp_client import MCPCallError  # noqa: PLC0415

    pull_payload = {
        "notifications": [
            {
                "id": 401,
                "tier": "urgent",
                "category": "sync",
                "message": "first",
                "enqueued_at": "2026-06-04T10:00:00.000000Z",
                "attempt_count": 1,
            },
            {
                "id": 402,
                "tier": "urgent",
                "category": "sync",
                "message": "second",
                "enqueued_at": "2026-06-04T10:00:01.000000Z",
                "attempt_count": 1,
            },
        ],
        "count": 2,
    }
    ack_call_count = {"n": 0}

    def fake_tool_call(
        _base: str,
        _key: str,
        _sess: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "pull_pending_notifications":
            return pull_payload
        if tool_name == "ack_notification":
            ack_call_count["n"] += 1
            if ack_call_count["n"] == 2:
                # Second ack call boom.
                raise MCPCallError("ack transport timeout")
            return {
                "ok": True,
                "final_status": "ok",
                "notification_id": arguments["notification_id"],
            }
        raise AssertionError(f"unexpected tool {tool_name!r}")

    with patch.object(module, "open_session", return_value="sess-xyz"), patch.object(
        module, "tool_call", side_effect=fake_tool_call
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    # Both lines on stdout (already flushed before either ack ran).
    stdout_lines = [line for line in captured.out.splitlines() if line]
    assert stdout_lines == ["[sync] first", "[sync] second"]

    # One ack_failed log line for the second row only.
    ack_failed = [
        line for line in captured.err.splitlines() if "cron.pull.ack_failed" in line
    ]
    assert len(ack_failed) == 1, f"expected exactly 1 ack_failed log, got {ack_failed!r}"
    parsed = json.loads(ack_failed[0])
    assert parsed["notification_id"] == 402
    assert "ack transport timeout" in parsed["error"]


def test_pull_strips_whitespace_only_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P5: a whitespace-only env var (`MAILBOT_ROUTER_KEY="   "`) must be
    treated as missing — otherwise we'd send `Authorization: Bearer    ` to
    the server, which fails opaquely with a 401 instead of the clear
    missing-key event."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "   ")
    module = _load_script_module("pull_and_deliver")
    rc = module.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""
    assert "cron.pull.missing_api_key" in captured.err


def test_pull_rejects_boolean_id_as_int(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P8: a malformed server response with `id: true` must NOT slip through
    the `isinstance(int)` check. Python `bool` is a subclass of `int`, so a
    naive guard would coerce `True` → `notification_id=1` and ack notification
    id 1 (silently corrupting a real notification's state)."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    module = _load_script_module("pull_and_deliver")

    pull_payload = {
        "notifications": [
            {
                "id": True,  # malformed shape
                "tier": "urgent",
                "category": "health",
                "message": "bogus",
                "enqueued_at": "2026-06-04T10:00:00.000000Z",
                "attempt_count": 1,
            },
        ],
        "count": 1,
    }

    tool_calls: list[str] = []

    def fake_tool_call(
        _base: str,
        _key: str,
        _sess: str,
        tool_name: str,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        tool_calls.append(tool_name)
        if tool_name == "pull_pending_notifications":
            return pull_payload
        raise AssertionError(f"unexpected tool {tool_name!r}")

    with patch.object(module, "open_session", return_value="sess-xyz"), patch.object(
        module, "tool_call", side_effect=fake_tool_call
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    # No ack should have been issued for the malformed row.
    assert "ack_notification" not in tool_calls
    # Nothing on stdout (the only row was skipped).
    assert captured.out == ""


# ---------------------------------------------------------------------------
# digest_prepare — branch coverage.
# ---------------------------------------------------------------------------


def test_digest_missing_api_key_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unlike the pull loop, the digest is daily — surfacing a
    bootstrap-misconfiguration loudly via exit code 1 is the right move
    (the agent step downstream should NOT proceed with an absent payload).
    """
    monkeypatch.delenv("MAILBOT_ROUTER_KEY", raising=False)
    module = _load_script_module("digest_prepare")

    rc = module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "cron.digest.missing_api_key" in captured.err


def test_digest_writes_payload_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A successful compose_digest call writes the JSON payload to the
    configured output path via os.replace (atomic across the .tmp shim).
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    output_path = tmp_path / "digest-payload.json"
    monkeypatch.setenv("MAILBOT_DIGEST_OUTPUT", str(output_path))

    module = _load_script_module("digest_prepare")

    payload: dict[str, Any] = {
        "unread_by_importance": {
            "high": [{"email_id": "m1", "subject": "important", "from_address": "a@b.c"}],
            "medium": [],
            "low": [],
        },
        "pending_tier2_batches": [],
        "queued_important_notifications": [],
        "weekly_artifacts": None,
    }

    with patch.object(
        module, "open_session", return_value="sess-xyz"
    ), patch.object(module, "tool_call", return_value=payload):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert output_path.exists()
    written = json.loads(output_path.read_text())
    assert written == payload

    # The temp file should NOT remain after the atomic replace.
    assert not (tmp_path / "digest-payload.json.tmp").exists()

    # Structured success log line.
    assert "cron.digest.payload_written" in captured.err

    # Per Hermes's cron-with-agent contract (verified live 2026-06-04):
    # script stdout becomes the agent's prompt input. Empty stdout = no AI
    # call. So digest_prepare.py MUST write the payload to stdout too,
    # not only to the file. Asserting stdout has parseable JSON matching
    # the payload guards against an accidental "file-only" regression.
    stdout_parsed = json.loads(captured.out)
    assert stdout_parsed == payload


def test_digest_compose_failure_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If compose_digest raises MCPCallError, exit 1 + log; do NOT write
    a stale payload to disk."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    output_path = tmp_path / "digest-payload.json"
    monkeypatch.setenv("MAILBOT_DIGEST_OUTPUT", str(output_path))

    module = _load_script_module("digest_prepare")
    from _mcp_client import MCPCallError  # noqa: PLC0415  - test-scoped

    with patch.object(
        module, "open_session", return_value="sess-xyz"
    ), patch.object(
        module, "tool_call", side_effect=MCPCallError("compose blew up")
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert not output_path.exists()
    assert "cron.digest.compose_call_failed" in captured.err


def test_digest_cleans_up_tmp_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P4: if ``os.replace`` fails after ``json.dump`` succeeds (e.g.,
    cross-device rename, permission flip), the ``.tmp`` file must be
    unlinked so a stale partial write isn't left on disk. The previous
    behavior left the .tmp in place; on a subsequent run a different
    failure could see ``os.replace`` install the stale file atomically.
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    output_path = tmp_path / "digest-payload.json"
    tmp_file = tmp_path / "digest-payload.json.tmp"
    monkeypatch.setenv("MAILBOT_DIGEST_OUTPUT", str(output_path))

    module = _load_script_module("digest_prepare")
    payload: dict[str, Any] = {
        "unread_by_importance": {"high": [], "medium": [], "low": []},
        "pending_tier2_batches": [],
        "queued_important_notifications": [],
        "weekly_artifacts": None,
    }

    def boom_replace(_src: str, _dst: str) -> None:
        # The .tmp file should exist at this point — json.dump has run.
        assert tmp_file.exists(), "expected .tmp to exist before os.replace"
        raise OSError("cross-device rename simulated")

    with patch.object(
        module, "open_session", return_value="sess-xyz"
    ), patch.object(module, "tool_call", return_value=payload), patch.object(
        module.os, "replace", side_effect=boom_replace
    ):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 1
    # P4 invariant: no stale .tmp file left on disk.
    assert not tmp_file.exists(), (
        f"P4 violation: .tmp file {tmp_file} not cleaned up after OSError"
    )
    assert not output_path.exists()
    assert "cron.digest.write_failed" in captured.err


def test_digest_handles_bare_filename_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P6: a bare filename in ``MAILBOT_DIGEST_OUTPUT`` (no directory
    component) made ``os.path.dirname`` return ``""``, and ``os.makedirs("")``
    raises ``FileNotFoundError`` with a cryptic message. Guard via walrus
    so we only call makedirs when the path has a real parent directory.
    """
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    # Bare filename — no directory component, no leading "./".
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAILBOT_DIGEST_OUTPUT", "digest.json")

    module = _load_script_module("digest_prepare")
    payload: dict[str, Any] = {
        "unread_by_importance": {"high": [], "medium": [], "low": []},
        "pending_tier2_batches": [],
        "queued_important_notifications": [],
        "weekly_artifacts": None,
    }

    with patch.object(
        module, "open_session", return_value="sess-xyz"
    ), patch.object(module, "tool_call", return_value=payload):
        rc = module.main()
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0, got {rc}; stderr: {captured.err}"
    written = tmp_path / "digest.json"
    assert written.exists()


def test_digest_strips_whitespace_only_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P5: digest variant of the env-var-strip fix."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "\t  \n")
    module = _load_script_module("digest_prepare")
    rc = module.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "cron.digest.missing_api_key" in captured.err


# ---------------------------------------------------------------------------
# _mcp_client — narrow contract coverage.
# ---------------------------------------------------------------------------


def test_log_event_writes_jsonl_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`log_event` writes ONE line per call, valid JSON, to stderr."""
    _load_script_module("pull_and_deliver")  # ensures _mcp_client on path
    from _mcp_client import log_event  # noqa: PLC0415

    log_event("test.event", x=1, y="hello")
    captured = capsys.readouterr()

    assert captured.out == ""  # never stdout
    lines = [line for line in captured.err.splitlines() if line]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed == {"event": "test.event", "x": 1, "y": "hello"}


def test_mcp_call_surfaces_jsonrpc_error_payload() -> None:
    """`mcp_call` translates a JSON-RPC error payload into MCPCallError
    with the error.message preserved — operator must be able to grep the
    log line for the upstream cause.
    """
    _load_script_module("pull_and_deliver")
    from _mcp_client import MCPCallError, mcp_call  # noqa: PLC0415

    error_response = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "test",
            "error": {"code": -32601, "message": "Method not found"},
        }
    ).encode("utf-8")

    class FakeResponse:
        headers = {"Mcp-Session-Id": None}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return error_response

    with patch(
        "_mcp_client.urllib_request.urlopen", return_value=FakeResponse()
    ):
        with pytest.raises(MCPCallError) as excinfo:
            mcp_call(
                "http://x/mcp/", "key", "tools/call", params={"name": "x"}
            )
    assert "Method not found" in str(excinfo.value)


def test_mcp_call_handles_sse_framing() -> None:
    """FastMCP's streamable transport may return SSE-framed responses
    (`event: message\\ndata: <json>\\n\\n`). The client must extract the
    `data:` line and parse it.
    """
    _load_script_module("pull_and_deliver")
    from _mcp_client import mcp_call  # noqa: PLC0415

    sse_body = (
        b"event: message\n"
        b'data: {"jsonrpc":"2.0","id":"x","result":{"ok":true}}\n\n'
    )

    class FakeResponse:
        headers = {"Mcp-Session-Id": "sess-abc"}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return sse_body

    with patch(
        "_mcp_client.urllib_request.urlopen", return_value=FakeResponse()
    ):
        result, session_id = mcp_call("http://x/mcp/", "key", "initialize")
    assert result == {"ok": True}
    assert session_id == "sess-abc"


def test_mcp_call_picks_matching_frame_from_multi_event_sse() -> None:
    """P3: a multi-event SSE response containing a progress notification
    and a result event must yield the RESULT frame, not the progress frame.

    The previous "first data: line wins" parser silently returned the
    progress payload, which lacks `result` — downstream callers either
    crashed on the missing key or returned an empty dict masquerading as
    a tool result. The fix walks every `data:` line, parses each as JSON,
    and prefers the one whose `id` matches the request.
    """
    _load_script_module("pull_and_deliver")
    from _mcp_client import mcp_call  # noqa: PLC0415

    # Patch uuid.uuid4 so we can predict the request id in advance.
    class FixedUUID:
        def __str__(self) -> str:
            return "req-123"

    sse_body = (
        b"event: progress\n"
        b'data: {"jsonrpc":"2.0","method":"notifications/progress","params":{"pct":50}}\n\n'
        b"event: message\n"
        b'data: {"jsonrpc":"2.0","id":"req-123","result":{"actual":"yes"}}\n\n'
    )

    class FakeResponse:
        headers = {"Mcp-Session-Id": "sess-multi"}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return sse_body

    with patch("_mcp_client.uuid.uuid4", return_value=FixedUUID()), patch(
        "_mcp_client.urllib_request.urlopen", return_value=FakeResponse()
    ):
        result, _ = mcp_call("http://x/mcp/", "key", "tools/call")
    # MUST be the actual result, not the progress event's params.
    assert result == {"actual": "yes"}


def test_mcp_call_raises_on_sse_with_no_parseable_data_frames() -> None:
    """P3: SSE response with `event:` prefix but every `data:` line is
    unparseable JSON (or empty) must raise MCPCallError with a clear
    message — not silently return an empty dict."""
    _load_script_module("pull_and_deliver")
    from _mcp_client import MCPCallError, mcp_call  # noqa: PLC0415

    sse_body = (
        b"event: ping\n"
        b"data: \n\n"  # empty data
        b"event: malformed\n"
        b"data: not json at all\n\n"
    )

    class FakeResponse:
        headers = {"Mcp-Session-Id": "x"}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return sse_body

    with patch(
        "_mcp_client.urllib_request.urlopen", return_value=FakeResponse()
    ):
        with pytest.raises(MCPCallError) as excinfo:
            mcp_call("http://x/mcp/", "key", "tools/call")
    assert "no parseable data frame" in str(excinfo.value)


def test_mcp_call_catches_socket_timeout_as_mcp_call_error() -> None:
    """P7: ``socket.timeout`` is a subclass of OSError, NOT of
    ``urllib.error.URLError`` on all Python versions / urlopen code paths.
    A bare ``urlopen`` timeout previously propagated uncaught past the
    URLError handler. The new ``except OSError`` clause catches it and
    surfaces as MCPCallError so the cron-tick error path runs cleanly.
    """
    import socket as _socket  # noqa: PLC0415

    _load_script_module("pull_and_deliver")
    from _mcp_client import MCPCallError, mcp_call  # noqa: PLC0415

    def raise_timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise _socket.timeout("connection timed out")

    with patch("_mcp_client.urllib_request.urlopen", side_effect=raise_timeout):
        with pytest.raises(MCPCallError) as excinfo:
            mcp_call("http://x/mcp/", "key", "initialize")
    assert "MCP socket error" in str(excinfo.value)
    assert "connection timed out" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Pytest fixture: keep stderr/stdout buffers clean between tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_streams() -> None:
    """Some script paths bypass capsys by writing directly to
    `sys.stderr.write`; this fixture ensures stderr is a fresh StringIO
    if pytest's capsys hasn't taken over yet."""
    # capsys takes precedence — this is a defensive no-op when capsys is
    # active; the io.StringIO replacement only kicks in if a caller
    # disables capsys (we don't, but the fixture documents the contract).
    if not isinstance(sys.stderr, io.StringIO):
        return
    sys.stderr = io.StringIO()
