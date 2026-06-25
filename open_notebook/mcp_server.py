from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

try:
    from api.client import APIClient
except ModuleNotFoundError:

    class APIClient:
        """Small packaged fallback for the first-party MCP console script."""

        def __init__(self, base_url: str | None = None):
            self.base_url = (base_url or os.getenv("OPEN_NOTEBOOK_URL") or "http://127.0.0.1:5055").rstrip("/")
            self.timeout = float(os.getenv("API_CLIENT_TIMEOUT", "300.0"))
            self.headers: dict[str, str] = {}
            password = os.getenv("OPEN_NOTEBOOK_PASSWORD")
            if password:
                self.headers["Authorization"] = f"Bearer {password}"

        def _make_request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
            headers = kwargs.pop("headers", {})
            headers.update(self.headers)
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method,
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()

        def get_notebooks(
            self,
            archived: bool | None = None,
            order_by: str = "updated desc",
        ) -> list[dict[str, Any]]:
            params: dict[str, Any] = {"order_by": order_by}
            if archived is not None:
                params["archived"] = str(archived).lower()
            result = self._make_request("GET", "/api/notebooks", params=params)
            return result if isinstance(result, list) else [result]

        def get_notebook(self, notebook_id: str) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("GET", f"/api/notebooks/{notebook_id}")

        def create_notebook(
            self,
            name: str,
            description: str = "",
        ) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request(
                "POST",
                "/api/notebooks",
                json={"name": name, "description": description},
            )

        def get_notes(self, notebook_id: str | None = None) -> list[dict[str, Any]]:
            params = {"notebook_id": notebook_id} if notebook_id else {}
            result = self._make_request("GET", "/api/notes", params=params)
            return result if isinstance(result, list) else [result]

        def create_note(
            self,
            content: str,
            title: str | None = None,
            note_type: str = "human",
            notebook_id: str | None = None,
        ) -> dict[str, Any] | list[dict[str, Any]]:
            data = {"content": content, "note_type": note_type}
            if title:
                data["title"] = title
            if notebook_id:
                data["notebook_id"] = notebook_id
            return self._make_request("POST", "/api/notes", json=data)

        def get_sources(self, notebook_id: str | None = None) -> list[dict[str, Any]]:
            params = {"notebook_id": notebook_id} if notebook_id else {}
            result = self._make_request("GET", "/api/sources", params=params)
            return result if isinstance(result, list) else [result]

        def search(
            self,
            query: str,
            search_type: str = "text",
            limit: int = 20,
            search_sources: bool = True,
            search_notes: bool = True,
            minimum_score: float = 0.2,
        ) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request(
                "POST",
                "/api/search/ask/simple",
                json={"query": query, "type": search_type, "limit": limit},
            )

        def get_models(self, model_type: str | None = None) -> list[dict[str, Any]]:
            params = {"type": model_type} if model_type else {}
            result = self._make_request("GET", "/api/models", params=params)
            return result if isinstance(result, list) else [result]

        def get_default_models(self) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("GET", "/api/models/defaults")

        def get_mcp_servers(self) -> list[dict[str, Any]]:
            result = self._make_request("GET", "/api/mcp/servers")
            return result if isinstance(result, list) else [result]

        def discover_local_mcp_servers(self) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("GET", "/api/mcp/discover-local")

        def import_local_mcp_server(
            self,
            candidate_id: str,
            enabled: bool = True,
        ) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request(
                "POST",
                "/api/mcp/import-local",
                json={"candidate_id": candidate_id, "enabled": enabled},
            )

        def create_mcp_server(self, **server: Any) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("POST", "/api/mcp/servers", json=server)

        def update_mcp_server(
            self,
            server_id: str,
            **updates: Any,
        ) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("PUT", f"/api/mcp/servers/{server_id}", json=updates)

        def test_mcp_server(self, server_id: str) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("POST", f"/api/mcp/servers/{server_id}/test")

        def delete_mcp_server(self, server_id: str) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("DELETE", f"/api/mcp/servers/{server_id}")

        def get_codex_mcp_profile(self) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request("GET", "/api/models/codex-app-server/mcp-profile")

        def update_codex_mcp_profile(
            self,
            mode: str,
            selected_server_ids: list[str] | None = None,
            custom_profile_name: str | None = None,
        ) -> dict[str, Any] | list[dict[str, Any]]:
            return self._make_request(
                "PUT",
                "/api/models/codex-app-server/mcp-profile",
                json={
                    "mode": mode,
                    "selected_server_ids": selected_server_ids or [],
                    "custom_profile_name": custom_profile_name,
                },
            )


def _client(base_url: str | None = None) -> APIClient:
    return APIClient(base_url=base_url or os.getenv("OPEN_NOTEBOOK_URL"))


def list_notebooks_tool(
    client: APIClient,
    archived: bool | None = None,
    order_by: str = "updated desc",
) -> list[dict[str, Any]]:
    return client.get_notebooks(archived=archived, order_by=order_by)


def get_notebook_tool(client: APIClient, notebook_id: str) -> dict[str, Any] | list[dict[str, Any]]:
    return client.get_notebook(notebook_id)


def create_notebook_tool(
    client: APIClient,
    name: str,
    description: str = "",
) -> dict[str, Any] | list[dict[str, Any]]:
    return client.create_notebook(name=name, description=description)


def list_notes_tool(
    client: APIClient,
    notebook_id: str | None = None,
) -> list[dict[str, Any]]:
    return client.get_notes(notebook_id=notebook_id)


def create_note_tool(
    client: APIClient,
    content: str,
    title: str | None = None,
    note_type: str = "human",
    notebook_id: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    return client.create_note(
        content=content,
        title=title,
        note_type=note_type,
        notebook_id=notebook_id,
    )


def list_sources_tool(
    client: APIClient,
    notebook_id: str | None = None,
) -> list[dict[str, Any]]:
    return client.get_sources(notebook_id=notebook_id)


def search_tool(
    client: APIClient,
    query: str,
    search_type: str = "text",
    limit: int = 20,
    search_sources: bool = True,
    search_notes: bool = True,
    minimum_score: float = 0.2,
) -> dict[str, Any] | list[dict[str, Any]]:
    return client.search(
        query=query,
        search_type=search_type,
        limit=limit,
        search_sources=search_sources,
        search_notes=search_notes,
        minimum_score=minimum_score,
    )


def list_models_tool(client: APIClient, model_type: str | None = None) -> list[dict[str, Any]]:
    return client.get_models(model_type=model_type)


def get_default_models_tool(client: APIClient) -> dict[str, Any] | list[dict[str, Any]]:
    return client.get_default_models()


def list_mcp_servers_tool(client: APIClient) -> list[dict[str, Any]]:
    return client.get_mcp_servers()


def discover_local_mcp_servers_tool(client: APIClient) -> dict[str, Any] | list[dict[str, Any]]:
    return client.discover_local_mcp_servers()


def import_local_mcp_server_tool(
    client: APIClient,
    candidate_id: str,
    enabled: bool = True,
) -> dict[str, Any] | list[dict[str, Any]]:
    return client.import_local_mcp_server(candidate_id=candidate_id, enabled=enabled)


def create_mcp_server_tool(
    client: APIClient,
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    enabled: bool = True,
    timeout: int = 30,
) -> dict[str, Any] | list[dict[str, Any]]:
    return client.create_mcp_server(
        name=name,
        transport="stdio",
        command=command,
        args=args or [],
        env=env or {},
        enabled=enabled,
        timeout=timeout,
        concurrency=1,
    )


def update_mcp_server_tool(
    client: APIClient,
    server_id: str,
    name: str | None = None,
    enabled: bool | None = None,
    allowed_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    tool_permissions: dict[str, str] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name
    if enabled is not None:
        updates["enabled"] = enabled
    if allowed_tools is not None:
        updates["allowed_tools"] = allowed_tools
    if disabled_tools is not None:
        updates["disabled_tools"] = disabled_tools
    if tool_permissions is not None:
        updates["tool_permissions"] = tool_permissions
    return client.update_mcp_server(server_id, **updates)


def test_mcp_server_tool(client: APIClient, server_id: str) -> dict[str, Any] | list[dict[str, Any]]:
    return client.test_mcp_server(server_id)


def delete_mcp_server_tool(client: APIClient, server_id: str) -> dict[str, Any] | list[dict[str, Any]]:
    return client.delete_mcp_server(server_id)


def get_codex_mcp_profile_tool(client: APIClient) -> dict[str, Any] | list[dict[str, Any]]:
    return client.get_codex_mcp_profile()


def update_codex_mcp_profile_tool(
    client: APIClient,
    mode: str,
    selected_server_ids: list[str] | None = None,
    custom_profile_name: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    return client.update_codex_mcp_profile(
        mode=mode,
        selected_server_ids=selected_server_ids,
        custom_profile_name=custom_profile_name,
    )


def create_mcp_server(api_client: APIClient | None = None) -> FastMCP:
    client = api_client or _client()
    server = FastMCP(
        "Open Notebook",
        instructions=(
            "Read and write Open Notebook data through its authenticated HTTP API. "
            "Mutation tools in this reference server are limited to write-safe creation flows."
        ),
    )

    @server.tool
    def list_notebooks(
        archived: bool | None = None,
        order_by: str = "updated desc",
    ) -> list[dict[str, Any]]:
        """List Open Notebook notebooks."""
        return list_notebooks_tool(client, archived=archived, order_by=order_by)

    @server.tool
    def get_notebook(notebook_id: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Get one notebook by id."""
        return get_notebook_tool(client, notebook_id=notebook_id)

    @server.tool
    def create_notebook(name: str, description: str = "") -> dict[str, Any] | list[dict[str, Any]]:
        """Create a notebook."""
        return create_notebook_tool(client, name=name, description=description)

    @server.tool
    def list_notes(notebook_id: str | None = None) -> list[dict[str, Any]]:
        """List notes, optionally filtered by notebook id."""
        return list_notes_tool(client, notebook_id=notebook_id)

    @server.tool
    def create_note(
        content: str,
        title: str | None = None,
        note_type: str = "human",
        notebook_id: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Create a note, optionally attached to a notebook."""
        return create_note_tool(
            client,
            content=content,
            title=title,
            note_type=note_type,
            notebook_id=notebook_id,
        )

    @server.tool
    def list_sources(notebook_id: str | None = None) -> list[dict[str, Any]]:
        """List sources, optionally filtered by notebook id."""
        return list_sources_tool(client, notebook_id=notebook_id)

    @server.tool
    def search(
        query: str,
        search_type: str = "text",
        limit: int = 20,
        search_sources: bool = True,
        search_notes: bool = True,
        minimum_score: float = 0.2,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Search Open Notebook content."""
        return search_tool(
            client,
            query=query,
            search_type=search_type,
            limit=limit,
            search_sources=search_sources,
            search_notes=search_notes,
            minimum_score=minimum_score,
        )

    @server.tool
    def list_models(model_type: str | None = None) -> list[dict[str, Any]]:
        """List configured AI models."""
        return list_models_tool(client, model_type=model_type)

    @server.tool
    def get_default_models() -> dict[str, Any] | list[dict[str, Any]]:
        """Get default model assignments."""
        return get_default_models_tool(client)

    @server.tool
    def list_mcp_servers() -> list[dict[str, Any]]:
        """List configured Open Notebook MCP servers with secret values redacted."""
        return list_mcp_servers_tool(client)

    @server.tool
    def discover_local_mcp_servers() -> dict[str, Any] | list[dict[str, Any]]:
        """Discover local MCP server candidates from local agent runtime config."""
        return discover_local_mcp_servers_tool(client)

    @server.tool
    def import_local_mcp_server(
        candidate_id: str,
        enabled: bool = True,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Import one discovered local MCP server candidate by candidate id."""
        return import_local_mcp_server_tool(client, candidate_id=candidate_id, enabled=enabled)

    @server.tool
    def create_mcp_server(
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        enabled: bool = True,
        timeout: int = 30,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Create a stdio MCP server config. Only pass non-secret env values."""
        return create_mcp_server_tool(
            client,
            name=name,
            command=command,
            args=args,
            env=env,
            enabled=enabled,
            timeout=timeout,
        )

    @server.tool
    def update_mcp_server(
        server_id: str,
        name: str | None = None,
        enabled: bool | None = None,
        allowed_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        tool_permissions: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Update an MCP server's metadata, enabled state, or tool policy."""
        return update_mcp_server_tool(
            client,
            server_id=server_id,
            name=name,
            enabled=enabled,
            allowed_tools=allowed_tools,
            disabled_tools=disabled_tools,
            tool_permissions=tool_permissions,
        )

    @server.tool
    def test_mcp_server(server_id: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Test one configured MCP server and list its tools."""
        return test_mcp_server_tool(client, server_id)

    @server.tool
    def delete_mcp_server(server_id: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Delete one configured MCP server."""
        return delete_mcp_server_tool(client, server_id)

    @server.tool
    def get_codex_mcp_profile() -> dict[str, Any] | list[dict[str, Any]]:
        """Get Codex App Server MCP profile preferences and safe preview."""
        return get_codex_mcp_profile_tool(client)

    @server.tool
    def update_codex_mcp_profile(
        mode: str,
        selected_server_ids: list[str] | None = None,
        custom_profile_name: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Update Codex App Server MCP profile preferences."""
        return update_codex_mcp_profile_tool(
            client,
            mode=mode,
            selected_server_ids=selected_server_ids,
            custom_profile_name=custom_profile_name,
        )

    return server


def main() -> None:
    transport = os.getenv("OPEN_NOTEBOOK_MCP_TRANSPORT", "stdio")
    create_mcp_server().run(transport=transport)


if __name__ == "__main__":
    main()
