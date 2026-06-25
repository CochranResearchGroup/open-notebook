from __future__ import annotations

import hashlib
import json
import os
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from open_notebook.domain.mcp_server_config import MCPServerConfig

SECRET_KEY_PARTS = ("key", "token", "secret", "password", "credential")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _signature(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _redact_env(env: dict[str, Any] | None) -> tuple[dict[str, str], list[str]]:
    redacted: dict[str, str] = {}
    keys: list[str] = []
    for key, value in (env or {}).items():
        if not isinstance(key, str) or not key.strip():
            continue
        name = key.strip()
        keys.append(name)
        lower = name.lower()
        if any(part in lower for part in SECRET_KEY_PARTS):
            redacted[name] = "<redacted>"
        elif value is None:
            redacted[name] = ""
        else:
            redacted[name] = str(value)
    return redacted, sorted(keys)


def _docker_localhost_target() -> str | None:
    explicit = os.getenv("OPEN_NOTEBOOK_MCP_LOCALHOST_HOST")
    if explicit:
        return explicit
    if Path("/.dockerenv").exists():
        return "host.docker.internal"
    return None


def _runtime_url_and_metadata(url: str | None) -> tuple[str | None, dict[str, Any]]:
    if not url:
        return None, {}
    parsed = urlparse(url)
    if parsed.hostname not in LOOPBACK_HOSTS:
        return url, {}

    target = _docker_localhost_target()
    if not target:
        return url, {}

    netloc = target
    if parsed.port:
        netloc = f"{target}:{parsed.port}"
    rewritten = urlunparse(parsed._replace(netloc=netloc))
    return rewritten, {
        "original_url": url,
        "host_header": parsed.netloc,
        "localhost_rewritten_for_runtime": True,
    }


def _codex_config_paths() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("OPEN_NOTEBOOK_CODEX_HOME", "CODEX_HOME"):
        value = os.getenv(env_name)
        if value:
            candidates.append(Path(value).expanduser() / "config.toml")
    candidates.append(Path.home() / ".codex" / "config.toml")
    candidates.append(Path("/codex-home/config.toml"))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _candidate_payload(
    *,
    source: str,
    source_path: Path,
    server_name: str,
    raw: dict[str, Any],
) -> dict[str, Any] | None:
    command = raw.get("command")
    url = raw.get("url")
    transport = str(raw.get("transport") or ("stdio" if command else "http")).strip()
    if transport == "stdio" and not command:
        return None
    if transport != "stdio" and not url:
        return None

    args = raw.get("args") or []
    if not isinstance(args, list):
        args = [str(args)]

    redacted_env, env_keys = _redact_env(raw.get("env"))
    metadata = {
        "source": source,
        "source_path": str(source_path),
        "source_server_name": server_name,
    }
    signature_payload = {
        "source": source,
        "name": server_name,
        "transport": transport,
        "command": command,
        "args": [str(item) for item in args],
        "url": url,
        "env_keys": env_keys,
    }
    signature = _signature(signature_payload)
    return {
        "source": source,
        "source_path": str(source_path),
        "candidate_id": f"{source}:{signature[:16]}",
        "signature": signature,
        "name": str(raw.get("name") or server_name).replace("_", " ").title(),
        "transport": transport,
        "command": str(command) if command else None,
        "args": [str(item) for item in args],
        "env": redacted_env,
        "env_keys": env_keys,
        "url": str(url) if url else None,
        "auth_env_var": raw.get("auth_env_var"),
        "enabled": True,
        "allowed_tools": [],
        "disabled_tools": [],
        "tool_permissions": {},
        "timeout": int(raw.get("timeout") or 30),
        "concurrency": int(raw.get("concurrency") or 1),
        "metadata": {
            **metadata,
            "local_discovery_signature": signature,
            "env_values_redacted": True,
        },
    }


def _codex_candidates(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.exists():
        return [], None
    try:
        data = tomllib.loads(path.read_text())
    except Exception as exc:
        return [], f"Could not read Codex config {path}: {exc}"

    servers = data.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        return [], None

    candidates: list[dict[str, Any]] = []
    for server_name, raw in servers.items():
        if not isinstance(raw, dict):
            continue
        candidate = _candidate_payload(
            source="codex",
            source_path=path,
            server_name=str(server_name),
            raw=raw,
        )
        if candidate:
            candidates.append(candidate)
    return candidates, None


async def discover_local_mcp_servers() -> dict[str, Any]:
    searched_paths = [str(path) for path in _codex_config_paths()]
    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []

    for path in _codex_config_paths():
        found, warning = _codex_candidates(path)
        candidates.extend(found)
        if warning:
            warnings.append(warning)

    try:
        imported = await MCPServerConfig.get_all(order_by="name asc")
    except Exception as exc:
        imported = []
        warnings.append(f"Could not read configured MCP servers: {exc}")
    imported_by_signature: dict[str, str | None] = {}
    for server in imported:
        signature = server.metadata.get("local_discovery_signature")
        if isinstance(signature, str):
            imported_by_signature[signature] = server.id

    for candidate in candidates:
        imported_id = imported_by_signature.get(candidate["signature"])
        candidate["already_imported"] = imported_id is not None
        candidate["imported_server_id"] = imported_id

    return {
        "candidates": candidates,
        "searched_paths": searched_paths,
        "warnings": warnings,
    }


async def import_local_mcp_server(candidate_id: str, enabled: bool = True) -> MCPServerConfig:
    discovery = await discover_local_mcp_servers()
    for candidate in discovery["candidates"]:
        if candidate["candidate_id"] != candidate_id:
            continue
        if candidate.get("already_imported") and candidate.get("imported_server_id"):
            return await MCPServerConfig.get(candidate["imported_server_id"])
        url, runtime_metadata = _runtime_url_and_metadata(candidate.get("url"))
        server = MCPServerConfig(
            name=candidate["name"],
            transport=candidate["transport"],
            command=candidate.get("command"),
            args=candidate.get("args", []),
            env={},
            url=url,
            auth_env_var=candidate.get("auth_env_var"),
            enabled=enabled,
            allowed_tools=candidate.get("allowed_tools", []),
            disabled_tools=candidate.get("disabled_tools", []),
            tool_permissions=candidate.get("tool_permissions", {}),
            timeout=candidate.get("timeout", 30),
            concurrency=candidate.get("concurrency", 1),
            metadata={
                **candidate.get("metadata", {}),
                **runtime_metadata,
                "imported_from_local_discovery": True,
                "candidate_id": candidate_id,
            },
        )
        await server.save()
        return server
    raise ValueError(f"Local MCP server candidate was not found: {candidate_id}")
