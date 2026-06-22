import re
import tempfile
from pathlib import Path
from typing import Any

from open_notebook.domain.codex_mcp_profile import CodexMCPProfile
from open_notebook.domain.mcp_server_config import MCPServerConfig
from open_notebook.domain.mcp_tool_audit import (
    MCPToolAudit,
    summarize_mcp_arguments,
)
from open_notebook.mcp_client import MCPClientError, call_mcp_tool, list_mcp_tools

CODEX_DYNAMIC_MCP_NAMESPACE = "open_notebook_mcp"
DEFAULT_CODEX_MCP_PROFILE_NAME = "open-notebook-mcp"


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _codex_server_name(config: MCPServerConfig) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", config.name.strip().lower()).strip("-")
    if not base:
        base = "mcp-server"
    if config.id:
        suffix = config.id.split(":", 1)[-1].replace("⟩", "").replace("⟨", "")
        suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", suffix).strip("-")
        if suffix and suffix not in base:
            base = f"{base}-{suffix}"
    return base[:80]


def _server_has_mutating_classification(config: MCPServerConfig) -> bool:
    return any(permission == "mutate" for permission in config.tool_permissions.values())


def _server_to_summary(config: MCPServerConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": config.name,
        "transport": config.transport,
        "enabled": config.enabled,
        "codex_native_supported": config.transport == "stdio" and config.enabled,
        "has_mutating_classification": _server_has_mutating_classification(config),
        "env_keys": sorted(config.env.keys()),
    }


def _server_to_codex_toml(
    config: MCPServerConfig,
    *,
    redact_env_values: bool = True,
) -> str:
    name = _codex_server_name(config)
    lines = [
        f"[mcp_servers.{name}]",
        f"command = {_toml_string(config.command or '')}",
    ]
    if config.args:
        lines.append(f"args = {_toml_array(config.args)}")
    if config.env:
        lines.append(f"[mcp_servers.{name}.env]")
        for key in sorted(config.env):
            value = "${" + key + "}" if redact_env_values else config.env[key]
            lines.append(f"{key} = {_toml_string(value)}")
    return "\n".join(lines)


def _dynamic_tool_name(config: MCPServerConfig, tool_name: str) -> str:
    return f"{_codex_server_name(config)}__{tool_name}"


def _selected_servers(
    profile: CodexMCPProfile,
    servers: list[MCPServerConfig],
) -> list[MCPServerConfig]:
    stdio_enabled = [
        server
        for server in servers
        if server.enabled and server.transport == "stdio" and server.command
    ]
    if profile.mode == "none":
        return []
    if profile.mode == "read_only":
        return [
            server
            for server in stdio_enabled
            if not _server_has_mutating_classification(server)
        ]
    if profile.mode == "selected":
        selected = set(profile.selected_server_ids)
        return [server for server in stdio_enabled if server.id in selected]
    return []


async def build_codex_mcp_profile_response(
    profile: CodexMCPProfile | None = None,
) -> dict[str, Any]:
    profile = profile or await CodexMCPProfile.get_instance()  # type: ignore[assignment]
    servers = await MCPServerConfig.get_all(order_by="name asc")
    selected = _selected_servers(profile, servers)
    snippet = "\n\n".join(
        _server_to_codex_toml(server, redact_env_values=True)
        for server in selected
    )
    warnings: list[str] = []

    if profile.mode in {"read_only", "selected"} and selected:
        warnings.append(
            "Codex-native MCP config connects directly to MCP servers and does "
            "not enforce Open Notebook per-tool disabled or mutate settings. "
            "Use only trusted read-only MCP servers here."
        )
    if profile.mode == "selected":
        selected_ids = set(profile.selected_server_ids)
        missing = sorted(
            server_id
            for server_id in selected_ids
            if not any(server.id == server_id for server in servers)
        )
        if missing:
            warnings.append(f"Selected MCP servers were not found: {', '.join(missing)}")
    if profile.mode == "custom":
        warnings.append(
            "Custom profile mode expects Codex to be configured outside Open Notebook."
        )

    return {
        "mode": profile.mode,
        "selected_server_ids": profile.selected_server_ids,
        "custom_profile_name": profile.custom_profile_name,
        "available_servers": [_server_to_summary(server) for server in servers],
        "codex_config_toml": snippet,
        "warnings": warnings,
    }


async def materialize_codex_mcp_profile(
    *,
    codex_home: str | None = None,
    profile: CodexMCPProfile | None = None,
    profile_name: str = DEFAULT_CODEX_MCP_PROFILE_NAME,
) -> dict[str, Any]:
    profile = profile or await CodexMCPProfile.get_instance()  # type: ignore[assignment]
    if profile.mode not in {"read_only", "selected"}:
        return {
            "enabled": False,
            "profile_name": None,
            "path": None,
            "server_names": [],
        }

    servers = await MCPServerConfig.get_all(order_by="name asc")
    selected = _selected_servers(profile, servers)
    if not selected:
        return {
            "enabled": False,
            "profile_name": None,
            "path": None,
            "server_names": [],
        }

    codex_home_path = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    codex_home_path.mkdir(parents=True, exist_ok=True)
    safe_profile_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", profile_name).strip(".-")
    if not safe_profile_name:
        safe_profile_name = DEFAULT_CODEX_MCP_PROFILE_NAME
    profile_path = codex_home_path / f"{safe_profile_name}.config.toml"
    server_names = [_codex_server_name(server) for server in selected]
    content = "\n\n".join(
        _server_to_codex_toml(server, redact_env_values=False)
        for server in selected
    )
    content = (
        "# Managed by Open Notebook. Do not store this file in the repo.\n"
        "# It is regenerated from the Codex App Server MCP profile UX.\n\n"
        f"{content}\n"
    )

    tmp_path = profile_path.with_suffix(profile_path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.chmod(0o600)
    tmp_path.replace(profile_path)
    profile_path.chmod(0o600)

    return {
        "enabled": True,
        "profile_name": safe_profile_name,
        "path": str(profile_path),
        "server_names": server_names,
    }


async def build_codex_mcp_config_overrides(
    profile: CodexMCPProfile | None = None,
) -> dict[str, Any]:
    profile = profile or await CodexMCPProfile.get_instance()  # type: ignore[assignment]
    if profile.mode not in {"read_only", "selected"}:
        return {
            "enabled": False,
            "overrides": [],
            "server_names": [],
            "skipped_env_servers": [],
        }

    servers = await MCPServerConfig.get_all(order_by="name asc")
    selected = _selected_servers(profile, servers)
    overrides: list[str] = []
    server_names: list[str] = []
    skipped_env_servers: list[str] = []

    for server in selected:
        if server.env:
            skipped_env_servers.append(server.name)
            continue
        name = _codex_server_name(server)
        server_names.append(name)
        overrides.append(f"mcp_servers.{name}.command={_toml_string(server.command or '')}")
        if server.args:
            overrides.append(f"mcp_servers.{name}.args={_toml_array(server.args)}")
        if server.url:
            overrides.append(f"mcp_servers.{name}.url={_toml_string(server.url)}")

    return {
        "enabled": bool(overrides),
        "overrides": overrides,
        "server_names": server_names,
        "skipped_env_servers": skipped_env_servers,
    }


def _base_codex_home(codex_home: str | None = None) -> Path:
    return Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"


def _link_codex_auth_files(source_home: Path, target_home: Path) -> None:
    for source_path in source_home.glob("auth.json*"):
        target_path = target_home / source_path.name
        if target_path.exists() or target_path.is_symlink():
            continue
        target_path.symlink_to(source_path)


def _write_managed_codex_config(path: Path, selected: list[MCPServerConfig]) -> None:
    content = "\n\n".join(
        _server_to_codex_toml(server, redact_env_values=False)
        for server in selected
    )
    content = (
        "# Managed by Open Notebook for one Codex app-server launch.\n"
        "# This file may contain MCP environment values and must stay private.\n\n"
        f"{content}\n"
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


async def build_codex_mcp_launch_config(
    *,
    codex_home: str | None = None,
    profile: CodexMCPProfile | None = None,
) -> dict[str, Any]:
    profile = profile or await CodexMCPProfile.get_instance()  # type: ignore[assignment]
    if profile.mode not in {"read_only", "selected"}:
        return {
            "enabled": False,
            "config_overrides": [],
            "codex_home": codex_home,
            "cleanup_path": None,
            "server_names": [],
            "env_server_names": [],
        }

    servers = await MCPServerConfig.get_all(order_by="name asc")
    selected = _selected_servers(profile, servers)
    if not selected:
        return {
            "enabled": False,
            "config_overrides": [],
            "codex_home": codex_home,
            "cleanup_path": None,
            "server_names": [],
            "env_server_names": [],
        }

    env_servers = [server for server in selected if server.env]
    if not env_servers:
        overrides_result = await build_codex_mcp_config_overrides(profile)
        return {
            "enabled": overrides_result["enabled"],
            "config_overrides": overrides_result["overrides"],
            "codex_home": codex_home,
            "cleanup_path": None,
            "server_names": overrides_result["server_names"],
            "env_server_names": [],
        }

    base_home = _base_codex_home(codex_home)
    runtime_home = Path(
        tempfile.mkdtemp(prefix="open-notebook-codex-mcp-", dir="/tmp")
    )
    runtime_home.chmod(0o700)
    _link_codex_auth_files(base_home, runtime_home)
    _write_managed_codex_config(runtime_home / "config.toml", selected)

    return {
        "enabled": True,
        "config_overrides": [],
        "codex_home": str(runtime_home),
        "cleanup_path": str(runtime_home),
        "server_names": [_codex_server_name(server) for server in selected],
        "env_server_names": [_codex_server_name(server) for server in env_servers],
    }


async def build_codex_dynamic_tool_specs(
    profile: CodexMCPProfile | None = None,
) -> list[dict[str, Any]]:
    profile = profile or await CodexMCPProfile.get_instance()  # type: ignore[assignment]
    servers = await MCPServerConfig.get_all(order_by="name asc")
    selected = _selected_servers(profile, servers)
    tools: list[dict[str, Any]] = []

    for server in selected:
        try:
            for tool in await list_mcp_tools(server):
                if not tool.get("enabled") or tool.get("permission") != "read":
                    continue
                tools.append(
                    {
                        "type": "function",
                        "name": _dynamic_tool_name(server, tool["name"]),
                        "description": (
                            f"{server.name}: {tool.get('description') or tool['name']}"
                        ),
                        "inputSchema": tool.get("input_schema") or {"type": "object"},
                    }
                )
        except Exception:
            continue

    if not tools:
        return []

    return [
        {
            "type": "namespace",
            "name": CODEX_DYNAMIC_MCP_NAMESPACE,
            "description": (
                "Read-only MCP tools mediated by Open Notebook. Tool calls are "
                "checked against Open Notebook server/tool permissions and audited."
            ),
            "tools": tools,
        }
    ]


async def call_codex_dynamic_mcp_tool(
    params: dict[str, Any],
    profile: CodexMCPProfile | None = None,
) -> dict[str, Any]:
    namespace = params.get("namespace")
    if namespace not in {None, CODEX_DYNAMIC_MCP_NAMESPACE}:
        raise MCPClientError(f"Unsupported Codex dynamic tool namespace: {namespace}")

    tool_name = params.get("tool")
    if not isinstance(tool_name, str) or "__" not in tool_name:
        raise MCPClientError("Codex dynamic MCP tool name must include a server prefix")

    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise MCPClientError("Codex dynamic MCP tool arguments must be a JSON object")

    profile = profile or await CodexMCPProfile.get_instance()  # type: ignore[assignment]
    servers = await MCPServerConfig.get_all(order_by="name asc")
    for server in _selected_servers(profile, servers):
        prefix = f"{_codex_server_name(server)}__"
        if not tool_name.startswith(prefix):
            continue
        raw_tool_name = tool_name[len(prefix) :]
        try:
            result = await call_mcp_tool(
                server,
                raw_tool_name,
                arguments,
                allow_mutation=False,
            )
            await MCPToolAudit(
                server_id=server.id,
                server_name=server.name,
                tool_name=raw_tool_name,
                permission=result["permission"],
                caller="codex_app_server",
                status="success" if not result.get("is_error", False) else "failed",
                error=None if not result.get("is_error", False) else "Tool returned error",
                argument_summary=summarize_mcp_arguments(arguments),
                result_summary={
                    "content_items": len(result.get("content", [])),
                    "text_length": len(result.get("text", "")),
                    "truncated": result.get("truncated", False),
                },
            ).save()
            return {
                "contentItems": [
                    {
                        "type": "inputText",
                        "text": result.get("text")
                        or str(result.get("content", "No tool output")),
                    }
                ],
                "success": not result.get("is_error", False),
            }
        except Exception as exc:
            await MCPToolAudit(
                server_id=server.id,
                server_name=server.name,
                tool_name=raw_tool_name,
                permission="disabled",
                caller="codex_app_server",
                status="failed",
                error=str(exc),
                argument_summary=summarize_mcp_arguments(arguments),
                result_summary={},
            ).save()
            raise

    raise MCPClientError(f"Codex dynamic MCP tool is not configured: {tool_name}")
