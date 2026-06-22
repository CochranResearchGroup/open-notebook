from typing import ClassVar, Literal, Optional

from pydantic import Field, field_validator

from open_notebook.domain.base import RecordModel

CodexMCPProfileMode = Literal["none", "read_only", "selected", "custom"]


class CodexMCPProfile(RecordModel):
    record_id: ClassVar[str] = "open_notebook:codex_mcp_profile"

    mode: CodexMCPProfileMode = "none"
    selected_server_ids: list[str] = Field(default_factory=list)
    custom_profile_name: Optional[str] = None

    @field_validator("selected_server_ids")
    @classmethod
    def dedupe_selected_server_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for server_id in value:
            server_id = server_id.strip()
            if server_id and server_id not in seen:
                seen.add(server_id)
                deduped.append(server_id)
        return deduped
