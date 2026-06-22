from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from open_notebook.domain.mcp_server_config import MCPServerConfig
from open_notebook.domain.mcp_tool_audit import MCPToolAudit, summarize_mcp_arguments
from open_notebook.mcp_chat import (
    build_mcp_augmented_chat_message,
    parse_mcp_chat_command,
)
from open_notebook.mcp_client import (
    call_mcp_tool,
    normalize_mcp_tool,
    normalize_mcp_tool_result,
    redacted_mcp_config,
)


class FakeTool:
    name = "list_files"
    description = "List files"
    inputSchema = {"type": "object"}


def test_redacted_mcp_config_exposes_env_keys_without_values():
    config = MCPServerConfig(
        id="mcp_server_config:local",
        name="Local tools",
        command="local-mcp",
        env={"TOKEN": "secret", "MODE": "readonly"},
    )

    data = redacted_mcp_config(config)

    assert data["env_keys"] == ["MODE", "TOKEN"]
    assert "secret" not in str(data)
    assert "TOKEN" in data["env_keys"]


def test_normalize_tool_applies_allow_and_disable_rules():
    config = MCPServerConfig(
        name="Local tools",
        command="local-mcp",
        allowed_tools=["list_files"],
        disabled_tools=["dangerous_delete"],
        tool_permissions={"list_files": "read"},
    )

    tool = normalize_mcp_tool(config, FakeTool())

    assert tool == {
        "name": "list_files",
        "description": "List files",
        "input_schema": {"type": "object"},
        "enabled": True,
        "permission": "read",
    }


def test_normalize_mcp_tool_result_extracts_text_content():
    result = SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(type="text", text="hello from tool")],
    )

    normalized = normalize_mcp_tool_result(result)

    assert normalized["is_error"] is False
    assert normalized["text"] == "hello from tool"
    assert normalized["content"] == [{"type": "text", "text": "hello from tool"}]


def test_summarize_mcp_arguments_redacts_values():
    summary = summarize_mcp_arguments({"token": "secret", "path": "."})

    assert summary == {"type": "object", "keys": ["path", "token"], "size": 2}
    assert "secret" not in str(summary)


def test_parse_mcp_chat_command_requires_json_object():
    command = parse_mcp_chat_command(
        '/mcp mcp_server_config:local list_files {"path": "."}'
    )

    assert command is not None
    assert command.server_id == "mcp_server_config:local"
    assert command.tool_name == "list_files"
    assert command.arguments == {"path": "."}


def test_parse_mcp_chat_command_ignores_normal_chat():
    assert parse_mcp_chat_command("summarize this notebook") is None


@pytest.mark.asyncio
async def test_call_mcp_tool_rejects_mutating_tool_in_read_only_workflow():
    config = MCPServerConfig(
        name="Local tools",
        command="local-mcp",
        tool_permissions={"delete_file": "mutate"},
    )

    try:
        await call_mcp_tool(config, "delete_file", {}, allow_mutation=False)
    except Exception as exc:
        assert "classified as mutating" in str(exc)
    else:
        raise AssertionError("Expected mutating tool to be rejected")


@pytest.mark.asyncio
async def test_build_mcp_augmented_chat_message_calls_read_only_tool():
    config = MCPServerConfig(
        id="mcp_server_config:local",
        name="Local tools",
        command="local-mcp",
    )

    with (
        patch.object(
            MCPServerConfig,
            "get",
            new_callable=AsyncMock,
            return_value=config,
        ),
        patch(
            "open_notebook.mcp_chat.call_mcp_tool",
            new_callable=AsyncMock,
            return_value={
                "text": "tool result",
                "content": [{"type": "text", "text": "tool result"}],
                "permission": "read",
                "is_error": False,
            },
        ) as call_tool,
    ):
        message = await build_mcp_augmented_chat_message(
            '/mcp mcp_server_config:local list_files {"path": "."}'
        )

    assert "MCP result:\ntool result" in message
    assert "read-only MCP tool call" in message
    call_tool.assert_awaited_once_with(config, "list_files", {"path": "."}, allow_mutation=False)


def test_create_mcp_server_endpoint_redacts_env_values():
    client = TestClient(app)

    async def fake_save(self):
        self.id = "mcp_server_config:created"

    with patch.object(MCPServerConfig, "save", new=fake_save):
        response = client.post(
            "/api/mcp/servers",
            json={
                "name": "Local tools",
                "command": "local-mcp",
                "args": ["--stdio"],
                "env": {"TOKEN": "secret"},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "mcp_server_config:created"
    assert data["env"] == {}
    assert data["env_keys"] == ["TOKEN"]
    assert "secret" not in str(data)


def test_test_mcp_server_endpoint_lists_tools():
    client = TestClient(app)
    config = MCPServerConfig(
        id="mcp_server_config:local",
        name="Local tools",
        command="local-mcp",
    )

    with (
        patch.object(
            MCPServerConfig,
            "get",
            new_callable=AsyncMock,
            return_value=config,
        ),
        patch(
            "api.routers.mcp_servers.list_mcp_tools",
            new_callable=AsyncMock,
            return_value=[
                {
                    "name": "list_files",
                    "description": "List files",
                    "input_schema": {"type": "object"},
                    "enabled": True,
                    "permission": "read",
                }
            ],
        ),
    ):
        response = client.post("/api/mcp/servers/mcp_server_config:local/test")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["tools"][0]["name"] == "list_files"


def test_call_mcp_tool_endpoint_returns_tool_result():
    client = TestClient(app)
    config = MCPServerConfig(
        id="mcp_server_config:local",
        name="Local tools",
        command="local-mcp",
    )

    with (
        patch.object(
            MCPServerConfig,
            "get",
            new_callable=AsyncMock,
            return_value=config,
        ),
        patch.object(MCPToolAudit, "save", new_callable=AsyncMock) as save_audit,
        patch(
            "api.routers.mcp_servers.call_mcp_tool",
            new_callable=AsyncMock,
            return_value={
                "tool_name": "list_files",
                "permission": "read",
                "is_error": False,
                "content": [{"type": "text", "text": "files"}],
                "text": "files",
                "truncated": False,
            },
        ) as call_tool_mock,
    ):
        response = client.post(
            "/api/mcp/tool-call",
            json={
                "server_id": "mcp_server_config:local",
                "tool_name": "list_files",
                "arguments": {"path": "."},
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["text"] == "files"
    save_audit.assert_awaited_once()
    call_tool_mock.assert_awaited_once_with(
        config,
        "list_files",
        {"path": "."},
        allow_mutation=False,
    )


def test_list_mcp_tool_audit_endpoint_returns_redacted_records():
    client = TestClient(app)
    audit = MCPToolAudit(
        id="mcp_tool_audit:one",
        server_id="mcp_server_config:local",
        server_name="Local tools",
        tool_name="list_files",
        permission="read",
        caller="api",
        status="success",
        argument_summary={"type": "object", "keys": ["path"], "size": 1},
        result_summary={"text_length": 5},
    )

    with patch.object(
        MCPToolAudit,
        "get_all",
        new_callable=AsyncMock,
        return_value=[audit],
    ):
        response = client.get("/api/mcp/tool-audit")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["tool_name"] == "list_files"
    assert data[0]["argument_summary"] == {
        "type": "object",
        "keys": ["path"],
        "size": 1,
    }
