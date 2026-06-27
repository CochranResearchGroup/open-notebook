import json

import httpx
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from open_notebook.ai.auracall import AuraCallChatModel, AuraCallLanguageModel
from open_notebook.ai.models import AURACALL_PROVIDER, ModelManager

REAL_HTTPX_CLIENT = httpx.Client


def _mock_client(handler):
    transport = httpx.MockTransport(handler)
    return REAL_HTTPX_CLIENT(transport=transport, timeout=60)


def test_auracall_chat_model_returns_immediate_chat_completion(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "agent:instant"
        assert payload["messages"] == [
            {"role": "system", "content": "Be brief"},
            {"role": "user", "content": "Hi"},
        ]
        assert payload["auracall"]["chatCompletionSyncTimeoutMs"] == 123
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Immediate answer"}}
                ]
            },
        )

    monkeypatch.setattr(
        "open_notebook.ai.auracall.httpx.Client",
        lambda timeout: _mock_client(handler),
    )

    model = AuraCallChatModel(
        model="agent:instant",
        api_key="test-key",
        base_url="http://auracall.local/v1",
        sync_timeout_ms=123,
    )
    response = model.invoke(
        [SystemMessage(content="Be brief"), HumanMessage(content="Hi")]
    )

    assert response.content == "Immediate answer"
    assert len(requests) == 1


def test_auracall_chat_model_polls_pending_chat_completion(monkeypatch):
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "error": {
                        "type": "auracall_execution_pending",
                        "response_id": "resp_123",
                        "response_status": "in_progress",
                    }
                },
            )
        if request.url.path == "/v1/responses/resp_123":
            return httpx.Response(
                200,
                json={
                    "id": "resp_123",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "Polled answer"}],
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    monkeypatch.setattr(
        "open_notebook.ai.auracall.httpx.Client",
        lambda timeout: _mock_client(handler),
    )

    model = AuraCallChatModel(
        model="agent:pro",
        api_key="test-key",
        base_url="http://auracall.local/v1",
        poll_interval=0,
    )
    response = model.invoke([HumanMessage(content="Hi")])

    assert response.content == "Polled answer"
    assert paths == ["/v1/chat/completions", "/v1/responses/resp_123"]


def test_auracall_chat_model_polls_non_2xx_pending_chat_completion(monkeypatch):
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                504,
                json={
                    "error": {
                        "type": "auracall_execution_pending",
                        "message": "Poll /v1/responses/{response_id}",
                        "response_id": "resp_pending_error",
                        "response_status": "in_progress",
                    }
                },
            )
        if request.url.path == "/v1/responses/resp_pending_error":
            return httpx.Response(
                200,
                json={
                    "id": "resp_pending_error",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "Recovered answer"}
                            ],
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    monkeypatch.setattr(
        "open_notebook.ai.auracall.httpx.Client",
        lambda timeout: _mock_client(handler),
    )

    model = AuraCallChatModel(
        model="agent:pro",
        api_key="test-key",
        base_url="http://auracall.local/v1",
        poll_interval=0,
    )
    response = model.invoke([HumanMessage(content="Hi")])

    assert response.content == "Recovered answer"
    assert paths == ["/v1/chat/completions", "/v1/responses/resp_pending_error"]


def test_auracall_language_model_returns_langchain_adapter():
    model = AuraCallLanguageModel(
        model_name="agent:medium",
        config={
            "api_key": "test-key",
            "base_url": "http://auracall.local/v1",
            "max_tokens": 4096,
        },
    )

    langchain_model = model.to_langchain()

    assert isinstance(langchain_model, AuraCallChatModel)
    assert langchain_model.model == "agent:medium"
    assert langchain_model.api_key == "test-key"
    assert langchain_model.base_url == "http://auracall.local/v1"
    assert langchain_model.max_tokens == 4096


@pytest.mark.asyncio
async def test_model_manager_uses_auracall_language_adapter(monkeypatch):
    class FakeModel:
        id = "model:auracall"
        name = "agent:open-notebook-pro-chatgpt-soylei"
        provider = AURACALL_PROVIDER
        type = "language"
        credential = None

    async def fake_get(model_id):
        return FakeModel()

    async def fake_provision(provider):
        return True

    monkeypatch.setattr("open_notebook.ai.models.Model.get", fake_get)
    monkeypatch.setattr(
        "open_notebook.ai.key_provider.provision_provider_keys",
        fake_provision,
    )

    model = await ModelManager().get_model("model:auracall")

    assert isinstance(model, AuraCallLanguageModel)
