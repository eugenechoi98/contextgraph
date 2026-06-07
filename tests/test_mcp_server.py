from pathlib import Path

import pytest

from contextgraph_studio.api.mcp_server import build_tool_definitions, create_mcp_server, dispatch_tool_call
from contextgraph_studio.config import Settings
from contextgraph_studio.models.context_pack import ContextPack, RetrieveContextRequest
from contextgraph_studio.models.scan import ScanRepoRequest
from contextgraph_studio.models.trace import GetTraceRequest, TraceRecord


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def build_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token(token: str) -> bool:\n    return token == 'ok'\n", encoding="utf-8")


def test_mcp_server_lists_required_tools(tmp_path: Path) -> None:
    server = create_mcp_server(make_settings(tmp_path))
    assert server is not None
    tools = build_tool_definitions()
    names = {tool.name for tool in tools}
    assert names == {"retrieve_context", "scan_repo", "get_trace"}
    retrieve_tool = next(tool for tool in tools if tool.name == "retrieve_context")
    assert "repo_id" in retrieve_tool.inputSchema["required"]


def test_mcp_tool_schemas_match_shared_models() -> None:
    tools = {tool.name: tool for tool in build_tool_definitions()}
    retrieve_schema = RetrieveContextRequest.model_json_schema()
    retrieve_schema["required"] = ["query", "repo_id"]
    assert tools["retrieve_context"].inputSchema == retrieve_schema
    assert tools["retrieve_context"].outputSchema == ContextPack.model_json_schema()
    assert tools["scan_repo"].inputSchema == ScanRepoRequest.model_json_schema()
    assert tools["get_trace"].inputSchema == GetTraceRequest.model_json_schema()
    assert tools["get_trace"].outputSchema == TraceRecord.model_json_schema(mode="serialization")


def test_mcp_dispatch_calls_shared_services(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)

    scan_payload = dispatch_tool_call("scan_repo", {"path": str(repo)}, settings)
    assert scan_payload["status"] == "done"

    retrieve_payload = dispatch_tool_call(
        "retrieve_context",
        {"query": "verify token", "repo_id": scan_payload["repo_id"], "max_tokens": 500, "trace": True},
        settings,
    )
    assert "bm25" in retrieve_payload["retrieval_strategy"]

    trace_payload = dispatch_tool_call("get_trace", {"trace_id": retrieve_payload["trace_id"]}, settings)
    assert trace_payload["trace_id"] == retrieve_payload["trace_id"]


def test_mcp_dispatch_returns_readable_errors(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with pytest.raises(Exception) as exc_info:
        dispatch_tool_call("retrieve_context", {"query": "verify token"}, settings)
    assert "repo_id" in str(exc_info.value)
