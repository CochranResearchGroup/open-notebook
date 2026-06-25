import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from open_notebook.domain.mcp_server_config import MCPServerConfig


class MCPClientError(RuntimeError):
    pass


MAX_MCP_RESULT_CHARS = int(os.getenv("OPEN_NOTEBOOK_MCP_MAX_RESULT_CHARS", "20000"))


def redacted_mcp_config(config: MCPServerConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": config.name,
        "transport": config.transport,
        "command": config.command,
        "args": config.args,
        "env_keys": sorted(config.env.keys()),
        "url": config.url,
        "auth_env_var": config.auth_env_var,
        "enabled": config.enabled,
        "allowed_tools": config.allowed_tools,
        "disabled_tools": config.disabled_tools,
        "tool_permissions": config.tool_permissions,
        "timeout": config.timeout,
        "concurrency": config.concurrency,
        "metadata": config.metadata,
    }


def _tool_enabled(config: MCPServerConfig, name: str) -> bool:
    if name in config.disabled_tools:
        return False
    if config.allowed_tools and name not in config.allowed_tools:
        return False
    return True


def _tool_permission(config: MCPServerConfig, name: str) -> str:
    if not _tool_enabled(config, name):
        return "disabled"
    return config.tool_permissions.get(name, "read")


def normalize_mcp_tool(config: MCPServerConfig, tool: Any) -> dict[str, Any]:
    name = getattr(tool, "name", "")
    input_schema = getattr(tool, "inputSchema", None)
    if input_schema is None:
        input_schema = getattr(tool, "input_schema", None)
    return {
        "name": name,
        "description": getattr(tool, "description", None),
        "input_schema": input_schema or {},
        "enabled": _tool_enabled(config, name),
        "permission": _tool_permission(config, name),
    }


def _normalize_content_item(item: Any) -> dict[str, Any]:
    item_type = getattr(item, "type", None)
    if hasattr(item, "text"):
        return {"type": item_type or "text", "text": getattr(item, "text")}
    if hasattr(item, "data"):
        return {"type": item_type or "data", "data": getattr(item, "data")}
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return {"type": item_type or "unknown", "value": str(item)}


def normalize_mcp_tool_result(result: Any) -> dict[str, Any]:
    content = [_normalize_content_item(item) for item in getattr(result, "content", [])]
    text = "\n".join(
        str(item.get("text", ""))
        for item in content
        if item.get("type") == "text" and item.get("text") is not None
    )
    truncated = False
    if len(text) > MAX_MCP_RESULT_CHARS:
        text = text[:MAX_MCP_RESULT_CHARS] + "\n[truncated]"
        truncated = True
    return {
        "is_error": bool(getattr(result, "isError", False)),
        "content": content,
        "text": text,
        "truncated": truncated,
    }


def _mcp_headers(config: MCPServerConfig) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    host_header = config.metadata.get("host_header")
    if isinstance(host_header, str) and host_header.strip():
        headers["Host"] = host_header.strip()
    if not config.auth_env_var:
        return headers or None
    token = os.getenv(config.auth_env_var)
    if not token:
        raise MCPClientError(
            f"MCP auth environment variable '{config.auth_env_var}' is not set"
        )
    headers["Authorization"] = f"Bearer {token}"
    return headers


@asynccontextmanager
async def _mcp_session(config: MCPServerConfig):
    if config.transport == "stdio":
        if not config.command:
            raise MCPClientError("stdio MCP server command is required")

        env = os.environ.copy()
        env.update(config.env)
        params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return

    if not config.url:
        raise MCPClientError(f"{config.transport} MCP server URL is required")

    headers = _mcp_headers(config)
    if config.transport == "http":
        async with streamablehttp_client(
            config.url,
            headers=headers,
            timeout=config.timeout,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return

    if config.transport == "sse":
        async with sse_client(
            config.url,
            headers=headers,
            timeout=config.timeout,
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return

    raise MCPClientError(
        f"MCP transport '{config.transport}' is configured but is not supported"
    )


async def list_mcp_tools(config: MCPServerConfig) -> list[dict[str, Any]]:
    try:
        async with asyncio.timeout(config.timeout):
            async with _mcp_session(config) as session:
                result = await session.list_tools()
                return [normalize_mcp_tool(config, tool) for tool in result.tools]
    except TimeoutError as exc:
        raise MCPClientError(
            f"MCP server '{config.name}' timed out after {config.timeout}s"
        ) from exc
    except MCPClientError:
        raise
    except Exception as exc:
        raise MCPClientError(f"MCP server '{config.name}' failed: {exc}") from exc


async def call_mcp_tool(
    config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    allow_mutation: bool = False,
) -> dict[str, Any]:
    if not config.enabled:
        raise MCPClientError(f"MCP server '{config.name}' is disabled")
    if not _tool_enabled(config, tool_name):
        raise MCPClientError(f"MCP tool '{tool_name}' is disabled")

    permission = _tool_permission(config, tool_name)
    if permission == "disabled":
        raise MCPClientError(f"MCP tool '{tool_name}' is disabled")
    if permission == "mutate" and not allow_mutation:
        raise MCPClientError(
            f"MCP tool '{tool_name}' is classified as mutating and cannot be "
            "called from a read-only workflow"
        )
    try:
        async with asyncio.timeout(config.timeout):
            async with _mcp_session(config) as session:
                result = await session.call_tool(tool_name, arguments or {})
                normalized = normalize_mcp_tool_result(result)
                normalized["tool_name"] = tool_name
                normalized["permission"] = permission
                return normalized
    except TimeoutError as exc:
        raise MCPClientError(
            f"MCP tool '{tool_name}' timed out after {config.timeout}s"
        ) from exc
    except MCPClientError:
        raise
    except Exception as exc:
        raise MCPClientError(f"MCP tool '{tool_name}' failed: {exc}") from exc
