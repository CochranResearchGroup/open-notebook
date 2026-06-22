from typing import Any, ClassVar, Literal, Optional

from pydantic import Field

from open_notebook.domain.base import ObjectModel


class MCPToolAudit(ObjectModel):
    table_name: ClassVar[str] = "mcp_tool_audit"
    nullable_fields: ClassVar[set[str]] = {"error", "server_id", "server_name"}

    server_id: Optional[str] = None
    server_name: Optional[str] = None
    tool_name: str
    permission: Literal["read", "mutate", "disabled"]
    caller: str = "api"
    status: Literal["success", "failed"] = "success"
    error: Optional[str] = None
    argument_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)


def summarize_mcp_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "keys": sorted(arguments.keys()),
        "size": len(arguments),
    }
