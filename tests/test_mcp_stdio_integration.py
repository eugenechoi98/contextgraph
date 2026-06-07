import json
import os
from pathlib import Path
from uuid import uuid4

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def build_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def normalize_token(token: str) -> str:\n"
        "    return token.strip()\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    cleaned = normalize_token(token)\n"
        "    return cleaned == 'ok'\n",
        encoding="utf-8",
    )


@pytest.mark.anyio
async def test_mcp_stdio_real_protocol_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    errlog_path = tmp_path / "mcp-stderr.log"
    sentinel = f"phase3b-{uuid4().hex}"
    database_path = tmp_path / ".data" / "contextgraph.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CGSTUDIO_SECRET_SENTINEL"] = sentinel
    env["CGSTUDIO_DB_PATH"] = str(database_path)

    server = StdioServerParameters(
        command=str(Path.cwd() / ".venv" / "Scripts" / "cgstudio.exe"),
        args=["mcp"],
        cwd=str(Path.cwd()),
        env=env,
    )

    with errlog_path.open("w+", encoding="utf-8") as errlog:
        with anyio.fail_after(30):
            async with stdio_client(server, errlog=errlog) as streams:
                read_stream, write_stream = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    tools_result = await session.list_tools()
                    tool_names = {tool.name for tool in tools_result.tools}
                    assert tool_names == {"retrieve_context", "scan_repo", "get_trace"}

                    retrieve_tool = next(tool for tool in tools_result.tools if tool.name == "retrieve_context")
                    assert retrieve_tool.inputSchema["required"] == ["query", "repo_id"]

                    scan_result = await session.call_tool("scan_repo", {"path": str(repo)})
                    assert scan_result.isError is False
                    scan_payload = scan_result.structuredContent
                    assert scan_payload["status"] == "done"
                    assert scan_payload["repo_id"]
                    assert scan_payload["scan_run_id"]
                    assert scan_payload["stats"]["files"] == 1

                    scan_status = await session.call_tool("scan_repo", {"scan_run_id": scan_payload["scan_run_id"]})
                    assert scan_status.isError is False
                    assert scan_status.structuredContent["scan_run_id"] == scan_payload["scan_run_id"]

                    bad_scan = await session.call_tool(
                        "scan_repo",
                        {"path": str(repo), "scan_run_id": scan_payload["scan_run_id"]},
                    )
                    assert bad_scan.isError is True
                    assert "validation_error" in bad_scan.content[0].text

                    missing_path = await session.call_tool("scan_repo", {"path": str(repo / "missing")})
                    assert missing_path.isError is True
                    assert "validation_error" in missing_path.content[0].text

                    retrieve_result = await session.call_tool(
                        "retrieve_context",
                        {
                            "query": "verify token auth flow",
                            "repo_id": scan_payload["repo_id"],
                            "task_hint": "security_auth",
                            "max_tokens": 500,
                            "trace": True,
                        },
                    )
                    assert retrieve_result.isError is False
                    pack = retrieve_result.structuredContent
                    assert pack["trace_id"]
                    assert pack["token_estimate"] <= 500
                    assert pack["retrieval_strategy"]
                    chunk_ids = [item["chunk_id"] for item in pack["required"] + pack["supporting"]]
                    assert len(chunk_ids) == len(set(chunk_ids))

                    no_trace_result = await session.call_tool(
                        "retrieve_context",
                        {
                            "query": "verify token auth flow",
                            "repo_id": scan_payload["repo_id"],
                            "max_tokens": 500,
                            "trace": False,
                        },
                    )
                    assert no_trace_result.isError is False
                    assert no_trace_result.structuredContent["trace_id"] is None

                    empty_query = await session.call_tool(
                        "retrieve_context",
                        {"query": "", "repo_id": scan_payload["repo_id"], "max_tokens": 500},
                    )
                    assert empty_query.isError is True

                    invalid_tokens = await session.call_tool(
                        "retrieve_context",
                        {"query": "verify token", "repo_id": scan_payload["repo_id"], "max_tokens": 50},
                    )
                    assert invalid_tokens.isError is True

                    missing_repo = await session.call_tool(
                        "retrieve_context",
                        {"query": "verify token", "repo_id": "missing-repo", "max_tokens": 500},
                    )
                    assert missing_repo.isError is True
                    assert "not_found" in missing_repo.content[0].text

                    trace_result = await session.call_tool("get_trace", {"trace_id": pack["trace_id"]})
                    assert trace_result.isError is False
                    trace = trace_result.structuredContent
                    assert trace["trace_id"] == pack["trace_id"]
                    assert trace["repo_id"] == scan_payload["repo_id"]
                    assert trace["query"] == "verify token auth flow"
                    assert trace["retrieval_strategy"] == pack["retrieval_strategy"]
                    assert trace["final_selection"]["trace_id"] == pack["trace_id"]
                    assert trace["index_version"] == scan_payload["scan_run_id"]

                    missing_trace = await session.call_tool("get_trace", {"trace_id": "missing-trace"})
                    assert missing_trace.isError is True
                    assert "not_found" in missing_trace.content[0].text

        errlog.flush()
        errlog.seek(0)
        stderr_text = errlog.read()
    assert sentinel not in stderr_text


@pytest.mark.anyio
async def test_mcp_stdio_can_restart_cleanly(tmp_path: Path) -> None:
    async def run_once() -> list[str]:
        errlog_path = tmp_path / f"mcp-stderr-{uuid4().hex}.log"
        database_path = tmp_path / ".data" / f"{uuid4().hex}.db"
        database_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["CGSTUDIO_DB_PATH"] = str(database_path)
        server = StdioServerParameters(
            command=str(Path.cwd() / ".venv" / "Scripts" / "cgstudio.exe"),
            args=["mcp"],
            cwd=str(Path.cwd()),
            env=env,
        )
        with errlog_path.open("w+", encoding="utf-8") as errlog:
            with anyio.fail_after(20):
                async with stdio_client(server, errlog=errlog) as streams:
                    read_stream, write_stream = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        return [tool.name for tool in tools.tools]

    assert await run_once() == ["retrieve_context", "scan_repo", "get_trace"]
    assert await run_once() == ["retrieve_context", "scan_repo", "get_trace"]
