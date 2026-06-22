from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from open_notebook.ai.codex_app_server import _CodexAppServerClient


def _private_codex_home(
    base_codex_home: str | None,
    *,
    project: str,
    open_notebook_url: str,
    open_notebook_password: str,
) -> Path:
    runtime_home = Path(
        tempfile.mkdtemp(prefix="open-notebook-codex-open-notebook-mcp-", dir="/tmp")
    )
    runtime_home.chmod(0o700)
    base_home = Path(base_codex_home).expanduser() if base_codex_home else Path.home() / ".codex"
    for auth_path in base_home.glob("auth.json*"):
        (runtime_home / auth_path.name).symlink_to(auth_path)
    config = "\n".join(
        [
            "# Managed by Open Notebook Codex/Open Notebook MCP smoke.",
            "[mcp_servers.open_notebook]",
            'command = "uv"',
            "args = " + json.dumps(["run", "--project", project, "open-notebook-mcp"]),
            "[mcp_servers.open_notebook.env]",
            f"OPEN_NOTEBOOK_URL = {json.dumps(open_notebook_url)}",
            f"OPEN_NOTEBOOK_PASSWORD = {json.dumps(open_notebook_password)}",
            "",
        ]
    )
    config_path = runtime_home / "config.toml"
    config_path.write_text(config, encoding="utf-8")
    config_path.chmod(0o600)
    return runtime_home


def _response_text(response: dict[str, Any]) -> str:
    return json.dumps(response, sort_keys=True)


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    marker = f"open-notebook-codex-mcp-smoke-{uuid.uuid4()}"
    cwd = Path(args.cwd).expanduser()
    cwd.mkdir(parents=True, exist_ok=True)
    runtime_codex_home = _private_codex_home(
        args.codex_home,
        project=args.project,
        open_notebook_url=args.open_notebook_url,
        open_notebook_password=args.open_notebook_password,
    )
    client = _CodexAppServerClient(args.codex_bin, args.profile or "", str(runtime_codex_home), [])
    try:
        init_id = client.send(
            "initialize",
            {
                "clientInfo": {
                    "name": "open-notebook-codex-open-notebook-mcp-smoke",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        init_response = client.wait_for_response(init_id, min(args.timeout, 60))
        if "error" in init_response:
            raise RuntimeError(f"initialize failed: {init_response['error']}")

        thread_req = client.send(
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
        thread_response = client.wait_for_response(thread_req, min(args.timeout, 120))
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

        list_req = client.send(
            "mcpServer/tool/call",
            {
                "threadId": thread_id,
                "server": "open_notebook",
                "tool": "list_notebooks",
                "arguments": {},
            },
        )
        list_response = client.wait_for_response(list_req, min(args.timeout, 120))
        if "error" in list_response:
            raise RuntimeError(f"list_notebooks failed: {list_response['error']}")

        create_req = client.send(
            "mcpServer/tool/call",
            {
                "threadId": thread_id,
                "server": "open_notebook",
                "tool": "create_note",
                "arguments": {
                    "content": marker,
                    "title": "Open Notebook Codex MCP smoke",
                    "note_type": "human",
                },
            },
        )
        create_response = client.wait_for_response(create_req, min(args.timeout, 120))
        if "error" in create_response:
            raise RuntimeError(f"create_note failed: {create_response['error']}")
        error = None
    except Exception as exc:
        status_response = {}
        list_response = {}
        create_response = {}
        error = str(exc)
    finally:
        client.close()
        shutil.rmtree(runtime_codex_home, ignore_errors=True)

    status_text = _response_text(status_response)
    list_text = _response_text(list_response)
    create_text = _response_text(create_response)
    return {
        "success": (
            "open_notebook" in status_text
            and "error" not in list_response
            and "error" not in create_response
            and marker in create_text
        ),
        "status_response_contains_server": "open_notebook" in status_text,
        "list_notebooks_response_length": len(list_text),
        "create_note_contains_marker": marker in create_text,
        "error": error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prove Codex app-server can use the first-party Open Notebook MCP server."
    )
    parser.add_argument("--project", default=os.getcwd())
    parser.add_argument("--open-notebook-url", default="http://127.0.0.1:5055")
    parser.add_argument("--open-notebook-password", required=True)
    parser.add_argument("--codex-bin", default=os.getenv("OPEN_NOTEBOOK_CODEX_BIN", "codex"))
    parser.add_argument("--codex-home", default=os.getenv("OPEN_NOTEBOOK_CODEX_HOME"))
    parser.add_argument("--profile", default=os.getenv("OPEN_NOTEBOOK_CODEX_PROFILE", ""))
    parser.add_argument("--model", default=os.getenv("OPEN_NOTEBOOK_CODEX_APP_SERVER_MODEL", "gpt-5.5"))
    parser.add_argument("--sandbox", default="read-only")
    parser.add_argument("--cwd", default="/tmp/open-notebook-codex-open-notebook-mcp-smoke")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    result = run_smoke(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
