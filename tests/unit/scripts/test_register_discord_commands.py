"""Story 9.5.1: scripts/register_discord_commands.py unit + integration tests.

Coverage:
- Task 1: build_command_payload — frozen-fixture assertion (test_build_command_payload_matches_fixture)
- Task 2: parse_registration_response — 200 / 201 / 400 / 401 paths
- Task 3: --dry-run via subprocess — asserts stdout is valid JSON, exit code 0, zero network calls
- Task 4: --apply — patches httpx.Client, asserts POST fires per command with right auth
- Task 5: --delete-all — patches httpx, asserts one DELETE per enumerated ID

Per AC-4 (OQ-2 resolution): NO integration test on --apply's real network path.
That verification is subsumed into Story 9.5.2's first live walk.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

import scripts.register_discord_commands as rdc

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_PAYLOAD = (
    Path(__file__).parent / "fixtures" / "discord_register_payload_expected.json"
)
_POLICY_YAML = _PROJECT_ROOT / "router" / "policy.yaml"


# ---------------------------------------------------------------------------
# Task 1 — build_command_payload
# ---------------------------------------------------------------------------


def test_build_command_payload_matches_fixture() -> None:
    """AC-1, AC-2: payload builder produces exact frozen JSON structure.

    The fixture is the source-of-truth for what /model registers as; any
    policy.yaml task addition/removal fails this test explicitly (Adam
    updates the fixture as part of the payload-changing PR).
    """
    payload = rdc.build_command_payload(_POLICY_YAML)
    with _FIXTURE_PAYLOAD.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)
    assert payload == expected


def test_build_command_payload_returns_single_top_level_slash() -> None:
    """AC-2: single top-level /model with three subcommands (Adam-decision 2026-07-03)."""
    payload = rdc.build_command_payload(_POLICY_YAML)
    assert len(payload) == 1
    root = payload[0]
    assert root["name"] == "model"
    # Discord subcommand option type is 1 per https://discord.com/developers/docs/interactions/application-commands#application-command-object-application-command-option-type
    subcommand_names = {opt["name"] for opt in root["options"] if opt["type"] == 1}
    assert subcommand_names == {"set", "persist", "inspect"}


def test_build_command_payload_model_choices_are_epic9_short_forms() -> None:
    """AC-2: model choices are literal qwen/haiku/opus per Epic 9 known-model set."""
    payload = rdc.build_command_payload(_POLICY_YAML)
    root = payload[0]
    set_sub = next(opt for opt in root["options"] if opt["name"] == "set")
    model_opt = next(o for o in set_sub["options"] if o["name"] == "model")
    choice_values = {c["value"] for c in model_opt["choices"]}
    assert choice_values == {"qwen", "haiku", "opus"}


def test_build_command_payload_persist_task_choices_exclude_embedding() -> None:
    """AC-2: /model persist task choices exclude `embedding` per Story 9-4 AC-2."""
    payload = rdc.build_command_payload(_POLICY_YAML)
    root = payload[0]
    persist_sub = next(opt for opt in root["options"] if opt["name"] == "persist")
    task_opt = next(o for o in persist_sub["options"] if o["name"] == "task")
    choice_values = {c["value"] for c in task_opt["choices"]}
    assert "embedding" not in choice_values
    # sanity: known Epic 9 overridable tasks are present
    assert "draft_reply" in choice_values
    assert "summary_short" in choice_values


# ---------------------------------------------------------------------------
# Task 2 — parse_registration_response
# ---------------------------------------------------------------------------


def _mock_response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status_code=status, json=body)


def test_parse_registration_response_200_captures_command_id() -> None:
    resp = _mock_response(200, {"id": "1234567890", "name": "model"})
    result = rdc.parse_registration_response(resp)
    assert result.success is True
    assert result.command_id == "1234567890"
    assert result.error_code is None


def test_parse_registration_response_201_captures_command_id() -> None:
    resp = _mock_response(201, {"id": "9876543210", "name": "model"})
    result = rdc.parse_registration_response(resp)
    assert result.success is True
    assert result.command_id == "9876543210"


def test_parse_registration_response_400_invalid_form_body() -> None:
    resp = _mock_response(400, {"code": 50035, "message": "Invalid Form Body"})
    result = rdc.parse_registration_response(resp)
    assert result.success is False
    assert result.command_id is None
    assert result.error_code == 50035
    assert result.error_message == "Invalid Form Body"


def test_parse_registration_response_401_missing_scope() -> None:
    resp = _mock_response(401, {"code": 0, "message": "401: Unauthorized"})
    result = rdc.parse_registration_response(resp)
    assert result.success is False
    assert result.error_code == 0
    assert "Unauthorized" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Task 3 — --dry-run via subprocess
# ---------------------------------------------------------------------------


def test_dry_run_via_subprocess() -> None:
    """AC-4: --dry-run exits 0, prints JSON matching fixture, zero network."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.register_discord_commands", "--dry-run"],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    # Script writes raw UTF-8 to stdout.buffer to preserve em-dashes on Windows.
    parsed = json.loads(result.stdout.decode("utf-8"))
    with _FIXTURE_PAYLOAD.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)
    assert parsed == expected


def test_dry_run_makes_zero_network_calls_in_process() -> None:
    """In-process cross-check: patch httpx.Client, assert no method fired."""
    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        rc = rdc.main(["--dry-run"])
    assert rc == 0
    client_inst.post.assert_not_called()
    client_inst.get.assert_not_called()
    client_inst.delete.assert_not_called()


# ---------------------------------------------------------------------------
# Task 4 — --apply
# ---------------------------------------------------------------------------


def test_apply_missing_bot_token_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "111")
    rc = rdc.main(["--apply"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "DISCORD_BOT_TOKEN" in err


def test_apply_missing_application_id_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    rc = rdc.main(["--apply"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "DISCORD_APPLICATION_ID" in err


def test_apply_calls_discord_post_with_bot_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret-token")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-111")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.post.return_value = httpx.Response(
            status_code=201, json={"id": "cmd-xyz", "name": "model"}
        )
        rc = rdc.main(["--apply"])

    assert rc == 0, capsys.readouterr()
    # One POST per top-level command; payload has one entry.
    assert client_inst.post.call_count == 1
    call = client_inst.post.call_args
    url = call.args[0] if call.args else call.kwargs["url"]
    assert url == "https://discord.com/api/v10/applications/app-111/commands"
    headers = call.kwargs["headers"]
    assert headers["Authorization"] == "Bot sekret-token"


def test_apply_reports_failure_and_exits_1_on_4xx(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "111")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.post.return_value = httpx.Response(
            status_code=400, json={"code": 50035, "message": "Invalid Form Body"}
        )
        rc = rdc.main(["--apply"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "50035" in err
    assert "Invalid Form Body" in err


# ---------------------------------------------------------------------------
# Task 5 — --delete-all
# ---------------------------------------------------------------------------


def test_delete_all_deletes_each_enumerated_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-42")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.get.return_value = httpx.Response(
            status_code=200,
            json=[
                {"id": "cmd-1", "name": "model"},
                {"id": "cmd-2", "name": "cost"},
            ],
        )
        client_inst.delete.return_value = httpx.Response(status_code=204)
        rc = rdc.main(["--delete-all"])

    assert rc == 0, capsys.readouterr()
    assert client_inst.delete.call_count == 2
    delete_urls = {call.args[0] for call in client_inst.delete.call_args_list}
    assert delete_urls == {
        "https://discord.com/api/v10/applications/app-42/commands/cmd-1",
        "https://discord.com/api/v10/applications/app-42/commands/cmd-2",
    }


def test_delete_all_missing_credentials_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    rc = rdc.main(["--delete-all"])
    assert rc == 2


# ---------------------------------------------------------------------------
# Argparse smoke — mutual exclusion
# ---------------------------------------------------------------------------


def test_mutually_exclusive_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        rdc.main(["--dry-run", "--apply"])


def test_default_mode_is_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-1: --dry-run is the default when no explicit mode is supplied."""
    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        rc = rdc.main([])
    assert rc == 0
    client_inst.post.assert_not_called()


# ---------------------------------------------------------------------------
# CR fix regression tests
# ---------------------------------------------------------------------------


def test_cr_f1_parse_response_handles_non_json_body() -> None:
    """CR-F1 + CR-F3: 5xx with Cloudflare HTML body → structured failure, no raise, raw body NOT echoed."""
    dangerous_body = "<html>SENSITIVE_LEAK_MARKER</html>"
    resp = httpx.Response(status_code=502, text=dangerous_body)
    result = rdc.parse_registration_response(resp)
    assert result.success is False
    assert result.error_code == 502
    assert "non-JSON" in (result.error_message or "")
    # CR-F3 defense-in-depth: raw response body must NOT appear in the
    # structured error_message (would risk token echo on a 401).
    assert "SENSITIVE_LEAK_MARKER" not in (result.error_message or "")


def test_cr_f1_parse_response_handles_empty_body() -> None:
    """CR-F1: 500 with empty body → structured failure, no raise."""
    resp = httpx.Response(status_code=500, text="")
    result = rdc.parse_registration_response(resp)
    assert result.success is False
    assert result.error_code == 500


def test_cr_f5_parse_response_treats_2xx_missing_id_as_failure() -> None:
    """CR-F5: 200 response missing 'id' field → failure, not silent success."""
    resp = httpx.Response(status_code=200, json={"name": "model"})  # no "id"
    result = rdc.parse_registration_response(resp)
    assert result.success is False
    assert result.command_id is None
    assert result.error_code == 200
    assert "missing required 'id'" in (result.error_message or "")


def test_cr_f4_load_task_names_handles_empty_yaml(tmp_path: Path) -> None:
    """CR-F4: empty policy.yaml → empty list, not AttributeError."""
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    assert rdc._load_task_names(empty_yaml) == []


def test_cr_f4_load_task_names_handles_comments_only(tmp_path: Path) -> None:
    """CR-F4: yaml with only comments → empty list."""
    only_comments = tmp_path / "comments.yaml"
    only_comments.write_text("# just a comment\n# another\n", encoding="utf-8")
    assert rdc._load_task_names(only_comments) == []


def test_cr_f4_load_task_names_handles_non_dict_root(tmp_path: Path) -> None:
    """CR-F4: yaml root is a list, not a dict → empty list, not AttributeError."""
    non_dict = tmp_path / "list.yaml"
    non_dict.write_text("- foo\n- bar\n", encoding="utf-8")
    assert rdc._load_task_names(non_dict) == []


def test_cr_f8_root_command_has_type_field() -> None:
    """CR-F8: root command payload includes type=1 (CHAT_INPUT)."""
    payload = rdc.build_command_payload(_POLICY_YAML)
    assert payload[0]["type"] == 1


def test_cr_f9_whitespace_only_token_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CR-F9: whitespace-only DISCORD_BOT_TOKEN treated as missing."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "   ")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "111")
    rc = rdc.main(["--apply"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "DISCORD_BOT_TOKEN" in err


def test_cr_f9_whitespace_only_app_id_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CR-F9: whitespace-only DISCORD_APPLICATION_ID treated as missing."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "\t\n ")
    rc = rdc.main(["--apply"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "DISCORD_APPLICATION_ID" in err


def test_cr_f11_delete_all_prints_no_commands_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CR-F11: --delete-all against empty registration prints explicit message."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-empty")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.get.return_value = httpx.Response(status_code=200, json=[])
        rc = rdc.main(["--delete-all"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "No commands found" in out
    client_inst.delete.assert_not_called()


def test_cr_f2_delete_all_skips_command_missing_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CR-F2: malformed command entry (no 'id') is skipped with warning, not KeyError."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-42")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.get.return_value = httpx.Response(
            status_code=200,
            json=[
                {"name": "no-id-here"},  # malformed
                {"id": "cmd-good", "name": "model"},
            ],
        )
        client_inst.delete.return_value = httpx.Response(status_code=204)
        rc = rdc.main(["--delete-all"])

    assert rc == 0, capsys.readouterr()
    captured = capsys.readouterr()
    assert "Skipping malformed" in captured.err
    # Only the well-formed entry got deleted
    assert client_inst.delete.call_count == 1


def test_cr_f3_delete_all_error_path_uses_structured_parser(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CR-F3: 401 on enumerate → prints only Discord's structured code+message.

    Constructs a JSON-parseable 401 (real Discord shape). The structured
    parser extracts code + message from the JSON body; raw response text is
    never printed to stderr. Regression against the pre-fix code path which
    did `f"{resp.status_code} {resp.text}"` and could echo sensitive fragments.
    """
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-42")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.get.return_value = httpx.Response(
            status_code=401,
            json={"code": 0, "message": "401: Unauthorized"},
        )
        rc = rdc.main(["--delete-all"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "Unauthorized" in err
    # The structured error line uses "Failed to enumerate commands: 0 401: Unauthorized"
    # — verify the code and message both appear.
    assert "Failed to enumerate commands" in err


def test_cr_f3_delete_all_delete_failure_uses_structured_parser(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CR-F3: per-command DELETE failure also uses structured parser."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "sekret")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-42")

    with patch.object(rdc.httpx, "Client") as client_cls:
        client_inst = MagicMock()
        client_cls.return_value.__enter__.return_value = client_inst
        client_inst.get.return_value = httpx.Response(
            status_code=200,
            json=[{"id": "cmd-x", "name": "model"}],
        )
        client_inst.delete.return_value = httpx.Response(
            status_code=403,
            json={"code": 50001, "message": "Missing Access"},
        )
        rc = rdc.main(["--delete-all"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "Missing Access" in err
    assert "50001" in err
