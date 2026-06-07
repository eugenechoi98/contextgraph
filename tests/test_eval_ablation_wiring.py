import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.eval.runner import run_eval
from contextgraph_studio.services.indexer import index_repository


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "vector_index_enabled": True,
        "hybrid_vector_enabled": False,
        "hybrid_graph_enabled": True,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-sha256",
        "embedding_dimension": 16,
        "embedding_batch_size": 8,
    }
    defaults.update(overrides)
    return Settings(**defaults)


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
    (repo / "session.py").write_text(
        "def issue_session(user_id: str) -> str:\n"
        "    return user_id.strip()\n",
        encoding="utf-8",
    )


def write_dataset(path: Path) -> None:
    payload = {
        "dataset": "ablation_wiring",
        "cases": [
            {
                "id": "auth_graph_vector",
                "query": "verify token auth flow",
                "task_hint": "security_auth",
                "repo_id": None,
                "expected_files": ["auth.py"],
                "critical_files": ["auth.py"],
                "helpful_files": ["session.py"],
                "intent_tags": ["retrieval"],
                "expects_tests": "implicit",
                "notes": "Known graph seed and deterministic vector smoke.",
                "status": "active",
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _single_case(result, config_name: str):
    config_result = next(item for item in result.configs if item.config.name == config_name)
    assert len(config_result.case_results) == 1
    return config_result.case_results[0]


def test_eval_ablation_wiring_tracks_requested_executed_and_participating_routes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    dataset_path = tmp_path / "dataset.json"
    write_dataset(dataset_path)
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)
    original_flags = (settings.hybrid_vector_enabled, settings.hybrid_graph_enabled)

    result = run_eval(
        settings,
        repo_id=str(indexed["repo_id"]),
        dataset_path=dataset_path,
        config_names=["bm25_only", "bm25_graph", "bm25_vector", "bm25_vector_graph"],
        output_dir=tmp_path / "reports",
    )

    assert settings.hybrid_vector_enabled == original_flags[0]
    assert settings.hybrid_graph_enabled == original_flags[1]
    assert result.vector_quality_valid is False

    bm25_only = _single_case(result, "bm25_only")
    assert bm25_only.requested_routes == ["bm25"]
    assert bm25_only.executed_routes == ["bm25"]
    assert bm25_only.participating_routes == ["bm25"]
    assert bm25_only.effective_flags == {"hybrid_vector_enabled": False, "hybrid_graph_enabled": False}
    assert bm25_only.route_diagnostics["bm25"]["executed"] is True
    assert bm25_only.route_diagnostics["vector"]["reason"] == "disabled_by_ablation"
    assert bm25_only.route_diagnostics["graph"]["reason"] == "disabled_by_ablation"

    bm25_graph = _single_case(result, "bm25_graph")
    assert bm25_graph.requested_routes == ["bm25", "graph"]
    assert "bm25" in bm25_graph.executed_routes
    assert "graph" in bm25_graph.executed_routes
    assert bm25_graph.route_diagnostics["graph"]["executed"] is True
    assert bm25_graph.route_diagnostics["graph"]["seed_count"] > 0
    assert bm25_graph.route_diagnostics["graph"]["hit_count"] > 0
    assert "graph" in bm25_graph.participating_routes

    bm25_vector = _single_case(result, "bm25_vector")
    assert bm25_vector.requested_routes == ["bm25", "vector"]
    assert "vector" in bm25_vector.executed_routes
    assert bm25_vector.route_diagnostics["vector"]["executed"] is True
    assert bm25_vector.route_diagnostics["vector"]["hit_count"] > 0
    assert "vector" in bm25_vector.participating_routes

    bm25_vector_graph = _single_case(result, "bm25_vector_graph")
    assert bm25_vector_graph.requested_routes == ["bm25", "vector", "graph"]
    assert bm25_vector_graph.executed_routes == ["bm25", "vector", "graph"]
    assert "vector" in bm25_vector_graph.participating_routes
    assert "graph" in bm25_vector_graph.participating_routes


def test_eval_ablation_wiring_reports_missing_embeddings_without_blocking_bm25(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    dataset_path = tmp_path / "dataset.json"
    write_dataset(dataset_path)

    index_settings = make_settings(tmp_path, vector_index_enabled=False)
    indexed = index_repository(repo, index_settings)
    eval_settings = make_settings(tmp_path, database_path=index_settings.database_path, data_dir=index_settings.data_dir)

    result = run_eval(
        eval_settings,
        repo_id=str(indexed["repo_id"]),
        dataset_path=dataset_path,
        config_names=["bm25_vector"],
        output_dir=tmp_path / "reports",
    )

    case = _single_case(result, "bm25_vector")
    assert case.requested_routes == ["bm25", "vector"]
    assert case.executed_routes == ["bm25", "vector"]
    assert case.participating_routes == ["bm25"]
    assert case.route_diagnostics["vector"]["executed"] is True
    assert case.route_diagnostics["vector"]["hit_count"] == 0
    assert case.route_diagnostics["vector"]["reason"] == "missing_embeddings"
    assert case.route_diagnostics["bm25"]["executed"] is True
    assert case.error is None
