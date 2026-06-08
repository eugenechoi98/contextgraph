"""CLI 入口。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from contextgraph_studio.api.main import app as fastapi_app
from contextgraph_studio.api.mcp_server import serve_mcp_stdio
from contextgraph_studio.application.errors import ApplicationError
from contextgraph_studio.application.get_trace import GetTraceService
from contextgraph_studio.application.retrieve_context import RetrieveContextService
from contextgraph_studio.application.scan_repo import ScanRepoService
from contextgraph_studio.config import get_settings
from contextgraph_studio.db import init_db
from contextgraph_studio.eval.datasets.swebench_lite import inspect_swebench_lite
from contextgraph_studio.eval.runner import run_eval
from contextgraph_studio.eval.swebench_localization import run_swebench_localization
from contextgraph_studio.graph.traversal import graph_search
from contextgraph_studio.models.context_pack import RetrieveContextRequest
from contextgraph_studio.models.scan import ScanRepoRequest
from contextgraph_studio.models.trace import GetTraceRequest
from contextgraph_studio.retrieval.vector import search_similar_chunks
from contextgraph_studio.services.retriever import search_bm25
from contextgraph_studio.services.scan_resolver import resolve_repo_and_scan_run


app = typer.Typer(help="ContextGraph Studio CLI")


@app.command("init-db")
def cli_init_db() -> None:
    """初始化数据库。"""

    settings = get_settings()
    database_path = init_db(settings)
    typer.echo(f"Database initialized: {database_path}")


@app.command("index-repo")
def cli_index_repo(repo_path: str) -> None:
    """索引本地仓库。"""

    settings = get_settings()
    try:
        result = ScanRepoService(settings).execute(ScanRepoRequest(path=repo_path))
    except ApplicationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2))


@app.command("index")
def cli_index(repo_path: str) -> None:
    """正式索引命令。"""

    cli_index_repo(repo_path)


@app.command("scan-repo")
def cli_scan_repo(
    path: str | None = None,
    scan_run_id: str | None = None,
    repo_id: str | None = None,
    with_vectors: bool | None = None,
) -> None:
    """触发索引或查询 scan_run 状态。"""

    settings = get_settings()
    try:
        result = ScanRepoService(settings).execute(
            ScanRepoRequest(
                path=path,
                scan_run_id=scan_run_id,
                repo_id=repo_id,
                with_vectors=with_vectors,
            )
        )
    except ApplicationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2))


@app.command("retrieve")
def cli_retrieve(
    query: str,
    top_k: int = 8,
    task_hint: str | None = None,
    max_tokens: int | None = None,
    repo_id: str | None = None,
    trace: bool = True,
) -> None:
    """执行检索。"""

    settings = get_settings()
    try:
        pack = RetrieveContextService(settings).execute(
            RetrieveContextRequest(
                query=query,
                top_k=top_k,
                task_hint=task_hint,
                max_tokens=max_tokens,
                repo_id=repo_id,
                trace=trace,
            )
        )
    except ApplicationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(pack.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2))


@app.command("eval")
def cli_eval(
    repo_id: Annotated[str, typer.Option("--repo-id")],
    dataset: Annotated[Path, typer.Option("--dataset")] = Path("eval/fixtures/contextgraph_golden.json"),
    config: Annotated[list[str] | None, typer.Option("--config")] = None,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("eval/reports"),
    max_cases: Annotated[int | None, typer.Option("--max-cases")] = None,
) -> None:
    """运行本地 golden dataset 评测。"""

    settings = get_settings()
    try:
        result = run_eval(
            settings,
            repo_id=repo_id,
            dataset_path=dataset,
            config_names=config,
            output_dir=output_dir,
            max_cases=max_cases,
        )
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "eval_run_id": result.eval_run_id,
        "json_report_path": result.json_report_path,
        "markdown_report_path": result.markdown_report_path,
        "active_case_count": result.active_cases,
        "failed_case_count": sum(config_result.failed_case_count for config_result in result.configs),
        "configs": [
            {
                "name": config_result.config.name,
                "mrr": config_result.metrics.mrr,
                "critical_file_hit_rate": config_result.metrics.critical_file_hit_rate,
                "critical_file_any_hit_rate": config_result.metrics.critical_file_any_hit_rate,
                "recall_at_5": config_result.metrics.recall_at_k[5],
                "avg_token_count": config_result.metrics.avg_token_count,
            }
            for config_result in result.configs
        ],
    }
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@app.command("swebench-inspect")
def cli_swebench_inspect(
    dataset: Annotated[Path | None, typer.Option("--dataset")] = None,
    source: Annotated[str, typer.Option("--source")] = "local",
    split: Annotated[str, typer.Option("--split")] = "test",
    max_instances: Annotated[int | None, typer.Option("--max-instances")] = None,
    instance_id: Annotated[list[str] | None, typer.Option("--instance-id")] = None,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("eval/manifests/generated"),
    allow_network: Annotated[bool, typer.Option("--allow-network")] = False,
    critical_lines_threshold: Annotated[int, typer.Option("--critical-lines-threshold")] = 5,
) -> None:
    """Inspect SWE-bench Lite data and generate dry-run ground truth manifests."""

    if source not in {"local", "hf"}:
        typer.echo("--source must be either 'local' or 'hf'.", err=True)
        raise typer.Exit(code=1)
    try:
        manifest, json_path, markdown_path = inspect_swebench_lite(
            dataset_path=dataset,
            source=source,  # type: ignore[arg-type]
            split=split,
            max_instances=max_instances,
            instance_ids=set(instance_id or []) or None,
            output_dir=output_dir,
            allow_network=allow_network,
            critical_changed_lines_threshold=critical_lines_threshold,
        )
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "json_manifest_path": str(json_path),
        "markdown_manifest_path": str(markdown_path),
        "instance_count": manifest.total_instances,
        "critical_file_count": sum(len(instance.critical_files) for instance in manifest.instances),
        "excluded_file_count": sum(len(instance.excluded_files) for instance in manifest.instances),
    }
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@app.command("swebench-localize")
def cli_swebench_localize(
    manifest: Annotated[Path, typer.Option("--manifest")],
    cache_dir: Annotated[Path | None, typer.Option("--cache-dir")] = None,
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
    max_instances: Annotated[int, typer.Option("--max-instances")] = 1,
    instance_id: Annotated[list[str] | None, typer.Option("--instance-id")] = None,
    config: Annotated[list[str] | None, typer.Option("--config")] = None,
    allow_network: Annotated[bool, typer.Option("--allow-network")] = False,
    min_free_bytes: Annotated[int | None, typer.Option("--min-free-bytes")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens")] = None,
) -> None:
    """Run an isolated SWE-bench Lite localization smoke."""

    settings = get_settings()
    try:
        result = run_swebench_localization(
            settings,
            manifest_path=manifest,
            cache_dir=cache_dir,
            output_dir=output_dir,
            max_instances=max_instances,
            instance_ids=set(instance_id or []) or None,
            config_names=config,
            allow_network=allow_network,
            min_free_bytes=min_free_bytes,
            dry_run=dry_run,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "run_id": result.run_id,
        "json_report_path": result.json_report_path,
        "markdown_report_path": result.markdown_report_path,
        "dry_run": result.dry_run,
        "allow_network": result.allow_network,
        "selected_instance_count": result.selected_instance_count,
        "case_result_count": len(result.case_results),
        "passed_case_count": result.passed_case_count,
        "failed_case_count": result.failed_case_count,
        "critical_hit_count": sum(1 for case in result.case_results if case.critical_file_hit),
        "graph_hit_case_count": sum(1 for case in result.case_results if case.graph_hit_count > 0),
    }
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@app.command("get-trace")
def cli_get_trace(trace_id: str) -> None:
    """读取结构化 trace。"""

    settings = get_settings()
    try:
        record = GetTraceService(settings).execute(GetTraceRequest(trace_id=trace_id))
    except ApplicationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(record.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2))


@app.command("search")
def cli_search(query: str, top_k: int = 8, repo_id: str | None = None) -> None:
    """调试用 BM25 搜索。"""

    settings = get_settings()
    from contextgraph_studio.db import connect, init_db

    init_db(settings)
    with connect(settings.database_path) as connection:
        resolved_repo_id, scan_run_id = resolve_repo_and_scan_run(connection, repo_id)
        hits = search_bm25(connection, query, resolved_repo_id, scan_run_id, top_k)
    typer.echo(
        json.dumps(
            [
                {
                    "chunk_id": hit.chunk_id,
                    "file_path": hit.file_path,
                    "entity": hit.entity,
                    "chunk_kind": hit.chunk_kind,
                    "line_start": hit.line_start,
                    "line_end": hit.line_end,
                    "score": hit.score,
                }
                for hit in hits
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("vector-search")
def cli_vector_search(query: str, top_k: int = 10, repo_id: str | None = None) -> None:
    """调试用向量搜索。"""

    settings = get_settings()
    try:
        hits = search_similar_chunks(query, settings, repo_id=repo_id, top_k=top_k)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        json.dumps(
            [
                {
                    "chunk_id": hit.chunk_id,
                    "file_path": hit.file_path,
                    "entity": hit.entity,
                    "chunk_kind": hit.chunk_kind,
                    "line_start": hit.line_start,
                    "line_end": hit.line_end,
                    "score": hit.score,
                    "provider": hit.provider,
                    "model": hit.model,
                    "dim": hit.dim,
                }
                for hit in hits
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("graph-search")
def cli_graph_search(
    symbol: Annotated[str | None, typer.Option("--symbol")] = None,
    entity_id: Annotated[str | None, typer.Option("--entity-id")] = None,
    repo_id: Annotated[str | None, typer.Option("--repo-id")] = None,
    hops: Annotated[int, typer.Option("--hops")] = 2,
    edge_type: Annotated[list[str] | None, typer.Option("--edge-type")] = None,
) -> None:
    """调试用图搜索。"""

    if not symbol and not entity_id:
        typer.echo("Provide either --symbol or --entity-id for graph-search.", err=True)
        raise typer.Exit(code=1)
    settings = get_settings()
    try:
        hits = graph_search(
            settings,
            symbol=symbol,
            entity_id=entity_id,
            repo_id=repo_id,
            edge_types=edge_type,
            max_hops=hops,
        )
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps([hit.as_dict() for hit in hits], ensure_ascii=False, indent=2))


@app.command("serve")
def cli_serve(host: str | None = None, port: int | None = None) -> None:
    """启动 FastAPI 服务。"""

    settings = get_settings()
    uvicorn.run(
        fastapi_app,
        host=host or settings.host,
        port=port or settings.port,
        log_level=settings.log_level,
    )


@app.command("mcp")
def cli_mcp() -> None:
    """启动 stdio MCP server。"""

    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.WARNING))
    try:
        serve_mcp_stdio(settings)
    except Exception as exc:
        typer.echo(f"Failed to start MCP server: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
