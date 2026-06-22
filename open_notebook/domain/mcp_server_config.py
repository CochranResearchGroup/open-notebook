from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from open_notebook.domain.base import ObjectModel

MCPTransport = Literal["stdio", "http", "sse", "websocket"]
MCPToolPermission = Literal["read", "mutate", "disabled"]


class MCPServerConfig(ObjectModel):
    table_name = "mcp_server_config"
    nullable_fields = {"command", "url"}

    name: str
    transport: MCPTransport = "stdio"
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    auth_env_var: Optional[str] = None
    enabled: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    tool_permissions: dict[str, MCPToolPermission] = Field(default_factory=dict)
    timeout: int = 30
    concurrency: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("MCP server name cannot be empty")
        return value

    @field_validator("command", "url", "auth_env_var", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if value < 1 or value > 300:
            raise ValueError("MCP server timeout must be between 1 and 300 seconds")
        return value

    @field_validator("concurrency")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("MCP server concurrency must be between 1 and 10")
        return value

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "MCPServerConfig":
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio MCP servers require a command")
        if self.transport != "stdio" and not self.url:
            raise ValueError(f"{self.transport} MCP servers require a URL")
        return self
