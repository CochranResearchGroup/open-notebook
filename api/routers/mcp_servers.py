from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.mcp_discovery_service import (
    discover_local_mcp_servers,
    import_local_mcp_server,
)
from api.models import (
    MCPLocalDiscoveryResponse,
    MCPLocalImportRequest,
    MCPServerCreate,
    MCPServerResponse,
    MCPServerTestResponse,
    MCPServerUpdate,
    MCPToolAuditResponse,
    MCPToolCallRequest,
    MCPToolCallResponse,
)
from open_notebook.domain.mcp_server_config import MCPServerConfig
from open_notebook.domain.mcp_tool_audit import (
    MCPToolAudit,
    summarize_mcp_arguments,
)
from open_notebook.exceptions import InvalidInputError, NotFoundError
from open_notebook.mcp_client import (
    MCPClientError,
    call_mcp_tool,
    list_mcp_tools,
    redacted_mcp_config,
)

router = APIRouter()


def _to_response(config: MCPServerConfig) -> MCPServerResponse:
    return MCPServerResponse(**redacted_mcp_config(config))


def _apply_update(config: MCPServerConfig, update: MCPServerUpdate) -> MCPServerConfig:
    values = update.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(config, key, value)
    return MCPServerConfig(**config.model_dump())


def _to_audit_response(audit: MCPToolAudit) -> MCPToolAuditResponse:
    return MCPToolAuditResponse(
        id=audit.id,
        server_id=audit.server_id,
        server_name=audit.server_name,
        tool_name=audit.tool_name,
        permission=audit.permission,
        caller=audit.caller,
        status=audit.status,
        error=audit.error,
        argument_summary=audit.argument_summary,
        result_summary=audit.result_summary,
        created=str(audit.created) if audit.created else None,
        updated=str(audit.updated) if audit.updated else None,
    )


@router.get("/mcp/servers", response_model=list[MCPServerResponse])
async def list_servers():
    servers = await MCPServerConfig.get_all(order_by="name asc")
    return [_to_response(server) for server in servers]


@router.get("/mcp/discover-local", response_model=MCPLocalDiscoveryResponse)
async def discover_local_servers():
    return MCPLocalDiscoveryResponse(**await discover_local_mcp_servers())


@router.post("/mcp/import-local", response_model=MCPServerResponse)
async def import_local_server(payload: MCPLocalImportRequest):
    try:
        server = await import_local_mcp_server(
            payload.candidate_id,
            enabled=payload.enabled,
        )
        return _to_response(server)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mcp/servers", response_model=MCPServerResponse)
async def create_server(payload: MCPServerCreate):
    try:
        server = MCPServerConfig(**payload.model_dump())
        await server.save()
        return _to_response(server)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/mcp/servers/{server_id:path}", response_model=MCPServerResponse)
async def update_server(server_id: str, payload: MCPServerUpdate):
    try:
        server = await MCPServerConfig.get(server_id)
        server = _apply_update(server, payload)
        await server.save()
        return _to_response(server)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/mcp/servers/{server_id:path}")
async def delete_server(server_id: str):
    try:
        server = await MCPServerConfig.get(server_id)
        deleted = await server.delete()
        return {"deleted": deleted}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mcp/servers/{server_id:path}/tools", response_model=MCPServerTestResponse)
async def get_server_tools(server_id: str):
    return await test_server(server_id)


@router.post("/mcp/servers/{server_id:path}/test", response_model=MCPServerTestResponse)
async def test_server(server_id: str):
    try:
        server = await MCPServerConfig.get(server_id)
        tools = await list_mcp_tools(server)
        return MCPServerTestResponse(
            success=True,
            message=f"Connected to {server.name}",
            tools=tools,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MCPClientError as exc:
        logger.warning(f"MCP server test failed for {server_id}: {exc}")
        return MCPServerTestResponse(success=False, message=str(exc), tools=[])


@router.post("/mcp/tool-call", response_model=MCPToolCallResponse)
async def call_tool(payload: MCPToolCallRequest):
    server: MCPServerConfig | None = None
    try:
        server = await MCPServerConfig.get(payload.server_id)
        result = await call_mcp_tool(
            server,
            payload.tool_name,
            payload.arguments,
            allow_mutation=payload.allow_mutation,
        )
        await MCPToolAudit(
            server_id=server.id,
            server_name=server.name,
            tool_name=payload.tool_name,
            permission=result["permission"],
            caller="api",
            status="success" if not result.get("is_error", False) else "failed",
            error=None if not result.get("is_error", False) else "Tool returned error",
            argument_summary=summarize_mcp_arguments(payload.arguments),
            result_summary={
                "content_items": len(result.get("content", [])),
                "text_length": len(result.get("text", "")),
                "truncated": result.get("truncated", False),
            },
        ).save()
        return MCPToolCallResponse(
            success=not result.get("is_error", False),
            message="Tool call completed",
            tool_name=payload.tool_name,
            permission=result["permission"],
            is_error=result.get("is_error", False),
            content=result.get("content", []),
            text=result.get("text", ""),
            truncated=result.get("truncated", False),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MCPClientError as exc:
        logger.warning(
            f"MCP tool call failed for {payload.server_id}/{payload.tool_name}: {exc}"
        )
        await MCPToolAudit(
            server_id=server.id if server else payload.server_id,
            server_name=server.name if server else None,
            tool_name=payload.tool_name,
            permission="disabled",
            caller="api",
            status="failed",
            error=str(exc),
            argument_summary=summarize_mcp_arguments(payload.arguments),
            result_summary={},
        ).save()
        return MCPToolCallResponse(
            success=False,
            message=str(exc),
            tool_name=payload.tool_name,
            permission="disabled",
            is_error=True,
            content=[],
            text="",
            truncated=False,
        )


@router.get("/mcp/tool-audit", response_model=list[MCPToolAuditResponse])
async def list_tool_audit(
    limit: int = Query(100, ge=1, le=500, description="Maximum audit records")
):
    records = await MCPToolAudit.get_all(order_by="created desc")
    return [_to_audit_response(record) for record in records[:limit]]
