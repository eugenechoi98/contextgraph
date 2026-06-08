"""SWE-bench Lite 本地定位 smoke runner。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from contextgraph_studio.application.scan_repo import ScanRepoService
from contextgraph_studio.config import Settings
from contextgraph_studio.domain import utc_now_epoch
from contextgraph_studio.eval.configs import resolve_eval_configs
from contextgraph_studio.eval.datasets.repo_checkout import CheckoutRequest, checkout_repo_at_commit, safe_instance_id
from contextgraph_studio.eval.datasets.swebench_lite import SweBenchGroundTruth, SweBenchManifest
from contextgraph_studio.eval.metrics import DEFAULT_KS, dedupe_files
from contextgraph_studio.models.scan import ScanRepoRequest
from contextgraph_studio.services.retriever import retrieve_context_debug


class SweBenchLocalizationCaseResult(BaseModel):
    """单个 SWE-bench instance 的定位结果。"""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    repo: str
    base_commit: str
    config_name: str
    status: str
    checkout_path: str | None = None
    database_path: str
    repo_id: str | None = None
    scan_run_id: str | None = None
    retrieved_files: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)
    critical_files: list[str] = Field(default_factory=list)
    expected_hits: list[str] = Field(default_factory=list)
    missed_critical_files: list[str] = Field(default_factory=list)
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    precision_at_k: dict[int, float] = Field(default_factory=dict)
    reciprocal_rank: float = 0.0
    critical_file_hit: bool = False
    token_count: int | None = None
    trace_id: str | None = None
    retrieval_strategy: list[str] = Field(default_factory=list)
    route_diagnostics: dict[str, dict[str, object]] = Field(default_factory=dict)
    graph_hit_count: int = 0
    error: str | None = None


class SweBenchLocalizationRunResult(BaseModel):
    """一次 SWE-bench localization smoke 的完整报告。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: int
    manifest_path: str
    cache_dir: str
    output_dir: str
    dry_run: bool
    allow_network: bool
    selected_instance_count: int
    max_instances: int
    config_names: list[str]
    case_results: list[SweBenchLocalizationCaseResult]
    json_report_path: str
    markdown_report_path: str

    @property
    def passed_case_count(self) -> int:
        return sum(1 for case in self.case_results if case.status == "passed")

    @property
    def failed_case_count(self) -> int:
        return sum(1 for case in self.case_results if case.status == "failed")


def run_swebench_localization(
    settings: Settings,
    *,
    manifest_path: Path,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
    max_instances: int = 1,
    instance_ids: set[str] | None = None,
    config_names: list[str] | None = None,
    allow_network: bool = False,
    min_free_bytes: int | None = None,
    dry_run: bool = False,
    max_tokens: int | None = None,
) -> SweBenchLocalizationRunResult:
    """运行最多 3 个 SWE-bench case 的本地定位 smoke。"""

    if max_instances < 1 or max_instances > 3:
        raise ValueError("max_instances must be between 1 and 3 for SWE-bench localization smoke.")

    cache_root = (cache_dir or settings.swebench_cache_dir).expanduser().resolve()
    report_root = (output_dir or (cache_root / "reports")).resolve()
    manifest = SweBenchManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    selected = _select_instances(manifest.instances, max_instances=max_instances, instance_ids=instance_ids)
    configs = resolve_eval_configs(config_names or ["bm25_only", "bm25_graph"])
    unsupported = [config.name for config in configs if config.vector_enabled]
    if unsupported:
        raise ValueError(f"SWE-bench localization smoke does not enable vector configs yet: {unsupported}")

    case_results: list[SweBenchLocalizationCaseResult] = []
    for instance in selected:
        db_path = _db_path(cache_root, instance.instance_id)
        for config in configs:
            if dry_run:
                case_results.append(_dry_case(instance, config.name, cache_root, db_path))
                continue
            try:
                checkout = checkout_repo_at_commit(
                    CheckoutRequest(
                        repo=instance.repo,
                        base_commit=instance.base_commit,
                        instance_id=instance.instance_id,
                        cache_dir=cache_root,
                        allow_network=allow_network,
                        min_free_bytes=min_free_bytes
                        if min_free_bytes is not None
                        else settings.swebench_min_free_bytes,
                    )
                )
                runtime_settings = _runtime_settings(settings, db_path, graph_enabled=config.graph_enabled)
                scan = ScanRepoService(runtime_settings).execute(ScanRepoRequest(path=checkout.checkout_path))
                pack, debug = retrieve_context_debug(
                    instance.query,
                    runtime_settings,
                    top_k=max(DEFAULT_KS),
                    task_hint="general",
                    repo_id=scan.repo_id,
                    trace=True,
                    max_tokens=max_tokens,
                )
                retrieved_files = dedupe_files([item.file_path for item in pack.required + pack.supporting])
                case_results.append(
                    _scored_case(
                        instance,
                        config.name,
                        db_path=db_path,
                        checkout_path=checkout.checkout_path,
                        repo_id=scan.repo_id,
                        scan_run_id=scan.scan_run_id,
                        retrieved_files=retrieved_files,
                        token_count=pack.token_estimate,
                        trace_id=pack.trace_id,
                        retrieval_strategy=pack.retrieval_strategy,
                        route_diagnostics=dict(debug.get("route_diagnostics", {})),
                    )
                )
            except Exception as exc:
                case_results.append(
                    _error_case(instance, config.name, db_path=db_path, error=str(exc))
                )

    report_root.mkdir(parents=True, exist_ok=True)
    created_at = utc_now_epoch()
    json_path = report_root / f"swebench_localization_{created_at}.json"
    markdown_path = report_root / f"swebench_localization_{created_at}.md"
    result = SweBenchLocalizationRunResult(
        run_id=str(uuid4()),
        created_at=created_at,
        manifest_path=str(manifest_path.resolve()),
        cache_dir=str(cache_root),
        output_dir=str(report_root),
        dry_run=dry_run,
        allow_network=allow_network,
        selected_instance_count=len(selected),
        max_instances=max_instances,
        config_names=[config.name for config in configs],
        case_results=case_results,
        json_report_path=str(json_path),
        markdown_report_path=str(markdown_path),
    )
    json_path.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_localization_markdown(result), encoding="utf-8")
    return result


def render_localization_markdown(result: SweBenchLocalizationRunResult) -> str:
    """渲染简短 Markdown smoke 报告。"""

    lines = [
        "# SWE-bench Localization Smoke",
        "",
        f"- run_id: `{result.run_id}`",
        f"- dry_run: `{str(result.dry_run).lower()}`",
        f"- allow_network: `{str(result.allow_network).lower()}`",
        f"- selected_instance_count: `{result.selected_instance_count}`",
        f"- configs: `{', '.join(result.config_names)}`",
        "",
        "| instance | config | status | critical_hit | recall@5 | graph_hits | error |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for case in result.case_results:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.instance_id,
                    case.config_name,
                    case.status,
                    str(case.critical_file_hit).lower(),
                    f"{case.recall_at_k.get(5, 0.0):.3f}",
                    str(case.graph_hit_count),
                    (case.error or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _select_instances(
    instances: list[SweBenchGroundTruth],
    *,
    max_instances: int,
    instance_ids: set[str] | None,
) -> list[SweBenchGroundTruth]:
    selected = [item for item in instances if not instance_ids or item.instance_id in instance_ids]
    if not selected:
        raise ValueError("No SWE-bench instances selected.")
    return selected[:max_instances]


def _runtime_settings(settings: Settings, db_path: Path, *, graph_enabled: bool) -> Settings:
    return settings.model_copy(
        update={
            "data_dir": db_path.parent,
            "database_path": db_path,
            "vector_index_enabled": False,
            "hybrid_vector_enabled": False,
            "hybrid_graph_enabled": graph_enabled,
        }
    )


def _db_path(cache_root: Path, instance_id: str) -> Path:
    return (cache_root / "db" / f"{safe_instance_id(instance_id)}.sqlite").resolve()


def _dry_case(
    instance: SweBenchGroundTruth,
    config_name: str,
    cache_root: Path,
    db_path: Path,
) -> SweBenchLocalizationCaseResult:
    return SweBenchLocalizationCaseResult(
        instance_id=instance.instance_id,
        repo=instance.repo,
        base_commit=instance.base_commit,
        config_name=config_name,
        status="dry_run",
        checkout_path=str(cache_root / "repos" / safe_instance_id(instance.instance_id) / "checkout"),
        database_path=str(db_path),
        expected_files=instance.expected_files,
        critical_files=instance.critical_files,
        error="dry_run: checkout, DB init, indexing, and retrieval were skipped.",
    )


def _error_case(
    instance: SweBenchGroundTruth,
    config_name: str,
    *,
    db_path: Path,
    error: str,
) -> SweBenchLocalizationCaseResult:
    return SweBenchLocalizationCaseResult(
        instance_id=instance.instance_id,
        repo=instance.repo,
        base_commit=instance.base_commit,
        config_name=config_name,
        status="failed",
        database_path=str(db_path),
        expected_files=instance.expected_files,
        critical_files=instance.critical_files,
        error=error,
    )


def _scored_case(
    instance: SweBenchGroundTruth,
    config_name: str,
    *,
    db_path: Path,
    checkout_path: str,
    repo_id: str,
    scan_run_id: str,
    retrieved_files: list[str],
    token_count: int,
    trace_id: str | None,
    retrieval_strategy: list[str],
    route_diagnostics: dict[str, dict[str, object]],
) -> SweBenchLocalizationCaseResult:
    expected_set = set(instance.expected_files)
    critical_set = set(instance.critical_files)
    expected_hits = [path for path in retrieved_files if path in expected_set]
    missed_critical = [path for path in instance.critical_files if path not in retrieved_files]
    recall_at_k = {}
    precision_at_k = {}
    for k in DEFAULT_KS:
        top_files = retrieved_files[:k]
        hit_count = sum(1 for path in top_files if path in expected_set)
        recall_at_k[k] = hit_count / len(instance.expected_files) if instance.expected_files else 0.0
        precision_at_k[k] = hit_count / len(top_files) if top_files else 0.0
    first_rank = next((index + 1 for index, path in enumerate(retrieved_files) if path in expected_set), None)
    graph_debug = route_diagnostics.get("graph", {})
    return SweBenchLocalizationCaseResult(
        instance_id=instance.instance_id,
        repo=instance.repo,
        base_commit=instance.base_commit,
        config_name=config_name,
        status="passed",
        checkout_path=checkout_path,
        database_path=str(db_path),
        repo_id=repo_id,
        scan_run_id=scan_run_id,
        retrieved_files=retrieved_files,
        expected_files=instance.expected_files,
        critical_files=instance.critical_files,
        expected_hits=expected_hits,
        missed_critical_files=missed_critical,
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        reciprocal_rank=(1.0 / first_rank) if first_rank else 0.0,
        critical_file_hit=all(path in retrieved_files for path in critical_set) if critical_set else True,
        token_count=token_count,
        trace_id=trace_id,
        retrieval_strategy=retrieval_strategy,
        route_diagnostics=route_diagnostics,
        graph_hit_count=int(graph_debug.get("hit_count", 0) or 0),
    )
