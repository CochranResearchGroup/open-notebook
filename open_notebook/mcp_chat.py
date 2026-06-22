import json
from dataclasses import dataclass
from typing import Any

from open_notebook.domain.mcp_server_config import MCPServerConfig
from open_notebook.exceptions import NotFoundError
from open_notebook.mcp_client import MCPClientError, call_mcp_tool


@dataclass(frozen=True)
class MCPChatCommand:
    server_id: str
    tool_name: str
    arguments: dict[str, Any]


def parse_mcp_chat_command(message: str) -> MCPChatCommand | None:
    stripped = message.strip()
    if not stripped.startswith("/mcp "):
        return None

    parts = stripped.split(maxsplit=3)
    if len(parts) < 3:
        raise ValueError("Use /mcp <server-id> <tool-name> <json-args>")

    raw_args = parts[3] if len(parts) == 4 else "{}"
    try:
        arguments = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        raise ValueError(f"MCP arguments must be a JSON object: {exc}") from exc
    if not isinstance(arguments, dict):
        raise ValueError("MCP arguments must be a JSON object")

    return MCPChatCommand(
        server_id=parts[1],
        tool_name=parts[2],
        arguments=arguments,
    )


async def build_mcp_augmented_chat_message(message: str) -> str:
    command = parse_mcp_chat_command(message)
    if command is None:
        return message

    try:
        config = await MCPServerConfig.get(command.server_id)
    except NotFoundError as exc:
        raise MCPClientError(f"MCP server '{command.server_id}' was not found") from exc
    result = await call_mcp_tool(
        config,
        command.tool_name,
        command.arguments,
        allow_mutation=False,
    )
    rendered_result = result.get("text") or json.dumps(result.get("content", []))

    return (
        "The user explicitly requested a read-only MCP tool call.\n\n"
        f"Original request: {message}\n\n"
        f"MCP server: {config.name} ({command.server_id})\n"
        f"MCP tool: {command.tool_name}\n"
        f"MCP arguments: {json.dumps(command.arguments, sort_keys=True)}\n"
        f"MCP result:\n{rendered_result}"
    )
