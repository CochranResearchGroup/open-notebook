"""AuraCall provider integration."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from esperanto.common_types import Model
from esperanto.providers.llm.base import LanguageModel
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

AURACALL_PROVIDER = "auracall"
AURACALL_OPENAI_COMPATIBLE_PROVIDER = "openai-compatible"
DEFAULT_AURACALL_BASE_URL = "http://127.0.0.1:18095/v1"
DEFAULT_AURACALL_MODEL = "agent:open-notebook-pro-chatgpt-soylei"
TERMINAL_FAILURE_STATUSES = {"failed", "cancelled", "canceled", "expired"}


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _langchain_role(message: BaseMessage) -> str:
    role = getattr(message, "type", "")
    if role in {"system", "human", "ai"}:
        return {"human": "user", "ai": "assistant"}.get(role, role)
    return "user"


def _extract_responses_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n\n".join(parts)


def _extract_chat_completion_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return _message_content_to_text(message.get("content") or "")


def _raise_for_http_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        data = response.json()
    except Exception:
        data = {"error": {"message": response.text}}
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("type") or response.text
    else:
        message = response.text
    raise RuntimeError(f"AuraCall API error: {message}")


class AuraCallChatModel(BaseChatModel):
    model: str = Field(default=DEFAULT_AURACALL_MODEL)
    api_key: str | None = Field(
        default_factory=lambda: os.environ.get("AURACALL_API_KEY")
        or os.environ.get("OPENAI_COMPATIBLE_API_KEY")
    )
    base_url: str = Field(
        default_factory=lambda: (
            os.environ.get("AURACALL_BASE_URL")
            or os.environ.get("OPENAI_COMPATIBLE_BASE_URL")
            or DEFAULT_AURACALL_BASE_URL
        )
    )
    max_tokens: int = 850
    temperature: float = 1.0
    top_p: float = 0.9
    request_timeout: float = Field(
        default_factory=lambda: float(
            os.environ.get("OPEN_NOTEBOOK_AURACALL_REQUEST_TIMEOUT") or "60"
        )
    )
    poll_timeout: float = Field(
        default_factory=lambda: float(
            os.environ.get("OPEN_NOTEBOOK_AURACALL_POLL_TIMEOUT") or "900"
        )
    )
    poll_interval: float = Field(
        default_factory=lambda: float(
            os.environ.get("OPEN_NOTEBOOK_AURACALL_POLL_INTERVAL") or "2"
        )
    )
    sync_timeout_ms: int = Field(
        default_factory=lambda: int(
            os.environ.get("OPEN_NOTEBOOK_AURACALL_CHAT_COMPLETION_SYNC_TIMEOUT_MS")
            or "30000"
        )
    )

    @property
    def _llm_type(self) -> str:
        return AURACALL_PROVIDER

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _messages_payload(self, messages: list[BaseMessage]) -> list[dict[str, str]]:
        return [
            {
                "role": _langchain_role(message),
                "content": _message_content_to_text(message.content),
            }
            for message in messages
        ]

    def _completion_payload(
        self,
        messages: list[BaseMessage],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": self._messages_payload(messages),
            "stream": False,
            "max_tokens": int(kwargs.get("max_tokens") or self.max_tokens),
            "temperature": float(kwargs.get("temperature") or self.temperature),
            "top_p": float(kwargs.get("top_p") or self.top_p),
            "auracall": {"chatCompletionSyncTimeoutMs": self.sync_timeout_ms},
        }
        if kwargs.get("response_format"):
            payload["response_format"] = kwargs["response_format"]
        if kwargs.get("metadata"):
            payload["metadata"] = kwargs["metadata"]
        return payload

    def _final_text_from_chat_completion(self, data: dict[str, Any]) -> str | None:
        error = data.get("error")
        if isinstance(error, dict) and error.get("type") == "auracall_execution_pending":
            return None
        if isinstance(error, dict):
            raise RuntimeError(error.get("message") or "AuraCall chat completion failed")
        return _extract_chat_completion_text(data)

    def _pending_response_id(self, data: dict[str, Any]) -> str | None:
        error = data.get("error")
        if not isinstance(error, dict):
            return None
        if error.get("type") != "auracall_execution_pending":
            return None
        response_id = error.get("response_id")
        return response_id if isinstance(response_id, str) and response_id else None

    def _poll_response(self, client: httpx.Client, response_id: str) -> str:
        deadline = time.monotonic() + self.poll_timeout
        while True:
            response = client.get(
                f"{self.base_url.rstrip('/')}/responses/{response_id}",
                headers=self._headers(),
            )
            _raise_for_http_error(response)
            data = response.json()
            status = data.get("status")
            if status == "completed":
                return _extract_responses_text(data)
            if status in TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(
                    f"AuraCall execution {response_id} ended with status {status}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AuraCall execution {response_id} did not complete within "
                    f"{self.poll_timeout}s"
                )
            time.sleep(self.poll_interval)

    async def _apoll_response(self, client: httpx.AsyncClient, response_id: str) -> str:
        deadline = time.monotonic() + self.poll_timeout
        while True:
            response = await client.get(
                f"{self.base_url.rstrip('/')}/responses/{response_id}",
                headers=self._headers(),
            )
            _raise_for_http_error(response)
            data = response.json()
            status = data.get("status")
            if status == "completed":
                return _extract_responses_text(data)
            if status in TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(
                    f"AuraCall execution {response_id} ended with status {status}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AuraCall execution {response_id} did not complete within "
                    f"{self.poll_timeout}s"
                )
            await asyncio.sleep(self.poll_interval)

    def _complete(self, messages: list[BaseMessage], kwargs: dict[str, Any]) -> str:
        with httpx.Client(timeout=self.request_timeout) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=self._headers(),
                json=self._completion_payload(messages, kwargs),
            )
            _raise_for_http_error(response)
            data = response.json()
            text = self._final_text_from_chat_completion(data)
            if text is not None:
                return text
            response_id = self._pending_response_id(data)
            if not response_id:
                raise RuntimeError("AuraCall pending response did not include response_id")
            return self._poll_response(client, response_id)

    async def _acomplete(self, messages: list[BaseMessage], kwargs: dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=self._headers(),
                json=self._completion_payload(messages, kwargs),
            )
            _raise_for_http_error(response)
            data = response.json()
            text = self._final_text_from_chat_completion(data)
            if text is not None:
                return text
            response_id = self._pending_response_id(data)
            if not response_id:
                raise RuntimeError("AuraCall pending response did not include response_id")
            return await self._apoll_response(client, response_id)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        content = self._complete(messages, kwargs)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        content = await self._acomplete(messages, kwargs)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


@dataclass
class AuraCallLanguageModel(LanguageModel):
    @property
    def provider(self) -> str:
        return AURACALL_PROVIDER

    def _get_default_model(self) -> str:
        return DEFAULT_AURACALL_MODEL

    def _get_models(self) -> list[Model]:
        model_name = self.get_model_name()
        return [Model(id=model_name, owned_by=AURACALL_PROVIDER)]

    def to_langchain(self) -> AuraCallChatModel:
        config = dict(self._config)
        config.setdefault("model", self.get_model_name())
        config.pop("model_name", None)
        return AuraCallChatModel(**config)

    def chat_complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        from langchain_core.messages import HumanMessage, SystemMessage

        langchain_messages: list[BaseMessage] = []
        for message in messages:
            content = message.get("content") or ""
            if message.get("role") == "system":
                langchain_messages.append(SystemMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))
        response = self.to_langchain().invoke(langchain_messages, **kwargs)
        return {"content": _message_content_to_text(response.content)}

    async def achat_complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        from langchain_core.messages import HumanMessage, SystemMessage

        langchain_messages: list[BaseMessage] = []
        for message in messages:
            content = message.get("content") or ""
            if message.get("role") == "system":
                langchain_messages.append(SystemMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))
        response = await self.to_langchain().ainvoke(langchain_messages, **kwargs)
        return {"content": _message_content_to_text(response.content)}
