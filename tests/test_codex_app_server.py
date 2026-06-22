import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from api.main import app
from open_notebook.ai.codex_app_server import (
    CodexAppServerChatModel,
    _CodexAppServerClient,
)
from open_notebook.ai.codex_mcp import (
    build_codex_dynamic_tool_specs,
    build_codex_mcp_config_overrides,
    build_codex_mcp_launch_config,
    build_codex_mcp_profile_response,
    materialize_codex_mcp_profile,
)
from open_notebook.ai.models import Model, ModelManager
from open_notebook.domain.codex_mcp_profile import CodexMCPProfile
from open_notebook.domain.mcp_server_config import MCPServerConfig


class FakeCodexClient:
    instances = []

    def __init__(self, codex_bin, profile, codex_home, config_overrides=None):
        self.codex_bin = codex_bin
        self.profile = profile
        self.codex_home = codex_home
        self.config_overrides = config_overrides or []
        self.sent = []
        self.closed = False
        FakeCodexClient.instances.append(self)

    def send(self, method, params=None):
        self.sent.append((method, params or {}))
        return len(self.sent)

    def wait_for_response(self, request_id, timeout):
        method, _ = self.sent[request_id - 1]
        if method == "initialize":
            return {"id": request_id, "result": {}}
        if method == "thread/start":
            return {"id": request_id, "result": {"thread": {"id": "thread-1"}}}
        if method == "turn/start":
            return {"id": request_id, "result": {"turn": {"id": "turn-1"}}}
        return {"id": request_id, "result": {}}

    def wait_for_completion(self, timeout):
        return "Codex answer"

    def close(self):
        self.closed = True


def test_codex_app_server_chat_model_invokes_app_server_protocol(tmp_path):
    FakeCodexClient.instances = []
    model = CodexAppServerChatModel(
        model="gpt-5.5",
        codex_bin="codex",
        cwd=str(tmp_path),
        timeout=30,
    )
    model._client_class = FakeCodexClient

    with patch(
        "open_notebook.ai.codex_app_server.materialize_codex_mcp_profile",
        new_callable=AsyncMock,
        return_value={"enabled": False, "profile_name": None},
    ), patch(
        "open_notebook.ai.codex_app_server.build_codex_mcp_launch_config",
        new_callable=AsyncMock,
        return_value={
            "enabled": False,
            "config_overrides": [],
            "codex_home": None,
            "cleanup_path": None,
        },
    ):
        response = model.invoke([HumanMessage(content="Say hi")])

    assert response.content == "Codex answer"
    client = FakeCodexClient.instances[0]
    assert [method for method, _ in client.sent] == [
        "initialize",
        "thread/start",
        "turn/start",
    ]
    assert client.sent[1][1]["model"] == "gpt-5.5"
    assert client.sent[1][1]["sandbox"] == "read-only"
    assert client.sent[2][1]["threadId"] == "thread-1"
    assert "Say hi" in client.sent[2][1]["input"][0]["text"]
    assert client.closed is True


def test_codex_app_server_chat_model_uses_materialized_mcp_profile(tmp_path):
    FakeCodexClient.instances = []
    model = CodexAppServerChatModel(
        model="gpt-5.5",
        codex_bin="codex",
        profile="base-profile",
        codex_home=str(tmp_path / "codex-home"),
        cwd=str(tmp_path),
        timeout=30,
    )
    model._client_class = FakeCodexClient

    with patch(
        "open_notebook.ai.codex_app_server.build_codex_mcp_launch_config",
        new_callable=AsyncMock,
        return_value={
            "enabled": False,
            "config_overrides": [],
            "codex_home": str(tmp_path / "codex-home"),
            "cleanup_path": None,
        },
    ), patch(
        "open_notebook.ai.codex_app_server.materialize_codex_mcp_profile",
        new_callable=AsyncMock,
        return_value={
            "enabled": True,
            "profile_name": "open-notebook-mcp",
            "path": str(tmp_path / "codex-home/open-notebook-mcp.config.toml"),
            "server_names": ["read-tools-read"],
        },
    ) as materialize:
        response = model.invoke([HumanMessage(content="Say hi")])

    assert response.content == "Codex answer"
    client = FakeCodexClient.instances[0]
    assert client.profile == "open-notebook-mcp"
    assert client.codex_home == str(tmp_path / "codex-home")
    materialize.assert_awaited_once_with(
        codex_home=str(tmp_path / "codex-home"),
        profile_name="open-notebook-mcp",
    )


def test_codex_app_server_chat_model_uses_mcp_config_overrides(tmp_path):
    FakeCodexClient.instances = []
    model = CodexAppServerChatModel(
        model="gpt-5.5",
        codex_bin="codex",
        profile="base-profile",
        cwd=str(tmp_path),
        timeout=30,
    )
    model._client_class = FakeCodexClient
    overrides = [
        'mcp_servers.read-tools.command="read-mcp"',
        'mcp_servers.read-tools.args=["--stdio"]',
    ]

    with patch(
        "open_notebook.ai.codex_app_server.build_codex_mcp_launch_config",
        new_callable=AsyncMock,
        return_value={
            "enabled": True,
            "config_overrides": overrides,
            "codex_home": None,
            "cleanup_path": None,
        },
    ), patch(
        "open_notebook.ai.codex_app_server.materialize_codex_mcp_profile",
        new_callable=AsyncMock,
    ) as materialize:
        response = model.invoke([HumanMessage(content="Say hi")])

    assert response.content == "Codex answer"
    client = FakeCodexClient.instances[0]
    assert client.profile == "base-profile"
    assert client.config_overrides == overrides
    materialize.assert_not_awaited()


def test_codex_app_server_chat_model_advertises_dynamic_tools(tmp_path):
    FakeCodexClient.instances = []
    tool_specs = [
        {
            "type": "namespace",
            "name": "open_notebook_mcp",
            "description": "Read-only tools",
            "tools": [
                {
                    "type": "function",
                    "name": "local__list",
                    "description": "List",
                    "inputSchema": {"type": "object"},
                }
            ],
        }
    ]
    model = CodexAppServerChatModel(
        model="gpt-5.5",
        codex_bin="codex",
        cwd=str(tmp_path),
        timeout=30,
    )
    model._client_class = FakeCodexClient

    with (
        patch.object(model, "_load_dynamic_tool_specs", return_value=tool_specs),
        patch(
            "open_notebook.ai.codex_app_server.materialize_codex_mcp_profile",
            new_callable=AsyncMock,
            return_value={"enabled": False, "profile_name": None},
        ),
        patch(
            "open_notebook.ai.codex_app_server.build_codex_mcp_config_overrides",
            new_callable=AsyncMock,
            return_value={"enabled": False, "overrides": []},
        ),
        patch(
            "open_notebook.ai.codex_app_server.build_codex_mcp_launch_config",
            new_callable=AsyncMock,
            return_value={
                "enabled": False,
                "config_overrides": [],
                "codex_home": None,
                "cleanup_path": None,
            },
        ),
    ):
        response = model.invoke([HumanMessage(content="Say hi")])

    assert response.content == "Codex answer"
    thread_params = FakeCodexClient.instances[0].sent[1][1]
    assert thread_params["config"]["experimental_dynamic_tools"] == tool_specs
    assert "open_notebook_mcp" in thread_params["developerInstructions"]


def test_codex_app_server_client_handles_dynamic_tool_call_request():
    client = object.__new__(_CodexAppServerClient)
    client.proc = None
    client.next_id = 1
    client.selector = None
    stdin = io.StringIO()

    client.proc = SimpleNamespace(stdin=stdin)

    async def fake_call(params):
        assert params["tool"] == "local__list"
        return {
            "contentItems": [{"type": "inputText", "text": "tool output"}],
            "success": True,
        }

    with patch(
        "open_notebook.ai.codex_app_server.call_codex_dynamic_mcp_tool",
        side_effect=fake_call,
    ):
        client._reply_to_server_request(
            {
                "id": 7,
                "method": "item/tool/call",
                "params": {
                    "namespace": "open_notebook_mcp",
                    "tool": "local__list",
                    "arguments": {},
                },
            }
        )

    response = json.loads(stdin.getvalue())
    assert response == {
        "id": 7,
        "result": {
            "contentItems": [{"type": "inputText", "text": "tool output"}],
            "success": True,
        },
    }


def test_codex_app_server_client_declines_mcp_elicitation_request():
    client = object.__new__(_CodexAppServerClient)
    stdin = io.StringIO()
    client.proc = SimpleNamespace(stdin=stdin)

    client._reply_to_server_request(
        {
            "id": 8,
            "method": "mcpServer/elicitation/request",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "serverName": "open_notebook_mcp",
                "mode": "form",
                "_meta": None,
                "message": "Need more input",
                "requestedSchema": {"type": "object", "properties": {}},
            },
        }
    )

    response = json.loads(stdin.getvalue())
    assert response == {
        "id": 8,
        "result": {
            "action": "decline",
            "content": None,
            "_meta": None,
        },
    }


def test_codex_app_server_client_accepts_mcp_tool_call_elicitation_request():
    client = object.__new__(_CodexAppServerClient)
    stdin = io.StringIO()
    client.proc = SimpleNamespace(stdin=stdin)

    client._reply_to_server_request(
        {
            "id": 10,
            "method": "mcpServer/elicitation/request",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "serverName": "open_notebook_mcp",
                "mode": "form",
                "_meta": {"codex_approval_kind": "mcp_tool_call"},
                "message": 'Allow MCP server to run tool "list"?',
                "requestedSchema": {"type": "object", "properties": {}},
            },
        }
    )

    response = json.loads(stdin.getvalue())
    assert response == {
        "id": 10,
        "result": {
            "action": "accept",
            "content": {},
            "_meta": None,
        },
    }


def test_codex_app_server_client_grants_turn_scoped_permission_request():
    client = object.__new__(_CodexAppServerClient)
    stdin = io.StringIO()
    client.proc = SimpleNamespace(stdin=stdin)

    client._reply_to_server_request(
        {
            "id": 9,
            "method": "item/permissions/requestApproval",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "item-1",
                "environmentId": None,
                "startedAtMs": 0,
                "cwd": "/tmp/open-notebook",
                "reason": "MCP tool call",
                "permissions": {
                    "network": {"enabled": True},
                    "fileSystem": None,
                },
            },
        }
    )

    response = json.loads(stdin.getvalue())
    assert response == {
        "id": 9,
        "result": {
            "permissions": {"network": {"enabled": True}},
            "scope": "turn",
            "strictAutoReview": False,
        },
    }


@pytest.mark.asyncio
async def test_model_manager_creates_codex_app_server_language_model():
    manager = ModelManager()
    db_model = Model(
        id="model:codex",
        name="gpt-5.5",
        provider="codex_app_server",
        type="language",
    )

    with patch.object(Model, "get", new_callable=AsyncMock, return_value=db_model):
        model = await manager.get_model("model:codex")

    langchain_model = model.to_langchain()
    assert isinstance(langchain_model, CodexAppServerChatModel)
    assert langchain_model.model == "gpt-5.5"


def test_codex_app_server_status_endpoint_reports_safe_runtime_metadata():
    client = TestClient(app)
    db_model = Model(
        id="model:codex",
        name="gpt-5.5",
        provider="codex_app_server",
        type="language",
    )
    status = {
        "provider": "codex_app_server",
        "enabled": True,
        "available": True,
        "cli_found": True,
        "help_ok": True,
        "help_error": None,
        "codex_bin": "codex",
        "codex_bin_path": "/usr/local/bin/codex",
        "profile": "",
        "codex_home_configured": True,
        "codex_home_label": "configured (.../codex-home)",
        "model": "gpt-5.5",
        "cwd": "/tmp/open-notebook-codex-app-server-cwd",
        "effort": "medium",
        "sandbox": "read-only",
        "timeout": 900,
    }

    with (
        patch("api.routers.models.codex_app_server_status", return_value=status),
        patch(
            "api.routers.models._get_codex_registered_model",
            new_callable=AsyncMock,
            return_value=db_model,
        ),
        patch(
            "api.routers.models._codex_default_slots",
            new_callable=AsyncMock,
            return_value={
                "default_chat_model": True,
                "default_transformation_model": True,
                "large_context_model": True,
                "default_tools_model": True,
            },
        ),
    ):
        response = client.get("/api/models/codex-app-server/status")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["registered_model_id"] == "model:codex"
    assert data["codex_home_label"] == "configured (.../codex-home)"
    assert "auth" not in str(data).lower()


def test_sync_codex_app_server_model_endpoint():
    client = TestClient(app)

    with patch(
        "api.routers.models.sync_provider_models",
        new_callable=AsyncMock,
        return_value=(1, 1, 0),
    ) as sync:
        response = client.post("/api/models/codex-app-server/sync")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "codex_app_server",
        "discovered": 1,
        "new": 1,
        "existing": 0,
    }
    sync.assert_awaited_once_with("codex_app_server", auto_register=True)


def test_set_codex_app_server_language_defaults_endpoint():
    client = TestClient(app)
    db_model = Model(
        id="model:codex",
        name="gpt-5.5",
        provider="codex_app_server",
        type="language",
    )

    class FakeDefaults:
        default_chat_model = None
        default_transformation_model = None
        large_context_model = None
        default_tools_model = None

        def __init__(self):
            self.update = AsyncMock()

    defaults = FakeDefaults()

    with (
        patch(
            "api.routers.models._ensure_codex_registered_model",
            new_callable=AsyncMock,
            return_value=db_model,
        ),
        patch(
            "api.routers.models.DefaultModels.get_instance",
            new_callable=AsyncMock,
            return_value=defaults,
        ),
    ):
        response = client.post("/api/models/codex-app-server/set-language-defaults")

    assert response.status_code == 200
    assert response.json()["model_id"] == "model:codex"
    assert defaults.default_chat_model == "model:codex"
    assert defaults.default_transformation_model == "model:codex"
    assert defaults.large_context_model == "model:codex"
    assert defaults.default_tools_model == "model:codex"
    defaults.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_codex_mcp_profile_read_only_snippet_omits_mutating_servers():
    profile = CodexMCPProfile(mode="read_only")
    read_server = MCPServerConfig(
        id="mcp_server_config:read",
        name="Read Tools",
        command="read-mcp",
        args=["--stdio"],
        env={"TOKEN": "secret"},
        tool_permissions={"list": "read"},
    )
    mutating_server = MCPServerConfig(
        id="mcp_server_config:write",
        name="Write Tools",
        command="write-mcp",
        tool_permissions={"delete": "mutate"},
    )

    with patch.object(
        MCPServerConfig,
        "get_all",
        new_callable=AsyncMock,
        return_value=[read_server, mutating_server],
    ):
        response = await build_codex_mcp_profile_response(profile)

    assert "read-mcp" in response["codex_config_toml"]
    assert "write-mcp" not in response["codex_config_toml"]
    assert "secret" not in response["codex_config_toml"]
    assert '${TOKEN}' in response["codex_config_toml"]
    assert response["warnings"]


@pytest.mark.asyncio
async def test_codex_dynamic_tool_specs_include_enabled_read_tools():
    profile = CodexMCPProfile(mode="selected", selected_server_ids=["mcp_server_config:read"])
    read_server = MCPServerConfig(
        id="mcp_server_config:read",
        name="Read Tools",
        command="read-mcp",
        tool_permissions={"list": "read"},
    )

    with (
        patch.object(
            MCPServerConfig,
            "get_all",
            new_callable=AsyncMock,
            return_value=[read_server],
        ),
        patch(
            "open_notebook.ai.codex_mcp.list_mcp_tools",
            new_callable=AsyncMock,
            return_value=[
                {
                    "name": "list",
                    "description": "List records",
                    "input_schema": {"type": "object"},
                    "enabled": True,
                    "permission": "read",
                },
                {
                    "name": "delete",
                    "description": "Delete records",
                    "input_schema": {"type": "object"},
                    "enabled": True,
                    "permission": "mutate",
                },
            ],
        ),
    ):
        specs = await build_codex_dynamic_tool_specs(profile)

    assert specs[0]["name"] == "open_notebook_mcp"
    tool_names = [tool["name"] for tool in specs[0]["tools"]]
    assert tool_names == ["read-tools__list"]


@pytest.mark.asyncio
async def test_materialize_codex_mcp_profile_writes_managed_profile(tmp_path):
    profile = CodexMCPProfile(mode="selected", selected_server_ids=["mcp_server_config:read"])
    server = MCPServerConfig(
        id="mcp_server_config:read",
        name="Read Tools",
        command="read-mcp",
        args=["--stdio"],
        env={"TOKEN": "secret-value"},
        tool_permissions={"list": "read"},
    )

    with patch.object(
        MCPServerConfig,
        "get_all",
        new_callable=AsyncMock,
        return_value=[server],
    ):
        result = await materialize_codex_mcp_profile(
            codex_home=str(tmp_path),
            profile=profile,
            profile_name="open-notebook-mcp",
        )

    profile_path = tmp_path / "open-notebook-mcp.config.toml"
    assert result["enabled"] is True
    assert result["profile_name"] == "open-notebook-mcp"
    assert result["path"] == str(profile_path)
    text = profile_path.read_text()
    assert "[mcp_servers.read-tools]" in text
    assert 'command = "read-mcp"' in text
    assert 'args = ["--stdio"]' in text
    assert 'TOKEN = "secret-value"' in text
    assert profile_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_codex_mcp_config_overrides_skip_env_servers():
    profile = CodexMCPProfile(
        mode="selected",
        selected_server_ids=["mcp_server_config:read", "mcp_server_config:secret"],
    )
    read_server = MCPServerConfig(
        id="mcp_server_config:read",
        name="Read Tools",
        command="read-mcp",
        args=["--stdio"],
        tool_permissions={"list": "read"},
    )
    secret_server = MCPServerConfig(
        id="mcp_server_config:secret",
        name="Secret Tools",
        command="secret-mcp",
        env={"TOKEN": "secret-value"},
        tool_permissions={"list": "read"},
    )

    with patch.object(
        MCPServerConfig,
        "get_all",
        new_callable=AsyncMock,
        return_value=[read_server, secret_server],
    ):
        result = await build_codex_mcp_config_overrides(profile)

    assert result["enabled"] is True
    assert result["server_names"] == ["read-tools"]
    assert result["skipped_env_servers"] == ["Secret Tools"]
    assert result["overrides"] == [
        'mcp_servers.read-tools.command="read-mcp"',
        'mcp_servers.read-tools.args=["--stdio"]',
    ]
    assert "secret-value" not in str(result)


@pytest.mark.asyncio
async def test_codex_mcp_launch_config_writes_temp_home_for_env_servers(tmp_path):
    base_home = tmp_path / "base-codex-home"
    base_home.mkdir()
    auth_path = base_home / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")
    auth_path.chmod(0o600)
    profile = CodexMCPProfile(
        mode="selected",
        selected_server_ids=["mcp_server_config:secret"],
    )
    secret_server = MCPServerConfig(
        id="mcp_server_config:secret",
        name="Secret Tools",
        command="secret-mcp",
        args=["--stdio"],
        env={"TOKEN": "secret-value"},
        tool_permissions={"list": "read"},
    )

    with patch.object(
        MCPServerConfig,
        "get_all",
        new_callable=AsyncMock,
        return_value=[secret_server],
    ):
        result = await build_codex_mcp_launch_config(
            codex_home=str(base_home),
            profile=profile,
        )

    runtime_home = Path(result["codex_home"])
    try:
        assert result["enabled"] is True
        assert result["config_overrides"] == []
        assert result["cleanup_path"] == str(runtime_home)
        assert result["server_names"] == ["secret-tools"]
        assert result["env_server_names"] == ["secret-tools"]
        assert runtime_home.stat().st_mode & 0o777 == 0o700
        assert (runtime_home / "auth.json").is_symlink()
        assert (runtime_home / "auth.json").resolve() == auth_path
        config_path = runtime_home / "config.toml"
        text = config_path.read_text()
        assert "[mcp_servers.secret-tools]" in text
        assert 'command = "secret-mcp"' in text
        assert 'args = ["--stdio"]' in text
        assert 'TOKEN = "secret-value"' in text
        assert config_path.stat().st_mode & 0o777 == 0o600
    finally:
        import shutil

        shutil.rmtree(runtime_home, ignore_errors=True)


def test_get_codex_mcp_profile_endpoint():
    client = TestClient(app)
    profile = CodexMCPProfile(mode="none")

    with (
        patch(
            "api.routers.models.CodexMCPProfile.get_instance",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "api.routers.models.build_codex_mcp_profile_response",
            new_callable=AsyncMock,
            return_value={
                "mode": "none",
                "selected_server_ids": [],
                "custom_profile_name": None,
                "available_servers": [],
                "codex_config_toml": "",
                "warnings": [],
            },
        ),
    ):
        response = client.get("/api/models/codex-app-server/mcp-profile")

    assert response.status_code == 200
    assert response.json()["mode"] == "none"


def test_update_codex_mcp_profile_endpoint():
    client = TestClient(app)

    class FakeProfile:
        mode = "none"
        selected_server_ids = []
        custom_profile_name = None

        def __init__(self):
            self.update = AsyncMock()

    profile = FakeProfile()

    with (
        patch(
            "api.routers.models.CodexMCPProfile.get_instance",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "api.routers.models.build_codex_mcp_profile_response",
            new_callable=AsyncMock,
            return_value={
                "mode": "selected",
                "selected_server_ids": ["mcp_server_config:read"],
                "custom_profile_name": None,
                "available_servers": [],
                "codex_config_toml": "",
                "warnings": [],
            },
        ),
    ):
        response = client.put(
            "/api/models/codex-app-server/mcp-profile",
            json={
                "mode": "selected",
                "selected_server_ids": ["mcp_server_config:read"],
            },
        )

    assert response.status_code == 200
    assert response.json()["mode"] == "selected"
    assert profile.mode == "selected"
    assert profile.selected_server_ids == ["mcp_server_config:read"]
    profile.update.assert_awaited_once()
