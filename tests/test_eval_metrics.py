import pytest

from contextgraph_studio.eval.metrics import aggregate_metrics, build_case_result, build_graph_characterization
from contextgraph_studio.eval.models import GoldenCase


def make_case(**overrides) -> GoldenCase:
    payload = {
        "id": "case_001",
        "query": "verify token auth flow",
        "expected_files": ["auth.py", "session.py"],
        "critical_files": ["auth.py"],
        "helpful_files": ["tests/test_auth.py"],
        "intent_tags": ["retrieval"],
        "expects_tests": "implicit",
        "graph_expectation": "helpful",
        "notes": "Base case.",
        "status": "active",
    }
    payload.update(overrides)
    return GoldenCase.model_validate(payload)


def test_build_case_result_dedupes_files_and_computes_scores() -> None:
    case = make_case()

    result = build_case_result(
        case,
        retrieved_files=["misc.py", "auth.py", "auth.py", "tests/test_auth.py", "session.py"],
        token_count=120,
        latency_ms=25,
        trace_id="trace-1",
        retrieval_strategy=["bm25", "graph"],
    )

    assert result.retrieved_files == ["misc.py", "auth.py", "tests/test_auth.py", "session.py"]
    assert result.expected_hits == ["auth.py", "session.py"]
    assert result.helpful_hits == ["tests/test_auth.py"]
    assert result.recall_at_k[1] == 0.0
    assert result.recall_at_k[3] == 0.5
    assert result.recall_at_k[5] == 1.0
    assert result.precision_at_k[3] == pytest.approx(1 / 3)
    assert result.precision_at_k[5] == pytest.approx(2 / 4)
    assert result.first_relevant_rank == 2
    assert result.reciprocal_rank == 0.5
    assert result.critical_file_all_hit is True
    assert result.critical_file_any_hit is True
    assert result.missed_critical_files == []
    assert result.graph_expectation == "helpful"
    assert result.graph_requested is False
    assert result.graph_executed is False
    assert result.graph_participated is False
    assert result.graph_hit_count == 0


def test_aggregate_metrics_respects_critical_and_helpful_layers() -> None:
    case_a = make_case(id="case_a")
    case_b = make_case(
        id="case_b",
        expected_files=["planner.py"],
        critical_files=["planner.py"],
        helpful_files=["tests/test_planner.py"],
    )
    result_a = build_case_result(
        case_a,
        retrieved_files=["auth.py", "tests/test_auth.py"],
        token_count=100,
        latency_ms=20,
        trace_id="trace-a",
        retrieval_strategy=["bm25"],
    )
    result_b = build_case_result(
        case_b,
        retrieved_files=["misc.py"],
        token_count=None,
        latency_ms=None,
        trace_id=None,
        retrieval_strategy=[],
        error="not found",
    )

    metrics = aggregate_metrics([case_a, case_b], [result_a, result_b])

    assert metrics.recall_at_k[1] == pytest.approx(0.25)
    assert metrics.precision_at_k[1] == pytest.approx(0.5)
    assert metrics.mrr == pytest.approx(0.5)
    assert metrics.critical_file_hit_rate == pytest.approx(0.5)
    assert metrics.critical_file_any_hit_rate == pytest.approx(0.5)
    assert metrics.expected_file_hit_rate == pytest.approx(1 / 3)
    assert metrics.helpful_file_hit_rate == pytest.approx(1 / 2)
    assert metrics.avg_token_count == 100.0
    assert metrics.avg_latency_ms == 20.0
    assert metrics.missed_critical_files == ["case_b:planner.py"]


def test_build_graph_characterization_separates_expectation_groups() -> None:
    required_case = make_case(id="required_case", graph_expectation="required")
    none_case = make_case(
        id="none_case",
        expected_files=["docs.md"],
        critical_files=["docs.md"],
        helpful_files=[],
        graph_expectation="none",
    )

    required_result = build_case_result(
        required_case,
        retrieved_files=["auth.py"],
        token_count=100,
        latency_ms=20,
        trace_id="trace-required",
        retrieval_strategy=["bm25", "graph"],
        requested_routes=["bm25", "graph"],
        executed_routes=["bm25", "graph"],
        participating_routes=["bm25", "graph"],
        route_diagnostics={"graph": {"hit_count": 2, "reason": None, "seed_count": 6}},
    )
    none_result = build_case_result(
        none_case,
        retrieved_files=["docs.md"],
        token_count=90,
        latency_ms=10,
        trace_id="trace-none",
        retrieval_strategy=["bm25"],
        requested_routes=["bm25", "graph"],
        executed_routes=["bm25", "graph"],
        participating_routes=["bm25"],
        route_diagnostics={"graph": {"hit_count": 0, "reason": "no_entity_seed", "seed_count": 0}},
    )

    summary = build_graph_characterization([required_result, none_result])

    assert summary.graph_participation_rate == pytest.approx(0.5)
    assert summary.graph_required_case_participation_rate == pytest.approx(1.0)
    assert summary.graph_helpful_case_participation_rate == pytest.approx(0.0)
    assert summary.graph_none_case_participation_rate == pytest.approx(0.0)
    assert summary.graph_requested_case_count == 2
    assert summary.graph_executed_case_count == 2
    assert summary.graph_participating_case_count == 1
    assert summary.graph_expectation_counts == {"required": 1, "helpful": 0, "none": 1}
    assert summary.graph_reason_counts == {"no_entity_seed": 1}
