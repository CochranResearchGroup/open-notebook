from open_notebook.mcp_server import (
    create_mcp_server,
    create_mcp_server_tool,
    create_note_tool,
    create_notebook_tool,
    discover_local_mcp_servers_tool,
    get_default_models_tool,
    import_local_mcp_server_tool,
    list_mcp_servers_tool,
    list_models_tool,
    list_notebooks_tool,
    search_tool,
    update_codex_mcp_profile_tool,
    update_mcp_server_tool,
)


class FakeAPIClient:
    def __init__(self):
        self.calls = []

    def get_notebooks(self, archived=None, order_by="updated desc"):
        self.calls.append(("get_notebooks", archived, order_by))
        return [{"id": "notebook:1", "name": "Notebook"}]

    def create_notebook(self, name, description=""):
        self.calls.append(("create_notebook", name, description))
        return {"id": "notebook:2", "name": name, "description": description}

    def create_note(self, content, title=None, note_type="human", notebook_id=None):
        self.calls.append(("create_note", content, title, note_type, notebook_id))
        return {"id": "note:1", "content": content, "title": title}

    def search(
        self,
        query,
        search_type="text",
        limit=100,
        search_sources=True,
        search_notes=True,
        minimum_score=0.2,
    ):
        self.calls.append(
            (
                "search",
                query,
                search_type,
                limit,
                search_sources,
                search_notes,
                minimum_score,
            )
        )
        return {"results": [], "total_count": 0, "search_type": search_type}

    def get_models(self, model_type=None):
        self.calls.append(("get_models", model_type))
        return [{"id": "model:1", "type": model_type or "language"}]

    def get_default_models(self):
        self.calls.append(("get_default_models",))
        return {"default_chat_model": "model:1"}

    def get_mcp_servers(self):
        self.calls.append(("get_mcp_servers",))
        return [{"id": "mcp_server_config:1", "name": "CodeGraph"}]

    def discover_local_mcp_servers(self):
        self.calls.append(("discover_local_mcp_servers",))
        return {"candidates": [{"candidate_id": "codex:abc"}]}

    def import_local_mcp_server(self, candidate_id, enabled=True):
        self.calls.append(("import_local_mcp_server", candidate_id, enabled))
        return {"id": "mcp_server_config:imported"}

    def create_mcp_server(self, **server):
        self.calls.append(("create_mcp_server", server))
        return {"id": "mcp_server_config:created", **server}

    def update_mcp_server(self, server_id, **updates):
        self.calls.append(("update_mcp_server", server_id, updates))
        return {"id": server_id, **updates}

    def update_codex_mcp_profile(
        self,
        mode,
        selected_server_ids=None,
        custom_profile_name=None,
    ):
        self.calls.append(
            (
                "update_codex_mcp_profile",
                mode,
                selected_server_ids,
                custom_profile_name,
            )
        )
        return {"mode": mode, "selected_server_ids": selected_server_ids or []}


def test_mcp_tool_wrappers_call_existing_api_client_methods():
    client = FakeAPIClient()

    assert list_notebooks_tool(client)[0]["id"] == "notebook:1"
    assert create_notebook_tool(client, "New", "Desc")["id"] == "notebook:2"
    assert create_note_tool(client, "Body", title="Title", notebook_id="notebook:1")[
        "id"
    ] == "note:1"
    assert search_tool(client, "query", limit=5)["total_count"] == 0
    assert list_models_tool(client, "language")[0]["id"] == "model:1"
    assert get_default_models_tool(client)["default_chat_model"] == "model:1"
    assert list_mcp_servers_tool(client)[0]["name"] == "CodeGraph"
    assert discover_local_mcp_servers_tool(client)["candidates"][0]["candidate_id"] == "codex:abc"
    assert import_local_mcp_server_tool(client, "codex:abc")["id"] == "mcp_server_config:imported"
    assert create_mcp_server_tool(client, "Local", "local-mcp")["id"] == "mcp_server_config:created"
    assert update_mcp_server_tool(client, "mcp_server_config:1", enabled=False)["enabled"] is False
    assert update_codex_mcp_profile_tool(
        client,
        "selected",
        ["mcp_server_config:1"],
    )["mode"] == "selected"

    assert ("create_notebook", "New", "Desc") in client.calls
    assert ("create_note", "Body", "Title", "human", "notebook:1") in client.calls
    assert ("get_models", "language") in client.calls
    assert ("import_local_mcp_server", "codex:abc", True) in client.calls


def test_create_mcp_server_with_injected_client():
    server = create_mcp_server(api_client=FakeAPIClient())

    assert server is not None
