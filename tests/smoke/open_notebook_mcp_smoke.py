from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _content_text(result: Any) -> str:
    content = getattr(result, "content", [])
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(json.dumps(_jsonable(item), sort_keys=True))
    return "\n".join(parts)


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    command = args.command or shutil.which("uv") or sys.executable
    command_args = (
        ["run", "--project", args.project, "open-notebook-mcp"]
        if command.endswith("uv")
        else ["-m", "open_notebook.mcp_server"]
    )
    env = os.environ.copy()
    env["OPEN_NOTEBOOK_URL"] = args.open_notebook_url
    if args.open_notebook_password:
        env["OPEN_NOTEBOOK_PASSWORD"] = args.open_notebook_password

    params = StdioServerParameters(command=command, args=command_args, env=env)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = sorted(tool.name for tool in tools.tools)

            list_result = await session.call_tool("list_notebooks", {})
            create_result = await session.call_tool(
                "create_note",
                {
                    "content": args.note_content,
                    "title": "Open Notebook MCP smoke",
                    "note_type": "human",
                },
            )

    list_text = _content_text(list_result)
    create_text = _content_text(create_result)
    return {
        "success": (
            "list_notebooks" in tool_names
            and "create_note" in tool_names
            and not getattr(list_result, "isError", False)
            and not getattr(create_result, "isError", False)
            and args.note_content in create_text
        ),
        "tool_names": tool_names,
        "list_notebooks_is_error": getattr(list_result, "isError", False),
        "create_note_is_error": getattr(create_result, "isError", False),
        "list_notebooks_text_length": len(list_text),
        "create_note_contains_marker": args.note_content in create_text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test the first-party Open Notebook MCP server over stdio."
    )
    parser.add_argument("--project", default=os.getcwd())
    parser.add_argument("--command", default=None)
    parser.add_argument(
        "--open-notebook-url",
        default=os.getenv("OPEN_NOTEBOOK_URL", "http://127.0.0.1:5055"),
    )
    parser.add_argument(
        "--open-notebook-password",
        default=os.getenv("OPEN_NOTEBOOK_PASSWORD", ""),
    )
    parser.add_argument(
        "--note-content",
        default="open-notebook-mcp-smoke-note",
    )
    args = parser.parse_args()

    result = asyncio.run(run_smoke(args))
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
