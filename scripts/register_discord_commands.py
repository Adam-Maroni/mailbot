"""Story 9.5.1: one-shot Discord Developer Portal API client for the /model slash-command family.

Path γ discharge — this script is the MailBot-side alternative to modifying
Hermes source. Registration happens out-of-band: Adam runs this once per
Discord application, Discord persists the commands server-side, and stock
upstream Hermes routes incoming interactions to mailbot-api's MCP verbs
unchanged. See docs/runbooks/discord-slash-registration.md for the ops flow.

Modes:
  --dry-run      (default) — build payload from router/policy.yaml, print JSON to stdout, exit 0
  --apply        — POST payload to Discord; requires DISCORD_BOT_TOKEN + DISCORD_APPLICATION_ID
  --delete-all   — enumerate + DELETE all registered application commands

Byte-identical invariant (AC-7 of Story 9.5.1):
  This script does NOT modify mailbot-api's mcp_server.py, router/policy.py,
  or router/policy.yaml. It only READS policy.yaml to derive the /model
  persist subcommand's task choice list.

Reference:
  https://discord.com/developers/docs/interactions/application-commands
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

DISCORD_API_VERSION = "v10"
DISCORD_API_BASE = f"https://discord.com/api/{DISCORD_API_VERSION}"

# CR-F6: split connect vs read timeout so a hung TCP handshake fails fast
# while an accepted-but-slow API call has room to complete. Rate-limited
# writes (Discord's global 50/sec limit) can legitimately take 5-15s of
# server-side wait before the 429 response arrives.
_DISCORD_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0)

# Epic 9 short-form model set — matches Story 9-3 / 9-4 known-model registry.
KNOWN_MODEL_SHORT_FORMS: tuple[str, ...] = ("qwen", "haiku", "opus")

# `embedding` is not a /model overridable task per Story 9-4 AC-2:
# Router.dispatch_embedding handles embedding routing, not ask_router, so
# force_model has no defined semantics for this task type. Registering it as
# a `/model persist task=embedding` choice would let a user set a persistent
# override that the Router never consults — surfacing as silent-no-op.
# Excluding it from the Discord picker prevents the confused-user path.
EXCLUDED_FROM_PERSIST_CHOICES: frozenset[str] = frozenset({"embedding"})

# Discord application command types (root-level command.type field)
# https://discord.com/developers/docs/interactions/application-commands#application-command-object-application-command-types
_CMD_CHAT_INPUT = 1  # slash command (the only type this script emits)

# Discord application command option types (per-option option.type field)
# https://discord.com/developers/docs/interactions/application-commands#application-command-object-application-command-option-type
_OPT_SUB_COMMAND = 1
_OPT_STRING = 3

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_POLICY_YAML = _PROJECT_ROOT / "router" / "policy.yaml"


@dataclass(frozen=True)
class RegistrationResult:
    """Result of parsing a Discord Portal registration response."""

    success: bool
    command_id: str | None
    error_code: int | None
    error_message: str | None


def _load_task_names(policy_path: Path) -> list[str]:
    """Extract top-level task names from router/policy.yaml, sorted deterministically."""
    with policy_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    # yaml.safe_load returns None on empty/comments-only files (CR-F4);
    # treat as "no tasks" rather than crashing on .get() dereference.
    if not isinstance(data, dict):
        return []
    tasks = data.get("tasks", {})
    if not isinstance(tasks, dict):
        return []
    names = sorted(t for t in tasks.keys() if t not in EXCLUDED_FROM_PERSIST_CHOICES)
    return names


def _model_choices() -> list[dict[str, str]]:
    return [{"name": m, "value": m} for m in KNOWN_MODEL_SHORT_FORMS]


def _task_choices(policy_path: Path) -> list[dict[str, str]]:
    return [{"name": t, "value": t} for t in _load_task_names(policy_path)]


def build_command_payload(policy_path: Path) -> list[dict[str, Any]]:
    """Build the Discord application command JSON payload for the /model family.

    Returns a list of one command (top-level /model with three subcommands).
    Discord dedupes by (application_id, name), so re-POST is idempotent.
    """
    model_choices = _model_choices()
    task_choices = _task_choices(policy_path)

    set_subcommand = {
        "name": "set",
        "description": "Override the model for the current one-shot dispatch",
        "type": _OPT_SUB_COMMAND,
        "options": [
            {
                "name": "model",
                "description": "Model short-form (qwen | haiku | opus)",
                "type": _OPT_STRING,
                "required": True,
                "choices": model_choices,
            }
        ],
    }

    persist_subcommand = {
        "name": "persist",
        "description": "Persist a model override for a specific task in policy.user-overrides.yaml",
        "type": _OPT_SUB_COMMAND,
        "options": [
            {
                "name": "task",
                "description": "Router task name (see router/policy.yaml)",
                "type": _OPT_STRING,
                "required": True,
                "choices": task_choices,
            },
            {
                "name": "model",
                "description": "Model short-form (qwen | haiku | opus)",
                "type": _OPT_STRING,
                "required": True,
                "choices": model_choices,
            },
        ],
    }

    inspect_subcommand = {
        "name": "inspect",
        "description": "Show the current effective /model policy (base + user overrides)",
        "type": _OPT_SUB_COMMAND,
        "options": [],
    }

    root_command = {
        "name": "model",
        # CR-F8: explicit type=1 (CHAT_INPUT). Discord defaults omitted type
        # to CHAT_INPUT but the API contract is not satisfied without it.
        "type": _CMD_CHAT_INPUT,
        # CR-F13: ASCII-only description (no em-dash) — bypasses the httpx
        # JSON-encoder edge case and keeps the payload safe across any
        # intermediate proxy that might mishandle non-ASCII.
        "description": "MailBot Router /model family - one-shot / persistent / inspect",
        "options": [set_subcommand, persist_subcommand, inspect_subcommand],
    }

    return [root_command]


def parse_registration_response(response: httpx.Response) -> RegistrationResult:
    """Turn a Discord Portal response into a structured result.

    Success on 200/201 IF the body carries a non-None `id` (Discord's contract
    for a successful create/update). Missing-id-on-2xx is treated as failure
    (CR-F5) — silent success with no command_id would mask real problems.

    On 4xx/5xx: captures Discord's error `code` + `message` when the body is
    valid JSON. When the body is non-JSON (Cloudflare HTML 5xx page, empty
    body, upstream gateway error — CR-F1), returns a structured failure
    without raising, so the caller can exit 1 cleanly instead of trace-dumping.

    Reference: https://discord.com/developers/docs/reference#error-messages
    """
    try:
        body: dict[str, Any] = response.json()
    except (ValueError, json.JSONDecodeError):
        # Non-JSON response (e.g., Cloudflare HTML error page, empty body,
        # upstream gateway error). CR-F1 + CR-F3 defense: NEVER include the
        # raw response.text in the error_message. A 401's body content could
        # in theory echo header fragments referencing the bearer token; a
        # Cloudflare page reveals nothing useful. Keep the status code as
        # the sole diagnostic signal; operator inspects Discord's status
        # page or re-runs with a network trace if root cause is needed.
        return RegistrationResult(
            success=False,
            command_id=None,
            error_code=response.status_code,
            error_message="non-JSON response body (raw body suppressed for safety)",
        )

    if response.status_code in (200, 201):
        command_id = body.get("id")
        if command_id is None:
            return RegistrationResult(
                success=False,
                command_id=None,
                error_code=response.status_code,
                error_message="2xx response missing required 'id' field",
            )
        return RegistrationResult(
            success=True,
            command_id=command_id,
            error_code=None,
            error_message=None,
        )
    return RegistrationResult(
        success=False,
        command_id=None,
        error_code=body.get("code"),
        error_message=body.get("message"),
    )


def _read_credentials() -> tuple[str, str] | None:
    """Return (token, app_id) or None if either env var is missing or whitespace-only.

    CR-F9: strips whitespace before the "is this present?" check so a token
    that is literally `"   "` (accidental copy-paste of leading/trailing spaces)
    doesn't reach the Authorization header as `Bot    ` and produce a
    confusing 401.
    """
    token_raw = os.environ.get("DISCORD_BOT_TOKEN") or ""
    app_id_raw = os.environ.get("DISCORD_APPLICATION_ID") or ""
    token = token_raw.strip()
    app_id = app_id_raw.strip()
    if not token:
        print(
            "ERROR: DISCORD_BOT_TOKEN environment variable is required for --apply / --delete-all",
            file=sys.stderr,
        )
        return None
    if not app_id:
        print(
            "ERROR: DISCORD_APPLICATION_ID environment variable is required for --apply / --delete-all",
            file=sys.stderr,
        )
        return None
    return token, app_id


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def cmd_dry_run(policy_path: Path) -> int:
    payload = build_command_payload(policy_path)
    # Force UTF-8 output — Windows stdout defaults to cp1252 and would mangle
    # any non-ASCII in the payload's description fields (defense-in-depth
    # even after CR-F13's ASCII-fication of the current descriptions, since
    # future task/subcommand additions may legitimately need non-ASCII).
    # Write bytes directly to sys.stdout.buffer to bypass the platform codec,
    # then flush explicitly so `python ... | jq` pipelines don't race (CR-F10).
    encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()
    return 0


def cmd_apply(policy_path: Path) -> int:
    creds = _read_credentials()
    if creds is None:
        return 2
    token, app_id = creds
    payload = build_command_payload(policy_path)
    url = f"{DISCORD_API_BASE}/applications/{app_id}/commands"
    headers = _auth_headers(token)

    with httpx.Client(timeout=_DISCORD_TIMEOUT) as client:
        for command in payload:
            resp = client.post(url, headers=headers, json=command)
            result = parse_registration_response(resp)
            if not result.success:
                print(
                    f"Failed /{command['name']}: {result.error_code} {result.error_message}",
                    file=sys.stderr,
                )
                return 1
            print(f"Registered /{command['name']} → command_id={result.command_id}")

    print(
        "Summary: registration complete. Discord commands appear in-client "
        "autocomplete within ~1 minute globally. Verify by typing / in Discord."
    )
    return 0


def cmd_delete_all(policy_path: Path) -> int:
    creds = _read_credentials()
    if creds is None:
        return 2
    token, app_id = creds
    list_url = f"{DISCORD_API_BASE}/applications/{app_id}/commands"
    headers = _auth_headers(token)

    with httpx.Client(timeout=_DISCORD_TIMEOUT) as client:
        resp = client.get(list_url, headers=headers)
        if resp.status_code != 200:
            # CR-F3: never print raw resp.text — a 401 body can echo header
            # fragments that reference the bearer token. Use the structured
            # parser which extracts only Discord's code + message fields.
            result = parse_registration_response(resp)
            print(
                f"Failed to enumerate commands: {result.error_code} {result.error_message}",
                file=sys.stderr,
            )
            return 1
        try:
            commands = resp.json()
        except (ValueError, json.JSONDecodeError):
            print(
                "Failed to parse enumerate response as JSON",
                file=sys.stderr,
            )
            return 1
        if not isinstance(commands, list):
            print(
                f"Unexpected enumerate response shape: {type(commands).__name__}",
                file=sys.stderr,
            )
            return 1

        # CR-F11: explicit no-op message when zero commands are registered so
        # operators aren't left wondering whether the API call actually ran.
        if not commands:
            print("No commands found — application has zero registered commands. Nothing to delete.")
            return 0

        for command in commands:
            # CR-F2: defensive dict.get on both id and name. A malformed
            # Discord response missing "id" gets skipped with a warning
            # rather than crashing with a raw KeyError traceback.
            cmd_id = command.get("id") if isinstance(command, dict) else None
            cmd_name = command.get("name", "?") if isinstance(command, dict) else "?"
            if cmd_id is None:
                print(
                    f"Skipping malformed command entry (no 'id' field): {command!r}",
                    file=sys.stderr,
                )
                continue
            del_url = f"{DISCORD_API_BASE}/applications/{app_id}/commands/{cmd_id}"
            del_resp = client.delete(del_url, headers=headers)
            if del_resp.status_code not in (200, 204):
                # CR-F3: uniform structured error path via parse_registration_response.
                result = parse_registration_response(del_resp)
                print(
                    f"Failed to delete /{cmd_name} (id={cmd_id}): {result.error_code} {result.error_message}",
                    file=sys.stderr,
                )
                return 1
            print(f"Deleted /{cmd_name} (command_id={cmd_id})")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="register_discord_commands",
        description=(
            "One-shot Discord Portal API registration for the /model slash-command family. "
            "Reads router/policy.yaml to build the payload. Idempotent — Discord dedupes "
            "by (application_id, command_name). See docs/runbooks/discord-slash-registration.md."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="mode",
        action="store_const",
        const="dry-run",
        help="Build payload and print JSON to stdout. No network calls. Default when no mode is supplied.",
    )
    mode.add_argument(
        "--apply",
        dest="mode",
        action="store_const",
        const="apply",
        help="POST payload to Discord Portal. Requires DISCORD_BOT_TOKEN + DISCORD_APPLICATION_ID.",
    )
    mode.add_argument(
        "--delete-all",
        dest="mode",
        action="store_const",
        const="delete-all",
        help="Enumerate and DELETE all registered application commands. Iteration aid.",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=_DEFAULT_POLICY_YAML,
        help=f"Path to router/policy.yaml (default: {_DEFAULT_POLICY_YAML})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    mode = args.mode or "dry-run"
    policy_path: Path = args.policy

    if mode == "dry-run":
        return cmd_dry_run(policy_path)
    if mode == "apply":
        return cmd_apply(policy_path)
    if mode == "delete-all":
        return cmd_delete_all(policy_path)
    # unreachable
    print(f"Unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
