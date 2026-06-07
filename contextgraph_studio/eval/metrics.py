"""文件级评测指标。"""

from __future__ import annotations

from collections import OrderedDict

from contextgraph_studio.eval.models import CaseEvalResult, EvalMetrics, GoldenCase


DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 10)


def dedupe_files(file_paths: list[str]) -> list[str]:
    """按出现顺序对文件路径去重。"""

    return list(OrderedDict.fromkeys(path.replace("\\", "/") for path in file_paths if path))


def build_case_result(
    case: GoldenCase,
    *,
    retrieved_files: list[str],
    token_count: int | None,
    latency_ms: int | None,
    trace_id: str | None,
    retrieval_strategy: list[str],
    requested_routes: list[str] | None = None,
    executed_routes: list[str] | None = None,
    participating_routes: list[str] | None = None,
    effective_flags: dict[str, bool] | None = None,
    route_diagnostics: dict[str, dict[str, object]] | None = None,
    error: str | None = None,
    ks: tuple[int, ...] = DEFAULT_KS,
) -> CaseEvalResult:
    """构造单 case 的评测结果。"""

    retrieved = dedupe_files(retrieved_files)
    expected_set = set(case.expected_files)
    helpful_set = set(case.helpful_files)
    critical_set = set(case.critical_files)

    expected_hits = [path for path in retrieved if path in expected_set]
    helpful_hits = [path for path in retrieved if path in helpful_set]
    missed_critical = [path for path in case.critical_files if path not in retrieved]

    recall_at_k: dict[int, float] = {}
    precision_at_k: dict[int, float] = {}
    for k in ks:
        top_files = retrieved[:k]
        expected_hit_count = sum(1 for path in top_files if path in expected_set)
        recall_at_k[k] = expected_hit_count / len(case.expected_files)
        denominator = len(top_files)
        precision_at_k[k] = expected_hit_count / denominator if denominator else 0.0

    first_relevant_rank = next((index + 1 for index, path in enumerate(retrieved) if path in expected_set), None)
    reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    critical_any_hit = any(path in retrieved for path in critical_set) if critical_set else True
    critical_all_hit = all(path in retrieved for path in critical_set) if critical_set else True

    return CaseEvalResult(
        case_id=case.id,
        query=case.query,
        task_hint=case.task_hint,
        expects_tests=case.expects_tests,
        status="failed" if error else "passed",
        expected_files=case.expected_files,
        critical_files=case.critical_files,
        helpful_files=case.helpful_files,
        retrieved_files=retrieved,
        expected_hits=expected_hits,
        helpful_hits=helpful_hits,
        missed_critical_files=missed_critical,
        first_relevant_rank=first_relevant_rank,
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        reciprocal_rank=reciprocal_rank,
        critical_file_all_hit=critical_all_hit,
        critical_file_any_hit=critical_any_hit,
        token_count=token_count,
        latency_ms=latency_ms,
        trace_id=trace_id,
        retrieval_strategy=retrieval_strategy,
        requested_routes=list(requested_routes or []),
        executed_routes=list(executed_routes or []),
        participating_routes=list(participating_routes or []),
        effective_flags=dict(effective_flags or {}),
        route_diagnostics=dict(route_diagnostics or {}),
        error=error,
    )


def aggregate_metrics(
    cases: list[GoldenCase],
    results: list[CaseEvalResult],
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
) -> EvalMetrics:
    """聚合 active cases 的评测指标。"""

    if not cases:
        raise ValueError("Cannot aggregate metrics without active cases.")
    if len(cases) != len(results):
        raise ValueError("Active cases and case results must have the same length.")

    case_count = len(cases)
    recall_at_k = {
        k: sum(result.recall_at_k[k] for result in results) / case_count
        for k in ks
    }
    precision_at_k = {
        k: sum(result.precision_at_k[k] for result in results) / case_count
        for k in ks
    }
    mrr = sum(result.reciprocal_rank for result in results) / case_count
    critical_file_hit_rate = sum(1 for result in results if result.critical_file_all_hit) / case_count
    critical_file_any_hit_rate = sum(1 for result in results if result.critical_file_any_hit) / case_count

    total_expected = sum(len(case.expected_files) for case in cases)
    total_helpful = sum(len(case.helpful_files) for case in cases)
    expected_hits = sum(len(result.expected_hits) for result in results)
    helpful_hits = sum(len(result.helpful_hits) for result in results)

    successful = [result for result in results if result.error is None]
    avg_token_count = (
        sum((result.token_count or 0) for result in successful) / len(successful)
        if successful
        else 0.0
    )
    avg_latency_ms = (
        sum((result.latency_ms or 0) for result in successful) / len(successful)
        if successful
        else 0.0
    )

    missed_critical = sorted(
        f"{result.case_id}:{file_path}"
        for result in results
        for file_path in result.missed_critical_files
    )

    return EvalMetrics(
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        mrr=mrr,
        critical_file_hit_rate=critical_file_hit_rate,
        critical_file_any_hit_rate=critical_file_any_hit_rate,
        expected_file_hit_rate=(expected_hits / total_expected) if total_expected else 0.0,
        helpful_file_hit_rate=(helpful_hits / total_helpful) if total_helpful else 0.0,
        avg_token_count=avg_token_count,
        avg_latency_ms=avg_latency_ms,
        missed_critical_files=missed_critical,
    )
