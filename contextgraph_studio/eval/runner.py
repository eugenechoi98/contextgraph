"""Golden dataset 执行器与报告生成。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.domain import utc_now_epoch
from contextgraph_studio.eval.configs import resolve_eval_configs
from contextgraph_studio.eval.metrics import (
    DEFAULT_KS,
    aggregate_metrics,
    build_case_result,
    build_graph_characterization,
    dedupe_files,
)
from contextgraph_studio.eval.models import ConfigEvalResult, EvalConfig, EvalRunResult, GoldenDataset
from contextgraph_studio.services.retriever import retrieve_context_debug
from contextgraph_studio.services.scan_resolver import resolve_repo_and_scan_run


def load_golden_dataset(dataset_path: Path) -> GoldenDataset:
    """读取 golden dataset 文件。"""

    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return GoldenDataset(dataset=dataset_path.stem, cases=raw)
    if isinstance(raw, dict) and "cases" in raw:
        return GoldenDataset.model_validate(raw)
    raise ValueError("Golden dataset must be a JSON array of cases or an object containing a 'cases' list.")


def build_eval_runtime_settings(base_settings: Settings, config: EvalConfig) -> Settings:
    """为单个 ablation config 构造隔离的运行配置。"""

    if not config.bm25_enabled:
        raise ValueError("Current eval runner does not support disabling BM25.")
    return base_settings.model_copy(
        update={
            "hybrid_vector_enabled": config.vector_enabled,
            "hybrid_graph_enabled": config.graph_enabled,
        }
    )


def evaluate_vector_quality(settings: Settings) -> tuple[bool, str]:
    """标记当前 embedding provider 的质量结论是否有效。"""

    provider = settings.embedding_provider.strip().lower()
    model = settings.embedding_model.strip()
    if provider == "deterministic":
        return (
            False,
            "Deterministic embeddings validate pipeline correctness only; they do not measure semantic retrieval quality.",
        )
    if provider in {"nomic", "local_nomic", "sentence_transformer", "sentence-transformer"} and "nomic" in model.lower():
        return (
            False,
            "A real local embedding provider is configured, but this phase does not certify semantic vector quality until dedicated local smoke and reindex validation are completed.",
        )
    return (
        False,
        "The current embedding provider is not certified for semantic quality conclusions in this phase.",
    )


def run_eval(
    settings: Settings,
    *,
    repo_id: str,
    dataset_path: Path,
    config_names: list[str] | None = None,
    output_dir: Path | None = None,
    max_cases: int | None = None,
) -> EvalRunResult:
    """执行一轮 golden dataset 评测。"""

    init_db(settings)
    dataset = load_golden_dataset(dataset_path)
    active_cases = [case for case in dataset.cases if case.status == "active"]
    draft_cases = [case for case in dataset.cases if case.status == "draft"]
    if max_cases is not None:
        if max_cases <= 0:
            raise ValueError("max_cases must be greater than 0.")
        active_cases = active_cases[:max_cases]
    if not active_cases:
        raise ValueError("No active cases selected for evaluation.")

    eval_configs = resolve_eval_configs(config_names)
    vector_quality_valid, vector_quality_note = evaluate_vector_quality(settings)

    with connect(settings.database_path) as connection:
        _, scan_run_id = resolve_repo_and_scan_run(connection, repo_id)

    config_results: list[ConfigEvalResult] = []
    for config in eval_configs:
        runtime_settings = build_eval_runtime_settings(settings, config)
        case_results = []
        for case in active_cases:
            case_repo_id = case.repo_id or repo_id
            try:
                pack, debug = retrieve_context_debug(
                    case.query,
                    runtime_settings,
                    top_k=max(DEFAULT_KS),
                    task_hint=case.task_hint,
                    repo_id=case_repo_id,
                    trace=True,
                )
                retrieved_files = dedupe_files([item.file_path for item in pack.required + pack.supporting])
                case_result = build_case_result(
                    case,
                    retrieved_files=retrieved_files,
                    token_count=pack.token_estimate,
                    latency_ms=int(debug["latency_ms"]) if debug.get("latency_ms") is not None else None,
                    trace_id=pack.trace_id,
                    retrieval_strategy=pack.retrieval_strategy,
                    requested_routes=list(debug.get("requested_routes", [])),
                    executed_routes=list(debug.get("executed_routes", [])),
                    participating_routes=list(debug.get("participating_routes", [])),
                    effective_flags=dict(debug.get("effective_flags", {})),
                    route_diagnostics=dict(debug.get("route_diagnostics", {})),
                )
            except Exception as exc:
                case_result = build_case_result(
                    case,
                    retrieved_files=[],
                    token_count=None,
                    latency_ms=None,
                    trace_id=None,
                    retrieval_strategy=[],
                    requested_routes=[],
                    executed_routes=[],
                    participating_routes=[],
                    effective_flags={},
                    route_diagnostics={},
                    error=str(exc),
                )
            case_results.append(case_result)

        metrics = aggregate_metrics(active_cases, case_results)
        graph_characterization = build_graph_characterization(case_results)
        config_results.append(
            ConfigEvalResult(
                config=config,
                metrics=metrics,
                graph_characterization=graph_characterization,
                case_results=case_results,
                passed_case_count=sum(1 for item in case_results if item.error is None),
                failed_case_count=sum(1 for item in case_results if item.error is not None),
            )
        )

    created_at = utc_now_epoch()
    output_root = (output_dir or Path("eval/reports")).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = str(created_at)
    json_report_path = output_root / f"eval_report_{timestamp}.json"
    markdown_report_path = output_root / f"eval_report_{timestamp}.md"
    latest_json_report_path = output_root / "latest_eval_report.json"
    latest_markdown_report_path = output_root / "latest_eval_report.md"

    run_result = EvalRunResult(
        eval_run_id=str(uuid4()),
        repo_id=repo_id,
        scan_run_id=scan_run_id,
        dataset=dataset.dataset,
        dataset_path=str(dataset_path.resolve()),
        created_at=created_at,
        active_cases=len(active_cases),
        draft_cases=len(draft_cases),
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        vector_quality_valid=vector_quality_valid,
        vector_quality_note=vector_quality_note,
        configs=config_results,
        json_report_path=str(json_report_path),
        markdown_report_path=str(markdown_report_path),
        latest_json_report_path=str(latest_json_report_path),
        latest_markdown_report_path=str(latest_markdown_report_path),
    )

    json_payload = json.dumps(run_result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    markdown_payload = render_markdown_report(run_result)
    json_report_path.write_text(json_payload, encoding="utf-8")
    markdown_report_path.write_text(markdown_payload, encoding="utf-8")
    latest_json_report_path.write_text(json_payload, encoding="utf-8")
    latest_markdown_report_path.write_text(markdown_payload, encoding="utf-8")

    persist_eval_run(settings, run_result)
    return run_result


def persist_eval_run(settings: Settings, result: EvalRunResult) -> None:
    """把 eval run 写入 SQLite。"""

    with connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO eval_runs (id, repo_id, eval_dataset, config_json, results_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.eval_run_id,
                result.repo_id,
                result.dataset,
                json.dumps([config.config.model_dump(mode="json") for config in result.configs], ensure_ascii=False),
                json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
                result.created_at,
            ),
        )
        connection.commit()


def render_markdown_report(result: EvalRunResult) -> str:
    """渲染 Markdown 报告。"""

    lines: list[str] = [
        "# Eval Report",
        "",
        "## Run Metadata",
        "",
        f"- repo_id: `{result.repo_id}`",
        f"- scan_run_id: `{result.scan_run_id}`",
        f"- created_at: `{result.created_at}`",
        f"- dataset: `{result.dataset}`",
        f"- dataset_path: `{result.dataset_path}`",
        f"- active_cases: `{result.active_cases}`",
        f"- draft_cases: `{result.draft_cases}`",
        f"- embedding_provider: `{result.embedding_provider}`",
        f"- embedding_model: `{result.embedding_model}`",
        f"- vector_quality_valid: `{str(result.vector_quality_valid).lower()}`",
        "",
        "## Ablation Summary",
        "",
        "| config | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@5 | MRR | critical_file_hit_rate | critical_file_any_hit_rate | avg_token_count | avg_latency_ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for config_result in result.configs:
        metrics = config_result.metrics
        lines.append(
            "| "
            + " | ".join(
                [
                    config_result.config.name,
                    f"{metrics.recall_at_k[1]:.3f}",
                    f"{metrics.recall_at_k[3]:.3f}",
                    f"{metrics.recall_at_k[5]:.3f}",
                    f"{metrics.recall_at_k[10]:.3f}",
                    f"{metrics.precision_at_k[5]:.3f}",
                    f"{metrics.mrr:.3f}",
                    f"{metrics.critical_file_hit_rate:.3f}",
                    f"{metrics.critical_file_any_hit_rate:.3f}",
                    f"{metrics.avg_token_count:.1f}",
                    f"{metrics.avg_latency_ms:.1f}",
                ]
            )
            + " |"
        )

    for config_result in result.configs:
        graph = config_result.graph_characterization
        lines.extend(
            [
                "",
                f"## Graph Characterization - {config_result.config.name}",
                "",
                f"- graph_participation_rate: `{graph.graph_participation_rate:.3f}`",
                f"- graph_required_case_participation_rate: `{graph.graph_required_case_participation_rate:.3f}`",
                f"- graph_helpful_case_participation_rate: `{graph.graph_helpful_case_participation_rate:.3f}`",
                f"- graph_none_case_participation_rate: `{graph.graph_none_case_participation_rate:.3f}`",
                f"- graph_requested_case_count: `{graph.graph_requested_case_count}`",
                f"- graph_executed_case_count: `{graph.graph_executed_case_count}`",
                f"- graph_participating_case_count: `{graph.graph_participating_case_count}`",
                f"- graph_expectation_counts: `{json.dumps(graph.graph_expectation_counts, ensure_ascii=False, sort_keys=True)}`",
                f"- graph_reason_counts: `{json.dumps(graph.graph_reason_counts, ensure_ascii=False, sort_keys=True)}`",
                "",
                "| case_id | task_hint | graph_expectation | requested_graph | executed_graph | participating_graph | seed_count | hit_count | reason |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for case in config_result.case_results:
            graph_diag = case.route_diagnostics.get("graph", {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        case.case_id,
                        case.task_hint or "general",
                        case.graph_expectation,
                        str(case.graph_requested).lower(),
                        str(case.graph_executed).lower(),
                        str(case.graph_participated).lower(),
                        str(graph_diag.get("seed_count", 0) or 0),
                        str(case.graph_hit_count),
                        case.graph_reason or "(none)",
                    ]
                )
                + " |"
            )

    for config_result in result.configs:
        lines.extend(
            [
                "",
                f"## Critical Misses - {config_result.config.name}",
                "",
            ]
        )
        misses = [case for case in config_result.case_results if case.missed_critical_files]
        if not misses:
            lines.append("- None")
        else:
            for case in misses:
                lines.extend(
                    [
                        f"- case_id: `{case.case_id}`",
                        f"  - query: {case.query}",
                        f"  - missed critical files: {', '.join(case.missed_critical_files)}",
                        f"  - retrieved top files: {', '.join(case.retrieved_files[:5]) if case.retrieved_files else '(none)'}",
                        f"  - retrieval strategy: {', '.join(case.retrieval_strategy) if case.retrieval_strategy else '(none)'}",
                    ]
                )

        lines.extend(
            [
                "",
                f"## Per-case Detail - {config_result.config.name}",
                "",
            ]
        )
        for case in config_result.case_results:
            lines.extend(
                [
                    f"### {case.case_id}",
                    "",
                    f"- status: `{case.status}`",
                    f"- query: {case.query}",
                    f"- graph_expectation: `{case.graph_expectation}`",
                    f"- expected: {', '.join(case.expected_files)}",
                    f"- critical: {', '.join(case.critical_files) if case.critical_files else '(none)'}",
                    f"- helpful: {', '.join(case.helpful_files) if case.helpful_files else '(none)'}",
                    f"- retrieved: {', '.join(case.retrieved_files) if case.retrieved_files else '(none)'}",
                    f"- first relevant rank: `{case.first_relevant_rank}`",
                    f"- token count: `{case.token_count}`",
                    f"- latency_ms: `{case.latency_ms}`",
                    f"- trace_id: `{case.trace_id}`",
                    f"- requested_routes: {', '.join(case.requested_routes) if case.requested_routes else '(none)'}",
                    f"- executed_routes: {', '.join(case.executed_routes) if case.executed_routes else '(none)'}",
                    f"- participating_routes: {', '.join(case.participating_routes) if case.participating_routes else '(none)'}",
                    f"- graph_requested: `{str(case.graph_requested).lower()}`",
                    f"- graph_executed: `{str(case.graph_executed).lower()}`",
                    f"- graph_participated: `{str(case.graph_participated).lower()}`",
                    f"- graph_hit_count: `{case.graph_hit_count}`",
                    f"- graph_reason: `{case.graph_reason}`",
                    f"- effective_flags: `{json.dumps(case.effective_flags, ensure_ascii=False, sort_keys=True)}`",
                    f"- route_diagnostics: `{json.dumps(case.route_diagnostics, ensure_ascii=False, sort_keys=True)}`",
                    f"- errors: {case.error or '(none)'}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Validity Notes",
            "",
            f"- {result.vector_quality_note}",
            "- graph_expectation is a human-authored characterization label and is not a strict pass/fail gate.",
            "- Graph is not required to participate for every query; 'none' cases can legitimately have no graph contribution.",
            "- graph_seeded_by_bm25 is not implemented in this phase and is not reported as graph_only.",
            "- This dataset is a small first-party repository golden dataset, not a general benchmark.",
            "",
        ]
    )
    return "\n".join(lines)
