from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from open_notebook.ai.codex_app_server import (
    CodexAppServerChatModel,
    _CodexAppServerClient,
)


def _read_calls(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    calls: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            calls.append(decoded)
    return calls


def _server_args(server_script: Path, log_path: Path, marker: str, env_bearing: bool) -> list[str]:
    args = [
        str(server_script),
        "--log-path",
        str(log_path),
    ]
    if env_bearing:
        args.extend(["--marker-env", "OPEN_NOTEBOOK_NATIVE_MCP_SMOKE_MARKER"])
    else:
        args.extend(["--marker", marker])
    return args


def _config_overrides(
    server_script: Path,
    log_path: Path,
    marker: str,
    *,
    env_bearing: bool = False,
) -> list[str]:
    if env_bearing:
        return []
    return [
        f"mcp_servers.open_notebook_native_smoke.command={json.dumps(sys.executable)}",
        "mcp_servers.open_notebook_native_smoke.args="
        + json.dumps(_server_args(server_script, log_path, marker, env_bearing)),
    ]


def _private_codex_home(
    base_codex_home: str | None,
    server_script: Path,
    log_path: Path,
    marker: str,
) -> Path:
    runtime_home = Path(
        tempfile.mkdtemp(prefix="open-notebook-codex-native-mcp-smoke-", dir="/tmp")
    )
    runtime_home.chmod(0o700)
    base_home = Path(base_codex_home).expanduser() if base_codex_home else Path.home() / ".codex"
    for auth_path in base_home.glob("auth.json*"):
        (runtime_home / auth_path.name).symlink_to(auth_path)
    config = "\n".join(
        [
            "# Managed by Open Notebook native MCP smoke.",
            "[mcp_servers.open_notebook_native_smoke]",
            f"command = {json.dumps(sys.executable)}",
            "args = " + json.dumps(_server_args(server_script, log_path, marker, True)),
            "[mcp_servers.open_notebook_native_smoke.env]",
            f"OPEN_NOTEBOOK_NATIVE_MCP_SMOKE_MARKER = {json.dumps(marker)}",
            "",
        ]
    )
    config_path = runtime_home / "config.toml"
    config_path.write_text(config, encoding="utf-8")
    config_path.chmod(0o600)
    return runtime_home


def run_direct_smoke(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir).expanduser()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / "native-mcp-calls.jsonl"
    marker = f"open-notebook-native-mcp-smoke-{uuid.uuid4()}"
    server_script = Path(__file__).with_name("codex_native_mcp_server.py").resolve()
    cwd = Path(args.cwd).expanduser()
    cwd.mkdir(parents=True, exist_ok=True)
    overrides = _config_overrides(
        server_script,
        log_path,
        marker,
        env_bearing=args.env_bearing,
    )
    runtime_codex_home = (
        _private_codex_home(args.codex_home, server_script, log_path, marker)
        if args.env_bearing
        else None
    )

    client = _CodexAppServerClient(
        args.codex_bin,
        args.profile or "",
        str(runtime_codex_home) if runtime_codex_home else args.codex_home,
        overrides,
    )
    try:
        init_id = client.send(
            "initialize",
            {
                "clientInfo": {
                    "name": "open-notebook-native-mcp-smoke",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        init_response = client.wait_for_response(init_id, min(args.timeout, 60))
        if "error" in init_response:
            raise RuntimeError(f"initialize failed: {init_response['error']}")

        thread_id_req = client.send(
            "thread/start",
            {
                "cwd": str(cwd),
                "model": args.model,
                "approvalPolicy": "never",
                "sandbox": args.sandbox,
                "ephemeral": True,
                "personality": "pragmatic",
                "threadSource": "user",
                "sessionStartSource": "startup",
            },
        )
        thread_response = client.wait_for_response(thread_id_req, min(args.timeout, 120))
        if "error" in thread_response:
            raise RuntimeError(f"thread/start failed: {thread_response['error']}")
        thread_id = thread_response["result"]["thread"]["id"]

        status_req = client.send(
            "mcpServerStatus/list",
            {"threadId": thread_id, "detail": "full"},
        )
        status_response = client.wait_for_response(status_req, min(args.timeout, 120))
        if "error" in status_response:
            raise RuntimeError(f"mcpServerStatus/list failed: {status_response['error']}")

        call_req = client.send(
            "mcpServer/tool/call",
            {
                "threadId": thread_id,
                "server": "open_notebook_native_smoke",
                "tool": "native_smoke_lookup",
                "arguments": {"request": "direct Codex app-server MCP smoke"},
            },
        )
        call_response = client.wait_for_response(call_req, min(args.timeout, 120))
        if "error" in call_response:
            raise RuntimeError(f"mcpServer/tool/call failed: {call_response['error']}")
        error = None
    except Exception as exc:
        status_response = {}
        call_response = {}
        error = str(exc)
    finally:
        client.close()
        if runtime_codex_home:
            shutil.rmtree(runtime_codex_home, ignore_errors=True)

    calls = _read_calls(log_path)
    tool_called = any(call.get("tool") == "native_smoke_lookup" for call in calls)
    call_response_text = json.dumps(call_response, sort_keys=True)
    status_response_text = json.dumps(status_response, sort_keys=True)
    return {
        "mode": "direct",
        "env_bearing": args.env_bearing,
        "success": tool_called and marker in call_response_text,
        "tool_called": tool_called,
        "call_count": len(calls),
        "call_response_contains_marker": marker in call_response_text,
        "status_response_contains_server": "open_notebook_native_smoke"
        in status_response_text,
        "error": error,
        "runtime_dir": str(runtime_dir),
    }


def run_model_smoke(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir).expanduser()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / "native-mcp-calls.jsonl"
    marker = f"open-notebook-native-mcp-smoke-{uuid.uuid4()}"
    server_script = Path(__file__).with_name("codex_native_mcp_server.py").resolve()
    cwd = Path(args.cwd).expanduser()
    cwd.mkdir(parents=True, exist_ok=True)
    overrides = _config_overrides(
        server_script,
        log_path,
        marker,
        env_bearing=args.env_bearing,
    )
    runtime_codex_home = (
        _private_codex_home(args.codex_home, server_script, log_path, marker)
        if args.env_bearing
        else None
    )
    server_request_log_path = runtime_dir / "server-requests.jsonl"
    model = CodexAppServerChatModel(
        model=args.model,
        codex_bin=args.codex_bin,
        profile=args.profile or "",
        codex_home=args.codex_home,
        cwd=str(cwd),
        timeout=args.timeout,
        sandbox=args.sandbox,
    )
    prompt = (
        "Use the open_notebook_native_smoke MCP server's native_smoke_lookup "
        "tool to retrieve the exact hidden Open Notebook native MCP smoke "
        "marker. Reply with only that marker."
    )

    original_reply = _CodexAppServerClient._reply_to_server_request

    def _recording_reply(client: _CodexAppServerClient, request: dict[str, Any]) -> None:
        server_request_log_path.parent.mkdir(parents=True, exist_ok=True)
        with server_request_log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "method": request.get("method"),
                        "params": request.get("params"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        original_reply(client, request)

    with patch(
        "open_notebook.ai.codex_app_server.build_codex_mcp_config_overrides",
        return_value={
            "enabled": True,
            "overrides": overrides,
            "server_names": ["open_notebook_native_smoke"],
            "skipped_env_servers": [],
        },
    ), patch(
        "open_notebook.ai.codex_app_server.build_codex_mcp_launch_config",
        return_value={
            "enabled": True,
            "config_overrides": overrides,
            "codex_home": str(runtime_codex_home) if runtime_codex_home else args.codex_home,
            "cleanup_path": None,
            "server_names": ["open_notebook_native_smoke"],
            "env_server_names": ["open_notebook_native_smoke"] if args.env_bearing else [],
        },
    ), patch.object(
        _CodexAppServerClient,
        "_reply_to_server_request",
        _recording_reply,
    ):
        try:
            response = model.invoke([HumanMessage(content=prompt)])
            response_content = str(response.content)
            error = None
        except Exception as exc:
            response_content = ""
            error = str(exc)

    calls = _read_calls(log_path)
    server_requests = _read_calls(server_request_log_path)
    if runtime_codex_home:
        shutil.rmtree(runtime_codex_home, ignore_errors=True)
    tool_called = any(call.get("tool") == "native_smoke_lookup" for call in calls)
    return {
        "mode": "model",
        "env_bearing": args.env_bearing,
        "success": tool_called and marker in response_content,
        "tool_called": tool_called,
        "call_count": len(calls),
        "server_request_methods": [
            request.get("method") for request in server_requests
        ],
        "response_contains_marker": marker in response_content,
        "response_preview": response_content[:500],
        "error": error,
        "runtime_dir": str(runtime_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live smoke for Codex app-server native MCP calls."
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--profile", default="")
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--cwd", default="/tmp/open-notebook-codex-native-mcp-cwd")
    parser.add_argument("--runtime-dir", default="/tmp/open-notebook-codex-native-mcp-smoke")
    parser.add_argument("--mode", choices=["direct", "model"], default="direct")
    parser.add_argument("--env-bearing", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--sandbox", default="read-only")
    args = parser.parse_args()

    result = run_direct_smoke(args) if args.mode == "direct" else run_model_smoke(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
