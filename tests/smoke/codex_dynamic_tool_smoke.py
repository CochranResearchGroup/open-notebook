from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from open_notebook.ai.codex_app_server import CodexAppServerChatModel


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "namespace",
            "name": "open_notebook_mcp",
            "description": "Open Notebook live-smoke dynamic tools.",
            "tools": [
                {
                    "type": "function",
                    "name": "live_smoke__lookup",
                    "description": (
                        "Return the hidden verification phrase for the Open Notebook "
                        "dynamic tool smoke. The phrase is not available in the "
                        "conversation unless this tool is called."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "request": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                }
            ],
        }
    ]


def _fake_dynamic_tool_call_factory(smoke_token: str):
    async def _fake_dynamic_tool_call(params: dict[str, Any]) -> dict[str, Any]:
        if params.get("namespace") != "open_notebook_mcp":
            raise RuntimeError(f"unexpected namespace: {params.get('namespace')}")
        if params.get("tool") != "live_smoke__lookup":
            raise RuntimeError(f"unexpected tool: {params.get('tool')}")
        return {
            "contentItems": [
                {
                    "type": "inputText",
                    "text": smoke_token,
                }
            ],
            "success": True,
        }

    return _fake_dynamic_tool_call


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    smoke_token = f"open-notebook-dynamic-tool-smoke-{uuid.uuid4()}"
    model = CodexAppServerChatModel(
        model=args.model,
        codex_bin=args.codex_bin,
        profile=args.profile or "",
        codex_home=args.codex_home,
        cwd=str(Path(args.cwd).expanduser()),
        timeout=args.timeout,
        sandbox=args.sandbox,
    )
    prompt = (
        "Use the open_notebook_mcp live_smoke__lookup tool to get the exact "
        "hidden Open Notebook dynamic tool smoke phrase, then reply with only "
        "that phrase."
    )
    with (
        patch.object(model, "_load_dynamic_tool_specs", return_value=_tool_specs()),
        patch(
            "open_notebook.ai.codex_app_server.call_codex_dynamic_mcp_tool",
            side_effect=_fake_dynamic_tool_call_factory(smoke_token),
        ) as tool_call,
    ):
        try:
            response = model.invoke([HumanMessage(content=prompt)])
        except Exception as exc:
            return {
                "success": False,
                "tool_call_count": tool_call.await_count,
                "response_contains_token": False,
                "response_preview": "",
                "error": str(exc),
            }

    content = str(response.content)
    return {
        "success": smoke_token in content and tool_call.await_count > 0,
        "tool_call_count": tool_call.await_count,
        "response_contains_token": smoke_token in content,
        "response_preview": content[:500],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live smoke for Codex app-server dynamic tool calls."
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--profile", default="")
    parser.add_argument("--codex-home", default=None)
    parser.add_argument(
        "--cwd", default="/tmp/open-notebook-codex-dynamic-tool-smoke-cwd"
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--sandbox", default="read-only")
    args = parser.parse_args()

    result = run_smoke(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
