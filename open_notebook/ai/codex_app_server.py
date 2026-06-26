from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import selectors
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from loguru import logger
from pydantic import Field, PrivateAttr

from open_notebook.ai.codex_mcp import (
    build_codex_dynamic_tool_specs,
    build_codex_mcp_config_overrides,
    build_codex_mcp_launch_config,
    call_codex_dynamic_mcp_tool,
    materialize_codex_mcp_profile,
)

CODEX_APP_SERVER_PROVIDER = "codex_app_server"
DEFAULT_CODEX_APP_SERVER_MODEL = "gpt-5.5"
DEFAULT_CODEX_APP_SERVER_CWD = "/tmp/open-notebook-codex-app-server-cwd"


def codex_app_server_model_name() -> str:
    return os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_MODEL") or DEFAULT_CODEX_APP_SERVER_MODEL


def codex_app_server_available() -> bool:
    enabled = (os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_ENABLED") or "").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return False
    codex_bin = os.environ.get("OPEN_NOTEBOOK_CODEX_BIN") or "codex"
    if os.path.isabs(codex_bin) or os.sep in codex_bin:
        return os.access(codex_bin, os.X_OK)
    path_value = os.environ.get("PATH") or os.defpath
    return any(
        os.access(os.path.join(path_dir, codex_bin), os.X_OK)
        for path_dir in path_value.split(os.pathsep)
    )


def _codex_bin_path(codex_bin: str) -> str | None:
    if os.path.isabs(codex_bin) or os.sep in codex_bin:
        return codex_bin if os.access(codex_bin, os.X_OK) else None
    return shutil.which(codex_bin)


def _redacted_path_label(path_value: str | None) -> str | None:
    if not path_value:
        return None
    expanded = Path(path_value).expanduser()
    name = expanded.name or str(expanded)
    return f"configured (.../{name})"


def _run_async_blocking(coro: Any) -> Any:
    """Run async setup from sync LangGraph/Codex glue code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    def run_in_new_loop() -> Any:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run_in_new_loop).result()


def codex_app_server_status() -> dict[str, Any]:
    enabled_value = (os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_ENABLED") or "").strip().lower()
    enabled = enabled_value not in {"0", "false", "no", "off"}
    codex_bin = os.environ.get("OPEN_NOTEBOOK_CODEX_BIN") or "codex"
    resolved_bin = _codex_bin_path(codex_bin)
    help_ok = False
    help_error: str | None = None

    if enabled and resolved_bin:
        try:
            subprocess.run(
                [codex_bin, "app-server", "--help"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            help_ok = True
        except Exception as exc:
            help_error = str(exc)

    codex_home = os.environ.get("OPEN_NOTEBOOK_CODEX_HOME")
    cwd = os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_CWD") or DEFAULT_CODEX_APP_SERVER_CWD
    effort = os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_EFFORT") or "medium"
    sandbox = os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_SANDBOX") or "read-only"
    timeout = int(os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_TIMEOUT") or "900")

    return {
        "provider": CODEX_APP_SERVER_PROVIDER,
        "enabled": enabled,
        "available": enabled and resolved_bin is not None and help_ok,
        "cli_found": resolved_bin is not None,
        "help_ok": help_ok,
        "help_error": help_error,
        "codex_bin": codex_bin,
        "codex_bin_path": resolved_bin,
        "profile": os.environ.get("OPEN_NOTEBOOK_CODEX_PROFILE") or "",
        "codex_home_configured": bool(codex_home),
        "codex_home_label": _redacted_path_label(codex_home),
        "model": codex_app_server_model_name(),
        "cwd": cwd,
        "effort": effort,
        "sandbox": sandbox,
        "timeout": timeout,
    }


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


def _format_messages(messages: list[BaseMessage]) -> str:
    rendered: list[str] = []
    for message in messages:
        role = getattr(message, "type", message.__class__.__name__).replace("_", " ")
        rendered.append(f"{role.upper()}:\n{_message_content_to_text(message.content)}")
    return "\n\n".join(rendered)


class _CodexAppServerClient:
    def __init__(
        self,
        codex_bin: str,
        profile: str,
        codex_home: str | None,
        config_overrides: list[str] | None = None,
    ) -> None:
        command = [codex_bin]
        if profile:
            command.extend(["--profile", profile])
        for override in config_overrides or []:
            command.extend(["-c", override])
        command.extend(["app-server", "--listen", "stdio://"])

        env = os.environ.copy()
        if codex_home:
            env["CODEX_HOME"] = str(Path(codex_home).expanduser())

        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        if self.proc.stdin is None or self.proc.stdout is None or self.proc.stderr is None:
            raise RuntimeError("Failed to open Codex app-server pipes")

        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.proc.stderr, selectors.EVENT_READ, "stderr")
        self.next_id = 1

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)

    def send(self, method: str, params: dict[str, Any] | None = None) -> int:
        request_id = self.next_id
        self.next_id += 1
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()
        return request_id

    def _write_response(self, response: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(response, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def _unsupported_server_request_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": request.get("id"),
            "error": {
                "code": -32603,
                "message": (
                    "Open Notebook Codex app-server wrapper does not handle "
                    f"server request {request.get('method')!r}."
                ),
            },
        }

    def _reply_to_server_request(self, request: dict[str, Any]) -> None:
        method = request.get("method")
        if method == "item/tool/call":
            try:
                result = asyncio.run(
                    call_codex_dynamic_mcp_tool(
                        request.get("params")
                        if isinstance(request.get("params"), dict)
                        else {}
                    )
                )
                self._write_response({"id": request.get("id"), "result": result})
                return
            except Exception as exc:
                self._write_response(
                    {
                        "id": request.get("id"),
                        "result": {
                            "contentItems": [
                                {
                                    "type": "inputText",
                                    "text": f"Open Notebook MCP tool call failed: {exc}",
                                }
                            ],
                            "success": False,
                        },
                    }
                )
                return

        if method == "account/chatgptAuthTokens/refresh":
            self._write_response(
                {
                    "id": request.get("id"),
                    "error": {
                        "code": -32603,
                        "message": (
                            "Open Notebook does not refresh Codex auth tokens. "
                            "Refresh Codex credentials in the local Codex runtime."
                        ),
                    },
                }
            )
            return

        if method == "mcpServer/elicitation/request":
            params = request.get("params") if isinstance(request.get("params"), dict) else {}
            metadata = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
            action = (
                "accept"
                if metadata.get("codex_approval_kind") == "mcp_tool_call"
                else "decline"
            )
            self._write_response(
                {
                    "id": request.get("id"),
                    "result": {
                        "action": action,
                        "content": {} if action == "accept" else None,
                        "_meta": None,
                    },
                }
            )
            return

        if method == "item/permissions/requestApproval":
            params = request.get("params") if isinstance(request.get("params"), dict) else {}
            requested = (
                params.get("permissions")
                if isinstance(params.get("permissions"), dict)
                else {}
            )
            granted = {
                key: value
                for key, value in requested.items()
                if key in {"network", "fileSystem"} and value is not None
            }
            self._write_response(
                {
                    "id": request.get("id"),
                    "result": {
                        "permissions": granted,
                        "scope": "turn",
                        "strictAutoReview": False,
                    },
                }
            )
            return

        self._write_response(self._unsupported_server_request_response(request))

    def read_message(self, deadline: float) -> dict[str, Any] | None:
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return None
            remaining = max(0.1, min(0.5, deadline - time.monotonic()))
            events = self.selector.select(remaining)
            if not events:
                continue
            for key, _ in events:
                stream_name = key.data
                line = key.fileobj.readline()
                if not line:
                    continue
                if stream_name == "stderr":
                    logger.debug(f"codex app-server stderr: {line.rstrip()}")
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"codex app-server non-json stdout: {line.rstrip()}")
                    continue
                if "id" in message and "method" in message:
                    self._reply_to_server_request(message)
                    continue
                return message
        return None

    def wait_for_response(self, request_id: int, timeout: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.read_message(deadline)
            if not message:
                continue
            if message.get("id") == request_id:
                return message
        raise TimeoutError(f"timed out waiting for Codex app-server response {request_id}")

    def wait_for_completion(self, timeout: int) -> str:
        deadline = time.monotonic() + timeout
        last_message = ""
        idle_after_final = False

        while time.monotonic() < deadline:
            message = self.read_message(deadline)
            if not message:
                continue

            method = message.get("method")
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            item = params.get("item") if isinstance(params.get("item"), dict) else {}

            if method == "item/completed":
                if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                    last_message = item["text"]
                    if item.get("phase") == "final_answer":
                        idle_after_final = True
                elif item.get("type") == "assistantMessage":
                    chunks = [
                        part["text"]
                        for part in item.get("content") or []
                        if isinstance(part, dict) and isinstance(part.get("text"), str)
                    ]
                    if chunks:
                        last_message = "\n".join(chunks)

            if method == "turn/completed":
                turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
                if turn.get("status") != "completed":
                    raise RuntimeError(f"Codex app-server turn failed: {turn.get('error')}")
                return last_message

            if method == "thread/status/changed" and idle_after_final:
                status = params.get("status") if isinstance(params.get("status"), dict) else {}
                if status.get("type") == "idle":
                    return last_message

        raise TimeoutError("timed out waiting for Codex app-server turn completion")


class CodexAppServerChatModel(BaseChatModel):
    model: str = Field(default_factory=codex_app_server_model_name)
    codex_bin: str = Field(default_factory=lambda: os.environ.get("OPEN_NOTEBOOK_CODEX_BIN") or "codex")
    profile: str = Field(default_factory=lambda: os.environ.get("OPEN_NOTEBOOK_CODEX_PROFILE") or "")
    codex_home: Optional[str] = Field(default_factory=lambda: os.environ.get("OPEN_NOTEBOOK_CODEX_HOME"))
    mcp_profile_name: str = Field(
        default_factory=lambda: os.environ.get(
            "OPEN_NOTEBOOK_CODEX_APP_SERVER_MCP_PROFILE_NAME"
        )
        or "open-notebook-mcp"
    )
    cwd: str = Field(
        default_factory=lambda: os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_CWD")
        or DEFAULT_CODEX_APP_SERVER_CWD
    )
    effort: str = Field(
        default_factory=lambda: os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_EFFORT") or "medium"
    )
    timeout: int = Field(
        default_factory=lambda: int(os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_TIMEOUT") or "900")
    )
    sandbox: str = Field(
        default_factory=lambda: os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_SANDBOX") or "read-only"
    )
    _client_class: Any = PrivateAttr(default=_CodexAppServerClient)

    @property
    def _llm_type(self) -> str:
        return "codex_app_server"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        content = self._run_turn(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return await asyncio.to_thread(self._generate, messages, stop, None, **kwargs)

    def _run_turn(self, messages: list[BaseMessage]) -> str:
        Path(self.cwd).mkdir(parents=True, exist_ok=True)
        dynamic_tool_specs = self._load_dynamic_tool_specs()
        mcp_launch_config = self._mcp_launch_config()
        config_overrides = mcp_launch_config["config_overrides"]
        launch_codex_home = mcp_launch_config["codex_home"]
        cleanup_path = mcp_launch_config["cleanup_path"]
        launch_profile = (
            self.profile
            if mcp_launch_config.get("enabled")
            else self._launch_profile()
        )
        client: _CodexAppServerClient | None = None
        try:
            client = self._client_class(
                self.codex_bin,
                launch_profile,
                launch_codex_home,
                config_overrides,
            )
            init_id = client.send(
                "initialize",
                {
                    "clientInfo": {"name": "open-notebook-codex-app-server", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            init_response = client.wait_for_response(init_id, min(self.timeout, 60))
            if "error" in init_response:
                raise RuntimeError(f"Codex app-server initialize failed: {init_response['error']}")

            thread_params: dict[str, Any] = {
                "cwd": self.cwd,
                "model": self.model,
                "approvalPolicy": "never",
                "sandbox": self.sandbox,
                "ephemeral": True,
                "personality": "pragmatic",
                "threadSource": "user",
                "sessionStartSource": "startup",
            }
            if dynamic_tool_specs:
                thread_params["config"] = {
                    "experimental_dynamic_tools": dynamic_tool_specs
                }
                thread_params["developerInstructions"] = (
                    "Open Notebook exposes selected read-only MCP tools through "
                    "the open_notebook_mcp dynamic-tool namespace. Use them only "
                    "when they directly help answer the user's notebook question."
                )

            thread_id_req = client.send("thread/start", thread_params)
            thread_response = client.wait_for_response(thread_id_req, min(self.timeout, 120))
            if "error" in thread_response:
                raise RuntimeError(f"Codex app-server thread/start failed: {thread_response['error']}")
            thread_id = thread_response["result"]["thread"]["id"]

            turn_id_req = client.send(
                "turn/start",
                {
                    "threadId": thread_id,
                    "cwd": self.cwd,
                    "model": self.model,
                    "approvalPolicy": "never",
                    "effort": self.effort,
                    "input": [{"type": "text", "text": _format_messages(messages)}],
                },
            )
            turn_response = client.wait_for_response(turn_id_req, min(self.timeout, 120))
            if "error" in turn_response:
                raise RuntimeError(f"Codex app-server turn/start failed: {turn_response['error']}")

            return client.wait_for_completion(self.timeout)
        finally:
            if client is not None:
                client.close()
            if cleanup_path:
                shutil.rmtree(cleanup_path, ignore_errors=True)

    def _load_dynamic_tool_specs(self) -> list[dict[str, Any]]:
        enabled = (
            os.environ.get("OPEN_NOTEBOOK_CODEX_APP_SERVER_DYNAMIC_TOOLS") or ""
        ).strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return []
        try:
            return _run_async_blocking(build_codex_dynamic_tool_specs())
        except Exception as exc:
            logger.warning(f"Could not load Codex dynamic MCP tool specs: {exc}")
            return []

    def _launch_profile(self) -> str:
        try:
            result = _run_async_blocking(
                materialize_codex_mcp_profile(
                    codex_home=self.codex_home,
                    profile_name=self.mcp_profile_name,
                )
            )
        except Exception as exc:
            logger.warning(f"Could not materialize Codex MCP profile: {exc}")
            return self.profile

        if result.get("enabled") and isinstance(result.get("profile_name"), str):
            return result["profile_name"]
        return self.profile

    def _mcp_config_overrides(self) -> list[str]:
        try:
            result = _run_async_blocking(build_codex_mcp_config_overrides())
        except Exception as exc:
            logger.warning(f"Could not build Codex MCP config overrides: {exc}")
            return []
        overrides = result.get("overrides")
        return overrides if isinstance(overrides, list) else []

    def _mcp_launch_config(self) -> dict[str, Any]:
        try:
            result = _run_async_blocking(
                build_codex_mcp_launch_config(codex_home=self.codex_home)
            )
        except Exception as exc:
            logger.warning(f"Could not build Codex MCP launch config: {exc}")
            return {
                "config_overrides": self._mcp_config_overrides(),
                "codex_home": self.codex_home,
                "cleanup_path": None,
            }

        overrides = result.get("config_overrides")
        return {
            "enabled": bool(result.get("enabled")),
            "config_overrides": overrides if isinstance(overrides, list) else [],
            "codex_home": result.get("codex_home") or self.codex_home,
            "cleanup_path": result.get("cleanup_path"),
        }


class CodexAppServerLanguageModel:
    def __init__(self, model_name: str, config: dict[str, Any] | None = None) -> None:
        self.model_name = model_name
        self.config = config or {}

    def to_langchain(self) -> CodexAppServerChatModel:
        return CodexAppServerChatModel(model=self.model_name, **self.config)

    async def achat_complete(self, messages: list[dict[str, str]]) -> SimpleNamespace:
        from langchain_core.messages import HumanMessage, SystemMessage

        langchain_messages: list[BaseMessage] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))
        response = await self.to_langchain().ainvoke(langchain_messages)
        return SimpleNamespace(content=_message_content_to_text(response.content))
