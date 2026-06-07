"""MCP stdio server。"""

from __future__ import annotations

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from contextgraph_studio.application.errors import ApplicationError, ValidationAppError
from contextgraph_studio.application.get_trace import GetTraceService
from contextgraph_studio.application.retrieve_context import RetrieveContextService
from contextgraph_studio.application.scan_repo import ScanRepoService
from contextgraph_studio.config import Settings, get_settings
from contextgraph_studio.models.context_pack import ContextPack, RetrieveContextRequest
from contextgraph_studio.models.scan import ScanRepoRequest, ScanRepoResult
from contextgraph_studio.models.trace import GetTraceRequest, TraceRecord


def create_mcp_server(settings: Settings | None = None) -> Server:
    """创建 MCP server，并绑定共享应用服务。"""

    runtime_settings = settings or get_settings()
    server = Server("contextgraph")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return build_tool_definitions()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> dict:
        try:
            return dispatch_tool_call(name, arguments, runtime_settings)
        except ApplicationError as exc:
            raise ValueError(str(exc)) from exc

    return server


def build_tool_definitions() -> list[Tool]:
    """构造三个 MCP tool 定义。"""

    retrieve_schema = RetrieveContextRequest.model_json_schema()
    retrieve_schema["required"] = ["query", "repo_id"]
    scan_schema = ScanRepoRequest.model_json_schema()
    get_trace_schema = GetTraceRequest.model_json_schema()

    return [
        Tool(
            name="retrieve_context",
            description="Retrieve relevant code context for an AI coding task.",
            inputSchema=retrieve_schema,
            outputSchema=ContextPack.model_json_schema(),
        ),
        Tool(
            name="scan_repo",
            description="Trigger a synchronous repository scan or query an existing scan_run status.",
            inputSchema=scan_schema,
            outputSchema=ScanRepoResult.model_json_schema(),
        ),
        Tool(
            name="get_trace",
            description="Retrieve a structured retrieval trace for debugging and explainability.",
            inputSchema=get_trace_schema,
            outputSchema=TraceRecord.model_json_schema(mode="serialization"),
        ),
    ]


def dispatch_tool_call(name: str, arguments: dict, settings: Settings | None = None) -> dict:
    """供 MCP handler 和测试共享的 tool 分发逻辑。"""

    runtime_settings = settings or get_settings()
    if name == "retrieve_context":
        request = RetrieveContextRequest.model_validate(arguments)
        if not request.repo_id:
            raise ValidationAppError("repo_id is required for retrieve_context.")
        return RetrieveContextService(runtime_settings).execute(request).model_dump(mode="json", by_alias=True)
    if name == "scan_repo":
        request = ScanRepoRequest.model_validate(arguments)
        return ScanRepoService(runtime_settings).execute(request).model_dump(mode="json", by_alias=True)
    if name == "get_trace":
        request = GetTraceRequest.model_validate(arguments)
        return GetTraceService(runtime_settings).execute(request).model_dump(mode="json", by_alias=True)
    raise ValidationAppError(f"Unknown tool: {name}")


async def run_mcp_stdio(settings: Settings | None = None) -> None:
    """以 stdio 方式运行 MCP server。"""

    server = create_mcp_server(settings)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def serve_mcp_stdio(settings: Settings | None = None) -> None:
    """同步入口：启动 stdio MCP server。"""

    anyio.run(run_mcp_stdio, settings)
